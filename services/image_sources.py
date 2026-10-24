from __future__ import annotations

MAX_SOURCES = 12


def get_sources(identity) -> list[dict]:
    if identity is None:
        return []
    raw = (getattr(identity, "assistant_prefs", None) or {}).get("image_sources")
    return list(raw) if isinstance(raw, list) else []


def set_source(identity, topic: str, site: str) -> tuple[str, dict | None]:
    from services.web import normalize_domain
    topic = (topic or "").strip().lower()
    dom = normalize_domain(site)
    if not topic:
        return "bad", None
    sources = get_sources(identity)
    idx = next((i for i, s in enumerate(sources)
                if str(s.get("topic", "")).lower() == topic), None)

    if not dom:
        if idx is None:
            return "noop", None
        removed = sources.pop(idx)
        _persist(identity, sources)
        return "removed", removed

    entry = {"topic": topic, "site": dom}
    if idx is not None:
        sources[idx] = entry
        _persist(identity, sources)
        return "updated", entry
    if len(sources) >= MAX_SOURCES:
        return "full", None
    sources.append(entry)
    _persist(identity, sources)
    return "added", entry


def _persist(identity, sources: list[dict]) -> None:
    prefs = dict(getattr(identity, "assistant_prefs", None) or {})
    prefs["image_sources"] = sources
    identity.assistant_prefs = prefs
    try:
        identity.save()
    except Exception as e:
        print(f"[img-src] identity.save fail: {type(e).__name__}: {e}")


_IMG_REQUEST_WORDS = ("мем", "картинк", "арт", "фото", "обои", "изображени",
                      "гифк", "пикч", "открытк", "скрин")


def looks_like_image_request(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in _IMG_REQUEST_WORDS)


def resolve_site(identity, topic_or_query: str) -> str:
    q = (topic_or_query or "").strip().lower()
    if not q:
        return ""
    for s in get_sources(identity):
        t = str(s.get("topic", "")).lower()
        if t and (t in q or q in t):
            return str(s.get("site", ""))
    return ""


def format_sources_prompt(identity) -> str:
    sources = get_sources(identity)
    if not sources:
        return ""
    lines = ["<источники_картинок>",
             "Господин задал, где искать картинки по темам. Если его запрос "
             "про такую тему — передавай site в search_images:"]
    for s in sources:
        lines.append(f"- {s.get('topic')} → {s.get('site')}")
    lines.append("</источники_картинок>")
    return "\n".join(lines)
