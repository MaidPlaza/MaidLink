from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from persona.character import Character, OutfitPolicy
    from persona.evolution import CharacterIdentity


DEFAULT_HONORIFIC_BY_GENDER: dict[str, str] = {
    "male": "Господин",
    "female": "Госпожа",
}
DEFAULT_HONORIFIC = "Господин"

_CASUAL_SPEECH_MARKERS = ("груб", "фамиль", "развяз", "casual", "rude")
_INTIMATE_SHIFT_TIERS = ("close", "intimate")


def resolve_honorific(character: "Character", *, override: str = "") -> str:
    ov = (override or "").strip()
    if ov:
        return ov
    ss = getattr(character, "speaking_style", None)
    explicit = (ss.honorific if ss else "") or ""
    explicit = explicit.strip()
    if explicit:
        return explicit
    user_gender = getattr(character, "user_gender", "") or ""
    return DEFAULT_HONORIFIC_BY_GENDER.get(user_gender, DEFAULT_HONORIFIC)


def resolve_address_form(character: "Character", *, tier: str = "distant",
                         override: str = "") -> str:
    ov = (override or "").strip().lower()
    if ov in ("ты", "вы"):
        return ov
    ss = getattr(character, "speaking_style", None)
    base = ((getattr(ss, "address_form", "") if ss else "") or "").strip().lower()
    if base not in ("ты", "вы"):
        sl = ((getattr(ss, "speech_level", "") if ss else "") or "").lower()
        base = "ты" if any(m in sl for m in _CASUAL_SPEECH_MARKERS) else "вы"
    shift = ((getattr(ss, "address_form_intimate", "") if ss else "") or "").strip().lower()
    if shift in ("ты", "вы") and tier in _INTIMATE_SHIFT_TIERS:
        return shift
    return base


_FORM_CUE = (r"(?:дава[йя]\w*|мож(?:но|ешь|ете)|перейд[ёе]м|переход\w*|обраща\w+|"
             r"говор\w+|зов\w+|называ\w+|хоч\w+|предпочита\w+|буд\w+\s+рад\w*)")
_RE_FORM = re.compile(_FORM_CUE + r"[^.!?\n]{0,30}?\bна\s+[«\"]?(ты|вы)\b", re.IGNORECASE)
_RE_FORM_BARE = re.compile(r"^[«\"]?\s*(?:дава[йя]\s+)?на\s+[«\"]?(ты|вы)[»\"]?\s*[.!?]*$",
                           re.IGNORECASE)
_HONORIFIC_FORMS = {
    "господин": "Господин", "господине": "Господин", "господином": "Господин",
    "хозяин": "Хозяин", "хозяине": "Хозяин", "хозяином": "Хозяин",
    "госпожа": "Госпожа", "госпоже": "Госпожа", "госпожой": "Госпожа",
    "повелитель": "Повелитель", "повелителю": "Повелитель", "повелителем": "Повелитель",
    "мастер": "Мастер", "мастером": "Мастер", "сэр": "сэр", "сэром": "сэр",
}
_RE_HON = re.compile(
    r"(?:зов[иите]+|называ\w+|обраща\w+\s+ко\s*мне|можешь\s+звать\s+меня)\s+"
    r"(?:меня\s+)?(?:как\s+|по[\s-]имени\s+)?[«\"]?([А-Яа-яЁё]+)\b", re.IGNORECASE)


def detect_address_directive(message: str) -> dict:
    msg = (message or "").strip()
    if not msg:
        return {}
    out: dict = {}
    m = _RE_FORM.search(msg) or _RE_FORM_BARE.match(msg)
    if m:
        out["form"] = m.group(1).lower()
    h = _RE_HON.search(msg)
    if h:
        w = h.group(1).lower()
        if w in _HONORIFIC_FORMS:
            out["honorific"] = _HONORIFIC_FORMS[w]
    return out


@dataclass(frozen=True)
class CharacterContext:
    character: "Character"
    identity: "CharacterIdentity"
    character_id: str

    @property
    def tier(self) -> str:
        from persona.evolution import compute_relationship_tier
        return compute_relationship_tier(self.identity, self.character)

    @property
    def honorific(self) -> str:
        return resolve_honorific(self.character)

    @property
    def address_form(self) -> str:
        return resolve_address_form(self.character, tier=self.tier)

    @property
    def archetypes(self) -> list[str]:
        a = getattr(self.character, "archetype", "") or ""
        return [a] if a else []

    @property
    def outfit_policy(self) -> "OutfitPolicy":
        return self.character.outfit_policy
