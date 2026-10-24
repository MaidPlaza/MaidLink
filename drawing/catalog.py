from __future__ import annotations

from pathlib import Path

import yaml

from drawing.assets import (
    Outfit, Scene, Pose, ModifierCategory, ModifierOption,
    CharacterRestrictions, Compatibility, RendererPrompt,
    RATING_ORDER, TIER_ORDER, rating_le, tier_ge,
)


class AssetValidationError(Exception):
    pass


VALID_RATINGS = set(RATING_ORDER.keys())
VALID_TIERS = set(TIER_ORDER.keys())


class AssetCatalog:
    def __init__(
        self,
        *,
        outfits: dict[str, Outfit],
        scenes: dict[str, Scene],
        poses: dict[str, Pose],
        modifiers: dict[str, ModifierCategory],
        errors: list[str],
    ):
        self.outfits = outfits
        self.scenes = scenes
        self.poses = poses
        self.modifiers = modifiers
        self.errors = errors
        self.own_outfit_ids: set[str] = set()

    @classmethod
    def load(cls, project_root: Path | str,
             *, assets_root: Path | str | None = None) -> "AssetCatalog":
        root = Path(project_root)
        errors: list[str] = []

        try:
            from services import addons as _addons
            extra = {k: _addons.content_dirs(root, k)
                     for k in ("wardrobe", "scenes", "poses", "modifiers")}
        except Exception:
            extra = {}

        def _merge(loader, key, core_dir):
            merged: dict = {}
            for d in [core_dir, *extra.get(key, [])]:
                merged.update(loader(d, errors))
            return merged

        from app_paths import content_base
        cbase = content_base(assets_root if assets_root is not None else root)
        outfits = _merge(_load_outfits, "wardrobe", cbase / "wardrobe")
        scenes = _merge(_load_scenes, "scenes", cbase / "scenes")
        poses = _merge(_load_poses, "poses", cbase / "poses")
        modifiers = _merge(_load_modifiers, "modifiers", cbase / "modifiers")

        return cls(
            outfits=outfits, scenes=scenes, poses=poses,
            modifiers=modifiers, errors=errors,
        )

    def available_renderer_ids(self) -> set[str]:
        ids: set[str] = set()
        for o in self.outfits.values():
            ids.update(o.renderer_prompts.keys())
        for s in self.scenes.values():
            ids.update(s.renderer_prompts.keys())
        for p in self.poses.values():
            ids.update(p.renderer_prompts.keys())
        for m in self.modifiers.values():
            for opt in m.options:
                ids.update(opt.renderer_prompts.keys())
        return ids

    def get_modifier(self, category: str) -> ModifierCategory | None:
        return self.modifiers.get(category)

    def register_outfit(self, data: dict, *, source: str = "",
                        own: bool = False) -> str | None:
        outfit = _parse_outfit(data, source or "<register_outfit>", [])
        if outfit is None:
            return None
        self.outfits[outfit.id] = outfit
        if own:
            self.own_outfit_ids.add(outfit.id)
        else:
            self.own_outfit_ids.discard(outfit.id)
        return outfit.id

    def unregister_outfit(self, outfit_id: str) -> None:
        self.outfits.pop(outfit_id, None)
        self.own_outfit_ids.discard(outfit_id)

    def is_own_outfit(self, outfit_id: str) -> bool:
        return outfit_id in self.own_outfit_ids

    def compatible_outfits(
        self,
        *,
        renderer_id: str,
        max_rating: str,
        current_tier: str,
        character_id: str,
        character_archetypes: list[str],
        character_tag_gates: dict[str, str] | None = None,
        character_blocked_tags: list[str] | tuple[str, ...] | None = None,
        character_pair: str = "",
    ) -> list[Outfit]:
        from drawing.assets import effective_required_tier
        from persona.gender import pair_allows
        own_ids = getattr(self, "own_outfit_ids", None) or ()
        out: list[Outfit] = []
        for o in self.outfits.values():
            if not o.supports_renderer(renderer_id):
                continue
            if not rating_le(o.rating, max_rating):
                continue
            if character_pair and not pair_allows(o.pairs, character_pair):
                continue
            eff_tier = effective_required_tier(
                o.required_tier, list(o.tags),
                character_tag_gates=character_tag_gates,
                character_blocked_tags=character_blocked_tags,
            )
            if eff_tier is None:
                continue
            if o.id not in own_ids and not tier_ge(current_tier, eff_tier):
                continue
            if not o.character_restrictions.allows_character(
                character_id, character_archetypes
            ):
                continue
            out.append(o)
        return sorted(out, key=lambda x: x.id)

    def compatible_scenes(
        self,
        *,
        renderer_id: str,
        max_rating: str,
    ) -> list[Scene]:
        out = [
            s for s in self.scenes.values()
            if s.supports_renderer(renderer_id) and rating_le(s.rating, max_rating)
        ]
        return sorted(out, key=lambda x: x.id)

    def compatible_poses(
        self,
        *,
        renderer_id: str,
        max_rating: str,
    ) -> list[Pose]:
        out = [
            p for p in self.poses.values()
            if p.supports_renderer(renderer_id) and rating_le(p.rating, max_rating)
        ]
        return sorted(out, key=lambda x: x.id)

    def modifier_options(
        self,
        category: str,
        *,
        renderer_id: str,
    ) -> list[ModifierOption]:
        cat = self.modifiers.get(category)
        if cat is None:
            return []
        return cat.options_for_renderer(renderer_id)


