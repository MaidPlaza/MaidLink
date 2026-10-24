from __future__ import annotations

import json
import re
from pathlib import Path

from app_paths import ASSETS_ROOT

_ROOT = ASSETS_ROOT
_ATTR = _ROOT / "drawing" / "danbooru_tags" / "tag_attributes.json"

LEVELS = ["face", "head_shoulders", "upper_body", "cowboy", "full"]
_IDX = {name: i for i, name in enumerate(LEVELS)}

FRAMING_LEVEL: dict[str, str | None] = {
    "close_up": "face",
    "portrait": "head_shoulders",
    "medium": "upper_body",
    "full_body": "full",
    "from_above": None,
    "from_below": None,
    "from_side": None,
    "dutch_angle": None,
}

_COLOR = {"aqua", "black", "blue", "brown", "green", "grey", "gray", "orange",
          "pink", "purple", "red", "white", "yellow", "blonde", "silver", "gold",
          "golden", "dark", "light", "pale", "navy", "teal", "cyan", "magenta",
          "beige", "tan", "cream", "ivory", "crimson", "azure", "multicolored",
          "two-tone", "rainbow", "gradient"}
_PATTERN = {"frilled", "striped", "plaid", "checkered", "floral", "lace",
            "lace-trimmed", "fur-trimmed", "ribbon-trimmed", "pleated", "sleeveless",
            "strapless", "off-shoulder", "detached", "puffy", "ruffled", "layered",
            "sailor", "pinstripe", "gingham", "houndstooth", "argyle", "translucent",
            "sheer", "see-through", "high-waist", "low-cut"}
_PREFIX = _COLOR | _PATTERN

_ZONES: dict[str, str] | None = None


def _load() -> dict[str, str]:
    global _ZONES
    if _ZONES is None:
        try:
            data = json.loads(_ATTR.read_text(encoding="utf-8"))
            _ZONES = {t: a["zone"]
                      for t, a in (data.get("tags") or {}).items()
                      if isinstance(a, dict) and a.get("zone")}
        except Exception:
            _ZONES = {}
    return _ZONES


_LABELS: dict[str, set[str]] | None = None


def _load_labels() -> dict[str, set[str]]:
    global _LABELS
    if _LABELS is None:
        try:
            data = json.loads(_ATTR.read_text(encoding="utf-8"))
            _LABELS = {t: set(a["labels"])
                       for t, a in (data.get("tags") or {}).items()
                       if isinstance(a, dict) and a.get("labels")}
        except Exception:
            _LABELS = {}
    return _LABELS


def labels_of(tag: str) -> set[str]:
    return _load_labels().get(_norm(tag), set())


_RATINGS: dict[str, str] | None = None


def _load_ratings() -> dict[str, str]:
    global _RATINGS
    if _RATINGS is None:
        try:
            data = json.loads(_ATTR.read_text(encoding="utf-8"))
            _RATINGS = {t: a["rating"]
                        for t, a in (data.get("tags") or {}).items()
                        if isinstance(a, dict) and a.get("rating")}
        except Exception:
            _RATINGS = {}
    return _RATINGS


def rating_of(tag: str) -> str:
    return _load_ratings().get(_norm(tag), "sfw")


def _norm(tag: str) -> str:
    t = tag.strip().strip("()")
    t = re.sub(r":[\d.]+$", "", t)
    return t.strip("() ").lower()


_FIGURE_ATTR_ALWAYS = frozenset({
    "flat chest", "small breasts", "medium breasts", "large breasts",
    "huge breasts", "gigantic breasts",
})


def zone_of(tag: str) -> str:
    z = _load()
    t = _norm(tag)
    if t in _FIGURE_ATTR_ALWAYS:
        return "face"
    if t in z:
        return z[t]
    toks = t.split()
    for i in range(1, len(toks)):
        if toks[i - 1] not in _PREFIX:
            break
        rest = " ".join(toks[i:])
        if rest in z:
            return z[rest]
    if t in _EXACT_FALLBACK:
        return _EXACT_FALLBACK[t]
    for kw, zone in _KEYWORD_FALLBACK:
        if kw in t:
            return zone
    return "face"


_EXACT_FALLBACK = {"standing": "upper_body"}
_KEYWORD_FALLBACK = (("waist apron", "cowboy"), ("apron", "upper_body"))


def framing_level(framing_option_id: str | None) -> str | None:
    if not framing_option_id:
        return None
    return FRAMING_LEVEL.get(framing_option_id)


def visible_at(tag: str, level: str | None) -> bool:
    if level is None:
        return True
    return _IDX[level] >= _IDX[zone_of(tag)]


def visible_in_band(tag: str, level: str | None, floor: str | None = None) -> bool:
    if level is None:
        return True
    zi = _IDX[zone_of(tag)]
    if zi > _IDX[level]:
        return False
    if floor is not None and zi < _IDX[floor]:
        return False
    return True


def crop_band(csv: str, level: str | None, floor: str | None, *, keep=()) -> str:
    if level is None or not csv:
        return csv
    out: list[str] = []
    for raw in csv.split(","):
        t = raw.strip()
        if not t:
            continue
        if any(k in t.lower() for k in keep) or visible_in_band(t, level, floor):
            out.append(t)
    return ", ".join(out)


def filter_fragment(fragment: str, level: str | None) -> tuple[str, list[str]]:
    if level is None or not fragment:
        return fragment, []
    kept: list[str] = []
    dropped: list[str] = []
    for raw in fragment.split(","):
        if not raw.strip():
            continue
        if visible_at(raw, level):
            kept.append(raw.strip())
        else:
            dropped.append(_norm(raw))
    return ", ".join(kept), dropped


def component_min_level(fragment: str) -> str | None:
    max_idx = 0
    for raw in (fragment or "").split(","):
        if raw.strip():
            max_idx = max(max_idx, _IDX[zone_of(raw)])
    return LEVELS[max_idx] if max_idx > 0 else None


def component_fits(fragment: str, level: str | None) -> bool:
    if level is None:
        return True
    need = component_min_level(fragment)
    return need is None or _IDX[level] >= _IDX[need]
