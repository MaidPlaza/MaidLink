from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Optional

from persona import crypto


@dataclass
class ReflectionItem:
    id: str
    character_id: str
    messages: list[dict]
    ended_at: float
    reason: str
    attempts: int = 0
    started_at: float = 0.0
    progress: int = -1
    enc: dict | None = None

    @classmethod
    def new(cls, character_id: str, messages: list[dict], reason: str,
            started_at: float = 0.0) -> "ReflectionItem":
        return cls(
            id=str(uuid.uuid4()),
            character_id=character_id,
            messages=[dict(m) for m in messages],
            ended_at=time.time(),
            reason=reason,
            started_at=float(started_at or 0.0),
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_sealed(self) -> bool:
        return isinstance(self.enc, dict)

    @classmethod
    def from_dict(cls, d: dict) -> "ReflectionItem":
        return cls(
            id=d["id"],
            character_id=d["character_id"],
            messages=d.get("messages", []),
            ended_at=d.get("ended_at", 0.0),
            reason=d.get("reason", ""),
            attempts=d.get("attempts", 0),
            started_at=float(d.get("started_at", 0.0) or 0.0),
            progress=d.get("progress", -1),
            enc=d.get("enc"),
        )


class CancelledByActivity(Exception):
    pass


class ReflectionQueue:
    def __init__(self, path: str | Path, key_provider=None) -> None:
        self._path = Path(path)
        self._items: list[ReflectionItem] = []
        self._key_provider = key_provider
        self._load()

    def set_key_provider(self, key_provider) -> None:
        self._key_provider = key_provider

    def _key_for(self, character_id: str) -> Optional[bytes]:
        if self._key_provider is None:
            return None
        try:
            return self._key_provider(character_id)
        except Exception as e:
            print(f"[refl-queue] key_provider failed for {character_id}: {e}")
            return None

    def add(self, item: ReflectionItem) -> None:
        self._items.append(item)
        self.save()

    def peek(self, prefer_character_id: Optional[str] = None, *,
             ready_only: bool = False) -> Optional[ReflectionItem]:
        if not self._items:
            return None

        def usable(it: ReflectionItem) -> bool:
            return not ready_only or self.unseal(it)

        if prefer_character_id:
            for it in self._items:
                if it.character_id == prefer_character_id and usable(it):
                    return it
        for it in self._items:
            if usable(it):
                return it
        return None

    def unseal(self, item: ReflectionItem) -> bool:
        if not item.is_sealed:
            return True
        dek = self._key_for(item.character_id)
        if dek is None:
            return False
        try:
            item.messages = crypto.open_session(item.enc, dek, item.id)
        except crypto.CryptoError as e:
            print(f"[refl-queue] {item.id[:8]}: транскрипт не читается ({e})")
            return False
        item.enc = None
        return True

    def has_for(self, character_id: str) -> bool:
        return any(it.character_id == character_id for it in self._items)

    def rename_character(self, old_id: str, new_id: str) -> int:
        n = 0
        for it in self._items:
            if it.character_id == old_id:
                it.character_id = new_id
                n += 1
        if n:
            self.save()
        return n

    def remove(self, item_id: str) -> bool:
        for i, it in enumerate(self._items):
            if it.id == item_id:
                del self._items[i]
                self.save()
                return True
        return False

    def remove_character(self, character_id: str) -> int:
        before = len(self._items)
        self._items = [it for it in self._items if it.character_id != character_id]
        removed = before - len(self._items)
        if removed:
            self.save()
        return removed

    def increment_attempts(self, item_id: str) -> int:
        for it in self._items:
            if it.id == item_id:
                it.attempts += 1
                self.save()
                return it.attempts
        return 0

    def __len__(self) -> int:
        return len(self._items)

    def all(self) -> list[ReflectionItem]:
        return list(self._items)

    def _row(self, item: ReflectionItem) -> dict:
        d = item.to_dict()
        if item.is_sealed:
            return d
        dek = self._key_for(item.character_id)
        if dek is None:
            return d
        d["messages"] = []
        d["enc"] = crypto.seal_session(item.messages, dek, item.id)
        return d

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        data = {"items": [self._row(it) for it in self._items]}
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(self._path)

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._items = [ReflectionItem.from_dict(d) for d in data.get("items", [])]
        except Exception as e:
            print(f"[refl-queue] load failed ({e}), starting empty")
            self._items = []


STEP_NAMES = [
    "extract",
    "dedup",
    "master_summary",
    "sleep",
    "decay",
    "evolve",
    "entity_opinions",
    "relationship_level",
    "trait_checks",
    "noop",
]

STEP_LABELS_RU = {
    0: "извлечение фактов",
    1: "чистка дублей памяти",
    2: "обновление сводки",
    3: "дневник персонажа",
    4: "затухание мыслей",
    5: "эволюция характера",
    6: "мнения о людях",
    7: "уровень отношений",
    8: "проверка черт",
}


def _mmproj_available(config, project_root: Path) -> bool:
    if config is None:
        return False
    mmproj = (getattr(config.llm, "server_mmproj", "") or "").strip()
    if not mmproj:
        return False
    p = Path(mmproj)
    if not p.is_absolute():
        p = project_root / mmproj
    return p.exists()


def _describe_one_image(client, url: str, role: str, char_name: str,
                        honorific: str, char_gender: str = "female") -> str:
    system = ("Ты — служебный анализатор кадров для дневника. Описывай изображение "
              "фактически: кто/что в кадре, обстановка, поза и одежда, настроение. "
              "1–2 коротких предложения по-русски, без вступлений и оценок качества.")
    if role == "assistant":
        from persona.gender import g as _gpick
        ask = (f"Это снимок, который {char_name} "
               f"{_gpick(char_gender, 'отправила', 'отправил')} в чате "
               f"(изображение сгенерировано по "
               f"{_gpick(char_gender, 'её', 'его')} решению). "
               "Опиши содержимое кадра.")
    else:
        ask = f"Это фото, которое прислал {honorific}. Опиши содержимое кадра."
    raw = client.chat(
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": url}},
            {"type": "text", "text": ask},
        ]}],
        system=system, thinking=False, label="Описание снимка",
        max_tokens=512,
    )
    desc = " ".join((raw or "").split())
    return desc[:400]


