from __future__ import annotations

import re

_WISH_WORDS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "confidence": (("смелее", "увереннее", "решительнее", "посмелее", "поувереннее"),
                   ("осторожнее", "поосторожнее", "скромнее", "поскромнее", "не так самоуверенно")),
    "warmth": (("теплее", "потеплее", "заботливее", "мягче", "помягче", "ласковее", "поласковее"),
               ("построже", "строже", "холоднее", "не опекай", "поменьше опеки", "меньше опеки",
                "не нянчись")),
    "openness": (("любопытнее", "полюбопытнее", "интересуйся", "открытее", "пооткрытее"),
                 ("сосредоточеннее", "не отвлекайся", "не разбрасывайся", "поменьше нового")),
    "cheerfulness": (("веселее", "повеселее", "бодрее", "пободрее", "жизнерадостнее"),
                     ("спокойнее", "поспокойнее", "тише", "потише", "не так бодро")),
    "playfulness": (("игривее", "поигривее", "шути больше", "шутишь больше", "больше шуток",
                     "шутливее"),
                    ("серьёзнее", "посерьёзнее", "поменьше шуток", "меньше шуток", "без шуток")),
    "energy": (("инициативнее", "активнее", "поактивнее", "предлагай сама", "предлагай сам",
                "не жди указаний"),
               ("не суетись", "поменьше инициативы", "меньше инициативы", "не лезь вперёд",
                "не торопись", "без суеты")),
    "expressiveness": (("эмоциональнее", "поэмоциональнее", "ярче", "поярче", "не сдерживайся",
                        "открытее в чувствах"),
                       ("сдержаннее", "посдержаннее", "поменьше эмоций", "меньше эмоций",
                        "не драматизируй", "ровнее")),
    "diligence": (("внимательнее", "повнимательнее", "аккуратнее", "поаккуратнее", "тщательнее",
                   "дотошнее"),
                  ("не заморачивайся", "попроще", "не придирайся", "поменьше придирок",
                   "меньше придирок", "не перепроверяй")),
    "directness": (("прямее", "попрямее", "говори прямо", "без обиняков", "откровеннее",
                    "не смягчай"),
                   ("тактичнее", "потактичнее", "деликатнее", "поделикатнее", "не руби",
                    "помягче в словах", "аккуратнее в словах")),
}

_FRAME_RX = re.compile(
    r"(?:хочу|хотел\w*\s+бы|хотелось\s+бы|мне\s+бы\s+хотелось|прошу|попробуй|постарайся|"
    r"давай\s+ты\s+буд\w+|можешь\s+быть|будь|стань|старайся|был\w*\s+бы\s+неплохо|"
    r"было\s+бы\s+здорово|мне\s+нравится,?\s+когда\s+ты)", re.IGNORECASE)
_CANCEL_RX = re.compile(
    r"(?:не\s+надо|не\s+нужно|хватит|перестань|забудь|отмен\w+|больше\s+не)\s+"
    r"(?:стараться\s+быть|стараться|быть|про|о)?\s*", re.IGNORECASE)
_NEG_RX = re.compile(r"\bне\s+(?:надо|нужно|стоит)\b", re.IGNORECASE)


def _find_words(text: str) -> list[tuple[str, int, str]]:
    low = text.lower()
    out: list[tuple[str, int, str]] = []
    for axis, (ups, downs) in _WISH_WORDS.items():
        for w in ups:
            if re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", low):
                out.append((axis, +1, w))
        for w in downs:
            if re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", low):
                out.append((axis, -1, w))
    phrases = [w for _, _, w in out]
    return [(a, d, w) for a, d, w in out
            if not any(o != w and w in o for o in phrases)]


def detect_axis_wishes(message: str) -> dict[str, int]:
    msg = (message or "").strip()
    if not msg:
        return {}
    found = _find_words(msg)
    if not found:
        return {}
    out: dict[str, int] = {}
    cancel = bool(_CANCEL_RX.search(msg))
    frame = bool(_FRAME_RX.search(msg))
    for axis, d, w in found:
        if cancel:
            out[axis] = 0
        elif frame and not _NEG_RX.search(msg):
            out.setdefault(axis, d)
    return out


def apply_axis_wishes(identity, message: str, *, source: str = "chat") -> list[tuple[str, int]]:
    from persona.axis_dynamics import set_axis_goal
    changes: list[tuple[str, int]] = []
    for axis, d in detect_axis_wishes(message).items():
        if set_axis_goal(identity, axis, d, source=source, note=message[:120]):
            changes.append((axis, d))
    return changes
