from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from drawing.assets import BaseAppearance
from drawing.catalog import AssetCatalog
from drawing.choice import Choice
from drawing.critic import VisionCritic, Verdict, request_apology
from drawing.gate import GateResult
from drawing.llm_choice import DEFAULT_MAX_RETRIES, request_choice
from drawing.renderer import (
    ASPECT_TALL, DEFAULT_ASPECT, AssembledPrompt, EmptyPromptError,
    RendererAdapter, RenderResult, aspect_to_dimensions,
)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from persona.character_context import CharacterContext


DEFAULT_CRITIC_MAX_RETRIES = 2
DEFAULT_CRITIC_SOFT_THRESHOLD = 0.7


def _fmt_asset_for_critic(item) -> str:
    tags = ", ".join(getattr(item, "tags", None) or [])
    return f"{item.name} (выглядит как: {tags})" if tags else item.name


def _choice_summary_for_critic(choice: Choice, catalog: AssetCatalog) -> dict[str, str]:
    out: dict[str, str] = {}
    o = catalog.outfits.get(choice.outfit_id)
    if o:
        out["outfit"] = _fmt_asset_for_critic(o)
    s = catalog.scenes.get(choice.scene_id)
    if s:
        out["scene"] = _fmt_asset_for_critic(s)
    p = catalog.poses.get(choice.pose_id)
    if p:
        out["pose"] = _fmt_asset_for_critic(p)
    return out


@dataclass(frozen=True)
class PipelineRequest:
    character_id: str
    character_name: str
    character_archetypes: list[str]
    base_appearance: BaseAppearance | None
    user_intent: str
    max_rating: str
    current_tier: str
    refusal_style_hint: str | None = None
    character_tag_gates: dict[str, str] | None = None
    character_blocked_tags: list[str] | None = None
    current_portrait_outfit_id: str | None = None
    styling_hairstyle: tuple = ()
    styling_extra: tuple = ()
    styling_underwear: tuple = ()
    styling_intimate: tuple = ()
    underwear_layer: bool = True
    safety_positive: list[str] | None = None
    safety_negative: list[str] | None = None
    seed: int | None = None
    max_retries: int = DEFAULT_MAX_RETRIES
    critic_max_retries: int = 0
    critic_soft_threshold: float = DEFAULT_CRITIC_SOFT_THRESHOLD
    filename_prefix: str = ""
    style_tags: list[str] | None = None
    quality_tags: list[str] | None = None
    style_exclude: list[str] | None = None
    persona_hint: str | None = None
    framing_hint: str | None = None
    mood_hint: str | None = None
    reference_tags: list[str] | None = None
    anatomy: object | None = None
    snapshot_carry: dict | None = None
    recent_frames: tuple = ()
    allow_contact: bool = False

    @classmethod
    def from_persona(
        cls,
        persona: "CharacterContext",
        *,
        base_appearance: BaseAppearance | None,
        user_intent: str,
        max_rating: str,
        refusal_style_hint: str | None = None,
        current_portrait_outfit_id: str | None = None,
        safety_positive: list[str] | None = None,
        safety_negative: list[str] | None = None,
        seed: int | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        critic_max_retries: int = 0,
        critic_soft_threshold: float = DEFAULT_CRITIC_SOFT_THRESHOLD,
        filename_prefix: str = "",
        style_tags: list[str] | None = None,
        quality_tags: list[str] | None = None,
        style_exclude: list[str] | None = None,
        persona_hint: str | None = None,
        framing_hint: str | None = None,
        mood_hint: str | None = None,
        reference_tags: list[str] | None = None,
        styling_hairstyle: tuple = (),
        styling_extra: tuple = (),
        styling_underwear: tuple = (),
        styling_intimate: tuple = (),
        underwear_layer: bool = True,
        anatomy: object | None = None,
        snapshot_carry: dict | None = None,
        recent_frames: tuple = (),
        allow_contact: bool = False,
    ) -> "PipelineRequest":
        policy = persona.outfit_policy
        return cls(
            character_id=persona.character_id,
            character_name=persona.character.name,
            character_archetypes=list(persona.archetypes),
            base_appearance=base_appearance,
            user_intent=user_intent,
            max_rating=max_rating,
            current_tier=persona.tier,
            refusal_style_hint=refusal_style_hint,
            character_tag_gates=dict(policy.tag_tier_gates) if policy else None,
            character_blocked_tags=list(policy.blocked_tags) if policy else None,
            current_portrait_outfit_id=current_portrait_outfit_id,
            safety_positive=safety_positive,
            safety_negative=safety_negative,
            seed=seed,
            max_retries=max_retries,
            critic_max_retries=critic_max_retries,
            critic_soft_threshold=critic_soft_threshold,
            filename_prefix=filename_prefix,
            style_tags=style_tags,
            quality_tags=quality_tags,
            style_exclude=style_exclude,
            persona_hint=persona_hint,
            framing_hint=framing_hint,
            mood_hint=mood_hint,
            reference_tags=reference_tags,
            styling_hairstyle=tuple(styling_hairstyle or ()),
            styling_extra=tuple(styling_extra or ()),
            styling_underwear=tuple(styling_underwear or ()),
            styling_intimate=tuple(styling_intimate or ()),
            underwear_layer=bool(underwear_layer),
            anatomy=anatomy,
            snapshot_carry=snapshot_carry,
            recent_frames=tuple(tuple(f) for f in recent_frames or ()),
            allow_contact=bool(allow_contact),
        )


