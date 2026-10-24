from __future__ import annotations

import re

REGIONS: dict[str, str] = {
    "shoulders": "плечи", "arms": "руки", "collarbone": "ключицы",
    "chest": "грудь", "midriff": "живот", "back": "спина",
    "thighs": "бёдра", "legs": "ноги", "feet": "ступни",
}

_ALL_RX = re.compile(r"\b(?:nude|completely nude|underwear only|naked)\b")

_OPEN_RULES: tuple[tuple[re.Pattern, tuple[str, ...]], ...] = tuple(
    (re.compile(p), zones) for p, zones in (
        (r"\b(?:sleeveless|halterneck|leotard|one-piece swimsuit|swimsuit)\b",
         ("shoulders", "arms")),
        (r"\b(?:strapless|tube top|spaghetti strap|camisole|tank top|bare shoulders"
         r"|off[- ]shoulder|bikini|sports bra)\b", ("shoulders", "arms", "collarbone")),
        (r"\b(?:single bare shoulder|strap slip)\b", ("shoulders", "collarbone")),
        (r"\b(?:short sleeves|puffy short sleeves|sleeves rolled up|sleeves pushed up"
         r"|bare arms)\b", ("arms",)),
        (r"\b(?:open collar|v-neck|cleavage|low neckline|plunging neckline"
         r"|partially unbuttoned|unbuttoned|open shirt|collarbone)\b", ("collarbone",)),
        (r"\b(?:open shirt|partially unbuttoned|unbuttoned|no shirt|shirtless"
         r"|topless(?: male| female)?|open robe)\b", ("chest", "collarbone")),
        (r"\b(?:midriff|navel|crop top|cropped (?:shirt|top|hoodie|sweater|tank top)"
         r"|bikini|sports bra|tube top|bandeau|sarashi|lingerie|bra|topless"
         r"|shirt lift|open shirt|open clothes|sweater lift|clothes lift"
         r"|navel cutout|stomach cutout)\b", ("midriff",)),
        (r"\b(?:backless|back cutout|bare back|topless)\b", ("back",)),
        (r"\b(?:miniskirt|microskirt|short shorts|shorts|hot pants|bikini|leotard"
         r"|swimsuit|zettai ryouiki|garter straps|side slit|thigh cutout|no pants"
         r"|bare legs|skirt lift|dress lift|panties)\b", ("thighs",)),
        (r"\b(?:shorts|short shorts|bare legs|barefoot|bikini|swimsuit|leotard"
         r"|no pants)\b", ("legs",)),
        (r"\b(?:barefoot|sandals|flip-flops|bare feet)\b", ("feet",)),
        (r"\b(?:chemise|negligee|nightgown|babydoll|slip dress)\b",
         ("shoulders", "arms", "collarbone", "thighs")),
        (r"\b(?:see-through (?:clothes|dress|shirt|nightgown|chemise|negligee|leotard)"
         r"|sheer (?:clothes|dress|chemise|nightgown))\b",
         ("shoulders", "arms", "collarbone", "chest", "midriff", "back", "thighs", "legs")),
        (r"\bsee-through sleeves\b", ("arms",)),
        (r"\b(?:shirt pull|dress pull|kimono pull|leotard pull|clothes down|bra pull"
         r"|breasts out|breast slip|no bra)\b", ("shoulders", "collarbone", "chest")),
        (r"\b(?:pants pull|pantyhose pull|skirt pull|shorts pull|open skirt|open pants"
         r"|open shorts|skirt around one leg|panties aside|leotard aside|bottomless)\b",
         ("thighs", "legs")),
        (r"\bnipples\b", ("chest",)),
        (r"\b(?:pussy|penis)\b", ("thighs",)),
    ))

BODY_MARK_REGION: dict[str, tuple[str, ...]] = {
    "abs": ("midriff",), "obliques": ("midriff",), "navel": ("midriff",),
    "stomach": ("midriff",), "toned stomach": ("midriff",),
    "mole on stomach": ("midriff",), "mole on collarbone": ("collarbone",),
    "collarbone": ("collarbone",), "chest hair": ("chest",),
    "arm hair": ("arms",), "mole on thigh": ("thighs",),
    "linea alba": ("midriff",),
    "groin": ("hips",), "ass": ("buttocks",), "huge ass": ("buttocks",),
    "flat ass": ("buttocks",), "mole on ass": ("buttocks",),
    "body freckles": ("shoulders", "arms", "collarbone", "chest", "midriff",
                      "back", "thighs", "legs"),
    "tanlines": ("shoulders", "collarbone", "chest", "midriff", "back",
                 "thighs", "legs"),
}
_TATTOO_RX = re.compile(r"^(arm|back|thigh|leg|chest|stomach|shoulder)s? tattoo$")
_TATTOO_REGION = {"arm": "arms", "back": "back", "thigh": "thighs", "leg": "legs",
                  "chest": "chest", "stomach": "midriff", "shoulder": "shoulders"}

