from __future__ import annotations

import random
import time

BASE_CHANCE_BY_TIER: dict[str, float] = {
    "estranged": 0.01,
    "distant": 0.015,
    "warming": 0.03,
    "close": 0.06,
    "intimate": 0.09,
}
_BASE_DEFAULT = 0.03
CONTACT_FLOOR_SEC = 3600.0
RAMP_FULL_SEC = 3 * 3600.0
RAMP_START = 0.5
DAY_PENALTY = 0.4
IGNORE_PENALTY = 0.6
SKIP_COOLDOWN_SEC = 2 * 3600.0
DAY_START_HOUR = 5

IGNORE_KEY = "proactive_ignore"
HOOK_KEY = "proactive_hook"
SENT_KEY = "proactive_sent"
_SENT_KEEP_SEC = 3 * 86400.0


def ignore_streak(event_log: dict | None) -> int:
    try:
        return int(((event_log or {}).get(IGNORE_KEY) or {}).get("streak", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _sent_times(event_log: dict | None) -> list[float]:
    try:
        return [float(t) for t in (((event_log or {}).get(SENT_KEY) or {}).get("times") or [])]
    except (TypeError, ValueError):
        return []


def record_sent(event_log: dict, now: float) -> None:
    times = [t for t in _sent_times(event_log) if now - t < _SENT_KEEP_SEC]
    times.append(float(now))
    event_log[SENT_KEY] = {"times": times}


def last_sent_at(event_log: dict | None) -> float:
    return max(_sent_times(event_log), default=0.0)


def _day_key(ts: float) -> tuple[int, int]:
    try:
        lt = time.localtime(ts - DAY_START_HOUR * 3600)
    except (OSError, OverflowError, ValueError):
        return 0, 0
    return lt.tm_year, lt.tm_yday


def sent_today(event_log: dict | None, now: float) -> int:
    today = _day_key(now)
    return sum(1 for t in _sent_times(event_log) if _day_key(t) == today)


def contact_ramp(since_contact: float) -> float:
    if since_contact < CONTACT_FLOOR_SEC:
        return 0.0
    span = RAMP_FULL_SEC - CONTACT_FLOOR_SEC
    return RAMP_START + (1.0 - RAMP_START) * min(1.0, (since_contact - CONTACT_FLOOR_SEC) / span)


def penalty(sent: int, streak: int) -> float:
    return DAY_PENALTY ** max(0, sent) * IGNORE_PENALTY ** max(0, streak)


def decision_chance(tier: str, since_contact: float, *, sent: int = 0,
                    streak: int = 0, scale: float = 1.0) -> float:
    ramp = contact_ramp(since_contact)
    if ramp <= 0.0:
        return 0.0
    p = BASE_CHANCE_BY_TIER.get(tier, _BASE_DEFAULT) * ramp * penalty(sent, streak) * scale
    return max(0.0, min(1.0, p))


HOOK_WEIGHTS: dict[str, int] = {
    "loop": 3,
    "thought": 3,
    "discovery": 2,
    "plain": 2,
    "photo": 1,
}


def choose_hook(available: list[str], last_kind: str = "",
                rng: random.Random | None = None) -> str:
    pool = [k for k in available if k in HOOK_WEIGHTS]
    if not pool:
        return "plain"
    if last_kind in pool and len(pool) > 1:
        pool = [k for k in pool if k != last_kind]
    weights = [HOOK_WEIGHTS[k] for k in pool]
    return (rng or random).choices(pool, weights=weights, k=1)[0]


def _clip(text: str, limit: int = 300) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > limit // 2 else cut).rstrip(",.;:— ") + "…"


def hook_block(kind: str, data: dict | None, honorific: str) -> str:
    d = data or {}
    if kind == "plan":
        what = d.get("description") or d.get("title") or "что-то важное"
        where = f" ({d['where']})" if d.get("where") else ""
        if d.get("when") == "tomorrow":
            frame = (f"завтра у {honorific}а по плану: «{what}»{where}. Можешь "
                     f"написать об этом — пожелать удачи заранее, спросить, "
                     f"какой настрой, или мягко напомнить")
        elif d.get("evening"):
            frame = (f"сегодня у {honorific}а было запланировано: «{what}»{where}, "
                     f"и день уже к вечеру. Можешь спросить, как прошло")
        else:
            frame = (f"сегодня у {honorific}а по плану: «{what}»{where}. Можешь "
                     f"пожелать удачи или спросить, как настрой")
        return f"Повод: {frame} — в своём характере, без допроса."
    if kind == "loop":
        soft = (" (недавно уже заговаривала об этом — если поднимешь снова, "
                "не дави)" if d.get("raised") else "")
        return (f"Повод: {honorific} делился темой «{d.get('title', '')}» — "
                f"можно мягко спросить, как с этим дела{soft}.")
    if kind == "thought":
        return ("Повод: недавно ты записала у себя мысль: "
                f"«{_clip(d.get('text', ''))}». Если она правда просится "
                "наружу — поделись ею своими словами; нет — не вымучивай.")
    if kind == "discovery":
        return (f"Повод: тебя в последнее время занимает «{d.get('interest', '')}». "
                "Можешь прямо сейчас сходить в поиск (web_search, а если это "
                "про аниме — search_anime_art), найти что-то любопытное по теме "
                "и поделиться находкой (картинку покажет show_image c номером "
                "из выдачи). Принеси одну находку, не лекцию.")
    if kind == "photo":
        return ("Повод: можешь предложить ему свой снимок — сначала спроси, "
                "хочет ли (draw вызывай только после его согласия), — или "
                "просто написать пару тёплых слов.")
    return ("Повода нет — просто тишина. Можешь коротко дать о себе знать "
            "или спросить, как он; если кажется, что что-то было — поищи "
            "повод в памяти (search_memory).")


def ignore_hint(streak: int) -> str:
    if streak <= 0:
        return ""
    tail = "прошлая весточка осталась без ответа" if streak == 1 else \
        f"последние весточки ({streak}) остались без ответа"
    return (f" Учти: {tail} — не ставь это ему в укор; можно мягко отметить, "
            f"что скучала, или просто быть короче обычного.")


def build_trigger(*, honorific: str, tod: str, gap_line: str,
                  hook_kind: str, hook_data: dict | None,
                  streak: int = 0) -> str:
    return (
        f"(Служебная ситуация — {honorific} этого текста не видит. Сейчас {tod}, "
        f"{gap_line} Он не писал; у тебя свободная минутка, и ты можешь — если "
        f"сама захочешь — написать ему первой.\n"
        f"{hook_block(hook_kind, hook_data, honorific)}\n"
        f"Реши сама, по своему характеру, настроению и вашей стадии отношений: "
        f"писать ли сейчас вообще, и если да — что. Обязанности писать нет; "
        f"повод выше — подсказка, не предписание.{ignore_hint(streak)}\n"
        f"Если решаешь не писать сейчас — ответь ровно одним словом: SKIP "
        f"(служебный маркер, {honorific} его не увидит; это нормальный выбор). "
        f"Если пишешь — просто напиши ему, как написала бы сама: коротко, в "
        f"своём тоне, без отчёта о причинах. Не начинай со своего имени.)"
    )