def _safety_negative(request: "PipelineRequest", tags=(), outfit: str = "") -> list[str] | None:
    neg = list(request.safety_negative or [])
    if request.max_rating != "sfw" and not request.allow_contact:
        from drawing.ladder import level_of, partner_negative
        if level_of(tags) >= 3:
            neg += [t for t in partner_negative(_subject_male(request)) if t not in neg]
    if request.max_rating == "sfw":
        neg += [t for t in SFW_EXPOSURE_NEGATIVE if t not in neg]
        if "back focus" in {str(t).strip().lower() for t in tags or ()} \
                and not re.search(r"backless|back cutout|bare back", (outfit or "").lower()):
            neg += [t for t in SFW_BACK_NEGATIVE if t not in neg]
    return neg or None


def _subject_male(request: "PipelineRequest") -> bool:
    ba = request.base_appearance
    if ba is None:
        return False
    try:
        pos = " ".join(str(v) for v in (ba.renderer_prompts or {}).values())
    except Exception:
        pos = ""
    return "1boy" in {t.strip().lower() for t in pos.split(",")}


SFW_EXPOSURE_NEGATIVE = ("pantyshot", "upskirt", "panties", "underwear",
                         "nude", "completely nude", "nipples", "topless female")
SFW_BACK_NEGATIVE = ("bare back", "backless outfit", "back cutout")
POSE_OPPOSITE_NEGATIVE: dict[str, tuple[str, ...]] = {
    "on stomach": ("on back",), "on back": ("on stomach",),
}


@dataclass(frozen=True)
class PipelineResult:
    choice: Choice
    gate: GateResult
    image_path: Path | None = None
    assembled_prompt: AssembledPrompt | None = None
    render_result: RenderResult | None = None
    refusal_reason: str | None = None
    error: str | None = None
    critic_verdicts: list[Verdict] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return self.image_path is not None and not self.error

    @property
    def is_refusal(self) -> bool:
        return self.refusal_reason is not None and not self.is_success

    @property
    def is_error(self) -> bool:
        return self.error is not None and not self.is_success