def _read_yaml(path: Path) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return None


def _validate_rating(rating: str, where: str, errors: list[str]) -> bool:
    if rating not in VALID_RATINGS:
        errors.append(f"{where}: rating={rating!r} не из {sorted(VALID_RATINGS)}")
        return False
    return True


def _validate_tier(tier: str, where: str, errors: list[str]) -> bool:
    if tier not in VALID_TIERS:
        errors.append(f"{where}: required_tier={tier!r} не из {sorted(VALID_TIERS)}")
        return False
    return True


def _require(data: dict, key: str, where: str, errors: list[str]) -> bool:
    if key not in data or data[key] in (None, ""):
        errors.append(f"{where}: отсутствует обязательное поле {key!r}")
        return False
    return True


def _parse_renderer_prompts(data: dict | None) -> dict[str, RendererPrompt]:
    if not isinstance(data, dict):
        return {}
    return {
        renderer_id: RendererPrompt.from_dict(value)
        for renderer_id, value in data.items()
    }


def _parse_modifier_prompts(data: dict | None) -> dict[str, str]:
    if not isinstance(data, dict):
        return {}
    return {k: str(v).strip() for k, v in data.items() if v}


def _parse_outfit(
    data: dict, where: str, errors: list[str], source_path: Path | None = None
) -> Outfit | None:
    if not all(
        _require(data, k, where, errors)
        for k in ("id", "name", "rating", "renderer_prompts")
    ):
        return None
    if not _validate_rating(data["rating"], where, errors):
        return None
    required_tier = data.get("required_tier", "distant")
    if not _validate_tier(required_tier, where, errors):
        return None
    hs = data.get("hairstyle") or {}
    if not isinstance(hs, dict):
        errors.append(f"{where}: hairstyle должен быть словарём {{tags, min_hair_length}}")
        hs = {}
    try:
        return Outfit(
            format_version=int(data.get("costume_format_version", 1)),
            id=str(data["id"]),
            name=str(data["name"]),
            rating=str(data["rating"]),
            required_tier=required_tier,
            tags=tuple(data.get("tags") or ()),
            character_restrictions=CharacterRestrictions.from_dict(
                data.get("character_restrictions")
            ),
            compatibility=Compatibility.from_dict(data.get("compatibility")),
            renderer_prompts=_parse_renderer_prompts(data.get("renderer_prompts")),
            author=str(data.get("author", "")),
            license=str(data.get("license", "")),
            created_at=str(data.get("created_at", "")),
            preview=str(data.get("preview", "")),
            source_path=source_path,
            hairstyle_tags=tuple(
                str(t).strip() for t in (hs.get("tags") or ()) if str(t).strip()
            ),
            hairstyle_min_length=str(hs.get("min_hair_length", "") or "").strip().lower(),
            pairs=tuple(
                [data["pairs"]] if isinstance(data.get("pairs"), str)
                else (data.get("pairs") or ())
            ),
        )
    except (TypeError, ValueError) as e:
        errors.append(f"{where}: ошибка построения dataclass: {e}")
        return None


def _load_outfits(wardrobe_dir: Path, errors: list[str]) -> dict[str, Outfit]:
    out: dict[str, Outfit] = {}
    if not wardrobe_dir.exists():
        return out
    for manifest_path in sorted(wardrobe_dir.glob("*/*/manifest.yaml")):
        where = str(manifest_path.relative_to(wardrobe_dir.parent))
        data = _read_yaml(manifest_path)
        if data is None:
            errors.append(f"{where}: не удалось распарсить YAML")
            continue
        outfit = _parse_outfit(data, where, errors, source_path=manifest_path)
        if outfit is None:
            continue

        if outfit.id in out:
            errors.append(
                f"{where}: дубликат id {outfit.id!r} (уже встречался в "
                f"{out[outfit.id].source_path})"
            )
            continue
        out[outfit.id] = outfit
    return out


