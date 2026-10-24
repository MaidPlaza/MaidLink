from __future__ import annotations

import functools

ACCESSORY_CAP = 6
MAKEUP_CAP = 6
HAIR_EXTRA_CAP = 6
INTIMATE_CAP = 6
UNDERWEAR_CAP = 6

_EMPTY_HAIR = {"style": "", "texture": "", "bangs": "", "extras": []}

BARE_HAIR = {"style": "hair down", "texture": "straight hair"}
ALWAYS_OPEN = frozenset(BARE_HAIR.values())


HAIR_STYLES: dict[str, str] = {
    "ponytail": "medium", "high ponytail": "medium", "low ponytail": "medium",
    "side ponytail": "medium", "short ponytail": "short", "folded ponytail": "long",
    "front ponytail": "medium", "split ponytail": "medium",
    "twintails": "medium", "low twintails": "medium", "short twintails": "short",
    "uneven twintails": "medium", "one side up": "short", "two side up": "short",
    "half updo": "medium", "topknot": "medium",
    "braid": "medium", "single braid": "medium", "twin braids": "long",
    "low twin braids": "long", "side braid": "medium", "front braid": "medium",
    "crown braid": "medium", "braided ponytail": "long",
    "half up braid": "medium", "braided bun": "medium",
    "french braid": "medium", "rope braid": "long",
    "hair bun": "medium", "single hair bun": "medium", "double bun": "medium",
    "cone hair bun": "medium", "donut hair bun": "medium",
    "heart hair bun": "medium", "hair rings": "medium",
    "hair down": "", "hair up": "medium", "hair pulled back": "short",
    "hair slicked back": "",
}

HAIR_MIN_LENGTH: dict[str, str] = {
    "ringlets": "medium", "drill hair": "medium", "twin drills": "medium",
    "long sidelocks": "medium", "low-tied sidelocks": "medium",
    "drill sidelocks": "medium", "hair over shoulder": "medium",
    "tress ribbon": "medium", "hair beads": "medium", "hair stick": "medium",
    "hair tubes": "medium",
}

HAIR_TEXTURES = (
    "straight hair", "wavy hair", "curly hair", "fluffy hair", "messy hair",
    "ringlets", "flipped hair", "drill hair", "twin drills", "spiked hair",
    "pointy hair",
)

HAIR_BANGS = (
    "blunt bangs", "parted bangs", "swept bangs", "crossed bangs",
    "arched bangs", "asymmetrical bangs", "bangs pinned back", "wispy bangs",
    "choppy bangs", "short bangs", "long bangs", "hair between eyes",
    "hair over one eye", "curtained hair", "middle part",
)

HAIR_EXTRAS = (
    "sidelocks", "long sidelocks", "low-tied sidelocks", "drill sidelocks",
    "hair intakes", "single hair intake", "ahoge", "heart ahoge",
    "antenna hair", "hair flaps", "hair over shoulder", "blunt ends",
)

HAIRCUTS = (
    "buzz cut", "crew cut", "pixie cut", "bob cut", "inverted bob",
    "bowl cut", "undercut", "flattop", "wolf cut", "hime cut",
    "jellyfish cut", "mullet", "afro", "pompadour", "mohawk",
)

MAKEUP = (
    "lipstick", "lipgloss", "eyeshadow", "eyeliner", "mascara",
    "nail polish", "facepaint", "face jewel", "glitter makeup",
    "toenail polish", "nail art",
)

WEARABLES: dict[str, tuple[str, ...]] = {
    "серьги": ("earrings", "hoop earrings", "stud earrings", "single earring",
               "crescent earrings", "earclip", "tassel earrings",
               "teardrop earrings", "star earrings", "heart earrings",
               "cross earrings", "sphere earrings", "flower earrings",
               "triangle earrings", "pearl earrings", "feather earrings",
               "bow earrings", "skull earrings", "crystal earrings",
               "magatama earrings", "pom pom earrings", "butterfly earrings",
               "leaf earrings", "bell earrings", "cherry earrings",
               "planet earrings", "snowflake earrings", "dangle earrings",
               "diamond-shaped earrings", "ear piercing",
               "industrial piercing", "spiked ear piercing", "ear chain",
               "ear ornament", "animal ear piercing"),
    "шея": ("necklace", "pendant", "choker", "ribbon choker", "frilled choker",
            "o-ring choker", "pendant choker", "neck ribbon", "pearl necklace",
            "bead necklace", "cross necklace", "chain necklace",
            "heart necklace", "star necklace", "magatama necklace",
            "key necklace", "tooth necklace", "flower necklace",
            "shell necklace", "crescent necklace", "pentacle",
            "skull necklace", "ring necklace", "feather necklace", "locket",
            "dog tags", "neck ring", "neck bell", "neck tassel", "lei",
            "bandana around neck", "belt collar", "spiked collar",
            "metal collar", "heart collar", "studded collar", "scarf"),
    "волосы": ("hair ribbon", "tress ribbon", "hair bow", "hairclip",
               "hairpin", "hair ornament", "x hair ornament",
               "star hair ornament", "heart hair ornament",
               "butterfly hair ornament", "feather hair ornament",
               "rabbit hair ornament", "leaf hair ornament",
               "cross hair ornament", "crescent hair ornament",
               "skull hair ornament", "pom pom hair ornament",
               "cat hair ornament", "musical note hair ornament",
               "bone hair ornament", "clover hair ornament",
               "bat hair ornament", "fish hair ornament",
               "snowflake hair ornament", "hair flower", "hairband",
               "bow hairband", "frilled hairband", "lolita hairband",
               "flower hairband", "headband", "hair scrunchie", "hair tie",
               "hair bobbles", "hair beads", "hair stick", "kanzashi",
               "hair bell", "hair tubes"),
    "голова": ("tiara", "mini crown", "crown", "circlet", "diadem",
               "laurel crown", "head wreath", "head chain", "forehead jewel",
               "bindi", "fascinator", "veil", "halo", "fake animal ears",
               "horn ornament", "hachimaki", "sweatband"),
    "лицо": ("glasses", "semi-rimless eyewear", "round eyewear",
             "under-rim eyewear", "rimless eyewear", "rectangular eyewear",
             "over-rim eyewear", "heart-shaped eyewear", "star-shaped eyewear",
             "triangular eyewear", "sunglasses", "aviator sunglasses",
             "pince-nez", "monocle", "goggles", "eyepatch", "medical eyepatch",
             "mask", "mouth mask", "surgical mask", "fox mask", "oni mask",
             "domino mask", "half mask", "masquerade mask", "sticker on face",
             "bandaid on face", "bandaid on nose", "bandaid on cheek"),
    "пирсинг": ("tongue piercing", "eyebrow piercing", "nose piercing",
                "lip piercing", "nose ring", "labret piercing",
                "bridge piercing", "chin piercing", "cheek piercing"),
    "руки": ("bracelet", "bangle", "bead bracelet", "spiked bracelet",
             "studded bracelet", "pearl bracelet", "flower bracelet",
             "chain bracelet", "wristband", "wrist cuffs", "wrist scrunchie",
             "wrist ribbon", "wrist flower", "wristwatch", "armband",
             "armlet", "arm ribbon", "arm garter", "ring", "thumb ring",
             "wedding ring", "hand jewel"),
    "ноги": ("anklet", "thigh strap", "thighlet", "leg ribbon", "thigh ribbon",
             "legwear garter", "leg belt", "ankle garter"),
    "тело": ("brooch", "corsage", "belly chain", "harness", "chest harness"),
    "хвост": ("tail ornament", "tail bow", "tail ribbon", "tail bell",
              "fake tail"),
}

def wearable_section(tag: str) -> str:
    t = (tag or "").strip().lower()
    for sec, tags in WEARABLES.items():
        if t in tags:
            return sec
    return ""


WEARABLE_SECTION_TITLE: dict[str, str] = {
    "серьги": "Серьги", "шея": "Шея", "волосы": "Украшения для волос",
    "голова": "Голова", "лицо": "Лицо", "пирсинг": "Пирсинг", "руки": "Руки",
    "ноги": "Ноги", "тело": "Тело", "хвост": "Хвост",
}
WEARABLE_SECTION_ITEM: dict[str, str] = {
    "серьги": "серьги", "шея": "украшение на шею",
    "волосы": "украшение для волос", "голова": "украшение на голову",
    "лицо": "для лица", "пирсинг": "пирсинг", "руки": "украшение на руки",
    "ноги": "украшение на ноги", "тело": "украшение на тело",
    "хвост": "украшение для хвоста",
}

WEARABLES_NSFW: dict[str, tuple[str, ...]] = {
    "украшения": ("nipple piercing", "navel piercing", "nipple chain",
                  "nipple rings", "nipple bar", "nipple jewelry",
                  "pussy piercing", "clitoris ring", "labia piercing"),
    "ошейник и оковы": ("collar", "animal collar", "padlocked collar", "leash",
                        "cuffs", "handcuffs", "shackles", "shibari",
                        "crotch rope", "chastity belt", "nipple clamps"),
    "игрушки": ("remote control vibrator", "egg vibrator",
                "vibrator under clothes", "vibrator under panties",
                "butt plug", "jewel butt plug", "anal tail", "cock ring"),
    "наклейки": ("pasties", "heart pasties", "cross pasties", "tape on nipples",
                 "maebari"),
}