COMPOSER_BODY_REGION: dict[str, tuple[str, ...]] = {
    "collarbone": ("collarbone",), "armpits": ("shoulders", "arms"),
    "navel": ("midriff",), "midriff": ("midriff",), "stomach": ("midriff",),
    "bare midriff": ("midriff",),
    "nipples": ("chest",), "areolae": ("chest",), "breasts out": ("chest",),
    "breast slip": ("chest",), "nipple slip": ("chest",), "one breast out": ("chest",),
    "pussy": ("hips",), "clitoris": ("hips",), "pubic hair": ("hips",),
    "female pubic hair": ("hips",),
    "bare shoulders": ("shoulders",), "bare arms": ("arms",),
    "bare legs": ("legs",), "barefoot": ("feet",),
}


_COLLAR_RX = re.compile(r"\b(?:high collar|turtleneck|collared (?:dress|shirt)"
                        r"|dress shirt)\b")
_COLLAR_OPEN_RX = re.compile(r"\b(?:open collar|unbuttoned|partially unbuttoned"
                             r"|open shirt|off[- ]shoulder|v-neck|cleavage|plunging"
                             r"|strapless|tube top|topless|no shirt|shirtless"
                             r"|shirt pull|dress pull|kimono pull|leotard pull"
                             r"|clothes down|bra pull|breasts out|nude)\b")

_OPEN_SHOE_RX = re.compile(r"\b(?:sandals|flip-flops)\b")
_FOOT_BARE_RX = re.compile(r"\b(?:barefoot|bare feet)\b")
_FOOT_COVER_RX = re.compile(r"\b(?:tabi|thighhighs|pantyhose|tights|socks|kneehighs"
                            r"|stockings)\b")


def exposed(*fragments: str) -> set[str]:
    blob = ", ".join(f for f in fragments if f).lower()
    if _ALL_RX.search(blob):
        return set(REGIONS)
    out: set[str] = set()
    for rx, zones in _OPEN_RULES:
        if rx.search(blob):
            out.update(zones)
    if "collarbone" in out and _COLLAR_RX.search(blob) and not _COLLAR_OPEN_RX.search(blob):
        out.discard("collarbone")
    if ("feet" in out and not _FOOT_BARE_RX.search(blob) and _OPEN_SHOE_RX.search(blob)
            and _FOOT_COVER_RX.search(blob)):
        out.discard("feet")
    return out


def mark_region(tag: str) -> tuple[str, ...] | None:
    t = (tag or "").strip().lower()
    if t in BODY_MARK_REGION:
        return BODY_MARK_REGION[t]
    m = _TATTOO_RX.match(t)
    if m:
        return (_TATTOO_REGION[m.group(1)],)
    return None


def drop_hidden_marks(csv: str, open_regions: set[str]) -> tuple[str, list[str]]:
    if not csv:
        return csv, []
    kept, dropped = [], []
    for t in (p.strip() for p in csv.split(",")):
        if not t:
            continue
        need = mark_region(t)
        if need is not None and not (set(need) & open_regions):
            dropped.append(t)
        else:
            kept.append(t)
    return ", ".join(kept), dropped


_BREAST_PICK_RX = re.compile(
    r"nipple|areola|^breasts apart$|^(?:perky|sagging|pointy|hanging|unaligned) breasts$")


def drop_covered_picks(tags: list[str], open_regions: set[str]) -> list[str]:
    out = []
    for t in tags:
        low = t.strip().lower()
        need = COMPOSER_BODY_REGION.get(low) or (
            ("chest",) if _BREAST_PICK_RX.search(low) else None)
        if need is not None and not (set(need) & open_regions):
            continue
        out.append(t)
    return out