def _load_scenes(scenes_dir: Path, errors: list[str]) -> dict[str, Scene]:
    out: dict[str, Scene] = {}
    if not scenes_dir.exists():
        return out
    for manifest_path in sorted(scenes_dir.glob("*/*/manifest.yaml")):
        where = str(manifest_path.relative_to(scenes_dir.parent))
        data = _read_yaml(manifest_path)
        if data is None:
            errors.append(f"{where}: не удалось распарсить YAML")
            continue
        if not all(
            _require(data, k, where, errors)
            for k in ("id", "name", "rating", "renderer_prompts")
        ):
            continue
        if not _validate_rating(data["rating"], where, errors):
            continue
        category = data.get("category") or manifest_path.parent.parent.name

        try:
            scene = Scene(
                format_version=int(data.get("scene_format_version", 1)),
                id=str(data["id"]),
                name=str(data["name"]),
                category=str(category),
                rating=str(data["rating"]),
                tags=tuple(data.get("tags") or ()),
                renderer_prompts=_parse_renderer_prompts(data.get("renderer_prompts")),
                preview=str(data.get("preview", "")),
                source_path=manifest_path,
            )
        except (TypeError, ValueError) as e:
            errors.append(f"{where}: ошибка построения dataclass: {e}")
            continue

        if scene.id in out:
            errors.append(f"{where}: дубликат id {scene.id!r}")
            continue
        out[scene.id] = scene
    return out


def _load_poses(poses_dir: Path, errors: list[str]) -> dict[str, Pose]:
    out: dict[str, Pose] = {}
    if not poses_dir.exists():
        return out
    for manifest_path in sorted(poses_dir.glob("*/*/manifest.yaml")):
        where = str(manifest_path.relative_to(poses_dir.parent))
        data = _read_yaml(manifest_path)
        if data is None:
            errors.append(f"{where}: не удалось распарсить YAML")
            continue
        if not all(
            _require(data, k, where, errors)
            for k in ("id", "name", "rating", "renderer_prompts")
        ):
            continue
        if not _validate_rating(data["rating"], where, errors):
            continue
        category = data.get("category") or manifest_path.parent.parent.name

        try:
            pose = Pose(
                format_version=int(data.get("pose_format_version", 1)),
                id=str(data["id"]),
                name=str(data["name"]),
                category=str(category),
                rating=str(data["rating"]),
                tags=tuple(data.get("tags") or ()),
                mood_hints=tuple(data.get("mood_hints") or ()),
                renderer_prompts=_parse_renderer_prompts(data.get("renderer_prompts")),
                preview=str(data.get("preview", "")),
                source_path=manifest_path,
            )
        except (TypeError, ValueError) as e:
            errors.append(f"{where}: ошибка построения dataclass: {e}")
            continue

        if pose.id in out:
            errors.append(f"{where}: дубликат id {pose.id!r}")
            continue
        out[pose.id] = pose
    return out


def _load_modifiers(modifiers_dir: Path, errors: list[str]) -> dict[str, ModifierCategory]:
    out: dict[str, ModifierCategory] = {}
    if not modifiers_dir.exists():
        return out
    for manifest_path in sorted(modifiers_dir.glob("*.yaml")):
        where = str(manifest_path.relative_to(modifiers_dir.parent))
        data = _read_yaml(manifest_path)
        if data is None:
            errors.append(f"{where}: не удалось распарсить YAML")
            continue
        if not _require(data, "category", where, errors):
            continue
        category = str(data["category"])

        options_data = data.get("options") or []
        if not isinstance(options_data, list):
            errors.append(f"{where}: options должно быть списком")
            continue

        opts: list[ModifierOption] = []
        for i, raw in enumerate(options_data):
            if not isinstance(raw, dict):
                errors.append(f"{where}: option[{i}] не dict")
                continue
            opt_id = raw.get("id")
            opt_name = raw.get("name") or opt_id
            if not opt_id:
                errors.append(f"{where}: option[{i}] без id")
                continue
            opts.append(ModifierOption(
                id=str(opt_id),
                name=str(opt_name),
                renderer_prompts=_parse_modifier_prompts(raw.get("renderer_prompts")),
            ))

        if not opts:
            errors.append(f"{where}: ни одной валидной option")
            continue

        if category in out:
            errors.append(f"{where}: дубликат category {category!r}")
            continue

        out[category] = ModifierCategory(
            format_version=int(data.get("modifier_format_version", 1)),
            category=category,
            description=str(data.get("description", "")),
            options=tuple(opts),
            source_path=manifest_path,
        )
    return out