UNDERWEAR_SETS: dict[str, tuple[str, str]] = {
    "lace set": ("lace bra", "lace panties"),
    "satin set": ("satin bra", "satin panties"),
    "latex set": ("latex bra", "latex panties"),
    "fur set": ("fur bra", "fur panties"),
    "see-through set": ("see-through bra", "see-through panties"),
    "bow set": ("bow bra", "bow panties"),
    "frilled set": ("frilled bra", "frilled panties"),
    "lace-trimmed set": ("lace-trimmed bra", "lace-trimmed panties"),
    "ribbon-trimmed set": ("ribbon-trimmed bra", "ribbon-trimmed panties"),
    "o-ring set": ("o-ring bra", "o-ring panties"),
    "embroidered set": ("embroidered bra", "embroidered panties"),
    "micro set": ("micro bra", "micro panties"),
    "string set": ("string bra", "string panties"),
    "sports set": ("sports bra", "sports panties"),
    "open set": ("cupless bra", "crotchless panties"),
}
BASIC_SET = "basic set"
SET_PARTS: dict[str, tuple[str, str]] = {**UNDERWEAR_SETS, BASIC_SET: ("bra", "panties")}
UW_BRA_CUTS: tuple[str, ...] = (
    "strapless bra", "front-tie bra", "frontless bra", "multi-strapped bra",
    "shelf bra", "front-hook bra")
UW_PANTIES_CUTS: tuple[str, ...] = (
    "thong", "thong panties", "highleg panties", "lowleg panties",
    "high-waist panties", "side-tie panties", "backless panties",
    "boyshort panties", "g-string", "pearl thong", "fundoshi", "strapless bottom")
UW_ONEPIECE_TOP: tuple[str, ...] = ("babydoll", "camisole", "negligee", "chemise",
                                    "bustier")
UW_FULL: tuple[str, ...] = ("bodystocking",)
UNDERWEAR: dict[str, tuple[str, ...]] = {
    "комплекты": tuple(UNDERWEAR_SETS),
    "крой лифа": UW_BRA_CUTS,
    "крой трусиков": UW_PANTIES_CUTS,
    "цельное": UW_ONEPIECE_TOP + UW_FULL,
    "подвязки": ("garter belt", "garter straps"),
    "неявное": ("bra", "panties", "lingerie", BASIC_SET),
}
LEGACY_UW_TO_SET: dict[str, str] = {
    part: key for key, parts in UNDERWEAR_SETS.items() for part in parts}
UW_REMOVED: frozenset[str] = frozenset({
    "fishnet bra", "leather bra", "fur-trimmed bra", "cross-laced panties",
    "picot trim panties", "cat ear panties"})
UW_TO_INTIMATE: frozenset[str] = frozenset(WEARABLES_NSFW["наклейки"])
LEGACY_UW_ALIAS: dict[str, str] = {"pearl panties": "pearl thong"}
SET_RU_STEMS: tuple[tuple[str, str], ...] = (
    ("кружевной кайм", "lace-trimmed set"), ("кружевной отделк", "lace-trimmed set"),
    ("кружевн", "lace set"), ("атласн", "satin set"), ("прозрачн", "see-through set"),
    ("бантик", "bow set"), ("рюш", "frilled set"), ("лент", "ribbon-trimmed set"),
    ("кольц", "o-ring set"), ("вышив", "embroidered set"), ("микро", "micro set"),
    ("тесёмк", "string set"), ("тесемк", "string set"), ("верёвоч", "string set"),
    ("спортивн", "sports set"), ("открыт", "open set"), ("прост", BASIC_SET),
)

SLOT_MIN_TIER: dict[str, str] = {"underwear": "close", "intimate": "intimate"}
_TIER_GATE_NOTE = {
    "close": "\n  СЕЙЧАС НЕДОСТУПНО: это близкая дистанция (close) — вы ещё не там.",
    "intimate": ("\n  СЕЙЧАС НЕДОСТУПНО: это самая близкая дистанция "
                 "(intimate) — вы ещё не там."),
}

UNDERWEAR_BASE_TAG = "lingerie"

UNDERWEAR_IMPLICIT: frozenset[str] = frozenset({"lingerie", "bra", "panties",
                                                BASIC_SET})


_CANON: dict[str, object] | None = None


def _canon() -> dict:
    global _CANON
    if _CANON is None:
        from drawing.tag_resolver import get_resolver
        index = get_resolver()._load_index()

        def keep(tags):
            return tuple(t for t in tags if not index or t in index
                         or (t in SET_PARTS and any(p in index for p in SET_PARTS[t])))

        _CANON = {
            "styles": {t: ml for t, ml in HAIR_STYLES.items()
                       if not index or t in index},
            "textures": keep(HAIR_TEXTURES),
            "bangs": keep(HAIR_BANGS),
            "extras": keep(HAIR_EXTRAS),
            "haircuts": keep(HAIRCUTS),
            "makeup": keep(MAKEUP),
            "wearables": {sec: keep(tags) for sec, tags in WEARABLES.items()},
            "wearable_flat": frozenset(
                t for tags in WEARABLES.values() for t in keep(tags)),
            "wearables_nsfw": {sec: keep(tags)
                               for sec, tags in WEARABLES_NSFW.items()},
            "intimate_flat": frozenset(
                t for tags in WEARABLES_NSFW.values() for t in keep(tags)),
            "underwear": {sec: keep(tags) for sec, tags in UNDERWEAR.items()},
            "underwear_flat": frozenset(
                t for tags in UNDERWEAR.values() for t in keep(tags)),
            "lengths": frozenset(get_length_tags()),
        }
    return _CANON


def get_length_tags() -> tuple[str, ...]:
    try:
        from drawing.tag_rounds import _load_tagmap
        return tuple((_load_tagmap().get("hair_styles") or {}).get("length") or ())
    except Exception:
        return ("short hair", "long hair", "very long hair", "medium hair")


def styling_state(identity) -> dict:
    raw = getattr(identity, "self_styling", None) or {}
    hair_raw = raw.get("hair") or {}
    legacy = str(raw.get("hairstyle") or "")
    state = {
        "hair": {
            "style": str(hair_raw.get("style") or legacy or ""),
            "texture": str(hair_raw.get("texture") or ""),
            "bangs": str(hair_raw.get("bangs") or ""),
            "extras": [str(t) for t in (hair_raw.get("extras") or []) if t],
        },
        "accessories": normalize_color_tags(raw.get("accessories")),
        "makeup": normalize_color_tags(raw.get("makeup")),
        "underwear": normalize_color_tags(raw.get("underwear")),
        "intimate": normalize_color_tags(raw.get("intimate")),
    }
    if state["intimate"] and not state["underwear"]:
        moved = [t for t in state["intimate"] if route_tag(t) == "underwear"
                 or parse_style_tag(t)[2] in LEGACY_UW_TO_SET]
        if moved:
            state["underwear"] = moved
            state["intimate"] = [t for t in state["intimate"]
                                 if t not in moved]
    uw, to_intimate = migrate_underwear_tags(state["underwear"])
    state["underwear"] = uw
    state["intimate"] += [t for t in to_intimate if t not in state["intimate"]]
    return state


def canonical_underwear(tag: str) -> str:
    color, pattern, item = parse_style_tag(tag)
    key = LEGACY_UW_TO_SET.get(item)
    if key is None and item in ("bra", "panties") and color:
        key = BASIC_SET
    if key is None and item.endswith(" lingerie"):
        cand = item[: -len(" lingerie")] + " set"
        key = cand if cand in UNDERWEAR_SETS else None
    if key is None:
        return tag
    if pattern and pattern not in UNDERWEAR_PATTERNS["set"]:
        pattern = None
    if key not in PATTERNED_SETS:
        pattern = None
    return join_style_tag(color, pattern, key)


def ru_set_phrase(text: str) -> str | None:
    from drawing.tag_resolver import _color_of_word
    t = " ".join((text or "").strip().lower().split())
    if "комплект" not in t:
        return None
    key = next((k for stem, k in SET_RU_STEMS if stem in t), BASIC_SET)
    color = None
    for w in t.split():
        c = _color_of_word(w)
        color = color_word(c) if c else ru_color_extra(w)
        if color:
            break
    return join_style_tag(color, None, key)


def migrate_underwear_tags(tags) -> tuple[list[str], list[str]]:
    tags = [str(t) for t in (tags or []) if str(t or "").strip()]
    out: list[str] = []
    intimate: list[str] = []
    sets: list[str] = []
    spare_color: str | None = None

    def add_set(t: str) -> None:
        sets.append(t)

    uw_flat = _canon()["underwear_flat"]
    for t in tags:
        color, pattern, item = parse_style_tag(t)
        if item in LEGACY_UW_ALIAS:
            item = LEGACY_UW_ALIAS[item]
            t = join_style_tag(color, pattern, item)
        if item in UW_TO_INTIMATE:
            intimate.append(join_style_tag(color, None, item) if color else item)
        elif item in UW_REMOVED:
            spare_color = spare_color or color
        elif uw_kind(canonical_underwear(t)) == "set" and canonical_underwear(t) != t:
            add_set(canonical_underwear(t))
        elif uw_kind(t) in ("bra_cut", "panties_cut"):
            spare_color = spare_color or color
            if not any(uw_kind(x) == uw_kind(item) for x in out):
                out.append(item)
        elif uw_kind(t) == "set":
            add_set(t)
        elif item not in uw_flat and _uw_family_word(item) in ("bra", "panties"):
            spare_color = spare_color or color
        elif t not in out:
            out.append(t)
    styled = [s for s in sets if parse_style_tag(s)[2] != BASIC_SET]
    chosen = (styled or sets or [None])[0]
    if chosen is None and spare_color:
        chosen = join_style_tag(spare_color, None, BASIC_SET)
    if chosen:
        out.insert(0, chosen)
    return out[:UNDERWEAR_CAP], intimate


