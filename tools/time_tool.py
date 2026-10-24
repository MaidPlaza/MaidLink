from __future__ import annotations

from datetime import datetime

from tools.registry import ToolContext


_DAYS_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
_MONTHS_RU = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def handle_get_time(args: dict, ctx: ToolContext) -> str:
    now = datetime.now()
    h = now.hour
    if h < 5 or h >= 23:
        period = "ночь"
    elif h < 11:
        period = "утро"
    elif h < 17:
        period = "день"
    else:
        period = "вечер"
    time_str = f"{now.hour}:{now.minute:02d}"
    date_human = f"{now.day} {_MONTHS_RU[now.month - 1]} {now.year}"
    iso_str = now.strftime("%Y-%m-%dT%H:%M")
    if ctx.debug:
        print(f"[MEM] get_time() → {iso_str}")
    return (
        f"Сейчас {time_str}, {period}, {_DAYS_RU[now.weekday()]}, "
        f"{date_human}.\n"
        f"ISO-форма для расчётов: {iso_str}."
    )
