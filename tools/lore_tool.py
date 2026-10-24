from __future__ import annotations

from tools.registry import ToolContext


def handle_get_lore(args: dict, ctx: ToolContext) -> str:
    topic = str(args.get("topic") or "").strip()
    if not topic:
        return ("Укажи topic — тему из твоего лор-индекса (например тему из "
                "строки «канон по темам: …» в твоём промпте).")
    sess = getattr(getattr(ctx, "memory", None), "_session_state_ref", None)
    if sess is None:
        return "Лор недоступен (нет активной сессии)."
    from persona.lore import find_by_topic
    entries = find_by_topic(sess, topic)
    if not entries:
        return (f"По теме {topic!r} канона нет. Не выдумывай факты вместо "
                f"него: скажи честно, что точно не знаешь/не помнишь.")
    parts = [f"[{e.topic}]\n{e.text}" for e in entries]
    return ("Твой канон по запрошенной теме (перескажи своими словами, в "
            "своём тоне; не противоречь):\n\n" + "\n\n".join(parts))


GET_LORE_SCHEMA = {
    "name": "get_lore",
    "description": (
        "Достать твой личный канон (лор), канон мира (Бюро, Устав) или "
        "справку приложения по теме. Темы перечислены в твоём промпте "
        "(«канон по темам», «канон мира по темам», «справка»). "
        "Зови, когда просят рассказать подробнее о тебе/о приложении, а "
        "нужных фактов в контексте нет."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {"type": "string",
                      "description": "тема из индекса (или её часть)"},
        },
        "required": ["topic"],
    },
}
