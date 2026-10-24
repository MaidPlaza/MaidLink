from __future__ import annotations


def g(gender: str, female: str, male: str) -> str:
    return male if (gender or "").strip().lower() == "male" else female


def gender_of(character) -> str:
    return (getattr(character, "gender", "") or "female").strip().lower() or "female"


PAIRS = ("f4m", "f4f", "m4f", "m4m")


def pair_of(character) -> str:
    cg = "m" if gender_of(character) == "male" else "f"
    ug_raw = (getattr(character, "user_gender", "") or "male").strip().lower()
    ug = "f" if ug_raw == "female" else "m"
    return f"{cg}4{ug}"


def _expand(code: str) -> set[str]:
    code = (code or "").strip().lower()
    if code in PAIRS:
        return {code}
    if code == "f4*":
        return {"f4m", "f4f"}
    if code == "m4*":
        return {"m4f", "m4m"}
    if code == "*4m":
        return {"f4m", "m4m"}
    if code == "*4f":
        return {"f4f", "m4f"}
    if code in ("*", "*4*"):
        return set(PAIRS)
    return set()


def pair_allows(declared, pair: str) -> bool:
    if not declared:
        return True
    if isinstance(declared, str):
        declared = [declared]
    allowed: set[str] = set()
    for code in declared:
        allowed |= _expand(code)
    if not allowed:
        return True
    return (pair or "").strip().lower() in allowed


DESCRIPTION_TOKENS: dict[str, tuple[str, str]] = {
    "кто":       ("Эта горничная", "Этот дворецкий"),
    "кто_мл":    ("эта горничная", "этот дворецкий"),
    "кто_рд":    ("этой горничной", "этого дворецкого"),
    "кто_дт":    ("этой горничной", "этому дворецкому"),
    "она":       ("она",           "он"),
    "ей":        ("ей",            "ему"),
    "её":        ("её",            "его"),
    "неё":       ("неё",           "него"),
    "ней":       ("ней",           "ним"),
    "ней_д":     ("ней",           "нему"),
    "самой_д":   ("самой",         "самому"),
    "нём":       ("ней",           "нём"),
    "сама":      ("сама",          "сам"),
    "рада":      ("рада",          "рад"),
    "собиралась": ("собиралась",   "собирался"),
    "хотела":    ("хотела",        "хотел"),
    "угадала":   ("угадала",       "угадал"),
    "ждала":     ("ждала",         "ждал"),
    "сняла":     ("сняла",         "снял"),
    "первой":    ("первой",        "первым"),
    "цифровая":  ("цифровая",      "цифровой"),
}


_IRREGULAR = {
    "влезла": "влез", "ошиблась": "ошибся", "перенесла": "перенёс",
    "зашла": "зашёл", "нашла": "нашёл", "пришла": "пришёл",
    "склонна": "склонен", "нужна": "нужен", "желанна": "желанен",
    "произошла": "произошёл", "подошла": "подошёл",
    "довольна": "доволен", "довела": "довёл",
}


def _derive_masculine(fem: str) -> str:
    low = fem.lower()
    if low in _IRREGULAR:
        return _IRREGULAR[low]
    if low.endswith("лась"):
        return fem[:-4] + "лся"
    if low.endswith("ла") or low.endswith("а"):
        return fem[:-1]
    return ""


def fill_forms(text: str, gender: str) -> str:
    if not text:
        return ""
    import re as _re

    def _one(m):
        token = m.group(1)
        pair = DESCRIPTION_TOKENS.get(token)
        if pair is not None:
            return g(gender, *pair)
        low = token.lower()
        cap = token[:1].isupper()
        pair = DESCRIPTION_TOKENS.get(low)
        male = pair[1] if pair is not None else _derive_masculine(low)
        if not male:
            return m.group(0)
        out = g(gender, low, male)
        return out[:1].upper() + out[1:] if cap else out

    return _re.sub(r"\{([^{}\s]+)\}", _one, str(text))


fill_description = fill_forms
