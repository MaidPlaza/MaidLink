from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


RATING_ORDER: dict[str, int] = {
    "sfw": 0,
    "suggestive": 1,
    "nsfw": 2,
}

TIER_ORDER: dict[str, int] = {
    "estranged": 0,
    "distant": 1,
    "warming": 2,
    "close": 3,
    "intimate": 4,
}

TIER_LABELS_RU: dict[str, str] = {
    "estranged": "отчуждение",
    "distant": "дистанция",
    "warming": "потепление",
    "close": "близость",
    "intimate": "полное доверие",
}


ASPECT_SQUARE = "square"
ASPECT_TALL = "tall"
ASPECT_WIDE = "wide"
ASPECT_PORTRAIT_COMPACT = "portrait_compact"
VALID_ASPECTS: tuple[str, ...] = (
    ASPECT_SQUARE, ASPECT_TALL, ASPECT_WIDE, ASPECT_PORTRAIT_COMPACT)

ASPECT_DIMENSIONS: dict[str, tuple[int, int]] = {
    ASPECT_SQUARE: (1536, 1536),
    ASPECT_TALL:   (1024, 1536),
    ASPECT_WIDE:   (1536, 1024),
    ASPECT_PORTRAIT_COMPACT: (688, 1024),
}
DEFAULT_ASPECT = ASPECT_SQUARE


def aspect_to_dimensions(aspect: str) -> tuple[int, int]:
    return ASPECT_DIMENSIONS.get(aspect, ASPECT_DIMENSIONS[DEFAULT_ASPECT])



def rating_le(rating: str, max_rating: str) -> bool:
    return RATING_ORDER.get(rating, 999) <= RATING_ORDER.get(max_rating, -1)


def tier_ge(current_tier: str, required_tier: str) -> bool:
    return TIER_ORDER.get(current_tier, -1) >= TIER_ORDER.get(required_tier, 999)


def effective_required_tier(
    outfit_global_tier: str,
    outfit_tags: list[str] | tuple[str, ...],
    character_tag_gates: dict[str, str] | None = None,
    character_blocked_tags: list[str] | tuple[str, ...] | None = None,
) -> str | None:
    blocked = set(character_blocked_tags or [])
    for tag in outfit_tags:
        if tag in blocked:
            return None

    tiers_to_check = [outfit_global_tier]
    gates = character_tag_gates or {}
    for tag in outfit_tags:
        char_min = gates.get(tag)
        if char_min:
            tiers_to_check.append(char_min)

    return max(tiers_to_check, key=lambda t: TIER_ORDER.get(t, -1))


@dataclass(frozen=True)
class RendererPrompt:
    positive: str = ""
    negative: str = ""

    @classmethod
    def from_dict(cls, data) -> "RendererPrompt":
        if isinstance(data, str):
            return cls(positive=data, negative="")
        if isinstance(data, dict):
            return cls(
                positive=str(data.get("positive", "")).strip(),
                negative=str(data.get("negative", "")).strip(),
            )
        return cls()


@dataclass(frozen=True)
class CharacterRestrictions:
    required_archetypes: tuple[str, ...] = ()
    block_list: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict | None) -> "CharacterRestrictions":
        if not data:
            return cls()
        return cls(
            required_archetypes=tuple(data.get("required_archetypes") or ()),
            block_list=tuple(data.get("block_list") or ()),
        )

    def is_universal(self) -> bool:
        return not self.required_archetypes

    def allows_character(self, character_id: str, archetypes: list[str]) -> bool:
        if character_id in self.block_list:
            return False
        if not self.required_archetypes:
            return True
        return any(a in self.required_archetypes for a in archetypes)


@dataclass(frozen=True)
class Compatibility:
    scenes: tuple[str, ...] = ()
    blocks: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict | None) -> "Compatibility":
        if not data:
            return cls()
        return cls(
            scenes=tuple(data.get("scenes") or ()),
            blocks=tuple(data.get("blocks") or ()),
        )


@dataclass(frozen=True)
class BaseAppearance:
    description: str = ""
    hard_tags: tuple[str, ...] = ()
    renderer_prompts: dict[str, str] = field(default_factory=dict)
    hair_length: str = ""
    hairstyle_tags: tuple[str, ...] = ()
    favorite_colors: tuple[str, ...] = ()
    mood_expressions: dict[str, str] = field(default_factory=dict)
    negative_tags: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict | None) -> "BaseAppearance":
        if not data:
            return cls()
        body = data.get("base_appearance", data)
        if not isinstance(body, dict):
            return cls()
        me_src = data.get("mood_expressions") or body.get("mood_expressions") or {}
        return cls(
            description=str(body.get("description", "")),
            hard_tags=tuple(body.get("hard_tags") or ()),
            negative_tags=tuple(
                str(t).strip() for t in (body.get("negative_tags") or ())
                if str(t).strip()
            ),
            renderer_prompts={
                k: str(v)
                for k, v in (body.get("renderer_prompts") or {}).items()
                if v
            },
            hair_length=str(body.get("hair_length", "") or "").strip().lower(),
            hairstyle_tags=tuple(
                str(t).strip() for t in (body.get("hairstyle_tags") or ())
                if str(t).strip()
            ),
            favorite_colors=tuple(
                str(c).strip() for c in (body.get("favorite_colors") or ()) if str(c).strip()
            ),
            mood_expressions={
                str(k).strip(): str(v).strip()
                for k, v in me_src.items()
                if str(v).strip()
            },
        )

    def positive_for(self, renderer_id: str) -> str:
        return self.renderer_prompts.get(renderer_id, "")


