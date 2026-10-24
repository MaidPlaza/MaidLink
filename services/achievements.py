from __future__ import annotations

import time
from dataclasses import dataclass, replace

from services import gacha

TIER_BOUNDS = (0.1, 0.3, 0.6, 0.95)
ROMAN = ("I", "II", "III", "IV", "V")
REL_AXES = (("trust", "Доверие"), ("closeness", "Близость"), ("respect", "Уважение"))


@dataclass(frozen=True)
class Achievement:
    id: str
    title: str
    hint: str
    tickets: int
    kind: str
    hidden: bool = False
    axis: str = ""
    level: int = 0


TUTORIAL: tuple[Achievement, ...] = (
    Achievement("first_web_search", "Первый поиск в интернете",
                "Попроси поискать что-нибудь в интернете.", 1, "tutorial"),
    Achievement("first_anime_art", "Первый аниме-арт",
                "Попроси найти аниме-картинку по описанию.", 1, "tutorial"),
    Achievement("first_photo", "Первый снимок",
                "Попроси сделать снимок — персонаж нарисует себя.", 1, "tutorial"),
    Achievement("first_style", "Первая обновка в образе",
                "Попроси примерить что-то из открытого: укладку, макияж, украшение.",
                1, "tutorial"),
    Achievement("first_outfit", "Первое переодевание",
                "Подготовь наряд в гардеробе и попроси переодеться.", 1, "tutorial"),
    Achievement("first_note", "Первая заметка",
                "Попроси записать что-нибудь в заметки.", 1, "tutorial"),
    Achievement("first_reminder", "Первое напоминание",
                "Попроси напомнить о чём-нибудь к нужному времени.", 1, "tutorial"),
    Achievement("first_gallery", "Первый снимок в галерее",
                "Отметь сердечком снимок в чате — он попадёт в галерею карточки.",
                1, "tutorial"),
    Achievement("first_document", "Первый документ",
                "Приложи к разговору документ кнопкой «+» у поля ввода.", 1, "tutorial"),
)

RELATION: tuple[Achievement, ...] = tuple(
    Achievement(f"rel_{axis}_{level}", f"{label}: уровень {ROMAN[level - 1]}",
                f"Ось «{label}» поднимается до уровня {ROMAN[level - 1]}.",
                level, "relation", axis=axis, level=level)
    for axis, label in REL_AXES for level in range(2, 6)
)

HIDDEN: tuple[Achievement, ...] = (
    Achievement("streak_7", "Неделя рядом", "Семь дней подряд с персонажем.", 3, "hidden", True),
    Achievement("streak_30", "Месяц рядом", "Тридцать дней подряд.", 7, "hidden", True),
    Achievement("sessions_10", "Десятая сессия", "Десять сессий.", 2, "hidden", True),
    Achievement("sessions_50", "Полсотни сессий", "Пятьдесят сессий.", 5, "hidden", True),
    Achievement("sessions_100", "Сотая сессия", "Сто сессий.", 7, "hidden", True),
    Achievement("images_10", "Десятый снимок", "Десять снимков.", 2, "hidden", True),
    Achievement("images_100", "Сотый снимок", "Сто снимков.", 5, "hidden", True),
    Achievement("messages_1000", "Тысяча сообщений", "Тысяча сообщений на двоих.", 5, "hidden", True),
    Achievement("longest_100", "Долгий разговор", "Сто сообщений за одну сессию.", 3, "hidden", True),
    Achievement("proactive_5", "На связи", "Ответить на пять весточек персонажа.", 2, "hidden", True),
    Achievement("collection_25", "Коллекционер", "Двадцать пять открытых обновок.", 2, "hidden", True),
    Achievement("collection_50", "Знаток образа", "Пятьдесят открытых обновок.", 3, "hidden", True),
    Achievement("collection_100", "Полный образ", "Сто открытых обновок.", 5, "hidden", True),
    Achievement("legendary_first", "Первая легенда", "Выпала легендарная вещь.", 2, "hidden", True),
    Achievement("gesture_first", "Первое прикосновение", "Погладить персонажа по голове.", 2, "hidden", True),
)

def _scaled(items: tuple[Achievement, ...]) -> tuple[Achievement, ...]:
    return tuple(replace(a, tickets=a.tickets * gacha.TICKET_RATE) for a in items)


TUTORIAL = _scaled(TUTORIAL)
RELATION = _scaled(RELATION)
HIDDEN = _scaled(HIDDEN)