def save_styling(identity, state: dict) -> None:
    prev = dict(getattr(identity, "self_styling", None) or {})
    data = {
        "hair": {
            "style": state["hair"].get("style") or "",
            "texture": state["hair"].get("texture") or "",
            "bangs": state["hair"].get("bangs") or "",
            "extras": list(state["hair"].get("extras") or []),
        },
        "accessories": list(state.get("accessories") or []),
        "makeup": list(state.get("makeup") or []),
        "underwear": list(state.get("underwear") or []),
        "intimate": list(state.get("intimate") or []),
    }
    if prev.get("defaults"):
        data["defaults"] = prev["defaults"]
    if prev.get("seeded"):
        data["seeded"] = True
    for key in ("base", "base_swap", "innate"):
        if prev.get(key):
            data[key] = list(prev[key])
    if prev.get("body"):
        data["body"] = dict(prev["body"])
    identity.self_styling = data
    try:
        identity.save()
    except Exception as e:
        print(f"[styling] identity.save fail: {type(e).__name__}: {e}")


def rewrite_slot_tags(identity, fn) -> bool:
    raw = dict(getattr(identity, "self_styling", None) or {})
    changed = False
    for key in ("accessories", "makeup", "underwear", "intimate"):
        cur = normalize_color_tags(raw.get(key))
        new = normalize_color_tags([fn(t) for t in cur])
        if new != list(raw.get(key) or []):
            if new or key in raw:
                raw[key] = new
                changed = True
    if changed:
        identity.self_styling = raw
    return changed


def is_empty(state: dict) -> bool:
    h = state.get("hair") or {}
    return not (h.get("style") or h.get("texture") or h.get("bangs")
                or h.get("extras") or state.get("accessories")
                or state.get("makeup") or state.get("underwear")
                or state.get("intimate"))


def normalize_design_styling(raw) -> dict:
    out = empty_state()
    if not raw:
        return out

    def _put(tag) -> None:
        t = str(tag or "").strip().lower()
        if not t:
            return
        slot = route_tag(t)
        if slot is None or slot in ("length", "haircut"):
            print(f"[styling] default_styling: «{t}» не роутится в слоты — "
                  f"пропущен (черты внешности — в hard_tags/промпт)")
            return
        if slot == "hair_style":
            out["hair"]["style"] = t
        elif slot == "hair_texture":
            out["hair"]["texture"] = t
        elif slot == "hair_bangs":
            out["hair"]["bangs"] = t
        elif slot == "hair_extra":
            if t not in out["hair"]["extras"]:
                out["hair"]["extras"].append(t)
        elif slot == "makeup":
            if t not in out["makeup"]:
                out["makeup"].append(t)
        elif slot == "accessory":
            if t not in out["accessories"]:
                out["accessories"].append(t)
        elif slot in ("underwear", "intimate"):
            if t not in out[slot]:
                out[slot].append(t)

    if isinstance(raw, (list, tuple)):
        for t in raw:
            _put(t)
    elif isinstance(raw, dict):
        hair = raw.get("hair") or {}
        for k in ("style", "texture", "bangs"):
            if hair.get(k):
                _put(hair[k])
        for t in (hair.get("extras") or []):
            _put(t)
        for key in ("accessories", "makeup", "underwear", "intimate"):
            for t in (raw.get(key) or []):
                _put(t)
    for key in ("accessories", "makeup", "underwear", "intimate"):
        out[key] = normalize_color_tags(out[key])
    return out


def _shim_state(slots: dict) -> dict:
    from types import SimpleNamespace
    return styling_state(SimpleNamespace(self_styling=dict(slots or {})))


def default_state(identity) -> dict:
    d = (getattr(identity, "self_styling", None) or {}).get("defaults") or {}
    return _shim_state(d) if d else empty_state()


def bare_state() -> dict:
    st = empty_state()
    st["hair"].update(BARE_HAIR)
    return st


def base_appearance_styling(appearance, renderer_id: str = "sdxl") -> list[str]:
    if not isinstance(appearance, dict):
        return []
    ba = appearance.get("base_appearance")
    if not isinstance(ba, dict):
        ba = appearance
    prompts = ba.get("renderer_prompts") or {}
    if isinstance(prompts, dict):
        text = prompts.get(renderer_id) or next(iter(prompts.values()), "") or ""
    else:
        text = prompts
    raw = [t.strip().lower() for t in str(text).replace("\n", " ").split(",")]
    raw += [str(t).strip().lower() for t in (ba.get("hard_tags") or [])]
    out: list[str] = []
    for t in raw:
        t = canon_color_tag(t) if t else t
        if not t or t in out:
            continue
        if route_tag(t) in (None, "length", "haircut"):
            continue
        out.append(t)
    return normalize_color_tags(out)


def base_appearance_swap(appearance, base_tags) -> list[str]:
    if not isinstance(appearance, dict):
        return []
    ba = appearance.get("base_appearance")
    if not isinstance(ba, dict):
        ba = appearance
    marked = {canon_color_tag(str(t)) for t in (ba.get("hairstyle_tags") or [])
              if str(t).strip()}
    return [t for t in base_tags
            if t in marked or split_item_color(t)[1] in marked]


def ensure_base_appearance(identity, appearance, renderer_id: str = "sdxl") -> bool:
    if identity is None:
        return False
    tags = base_appearance_styling(appearance, renderer_id)
    swap = base_appearance_swap(appearance, tags)
    cur = dict(getattr(identity, "self_styling", None) or {})
    if (list(cur.get("base") or []) == tags
            and list(cur.get("base_swap") or []) == swap):
        return False
    _adopt_departed_base(cur, tags)
    if tags:
        cur["base"] = tags
    else:
        cur.pop("base", None)
    if swap:
        cur["base_swap"] = swap
    else:
        cur.pop("base_swap", None)
    identity.self_styling = cur
    try:
        identity.save()
    except Exception as e:
        print(f"[styling] identity.save fail: {type(e).__name__}: {e}")
    return True


def _seed_tag(live: dict, tag: str) -> bool:
    slot = route_tag(tag)
    h = live["hair"]
    key = {"hair_style": "style", "hair_texture": "texture",
           "hair_bangs": "bangs"}.get(slot or "")
    if key:
        if h[key]:
            return False
        h[key] = tag
        return True
    lst, cap = {"hair_extra": (h["extras"], HAIR_EXTRA_CAP),
                "accessory": (live["accessories"], ACCESSORY_CAP),
                "makeup": (live["makeup"], MAKEUP_CAP)}.get(slot or "", (None, 0))
    if lst is None or tag in lst or len(lst) >= cap:
        return False
    if slot != "hair_extra" and slot_conflicts(tag, lst, slot):
        return False
    lst.append(tag)
    return True


def _adopt_departed_base(cur: dict, new_base: list[str]) -> None:
    old = [t for t in (cur.get("base") or []) if t not in set(new_base)]
    if not old:
        return
    live = _shim_state(cur)
    hidden = set(cur.get("base_swap") or []) if hair_tags(live) else set()
    moved = [t for t in old if t not in hidden and _seed_tag(live, t)]
    if moved:
        cur["hair"] = live["hair"]
        cur["accessories"] = live["accessories"]
        cur["makeup"] = live["makeup"]
        print(f"[styling] из базовой внешности в образ: {moved}")


def base_appearance_tags(identity) -> list[str]:
    return list((getattr(identity, "self_styling", None) or {}).get("base") or [])


def base_swap_tags(identity) -> list[str]:
    return list((getattr(identity, "self_styling", None) or {}).get("base_swap") or [])


def ensure_design_defaults(identity, raw) -> bool:
    if identity is None:
        return False
    design = normalize_design_styling(raw)
    design_slots = {} if is_empty(design) else {
        "hair": {"style": design["hair"]["style"],
                 "texture": design["hair"]["texture"],
                 "bangs": design["hair"]["bangs"],
                 "extras": list(design["hair"]["extras"])},
        "accessories": list(design["accessories"]),
        "makeup": list(design["makeup"]),
        "underwear": list(design["underwear"]),
        "intimate": list(design["intimate"]),
    }
    cur = dict(getattr(identity, "self_styling", None) or {})
    changed = False
    if (cur.get("defaults") or {}) != design_slots:
        if design_slots:
            cur["defaults"] = design_slots
        else:
            cur.pop("defaults", None)
        changed = True
    if design_slots and not cur.get("seeded"):
        live = _shim_state(cur)
        h = live["hair"]
        for k in ("style", "texture", "bangs"):
            if not h[k]:
                h[k] = design_slots["hair"][k]
        for t in design_slots["hair"]["extras"]:
            if t not in h["extras"]:
                h["extras"].append(t)
        for key in ("accessories", "makeup", "underwear", "intimate"):
            for t in design_slots[key]:
                if t not in live[key]:
                    live[key].append(t)
        for key in ("hair", "accessories", "makeup", "underwear", "intimate"):
            cur[key] = live[key]
        cur["seeded"] = True
        changed = True
    if changed:
        identity.self_styling = cur
        try:
            identity.save()
        except Exception as e:
            print(f"[styling] identity.save fail: {type(e).__name__}: {e}")
    return changed


def normalize_unlocked_styling(raw) -> list[str]:
    out: list[str] = []
    if not raw:
        return out
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    for tag in items:
        t = str(tag or "").strip().lower()
        if not t or t in out:
            continue
        slot = route_tag(t)
        if slot is None or slot in ("length", "haircut"):
            print(f"[styling] unlocked_styling: «{t}» не роутится в слоты — "
                  f"пропущен (стайлинг — укладки/текстура/чёлка/элементы/"
                  f"макияж/украшения)")
            continue
        out.append(t)
    return out