HAIR_LENGTH_ORDER: dict[str, int] = {
    "very short": 0, "short": 1, "medium": 2, "long": 3,
    "very long": 4, "absurdly long": 5,
}

_HAIR_LENGTH_TAGS: tuple[tuple[str, str], ...] = (
    ("absurdly long hair", "absurdly long"),
    ("very long hair", "very long"),
    ("very short hair", "very short"),
    ("long hair", "long"),
    ("short hair", "short"),
    ("medium hair", "medium"),
)


def derive_hair_length(appearance: "BaseAppearance", renderer_id: str) -> str:
    explicit = (getattr(appearance, "hair_length", "") or "").strip().lower()
    if explicit:
        return explicit
    prompt = (appearance.positive_for(renderer_id) or "").lower()
    for tag, length in _HAIR_LENGTH_TAGS:
        if tag in prompt:
            return length
    return ""


HEADLESS_HAIR_MIN: dict[str, str] = {
    "face": "medium", "head_shoulders": "medium", "upper_body": "medium",
    "cowboy": "very long", "full": "absurdly long",
}
_HAIR_TOP_WORDS = ("bangs", "ahoge", "ornament", "hairclip", "hair clip", "hairband",
                   "hair band", "hair flower", "hair bow", "hair ribbon", "bun",
                   "between eyes", "intakes", "over one eye", "over eyes", "hair up",
                   "hairpin", "hair stick", "hime cut", "headband")
_HAIR_HANGING_WORDS = ("braid", "twintail", "ponytail", "sidelock", "drill", "ringlet")
_BODY_HAIR = ("chest hair", "arm hair", "pubic hair", "leg hair", "armpit hair")


def hair_in_frame(base_positive: str, hair_length: str, floor: str | None) -> list[str]:
    need = HEADLESS_HAIR_MIN.get(floor or "")
    if not need or not hair_length_ge(hair_length, need):
        return []
    out = []
    for raw in (base_positive or "").split(","):
        t = raw.strip()
        low = t.lower()
        if not t or any(b in low for b in _BODY_HAIR):
            continue
        if any(w in low for w in _HAIR_TOP_WORDS):
            continue
        if "hair" in low or any(w in low for w in _HAIR_HANGING_WORDS):
            out.append(t)
    return out


def hair_length_ge(current: str, need: str) -> bool:
    if not need:
        return True
    cur_i = HAIR_LENGTH_ORDER.get((current or "").strip().lower())
    need_i = HAIR_LENGTH_ORDER.get((need or "").strip().lower())
    if need_i is None:
        return True
    return cur_i is not None and cur_i >= need_i


def _swap_hairstyle(base_positive: str, strip: set[str],
                    new_tags: list[str]) -> str:
    parts = [t.strip() for t in (base_positive or "").split(",") if t.strip()]
    out: list[str] = []
    insert_at: int | None = None
    for t in parts:
        if t.lower() in strip:
            if insert_at is None:
                insert_at = len(out)
            continue
        out.append(t)
    if insert_at is None:
        insert_at = len(out)
        first = next((i for i, t in enumerate(out)
                      if t.lower().endswith(" hair")), None)
        if first is not None:
            insert_at = first + 1
            while insert_at < len(out) and out[insert_at].lower().endswith(" hair"):
                insert_at += 1
    have = {t.lower() for t in out}
    out[insert_at:insert_at] = [t for t in new_tags if t and t.lower() not in have]
    return ", ".join(out)


def apply_outfit_hairstyle(base_positive: str, appearance: "BaseAppearance | None",
                           outfit: "Outfit | None", renderer_id: str) -> str:
    if outfit is None or appearance is None:
        return base_positive
    new_tags = [t for t in getattr(outfit, "hairstyle_tags", ()) if t]
    if not new_tags:
        return base_positive
    cur_len = derive_hair_length(appearance, renderer_id)
    if not hair_length_ge(cur_len, getattr(outfit, "hairstyle_min_length", "")):
        return base_positive
    strip = {t.strip().lower() for t in getattr(appearance, "hairstyle_tags", ())}
    return _swap_hairstyle(base_positive, strip, new_tags)