def hint_line(open_regions: set[str]) -> str:
    opened = [ru for k, ru in REGIONS.items() if k in open_regions]
    closed = [ru for k, ru in REGIONS.items() if k not in open_regions]
    return (f"  По наряду открыто: {', '.join(opened) or 'только лицо и кисти'}; "
            f"закрыто: {', '.join(closed) or '—'}. Части тела в закрытом не называй.\n")


_TOP_UW_RX = re.compile(
    r"\bbra\b|open shirt|shirt lift|cleavage|underboob|sideboob|(?<!partially )unbuttoned"
    r"|shirt pull|dress pull|kimono pull|clothes down|sweater lift|open robe"
    r"|open clothes|unzipped|clothes aside|clothing aside|clothes lift")
_TOP_BARE_RX = re.compile(
    r"\b(?:topless|nipples?|areolae?)\b|breasts out|bra pull|breast slip"
    r"|nipple slip|areola slip|one breast out")
_BOT_UW_RX = re.compile(
    r"\b(?:pant(?:y|ies)|thong)\b|skirt lift|dress lift|garter"
    r"|no pants|pants pull|pantyhose pull|shorts pull|skirt pull|open skirt"
    r"|open pants|open shorts|skirt around one leg")
_BOT_BARE_RX = re.compile(
    r"\b(?:bottomless|pussy|anus|vaginal|anal)\b|panties aside|leotard aside")
_BOTH_UW_RX = re.compile(
    r"\b(?:underwear|lingerie|babydoll|negligee|nightgown|chemise|undressing"
    r"|removing clothes)\b")
_PEEK = frozenset({"bra peek", "panty peek"})
_REM_TOP_RX = re.compile(r"\b(?:shirt|blouse|sweater|top|hoodie)\b")
_REM_BOT_RX = re.compile(r"\b(?:skirt|pants|shorts|jeans|trousers|hakama)\b")
_REM_ONEPIECE_RX = re.compile(
    r"\b(?:dress|kimono|yukata|robe|gown|leotard|bodysuit|swimsuit|overalls)\b")
_REM_OUTFIT_NAMES = frozenset({"maid", "wa maid", "miko", "nun", "butler", "waitress"})
_REAR_VIEW = frozenset({"from behind", "looking back", "ass focus", "bent over",
                        "all fours", "on stomach", "top-down bottom-up", "from side"})
_REAR_ONLY = frozenset({"on stomach", "from behind", "facing away", "back focus"})
_FRONT_REGIONS = frozenset({"chest", "collarbone", "midriff", "hips"})
_REM_BRA_RX = re.compile(r"\bbra\b")
_REM_PANTIES_RX = re.compile(r"\b(?:pant(?:y|ies)|thong)\b")
_FULLY_NUDE = frozenset({"nude", "completely nude"})
_FRAME_TOP = frozenset({"portrait", "upper body", "close-up"})
_FRAME_BOT = frozenset({"lower body"})
_TORSO = frozenset({"shoulders", "arms", "collarbone", "chest", "midriff", "back"})


def _norm_set(tags) -> set[str]:
    return {t.strip().lower().replace("_", " ") for t in (tags or ()) if t}


def _signals(tags, remove) -> tuple[bool, bool, bool, bool, bool, bool]:
    tag_blob = ", ".join(t for t in (tags or ()) if t).lower()
    rem_blob = ", ".join(r for r in (remove or ()) if r).lower().replace("dress shirt", "shirt")
    nude = bool(_norm_set(tags) & _FULLY_NUDE)
    both = bool(_BOTH_UW_RX.search(tag_blob))
    one_off = bool(_REM_ONEPIECE_RX.search(rem_blob)
                   or _norm_set(remove) & _REM_OUTFIT_NAMES)
    torso_off = one_off or bool(_REM_TOP_RX.search(rem_blob))
    legs_off = one_off or bool(_REM_BOT_RX.search(rem_blob))
    top_uw = both or torso_off or bool(_TOP_UW_RX.search(tag_blob))
    bot_uw = both or legs_off or bool(_BOT_UW_RX.search(tag_blob))
    top_bare = nude or bool(_TOP_BARE_RX.search(tag_blob) or _REM_BRA_RX.search(rem_blob))
    bot_bare = nude or bool(_BOT_BARE_RX.search(tag_blob)
                            or _REM_PANTIES_RX.search(rem_blob))
    return top_uw, bot_uw, top_bare, bot_bare, torso_off, legs_off