def describe_session_images(messages: list[dict], client, *, char_name: str,
                            char_gender: str = "female",
                            honorific: str, vision_ok: bool,
                            check_active: Optional[Callable[[], None]] = None) -> int:
    replaced = 0
    for m in messages:
        content = m.get("content")
        if not isinstance(content, list):
            continue
        role = m.get("role", "")
        parts: list[str] = []
        for chunk in content:
            if not isinstance(chunk, dict):
                continue
            ctype = chunk.get("type")
            if ctype == "text":
                t = (chunk.get("text") or "").strip()
                if t:
                    parts.append(t)
            elif ctype == "image_url":
                if check_active is not None:
                    check_active()
                desc = ""
                if vision_ok:
                    try:
                        url = (chunk.get("image_url") or {}).get("url", "")
                        if url:
                            desc = _describe_one_image(client, url, role,
                                                       char_name, honorific,
                                                       char_gender)
                    except Exception as e:
                        print(f"[refl] image describe failed: "
                              f"{type(e).__name__}: {e}")
                if role == "assistant":
                    parts.append(f"*отправляет снимок: {desc}*" if desc
                                 else "*отправляет снимок*")
                else:
                    parts.append(f"*фото от {honorific}: {desc}*" if desc
                                 else f"*фото от {honorific}*")
        m["content"] = "\n".join(parts)
        replaced += 1
    return replaced


def character_id_from_state(state: dict) -> str:
    return state.get("character_id") or state["config"].character_id


def load_character_state_for_reflection(
    character_id: str, project_root: Path, client, store=None
) -> dict:
    from memory.unified import UnifiedMemory, MemoryRecord
    from persona.character_store import CharacterStore

    if store is None:
        store = CharacterStore(
            characters_dir=project_root / "characters",
            baseline_dir=None,
            runtime_cache_dir=project_root / "runtime_cache",
        )

    loaded = store.load(character_id)
    character = loaded["character"]
    identity = loaded["identity"]

    from persona.character_context import resolve_honorific, CharacterContext
    memory = UnifiedMemory(None, "", client)
    memory.user_honorific = resolve_honorific(character)
    memory.load_records(loaded["memory_records"])
    memory.load_address_overrides(character)

    return {
        "character": character,
        "character_id": character_id,
        "persona": CharacterContext(
            character=character, identity=identity, character_id=character_id,
        ),
        "store": store,
        "memory": memory,
        "identity": identity,
        "client": client,
        "session_start_count": len(memory.records),
    }