ALL: tuple[Achievement, ...] = TUTORIAL + RELATION + HIDDEN
BY_ID: dict[str, Achievement] = {a.id: a for a in ALL}

_TOOL_RULES = {
    "web_search": ("first_web_search", lambda r: True),
    "search_anime_art": ("first_anime_art", lambda r: True),
    "style_self": ("first_style", lambda r: r.startswith("Готово")),
    "change_outfit": ("first_outfit", lambda r: r.startswith("Принято")),
    "write_note": ("first_note", lambda r: "создана" in r),
    "append_note": ("first_note", lambda r: r.startswith("Заметка") and "переполн" not in r),
    "set_reminder": ("first_reminder",
                     lambda r: "поставлено" in r or r.startswith("Хорошо, ")),
}


def _block(identity) -> dict | None:
    if not gacha.has_gacha(identity):
        return None
    gacha.ensure_state(identity)
    return identity.gacha.setdefault("achievements", {})


def earned(identity) -> dict:
    b = _block(identity)
    return dict(b) if b else {}


def award(identity, aid: str, now: float | None = None) -> Achievement | None:
    a = BY_ID.get(aid)
    b = _block(identity)
    if a is None or b is None or aid in b:
        return None
    gacha.grant(identity, a.tickets, aid)
    b[aid] = {"at": now if now is not None else time.time(), "tickets": a.tickets}
    return a


def on_tool_result(identity, name: str, result) -> list[Achievement]:
    rule = _TOOL_RULES.get(name or "")
    if rule is None:
        return []
    aid, ok = rule
    text = str(result or "").strip()
    if not ok(text):
        return []
    a = award(identity, aid)
    return [a] if a else []


def tier_index(value: float) -> int:
    return sum(1 for b in TIER_BOUNDS if float(value or 0.0) >= b)


def check_progress(identity, *, axis_values: dict | None = None,
                   unlocked: int = 0, legendary: bool = False,
                   now: float | None = None) -> list[Achievement]:
    if _block(identity) is None:
        return []
    out: list[Achievement] = []

    def hit(aid: str) -> None:
        a = award(identity, aid, now)
        if a:
            out.append(a)

    for axis, _label in REL_AXES:
        level = tier_index((axis_values or {}).get(axis, 0.0)) + 1
        for n in range(2, level + 1):
            hit(f"rel_{axis}_{n}")
    st = getattr(identity, "stats", None) or {}
    g = lambda k: int(st.get(k, 0) or 0)
    best_streak = max(g("best_streak_days"), g("streak_days"))
    if best_streak >= 7:
        hit("streak_7")
    if best_streak >= 30:
        hit("streak_30")
    for n in (10, 50, 100):
        if g("sessions") >= n:
            hit(f"sessions_{n}")
    for n in (10, 100):
        if g("images") >= n:
            hit(f"images_{n}")
    if g("messages_user") + g("messages_assistant") >= 1000:
        hit("messages_1000")
    if g("longest_messages") >= 100:
        hit("longest_100")
    if g("proactive_answered") >= 5:
        hit("proactive_5")
    for n in (25, 50, 100):
        if unlocked >= n:
            hit(f"collection_{n}")
    if legendary:
        hit("legendary_first")
    return out


def counts(identity) -> dict:
    e = earned(identity)
    return {"earned": len(e), "total": len(ALL),
            "tickets_earned": sum(int(v.get("tickets", 0) or 0) for v in e.values())}


def report(identity) -> dict:
    e = earned(identity)

    def row(a: Achievement) -> dict:
        got = e.get(a.id)
        return {"id": a.id, "title": a.title, "hint": a.hint, "tickets": a.tickets,
                "earned": got is not None, "at": (got or {}).get("at")}

    relations = []
    for axis, label in REL_AXES:
        relations.append({
            "axis": axis, "label": label,
            "levels": [dict(row(a), level=a.level, roman=ROMAN[a.level - 1])
                       for a in RELATION if a.axis == axis],
        })
    hidden_earned = [row(a) for a in HIDDEN if a.id in e]
    hidden_earned.sort(key=lambda r: r.get("at") or 0)
    return {
        "daily": {"per_day": gacha.DAILY_TICKETS, "cap": gacha.TICKET_CAP,
                  "sphere_every": gacha.SPHERE_EVERY},
        "tutorial": [row(a) for a in TUTORIAL],
        "relations": relations,
        "hidden": hidden_earned,
        "hidden_total": len(HIDDEN),
        **counts(identity),
    }