def intimate_state(tags, remove=()) -> dict[str, str]:
    top_uw, bot_uw, top_bare, bot_bare, _, _ = _signals(tags, remove)
    return {"top": "bare" if top_bare else "underwear" if top_uw else "covered",
            "bottom": "bare" if bot_bare else "underwear" if bot_uw else "covered"}


def bare_zones(tags, remove=()) -> set[str]:
    st = intimate_state(tags, remove)
    return {z for z, s in st.items() if s == "bare"}


def underwear_zones(tags, remove=()) -> set[str]:
    top_uw, bot_uw, top_bare, bot_bare, _, _ = _signals(tags, remove)
    tset = _norm_set(tags)
    bot_uw = bot_uw or bool(tset & _FRAME_BOT)
    z: set[str] = set()
    if top_uw and not top_bare:
        z.add("top")
    if bot_uw and not bot_bare:
        z.add("bottom")
    if z or top_bare or bot_bare:
        return z
    if tset & _FRAME_TOP:
        return {"top"}
    return {"top", "bottom"}


_CARRY_STATE = frozenset({"nude", "completely nude", "underwear only", "topless female",
                          "topless male", "bottomless", "no bra", "no panties"})


def snapshot_state(tags, remove=()) -> dict | None:
    from services.self_styling import underwear_item_zone
    tags = [t for t in (tags or ()) if t]
    tset = _norm_set(tags)
    remove = [r for r in (remove or ()) if r]
    *_, torso_off, legs_off = _signals(tags, remove)
    carry = [t for t in tags if t.strip().lower() in _CARRY_STATE
             or underwear_item_zone(t) is not None or t.strip().lower() == "lingerie"]
    if tset & _FULLY_NUDE:
        level = "nude"
    elif "underwear only" in tset or (torso_off and legs_off):
        level = "underwear"
    elif carry or torso_off or legs_off:
        level = "partial"
    else:
        return None
    return {"level": level, "tags": carry, "remove": remove}


def describe_snapshot(st: dict | None, gender: str = "female") -> str:
    if not st:
        return ""
    was = "был" if gender == "male" else "была"
    if st["level"] == "nude":
        return f"{was} без одежды"
    if st["level"] == "underwear":
        items = [t for t in st["tags"] if t.lower() not in ("underwear only", "lingerie")]
        return f"{was} в белье" + (f" ({', '.join(items)})" if items else "")
    bits = list(st["tags"])
    if st["remove"]:
        bits.append(f"снято: {', '.join(st['remove'])}")
    part = "частично раздет" if gender == "male" else "частично раздета"
    return f"{was} {part}" + (f" ({'; '.join(bits)})" if bits else "")


_STRIP_FOR_UNDER_RX = re.compile(
    r"\b(?:dress|shirt|blouse|sweater|top|hoodie|skirt|pants|shorts|jeans|trousers"
    r"|hakama|kimono|yukata|robe|gown|leotard|bodysuit|swimsuit|overalls|apron|sash"
    r"|obi|vest|jacket|coat|cardigan|tailcoat|necktie|neck ribbon|bowtie|bow tie"
    r"|ascot|sleeves?|cuffs|collar|brooch|japanese clothes)\b")


def strip_for_underwear(outfit_tags) -> list[str]:
    out = []
    for t in outfit_tags or ():
        low = (t or "").strip().lower()
        if low and (low in _REM_OUTFIT_NAMES or _STRIP_FOR_UNDER_RX.search(low)):
            out.append(t)
    return out


def frame_open(outfit: str, tags=(), remove=(), *, outfit_gone: bool = False) -> set[str]:
    tags = [t for t in (tags or ()) if t and _norm_set([t]).isdisjoint(_PEEK)]
    tset = _norm_set(tags)
    if outfit_gone or tset & _FULLY_NUDE:
        out = set(REGIONS) | {"hips"}
    else:
        out = exposed(outfit, ", ".join(tags))
        top_uw, bot_uw, top_bare, bot_bare, torso_off, legs_off = _signals(tags, remove)
        if torso_off:
            out |= _TORSO
        if legs_off:
            out |= {"thighs", "legs"}
        if top_uw or top_bare:
            out |= {"chest", "collarbone"}
        if bot_uw or bot_bare:
            out |= {"thighs", "hips"}
    if "hips" in out and tset & _REAR_VIEW:
        out.add("buttocks")
    if tset & _REAR_ONLY:
        out -= _FRONT_REGIONS
    return out


def rear_view(tags) -> bool:
    return bool(_norm_set(tags) & _REAR_ONLY)