def explicit_additions(request, tags, remove, open_regions) -> list[str]:
    from drawing import exposure as _ex
    from services.nsfw_anatomy import positive_tags as _anat_pos
    remove = list(remove or ())
    tag_set = {t.strip().lower() for t in tags}
    bare = set() if _ex.rear_view(tags) else _ex.bare_zones(tags, remove)
    add: list[str] = list(_anat_pos(request.anatomy, bare=bare))
    if not tag_set & {"nude", "completely nude"} and request.underwear_layer:
        from services.self_styling import (UNDERWEAR_BASE_TAG, underwear_item_zone,
                                           underwear_zone_of)
        zones_ = _ex.underwear_zones(tags, remove)
        own = {underwear_item_zone(t) for t in tags} - {None}
        items: list[str] = []
        if zones_:
            both = zones_ == {"top", "bottom"}
            slot = [t for t in request.styling_underwear
                    if (both or underwear_zone_of(t) in zones_)
                    and underwear_zone_of(t) not in own]
            items.extend(slot)
            covered = own | {underwear_zone_of(t) for t in slot}
            for zone, default in (("top", "bra"), ("bottom", "panties")):
                if zone in zones_ and not covered & {zone, "set"}:
                    items.append(default)
        if items or own:
            add.append(UNDERWEAR_BASE_TAG)
            add.extend(items)
    add.extend(request.styling_intimate)
    kept, _ = _ex.drop_hidden_marks(", ".join(t for t in add if t), open_regions)
    return [t.strip() for t in kept.split(",") if t.strip()]


