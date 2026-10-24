from __future__ import annotations

import random

COLOR_BACKGROUND = {
    "white": "white background", "grey": "grey background", "gray": "grey background",
    "black": "black background", "blue": "blue background", "pink": "pink background",
    "purple": "purple background", "orange": "orange background",
    "yellow": "yellow background", "green": "green background", "aqua": "aqua background",
    "red": "red background", "brown": "brown background",
}
_COLOR_ALIAS = {
    "gray": "grey", "silver": "grey", "charcoal": "grey", "navy": "blue", "gold": "yellow",
    "golden": "yellow", "teal": "aqua", "cyan": "aqua", "turquoise": "aqua",
    "violet": "purple", "lavender": "purple", "lilac": "purple", "crimson": "red",
    "scarlet": "red", "rose": "pink", "cream": None, "ivory": None, "beige": None,
}
_BASE_WEIGHTS = {
    "white background": 0.6, "grey background": 0.5, "pink background": 1.0,
    "blue background": 1.0, "purple background": 1.0, "yellow background": 0.8,
    "orange background": 0.7, "aqua background": 0.8, "green background": 0.7,
    "red background": 0.5, "brown background": 0.4, "black background": 0.4,
}
FAVORITE_WEIGHT = 3.0
FAVORITE_ACHROMATIC_WEIGHT = 0.3
_ACHROMATIC = frozenset({"white background", "grey background", "black background"})
GRADIENT_SHARE = 0.45
BACKGROUND_TAGS = frozenset(set(COLOR_BACKGROUND.values()) | {
    "gradient background", "two-tone background", "colorful background",
    "monochrome background", "abstract background", "blurry background", "dark background",
    "transparent background"})
_DARK_TAGS = frozenset({"night", "darkness", "dark", "night sky", "starry sky"})


def _favorite_background(color) -> str | None:
    words = str(color or "").strip().lower().split()
    if not words:
        return None
    name = words[-1]
    if name in _COLOR_ALIAS:
        name = _COLOR_ALIAS[name]
        if name is None:
            return None
    return COLOR_BACKGROUND.get(name)


def choose_background(tags, favorite_colors=(), seed: int | None = None) -> list[str]:
    tset = {str(t).strip().lower() for t in tags or ()}
    if tset & BACKGROUND_TAGS:
        return []
    rng = random.Random(seed) if seed is not None else random.Random()
    if tset & _DARK_TAGS:
        return [rng.choice(["black background", "dark background"])]
    weights = dict(_BASE_WEIGHTS)
    for c in favorite_colors or ():
        tag = _favorite_background(c)
        if tag:
            weights[tag] = weights.get(tag, 0.0) + (
                FAVORITE_ACHROMATIC_WEIGHT if tag in _ACHROMATIC else FAVORITE_WEIGHT)
    names = list(weights)
    color = rng.choices(names, weights=[weights[n] for n in names])[0]
    out = [color]
    if rng.random() < GRADIENT_SHARE and color not in ("white background", "black background"):
        out.insert(0, "gradient background")
    return out
