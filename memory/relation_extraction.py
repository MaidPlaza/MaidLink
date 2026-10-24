from __future__ import annotations


def _build_extraction_system(entity_cards, char_name: str, honorific: str) -> str:
    from memory.entity_schema import RELATION_PREDICATES
    from prompts.reflection import RELATION_EXTRACT_PROMPT
    ents = "\n".join(
        f"  - «{c.title}» ({(c.details or {}).get('entity_type', '')})"
        for c in entity_cards) or "  (нет)"
    preds = ", ".join(RELATION_PREDICATES)
    return RELATION_EXTRACT_PROMPT.format(char_name=char_name, ents=ents, preds=preds)


def apply_relation_directives(items, memory) -> dict:
    import time as _t

    import tools.link_entities as le
    from tools.semantic import SemanticDeps

    deps = SemanticDeps(memory=memory, now=_t.time(),
                        debug=getattr(memory, "debug", False))
    res = {"linked": 0, "skipped": 0}
    for item in (items or []):
        if not isinstance(item, dict):
            continue
        r = le._link_executor(item, deps)
        res["linked" if r.ok else "skipped"] += 1
    return res


def extract_relations_from_session(messages, memory, char_name: str = "",
                                   honorific: str = "Господин",
                                   gender: str = "female") -> dict:
    from memory.entity_schema import ENTITY_TYPE_TOPIC, is_entity_card
    from memory.conversation import tail_by_tokens
    from memory.unified import (_parse_llm_json, format_dialogue,
                                EXTRACT_TOKEN_BUDGET)

    if not getattr(memory, "_client", None) or len(messages or []) < 2:
        return {"linked": 0, "skipped": 0}
    cards = [r for r in memory.records
             if is_entity_card(r) and not getattr(r, "is_forgotten", False)
             and (r.details or {}).get("entity_type") != ENTITY_TYPE_TOPIC]
    if len(cards) < 2:
        return {"linked": 0, "skipped": 0}

    system = _build_extraction_system(
        cards, char_name or "персонаж", honorific or "пользователь")
    convo = format_dialogue(tail_by_tokens(messages, EXTRACT_TOKEN_BUDGET),
                            honorific or "Господин", char_name or "")
    try:
        raw = memory._client.chat(
            messages=[{"role": "user", "content": convo}],
            system=system, thinking=False, label="Извлечение связей (session-end)")
    except Exception as e:
        print(f"[relations] extract chat error: {type(e).__name__}: {e}")
        return {"linked": 0, "skipped": 0}

    data = _parse_llm_json(raw, debug=getattr(memory, "debug", False))
    if not data:
        return {"linked": 0, "skipped": 0}
    return apply_relation_directives(data.get("relations", []), memory)