def outfit_hairstyle_active(appearance: "BaseAppearance | None",
                            outfit: "Outfit | None", renderer_id: str) -> bool:
    if outfit is None or appearance is None:
        return False
    if not [t for t in getattr(outfit, "hairstyle_tags", ()) if t]:
        return False
    cur_len = derive_hair_length(appearance, renderer_id)
    return hair_length_ge(cur_len, getattr(outfit, "hairstyle_min_length", ""))


def apply_self_styling(base_positive: str, appearance: "BaseAppearance | None",
                       outfit: "Outfit | None", renderer_id: str,
                       hairstyle_tags, extra_tags, *,
                       hair_down: bool = False) -> str:
    out = base_positive or ""
    hs = [t for t in (hairstyle_tags or ()) if t]
    if hs and appearance is not None:
        if not hair_down and not outfit_hairstyle_active(appearance, outfit,
                                                         renderer_id):
            strip = {t.strip().lower()
                     for t in getattr(appearance, "hairstyle_tags", ()) if t}
            out = _swap_hairstyle(out, strip, hs)
        else:
            from services.self_styling import route_tag
            keep = [t for t in hs if route_tag(t.lower()) != "hair_style"]
            if keep:
                out = _swap_hairstyle(out, set(), keep)
    extras = [t for t in (extra_tags or ()) if t]
    if extras:
        from services.self_styling import allowance_key, tag_color
        restyled = {allowance_key(t) for t in extras if tag_color(t)}
        if restyled:
            mine = {x.lower() for x in extras}
            parts = [t.strip() for t in out.split(",") if t.strip()]
            keep = [t for t in parts
                    if not (t.lower() not in mine and tag_color(t)
                            and allowance_key(t) in restyled)]
            if len(keep) != len(parts):
                out = ", ".join(keep)
        have = {t.strip().lower() for t in out.split(",") if t.strip()}
        add = [t for t in extras if t.lower() not in have]
        if add:
            out = ", ".join(p for p in [out, ", ".join(add)] if p)
    return out


HAIR_DOWN_TAG = "hair down"


def apply_hair_down(base_positive: str, appearance: "BaseAppearance | None",
                    outfit: "Outfit | None" = None) -> str:
    strip: set[str] = set()
    if appearance is not None:
        strip |= {t.strip().lower()
                  for t in getattr(appearance, "hairstyle_tags", ()) if t}
    if outfit is not None:
        strip |= {t.strip().lower()
                  for t in getattr(outfit, "hairstyle_tags", ()) if t}
    return _swap_hairstyle(base_positive, strip, [HAIR_DOWN_TAG])


@dataclass(frozen=True)
class Outfit:
    format_version: int
    id: str
    name: str
    rating: str
    required_tier: str
    tags: tuple[str, ...]
    character_restrictions: CharacterRestrictions
    compatibility: Compatibility
    renderer_prompts: dict[str, RendererPrompt]
    author: str = ""
    license: str = ""
    created_at: str = ""
    preview: str = ""
    source_path: Path | None = None
    hairstyle_tags: tuple[str, ...] = ()
    hairstyle_min_length: str = ""
    pairs: tuple[str, ...] = ()

    def supports_renderer(self, renderer_id: str) -> bool:
        return renderer_id in self.renderer_prompts


@dataclass(frozen=True)
class Scene:
    format_version: int
    id: str
    name: str
    category: str
    rating: str
    tags: tuple[str, ...]
    renderer_prompts: dict[str, RendererPrompt]
    preview: str = ""
    source_path: Path | None = None

    def supports_renderer(self, renderer_id: str) -> bool:
        return renderer_id in self.renderer_prompts


@dataclass(frozen=True)
class Pose:
    format_version: int
    id: str
    name: str
    category: str
    rating: str
    tags: tuple[str, ...]
    mood_hints: tuple[str, ...]
    renderer_prompts: dict[str, RendererPrompt]
    preview: str = ""
    source_path: Path | None = None

    def supports_renderer(self, renderer_id: str) -> bool:
        return renderer_id in self.renderer_prompts


@dataclass(frozen=True)
class ModifierOption:
    id: str
    name: str
    renderer_prompts: dict[str, str]

    def supports_renderer(self, renderer_id: str) -> bool:
        return renderer_id in self.renderer_prompts


@dataclass(frozen=True)
class ModifierCategory:
    format_version: int
    category: str
    description: str
    options: tuple[ModifierOption, ...]
    source_path: Path | None = None

    def get_option(self, option_id: str) -> ModifierOption | None:
        for o in self.options:
            if o.id == option_id:
                return o
        return None

    def options_for_renderer(self, renderer_id: str) -> list[ModifierOption]:
        return [o for o in self.options if o.supports_renderer(renderer_id)]