_persist_lock = threading.RLock()


def save_state_to_disk(state: dict, *, with_identity: bool = True) -> None:
    with _persist_lock:
        records = [r.to_dict() for r in state["memory"].records]
        store = state["store"]
        character_id = state["character_id"]

        store.set_memory_records(character_id, records)
        if with_identity:
            state["identity"].save()
        else:
            store.save(character_id, with_identity=False, with_memory=True)


async def _run_reflection(
    main_state: dict,
    item: ReflectionItem,
    queue: ReflectionQueue,
    project_root: Path,
    loop: asyncio.AbstractEventLoop,
) -> list[tuple[str, float]]:
    from services.background.model_lifecycle import get_global as _get_lifecycle
    lifecycle = _get_lifecycle()

    is_active = item.character_id == character_id_from_state(main_state)
    char_state = (main_state if is_active
                  else load_character_state_for_reflection(
                      item.character_id, project_root, main_state["client"]))

    activity_baseline = main_state.get("last_user_message_at", 0.0)

    def check_active() -> None:
        if main_state.get("last_user_message_at", 0.0) > activity_baseline:
            raise CancelledByActivity()
        if main_state.get("reflection_cancel_requested"):
            raise CancelledByActivity()

    persist_state = {
        "memory": char_state["memory"], "identity": char_state["identity"],
        "character_id": item.character_id, "store": char_state["store"],
    }

    step_timings: list[tuple[str, float]] = []

    async def run_step(idx: int, fn: Callable[[], Any]) -> None:
        if item.progress >= idx:
            return
        check_active()
        if idx in STEP_LABELS_RU:
            main_state["reflection_step"] = {
                "label": STEP_LABELS_RU[idx], "idx": idx + 1,
                "total": len(STEP_LABELS_RU),
            }
        _t0 = time.perf_counter()
        await loop.run_in_executor(None, fn)
        _dt = time.perf_counter() - _t0
        print(f"[refl] step {idx} {STEP_NAMES[idx]}: "
              f"{_dt:.1f}s ({item.character_id})")
        step_timings.append((STEP_NAMES[idx], _dt))
        if fn is not _noop_step:
            await loop.run_in_executor(None, lambda: save_state_to_disk(persist_state))
        item.progress = idx
        queue.save()

    messages = item.messages
    from persona.relationship_axes import (REL_MIN_TURNS, count_content_turns,
                                           count_sessions, session_note,
                                           session_weight)
    n_turns = count_content_turns(messages)
    _started = float(getattr(item, "started_at", 0.0) or 0.0)
    _duration = max(0.0, float(item.ended_at or 0.0) - _started) if _started > 0 else 0.0
    is_fleeting = n_turns < REL_MIN_TURNS
    char = char_state["character"]
    mem = char_state["memory"]
    identity = char_state["identity"]
    persona = char_state["persona"]
    client = char_state["client"]
    from services.addons import reflection_fragments
    client.system_suffix = "\n\n".join(reflection_fragments(project_root))
    from persona.character_context import resolve_honorific
    honorific = resolve_honorific(char)

    from persona.sleep import perform_sleep
    from persona.evolution import (
        evolve_character, update_master_summary,
        evolve_entity_opinions, evolve_loop_opinions,
        evolve_relationship_axes, reassess_master_regard, describe_acquaintance_phase,
        aggregate_trends,
    )

    async with lifecycle.using():
        if item.progress < 0:
            _vision_ok = _mmproj_available(main_state.get("config"), project_root)

            def _describe_images() -> int:
                return describe_session_images(
                    messages, client, char_name=char.name,
                    char_gender=(getattr(char, "gender", "") or "female"),
                    honorific=honorific,
                    vision_ok=_vision_ok, check_active=check_active)

            _t_img = time.perf_counter()
            _n_img = await loop.run_in_executor(None, _describe_images)
            if _n_img:
                queue.save()
                _dt_img = time.perf_counter() - _t_img
                step_timings.append(("images->text", _dt_img))
                print(f"[refl] images->text: {_n_img} msg(s) in {_dt_img:.1f}s "
                      f"(vision={_vision_ok}, {item.character_id})")

        def step_extract() -> None:
            before = len(mem.records)
            mem.extract_from_session(messages, char_name=char.name, honorific=honorific,
                                     gender=char.gender)
            added = len(mem.records) - before
            print(f"[refl] extract: +{added} records ({item.character_id})")
            try:
                from memory.relation_extraction import extract_relations_from_session
                rr = extract_relations_from_session(messages, mem, char_name=char.name,
                                                    honorific=honorific, gender=char.gender)
                print(f"[refl] relations: {rr} ({item.character_id})")
            except Exception as e:
                print(f"[refl] relations extract fail: {type(e).__name__}: {e}")
            try:
                from memory.loop_extraction import extract_loops_from_session
                lr = extract_loops_from_session(messages, mem, char_name=char.name,
                                                honorific=honorific, gender=char.gender)
                print(f"[refl] loops: {lr} ({item.character_id})")
            except Exception as e:
                print(f"[refl] loops extract fail: {type(e).__name__}: {e}")
            try:
                from memory.topic_extraction import extract_topic_opinions_from_session
                tp = extract_topic_opinions_from_session(messages, mem, char_name=char.name,
                                                         honorific=honorific, gender=char.gender)
                print(f"[refl] topics: {tp} ({item.character_id})")
            except Exception as e:
                print(f"[refl] topics extract fail: {type(e).__name__}: {e}")
            try:
                pr = mem.extract_preferences(messages, char_name=char.name, honorific=honorific)
                if any(pr.values()):
                    print(f"[refl] preferences: {pr} ({item.character_id})")
            except Exception as e:
                print(f"[refl] preferences extract fail: {type(e).__name__}: {e}")
            try:
                nr = mem.extract_user_rules(messages, char_name=char.name, honorific=honorific)
                if nr:
                    print(f"[refl] rules: +{nr} ({item.character_id})")
            except Exception as e:
                print(f"[refl] rules extract fail: {type(e).__name__}: {e}")
            try:
                from memory.habit_extraction import extract_habits_from_session
                hr = extract_habits_from_session(messages, mem, char_name=char.name,
                                                 honorific=honorific, gender=char.gender)
                if any(hr.values()):
                    print(f"[refl] habits: {hr} ({item.character_id})")
            except Exception as e:
                print(f"[refl] habits extract fail: {type(e).__name__}: {e}")
        await run_step(0, step_extract)

        def step_dedup() -> None:
            before = len(mem.records)
            mem.deduplicate_records(char_state["session_start_count"])
            removed = before - len(mem.records)
            print(f"[refl] dedup: -{removed} records ({item.character_id})")
        await run_step(1, step_dedup)

        def step_master() -> None:
            update_master_summary(client, persona, mem)
        await run_step(2, step_master)

        def step_sleep() -> None:
            from persona.sleep import diary_importance, thought_importance
            sleep_result = perform_sleep(client, persona, messages, [])
            if sleep_result.diary_entry:
                sig = int(sleep_result.session_significance or 0)
                _extra = {"session_turns": n_turns}
                if sig:
                    _extra["significance"] = sig
                mem.add_reflection(sleep_result.diary_entry, diary_importance(sig), "diary",
                                   extra=_extra)
            for interest in (sleep_result.new_interests or []):
                st = int(sleep_result.interest_strength.get(interest, 0) or 0)
                imp = thought_importance("interest", st)
                identity.add_thought(interest, kind="interest", importance=imp, strength=st)
                mem.add_reflection(f"Заинтересовала тема: {interest}", imp, "interest")
            for idea in (sleep_result.ideas or []):
                st = int(sleep_result.idea_strength.get(idea, 0) or 0)
                imp = thought_importance("idea", st)
                identity.add_thought(idea, kind="idea", importance=imp, strength=st)
                mem.add_reflection(f"Идея: {idea}", imp, "idea")
            for secret in (sleep_result.new_secrets or []):
                mem.add_reflection(secret, 0.6, "secret")
        await run_step(3, step_sleep)

        def step_decay() -> None:
            identity.decay_thoughts()
        await run_step(4, step_decay)

        _trends_cache: dict[str, str] = {}

        def get_trends() -> str:
            if "v" not in _trends_cache:
                _trends_cache["v"] = aggregate_trends(client, persona, mem)
            return _trends_cache["v"]

        def step_evolve() -> None:
            new_refls = [r for r in mem.records
                         if r.type == "рефлексия"
                         and r.created_at > identity.last_evolution]
            ref_importance = sum(r.importance for r in new_refls)
            identity.accumulate(ref_importance)
            if identity.should_evolve():
                evolve_character(client, persona, new_refls, memory=mem,
                                 trends_text=get_trends())
                print(f"[refl] character evolution fired ({item.character_id})")
            else:
                print(f"[refl] evolution threshold not reached "
                      f"({identity.accumulated_importance:.1f}, {item.character_id})")
            from persona.axis_dynamics import apply_goal_drip
            _drip = apply_goal_drip(identity, persona.character)
            if _drip:
                print(f"[axis-goal] капля: " + ", ".join(f"{a} {v:+.3f}" for a, v in _drip.items()))
        await run_step(5, step_evolve)

        def step_opinions() -> None:
            evolve_entity_opinions(client, persona, mem,
                                    session_start_count=char_state["session_start_count"])
            try:
                lo = evolve_loop_opinions(client, persona, mem)
                if lo:
                    print(f"[refl] loop opinions: {lo} ({item.character_id})")
            except Exception as e:
                print(f"[refl] loop opinions fail: {type(e).__name__}: {e}")
        await run_step(6, step_opinions)

        def step_relationship() -> None:
            refls_all = [f"- {r.details.get('description', r.title)}"
                         for r in mem.records
                         if r.type == "рефлексия" and not r.is_forgotten]
            rel_trends_text = get_trends()
            _wm = float(getattr(identity, "rel_axes_last_eval", 0.0) or 0.0)
            _fresh = [r for r in mem.records
                      if r.type == "рефлексия" and not r.is_forgotten
                      and r.created_at > _wm]
            if _wm <= 0.0:
                _fresh = _fresh[-3:]
            fresh_lines = [f"- {r.details.get('description', r.title)}"
                           for r in _fresh]
            if is_fleeting:
                print(f"[refl] оси отношений: сессия мимолётная ({n_turns} реплик) — "
                      f"не оцениваем ({item.character_id})")
            else:
                evolve_relationship_axes(
                    client, persona,
                    reflections_text="\n".join(fresh_lines[-10:]),
                    trends_text=rel_trends_text,
                    session_weight=session_weight(n_turns),
                    session_note=session_note(n_turns, _duration),
                )
            identity.rel_axes_last_eval = time.time()
            try:
                reassess_master_regard(
                    client, persona,
                    reflections_text="\n".join(refls_all[-30:]),
                    trends_text=rel_trends_text)
            except Exception as e:
                print(f"[refl] master regard fail: {type(e).__name__}: {e}")
            try:
                dur = next((s for s in persona.identity.relationship_statements
                            if s.id == "rel_duration"), None)
                if dur is not None:
                    dur.text = describe_acquaintance_phase(count_sessions(mem.records))
            except Exception as e:
                print(f"[refl] rel_duration fail: {type(e).__name__}: {e}")
        await run_step(7, step_relationship)

        def step_trait_checks() -> None:
            from persona.vulnerability_catalog import evaluate_all_triggers
            from persona.character import ActiveTrait
            import time
            cv = char.conditional_vulnerabilities
            cs = char.conditional_strengths
            quirk_cands, quirk_code = [], ""
            try:
                from app_paths import PROJECT_ROOT as _PR
                from services import nsfw_extra as _nx, nsfw_quirks as _nq
                _store = char_state.get("store")
                _arch = _store.get_archive(item.character_id) if _store else None
                quirk_code = _nx.read_code(_arch)
                quirk_cands = _nq.candidates(_PR, code_string=quirk_code,
                                             identity=identity)
            except Exception as e:
                print(f"[quirks] кандидаты не собраны: {type(e).__name__}: {e}")
            if not (cv.opt_in or cv.custom or cs.opt_in or cs.custom or quirk_cands):
                return
            vulns, strengths, quirks = evaluate_all_triggers(
                persona,
                session_messages=messages,
                client=client,
                quirks=quirk_cands,
            )
            triggered = list(vulns) + list(strengths)
            now = time.time()
            for tid, source_event in triggered:
                identity.active_traits.append(ActiveTrait(
                    trait_id=tid,
                    activated_at=now,
                    source_event=source_event,
                ))
            gained = []
            if quirks:
                try:
                    from app_paths import PROJECT_ROOT as _PR
                    from services import nsfw_quirks as _nq
                    gained = _nq.apply_verdicts(_PR, identity=identity,
                                                verdicts=quirks,
                                                code_string=quirk_code, now=now)
                except Exception as e:
                    print(f"[quirks] метки не применены: {type(e).__name__}: {e}")
            if not triggered and not quirks:
                print(f"[refl] trait_checks: no triggers ({item.character_id})")
                return
            print(f"[refl] trait_checks: activated {len(triggered)} "
                  f"({[t[0] for t in triggered]}, {item.character_id}); "
                  f"причуды: вердиктов {len(quirks)}, приобретено "
                  f"{[q.code for q in gained]}")
        await run_step(8, step_trait_checks)

        await run_step(9, _noop_step)

        await loop.run_in_executor(None, lambda: save_state_to_disk(persist_state))

    return step_timings