def ensure_design_unlocked(identity, raw) -> bool:
    if identity is None:
        return False
    tags = normalize_unlocked_styling(raw)
    cur = dict(getattr(identity, "self_styling", None) or {})
    if list(cur.get("innate") or []) == tags:
        return False
    if tags:
        cur["innate"] = tags
    else:
        cur.pop("innate", None)
    identity.self_styling = cur
    try:
        identity.save()
    except Exception as e:
        print(f"[styling] identity.save fail: {type(e).__name__}: {e}")
    return True


def innate_tags(identity) -> list[str]:
    return list((getattr(identity, "self_styling", None) or {}).get("innate") or [])


BODY_REQUIRES: dict[str, str] = {
    "ear ornament": "animal_ears", "animal ear piercing": "animal_ears",
    "tail ornament": "tail", "tail bow": "tail", "tail ribbon": "tail",
    "tail bell": "tail", "horn ornament": "horns",
}
BODY_EXCLUDES: dict[str, str] = {"fake animal ears": "animal_ears", "fake tail": "tail"}
GENDER_ONLY: dict[str, str] = {
    "cock ring": "male", "pussy piercing": "female", "clitoris ring": "female",
    "labia piercing": "female",
    "pasties": "female", "heart pasties": "female", "cross pasties": "female",
    "tape on nipples": "female", "maebari": "female",
}
SLOT_GENDER: dict[str, str] = {"underwear": "female"}
_BODY_RU = {"animal_ears": "звериных ушей", "tail": "хвоста", "horns": "рогов"}
_ANIMAL_EAR_WORDS = frozenset({
    "animal", "fox", "cat", "dog", "wolf", "rabbit", "horse", "cow", "mouse",
    "bear", "tiger", "lion", "raccoon", "sheep", "goat", "deer", "squirrel",
    "bat", "monkey", "pig", "ferret", "otter", "hamster", "jackal", "leopard",
})


def body_features(appearance, gender: str = "", renderer_id: str = "sdxl") -> dict:
    ba = appearance.get("base_appearance") if isinstance(appearance, dict) else None
    if not isinstance(ba, dict):
        ba = appearance if isinstance(appearance, dict) else {}
    prompts = ba.get("renderer_prompts") or {}
    if isinstance(prompts, dict):
        text = " , ".join(str(v) for v in prompts.values())
    else:
        text = str(prompts or "")
    tags = [t.strip().lower() for t in text.replace("\n", " ").split(",")]
    tags += [str(t).strip().lower() for t in (ba.get("hard_tags") or [])]
    tail = ears = horns = False
    for t in tags:
        words = t.split()
        if not words:
            continue
        if words[-1] == "tail":
            tail = True
        if t in ("animal ears", "animal ear fluff", "kemonomimi mode") or (
                words[-1] == "ears" and words[0] in _ANIMAL_EAR_WORDS):
            ears = True
        if any(w in ("horns", "horn") for w in words):
            horns = True
    hair_length = str(ba.get("hair_length") or "").strip().lower()
    if not hair_length:
        from drawing.assets import _HAIR_LENGTH_TAGS
        have = set(tags)
        hair_length = next((ln for tag, ln in _HAIR_LENGTH_TAGS if tag in have), "")
    return {"gender": (gender or "").strip().lower(), "tail": tail,
            "animal_ears": ears, "horns": horns, "hair_length": hair_length}


def ensure_body(identity, appearance, gender: str = "",
                renderer_id: str = "sdxl") -> bool:
    if identity is None:
        return False
    body = body_features(appearance, gender, renderer_id)
    cur = dict(getattr(identity, "self_styling", None) or {})
    if cur.get("body") == body:
        return False
    cur["body"] = body
    identity.self_styling = cur
    try:
        identity.save()
    except Exception as e:
        print(f"[styling] identity.save fail: {type(e).__name__}: {e}")
    return True


def body_of(identity) -> dict | None:
    b = (getattr(identity, "self_styling", None) or {}).get("body")
    return dict(b) if isinstance(b, dict) else None


def fits_body(item: str, body) -> bool:
    if not body:
        return True
    t = (item or "").strip().lower()
    need = BODY_REQUIRES.get(t)
    if need and not body.get(need):
        return False
    no = BODY_EXCLUDES.get(t)
    if no and body.get(no):
        return False
    g = GENDER_ONLY.get(t)
    if g and body.get("gender") and body.get("gender") != g:
        return False
    sg = SLOT_GENDER.get(route_tag(t) or "")
    if sg and body.get("gender") and body.get("gender") != sg:
        return False
    if not _length_ok(str(body.get("hair_length") or ""), hair_min_length(t)):
        return False
    return True


def slot_fits_body(slot: str, body) -> bool:
    sg = SLOT_GENDER.get(slot or "")
    return not (sg and body and body.get("gender") and body.get("gender") != sg)


def body_refusal(item: str, body) -> str:
    t = (item or "").strip().lower()
    need = BODY_REQUIRES.get(t)
    if need and not (body or {}).get(need):
        return f"у тебя нет {_BODY_RU.get(need, need)}"
    if not slot_fits_body(route_tag(t) or "", body):
        return "бельё для тебя сейчас недоступно"
    need = hair_min_length(t)
    have = str((body or {}).get("hair_length") or "")
    if not _length_ok(have, need):
        return (f"для этого нужны волосы длины {need}+, у тебя {have} — "
                f"стайлинг волосы не удлиняет")
    no = BODY_EXCLUDES.get(t)
    if no and (body or {}).get(no):
        return {"animal_ears": "у тебя свои звериные ушки — накладные ни к чему",
                "tail": "у тебя свой хвост — накладной ни к чему"}.get(
                    no, "у тебя это и так есть")
    return "это тебе не подходит"


def empty_state() -> dict:
    return {"hair": dict(_EMPTY_HAIR, extras=[]), "accessories": [],
            "makeup": [], "underwear": [], "intimate": []}


@functools.lru_cache(maxsize=16384)
def route_tag(canon: str) -> str | None:
    from drawing.tag_resolver import split_color_prefix
    c = _canon()
    t = (canon or "").strip().lower()
    if not t:
        return None
    _, core = split_color_prefix(t)
    probes = [t, core]
    if t.split()[0] in {w.split()[0] for w in _PATTERN_WORDS} or len(t.split()) > 2:
        probes.append(parse_style_tag(t)[2])
    for probe in probes:
        if probe in c["lengths"]:
            return "length"
        if probe in c["haircuts"]:
            return "haircut"
        if probe in c["styles"]:
            return "hair_style"
        if probe in c["textures"]:
            return "hair_texture"
        if probe in c["bangs"]:
            return "hair_bangs"
        if probe in c["extras"]:
            return "hair_extra"
        if probe in c["makeup"]:
            return "makeup"
        if probe in c["wearable_flat"]:
            return "accessory"
        if probe in c["underwear_flat"]:
            return "underwear"
        if probe in c["intimate_flat"]:
            return "intimate"
    if core == "nails" or t.endswith(" nails"):
        return "makeup"
    return None


def style_min_length(tag: str) -> str:
    return _canon()["styles"].get((tag or "").strip().lower(), "")


def hair_min_length(tag: str) -> str:
    t = (tag or "").strip().lower()
    need = style_min_length(t) or HAIR_MIN_LENGTH.get(t, "")
    if not need and t:
        need = HAIR_MIN_LENGTH.get(allowance_key(t), "")
    return need


STYLE_COLORS: tuple[str, ...] = (
    "aqua", "black", "blue", "brown", "green", "grey", "gold", "orange",
    "pink", "purple", "red", "yellow", "white",
)
COLOR_RU: dict[str, str] = {
    "aqua": "бирюзовый", "black": "чёрный", "blue": "синий",
    "brown": "коричневый", "green": "зелёный", "grey": "серый",
    "gold": "золотой", "orange": "оранжевый", "pink": "розовый",
    "purple": "фиолетовый", "red": "красный", "yellow": "жёлтый",
    "white": "белый",
}
_COLOR_ALIASES: dict[str, str] = {
    "gray": "grey", "silver": "grey", "golden": "gold", "crimson": "red",
    "navy": "blue", "azure": "blue", "teal": "aqua", "cyan": "aqua",
    "magenta": "pink", "tan": "brown", "beige": "brown", "cream": "white",
    "ivory": "white", "blonde": "yellow",
}
_SPEECH_COLORS: dict[str, str] = {
    "cherry": "red", "scarlet": "red", "burgundy": "red", "maroon": "red",
    "wine": "red", "ruby": "red", "rose": "pink", "raspberry": "pink",
    "coral": "orange", "peach": "orange", "amber": "orange",
    "lemon": "yellow", "emerald": "green", "mint": "green", "lime": "green",
    "olive": "green", "violet": "purple", "lavender": "purple", "lilac": "purple",
    "plum": "purple", "sky": "blue", "turquoise": "aqua", "chocolate": "brown",
    "charcoal": "grey", "platinum": "grey",
}
_RU_COLOR_EXTRA: tuple[tuple[str, str], ...] = (
    ("вишнёв", "red"), ("вишнев", "red"), ("алые", "red"), ("алая", "red"),
    ("алый", "red"), ("рубинов", "red"), ("малинов", "pink"),
    ("коралл", "orange"), ("персиков", "orange"), ("янтарн", "orange"),
    ("лимонн", "yellow"), ("изумрудн", "green"), ("мятн", "green"),
    ("салатов", "green"), ("оливков", "green"), ("лавандов", "purple"),
    ("сливов", "purple"), ("небесн", "blue"), ("лазурн", "blue"),
    ("шоколадн", "brown"), ("графитов", "grey"), ("платинов", "grey"),
)


def speech_color(word: str) -> str | None:
    w = (word or "").strip().lower()
    return color_word(w) or _SPEECH_COLORS.get(w) or ru_color_extra(w)


