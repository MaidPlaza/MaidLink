from __future__ import annotations

from services.log_privacy import priv


def _build_extraction_system(char_name: str, honorific: str) -> str:
    from prompts.reflection import TOPIC_EXTRACT_PROMPT
    return TOPIC_EXTRACT_PROMPT.format(char_name=char_name, honorific=honorific)


def apply_topic_opinions(items, memory) -> dict:
    res = {"saved": 0, "skipped": 0}
    for item in (items or []):
        if not isinstance(item, dict):
            res["skipped"] += 1
            continue
        topic = (item.get("topic") or "").strip().strip("«»\"'").strip()
        opinion = (item.get("opinion") or "").strip()
        if not topic or not opinion:
            res["skipped"] += 1
            continue
        try:
            memory.upsert_entity("тема", topic, my_opinion=opinion[:240])
            res["saved"] += 1
        except Exception as e:
            print(f"[topics] upsert fail «{priv(topic)}»: {e}")
            res["skipped"] += 1
    return res


from prompts.reflection import (
    _FORMATION_TASK,
)


def form_topic_opinions_from_material(client, persona, memory, material_text: str) -> dict:
    from memory.unified import _parse_llm_json
    from persona.prompt_builder import build_system_prompt
    from persona.prompt_context import ContextSpec

    if not client or not (material_text or "").strip():
        return {"saved": 0, "skipped": 0}
    try:
        sysp = build_system_prompt(persona, spec=ContextSpec.opinion(), memory=memory)
    except Exception as e:
        print(f"[topics-B] не собрать персона-линзу: {e}")
        return {"saved": 0, "skipped": 0}
    task = _FORMATION_TASK.format(material=material_text[:3000])
    try:
        raw = client.chat(messages=[{"role": "user", "content": task}],
                          system=sysp, thinking=True,
                          label="Формирование мнений о темах (консолидация)")
    except Exception as e:
        print(f"[topics-B] chat error: {type(e).__name__}: {e}")
        return {"saved": 0, "skipped": 0}
    data = _parse_llm_json(raw, debug=getattr(memory, "debug", False))
    if not data:
        return {"saved": 0, "skipped": 0}
    return apply_topic_opinions(data.get("topics", []), memory)


def extract_topic_opinions_from_session(messages, memory, char_name: str = "",
                                        honorific: str = "Господин",
                                        gender: str = "female") -> dict:
    from memory.conversation import tail_by_tokens
    from memory.unified import (_parse_llm_json, format_dialogue,
                                EXTRACT_TOKEN_BUDGET)

    if not getattr(memory, "_client", None) or len(messages or []) < 2:
        return {"saved": 0, "skipped": 0}
    system = _build_extraction_system(char_name or "персонаж", honorific or "пользователь")
    convo = format_dialogue(tail_by_tokens(messages, EXTRACT_TOKEN_BUDGET),
                            honorific or "Господин", char_name or "")
    try:
        raw = memory._client.chat(
            messages=[{"role": "user", "content": convo}],
            system=system, thinking=False, label="Извлечение тем-мнений (session-end)")
    except Exception as e:
        print(f"[topics] extract chat error: {type(e).__name__}: {e}")
        return {"saved": 0, "skipped": 0}
    data = _parse_llm_json(raw, debug=getattr(memory, "debug", False))
    if not data:
        return {"saved": 0, "skipped": 0}
    return apply_topic_opinions(data.get("topics", []), memory)
