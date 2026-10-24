from __future__ import annotations

import re

from drawing.assets import BaseAppearance
from drawing.catalog import AssetCatalog
from drawing.choice import Choice
from drawing.gate import GateResult
from drawing.pipeline import PipelineRequest, PipelineResult


PORTRAIT_PREFERRED_SCENES = ("studio_grey", "library", "living_room", "garden", "kitchen")
PORTRAIT_PREFERRED_POSES = ("hands_behind", "smile_wave", "relaxed")
PORTRAIT_PREFERRED_OUTFITS = ("maid_classic", "sundress", "yukata_summer")
PORTRAIT_MODIFIERS = {
    "expression": "gentle_smile",
    "framing": "medium",
}


def appearance_with_mood_extras(base: BaseAppearance, renderer_id: str,
                                mood_state: str | None) -> BaseAppearance:
    if not mood_state:
        return base
    import unicodedata
    key = unicodedata.normalize("NFC", str(mood_state)).strip()
    extra = (getattr(base, "mood_expressions", None) or {}).get(key, "")
    if not extra:
        return base
    prompt = base.positive_for(renderer_id)
    have = {t.strip() for t in prompt.split(",") if t.strip()}
    add = [t.strip() for t in extra.split(",") if t.strip() and t.strip() not in have]
    if not add:
        return base
    from dataclasses import replace
    prompts = dict(base.renderer_prompts)
    prompts[renderer_id] = (prompt + ", " if prompt else "") + ", ".join(add)
    return replace(base, renderer_prompts=prompts)


def mood_expression_override(base: BaseAppearance, mood_state: str | None,
                             default_expr: str | None) -> str | None:
    if mood_state:
        import unicodedata
        key = unicodedata.normalize("NFC", str(mood_state)).strip()
        if (getattr(base, "mood_expressions", None) or {}).get(key, ""):
            return ""
    return default_expr


HANDS_FREE_POSE = "hands_free"
_HAND_RX = re.compile(
    r"\b(hands?|fingers?|fists?|arms?|palms?|waving|wave|salute|clasped|"
    r"peace sign|thumbs? up|pointing|covering|holding|v sign)\b")


def expression_uses_hands(tags: str | None) -> bool:
    return bool(tags) and bool(_HAND_RX.search(str(tags).lower()))


def pose_for_expression(base: BaseAppearance, mood_state: str | None,
                        default_expr: str | None, catalog: AssetCatalog,
                        renderer_id: str) -> str | None:
    tags = ""
    if mood_state:
        import unicodedata
        key = unicodedata.normalize("NFC", str(mood_state)).strip()
        tags = (getattr(base, "mood_expressions", None) or {}).get(key, "") or ""
    if not tags and default_expr:
        cat = catalog.modifiers.get("expression")
        opt = cat.get_option(default_expr) if cat is not None else None
        if opt is not None and opt.supports_renderer(renderer_id):
            tags = opt.renderer_prompts[renderer_id]
    return HANDS_FREE_POSE if expression_uses_hands(tags) else None


class PortraitBuildError(Exception):
    pass


def _first_available(catalog: AssetCatalog, attr: str, preferred: tuple[str, ...],
                     renderer_id: str, character_id: str = "",
                     character_archetypes: list | None = None,
                     max_rating: str = "sfw",
                     current_tier: str = "distant",
                     character_tag_gates: dict[str, str] | None = None,
                     character_blocked_tags: list[str] | None = None) -> str | None:
    if attr == "outfits":
        items = catalog.compatible_outfits(
            renderer_id=renderer_id,
            max_rating=max_rating,
            current_tier=current_tier,
            character_id=character_id,
            character_archetypes=character_archetypes or [],
            character_tag_gates=character_tag_gates,
            character_blocked_tags=character_blocked_tags,
        )
    elif attr == "scenes":
        items = catalog.compatible_scenes(renderer_id=renderer_id, max_rating=max_rating)
    elif attr == "poses":
        items = catalog.compatible_poses(renderer_id=renderer_id, max_rating=max_rating)
    else:
        return None

    available_ids = {i.id for i in items}
    for preferred_id in preferred:
        if preferred_id in available_ids:
            return preferred_id
    return items[0].id if items else None


