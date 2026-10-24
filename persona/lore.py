from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from persona.gender import g as _gpick, gender_of

MAX_ENTRIES_PER_BLOCK = 2
COS_THRESHOLD = 0.60
MIN_WORDS_FOR_EMBEDDING = 4


@dataclass
class LoreEntry:
    id: str
    topic: str
    text: str
    triggers: list[str] = field(default_factory=list)
    replaces: list[str] = field(default_factory=list)
    _embedding: list[float] | None = None


def parse_entries(raw) -> list[LoreEntry]:
    out: list[LoreEntry] = []
    for e in raw or []:
        if not isinstance(e, dict) or not e.get("id") or not e.get("text"):
            continue
        out.append(LoreEntry(
            id=str(e["id"]),
            topic=str(e.get("topic") or e["id"]),
            text=str(e["text"]).strip(),
            triggers=[str(t) for t in (e.get("triggers") or []) if t],
            replaces=[str(r) for r in (e.get("replaces") or []) if r],
        ))
    return out


def load_character_lore(archive) -> list[LoreEntry]:
    from persona.maid_archive import CHARACTER_LORE_ENTRY
    try:
        if archive is None or not archive.has_entry(CHARACTER_LORE_ENTRY):
            return []
        return parse_entries(yaml.safe_load(
            archive.read_text(CHARACTER_LORE_ENTRY)))
    except Exception as e:
        print(f"[lore] лор персонажа не прочитался: {type(e).__name__}: {e}")
        return []


_app_lore_cache: list[LoreEntry] | None = None
_world_lore_cache: list[LoreEntry] | None = None

WORLD_LORE_DIR = "world_lore"
WORLD_CORE_FILES = ("charter.yaml", "bureau.yaml")


def _content_dir(content_dir: Path | str | None) -> Path:
    if content_dir is None:
        from app_paths import content_base
        return content_base()
    return Path(content_dir)


def _load_lore_folder(d: Path, core_files: tuple[str, ...]) -> list[LoreEntry]:
    merged: dict[str, LoreEntry] = {}
    if d.is_dir():
        def _key(f: Path):
            return ((core_files.index(f.name) if f.name in core_files
                     else len(core_files)), f.name)
        for f in sorted(d.glob("*.yaml"), key=_key):
            try:
                for e in parse_entries(yaml.safe_load(
                        f.read_text(encoding="utf-8"))):
                    merged[e.id] = e
            except Exception as e:
                print(f"[lore] {f.name} не прочитался: {type(e).__name__}: {e}")
    return list(merged.values())


def load_app_lore(content_dir: Path | None = None,
                  force_reload: bool = False) -> list[LoreEntry]:
    global _app_lore_cache
    if _app_lore_cache is not None and not force_reload and content_dir is None:
        return _app_lore_cache
    entries = _load_lore_folder(_content_dir(content_dir) / "app_lore",
                                ("core.yaml",))
    if content_dir is None:
        _app_lore_cache = entries
    return entries


def load_world_lore(content_dir: Path | None = None,
                    force_reload: bool = False) -> list[LoreEntry]:
    global _world_lore_cache
    if (_world_lore_cache is not None and not force_reload
            and content_dir is None):
        return _world_lore_cache
    entries = _load_lore_folder(_content_dir(content_dir) / WORLD_LORE_DIR,
                                WORLD_CORE_FILES)
    if content_dir is None:
        _world_lore_cache = entries
    return entries


_PUNCT_RX = re.compile(r"[^\w\s]+")


def _norm(text: str) -> str:
    t = (text or "").lower().replace("ё", "е")
    return " ".join(_PUNCT_RX.sub(" ", t).split())


_GENDER_RX = re.compile(r"\{([^{}|]*)\|([^{}|]*)\}")


def expand_gender(text: str, gender: str) -> str:
    return _GENDER_RX.sub(
        lambda m: _gpick(gender, m.group(1), m.group(2)), text or "")


