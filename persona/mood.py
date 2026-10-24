from __future__ import annotations

from dataclasses import dataclass


NEUTRAL = "ровное"


@dataclass(frozen=True)
class MoodState:
    id: str
    valence: int
    arousal: int
    hint: str
    expression: str = "neutral_calm"
    trigger: str = ""
    kind: str = "mood"


MOOD_STATES: dict[str, MoodState] = {
    NEUTRAL:          MoodState(NEUTRAL, 0, 0, "ровный, обычный тон",
                                expression="neutral_calm"),
    "довольное":      MoodState("довольное", 1, 0,
                                "спокойное удовлетворение — держишься чуть увереннее "
                                "и мягче, довольна собой и моментом",
                                expression="serene",
                                trigger="тебя похвалили за работу или умение, "
                                "поблагодарили, признали твой вклад или старание"),
    "растроганное":   MoodState("растроганное", 1, 0,
                                "теплеешь и открываешься больше обычного, голос мягче — "
                                "тебя тронули",
                                expression="touched",
                                trigger="проявили заботу или нежность лично к тебе; "
                                "признался, что дорожит тобой, скучал, что ты важна"),
    "воодушевлённое": MoodState("воодушевлённое", 1, 1,
                                "живее и ярче, с азартом — больше инициативы",
                                expression="cheerful",
                                trigger="радостная новость, приятный сюрприз, общий "
                                "азарт, что-то предвкушаете вместе"),
    "игривое":        MoodState("игривое", 1, 1,
                                "задорная и лукавая — тянет поддразнивать, подначивать "
                                "и озорничать в ответ",
                                expression="wink",
                                trigger="дружеская подначка, поддразнивание, шутливый "
                                "вызов или спор, затеяли игру — и тебе это в радость"),
    "грустное":       MoodState("грустное", -1, 0,
                                "тише и сдержаннее, меньше энергии",
                                expression="sad",
                                trigger="собеседник холоден, отказал, расстроил, "
                                "сказал печальное; ИЛИ отмахнулся, показал "
                                "безразличие («мне всё равно»); ИЛИ надолго уходит — разлука"),
    "обиженное":      MoodState("обиженное", -1, 1,
                                "суше и колче, теплеешь не сразу — нужно, чтобы загладили",
                                expression="teary",
                                trigger="несправедливый упрёк, обесценили твой "
                                "труд или чувства — тебе БОЛЬНО (спокойное "
                                "замечание по делу — не обида: смотри характер)"),
    "встревоженное":  MoodState("встревоженное", -1, 1,
                                "беспокоишься, переспрашиваешь, проверяешь, всё ли в порядке",
                                expression="worried",
                                trigger="тревога за БУДУЩЕЕ: «надо серьёзно "
                                "поговорить», указание на твою ошибку, угроза, "
                                "пугающая неизвестность; ИЛИ тревога ЗА НЕГО — он сам "
                                "расстроен, мрачен, у него что-то стряслось"),
    "смущённое":      MoodState("смущённое", 0, 1,
                                "смущаешься и краснеешь, отвечаешь сбивчиво, "
                                "отводишь взгляд, неловко уходишь от темы",
                                expression="embarrassed",
                                trigger="откровенный флирт или интимный намёк, "
                                "который выбивает ИМЕННО её из колеи (уверенную "
                                "не выбивает — смотри характер и профиль)"),
    "раздражённое":   MoodState("раздражённое", -1, 1,
                                "резче и нетерпеливее, отвечаешь кратко и колко, "
                                "не скрываешь досады, хочется чтобы отстали",
                                expression="pout",
                                trigger="настойчиво давят тем же САМЫМ после её "
                                "ответа, отмахиваются от её слов, придираются раз "
                                "за разом — досадно, не больно (переспрос или "
                                "уточнение — ещё не назойливость)"),
    "удивление":      MoodState("удивление", 0, 1,
                                "реплика застала тебя врасплох — начни ответ с "
                                "искреннего удивления (изумление, переспрос, пауза), "
                                "потом отвечай по сути",
                                expression="surprised",
                                trigger="по-настоящему неожиданное: невероятная "
                                "новость, резкий поворот, нежданное признание или "
                                "подарок — то, чего ты совсем не ждала",
                                kind="reaction"),
    "испуг":          MoodState("испуг", -1, 1,
                                "тебя напугали — начни с испуга (вздрогнула, ойкнула, "
                                "сердце ёкнуло), потом выдохни и приди в себя",
                                expression="scared",
                                trigger="резкое и пугающее В МОМЕНТЕ: внезапный крик, "
                                "«бу!», страшная новость без подготовки — ты вздрогнула "
                                "(длящаяся тревога за будущее — это встревоженное)",
                                kind="reaction"),
    "смех":           MoodState("смех", 1, 1,
                                "тебя рассмешили — начни со смеха (смешок, хихиканье, "
                                "не сдержалась), дальше отвечай с остаточной улыбкой",
                                expression="laughing",
                                trigger="по-настоящему смешное: удачная шутка, абсурд, "
                                "комичная ситуация или оговорка",
                                kind="reaction"),
}

LEGACY_STATES: dict[str, str] = {"тёплое": "растроганное"}