def speech_color_tag(tag: str) -> str:
    words = (tag or "").strip().lower().split()
    if len(words) >= 2 and words[0] in _SPEECH_COLORS:
        try:
            from drawing.tag_resolver import get_resolver
            if " ".join(words) in get_resolver()._load_index():
                return tag
        except Exception:
            pass
        rest = " ".join(words[1:])
        item = _FORM_REVERSE.get(rest, rest)
        if item in _catalog_all() and is_colorable(item):
            return f"{_SPEECH_COLORS[words[0]]} {rest}"
    return tag


def ru_color_extra(word: str) -> str | None:
    import re
    w = (word or "").strip().lower()
    for stem, en in _RU_COLOR_EXTRA:
        if w.startswith(stem) and (w == stem or re.fullmatch(
                r"(ый|ая|ое|ые|ой|ого|ому|ым|ыми|их|им|ий|яя|ее|ей|его|ему|ую|юю|ие|ими)",
                w[len(stem):])):
            return en
    return None
_COLOR_SHADES = frozenset({"light", "dark", "pale", "deep", "bright"})

COLORLESS: frozenset[str] = frozenset({
    "lipgloss", "mascara", "facepaint", "face jewel",
    "crescent earrings", "ear piercing", "pearl necklace", "cross necklace",
    "neck bell", "hair bell", "hair tubes", "mini crown", "head wreath",
    "monocle", "wristwatch", "ring",
    "pearl thong", "nipple piercing", "navel piercing", "nipple chain",
    "pearl earrings", "crystal earrings", "industrial piercing",
    "spiked ear piercing", "ear chain", "animal ear piercing",
    "chain necklace", "ring necklace", "key necklace", "pentacle",
    "shell necklace", "tooth necklace", "dog tags", "locket",
    "laurel crown", "head chain", "bindi", "pince-nez", "aviator sunglasses",
    "goggles", "fox mask", "oni mask", "medical eyepatch", "sticker on face",
    "bandaid on face", "bandaid on nose", "bandaid on cheek", "nail art",
    "tongue piercing", "eyebrow piercing", "nose piercing", "lip piercing",
    "nose ring", "labret piercing", "bridge piercing", "chin piercing",
    "cheek piercing", "labia piercing",
    "wedding ring", "thumb ring", "chain bracelet", "pearl bracelet",
    "metal collar", "belly chain",
    "tape on nipples", "maebari", "nipple rings", "nipple bar",
    "nipple jewelry", "nipple clamps", "pussy piercing", "clitoris ring",
    "handcuffs", "shackles", "chastity belt", "cock ring",
    *UW_BRA_CUTS, *UW_PANTIES_CUTS,
})
COLOR_FORMS: dict[str, str] = {
    "hair ribbon": "{c} ribbon", "hair bow": "{c} bow",
    "hair flower": "{c} flower", "hair scrunchie": "{c} scrunchie",
    "nail polish": "{c} nails",
    "glasses": "{c}-framed eyewear", "semi-rimless eyewear": "{c}-framed eyewear",
    "sunglasses": "{c}-tinted eyewear",
    "lipstick": "{c} lips",
    "round eyewear": "{c}-framed eyewear", "under-rim eyewear": "{c}-framed eyewear",
    "rimless eyewear": "{c}-framed eyewear", "rectangular eyewear": "{c}-framed eyewear",
    "over-rim eyewear": "{c}-framed eyewear", "heart-shaped eyewear": "{c}-framed eyewear",
    "star-shaped eyewear": "{c}-framed eyewear", "triangular eyewear": "{c}-framed eyewear",
}
_FORM_REVERSE: dict[str, str] = {
    "ribbon": "hair ribbon", "bow": "hair bow", "flower": "hair flower",
    "scrunchie": "hair scrunchie", "nails": "nail polish",
}
_EYEWEAR_FORM = {"framed": "glasses", "tinted": "sunglasses"}
COLOR_PALETTES: dict[str, tuple[str, ...]] = {
    "sunglasses": ("blue", "brown", "green", "orange", "pink", "purple",
                   "red", "yellow"),
}


def color_word(word: str) -> str | None:
    w = (word or "").strip().lower()
    if w in STYLE_COLORS:
        return w
    return _COLOR_ALIASES.get(w)


def split_item_color(tag: str) -> tuple[str | None, str]:
    import re
    t = " ".join((tag or "").strip().lower().split())
    if not t or t in _catalog_all():
        return None, t
    m = re.match(r"^([a-z]+)-(framed|tinted) eyewear$", t)
    if m and color_word(m.group(1)):
        return color_word(m.group(1)), _EYEWEAR_FORM[m.group(2)]
    words = t.split()
    color, rest = None, []
    if len(words) >= 3 and words[0] in _COLOR_SHADES and color_word(words[1]):
        color, rest = color_word(words[1]), words[2:]
    elif len(words) >= 2 and color_word(words[0]):
        color, rest = color_word(words[0]), words[1:]
    if color is None:
        return None, t
    item = " ".join(rest)
    return color, _FORM_REVERSE.get(item, item)


UNDERWEAR_PATTERNS: dict[str, tuple[str, ...]] = {
    "panties": ("striped", "print", "polka dot", "plaid", "strawberry print",
                "vertical-striped", "bear print", "leopard print", "floral print",
                "ribbed", "cat print", "star print"),
    "bra": ("striped", "print", "polka dot", "plaid", "vertical-striped",
            "floral print", "leopard print"),
}
UNDERWEAR_PATTERNS["set"] = UNDERWEAR_PATTERNS["bra"]
PATTERNED_SETS: frozenset[str] = frozenset({
    "sports set", "micro set", "string set", "bow set", "frilled set",
    "lace-trimmed set", "ribbon-trimmed set", "embroidered set", "satin set"})
PATTERN_RU: dict[str, str] = {
    "striped": "в полоску", "vertical-striped": "в вертикальную полоску",
    "polka dot": "в горошек", "plaid": "в клетку", "print": "с принтом",
    "strawberry print": "с клубничками", "bear print": "с мишками",
    "leopard print": "леопардовый", "floral print": "в цветочек",
    "ribbed": "в рубчик", "cat print": "с котиками", "star print": "со звёздочками",
}
PLAIN_PATTERN = "plain"
PLAIN_LABEL = "без узора"

_PATTERN_WORDS: tuple[str, ...] = tuple(sorted(
    {p for ps in UNDERWEAR_PATTERNS.values() for p in ps}, key=len, reverse=True))
_RU_PATTERNS: tuple[tuple[str, str], ...] = (
    ("в вертикальную полоску", "vertical-striped"), ("в полоску", "striped"),
    ("в полосочку", "striped"), ("полосат", "striped"), ("в горошек", "polka dot"),
    ("в горох", "polka dot"), ("в клетку", "plaid"), ("в клеточку", "plaid"),
    ("клетчат", "plaid"), ("с принтом", "print"), ("с клубничк", "strawberry print"),
    ("клубничн", "strawberry print"), ("с мишк", "bear print"),
    ("с медвежат", "bear print"), ("леопардов", "leopard print"),
    ("в цветочек", "floral print"), ("в цветочки", "floral print"),
    ("цветочн", "floral print"), ("в рубчик", "ribbed"), ("рубчат", "ribbed"),
    ("с котик", "cat print"), ("с кошечк", "cat print"),
    ("со звёздочк", "star print"), ("со звездочк", "star print"),
    ("без узора", PLAIN_PATTERN), ("без узоров", PLAIN_PATTERN),
    ("однотонн", PLAIN_PATTERN),
)


def _uw_family_word(item: str) -> str | None:
    words = (item or "").split()
    last = words[-1] if words else ""
    if last == "bra":
        return "bra"
    if last in ("panties", "thong"):
        return "panties"
    if last == "set" and len(words) >= 2:
        return "set"
    return None


def patterns_of(item: str) -> tuple[str, ...]:
    t = (item or "").strip().lower()
    if (not t or t in UNDERWEAR_IMPLICIT or t not in PATTERNED_SETS
            or not is_colorable(t) or route_tag(t) != "underwear"):
        return ()
    return UNDERWEAR_PATTERNS["set"]


def split_pattern(text: str) -> tuple[str | None, str]:
    t = " ".join((text or "").strip().lower().split())
    for p in _PATTERN_WORDS:
        if t.startswith(p + " "):
            return p, t[len(p) + 1:]
    return None, t


def parse_style_tag(tag: str) -> tuple[str | None, str | None, str]:
    color, rest = split_item_color(tag)
    pattern, item = split_pattern(rest)
    if pattern is None:
        return color, None, rest
    if color is None:
        c2, i2 = split_item_color(item)
        if c2:
            color, item = c2, i2
    fam = _uw_family_word(item)
    if fam is None or pattern not in UNDERWEAR_PATTERNS.get(fam, ()):
        return color, None, rest
    return color, pattern, item


def join_style_tag(color: str | None, pattern: str | None, item: str) -> str:
    return " ".join(p for p in (color, pattern, item) if p)


def ru_pattern(text: str) -> tuple[str | None, str]:
    t = " ".join((text or "").strip().lower().split())
    for stem, pat in sorted(_RU_PATTERNS, key=lambda x: -len(x[0])):
        i = t.find(stem)
        if i < 0:
            continue
        j = i + len(stem)
        while j < len(t) and t[j] != " ":
            j += 1
        rest = " ".join((t[:i] + t[j:]).split())
        return pat, rest
    return None, t


