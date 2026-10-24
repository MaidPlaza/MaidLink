from __future__ import annotations

from services.log_privacy import priv


def _format_open_list(open_loops) -> str:
    from memory.loops import LOOP_SUBJ_MINE
    lines = []
    for l in open_loops:
        d = l.details or {}
        owner = "ассистента" if d.get("subject") == LOOP_SUBJ_MINE else "собеседника"
        lines.append(f"  - «{l.title}» ({d.get('kind', '')} {owner})")
    return "\n".join(lines) or "  (пока нет)"


def _build_extraction_system(open_loops, char_name: str, honorific: str) -> str:
    from prompts.reflection import LOOP_EXTRACT_PROMPT
    return LOOP_EXTRACT_PROMPT.format(
        char_name=char_name, honorific=honorific, open_list=_format_open_list(open_loops))


def _build_close_system(open_loops, char_name: str, honorific: str) -> str:
    from prompts.reflection import LOOP_CLOSE_PROMPT
    return LOOP_CLOSE_PROMPT.format(
        char_name=char_name, honorific=honorific, open_list=_format_open_list(open_loops))


def apply_loop_directives(items, memory) -> dict:
    import time as _t

    import tools.close_loop as _cl
    import tools.track_loop as _tl
    from tools.semantic import SemanticDeps

    deps = SemanticDeps(memory=memory, now=_t.time(),
                        debug=getattr(memory, "debug", False))
    res = {"opened": 0, "closed": 0, "refreshed": 0, "skipped": 0}
    for item in (items or []):
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or "").strip().lower()
        if action == "open":
            r = _tl._loop_executor(item, deps)
            if r.ok:
                if r.data and r.data.get("refreshed"):
                    res["refreshed"] += 1
                else:
                    res["opened"] += 1
            else:
                res["skipped"] += 1
        elif action == "close":
            r = _cl._close_executor(item, deps)
            res["closed" if r.ok else "skipped"] += 1
        else:
            res["skipped"] += 1
    return res


def extract_loops_from_session(messages, memory, char_name: str = "",
                               honorific: str = "Господин",
                               gender: str = "female") -> dict:
    from memory.conversation import tail_by_tokens
    from memory.unified import (_parse_llm_json, format_dialogue,
                                EXTRACT_TOKEN_BUDGET)

    totals = {"opened": 0, "closed": 0, "refreshed": 0, "skipped": 0}
    if not getattr(memory, "_client", None) or len(messages or []) < 2:
        return totals

    convo = format_dialogue(tail_by_tokens(messages, EXTRACT_TOKEN_BUDGET),
                            honorific or "Господин", char_name or "")
    name = char_name or "персонаж"
    hon = honorific or "пользователь"
    debug = getattr(memory, "debug", False)

    def _round(system: str, label: str) -> None:
        try:
            raw = memory._client.chat(
                messages=[{"role": "user", "content": convo}],
                system=system, thinking=False, label=label)
        except Exception as e:
            print(f"[loops] {label} chat error: {type(e).__name__}: {e}")
            return
        data = _parse_llm_json(raw, debug=debug)
        directives = data.get("loops", []) if isinstance(data, dict) else []
        if directives:
            print(f"[loops] {label}: директив {len(directives)} "
                  f"{priv(str(directives), 200)}")
        r = apply_loop_directives(directives, memory)
        for k in totals:
            totals[k] += r.get(k, 0)

    open_now = memory.get_open_loops()
    if open_now:
        _round(_build_close_system(open_now, name, hon), "Закрытие петель (session-end)")
    _round(_build_extraction_system(memory.get_open_loops(), name, hon),
           "Извлечение петель (session-end)")
    return totals