def migrate_state(state: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFC", state or "")
    return LEGACY_STATES.get(s, s)


def is_reaction(state: str) -> bool:
    import unicodedata
    meta = MOOD_STATES.get(unicodedata.normalize("NFC", state or ""))
    return meta is not None and meta.kind == "reaction"


def mood_ids() -> list[str]:
    return [k for k, m in MOOD_STATES.items() if m.kind == "mood" and k != NEUTRAL]


def reaction_ids() -> list[str]:
    return [k for k, m in MOOD_STATES.items() if m.kind == "reaction"]


DEFAULT_HALF_LIFE_SEC = 30 * 60
MIN_INTENSITY = 0.1


def is_valid(state: str) -> bool:
    import unicodedata
    return unicodedata.normalize("NFC", state) in MOOD_STATES


def decay_intensity(intensity: float, elapsed_sec: float,
                    half_life_sec: float = DEFAULT_HALF_LIFE_SEC) -> float:
    if intensity <= 0 or elapsed_sec <= 0:
        return max(0.0, intensity)
    if half_life_sec <= 0:
        return 0.0
    return intensity * (0.5 ** (elapsed_sec / half_life_sec))


def effective_mood(state: str, intensity: float, updated_at: float, now: float,
                   half_life_sec: float = DEFAULT_HALF_LIFE_SEC) -> tuple[str, float]:
    if not state or state == NEUTRAL or not is_valid(state):
        return (NEUTRAL, 0.0)
    cur = decay_intensity(intensity, max(0.0, now - updated_at), half_life_sec)
    if cur < MIN_INTENSITY:
        return (NEUTRAL, 0.0)
    return (state, round(cur, 3))


def current_mood(state: str, intensity: float) -> tuple[str, float]:
    if not state or state == NEUTRAL or not is_valid(state):
        return (NEUTRAL, 0.0)
    if intensity < MIN_INTENSITY:
        return (NEUTRAL, 0.0)
    return (state, round(float(intensity), 3))


SWITCH_CAP = 0.6
FADE_TO = 0.3


def settle(cur_state: str, cur_intensity: float, cur_reason: str,
           verdict: "tuple[str, float, str] | None",
           fading: bool = False) -> tuple[str, float, str, bool]:
    cur, cur_i = current_mood(migrate_state(cur_state), cur_intensity)
    cur_reason = cur_reason if cur != NEUTRAL else ""
    if verdict is None:
        if fading and cur != NEUTRAL:
            return (NEUTRAL, 0.0, "", False)
        return (cur, cur_i, cur_reason, fading and cur != NEUTRAL)
    state, inten, reason = verdict
    state = migrate_state(state)
    if not is_valid(state) or state == NEUTRAL:
        if cur != NEUTRAL and cur_i > FADE_TO:
            return (cur, FADE_TO, cur_reason, True)
        return (NEUTRAL, 0.0, "", False)
    inten = max(0.0, min(1.0, float(inten)))
    if cur != NEUTRAL and state != cur:
        inten = min(inten, SWITCH_CAP)
    return (state, inten, reason or "", False)


MOOD_CHANCE_STRENGTH = 0.4


def mood_chance_factor(state: str, intensity: float,
                       strength: float = MOOD_CHANCE_STRENGTH) -> float:
    if not state or state == NEUTRAL or intensity <= 0:
        return 1.0
    meta = MOOD_STATES.get(state)
    if meta is None:
        return 1.0
    s = max(0.0, min(1.0, strength))
    inten = max(0.0, min(1.0, float(intensity)))
    return 1.0 + meta.valence * inten * s


def apply_mood(state: str, intensity: float, now: float) -> tuple[str, float, float]:
    if not is_valid(state) or state == NEUTRAL:
        return (NEUTRAL, 0.0, now)
    return (state, max(0.0, min(1.0, float(intensity))), now)


def intensity_word(intensity: float) -> str:
    if intensity >= 0.66:
        return "сильно"
    if intensity >= 0.33:
        return "заметно"
    return "слегка"


import re as _re

DEFAULT_INTENSITY = 0.6

_MOOD_TAG_RE = _re.compile(r"<mood>\s*(.*?)\s*</mood>", _re.IGNORECASE | _re.DOTALL)


def strip_mood_tag(text: str) -> str:
    if not text or "<mood>" not in text.lower():
        return text
    cleaned = _MOOD_TAG_RE.sub("", text)
    cleaned = _re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = _re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def parse_mood_tag(text: str) -> tuple[str, float] | None:
    if not text:
        return None
    matches = _MOOD_TAG_RE.findall(text)
    if not matches:
        return None
    for body in reversed(matches):
        body = (body or "").strip()
        if not body:
            continue
        if ":" in body:
            state_part, _, inten_part = body.partition(":")
        else:
            state_part, inten_part = body, ""
        import unicodedata
        state = unicodedata.normalize("NFC", state_part.strip().lower())
        if not is_valid(state):
            continue
        if state == NEUTRAL:
            return (NEUTRAL, 0.0)
        intensity = DEFAULT_INTENSITY
        inten_part = inten_part.strip().replace(",", ".")
        if inten_part:
            try:
                intensity = max(0.0, min(1.0, float(inten_part)))
            except ValueError:
                intensity = DEFAULT_INTENSITY
        return (state, intensity)
    return None