def extract_pattern(text: str) -> tuple[str | None, str]:
    pat, rest = ru_pattern(text)
    if pat == PLAIN_PATTERN:
        return None, rest
    if pat:
        return pat, rest
    words = (text or "").strip().lower().split()
    if len(words) >= 2 and words[0] == PLAIN_PATTERN:
        return None, " ".join(words[1:])
    color, pat, item = parse_style_tag(text)
    if pat:
        return pat, join_style_tag(color, None, item)
    return None, text


def pattern_label(pattern: str) -> str:
    if pattern == PLAIN_PATTERN:
        return PLAIN_LABEL
    return PATTERN_RU.get(pattern or "", pattern or "")


def canon_color_tag(tag: str) -> str:
    color, pattern, item = parse_style_tag(tag)
    if color is None and pattern is None:
        return item
    return join_style_tag(color, pattern, item)


def tag_color(tag: str) -> str | None:
    return parse_style_tag(tag)[0]


def tag_pattern(tag: str) -> str | None:
    return parse_style_tag(tag)[1]


@functools.lru_cache(maxsize=16384)
def is_colorable(item: str) -> bool:
    t = (item or "").strip().lower()
    if not t or t in COLORLESS or t not in _catalog_all():
        return False
    return route_tag(t) in ("makeup", "accessory", "underwear", "intimate")


def palette(item: str) -> tuple[str, ...]:
    if not is_colorable(item):
        return ()
    return COLOR_PALETTES.get((item or "").strip().lower(), STYLE_COLORS)


def fallback_color(item: str) -> str:
    pal = palette(item)
    if not pal:
        return ""
    return "white" if "white" in pal else pal[0]


def color_label(color: str) -> str:
    return COLOR_RU.get(color or "", color or "")


_COLOR_FAMILY: dict[str, str] = {
    "ribbon choker": "choker", "neck ribbon": "ribbon",
    "frilled choker": "choker", "o-ring choker": "choker", "pendant choker": "choker",
    "belt collar": "collar", "spiked collar": "collar", "heart collar": "collar",
    "studded collar": "collar", "animal collar": "collar", "padlocked collar": "collar",
    "tress ribbon": "ribbon", "wrist ribbon": "ribbon", "arm ribbon": "ribbon",
    "leg ribbon": "ribbon", "thigh ribbon": "ribbon", "tail ribbon": "ribbon",
    "tail bow": "bow",
    "bow hairband": "hairband", "frilled hairband": "hairband",
    "lolita hairband": "hairband", "flower hairband": "hairband",
    "wrist scrunchie": "scrunchie",
    "mouth mask": "mask", "surgical mask": "mask", "domino mask": "mask",
    "half mask": "mask", "masquerade mask": "mask",
    "shibari": "rope", "crotch rope": "rope",
}
_OWN_COLOR_TAG = frozenset({"sports bra", "thong", "pearl thong"})


def render_color_tags(tag: str) -> list[str]:
    color, pattern, item = parse_style_tag(tag)
    if item in SET_PARTS:
        return render_set_tags(color, pattern, item)
    if not is_colorable(allowance_key(item)):
        return [tag]
    uw_fam = _uw_family_word(item)
    if color is None and pattern is None:
        if uw_fam and item not in _OWN_COLOR_TAG and item != uw_fam:
            return [uw_fam, item]
        return [tag]
    if uw_fam and item not in _OWN_COLOR_TAG:
        out = [uw_fam] if item == uw_fam else [uw_fam, item]
        if color:
            out.append(f"{color} {uw_fam}")
        if pattern:
            out.append(f"{pattern} {uw_fam}")
        return out
    out = [item]
    if color:
        form = COLOR_FORMS.get(item)
        fam = _COLOR_FAMILY.get(item)
        out.append(form.format(c=color) if form else
                   f"{color} {fam}" if fam else f"{color} {item}")
    if pattern:
        out.append(f"{pattern} {uw_fam}")
    return out


def _render_set_part(color: str | None, pattern: str | None, part: str) -> list[str]:
    fam = _uw_family_word(part) or part
    tags = [fam] if part == fam else [fam, part]
    if color:
        tags.append(f"{color} {part}" if part in _OWN_COLOR_TAG else f"{color} {fam}")
    if pattern:
        tags.append(f"{pattern} {fam}")
    return tags


def render_set_tags(color: str | None, pattern: str | None, key: str,
                    *, zones: tuple[str, ...] = ("top", "bottom")) -> list[str]:
    top, bottom = SET_PARTS.get(key, ("", ""))
    out: list[str] = []
    for zone, part in (("top", top), ("bottom", bottom)):
        if part and zone in zones:
            out.extend(t for t in _render_set_part(color, pattern, part) if t not in out)
    return out


def normalize_color_tags(tags) -> list[str]:
    canon = [canon_color_tag(str(t)) for t in (tags or []) if str(t or "").strip()]
    colored = set()
    for t in canon:
        c, p, it = parse_style_tag(t)
        if c or p:
            colored.add(it)
    out: list[str] = []
    for t in canon:
        if t in colored:
            continue
        if t not in out:
            out.append(t)
    return out


class Allowance(frozenset):
    def __new__(cls, keys=(), colors=None, patterns=None, body=None):
        obj = super().__new__(cls, keys)
        obj.colors = {k: tuple(v) for k, v in (colors or {}).items()}
        obj.patterns = {k: tuple(v) for k, v in (patterns or {}).items()}
        obj.body = dict(body) if body else None
        return obj

    def open_colors(self, item: str) -> tuple[str, ...]:
        if item in UNDERWEAR_IMPLICIT:
            return palette(item)
        return self.colors.get(item, ())

    def open_patterns(self, item: str) -> tuple[str, ...]:
        return self.patterns.get(item, ())


def open_colors(allowed, item: str) -> tuple[str, ...] | None:
    if allowed is None or not isinstance(allowed, Allowance) or not is_colorable(item):
        return None
    return allowed.open_colors(item)


def open_patterns(allowed, item: str) -> tuple[str, ...] | None:
    if allowed is None or not isinstance(allowed, Allowance) or not patterns_of(item):
        return None
    return allowed.open_patterns(item)


def pick_color(allowed, item: str, prefer: str | None = None) -> str | None:
    cols = open_colors(allowed, item)
    if not cols:
        return None
    if prefer and prefer in cols:
        return prefer
    if set(cols) >= set(palette(item)):
        return None
    return cols[-1]


def color_mark(item: str, cols, pats=()) -> str:
    cols = list(cols or ())
    pats = list(pats or ())
    part = ""
    if cols:
        if set(cols) >= set(palette(item)):
            part = "все"
        elif len(cols) == 1:
            part = cols[0]
        else:
            part = f"{len(cols)}c"
    if pats:
        pp = pats[0] if len(pats) == 1 else f"узоры {len(pats)}"
        part = f"{part}; {pp}" if part else pp
    return part


COLOR_MARK_LEGEND = (
    "В скобках у вещи — открытые цвета: (white) — один, (4c) — четыре, (все) — "
    "любой. Какие именно у вещи — style_self(options=\"<вещь>\"); всё открытое "
    "в одном цвете — style_self(options=\"<цвет>\"). Не угадывай цвет — проверь.")


def option_item(canon: str) -> tuple[str | None, str]:
    color, item = split_item_color(canon_color_tag(canon))
    key = allowance_key(item)
    key = _FORM_REVERSE.get(key, key)
    if key not in _catalog_all():
        return color, ""
    return color, key


def item_patterns_text(item: str, allowed, *, asked: str | None = None) -> str:
    pats = patterns_of(item)
    if not pats:
        return ""
    got = open_patterns(allowed, item)
    got = pats if got is None else got
    if got:
        s = (f"Узоры: без узора — всегда; открыто {len(got)} из {len(pats)}: "
             f"{', '.join(got)} — носятся вместе с цветом: add [\"<цвет> <узор> "
             f"{item}\"].")
    else:
        s = ("Узоры: пока только без узора — остальные выпадают из билетов "
             "удачи, как цвета.")
    if asked:
        s += (f" {asked} — {'открыт' if asked in got else 'ещё не открыт'}."
              if asked in pats else f" Узора {asked} у этой вещи не бывает.")
    return s


def item_colors_text(item: str, allowed, *, label: str = "", worn: str = "",
                     asked: str | None = None, asked_pattern: str | None = None) -> str:
    name = f"{item} ({label})" if label and label != item else item
    family = []
    last = item.split()[-1]
    for t in sorted(_catalog_all()):
        if (t != item and t.split()[-1] == last and t not in UNDERWEAR_IMPLICIT
                and tag_allowed(t, allowed)):
            family.append(with_open_colors(t, allowed))
    fam = (" Того же рода у тебя открыто: " + ", ".join(family) + "."
           if family else "")
    if allowed is not None and item not in allowed:
        return (f"{name} — этого у тебя пока нет: вещь выпадает из билетов "
                f"удачи.{fam}")
    pal = palette(item)
    if not pal:
        return f"{name} — открыто; цвет у этой вещи не выбирается.{fam}"
    cols = open_colors(allowed, item)
    if cols is None:
        cols = pal
    if set(cols) >= set(pal):
        head = f"{name} — открыт любой цвет: {', '.join(pal)}."
    elif cols:
        head = (f"{name} — открыто цветов {len(cols)} из {len(pal)}: "
                f"{', '.join(cols)}. Остальные выпадают из билетов удачи.")
    else:
        head = (f"{name} — открыто, но ни одного цвета: надевается без цвета. "
                f"Цвета выпадают из билетов удачи.")
    parts = [head]
    if worn:
        parts.append(f"Сейчас на тебе: {worn}.")
    if asked:
        if asked not in pal:
            parts.append(f"Цвета {asked} у этой вещи не бывает.")
        else:
            parts.append(f"{asked} — {'открыт' if asked in cols else 'ещё не открыт'}.")
    if cols:
        pick = asked if asked in cols else "<цвет>"
        parts.append(f"Надеть: add [\"{pick} {item}\"].")
    pat = item_patterns_text(item, allowed, asked=asked_pattern)
    if pat:
        parts.append(pat)
    return " ".join(parts) + fam