def _noop_step() -> None:
    return None


def format_step_timings(timings: list[tuple[str, float]]) -> str:
    parts = [f"{name} {sec:.1f}s" for name, sec in timings if sec >= 0.05]
    return " | ".join(parts)


async def reflection_worker(
    state_provider: Callable[[], Optional[dict]],
    queue: ReflectionQueue,
    project_root: Path,
    config,
) -> None:
    from services.background.analyzer import analyzer_tick, DecisionVerdict
    from services.background.busy import busy_with, session_engaged

    print(f"[refl-worker] started "
          f"(gate=analyzer_tick+session, max_attempts={config.session.reflection_max_attempts})")
    _engaged_logged: bool | None = None

    while True:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            print("[refl-worker] cancelled, exiting")
            return

        state = state_provider()
        if not state:
            continue

        from services.background.model_lifecycle import get_global as _get_lc
        decision = analyzer_tick(llm_loaded=_get_lc().is_loaded)
        if decision.verdict is DecisionVerdict.STOP:
            continue

        if busy_with(state) is not None:
            continue

        engaged = session_engaged(state)
        if engaged != _engaged_logged:
            _engaged_logged = engaged
            if engaged:
                print("[refl-worker] живая сессия — рефлексия ждёт её конца")
        if engaged:
            continue

        active_id = character_id_from_state(state)
        item = queue.peek(prefer_character_id=active_id, ready_only=True)
        if item is None:
            continue

        loop = asyncio.get_event_loop()
        state["reflection_running"] = True
        from services.background.persona_status import persona_status
        persona_status.set_busy(
            actor="reflection_worker",
            label="SLEEPING",
            reason="осмысляет прошедшую сессию",
            priority=2,
        )
        _t_item = time.perf_counter()
        try:
            timings = await _run_reflection(state, item, queue, project_root, loop)
            queue.remove(item.id)
            _total = time.perf_counter() - _t_item
            print(f"[refl-worker] DONE: {item.character_id} ({item.id[:8]}) "
                  f"in {_total:.0f}s")
            summary = format_step_timings(timings or [])
            if summary:
                print(f"[refl] timings ({item.character_id}): {summary}")
                state["last_reflection_report"] = (
                    f"{item.character_id}, {_total:.0f}s всего: {summary}")
        except CancelledByActivity:
            print(f"[refl-worker] cancelled at step {item.progress + 1}/{len(STEP_NAMES)}: "
                  f"{item.character_id} ({item.id[:8]}) — resume on next idle window")
        except Exception as e:
            attempts = queue.increment_attempts(item.id)
            print(f"[refl-worker] ERROR (attempt {attempts}): {item.character_id} "
                  f"({item.id[:8]}): {type(e).__name__}: {e}")
            if attempts >= config.session.reflection_max_attempts:
                print(f"[refl-worker] giving up on {item.id[:8]} "
                      f"after {attempts} attempts — dropping")
                queue.remove(item.id)
        finally:
            state["reflection_running"] = False
            state.pop("reflection_step", None)
            state.pop("reflection_cancel_requested", None)
            persona_status.set_idle("reflection_worker")
            try:
                state["client"].system_suffix = ""
            except Exception:
                pass
