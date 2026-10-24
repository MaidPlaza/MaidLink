from __future__ import annotations

import re
from dataclasses import dataclass
from typing import NamedTuple

OPEN, CLOSE = "⟦", "⟧"
PREFIX = "жест:"
NO_NAME = "тебя"


@dataclass(frozen=True)
class Gesture:
    id: str
    template: str
    title: str
    zone: str


CATALOG: tuple[Gesture, ...] = (
    Gesture("headpat", "гладит {name} по голове", "Погладить по голове", "head"),
)
BY_ID: dict[str, Gesture] = {g.id: g for g in CATALOG}


class Match(NamedTuple):
    gesture: Gesture
    inner: str


TOKEN_RX = re.compile(
    re.escape(OPEN) + r"\s*" + re.escape(PREFIX)
    + r"\s*([^" + CLOSE + r"]{1,80}?)\s*" + re.escape(CLOSE))


def _pattern(g: Gesture) -> re.Pattern:
    head, tail = g.template.split("{name}", 1)
    inner = re.escape(head) + r"[^" + CLOSE + r"]+?" + re.escape(tail)
    return re.compile(re.escape(OPEN) + r"\s*" + re.escape(PREFIX)
                      + r"\s*(" + inner + r")\s*" + re.escape(CLOSE))


_PATTERNS: tuple[tuple[Gesture, re.Pattern], ...] = tuple((g, _pattern(g)) for g in CATALOG)

_CONSONANTS = set("бвгджзклмнпрстфхцчшщ")


def accusative(name: str, gender: str = "female") -> str:
    words = (name or "").split()
    if not words:
        return ""
    male = (gender or "").strip().lower() == "male"
    out = []
    for w in words:
        low = w.lower()
        if len(w) < 2:
            out.append(w)
            continue
        if low.endswith("а"):
            out.append(w[:-1] + "у")
        elif low.endswith("я"):
            out.append(w[:-1] + "ю")
        elif male and low.endswith(("й", "ь")):
            out.append(w[:-1] + "я")
        elif male and low[-1] in _CONSONANTS:
            out.append(w + "а")
        else:
            out.append(w)
    return " ".join(out)


def label(g: Gesture, name_acc: str = "") -> str:
    return g.template.format(name=(name_acc or "").strip() or NO_NAME)


def token(g: Gesture, name_acc: str = "") -> str:
    return f"{OPEN}{PREFIX} {label(g, name_acc)}{CLOSE}"


def find(text) -> list[Match]:
    out: list[Match] = []
    if not isinstance(text, str) or OPEN not in text:
        return out
    for m in TOKEN_RX.finditer(text):
        whole = m.group(0)
        for g, rx in _PATTERNS:
            mm = rx.fullmatch(whole)
            if mm:
                out.append(Match(g, mm.group(1).strip()))
                break
    return out


def has_gesture(text) -> bool:
    return bool(find(text))


def render_transcript(text):
    if not isinstance(text, str) or OPEN not in text:
        return text
    return TOKEN_RX.sub(lambda m: f"<жест>{m.group(1).strip()}</жест>", text)


def turn_hint(matches: list[Match]) -> str:
    labels = "; ".join(dict.fromkeys(m.inner for m in matches))
    if not labels:
        return ""
    return (f"В этой реплике собеседник сделал жест через экран: {labels} — ты "
            "ощущаешь его. Отреагируй на жест в характере и по настроению: "
            "принять, смутиться, отстраниться или попросить так не делать — "
            "восторг не обязателен. Механику не пересказывай, сам жест за "
            "собеседника не описывай и ответным прикосновением не отвечай.")


def appraisal_note(text) -> str:
    if not has_gesture(text):
        return ""
    return ("В реплике есть жест через экран (⟦жест: …⟧): собеседник сделал его "
            "по отношению к персонажу — это настоящий стимул, а не слова о нём; "
            "суди по характеру, темпераменту и текущему настроению персонажа.")


def catalog_payload(name: str = "", gender: str = "female") -> dict:
    name_acc = accusative(name, gender)
    return {"open": OPEN, "close": CLOSE, "prefix": PREFIX,
            "name": name_acc or NO_NAME,
            "gestures": [{"id": g.id, "label": label(g, name_acc),
                          "title": g.title, "zone": g.zone,
                          "token": token(g, name_acc)} for g in CATALOG]}