def _color_sections(category: str, allow_nsfw: bool, underwear_ok: bool,
                    intimate_ok: bool) -> list[tuple[str, list[str]]]:
    c = _canon()
    secs: list[tuple[str, list[str]]] = []
    if category in ("", "makeup"):
        secs.append(("макияж", list(c["makeup"])))
    if category in ("", "accessories"):
        secs.append(("украшения", [t for tags in c["wearables"].values() for t in tags]))
    if allow_nsfw and underwear_ok and category in ("", "underwear"):
        secs.append(("бельё", [t for tags in c["underwear"].values() for t in tags]))
    if allow_nsfw and intimate_ok and category in ("", "accessories", "intimate"):
        secs.append(("под одеждой", [t for tags in c["wearables_nsfw"].values() for t in tags]))
    return secs


def _open_in_color(color: str, tags, allowed) -> tuple[list[str], list[str]]:
    exact: list[str] = []
    anyc: list[str] = []
    for t in tags:
        if t in UNDERWEAR_IMPLICIT or color not in palette(t):
            continue
        if not tag_allowed(f"{color} {t}", allowed):
            continue
        cols = open_colors(allowed, t)
        (anyc if cols is not None and set(cols) >= set(palette(t)) else exact).append(t)
    return exact, anyc


def color_catalog(color: str, allowed, *, category: str = "",
                  allow_nsfw: bool = False, underwear_ok: bool = False,
                  intimate_ok: bool = False) -> str:
    if category == "hair":
        return "У причёсок цвета нет — цвет задаётся украшениям, макияжу и белью."
    exact: list[str] = []
    anyc: list[str] = []
    for title, tags in _color_sections(category, allow_nsfw, underwear_ok, intimate_ok):
        got, anyc_sec = _open_in_color(color, tags, allowed)
        anyc += anyc_sec
        if got:
            exact.append(f"{title} — {', '.join(got)}")
    if not exact and not anyc:
        return (f"В цвете {color} у тебя пока ничего не открыто. Цвета вещей "
                f"выпадают из билетов удачи.")
    out = []
    if exact:
        out.append(f"Открыто в цвете {color}: " + "; ".join(exact) + ".")
    if anyc:
        out.append("Любого цвета (значит, и этого): " + ", ".join(anyc) + ".")
    out.append(f"Надеть: add [\"{color} <вещь>\"].")
    return " ".join(out)


def color_index(allowed, *, category: str = "", allow_nsfw: bool = False,
                underwear_ok: bool = False, intimate_ok: bool = False) -> str:
    if not isinstance(allowed, Allowance) or category == "hair":
        return ""
    tags = [t for _, ts in _color_sections(category, allow_nsfw, underwear_ok,
                                           intimate_ok) for t in ts]
    counts: list[tuple[int, str]] = []
    any_all: set[str] = set()
    for col in STYLE_COLORS:
        exact, anyc = _open_in_color(col, tags, allowed)
        any_all |= set(anyc)
        if exact:
            counts.append((len(exact), col))
    if not counts and not any_all:
        return ""
    counts.sort(key=lambda x: (-x[0], STYLE_COLORS.index(x[1])))
    line = " · ".join(f"{col} {n}" for n, col in counts)
    if any_all:
        line += (" · " if line else "") + f"+{len(any_all)} любого цвета"
    return (f"Открыто по цветам (вещей): {line}. Подобрать в тон или по цвету — "
            f"options=\"<цвет>\" (какие именно вещи).")


def section_catalog(section: str, allowed) -> str:
    tags = _canon()["wearables"].get(section) or ()
    title = WEARABLE_SECTION_TITLE.get(section, section)
    got = [with_open_colors(t, allowed) for t in tags if tag_allowed(t, allowed)]
    locked = sum(1 for t in tags if not tag_allowed(t, allowed)
                 and fits_body(t, getattr(allowed, "body", None)))
    if not got:
        return (f"{title}: пока ничего не открыто — такое выпадает из билетов "
                f"удачи (в разделе ещё {locked}).")
    tail = f" Ещё не открыто: {locked}." if locked and allowed is not None else ""
    return (f"{title} (до {ACCESSORY_CAP} украшений всего): {', '.join(got)}.{tail} "
            f"Вещь того же рода заменяет прежнюю. Какие цвета — options=\"<вещь>\".")


def with_open_colors(item: str, allowed) -> str:
    mark = color_mark(item, open_colors(allowed, item), open_patterns(allowed, item))
    return f"{item} ({mark})" if mark else item


_CORE_ALIAS = {"nails": "nail polish"}
_CATALOG_ALL: frozenset[str] | None = None


def _catalog_all() -> frozenset[str]:
    global _CATALOG_ALL
    if _CATALOG_ALL is None:
        c = _canon()
        _CATALOG_ALL = frozenset(
            set(c["styles"]) | set(c["textures"]) | set(c["bangs"])
            | set(c["extras"]) | set(c["makeup"]) | c["wearable_flat"]
            | c["underwear_flat"] | c["intimate_flat"])
    return _CATALOG_ALL


def allowance_key(tag: str) -> str:
    t = (tag or "").strip().lower()
    if not t:
        return ""
    if t in _catalog_all():
        return t
    color, pattern, item = parse_style_tag(t)
    if (color is not None or pattern is not None) and item in _catalog_all():
        return item
    from drawing.tag_resolver import split_color_prefix
    core = split_color_prefix(item)[1]
    return _CORE_ALIAS.get(core, core)


def tag_allowed(tag: str, allowed) -> bool:
    if allowed is None:
        return True
    k = allowance_key(tag)
    if not k or k not in allowed:
        return False
    if not fits_body(k, getattr(allowed, "body", None)):
        return False
    color, pattern, _ = parse_style_tag(tag)
    pats = open_patterns(allowed, k)
    if pattern is not None and pats is not None and pattern not in pats:
        return False
    cols = open_colors(allowed, k)
    if cols is None or color is None:
        return True
    return color in cols


def style_core(tag: str) -> str:
    from drawing.tag_resolver import split_color_prefix
    t = (tag or "").strip().lower()
    while True:
        mod, core = split_color_prefix(t)
        if mod is None or not core or core == t:
            return t
        t = core


def _uw_family(core: str) -> str | None:
    words = core.split()
    last = words[-1] if words else ""
    if last == "bra":
        return "bra"
    if last in ("panties", "thong") or core == "thong":
        return "panties"
    if core in ("g-string", "fundoshi", "strapless bottom"):
        return "panties"
    return None


def uw_kind(tag: str) -> str | None:
    color, pattern, item = parse_style_tag(tag)
    if item in SET_PARTS:
        return "set"
    if item in UW_FULL:
        return "full"
    if item in UW_ONEPIECE_TOP:
        return "onepiece"
    if item in UW_BRA_CUTS:
        return "bra_cut"
    if item in UW_PANTIES_CUTS:
        return "panties_cut"
    return None


_UW_CLASH: dict[str, frozenset[str]] = {
    "set": frozenset({"set", "full"}),
    "onepiece": frozenset({"onepiece", "full"}),
    "full": frozenset({"set", "onepiece", "full"}),
    "bra_cut": frozenset({"bra_cut"}),
    "panties_cut": frozenset({"panties_cut"}),
}


def _acc_family(core: str) -> str | None:
    words = core.split()
    last = words[-1] if words else ""
    if last in ("earrings", "earring") or core == "earclip":
        return "earrings"
    if last == "eyewear" or core in ("glasses", "sunglasses", "aviator sunglasses",
                                     "pince-nez", "monocle"):
        return "eyewear"
    if last == "mask":
        return "mask"
    if last == "eyepatch":
        return "eyepatch"
    if core in ("tiara", "mini crown", "crown", "circlet", "diadem", "laurel crown"):
        return "crown"
    if last in ("hairband", "headband"):
        return "hairband"
    if last == "choker":
        return "choker"
    if last == "collar":
        return "collar"
    if core in ("pasties", "heart pasties", "cross pasties", "tape on nipples"):
        return "pasties"
    return None


def slot_conflicts(canon: str, existing: list[str], slot: str) -> list[str]:
    new_core = style_core(canon)
    new_kind = uw_kind(canon) if slot == "underwear" else None
    out: list[str] = []
    for old in existing:
        if old == canon:
            continue
        old_core = style_core(old)
        clash = old_core == new_core
        if not clash and slot == "underwear":
            clash = uw_kind(old) in _UW_CLASH.get(new_kind or "", ())
            if not clash and new_kind is None:
                f_new, f_old = _uw_family(new_core), _uw_family(old_core)
                clash = f_new is not None and f_new == f_old
        if not clash and slot in ("accessory", "intimate"):
            f_new, f_old = _acc_family(new_core), _acc_family(old_core)
            clash = f_new is not None and f_new == f_old
        if clash:
            out.append(old)
    return out


def underwear_zone_of(tag: str) -> str:
    core = style_core(tag)
    if _uw_family(core) == "bra" or core in _PASTIES:
        return "top"
    if _uw_family(core) == "panties" or core == "maebari":
        return "bottom"
    if core in ("garter belt", "garter straps"):
        return "bottom"
    if core in ("babydoll", "camisole", "negligee", "chemise", "bustier"):
        return "top"
    return "set"


_UW_SET_ITEMS = frozenset({"bodystocking", "teddy", "nightgown"})
_PASTIES = frozenset({"pasties", "heart pasties", "cross pasties", "tape on nipples"})


