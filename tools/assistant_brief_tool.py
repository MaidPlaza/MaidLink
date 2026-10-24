from __future__ import annotations

from tools.registry import ToolContext


def handle_configure_brief(args: dict, ctx: ToolContext) -> str:
    idy = getattr(ctx, "identity", None)
    if idy is None:
        return "Настройки сводки недоступны (нет активного персонажа)."
    from services import assistant_brief as ab

    def _b(key):
        v = args.get(key)
        if isinstance(v, str):
            v = v.strip().lower() in ("1", "true", "yes", "да", "on")
        return None if v is None else bool(v)

    enabled = _b("enabled")
    include_patch = {k: _b(k) for k in ("weather", "plans", "reminders",
                                        "promises")}
    include_patch = {k: v for k, v in include_patch.items() if v is not None}
    if enabled is None and not include_patch:
        sess = getattr(getattr(ctx, "memory", None), "_session_state_ref", None)
        if sess is not None and sess.get("brief_offer_active"):
            enabled = True
        else:
            st = ab.brief_state(idy)
            inc = ", ".join(k for k, v in st["include"].items() if v) or "ничего"
            return (f"Текущее состояние сводки: "
                    f"{'включена' if st['enabled'] else 'выключена'}; состав: {inc}.")

    st = ab.set_brief(idy, enabled=enabled, include_patch=include_patch)
    parts = []
    if enabled is True:
        parts.append("утренняя сводка ВКЛЮЧЕНА — теперь при первом появлении "
                     "Господина после долгого перерыва ты сама коротко "
                     "сориентируешь его по дню")
    elif enabled is False:
        parts.append("утренняя сводка ВЫКЛЮЧЕНА — больше не присылаешь её")
    for k, ru in (("weather", "погода"), ("plans", "планы"),
                  ("reminders", "напоминания"), ("promises", "обещания")):
        if k in include_patch:
            parts.append(f"{ru}: {'в составе' if st['include'][k] else 'исключена' if ru == 'погода' else 'исключены'}")
    return "Готово: " + "; ".join(parts) + "."


CONFIGURE_BRIEF_SCHEMA = {
    "name": "configure_brief",
    "description": (
        "Включить/выключить или настроить состав твоей утренней сводки дня. "
        "Вызывай ТОЛЬКО когда Господин ЯВНО согласился на услугу, попросил "
        "отключить её или изменить состав («без погоды»). НЕ включай по "
        "собственной инициативе."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "enabled": {"type": "boolean",
                        "description": "true — включить сводку (Господин согласился); false — выключить (попросил)"},
            "weather": {"type": "boolean", "description": "показывать погоду в сводке"},
            "plans": {"type": "boolean", "description": "показывать планы с дедлайнами"},
            "reminders": {"type": "boolean", "description": "показывать напоминания дня"},
            "promises": {"type": "boolean", "description": "показывать его открытые обещания"},
        },
        "required": [],
    },
}
