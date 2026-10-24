import asyncio
import contextlib
import json
import re
import os
import sys
import time
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app_paths import PROJECT_ROOT, ASSETS_ROOT
from config import AppConfig, LLM_MODELS
from image_gen.server_manager import ComfyUIServerManager
from llm.llama_client import LlamaClient, strip_tool_calls, strip_trailing_filler
from llm.server_manager import LlamaServerManager
from memory.unified import UnifiedMemory, MemoryRecord
from memory.conversation import ConversationHistory
from persona.character import Character
from persona.character_context import resolve_honorific, CharacterContext
from persona.gender import g as gpick, gender_of, pair_allows, pair_of
from persona.prompt_context import ContextSpec
from persona.prompt_builder import build_prompt_parts, build_system_prompt
from persona.evolution import CharacterIdentity
from persona import mood as mood_mod
from persona import aftereffects as _aftereffects
from persona import mood_appraisal
from memory.entity_detector import detect_entities
from api.session_manager import (
    ReflectionItem, ReflectionQueue,
    reflection_worker, character_id_from_state,
    _run_reflection, STEP_NAMES, CancelledByActivity,
)
from api.settings_store import load_overlay, read_current, apply_and_save
from api import local_guard
from services.background import (
    AnalyzerConfig, analyzer_loop, app_state_mirror,
    IdleThresholds, ModelLifecycle, ModelState,
    idle_driver, set_lifecycle, get_lifecycle,
    reminder_notify_loop,
)
from services.background.jobs import (
    JobRunner, JobRunnerConfig, MemoryPruneJob, MemoryConsolidationJob,
    ReminderDeliveryJob, ReminderHistoryCleanupJob, ScenarioJob,
)
from services.background.busy import busy_with, session_engaged
from services.background.nvml_probe import (
    get_vram_info, shutdown as nvml_shutdown,
)
from services.log_privacy import priv
from services import gestures as _gestures

_IS_FROZEN = bool(getattr(sys, "frozen", False))
_PROD_COMMANDS = frozenset({"/style"})
_CHAT_TRACE = (not _IS_FROZEN) or os.environ.get("MAIDLINK_CHAT_TRACE") == "1"


def _tool_call_notice(name: str, args_preview: str = "") -> str:
    if _CHAT_TRACE:
        return f"🔧 {name}({args_preview})"
    return f"Вызван инструмент {name}"


_MOOD_IDS = {
    "ровное": 0, "довольное": 1, "растроганное": 2, "воодушевлённое": 3,
    "игривое": 4, "грустное": 5, "обиженное": 6, "встревоженное": 7,
    "смущённое": 8, "раздражённое": 9, "удивление": 10, "испуг": 11, "смех": 12,
}


def _display_mood(identity) -> str:
    if identity is None:
        return mood_mod.NEUTRAL
    rx = (getattr(identity, "reaction_state", "") or "").strip()
    if rx:
        return rx
    live, _ = mood_mod.current_mood(
        getattr(identity, "mood_state", "") or "",
        float(getattr(identity, "mood_intensity", 0.0) or 0.0))
    return live or mood_mod.NEUTRAL


def _reply_mood_id(state) -> int:
    idy = state.get("identity") if isinstance(state, dict) else None
    if idy is None:
        return 0
    st = ((getattr(idy, "reaction_state", "") or "")
          or (getattr(idy, "mood_state", "") or ""))
    import unicodedata as _ud
    return _MOOD_IDS.get(_ud.normalize("NFC", (st or "").strip().lower()), 0)


def _effective_honorific(state) -> str:
    mem = state.get("memory") if isinstance(state, dict) else None
    h = getattr(mem, "user_honorific", "") if mem else ""
    return h or resolve_honorific(state["character"])


_llama_mgr: LlamaServerManager | None = None
_comfy_mgr: ComfyUIServerManager | None = None
_comfy_ready: bool = False
_embed_mgr: LlamaServerManager | None = None
_reflection_queue: ReflectionQueue | None = None


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI):
    global _llama_mgr, _comfy_mgr, _reflection_queue, _embed_mgr, _app_config

    config = AppConfig()
    project_root = PROJECT_ROOT
    load_overlay(config, project_root)
    from config import apply_model_choice
    apply_model_choice(config, config.llm.model_choice)
    from services import setup as _setup_mod
    config.llm.model = _setup_mod.resolve_llm_model(project_root, config.llm.model)
    from services import addons as _addons_mod
    _addons_mod.apply_rating_ceiling(config, project_root)

    _app_config = config

    try:
        queued = _setup_mod.autostart_runtime(project_root, config.llm.model_choice)
        if queued:
            print(f"[lifespan] Докачиваю библиотеки CUDA: {', '.join(queued)}")
    except Exception as e:
        print(f"[lifespan] Докачка библиотек CUDA не стартовала "
              f"({type(e).__name__}: {e})")

    local_guard.publish_token_file(_API_TOKEN, project_root)

    _llama_mgr = LlamaServerManager(config.llm, project_root, ASSETS_ROOT)
    _comfy_mgr = ComfyUIServerManager(config.image_gen, project_root, ASSETS_ROOT)
    _embed_mgr = LlamaServerManager(config.embedder, project_root, ASSETS_ROOT,
                                    log_name="llama-embed")

    _reflection_queue = ReflectionQueue(project_root / config.session.queue_path)
    if len(_reflection_queue) > 0:
        print(f"[lifespan] Reflection queue: {len(_reflection_queue)} pending item(s)")

    loop = asyncio.get_event_loop()
    async def _start_comfy_bg():
        global _comfy_ready
        from services import image_gen_setup as _ig

        def _comfy_can_start() -> bool:
            return _ig.comfy_installed(project_root) and not _ig.is_installing()

        if not _comfy_can_start():
            print("[lifespan] ComfyUI ждёт установки модуля рисования")
            while not _comfy_can_start():
                await asyncio.sleep(5)
        for attempt in (1, 2, 3):
            try:
                await loop.run_in_executor(None, _comfy_mgr.start)
                _comfy_ready = True
                print("[lifespan] ComfyUI готов (фон); llama будет загружена "
                      "по требованию")
                return
            except Exception as e:
                tail = (" — рисование недоступно до перезапуска"
                        if attempt == 3 else " — повтор через 10с")
                print(f"[lifespan] ComfyUI старт (попытка {attempt}/3) не удался "
                      f"({type(e).__name__}: {e}){tail}")
                if attempt < 3:
                    await asyncio.sleep(10)

    async def _start_embed_bg():
        embed_model = project_root / config.embedder.model
        if not embed_model.exists():
            print("[lifespan] Эмбеддер ждёт свою модель (мастер первого запуска)")
            while not embed_model.exists():
                await asyncio.sleep(3)
        try:
            print("[lifespan] Запускаю эмбеддер-сервер (:8002, фон)...")
            await loop.run_in_executor(None, _embed_mgr.start)
            print("[lifespan] Эмбеддер готов")
        except Exception as e:
            print(f"[lifespan] Эмбеддер недоступен ({type(e).__name__}: {e}) — "
                  f"память на substring-поиске")

    if config.image_gen.enabled:
        print("[lifespan] Запускаю ComfyUI в фоне (llama lazy)...")
        comfy_start_task = asyncio.create_task(_start_comfy_bg())
    else:
        print("[lifespan] image_gen выключен — ComfyUI не запускаю (рисование off)")
        comfy_start_task = None
    embed_start_task = asyncio.create_task(_start_embed_bg())
    timer_watch_task = asyncio.create_task(_timer_watcher())

    lc = config.lifecycle
    lifecycle = ModelLifecycle(_llama_mgr, thresholds=IdleThresholds(
        foreground_unloaded_after=lc.foreground_unloaded_after_sec,
        idle_foreground_unloaded_after=lc.idle_foreground_unloaded_after_sec,
        background_unloaded_after=lc.background_unloaded_after_sec,
    ))
    set_lifecycle(lifecycle)

    watchdog_task = asyncio.create_task(_idle_session_watchdog())

    reflection_task = asyncio.create_task(reflection_worker(
        state_provider=lambda: _state if _state else None,
        queue=_reflection_queue,
        project_root=project_root,
        config=config,
    ))

    analyzer_task = asyncio.create_task(analyzer_loop(AnalyzerConfig()))

    lifecycle_task = asyncio.create_task(idle_driver(lifecycle, tick_sec=15.0))

    job_runner = JobRunner(
        lifecycle,
        config=JobRunnerConfig(state_path=project_root / "data" / "job_runs.json"),
    )
    job_runner.register(MemoryPruneJob())
    job_runner.register(MemoryConsolidationJob())
    job_runner.register(ReminderDeliveryJob())
    job_runner.register(ReminderHistoryCleanupJob())
    job_runner.register(ScenarioJob())
    from services.background.jobs.outfit_prepare import OutfitPrepareJob
    job_runner.register(OutfitPrepareJob())
    runner_task = asyncio.create_task(job_runner.run_loop(
        state_provider=lambda: _state if _state else None,
        save_memory=_save_memory,
    ))

    reminder_notify_task = asyncio.create_task(reminder_notify_loop(
        state_provider=lambda: _state if _state else None,
        save_memory=_save_memory,
        tick_sec=60.0,
    ))

    try:
        yield
    finally:
        print("[lifespan] Остановка сервисов...")
        local_guard.retract_token_file(_API_TOKEN, project_root)
        for t in (comfy_start_task, embed_start_task, timer_watch_task):
            if t is not None:
                t.cancel()
        watchdog_task.cancel()
        reflection_task.cancel()
        analyzer_task.cancel()
        lifecycle_task.cancel()
        runner_task.cancel()
        reminder_notify_task.cancel()
        for t in (comfy_start_task, embed_start_task, timer_watch_task,
                  watchdog_task, reflection_task, analyzer_task,
                  lifecycle_task, runner_task, reminder_notify_task):
            if t is None:
                continue
            try:
                await t
            except asyncio.CancelledError:
                pass
        nvml_shutdown()
        try:
            store = _state.get("store") if _state else None
            if store is not None:
                store.close_all()
                print("[lifespan] CharacterStore: все архивы закрыты")
        except Exception as e:
            print(f"[lifespan] CharacterStore close_all error: {e}")
        if _comfy_mgr:
            _comfy_mgr.stop()
            _comfy_mgr.client.close()
        if _embed_mgr:
            try:
                _embed_mgr.stop()
            except Exception:
                pass
        if _llama_mgr:
            _llama_mgr.stop()


PROACTIVE_TTL_SEC = 12 * 60 * 60


async def _expire_proactive_session(state: dict, loop) -> None:
    if not state["history"].messages:
        return
    if state.get("session_processing"):
        return
    if state.get("session_initiated_by") != "proactive":
        return

    lifecycle = get_lifecycle()
    if lifecycle is None:
        print("[watchdog] proactive expiry: lifecycle недоступен, пропускаю")
        return

    print("[watchdog] proactive expiry: загружаю модель для парящего комментария...")
    try:
        await lifecycle.ensure_loaded()
    except Exception as e:
        print(f"[watchdog] proactive expiry: ensure_loaded failed: {e!r}")
        return

    if state.get("session_initiated_by") != "proactive":
        print("[watchdog] proactive expiry: пока грузили модель юзер ответил — отменяю")
        return

    character = state["character"]
    identity = state["identity"]
    memory = state["memory"]
    client = state["client"]
    history = state["history"]

    user_prompt = (
        "[Внутренний триггер: ты сама написала первой (напоминание или своя "
        "инициатива), прошло уже много часов, а ответа так и не получила.]\n\n"
        "Напиши короткий (1-2 предложения) внутренний комментарий — твоя "
        "реакция на то что тебя проигнорировали. Это не сообщение ему, а "
        "твоя мысль про себя, для памяти. Тон — в соответствии с твоим "
        "характером и настроением."
    )

    try:
        embed = client.embed(user_prompt) if hasattr(client, "embed") else None
    except Exception:
        embed = None

    system_prompt = build_system_prompt(
        state["persona"],
        spec=ContextSpec.proactive(),
        memory=memory,
    )

    def _gen():
        return client.chat(
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt,
            thinking=False,
            label="Proactive session expiry",
        )

    text = ""
    try:
        raw = await loop.run_in_executor(None, _gen)
        text = (raw or "").strip()
        import re
        text = re.sub(r"[一-鿿㐀-䶿　-〿]+", "", text).strip()
    except Exception as e:
        print(f"[watchdog] proactive expiry: LLM failed: {e!r}")

    if state.get("session_initiated_by") != "proactive":
        print("[watchdog] proactive expiry: юзер ответил после LLM — отменяю")
        return

    if text and len(text) >= 5:
        history.add("assistant", text, mood=_mood_meta(state))
        print(f"[watchdog] proactive expiry comment: {priv(text, 80)}")
        ws = state.get("active_ws")
        if ws is not None:
            try:
                await ws.send_json({"type": "response", "text": text,
                                    "id_mood": _reply_mood_id(state)})
            except Exception:
                pass
    else:
        print("[watchdog] proactive expiry: пустой LLM-ответ, ставлю заметку")
        history.add("assistant", "(Так и не дождалась ответа.)")

    _bump_proactive_ignore(state)

    try:
        await _finalize_session_sync(
            state, ws=None, loop=loop,
            reason="истёк 12-часовой TTL ожидания ответа",
        )
    except Exception as e:
        print(f"[watchdog] proactive expiry: finalize error: {e!r}")


async def _idle_session_watchdog() -> None:
    BACKGROUND_DROP_AFTER_SEC = 60
    REMINDER_GRACE_SEC = 10 * 60

    while True:
        try:
            await asyncio.sleep(15)
        except asyncio.CancelledError:
            return

        if not _state:
            continue

        s = _state
        if not s.get("history") or not s["history"].messages:
            continue
        if s.get("session_processing"):
            continue

        if s.get("session_initiated_by") == "proactive":
            started = s.get("proactive_session_started_at", 0.0)
            if started > 0 and time.time() - started >= PROACTIVE_TTL_SEC:
                print(f"[watchdog] proactive session {(time.time()-started)/3600:.1f}ч "
                      f"≥ {PROACTIVE_TTL_SEC/3600:.0f}ч TTL — запускаю expiry")
                try:
                    loop = asyncio.get_event_loop()
                    await _expire_proactive_session(s, loop)
                except Exception as e:
                    print(f"[watchdog] _expire_proactive_session error: {e}")
            continue

        last_reminder = s.get("last_reminder_delivered_at", 0.0)
        if last_reminder > 0:
            since_reminder = time.time() - last_reminder
            if since_reminder < REMINDER_GRACE_SEC:
                continue

        diag = app_state_mirror.get_diagnostic()
        if (
            diag["state"] == "BACKGROUND"
            and not diag["is_stale"]
            and diag.get("time_in_state_sec") is not None
            and diag["time_in_state_sec"] >= BACKGROUND_DROP_AFTER_SEC
        ):
            t = diag["time_in_state_sec"]
            n_msgs = len(s['history'].messages)
            print(f"[watchdog] BACKGROUND for {t:.0f}s, finalize session "
                  f"({n_msgs} msgs) с summary")
            try:
                loop = asyncio.get_event_loop()
                lifecycle = get_lifecycle()
                if lifecycle is not None:
                    try:
                        await lifecycle.ensure_loaded()
                    except Exception as e:
                        print(f"[watchdog] ensure_loaded failed: {e!r} — "
                              f"fallback на drop без summary")
                        await _drop_session(s, reason=f"свернуто в трей на {t/60:.0f} мин "
                                                     f"(модель недоступна)")
                        continue
                await _finalize_session_sync(
                    s, ws=None, loop=loop,
                    reason=f"свернуто в трей на {t/60:.0f} мин",
                )
            except Exception as e:
                print(f"[watchdog] BG finalize error: {e}")
            continue

        last_at = s.get("last_user_message_at", 0.0)
        if last_at <= 0:
            continue

        idle_sec = time.time() - last_at
        threshold_min = s["config"].session.idle_timeout_minutes
        if threshold_min <= 0:
            continue
        if idle_sec < threshold_min * 60:
            continue

        print(f"[watchdog] idle {idle_sec/60:.1f} мин > {threshold_min} мин, "
              f"закрываю сессию автоматически")
        try:
            loop = asyncio.get_event_loop()
            await _finalize_session_sync(
                s, ws=None, loop=loop,
                reason=f"idle {idle_sec/60:.0f} мин",
            )
        except Exception as e:
            print(f"[watchdog] ошибка авто-закрытия: {e}")


app = FastAPI(title="MaidLink API", version="0.1.0", lifespan=_lifespan)

_API_TOKEN = local_guard.resolve_api_token()
local_guard.install(app, _API_TOKEN)
local_guard.install_log_redaction()

_project_root = PROJECT_ROOT
_media_dir = _project_root / "image_gen" / "generated"
_media_dir.mkdir(parents=True, exist_ok=True)


class _NoStoreStatic(StaticFiles):
    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-store"
        return resp


app.mount("/media/generated", _NoStoreStatic(directory=str(_media_dir)), name="generated")

_state = {}
_app_config = None


def _refresh_persona(state: dict) -> None:
    state["persona"] = CharacterContext(
        character=state["character"],
        identity=state["identity"],
        character_id=state["character_id"],
    )
    _get_wardrobe(state)
    state["base_appearance"] = None
    try:
        from drawing import BaseAppearance as _BA
        store = state.get("store")
        archive = store.get_archive(state["character_id"]) if store else None
        if archive and archive.has_entry("visual/appearance.yaml"):
            _app_yaml = archive.read_yaml("visual/appearance.yaml")
            state["base_appearance"] = _BA.from_dict(_app_yaml)
            if state.get("identity") is not None:
                from services.self_styling import ensure_design_defaults
                if ensure_design_defaults(state["identity"],
                                          (_app_yaml or {}).get("default_styling")):
                    print("[styling] дефолтный стайлинг дизайна пришит "
                          "к identity")
                from services.self_styling import ensure_design_unlocked
                if ensure_design_unlocked(state["identity"],
                                          (_app_yaml or {}).get("unlocked_styling")):
                    print("[styling] врождённый стайлинг пришит к identity: "
                          f"{(state['identity'].self_styling or {}).get('innate')}")
                from services.self_styling import ensure_base_appearance
                _rid = (getattr(getattr(state.get("config"), "drawing", None),
                                "renderer_id", "") or "sdxl")
                if ensure_base_appearance(state["identity"], _app_yaml, _rid):
                    print("[styling] стайлинг базовой внешности пришит к identity: "
                          f"{(state['identity'].self_styling or {}).get('base')}")
                from services.self_styling import ensure_body
                if ensure_body(state["identity"], _app_yaml,
                               gender_of(state.get("character")), _rid):
                    print("[styling] признаки тела: "
                          f"{(state['identity'].self_styling or {}).get('body')}")
    except Exception as e:
        print(f"[persona] cannot cache base_appearance: {e}")


def _get_state():
    if _state:
        return _state

    project_root = PROJECT_ROOT
    if _app_config is not None:
        config = _app_config
    else:
        config = AppConfig()
        load_overlay(config, project_root)
        from config import apply_model_choice
        apply_model_choice(config, config.llm.model_choice)

    client = LlamaClient(config.llm)
    client.load()
    client.debug_thinking = False
    client.reasoning_mode = config.llm.reasoning_mode
    from config import LLM_MODELS as _LM
    _spec0 = _LM.get(config.llm.model_choice) or {}
    client.fast_post_session = bool(_spec0.get("fast_post", False))

    from persona.character_store import CharacterLockedError, CharacterStore
    store = CharacterStore(
        characters_dir=project_root / "characters",
        baseline_dir=None,
        runtime_cache_dir=project_root / "runtime_cache",
        app_version="0.4.2",
    )
    _reflection_queue.set_key_provider(store.session_key)
    _available_ids = [info["id"] for info in store.list_available()]
    _apply_store_renames(store)
    character_id = config.character_id
    if character_id not in _available_ids:
        character_id = _available_ids[0] if _available_ids else None
    try:
        loaded = store.load(character_id) if character_id is not None else None
    except CharacterLockedError:
        print(f"[lifespan] {character_id}: защищён паролем — ждёт разблокировки")
        loaded = None
        character_id = None
    character = loaded["character"] if loaded else None
    identity = loaded["identity"] if loaded else None

    _chars_dir = project_root / "characters"
    if _chars_dir.exists():
        for char_dir in _chars_dir.iterdir():
            if not char_dir.is_dir():
                continue
            portrait = char_dir / "portrait.png"
            if portrait.exists():
                try:
                    portrait.unlink()
                except OSError as e:
                    print(f"[init] cannot remove stale portrait {portrait}: {e}")

    memory = UnifiedMemory(None, "", client)
    memory.debug = False
    memory.weather_config = config.weather
    if character is not None:
        memory.user_honorific = resolve_honorific(character)
        memory.load_records(loaded["memory_records"])
        memory.load_address_overrides(character)
        if not memory.records:
            memory.bootstrap_from_character(character)

        try:
            from memory.migrations import run_all as _run_migrations
            counters = _run_migrations(memory)
            if any(counters.values()):
                print(f"[migrations] {counters}")
        except Exception as e:
            print(f"[migrations] skipped: {e}")

    from drawing import AssetCatalog, DrawingPipeline, SDXLAdapter, ImageStorage
    drawing_catalog = AssetCatalog.load(project_root, assets_root=ASSETS_ROOT)
    if drawing_catalog.errors:
        print(f"[drawing] catalog loaded with {len(drawing_catalog.errors)} error(s):")
        for err in drawing_catalog.errors[:10]:
            print(f"  - {err}")

    drawing_storage = ImageStorage(
        root_dir=project_root / config.image_gen.output_dir,
        media_url_prefix="/media/generated",
    )
    try:
        from drawing.storage import purge_session_images
        _purged = purge_session_images(project_root, config.image_gen)
        if _purged:
            print(f"[drawing] чистка сгенерированных кадров прошлых запусков: {_purged}")
    except Exception as e:
        print(f"[drawing] purge на старте не удался: {e}")

    from drawing import StyleCatalog
    from app_paths import content_base
    style_catalog = StyleCatalog(
        builtin_yaml=content_base() / "styles" / "builtin.yaml",
        user_dir=project_root / "data" / "styles",
    )
    if style_catalog.errors:
        print(f"[drawing] style catalog loaded with {len(style_catalog.errors)} error(s):")
        for err in style_catalog.errors[:10]:
            print(f"  - {err}")

    drawing_pipeline: object | None = None

    history = ConversationHistory(max_messages=config.llm.max_history_messages,
                                  max_tokens=config.llm.max_history_tokens)

    client.activity_observer = lambda label: _state.__setitem__("llm_activity", label)
    _state.update({
        "config": config,
        "client": client,
        "character": character,
        "character_id": character_id,
        "store": store,
        "memory": memory,
        "identity": identity,
        "history": history,
        "session_start_count": len(memory.records),
        "drawing_catalog": drawing_catalog,
        "drawing_pipeline": drawing_pipeline,
        "drawing_storage": drawing_storage,
        "drawing_style_catalog": style_catalog,
        "last_user_message_at": 0.0,
        "session_processing": False,
        "session_processing_done": asyncio.Event(),
        "active_ws": None,
        "pending_session_events": [],
        "last_reminder_delivered_at": 0.0,
        "runtime_portrait_outfit_id": None,
        "wardrobe": None,
        "wardrobe_preparing": None,
        "style_changing": None,
        "character_default_outfit_id": None,
        "character_outfit_ids": [],
        "session_initiated_by": None,
        "proactive_session_started_at": 0.0,
        "document": None,
        "shown_image_urls": set(),
        "image_source_hint_shown": False,
        "last_image_rows": {},
        "last_shown_image_tags": None,
        "last_reflection_report": "",
    })
    _state["persona"] = None
    if character is not None:
        _refresh_persona(_state)
        _register_character_default_outfit(_state)
    _state["session_processing_done"].set()

    _state["memory"]._session_state_ref = _state
    return _state


_CHARACTER_OUTFIT_FILES = ("visual/default_outfit.yaml", "visual/casual_outfit.yaml")


def _register_character_default_outfit(state: dict) -> None:
    catalog = state.get("drawing_catalog")
    store = state.get("store")
    character_id = state.get("character_id")
    for prev in (state.get("character_outfit_ids") or []):
        if catalog is not None:
            catalog.unregister_outfit(prev)
    state["character_outfit_ids"] = []
    state["character_default_outfit_id"] = None
    state["character_casual_outfit_id"] = None
    if catalog is None or store is None or not character_id:
        return
    try:
        archive = store.get_archive(character_id)
        if not archive:
            return
        registered: list[str] = []
        for fname in _CHARACTER_OUTFIT_FILES:
            if not archive.has_entry(fname):
                continue
            data = archive.read_yaml(fname)
            if not isinstance(data, dict):
                continue
            oid = catalog.register_outfit(data, source=f"{character_id}.maid:{fname}", own=True)
            if not oid:
                continue
            registered.append(oid)
            if fname == "visual/default_outfit.yaml":
                state["character_default_outfit_id"] = oid
            elif fname == "visual/casual_outfit.yaml":
                state["character_casual_outfit_id"] = oid
        state["character_outfit_ids"] = registered
    except Exception as e:
        print(f"[drawing] cannot register outfits for {character_id}: {e}")

    try:
        wardrobe = _get_wardrobe(state)
        if wardrobe is not None:
            state["config"].drawing.active_style_id = wardrobe.get_style()
    except Exception as e:
        print(f"[drawing] cannot load character style for {character_id}: {e}")


_IMAGE_TURN_MARKER = "*отправляет снимок*"

_DRAW_AGAIN_RX = re.compile(
    r"\b(?:ещё|еще)\s+(?:раз(?:ок)?|один|одну|одно|пару|парочку|так(?:ой|ую|ое)|"
    r"снимок|фото|кадр|селфи)\b|\bповтори|\bпересними|\bпеределай|\bзаново\b|"
    r"\bдруг(?:ой|ом) ракурс|\bпо-?другому\b", re.IGNORECASE)


def _is_marker_message(m: dict) -> bool:
    from memory.unified import is_service_note
    return (m.get("mood") or {}).get("kind") == "marker" or is_service_note(m)


def _is_image_turn(m: dict, *, tools: bool = False) -> bool:
    if not isinstance(m, dict) or m.get("role") != "assistant":
        return False
    content = m.get("content")
    if isinstance(content, list):
        if any(isinstance(p, dict) and p.get("type") == "image_url" for p in content):
            return True
    elif isinstance(content, str) and _IMAGE_TURN_MARKER in content:
        return True
    if tools:
        for tc in m.get("tool_calls") or []:
            name = ((tc or {}).get("function") or {}).get("name")
            if name in _IMAGE_ACTION_TOOLS and name != "draw":
                return True
    return False


def _draw_recently_requested(history, current_text: str) -> bool:
    try:
        from tools.draw import DRAW_TOOL
        from memory.unified import _flatten_dialogue_content
        triggers = DRAW_TOOL.triggers
        cur = (current_text or "").lower()
        if any(t in cur for t in triggers):
            return True
        msgs = getattr(history, "messages", None) or []
        users = 0
        delivered_after = False
        for m in reversed(msgs):
            if not isinstance(m, dict) or _is_marker_message(m):
                continue
            if _is_image_turn(m):
                delivered_after = True
                continue
            if m.get("role") != "user":
                continue
            users += 1
            text = _flatten_dialogue_content(m.get("content", "")).lower()
            if any(t in text for t in triggers):
                if not delivered_after:
                    return True
                return bool(_DRAW_AGAIN_RX.search(cur))
            if users >= 2:
                break
        return False
    except Exception:
        return False


def _inject_workflow_prompt(workflow: dict, prompt: str, negative: str = "",
                            seed: int | None = None) -> dict:
    import copy
    import random
    wf = copy.deepcopy(workflow)

    if "17" in wf and wf["17"].get("class_type") == "CLIPTextEncode":
        wf["17"]["inputs"]["text"] = prompt

    if "7" in wf and wf["7"].get("class_type") == "CLIPTextEncode":
        existing = wf["7"]["inputs"].get("text", "")
        if negative:
            wf["7"]["inputs"]["text"] = f"{existing} {negative}".strip()

    if seed is None:
        seed = random.randint(0, 2**63 - 1)
    for node_id, node in wf.items():
        if "seed" in node.get("inputs", {}):
            wf[node_id]["inputs"]["seed"] = seed
            seed = (seed * 16807 + 17) % (2**63 - 1)

    return wf


async def _finalize_session_sync(state: dict, ws: WebSocket | None, loop,
                                  reason: str = "") -> None:
    if not state["history"].messages:
        return
    if state.get("session_processing"):
        return

    state["session_processing"] = True
    state["session_processing_done"].clear()
    try:
        _pending_marks = state.pop("pending_scenario_marks", None) or []
        if _pending_marks:
            from persona import scenarios as _scn
            _idy = state["identity"]
            if not getattr(_idy, "event_log", None):
                _idy.event_log = {}
            for _sid, _sts in _pending_marks:
                _scn.mark_fired(_idy.event_log, _sid, _sts)
            try:
                _idy.save()
            except Exception:
                pass
            print(f"[event] сценарии засчитаны (finalize): "
                  f"{[sid for sid, _ in _pending_marks]}")
        _scenario_close(state, reason="session_end")
        _aftereffect_close(state, reason="session")

        summary_snapshot = []
        reflection_snapshot = []
        for m in state["history"].get_session_log():
            content = m.get("content", "")
            if isinstance(content, list):
                text_parts = [p["text"] for p in content
                              if isinstance(p, dict) and p.get("type") == "text"]
                flat = " ".join(text_parts) if text_parts else "[изображение]"
            else:
                flat = content
            summary_snapshot.append({"role": m["role"], "content": flat})
            reflection_snapshot.append({"role": m["role"], "content": content})

        if _reflection_queue is not None and reflection_snapshot:
            character_id = character_id_from_state(state)
            _reflection_queue.add(ReflectionItem.new(
                character_id=character_id,
                messages=reflection_snapshot,
                reason=reason,
                started_at=float((state.get("stats_session") or {}).get("started_at", 0.0) or 0.0),
            ))
            print(f"[finalize] queued reflection for {character_id} "
                  f"({len(reflection_snapshot)} msgs, queue size: {len(_reflection_queue)})")

        from persona.evolution import generate_session_summary

        def _gen_summary():
            from services.addons import reflection_fragments as _rf
            _cl = state["client"]
            _cl.system_suffix = "\n\n".join(_rf(PROJECT_ROOT))
            try:
                generate_session_summary(
                    state["client"],
                    state["character"],
                    state["identity"],
                    summary_snapshot,
                )
            finally:
                _cl.system_suffix = ""
            state["identity"].save()

        try:
            await loop.run_in_executor(None, _gen_summary)
        except Exception as e:
            print(f"[finalize] сводка сессии не удалась "
                  f"({type(e).__name__}: {e}) — сессия закрывается без summary")

        try:
            from persona.relationship_axes import REL_MIN_TURNS, count_content_turns
            if state.get("stats_session") and count_content_turns(reflection_snapshot) < REL_MIN_TURNS:
                _stats_bump(state, "sessions", -1)
        except Exception as e:
            print(f"[stats] fleeting-session rollback failed: {e}")
        _stats_on_session_end(state)
        state["history"].clear()
        state["session_start_count"] = len(state["memory"].records)
        state["last_user_message_at"] = 0.0
        state["runtime_portrait_outfit_id"] = None
        state["document"] = None
        state["shown_image_urls"] = set()
        state["image_source_hint_shown"] = False
        state["last_image_rows"] = {}
        state["last_shown_image_tags"] = None
        state["fake_image_action_seen"] = False
        state["session_initiated_by"] = None
        state["proactive_session_started_at"] = 0.0
        state["last_reminder_delivered_at"] = 0.0

        event = {
            "type": "session_ended",
            "reason": reason,
            "summary": state["identity"].last_session_summary or "",
            "mood": state["identity"].last_session_mood or "",
        }
        if ws:
            await ws.send_json(event)
        else:
            await _broadcast_or_queue_session_event(state, event)
    finally:
        state["session_processing"] = False
        state["session_processing_done"].set()


async def _drop_session(state: dict, reason: str = "") -> None:
    state["history"].clear()
    state.pop("stats_session", None)
    state["last_user_message_at"] = 0.0
    state["runtime_portrait_outfit_id"] = None
    state["document"] = None
    state["shown_image_urls"] = set()
    state["image_source_hint_shown"] = False
    state["last_image_rows"] = {}
    state["last_shown_image_tags"] = None
    state["fake_image_action_seen"] = False
    state["session_processing"] = False
    state["pending_scenario_marks"] = []
    state["scenario"] = None
    _aftereffect_close(state, reason="drop")
    state.pop("quirk_code", None)
    state.pop("pending_scenario_marker", None)
    state["session_processing_done"].set()
    state["session_initiated_by"] = None
    state["proactive_session_started_at"] = 0.0
    state["last_reminder_delivered_at"] = 0.0

    event = {
        "type": "session_ended",
        "reason": reason or "сессия отброшена",
        "summary": "",
        "mood": "",
    }
    await _broadcast_or_queue_session_event(state, event)


async def _broadcast_or_queue_session_event(state: dict, event: dict) -> None:
    ws = state.get("active_ws")
    if ws is not None:
        try:
            await ws.send_json(event)
            return
        except Exception:
            pass
    state.setdefault("pending_session_events", []).append(event)


_REACTION_TOOLISH_RX = re.compile(
    r"вызыва\w+\s+инструмент|\bdraw\b|<call|intent\s*=|\bshow_image\b|"
    r"\bsearch_anime_art\b|\bsearch_images\b|\bopen_anime_art\b", re.IGNORECASE)
_REACTION_RETRY_NOTE = (
    " (Служебное: снимок УЖЕ доставлен, инструментов в этой реплике нет. Не "
    "описывай вызов, не делай и не обещай новый снимок — просто скажи что-нибудь "
    "о готовом кадре.)")

_REACTION_REDELIVERY_NOTE = (
    " Снимок действительно сделан и доставлен — даже если раньше в разговоре "
    "кадр не приходил, теперь он на месте. Делать его заново, вызывать что-либо "
    "или обещать новую попытку не нужно.")
_PHOTO_MISSING_RX = re.compile(
    r"не\s+(?:приш[её]?л|дош[её]?л|вижу|видно|получил|появил|загруз|отобраз|"
    r"отправил|прислал|скинул|приходи|прикрепи)|"
    r"(?:фото|фотк\w*|снимк\w*|снимок|кадр\w*|картинк\w*|селфи|изображени\w*)\s+"
    r"(?:нет|нету|не\s+было|так\s+и\s+нет)|"
    r"\bнет\s+(?:никако\w+\s+)?(?:фото|фотк\w*|снимк\w*|кадр\w*|картинк\w*|селфи|"
    r"изображени\w*)|"
    r"\bгде\s+(?:же\s+)?(?:фото|фотк\w*|снимок|кадр|картинк\w*|селфи|изображени\w*)|"
    r"ничего\s+(?:нет|не\s+(?:приш|вижу|видно|появил))|\bпусто\b",
    re.IGNORECASE)


def _delivery_was_troubled(dialogue: list, max_user_turns: int = 3) -> bool:
    from memory.unified import _flatten_dialogue_content, is_service_note
    users = 0
    for m in reversed(dialogue or []):
        if not isinstance(m, dict):
            continue
        if is_service_note(m):
            return True
        if m.get("role") != "user" or _is_marker_message(m):
            continue
        users += 1
        if _PHOTO_MISSING_RX.search(_flatten_dialogue_content(m.get("content", ""))):
            return True
        if users >= max_user_turns:
            break
    return False


def _reaction_dialogue(state: dict, dialogue: list, ack: str, honorific: str,
                       gender: str) -> list:
    from memory.unified import is_service_note
    out = []
    for m in dialogue or []:
        if not isinstance(m, dict) or is_service_note(m):
            continue
        role = m.get("role")
        if role == "tool":
            continue
        if role == "assistant" and m.get("tool_calls") and not (m.get("content") or ""):
            continue
        out.append(m)
    if (ack or "").strip():
        out.append({"role": "assistant", "content": ack.strip()})
    name = getattr(state.get("character"), "name", "") or "Ты"
    out.append({
        "role": "user",
        "content": (f"({name} {gpick(gender, 'сделала', 'сделал')} снимок и "
                    f"{gpick(gender, 'отправила', 'отправил')} его: кадр уже в "
                    f"чате, {honorific} на него смотрит.)"),
        "mood": {"kind": "marker", "marker": "image_delivered"},
    })
    return out


def _generate_image_reaction(state: dict, image_path, intent: str = "",
                             ack: str = "", explicit: bool = False,
                             proactive: bool = False, tags: str = "") -> str:
    import base64
    from persona.prompt_builder import build_system_prompt
    from llm.llama_client import strip_tool_calls
    from memory.unified import _flatten_dialogue_content

    honorific = _effective_honorific(state)
    deflect = explicit and state["client"].backend.nsfw_needs_deflection
    static_fallback = "*смущённо отворачивается* ...н-ну вот, держи~"

    img_b64 = None
    if image_path is not None and not deflect and vision_available(state):
        try:
            img_b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
        except Exception as e:
            print(f"[image-reaction] cannot read {image_path}: {e}")

    dialogue = state["history"].get_messages()
    last_user = ""
    for m in reversed(dialogue):
        if m.get("role") != "user" or _is_marker_message(m):
            continue
        last_user = _flatten_dialogue_content(m.get("content", "")).strip()
        break

    _cg = gender_of(state.get("character"))
    parts = [
        f"Твой снимок готов, и ты уже {gpick(_cg, 'отправила', 'отправил')} "
        f"его: кадр в чате, {honorific} "
        "видит его прямо сейчас."
    ]
    if proactive:
        parts.append(
            f" Снимок — ТВОЯ инициатива, его никто не просил: тебе "
            f"{gpick(_cg, 'самой', 'самому')} "
            "захотелось поделиться этим моментом."
        )
    elif dialogue:
        parts.append(" Снимок — часть вашего разговора.")
        if last_user:
            parts.append(f" Его последняя реплика: «{last_user[:200]}».")
    if ack:
        _ack_q = ack if len(ack) <= 600 else "…" + ack[-600:]
        parts.append(
            f" Перед снимком ты {gpick(_cg, 'успела', 'успел')} сказать: "
            f"«{_ack_q}» — это уже "
            "отправлено, продолжай с этого места, не повторяясь."
        )
    if img_b64 is not None:
        if tags:
            parts.append(
                f" Сам кадр приложен, а собирался он по тегам: {tags}. Это "
                "твоя внутренняя справка о том, что́ на нём на самом деле — "
                f"сверься с ней, если что-то вышло не так, как ты "
                f"{gpick(_cg, 'задумывала', 'задумывал')}. "
                "Сами теги и английские слова из них в реплике не упоминай."
            )
        else:
            parts.append(
                " Сам кадр приложен — реагируй на то, что реально вышло, даже "
                f"если вышло не совсем так, как ты "
                f"{gpick(_cg, 'задумывала', 'задумывал')}."
            )
    else:
        if tags:
            parts.append(
                f" Сам кадр тебе сейчас не показан, но собирался он по тегам: "
                f"{tags} — по ним ты знаешь, что́ на нём. Сами теги и "
                "английские слова из них в реплике не упоминай."
            )
        else:
            desc = (intent or ("ты на откровенном снимке" if explicit
                               else "ты на своём снимке")).strip()
            for a, b in (("персонаж ", "ты "), ("персонажа", "тебя"),
                         ("девушка ", "ты ")):
                desc = desc.replace(a, b)
            parts.append(f" На снимке: {desc}.")
    if not proactive and _delivery_was_troubled(dialogue):
        parts.append(_REACTION_REDELIVERY_NOTE)
    parts.append(
        f" Теперь твой ход: ответь так, как {gpick(_cg, 'сама', 'сам')} "
        f"считаешь нужным — в своём "
        f"характере, настроении и по ситуации разговора. Пересказывать кадр "
        f"по пунктам не нужно — {honorific} видит его сам."
    )
    user_text = "".join(parts)

    system_prompt = build_system_prompt(
        state["persona"],
        spec=(ContextSpec.nsfw_reaction() if explicit
              else ContextSpec.image_reaction()),
        memory=state["memory"],
        dialogue=_reaction_dialogue(state, dialogue, ack, honorific, _cg),
        scenario_note=_scenario_block(state, advance=False),
        aftereffect_note=_aftereffect_block(state, advance=False),
        quirks_note=_quirks_block(state),
        current_outfit_label=(None if explicit
                              else _get_current_outfit_label(state)),
    )

    if img_b64 is not None:
        content = [
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            {"type": "text", "text": user_text},
        ]
    else:
        content = user_text

    try:
        response = state["client"].chat(
            messages=[{"role": "user", "content": content}],
            system=system_prompt,
            thinking=state["client"].live_thinking(),
            live_turn=True,
            label="Реакция на снимок",
        )
    except Exception as e:
        print(f"[image-reaction] chat error: {e}")
        return static_fallback if explicit else ""

    reaction = strip_tool_calls(response or "").strip()
    if not reaction or _REACTION_TOOLISH_RX.search(reaction):
        print(f"[image-reaction] tool-call narrative/empty → retry: "
              f"{(response or '')[:80]!r}")
        _retry_text = user_text + _REACTION_RETRY_NOTE
        _retry_content = (content[:-1] + [{"type": "text", "text": _retry_text}]
                          if isinstance(content, list) else _retry_text)
        try:
            response2 = state["client"].chat(
                messages=[{"role": "user", "content": _retry_content}],
                system=system_prompt, thinking=False, live_turn=True,
                label="Реакция на снимок (повтор)")
        except Exception as e:
            print(f"[image-reaction] retry chat error: {e}")
            response2 = ""
        reaction2 = strip_tool_calls(response2 or "").strip()
        if reaction2 and not _REACTION_TOOLISH_RX.search(reaction2):
            reaction = reaction2
        else:
            reaction = "\n".join(
                ln for ln in (reaction2 or reaction).splitlines()
                if not _REACTION_TOOLISH_RX.search(ln)).strip()
    reaction = mood_mod.strip_mood_tag(reaction).strip()
    low = reaction.lower()[:80]
    if deflect and any(m in low for m in ("не могу", "не буду", "неуместно", "извин")):
        return static_fallback
    if explicit and not reaction:
        return static_fallback
    return reaction


def _nsfw_relationship_note(honorific: str, gender: str = "female") -> str:
    return (
        f" Учитывай: ты {gpick(gender, 'пошла', 'пошёл')} на это потому, что "
        f"у вас с {honorific} очень "
        f"близкие, доверительные отношения — это интимный жест между близкими по "
        f"взаимному желанию, не случайность и не то, о чём ты жалеешь. Смущение "
        f"уместно; паника/сожаление/«я не "
        f"{gpick(gender, 'должна', 'должен')} "
        f"{gpick(gender, 'была', 'был')}» — нет."
    )


def _generate_nsfw_ack(state: dict, intent: str) -> str:
    from persona.prompt_builder import build_system_prompt
    from llm.llama_client import strip_tool_calls

    honorific = _effective_honorific(state)
    desc = (intent or "откровенный снимок себя").strip()
    for a, b in (("персонаж ", "ты "), ("персонажа", "тебя"), ("девушка ", "ты ")):
        desc = desc.replace(a, b)
    deflect = state["client"].backend.nsfw_needs_deflection
    _tail = (" Ответь ему КОРОТКО ПЕРЕД снимком: что сейчас сделаешь его / попроси "
             "чуть подождать, в характере (можно с предвкушением или смущением)." if deflect else
             " Ответь ПЕРЕД снимком в характере — с предвкушением, можно смело и игриво.")
    _cg = gender_of(state.get("character"))
    user_text = (
        f"Ты УЖЕ {gpick(_cg, 'согласилась', 'согласился')} сделать {honorific} "
        f"этот смелый снимок ({desc}) и "
        f"сейчас его готовишь — он будет через несколько секунд."
        + _nsfw_relationship_note(honorific, _cg) + _tail +
        " НЕ описывай сам снимок — его ещё нет. Не начинай со своего имени. 1 фраза."
    )
    try:
        system_prompt = build_system_prompt(
            state["persona"],
            spec=ContextSpec.nsfw_reaction(),
            memory=state["memory"],
            dialogue=state["history"].get_messages(),
        )
        response = state["client"].chat(
            messages=[{"role": "user", "content": user_text}],
            system=system_prompt, thinking=state["client"].live_thinking(),
            label="NSFW-подводка", live_turn=True)
    except Exception as e:
        print(f"[nsfw-ack] chat error: {e}")
        return "Момент~ сейчас сделаю…"
    ack = strip_tool_calls(response or "").strip()
    ack = mood_mod.strip_mood_tag(ack).strip()
    low = ack.lower()[:80]
    if (not ack) or (deflect and any(m in low for m in
                     ("не могу", "не буду", "неуместно", "извин"))):
        return "Момент~ сейчас сделаю…"
    return ack


def _order_pending_actions(actions: list[dict]) -> list[dict]:
    return sorted(actions, key=lambda a: 1 if a.get("kind") == "end_session" else 0)


def _build_continuation_observation(state: dict, drained_kinds: list[str]) -> dict | None:
    if "image" in drained_kinds:
        return None
    if "change_outfit" not in drained_kinds:
        return None

    outfit_id = state.get("runtime_portrait_outfit_id")
    catalog = state.get("drawing_catalog")
    outfit_name = outfit_id
    outfits = getattr(catalog, "outfits", None)
    if outfits and outfit_id in outfits:
        outfit_name = outfits[outfit_id].name or outfit_id

    _cg = gender_of(state.get("character"))
    body = (
        f"Ты {gpick(_cg, 'закончила', 'закончил')} переодеваться в "
        f"«{outfit_name}» и {gpick(_cg, 'вернулась', 'вернулся')} к разговору — "
        "портрет уже показывает новый наряд, пользователь его видит. Продолжи "
        "диалог естественной репликой по ситуации и своему характеру — как ты "
        f"{gpick(_cg, 'вернулась', 'вернулся')} бы к собеседнику, только что "
        "переодевшись. Обязательных фраз "
        "нет: спрашивать мнение о наряде не нужно, если разговор к этому не "
        "располагает. Твоя реплика ПЕРЕД уходом переодеваться уже прозвучала "
        "и видна собеседнику — НЕ повторяй и не пересказывай её (фраза-уход "
        "дословно второй раз = поломка); сейчас нужна ТОЛЬКО новая реплика-"
        "возвращение. Отдельный снимок (draw) не нужен — портрет уже новый. "
        "change_outfit повторно НЕ вызывай; другие инструменты — только если "
        "пользователь явно просил что-то ещё, помимо переодевания."
    )
    return {"role": "user", "content": f"<tool_response>\n{body}\n</tool_response>"}


def _merge_image_history_entry(ack: str, comment: str) -> str:
    parts = [x.strip() for x in (ack, _IMAGE_TURN_MARKER, comment)
             if x and x.strip()]
    return "\n".join(parts)


def _build_image_history_entry(ack: str, comment: str, image_path=None):
    if image_path is not None:
        try:
            import base64
            b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
            parts: list[dict] = []
            if (ack or "").strip():
                parts.append({"type": "text", "text": ack.strip()})
            parts.append({"type": "image_url",
                          "image_url": {"url": f"data:image/png;base64,{b64}"}})
            if (comment or "").strip():
                parts.append({"type": "text", "text": comment.strip()})
            return parts
        except Exception as e:
            print(f"[drawing] cannot embed snapshot into history: {e}")
    return _merge_image_history_entry(ack, comment)


def _apply_mood_from_response(state: dict, raw_text: str,
                              reasoning: str = "") -> None:
    parsed = mood_mod.parse_mood_tag(raw_text or "")
    if parsed is None and reasoning:
        parsed = mood_mod.parse_mood_tag(reasoning)
    if parsed is None:
        return
    identity = state.get("identity")
    if identity is None:
        return
    state_name, intensity = parsed
    st, inten, ts = mood_mod.apply_mood(state_name, intensity, now=time.time())
    if mood_mod.is_reaction(st):
        identity.reaction_state = st
        identity.reaction_intensity = inten
        print(f"[mood] {state.get('character_id','?')}: {st} ({inten:.2f}) [реакция, тег]")
        return
    identity.mood_state = st
    identity.mood_intensity = inten
    identity.mood_updated_at = ts
    print(f"[mood] {state.get('character_id','?')}: {st} ({inten:.2f})")


def _render_semantic_confirmation(state: dict, facts: str) -> str:
    from persona.prompt_builder import build_system_prompt
    from llm.llama_client import strip_tool_calls
    honorific = _effective_honorific(state)
    sysp = build_system_prompt(
        state["persona"], spec=ContextSpec.action_confirmation(),
        memory=state["memory"], dialogue=state["history"].get_messages())
    user = (
        f"Действие, которое ты только что затеяла для {honorific}, успешно выполнено.\n"
        f"Итог (факт): {facts}\n\n"
        f"Это ФИНАЛЬНОЕ подтверждение пользователю. Сообщи {honorific} КОРОТКО и "
        f"естественно, в своём стиле, что готово — одной фразой, ОБЯЗАТЕЛЬНО с "
        f"конкретикой из факта выше (что именно сделано). Секунду назад ты уже коротко ответила, "
        f"что приняла просьбу (см. недавний диалог) — НЕ повторяй ту реплику и НЕ "
        f"начинай теми же словами; здесь добавь именно ИТОГ. Не начинай со своего имени."
    )
    try:
        resp = state["client"].chat(
            messages=[{"role": "user", "content": user}],
            system=sysp, thinking=False, label="semantic:confirm")
    except Exception as e:
        print(f"[semantic:confirm] chat error: {e}")
        return ""
    out = strip_tool_calls(resp or "").strip()
    out = mood_mod.strip_mood_tag(out).strip()
    low = out.lower()[:60]
    if not out or any(m in low for m in ("не могу", "не буду", "извин")):
        return ""
    return out


async def _process_semantic_pending(state: dict, ws, loop, action: dict) -> None:
    from tools.semantic import process_semantic_action, SemanticDeps
    import time as _t
    client = state.get("client")
    if client is None:
        return
    tool_name = action.get("tool", "?")

    def _llm_chat(system: str, user: str) -> str:
        return client.chat(
            messages=[{"role": "user", "content": user}],
            system=system, thinking=False, label=f"semantic:{tool_name}")

    deps = SemanticDeps(
        memory=state.get("memory"),
        now=_t.time(),
        debug=bool(state.get("debug_llm")),
        persona=state.get("persona"),
    )
    res = None
    out_msg = ""
    in_character = False
    lifecycle = get_lifecycle()
    try:
        async with lifecycle.using():
            res = await loop.run_in_executor(
                None,
                lambda: process_semantic_action(action, llm_chat=_llm_chat, deps=deps))
            out_msg = res.message
            if res.ok and res.facts:
                conf = await loop.run_in_executor(
                    None, lambda: _render_semantic_confirmation(state, res.facts))
                if conf:
                    out_msg = conf
                    in_character = True
    except Exception as e:
        print(f"[semantic:{tool_name}] dispatch error: {type(e).__name__}: {e}")
        return

    if out_msg:
        try:
            _conf_stats = state["client"].last_stats if in_character else None
            await ws.send_json({"type": "response", "text": out_msg,
                                "id_mood": _reply_mood_id(state)})
            _hist_add_assistant(state, out_msg)
            await _send_reply_stats(state, ws, _conf_stats)
        except Exception:
            pass
    if res is not None and res.ok and res.data.get("record_id"):
        try:
            _save_memory()
        except Exception:
            pass
    print(f"[semantic:{tool_name}] {'ok' if (res and res.ok) else 'fail'} "
          f"(confirm={'in-character' if in_character else 'template' if out_msg else 'none'})")


async def _process_pending_actions(state: dict, ws: WebSocket, loop) -> None:
    memory = state["memory"]
    actions = _order_pending_actions(list(memory.pending_actions))
    memory.pending_actions.clear()

    if not actions:
        return

    config = state["config"]

    for action in actions:
        kind = action.get("kind")

        if kind == "end_session":
            reason = action.get("reason") or "LLM tool"
            await _finalize_session_sync(state, ws, loop, reason=reason)
            continue

        if kind == "change_outfit":
            await _handle_change_outfit_action(state, ws, loop, action)
            continue

        if kind == "semantic":
            await _process_semantic_pending(state, ws, loop, action)
            continue

        if kind == "url_opened":
            try:
                await ws.send_json({"type": "system",
                                    "text": f"🌐 Открыто в браузере: {action.get('url', '')}"})
            except Exception:
                pass
            continue

        if kind == "app_opened":
            try:
                await ws.send_json({"type": "system",
                                    "text": f"🖥 Открыто приложение: {action.get('name', '')}"})
            except Exception:
                pass
            continue

        if kind == "image_url":
            url = action.get("url", "")
            try:
                from urllib.parse import urlparse as _up
                dom = _up(url).hostname or "интернет"
            except Exception:
                dom = "интернет"
            from services.web import media_kind_of
            _mk = media_kind_of(url)
            try:
                if _mk == "video":
                    await ws.send_json({"type": "system",
                                        "text": f"🎬 Видео из интернета ({dom})"})
                    await ws.send_json({"type": "image",
                                        "url": _register_webimg(url),
                                        "media": "video"})
                else:
                    await ws.send_json({"type": "system",
                                        "text": f"🖼 Картинка из интернета ({dom})"})
                    await ws.send_json({"type": "image",
                                        "url": _register_webimg(url)})
            except Exception:
                pass
            continue

        if kind == "video_embed":
            try:
                await ws.send_json({"type": "system",
                                    "text": "▶️ Видео с YouTube"})
                await ws.send_json({
                    "type": "video_embed",
                    "video_id": action.get("video_id", ""),
                    "url": action.get("url", ""),
                })
            except Exception:
                pass
            continue

        if kind != "image":
            await ws.send_json({
                "type": "system",
                "text": f"Неизвестный pending action: {kind!r}",
            })
            continue

        intent = action.get("intent", "").strip()
        if not intent:
            continue

        await _send_pending_portrait_reveal(state, ws)

        ack = (state.pop("pending_image_ack", "") or "").strip()

        if not config.image_gen.enabled:
            await ws.send_json({"type": "system",
                                 "text": "🚫 Генерация картинок выключена в настройках."})
            continue

        try:
            pipeline = _ensure_drawing_pipeline(state)
        except Exception as init_err:
            await ws.send_json({
                "type": "system",
                "text": f"❌ Drawing pipeline недоступен: {init_err}",
            })
            continue

        request = _build_drawing_request(state, intent)

        import time as _img_t
        _img_t0 = _img_t.monotonic()
        state["drawing_active"] = True

        try:
            compose_draw = state["client"].backend.compose_drawing
            compose_think = compose_draw and state["client"].live_thinking()
            def llm_chat(system: str, user: str) -> str:
                return state["client"].chat(
                    messages=[{"role": "user", "content": user}],
                    system=system, thinking=compose_think, label="Draw: tag selection",
                    live_turn=True, lang_guard=False)

            lifecycle = get_lifecycle()
            async with lifecycle.using():
                selection = await loop.run_in_executor(
                    None,
                    lambda: pipeline.select_freeform(request, llm_chat=llm_chat,
                                                     compose=compose_draw),
                )

            def _swap_to_render():
                _llama_mgr.stop()
                _llama_mgr.wait_vram_released()

            def _swap_to_llm():
                _release_comfy()
                _llama_mgr.start()

            result = await loop.run_in_executor(
                None,
                lambda: pipeline.render_freeform(
                    selection, request,
                    before_render=_swap_to_render,
                    after_render=_swap_to_llm,
                ),
            )

            if result.is_refusal:
                await ws.send_json({
                    "type": "response",
                    "text": result.refusal_reason,
                    "id_mood": _reply_mood_id(state),
                })
                _hist_add_assistant(state, result.refusal_reason)
                await _send_reply_stats(state, ws)
                continue

            if result.is_error:
                await ws.send_json({
                    "type": "system",
                    "text": f"❌ Ошибка генерации: {result.error}",
                })
                continue

            last_verdict = result.critic_verdicts[-1] if result.critic_verdicts else None
            if last_verdict is not None and last_verdict.should_regen(
                request.critic_soft_threshold
            ):
                from drawing import request_apology
                _apology_sysp = build_system_prompt(
                    state["persona"], spec=ContextSpec.action_confirmation(),
                    memory=state["memory"], dialogue=state["history"].get_messages())
                hint = request.refusal_style_hint
                apology = await loop.run_in_executor(
                    None,
                    lambda: request_apology(
                        state["client"],
                        system_prompt=_apology_sysp,
                        refusal_style_hint=hint,
                    ),
                )
                _apology_stats = state["client"].last_stats if apology else None
                if not apology:
                    apology = ("Что-то у меня сегодня не получается красиво "
                               "нарисовать — давай попробуем позже.")
                await ws.send_json({"type": "response", "text": apology,
                                    "id_mood": _reply_mood_id(state)})
                _hist_add_assistant(state, apology)
                await _send_reply_stats(state, ws, _apology_stats)
                print(f"[drawing] vision critic exhausted retries: "
                      f"{len(result.critic_verdicts)} attempts, "
                      f"last verdict={last_verdict.verdict} "
                      f"issues={last_verdict.issues}")
                continue

            from drawing.tag_rounds import is_explicit_selection
            _nsfw_img = bool(action.get("nsfw")) or is_explicit_selection(
                selection.get("tags") or (), selection.get("remove") or ())
            if _nsfw_img:
                mark_body_context(state)
                _quirks_raise(state, "explicit_image")
            _record_snapshot_state(state, selection, request.current_portrait_outfit_id)
            _record_recent_snapshot(state, selection, request.user_intent)

            storage = state["drawing_storage"]
            _img_gen_s = round(_img_t.monotonic() - _img_t0, 1)
            try:
                stored = storage.save_from_pipeline(
                    result,
                    character_id=state["character_id"],
                    intent=intent,
                    rating="nsfw" if _nsfw_img else "sfw",
                )
            except Exception as e:
                print(f"[drawing] storage.save failed: {e}; fallback to raw path")
                await ws.send_json({
                    "type": "image",
                    "url": f"/media/generated/{result.image_path.name}",
                    "prompt": (result.assembled_prompt.positive[:200]
                               if result.assembled_prompt else intent),
                    "gen_seconds": _img_gen_s,
                })
                path = result.image_path
            else:
                await ws.send_json({
                    "type": "image",
                    "url": stored.media_url,
                    "prompt": (result.assembled_prompt.positive[:200]
                               if result.assembled_prompt else intent),
                    "gen_seconds": _img_gen_s,
                })
                path = stored.image_path
            _stats_bump(state, "images")
            _achievement_award(state, "first_photo")

            _content_tags = (result.assembled_prompt.content_tags
                             if result.assembled_prompt is not None else "")
            state.pop("turn_timings", None)
            comment = ""
            _comment_stats = None
            try:
                comment = await loop.run_in_executor(
                    None, lambda: _generate_image_reaction(
                        state, path, intent=intent, ack=ack,
                        explicit=_nsfw_img,
                        proactive=bool(action.get("proactive")),
                        tags=_content_tags))
                _comment_stats = state["client"].last_stats if comment else None
                if (comment and getattr(state["config"].session, "grammar_polish", False)
                        and state["client"].backend.needs_grammar_pass):
                    from persona.grammar import correct_grammar
                    _gpol = await loop.run_in_executor(
                        None,
                        lambda c=comment: correct_grammar(
                            state["client"], c, character=state["character"],
                            dialogue=state["history"].get_messages(),
                            honorific=(getattr(state["memory"], "user_honorific", None)
                                       or resolve_honorific(state["character"]))))
                    if _gpol and _gpol != comment:
                        await ws.send_json({"type": "debug", "tag": "grammar",
                                            "data": {"before": comment, "after": _gpol}})
                        comment = _gpol
                if comment:
                    await ws.send_json({
                        "type": "response",
                        "text": comment,
                        "id_mood": _reply_mood_id(state),
                    })
            except Exception as comment_err:
                await ws.send_json({
                    "type": "system",
                    "text": f"⚠️ Комментарий не получился: {comment_err}",
                })
            _embed_path = path if vision_available(state) else None
            entry = _build_image_history_entry(ack, comment, image_path=_embed_path)
            if entry:
                _hist_add_assistant(state, entry)
            await _send_reply_stats(state, ws, _comment_stats)

        except Exception as e:
            await ws.send_json({
                "type": "system",
                "text": f"❌ Ошибка генерации: {e}",
            })
            try:
                await loop.run_in_executor(None, _release_comfy)
                if not _llama_mgr.is_responsive(timeout_sec=0.5):
                    await loop.run_in_executor(None, _llama_mgr.start)
            except Exception as recovery_err:
                await ws.send_json({
                    "type": "system",
                    "text": f"❌ Recovery error: {recovery_err}",
                })
        finally:
            state.pop("drawing_active", None)


async def _handle_change_outfit_action(state: dict, ws: WebSocket, loop, action: dict) -> None:
    from persona.evolution import compute_relationship_tier
    from drawing.assets import tier_ge, effective_required_tier

    outfit_id = (action.get("outfit_id") or "").strip()
    config = state["config"]
    drawing = config.drawing

    catalog = state.get("drawing_catalog")
    if catalog is None or outfit_id not in catalog.outfits:
        await ws.send_json({
            "type": "system",
            "text": f"❌ Костюм {outfit_id!r} не найден в каталоге.",
        })
        return

    character = state["character"]
    character_id = state["character_id"]
    archetype = getattr(character, "archetype", "") or ""
    outfit_policy = getattr(character, "outfit_policy", None)
    current_tier = state["persona"].tier

    outfit = catalog.outfits[outfit_id]
    if not tier_ge(current_tier, drawing.outfit_change_min_tier):
        await ws.send_json({
            "type": "system",
            "text": "❌ Состояние изменилось — переодевание сейчас не пройдёт.",
        })
        return
    if outfit_policy:
        eff_tier = effective_required_tier(
            outfit.required_tier, list(outfit.tags),
            character_tag_gates=outfit_policy.tag_tier_gates,
            character_blocked_tags=list(outfit_policy.blocked_tags),
        )
        if eff_tier is None or not tier_ge(current_tier, eff_tier):
            await ws.send_json({
                "type": "system",
                "text": "❌ Состояние изменилось — этот костюм сейчас недоступен.",
            })
            return

    wardrobe = _get_wardrobe(state)
    outfit_name = outfit.name or outfit_id
    if wardrobe is None or not wardrobe.is_prepared(outfit_id):
        if wardrobe is not None:
            wardrobe.enqueue(outfit_id)
        await ws.send_json({
            "type": "system",
            "text": (f"👗 Наряд «{outfit_name}» ещё не подготовлен — поставлен "
                     f"в очередь подготовки (см. панель гардероба)."),
        })
        return

    state["runtime_portrait_outfit_id"] = outfit_id
    state.pop("snapshot_state", None)
    state["pending_portrait_reveal"] = {
        "character_id": character_id,
        "text": (f"👗 {character.name} "
                 f"{gpick(gender_of(character), 'переоделась', 'переоделся')} "
                 f"в «{outfit_name}»"),
    }

    try:
        from drawing.face_crop import crop_face_avatar
        cdir = PROJECT_ROOT / "characters" / character_id
        avatar_target = cdir / f"{_avatar_basename(state)}.png"
        portrait_src = cdir / f"{_portrait_basename(state)}.png"
        if not avatar_target.exists() and portrait_src.exists():
            await loop.run_in_executor(
                None, lambda: crop_face_avatar(portrait_src, avatar_target))
    except Exception as e:
        print(f"[wardrobe] avatar crop failed ({outfit_id}): {e}")


async def _send_reply_stats(state: dict, ws, gen_stats=None) -> None:
    from memory.conversation import estimate_tokens as _et
    try:
        _full_ctx = 0
        for _i, _a in enumerate(state["config"].llm.server_launch_args):
            if _a == "-c":
                _full_ctx = int(state["config"].llm.server_launch_args[_i + 1])
                break
    except Exception:
        _full_ctx = 0
    _sys_tokens = _et(state.get("last_prompt") or "")
    _hist_tokens = state["history"].window_tokens()
    payload = {
        "type": "stats",
        "ctx_tokens": _sys_tokens + _hist_tokens,
        "ctx_budget": _full_ctx or state["history"].max_tokens,
        "hist_tokens": _hist_tokens,
        "hist_budget": state["history"].max_tokens,
    }
    if gen_stats:
        payload.update(
            tokens=gen_stats.tokens,
            tps=round(gen_stats.tokens_per_second, 1),
            ttft=round(gen_stats.time_to_first_token, 2),
            gen=round(gen_stats.elapsed_seconds, 1),
            total=round(gen_stats.elapsed_seconds, 1),
        )
        if getattr(gen_stats, "gen_tps", 0):
            payload["gen_tps"] = round(gen_stats.gen_tps, 1)
        if getattr(gen_stats, "prefill_tps", 0):
            payload["prefill_tps"] = round(gen_stats.prefill_tps)
        _maybe_probe_slow_turn(state, gen_stats)
    import time as _t_mod
    _tt = state.pop("turn_timings", None)
    if _tt and (_t_mod.monotonic() - _tt.get("t0", 0)) < 600:
        if _tt.get("mood"):
            payload["prep_mood"] = round(_tt["mood"], 2)
        if _tt.get("recall"):
            payload["prep_recall"] = round(_tt["recall"], 2)
        payload["total"] = round(_t_mod.monotonic() - _tt["t0"], 1)
    try:
        await ws.send_json(payload)
    except Exception:
        pass


_last_vram_probe_ts: float = 0.0


def _maybe_probe_slow_turn(state: dict, gen_stats) -> None:
    global _last_vram_probe_ts
    gen_tps = float(getattr(gen_stats, "gen_tps", 0) or 0)
    if gen_tps <= 0 or getattr(gen_stats, "tokens", 0) < 32:
        return
    try:
        choice = state["config"].llm.model_choice
        expected = float(LLM_MODELS.get(choice, {}).get("expected_tps") or 0)
    except Exception:
        expected = 0.0
    if not expected or gen_tps >= expected * 0.5:
        return
    now = time.monotonic()
    if now - _last_vram_probe_ts < 120:
        return
    _last_vram_probe_ts = now
    pid = _llama_mgr.pid if _llama_mgr is not None else None

    def _probe():
        from services.vram_probe import slow_turn_verdict
        try:
            print(slow_turn_verdict(pid, gen_tps, expected))
        except Exception as e:
            print(f"[vram] probe failed: {type(e).__name__}: {e}")

    try:
        asyncio.get_running_loop().run_in_executor(None, _probe)
    except RuntimeError:
        pass


_SEARCH_TRACE_TOOLS = frozenset({"search_anime_art", "search_images", "web_search"})


def _trace_result_short(name: str, result_short: str) -> str:
    if name in _SEARCH_TRACE_TOOLS:
        return ("(выдача была показана тебе в тот момент и УСТАРЕЛА — для "
                "нового показа сделай НОВЫЙ поиск)")
    return result_short


_IMAGE_ACTION_TOOLS = frozenset({"draw", "show_image", "search_anime_art",
                                 "search_images", "open_anime_art"})

_PHOTO_WORD = r"(?:снимок|селфи|фотографи[яю]|фото(?![а-я])|картинк\w+)"
_FAKE_IMAGE_NEW_RX = [
    re.compile(r"\*[^*\n]{0,80}?(?:отправля\w*|шлёт|шлю|посыла\w*|высыла\w*|"
               r"скидыва\w*|прикрепля\w*|фотографиру\w*|снимает|делает)"
               r"[^*\n]{0,50}?(?:снимок|снимк\w+|фото\w*|селфи|картинк\w+|камер\w+)"
               r"[^*\n]{0,80}?\*", re.IGNORECASE),
    re.compile(r"\b(?:держи|лови)\b[^.!?\n]{0,12}?\b" + _PHOTO_WORD, re.IGNORECASE),
    re.compile(r"\b(?:отправляю|прикрепляю|скидываю|посылаю|высылаю|шлю)"
               r"\b[^.!?\n]{0,30}?\b" + _PHOTO_WORD, re.IGNORECASE),
]
_FAKE_IMAGE_REF_RX = [
    re.compile(r"\bвот\b[^.!?\n]{0,12}?\b" + _PHOTO_WORD, re.IGNORECASE),
    re.compile(r"\b(?:отправил(?:а)?|прислал(?:а)?|прикрепил(?:а)?|"
               r"скинул(?:а)?|выслал(?:а)?|послал(?:а)?)"
               r"\b[^.!?\n]{0,30}?\b" + _PHOTO_WORD, re.IGNORECASE),
]
_FAKE_IMAGE_RX = _FAKE_IMAGE_NEW_RX + _FAKE_IMAGE_REF_RX
_FAKE_REF_NEW_WORD_RX = re.compile(
    r"\b(?:ещё|еще|нов(?:ый|ое|ую|ая)|втор(?:ой|ое|ую|ая)|друг(?:ой|ое|ую|ая))\b",
    re.IGNORECASE)


def _detect_fake_image_action(text: str, delivered_recently: bool = False) -> str | None:
    for rx in _FAKE_IMAGE_NEW_RX:
        m = rx.search(text or "")
        if m:
            return m.group(0)
    for rx in _FAKE_IMAGE_REF_RX:
        m = rx.search(text or "")
        if m and (not delivered_recently or _FAKE_REF_NEW_WORD_RX.search(m.group(0))):
            return m.group(0)
    return None


def _recent_image_delivered(history, max_user_turns: int = 3) -> bool:
    users = 0
    for m in reversed(getattr(history, "messages", None) or []):
        if not isinstance(m, dict) or _is_marker_message(m):
            continue
        if m.get("role") == "user":
            users += 1
            if users > max_user_turns:
                break
        elif _is_image_turn(m, tools=True):
            return True
    return False


def _fake_action_nudge(gender: str, delivered_recently: bool = False) -> str:
    if delivered_recently:
        return (
            f"(служебное, Господин этого не видит: в этой реплике ты "
            f"{gpick(gender, 'описала', 'описал')} отправку НОВОГО снимка/картинки "
            "ТЕКСТОМ — так ничего не отправляется, нового изображения Господин НЕ "
            "получил. Прежний снимок, уже доставленный в чат, на месте — о нём "
            "говорить можно. Отправить ещё один = вызвать инструмент draw (intent = "
            "что на снимке); показать найденную в интернете картинку = поиск "
            "(search_anime_art/search_images) и show_image(number=N) из СВЕЖЕЙ "
            "выдачи. Если отправлять нечего — перепиши ответ БЕЗ обещания нового "
            "изображения. Ответь заново.)"
        )
    return (
        f"(служебное, Господин этого не видит: ты "
        f"{gpick(gender, 'описала', 'описал')} отправку снимка/картинки "
        "ТЕКСТОМ — так ничего не отправляется, Господин НЕ получил изображения. "
        "Реально отправить свой снимок = вызвать инструмент draw (intent = что на "
        "снимке). Показать найденную в интернете картинку = поиск "
        "(search_anime_art/search_images) и show_image(number=N) из СВЕЖЕЙ выдачи. "
        "Если отправлять нечего — перепиши ответ БЕЗ обещания изображения. "
        "Ответь заново.)"
    )

_FAKE_ACTION_INOCULATION = (
    "(снимок не был отправлен — описание действия текстом ничего не делает; "
    "реальная отправка изображения происходит только вызовом инструмента draw "
    "или show_image)"
)
_FAKE_ACTION_INOCULATION_NEW = (
    "(новый снимок не был отправлен — описание действия текстом ничего не "
    "делает; прежний, уже доставленный снимок остаётся в чате; реальная "
    "отправка изображения происходит только вызовом инструмента draw или "
    "show_image)"
)

_DRAW_REASK_RX = re.compile(
    r"\b(?:хочешь|хотите|хочется|мне|давай я|может(?:\s+быть)?|точно|правда)\b"
    r"[^.!?\n]{0,50}?"
    r"\b(?:сфотографир\w+|сфотка\w+|сниму|снять|снимать|нарису\w+|нарисовать|"
    r"сдела(?:ю|ть)\s+(?:снимок|фото|селфи))"
    r"[^!?\n]{0,30}\?", re.IGNORECASE)

_PHOTO_OFFER_RX = re.compile(
    r"\b(?:хочешь|хотите|могу|давай|показать)\b[^.!?\n]{0,60}?"
    r"\b(?:сфотографир\w+|сниму|снимок|селфи|нарису\w+|фото(?![а-я]))"
    r"[^?\n]{0,30}\?", re.IGNORECASE)

_CONSENT_WORDS = frozenset(
    "да ага угу конечно давай хочу можно обязательно валяй пожалуйста ну и очень".split())
_CONSENT_BLOCKERS = ("не", "но", "потом", "позже", "завтра", "сначала",
                     "подожди", "погоди")


def _is_short_consent(text: str) -> bool:
    words = re.findall(r"[а-яё]+", (text or "").lower())
    if not words or len(words) > 5:
        return False
    if any(w in _CONSENT_BLOCKERS for w in words):
        return False
    core = {"да", "давай", "конечно", "хочу", "можно", "ага", "угу",
            "обязательно", "валяй"}
    return set(words) <= _CONSENT_WORDS and any(w in core for w in words)


_MEMORY_PROBE_RX = re.compile(
    r"\b(?:помнишь|помните|не помнишь|не помните)\b|"
    r"\bчто я (?:тебе |вам )?(?:говорил|рассказыва\w+)|"
    r"\bкак (?:его|её|их|меня )?звали\b|\bкак зовут\b|"
    r"\bчто мы (?:решили|договорились|планировали|обсуждали)\b",
    re.IGNORECASE)

_IGNORANCE_RX = re.compile(
    r"не помню|не припомню|не припоминаю|не могу вспомнить|забыл(?:а)?|"
    r"запамятовал(?:а)?|память (?:меня )?подводит", re.IGNORECASE)


def _detect_memory_refusal(user_text: str, reply: str) -> str | None:
    if not _MEMORY_PROBE_RX.search(user_text or ""):
        return None
    m = _IGNORANCE_RX.search(reply or "")
    return m.group(0) if m else None


def _last_assistant_text(history) -> str:
    try:
        for m in reversed(getattr(history, "messages", None) or []):
            if not isinstance(m, dict) or m.get("role") != "assistant":
                continue
            c = m.get("content")
            if isinstance(c, str) and c.strip():
                return c
    except Exception:
        pass
    return ""


def _draw_trigger_in(text: str) -> bool:
    try:
        from tools.draw import DRAW_TOOL
        blob = (text or "").lower()
        return any(t in blob for t in DRAW_TOOL.triggers)
    except Exception:
        return False


def _draw_reask_nudge(gender: str) -> str:
    return (
        "(служебное, Господин этого не видит: он УЖЕ попросил снимок — согласие "
        "есть, переспрашивать «сделать ли?» не нужно, со стороны это выглядит как "
        "отказ. Вызови draw прямо сейчас; intent возьми из слов Господина, "
        f"недостающие детали образа реши {gpick(gender, 'сама', 'сам')} "
        "по своему вкусу. Ответь заново.)"
    )

def _consent_draw_nudge(gender: str) -> str:
    return (
        f"(служебное, Господин этого не видит: ты "
        f"{gpick(gender, 'сама предложила', 'сам предложил')} снимок, и "
        "Господин только что согласился — выполни обещанное: вызови draw прямо "
        f"сейчас, intent = то, что ты "
        f"{gpick(gender, 'предлагала', 'предлагал')}. "
        "Не переспрашивай. Ответь заново.)"
    )

_MEMORY_REFUSAL_NUDGE = (
    "(служебное, Господин этого не видит: прежде чем отвечать «не помню» — "
    "поищи в памяти: вызови search_memory с запросом по словам Господина "
    "(имя, тема, событие). «Не помню» допустимо ТОЛЬКО после пустого поиска. "
    "Ответь заново.)"
)


async def _ack_reminder(s: dict, ws, record_id: str) -> None:
    if not record_id:
        return
    record = next(
        (r for r in s["memory"].records
         if r.record_id == record_id and r.type == "напоминание"),
        None,
    )
    if record is None or record.details.get("acknowledged"):
        return
    record.details["acknowledged"] = True
    record.details["acknowledged_at"] = time.time()
    try:
        _save_memory()
    except Exception as e:
        print(f"[ack] save failed: {e}")
    try:
        await ws.send_json({
            "type": "reminder_acknowledged",
            "record_id": record_id,
        })
    except Exception:
        pass
    print(f"[ack] reminder {record_id} acknowledged by user")


async def _collect_burst(s: dict, ws, first_text: str, first_image,
                         lifecycle) -> tuple[str, object]:
    scfg = getattr(s.get("config"), "session", None)
    base_wait = float(getattr(scfg, "burst_wait_seconds", 2.0) or 0.0)
    typing_grace = float(getattr(scfg, "burst_typing_grace_seconds", 4.0) or 0.0)
    max_hold = float(getattr(scfg, "burst_max_hold_seconds", 90.0) or 0.0)
    texts = [first_text] if first_text else []
    image = first_image
    if base_wait <= 0 or image or (first_text or "").startswith("/"):
        return "\n".join(texts), image
    start = time.monotonic()
    deadline = start + base_wait
    merged = 0
    while True:
        if max_hold > 0:
            deadline = min(deadline, start + max_hold)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            nxt = await asyncio.wait_for(ws.receive_json(), timeout=remaining)
        except asyncio.TimeoutError:
            break
        ntype = nxt.get("type")
        if ntype == "typing":
            deadline = time.monotonic() + typing_grace
            continue
        if ntype == "keystroke":
            try:
                lifecycle.preload()
            except Exception:
                pass
            deadline = time.monotonic() + typing_grace
            continue
        if ntype == "acknowledge_reminder":
            await _ack_reminder(s, ws, nxt.get("record_id", ""))
            continue
        if ntype == "message":
            t = (nxt.get("text") or "").strip()
            img = nxt.get("image")
            if t.startswith("/") and not img:
                s.setdefault("queued_ws_messages", []).append(nxt)
                break
            if t:
                texts.append(t)
                merged += 1
            s["last_user_message_at"] = time.time()
            if img:
                image = img
                break
            deadline = time.monotonic() + base_wait
            continue
    if merged:
        print(f"[burst] склеено сообщений: {1 + merged}")
    return "\n".join(texts), image


async def _watch_ws_during_generation(s: dict, ws, gen_future, ui_visible: dict,
                                      client) -> str:
    while True:
        recv = asyncio.ensure_future(ws.receive_json())
        done, _pending = await asyncio.wait(
            {gen_future, recv}, return_when=asyncio.FIRST_COMPLETED)
        if gen_future in done:
            if recv.done() and not recv.cancelled():
                try:
                    data = recv.result()
                except Exception:
                    data = None
                if isinstance(data, dict):
                    ntype = data.get("type")
                    if ntype == "message":
                        s.setdefault("queued_ws_messages", []).append(data)
                    elif ntype == "acknowledge_reminder":
                        await _ack_reminder(s, ws, data.get("record_id", ""))
            else:
                recv.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await recv
            return "done"
        try:
            data = recv.result()
        except Exception:
            await gen_future
            raise
        ntype = data.get("type") if isinstance(data, dict) else None
        if ntype == "typing" or ntype == "keystroke":
            continue
        if ntype == "acknowledge_reminder":
            await _ack_reminder(s, ws, data.get("record_id", ""))
            continue
        if ntype != "message":
            continue
        s.setdefault("queued_ws_messages", []).append(data)
        _limit = int(getattr(getattr(s.get("config"), "session", None),
                             "burst_interrupt_visible_chars", 0) or 0)
        _barely_started = (_limit > 0
                           and ui_visible.get("chars", 0) <= _limit)
        if not ui_visible.get("v") or _barely_started:
            client.request_cancel()
            await gen_future
            return "interrupt"


def _mood_meta(state: dict) -> dict | None:
    idy = state.get("identity")
    if idy is None:
        return None
    rx = (getattr(idy, "reaction_state", "") or "").strip()
    if rx:
        return {"state": rx, "kind": "reaction",
                "intensity": float(getattr(idy, "reaction_intensity", 0.0) or 0.0)}
    st = (getattr(idy, "mood_state", "") or "").strip()
    if not st or st == mood_mod.NEUTRAL:
        return None
    return {"state": st, "kind": "mood",
            "intensity": float(getattr(idy, "mood_intensity", 0.0) or 0.0)}


def _hist_add_assistant(state: dict, text: str) -> None:
    state["history"].add("assistant", text, mood=_mood_meta(state))
    _stats_bump(state, "messages_assistant")
    _stats_session_tick(state)
    _achievements_check(state)


def _stats_touch(state: dict):
    idy = state.get("identity")
    if idy is None or not hasattr(idy, "ensure_stats"):
        return None
    if not (getattr(idy, "stats", None) or {}).get("since"):
        n = 0
        try:
            n = sum(1 for r in getattr(state.get("memory"), "records", [])
                    if getattr(r, "type", "") == "рефлексия"
                    and not getattr(r, "is_forgotten", False))
        except Exception:
            n = 0
        idy.ensure_stats(sessions_backfill=n)
    return idy.stats


def _stats_bump(state: dict, key: str, n: int = 1) -> None:
    idy = state.get("identity")
    if idy is None or not hasattr(idy, "bump_stat"):
        return
    try:
        _stats_touch(state)
        idy.bump_stat(key, n)
    except Exception as e:
        print(f"[stats] {key}: {type(e).__name__}: {e}")


_TALK_GAP_CAP_SEC = 600.0


def _stats_session_tick(state: dict, now: float | None = None) -> None:
    idy = state.get("identity")
    if idy is None or not hasattr(idy, "bump_stat"):
        return
    now = time.time() if now is None else float(now)
    cur = state.get("stats_session")
    if not isinstance(cur, dict):
        cur = state["stats_session"] = {"started_at": now, "last_at": now,
                                        "messages": 0, "talk": 0.0}
    gap = max(0.0, now - float(cur.get("last_at", now) or now))
    inc = min(gap, _TALK_GAP_CAP_SEC) / 60.0
    cur["last_at"] = now
    cur["messages"] = int(cur.get("messages", 0) or 0) + 1
    cur["talk"] = float(cur.get("talk", 0.0) or 0.0) + inc
    st = _stats_touch(state)
    if st is None:
        return
    st["talk_minutes"] = round(float(st.get("talk_minutes", 0.0) or 0.0) + inc, 3)
    if cur["messages"] > int(st.get("longest_messages", 0) or 0):
        st["longest_messages"] = cur["messages"]
    if cur["talk"] > float(st.get("longest_minutes", 0.0) or 0.0):
        st["longest_minutes"] = round(cur["talk"], 3)


def _stats_on_day(st: dict, now: float) -> None:
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    last = str(st.get("last_day") or "")
    if last == today:
        return
    yesterday = time.strftime("%Y-%m-%d", time.localtime(now - 86400))
    st["streak_days"] = (int(st.get("streak_days", 0) or 0) + 1) if last == yesterday else 1
    st["best_streak_days"] = max(int(st.get("best_streak_days", 0) or 0), st["streak_days"])
    st["last_day"] = today


def _stats_on_user_message(state: dict, now: float | None = None) -> None:
    now = time.time() if now is None else float(now)
    msgs = getattr(state.get("history"), "messages", None) or []
    n_user = sum(1 for m in msgs if isinstance(m, dict)
                 and m.get("role") == "user" and m.get("kind") != "marker"
                 and (m.get("mood") or {}).get("kind") != "marker")
    _stats_bump(state, "messages_user")
    if n_user == 1:
        _stats_bump(state, "sessions")
        state["stats_session"] = {"started_at": now, "last_at": now,
                                  "messages": 0, "talk": 0.0}
    st = _stats_touch(state)
    if st is not None:
        _stats_on_day(st, now)
    _stats_session_tick(state, now)


def _stats_on_session_end(state: dict) -> None:
    idy = state.get("identity")
    cur = state.pop("stats_session", None)
    if idy is None or not cur or not hasattr(idy, "bump_stat"):
        return
    st = _stats_touch(state)
    if st is None:
        return
    from persona import mood as _mood
    label = str(getattr(idy, "last_session_mood", "") or "").strip() or _mood.NEUTRAL
    moods = st.get("moods") if isinstance(st.get("moods"), dict) else {}
    moods[label] = int(moods.get(label, 0) or 0) + 1
    st["moods"] = moods


def _flush_mood_marker(state: dict) -> None:
    mk = state.pop("pending_mood_marker", None)
    if not mk:
        return
    prev, new = mk
    prev = prev or "ровное"
    name = (getattr(getattr(state.get("persona"), "character", None), "name", "")
            or "").strip()
    who = f"Твоё настроение, {name}," if name else "Твоё настроение"
    state["history"].add(
        "user", f"({who} сменилось: {prev} → {new}.)",
        mood={"kind": "marker", "marker": "mood", "from": prev, "to": new})


_WEBIMG_ALLOW: dict[str, float] = {}
_WEBIMG_CAP = 300
_WEBIMG_MAX_BYTES = 30 * 1024 * 1024


def _register_webimg(url: str) -> str:
    from urllib.parse import quote
    _WEBIMG_ALLOW[url] = time.time()
    if len(_WEBIMG_ALLOW) > _WEBIMG_CAP:
        for old in sorted(_WEBIMG_ALLOW, key=_WEBIMG_ALLOW.get)[
                :len(_WEBIMG_ALLOW) - _WEBIMG_CAP]:
            _WEBIMG_ALLOW.pop(old, None)
    return f"/api/webimg?u={quote(url, safe='')}"


@app.get("/api/webimg")
def get_webimg(u: str):
    if u not in _WEBIMG_ALLOW:
        return Response(status_code=403, content=b"not in allowlist")
    from urllib.parse import urlparse as _up
    host = _up(u).hostname or "?"
    try:
        import httpx
        r = httpx.get(u, timeout=20.0, follow_redirects=True,
                      headers={"User-Agent": "MaidLink"})
    except Exception as e:
        print(f"[webimg] {host}: не скачалось — {type(e).__name__}: {e}")
        return Response(status_code=502, content=b"fetch failed")
    ctype = (r.headers.get("content-type") or "").split(";")[0].strip()
    if r.status_code >= 400 or not (ctype.startswith("image/") or ctype.startswith("video/")):
        cf = bool(r.headers.get("cf-mitigated")) or (
            r.status_code in (403, 503) and "cloudflare" in (r.headers.get("server") or "").lower()
            and ctype == "text/html")
        print(f"[webimg] {host}: HTTP {r.status_code}, {ctype or 'без типа'}"
              f"{' — проверка Cloudflare вместо файла' if cf else ''}")
        if r.status_code >= 400:
            return Response(status_code=502, content=b"fetch failed")
        return Response(status_code=415, content=b"not an image/video")
    if len(r.content) > _WEBIMG_MAX_BYTES:
        return Response(status_code=413, content=b"too large")
    return Response(content=r.content, media_type=ctype,
                    headers={"Cache-Control": "max-age=86400",
                             "Accept-Ranges": "none"})


async def _send_pending_portrait_reveal(state: dict, ws) -> None:
    reveal = state.pop("pending_portrait_reveal", None)
    if not reveal:
        return
    try:
        await ws.send_json({"type": "system", "text": reveal["text"]})
        await ws.send_json({
            "type": "portrait_updated",
            "url": (f"/api/characters/{reveal['character_id']}/avatar/portrait"
                    f"?t={int(time.time())}"),
            "character_id": reveal["character_id"],
        })
    except Exception:
        pass


def _portrait_basename(state: dict) -> str:
    oid = state.get("runtime_portrait_outfit_id")
    if oid:
        from services.wardrobe import outfit_basename
        return outfit_basename(oid)
    return "portrait_default"


def _avatar_basename(state: dict) -> str:
    oid = state.get("runtime_portrait_outfit_id")
    return f"avatar_chat_{oid}" if oid else "avatar_chat"


def _get_wardrobe(state: dict):
    cid = state.get("character_id")
    if not cid:
        return None
    from services.wardrobe import Wardrobe
    want_dir = PROJECT_ROOT / "characters" / cid
    w = state.get("wardrobe")
    if w is None or getattr(w, "dir", None) != want_dir:
        w = Wardrobe(want_dir)
        state["wardrobe"] = w
    return w


def _visible_styling(state: dict) -> tuple[tuple, tuple]:
    try:
        from services.self_styling import render_parts, styling_state
        idy = state.get("identity")
        if idy is None:
            return (), ()
        p = render_parts(styling_state(idy))
        return tuple(p[0]), tuple(p[1])
    except Exception as e:
        print(f"[styling] visible_styling failed: {type(e).__name__}: {e}")
        return (), ()


async def _apply_packed_portrait(state: dict, ws: WebSocket | None, loop) -> bool:
    style_id = (state["config"].drawing.active_style_id or "default")
    if style_id != "default":
        return False
    store = state.get("store")
    char_id = state.get("character_id") or ""
    if store is None or not char_id:
        return False
    try:
        archive = store.get_archive(char_id)
    except Exception:
        archive = None
    if archive is None:
        return False
    key = state.get("runtime_portrait_outfit_id") or "default"
    entry = f"visual/portraits/{key}.png"
    if not archive.has_entry(entry):
        return False

    basename = _portrait_basename(state)
    target = PROJECT_ROOT / "characters" / char_id / f"{basename}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_bytes(archive.read_bytes(entry))
    except Exception as e:
        print(f"[portrait] packed {entry} write failed: {e}")
        return False

    avatar_target = target.parent / f"{_avatar_basename(state)}.png"
    packed_avatar = ("visual/avatar_chat.png"
                     if key == "default" and archive.has_entry("visual/avatar_chat.png")
                     else None)
    try:
        if packed_avatar:
            avatar_target.write_bytes(archive.read_bytes(packed_avatar))
        else:
            from drawing.face_crop import crop_face_avatar
            await loop.run_in_executor(
                None, lambda: crop_face_avatar(target, avatar_target))
    except Exception as e:
        print(f"[portrait] packed avatar failed: {e}")

    if ws:
        import time as _pt
        await ws.send_json({
            "type": "portrait_updated",
            "url": f"/api/characters/{char_id}/avatar/portrait?t={int(_pt.time())}",
            "character_id": char_id,
        })
        await ws.send_json({"type": "system", "text": "✓ Портрет обновлён (встроенный образ)."})
    print(f"[portrait] {char_id}: упакованный портрет '{key}' → {target.name}")
    return True


async def _regenerate_portrait_and_moods(state: dict, ws: WebSocket | None,
                                         loop) -> None:
    import random as _r
    seed = _r.randint(0, 2**63 - 1)
    await _regenerate_portrait(state, ws, loop, seed=seed)
    await _generate_mood_portraits(state, ws, loop, seed=seed)
    if ws:
        try:
            import time as _t2
            cid = state.get("character_id", "")
            await ws.send_json({
                "type": "portrait_updated",
                "url": f"/api/characters/{cid}/avatar/portrait?t={int(_t2.time())}",
                "character_id": cid,
            })
        except Exception:
            pass


async def _regenerate_portrait(state: dict, ws: WebSocket | None, loop,
                               *, seed: int | None = None,
                               manage_vram: bool = True) -> None:
    if await _apply_packed_portrait(state, ws, loop):
        return

    from drawing import (
        AssetCatalog, BaseAppearance, DrawingPipeline,
        build_portrait_request_and_choice, PortraitBuildError,
    )
    _st_hair, _st_extra = _visible_styling(state)
    from persona.evolution import compute_relationship_tier

    catalog = state.get("drawing_catalog")
    config = state["config"]
    pipeline = state.get("drawing_pipeline")
    if catalog is None or pipeline is None:
        try:
            pipeline = _ensure_drawing_pipeline(state)
        except Exception as e:
            if ws:
                await ws.send_json({
                    "type": "system",
                    "text": f"❌ Не могу перегенерировать портрет: {e}",
                })
            return

    character = state["character"]
    identity = state["identity"]
    character_id = state["character_id"]
    archetype = getattr(character, "archetype", "") or ""

    base_appearance = BaseAppearance()
    try:
        store = state.get("store")
        archive = store.get_archive(character_id) if store else None
        if archive and archive.has_entry("visual/appearance.yaml"):
            visual_data = archive.read_yaml("visual/appearance.yaml")
            base_appearance = BaseAppearance.from_dict(visual_data)
    except Exception as e:
        print(f"[portrait] cannot load base_appearance: {e}")

    char_style_id = None
    try:
        store = state.get("store")
        archive = store.get_archive(character_id) if store else None
        if archive and archive.has_entry("visual/style.yaml"):
            style_data = archive.read_yaml("visual/style.yaml")
            char_style_id = (style_data or {}).get("preferred_style_id") or None
    except Exception:
        pass
    style_catalog = state.get("drawing_style_catalog")
    style_tags = None
    if style_catalog is not None:
        pack = style_catalog.resolve(
            active_style_id=config.drawing.active_style_id,
            character_override_id=char_style_id,
            renderer_id=config.drawing.renderer_id,
        )
        style_tags = list(pack.tags) or None

    runtime_outfit = state.get("runtime_portrait_outfit_id")
    drawing = config.drawing
    outfit_policy = getattr(character, "outfit_policy", None)
    try:
        from drawing import appearance_with_mood_extras, pose_for_expression
        from drawing import mood_expression_override as _meo
        choose_result, request = build_portrait_request_and_choice(
            character_id=character_id,
            character_name=character.name,
            character_archetypes=state["persona"].archetypes,
            base_appearance=appearance_with_mood_extras(
                base_appearance, drawing.renderer_id, "ровное"),
            expression_override=_meo(base_appearance, "ровное", None),
            pose_override=pose_for_expression(
                base_appearance, "ровное", None, catalog, drawing.renderer_id),
            catalog=catalog,
            renderer_id=drawing.renderer_id,
            max_rating=drawing.max_rating,
            current_tier=state["persona"].tier,
            style_tags=style_tags,
            safety_positive=list(drawing.positive_safety_tags) or None,
            safety_negative=list(drawing.negative_safety_tags) or None,
            override_outfit_id=runtime_outfit,
            character_default_outfit_id=state.get("character_default_outfit_id"),
            character_tag_gates=outfit_policy.tag_tier_gates if outfit_policy else None,
            character_blocked_tags=list(outfit_policy.blocked_tags) if outfit_policy else None,
            quality_tags=list(drawing.quality_tags) or None,
            critic_max_retries=(
                drawing.vision_critic_max_retries
                if (manage_vram and drawing.vision_critic_enabled) else 0
            ),
            critic_soft_threshold=drawing.vision_critic_soft_threshold,
            styling_hairstyle=_st_hair,
            styling_extra=_st_extra,
            seed=seed,
        )
    except PortraitBuildError as e:
        if ws:
            await ws.send_json({
                "type": "system",
                "text": f"❌ Не могу собрать портрет: {e}",
            })
        return

    if ws:
        await ws.send_json({
            "type": "system",
            "text": "🎨 Перегенерирую портрет с новым стилем (≈30-60 сек)...",
        })

    def _swap_to_render():
        _llama_mgr.stop()
        _llama_mgr.wait_vram_released()

    def _swap_to_llm():
        _release_comfy()
        _llama_mgr.start()

    try:
        result = await loop.run_in_executor(
            None,
            lambda: pipeline.render_choice(
                choose_result, request,
                before_render=(_swap_to_render if manage_vram else None),
                after_render=(_swap_to_llm if manage_vram else None),
            ),
        )
    except Exception as e:
        if ws:
            await ws.send_json({
                "type": "system",
                "text": f"❌ Render портрета упал: {type(e).__name__}: {e}",
            })
        try:
            if manage_vram and not _llama_mgr.is_responsive(timeout_sec=0.5):
                await loop.run_in_executor(None, _llama_mgr.start)
        except Exception:
            pass
        return

    if not result.is_success:
        msg = result.refusal_reason or result.error or "(unknown)"
        if ws:
            await ws.send_json({
                "type": "system",
                "text": f"❌ Портрет не получился: {msg}",
            })
        return

    if result.critic_verdicts:
        last_v = result.critic_verdicts[-1]
        if last_v.should_regen(drawing.vision_critic_soft_threshold):
            issue_preview = "; ".join(last_v.issues[:2]) if last_v.issues else "без подробностей"
            attempts = len(result.critic_verdicts)
            if ws:
                await ws.send_json({
                    "type": "system",
                    "text": (
                        f"❌ Портрет не прошёл проверку качества "
                        f"({last_v.verdict}, severity={last_v.severity}, "
                        f"попыток={attempts}): {issue_preview}.\n"
                        f"Стиль изменён, но портрет оставлен прежним."
                    ),
                })
            return

    storage = state["drawing_storage"]
    try:
        stored = storage.save_from_pipeline(
            result,
            character_id=character_id,
            intent="portrait regen (style change)",
            rating=drawing.max_rating,
        )
    except Exception as e:
        print(f"[portrait] storage.save failed: {e}; используем raw render path")
        stored = None

    src_path = stored.image_path if stored else result.image_path

    import shutil
    basename = _portrait_basename(state)
    portrait_target = (PROJECT_ROOT / "characters" /
                       character_id / f"{basename}.png")
    portrait_target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(src_path, portrait_target)
    except Exception as e:
        if ws:
            await ws.send_json({
                "type": "system",
                "text": f"❌ Не могу сохранить portrait.png: {e}",
            })
        return

    try:
        from drawing.face_crop import crop_face_avatar
        avatar_target = portrait_target.parent / f"{_avatar_basename(state)}.png"
        ok = await loop.run_in_executor(
            None, lambda: crop_face_avatar(portrait_target, avatar_target))
        print(f"[portrait] аватарка {'обновлена' if ok else 'не тронута (лицо не найдено)'}: "
              f"{avatar_target.name}")
    except Exception as e:
        print(f"[portrait] avatar crop failed: {e}")
    if portrait_target.name == "portrait_default.png":
        try:
            await loop.run_in_executor(None, _list_avatar_sync, portrait_target.parent)
        except Exception as e:
            print(f"[portrait] list avatar failed: {e}")

    if ws:
        critic_note = ""
        if result.critic_verdicts:
            last_v = result.critic_verdicts[-1]
            attempts = len(result.critic_verdicts)
            critic_note = (f" (критик: {last_v.verdict}, "
                           f"confidence={last_v.confidence:.2f}, "
                           f"попыток={attempts})")
        import time
        url = f"/api/characters/{character_id}/avatar/portrait?t={int(time.time())}"
        await ws.send_json({
            "type": "portrait_updated",
            "url": url,
            "character_id": character_id,
        })
        await ws.send_json({
            "type": "system",
            "text": f"✓ Портрет обновлён.{critic_note}",
        })


async def _generate_mood_portraits(state: dict, ws: WebSocket | None, loop,
                                   *, seed: int | None = None,
                                   manage_vram: bool = True) -> None:
    if not state["config"].drawing.mood_portraits_enabled:
        return
    import shutil
    from drawing import (
        BaseAppearance, build_portrait_request_and_choice, PortraitBuildError,
    )
    from persona import mood as mood_mod

    catalog = state.get("drawing_catalog")
    pipeline = state.get("drawing_pipeline")
    if catalog is None or pipeline is None:
        try:
            pipeline = _ensure_drawing_pipeline(state)
        except Exception as e:
            if ws:
                await ws.send_json({"type": "system",
                                    "text": f"❌ mood-портреты недоступны: {e}"})
            return

    character = state["character"]
    character_id = state["character_id"]
    config = state["config"]
    drawing = config.drawing

    base_appearance = BaseAppearance()
    char_style_id = None
    store = state.get("store")
    try:
        archive = store.get_archive(character_id) if store else None
        if archive and archive.has_entry("visual/appearance.yaml"):
            base_appearance = BaseAppearance.from_dict(
                archive.read_yaml("visual/appearance.yaml"))
        if archive and archive.has_entry("visual/style.yaml"):
            char_style_id = (archive.read_yaml("visual/style.yaml") or {}).get(
                "preferred_style_id") or None
    except Exception as e:
        print(f"[mood-portrait] visual load failed: {e}")
    style_catalog = state.get("drawing_style_catalog")
    style_tags = None
    if style_catalog is not None:
        pack = style_catalog.resolve(
            active_style_id=config.drawing.active_style_id,
            character_override_id=char_style_id,
            renderer_id=config.drawing.renderer_id,
        )
        style_tags = list(pack.tags) or None

    runtime_outfit = state.get("runtime_portrait_outfit_id")
    outfit_policy = getattr(character, "outfit_policy", None)
    basename = _portrait_basename(state)
    moods = [(name, meta.expression)
             for name, meta in mood_mod.MOOD_STATES.items()
             if name != mood_mod.NEUTRAL]

    import random as _random
    if seed is None:
        seed = _random.randint(0, 2**63 - 1)

    if ws:
        await ws.send_json({
            "type": "system",
            "text": (f"🎭 Генерирую {len(moods)} mood-портретов "
                     f"(~по минуте каждый, чат пока недоступен)..."),
        })

    if manage_vram:
        await loop.run_in_executor(None, _llama_mgr.stop)

    from drawing import appearance_with_mood_extras, pose_for_expression
    from drawing import mood_expression_override as _mood_expr_override
    _st_hair, _st_extra = _visible_styling(state)
    done = 0
    try:
        for mood_name, expr in moods:
            try:
                choose_result, request = build_portrait_request_and_choice(
                    character_id=character_id,
                    character_name=character.name,
                    character_archetypes=state["persona"].archetypes,
                    base_appearance=appearance_with_mood_extras(
                        base_appearance, drawing.renderer_id, mood_name),
                    styling_hairstyle=_st_hair,
                    styling_extra=_st_extra,
                    catalog=catalog,
                    renderer_id=drawing.renderer_id,
                    max_rating=drawing.max_rating,
                    current_tier=state["persona"].tier,
                    style_tags=style_tags,
                    safety_positive=list(drawing.positive_safety_tags) or None,
                    safety_negative=list(drawing.negative_safety_tags) or None,
                    override_outfit_id=runtime_outfit,
                    character_default_outfit_id=state.get("character_default_outfit_id"),
                    character_tag_gates=outfit_policy.tag_tier_gates if outfit_policy else None,
                    character_blocked_tags=list(outfit_policy.blocked_tags) if outfit_policy else None,
                    quality_tags=list(drawing.quality_tags) or None,
                    critic_max_retries=0,
                    critic_soft_threshold=drawing.vision_critic_soft_threshold,
                    expression_override=_mood_expr_override(
                        base_appearance, mood_name, expr),
                    pose_override=pose_for_expression(
                        base_appearance, mood_name, expr, catalog, drawing.renderer_id),
                    seed=seed,
                )
            except PortraitBuildError as e:
                print(f"[mood-portrait] {mood_name}: build failed: {e}")
                continue

            try:
                result = await loop.run_in_executor(
                    None,
                    lambda cr=choose_result, rq=request: pipeline.render_choice(
                        cr, rq,
                    ),
                )
            except Exception as e:
                print(f"[mood-portrait] {mood_name}: render failed: {type(e).__name__}: {e}")
                continue

            if not getattr(result, "is_success", False):
                print(f"[mood-portrait] {mood_name}: not success, skip")
                continue

            target = (PROJECT_ROOT / "characters" /
                      character_id / f"{basename}_{mood_name}.png")
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(result.image_path, target)
                done += 1
                print(f"[mood-portrait] {mood_name} -> {target.name}")
            except Exception as e:
                print(f"[mood-portrait] {mood_name}: copy failed: {e}")
    finally:
        if manage_vram:
            try:
                await loop.run_in_executor(
                    None, lambda: (_release_comfy(), _llama_mgr.start()))
            except Exception:
                pass

    if drawing.portrait_align_enabled:
        try:
            from drawing.assets import ASPECT_DIMENSIONS, ASPECT_TALL
            from drawing.face_crop import align_portrait_set
            base_dir = PROJECT_ROOT / "characters" / character_id
            align_paths = [str(base_dir / f"{basename}.png")]
            align_paths += [str(base_dir / f"{basename}_{m}.png") for m, _ in moods]
            align_paths = [p for p in align_paths if Path(p).exists()]
            res = await loop.run_in_executor(None, lambda: align_portrait_set(
                align_paths,
                scale=drawing.portrait_align_scale,
                shift=drawing.portrait_align_shift,
                target=ASPECT_DIMENSIONS[ASPECT_TALL]))
            ok = sum(1 for v in res.values() if v == "ok")
            print(f"[mood-portrait] face-align {ok}/{len(align_paths)}: {res}")
        except Exception as e:
            print(f"[mood-portrait] face-align failed: {type(e).__name__}: {e}")

    if ws:
        await ws.send_json({
            "type": "system",
            "text": f"✓ Mood-портреты готовы: {done}/{len(moods)}.",
        })


PREPARE_TIER = "intimate"


async def _render_outfit_step(state: dict, outfit_id: str, step: str,
                              seed: int, loop) -> bool:
    import shutil
    from drawing import (BaseAppearance, build_portrait_request_and_choice,
                         PortraitBuildError)
    from persona import mood as mood_mod
    from services.wardrobe import BASE_STEP, step_filename

    catalog = state.get("drawing_catalog")
    pipeline = state.get("drawing_pipeline") or _ensure_drawing_pipeline(state)
    character = state["character"]
    character_id = state["character_id"]
    drawing = state["config"].drawing

    base_appearance = BaseAppearance()
    char_style_id = None
    store = state.get("store")
    try:
        archive = store.get_archive(character_id) if store else None
        if archive and archive.has_entry("visual/appearance.yaml"):
            base_appearance = BaseAppearance.from_dict(
                archive.read_yaml("visual/appearance.yaml"))
        if archive and archive.has_entry("visual/style.yaml"):
            char_style_id = (archive.read_yaml("visual/style.yaml") or {}).get(
                "preferred_style_id") or None
    except Exception as e:
        print(f"[wardrobe] visual load failed: {e}")
    style_tags = None
    style_catalog = state.get("drawing_style_catalog")
    if style_catalog is not None:
        pack = style_catalog.resolve(
            active_style_id=drawing.active_style_id,
            character_override_id=char_style_id,
            renderer_id=drawing.renderer_id,
        )
        style_tags = list(pack.tags) or None

    expr = None
    if step != BASE_STEP:
        meta = mood_mod.MOOD_STATES.get(step)
        if meta is None:
            return False
        expr = meta.expression

    outfit_policy = getattr(character, "outfit_policy", None)
    _st_hair, _st_extra = _visible_styling(state)
    _mood_key = mood_mod.NEUTRAL if step == BASE_STEP else step
    try:
        from drawing import appearance_with_mood_extras, pose_for_expression
        from drawing import mood_expression_override as _meo
        choose_result, request = build_portrait_request_and_choice(
            character_id=character_id,
            character_name=character.name,
            character_archetypes=state["persona"].archetypes,
            base_appearance=appearance_with_mood_extras(
                base_appearance, drawing.renderer_id, _mood_key),
            styling_hairstyle=_st_hair,
            styling_extra=_st_extra,
            catalog=catalog,
            renderer_id=drawing.renderer_id,
            max_rating=drawing.max_rating,
            current_tier=PREPARE_TIER,
            style_tags=style_tags,
            safety_positive=list(drawing.positive_safety_tags) or None,
            safety_negative=list(drawing.negative_safety_tags) or None,
            override_outfit_id=outfit_id,
            character_default_outfit_id=state.get("character_default_outfit_id"),
            character_tag_gates=outfit_policy.tag_tier_gates if outfit_policy else None,
            character_blocked_tags=list(outfit_policy.blocked_tags) if outfit_policy else None,
            quality_tags=list(drawing.quality_tags) or None,
            critic_max_retries=0,
            critic_soft_threshold=drawing.vision_critic_soft_threshold,
            expression_override=_meo(base_appearance, _mood_key, expr),
            pose_override=pose_for_expression(
                base_appearance, _mood_key, expr, catalog, drawing.renderer_id),
            seed=seed,
        )
    except PortraitBuildError as e:
        print(f"[wardrobe] {outfit_id}/{step}: build failed: {e}")
        return False
    _chosen = getattr(getattr(choose_result, "choice", None), "outfit_id", None)
    if _chosen != outfit_id:
        print(f"[wardrobe] {outfit_id}/{step}: костюм недоступен для подготовки "
              f"(рейтинг/blocked_tags) — билдер подставил {_chosen!r}, шаг пропущен")
        return False

    try:
        result = await loop.run_in_executor(
            None, lambda: pipeline.render_choice(choose_result, request))
    except Exception as e:
        print(f"[wardrobe] {outfit_id}/{step}: render failed: {type(e).__name__}: {e}")
        return False
    if not getattr(result, "is_success", False):
        print(f"[wardrobe] {outfit_id}/{step}: not success, skip")
        return False

    target = PROJECT_ROOT / "characters" / character_id / step_filename(outfit_id, step)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(result.image_path, target)
        print(f"[wardrobe] {outfit_id}/{step} -> {target.name}")
        return True
    except Exception as e:
        print(f"[wardrobe] {outfit_id}/{step}: copy failed: {e}")
        return False


async def _align_outfit_set(state: dict, outfit_id: str, loop) -> None:
    drawing = state["config"].drawing
    if not drawing.portrait_align_enabled:
        return
    try:
        from drawing.assets import ASPECT_DIMENSIONS, ASPECT_TALL
        from drawing.face_crop import align_portrait_set
        from services.wardrobe import required_steps, step_filename
        base_dir = PROJECT_ROOT / "characters" / state["character_id"]
        paths = [str(base_dir / step_filename(outfit_id, s))
                 for s in required_steps()]
        paths = [p for p in paths if Path(p).exists()]
        if not paths:
            return
        res = await loop.run_in_executor(None, lambda: align_portrait_set(
            paths, scale=drawing.portrait_align_scale,
            shift=drawing.portrait_align_shift,
            target=ASPECT_DIMENSIONS[ASPECT_TALL]))
        ok = sum(1 for v in res.values() if v == "ok")
        print(f"[wardrobe] {outfit_id}: face-align {ok}/{len(paths)}")
    except Exception as e:
        print(f"[wardrobe] {outfit_id}: face-align failed: {type(e).__name__}: {e}")


def _export_outfit_set(char_dir: Path, outfit_id: str, export_root: Path) -> list[str]:
    import shutil
    from services.wardrobe import required_steps, step_filename
    out_dir = export_root / outfit_id
    out_dir.mkdir(parents=True, exist_ok=True)
    exported: list[str] = []
    for step in required_steps():
        src = char_dir / step_filename(outfit_id, step)
        if not src.exists():
            continue
        dst = out_dir / src.name.removeprefix("portrait_")
        shutil.copy2(src, dst)
        exported.append(dst.name)
    return exported


async def _export_outfit_set_with_avatar(state: dict, outfit_id: str, loop) -> str:
    char_dir = PROJECT_ROOT / "characters" / state["character_id"]
    export_root = PROJECT_ROOT / "portraits"
    exported = await loop.run_in_executor(
        None, lambda: _export_outfit_set(char_dir, outfit_id, export_root))
    if not exported:
        return f"⚠️ Экспортировать нечего — файлов набора «{outfit_id}» нет."
    avatar_note = ""
    try:
        from drawing.face_crop import crop_face_avatar
        base = export_root / outfit_id / f"{outfit_id}.png"
        avatar = export_root / outfit_id / "avatar_chat.png"
        if base.exists():
            await loop.run_in_executor(
                None, lambda: crop_face_avatar(base, avatar))
            avatar_note = " + avatar_chat.png"
    except Exception as e:
        avatar_note = f" (аватарка не вышла: {e})"
        print(f"[wardrobe] export avatar crop failed ({outfit_id}): {e}")
    return (f"📦 Набор экспортирован: portraits/{outfit_id}/ — "
            f"{len(exported)} портретов{avatar_note}. Имена готовы для "
            f"visual/portraits/ в .maid.")


async def _prepare_outfit_now(state: dict, ws: WebSocket | None, loop,
                              outfit_id: str) -> None:
    wardrobe = _get_wardrobe(state)
    if wardrobe is None:
        return
    who = busy_with(state)
    if who is not None:
        if ws:
            await ws.send_json({"type": "system", "text": (
                f"⏳ Подготовку сейчас не начать: идёт {who}. "
                f"Попробуй чуть позже.")})
        return
    state["wardrobe_preparing"] = outfit_id
    seed = wardrobe.ensure_seed(outfit_id)
    done, total = wardrobe.progress(outfit_id)
    if ws:
        await ws.send_json({"type": "system", "text": (
            f"👗 Готовлю наряд (осталось {total - done} из {total} портретов, "
            f"~по минуте каждый) — чат пока недоступен...")})
    try:
        await loop.run_in_executor(None, _llama_mgr.stop)
        try:
            while True:
                step = wardrobe.next_step(outfit_id)
                if step is None:
                    break
                await _render_outfit_step(state, outfit_id, step, seed, loop)
                wardrobe.mark_step(outfit_id, step)
        finally:
            try:
                await loop.run_in_executor(
                    None, lambda: (_release_comfy(), _llama_mgr.start()))
            except Exception:
                pass
        await _align_outfit_set(state, outfit_id, loop)
        wardrobe.mark_prepared(outfit_id)
        outfit = (state.get("drawing_catalog").outfits.get(outfit_id)
                  if state.get("drawing_catalog") else None)
        if ws:
            await ws.send_json({"type": "system", "text": (
                f"✓ Наряд «{(outfit.name if outfit else outfit_id)}» подготовлен — "
                f"теперь переодевание в него мгновенно.")})
        try:
            note = await _export_outfit_set_with_avatar(state, outfit_id, loop)
            if ws:
                await ws.send_json({"type": "system", "text": note})
        except Exception as e:
            print(f"[wardrobe] export failed ({outfit_id}): {e}")
    finally:
        state["wardrobe_preparing"] = None


async def prepare_outfit_background_step(state: dict, should_abort, log) -> dict:
    wardrobe = _get_wardrobe(state)
    if wardrobe is None:
        return {"status": "skipped", "reason": "нет активного персонажа"}
    outfit_id = wardrobe.head()
    if not outfit_id:
        return {"status": "skipped", "reason": "очередь пуста"}
    catalog = state.get("drawing_catalog")
    if catalog is None:
        return {"status": "skipped", "reason": "каталог не инициализирован"}
    if outfit_id not in catalog.outfits:
        wardrobe.dequeue(outfit_id)
        log(f"костюма '{outfit_id}' больше нет в каталоге — убран из очереди")
        return {"status": "skipped",
                "reason": f"костюм {outfit_id!r} не в каталоге"}
    if state.get("wardrobe_preparing"):
        return {"status": "skipped", "reason": "подготовка уже идёт"}

    step = wardrobe.next_step(outfit_id)
    if step is None:
        await _align_outfit_set(state, outfit_id, asyncio.get_event_loop())
        wardrobe.mark_prepared(outfit_id)
        log(f"наряд {outfit_id} подготовлен")
        return {"status": "prepared", "outfit_id": outfit_id}

    if should_abort():
        return {"status": "aborted"}

    loop = asyncio.get_event_loop()
    state["wardrobe_preparing"] = outfit_id
    try:
        lifecycle = get_lifecycle()
        if lifecycle is not None:
            await lifecycle.request_unload(reason="wardrobe prepare")
        seed = wardrobe.ensure_seed(outfit_id)
        ok = await _render_outfit_step(state, outfit_id, step, seed, loop)
        wardrobe.mark_step(outfit_id, step)
        try:
            await loop.run_in_executor(None, _release_comfy)
        except Exception:
            pass
        done, total = wardrobe.progress(outfit_id)
        log(f"{outfit_id}: шаг «{step}» {'ok' if ok else 'брак/сбой'} ({done}/{total})")
        if wardrobe.next_step(outfit_id) is None:
            await _align_outfit_set(state, outfit_id, loop)
            wardrobe.mark_prepared(outfit_id)
            log(f"наряд {outfit_id} подготовлен")
            return {"status": "prepared", "outfit_id": outfit_id,
                    "step": step, "done": done, "total": total}
        return {"status": "step", "outfit_id": outfit_id, "step": step,
                "done": done, "total": total}
    finally:
        state["wardrobe_preparing"] = None


async def _send_portrait_updated(state: dict, ws: WebSocket | None) -> None:
    if ws is None:
        return
    try:
        import time as _t
        cid = state.get("character_id", "")
        await ws.send_json({
            "type": "portrait_updated",
            "url": f"/api/characters/{cid}/avatar/portrait?t={int(_t.time())}",
            "character_id": cid,
        })
    except Exception:
        pass


def _reset_all_outfit_files(state: dict) -> int:
    cid = state.get("character_id")
    if not cid:
        return 0
    cdir = PROJECT_ROOT / "characters" / cid
    if not cdir.exists():
        return 0
    removed = 0
    for pattern in ("portrait_*.png", "avatar_chat.png", "avatar_chat_*.png"):
        for f in cdir.glob(pattern):
            try:
                f.unlink()
                removed += 1
            except OSError as e:
                print(f"[style] delete {f.name} failed: {e}")
    return removed


def _restore_baked_portraits(state: dict) -> int:
    store = state.get("store")
    cid = state.get("character_id")
    if store is None or not cid:
        return 0
    try:
        archive = store.get_archive(cid)
    except Exception:
        archive = None
    if archive is None:
        return 0
    cdir = PROJECT_ROOT / "characters" / cid
    cdir.mkdir(parents=True, exist_ok=True)
    prefix = "visual/portraits/"
    n = 0
    for entry in archive.list_entries():
        if not (entry.startswith(prefix) and entry.endswith(".png")):
            continue
        key = entry[len(prefix):-len(".png")]
        if not key:
            continue
        try:
            (cdir / f"portrait_{key}.png").write_bytes(archive.read_bytes(entry))
            n += 1
        except Exception as e:
            print(f"[style] restore {entry} failed: {e}")
    if archive.has_entry("visual/avatar_chat.png"):
        try:
            (cdir / "avatar_chat.png").write_bytes(
                archive.read_bytes("visual/avatar_chat.png"))
            n += 1
        except Exception as e:
            print(f"[style] restore avatar failed: {e}")
    return n


def _sync_default_slot_from_outfit(state: dict, oid: str) -> None:
    import shutil
    from services.wardrobe import required_steps, step_filename, BASE_STEP
    cid = state.get("character_id")
    if not cid:
        return
    cdir = PROJECT_ROOT / "characters" / cid
    base_src = cdir / step_filename(oid, BASE_STEP)
    if base_src.exists():
        try:
            shutil.copy2(base_src, cdir / "portrait_default.png")
            (cdir / "list_avatar.png").unlink(missing_ok=True)
        except OSError as e:
            print(f"[style] sync default base failed: {e}")
    for s in required_steps():
        if s == BASE_STEP:
            continue
        src = cdir / step_filename(oid, s)
        if src.exists():
            try:
                shutil.copy2(src, cdir / f"portrait_default_{s}.png")
            except OSError:
                pass
    av_src = cdir / f"avatar_chat_{oid}.png"
    try:
        if av_src.exists():
            shutil.copy2(av_src, cdir / "avatar_chat.png")
        elif (cdir / "portrait_default.png").exists():
            from drawing.face_crop import crop_face_avatar
            crop_face_avatar(cdir / "portrait_default.png", cdir / "avatar_chat.png")
    except Exception as e:
        print(f"[style] sync default avatar failed: {e}")


async def _apply_style_change(state: dict, ws: WebSocket | None, loop,
                              new_style_id: str) -> None:
    from services.wardrobe import required_steps
    new_style_id = (new_style_id or "default").strip() or "default"
    wardrobe = _get_wardrobe(state)
    if wardrobe is None:
        state["config"].drawing.active_style_id = new_style_id
        await _regenerate_portrait_and_moods(state, ws, loop)
        return
    if wardrobe.get_style() == new_style_id:
        return
    fast = (new_style_id == "default")
    character_id = state.get("character_id")

    if not fast and not drawing_available(state):
        wardrobe.set_style(new_style_id)
        state["config"].drawing.active_style_id = new_style_id
        _reset_all_outfit_files(state)
        if ws:
            await ws.send_json({"type": "system", "text": (
                "Стиль сохранён, но рисование сейчас недоступно — портреты не "
                "перегенерированы. Подключите модуль генерации.")})
        return

    if not fast:
        who = busy_with(state)
        if who is not None:
            if ws:
                await ws.send_json({"type": "system", "text": (
                    f"⏳ Сейчас идёт {who} — смену стиля начну после завершения. "
                    f"Стиль пока НЕ изменён.")})
            return

    wardrobe.set_style(new_style_id)
    state["config"].drawing.active_style_id = new_style_id
    state["runtime_portrait_outfit_id"] = None
    removed = _reset_all_outfit_files(state)
    print(f"[style] {character_id}: → {new_style_id!r} "
          f"(сброшено {removed} файлов, fast={fast})")

    default_oids = list(state.get("character_outfit_ids") or [])
    default_oid = state.get("character_default_outfit_id")

    if fast:
        n = _restore_baked_portraits(state)
        if ws:
            await ws.send_json({"type": "system", "text": (
                f"✓ Стиль сброшен на дефолтный — вшитые наборы восстановлены "
                f"из архива ({n} портретов), рендер не потребовался.")})
        await _send_portrait_updated(state, ws)
        return

    if not default_oids:
        state["style_changing"] = new_style_id
        try:
            if ws:
                await ws.send_json({"type": "system", "text": (
                    f"🎨 Меняю стиль на «{new_style_id}»: перерисовываю портрет "
                    f"(~1-2 минуты, чат недоступен)...")})
            await _regenerate_portrait_and_moods(state, ws, loop)
        finally:
            state["style_changing"] = None
        if ws:
            await ws.send_json({"type": "system", "text": (
                "✓ Стиль применён. Костюмы можно готовить из панели гардероба.")})
        return

    state["style_changing"] = new_style_id
    try:
        if ws:
            await ws.send_json({"type": "system", "text": (
                f"🎨 Меняю стиль на «{new_style_id}»: рисую {len(default_oids)} "
                f"базовых набора (~20 минут, чат недоступен). Остальные костюмы "
                f"можно будет подготовить после.")})
        await loop.run_in_executor(None, _llama_mgr.stop)
        try:
            catalog = state.get("drawing_catalog")
            for oid in default_oids:
                seed = wardrobe.ensure_seed(oid)
                for step in required_steps():
                    await _render_outfit_step(state, oid, step, seed, loop)
                    wardrobe.mark_step(oid, step)
                await _align_outfit_set(state, oid, loop)
                wardrobe.mark_prepared(oid)
                if oid == default_oid:
                    _sync_default_slot_from_outfit(state, oid)
                if ws:
                    outfit = catalog.outfits.get(oid) if catalog else None
                    await ws.send_json({"type": "system", "text": (
                        f"  ✓ набор «{(outfit.name if outfit else oid)}» готов")})
        finally:
            try:
                await loop.run_in_executor(
                    None, lambda: (_release_comfy(), _llama_mgr.start()))
            except Exception:
                pass
    finally:
        state["style_changing"] = None

    if ws:
        await ws.send_json({"type": "system", "text": (
            "✓ Стиль применён. Базовые наборы готовы; остальные костюмы теперь "
            "доступны для подготовки в новом стиле.")})
    await _send_portrait_updated(state, ws)


def _wardrobe_outfit_hair(state: dict, catalog, current_outfit: dict | None) -> bool:
    oid = (current_outfit or {}).get("id")
    if not oid or catalog is None:
        return False
    try:
        from drawing.assets import outfit_hairstyle_active
        from services.self_styling import character_base_appearance
        outfit = catalog.outfits.get(oid)
        if outfit is None or not getattr(outfit, "hairstyle_tags", ()):
            return False
        rid = getattr(state["config"].drawing, "renderer_id", "sdxl") or "sdxl"
        return bool(outfit_hairstyle_active(character_base_appearance(state), outfit, rid))
    except Exception:
        return False


def _wardrobe_styling(state: dict, *, outfit_hair: bool = False) -> dict | None:
    idy = state.get("identity")
    try:
        from services import gacha as _gacha
        if not _gacha.has_gacha(idy):
            return None
        allow_nsfw, cur_len = _gacha_env(state)
        return _gacha.collection(idy, allow_nsfw=allow_nsfw, cur_len=cur_len,
                                 outfit_hair=outfit_hair) or None
    except Exception as e:
        print(f"[wardrobe] styling section failed: {type(e).__name__}: {e}")
        return None


def _wardrobe_current_outfit(state: dict, catalog) -> dict | None:
    oid = state.get("runtime_portrait_outfit_id")
    is_default = not oid
    if is_default:
        oid = state.get("character_default_outfit_id")
    if not oid:
        return None
    outfit = catalog.outfits.get(oid) if catalog is not None else None
    return {"id": oid, "name": (getattr(outfit, "name", "") or oid),
            "default": is_default}


def _wardrobe_overview(state: dict) -> dict:
    catalog = state.get("drawing_catalog")
    wardrobe = _get_wardrobe(state)
    persona = state.get("persona")
    current_outfit = _wardrobe_current_outfit(state, catalog)
    styling = _wardrobe_styling(
        state, outfit_hair=_wardrobe_outfit_hair(state, catalog, current_outfit))
    if catalog is None or wardrobe is None or persona is None:
        return {"outfits": [], "preparing": None,
                "current_outfit": current_outfit, "styling": styling}
    drawing = state["config"].drawing
    policy = persona.outfit_policy
    available = catalog.compatible_outfits(
        renderer_id=drawing.renderer_id,
        max_rating=drawing.max_rating,
        current_tier=persona.tier,
        character_id=state.get("character_id"),
        character_pair=pair_of(state.get("character")),
        character_archetypes=persona.archetypes,
        character_tag_gates=dict(policy.tag_tier_gates) if policy else {},
        character_blocked_tags=list(policy.blocked_tags) if policy else [],
    )
    preparing = state.get("wardrobe_preparing")
    current = current_outfit["id"] if current_outfit else None
    protected = set(state.get("character_outfit_ids") or [])
    outfits = []
    for o in available:
        st = wardrobe.status(o.id, preparing_now=preparing)
        st.update({"id": o.id, "name": o.name or o.id, "rating": o.rating,
                   "current": o.id == current, "protected": o.id in protected})
        outfits.append(st)
    outfits.sort(key=lambda s: (not s["preparing"], not s["prepared"],
                                not s["queued"], s["name"]))
    return {"outfits": outfits, "preparing": preparing,
            "current_outfit": current_outfit, "styling": styling}


@app.get("/api/wardrobe")
async def get_wardrobe_overview():
    return _wardrobe_overview(_get_state())


@app.post("/api/wardrobe/prepare")
async def post_wardrobe_prepare(payload: dict):
    s = _get_state()
    outfit_id = str(payload.get("outfit_id") or "").strip()
    catalog = s.get("drawing_catalog")
    wardrobe = _get_wardrobe(s)
    if not outfit_id or catalog is None or outfit_id not in catalog.outfits:
        return {"error": f"неизвестный костюм {outfit_id!r}"}
    if wardrobe is None:
        return {"error": "персонаж не загружен"}
    if wardrobe.is_prepared(outfit_id):
        return {"status": "prepared", **wardrobe.status(outfit_id)}
    if not wardrobe.is_queued(outfit_id):
        wardrobe.enqueue(outfit_id)
        return {"status": "queued", **wardrobe.status(outfit_id)}
    who = busy_with(s)
    if who is not None:
        return {"status": "busy", "busy_with": who,
                **wardrobe.status(outfit_id,
                                  preparing_now=s.get("wardrobe_preparing"))}
    ws = s.get("active_ws")
    loop = asyncio.get_event_loop()
    asyncio.create_task(_prepare_outfit_now(s, ws, loop, outfit_id))
    return {"status": "preparing",
            **wardrobe.status(outfit_id, preparing_now=outfit_id)}


@app.post("/api/wardrobe/regenerate")
async def post_wardrobe_regenerate(payload: dict):
    s = _get_state()
    outfit_id = str(payload.get("outfit_id") or "").strip()
    catalog = s.get("drawing_catalog")
    wardrobe = _get_wardrobe(s)
    if not outfit_id or catalog is None or outfit_id not in catalog.outfits:
        return {"error": f"неизвестный костюм {outfit_id!r}"}
    if wardrobe is None:
        return {"error": "персонаж не загружен"}
    if outfit_id in (s.get("character_outfit_ids") or []):
        return {"status": "protected",
                **wardrobe.status(outfit_id, preparing_now=s.get("wardrobe_preparing"))}
    if s.get("wardrobe_preparing") == outfit_id:
        return {"status": "busy", "busy_with": "outfit_prepare",
                **wardrobe.status(outfit_id, preparing_now=outfit_id)}

    character_id = s.get("character_id")
    outfit = catalog.outfits[outfit_id]
    outfit_name = outfit.name or outfit_id
    removed = wardrobe.delete_set(outfit_id)
    try:
        if character_id:
            av = (PROJECT_ROOT / "characters" / character_id
                  / f"avatar_chat_{outfit_id}.png")
            if av.exists():
                av.unlink()
    except OSError as e:
        print(f"[wardrobe] delete avatar {outfit_id} failed: {e}")
    worn = s.get("runtime_portrait_outfit_id") == outfit_id
    if worn:
        s["runtime_portrait_outfit_id"] = None
        ws = s.get("active_ws")
        if ws is not None:
            try:
                import time as _t
                await ws.send_json({
                    "type": "portrait_updated",
                    "url": (f"/api/characters/{character_id}/avatar/portrait"
                            f"?t={int(_t.time())}"),
                    "character_id": character_id,
                })
                await ws.send_json({
                    "type": "system",
                    "text": (f"👗 Набор «{outfit_name}» удалён и готовится заново — "
                             f"наряд сброшен на дефолтный."),
                })
            except Exception:
                pass
    wardrobe.enqueue(outfit_id)
    print(f"[wardrobe] regenerate {outfit_id}: removed {removed} file(s), "
          f"worn={worn}, re-queued ({character_id})")
    return {"status": "queued", "worn_reset": worn,
            **wardrobe.status(outfit_id, preparing_now=s.get("wardrobe_preparing"))}


_HAIRSTYLE_NOTES = {
    ("hair down",): "волосы распущены",
    ("high ponytail",): "волосы собраны в высокий хвост",
    ("high ponytail", "hair bow"): "волосы собраны в высокий хвост с бантом",
    ("two side up",): "два коротких хвостика по бокам, остальные волосы распущены",
}


def _outfit_hairstyle_note(state: dict, outfit) -> str:
    if outfit is None or not getattr(outfit, "hairstyle_tags", ()):
        return ""
    appearance = state.get("base_appearance")
    if appearance is None:
        return ""
    from drawing.assets import derive_hair_length, hair_length_ge
    cfg = state.get("config")
    rid = cfg.drawing.renderer_id if cfg is not None else "sdxl"
    if not hair_length_ge(derive_hair_length(appearance, rid),
                          getattr(outfit, "hairstyle_min_length", "")):
        return ""
    key = tuple(t.strip().lower() for t in outfit.hairstyle_tags if t)
    human = _HAIRSTYLE_NOTES.get(key)
    if human is None:
        human = "причёска изменена под наряд (" + ", ".join(key) + ")"
    return f"Причёска под этот наряд: {human} (не твоя обычная укладка)."


def _get_current_outfit_label(state: dict, outfit_id: str | None = None) -> str | None:
    if outfit_id is None:
        outfit_id = state.get("runtime_portrait_outfit_id")
    is_default = False
    if not outfit_id:
        outfit_id = state.get("character_default_outfit_id")
        is_default = True
    if not outfit_id:
        return None
    catalog = state.get("drawing_catalog")
    outfit = catalog.outfits.get(outfit_id) if catalog is not None else None
    name = (outfit.name if outfit else "") or outfit_id
    tags = ", ".join(outfit.tags[:3]) if (outfit and outfit.tags) else ""
    line = f"На тебе сейчас: {name} (outfit_id={outfit_id})"
    if is_default:
        line += " — твой обычный наряд, в него ты возвращаешься, когда ничего другого не надето"
    if tags:
        line += f". Образ: {tags}."
    elif not line.endswith("."):
        line += "."
    hs_note = _outfit_hairstyle_note(state, outfit)
    if hs_note:
        line += f" {hs_note}"
    try:
        from services.self_styling import describe, styling_state
        _nsfw_on = False
        try:
            _nsfw_on = (state["config"].drawing.max_rating != "sfw")
        except Exception:
            pass
        _stl = describe(styling_state(state.get("identity")),
                        include_intimate=_nsfw_on)
        if _stl:
            line += (f" Твой стайлинг поверх базовой внешности (эти теги идут "
                     f"в твои снимки, сохраняется между сессиями): {_stl}.")
        else:
            line += (" Стайлинга поверх базовой внешности сейчас нет — "
                     "обычная укладка, без украшений и макияжа.")
        try:
            from services import gacha as _gacha
            _idy = state.get("identity")
            if _gacha.has_gacha(_idy):
                _new = _gacha.unworn_unlocked(_idy, allow_nsfw=_nsfw_on)
                if _new:
                    line += (" Открыто для тебя, но пока не надето: "
                             + ", ".join(_gacha.item_hint(_idy, t) for t in _new)
                             + " — можешь надеть, когда захочешь.")
                line += (" У вещей свои открытые цвета: в скобках — какой один, "
                         "сколько (4c) или все; носить можно только открытый. "
                         "Какие цвета у вещи — style_self(options=\"<вещь>\"), всё "
                         "открытое в одном цвете — options=\"<цвет>\"; цвет наугад "
                         "не называй, проверь.")
                _sph = _gacha.spheres(_idy)
                if _sph:
                    line += (f" Сфер изменения накоплено: {_sph} — каждая открывает "
                             "один новый цвет вещи, которая уже есть; тратит их "
                             f"{_effective_honorific(state)} в гардеробе, не ты.")
                _innate = _gacha.innate_cores(_idy)
                if _innate:
                    line += (f" Часть образа у тебя своя от рождения ({len(_innate)} "
                             "укладок и видов макияжа открыты сразу, без билетов) — "
                             "их видно в style_self(options=...).")
                line += (" Носить можно только открытое: новое выпадает из "
                         f"билетов удачи, которые вы с {_effective_honorific(state)} "
                         "открываете вместе в чате — маленькая лотерея на двоих, "
                         "что выпадет, не знает никто; сама ты билеты не крутишь. "
                         "style_self показывает только доступное.")
        except Exception:
            pass
        line += (" Стайлинг меняется инструментом style_self в любой момент — "
                 "по просьбе или по твоему желанию: укладка в рамках твоей "
                 "длины волос, украшения, макияж; style_self(options=\"hair\"|"
                 "\"makeup\"|\"accessories\") покажет варианты, reset вернёт "
                 "обычный вид, reset_full снимет всё (волосы прямые распущенные).")
    except Exception:
        pass
    line += (" Наряд и стайлинг видны на твоём портрете — упоминай их в "
             "разговоре естественно, не в каждом сообщении.")
    if not is_default:
        line += (" Наряд держится до конца сессии или следующего change_outfit "
                 "— потом вернёшься в свой обычный.")
    return line


def _release_comfy() -> None:
    if _comfy_mgr is None:
        return
    _comfy_mgr.free_vram()


def drawing_available(state: dict) -> bool:
    config = state.get("config")
    if config is None or not getattr(config.image_gen, "enabled", False):
        return False
    if not _comfy_ready:
        return False
    from services import image_gen_setup as _ig
    return _ig.checkpoint_installed(PROJECT_ROOT)


def vision_available(state: dict) -> bool:
    config = state.get("config")
    if config is None:
        return False
    mmproj = (getattr(config.llm, "server_mmproj", "") or "").strip()
    if not mmproj:
        return False
    p = Path(mmproj)
    if not p.is_absolute():
        p = PROJECT_ROOT / mmproj
    return p.exists()


def _image_data_url(image: str) -> str:
    image = (image or "").strip()
    return image if image.startswith("data:") else f"data:image/jpeg;base64,{image}"


def _get_drawing_boundaries(state: dict) -> str | None:
    if not drawing_available(state):
        return None
    catalog = state.get("drawing_catalog")
    config = state.get("config")
    if not catalog or not config:
        return None
    try:
        from drawing import format_chat_boundaries
        from persona.evolution import compute_relationship_tier
        character = state["character"]
        identity = state["identity"]
        archetype = getattr(character, "archetype", "") or ""
        outfit_policy = getattr(character, "outfit_policy", None)
        return format_chat_boundaries(
            catalog=catalog,
            character_gender=gender_of(character),
            character_pair=pair_of(character),
            renderer_id=config.drawing.renderer_id,
            max_rating=config.drawing.max_rating,
            current_tier=state["persona"].tier,
            character_id=state["persona"].character_id,
            character_archetypes=state["persona"].archetypes,
            outfit_change_min_tier=config.drawing.outfit_change_min_tier,
            current_portrait_outfit_id=state.get("runtime_portrait_outfit_id"),
            character_tag_gates=outfit_policy.tag_tier_gates if outfit_policy else None,
            character_blocked_tags=list(outfit_policy.blocked_tags) if outfit_policy else None,
            wardrobe=_get_wardrobe(state),
            default_outfit_id=state.get("character_default_outfit_id"),
            outfit_label=_get_current_outfit_label(state),
            honorific=getattr(state.get("persona"), "honorific", "") or "Господин",
        )
    except Exception as e:
        print(f"[drawing] boundaries build failed: {e}")
        return None


@app.get("/api/debug/drawing/styles")
async def debug_list_styles():
    s = _get_state()
    catalog = s.get("drawing_style_catalog")
    if catalog is None:
        return {"error": "style catalog не инициализирован"}

    config = s["config"]

    char_override = None
    try:
        store = s.get("store")
        archive = store.get_archive(s["character_id"]) if store else None
        if archive and archive.has_entry("visual/style.yaml"):
            style_data = archive.read_yaml("visual/style.yaml")
            char_override = (style_data or {}).get("preferred_style_id")
    except Exception as e:
        print(f"[debug] cannot load char style override: {e}")

    return {
        "active": config.drawing.active_style_id,
        "character_override": char_override,
        "renderer_id": config.drawing.renderer_id,
        "styles": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "renderer_id": p.renderer_id,
                "tags": list(p.tags),
                "source": p.source,
            }
            for p in catalog.list_all()
        ],
    }


@app.post("/api/debug/drawing/set-style")
async def debug_set_style(payload: dict):
    s = _get_state()
    catalog = s.get("drawing_style_catalog")
    if catalog is None:
        return {"error": "style catalog не инициализирован"}

    style_id = (payload.get("style_id") or "").strip()
    import_code = (payload.get("import_code") or "").strip()

    if import_code:
        try:
            pack = catalog.import_code(import_code)
            style_id = pack.id
        except Exception as e:
            return {"error": f"import failed: {type(e).__name__}: {e}"}

    if not style_id:
        return {"error": "style_id обязателен (или import_code)"}

    pack = catalog.get(style_id)
    if pack is None:
        return {
            "error": f"style {style_id!r} не найден",
            "available": [p.id for p in catalog.list_all()],
        }

    s["config"].drawing.active_style_id = style_id

    return {
        "ok": True,
        "active": style_id,
        "applied": {
            "id": pack.id,
            "name": pack.name,
            "renderer_id": pack.renderer_id,
            "tags": list(pack.tags),
            "source": pack.source,
        },
    }


def _style_users(style_id: str, s: dict) -> list[str]:
    names = {}
    try:
        names = {row["id"]: row.get("name") or row["id"]
                 for row in s["store"].list_available()}
    except Exception:
        pass
    users = []
    root = PROJECT_ROOT / "characters"
    for wf in sorted(root.glob("*/wardrobe.json")) if root.is_dir() else []:
        try:
            data = json.loads(wf.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if (data.get("style") or "default") == style_id:
            users.append(names.get(wf.parent.name, wf.parent.name))
    return users


@app.post("/api/debug/drawing/delete-style")
async def debug_delete_style(payload: dict):
    from drawing.styles import StyleError
    s = _get_state()
    catalog = s.get("drawing_style_catalog")
    if catalog is None:
        return {"error": "каталог стилей не инициализирован"}
    style_id = str((payload or {}).get("style_id") or "").strip()
    pack = catalog.get(style_id) if style_id else None
    if pack is None:
        return {"error": f"стиль {style_id!r} не найден"}
    if pack.source != "user_imported":
        return {"error": "встроенный стиль удалить нельзя"}
    users = _style_users(style_id, s)
    if s["config"].drawing.active_style_id == style_id or users:
        who = ", ".join(users) or "у текущего персонажа"
        return {"error": f"стиль выбран: {who} — сначала выберите другой стиль"}
    try:
        catalog.remove_user(style_id)
    except (StyleError, OSError) as e:
        return {"error": f"не удалось удалить стиль: {e}"}
    print(f"[style] удалён импортированный стиль {style_id!r}")
    return {"ok": True, "removed": style_id}


@app.post("/api/debug/drawing/test_choice")
async def debug_test_choice(payload: dict):
    intent = (payload.get("intent") or "").strip()
    if not intent:
        return {"error": "intent пуст"}

    s = _get_state()
    catalog = s.get("drawing_catalog")
    if catalog is None:
        return {"error": "drawing catalog не инициализирован"}

    from drawing import (
        build_choice_prompt, parse_choice_response, validate_choice,
    )
    from persona.evolution import compute_relationship_tier

    config = s["config"]
    character = s["character"]
    identity = s["identity"]
    character_id = s["character_id"]
    archetype = getattr(character, "archetype", "") or ""

    current_tier = s["persona"].tier

    system_prompt = build_choice_prompt(
        character_name=character.name,
        character_gender=gender_of(character),
        character_pair=pair_of(character),
        user_intent=intent,
        catalog=catalog,
        renderer_id=config.drawing.renderer_id,
        max_rating=config.drawing.max_rating,
        current_tier=current_tier,
        character_id=character_id,
        character_archetypes=s["persona"].archetypes,
    )

    import asyncio
    loop = asyncio.get_event_loop()
    lifecycle = get_lifecycle()
    try:
        async with lifecycle.using():
            raw_response = await loop.run_in_executor(
                None,
                lambda: s["client"].chat(
                    messages=[{"role": "user", "content": "Сделай выбор."}],
                    system=system_prompt,
                    thinking=s["client"].live_thinking(),
                    live_turn=True,
                    label="Debug: draw choice",
                )
            )
    except Exception as e:
        return {
            "intent": intent,
            "system_prompt_size": len(system_prompt),
            "system_prompt_preview": system_prompt[:500],
            "llm_error": f"{type(e).__name__}: {e}",
        }

    parse_error = None
    parsed = None
    try:
        choice = parse_choice_response(raw_response)
        parsed = {
            "outfit_id": choice.outfit_id,
            "scene_id": choice.scene_id,
            "pose_id": choice.pose_id,
            "modifiers": choice.modifiers,
            "requested_unavailable": choice.requested_unavailable,
            "refusal_reason": choice.refusal_reason,
            "is_generate": choice.is_generate(),
            "is_refusal": choice.is_refusal(),
        }
    except Exception as e:
        parse_error = f"{type(e).__name__}: {e}"

    gate_info = None
    if parsed and not parsed.get("is_refusal"):
        try:
            gate = validate_choice(
                choice,
                catalog=catalog,
                renderer_id=config.drawing.renderer_id,
                max_rating=config.drawing.max_rating,
                current_tier=current_tier,
                character_id=character_id,
                character_archetypes=s["persona"].archetypes,
            )
            gate_info = {
                "valid": gate.valid,
                "errors": gate.errors,
                "warnings": gate.warnings,
            }
        except Exception as e:
            gate_info = {"exception": f"{type(e).__name__}: {e}"}

    return {
        "intent": intent,
        "system_prompt_size": len(system_prompt),
        "raw_response": raw_response,
        "raw_response_length": len(raw_response),
        "parsed": parsed,
        "parse_error": parse_error,
        "gate": gate_info,
        "current_tier": current_tier,
    }


@app.post("/api/debug/llm_raw")
async def debug_llm_raw(payload: dict):
    import asyncio
    system = (payload.get("system") or "").strip()
    user = (payload.get("user") or "Ответь.").strip()
    thinking = bool(payload.get("thinking", False))
    s = _get_state()
    loop = asyncio.get_event_loop()
    lifecycle = get_lifecycle()
    try:
        async with lifecycle.using():
            resp = await loop.run_in_executor(
                None,
                lambda: s["client"].chat(
                    messages=[{"role": "user", "content": user}],
                    system=system,
                    thinking=thinking,
                    label="Debug: llm_raw",
                ),
            )
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    return {"response": resp, "length": len(resp)}


@app.get("/api/capabilities")
async def get_capabilities():
    s = _get_state()
    return {"drawing": drawing_available(s), "vision": vision_available(s)}


def _setup_choice() -> str:
    cfg = _app_config
    return (getattr(getattr(cfg, "llm", None), "model_choice", "") or "") if cfg else ""


@app.get("/api/setup/status")
async def setup_status_endpoint():
    from services import setup as _setup_mod
    return _setup_mod.setup_status(PROJECT_ROOT, _setup_choice())


@app.post("/api/setup/start")
async def setup_start_endpoint(payload: dict | None = None):
    from config import LLM_MODELS, apply_model_choice
    from services import setup as _setup_mod
    preset = ((payload or {}).get("preset") or "").strip().lower()
    if preset:
        if preset not in _setup_mod.wizard_preset_keys() or preset not in LLM_MODELS:
            return {"error": f"неизвестный пресет: {preset!r}"}
        if _app_config is not None and preset != _app_config.llm.model_choice:
            apply_model_choice(_app_config, preset)
            apply_and_save(_app_config, {"llm.model_choice": preset}, PROJECT_ROOT)
            try:
                if _state and _state.get("client") is not None:
                    from llm.backends import get_backend
                    _state["client"].backend = get_backend(_app_config.llm.family)
                    _state["client"].fast_post_session = bool(
                        LLM_MODELS[preset].get("fast_post", False))
            except Exception as e:
                print(f"[setup] client update failed: {e}")
            print(f"[setup] мастер: выбран пресет {preset} ({LLM_MODELS[preset]['label']})")
    queued = _setup_mod.start_downloads(PROJECT_ROOT, _setup_choice())
    return {"started": True, "queued": queued, "choice": _setup_mod.resolve_wizard_choice(_setup_choice())}


@app.post("/api/setup/agreement")
async def setup_agreement_endpoint(payload: dict | None = None):
    from services import agreement
    if (payload or {}).get("adult") is not True:
        return {"error": "нужно подтвердить, что вам исполнилось 18 лет"}
    rec = agreement.accept(PROJECT_ROOT)
    print(f"[setup] соглашение принято (редакция {rec['version']})")
    return {"ok": True, "version": rec["version"]}


@app.get("/api/imagegen/status")
async def imagegen_status_endpoint():
    from services import image_gen_setup as _ig
    st = _ig.status(PROJECT_ROOT)
    st["drawing_available"] = drawing_available({"config": _app_config})
    return st


@app.post("/api/imagegen/install")
async def imagegen_install_endpoint(payload: dict):
    from services import image_gen_setup as _ig
    non_agpl_only = bool((payload or {}).get("non_agpl_only"))
    st = _ig.status(PROJECT_ROOT)
    missing = set(st["missing"])
    agpl_missing = [k for k in st["agpl_components"] if k in missing]
    if not non_agpl_only and agpl_missing and not (payload or {}).get("agpl_consent"):
        return {"started": False, "error": "agpl_consent_required",
                "agpl_components": agpl_missing}
    queued = _ig.start_install(PROJECT_ROOT, include_agpl=not non_agpl_only)
    return {"started": True, "queued": queued}


@app.post("/api/imagegen/checkpoint")
async def imagegen_checkpoint_endpoint(payload: dict):
    from services import image_gen_setup as _ig
    src = (payload or {}).get("path", "")
    if not src:
        return {"ok": False, "error": "no path"}
    res = _ig.set_checkpoint_from_path(PROJECT_ROOT, src)
    pl = res.get("pipeline") if isinstance(res, dict) else None
    if res.get("ok") and pl:
        try:
            from api.settings_store import apply_and_save
            apply_and_save(_get_state()["config"],
                           {"image_gen.workflow_default": pl["workflow"]}, PROJECT_ROOT)
        except Exception as e:
            print(f"[imagegen] не удалось зафиксировать workflow: {e}")
    return res


@app.get("/api/addons")
async def addons_list_endpoint():
    from services import addons as _addons
    return {"addons": _addons.list_for_api(PROJECT_ROOT)}


@app.post("/api/addons/install")
async def addons_install_endpoint(payload: dict):
    from services import addons as _addons
    path = str((payload or {}).get("path") or "").strip()
    if not path:
        return {"ok": False, "error": "не указан путь к пакету"}
    return _addons.install_from_zip(PROJECT_ROOT, path)


@app.post("/api/addons/{addon_id}")
async def addons_toggle_endpoint(addon_id: str, payload: dict):
    from services import addons as _addons
    enabled = bool((payload or {}).get("enabled"))
    state = _addons.set_enabled(PROJECT_ROOT, addon_id, enabled)
    try:
        _addons.apply_rating_ceiling(_get_state()["config"], PROJECT_ROOT)
    except Exception as e:
        print(f"[addons] apply_rating_ceiling: {e}")
    return {"ok": True, "addon": addon_id, "enabled": state.get(addon_id, enabled)}


@app.post("/api/debug/drawing/draw_router")
async def debug_draw_router(payload: dict):
    import asyncio
    from drawing.intent_router import classify_draw_request, looks_like_image_request
    message = (payload.get("message") or "").strip()
    if not message:
        return {"error": "message пуст"}
    nsfw_enabled = bool(payload.get("nsfw_enabled", True))
    prefilter = bool(payload.get("prefilter", True))
    s = _get_state()

    def llm_chat(system: str, user: str) -> str:
        return s["client"].chat(
            messages=[{"role": "user", "content": user}],
            system=system, thinking=False, label="Debug: draw_router")

    loop = asyncio.get_event_loop()
    lifecycle = get_lifecycle()
    try:
        async with lifecycle.using():
            res = await loop.run_in_executor(
                None, lambda: classify_draw_request(
                    message, llm_chat, nsfw_enabled=nsfw_enabled,
                    prefilter=prefilter))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    return {
        "message": message,
        "nsfw_enabled": nsfw_enabled,
        "prefilter_hit": looks_like_image_request(message),
        "ran": res is not None,
        "result": res,
    }


@app.post("/api/debug/semantic")
async def debug_semantic(payload: dict):
    import asyncio
    import time as _t
    from tools import semantic as sm
    tool = (payload.get("tool") or "").strip()
    intent = (payload.get("intent") or "").strip()
    execute = bool(payload.get("execute", False))
    if not tool or not intent:
        return {"error": "нужны tool и intent",
                "registered": sm.registered_names()}

    s = _get_state()
    try:
        s["memory"]._ensure_registry()
    except Exception:
        pass
    defn = sm.get_processor(tool)
    if defn is None:
        return {"error": f"semantic tool {tool!r} не зарегистрирован",
                "registered": sm.registered_names()}

    deps = sm.SemanticDeps(memory=s.get("memory"), now=_t.time(),
                           debug=True, persona=s.get("persona"))

    def _llm_chat(system: str, user: str) -> str:
        return s["client"].chat(
            messages=[{"role": "user", "content": user}],
            system=system, thinking=False, label=f"debug:semantic:{tool}")

    loop = asyncio.get_event_loop()
    lifecycle = get_lifecycle()

    if not execute:
        def _extract():
            system = defn.build_extract_system(deps)
            raw = _llm_chat(system, intent)
            return raw, defn.parse(raw or "")
        try:
            async with lifecycle.using():
                raw, parsed = await loop.run_in_executor(None, _extract)
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}
        return {"tool": tool, "intent": intent, "executed": False,
                "parsed": parsed, "raw": (raw or "")[:400]}

    action = {"kind": "semantic", "tool": tool, "intent": intent}
    try:
        async with lifecycle.using():
            res = await loop.run_in_executor(
                None, lambda: sm.process_semantic_action(
                    action, llm_chat=_llm_chat, deps=deps))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    return {"tool": tool, "intent": intent, "executed": True,
            "ok": res.ok, "message": res.message, "data": res.data}


@app.post("/api/debug/retrieval")
async def debug_retrieval(payload: dict):
    import asyncio
    from memory import retrieval as _rt
    message = (payload.get("message") or "").strip()
    if not message:
        return {"error": "message пуст"}
    s = _get_state()
    mem = s.get("memory")
    if mem is None:
        return {"error": "память недоступна"}

    def _chat(system: str, user: str) -> str:
        return s["client"].chat(
            messages=[{"role": "user", "content": user}],
            system=system, thinking=False, label="debug:retrieval")

    loop = asyncio.get_event_loop()
    lifecycle = get_lifecycle()
    try:
        async with lifecycle.using():
            plan = await loop.run_in_executor(
                None, lambda: _rt.plan_retrieval(message, mem, _chat))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    if plan is None:
        return {"message": message, "ran": False,
                "reason": "нет записей в памяти или банальная реплика"}
    recalled, absent = _rt.execute_retrieval(plan, mem, user_text=message)
    return {
        "message": message,
        "index": _rt.build_memory_index(mem),
        "plan": {"recall": plan.recall, "queries": plan.queries, "absent": plan.absent},
        "recalled": [f"[{r.record_id}] {r.title} ({r.type})" for r in recalled],
        "absent": absent,
    }


@app.post("/api/debug/extract_loops")
async def debug_extract_loops(payload: dict | None = None):
    import asyncio
    from memory.loop_extraction import extract_loops_from_session
    s = _get_state()
    payload = payload or {}
    mem = s.get("memory")
    if mem is None:
        return {"error": "память недоступна"}
    msgs = payload.get("messages")
    if not msgs:
        hist = s.get("history")
        msgs = hist.get_messages() if hist else []
    if not msgs or len(msgs) < 2:
        return {"error": "нужно ≥2 сообщений (передай messages или поговори в сессии)"}

    char = s["character"]
    honorific = resolve_honorific(char)
    loop = asyncio.get_event_loop()
    lifecycle = get_lifecycle()
    try:
        async with lifecycle.using():
            applied = await loop.run_in_executor(
                None, lambda: extract_loops_from_session(
                    msgs, mem, char_name=char.name, honorific=honorific,
                    gender=getattr(char, "gender", "female")))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    try:
        _save_memory()
    except Exception:
        pass
    return {
        "applied": applied,
        "open_loops": [
            {"title": l.title, "kind": (l.details or {}).get("kind"),
             "subject": (l.details or {}).get("subject"),
             "salience": (l.details or {}).get("salience")}
            for l in mem.get_open_loops()],
    }


@app.post("/api/debug/session_extract")
async def debug_session_extract(payload: dict | None = None):
    import asyncio
    from memory.entity_schema import is_entity_card
    from memory.loop_extraction import extract_loops_from_session
    from memory.relation_extraction import extract_relations_from_session
    from memory.topic_extraction import extract_topic_opinions_from_session
    s = _get_state()
    payload = payload or {}
    mem = s.get("memory")
    if mem is None:
        return {"error": "память недоступна"}
    msgs = payload.get("messages") or (
        s["history"].get_messages() if s.get("history") else [])
    if not msgs or len(msgs) < 2:
        return {"error": "нужно ≥2 сообщений (передай messages)"}
    char = s["character"]
    honorific = resolve_honorific(char)
    gender = getattr(char, "gender", "female")
    loop = asyncio.get_event_loop()
    lifecycle = get_lifecycle()

    def _run():
        before = len(mem.records)
        mem.extract_from_session(msgs, char_name=char.name, honorific=honorific,
                                 gender=gender)
        ents = len(mem.records) - before
        rr = extract_relations_from_session(msgs, mem, char_name=char.name,
                                            honorific=honorific, gender=gender)
        lr = extract_loops_from_session(msgs, mem, char_name=char.name,
                                        honorific=honorific, gender=gender)
        tp = extract_topic_opinions_from_session(msgs, mem, char_name=char.name,
                                                 honorific=honorific, gender=gender)
        return ents, rr, lr, tp

    try:
        async with lifecycle.using():
            ents, rr, lr, tp = await loop.run_in_executor(None, _run)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    try:
        _save_memory()
    except Exception:
        pass
    cards = [r for r in mem.records if is_entity_card(r)]
    return {
        "entities_added": ents, "relations": rr, "loops": lr, "topics": tp,
        "cards": [{"title": c.title, "type": c.details.get("entity_type"),
                   "relations": c.details.get("relations"),
                   "my_opinion": c.details.get("my_opinion")} for c in cards],
        "open_loops": [l.title for l in mem.get_open_loops()],
    }


@app.get("/api/debug/loops")
async def debug_get_loops():
    s = _get_state()
    mem = s.get("memory")
    if mem is None:
        return {"error": "память недоступна"}
    return {
        "open_loops": [
            {"title": l.title,
             "kind": (l.details or {}).get("kind"),
             "subject": (l.details or {}).get("subject"),
             "salience": (l.details or {}).get("salience"),
             "my_opinion": (l.details or {}).get("my_opinion")}
            for l in mem.get_open_loops()
        ],
    }


@app.get("/api/debug/profile")
async def debug_get_profile():
    s = _get_state()
    mem = s.get("memory")
    if mem is None:
        return {"error": "память недоступна"}
    prof = mem.get_user_profile() or {}
    return {
        "summary": prof.get("summary", "") or "",
        "preferences": prof.get("preferences") or [],
        "rules": prof.get("rules") or [],
    }


@app.post("/api/debug/grammar")
async def debug_grammar(payload: dict):
    from persona.grammar import correct_grammar
    s = _get_state()
    text = ((payload or {}).get("text") or "")
    if not text.strip():
        return {"error": "нужен непустой text"}
    dialogue = (payload or {}).get("messages")
    if dialogue is None:
        hist = s.get("history")
        dialogue = hist.get_messages() if hist else []
    try:
        await get_lifecycle().ensure_loaded()
    except Exception as e:
        return {"error": f"модель недоступна: {e}"}
    loop = asyncio.get_event_loop()
    try:
        corrected = await loop.run_in_executor(
            None, lambda: correct_grammar(
                s["client"], text, character=s["character"], dialogue=dialogue,
                honorific=(getattr(s["memory"], "user_honorific", None)
                           or resolve_honorific(s["character"]))))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    return {"original": text, "corrected": corrected}


@app.post("/api/debug/evolve_opinions")
async def debug_evolve_opinions(payload: dict | None = None):
    import asyncio
    from memory.entity_schema import is_entity_card
    from persona.evolution import evolve_entity_opinions
    s = _get_state()
    mem = s.get("memory")
    if mem is None:
        return {"error": "память недоступна"}
    loop = asyncio.get_event_loop()
    lifecycle = get_lifecycle()
    try:
        async with lifecycle.using():
            updated = await loop.run_in_executor(
                None, lambda: evolve_entity_opinions(s["client"], s.get("persona"), mem, 0))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    try:
        _save_memory()
    except Exception:
        pass
    return {"updated": updated, "opinions": [
        {"title": c.title, "type": c.details.get("entity_type"),
         "opinion": c.details.get("my_opinion")}
        for c in mem.records if is_entity_card(c) and (c.details or {}).get("my_opinion")]}


@app.post("/api/debug/form_topic_opinions")
async def debug_form_topic_opinions(payload: dict | None = None):
    import asyncio
    from memory.entity_schema import ENTITY_TYPE_TOPIC, is_entity_card
    from memory.topic_extraction import form_topic_opinions_from_material
    s = _get_state()
    payload = payload or {}
    mem = s.get("memory")
    persona = s.get("persona")
    if mem is None or persona is None:
        return {"error": "состояние неполно (memory/persona)"}
    material = (payload.get("material") or "").strip()
    if not material:
        refls = [r for r in getattr(mem, "records", [])
                 if getattr(r, "type", "") == "рефлексия" and not r.is_forgotten]
        material = "\n".join(f"- {r.title}: {(r.details or {}).get('description', '')}"
                             for r in refls[-15:])
    if not material.strip():
        return {"error": "нет материала (передай material или накопи рефлексии)"}
    loop = asyncio.get_event_loop()
    lifecycle = get_lifecycle()
    try:
        async with lifecycle.using():
            res = await loop.run_in_executor(
                None, lambda: form_topic_opinions_from_material(
                    s["client"], persona, mem, material))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    try:
        _save_memory()
    except Exception:
        pass
    return {"formed": res, "topics": [
        {"title": c.title, "my_opinion": c.details.get("my_opinion")}
        for c in mem.records if is_entity_card(c)
        and (c.details or {}).get("entity_type") == ENTITY_TYPE_TOPIC]}


@app.post("/api/debug/evolve_loop_opinions")
async def debug_evolve_loop_opinions(payload: dict | None = None):
    import asyncio
    from memory.loops import LOOP_TYPE
    from persona.evolution import evolve_loop_opinions
    s = _get_state()
    mem = s.get("memory")
    persona = s.get("persona")
    if mem is None or persona is None:
        return {"error": "состояние неполно (memory/persona)"}
    loop = asyncio.get_event_loop()
    lifecycle = get_lifecycle()
    try:
        async with lifecycle.using():
            updated = await loop.run_in_executor(
                None, lambda: evolve_loop_opinions(s["client"], persona, mem))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    try:
        _save_memory()
    except Exception:
        pass
    return {"updated": updated, "loops": [
        {"title": r.title, "kind": (r.details or {}).get("kind"),
         "subject": (r.details or {}).get("subject"),
         "my_opinion": (r.details or {}).get("my_opinion")}
        for r in mem.records if r.type == LOOP_TYPE and not r.is_forgotten]}


@app.post("/api/debug/extract_rules")
async def debug_extract_rules(payload: dict | None = None):
    import asyncio
    s = _get_state()
    mem = s.get("memory")
    char = s.get("character")
    hist = s.get("history")
    if mem is None or hist is None:
        return {"error": "состояние неполно (memory/history)"}
    messages = hist.get_messages()
    before = list((mem.get_user_profile() or {}).get("rules") or [])
    loop = asyncio.get_event_loop()
    lifecycle = get_lifecycle()
    try:
        async with lifecycle.using():
            added = await loop.run_in_executor(None, lambda: mem.extract_user_rules(
                messages, char_name=getattr(char, "name", ""),
                honorific=resolve_honorific(char) if char else "Господин"))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    try:
        _save_memory()
    except Exception:
        pass
    return {"added": added, "before": before,
            "after": list((mem.get_user_profile() or {}).get("rules") or [])}


@app.post("/api/debug/extract_preferences")
async def debug_extract_preferences(payload: dict | None = None):
    import asyncio
    s = _get_state()
    mem = s.get("memory")
    char = s.get("character")
    hist = s.get("history")
    if mem is None or hist is None:
        return {"error": "состояние неполно (memory/history)"}
    messages = hist.get_messages()
    loop = asyncio.get_event_loop()
    lifecycle = get_lifecycle()
    try:
        async with lifecycle.using():
            routed = await loop.run_in_executor(None, lambda: mem.extract_preferences(
                messages, char_name=getattr(char, "name", ""),
                honorific=resolve_honorific(char) if char else "Господин"))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    try:
        _save_memory()
    except Exception:
        pass
    cards = [{"title": r.title, "entity_type": (r.details or {}).get("entity_type"),
              "user_preference": (r.details or {}).get("user_preference")}
             for r in mem.records if not r.is_forgotten and (r.details or {}).get("user_preference")]
    return {"routed": routed,
            "profile_preferences": (mem.get_user_profile() or {}).get("preferences") or [],
            "cards_with_pref": cards}


@app.post("/api/debug/infer_preferences")
async def debug_infer_preferences(payload: dict | None = None):
    import asyncio
    s = _get_state()
    mem = s.get("memory")
    char = s.get("character")
    if mem is None:
        return {"error": "нет memory"}
    material = str((payload or {}).get("material") or "").strip()
    if not material:
        refls = [r for r in mem.records
                 if getattr(r, "type", "") == "рефлексия" and not r.is_forgotten]
        refls.sort(key=lambda r: r.created_at or 0.0)
        material = ("<рефлексии>\n" + "\n".join(
            f"- {(r.details or {}).get('description') or r.title}" for r in refls[-20:])
            + "\n</рефлексии>")
    honorific = resolve_honorific(char) if char else "Господин"
    loop = asyncio.get_event_loop()
    lifecycle = get_lifecycle()
    try:
        async with lifecycle.using():
            routed = await loop.run_in_executor(
                None, lambda: mem.infer_preferences_from_material(material, honorific))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    try:
        _save_memory()
    except Exception:
        pass
    cards = [{"title": r.title, "entity_type": (r.details or {}).get("entity_type"),
              "user_preference": (r.details or {}).get("user_preference")}
             for r in mem.records if not r.is_forgotten and (r.details or {}).get("user_preference")]
    return {"routed": routed, "material_used": material[:300],
            "profile_preferences": (mem.get_user_profile() or {}).get("preferences") or [],
            "cards_with_pref": cards}


@app.post("/api/debug/consolidate_prefs")
async def debug_consolidate_prefs(payload: dict | None = None):
    import asyncio
    s = _get_state()
    mem = s.get("memory")
    char = s.get("character")
    if mem is None:
        return {"error": "нет memory"}
    honorific = resolve_honorific(char) if char else "Господин"
    loop = asyncio.get_event_loop()
    lifecycle = get_lifecycle()
    try:
        async with lifecycle.using():
            info = await loop.run_in_executor(
                None, lambda: mem.consolidate_preferences_rules(honorific))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    try:
        _save_memory()
    except Exception:
        pass
    prof = mem.get_user_profile() or {}
    return {"info": info,
            "preferences": prof.get("preferences") or [],
            "rules": prof.get("rules") or []}


@app.post("/api/debug/update_summary")
async def debug_update_summary(payload: dict | None = None):
    import asyncio
    from persona.evolution import update_master_summary
    s = _get_state()
    mem = s.get("memory")
    persona = s.get("persona")
    if mem is None or persona is None:
        return {"error": "состояние неполно (memory/persona)"}
    before = (mem.get_user_profile() or {}).get("summary", "")
    loop = asyncio.get_event_loop()
    lifecycle = get_lifecycle()
    try:
        async with lifecycle.using():
            changed = await loop.run_in_executor(
                None, lambda: update_master_summary(s["client"], persona, mem))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    try:
        _save_memory()
    except Exception:
        pass
    return {"changed": bool(changed),
            "summary_before": before,
            "summary_after": (mem.get_user_profile() or {}).get("summary", "")}


@app.post("/api/debug/evolve_relationship_axes")
async def debug_evolve_relationship_axes(payload: dict | None = None):
    import asyncio
    from persona.evolution import evolve_relationship_axes, compute_relationship_tier
    from persona.relationship_axes import (
        RELATIONSHIP_AXES, current_axis_values, select_relationship_axis_text)
    s = _get_state()
    persona = s.get("persona")
    if persona is None:
        return {"error": "состояние неполно (persona)"}
    payload = payload or {}
    refls = payload.get("reflections") or ""
    if isinstance(refls, list):
        refls = "\n".join(f"- {r}" for r in refls)
    trends = payload.get("trends") or ""
    loop = asyncio.get_event_loop()
    lifecycle = get_lifecycle()
    try:
        async with lifecycle.using():
            moved = await loop.run_in_executor(
                None, lambda: evolve_relationship_axes(
                    s["client"], persona, reflections_text=refls, trends_text=trends))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    try:
        from api.session_manager import save_state_to_disk
        save_state_to_disk(s, with_identity=True)
    except Exception:
        pass
    identity = persona.identity
    character = persona.character
    vals = current_axis_values(identity)
    return {"moved": moved,
            "tier": compute_relationship_tier(identity, character),
            "axes": {a: {"value": round(vals.get(a, 0.0), 3),
                         "text": select_relationship_axis_text(character, a, vals.get(a, 0.0))}
                     for a in RELATIONSHIP_AXES}}


@app.post("/api/debug/set_relationship_axes")
async def debug_set_relationship_axes(payload: dict):
    from persona.evolution import compute_relationship_tier
    from persona.relationship_axes import (
        RELATIONSHIP_AXES, REL_AXIS_PREFIX, PRIMARY_TIER_AXIS,
        current_axis_values, select_relationship_axis_text)
    s = _get_state()
    persona = s.get("persona")
    if persona is None:
        return {"error": "состояние неполно (persona)"}
    identity = persona.identity
    character = persona.character
    identity.ensure_relationship_axes(character)
    by_id = {st.id: st for st in identity.relationship_statements}
    changed = {}
    for axis in RELATIONSHIP_AXES:
        if axis in (payload or {}):
            try:
                v = max(0.0, min(1.0, float(payload[axis])))
            except (TypeError, ValueError):
                continue
            st = by_id.get(f"{REL_AXIS_PREFIX}{axis}")
            if st is not None:
                st.axis_value = v
                st.axis_momentum = 0.0
                st.text = select_relationship_axis_text(character, axis, v, fallback=st.text)
                changed[axis] = v
    prim = by_id.get(f"{REL_AXIS_PREFIX}{PRIMARY_TIER_AXIS}")
    if prim is not None:
        identity.relationship_level = prim.axis_value
    identity.save()
    try:
        from api.session_manager import save_state_to_disk
        save_state_to_disk(s, with_identity=True)
    except Exception:
        pass
    return {"changed": changed, "tier": compute_relationship_tier(identity, character),
            "axes": current_axis_values(identity)}


@app.post("/api/debug/reassess_regard")
async def debug_reassess_regard(payload: dict | None = None):
    import asyncio
    from persona.evolution import reassess_master_regard
    s = _get_state()
    persona = s.get("persona")
    if persona is None:
        return {"error": "состояние неполно (persona)"}
    payload = payload or {}
    refls = payload.get("reflections") or ""
    if isinstance(refls, list):
        refls = "\n".join(f"- {r}" for r in refls)
    trends = payload.get("trends") or ""

    def _regard_text():
        return next((st.text for st in persona.identity.relationship_statements
                     if st.id == "rel_master_to_me"), "")
    before = _regard_text()
    loop = asyncio.get_event_loop()
    lifecycle = get_lifecycle()
    try:
        async with lifecycle.using():
            changed = await loop.run_in_executor(
                None, lambda: reassess_master_regard(
                    s["client"], persona, reflections_text=refls, trends_text=trends))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    try:
        from api.session_manager import save_state_to_disk
        save_state_to_disk(s, with_identity=True)
    except Exception:
        pass
    return {"changed": changed, "before": before, "after": _regard_text()}


@app.post("/api/debug/drawing/multiround")
async def debug_multiround(payload: dict):
    import asyncio
    intent = (payload.get("intent") or "").strip()
    if not intent:
        return {"error": "intent пуст"}
    s = _get_state()
    drawing = s["config"].drawing
    catalog = s.get("drawing_catalog")
    if catalog is None:
        return {"error": "drawing catalog не инициализирован"}

    from drawing.tag_rounds import select_tags

    def llm_chat(system: str, user: str) -> str:
        return s["client"].chat(
            messages=[{"role": "user", "content": user}],
            system=system, thinking=False, label="Debug: tag round")

    loop = asyncio.get_event_loop()
    lifecycle = get_lifecycle()
    try:
        async with lifecycle.using():
            result = await loop.run_in_executor(
                None, lambda: select_tags(intent, llm_chat,
                                          max_rating=drawing.max_rating))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

    assembled = None
    try:
        from drawing import BaseAppearance
        from drawing.zones import filter_fragment
        store = s.get("store")
        cid = s["character_id"]
        base = BaseAppearance()
        archive = store.get_archive(cid) if store else None
        if archive and archive.has_entry("visual/appearance.yaml"):
            base = BaseAppearance.from_dict(
                archive.read_yaml("visual/appearance.yaml"))
        outfit_id = (payload.get("outfit_id")
                     or s.get("runtime_portrait_outfit_id") or "maid_classic")
        outfit = catalog.outfits.get(outfit_id)
        parts: list[str] = []
        if base.positive_for("sdxl"):
            parts.append(base.positive_for("sdxl"))
        if outfit and "sdxl" in outfit.renderer_prompts:
            parts.append(outfit.renderer_prompts["sdxl"].positive)
        if result["tags"]:
            parts.append(", ".join(result["tags"]))
        sc = s.get("drawing_style_catalog")
        if sc is not None:
            pack = sc.resolve(active_style_id=drawing.active_style_id,
                              character_override_id=None, renderer_id="sdxl")
            parts.extend(pack.tags)
        parts.extend(drawing.quality_tags)
        raw = ", ".join(p for p in parts if p)
        kept, dropped = filter_fragment(raw, result["framing_level"])
        assembled = {"outfit_id": outfit_id, "positive": kept,
                     "zone_dropped": dropped}
    except Exception as e:
        assembled = {"error": f"assemble failed: {type(e).__name__}: {e}"}

    return {"intent": intent, **result, "assembled": assembled}


@app.post("/api/debug/drawing/multiround_render")
async def debug_multiround_render(payload: dict):
    import asyncio
    import random as _r
    import shutil
    intent = (payload.get("intent") or "").strip()
    if not intent:
        return {"error": "intent пуст"}
    s = _get_state()
    drawing = s["config"].drawing
    catalog = s.get("drawing_catalog")
    pipeline = s.get("drawing_pipeline")
    if catalog is None or pipeline is None:
        try:
            pipeline = _ensure_drawing_pipeline(s)
        except Exception as e:
            return {"error": f"pipeline: {type(e).__name__}: {e}"}

    from drawing import AssembledPrompt, BaseAppearance
    from drawing.tag_rounds import select_tags
    from drawing.zones import filter_fragment

    def llm_chat(system: str, user: str) -> str:
        return s["client"].chat(
            messages=[{"role": "user", "content": user}],
            system=system, thinking=False, label="Debug: tag round")

    loop = asyncio.get_event_loop()
    lifecycle = get_lifecycle()
    sc = s.get("drawing_style_catalog")
    pack = None
    if sc is not None:
        pack = sc.resolve(
            active_style_id=(payload.get("style_id") or drawing.active_style_id),
            character_override_id=None, renderer_id="sdxl")
    exclude = list(pack.exclude) if pack else None
    try:
        async with lifecycle.using():
            result = await loop.run_in_executor(
                None, lambda: select_tags(intent, llm_chat,
                                          max_rating=drawing.max_rating,
                                          exclude_domains=exclude))
    except Exception as e:
        return {"error": f"rounds: {type(e).__name__}: {e}"}

    store = s.get("store")
    cid = s["character_id"]
    base = BaseAppearance()
    archive = store.get_archive(cid) if store else None
    if archive and archive.has_entry("visual/appearance.yaml"):
        base = BaseAppearance.from_dict(archive.read_yaml("visual/appearance.yaml"))
    outfit_id = (payload.get("outfit_id")
                 or s.get("runtime_portrait_outfit_id") or "maid_classic")
    outfit = catalog.outfits.get(outfit_id)
    from drawing.tag_rounds import OUTFIT_REPLACING
    _drop_outfit = bool(set(result["tags"]) & OUTFIT_REPLACING)
    parts: list[str] = []
    if base.positive_for("sdxl"):
        parts.append(base.positive_for("sdxl"))
    neg_parts: list[str] = []
    if outfit and "sdxl" in outfit.renderer_prompts and not _drop_outfit:
        if outfit.renderer_prompts["sdxl"].positive:
            parts.append(outfit.renderer_prompts["sdxl"].positive)
        if outfit.renderer_prompts["sdxl"].negative:
            neg_parts.append(outfit.renderer_prompts["sdxl"].negative)
    if result["tags"]:
        parts.append(", ".join(result["tags"]))
    if pack is not None:
        parts.extend(pack.tags)
    parts.extend(drawing.quality_tags)
    positive, _ = filter_fragment(", ".join(p for p in parts if p),
                                  result["framing_level"])
    neg_parts.extend(drawing.negative_safety_tags)
    negative = ", ".join(neg_parts)

    seed = int(payload.get("seed")) if payload.get("seed") is not None \
        else _r.randint(0, 2 ** 63 - 1)
    ap = AssembledPrompt(positive=positive, negative=negative, seed=seed)

    def do_render():
        _llama_mgr.stop()
        _llama_mgr.wait_vram_released()
        try:
            return pipeline.adapter.render(ap)
        finally:
            _release_comfy()
            _llama_mgr.start()

    try:
        rr = await loop.run_in_executor(None, do_render)
    except Exception as e:
        return {"error": f"render: {type(e).__name__}: {e}",
                "tags": result["tags"], "positive": positive}

    out = (PROJECT_ROOT / "characters" / cid / "ondemand_test.png")
    try:
        shutil.copy2(rr.image_path, out)
    except Exception as e:
        out = rr.image_path
        print(f"[multiround_render] copy failed: {e}")
    return {"intent": intent, "framing": result["framing"],
            "style": pack.id if pack else None, "excluded_domains": exclude,
            "rounds": result["rounds"], "tags": result["tags"],
            "positive": positive, "negative": negative, "seed": seed,
            "image": str(out)}


@app.post("/api/debug/proactive")
async def debug_proactive(payload: dict | None = None):
    import asyncio
    from persona import scenarios as _scn
    s = _get_state()
    payload = payload or {}

    _orig_level = s["identity"].relationship_level
    _orig_rating = s["config"].drawing.max_rating
    if "relationship_level" in payload:
        try:
            s["identity"].relationship_level = max(0.0, min(1.0,
                                                   float(payload["relationship_level"])))
        except (TypeError, ValueError):
            return {"error": f"bad relationship_level {payload['relationship_level']!r}"}
    if payload.get("max_rating") in ("sfw", "suggestive", "nsfw"):
        s["config"].drawing.max_rating = payload["max_rating"]
    if payload.get("clear_history", True) and s.get("history") is not None:
        s["history"].clear()

    def _restore():
        s["config"].drawing.max_rating = _orig_rating
        if s["identity"].relationship_level != _orig_level:
            s["identity"].relationship_level = _orig_level
            try:
                s["identity"].save()
            except Exception:
                pass

    try:
        ctx = _build_scenario_context(s)
        catalog = _get_scenario_catalog(s)
        eligible_ids = [e.id for e in catalog
                        if e.surface == "proactive" and _scn.eligible(e, ctx)]
        info = {
            "tier": ctx.tier,
            "idle_gap_sec": round(ctx.idle_gap_sec, 1),
            "first_ever": ctx.first_ever,
            "config_max_rating": s["config"].drawing.max_rating,
            "eligible_proactive": eligible_ids,
            "history_len": len(s["history"].messages) if s.get("history") else None,
        }

        if payload.get("peek_only"):
            return {**info, "dispatched": False, "reason": "peek_only"}

        ws = s.get("active_ws")
        if ws is None:
            return {**info, "dispatched": False, "error": "нет active_ws — открой UI"}
        if s["history"].messages:
            return {**info, "dispatched": False,
                    "error": "история не пуста (clear_history=false?) — proactive не лезет"}

        forced = payload.get("scenario_id") or payload.get("scene_id")
        if forced == _DECISION_ID:
            delivered = await _dispatch_proactive_decision(
                s, ws, asyncio.get_event_loop())
            return {**info, "dispatched": bool(delivered),
                    "scenario_id": _DECISION_ID, "action": "decision",
                    "forced": True,
                    "session_initiated_by": s.get("session_initiated_by")}
        elif forced:
            ev = next((e for e in catalog if e.id == forced), None)
            if ev is None:
                return {**info, "dispatched": False,
                        "error": f"сцена {forced!r} не найдена в merged-каталоге"}
        else:
            ev = _scn.select(catalog, ctx, "proactive", roll=lambda: 0.0)
            if ev is None:
                ev = _select_decision_moment(ctx, peek_only=True)
            if ev is None:
                return {**info, "dispatched": False,
                        "error": "нет eligible proactive-кандидата (кулдауны "
                                 "decision-канала? scene_id=proactive_decision "
                                 "форсит решение)"}

        if getattr(ev, "action", "") == "decision":
            delivered = await _dispatch_proactive_decision(
                s, ws, asyncio.get_event_loop())
        else:
            delivered = await _dispatch_proactive_scenario(
                s, ws, asyncio.get_event_loop(), ev)
        return {**info, "dispatched": bool(delivered), "scenario_id": ev.id,
                "action": ev.action or "text", "forced": bool(forced),
                "session_initiated_by": s.get("session_initiated_by")}
    finally:
        _restore()


@app.get("/api/debug/drawing")
async def debug_drawing():
    s = _get_state()
    cat = s.get("drawing_catalog")
    pipeline = s.get("drawing_pipeline")

    info = {
        "state_keys_drawing": [k for k in s.keys() if "draw" in k.lower()],
        "config_present": "drawing" in s.get("config").__dict__ if s.get("config") else False,
        "config_drawing": None,
        "catalog": None,
        "pipeline_initialized": pipeline is not None,
        "boundaries_preview": None,
        "boundaries_error": None,
    }
    if s.get("config") and hasattr(s["config"], "drawing"):
        d = s["config"].drawing
        info["config_drawing"] = {
            "max_rating": d.max_rating,
            "renderer_id": d.renderer_id,
            "negative_safety_count": len(d.negative_safety_tags),
        }
    if cat is not None:
        info["catalog"] = {
            "outfits": len(cat.outfits),
            "scenes": len(cat.scenes),
            "poses": len(cat.poses),
            "modifiers": list(cat.modifiers.keys()),
            "errors": cat.errors,
            "renderer_ids": sorted(cat.available_renderer_ids()),
        }
    try:
        b = _get_drawing_boundaries(s)
        info["boundaries_preview"] = (b[:500] if b else None)
    except Exception as e:
        import traceback
        info["boundaries_error"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"

    return info


def _ensure_drawing_pipeline(state: dict):
    pipeline = state.get("drawing_pipeline")
    if pipeline is not None:
        return pipeline

    if not drawing_available(state):
        raise RuntimeError(
            "модуль генерации изображений не установлен или не запущен")

    from drawing import DrawingPipeline, SDXLAdapter

    config = state["config"]
    workflow_path = ASSETS_ROOT / config.image_gen.workflow_default
    if not workflow_path.exists():
        raise RuntimeError(f"workflow template не найден: {workflow_path}")
    workflow_template = json.loads(workflow_path.read_text(encoding="utf-8"))

    if _comfy_mgr is None or _comfy_mgr.client is None:
        raise RuntimeError("ComfyUI ещё не запущен")

    adapter = SDXLAdapter(
        comfy_client=_comfy_mgr.client,
        workflow_template=workflow_template,
        timeout_sec=config.image_gen.generation_timeout_sec,
        poll_interval_sec=config.image_gen.poll_interval_sec,
        hard_timeout_sec=getattr(config.image_gen, "generation_hard_timeout_sec", None),
    )

    from drawing import VisionCritic
    critic = None
    if config.drawing.vision_critic_enabled:
        critic = VisionCritic(llm_client=state["client"])

    pipeline = DrawingPipeline(
        catalog=state["drawing_catalog"],
        adapter=adapter,
        vision_critic=critic,
        ensure_backend=_comfy_mgr.ensure_started,
    )
    state["drawing_pipeline"] = pipeline
    print(f"[drawing] pipeline инициализирован "
          f"(adapter={adapter.renderer_id}, critic={'on' if critic else 'off'})")
    return pipeline


def _backend_name(state: dict) -> str:
    return getattr(getattr(state.get("client"), "backend", None), "name", "")


def _build_scenario_context(state: dict):
    import time as _t
    from persona import scenarios as _scn

    idy = state["identity"]
    now = _t.time()
    lt = _t.localtime(now)
    hr = lt.tm_hour
    tod = ("night" if (hr < 5 or hr >= 23) else "morning" if hr < 12
           else "day" if hr < 17 else "evening")
    last_evo = float(getattr(idy, "last_evolution", 0.0) or 0.0)
    gap = (now - last_evo) if last_evo > 0 else 0.0

    if not getattr(idy, "event_log", None):
        idy.event_log = {}

    from persona import proactive as _pro
    contact = max(last_evo, float(state.get("last_user_message_at") or 0.0),
                  _pro.last_sent_at(idy.event_log))
    contact_gap = (now - contact) if contact > 0 else 0.0

    today_md = f"{lt.tm_mon:02d}-{lt.tm_mday:02d}"
    anniversaries: dict[str, str] = {}
    fm_ts = float((idy.event_log.get("first_meeting") or {}).get("last_fired_at", 0.0) or 0.0)
    if fm_ts > 0:
        flt = _t.localtime(fm_ts)
        if flt.tm_year < lt.tm_year:
            anniversaries["first_met"] = f"{flt.tm_mon:02d}-{flt.tm_mday:02d}"

    axis_values: dict[str, float] = {}
    for stmt in (getattr(idy, "self_statements", None) or []):
        sid = getattr(stmt, "id", "") or ""
        if sid.startswith("axis_"):
            axis_values[sid[len("axis_"):]] = float(getattr(stmt, "axis_value", 0.5) or 0.5)

    eff_ms, eff_mi = mood_mod.effective_mood(
        getattr(idy, "mood_state", "") or "",
        float(getattr(idy, "mood_intensity", 0.0) or 0.0),
        float(getattr(idy, "mood_updated_at", 0.0) or 0.0), now)

    chance_scale = (
        _scn.chance_scale_from_initiative(axis_values.get("energy", 0.5))
        * mood_mod.mood_chance_factor(eff_ms, eff_mi))

    n_sessions = 0
    mem = state.get("memory")
    if mem is not None:
        try:
            from persona.relationship_axes import count_sessions as _count_sessions
            n_sessions = _count_sessions(getattr(mem, "records", []))
        except Exception:
            n_sessions = 0

    return _scn.ScenarioContext(
        tier=state["persona"].tier,
        relationship_level=float(getattr(idy, "relationship_level", 0.0) or 0.0),
        first_ever=not (getattr(idy, "last_session_summary", "") or ""),
        session_count=n_sessions + 1,
        idle_gap_sec=gap,
        contact_gap_sec=contact_gap,
        traits=frozenset(getattr(getattr(state.get("character"), "scenarios", None),
                                 "traits", None) or ()),
        rating=str(getattr(getattr(state.get("config"), "drawing", None),
                           "max_rating", "sfw") or "sfw"),
        quirks=frozenset(q.code for q in _quirks_carried(state)),
        time_of_day=tod,
        mood_state=eff_ms or "ровное",
        now=now,
        event_log=idy.event_log,
        today_md=today_md,
        anniversaries=anniversaries,
        axis_values=axis_values,
        chance_scale=chance_scale,
        pair=pair_of(state.get("character")),
        outfits=_scenario_outfit_map(state),
    )


def _get_scenario_catalog(state: dict):
    cid = state.get("character_id")
    catalog = state.get("scenario_catalog")
    if catalog is None or state.get("scenario_catalog_char") != cid:
        from persona import scenarios as _scn
        shared = _scn.load_catalog()
        ch = getattr(state.get("character"), "scenarios", None)
        if ch is not None and (ch.disable or ch.custom):
            catalog = _scn.merge_catalog(
                shared, disable=ch.disable,
                custom=_scn.parse_scenarios(ch.custom))
            print(f"[scenarios] {state.get('character_id','?')}: merged "
                  f"(disable={len(ch.disable)}, custom={len(ch.custom)}) "
                  f"→ {len(catalog)} сценариев")
        else:
            catalog = shared
        state["scenario_catalog"] = catalog
        state["scenario_catalog_char"] = cid
    return catalog


SCENARIOS_ENABLED = True


def _peek_entry_scenario(state: dict):
    if not SCENARIOS_ENABLED:
        return None
    from persona import scenarios as _scn
    ctx = _build_scenario_context(state)
    return _scn.select(_get_scenario_catalog(state), ctx, "entry")


def _stage_scenario_mark(state: dict, scene_id: str) -> None:
    import time as _t
    state.setdefault("pending_scenario_marks", []).append((scene_id, _t.time()))


_SCENARIO_ROLE_TAGS = {"casual": ("повседневный", "домашний")}


def _scenario_char_name(state: dict) -> str:
    return (getattr(state.get("character"), "name", "") or "").strip()


def _scenario_outfit_map(state: dict) -> dict:
    out: dict = {}
    default_id = state.get("character_default_outfit_id") or ""
    if default_id:
        out["default"] = default_id
    catalog = state.get("drawing_catalog")
    cfg = state.get("config")
    try:
        wardrobe = _get_wardrobe(state)
    except Exception:
        wardrobe = None
    if catalog is None or wardrobe is None or cfg is None or not drawing_available(state):
        return out
    from drawing.assets import tier_ge as _tier_ge
    tier = getattr(state.get("persona"), "tier", "distant")
    if not _tier_ge(tier, cfg.drawing.outfit_change_min_tier):
        return out
    character = state.get("character")
    policy = getattr(character, "outfit_policy", None)
    try:
        avail = catalog.compatible_outfits(
            renderer_id=cfg.drawing.renderer_id,
            max_rating=cfg.drawing.max_rating,
            current_tier=tier,
            character_id=state.get("character_id") or "",
            character_archetypes=list(getattr(state.get("persona"), "archetypes", []) or []),
            character_tag_gates=dict(policy.tag_tier_gates) if policy else None,
            character_blocked_tags=list(policy.blocked_tags) if policy else None,
            character_pair=pair_of(character),
        )
    except Exception as e:
        print(f"[scenario] outfit map: compatible_outfits failed: {e}")
        return out
    prepared = [o for o in avail if o.id != default_id and wardrobe.is_prepared(o.id)]
    for o in prepared:
        out[o.id] = o.id
    for role, tags in _SCENARIO_ROLE_TAGS.items():
        cands = sorted((o for o in prepared if set(o.tags) & set(tags)),
                       key=lambda o: o.id)
        if cands:
            out[role] = cands[0].id
    casual_id = state.get("character_casual_outfit_id") or ""
    if casual_id and casual_id in out:
        out["casual"] = casual_id
    return out


def _scenario_begin(state: dict, sc, *, turn: int, source: str) -> dict:
    import time as _t
    rec = {"obj": sc, "id": sc.id, "title": sc.display_title, "level": sc.level,
           "started_at": _t.time(), "turn": int(turn), "source": source,
           "end_requested": False}
    state["scenario"] = rec
    print(f"[scenario] {state.get('character_id','?')}: старт {sc.id!r} "
          f"({source}, уровень {sc.level})")
    return rec


def _scenario_history_marker(state: dict, sc, event: str, *,
                             before_last: bool = False) -> None:
    from persona import scenarios as _scn
    hist = state.get("history")
    if hist is None:
        return
    name = _scenario_char_name(state)
    hon = _effective_honorific(state)
    gen = gender_of(state.get("character"))
    if event == "start":
        if not sc.memory_start:
            return
        text = _scn.start_marker_text(sc, name=name, honorific=hon, gender=gen)
        body = _scn.fill(sc.memory_start, name=name, honorific=hon, gender=gen)
    else:
        if not sc.memory_end:
            return
        text = _scn.end_marker_text(sc, name=name, honorific=hon, gender=gen)
        body = _scn.fill(sc.memory_end, name=name, honorific=hon, gender=gen)
    hist.add("user", text, mood={"kind": "marker", "marker": _scn.MARKER,
                                  "event": event, "title": sc.display_title,
                                  "text": body})
    if before_last and len(hist.messages) >= 2:
        m = hist.messages.pop()
        hist.messages.insert(len(hist.messages) - 1, m)
        if len(hist.session_log) >= 2 and hist.session_log[-1] is m:
            hist.session_log.pop()
            hist.session_log.insert(len(hist.session_log) - 1, m)


def _scenario_close(state: dict, *, reason: str) -> dict | None:
    rec = state.get("scenario")
    if not rec:
        return None
    state["scenario"] = None
    state.pop("pending_scenario_marker", None)
    try:
        _scenario_history_marker(state, rec["obj"], "end")
    except Exception as e:
        print(f"[scenario] end marker failed: {e}")
    print(f"[scenario] {state.get('character_id','?')}: {rec['id']!r} завершён "
          f"({reason}, ходов {rec.get('turn', 0)})")
    return rec


def _scenario_block(state: dict, *, advance: bool) -> str | None:
    import time as _t
    rec = state.get("scenario")
    if not rec:
        return None
    from persona import scenarios as _scn
    sc = rec["obj"]
    if advance:
        nxt = int(rec.get("turn", 0)) + 1
        if sc.is_over(nxt, _t.time() - float(rec.get("started_at", 0.0))):
            _scenario_close(state, reason="limit")
            return None
        rec["turn"] = nxt
    turn = max(1, int(rec.get("turn", 1)))
    text = _scn.render_block(sc, turn, backend=_backend_name(state),
                             honorific=_effective_honorific(state),
                             name=_scenario_char_name(state),
                             gender=gender_of(state.get("character")))
    return text or None


def _scenario_model_may_end(state: dict) -> bool:
    rec = state.get("scenario")
    return bool(rec and rec["obj"].model_may_end and int(rec.get("turn", 0)) >= 2)


def _quirk_code_string(state: dict) -> str:
    if "quirk_code" in state:
        return state["quirk_code"]
    code = ""
    try:
        from services import nsfw_anatomy as na
        store, persona = state.get("store"), state.get("persona")
        archive = store.get_archive(persona.character_id) if (store and persona) else None
        from services import nsfw_extra as _nx
        code = _nx.read_code(archive)
    except Exception as e:
        print(f"[quirks] код не прочитан: {type(e).__name__}: {e}")
    state["quirk_code"] = code
    return code


def _quirks_carried(state: dict) -> list:
    try:
        if getattr(state["config"].drawing, "max_rating", "sfw") == "sfw":
            return []
        from services import nsfw_quirks as nq
        return nq.carried(PROJECT_ROOT, code_string=_quirk_code_string(state),
                          identity=state["persona"].identity)
    except Exception as e:
        print(f"[quirks] skip: {type(e).__name__}: {e}")
        return []


def _quirks_block(state: dict) -> "str | None":
    from persona.gender import gender_of
    from services import nsfw_quirks as nq
    return nq.render_block(_quirks_carried(state),
                           gender=gender_of(state.get("character"))) or None


def _quirks_mood_cues(state: dict) -> dict:
    from persona.gender import gender_of
    from services import nsfw_quirks as nq
    return nq.mood_cues_of(_quirks_carried(state),
                           gender=gender_of(state.get("character")))


def _quirks_raise(state: dict, event: str) -> None:
    try:
        from services import nsfw_quirks as nq
        ae = nq.aftereffect_for(_quirks_carried(state), event)
        if ae is not None:
            _aftereffect_begin(state, ae, source=f"причуда/{event}")
    except Exception as e:
        print(f"[quirks] raise {event}: {type(e).__name__}: {e}")



def _aftereffect_begin(state: dict, ae, *, source: str = "") -> dict:
    import time as _t
    cur = state.get("aftereffect")
    if cur and cur.get("id") == ae.id:
        return cur
    rec = {"obj": ae, "id": ae.id, "started_at": _t.time(), "turn": 0,
           "source": source or ae.source}
    state["aftereffect"] = rec
    print(f"[aftereffect] {state.get('character_id','?')}: старт {ae.id!r} "
          f"({rec['source'] or 'без источника'})")
    return rec


def _aftereffect_close(state: dict, *, reason: str) -> None:
    rec = state.get("aftereffect")
    if not rec:
        return
    state["aftereffect"] = None
    print(f"[aftereffect] {state.get('character_id','?')}: конец "
          f"{rec.get('id')!r} ({reason})")


def _aftereffect_block(state: dict, *, advance: bool) -> "str | None":
    import time as _t
    rec = state.get("aftereffect")
    if not rec:
        return None
    from persona import aftereffects as _ae
    obj = rec["obj"]
    if advance:
        nxt = int(rec.get("turn", 0)) + 1
        if obj.is_over(nxt, _t.time() - float(rec.get("started_at", 0.0))):
            _aftereffect_close(state, reason="limit")
            return None
        rec["turn"] = nxt
    return _ae.render(obj) or None


def _aftereffect_mood_floor(state: dict) -> str:
    rec = state.get("aftereffect")
    return str(rec["obj"].mood_floor) if rec else ""


def _aftereffect_appraisal_note(state: dict) -> str:
    rec = state.get("aftereffect")
    if not rec:
        return ""
    text = (rec["obj"].text or "").strip()
    return f"Её состояние сейчас: {text}" if text else ""


def _scenario_appraisal_note(state: dict) -> str:
    rec = state.get("scenario")
    if not rec:
        return ""
    from persona import scenarios as _scn
    sc = rec["obj"]
    if sc.level == "background":
        return ""
    backend = _backend_name(state)
    turn = max(1, int(rec.get("turn", 1)))
    body = sc.presence_for(turn, backend) or sc.note_for(backend)
    body = _scn.fill(body, name=_scenario_char_name(state),
                     honorific=_effective_honorific(state),
                     gender=gender_of(state.get("character")))
    if not body:
        return ""
    if sc.level == "event":
        return f"Сейчас происходит (сценарий «{sc.display_title}»): {body}"
    return f"Обстоятельства разговора (для понимания смысла): {body}"


async def _scenario_apply_outfit(state: dict, ws, loop, sc, *,
                                 reveal_now: bool) -> str | None:
    if not sc.outfit:
        return None
    oid = _scenario_outfit_map(state).get(sc.outfit)
    if not oid:
        print(f"[scenario] {sc.id!r}: костюм {sc.outfit!r} недоступен — без переодевания")
        return None
    if state.get("runtime_portrait_outfit_id") == oid:
        return oid
    try:
        await _handle_change_outfit_action(state, ws, loop, {"outfit_id": oid})
    except Exception as e:
        print(f"[scenario] {sc.id!r}: переодевание в {oid!r} не удалось: {e}")
        return None
    if state.get("runtime_portrait_outfit_id") != oid:
        return None
    if reveal_now:
        await _send_pending_portrait_reveal(state, ws)
    return oid


async def _scenario_notify(state: dict, ws, sc, text: str | None = None) -> None:
    if ws is None or not _CHAT_TRACE:
        return
    try:
        await ws.send_json({"type": "system",
                            "text": text or f"🎬 Сценарий: «{sc.display_title}»"})
    except Exception:
        pass


def _flush_scenario_marker(state: dict) -> None:
    sc = state.pop("pending_scenario_marker", None)
    if sc is not None:
        _scenario_history_marker(state, sc, "start")


async def _scenario_after_turn(state: dict, ws) -> None:
    rec = state.get("scenario")
    if rec and rec.get("end_requested"):
        _scenario_close(state, reason="model")
        await _scenario_notify(state, ws, rec["obj"],
                               f"🎬 Сценарий «{rec['title']}» завершён — по решению персонажа.")


_DECISION_ID = "proactive_decision"
_DECISION_SKIP_ID = "proactive_decision_skip"
PROACTIVE_SCENARIO_SHARE = 0.5


def _bump_proactive_ignore(state: dict) -> None:
    from persona import proactive as _pro
    idy = state.get("identity")
    if idy is None:
        return
    if not getattr(idy, "event_log", None):
        idy.event_log = {}
    n = _pro.ignore_streak(idy.event_log) + 1
    idy.event_log[_pro.IGNORE_KEY] = {"streak": n, "at": time.time()}
    try:
        idy.save()
    except Exception:
        pass
    print(f"[proactive] весточка без ответа — стрик игнора: {n}")


def _reset_proactive_ignore(state: dict) -> None:
    from persona import proactive as _pro
    idy = state.get("identity")
    log = getattr(idy, "event_log", None) if idy is not None else None
    if not log or _pro.ignore_streak(log) <= 0:
        return
    log[_pro.IGNORE_KEY] = {"streak": 0, "at": time.time()}
    try:
        idy.save()
    except Exception:
        pass
    print("[proactive] Господин ответил на весточку — стрик игнора сброшен")


def _notification_text(state: dict) -> str:
    name = _scenario_char_name(state)
    verb = gpick(gender_of(state.get("character")), "написала", "написал")
    return f"{name} {verb} вам" if name else f"{verb.capitalize()} вам"


def _notification_icon(state: dict) -> str | None:
    cid = state.get("character_id")
    if not cid:
        return None
    cdir = PROJECT_ROOT / "characters" / cid
    for base in (_avatar_basename(state), "avatar_chat"):
        p = cdir / f"{base}.png"
        if p.exists():
            return str(p)
    return None


async def _notify_message(state: dict, ws) -> None:
    if ws is None:
        return
    payload = {"type": "notification", "kind": "message",
               "title": "", "body": _notification_text(state)}
    icon = _notification_icon(state)
    if icon:
        payload["icon"] = icon
    try:
        await ws.send_json(payload)
    except Exception as e:
        print(f"[notify] ws send fail: {type(e).__name__}: {e}")


def _contact_gap(ctx) -> float:
    return ctx.contact_gap_sec if ctx.contact_gap_sec is not None else ctx.idle_gap_sec


def _select_decision_moment(ctx, *, peek_only: bool = False):
    from persona.scenarios import Scenario
    from persona import proactive as _pro
    log = ctx.event_log or {}
    skipped = float((log.get(_DECISION_SKIP_ID) or {}).get("last_fired_at", 0.0) or 0.0)
    if (ctx.now - skipped) < _pro.SKIP_COOLDOWN_SEC:
        return None
    p = _pro.decision_chance(ctx.tier, _contact_gap(ctx),
                             sent=_pro.sent_today(log, ctx.now),
                             streak=_pro.ignore_streak(log),
                             scale=float(ctx.chance_scale or 1.0))
    if p <= 0.0:
        return None
    if not peek_only:
        import random
        if random.random() >= p:
            return None
    return Scenario(id=_DECISION_ID, surface="proactive", action="decision")


def _reflection_pending_for(state: dict) -> bool:
    cid = state.get("character_id")
    if not cid or _reflection_queue is None:
        return False
    try:
        return _reflection_queue.has_for(cid)
    except Exception:
        return False


def _select_proactive_scenario(state: dict, *, peek_only: bool = False):
    if not SCENARIOS_ENABLED:
        return None
    try:
        if not state["config"].session.proactive_enabled:
            return None
    except Exception:
        pass
    import random as _rnd
    from persona import scenarios as _scn
    ctx = _build_scenario_context(state)
    ev = _select_plan_event_proactive(state, ctx)
    if ev is not None:
        return ev
    moment = _select_decision_moment(ctx, peek_only=peek_only)
    if moment is None or peek_only:
        return moment
    if _rnd.random() < PROACTIVE_SCENARIO_SHARE:
        sc = _scn.pick_proactive(_get_scenario_catalog(state), ctx)
        if sc is not None:
            return sc
    return moment


def _select_plan_event_proactive(state: dict, ctx):
    import datetime as _dt
    from persona.scenarios import Scenario
    from persona import proactive as _pro
    from tools.planning import plan_events_for_day
    if _contact_gap(ctx) < _pro.CONTACT_FLOOR_SEC:
        return None
    mem = state.get("memory")
    recs = getattr(mem, "records", []) or []
    if not recs:
        return None
    today = _dt.date.fromtimestamp(ctx.now)
    pools = [(plan_events_for_day(recs, today), "today")]
    if ctx.time_of_day in ("evening", "night"):
        pools.append((plan_events_for_day(recs, today + _dt.timedelta(days=1)),
                      "tomorrow"))
    for pool, when in pools:
        for r in pool:
            d = r.details or {}
            raised = float(d.get("proactive_raised_at", 0.0) or 0.0)
            if raised and _dt.date.fromtimestamp(raised) == today:
                continue
            return Scenario(id="proactive_plan_event", surface="proactive",
                         action="decision",
                         params={"hook": {"kind": "plan",
                                          "record_id": r.record_id,
                                          "when": when}})
    return None


async def _maybe_initiate(state: dict, ws: WebSocket) -> None:
    import time as _t
    from persona import scenarios as _scn

    if state["history"].messages:
        return
    if state.get("identity") is None:
        return
    if state.get("_initiate_inflight"):
        return
    ev = _peek_entry_scenario(state)
    if not (ev and ev.initiate):
        return
    state["_initiate_inflight"] = True
    cid = state.get("character_id")

    lifecycle = get_lifecycle()
    loop = asyncio.get_event_loop()
    if ev.outfit:
        await _scenario_apply_outfit(state, ws, loop, ev, reveal_now=True)

    def _gen() -> str:
        from persona.prompt_builder import build_system_prompt
        from persona.prompt_context import ContextSpec
        from llm.llama_client import strip_tool_calls
        sysp = build_system_prompt(
            state["persona"], memory=state["memory"],
            spec=ContextSpec.full_chat(is_new_session=False),
            scenario_note=_scn.render_block(
                ev, 1, backend=_backend_name(state),
                honorific=_effective_honorific(state),
                name=_scenario_char_name(state), opening=True,
                gender=gender_of(state.get("character"))) or None,
            current_outfit_label=_get_current_outfit_label(state),
        )
        trigger = ("(Собеседник только что открыл чат и впервые видит тебя. Начни "
                   "разговор САМА — поздоровайся и представься первой, как описано "
                   "в блоке <сценарий>.)")
        resp = state["client"].chat(
            messages=[{"role": "user", "content": trigger}],
            system=sysp, thinking=False, label="Сценарий: знакомство")
        return strip_tool_calls(resp or "").strip()

    try:
        try:
            async with lifecycle.using():
                opening = await loop.run_in_executor(None, _gen)
        except Exception as e:
            print(f"[event] initiate {ev.id!r} fail: {type(e).__name__}: {e}")
            return
        opening = mood_mod.strip_mood_tag(opening).strip()
        if not opening:
            return
        if state["history"].messages or state.get("character_id") != cid:
            return

        target_ws = state.get("active_ws") or ws
        try:
            await target_ws.send_json({"type": "response", "text": opening,
                                       "id_mood": _reply_mood_id(state)})
            await _send_reply_stats(state, target_ws, state["client"].last_stats)
            await target_ws.send_json({"type": "done"})
        except Exception as _se:
            print(f"[event] {state.get('character_id','?')}: initiate {ev.id!r} "
                  f"НЕ доставлен (ws: {type(_se).__name__}) — откат, сцена не сожжена")
            return
        if state.get("character_id") != cid:
            return
        _stage_scenario_mark(state, ev.id)
        if state["history"].messages:
            _op = {"role": "assistant", "content": opening}
            _m = _mood_meta(state)
            if _m:
                _op["mood"] = _m
            state["history"].messages.insert(0, _op)
        else:
            _scenario_history_marker(state, ev, "start")
            _hist_add_assistant(state, opening)
        _scenario_begin(state, ev, turn=1, source="entry")
        await _scenario_notify(state, target_ws, ev)
        print(f"[event] {state.get('character_id','?')}: initiate {ev.id!r} → отправлено")
    finally:
        state["_initiate_inflight"] = False


def _resolve_selfie_intent(state: dict, ev) -> tuple[str, bool]:
    from drawing.assets import RATING_ORDER as _RO, tier_ge as _tier_ge
    p = ev.params or {}
    want_nsfw = str(p.get("rating", "sfw")).lower() == "nsfw"
    cfg_nsfw = _RO.get(state["config"].drawing.max_rating, 0) >= _RO["nsfw"]
    tier_ok = _tier_ge(getattr(state["persona"], "tier", "distant"), "intimate")
    eff_nsfw = want_nsfw and cfg_nsfw and tier_ok
    intent = (p.get("intent_nsfw") if eff_nsfw else p.get("intent_sfw")) or ""
    return " ".join(str(intent).split()), eff_nsfw


async def _dispatch_proactive_scenario(state: dict, ws, loop, ev, *,
                                       force: bool = False) -> bool:
    import time as _t
    from persona import scenarios as _scn
    from persona.prompt_builder import build_system_prompt
    from llm.llama_client import strip_tool_calls

    if ws is None or (state["history"].messages and not force):
        return False

    lifecycle = get_lifecycle()
    honorific = _effective_honorific(state)
    name = _scenario_char_name(state)
    _cg = gender_of(state.get("character"))
    target_oid = _scenario_outfit_map(state).get(ev.outfit) if ev.outfit else None
    block = _scn.render_block(ev, 1, backend=_backend_name(state), honorific=honorific,
                              name=name, opening=True, gender=_cg)

    def _gen() -> str:
        sysp = build_system_prompt(
            state["persona"], memory=state["memory"],
            spec=ContextSpec.proactive(),
            scenario_note=block or None,
            current_outfit_label=_get_current_outfit_label(state, target_oid),
        )
        trigger = (
            f"(Сейчас его нет рядом, а ты по своей инициативе пишешь ему "
            f"{gpick(_cg, 'первой', 'первым')} — без его сообщения. Обстоятельства — "
            f"в блоке <сценарий>: начни разговор {gpick(_cg, 'сама', 'сам')}, как "
            f"{gpick(_cg, 'начала', 'начал')} бы в этой ситуации. Если по твоему "
            f"характеру и настроению сейчас писать не хочется — ответь ровно одним "
            f"словом: SKIP (служебный маркер, {honorific} его не увидит).)")
        resp = state["client"].chat(
            messages=[{"role": "user", "content": trigger}],
            system=sysp, thinking=False, label=f"Proactive: {ev.id}")
        return strip_tool_calls(resp or "").strip()

    try:
        async with lifecycle.using():
            opening = await loop.run_in_executor(None, _gen)
    except Exception as e:
        print(f"[proactive] {ev.id!r} gen fail: {type(e).__name__}: {e}")
        return False
    opening = mood_mod.strip_mood_tag(opening).strip()

    idy = state["identity"]
    if not getattr(idy, "event_log", None):
        idy.event_log = {}
    if not opening or len(opening) < 3 or _is_skip_reply(opening):
        _scn.mark_fired(idy.event_log, _DECISION_SKIP_ID, _t.time())
        try:
            idy.save()
        except Exception:
            pass
        print(f"[proactive] {ev.id!r}: SKIP/пусто — сценарий не стартовал")
        return False

    if state["history"].messages and not force:
        return False
    if target_oid:
        await _scenario_apply_outfit(state, ws, loop, ev, reveal_now=True)
    try:
        await ws.send_json({"type": "response", "text": opening,
                            "id_mood": _reply_mood_id(state)})
    except Exception as e:
        print(f"[proactive] {ev.id!r}: ws send fail: {e} — отменяю")
        return False
    _hist_add_assistant(state, opening)
    _scenario_history_marker(state, ev, "start", before_last=True)
    await _send_reply_stats(state, ws, state["client"].last_stats)
    await _notify_message(state, ws)
    _scenario_begin(state, ev, turn=1, source="debug" if force else "proactive")
    await _scenario_notify(state, ws, ev)

    if state.get("session_initiated_by") is None and not force:
        state["session_initiated_by"] = "proactive"
        state["proactive_session_started_at"] = _t.time()
        print(f"[proactive] сессия → proactive "
              f"(start={state['proactive_session_started_at']:.0f})")

    _scn.mark_fired(idy.event_log, ev.id, _t.time())
    if not force:
        from persona import proactive as _pro
        _pro.record_sent(idy.event_log, _t.time())
    try:
        idy.save()
    except Exception:
        pass
    print(f"[proactive] {state.get('character_id','?')}: {ev.id!r} → доставлено")

    if ev.action == "send_selfie":
        intent, eff_nsfw = _resolve_selfie_intent(state, ev)
        if not intent:
            print(f"[proactive] {ev.id!r}: нет intent для селфи — только текст")
        else:
            state["memory"].pending_actions.append({
                "kind": "image", "intent": intent, "nsfw": eff_nsfw,
                "proactive": True,
            })
            try:
                await _process_pending_actions(state, ws, loop)
            except Exception as e:
                print(f"[proactive] selfie render fail: {type(e).__name__}: {e}")

    try:
        await ws.send_json({"type": "done"})
    except Exception:
        pass
    return True


def _is_skip_reply(text: str) -> bool:
    import re as _re
    return bool(_re.fullmatch(
        r"""[\s.,!…«»"'`\-—~()\[\]]*skip[\s.,!…«»"'`\-—~()\[\]]*""",
        (text or "").strip(), _re.IGNORECASE))


async def _timer_watcher() -> None:
    while True:
        try:
            await asyncio.sleep(2)
        except asyncio.CancelledError:
            return
        try:
            s = _state
            if not s or s.get("memory") is None or s.get("character") is None:
                continue
            now = time.time()
            for r in list(getattr(s["memory"], "records", [])):
                if getattr(r, "type", "") != "напоминание":
                    continue
                d = r.details or {}
                if d.get("kind") != "timer":
                    continue
                if d.get("expired") or d.get("delivered"):
                    continue
                fire_at = float(d.get("fire_at") or 0.0)
                if fire_at <= 0 or fire_at > now:
                    continue
                d["delivered"] = True
                d["expired"] = True
                d["expired_at"] = now
                try:
                    _save_memory()
                except Exception:
                    pass
                late = (now - fire_at) > 180
                label = d.get("description") or "таймер"
                dur = d.get("duration_min")
                dur_h = (f"{int(dur)} мин" if isinstance(dur, (int, float))
                         and dur == int(dur) else f"{dur:g} мин"
                         if isinstance(dur, (int, float)) else "")
                if late:
                    trigger = (f"(Служебное: твой таймер «{label}»"
                               f"{f' на {dur_h}' if dur_h else ''} сработал ещё "
                               f"{int((now - fire_at) // 60)} мин назад — тебя/его не "
                               f"было рядом. Скажи об этом коротко и по делу, в "
                               f"своём тоне, в контексте разговора, если он идёт.)")
                else:
                    trigger = (f"(Служебное: только что сработал твой таймер "
                               f"«{label}»{f' на {dur_h}' if dur_h else ''}. "
                               f"Панельку он уже видит. Прокомментируй коротко в "
                               f"контексте текущего разговора — одна-две фразы, "
                               f"по делу и в своём тоне.)")
                card_title = f"Таймер: {label}" + (f" ({dur_h})" if dur_h else "")
                if late:
                    card_title += f" — сработал {int((now - fire_at) // 60)} мин назад"
                ev = {
                    "kind": "timer",
                    "trigger": trigger,
                    "late": late,
                    "card": {"type": "reminder_card", "record_id": r.record_id,
                             "kind": "one_shot", "title": card_title},
                }
                await _interject_event(s, s.get("active_ws"), ev)
        except Exception as e:
            print(f"[timer] watcher tick error: {type(e).__name__}: {e}")


async def _interject_event(state: dict, ws, ev: dict) -> None:
    await _interject_once(state, ws, ev)
    await _drain_interjections(state, ws)


async def _interject_once(state: dict, ws, ev: dict) -> None:
    if ws is None:
        state.setdefault("pending_interjections", []).append(ev)
        return
    if state.get("turn_busy") or state.get("_interject_inflight"):
        state.setdefault("pending_interjections", []).append(ev)
        return

    state["_interject_inflight"] = True
    try:
        loop = asyncio.get_event_loop()
        card = ev.get("card")
        for payload in (card if isinstance(card, list) else ([card] if card else [])):
            try:
                await ws.send_json(payload)
            except Exception as e:
                print(f"[interject] card send fail: {e}")

        trigger = ev.get("trigger") or ""
        if not trigger:
            return
        history = state.get("history")
        msgs = (history.get_messages() if history is not None else []) + [
            {"role": "user", "content": trigger}]

        def _gen() -> str:
            sysp = build_system_prompt(
                state["persona"], memory=state["memory"],
                spec=ContextSpec.interjection(),
                current_outfit_label=_get_current_outfit_label(state),
            )
            return state["client"].chat(
                messages=msgs, system=sysp, thinking=False,
                label=f"Interjection [{ev.get('kind')}]")

        lifecycle = get_lifecycle()
        try:
            async with lifecycle.using():
                raw = await loop.run_in_executor(None, _gen)
        except Exception as e:
            print(f"[interject] gen fail: {type(e).__name__}: {e}")
            return
        reply = strip_tool_calls(raw or "").strip()
        reply = mood_mod.strip_mood_tag(reply).strip()
        if not reply:
            return
        try:
            await ws.send_json({"type": "response", "text": reply,
                                "id_mood": _reply_mood_id(state)})
        except Exception as e:
            print(f"[interject] ws send fail: {e}")
            return
        if history is not None:
            marker = ev.get("history_marker")
            if marker:
                history.add("user", marker, mood={"kind": "marker"})
            history.add("assistant", reply, mood=_mood_meta(state))
        await _send_reply_stats(state, ws, state["client"].last_stats)
        try:
            await ws.send_json({"type": "done"})
        except Exception:
            pass
        print(f"[interject] {ev.get('kind')}: доставлено"
              f"{' (с опозданием)' if ev.get('late') else ''}")
    finally:
        state["_interject_inflight"] = False


async def _turn_idle(state: dict, ws) -> None:
    state["turn_busy"] = False
    await _drain_interjections(state, ws)


async def _drain_interjections(state: dict, ws) -> None:
    while True:
        q = state.get("pending_interjections")
        if (not q or ws is None or state.get("turn_busy")
                or state.get("_interject_inflight")):
            return
        ev = q.pop(0)
        try:
            await _interject_once(state, ws, ev)
        except Exception as e:
            print(f"[interject] drain fail: {type(e).__name__}: {e}")


async def _maybe_morning_brief(state: dict, ws) -> None:
    from services import assistant_brief as _ab
    import time as _t

    if not _ab.ENABLED or ws is None or state.get("_brief_inflight"):
        return
    if not _ab.should_brief(state):
        return
    if _reflection_pending_for(state):
        return

    state["_brief_inflight"] = True
    try:
        loop = asyncio.get_event_loop()
        now = _t.time()
        cid = state.get("character_id")

        lines = _ab.collect_brief_lines(state, now)
        weather = await loop.run_in_executor(None, _ab.fetch_weather_line, state)
        if weather:
            lines.append(f"погода: {weather}")

        honorific = _effective_honorific(state)
        lt = _t.localtime(now)
        tod = ("ночь" if (lt.tm_hour < 5 or lt.tm_hour >= 23) else
               "утро" if lt.tm_hour < 12 else "день" if lt.tm_hour < 17 else "вечер")
        if lines:
            data_block = ("Данные на сегодня из твоих записей:\n"
                          + "\n".join(f"- {l}" for l in lines))
        else:
            data_block = ("В твоих записях на сегодня ПУСТО — ни планов, ни "
                          "напоминаний. Тогда сводка не нужна: просто коротко "
                          "и тепло пожелай ему хорошего дня, в своём характере.")
        trigger = (
            f"(Служебная ситуация — {honorific} этого текста не видит. Сейчас "
            f"{tod}; он только что появился после долгого перерыва, а ты "
            f"подписана встречать его короткой сводкой дня.\n{data_block}\n"
            f"Поздоровайся по фактическому времени суток. НЕ утверждай, что он "
            f"«только проснулся» — ты не знаешь, когда он встал. Подай всё "
            f"СВОИМИ словами, коротко и в своём тоне, не списком-докладом. "
            f"ВАЖНО: реплика НЕ требует ответа — закончи пожеланием или точкой, "
            f"БЕЗ вопроса и без «расскажи/напиши мне». Не начинай со своего имени.)"
        )

        def _gen() -> str:
            sysp = build_system_prompt(
                state["persona"], memory=state["memory"],
                spec=ContextSpec.morning_brief(),
            )
            return state["client"].chat(
                messages=[{"role": "user", "content": trigger}],
                system=sysp, thinking=False, label="Утренняя сводка")

        lifecycle = get_lifecycle()
        try:
            async with lifecycle.using():
                raw = await loop.run_in_executor(None, _gen)
        except Exception as e:
            print(f"[brief] gen fail: {type(e).__name__}: {e}")
            return

        reply = strip_tool_calls(raw or "").strip()
        reply = mood_mod.strip_mood_tag(reply).strip()
        if not reply:
            return
        if state["history"].messages or state.get("character_id") != cid:
            return
        try:
            await ws.send_json({"type": "response", "text": reply,
                                "id_mood": _reply_mood_id(state)})
        except Exception as e:
            print(f"[brief] ws send fail: {e}")
            return
        _hist_add_assistant(state, reply)
        await _send_reply_stats(state, ws, state["client"].last_stats)
        await _notify_message(state, ws)
        if state.get("session_initiated_by") is None:
            state["session_initiated_by"] = "proactive"
            state["proactive_session_started_at"] = now
        _ab.mark_briefed(state["identity"], now)
        print(f"[brief] {state.get('character_id','?')}: сводка доставлена "
              f"({len(lines)} пункт(ов))")
        try:
            await ws.send_json({"type": "done"})
        except Exception:
            pass
    finally:
        state["_brief_inflight"] = False


async def _dispatch_proactive_decision(state: dict, ws, loop,
                                       hook: dict | None = None) -> bool:
    import time as _t
    from persona import scenarios as _scn
    from persona.prompt_builder import build_system_prompt
    from llm.llama_client import strip_tool_calls
    from memory.loops import select_loop_for_checkin, mark_loop_raised

    if ws is None or state["history"].messages:
        return False

    mem = state["memory"]
    idy = state["identity"]
    honorific = _effective_honorific(state)
    now = _t.time()

    last_evo = float(getattr(idy, "last_evolution", 0.0) or 0.0)
    gap_h = int(max(0.0, (now - last_evo) if last_evo > 0 else 0.0) // 3600)
    lt = _t.localtime(now)
    tod = ("ночь" if (lt.tm_hour < 5 or lt.tm_hour >= 23) else
           "утро" if lt.tm_hour < 12 else "день" if lt.tm_hour < 17 else "вечер")
    gap_line = (f"с вашей прошлой встречи прошло около {gap_h} ч."
                if gap_h > 0 else "прошлая встреча была недавно.")

    from persona import proactive as _pro
    log = getattr(idy, "event_log", None) or {}
    streak = _pro.ignore_streak(log)

    loop_rec = None
    if hook is None:
        candidates: dict[str, dict] = {}
        try:
            loop_rec = select_loop_for_checkin(getattr(mem, "records", []), now)
        except Exception:
            loop_rec = None
        if loop_rec is not None:
            raised = int(((loop_rec.details or {}).get("raised_count", 0)) or 0)
            candidates["loop"] = {"title": loop_rec.title, "raised": bool(raised)}
        try:
            from persona.prompt_builder import _find_recent_consolidation_diary
            diary = _find_recent_consolidation_diary(mem)
        except Exception:
            diary = None
        if diary:
            candidates["thought"] = {"text": str(diary)}
        try:
            interests = [t.text for t in (idy.get_active_thoughts() or [])
                         if getattr(t, "kind", "") == "interest" and t.text]
        except Exception:
            interests = []
        if interests:
            import random as _rnd
            candidates["discovery"] = {"interest": _rnd.choice(interests)}
        candidates["plain"] = {}
        try:
            from drawing.assets import tier_ge as _tier_ge
            if drawing_available(state) and _tier_ge(state["persona"].tier, "warming"):
                candidates["photo"] = {}
        except Exception:
            pass
        last_kind = str((log.get(_pro.HOOK_KEY) or {}).get("kind", "") or "")
        kind = _pro.choose_hook(list(candidates), last_kind)
        hook = {"kind": kind, "data": candidates.get(kind) or {}}
    hook_kind = str(hook.get("kind") or "plain")
    hook_data = dict(hook.get("data") or {})

    plan_rec = None
    if hook_kind == "plan" and hook.get("record_id"):
        plan_rec = next((r for r in getattr(mem, "records", [])
                         if getattr(r, "record_id", None) == hook.get("record_id")),
                        None)
        if plan_rec is not None:
            d = plan_rec.details or {}
            hook_data = {"title": plan_rec.title,
                         "description": d.get("description", ""),
                         "where": d.get("where", ""),
                         "when": hook.get("when", "today"),
                         "evening": tod in ("вечер", "ночь")}
        else:
            hook_kind, hook_data = "plain", {}

    trigger = _pro.build_trigger(honorific=honorific, tod=tod, gap_line=gap_line,
                                 hook_kind=hook_kind, hook_data=hook_data,
                                 streak=streak)

    tools = mem.get_tools(query="")
    if not drawing_available(state):
        tools = [t for t in tools if t.get("function", {}).get("name")
                 not in ("draw", "change_outfit")]

    def _gen() -> str:
        sysp = build_system_prompt(
            state["persona"], memory=mem,
            spec=ContextSpec.proactive_decision(),
            current_outfit_label=_get_current_outfit_label(state),
            drawing_boundaries=_get_drawing_boundaries(state),
        )
        toks = []
        for token in state["client"].chat_with_tools(
            messages=[{"role": "user", "content": trigger}],
            system=sysp,
            tools=tools,
            tool_handler=mem.handle_tool_call,
            char_name=state["character"].name,
        ):
            toks.append(token)
        return "".join(toks)

    lifecycle = get_lifecycle()
    try:
        async with lifecycle.using():
            raw = await loop.run_in_executor(None, _gen)
    except Exception as e:
        print(f"[proactive-decision] gen fail: {type(e).__name__}: {e}")
        return False

    reply = strip_tool_calls(raw or "").strip()
    reply = mood_mod.strip_mood_tag(reply).strip()

    if not getattr(idy, "event_log", None):
        idy.event_log = {}

    if not reply or _is_skip_reply(reply):
        _scn.mark_fired(idy.event_log, _DECISION_SKIP_ID, now)
        try:
            idy.save()
        except Exception:
            pass
        mem.pending_actions.clear()
        if plan_rec is not None:
            plan_rec.details["proactive_raised_at"] = now
            try:
                _save_memory()
            except Exception:
                pass
        print(f"[proactive-decision] {state.get('character_id','?')}: "
              f"SKIP (крючок {hook_kind})")
        return False

    if state["history"].messages:
        return False
    try:
        await ws.send_json({"type": "response", "text": reply,
                                "id_mood": _reply_mood_id(state)})
    except Exception as e:
        print(f"[proactive-decision] ws send fail: {e}")
        return False
    _hist_add_assistant(state, reply)
    await _send_reply_stats(state, ws, state["client"].last_stats)
    await _notify_message(state, ws)

    if state.get("session_initiated_by") is None:
        state["session_initiated_by"] = "proactive"
        state["proactive_session_started_at"] = now
        print(f"[proactive] сессия → proactive (decision)")
    _scn.mark_fired(idy.event_log, _DECISION_ID, now)
    _pro.record_sent(idy.event_log, now)
    idy.event_log[_pro.HOOK_KEY] = {"kind": hook_kind, "at": now}
    try:
        idy.save()
    except Exception:
        pass
    if hook_kind == "loop" and loop_rec is not None:
        mark_loop_raised(loop_rec, now)
        try:
            _save_memory()
        except Exception:
            pass
    if plan_rec is not None:
        plan_rec.details["proactive_raised_at"] = now
        try:
            _save_memory()
        except Exception:
            pass
    print(f"[proactive-decision] {state.get('character_id','?')}: "
          f"доставлено (крючок {hook_kind})")

    try:
        await _process_pending_actions(state, ws, loop)
    except Exception as e:
        print(f"[proactive-decision] pending fail: {type(e).__name__}: {e}")
    try:
        await ws.send_json({"type": "done"})
    except Exception:
        pass
    return True


_BODY_WINDOW_FALLBACK = 4


def mark_body_context(state: dict, *, turns: int | None = None) -> None:
    state["body_ctx_left"] = max(int(state.get("body_ctx_left") or 0),
                                 int(turns or _BODY_WINDOW_FALLBACK))


def _body_block_for_turn(state: dict, user_text: str) -> str | None:
    try:
        drawing = state["config"].drawing
        if getattr(drawing, "max_rating", "sfw") == "sfw":
            state["body_ctx_left"] = 0
            return None
        from services import nsfw_anatomy as na
        book = na.codebook(PROJECT_ROOT)
        if book is None:
            state["body_ctx_left"] = 0
            return None

        own = ""
        try:
            for m in reversed(getattr(state.get("history"), "messages", None) or []):
                if isinstance(m, dict) and m.get("role") == "assistant":
                    own = str(m.get("content") or "")
                    break
        except Exception:
            own = ""
        if book.mentions_body(user_text, own):
            mark_body_context(state, turns=book.window)

        left = int(state.get("body_ctx_left") or 0)
        if left <= 0:
            return None
        state["body_ctx_left"] = left - 1

        persona = state["persona"]
        code = ""
        store = state.get("store")
        archive = store.get_archive(persona.character_id) if store else None
        from services import nsfw_extra as _nx
        code = _nx.read_code(archive)
        _app = ""
        try:
            if archive and archive.has_entry("visual/appearance.yaml"):
                from drawing import BaseAppearance
                _ba = BaseAppearance.from_dict(
                    archive.read_yaml("visual/appearance.yaml"))
                _rid = getattr(state["config"].drawing, "renderer_id", "sdxl") or "sdxl"
                _app = _ba.positive_for(_rid) or ""
        except Exception:
            _app = ""
        profile = na.profile_for(
            PROJECT_ROOT, anatomy_code=code,
            gender=(getattr(persona.character, "gender", "") or "female"),
            appearance_tags=[t.strip() for t in _app.split(",") if t.strip()])
        return na.describe(profile, book) or None
    except Exception as e:
        print(f"[anatomy] body block skip: {type(e).__name__}: {e}")
        return None


SNAPSHOT_CARRY_TURNS = 4


def _user_turn_count(state: dict) -> int:
    msgs = getattr(state.get("history"), "messages", None) or []
    return sum(1 for m in msgs if isinstance(m, dict) and m.get("role") == "user"
               and not _is_marker_message(m))


RECENT_SNAPSHOTS = 3
RECENT_SNAPSHOT_TURNS = 20


def _record_recent_snapshot(state: dict, selection: dict, intent: str = "") -> None:
    rec = list(state.get("snapshot_recent") or [])
    rec.append({"tags": list(selection.get("tags") or ()),
                "remove": list(selection.get("remove") or ()), "intent": intent or "",
                "turn": _user_turn_count(state)})
    state["snapshot_recent"] = rec[-RECENT_SNAPSHOTS:]


def _recent_snapshots(state: dict) -> list[dict]:
    now = _user_turn_count(state)
    return [r for r in state.get("snapshot_recent") or []
            if 0 <= now - int(r.get("turn") or 0) <= RECENT_SNAPSHOT_TURNS]





def _contact_allowed() -> bool:
    try:
        from drawing.ladder import contact_allowed
        from services import addons as _addons
        return contact_allowed(_addons.capabilities(PROJECT_ROOT))
    except Exception:
        return False


def _snapshot_ladder_level(state: dict) -> int:
    try:
        if getattr(state["config"].drawing, "max_rating", "sfw") == "sfw":
            return 0
    except Exception:
        return 0
    rec = _recent_snapshots(state)
    if not rec or _user_turn_count(state) - int(rec[-1].get("turn") or 0) > SNAPSHOT_CARRY_TURNS:
        return 0
    from drawing.ladder import level_of
    return level_of(rec[-1].get("tags") or (), rec[-1].get("remove") or ())


def _record_snapshot_state(state: dict, selection: dict, outfit_id: str | None) -> None:
    from drawing import exposure as _ex
    st = _ex.snapshot_state(selection.get("tags") or (), selection.get("remove") or ())
    if st is None:
        state.pop("snapshot_state", None)
        return
    state["snapshot_state"] = dict(st, outfit=outfit_id or "", turn=_user_turn_count(state))


def _snapshot_carry(state: dict, outfit_id: str | None = None) -> dict | None:
    st = state.get("snapshot_state")
    if not st:
        return None
    try:
        if getattr(state["config"].drawing, "max_rating", "sfw") == "sfw":
            return None
    except Exception:
        return None
    if outfit_id is not None and (outfit_id or "") != st.get("outfit", ""):
        return None
    if _user_turn_count(state) - int(st.get("turn") or 0) > SNAPSHOT_CARRY_TURNS:
        return None
    return st


def _snapshot_hint(state: dict) -> str:
    st = _snapshot_carry(state, state.get("runtime_portrait_outfit_id")
                         or state.get("character_default_outfit_id"))
    if not st:
        return ""
    from drawing import exposure as _ex
    return _ex.describe_snapshot(st, gender_of(state["character"]))


def _build_drawing_request(state: dict, intent: str):
    from drawing import BaseAppearance, PipelineRequest

    persona = state["persona"]
    character = persona.character
    config = state["config"]
    store = state.get("store")
    character_id = persona.character_id

    base_appearance = BaseAppearance()
    anatomy_code = ""
    try:
        archive = store.get_archive(character_id) if store else None
        if archive and archive.has_entry("visual/appearance.yaml"):
            visual_data = archive.read_yaml("visual/appearance.yaml")
            base_appearance = BaseAppearance.from_dict(visual_data)
        if archive:
            from services import nsfw_extra as _nx
            anatomy_code = _nx.read_code(archive)
    except Exception as e:
        print(f"[drawing] cannot load base_appearance: {e}")

    refusal_style_hint = None
    if character.prompt_overrides:
        refusal_style_hint = "в твоём стиле, в соответствии с твоими prompt_overrides"

    character_style_id = None
    try:
        archive = store.get_archive(character_id) if store else None
        if archive and archive.has_entry("visual/style.yaml"):
            style_data = archive.read_yaml("visual/style.yaml")
            character_style_id = (
                (style_data or {}).get("preferred_style_id") or None
            )
    except Exception as e:
        print(f"[drawing] cannot load character style override: {e}")

    style_catalog = state.get("drawing_style_catalog")
    style_tags = None
    style_exclude = None
    if style_catalog is not None:
        style_pack = style_catalog.resolve(
            active_style_id=config.drawing.active_style_id,
            character_override_id=character_style_id,
            renderer_id=config.drawing.renderer_id,
        )
        style_tags = list(style_pack.tags) or None
        style_exclude = list(style_pack.exclude) or None

    drawing = config.drawing

    effective_outfit = state.get("runtime_portrait_outfit_id")
    if not effective_outfit:
        try:
            from drawing.portrait import _first_available, PORTRAIT_PREFERRED_OUTFITS
            _pol = persona.outfit_policy
            _own = state.get("character_default_outfit_id")
            _preferred = (((_own,) + tuple(PORTRAIT_PREFERRED_OUTFITS))
                          if _own else PORTRAIT_PREFERRED_OUTFITS)
            effective_outfit = _first_available(
                state["drawing_catalog"], "outfits", _preferred,
                renderer_id=drawing.renderer_id,
                character_id=character_id,
                character_archetypes=persona.archetypes,
                max_rating=drawing.max_rating,
                current_tier=persona.tier,
                character_tag_gates=(_pol.tag_tier_gates if _pol else None),
                character_blocked_tags=(list(_pol.blocked_tags) if _pol else None),
            )
        except Exception as e:
            print(f"[drawing] cannot resolve default portrait outfit: {e}")
            effective_outfit = None

    eff_rating = drawing.max_rating

    from persona.mood_appraisal import build_persona
    persona_hint = build_persona(character)

    from drawing.tag_rounds import detect_framing
    framing_hint = None
    try:
        _msgs = getattr(state.get("history"), "messages", None) or []
        for _m in reversed(_msgs):
            if isinstance(_m, dict) and _m.get("role") == "user":
                framing_hint = detect_framing(_m.get("content") or "")
                break
    except Exception:
        framing_hint = None

    reference_tags = None
    try:
        _ref = state.get("last_shown_image_tags") or {}
        if _ref.get("tags"):
            from services.web import booru_tags_to_prompt
            reference_tags = booru_tags_to_prompt(list(_ref["tags"]))
    except Exception as e:
        print(f"[drawing] cannot build reference tags: {e}")
        reference_tags = None

    from persona.mood_appraisal import current_label
    mood_hint = None
    try:
        _idy = state.get("identity")
        if _idy is not None:
            _rx = (getattr(_idy, "reaction_state", "") or "").strip()
            if _rx and mood_mod.is_reaction(_rx):
                mood_hint = current_label(
                    _rx, float(getattr(_idy, "reaction_intensity", 0.0) or 0.0))
            else:
                mood_hint = current_label(
                    getattr(_idy, "mood_state", "") or "",
                    float(getattr(_idy, "mood_intensity", 0.0) or 0.0),
                )
    except Exception:
        mood_hint = None

    styling_hairstyle: tuple = ()
    styling_extra: tuple = ()
    styling_underwear: tuple = ()
    styling_intimate: tuple = ()
    underwear_layer = (getattr(character, "gender", "") or "female") != "male"
    try:
        from services.self_styling import render_parts, styling_state
        _hs, _extra, _under, _intim = render_parts(
            styling_state(state.get("identity")))
        styling_hairstyle, styling_extra = tuple(_hs), tuple(_extra)
        if eff_rating != "sfw":
            if underwear_layer:
                styling_underwear = tuple(_under)
            styling_intimate = tuple(_intim)
    except Exception as e:
        print(f"[drawing] self-styling skip: {type(e).__name__}: {e}")

    anatomy = None
    if eff_rating != "sfw":
        try:
            from services import nsfw_anatomy
            _rid = getattr(config.drawing, "renderer_id", "sdxl") or "sdxl"
            _app_tags: list[str] = []
            if base_appearance is not None:
                _app_tags = [t.strip() for t
                             in (base_appearance.positive_for(_rid) or "").split(",")
                             if t.strip()]
                _app_tags += [t for t in base_appearance.hard_tags if t]
            anatomy = nsfw_anatomy.profile_for(
                PROJECT_ROOT, anatomy_code=anatomy_code,
                gender=(getattr(character, "gender", "") or "female"),
                appearance_tags=_app_tags)
        except Exception as e:
            print(f"[drawing] anatomy skip: {type(e).__name__}: {e}")
            anatomy = None

    return PipelineRequest.from_persona(
        persona,
        base_appearance=base_appearance,
        user_intent=intent,
        max_rating=eff_rating,
        styling_hairstyle=styling_hairstyle,
        styling_extra=styling_extra,
        styling_underwear=styling_underwear,
        styling_intimate=styling_intimate,
        underwear_layer=underwear_layer,
        anatomy=anatomy,
        snapshot_carry=_snapshot_carry(state, effective_outfit),
        recent_frames=tuple(tuple(r.get("tags") or ()) for r in _recent_snapshots(state)),
        allow_contact=_contact_allowed(),
        refusal_style_hint=refusal_style_hint,
        safety_positive=list(drawing.positive_safety_tags) or None,
        safety_negative=list(drawing.negative_safety_tags) or None,
        style_tags=style_tags,
        style_exclude=style_exclude,
        persona_hint=persona_hint,
        framing_hint=framing_hint,
        mood_hint=mood_hint,
        reference_tags=reference_tags,
        quality_tags=list(drawing.quality_tags) or None,
        current_portrait_outfit_id=effective_outfit,
        critic_max_retries=(
            drawing.vision_critic_max_retries
            if (drawing.vision_critic_enabled and eff_rating == "sfw")
            else 0
        ),
        critic_soft_threshold=drawing.vision_critic_soft_threshold,
        filename_prefix=f"{character_id}/{character_id}",
    )


def _save_memory():
    from api.session_manager import save_state_to_disk
    save_state_to_disk(_get_state(), with_identity=False)


def _apply_store_renames(store) -> None:
    renames = store.consume_renames()
    for old_id, new_id in renames:
        if _reflection_queue is not None:
            n = _reflection_queue.rename_character(old_id, new_id)
            if n:
                print(f"[store] normalize: reflection queue {old_id} → {new_id} "
                      f"({n} item)")
        gen_root = PROJECT_ROOT / "image_gen" / "generated"
        old_dir, new_dir = gen_root / old_id, gen_root / new_id
        if old_dir.is_dir() and not new_dir.exists():
            try:
                old_dir.rename(new_dir)
            except OSError as e:
                print(f"[store] normalize: generated {old_id} → {new_id} "
                      f"не удалось: {e}")


@app.get("/api/characters")
async def list_characters():
    s = _get_state()
    store = s["store"]
    active_id = s.get("character_id") or s["config"].character_id

    characters = []
    _infos = store.list_available()
    _apply_store_renames(store)
    for info in _infos:
        char_id = info["id"]
        characters.append({
            "id": char_id,
            "baseline_id": info.get("baseline_id", char_id),
            "instance_id": info.get("instance_id"),
            "name": info["name"],
            "subtitle": info["subtitle"],
            "short_description": info["short_description"],
            "number": info.get("number"),
            "generation": info.get("generation"),
            "gender": info.get("gender") or "female",
            "avatar_portrait": f"/api/characters/{char_id}/avatar/portrait",
            "avatar_chat": f"/api/characters/{char_id}/avatar/chat",
            "accent_color": info["accent_color"],
            "first_meeting_at": info.get("first_meeting_at"),
            "active": char_id == active_id,
            "version": str(info.get("character_version")
                           or info.get("app_version_created") or "1.0"),
            "training": info.get("training"),
            "is_protected": bool(info.get("is_protected")),
            "is_unlocked": store.is_unlocked(char_id),
        })
    return {"characters": characters}


@app.post("/api/document")
async def attach_document_endpoint(payload: dict):
    s = _get_state()
    if s.get("character") is None:
        return {"ok": False, "error": "нет активного персонажа"}
    path = str((payload or {}).get("path") or "").strip()
    quiet = bool((payload or {}).get("quiet"))
    if not path:
        return {"ok": False, "error": "не указан путь к файлу"}

    from services.documents import DocumentError, attach_document, document_block
    loop = asyncio.get_event_loop()
    try:
        att = await loop.run_in_executor(
            None, lambda: attach_document(
                path, embed_fn=s["client"].embed, project_root=PROJECT_ROOT))
    except DocumentError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        print(f"[docs] attach fail: {type(e).__name__}: {e}")
        return {"ok": False, "error": "не получилось открыть файл"}

    s["document"] = att
    print(f"[docs] attached: {att.name} mode={att.mode} tokens={att.tokens} "
          f"chunks={len(att.chunks)}")
    _achievement_award(s, "first_document")

    ws = s.get("active_ws")
    if ws is not None:
        pages = f", {att.pages} стр." if att.pages else ""
        size_note = ("полностью в контексте" if att.mode == "full"
                     else f"объёмный (~{att.tokens} ток.), доступен поиском")
        try:
            await ws.send_json({"type": "system",
                                "text": f"📄 Приложен документ: {att.name}"
                                        f"{pages} — {size_note}."})
        except Exception:
            pass
        if not quiet:
            trigger = (
                f"(Служебное событие: {_effective_honorific(s)} только что приложил "
                f"к разговору документ «{att.name}»{pages}. "
                + ("Его полный текст теперь в блоке <документ>. "
                   if att.mode == "full" else
                   "Он объёмный — в <документ> только начало, остальное ищи "
                   "search_document(query). ")
                + f"Коротко отреагируй в своём характере: что за документ перед "
                  f"тобой и {gpick(gender_of(s.get('character')), 'готова', 'готов')} "
                  f"помочь с ним — по контексту разговора. Один-два "
                  "предложения, без пересказа всего содержимого.)")
            asyncio.create_task(_interject_event(s, ws, {
                "kind": "document", "trigger": trigger, "card": None,
                "late": False}))

    return {"ok": True, "name": att.name, "mode": att.mode,
            "tokens": att.tokens, "pages": att.pages,
            "chunks": len(att.chunks)}


@app.delete("/api/document")
async def detach_document_endpoint():
    s = _get_state()
    had = s.get("document")
    s["document"] = None
    return {"ok": True, "detached": bool(had)}


@app.post("/api/characters/import")
async def import_character_endpoint(payload: dict):
    s = _get_state()
    path = str((payload or {}).get("path") or "").strip()
    if not path:
        return {"ok": False, "error": "не указан путь к файлу"}
    _gap = _training_gap_for_file(Path(path))
    if _gap and _gap["status"] in ("level_behind", "newer"):
        return {"ok": False, "error": _gap["message"], "training": _gap}
    return s["store"].import_character(path)


@app.post("/api/characters/open-folder")
async def open_characters_folder():
    s = _get_state()
    folder = Path(s["store"].characters_dir)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(folder))
        else:
            import subprocess
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(folder)])
    except Exception as e:
        return {"ok": False, "error": f"не удалось открыть папку: {e}", "path": str(folder)}
    return {"ok": True, "path": str(folder)}


def _training_gap_for_file(path) -> dict | None:
    if not path:
        return None
    try:
        from persona.maid_archive import MaidArchive
        from persona.training import describe_gap, read_training
        a = MaidArchive.peek(path, ("baseline.yaml",), verify=False)
        try:
            name = str((a.read_yaml("baseline.yaml") or {}).get("name")
                       or a.manifest.get("character_id") or "персонаж")
            return describe_gap(read_training(a.manifest), char_name=name)
        finally:
            a.close()
    except Exception as e:
        print(f"[training] статус файла {path} не прочитан: {type(e).__name__}: {e}")
        return None


def _etag_matches(if_none_match: str | None, etag: str) -> bool:
    if not if_none_match:
        return False
    for tag in if_none_match.split(","):
        tag = tag.strip()
        if tag.startswith("W/"):
            tag = tag[2:]
        if tag == etag or tag == "*":
            return True
    return False


def _file_etag(path: Path) -> str:
    import hashlib
    st = path.stat()
    base = f"{st.st_mtime}-{st.st_size}"
    return f'"{hashlib.md5(base.encode(), usedforsecurity=False).hexdigest()}"'


def _file_response(path: Path, if_none_match: str | None,
                   cache_control: str = "no-cache, must-revalidate"):
    etag = _file_etag(path)
    headers = {"Cache-Control": cache_control, "ETag": etag}
    if _etag_matches(if_none_match, etag):
        return Response(status_code=304, headers=headers)
    return FileResponse(path, headers=headers)


def _conditional(if_none_match: str | None, etag: str, make_response):
    headers = {"Cache-Control": "no-cache", "ETag": etag}
    if _etag_matches(if_none_match, etag):
        return Response(status_code=304, headers=headers)
    return make_response(headers)


@app.get("/api/characters/{char_id}/avatar/{kind}")
async def get_character_avatar(request: Request, char_id: str, kind: str,
                               mood: str | None = None):
    project_root = PROJECT_ROOT
    avatar_dir = project_root / "characters" / char_id
    candidates: list[Path]
    if kind == "portrait":
        valid_mood = (mood and mood != mood_mod.NEUTRAL and mood_mod.is_valid(mood))
        if not _get_state()["config"].drawing.mood_portraits_enabled:
            valid_mood = False
        candidates = []
        if valid_mood:
            candidates.append(avatar_dir / f"portrait_default_{mood}.png")
        candidates.append(avatar_dir / "portrait_default.png")
        if valid_mood:
            candidates.append(avatar_dir / f"portrait_{mood}.png")
        candidates.append(avatar_dir / "portrait.png")
        candidates.append(avatar_dir / "avatar.webp")
    else:
        avatar_chat = avatar_dir / "avatar_chat.png"
        if not avatar_chat.exists() and (avatar_dir / "portrait_default.png").exists():
            try:
                from drawing.face_crop import crop_face_avatar
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: crop_face_avatar(
                        avatar_dir / "portrait_default.png", avatar_chat))
            except Exception as e:
                print(f"[avatar] lazy crop failed ({char_id}): {e}")
        candidates = [avatar_chat]
    for path in candidates:
        if path.exists():
            return _file_response(path, request.headers.get("if-none-match"))
    return {"error": "not found"}


@app.post("/api/characters/{char_id}/select")
async def select_character(char_id: str, payload: dict | None = None):
    s = _get_state()
    store = s["store"]

    secret = str((payload or {}).get("secret") or "")
    if store.is_protected(char_id) and not store.is_unlocked(char_id):
        if not secret:
            return {"error": "Персонаж защищён паролем", "locked": True}
        try:
            if not store.verify_secret(char_id, secret):
                return {"error": "Пароль не подошёл", "wrong_password": True}
        except Exception as e:
            return {"error": f"Не удалось открыть персонажа: {e}"}

    from persona.maid_archive import find_character_file as _find_char_file
    _gap = _training_gap_for_file(_find_char_file(store.characters_dir, char_id))
    if _gap and _gap["status"] in ("level_behind", "newer"):
        return {"error": _gap["message"], "training": _gap}

    if s.get("reflection_running") and s.get("character_id") != char_id:
        s["reflection_cancel_requested"] = True
        _deadline = time.time() + 20.0
        while s.get("reflection_running") and time.time() < _deadline:
            await asyncio.sleep(0.5)
        if s.get("reflection_running"):
            _step = (s.get("reflection_step") or {}).get("label") or "рефлексия"
            return {"error": f"Идёт рефлексия прошлой сессии ({_step}) — "
                             f"подожди её конца и попробуй снова", "busy": True}

    if s["history"].messages:
        await _drop_session(s, reason="смена персонажа")

    old_id = s.get("character_id")
    if old_id and old_id != char_id:
        store.unload(old_id)
        if not s["config"].image_gen.keep_generated:
            try:
                s["drawing_storage"].purge(old_id)
            except Exception as e:
                print(f"[drawing] purge {old_id} не удался: {e}")

    try:
        loaded = store.load(char_id, secret=secret or None)
    except KeyError as e:
        return {"error": f"Character {char_id} not found: {e}"}

    character = loaded["character"]
    identity = loaded["identity"]

    s["config"].character_id = char_id
    s["character"] = character
    s["character_id"] = char_id
    s["identity"] = identity
    _refresh_persona(s)
    _register_character_default_outfit(s)

    s["memory"] = UnifiedMemory(None, "", s["client"])
    s["memory"].weather_config = s["config"].weather
    s["memory"]._session_state_ref = s
    s["memory"].user_honorific = resolve_honorific(character)
    s["memory"].load_records(loaded["memory_records"])
    s["memory"].load_address_overrides(character)
    if not s["memory"].records:
        s["memory"].bootstrap_from_character(character)

    s["history"].clear()
    s["session_start_count"] = len(s["memory"].records)
    s["runtime_portrait_outfit_id"] = None

    ws = s.get("active_ws")
    if ws is not None:
        asyncio.create_task(_maybe_initiate(s, ws))

    return {"status": "ok", "name": character.name}


@app.post("/api/characters/{char_id}/reset")
async def reset_character(char_id: str, payload: dict | None = None):
    s = _get_state()
    store = s["store"]
    is_active = (char_id == s.get("character_id"))

    if is_active and s["history"].messages:
        await _drop_session(s, reason=f"reset character {char_id}")

    try:
        store.reset_in_place(char_id)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

    if is_active:
        loaded = store.load(char_id)
        s["character"] = loaded["character"]
        s["identity"] = loaded["identity"]
        _refresh_persona(s)
        s["memory"] = UnifiedMemory(None, "", s["client"])
        s["memory"].weather_config = s["config"].weather
        s["memory"]._session_state_ref = s
        s["memory"].user_honorific = resolve_honorific(s["character"])
        s["memory"].load_records(loaded["memory_records"])
        if not s["memory"].records:
            s["memory"].bootstrap_from_character(s["character"])
        s["history"].clear()
        s["session_start_count"] = len(s["memory"].records)
        s["runtime_portrait_outfit_id"] = None

    try:
        if _reflection_queue is not None:
            dropped = _reflection_queue.remove_character(char_id)
            if dropped:
                print(f"[reset] {char_id}: убрано {dropped} item(ов) из очереди рефлексии")
    except Exception as e:
        print(f"[reset] queue cleanup failed: {e}")
    return {"status": "ok", "character_id": char_id, "was_active": is_active}


def _protection_guard(char_id: str, s: dict) -> dict | None:
    if s.get("character") is None or char_id != s.get("character_id"):
        return {"ok": False,
                "error": "сначала выберите этого персонажа"}
    return None


@app.post("/api/characters/{char_id}/protect")
async def protect_character(char_id: str, payload: dict | None = None):
    s = _get_state()
    store = s["store"]
    if (bad := _protection_guard(char_id, s)) is not None:
        return bad
    password = str((payload or {}).get("password") or "")
    if len(password) < 4:
        return {"ok": False, "error": "пароль слишком короткий"}
    if store.is_protected(char_id):
        return {"ok": False, "error": "защита уже включена"}
    try:
        code = await asyncio.get_event_loop().run_in_executor(
            None, lambda: store.protect(char_id, password))
    except Exception as e:
        print(f"[protect] {char_id}: {type(e).__name__}: {e}")
        return {"ok": False, "error": f"не удалось включить защиту: {e}"}
    return {"ok": True, "recovery_code": code}


@app.post("/api/characters/{char_id}/unprotect")
async def unprotect_character(char_id: str, payload: dict | None = None):
    s = _get_state()
    store = s["store"]
    if (bad := _protection_guard(char_id, s)) is not None:
        return bad
    secret = str((payload or {}).get("secret") or "")
    if not store.is_protected(char_id):
        return {"ok": True}
    from persona import crypto as _crypto
    try:
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: store.unprotect(char_id, secret))
    except _crypto.WrongPasswordError:
        return {"ok": False, "error": "Пароль не подошёл", "wrong_password": True}
    except Exception as e:
        print(f"[unprotect] {char_id}: {type(e).__name__}: {e}")
        return {"ok": False, "error": f"не удалось снять защиту: {e}"}
    return {"ok": True}


@app.post("/api/characters/{char_id}/password")
async def change_character_password(char_id: str, payload: dict | None = None):
    s = _get_state()
    store = s["store"]
    if (bad := _protection_guard(char_id, s)) is not None:
        return bad
    old_secret = str((payload or {}).get("old_secret") or "")
    new_password = str((payload or {}).get("new_password") or "")
    if len(new_password) < 4:
        return {"ok": False, "error": "новый пароль слишком короткий"}
    if not store.is_protected(char_id):
        return {"ok": False, "error": "защита не включена"}
    from persona import crypto as _crypto
    try:
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: store.change_password(char_id, old_secret, new_password))
    except _crypto.WrongPasswordError:
        return {"ok": False, "error": "Текущий пароль не подошёл",
                "wrong_password": True}
    except Exception as e:
        print(f"[password] {char_id}: {type(e).__name__}: {e}")
        return {"ok": False, "error": f"не удалось сменить пароль: {e}"}
    return {"ok": True}


@app.post("/api/background/state")
async def push_app_state(payload: dict):
    state = payload.get("state")
    if isinstance(state, str):
        prev = app_state_mirror.get_diagnostic().get("state")
        app_state_mirror.set(state)
        if (state in ("FOREGROUND", "ACTIVE_CHAT")
                and prev in (None, "BACKGROUND", "IDLE_FOREGROUND")
                and _state):
            ws = _state.get("active_ws")
            if ws is not None:
                asyncio.create_task(_maybe_morning_brief(_state, ws))
    return {"status": "ok"}


@app.get("/api/background/state")
async def get_app_state():
    from services.background.analyzer import analyzer_tick
    _lc = get_lifecycle()
    decision = analyzer_tick(llm_loaded=bool(_lc and _lc.is_loaded))
    vram = get_vram_info(0)
    return {
        "state": app_state_mirror.get_diagnostic(),
        "vram": {
            "available": vram.available,
            "name": vram.name,
            "free_mb": vram.free_mb,
            "used_mb": vram.used_mb,
            "total_mb": vram.total_mb,
            "free_pct": round(vram.free_pct, 1),
        },
        "analyzer": {
            "verdict": decision.verdict.value,
            "reason": decision.reason,
            "is_go": decision.is_go,
        },
        "session_engaged": bool(_state) and session_engaged(_state),
    }


@app.get("/api/character")
async def get_character():
    s = _get_state()
    char = s["character"]
    identity = s["identity"]
    if char is None:
        return {"active": False, "name": None}
    return {
        "active": True,
        "name": char.name,
        "core_identity": char.core_identity,
        "mood": _display_mood(identity),
        "action": "ожидает",
        "avatar_portrait": f"/api/avatar/portrait",
        "avatar_chat": f"/api/avatar/chat",
        "accent_color": char.accent_color,
        "subtitle": char.subtitle,
        "short_description": char.short_description,
        "number": char.number,
        "generation": char.generation,
        "is_protected": s["store"].is_protected(s.get("character_id") or ""),
    }


@app.get("/api/avatar/{kind}")
async def get_avatar(request: Request, kind: str, mood: str | None = None):
    s = _get_state()
    char = s["character"]
    char_id = s.get("character_id", "")
    project_root = PROJECT_ROOT

    candidates: list[Path] = []
    if kind == "portrait":
        cdir = project_root / "characters" / char_id if char_id else None
        valid_mood = (mood and mood != mood_mod.NEUTRAL and mood_mod.is_valid(mood))
        if not s["config"].drawing.mood_portraits_enabled:
            valid_mood = False
        slot = _portrait_basename(s)
        default_oid = s.get("character_default_outfit_id")
        if cdir is not None:
            if valid_mood:
                candidates.append(cdir / f"{slot}_{mood}.png")
                if slot == "portrait_default" and default_oid:
                    candidates.append(cdir / f"portrait_{default_oid}_{mood}.png")
            candidates.append(cdir / f"{slot}.png")
            if slot != "portrait_default":
                if valid_mood:
                    candidates.append(cdir / f"portrait_default_{mood}.png")
                candidates.append(cdir / "portrait_default.png")
        candidates.append(project_root / (char.avatar_portrait or f"characters/{char_id or 'hinari'}/avatar.webp"))
    elif kind == "chat":
        cdir = project_root / "characters" / char_id if char_id else None
        if cdir is not None:
            if _portrait_basename(s) != "portrait_default":
                candidates.append(cdir / f"{_avatar_basename(s)}.png")
                candidates.append(cdir / "avatar_chat_outfit.png")
            avatar_default = cdir / "avatar_chat.png"
            if not avatar_default.exists() and (cdir / "portrait_default.png").exists():
                try:
                    from drawing.face_crop import crop_face_avatar
                    await asyncio.get_event_loop().run_in_executor(
                        None, lambda: crop_face_avatar(
                            cdir / "portrait_default.png", avatar_default))
                except Exception as e:
                    print(f"[avatar] lazy crop failed: {e}")
            candidates.append(avatar_default)
        candidates.append(project_root / (char.avatar_chat or f"characters/{char_id or 'hinari'}/avatar_chat.png"))
    else:
        return {"error": "unknown kind"}

    for path in candidates:
        if path.exists():
            return _file_response(path, request.headers.get("if-none-match"))
    return {"error": "file not found"}


@app.get("/api/settings")
async def get_settings():
    s = _get_state()
    return read_current(s["config"])


@app.post("/api/settings")
async def update_settings(patch: dict):
    s = _get_state()
    result = apply_and_save(s["config"], patch, PROJECT_ROOT)
    if "llm.reasoning_mode" in (patch or {}):
        s["client"].reasoning_mode = s["config"].llm.reasoning_mode
    if "llm.vram_free_mib" in (patch or {}):
        _v = int(s["config"].llm.vram_free_mib or 0)
        s["config"].llm.vram_free_mib = max(256, min(6144, _v))
        _lc = get_lifecycle()
        if _lc is not None and _lc.state.name == "LOADED":
            asyncio.create_task(_lc.request_unload("vram reserve change"))
    return result


@app.get("/api/models")
async def list_models():
    from config import LLM_MODELS, MODEL_CATALOG, model_label, resolve_ctx_step
    from services import setup as _setup_mod
    s = _get_state()
    overrides = getattr(s["config"].llm, "ctx_overrides", None) or {}
    current = s["config"].llm.model_choice
    keys = list(MODEL_CATALOG)
    if current in LLM_MODELS and current not in keys:
        keys.append(current)
    models = []
    for key in keys:
        spec = LLM_MODELS[key]
        avail = (not spec["model"]) or (PROJECT_ROOT / spec["model"]).exists()
        ctx_now, _hist = resolve_ctx_step(spec, overrides.get(key))
        entry = {
            "key": key, "label": model_label(key), "available": avail,
            "ctx_steps": [{"ctx": int(p[0]), "hist": int(p[1])}
                          for p in (spec.get("ctx_steps") or [])],
            "ctx_current": ctx_now,
            "ctx_default": int(spec.get("ctx") or 0),
            "experimental": bool(spec.get("experimental")),
        }
        group = _setup_mod.group_models(key)
        if group:
            missing = [m for m in group
                       if not _setup_mod.is_present(m, PROJECT_ROOT)]
            entry["downloadable"] = True
            entry["download_size"] = sum(m.size for m in missing)
            dl = _setup_mod.group_download_status(key)
            if dl is not None:
                entry["download"] = dl
        else:
            entry["downloadable"] = False
        models.append(entry)
    return {"current": current, "models": models}


@app.post("/api/models/download")
async def download_model(payload: dict):
    from config import LLM_MODELS
    from services import setup as _setup_mod
    choice = ((payload or {}).get("choice") or "").strip().lower()
    if choice not in LLM_MODELS:
        return {"error": f"неизвестная модель: {choice!r}"}
    res = _setup_mod.start_group_download(PROJECT_ROOT, choice)
    if "error" not in res:
        print(f"[model] докачка {choice}: queued={res.get('queued')}")
    return res


@app.post("/api/model/ctx")
async def set_model_ctx(payload: dict):
    from config import LLM_MODELS, apply_model_choice, resolve_ctx_step
    from services import setup as _setup_mod
    s = _get_state()
    choice = ((payload or {}).get("choice")
              or s["config"].llm.model_choice or "").strip().lower()
    spec = LLM_MODELS.get(choice)
    if spec is None:
        return {"error": f"неизвестная модель: {choice!r}"}
    try:
        ctx = int((payload or {}).get("ctx") or 0)
    except (TypeError, ValueError):
        ctx = 0
    steps = [int(p[0]) for p in (spec.get("ctx_steps") or [])]
    if ctx not in steps:
        return {"error": f"недопустимая ступень окна: {ctx}"}
    if s.get("session_processing"):
        return {"error": "идёт генерация — поменяй окно, когда освободится"}

    prev_over = dict(getattr(s["config"].llm, "ctx_overrides", None) or {})
    new_over = dict(prev_over)
    if ctx == int(spec.get("ctx") or 0):
        new_over.pop(choice, None)
    else:
        new_over[choice] = ctx
    if new_over == prev_over and choice == s["config"].llm.model_choice:
        ctx_now, hist_now = resolve_ctx_step(spec, new_over.get(choice))
        return {"ok": True, "choice": choice, "ctx": ctx_now, "hist": hist_now,
                "note": "уже выбрана"}

    def _apply(over: dict) -> None:
        s["config"].llm.ctx_overrides = over
        if choice == s["config"].llm.model_choice:
            apply_model_choice(s["config"], choice)
            s["config"].llm.model = _setup_mod.resolve_llm_model(
                PROJECT_ROOT, s["config"].llm.model)
            if s.get("history") is not None:
                s["history"].max_tokens = s["config"].llm.max_history_tokens

    _apply(new_over)
    if choice == s["config"].llm.model_choice:
        lifecycle = get_lifecycle()
        if lifecycle is not None and lifecycle.state.name == "LOADED":
            ok = await lifecycle.request_unload("ctx step change")
            if not ok:
                _apply(prev_over)
                return {"error": "модель сейчас занята фоновой задачей — "
                                 "попробуй поменять окно чуть позже"}
    apply_and_save(s["config"], {"llm.ctx_overrides": s["config"].llm.ctx_overrides},
                   PROJECT_ROOT)
    ctx_now, hist_now = resolve_ctx_step(spec, new_over.get(choice))
    print(f"[model] ctx step {choice} → {ctx_now} (hist {hist_now})")
    return {"ok": True, "choice": choice, "ctx": ctx_now, "hist": hist_now}


@app.post("/api/model")
async def switch_model(payload: dict):
    from config import LLM_MODELS
    s = _get_state()
    choice = ((payload or {}).get("choice") or "").strip().lower()
    if choice not in LLM_MODELS:
        return {"error": f"неизвестная модель: {choice!r}"}
    return await _apply_model_switch(s, choice)


async def _apply_model_switch(s: dict, choice: str) -> dict:
    from config import LLM_MODELS, apply_model_choice, model_label
    from llm.backends import get_backend
    spec = LLM_MODELS[choice]
    if spec["model"] and not (PROJECT_ROOT / spec["model"]).exists():
        return {"error": f"файл модели не найден: {spec['model']}"}
    if s.get("session_processing"):
        return {"error": "идёт генерация — переключи модель, когда освободится"}
    if choice == s["config"].llm.model_choice:
        return {"ok": True, "current": choice, "note": "уже выбрана"}
    prev_choice = s["config"].llm.model_choice
    apply_model_choice(s["config"], choice)
    if s.get("history") is not None:
        s["history"].max_tokens = s["config"].llm.max_history_tokens
    from services import setup as _setup_mod
    s["config"].llm.model = _setup_mod.resolve_llm_model(PROJECT_ROOT, s["config"].llm.model)
    apply_and_save(s["config"], {"llm.model_choice": choice}, PROJECT_ROOT)
    lifecycle = get_lifecycle()
    if lifecycle is not None and lifecycle.state.name == "LOADED":
        ok = await lifecycle.request_unload("model swap")
        if not ok:
            apply_model_choice(s["config"], prev_choice)
            if s.get("history") is not None:
                s["history"].max_tokens = s["config"].llm.max_history_tokens
            apply_and_save(s["config"], {"llm.model_choice": prev_choice}, PROJECT_ROOT)
            return {"error": "модель сейчас занята фоновой задачей — "
                             "попробуй переключить чуть позже"}
    elif _llama_mgr is not None:
        try:
            await asyncio.get_event_loop().run_in_executor(None, _llama_mgr.stop)
        except Exception as e:
            print(f"[model] stop llama failed: {e}")
    try:
        s["client"].backend = get_backend(s["config"].llm.family)
    except Exception as e:
        print(f"[model] backend update failed: {e}")
    s["client"].fast_post_session = bool(spec.get("fast_post", False))
    print(f"[model] → {choice} ({spec['label']}), family={s['config'].llm.family}"
          f"{', post=fast' if s['client'].fast_post_session else ''}")
    return {"ok": True, "current": choice, "label": model_label(choice)}


@app.get("/api/models/presets")
async def list_model_presets():
    from config import (LLM_MODELS, LLM_PRESETS, PRESET_ORDER, model_label,
                        resolve_ctx_step, resolve_preset)
    from services import setup as _setup_mod
    from services import machine_fit as _mf
    s = _get_state()
    cfg = s["config"]
    machine = _mf.machine_info()
    gpu = {"available": machine["gpu_available"], "total_mib": machine["vram_mib"]}
    free_after = int(getattr(cfg.llm, "vram_free_mib", 0) or 0)
    overrides = getattr(cfg.llm, "ctx_overrides", None) or {}

    def _model_block(mkey: str, ctx_override) -> dict:
        spec = LLM_MODELS[mkey]
        ctx, hist = resolve_ctx_step(spec, ctx_override)
        est = _mf.estimate_need_mib(spec, ctx, PROJECT_ROOT)
        verdict = _mf.fit_verdict(est["need_mib"], gpu, machine["ram_mib"], free_after)
        avail = (not spec["model"]) or (PROJECT_ROOT / spec["model"]).exists()
        out = {"model": mkey, "model_label": model_label(mkey), "available": avail,
               "vision": bool(spec.get("mmproj")),
               "experimental": bool(spec.get("experimental")),
               "ctx": ctx, "hist": hist,
               "expected_tps": spec.get("expected_tps"),
               **est, **verdict}
        group = _setup_mod.group_models(mkey)
        if group:
            missing = [m for m in group if not _setup_mod.is_present(m, PROJECT_ROOT)]
            out["downloadable"] = True
            out["download_size"] = sum(m.size for m in missing)
            dl = _setup_mod.group_download_status(mkey)
            if dl is not None:
                out["download"] = dl
        else:
            out["downloadable"] = False
        return out

    presets = []
    for key in PRESET_ORDER:
        p = LLM_PRESETS[key]
        entry = {"key": key, "label": p["label"], "summary": p.get("summary", "")}
        if p.get("model"):
            entry.update(_model_block(p["model"], None))
            entry["reasoning_mode"] = p["reasoning_mode"]
            entry["speed"] = int(p.get("speed") or 0)
        else:
            cur = cfg.llm.model_choice
            if cur in LLM_MODELS:
                entry["current"] = {**_model_block(cur, overrides.get(cur)),
                                    "reasoning_mode": cfg.llm.reasoning_mode}
        presets.append(entry)
    return {"current": resolve_preset(cfg), "machine": machine, "presets": presets}


@app.post("/api/model/preset")
async def apply_model_preset(payload: dict):
    from config import (LLM_MODELS, LLM_PRESETS, apply_model_choice, model_label,
                        resolve_preset)
    from services import setup as _setup_mod
    s = _get_state()
    cfg = s["config"]
    key = ((payload or {}).get("preset") or "").strip().lower()
    p = LLM_PRESETS.get(key)
    if p is None:
        return {"error": f"неизвестный пресет: {key!r}"}
    if not p.get("model"):
        cfg.llm.preset = key
        apply_and_save(cfg, {"llm.preset": key}, PROJECT_ROOT)
        print(f"[model] preset → {key}")
        return {"ok": True, "current": resolve_preset(cfg), "label": p["label"],
                "restart": False}
    mkey = p["model"]
    spec = LLM_MODELS[mkey]
    if spec["model"] and not (PROJECT_ROOT / spec["model"]).exists():
        return {"error": f"модель пресета не скачана: {spec['label']}"}
    if s.get("session_processing"):
        return {"error": "идёт генерация — выбери пресет, когда освободится"}
    prev = {"model_choice": cfg.llm.model_choice,
            "reasoning_mode": cfg.llm.reasoning_mode,
            "ctx_overrides": dict(getattr(cfg.llm, "ctx_overrides", None) or {}),
            "preset": getattr(cfg.llm, "preset", "")}
    switch_needed = cfg.llm.model_choice != mkey
    ctx_changed = bool(prev["ctx_overrides"].get(mkey))

    def _rollback() -> None:
        cfg.llm.ctx_overrides = dict(prev["ctx_overrides"])
        cfg.llm.reasoning_mode = prev["reasoning_mode"]
        cfg.llm.preset = prev["preset"]
        apply_model_choice(cfg, prev["model_choice"])
        cfg.llm.model = _setup_mod.resolve_llm_model(PROJECT_ROOT, cfg.llm.model)
        if s.get("history") is not None:
            s["history"].max_tokens = cfg.llm.max_history_tokens
        s["client"].reasoning_mode = cfg.llm.reasoning_mode
        apply_and_save(cfg, {}, PROJECT_ROOT)

    over = dict(prev["ctx_overrides"])
    over.pop(mkey, None)
    cfg.llm.ctx_overrides = over
    cfg.llm.reasoning_mode = p["reasoning_mode"]
    cfg.llm.preset = key
    if switch_needed:
        r = await _apply_model_switch(s, mkey)
        if r.get("error"):
            _rollback()
            return r
    else:
        apply_model_choice(cfg, mkey)
        cfg.llm.model = _setup_mod.resolve_llm_model(PROJECT_ROOT, cfg.llm.model)
        if s.get("history") is not None:
            s["history"].max_tokens = cfg.llm.max_history_tokens
        if ctx_changed:
            lifecycle = get_lifecycle()
            if lifecycle is not None and lifecycle.state.name == "LOADED":
                ok = await lifecycle.request_unload("preset ctx")
                if not ok:
                    _rollback()
                    return {"error": "модель сейчас занята фоновой задачей — "
                                     "попробуй выбрать пресет чуть позже"}
    s["client"].reasoning_mode = cfg.llm.reasoning_mode
    apply_and_save(cfg, {}, PROJECT_ROOT)
    print(f"[model] preset → {key} ({spec['label']}, reasoning={p['reasoning_mode']})")
    return {"ok": True, "current": resolve_preset(cfg), "label": p["label"],
            "model_label": model_label(p["model"]), "restart": switch_needed or ctx_changed}


@app.get("/api/character/theme")
async def get_character_theme():
    s = _get_state()
    cid = s.get("character_id")
    store = s.get("store")
    if not cid or store is None:
        return {"theme": None}
    bundle = store.ui_bundle(cid)
    return {"theme": bundle["structure"] if bundle else None}


@app.get("/api/characters/{char_id}/ui/structure")
async def get_character_ui_structure(request: Request, char_id: str, dark: int = 0):
    s = _get_state()
    store = s.get("store")
    bundle = store.ui_bundle(char_id) if store is not None else None
    if bundle is None:
        return {"structure": None}
    payload = {"structure": bundle["dark"] if dark else bundle["structure"]}
    return _conditional(request.headers.get("if-none-match"), bundle["etag"],
                        lambda h: JSONResponse(payload, headers=h))


_LIST_AVATAR_LOCKS: dict[str, asyncio.Lock] = {}


def _list_avatar_sync(cdir: Path) -> Path | None:
    from drawing.list_avatar import is_fresh, make_list_avatar
    portrait = cdir / "portrait_default.png"
    dst = cdir / "list_avatar.png"
    if not portrait.exists() or is_fresh(dst, portrait):
        return dst if dst.exists() else None
    try:
        status = make_list_avatar(portrait, dst)
        print(f"[list_avatar] {cdir.name}: {status}")
    except Exception as e:
        print(f"[list_avatar] {cdir.name}: {type(e).__name__}: {e}")
    return dst if dst.exists() else None


async def _ensure_list_avatar(char_id: str) -> Path | None:
    cdir = PROJECT_ROOT / "characters" / char_id
    lock = _LIST_AVATAR_LOCKS.setdefault(char_id, asyncio.Lock())
    async with lock:
        return await asyncio.get_event_loop().run_in_executor(
            None, _list_avatar_sync, cdir)


@app.get("/api/characters/{char_id}/ui/list-avatar")
async def get_character_list_avatar(request: Request, char_id: str):
    from drawing.list_avatar import has_matte
    if not char_id or any(ch in char_id for ch in "/\\") or ".." in char_id:
        return Response(status_code=404)
    s = _get_state()
    store = s.get("store")
    inm = request.headers.get("if-none-match")
    gen = await _ensure_list_avatar(char_id)
    bundle = store.ui_bundle(char_id) if store is not None else None
    png = bundle.get("list_avatar") if bundle else None
    if gen is not None and (not png or has_matte(gen)):
        return _file_response(gen, inm)
    if png:
        return _conditional(inm, bundle["etag"],
                            lambda h: Response(content=png, media_type="image/png", headers=h))
    if gen is not None:
        return _file_response(gen, inm)
    return Response(status_code=404)


_GALLERY_ID_RX = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _gallery_item_out(it: dict) -> dict:
    gid = it["id"]
    return {
        **{k: it.get(k) for k in ("id", "source", "intent", "rating", "added_at",
                                  "width", "height")},
        "created_at": it.get("created_at") or it.get("added_at"),
        "url": f"/api/gallery/{gid}",
        "thumb_url": f"/api/gallery/{gid}?thumb=1",
    }


def _active_archive(s):
    cid = s.get("character_id")
    store = s.get("store")
    return store.get_archive(cid) if (cid and store is not None) else None


def _active_gallery(s):
    cid = s.get("character_id")
    store = s.get("store")
    if not cid or store is None:
        return None, None
    return store.get_archive(cid), store.session_key(cid)


@app.get("/api/gallery")
async def gallery_list():
    from persona.gallery import GALLERY_MAX, load_index
    s = _get_state()
    archive, dek = _active_gallery(s)
    try:
        items = load_index(archive, dek) if archive is not None else []
    except Exception as e:
        print(f"[gallery] index unreadable: {type(e).__name__}: {e}")
        items = []
    return {"items": [_gallery_item_out(it) for it in items],
            "count": len(items), "max": GALLERY_MAX}


@app.post("/api/gallery/add")
async def gallery_add(payload: dict):
    from persona.gallery import GalleryFullError, add_image
    s = _get_state()
    archive, dek = _active_gallery(s)
    if archive is None or s.get("identity") is None:
        return {"error": "нет активного персонажа"}
    url = str((payload or {}).get("url") or "")
    storage = s.get("drawing_storage")
    path = storage.path_for_media_url(url) if storage is not None else None
    if path is None:
        return {"error": "в галерею можно сохранить только свой сгенерированный снимок"}
    meta: dict = {}
    sidecar = path.with_suffix(".json")
    if sidecar.exists():
        try:
            meta = json.loads(sidecar.read_text(encoding="utf-8")) or {}
        except Exception:
            meta = {}
    source = url.split("?", 1)[0]
    _m = source.find("/media/generated/")
    if _m > 0:
        source = source[_m:]
    created_at = None
    try:
        from datetime import datetime as _dt, timezone as _tz
        created_at = _dt.strptime(str(meta.get("generated_at") or ""),
                                  "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_tz.utc).timestamp()
    except ValueError:
        try:
            created_at = path.stat().st_mtime
        except OSError:
            created_at = None

    def _do():
        item = add_image(archive, path.read_bytes(), source=source,
                         intent=str(meta.get("intent") or ""),
                         rating=str(meta.get("rating") or ""),
                         prompt=str(meta.get("assembled_positive") or ""),
                         dek=dek, created_at=created_at)
        s["identity"].save()
        return item

    try:
        item = await asyncio.get_event_loop().run_in_executor(None, _do)
    except GalleryFullError as e:
        return {"error": f"галерея полна — максимум {e.limit} снимков; "
                         "удали лишнее в карточке персонажа"}
    except Exception as e:
        print(f"[gallery] add failed: {type(e).__name__}: {e}")
        return {"error": "не удалось сохранить снимок"}
    _achievement_award(s, "first_gallery")
    return {"ok": True, "item": _gallery_item_out(item)}


@app.post("/api/gallery/remove")
async def gallery_remove(payload: dict):
    from persona.gallery import remove_image
    s = _get_state()
    archive, dek = _active_gallery(s)
    gid = str((payload or {}).get("id") or "")
    if archive is None or s.get("identity") is None or not _GALLERY_ID_RX.match(gid):
        return {"error": "нет такого снимка"}

    def _do():
        ok = remove_image(archive, gid, dek=dek)
        if ok:
            s["identity"].save()
        return ok

    try:
        ok = await asyncio.get_event_loop().run_in_executor(None, _do)
    except Exception as e:
        print(f"[gallery] remove failed: {type(e).__name__}: {e}")
        return {"error": "не удалось удалить снимок"}
    return {"ok": bool(ok)}


@app.get("/api/gallery/{gid}")
async def gallery_image(gid: str, thumb: int = 0):
    from persona.gallery import read_image
    s = _get_state()
    archive, dek = _active_gallery(s)
    if archive is None or not _GALLERY_ID_RX.match(gid):
        return Response(status_code=404)
    try:
        data = read_image(archive, gid, thumb=bool(thumb), dek=dek)
    except Exception as e:
        print(f"[gallery] read failed ({gid}): {type(e).__name__}: {e}")
        data = None
    if not data:
        return Response(status_code=404)
    return Response(content=data, media_type="image/webp",
                    headers={"Cache-Control": "no-store"})


_INFO_TIER_BOUNDS = (0.1, 0.3, 0.6, 0.95)
_INFO_TIER_WORDS = {
    "trust": ("Недоверие", "Настороженность", "Откровенность", "Опора", "Преданность"),
    "intimacy": ("Отчуждение", "Дистанция", "Потепление", "Привязанность", "Сокровенность"),
    "respect": ("Пренебрежение", "Скепсис", "Признание", "Почтение", "Восхищение"),
}


def _info_tier(kind: str, value: float) -> tuple[str, str]:
    idx = sum(1 for b in _INFO_TIER_BOUNDS if value >= b)
    roman = ("I", "II", "III", "IV", "V")[idx]
    return roman, _INFO_TIER_WORDS.get(kind, _INFO_TIER_WORDS["trust"])[idx]


_THOUGHTS_TIER_IDX = 3
_DIARY_TIER_IDX = 4
_CARD_ENTRIES_MAX = 50
_DIARY_KINDS = ("diary", "diary_consolidation")


def _card_entries_section(trust_idx: int, required_idx: int, items_fn) -> dict:
    roman = ("I", "II", "III", "IV", "V")[required_idx]
    word = _INFO_TIER_WORDS["trust"][required_idx]
    out = {"unlocked": trust_idx >= required_idx, "tier_required": roman,
           "label_required": word, "items": []}
    if out["unlocked"]:
        try:
            out["items"] = items_fn()
        except Exception as e:
            print(f"[card] entries failed: {type(e).__name__}: {e}")
    return out


def _card_thoughts(idy) -> list[dict]:
    fn = getattr(idy, "get_active_thoughts", None)
    out = []
    for t in (fn() if callable(fn) else []):
        text = str(getattr(t, "text", "") or "").strip()
        if not text:
            continue
        out.append({"text": text, "kind": str(getattr(t, "kind", "") or ""),
                    "relevance": round(float(getattr(t, "relevance", 0.0) or 0.0), 3),
                    "created_at": float(getattr(t, "created_at", 0.0) or 0.0),
                    "tier": max(0, min(3, int(getattr(t, "strength", 0) or 0)))})
    return out[:_CARD_ENTRIES_MAX]


_CHARACTER_TIER_IDX = 2
_AXIS_CARD: tuple[tuple[str, str, str, str], ...] = (
    ("confidence", "Уверенность", "робость", "самоуверенность"),
    ("warmth", "Теплота", "холодность", "опека"),
    ("openness", "Открытость", "закрытость", "рассеянность"),
    ("cheerfulness", "Жизнерадостность", "уныние", "беспечность"),
    ("playfulness", "Игривость", "серьёзность", "дурачество"),
    ("energy", "Инициатива", "пассивность", "суета"),
    ("expressiveness", "Выразительность", "сдержанность", "несдержанность"),
    ("diligence", "Дотошность", "небрежность", "педантизм"),
    ("directness", "Прямота", "такт", "резкость"),
)


def _card_character(idy, character, state: dict | None = None) -> dict:
    from persona.vulnerability_catalog import resolve_trait
    vals = {}
    for st in getattr(idy, "self_statements", []) or []:
        sid = str(getattr(st, "id", "") or "")
        if sid.startswith("axis_"):
            vals[sid[len("axis_"):]] = float(getattr(st, "axis_value", 0.0) or 0.0)
    axes = []
    from persona.axis_dynamics import axis_frame, goal_dir
    from persona.evolution import axis_goal_phrase, axis_stimulus_hint
    from persona.gender import fill_forms as _fill_hint, gender_of as _gender_of
    _hint_gender = _gender_of(character)
    for key, label, left, right in _AXIS_CARD:
        if key not in vals:
            continue
        val = max(0.0, min(1.0, vals[key]))
        fr = axis_frame(character, key)
        g = goal_dir(idy, key)
        axes.append({"key": key, "label": label, "left": left, "right": right,
                     "value": round(val, 3), "norm": round(fr.norm, 3),
                     "band_lo": round(fr.band_lo, 3), "band_hi": round(fr.band_hi, 3),
                     "goal": g, "goal_label": axis_goal_phrase(key, g) if g else "",
                     "wish_down": axis_goal_phrase(key, -1),
                     "wish_up": axis_goal_phrase(key, 1),
                     "hint_down": _fill_hint(axis_stimulus_hint(key, -1), _hint_gender),
                     "hint_up": _fill_hint(axis_stimulus_hint(key, 1), _hint_gender)})
    from persona.gender import fill_description, fill_forms, gender_of
    gender = gender_of(character)

    def _row(tid, trait, kind, *, at=None, innate=False):
        return {
            "id": tid,
            "text": fill_forms(str(getattr(trait, "text", "") or ""), gender),
            "description": fill_description(
                str(getattr(trait, "description", "") or ""), gender),
            "kind": kind,
            "innate": bool(innate),
            "special": bool(getattr(trait, "special", False)),
            "activated_at": float(getattr(at, "activated_at", 0.0) or 0.0) if at else 0.0,
            "source_event": str(getattr(at, "source_event", "") or "") if at else "",
        }

    traits = []
    by_id = {str(at.trait_id): at for at in (getattr(idy, "active_traits", []) or [])}
    quirks = []
    if state is not None:
        try:
            for q in _quirks_carried(state):
                at = by_id.get(q.id)
                quirks.append(_row(q.id, q, "quirk", at=at, innate=at is None))
        except Exception as e:
            print(f"[card] причуды пропущены: {type(e).__name__}: {e}")
    for at in getattr(idy, "active_traits", []) or []:
        aid = str(at.trait_id)
        if aid.startswith("quirk_"):
            continue
        try:
            trait = resolve_trait(aid, character)
        except Exception:
            trait = None
        kind = ("strength" if str(getattr(trait, "id", "") or "").startswith("strength_")
                else "vulnerability")
        traits.append(_row(aid, trait, kind, at=at))
    traits.extend(quirks)
    from persona.axis_dynamics import goal_drip_rate, goal_overrides_natural, goal_respect_stage
    from persona.relationship_axes import current_axis_values as _rel_values
    _rv = _rel_values(idy).get("respect")
    _roman, _stage_label = _info_tier("respect", float(_rv)) if _rv is not None else ("", "")
    return {"axes": axes, "traits": traits,
            "goal_rate": round(goal_drip_rate(character, idy), 4),
            "goal_stage": goal_respect_stage(character, idy),
            "goal_stage_label": f"{_roman} {_stage_label}".strip(),
            "goal_override": goal_overrides_natural(character, idy)}


def _card_diary(memory) -> list[dict]:
    out = []
    for r in getattr(memory, "records", None) or []:
        if getattr(r, "type", "") != "рефлексия" or getattr(r, "is_forgotten", False):
            continue
        d = getattr(r, "details", None) or {}
        kind = str(d.get("reflection_type") or "diary")
        if kind not in _DIARY_KINDS:
            continue
        text = str(d.get("description") or getattr(r, "title", "") or "").strip()
        if not text:
            continue
        try:
            sig = int(d.get("significance") or 0)
        except (TypeError, ValueError):
            sig = 0
        out.append({"id": getattr(r, "record_id", ""), "text": text, "kind": kind,
                    "created_at": float(getattr(r, "created_at", 0.0) or 0.0),
                    "importance": round(float(getattr(r, "importance", 0.0) or 0.0), 3),
                    "tier": max(0, min(3, sig - 1))})
    out.sort(key=lambda x: x["created_at"], reverse=True)
    return out[:_CARD_ENTRIES_MAX]


def _gacha_env(s) -> tuple[bool, str]:
    from services.self_styling import character_hair_length
    try:
        allow_nsfw = (s["config"].drawing.max_rating != "sfw")
    except Exception:
        allow_nsfw = False
    return allow_nsfw, character_hair_length(s)


def _tickets_word(n: int) -> str:
    n = abs(int(n)) % 100
    if 10 < n < 20:
        return "билетов"
    n %= 10
    if n == 1:
        return "билет"
    if 1 < n < 5:
        return "билета"
    return "билетов"


def _achievement_cards(achs) -> list[dict]:
    if not achs:
        return []
    lines = [f"🎟 Достижение «{a.title}» — +{a.tickets} {_tickets_word(a.tickets)}"
             for a in achs]
    return [{"type": "system", "text": "\n".join(lines)}, {"type": "gacha_changed"}]


def _achievement_notify(state: dict, achs, loop=None) -> None:
    cards = _achievement_cards(achs)
    if not cards:
        return
    ev = {"kind": "achievement", "trigger": "", "late": False, "card": cards}
    ws = state.get("active_ws")
    if loop is not None:
        asyncio.run_coroutine_threadsafe(_interject_event(state, ws, ev), loop)
        return
    try:
        asyncio.get_running_loop().create_task(_interject_event(state, ws, ev))
    except RuntimeError:
        state.setdefault("pending_interjections", []).append(ev)


def _achievement_save(idy) -> None:
    try:
        idy.save()
    except Exception as e:
        print(f"[achievements] save fail: {type(e).__name__}: {e}")


def _achievement_award(state: dict, aid: str, loop=None) -> None:
    try:
        from services import achievements, gacha
        idy = state.get("identity")
        if idy is None or not gacha.has_gacha(idy):
            return
        a = achievements.award(idy, aid)
        if a is None:
            return
        _achievement_save(idy)
        print(f"[achievements] {aid}: +{a.tickets}")
        _achievement_notify(state, [a], loop)
    except Exception as e:
        print(f"[achievements] award {aid} failed: {type(e).__name__}: {e}")


def _achievements_on_tool(state: dict, name: str, result, loop=None) -> None:
    try:
        from services import achievements, gacha
        idy = state.get("identity")
        if idy is None or not gacha.has_gacha(idy):
            return
        achs = achievements.on_tool_result(idy, name, result)
        if achs:
            _achievement_save(idy)
            print(f"[achievements] tool {name}: {[a.id for a in achs]}")
            _achievement_notify(state, achs, loop)
    except Exception as e:
        print(f"[achievements] tool hook failed: {type(e).__name__}: {e}")


def _achievements_check(state: dict, *, notify: bool = True) -> list:
    try:
        from services import achievements, gacha
        from persona.relationship_axes import current_axis_values
        idy = state.get("identity")
        if idy is None or not gacha.has_gacha(idy):
            return []
        legendary = any(str(p.get("rarity") or "") == "legendary"
                        for p in (idy.gacha.get("pulls") or []))
        achs = achievements.check_progress(
            idy, axis_values=current_axis_values(idy) or {},
            unlocked=gacha.earned_count(idy), legendary=legendary)
        if achs:
            _achievement_save(idy)
            print(f"[achievements] +{sum(a.tickets for a in achs)} билетов: "
                  f"{[a.id for a in achs]}")
            if notify:
                _achievement_notify(state, achs)
        return achs
    except Exception as e:
        print(f"[achievements] check failed: {type(e).__name__}: {e}")
        return []


@app.get("/api/gacha/achievements")
async def gacha_achievements():
    from services import achievements
    s = _get_state()
    idy = s.get("identity")
    if idy is None or s.get("character") is None:
        return {"error": "нет активного персонажа"}
    _achievements_check(s)
    return achievements.report(idy)


@app.get("/api/gestures")
async def api_gestures():
    s = _get_state()
    ch = s.get("character")
    return _gestures.catalog_payload(name=getattr(ch, "name", "") or "",
                                     gender=getattr(ch, "gender", "") or "female")


@app.get("/api/gacha")
async def gacha_state():
    from services import gacha
    s = _get_state()
    idy = s.get("identity")
    if idy is None or s.get("character") is None:
        return {"error": "нет активного персонажа"}
    allow_nsfw, cur_len = _gacha_env(s)

    def _do():
        if gacha.touch(idy):
            idy.save()
        return gacha.summary(idy, allow_nsfw=allow_nsfw, cur_len=cur_len)

    out = await asyncio.get_event_loop().run_in_executor(None, _do)
    if _achievements_check(s):
        out = gacha.summary(idy, allow_nsfw=allow_nsfw, cur_len=cur_len)
    from services import achievements as _ach
    out["achievements"] = _ach.counts(idy)
    return out


@app.post("/api/gacha/pull")
async def gacha_pull():
    from services import gacha
    s = _get_state()
    idy = s.get("identity")
    character = s.get("character")
    if idy is None or character is None:
        return {"error": "нет активного персонажа"}
    allow_nsfw, cur_len = _gacha_env(s)

    def _do():
        item = gacha.pull(idy, allow_nsfw=allow_nsfw, cur_len=cur_len)
        idy.save()
        return item, gacha.summary(idy, allow_nsfw=allow_nsfw, cur_len=cur_len)

    try:
        item, summ = await asyncio.get_event_loop().run_in_executor(None, _do)
    except gacha.NoTickets:
        return {"error": "билетов нет — новые приходят каждый день"}
    except gacha.PoolEmpty:
        return {"error": "открывать больше нечего — вся коллекция собрана"}
    except Exception as e:
        print(f"[gacha] pull failed: {type(e).__name__}: {e}")
        return {"error": "не удалось открыть билет"}
    out = gacha.describe_item(item)
    print(f"[gacha] pull: {out['tag']} ({out['rarity']}), tickets={summ['tickets']}, "
          f"pool={summ['pool']}/{summ['total']}")
    achs = _achievements_check(s, notify=False)
    if achs:
        summ = gacha.summary(idy, allow_nsfw=allow_nsfw, cur_len=cur_len)
    ev = {
        "kind": "gacha",
        "trigger": gacha.reaction_trigger(
            out, honorific=_effective_honorific(s),
            female=(gender_of(character) != "male"),
            angle=item.get("angle"), series=item.get("series", "")),
        "card": _achievement_cards(achs) or None, "late": False,
        "history_marker": gacha.history_marker(out),
    }
    asyncio.create_task(_interject_event(s, s.get("active_ws"), ev))
    return {"ok": True, "item": out, **summ}


@app.post("/api/gacha/sphere")
async def gacha_use_sphere(request: Request):
    from services import gacha
    s = _get_state()
    idy = s.get("identity")
    if idy is None or s.get("character") is None:
        return {"error": "нет активного персонажа"}
    body = await request.json()
    tag = str((body or {}).get("tag") or "")
    color = str((body or {}).get("color") or "")
    pattern = str((body or {}).get("pattern") or "")
    allow_nsfw, _ = _gacha_env(s)

    def _do():
        res = gacha.use_sphere(idy, tag, color, pattern=pattern, allow_nsfw=allow_nsfw)
        idy.save()
        return res

    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _do)
    except gacha.GachaError as e:
        return {"error": str(e)}
    except Exception as e:
        print(f"[gacha] sphere failed: {type(e).__name__}: {e}")
        return {"error": "не удалось открыть цвет"}
    print(f"[gacha] sphere: {res['color'] or res['pattern']} {res['tag']}, осталось {res['spheres']}")
    return {"ok": True, **res,
            "styling": (_wardrobe_overview(s) or {}).get("styling")}


def _card_description(character) -> str:
    for key in ("profile_description", "short_description"):
        v = (getattr(character, key, "") or "").strip()
        if v:
            return v
    return ""


@app.get("/api/character/info")
async def get_character_info():
    from persona.relationship_axes import current_axis_values
    s = _get_state()
    character = s.get("character")
    idy = s.get("identity")
    if character is None or idy is None:
        return {"error": "нет активного персонажа"}
    version = "1.0"
    instance = s.get("character_id") or ""
    archive = None
    try:
        store = s.get("store")
        archive = store.get_archive(instance) if store else None
        if archive is not None:
            m = archive.manifest or {}
            instance = m.get("instance_id") or instance
            version = str(m.get("character_version") or m.get("app_version_created")
                          or version)
    except Exception:
        pass
    training = None
    try:
        from persona.character_store import _training_row
        from persona.training import (REQUIRED_TRAINING, TrainingVersion, describe_gap,
                                      read_training)
        if archive is not None:
            _m = archive.manifest or {}
            training = _training_row(_m)
            training["required"] = str(TrainingVersion.parse(REQUIRED_TRAINING))
            training["required_label"] = TrainingVersion.parse(REQUIRED_TRAINING).label
            training["message"] = describe_gap(
                read_training(_m), char_name=getattr(character, "name", "") or "персонаж")["message"]
    except Exception as e:
        print(f"[training] карточка: {type(e).__name__}: {e}")
        training = None
    lore = _card_description(character)
    vals = current_axis_values(idy) or {}
    seen = getattr(idy, "ui_seen_relations", {}) or {}
    AXES = (("trust", "trust"), ("intimacy", "closeness"), ("respect", "respect"))
    relations = {}
    for ui_key, axis in AXES:
        new = float(vals.get(axis, 0.0) or 0.0)
        last = float(seen.get(axis, new))
        roman, word = _info_tier(ui_key, new)
        relations[ui_key] = {"lastProgress": round(last, 4),
                             "newProgress": round(new, 4),
                             "tier": roman, "label": word}
    ctx_fill = 0.0
    try:
        budget = float(getattr(s["config"].llm, "history_budget", 0) or 0)
        if budget > 0:
            used = float(s["history"].window_tokens() or 0)
            ctx_fill = max(0.0, min(1.0, used / budget))
    except Exception:
        pass
    st = _stats_touch(s) or {}
    fm_ts = float((getattr(idy, "event_log", {}) or {}).get("first_meeting", {})
                  .get("last_fired_at", 0.0) or 0.0)
    days = int((time.time() - fm_ts) // 86400) + 1 if fm_ts > 0 else 0
    stats = {
        "days": max(0, days),
        "first_meeting_at": fm_ts or None,
        "since": st.get("since"),
        "sessions": int(st.get("sessions", 0) or 0),
        "messages_user": int(st.get("messages_user", 0) or 0),
        "messages_assistant": int(st.get("messages_assistant", 0) or 0),
        "images": int(st.get("images", 0) or 0),
    }
    stats["messages"] = stats["messages_user"] + stats["messages_assistant"]
    _now = time.time()
    _today = time.strftime("%Y-%m-%d", time.localtime(_now))
    _yest = time.strftime("%Y-%m-%d", time.localtime(_now - 86400))
    _last_day = str(st.get("last_day") or "")
    _moods = st.get("moods") if isinstance(st.get("moods"), dict) else {}
    stats.update({
        "longest_messages": int(st.get("longest_messages", 0) or 0),
        "longest_minutes": int(round(float(st.get("longest_minutes", 0.0) or 0.0))),
        "talk_minutes": int(round(float(st.get("talk_minutes", 0.0) or 0.0))),
        "streak_days": (int(st.get("streak_days", 0) or 0)
                        if _last_day in (_today, _yest) else 0),
        "best_streak_days": int(st.get("best_streak_days", 0) or 0),
        "proactive_sent": int(st.get("proactive_sent", 0) or 0),
        "proactive_answered": int(st.get("proactive_answered", 0) or 0),
        "moods_top": [[k, int(v)] for k, v in
                      sorted(_moods.items(), key=lambda kv: (-int(kv[1] or 0), kv[0]))[:3]],
    })
    trust_idx = sum(1 for b in _INFO_TIER_BOUNDS
                    if float(vals.get("trust", 0.0) or 0.0) >= b)
    thoughts = _card_entries_section(trust_idx, _THOUGHTS_TIER_IDX,
                                     lambda: _card_thoughts(idy))
    diary = _card_entries_section(trust_idx, _DIARY_TIER_IDX,
                                  lambda: _card_diary(s.get("memory")))
    character_tab = {
        "unlocked": trust_idx >= _CHARACTER_TIER_IDX,
        "tier_required": ("I", "II", "III", "IV", "V")[_CHARACTER_TIER_IDX],
        "label_required": _INFO_TIER_WORDS["trust"][_CHARACTER_TIER_IDX],
        "axes": [], "traits": [],
    }
    if character_tab["unlocked"]:
        try:
            character_tab.update(_card_character(idy, character, s))
        except Exception as e:
            print(f"[card] character tab failed: {type(e).__name__}: {e}")
    return {
        "id": instance,
        "name": getattr(character, "name", "") or "",
        "version": version,
        "lore": lore,
        "relations": relations,
        "ctx_fill": round(ctx_fill, 3),
        "stats": stats,
        "thoughts": thoughts,
        "diary": diary,
        "character_tab": character_tab,
        "training": training,
    }


@app.post("/api/character/info/seen")
async def character_info_seen():
    from persona.relationship_axes import current_axis_values
    s = _get_state()
    idy = s.get("identity")
    if idy is None:
        return {"ok": False}
    vals = current_axis_values(idy) or {}
    idy.ui_seen_relations = {k: float(v) for k, v in vals.items()}
    try:
        idy.save()
    except Exception as e:
        print(f"[ui] seen-коммит не сохранился: {type(e).__name__}: {e}")
        return {"ok": False}
    return {"ok": True}


@app.post("/api/app/exit-cleanup")
async def app_exit_cleanup():
    import asyncio
    from drawing.storage import purge_session_images
    cfg = (_state.get("config") if _state else None) or _app_config
    if cfg is None:
        return {"removed": 0}
    try:
        n = await asyncio.get_event_loop().run_in_executor(
            None, lambda: purge_session_images(PROJECT_ROOT, cfg.image_gen))
    except Exception as e:
        print(f"[drawing] чистка на выходе не удалась: {type(e).__name__}: {e}")
        return {"removed": 0}
    if n:
        print(f"[drawing] выход: удалено сгенерированных кадров: {n}")
    return {"removed": n}


@app.get("/api/status")
async def get_app_status():
    from services.background.busy import app_status
    return app_status(_get_state())


@app.get("/api/identity")
async def get_identity():
    s = _get_state()
    identity = s["identity"]
    character = s["character"]
    if identity is None or character is None:
        return {"active": False}
    from persona.evolution import compute_relationship_tier
    from persona.vulnerability_catalog import (
        _eligible_for_check,
        _eligible_strengths_for_check,
        resolve_trait,
    )

    axes = {
        st.id[len("axis_"):]: st.axis_value
        for st in identity.self_statements
        if st.id.startswith("axis_")
    }

    from persona.relationship_axes import (
        RELATIONSHIP_AXES as _REL_AXES, current_axis_values as _rel_vals,
        select_relationship_axis_text as _rel_text)
    _rv = _rel_vals(identity)
    relationship_axes = {
        a: {"value": round(_rv.get(a, 0.0), 3),
            "text": _rel_text(character, a, _rv.get(a, 0.0))}
        for a in _REL_AXES if a in _rv
    }

    active_traits = []
    for at in identity.active_traits:
        trait = resolve_trait(at.trait_id, character)
        active_traits.append({
            "trait_id": at.trait_id,
            "text": trait.text if trait else "(unknown)",
            "kind": "strength" if (trait and hasattr(trait, "id") and trait.id.startswith("strength_")) else "vulnerability",
            "activated_at": at.activated_at,
            "source_event": at.source_event,
        })

    eligible_vulns_not_active = [
        {"id": v.id, "text": v.text}
        for v in _eligible_for_check(character, identity)
    ]
    eligible_strengths_not_active = [
        {"id": s.id, "text": s.text}
        for s in _eligible_strengths_for_check(character, identity)
    ]

    _mem = s.get("memory")
    _profile_summary = ""
    if _mem is not None:
        try:
            _profile_summary = (_mem.get_user_profile() or {}).get("summary", "") or ""
        except Exception:
            _profile_summary = ""

    return {
        "self_statements": [
            {"id": st.id, "section": st.section, "text": st.text, "source": st.source}
            for st in identity.self_statements
        ],
        "relationships": [
            {"id": st.id, "text": st.text, "source": st.source}
            for st in identity.relationship_statements
        ],
        "thoughts": [
            {"text": t.text, "kind": t.kind, "relevance": t.relevance}
            for t in identity.get_active_thoughts()
        ],
        "master_summary": _profile_summary or identity.master_summary,
        "relationship_axes": relationship_axes,
        "axes": axes,
        "tier": compute_relationship_tier(identity, character),
        "last_session": identity.last_session_summary,
        "last_mood": identity.last_session_mood,
        "mood_state": getattr(identity, "mood_state", "ровное"),
        "mood_intensity": getattr(identity, "mood_intensity", 0.0),
        "mood_updated_at": getattr(identity, "mood_updated_at", 0.0),
        "mood_effective": list(mood_mod.effective_mood(
            getattr(identity, "mood_state", "ровное"),
            float(getattr(identity, "mood_intensity", 0.0) or 0.0),
            float(getattr(identity, "mood_updated_at", 0.0) or 0.0),
            now=time.time(),
        )),
        "mood_live": mood_mod.current_mood(
            getattr(identity, "mood_state", "") or "",
            float(getattr(identity, "mood_intensity", 0.0) or 0.0))[0],
        "reaction_state": getattr(identity, "reaction_state", "") or "",
        "reaction_intensity": getattr(identity, "reaction_intensity", 0.0) or 0.0,
        "reaction_reason": getattr(identity, "reaction_reason", "") or "",
        "accumulated_importance": identity.accumulated_importance,
        "relationship_level": identity.relationship_level,
        "relationship_momentum": identity.relationship_momentum,
        "relationship_tier": s["persona"].tier,
        "axes": axes,
        "active_traits": active_traits,
        "eligible_vulns_not_active": eligible_vulns_not_active,
        "eligible_strengths_not_active": eligible_strengths_not_active,
    }


@app.post("/api/character/axis_goal")
async def set_character_axis_goal(payload: dict):
    from persona.axis_dynamics import set_axis_goal
    from persona.evolution import AXES_DETAILS, axis_goal_phrase
    s = _get_state()
    idy = s.get("identity")
    if idy is None:
        return {"error": "персонаж не выбран"}
    axis = str(payload.get("axis") or "").strip()
    if axis not in AXES_DETAILS:
        return {"error": f"нет такой оси: {axis}"}
    try:
        d = int(payload.get("dir", 0))
    except (TypeError, ValueError):
        return {"error": "dir должен быть -1, 0 или 1"}
    before = set(getattr(idy, "axis_goals", {}) or {})
    changed = set_axis_goal(idy, axis, d, source="ui")
    g = 1 if d > 0 else (-1 if d < 0 else 0)
    goals_now = {k: int(v.get("dir", 0) or 0) for k, v in (getattr(idy, "axis_goals", {}) or {}).items()}
    return {"axis": axis, "goal": g, "goal_label": axis_goal_phrase(axis, g) if g else "",
            "changed": changed, "goals": goals_now,
            "cleared": sorted(before - set(goals_now) - {axis})}


@app.post("/api/identity/debug-set")
async def debug_set_identity(payload: dict):
    s = _get_state()
    identity = s["identity"]
    response = {"applied": [], "skipped": []}

    axes_overrides = payload.get("axes") or {}
    if isinstance(axes_overrides, dict):
        for axis_name, val in axes_overrides.items():
            try:
                v = max(0.0, min(1.0, float(val)))
            except (TypeError, ValueError):
                response["skipped"].append(f"axes.{axis_name}: bad value {val!r}")
                continue
            found = False
            for st in identity.self_statements:
                if st.id == f"axis_{axis_name}":
                    st.axis_value = v
                    response["applied"].append(f"axes.{axis_name}={v}")
                    found = True
                    break
            if not found:
                response["skipped"].append(f"axes.{axis_name}: no such axis")

    add_traits = payload.get("activate_traits") or []
    if isinstance(add_traits, list):
        from persona.character import ActiveTrait
        import time as _time
        for entry in add_traits:
            if not isinstance(entry, dict) or not entry.get("trait_id"):
                response["skipped"].append(f"activate_traits: bad entry {entry!r}")
                continue
            identity.active_traits.append(ActiveTrait(
                trait_id=entry["trait_id"],
                activated_at=_time.time(),
                source_event=entry.get("source_event", "debug-set"),
            ))
            response["applied"].append(f"trait+{entry['trait_id']}")

    if axes_overrides or add_traits:
        from persona.vulnerability_catalog import cleanup_inactive_traits
        removed = cleanup_inactive_traits(s["character"], identity)
        if removed:
            response["cleanup_removed"] = removed

    return response


@app.post("/api/debug/regenerate-portraits")
async def debug_regenerate_portraits(payload: dict | None = None):
    import random as _r
    s = _get_state()
    try:
        from drawing.catalog import AssetCatalog
        fresh = AssetCatalog.load(PROJECT_ROOT, assets_root=ASSETS_ROOT)
        s["drawing_catalog"] = fresh
        pipe = s.get("drawing_pipeline")
        if pipe is not None:
            pipe.catalog = fresh
    except Exception as _e:
        print(f"[regen] catalog reload failed: {_e}")
    loop = asyncio.get_event_loop()
    outfit_id = (payload or {}).get("outfit_id")
    if outfit_id:
        s["runtime_portrait_outfit_id"] = outfit_id
        s.pop("snapshot_state", None)
    _seed_in = (payload or {}).get("seed")
    seed = int(_seed_in) if _seed_in is not None else _r.randint(0, 2 ** 63 - 1)
    await loop.run_in_executor(None, _llama_mgr.stop)
    try:
        await _regenerate_portrait(s, None, loop, seed=seed, manage_vram=False)
        await _generate_mood_portraits(s, None, loop, seed=seed, manage_vram=False)
    finally:
        await loop.run_in_executor(
            None, lambda: (_release_comfy(), _llama_mgr.start()))
    return {"ok": True, "outfit": s.get("runtime_portrait_outfit_id"), "seed": seed}


@app.get("/api/memory/records")
async def get_memory_records():
    s = _get_state()
    records = []
    for r in s["memory"].records:
        if not r.is_forgotten:
            records.append({
                "type": r.type,
                "title": r.title,
                "details": {k: v for k, v in r.details.items() if not k.startswith("_")},
                "importance": r.importance,
            })
    return {"records": records, "total": len(records)}




@app.get("/api/prompt")
async def get_prompt(q: str = "", simulate: bool = False, new_session: bool = False):
    s = _get_state()
    total_tools = len(s["memory"]._ensure_registry().all())

    want_simulation = simulate or bool(q) or new_session
    live_prompt = s.get("last_prompt")

    if not want_simulation and live_prompt:
        return {
            "prompt": live_prompt,
            "tokens_approx": len(live_prompt) // 3,
            "active_tools": s.get("last_active_tools", []),
            "total_tools": total_tools,
            "source": "last_dispatched",
            "query": s.get("last_query", ""),
        }

    query_text = q or ""
    query_embedding = None
    if query_text and s["client"].is_available():
        try:
            query_embedding = s["client"].embed(query_text)
        except Exception:
            query_embedding = None

    tools = s["memory"].get_tools(query=query_text, query_embedding=query_embedding)
    prompt = build_system_prompt(
        s["persona"],
        memory=s["memory"],
        query_text=query_text or "debug",
        tools=tools,
        query_embedding=query_embedding,
        is_new_session=new_session,
        drawing_boundaries=_get_drawing_boundaries(s),
        current_outfit_label=_get_current_outfit_label(s),
    )
    return {
        "prompt": prompt,
        "tokens_approx": len(prompt) // 3,
        "active_tools": [t["function"]["name"] for t in tools],
        "total_tools": total_tools,
        "source": "simulated",
        "query": query_text,
        "is_new_session": new_session,
    }


class _TurnGuard:
    def __init__(self, lifecycle: ModelLifecycle) -> None:
        self._lifecycle = lifecycle
        self._held = False

    def acquire(self) -> None:
        if not self._held:
            self._lifecycle.acquire()
            self._held = True

    def release(self) -> None:
        if self._held:
            self._lifecycle.release()
            self._held = False


async def _handle_command(ws: WebSocket, cmd: str, s: dict, raw_text: str = ""):
    try:
        if _IS_FROZEN and cmd not in _PROD_COMMANDS:
            await ws.send_json({"type": "system", "text": f"Неизвестная команда: {cmd}."})
            return

        if cmd in ("/end", "/sleep"):
            if len(s["history"].messages) < 4:
                await ws.send_json({"type": "system", "text": f"Недостаточно сообщений для завершения сессии ({len(s['history'].messages)}/4)"})
                return

            loop = asyncio.get_event_loop()
            await _finalize_session_sync(s, ws, loop, reason=f"команда {cmd}")
            return


        if cmd == "/reset":
            character_id = s["character_id"]
            store = s["store"]

            s["history"].clear()
            s["runtime_portrait_outfit_id"] = None
            try:
                store.reset_in_place(character_id)
            except Exception as e:
                await ws.send_json({
                    "type": "system",
                    "text": f"Не удалось сбросить: {type(e).__name__}: {e}",
                })
                return
            loaded = store.load(character_id)
            s["character"] = loaded["character"]
            s["identity"] = loaded["identity"]
            _state["identity"] = s["identity"]
            _refresh_persona(s)
            s["memory"] = UnifiedMemory(None, "", s["client"])
            s["memory"].weather_config = s["config"].weather
            s["memory"]._session_state_ref = s
            s["memory"].user_honorific = resolve_honorific(s["character"])
            s["memory"].load_records(loaded["memory_records"])
            if not s["memory"].records:
                s["memory"].bootstrap_from_character(s["character"])
            _state["memory"] = s["memory"]
            s["session_start_count"] = len(s["memory"].records)

            s["session_initiated_by"] = None
            s["proactive_session_started_at"] = 0.0
            s["last_reminder_delivered_at"] = 0.0
            s["last_user_message_at"] = 0.0
            await ws.send_json({"type": "system", "text": "Состояние сброшено."})

        elif cmd == "/memory":
            count = len([r for r in s["memory"].records if not r.is_forgotten])
            await ws.send_json({"type": "system", "text": f"Записей в памяти: {count}"})

        elif cmd == "/style":
            catalog = s.get("drawing_style_catalog")
            if catalog is None:
                await ws.send_json({
                    "type": "system",
                    "text": "Style catalog не инициализирован.",
                })
                return

            parts = raw_text.split(None, 1)
            if len(parts) < 2 or not parts[1].strip():
                active = s["config"].drawing.active_style_id
                listing = ", ".join(p.id for p in catalog.list_all())
                await ws.send_json({
                    "type": "system",
                    "text": (
                        f"Активный стиль: {active!r}\n"
                        f"Доступные: {listing}\n\n"
                        f"Использование:\n"
                        f"  /style <id>        — активировать встроенный стиль\n"
                        f"  /style <code>      — импортировать (artstyle:v1:...) + активировать\n"
                        f"  /style-reset       — вернуть default"
                    ),
                })
                return

            arg = parts[1].strip()

            if arg.startswith("artstyle:"):
                from drawing import StyleCodeError, StyleValidationError
                try:
                    pack = catalog.import_code(arg)
                except (StyleCodeError, StyleValidationError) as e:
                    await ws.send_json({
                        "type": "system",
                        "text": f"❌ Не удалось импортировать стиль: {type(e).__name__}: {e}",
                    })
                    return
                tag_preview = ", ".join(pack.tags) if pack.tags else "(пусто)"
                await ws.send_json({
                    "type": "system",
                    "text": (f"✓ Стиль импортирован: {pack.id} "
                              f"({pack.name})\nТеги: {tag_preview}"),
                })
                loop = asyncio.get_event_loop()
                await _apply_style_change(s, ws, loop, pack.id)
                return

            pack = catalog.get(arg)
            if pack is None:
                listing = ", ".join(p.id for p in catalog.list_all())
                await ws.send_json({
                    "type": "system",
                    "text": (f"❌ Стиль {arg!r} не найден.\n"
                              f"Доступные: {listing}"),
                })
                return
            tag_preview = ", ".join(pack.tags) if pack.tags else "(пусто)"
            await ws.send_json({
                "type": "system",
                "text": f"✓ Активирую стиль: {pack.id} ({pack.name})\nТеги: {tag_preview}",
            })
            loop = asyncio.get_event_loop()
            await _apply_style_change(s, ws, loop, pack.id)

        elif cmd == "/style-reset":
            await ws.send_json({
                "type": "system",
                "text": "✓ Сбрасываю стиль на default (без стилизации).",
            })
            loop = asyncio.get_event_loop()
            await _apply_style_change(s, ws, loop, "default")

        elif cmd == "/stats":
            chat_mode = getattr(s["client"], "reasoning_mode", "deep")
            post_mode = "fast" if s["client"].fast_post_session else "reasoning"
            _stats_text = (
                f"Персонаж: {s['character'].name}\n"
                f"Сообщений: {len(s['history'].messages)}\n"
                f"Записей: {len(s['memory'].records)}\n"
                f"Важность: {s['identity'].accumulated_importance:.1f}/3.0\n"
                f"Режим чата: {chat_mode}\n"
                f"Режим пост-сессии: {post_mode}"
            )
            if s.get("last_reflection_report"):
                _stats_text += f"\nПоследняя рефлексия: {s['last_reflection_report']}"
            await ws.send_json({"type": "system", "text": _stats_text})

        elif cmd == "/fast":
            tokens = raw_text.lower().split()
            arg = tokens[1] if len(tokens) >= 2 else None
            cur = getattr(s["client"], "reasoning_mode", "deep")
            if arg in ("deep", "auto", "fast"):
                new_mode = arg
            elif arg in ("on", "true", "1", "вкл"):
                new_mode = "fast"
            elif arg in ("off", "false", "0", "выкл"):
                new_mode = "deep"
            elif arg in (None, "toggle", "cycle"):
                new_mode = {"deep": "auto", "auto": "fast", "fast": "deep"}.get(cur, "deep")
            else:
                await ws.send_json({"type": "system", "text":
                    "Использование: /fast deep|auto|fast (без аргумента — цикл)"})
                return
            s["client"].reasoning_mode = new_mode
            s["config"].llm.reasoning_mode = new_mode
            await ws.send_json({"type": "system", "text": f"Режим рассуждений: {new_mode}"})

        elif cmd == "/fastpost":
            tokens = raw_text.lower().split()
            arg = tokens[1] if len(tokens) >= 2 else None
            if arg in ("on", "true", "1", "вкл"):
                s["client"].fast_post_session = True
            elif arg in ("off", "false", "0", "выкл"):
                s["client"].fast_post_session = False
            elif arg in (None, "toggle"):
                s["client"].fast_post_session = not s["client"].fast_post_session
            else:
                await ws.send_json({"type": "system", "text":
                    "Использование: /fastpost on|off (без аргумента — переключить)"})
                return
            state = "fast" if s["client"].fast_post_session else "reasoning"
            await ws.send_json({"type": "system", "text": f"Режим пост-сессии: {state}"})

        elif cmd == "/prepare":
            parts = raw_text.split()
            arg = parts[1].strip() if len(parts) > 1 else ""
            force = len(parts) > 2 and parts[2].strip().lower() == "force"
            catalog = s.get("drawing_catalog")
            wardrobe = _get_wardrobe(s)
            if not arg:
                ids = ", ".join(sorted(catalog.outfits)) if catalog else "—"
                await ws.send_json({"type": "system", "text":
                    "Использование: /prepare <outfit_id> [force]\n"
                    f"Костюмы в каталоге: {ids}\n"
                    "Готовый набор экспортируется в portraits/<outfit_id>/ "
                    "(13 портретов + avatar_chat.png, имена под .maid)."})
                return
            if catalog is None or arg not in catalog.outfits:
                await ws.send_json({"type": "system", "text":
                    f"❌ Костюм {arg!r} не найден в каталоге."})
                return
            if wardrobe is None:
                await ws.send_json({"type": "system", "text": "❌ Персонаж не загружен."})
                return
            who = busy_with(s)
            if who is not None:
                await ws.send_json({"type": "system", "text":
                    f"⏳ Сейчас идёт {who} — запусти /prepare чуть позже."})
                return
            if wardrobe.is_prepared(arg) and not force:
                note = await _export_outfit_set_with_avatar(
                    s, arg, asyncio.get_event_loop())
                await ws.send_json({"type": "system", "text":
                    f"✓ «{arg}» уже подготовлен — перегенерация не запускалась. "
                    f"{note}\nПерегенерить с нуля: /prepare {arg} force"})
                return
            if force:
                wardrobe.reset(arg)
            from services.wardrobe import required_steps as _req_steps
            await ws.send_json({"type": "system", "text":
                f"👗 Готовлю набор «{arg}» ({len(_req_steps())} портретов, ~по минуте). "
                f"Текущий наряд НЕ меняется; по завершении набор ляжет в "
                f"portraits/{arg}/ (имена под .maid)."})
            asyncio.create_task(_prepare_outfit_now(s, ws, asyncio.get_event_loop(), arg))

        elif cmd == "/mood":
            import time as _t
            parts = raw_text.split(maxsplit=1)
            arg = parts[1].strip() if len(parts) > 1 else ""
            palette = ", ".join(mood_mod.mood_ids())
            reactions = ", ".join(mood_mod.reaction_ids())
            if not arg:
                cur = s["identity"]
                cur_rx = getattr(cur, "reaction_state", "") or ""
                await ws.send_json({"type": "system", "text":
                    f"Текущее: {getattr(cur,'mood_state','ровное')} "
                    f"({getattr(cur,'mood_intensity',0.0):.2f})"
                    + (f" · вспышка: {cur_rx}" if cur_rx else "") + "\n"
                    f"Использование: /mood <состояние>[:сила] | /mood reset\n"
                    f"Настроения: {palette}\n"
                    f"Реакции (на один ход): {reactions}\n"
                    f"Пример: /mood обиженное:0.8"})
                return
            idn = s["identity"]
            if arg.lower() in ("reset", "ровное", mood_mod.NEUTRAL):
                state_name, intensity = mood_mod.NEUTRAL, 0.0
            else:
                raw_state, _, raw_int = arg.partition(":")
                state_name = raw_state.strip()
                if not mood_mod.is_valid(state_name):
                    await ws.send_json({"type": "system", "text":
                        f"❌ Неизвестное состояние {state_name!r}.\n"
                        f"Настроения: {palette}\nРеакции: {reactions}"})
                    return
                try:
                    intensity = float(raw_int.strip().replace(",", ".")) if raw_int.strip() else 0.7
                except ValueError:
                    intensity = 0.7
            st, inten, ts = mood_mod.apply_mood(state_name, intensity, now=_t.time())
            if mood_mod.is_reaction(st):
                idn.reaction_state, idn.reaction_intensity = st, inten
                idn.reaction_reason = ""
                await ws.send_json({"type": "system", "text":
                    f"⚡ Вспышка → {st} ({inten:.2f}) — на один ход"})
            else:
                idn.mood_state, idn.mood_intensity, idn.mood_updated_at = st, inten, ts
                if st == mood_mod.NEUTRAL:
                    idn.reaction_state, idn.reaction_intensity, idn.reaction_reason = "", 0.0, ""
                await ws.send_json({"type": "system", "text":
                    f"🎭 Настроение → {st}"
                    + (f" ({inten:.2f})" if st != mood_mod.NEUTRAL else " (нейтраль)")})

        elif cmd in ("/rating", "/nsfw"):
            from drawing.assets import RATING_ORDER
            drawing = s["config"].drawing
            parts = raw_text.split(None, 1)
            arg = parts[1].strip().lower() if len(parts) > 1 and parts[1].strip() else ""
            arg = {"on": "nsfw", "вкл": "nsfw", "off": "sfw", "выкл": "sfw"}.get(arg, arg)
            if not arg:
                await ws.send_json({"type": "system", "text":
                    f"Рейтинг контента (потолок): {drawing.max_rating!r}\n"
                    f"Уровни: {', '.join(RATING_ORDER)}  (sfw < suggestive < nsfw)\n\n"
                    f"  /rating nsfw        — включить взрослый контент\n"
                    f"  /rating sfw         — выключить (безопасный режим)\n"
                    f"  /rating suggestive  — намёки/чувственно, без явного\n"
                    f"  (также /rating on|off)\n"
                    f"Сбрасывается на sfw при рестарте сервера."})
                return
            if arg not in RATING_ORDER:
                await ws.send_json({"type": "system", "text":
                    f"❌ Неизвестный рейтинг {arg!r}. Уровни: "
                    f"{', '.join(RATING_ORDER)} (или on|off)."})
                return
            from services import addons as _addons
            ceiling = _addons.max_rating_ceiling(PROJECT_ROOT)
            if RATING_ORDER.get(arg, 0) > RATING_ORDER.get(ceiling, 0):
                await ws.send_json({"type": "system", "text":
                    f"🚫 Рейтинг {arg!r} недоступен (потолок «{ceiling}»). "
                    f"Включите NSFW-аддон в настройках, чтобы поднять выше."})
                return
            old = drawing.max_rating
            drawing.max_rating = arg
            note = {"sfw": "🔒 Взрослый контент выключен (безопасный режим).",
                    "nsfw": "🔞 Взрослый контент включён.",
                    "suggestive": "😏 Намёки/чувственно, без явного."}[arg]
            await ws.send_json({"type": "system", "text":
                f"Рейтинг контента: {old!r} → {arg!r}.\n{note}"})

        elif cmd == "/tickets":
            from services import gacha
            idy = s.get("identity")
            if idy is None or s.get("character") is None:
                await ws.send_json({"type": "system", "text": "Нет активного персонажа."})
                return
            parts = raw_text.split(maxsplit=1)
            arg = parts[1].strip() if len(parts) > 1 else ""
            changed = gacha.touch(idy)
            if arg:
                try:
                    n = int(arg.replace("+", ""))
                except ValueError:
                    await ws.send_json({"type": "system", "text":
                        "❌ /tickets [N] — начислить N билетов удачи (отрицательное — "
                        "списать); без аргумента — баланс"})
                    return
                if n >= 0:
                    gacha.grant(idy, n, "console")
                else:
                    idy.gacha["tickets"] = max(0, gacha.tickets(idy) + n)
                changed = True
            if changed:
                idy.save()
                await ws.send_json({"type": "gacha_changed"})
            allow_nsfw, cur_len = _gacha_env(s)
            summ = gacha.summary(idy, allow_nsfw=allow_nsfw, cur_len=cur_len)
            await ws.send_json({"type": "system", "text":
                f"🎟 Билеты удачи: {summ['tickets']} (ежедневные копятся до "
                f"{summ['cap']}). Открыто {summ['unlocked']} из {summ['total']}, "
                f"в пуле {summ['pool']}.\n"
                "/tickets N — начислить N (отрицательное — списать)"})

        elif cmd == "/spheres":
            from services import gacha
            idy = s.get("identity")
            if idy is None or s.get("character") is None:
                await ws.send_json({"type": "system", "text": "Нет активного персонажа."})
                return
            parts = raw_text.split(maxsplit=1)
            arg = parts[1].strip() if len(parts) > 1 else ""
            changed = gacha.touch(idy)
            if arg:
                try:
                    n = int(arg.replace("+", ""))
                except ValueError:
                    await ws.send_json({"type": "system", "text":
                        "❌ /spheres [N] — начислить N сфер изменения (отрицательное — "
                        "списать); без аргумента — баланс"})
                    return
                idy.gacha["spheres"] = max(0, gacha.spheres(idy) + n)
                changed = True
            if changed:
                idy.save()
                await ws.send_json({"type": "gacha_changed"})
            await ws.send_json({"type": "system", "text":
                f"🔮 Сфер изменения: {gacha.spheres(idy)} — открывают цвет или узор "
                "уже открытой вещи (гардероб → «Стайлинг», клик по вещи).\n"
                "/spheres N — начислить N (отрицательное — списать)"})

        elif cmd == "/tier":
            from persona.relationship_axes import (
                CLOSENESS_STAGES, PRIMARY_TIER_AXIS, REL_AXIS_PREFIX,
                current_axis_values, select_relationship_axis_text)
            idy = s["identity"]
            parts = raw_text.split(maxsplit=1)
            arg = parts[1].strip().lower() if len(parts) > 1 else ""
            if not arg:
                cur = current_axis_values(idy).get(PRIMARY_TIER_AXIS)
                cur_txt = f"{cur:.2f}" if cur is not None else "—"
                await ws.send_json({"type": "system", "text":
                    f"Близость: {cur_txt} → ступень {s['persona'].tier!r}\n"
                    f"  /tier <{' | '.join(CLOSENESS_STAGES)}>  или  /tier <0..1>"})
                return
            mid = {"estranged": 0.05, "distant": 0.2, "warming": 0.45,
                   "close": 0.775, "intimate": 0.97}
            if arg in mid:
                lvl = mid[arg]
            else:
                try:
                    lvl = max(0.0, min(1.0, float(arg.replace(",", "."))))
                except ValueError:
                    await ws.send_json({"type": "system", "text":
                        f"❌ /tier <{' | '.join(CLOSENESS_STAGES)}> или число 0..1"})
                    return
            _st = next((t for t in idy.relationship_statements
                        if t.id == f"{REL_AXIS_PREFIX}{PRIMARY_TIER_AXIS}"), None)
            if _st is not None:
                _st.axis_value = lvl
                _st.axis_momentum = 0.0
                _st.text = select_relationship_axis_text(
                    s["character"], PRIMARY_TIER_AXIS, lvl, fallback=_st.text)
            idy.relationship_level = lvl
            await ws.send_json({"type": "system", "text":
                f"Близость → {lvl:.2f} (ступень {s['persona'].tier!r})"})

        elif cmd == "/grammar":
            sess = s["config"].session
            parts = raw_text.split(None, 1)
            arg = parts[1].strip().lower() if len(parts) > 1 else ""
            if arg in ("on", "вкл", "1"):
                sess.grammar_polish = True
            elif arg in ("off", "выкл", "0"):
                sess.grammar_polish = False
            elif arg:
                await ws.send_json({"type": "system", "text":
                    "Использование: /grammar [on|off]"})
                return
            await ws.send_json({"type": "system", "text":
                f"🔤 Грамма-пост-раунд: {'ВКЛ' if sess.grammar_polish else 'выкл'}"})

        elif cmd == "/reflect":
            msgs = s["history"].get_messages()
            if len(msgs) < 2:
                await ws.send_json({"type": "system", "text":
                    "Недостаточно сообщений для рефлексии (нужно ≥2). Сначала поговори."})
                return
            if s.get("reflection_running"):
                await ws.send_json({"type": "system", "text":
                    "Рефлексия уже идёт — подожди завершения."})
                return
            await ws.send_json({"type": "system", "text":
                f"🧠 Рефлексия по {len(msgs)} сообщениям ({len(STEP_NAMES)} шагов). "
                f"Прогресс — в консоли сервера, это надолго…"})
            loop = asyncio.get_event_loop()
            item = ReflectionItem.new(s["character_id"], msgs, reason="команда /reflect")
            s["reflection_running"] = True
            _t_refl = time.time()
            try:
                _timings = await _run_reflection(s, item, _reflection_queue,
                                                 _project_root, loop)
            except CancelledByActivity:
                await ws.send_json({"type": "system", "text":
                    "⏸ Рефлексия прервана активностью (пришло новое сообщение во время прогона)."})
                return
            except Exception as e:
                await ws.send_json({"type": "system", "text":
                    f"❌ Рефлексия упала: {type(e).__name__}: {e}"})
                return
            finally:
                s["reflection_running"] = False
            from api.session_manager import format_step_timings
            _summary = format_step_timings(_timings or [])
            _total_line = f"{time.time() - _t_refl:.0f}s всего"
            if _summary:
                s["last_reflection_report"] = (
                    f"{s['character_id']}, {_total_line}: {_summary}")
            await ws.send_json({"type": "system", "text":
                "✅ Рефлексия завершена. identity и память обновлены и сохранены. "
                + (f"\n⏱ {_total_line} — {_summary}" if _summary else "")
                + "\nСмотри: /state · /records · /loops · /prefs."})

        elif cmd == "/proactive":
            if s["history"].messages:
                await ws.send_json({"type": "system", "text":
                    "🕊 Момент решения работает только при ПУСТОЙ истории (нет "
                    "активной сессии) — сначала /reset или /end."})
                return
            if _reflection_pending_for(s):
                await ws.send_json({"type": "system", "text":
                    "🧠 Прошлая сессия ещё не отрефлексирована — решению не на "
                    "чем стоять (свежие записи появляются после рефлексии). "
                    "Прогони /reflect или дождись фонового воркера."})
                return
            await ws.send_json({"type": "system", "text":
                "🕊 Форсирую момент решения — модель решает сама (может и SKIP)…"})
            delivered = await _dispatch_proactive_decision(
                s, ws, asyncio.get_event_loop())
            if not delivered:
                await ws.send_json({"type": "system", "text":
                    "🕊 Решила не писать (SKIP) — или доставка сорвалась, "
                    "детали в консоли сервера."})

        elif cmd == "/scenario":
            from persona import scenarios as _scn
            _parts = (raw_text or cmd).split()
            _arg = _parts[1].strip() if len(_parts) > 1 else ""
            _cat = _get_scenario_catalog(s)
            if not _arg:
                _ctx = _build_scenario_context(s)
                _rec = s.get("scenario")
                _active = (f"«{_rec['title']}» ({_rec['id']}, уровень {_rec['level']}, "
                           f"ход {_rec['turn']}, источник {_rec['source']})"
                           if _rec else "нет")
                _elig = [f"{e.id} [{e.surface}/{e.level}]"
                         for e in _cat if _scn.eligible(e, _ctx)]
                await ws.send_json({"type": "system", "text":
                    f"🎬 Активный сценарий: {_active}\n"
                    f"Eligible сейчас ({_ctx.tier}, {_ctx.time_of_day}, пауза "
                    f"{int(_ctx.idle_gap_sec // 3600)} ч): " + (", ".join(_elig) or "—")
                    + f"\nКостюмы для открытия: {_ctx.outfits or '—'}\n"
                    f"В каталоге {len(_cat)}. /scenario <id> — форсировать, "
                    f"/scenario end — завершить."})
                return
            if _arg == "end":
                _rec = _scenario_close(s, reason="debug")
                await ws.send_json({"type": "system", "text":
                    (f"🎬 Сценарий «{_rec['title']}» завершён." if _rec
                     else "🎬 Активного сценария нет.")})
                return
            _sc = next((e for e in _cat if e.id == _arg), None)
            if _sc is None:
                await ws.send_json({"type": "system", "text":
                    f"🎬 Сценарий {_arg!r} не найден в каталоге."})
                return
            if s.get("scenario"):
                _scenario_close(s, reason="replaced")
            if _sc.initiate or _sc.surface == "proactive":
                await ws.send_json({"type": "system", "text":
                    f"🎬 Форсирую «{_sc.display_title}»: персонаж пишет первым…"})
                delivered = await _dispatch_proactive_scenario(
                    s, ws, asyncio.get_event_loop(), _sc, force=True)
                if not delivered:
                    await ws.send_json({"type": "system", "text":
                        "🎬 Не стартовал: SKIP или сбой генерации (детали в консоли)."})
            else:
                _scenario_begin(s, _sc, turn=0, source="debug")
                s["pending_scenario_marker"] = _sc
                if _sc.outfit:
                    await _scenario_apply_outfit(s, ws, asyncio.get_event_loop(), _sc,
                                                 reveal_now=True)
                await _scenario_notify(s, ws, _sc,
                    f"🎬 Сценарий «{_sc.display_title}» — вступит со следующего хода.")

        elif cmd == "/reembed":
            mem = s["memory"]
            await ws.send_json({"type": "system", "text":
                f"♻️ Переэмбеддинг {len(mem.records)} записей текущим эмбеддером…"})
            try:
                n = await asyncio.to_thread(mem.reembed_all)
            except Exception as e:
                await ws.send_json({"type": "system", "text":
                    f"❌ Переэмбеддинг упал: {type(e).__name__}: {e}"})
                return
            _save_memory()
            await ws.send_json({"type": "system", "text":
                f"✅ Переэмбеддил {n}/{len(mem.records)} записей, сохранено."})

        elif cmd == "/draw":
            if not drawing_available(s):
                await ws.send_json({"type": "system", "text":
                    "🚫 Рисование недоступно: модуль генерации не установлен или "
                    "не запущен (см. Настройки → Рисование)."})
                return
            parts = raw_text.split(maxsplit=1)
            intent = parts[1].strip() if len(parts) > 1 else ""
            if not intent:
                await ws.send_json({"type": "system", "text":
                    "Использование: /draw <что нарисовать>\n"
                    "Пример: /draw сидит у окна с чашкой чая, мягкий свет"})
                return
            from drawing.assets import RATING_ORDER as _RO
            nsfw = _RO.get(s["config"].drawing.max_rating, 0) >= _RO["nsfw"]
            await ws.send_json({"type": "system", "text":
                f"🎨 Генерирую: {intent!r}" + (" (nsfw)" if nsfw else "")
                + ". Модель уйдёт из VRAM на время рендера — подожди."})
            s["memory"].pending_actions.append({
                "kind": "image", "intent": intent, "nsfw": nsfw,
            })
            loop = asyncio.get_event_loop()
            await _process_pending_actions(s, ws, loop)

        elif cmd == "/portrait":
            if not drawing_available(s):
                await ws.send_json({"type": "system", "text":
                    "🚫 Рисование недоступно: модуль генерации не установлен или "
                    "не запущен (см. Настройки → Рисование)."})
                return
            import random as _random
            _seed = _random.randint(0, 2 ** 63 - 1)
            mood_on = s["config"].drawing.mood_portraits_enabled
            await ws.send_json({"type": "system", "text":
                "🎨 Перерисовываю портрет" + (" (+ mood-набор)" if mood_on else "")
                + ". Модель уйдёт из VRAM на время рендера — подожди."})
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _llama_mgr.stop)
            try:
                await _regenerate_portrait(s, ws, loop, seed=_seed, manage_vram=False)
                if mood_on:
                    await _generate_mood_portraits(s, ws, loop, seed=_seed, manage_vram=False)
            finally:
                await loop.run_in_executor(
                    None, lambda: (_release_comfy(), _llama_mgr.start()))

        elif cmd == "/memdump":
            if s.get("character") is None:
                await ws.send_json({"type": "system", "text":
                    "Нет активного персонажа — нечего выгружать."})
                return
            from datetime import datetime
            now = datetime.now()
            dump_dir = PROJECT_ROOT / "logs"
            dump_dir.mkdir(parents=True, exist_ok=True)
            path = dump_dir / (f"memory_{s['character_id']}_"
                               f"{now.strftime('%Y%m%d-%H%M%S')}.txt")
            char_name = getattr(s["character"], "name", "") or s["character_id"]
            header = (f"Дамп памяти MaidLink\n"
                      f"Персонаж: {char_name} ({s['character_id']})\n"
                      f"Создан: {now.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            path.write_text(header + s["memory"].dump_readable(),
                            encoding="utf-8")
            n_alive = sum(1 for r in s["memory"].records if not r.is_forgotten)
            await ws.send_json({"type": "system", "text":
                f"📄 Память выгружена ({n_alive} записей): {path}\n"
                f"⚠️ Файл содержит личные записи открытым текстом — "
                f"удалите его после отправки."})

        elif cmd == "/help":
            await ws.send_json({"type": "system", "text":
                "Команды:\n"
                "/end — завершить сессию (пост-обработка)\n"
                "/reset — сбросить всё состояние\n"
                "/rating [sfw|suggestive|nsfw|on|off] — потолок контента (NSFW-галка)\n"
                "/tier [distant|warming|close|intimate|0..1] — уровень отношений (debug)\n"
                "/style <id|code> — стиль рисования; /style-reset — сброс\n"
                "/mood <состояние>[:сила] — выставить настроение (debug); /mood reset\n"
                "/draw <промпт> — принудительно нарисовать картинку (debug)\n"
                "/portrait — перерисовать портрет дашборда (новая вариация)\n"
                "/reflect — прогнать рефлексию по текущей сессии сейчас (debug)\n"
                "/proactive — форсить момент проактивного решения (debug; нужна пустая история)\n"
                "/scenario [id|end] — сценарии: активный и eligible / форсировать / завершить (debug)\n"
                "/grammar [on|off] — грамматический пост-раунд (debug A/B)\n"
                "/memory — количество записей\n"
                "/memdump — выгрузить память в файл (logs/)\n"
                "/tickets [N] — билеты удачи: баланс / начислить N (debug)\n"
                "/spheres [N] — сферы изменения: баланс / начислить N (debug)\n"
                "/stats — статистика\n"
                "/fast [on|off] — режим основного чата (reasoning ⇄ fast)\n"
                "/fastpost [on|off] — режим пост-сессионной обработки\n"
                "/help — эта справка\n"
                "Фронт-команды (в консоль): /state · /records · /prompt · /loops · /prefs · /persona · /axis"
            })

        else:
            await ws.send_json({"type": "system", "text":
                f"Неизвестная команда: {cmd}. Введите /help"})

    except Exception as e:
        await ws.send_json({"type": "system", "text": f"Ошибка: {str(e)}"})


@app.websocket("/api/chat")
async def websocket_chat(ws: WebSocket):
    await ws.accept()
    s = _get_state()

    s["active_ws"] = ws

    async def _status_watcher():
        from services.background.busy import app_status
        last = None
        try:
            while True:
                st = app_status(s)
                code = st.get("code", "idle")
                if code in ("idle", "chat"):
                    code, text = "", ""
                else:
                    from services.background.busy import status_text as _stx
                    text = _stx(st)
                if (code, text) != last:
                    last = (code, text)
                    try:
                        await ws.send_json({"type": "app_status",
                                            "code": code, "text": text})
                    except Exception:
                        return
                await asyncio.sleep(1.5)
        except asyncio.CancelledError:
            pass
    _status_task = asyncio.create_task(_status_watcher())

    pending = s.get("pending_session_events", [])
    s["pending_session_events"] = []
    for evt in pending:
        try:
            await ws.send_json(evt)
        except Exception:
            break

    loop_ref = asyncio.get_event_loop()
    def _on_lifecycle_state(state: ModelState):
        try:
            asyncio.run_coroutine_threadsafe(
                ws.send_json({
                    "type": "model_state",
                    "state": state.value,
                }),
                loop_ref,
            )
        except Exception:
            pass

    lifecycle = get_lifecycle()
    unsub = lifecycle.add_listener(_on_lifecycle_state)
    try:
        await ws.send_json({"type": "model_state", "state": lifecycle.state.value})
    except Exception:
        pass

    from services.background.persona_status import persona_status, Claim
    def _on_persona_status(claim):
        try:
            asyncio.run_coroutine_threadsafe(
                ws.send_json({
                    "type": "persona_status",
                    "state": claim.label if claim else None,
                    "reason": claim.reason if claim else "",
                }),
                loop_ref,
            )
        except Exception:
            pass

    unsub_persona = persona_status.add_listener(_on_persona_status)
    try:
        current_claim = persona_status.get_current()
        await ws.send_json({
            "type": "persona_status",
            "state": current_claim.label if current_claim else None,
            "reason": current_claim.reason if current_claim else "",
        })
    except Exception:
        pass

    turn = _TurnGuard(lifecycle)

    try:
        try:
            await _maybe_initiate(s, ws)
        except Exception as _ie:
            print(f"[event] initiate hook error: {type(_ie).__name__}: {_ie}")

        asyncio.create_task(_maybe_morning_brief(s, ws))

        asyncio.create_task(_drain_interjections(s, ws))

        while True:
            _q = s.get("queued_ws_messages") or []
            if not _q:
                s["chat_turn_active"] = False
            data = _q.pop(0) if _q else await ws.receive_json()

            msg_type = data.get("type")

            if msg_type == "keystroke":
                lifecycle.preload()
                continue

            if msg_type == "typing":
                continue

            if msg_type == "acknowledge_reminder":
                await _ack_reminder(s, ws, data.get("record_id", ""))
                continue

            if msg_type != "message":
                continue

            user_text = data.get("text", "").strip()
            image_base64 = data.get("image")
            if not user_text and not image_base64:
                continue

            if s.get("character") is None:
                try:
                    await ws.send_json({"type": "system", "text": (
                        "Сначала выбери персонажа — нажми на чип внизу, "
                        "чтобы открыть окно выбора.")})
                except Exception:
                    pass
                continue

            user_text, image_base64 = await _collect_burst(
                s, ws, user_text, image_base64, lifecycle)

            s["client"].reasoning_mode = s["config"].llm.reasoning_mode

            s["turn_busy"] = True

            if len(s["history"].messages) == 0 and s.get("character") is not None:
                from services import assistant_brief as _ab_offer
                s["brief_offer_active"] = _ab_offer.should_offer(s)
                if s["brief_offer_active"]:
                    s["brief_offer_first"] = _ab_offer.is_first_meeting(s["identity"])
                    _ab_offer.set_brief(
                        s["identity"],
                        offered_at=_ab_offer.offered_at_for(s["identity"]))
                    print(f"[brief] {s.get('character_id','?')}: активирован "
                          f"хинт-предложение сводки"
                          f"{' (первое знакомство)' if s['brief_offer_first'] else ''}")

            s["last_user_message_at"] = time.time()
            if s.get("session_initiated_by") != "user":
                prev = s.get("session_initiated_by")
                s["session_initiated_by"] = "user"
                s["proactive_session_started_at"] = 0.0
                if prev == "proactive":
                    _stats_bump(s, "proactive_answered")
                    print(f"[chat] proactive session перехвачена юзером — переключаю на user-rules")
                    _reset_proactive_ignore(s)

            await lifecycle.ensure_loaded()

            turn.acquire()

            if s.get("session_processing"):
                await ws.send_json({
                    "type": "system",
                    "text": "⌛ Закрываю предыдущую сессию...",
                })
                try:
                    await asyncio.wait_for(
                        s["session_processing_done"].wait(),
                        timeout=25,
                    )
                except asyncio.TimeoutError:
                    await ws.send_json({
                        "type": "error",
                        "text": "Не удалось закрыть прошлую сессию вовремя — попробуй ещё раз",
                    })
                    turn.release()
                    await _turn_idle(s, ws)
                    continue

            if user_text and user_text.startswith("/"):
                cmd = user_text.lower().split()[0]
                try:
                    await _handle_command(ws, cmd, s, raw_text=user_text)
                finally:
                    turn.release()
                try:
                    await ws.send_json({"type": "done"})
                except Exception:
                    pass
                await _turn_idle(s, ws)
                continue

            import time as _tt_mod
            s["turn_timings"] = {"t0": _tt_mod.monotonic()}
            s["chat_turn_active"] = True
            query_embedding = s["client"].embed(user_text or "изображение")
            is_new = len(s["history"].messages) == 0
            draw_requested = (drawing_available(s)
                              and _draw_recently_requested(s["history"], user_text))
            tools = s["memory"].get_tools(
                query=user_text or "",
                query_embedding=query_embedding,
            )
            if not drawing_available(s):
                tools = [t for t in tools if t.get("function", {}).get("name")
                         not in ("draw", "change_outfit")]

            if is_new:
                import time as _t
                _idy = s["identity"]
                _now = _t.time()
                _ds, _di = mood_mod.effective_mood(
                    getattr(_idy, "mood_state", "") or mood_mod.NEUTRAL,
                    float(getattr(_idy, "mood_intensity", 0.0) or 0.0),
                    float(getattr(_idy, "mood_updated_at", 0.0) or 0.0),
                    _now,
                )
                _idy.mood_state, _idy.mood_intensity, _idy.mood_updated_at = _ds, _di, _now
                _idy.mood_fading = False
                _idy.reaction_state, _idy.reaction_intensity, _idy.reaction_reason = "", 0.0, ""
                if _ds != mood_mod.NEUTRAL:
                    print(f"[mood] {s.get('character_id','?')}: {_ds} ({_di:.2f}) "
                          f"[межсессионный спад]")

            _idy = s["identity"]
            _idy.reaction_state = ""
            _idy.reaction_intensity = 0.0
            _idy.reaction_reason = ""
            _idy.mood_shift_from = ""

            _mood_t0 = _tt_mod.monotonic()
            _appraised = await asyncio.to_thread(
                mood_appraisal.appraise,
                s["client"], s["character"], s["identity"], user_text or "",
                history=s["history"].get_messages(),
                scenario_note="\n".join(
                    x for x in (_scenario_appraisal_note(s),
                                _aftereffect_appraisal_note(s)) if x),
                extra_cues=_quirks_mood_cues(s),
            )
            _mood_el = _tt_mod.monotonic() - _mood_t0
            if _mood_el >= 0.05 and "turn_timings" in s:
                s["turn_timings"]["mood"] = _mood_el
            if _appraised is not None:
                _kind, _ms, _mi, _mt, _mr = _appraised
                _floor = _aftereffect_mood_floor(s)
                if not _aftereffects.allows_mood(_floor, _ms):
                    print(f"[aftereffect] {s.get('character_id','?')}: вердикт "
                          f"{_ms!r} отброшен полом {_floor!r}")
                    _appraised = None
            if _appraised is not None and _kind == "reaction":
                _idy.reaction_state = _ms
                _idy.reaction_intensity = _mi
                _idy.reaction_reason = _mr or ""
                print(f"[mood] {s.get('character_id','?')}: {_ms} ({_mi:.2f})"
                      f"{f' — {_mr}' if _mr else ''} [реакция, 1 ход]")
            else:
                _verdict = (_ms, _mi, _mr) if _appraised is not None else None
                _fading = bool(getattr(_idy, "mood_fading", False))
                if _verdict is not None or _fading:
                    _prev_bg = (_idy.mood_state or "").strip()
                    _ms, _mi, _mr, _idy.mood_fading = mood_mod.settle(
                        _idy.mood_state, _idy.mood_intensity, _idy.mood_reason,
                        _verdict, _fading)
                    _idy.mood_state = _ms
                    _idy.mood_intensity = _mi
                    _idy.mood_updated_at = _mt if _appraised is not None else time.time()
                    _idy.mood_reason = _mr
                    if _ms != _prev_bg:
                        s["pending_mood_marker"] = (_prev_bg, _ms)
                        _idy.mood_shift_from = _prev_bg or mood_mod.NEUTRAL
                    print(f"[mood] {s.get('character_id','?')}: {_ms} ({_mi:.2f})"
                          f"{f' — {_mr}' if _mr else ''}"
                          f"{' [отходит]' if _idy.mood_fading else ''} [appraisal]")

            from drawing.assets import RATING_ORDER as _RO, tier_ge as _tier_ge
            from drawing import intent_router as _ir
            if (user_text
                    and drawing_available(s)
                    and s["client"].backend.nsfw_needs_deflection
                    and _RO.get(s["config"].drawing.max_rating, 0) >= _RO["nsfw"]
                    and _tier_ge(getattr(s["persona"], "tier", "distant"), "intimate")):
                _loop = asyncio.get_event_loop()

                def _router_chat(system: str, user: str) -> str:
                    return s["client"].chat(
                        messages=[{"role": "user", "content": user}],
                        system=system, thinking=False, label="draw_router")

                _routed = await _loop.run_in_executor(
                    None,
                    lambda: _ir.classify_draw_request(
                        user_text, _router_chat, nsfw_enabled=True, prefilter=False),
                )
                if _routed and _routed["is_image"] and _routed["is_nsfw"]:
                    s["history"].add("user", user_text)
                    _flush_mood_marker(s)
                    _ack = await _loop.run_in_executor(
                        None, lambda: _generate_nsfw_ack(s, _routed["intent"]))
                    if _ack:
                        await ws.send_json({"type": "response", "text": _ack,
                                            "id_mood": _reply_mood_id(s)})
                        await _send_reply_stats(s, ws, s["client"].last_stats)
                    s["memory"].pending_actions.append({
                        "kind": "image", "intent": _routed["intent"], "nsfw": True,
                    })
                    try:
                        await _process_pending_actions(s, ws, _loop)
                    finally:
                        turn.release()
                    try:
                        await ws.send_json({"type": "done"})
                    except Exception:
                        pass
                    await _turn_idle(s, ws)
                    continue

            if is_new and not s.get("scenario"):
                _entry_ev = _peek_entry_scenario(s)
                if _entry_ev:
                    _stage_scenario_mark(s, _entry_ev.id)
                    _scenario_begin(s, _entry_ev, turn=0, source="entry")
                    s["pending_scenario_marker"] = _entry_ev
                    if _entry_ev.outfit:
                        await _scenario_apply_outfit(
                            s, ws, asyncio.get_event_loop(), _entry_ev, reveal_now=False)
                    await _scenario_notify(s, ws, _entry_ev)
                    print(f"[scenario] {s.get('character_id','?')}: entry "
                          f"{_entry_ev.id!r} (отметка — при финализации)")
            _scenario_note = _scenario_block(s, advance=True)
            _aftereffect_note = _aftereffect_block(s, advance=True)
            if not _scenario_model_may_end(s):
                tools = [t for t in tools
                         if t.get("function", {}).get("name") != "scenario_end"]

            _recalled, _absent = None, None
            if user_text and s.get("memory") is not None and s["memory"].records:
                from memory import retrieval as _rt
                _recall_t0 = _tt_mod.monotonic()

                def _retr_chat(_system: str, _user: str) -> str:
                    return s["client"].chat(
                        messages=[{"role": "user", "content": _user}],
                        system=_system, thinking=False, label="retrieval")
                from persona.mood_appraisal import format_context_window as _fcw
                _retr_ctx = _fcw(s["history"].get_messages(),
                                 getattr(s.get("character"), "name", "") or "")
                try:
                    _plan = await asyncio.to_thread(
                        _rt.plan_retrieval, user_text, s["memory"], _retr_chat,
                        _retr_ctx)
                    if _plan is not None:
                        _recalled, _absent = _rt.execute_retrieval(
                            _plan, s["memory"], user_text=user_text)
                        print(f"[retrieval] {s.get('character_id','?')}: "
                              f"recall={[r.title for r in _recalled]} absent={_absent}")
                except Exception as _re:
                    print(f"[retrieval] error: {type(_re).__name__}: {_re}")
                if "turn_timings" in s:
                    s["turn_timings"]["recall"] = (_tt_mod.monotonic()
                                                   - _recall_t0)

            _doc_blocks = None
            _att = s.get("document")
            if _att is not None:
                from services.documents import (document_block, excerpts_block,
                                                search_chunks)
                _doc_blocks = [document_block(_att)]
                if _att.mode == "rag":
                    _exc = search_chunks(_att, query=user_text or "",
                                         query_embedding=query_embedding)
                    _eb = excerpts_block(_exc)
                    if _eb:
                        _doc_blocks.append(_eb)

            from services import assistant_brief as _ab
            _extra_hints: list[str] = []
            if s.get("brief_offer_active"):
                _tpl = (_ab.OFFER_HINT_FIRST if s.get("brief_offer_first")
                        else _ab.OFFER_HINT)
                _extra_hints.append(_tpl.format(honorific=_effective_honorific(s)))
            elif (_ab.ENABLED and s.get("identity") is not None
                    and _ab.brief_state(s["identity"])["enabled"]):
                _extra_hints.append(
                    "Утренняя сводка дня уже ВКЛЮЧЕНА (Господин подписан) — "
                    "не предлагай её и не спрашивай разрешения повторно; "
                    "доставляется она автоматически. Менять состав или "
                    "отключать — configure_brief, только по его просьбе.")

            _body_block = _body_block_for_turn(s, user_text)
            if _body_block:
                _quirks_raise(s, "explicit_talk")
                try:
                    from services import gestures as _gst
                    if _gst.find(user_text or ""):
                        _quirks_raise(s, "gesture_in_explicit")
                except Exception as _e:
                    print(f"[quirks] жест: {type(_e).__name__}: {_e}")

            _gs = _gestures.find(user_text) if user_text else []
            if _gs:
                _extra_hints.append(_gestures.turn_hint(_gs))

            _lore_index, _lore_blocks = "", []
            if user_text:
                from persona import lore as _lore
                try:
                    _lore_index, _lore_blocks = _lore.lore_for_turn(
                        s, user_text, query_embedding)
                except Exception as e:
                    print(f"[lore] пропуск хода: {type(e).__name__}: {e}")

            if (user_text and s.get("identity") is not None
                    and not s.get("image_source_hint_shown")):
                from services.image_sources import (looks_like_image_request,
                                                    resolve_site)
                if (looks_like_image_request(user_text)
                        and not resolve_site(s["identity"], user_text)):
                    s["image_source_hint_shown"] = True
                    _extra_hints.append(
                        "Господин просит картинки, но откуда их брать по такой "
                        "теме он не говорил. Аниме-арты умеешь и так — "
                        "search_anime_art (danbooru, поиск по тегам), источник "
                        "не нужен. Для прочего, если уместно — спроси, есть ли "
                        "у него любимый сайт (запомнишь через "
                        "set_image_source); настаивать не нужно, можешь и "
                        "просто поискать в общем вебе.")

            if (s.get("last_shown_image_tags") or {}).get("tags"):
                _cg_hint = gender_of(s.get("character"))
                _extra_hints.append(
                    f"В этой сессии ты "
                    f"{gpick(_cg_hint, 'показывала', 'показывал')} Господину "
                    "картинку из "
                    "интернета. Если он просит нарисовать ТЕБЯ похоже («в "
                    "такой же позе», «повтори как на картинке», «сделай так "
                    "же») — это выполнимо, не отказывайся: вызывай draw с "
                    "коротким intent-ссылкой, например intent=\"в такой же "
                    f"позе, как на картинке, которую я "
                    f"{gpick(_cg_hint, 'показала', 'показал')}\" (+ пожелания "
                    "Господина). Пересказывать картинку подробно НЕ нужно — "
                    "её теги система подставит референсом сама.")

            try:
                from llm.backends import (length_creep_nudge as _lcn,
                                          style_wants_verbose as _swv_hint)
                _creep = _lcn(s["history"].get_messages(),
                              _swv_hint(getattr(s["character"],
                                                "response_style", "")))
                if _creep:
                    _extra_hints.append(_creep)
                    print(f"[length] {s.get('character_id','?')}: ответы "
                          f"разрослись — нудж в промпт")
            except Exception:
                pass

            if s.get("fake_image_action_seen"):
                _cg_fake = gender_of(s.get("character"))
                _extra_hints.append(
                    "ВАЖНО: описание действия текстом («*отправляет снимок*», "
                    "«вот фото») НИЧЕГО не отправляет — Господин изображения "
                    "НЕ получает. Реальная отправка только вызовом инструмента: "
                    "свой снимок/рисунок = draw; найденная в интернете картинка "
                    "= поиск (search_anime_art/search_images) и show_image. Не "
                    f"пиши, что {gpick(_cg_fake, 'отправила', 'отправил')} или "
                    f"{gpick(_cg_fake, 'прикрепила', 'прикрепил')} "
                    "изображение, если не "
                    f"{gpick(_cg_fake, 'вызвала', 'вызвал')} инструмент. О "
                    "снимках, которые уже пришли в чат после вызова, говорить "
                    "можно — запрет только на выдуманную отправку.")

            if user_text and s.get("memory") is not None:
                from persona.character_context import detect_address_directive
                _adir = detect_address_directive(user_text)
                if _adir and s["memory"].set_address_override(
                        character=s["character"], form=_adir.get("form", ""),
                        honorific=_adir.get("honorific", "")):
                    print(f"[address] {s.get('character_id','?')}: {_adir} → "
                          f"form={s['memory'].address_form_override!r} "
                          f"honorific={s['memory'].user_honorific!r}")

            if user_text and s.get("identity") is not None:
                try:
                    from persona.axis_wishes import apply_axis_wishes
                    _wishes = apply_axis_wishes(s["identity"], user_text)
                    if _wishes:
                        print(f"[axis-goal] {s.get('character_id','?')}: {_wishes}")
                except Exception as e:
                    print(f"[axis-goal] detect failed: {e}")
                try:
                    from persona.axis_stimuli import record_axis_stimuli
                    _stims = record_axis_stimuli(s["identity"], user_text)
                    if _stims:
                        print(f"[axis-stim] {s.get('character_id','?')}: "
                              f"{[(x['axis'], x['dir']) for x in _stims]}")
                except Exception as e:
                    print(f"[axis-stim] detect failed: {e}")

            from persona.speech_guard import assistant_texts as _sg_texts
            _sg_recent = _sg_texts(s["history"].get_messages())

            system_prompt, turn_tail = build_prompt_parts(
                s["persona"],
                memory=s["memory"],
                query_embedding=query_embedding,
                is_new_session=is_new,
                tools=tools,
                backend=s["client"].backend,
                query_text=user_text,
                draw_requested=draw_requested,
                draw_max_rating=s["config"].drawing.max_rating,
                draw_prev_state=_snapshot_hint(s) if draw_requested else "",
                draw_recent=_recent_snapshots(s) if draw_requested else (),
                draw_prev_level=_snapshot_ladder_level(s) if draw_requested else 0,
                draw_contact=_contact_allowed() if draw_requested else False,
                axis_examples=True,
                drawing_boundaries=_get_drawing_boundaries(s),
                current_outfit_label=_get_current_outfit_label(s),
                scenario_note=_scenario_note,
                aftereffect_note=_aftereffect_note,
                quirks_note=_quirks_block(s),
                recalled_records=_recalled,
                absent_refs=_absent,
                include_grammar=(not s["config"].session.grammar_polish
                                 and s["client"].backend.needs_grammar_pass),
                extra_sys_hints=_extra_hints or None,
                document_blocks=_doc_blocks,
                lore_index=_lore_index,
                lore_blocks=_lore_blocks,
                body_block=_body_block,
                speech_guard=True,
                recent_replies=_sg_recent,
            )

            s["last_prompt"] = (system_prompt
                                + (f"\n\n<!-- хвост хода (у точки генерации) -->\n{turn_tail}"
                                   if turn_tail else ""))
            s["last_prompt_static_chars"] = len(system_prompt)
            s["last_active_tools"] = [t["function"]["name"] for t in tools]
            s["last_query"] = user_text

            if image_base64 and not vision_available(s):
                image_base64 = None
                try:
                    await ws.send_json({"type": "debug", "tag": "vision",
                        "data": {"dropped": True, "reason": "mmproj not loaded"}})
                except Exception:
                    pass
            if image_base64:
                user_content = [{
                    "type": "image_url",
                    "image_url": {"url": _image_data_url(image_base64)},
                }]
                if user_text:
                    user_content.append({"type": "text", "text": user_text})
                s["history"].add("user", user_text or "[изображение]")
                s["history"].messages[-1]["content"] = user_content
            else:
                s["history"].add("user", user_text)
            _stats_on_user_message(s)
            if _gestures.has_gesture(user_text):
                _achievement_award(s, "gesture_first")
            _flush_mood_marker(s)
            _flush_scenario_marker(s)

            await lifecycle.ensure_loaded()

            full_response = ""
            ui_segment = ""
            had_split = False
            ui_visible = {"v": False, "chars": 0}
            loop = asyncio.get_event_loop()

            _real_tool_handler = s["memory"].handle_tool_call

            def _format_args(args: dict) -> str:
                if not args:
                    return ""
                parts: list[str] = []
                for k, v in args.items():
                    sv = str(v)
                    if len(sv) > 120:
                        sv = sv[:120] + "…"
                    parts.append(f"{k}={sv!r}")
                return ", ".join(parts)

            def debug_tool_handler(name: str, args: dict):
                args_preview = _format_args(args or {}) if _CHAT_TRACE else ""
                asyncio.run_coroutine_threadsafe(
                    ws.send_json({
                        "type": "system",
                        "text": _tool_call_notice(name, args_preview),
                    }),
                    loop,
                )

                s["tool_activity"] = name
                try:
                    result = _real_tool_handler(name, args)
                finally:
                    s["tool_activity"] = None
                _achievements_on_tool(s, name, result, loop)

                if not _CHAT_TRACE:
                    return result
                preview = (result or "").strip()
                max_len = 1200
                if len(preview) > max_len:
                    preview = (preview[:max_len]
                               + f"\n… [обрезано, полная длина {len(result)}]")
                asyncio.run_coroutine_threadsafe(
                    ws.send_json({
                        "type": "system",
                        "text": f"↳ {preview}" if preview else "↳ (пустой ответ)",
                    }),
                    loop,
                )
                return result

            continuation_obs = None

            def run_chat():
                nonlocal full_response
                msgs = s["history"].get_messages()
                if continuation_obs is not None:
                    msgs = msgs + (continuation_obs
                                   if isinstance(continuation_obs, list)
                                   else [continuation_obs])
                from llm.llama_client import STREAM_RESET as _SR
                from llm.llama_client import STREAM_SPLIT as _SP
                nonlocal ui_segment, had_split
                ui_segment, had_split = "", False
                _TAIL_HOLD = 32
                _FLUSH_EVERY = 0.12
                buf_full = ""
                seg = ""
                emitted = 0
                last_flush = 0.0

                def _flush():
                    nonlocal emitted, last_flush
                    now = time.monotonic()
                    if now - last_flush < _FLUSH_EVERY:
                        return
                    cut = max(0, len(seg) - _TAIL_HOLD)
                    if cut > emitted:
                        delta = seg[emitted:cut]
                        emitted = cut
                        last_flush = now
                        ui_visible["v"] = True
                        ui_visible["chars"] = ui_visible.get("chars", 0) + len(delta)
                        asyncio.run_coroutine_threadsafe(
                            ws.send_json({"type": "response_chunk", "text": delta}),
                            loop)

                from llm.backends import style_wants_verbose as _swv
                for token in s["client"].chat_with_tools(
                    messages=msgs,
                    system=system_prompt,
                    tail=turn_tail,
                    tools=tools,
                    tool_handler=debug_tool_handler,
                    char_name=s["character"].name,
                    char_gender=gender_of(s["character"]),
                    verbose_style=_swv(getattr(s["character"],
                                               "response_style", "")),
                    deferred_pending=lambda: any(
                        a.get("kind") in ("image", "change_outfit")
                        for a in s["memory"].pending_actions),
                ):
                    if token is _SR:
                        seg, emitted, last_flush = "", 0, 0.0
                        ui_visible["chars"] = 0
                        asyncio.run_coroutine_threadsafe(
                            ws.send_json({"type": "response_stream_reset"}), loop)
                        continue
                    if token is _SP:
                        seg_clean = strip_tool_calls(seg).strip()
                        if seg_clean:
                            had_split = True
                            buf_full += seg_clean + "\n\n"
                            ui_visible["v"] = True
                            ui_visible["chars"] = 10**9
                            asyncio.run_coroutine_threadsafe(
                                ws.send_json({"type": "response_split",
                                              "text": seg_clean,
                                              "id_mood": _reply_mood_id(s)}),
                                loop)
                        seg, emitted, last_flush = "", 0, 0.0
                        continue
                    seg += token
                    _flush()
                ui_segment = seg
                full_response = buf_full + seg
                return full_response

            _cont_budget = max(0, getattr(
                getattr(s.get("config"), "session", None),
                "continuation_budget", 0,
            ))
            _rounds_left = _cont_budget + 1
            _corrective_retry_left = 1
            _turn_interrupted = False
            while _rounds_left > 0:
                _rounds_left -= 1
                s["client"].last_reasoning = None

                gen_future = loop.run_in_executor(None, run_chat)
                verdict = await _watch_ws_during_generation(
                    s, ws, gen_future, ui_visible, s["client"])
                tokens = gen_future.result()
                if verdict == "interrupt":
                    s["memory"].pending_actions.clear()
                    s["pending_image_ack"] = ""
                    if ui_visible.get("chars", 0) > 0:
                        with contextlib.suppress(Exception):
                            await ws.send_json({"type": "response_stream_reset"})
                    print("[interrupt] генерация перебита новым сообщением — "
                          "ход перезапускается со склейкой")
                    _turn_interrupted = True
                    turn.release()
                    break

                _round_stats = s["client"].last_stats

                import uuid as _uuid
                for _t in list(s["client"].last_tool_trace or [])[:3]:
                    _tid = f"tr-{_uuid.uuid4().hex[:8]}"
                    s["history"].add_message({
                        "role": "assistant", "content": None,
                        "tool_calls": [{"id": _tid, "type": "function",
                                        "function": {"name": _t["name"],
                                                     "arguments": _t["arguments"]}}],
                    })
                    s["history"].add_message({
                        "role": "tool", "tool_call_id": _tid,
                        "content": _trace_result_short(_t["name"],
                                                       _t["result_short"]),
                    })

                if s["client"].last_reasoning:
                    await ws.send_json({
                        "type": "thinking",
                        "text": s["client"].last_reasoning,
                    })

                clean_response = strip_tool_calls(full_response)
                clean_response = re.sub(
                    r"[一-鿿㐀-䶿　-〿]+",
                    "",
                    clean_response,
                )
                clean_response = strip_trailing_filler(clean_response).strip()
                clean_response = mood_mod.strip_mood_tag(clean_response).strip()

                _fake_snippet = None
                _retry = None
                _cg_turn = gender_of(s.get("character"))
                if clean_response and not s["memory"].pending_actions:
                    _trace_names = {t.get("name")
                                    for t in (s["client"].last_tool_trace or [])}
                    if not (_trace_names & _IMAGE_ACTION_TOOLS):
                        _delivered = _recent_image_delivered(s["history"])
                        _fake_snippet = _detect_fake_image_action(
                            clean_response, delivered_recently=_delivered)
                        if _fake_snippet:
                            s["fake_image_action_seen"] = True
                            _retry = ("fake-action", _fake_snippet,
                                      _fake_action_nudge(_cg_turn, _delivered))
                    if (_retry is None and "draw" not in _trace_names
                            and drawing_available(s)):
                        if _draw_trigger_in(user_text):
                            _m = _DRAW_REASK_RX.search(clean_response)
                            if _m:
                                _retry = ("draw-reask", _m.group(0),
                                          _draw_reask_nudge(_cg_turn))
                        elif (_is_short_consent(user_text)
                              and _PHOTO_OFFER_RX.search(
                                  _last_assistant_text(s["history"]))):
                            _retry = ("draw-consent", (user_text or "").strip(),
                                      _consent_draw_nudge(_cg_turn))
                    if (_retry is None and user_text
                            and "search_memory" not in _trace_names):
                        _m = _detect_memory_refusal(user_text, clean_response)
                        if _m:
                            _retry = ("memory-refusal", _m,
                                      _MEMORY_REFUSAL_NUDGE)
                if _retry is not None:
                    _kind, _snippet, _nudge = _retry
                    if _corrective_retry_left > 0:
                        _corrective_retry_left -= 1
                        _rounds_left += 1
                        print(f"[{_kind}] {_snippet!r} → корректирующий ретрай")
                        await ws.send_json({"type": "response_stream_reset"})
                        continuation_obs = [
                            {"role": "assistant", "content": clean_response},
                            {"role": "user", "content": _nudge},
                        ]
                        continue
                    print(f"[{_kind}] {_snippet!r} повторно после ретрая — "
                          f"принимаем" + (", прививка в историю"
                                          if _fake_snippet else ""))

                if (clean_response and getattr(s["config"].session, "grammar_polish", False)
                        and s["client"].backend.needs_grammar_pass):
                    from persona.grammar import correct_grammar
                    _polished = await loop.run_in_executor(
                        None,
                        lambda txt=clean_response: correct_grammar(
                            s["client"], txt, character=s["character"],
                            dialogue=s["history"].get_messages(),
                            honorific=(getattr(s["memory"], "user_honorific", None)
                                       or resolve_honorific(s["character"])),
                        ),
                    )
                    if _polished and _polished != clean_response:
                        await ws.send_json({"type": "debug", "tag": "grammar",
                                            "data": {"before": clean_response,
                                                     "after": _polished}})
                        clean_response = _polished

                has_image_action = any(
                    a.get("kind") == "image"
                    for a in s["memory"].pending_actions
                )
                if has_image_action:
                    s["pending_image_ack"] = clean_response or ""

                if clean_response:
                    if had_split:
                        _ui_text = strip_tool_calls(ui_segment)
                        _ui_text = strip_trailing_filler(_ui_text).strip()
                        _ui_text = mood_mod.strip_mood_tag(_ui_text).strip()
                    else:
                        _ui_text = clean_response
                    await ws.send_json({
                        "type": "response",
                        "text": _ui_text or clean_response,
                        "id_mood": _reply_mood_id(s),
                    })
                    if not has_image_action:
                        _hist_add_assistant(s, clean_response)
                        if _fake_snippet:
                            s["history"].add("user", (
                                _FAKE_ACTION_INOCULATION_NEW
                                if _recent_image_delivered(s["history"])
                                else _FAKE_ACTION_INOCULATION),
                                mood={"kind": "marker", "marker": "fake_action"})
                    await _send_reply_stats(s, ws, _round_stats)
                else:
                    print(f"[LLM] empty response after cleanup "
                          f"(raw len={len(full_response)}) — skip UI send + history.add")

                await _send_pending_portrait_reveal(s, ws)

                drained_kinds = [a.get("kind") for a in s["memory"].pending_actions]
                if not drained_kinds:
                    break

                await _process_pending_actions(s, ws, loop)

                if "end_session" in drained_kinds:
                    break
                continuation_obs = _build_continuation_observation(s, drained_kinds)
                if continuation_obs is None:
                    break

            if _turn_interrupted:
                continue

            await _send_pending_portrait_reveal(s, ws)

            await _scenario_after_turn(s, ws)

            detection = detect_entities(user_text, s["memory"].records)
            if detection.matched or detection.candidates:
                await ws.send_json({
                    "type": "detection",
                    "matched": [r.title for r in detection.matched],
                    "candidates": [c["name"] for c in detection.candidates],
                })

            await ws.send_json({"type": "done"})
            turn.release()

            s["turn_busy"] = False
            await _drain_interjections(s, ws)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "text": str(e)})
        except Exception:
            pass
    finally:
        turn.release()
        s["turn_busy"] = False
        s["chat_turn_active"] = False
        try:
            unsub()
        except Exception:
            pass
        try:
            unsub_persona()
        except Exception:
            pass
        try:
            _status_task.cancel()
        except Exception:
            pass
        if s.get("active_ws") is ws:
            s["active_ws"] = None