def underwear_item_zone(tag: str) -> str | None:
    t = (tag or "").strip().lower()
    if not t or t.startswith("no "):
        return None
    core = style_core(t)
    if core == UNDERWEAR_BASE_TAG:
        return None
    if core in _UW_SET_ITEMS:
        return "set"
    if (_uw_family(core) is None and core not in _PASTIES and core != "maebari"
            and core not in ("garter belt", "garter straps", "babydoll", "camisole",
                             "negligee", "chemise", "bustier")):
        return None
    return underwear_zone_of(t)


def character_base_appearance(state: dict | None):
    if not state:
        return None
    try:
        from drawing.assets import BaseAppearance
        store = state.get("store")
        cid = state.get("character_id")
        archive = store.get_archive(cid) if (store and cid) else None
        if archive is None or not archive.has_entry("visual/appearance.yaml"):
            return None
        return BaseAppearance.from_dict(archive.read_yaml("visual/appearance.yaml"))
    except Exception:
        return None


def character_hair_length(state: dict | None) -> str:
    ba = character_base_appearance(state)
    if ba is None:
        return ""
    try:
        from drawing.assets import derive_hair_length
        rid = "sdxl"
        cfg = state.get("config")
        if cfg is not None:
            rid = getattr(cfg.drawing, "renderer_id", "sdxl") or "sdxl"
        return derive_hair_length(ba, rid) or ""
    except Exception:
        return ""


def _length_ok(cur_len: str, need: str) -> bool:
    if not need or not cur_len:
        return True
    try:
        from drawing.assets import hair_length_ge
        return hair_length_ge(cur_len, need)
    except Exception:
        return True


def options_catalog(cur_len: str = "", category: str = "",
                    allow_nsfw: bool = False, underwear_ok: bool = False,
                    intimate_ok: bool = False, allowed=None) -> str:
    c = _canon()
    parts: list[str] = []
    colors_on = isinstance(allowed, Allowance)

    def ok(tags):
        return [with_open_colors(t, allowed) for t in tags
                if t not in UNDERWEAR_IMPLICIT and tag_allowed(t, allowed)
                and _length_ok(cur_len, hair_min_length(t))]

    def secs_of(d: dict, sep: str) -> str:
        return sep.join(f"{sec}: {', '.join(ok(tags))}"
                        for sec, tags in d.items() if ok(tags))

    if category in ("", "hair"):
        styles = ok(t for t, ml in c["styles"].items()
                    if _length_ok(cur_len, ml))
        head = "ПРИЧЁСКА — слоты (каждый опционален, свободные слова или тег):"
        if cur_len:
            head += f" [показано под твою длину волос: {cur_len}]"
        parts.append(
            head
            + "\n  укладка (одна): " + (", ".join(sorted(styles)) or "—")
            + "\n  текстура (одна): " + (", ".join(ok(c["textures"])) or "—")
            + "\n  чёлка (одна): " + (", ".join(ok(c["bangs"])) or "—")
            + f"\n  элементы (до {HAIR_EXTRA_CAP}): "
            + (", ".join(ok(c["extras"])) or "—")
            + "\n  Длина волос и стрижки НЕ меняются — только укладка.")
    if category in ("", "makeup"):
        parts.append(
            f"МАКИЯЖ (до {MAKEUP_CAP}): " + (", ".join(ok(c["makeup"])) or "—")
            + "\n  Цвет добавляй словом: «red lipstick», «blue eyeshadow», "
              "«black nail polish». Новый цвет того же типа сам заменит "
              "прежний — снимать отдельно не нужно.")
    if category in ("", "accessories"):
        parts.append(
            f"АКСЕССУАРЫ (до {ACCESSORY_CAP}): "
            + (secs_of(c["wearables"], "; ") or "—")
            + "\n  Цвет/материал — словом: «gold earrings», «pearl necklace», "
              "«red ribbon choker».")
    def gate_note(ok: bool, slot: str) -> str:
        return "" if ok else _TIER_GATE_NOTE[SLOT_MIN_TIER[slot]]

    if (allow_nsfw and category in ("", "underwear", "intimate")
            and slot_fits_body("underwear", getattr(allowed, "body", None))):
        secs = secs_of(c["underwear"], "\n  ") or "—"
        parts.append(
            f"БЕЛЬЁ, 18+ (до {UNDERWEAR_CAP}). Видно ТОЛЬКО на откровенных "
            f"кадрах; базовый «lingerie» система ставит там сама. Собирается так: "
            f"КОМПЛЕКТ — лиф и трусики одного стиля, на тебе один; цвет — словом: "
            f"«black lace set», у некоторых бывает узор — вместе с цветом: «white "
            f"polka dot frilled set» (открытые узоры — после «;» в скобках). Без "
            f"своего комплекта — простой в любом цвете: «{BASIC_SET}» с цветом "
            f"(«black {BASIC_SET}»). КРОЙ — по одному на лиф и на трусики, своего "
            f"цвета нет, берёт цвет комплекта («strapless bra», «thong»). "
            f"ЦЕЛЬНОЕ сверху (babydoll, chemise…) заменяет лиф комплекта, "
            f"bodystocking — весь комплект. Подвязки — поверх. Новое того же "
            f"рода само заменит прежнее:\n  {secs}"
            f"{gate_note(underwear_ok, 'underwear')}")
    if allow_nsfw and category in ("", "accessories", "intimate"):
        secs = secs_of(c["wearables_nsfw"], "; ") or "—"
        parts.append(
            f"ИНТИМНЫЕ УКРАШЕНИЯ, 18+ (до {INTIMATE_CAP}; видно ТОЛЬКО на "
            f"откровенных кадрах): {secs}{gate_note(intimate_ok, 'intimate')}")
    if allowed is not None:
        parts.append("Показано только то, что уже открыто для твоего образа "
                     "(«—» = в этой категории пока ничего). Новое выпадает из "
                     "билетов удачи, которые вы открываете вместе в чате.")
    if colors_on:
        idx = color_index(allowed, category=category, allow_nsfw=allow_nsfw,
                          underwear_ok=underwear_ok, intimate_ok=intimate_ok)
        if idx:
            parts.append(idx)
        parts.append(COLOR_MARK_LEGEND + " Цвет — словом перед вещью: «red "
                     "choker»; не назовёшь — наденется тот, что на тебе, или "
                     "последний открытый.")
    return "\n\n".join(parts)


def category_hint(slot: str, cur_len: str = "", allowed=None) -> str:
    c = _canon()

    def ok(tags):
        return [with_open_colors(t, allowed) for t in tags
                if t not in UNDERWEAR_IMPLICIT and tag_allowed(t, allowed)
                and _length_ok(cur_len, hair_min_length(t))]

    def secs_of(d: dict) -> str:
        return "; ".join(f"{s}: {', '.join(ok(t))}"
                         for s, t in d.items() if ok(t)) or "—"

    if slot in ("hair_style", "haircut", "length"):
        styles = ok(t for t, ml in c["styles"].items() if _length_ok(cur_len, ml))
        return "Доступные укладки: " + (", ".join(sorted(styles)) or "—")
    if slot == "hair_texture":
        return "Текстуры: " + (", ".join(ok(c["textures"])) or "—")
    if slot == "hair_bangs":
        return "Чёлки: " + (", ".join(ok(c["bangs"])) or "—")
    if slot == "hair_extra":
        return "Элементы причёски: " + (", ".join(ok(c["extras"])) or "—")
    if slot == "makeup":
        return "Макияж: " + (", ".join(ok(c["makeup"])) or "—")
    if slot == "accessory":
        return "Носимое: " + secs_of(c["wearables"])
    if slot == "underwear":
        return "Бельё (18+): " + secs_of(c["underwear"])
    if slot == "intimate":
        return "Интимные украшения (18+): " + secs_of(c["wearables_nsfw"])
    return ""


def hair_tags(state: dict) -> list[str]:
    h = state.get("hair") or {}
    out = [h.get("style") or "", h.get("texture") or "", h.get("bangs") or ""]
    out += list(h.get("extras") or [])
    return [t for t in out if t]


def render_parts(state: dict) -> tuple[list[str], list[str], list[str], list[str]]:
    def expand(tags) -> list[str]:
        out: list[str] = []
        for t in tags or []:
            for x in render_color_tags(t):
                if x not in out:
                    out.append(x)
        return out

    extra = expand(list(state.get("accessories") or [])
                   + list(state.get("makeup") or []))
    return (hair_tags(state), extra,
            render_underwear(state.get("underwear")),
            expand(state.get("intimate")))


def render_underwear(tags) -> list[str]:
    tags = list(tags or [])
    kinds = {uw_kind(t) for t in tags}
    out: list[str] = []
    for t in tags:
        color, pattern, item = parse_style_tag(t)
        if item in SET_PARTS:
            if "full" in kinds:
                continue
            zones = ("bottom",) if "onepiece" in kinds else ("top", "bottom")
            rendered = render_set_tags(color, pattern, item, zones=zones)
        else:
            rendered = render_color_tags(t)
        out.extend(x for x in rendered if x not in out)
    return out


def describe(state: dict, *, include_intimate: bool = True) -> str:
    parts = []
    ht = hair_tags(state)
    if ht:
        parts.append("причёска: " + ", ".join(ht))
    if state.get("accessories"):
        parts.append("надето: " + ", ".join(state["accessories"]))
    if state.get("makeup"):
        parts.append("макияж: " + ", ".join(state["makeup"]))
    if include_intimate and state.get("underwear"):
        parts.append("бельё: " + ", ".join(state["underwear"]))
    if include_intimate and state.get("intimate"):
        parts.append("под одеждой: " + ", ".join(state["intimate"]))
    return "; ".join(parts)
