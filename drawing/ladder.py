from __future__ import annotations

import re

LEVEL_NAMES = {0: "одета", 1: "намёк", 2: "бельё", 3: "частичная нагота", 4: "нагота",
               5: "откровенная поза", 6: "в одиночку", 7: "со зрителем"}
SOLO_MAX_LEVEL = 6
CONTACT_LEVEL = 7
VIEWER_CONTACT_CAPABILITY = "viewer_contact"

SOLO_ACT_TAGS = frozenset({
    "masturbation", "female masturbation", "male masturbation",
    "masturbation through clothes", "clitoral stimulation", "fingering",
    "hand in own panties", "crotch rub", "nipple tweak",
    "sex toy", "vibrator", "dildo", "egg vibrator", "hitachi magic wand",
    "vibrator under clothes", "vibrator in thighhighs", "object insertion",
    "vaginal object insertion", "dildo riding", "onahole",
})
EXPLICIT_POSE_TAGS = frozenset({
    "spread legs", "m legs", "spread pussy", "spread ass", "spread anus",
    "top-down bottom-up", "knees apart feet together", "panties aside",
    "grabbing own breast", "grabbing own ass", "legs apart",
})
AROUSAL_TAGS = frozenset({
    "pussy juice", "pussy juice trail", "trembling", "heavy breathing", "sweat",
    "female orgasm", "orgasm", "torogao", "steaming body",
})

PARTNER_TAGS = frozenset({
    "handjob", "paizuri", "paizuri under clothes", "straddling paizuri",
    "perpendicular paizuri", "nursing handjob", "footjob", "pussyjob", "thigh sex",
    "frottage", "groping", "grabbing another's breast", "grabbing another's penis",
    "crotch grab", "anal fingering",
    "oral", "fellatio", "cunnilingus", "deepthroat", "breast sucking", "irrumatio",
    "licking nipple", "licking penis",
    "sex", "vaginal", "anal", "double penetration", "fisting", "deep penetration",
    "sex from behind", "clothed sex", "rough sex", "after sex",
    "cum", "ejaculation", "bukkake", "cumdrip", "facial", "cum in pussy", "cum on body",
    "cum on breasts", "internal cumshot", "cum in mouth", "cum in ass", "cum on ass",
    "cum on penis", "cumdrip from penis",
    "bdsm", "bondage", "shibari", "breast bondage", "spanked", "femdom", "dominatrix",
    "humiliation", "suspension",
    "cowgirl position", "reverse cowgirl position", "missionary", "doggystyle", "spooning",
    "standing sex", "suspended congress", "breast smother", "face to breasts",
    "head between breasts", "breasts on head",
    "strap-on", "milking machine", "hetero", "yuri", "yaoi",
})
_PARTNER_RX = re.compile(r"another's|\bpov hands\b|\bpov crotch\b|\bhetero\b|\byuri\b|\byaoi\b"
                         r"|\bmultiple (?:boys|girls)\b|\b\d(?:boys|girls)\b|\bimminent (?:sex|penetration)")


_PARTNER_NEG_FEMALE = ("1boy", "hetero", "multiple boys", "multiple girls", "yuri", "penis")
_PARTNER_NEG_MALE = ("1girl", "hetero", "multiple boys", "multiple girls", "yaoi")


def partner_negative(male: bool = False) -> tuple[str, ...]:
    return _PARTNER_NEG_MALE if male else _PARTNER_NEG_FEMALE


def _norm(t) -> str:
    return str(t or "").strip().lower().replace("_", " ")


def is_partner_tag(tag) -> bool:
    t = _norm(tag)
    return t in PARTNER_TAGS or bool(_PARTNER_RX.search(t))


def contact_allowed(capabilities=()) -> bool:
    return VIEWER_CONTACT_CAPABILITY in set(capabilities or ())


def max_level(capabilities=()) -> int:
    return CONTACT_LEVEL if contact_allowed(capabilities) else SOLO_MAX_LEVEL


_PARTIAL_TAGS = frozenset({"topless female", "topless male", "bottomless", "breasts out",
                           "nipples", "breast slip", "no bra", "pussy", "no panties"})
_UNDERWEAR_TAGS = frozenset({"bra peek", "panty peek", "pantyshot", "upskirt", "bra", "panties",
                             "lingerie", "thong", "underwear", "underwear only",
                             "see-through clothes"})
_TEASE_TAGS = frozenset({"single bare shoulder", "bare shoulders", "strap slip", "off shoulder",
                         "open collar", "partially unbuttoned", "open clothes", "skirt lift",
                         "dress lift", "cleavage", "midriff", "underboob", "sideboob"})


def exposure_level(tags, remove=()) -> int:
    from drawing import exposure as _ex
    tset = {_norm(t) for t in tags or ()}
    st = _ex.snapshot_state(list(tags or ()), list(remove or ()))
    if st is not None and st["level"] == "nude":
        return 4
    if tset & _PARTIAL_TAGS:
        return 3
    if (st is not None and st["level"] == "underwear") or tset & _UNDERWEAR_TAGS:
        return 2
    if st is not None or tset & _TEASE_TAGS:
        return 1
    return 0


def level_of(tags, remove=()) -> int:
    tset = {_norm(t) for t in tags or ()}
    if any(is_partner_tag(t) for t in tset):
        return CONTACT_LEVEL
    if tset & SOLO_ACT_TAGS:
        return 6
    exp = exposure_level(tags, remove)
    if exp >= 2 and tset & EXPLICIT_POSE_TAGS:
        return 5
    return exp