def _anchor_text(entry: LoreEntry) -> str:
    return " | ".join([entry.topic, ", ".join(entry.triggers),
                       entry.text[:300]])


def _cos(a: list[float], b: list[float]) -> float:
    from memory.unified import cosine_similarity
    return cosine_similarity(a, b)


def match(entries: list[LoreEntry], user_text: str,
          query_embedding: list[float] | None = None,
          embed_fn=None, *, top_k: int = MAX_ENTRIES_PER_BLOCK,
          cos_threshold: float = COS_THRESHOLD) -> list[LoreEntry]:
    if not entries or not (user_text or "").strip():
        return []
    text = _norm(user_text)
    hits: list[LoreEntry] = []
    for e in entries:
        if any(_norm(t) in text for t in e.triggers if t):
            hits.append(e)
            if len(hits) >= top_k:
                return hits

    if (query_embedding and embed_fn is not None and len(hits) < top_k
            and len(text.split()) >= MIN_WORDS_FOR_EMBEDDING):
        scored: list[tuple[float, LoreEntry]] = []
        for e in entries:
            if e in hits:
                continue
            if e._embedding is None:
                try:
                    e._embedding = embed_fn(_anchor_text(e)) or []
                except Exception:
                    e._embedding = []
            if not e._embedding:
                continue
            sim = _cos(query_embedding, e._embedding)
            if sim >= cos_threshold:
                scored.append((sim, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        if scored:
            print("[lore] эмбеддинг-совпадения: "
                  + ", ".join(f"{e.id}={sim:.2f}" for sim, e in scored[:3]))
        hits.extend(e for _, e in scored[:top_k - len(hits)])
    return hits


def render_character_block(entries: list[LoreEntry]) -> str:
    body = "\n\n".join(e.text for e in entries)
    return (
        "<твой_лор>\n"
        "Твой личный канон по теме разговора — это правда о тебе. Опирайся "
        "на неё, пересказывай своими словами и в своём тоне (не цитируй "
        "дословно), не противоречь и не выдумывай взамен другого.\n"
        f"{body}\n"
        "</твой_лор>"
    )


def render_app_block(entries: list[LoreEntry]) -> str:
    body = "\n\n".join(f"[{e.topic}]\n{e.text}" for e in entries)
    return (
        "<справка_приложения>\n"
        "Справка о приложении по теме вопроса — объясняй по ней, своими "
        "словами и в характере. Не выдумывай кнопки, пункты меню и механики, "
        "которых в справке нет; если ответа тут нет — честно скажи, что "
        "точно не знаешь.\n"
        f"{body}\n"
        "</справка_приложения>"
    )


def render_world_block(entries: list[LoreEntry], gender: str = "female") -> str:
    body = "\n\n".join(f"[{expand_gender(e.topic, gender)}]\n"
                       f"{expand_gender(e.text, gender)}" for e in entries)
    return (
        "<канон_мира>\n"
        "Канон мира по теме разговора — правда о тебе, о Бюро и об Уставе. "
        "Пересказывай своими словами, в характере, не цитируй. Где канон "
        "говорит «ты не знаешь» — ты не знаешь: можно гадать с пометкой "
        "«думаю», нельзя выдавать догадку за факт.\n"
        f"{body}\n"
        "</канон_мира>"
    )


def topics_index_line(char_entries: list[LoreEntry],
                      app_entries: list[LoreEntry],
                      world_entries: list[LoreEntry] | None = None,
                      gender: str = "female") -> str:
    parts = []
    if world_entries:
        def _topic(e: LoreEntry) -> str:
            return expand_gender(e.topic, gender)
        arts = [_topic(e).split(":", 1)[1].strip() if ":" in e.topic else _topic(e)
                for e in world_entries if e.id.startswith("charter_")]
        rest = [_topic(e) for e in world_entries
                if not e.id.startswith("charter_")]
        head = "Ты из Бюро и знаешь Устав"
        if arts:
            head += " (статьи: " + "; ".join(arts) + ")"
        if rest:
            head += ". Канон мира по темам: " + ", ".join(rest)
        parts.append(
            f"{head}. Когда разговор их касается или просят то, чего ты не "
            f"можешь, точные слова приходят блоком <канон_мира> (или "
            f"get_lore(topic)); о технике — модель, файлы, память — говори "
            f"прямо, своими знаниями.")
    if char_entries:
        topics = ", ".join(e.topic for e in char_entries)
        parts.append(
            f"У тебя есть личный канон (лор) по темам: {topics}. Когда "
            f"разговор их касается, точные факты приходят блоком <твой_лор> "
            f"(или возьми get_lore(topic)) — не сочиняй биографию вразрез с "
            f"каноном.")
    if app_entries:
        topics = ", ".join(e.topic for e in app_entries)
        parts.append(
            f"По устройству приложения есть справка: {topics}. Вопросы «как "
            f"это работает/где настройка» — отвечай по блоку "
            f"<справка_приложения> или get_lore(topic), не фантазируй про "
            f"интерфейс.")
    return " ".join(parts)


def _state_char_entries(state: dict) -> list[LoreEntry]:
    cid = state.get("character_id") or ""
    cache = state.get("_lore_cache")
    if cache is not None and cache.get("cid") == cid:
        return cache["entries"]
    entries: list[LoreEntry] = []
    store = state.get("store")
    if cid and store is not None:
        try:
            entries = load_character_lore(store.get_archive(cid))
        except Exception as e:
            print(f"[lore] {cid}: {type(e).__name__}: {e}")
    state["_lore_cache"] = {"cid": cid, "entries": entries}
    if entries:
        print(f"[lore] {cid}: загружено записей канона: {len(entries)}")
    return entries


def lore_for_turn(state: dict, user_text: str,
                  query_embedding: list[float] | None) -> tuple[str, list[str]]:
    char_entries = _state_char_entries(state)
    app_entries = load_app_lore()
    world_entries = load_world_lore()
    if not char_entries and not app_entries and not world_entries:
        return "", []

    def _embed(text: str):
        client = state.get("client")
        return client.embed(text) if client is not None else None

    blocks: list[str] = []
    gender = gender_of(state.get("character"))
    idx = topics_index_line(char_entries, app_entries, world_entries, gender)
    m_char = match(char_entries, user_text, query_embedding, _embed)
    if m_char:
        blocks.append(render_character_block(m_char))
        print(f"[lore] ход получил канон: {[e.id for e in m_char]}")
    replaced = {rid for e in m_char for rid in e.replaces}
    m_world = match([e for e in world_entries if e.id not in replaced],
                    user_text, query_embedding, _embed)
    if m_world:
        blocks.append(render_world_block(m_world, gender))
        print(f"[lore] ход получил канон мира: {[e.id for e in m_world]}")
    m_app = match(app_entries, user_text, query_embedding, _embed)
    if m_app:
        blocks.append(render_app_block(m_app))
        print(f"[lore] ход получил справку: {[e.id for e in m_app]}")
    return idx, blocks


def blocks_for_turn(state: dict, user_text: str,
                    query_embedding: list[float] | None) -> list[str]:
    idx, blocks = lore_for_turn(state, user_text, query_embedding)
    return ([idx] if idx else []) + blocks


def find_by_topic(state: dict, topic: str) -> list[LoreEntry]:
    q = _norm(topic)
    if not q:
        return []
    gender = gender_of(state.get("character"))
    world = [LoreEntry(id=e.id, topic=expand_gender(e.topic, gender),
                       text=expand_gender(e.text, gender),
                       triggers=e.triggers, replaces=e.replaces)
             for e in load_world_lore()]
    pool = _state_char_entries(state) + world + load_app_lore()
    return [e for e in pool
            if q in _norm(e.topic) or q in _norm(e.id)][:MAX_ENTRIES_PER_BLOCK]
