from __future__ import annotations

from dataclasses import dataclass

CODA = ("Это твоё состояние прямо сейчас — отыгрывай его в своей манере, "
        "вслух не объявляй и не объясняй.")

MOOD_FLOORS = ("positive",)


def parse_until(raw) -> object:
    if isinstance(raw, dict):
        if raw.get("turns") is not None:
            return {"turns": max(1, int(raw["turns"]))}
        if raw.get("seconds") is not None:
            return {"seconds": max(1.0, float(raw["seconds"]))}
        return "session_end"
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return {"turns": max(1, int(raw))}
    return "session_end"


@dataclass(frozen=True)
class Aftereffect:
    id: str
    text: str
    until: object = "session_end"
    mood_floor: str = ""
    source: str = ""

    def turn_limit(self) -> "int | None":
        u = self.until
        return int(u["turns"]) if isinstance(u, dict) and "turns" in u else None

    def seconds_limit(self) -> "float | None":
        u = self.until
        return float(u["seconds"]) if isinstance(u, dict) and "seconds" in u else None

    def is_over(self, next_turn: int, elapsed_sec: float) -> bool:
        tl = self.turn_limit()
        if tl is not None and next_turn > tl:
            return True
        sl = self.seconds_limit()
        if sl is not None and elapsed_sec >= sl:
            return True
        return False


def parse(raw, *, id: str, source: str = "") -> "Aftereffect | None":
    if not isinstance(raw, dict):
        return None
    text = str(raw.get("text") or "").strip()
    if not text:
        return None
    floor = str(raw.get("mood_floor") or "").strip()
    if floor not in MOOD_FLOORS:
        floor = ""
    return Aftereffect(id=str(id), text=" ".join(text.split()),
                       until=parse_until(raw.get("until")),
                       mood_floor=floor, source=str(source or ""))


def render(ae: Aftereffect) -> str:
    return f"{ae.text}\n{CODA}" if ae.text else ""


def allows_mood(floor: str, mood_state: str) -> bool:
    if floor != "positive":
        return True
    from persona.mood import MOOD_STATES
    meta = MOOD_STATES.get(mood_state or "")
    return meta is None or meta.valence >= 0
