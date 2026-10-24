from __future__ import annotations

import time
from datetime import datetime

from services.log_privacy import priv
from tools.registry import TIER_CONTEXTUAL, Tool, ToolContext

MIN_MINUTES = 0.2
MAX_MINUTES = 12 * 60


def handle_set_timer(args: dict, ctx: ToolContext) -> str:
    mem = ctx.memory
    if mem is None:
        return "Память недоступна — таймер поставить не могу."
    try:
        minutes = float(args.get("minutes"))
    except (TypeError, ValueError):
        return "Скажи длительность числом минут: set_timer(minutes=20, label=\"курица\")."
    if not (MIN_MINUTES <= minutes <= MAX_MINUTES):
        return (f"Длительность вне разумного ({minutes:g} мин) — от "
                f"{MIN_MINUTES:g} до {MAX_MINUTES:g} минут. Дольше — set_reminder.")
    label = str(args.get("label") or "").strip() or "таймер"

    fire_at = time.time() + minutes * 60
    mem.add_record(
        type="напоминание",
        title=f"Таймер: {label}"[:50],
        details={
            "kind": "timer",
            "description": label,
            "duration_min": minutes,
            "fire_at": fire_at,
            "fire_at_iso": datetime.fromtimestamp(fire_at).strftime("%Y-%m-%d %H:%M"),
            "message_text": "", "message_sent": False, "message_failed": False,
            "card_shown": False, "acknowledged": False, "expired": False,
            "delivered": False,
            "last_notification_at": 0.0, "notification_count": 0,
        },
        importance=0.7, embed_text=f"таймер {label}",
    )
    if minutes == int(minutes):
        dur = f"{int(minutes)} мин"
    else:
        dur = f"{int(minutes * 60)} сек" if minutes < 1 else f"{minutes:g} мин"
    if ctx.debug:
        print(f"[timer] set: «{priv(label)}» +{dur}")
    return (f"Таймер поставлен: «{label}», {dur} — когда сработает, ты дашь "
            f"знать сама (даже посреди разговора). Отмена — cancel_reminder.")


SET_TIMER_TOOL = Tool(
    name="set_timer",
    tier=TIER_CONTEXTUAL,
    capability="reminder",
    triggers=["таймер", "засеки", "отсчитай", "через минут"],
    schema={
        "name": "set_timer",
        "description": ("Поставить короткий таймер на N минут («засеки 20 минут — "
                        "курица в духовке»). Сработает точно и даст знать даже "
                        "посреди разговора. Для дат/времени суток — set_reminder."),
        "parameters": {
            "type": "object",
            "properties": {
                "minutes": {"type": "number",
                            "description": "длительность в минутах (можно дробную: 0.5 = 30 сек)"},
                "label": {"type": "string",
                          "description": "короткая метка, о чём таймер («курица»)"},
            },
            "required": ["minutes"],
        },
    },
    handler=handle_set_timer,
    summary=("set_timer(minutes, label) — короткий таймер; сработает даже посреди "
             "разговора (панелька + твоя реплика)"),
    help=(
        "set_timer(minutes, label) — короткий таймер.\n\n"
        "  minutes — число минут (дробные можно: 0.5 = 30 сек; максимум 12 часов)\n"
        "  label   — о чём («курица», «стирка»)\n\n"
        "Когда сработает — в чат придёт панелька, и ты сразу прокомментируешь "
        "сама, даже если идёт разговор. Посмотреть активные — list_reminders(); "
        "отменить — cancel_reminder.\n"
        "НЕ путай: «завтра в 15:00» / «каждый вечер» — это set_reminder."
    ),
)