class DrawingPipeline:
    def __init__(
        self,
        *,
        catalog: AssetCatalog,
        adapter: RendererAdapter,
        vision_critic: VisionCritic | None = None,
        ensure_backend: callable = None,
    ):
        self.catalog = catalog
        self.adapter = adapter
        self.vision_critic = vision_critic
        self.ensure_backend = ensure_backend

    def choose(
        self,
        request: PipelineRequest,
        *,
        llm_client,
    ) -> PipelineResult:
        choice, gate = request_choice(
            llm_client=llm_client,
            character_name=request.character_name,
            user_intent=request.user_intent,
            catalog=self.catalog,
            renderer_id=self.adapter.renderer_id,
            max_rating=request.max_rating,
            current_tier=request.current_tier,
            character_id=request.character_id,
            character_archetypes=request.character_archetypes,
            refusal_style_hint=request.refusal_style_hint,
            max_retries=request.max_retries,
            character_tag_gates=request.character_tag_gates,
            character_blocked_tags=request.character_blocked_tags,
            current_portrait_outfit_id=request.current_portrait_outfit_id,
        )

        if choice.is_refusal():
            return PipelineResult(
                choice=choice,
                gate=gate,
                refusal_reason=choice.refusal_reason or "(refusal без reason)",
            )

        return PipelineResult(choice=choice, gate=gate)

    def render_choice(
        self,
        choose_result: PipelineResult,
        request: PipelineRequest,
        *,
        before_render: callable = None,
        after_render: callable = None,
    ) -> PipelineResult:
        if choose_result.is_refusal or choose_result.is_error:
            return choose_result

        choice = choose_result.choice
        gate = choose_result.gate

        base_app = request.base_appearance
        if base_app is not None and (request.styling_hairstyle
                                     or request.styling_extra):
            import dataclasses
            from drawing.assets import apply_self_styling
            rid = self.adapter.renderer_id
            outfit = self.catalog.outfits.get(choice.outfit_id)
            styled = apply_self_styling(
                base_app.positive_for(rid), base_app, outfit, rid,
                request.styling_hairstyle, request.styling_extra)
            if styled != base_app.positive_for(rid):
                base_app = dataclasses.replace(
                    base_app,
                    renderer_prompts={**base_app.renderer_prompts,
                                      rid: styled})
        try:
            assembled = self.adapter.assemble_prompt(
                choice,
                base_appearance=base_app,
                catalog=self.catalog,
                safety_positive=request.safety_positive,
                safety_negative=_safety_negative(request),
                style_tags=request.style_tags,
                quality_tags=request.quality_tags,
                seed=request.seed,
                filename_prefix=request.filename_prefix,
            )
        except EmptyPromptError as e:
            return PipelineResult(
                choice=choice,
                gate=gate,
                error=f"assemble failed: {e}",
            )

        return self._render_loop(
            assembled, request, choice, gate,
            before_render=before_render, after_render=after_render,
        )

    def _render_loop(
        self,
        assembled: AssembledPrompt,
        request: PipelineRequest,
        choice: Choice,
        gate: GateResult,
        *,
        before_render: callable = None,
        after_render: callable = None,
    ) -> PipelineResult:
        critic_active = (
            self.vision_critic is not None
            and request.critic_max_retries > 0
        )
        max_attempts = (request.critic_max_retries + 1) if critic_active else 1
        verdicts: list[Verdict] = []
        last_render: RenderResult | None = None
        last_assembled = assembled

        for attempt in range(max_attempts):
            if attempt > 0:
                import random
                new_seed = random.randint(0, 2**63 - 1)
                last_assembled = AssembledPrompt(
                    positive=assembled.positive,
                    negative=assembled.negative,
                    seed=new_seed,
                    width=assembled.width,
                    height=assembled.height,
                    filename_prefix=assembled.filename_prefix,
                    extra=assembled.extra,
                )

            if before_render is not None:
                before_render()
            try:
                if self.ensure_backend is not None:
                    self.ensure_backend()
                last_render = self.adapter.render(last_assembled)
            except Exception as e:
                if after_render is not None:
                    try:
                        after_render()
                    except Exception:
                        pass
                return PipelineResult(
                    choice=choice,
                    gate=gate,
                    assembled_prompt=last_assembled,
                    error=f"render failed (attempt {attempt + 1}): {type(e).__name__}: {e}",
                    critic_verdicts=verdicts,
                )
            if after_render is not None:
                after_render()

            if not critic_active:
                break

            choice_summary = _choice_summary_for_critic(choice, self.catalog)
            verdict = self.vision_critic.judge(
                last_render.image_path,
                expected_outfit=choice_summary.get("outfit", ""),
                expected_scene=choice_summary.get("scene", ""),
                expected_pose=choice_summary.get("pose", ""),
                max_rating=request.max_rating,
            )
            verdicts.append(verdict)

            if not verdict.should_regen(request.critic_soft_threshold):
                break

        return PipelineResult(
            choice=choice,
            gate=gate,
            assembled_prompt=last_assembled,
            render_result=last_render,
            image_path=last_render.image_path if last_render else None,
            critic_verdicts=verdicts,
        )

    def select_freeform(self, request: PipelineRequest, *, llm_chat,
                        compose: bool = False) -> dict:
        if compose:
            from drawing.tag_rounds import compose_tags
            from drawing.color_template import apply as _apply_colors
            rid = self.adapter.renderer_id
            outfit_id = request.current_portrait_outfit_id or ""
            colors = (request.base_appearance.favorite_colors
                      if request.base_appearance is not None else ())
            from drawing.assets import (apply_hair_down, apply_outfit_hairstyle,
                                        apply_self_styling)
            from drawing.tag_rounds import detect_hair_down
            outfit = self.catalog.outfits.get(outfit_id) if outfit_id else None
            _hair_down = detect_hair_down(request.user_intent)
            appearance_tags: list[str] = []
            if request.base_appearance is not None:
                bp = apply_outfit_hairstyle(
                    request.base_appearance.positive_for(rid) or "",
                    request.base_appearance, outfit, rid)
                if _hair_down:
                    bp = apply_hair_down(bp, request.base_appearance, outfit)
                bp = apply_self_styling(
                    bp, request.base_appearance, outfit, rid,
                    request.styling_hairstyle, request.styling_extra,
                    hair_down=_hair_down)
                appearance_tags = [t.strip() for t in bp.split(",") if t.strip()]
                appearance_tags += [t for t in request.base_appearance.hard_tags if t]
            outfit_tags: list[str] = []
            if outfit is not None and rid in outfit.renderer_prompts:
                pos = _apply_colors(outfit.renderer_prompts[rid].positive or "", colors)
                outfit_tags = [t.strip() for t in pos.split(",") if t.strip()]
            from drawing.tag_resolver import get_resolver
            sel = compose_tags(
                request.user_intent, llm_chat,
                max_rating=request.max_rating,
                appearance_tags=appearance_tags, outfit_tags=outfit_tags,
                persona_hint=request.persona_hint,
                mood_hint=request.mood_hint,
                framing_override=request.framing_hint,
                exclude_domains=request.style_exclude,
                reference_tags=request.reference_tags,
                resolver=get_resolver(),
                underlayer_tags=(tuple(request.styling_underwear)
                                 + tuple(request.styling_intimate)),
                carry=(request.snapshot_carry if request.max_rating != "sfw" else None),
                recent_frames=request.recent_frames,
                allow_contact=request.allow_contact,
            )
        else:
            from drawing.tag_rounds import select_tags
            sel = select_tags(
                request.user_intent, llm_chat,
                max_rating=request.max_rating,
                exclude_domains=request.style_exclude,
                persona_hint=request.persona_hint,
                framing_override=request.framing_hint,
                mood_hint=request.mood_hint,
                reference_tags=request.reference_tags,
            )
        sel["outfit_id"] = request.current_portrait_outfit_id or ""
        from drawing.tag_rounds import detect_hair_down
        sel["hair_down"] = detect_hair_down(request.user_intent)
        return sel

    def render_freeform(
        self,
        selection: dict,
        request: PipelineRequest,
        *,
        before_render: callable = None,
        after_render: callable = None,
    ) -> PipelineResult:
        outfit_id = (selection.get("outfit_id")
                     or request.current_portrait_outfit_id or "")
        framing_tag = selection.get("framing")
        framing_level = selection.get("framing_level")
        tags = list(selection.get("tags") or [])

        rid = self.adapter.renderer_id

        from drawing.color_template import apply as _apply_colors
        colors = (request.base_appearance.favorite_colors
                  if request.base_appearance is not None else ())
        outfit_positive = outfit_negative = ""
        outfit = self.catalog.outfits.get(outfit_id) if outfit_id else None
        if outfit is not None and rid in outfit.renderer_prompts:
            rp = outfit.renderer_prompts[rid]
            outfit_positive = _apply_colors(rp.positive or "", colors)
            outfit_negative = _apply_colors(rp.negative or "", colors)

        _back_swapped = False
        if (request.max_rating == "sfw" and "back focus" in tags
                and not re.search(r"backless|back cutout|bare back", outfit_positive.lower())):
            tags = [t for t in tags if t != "back focus"]
            if "from behind" not in tags:
                tags.append("from behind")
            _back_swapped = True

        _remove = selection.get("remove") or []
        if _remove and outfit_positive:
            from drawing import zones as _z
            _rem = {_z._norm(r) for r in _remove}
            outfit_positive = ", ".join(
                t for t in outfit_positive.split(",") if _z._norm(t) not in _rem)

        from drawing.tag_rounds import OUTFIT_REPLACING
        outfit_dropped = bool(set(tags) & OUTFIT_REPLACING)
        if outfit_dropped:
            outfit_positive = outfit_negative = ""

        from drawing import exposure as _ex
        _open = _ex.frame_open(outfit_positive, tags, selection.get("remove") or (),
                               outfit_gone=outfit_dropped)

        base_positive = ""
        _anatomy_explicit = False
        if request.base_appearance is not None:
            from drawing.assets import (apply_hair_down, apply_outfit_hairstyle,
                                        apply_self_styling)
            _eff_outfit = None if outfit_dropped else outfit
            bp = apply_outfit_hairstyle(
                request.base_appearance.positive_for(rid) or "",
                request.base_appearance, _eff_outfit, rid)
            if selection.get("hair_down"):
                bp = apply_hair_down(bp, request.base_appearance, _eff_outfit)
            bp = apply_self_styling(
                bp, request.base_appearance, _eff_outfit, rid,
                request.styling_hairstyle, request.styling_extra,
                hair_down=bool(selection.get("hair_down")))
            if request.max_rating != "sfw":
                from drawing.tag_rounds import is_explicit_selection
                if is_explicit_selection(tags, selection.get("remove") or ()):
                    _anatomy_explicit = True
                    _tag_set = {t.strip().lower() for t in tags}
                    add = explicit_additions(
                        request, tags, selection.get("remove") or (), _open)
                    have = {t.strip().lower() for t in bp.split(",") if t.strip()}
                    add = [t for t in add
                           if t and t.lower() not in have
                           and t.lower() not in _tag_set]
                    if add:
                        bp = ", ".join(p for p in [bp, ", ".join(add)] if p)
            hard = [t for t in request.base_appearance.hard_tags if t]
            base_positive = ", ".join(p for p in ([bp] + hard) if p)
            base_positive, _hidden = _ex.drop_hidden_marks(base_positive, _open)
            if _hidden:
                print(f"[exposure] под одеждой не видно: {_hidden}")

        base_negative_tags: list[str] = []
        if request.base_appearance is not None:
            base_negative_tags += [
                t for t in getattr(request.base_appearance, "negative_tags", ()) or () if t]
        if _anatomy_explicit:
            from services.nsfw_anatomy import negative_tags as _anat_neg
            base_negative_tags += _anat_neg(request.anatomy)
        for _pose, _opposite in POSE_OPPOSITE_NEGATIVE.items():
            if _pose in tags:
                base_negative_tags += [t for t in _opposite if t not in tags]

        if selection.get("headless"):
            from drawing import zones as _zh
            _floor = selection.get("headless_floor")
            _keep = ("skin", "nail", "1girl", "1boy", "solo") + (
                ("breasts",) if "breast focus" in tags else ())
            if request.base_appearance is not None:
                from drawing import assets as _as
                _keep += tuple(_as.hair_in_frame(
                    base_positive, _as.derive_hair_length(request.base_appearance, rid),
                    _floor))
            base_positive = _zh.crop_band(base_positive, framing_level, _floor, keep=_keep)
            if _floor == "full":
                outfit_positive = _zh.crop_band(outfit_positive, framing_level, _floor)

        if "simple background" in tags:
            from drawing.backgrounds import choose_background
            _fav = (request.base_appearance.favorite_colors
                    if request.base_appearance is not None else ())
            _bg = choose_background(tags, _fav, seed=request.seed)
            if _bg:
                _i = tags.index("simple background") + 1
                tags = tags[:_i] + _bg + tags[_i:]

        aspect = (ASPECT_TALL if framing_level in ("cowboy", "full")
                  else DEFAULT_ASPECT)
        width, height = aspect_to_dimensions(aspect)

        synthetic = Choice(
            outfit_id=outfit_id,
            modifiers={"framing": framing_tag} if framing_tag else {},
            aspect=aspect,
        )
        gate = GateResult(valid=True)

        try:
            assembled = self.adapter.assemble_freeform(
                base_positive=base_positive,
                base_negative=", ".join(base_negative_tags),
                outfit_positive=outfit_positive,
                outfit_negative=outfit_negative,
                tags=tags,
                framing_level=framing_level,
                style_tags=request.style_tags,
                quality_tags=request.quality_tags,
                safety_positive=request.safety_positive,
                safety_negative=_safety_negative(
                    request, list(tags) + (["back focus"] if _back_swapped else []),
                    outfit_positive),
                seed=request.seed,
                width=width,
                height=height,
                filename_prefix=request.filename_prefix,
            )
        except EmptyPromptError as e:
            return PipelineResult(
                choice=synthetic, gate=gate, error=f"assemble failed: {e}",
            )

        return self._render_loop(
            assembled, request, synthetic, gate,
            before_render=before_render, after_render=after_render,
        )

    def run(
        self,
        request: PipelineRequest,
        *,
        llm_client,
    ) -> PipelineResult:
        choose_result = self.choose(request, llm_client=llm_client)
        return self.render_choice(choose_result, request)