def build_portrait_request_and_choice(
    *,
    character_id: str,
    character_name: str,
    character_archetypes: list[str],
    base_appearance: BaseAppearance | None,
    catalog: AssetCatalog,
    renderer_id: str = "sdxl",
    max_rating: str = "sfw",
    current_tier: str = "distant",
    style_tags: list[str] | None = None,
    safety_positive: list[str] | None = None,
    safety_negative: list[str] | None = None,
    quality_tags: list[str] | None = None,
    override_outfit_id: str | None = None,
    character_default_outfit_id: str | None = None,
    character_tag_gates: dict[str, str] | None = None,
    character_blocked_tags: list[str] | None = None,
    critic_max_retries: int = 0,
    critic_soft_threshold: float = 0.7,
    expression_override: str | None = None,
    seed: int | None = None,
    styling_hairstyle: tuple = (),
    styling_extra: tuple = (),
    pose_override: str | None = None,
) -> tuple[PipelineResult, PipelineRequest]:
    outfit_id: str | None = None
    if override_outfit_id:
        compatible = catalog.compatible_outfits(
            renderer_id=renderer_id,
            max_rating=max_rating,
            current_tier=current_tier,
            character_id=character_id,
            character_archetypes=character_archetypes,
            character_tag_gates=character_tag_gates,
            character_blocked_tags=character_blocked_tags,
        )
        if any(o.id == override_outfit_id for o in compatible):
            outfit_id = override_outfit_id

    if outfit_id is None:
        preferred = PORTRAIT_PREFERRED_OUTFITS
        if character_default_outfit_id:
            preferred = (character_default_outfit_id,) + tuple(
                o for o in PORTRAIT_PREFERRED_OUTFITS
                if o != character_default_outfit_id
            )
        outfit_id = _first_available(
            catalog, "outfits", preferred,
            renderer_id=renderer_id, character_id=character_id,
            character_archetypes=character_archetypes,
            max_rating=max_rating, current_tier=current_tier,
            character_tag_gates=character_tag_gates,
            character_blocked_tags=character_blocked_tags,
        )
    scene_id = _first_available(
        catalog, "scenes", PORTRAIT_PREFERRED_SCENES,
        renderer_id=renderer_id, max_rating=max_rating,
    )
    pose_id = _first_available(
        catalog, "poses",
        ((pose_override,) if pose_override else ()) + PORTRAIT_PREFERRED_POSES,
        renderer_id=renderer_id, max_rating=max_rating,
    )

    if not (outfit_id and scene_id and pose_id):
        raise PortraitBuildError(
            f"catalog недостаточно для portrait: "
            f"outfit={outfit_id!r}, scene={scene_id!r}, pose={pose_id!r}"
        )

    portrait_modifiers = dict(PORTRAIT_MODIFIERS)
    if expression_override:
        portrait_modifiers["expression"] = expression_override
    elif expression_override == "":
        portrait_modifiers.pop("expression", None)
    modifiers: dict[str, str] = {}
    for category, option_id in portrait_modifiers.items():
        cat = catalog.modifiers.get(category)
        if cat is None:
            continue
        opt = cat.get_option(option_id)
        if opt is not None and opt.supports_renderer(renderer_id):
            modifiers[category] = option_id

    choice = Choice(
        outfit_id=outfit_id,
        scene_id=scene_id,
        pose_id=pose_id,
        modifiers=modifiers,
        aspect="tall",
        requested_unavailable=False,
        refusal_reason=None,
    )

    request = PipelineRequest(
        character_id=character_id,
        character_name=character_name,
        character_archetypes=character_archetypes,
        base_appearance=base_appearance,
        user_intent="portrait regeneration",
        max_rating=max_rating,
        current_tier=current_tier,
        safety_positive=safety_positive,
        safety_negative=safety_negative,
        style_tags=style_tags,
        quality_tags=quality_tags,
        character_tag_gates=character_tag_gates,
        character_blocked_tags=character_blocked_tags,
        critic_max_retries=critic_max_retries,
        critic_soft_threshold=critic_soft_threshold,
        styling_hairstyle=tuple(styling_hairstyle or ()),
        styling_extra=tuple(styling_extra or ()),
        seed=seed,
        filename_prefix=f"{character_id}/{character_id}_portrait",
    )

    choose_result = PipelineResult(
        choice=choice,
        gate=GateResult(valid=True),
    )

    return choose_result, request
