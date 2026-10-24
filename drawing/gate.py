from __future__ import annotations

from dataclasses import dataclass, field

from drawing.assets import rating_le, tier_ge
from drawing.catalog import AssetCatalog
from drawing.choice import Choice


@dataclass
class GateResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)

    def to_retry_message(self) -> str:
        lines: list[str] = []
        if self.errors:
            lines.append("Ошибки выбора (выбери другие ассеты):")
            for e in self.errors:
                lines.append(f"  - {e}")
        if self.warnings:
            if lines:
                lines.append("")
            lines.append("Mismatch'и (можно оставить, если контекст оправдывает):")
            for w in self.warnings:
                lines.append(f"  - {w}")
        return "\n".join(lines)


def validate_choice(
    choice: Choice,
    *,
    catalog: AssetCatalog,
    renderer_id: str,
    max_rating: str,
    current_tier: str,
    character_id: str,
    character_archetypes: list[str],
) -> GateResult:
    if choice.is_refusal():
        return GateResult(valid=True)

    errors: list[str] = []
    warnings: list[str] = []

    outfit = catalog.outfits.get(choice.outfit_id)
    if outfit is None:
        errors.append(
            f"outfit_id {choice.outfit_id!r} не найден в каталоге "
            f"(доступные: {sorted(catalog.outfits.keys())})"
        )
    else:
        if not outfit.supports_renderer(renderer_id):
            errors.append(
                f"outfit {outfit.id!r} не поддерживает renderer {renderer_id!r}"
            )
        if not rating_le(outfit.rating, max_rating):
            errors.append(
                f"outfit {outfit.id!r} rating={outfit.rating!r} превышает "
                f"max_rating={max_rating!r}"
            )
        if not tier_ge(current_tier, outfit.required_tier):
            errors.append(
                f"outfit {outfit.id!r} требует tier ≥ {outfit.required_tier!r}, "
                f"текущий {current_tier!r}"
            )
        if not outfit.character_restrictions.allows_character(
            character_id, character_archetypes
        ):
            errors.append(
                f"outfit {outfit.id!r} недоступен персонажу {character_id!r} "
                f"(restrictions: block_list={list(outfit.character_restrictions.block_list)}, "
                f"required_archetypes={list(outfit.character_restrictions.required_archetypes)})"
            )

    scene = catalog.scenes.get(choice.scene_id)
    if scene is None:
        errors.append(
            f"scene_id {choice.scene_id!r} не найден в каталоге "
            f"(доступные: {sorted(catalog.scenes.keys())})"
        )
    else:
        if not scene.supports_renderer(renderer_id):
            errors.append(
                f"scene {scene.id!r} не поддерживает renderer {renderer_id!r}"
            )
        if not rating_le(scene.rating, max_rating):
            errors.append(
                f"scene {scene.id!r} rating={scene.rating!r} превышает "
                f"max_rating={max_rating!r}"
            )

    pose = catalog.poses.get(choice.pose_id)
    if pose is None:
        errors.append(
            f"pose_id {choice.pose_id!r} не найден в каталоге "
            f"(доступные: {sorted(catalog.poses.keys())})"
        )
    else:
        if not pose.supports_renderer(renderer_id):
            errors.append(
                f"pose {pose.id!r} не поддерживает renderer {renderer_id!r}"
            )
        if not rating_le(pose.rating, max_rating):
            errors.append(
                f"pose {pose.id!r} rating={pose.rating!r} превышает "
                f"max_rating={max_rating!r}"
            )

    for category, option_id in choice.modifiers.items():
        cat = catalog.modifiers.get(category)
        if cat is None:
            errors.append(
                f"modifier category {category!r} не существует "
                f"(доступные: {sorted(catalog.modifiers.keys())})"
            )
            continue
        opt = cat.get_option(option_id)
        if opt is None:
            errors.append(
                f"modifier {category!r} не имеет опции {option_id!r} "
                f"(доступные: {[o.id for o in cat.options]})"
            )
            continue
        if not opt.supports_renderer(renderer_id):
            errors.append(
                f"modifier {category!r}/{option_id!r} не поддерживает "
                f"renderer {renderer_id!r}"
            )

    if outfit is not None and scene is not None:
        blocks = set(outfit.compatibility.blocks)
        is_blocked = scene.id in blocks or scene.category in blocks

        if is_blocked:
            warnings.append(
                f"outfit {outfit.id!r} помечает scene {scene.id!r} "
                f"(category={scene.category!r}) как блокированную "
                f"({sorted(blocks)}) — композиция плохая"
            )
        else:
            allowed = set(outfit.compatibility.scenes)
            if allowed and scene.id not in allowed and scene.category not in allowed:
                warnings.append(
                    f"outfit {outfit.id!r} не указывает scene {scene.id!r} "
                    f"(category={scene.category!r}) в compatibility.scenes "
                    f"({sorted(allowed)}) — композиция нестандартная"
                )

    from drawing.zones import component_fits, component_min_level, framing_level
    level = framing_level(choice.modifiers.get("framing"))
    if level is not None:
        def _coherence(label: str, frag: str | None) -> None:
            if frag and not component_fits(frag, level):
                warnings.append(
                    f"{label} требует кадр ≥ {component_min_level(frag)!r}, "
                    f"выбран framing-уровень {level!r} — теги вне кадра будут "
                    f"отброшены (композиция беднее)"
                )

        if pose is not None and renderer_id in pose.renderer_prompts:
            _coherence(f"поза {pose.id!r}",
                       pose.renderer_prompts[renderer_id].positive)
        for cat_id in ("gesture", "prop"):
            oid = choice.modifiers.get(cat_id)
            cat = catalog.modifiers.get(cat_id) if oid else None
            opt = cat.get_option(oid) if cat else None
            if opt is not None:
                _coherence(f"{cat_id} {oid!r}", opt.renderer_prompts.get(renderer_id))

    return GateResult(
        valid=not errors,
        errors=errors,
        warnings=warnings,
    )
