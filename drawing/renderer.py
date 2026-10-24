from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from drawing.assets import BaseAppearance
from drawing.choice import Choice

if TYPE_CHECKING:
    from drawing.catalog import AssetCatalog


_TAG_WEIGHT_RE = re.compile(r"^\(\s*(.+?)\s*:\s*([0-9]*\.?[0-9]+)\s*\)$")


def _split_tag_weight(tag: str) -> tuple[str, float]:
    m = _TAG_WEIGHT_RE.match(tag.strip())
    if m:
        try:
            return m.group(1).strip(), float(m.group(2))
        except ValueError:
            pass
    return tag.strip(), 1.0


def _dedupe_key(base: str) -> str:
    return base.strip().strip("()").lower().replace("_", " ").strip()


def dedupe_tags(fragments: list[str]) -> list[str]:
    order: list[str] = []
    best: dict[str, tuple[float, str]] = {}
    for frag in fragments:
        if not frag:
            continue
        for raw in frag.split(","):
            raw = raw.strip()
            if not raw:
                continue
            base, w = _split_tag_weight(raw)
            key = _dedupe_key(base)
            if not key:
                continue
            if key not in best:
                best[key] = (w, base)
                order.append(key)
            elif w > best[key][0]:
                best[key] = (w, base)
    out: list[str] = []
    for key in order:
        w, base = best[key]
        out.append(base if w == 1.0 else f"({base}:{w:g})")
    return out


class EmptyPromptError(ValueError):
    pass


from drawing.assets import (
    ASPECT_SQUARE, ASPECT_TALL, ASPECT_WIDE,
    VALID_ASPECTS, ASPECT_DIMENSIONS, DEFAULT_ASPECT,
    aspect_to_dimensions,
)


@dataclass(frozen=True)
class AssembledPrompt:
    positive: str
    negative: str = ""
    seed: int | None = None
    width: int | None = None
    height: int | None = None
    filename_prefix: str = ""
    content_tags: str = ""
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RenderResult:
    image_path: Path
    prompt_used: AssembledPrompt
    duration_sec: float = 0.0
    extra: dict = field(default_factory=dict)


class RendererAdapter:
    renderer_id: str = ""
    positive_prefix: str = ""
    negative_prefix: str = ""

    def collect_fragments(
        self,
        choice: Choice,
        base_appearance: BaseAppearance | None,
        catalog: "AssetCatalog",
    ) -> tuple[list[str], list[str]]:
        positive: list[str] = []
        negative: list[str] = []

        outfit = catalog.outfits.get(choice.outfit_id)

        if base_appearance is not None:
            from drawing.assets import apply_outfit_hairstyle
            from drawing import exposure as _ex
            base_positive = apply_outfit_hairstyle(
                base_appearance.positive_for(self.renderer_id),
                base_appearance, outfit, self.renderer_id)
            _outfit_text = ""
            if outfit is not None and self.renderer_id in outfit.renderer_prompts:
                _outfit_text = outfit.renderer_prompts[self.renderer_id].positive or ""
            _open = _ex.exposed(_outfit_text)
            base_positive, _ = _ex.drop_hidden_marks(base_positive, _open)
            if base_positive:
                positive.append(base_positive)
            for tag in base_appearance.hard_tags:
                need = _ex.mark_region(tag) if tag else None
                if tag and (need is None or set(need) & _open):
                    positive.append(tag)
            for tag in getattr(base_appearance, "negative_tags", ()) or ():
                if tag:
                    negative.append(tag)

        from drawing.color_template import apply as _apply_colors
        colors = base_appearance.favorite_colors if base_appearance is not None else ()
        if outfit is not None and self.renderer_id in outfit.renderer_prompts:
            rp = outfit.renderer_prompts[self.renderer_id]
            if rp.positive:
                positive.append(_apply_colors(rp.positive, colors))
            if rp.negative:
                negative.append(_apply_colors(rp.negative, colors))

        scene = catalog.scenes.get(choice.scene_id)
        if scene is not None and self.renderer_id in scene.renderer_prompts:
            rp = scene.renderer_prompts[self.renderer_id]
            if rp.positive:
                positive.append(rp.positive)
            if rp.negative:
                negative.append(rp.negative)

        pose = catalog.poses.get(choice.pose_id)
        if pose is not None and self.renderer_id in pose.renderer_prompts:
            rp = pose.renderer_prompts[self.renderer_id]
            if rp.positive:
                positive.append(rp.positive)
            if rp.negative:
                negative.append(rp.negative)

        for category in sorted(choice.modifiers.keys()):
            option_id = choice.modifiers[category]
            cat = catalog.modifiers.get(category)
            if cat is None:
                continue
            opt = cat.get_option(option_id)
            if opt is None:
                continue
            mod_text = opt.renderer_prompts.get(self.renderer_id)
            if mod_text:
                positive.append(mod_text)

        from drawing.zones import filter_fragment, framing_level
        level = framing_level(choice.modifiers.get("framing"))
        if level is not None:
            filtered: list[str] = []
            dropped_all: list[str] = []
            for frag in positive:
                kept, dropped = filter_fragment(frag, level)
                if kept:
                    filtered.append(kept)
                dropped_all.extend(dropped)
            if dropped_all:
                print(f"[zones] framing '{level}': выброшено вне кадра "
                      f"({len(dropped_all)}): {dropped_all}")
            positive = filtered

        return positive, negative

    def assemble_prompt(
        self,
        choice: Choice,
        *,
        base_appearance: BaseAppearance | None = None,
        catalog: "AssetCatalog",
        safety_positive: list[str] | None = None,
        safety_negative: list[str] | None = None,
        style_tags: list[str] | None = None,
        quality_tags: list[str] | None = None,
        seed: int | None = None,
        filename_prefix: str = "",
    ) -> AssembledPrompt:
        if choice.is_refusal():
            raise EmptyPromptError(
                "Choice — это refusal, не должен попадать в adapter"
            )

        pos_frags, neg_frags = self.collect_fragments(
            choice, base_appearance, catalog
        )

        comp_frags = pos_frags
        pos_frags = []
        if quality_tags:
            pos_frags.extend(t for t in quality_tags if t)
        pos_frags.extend(comp_frags)
        if safety_positive:
            pos_frags.extend(t for t in safety_positive if t)
        if style_tags:
            pos_frags.extend(t for t in style_tags if t)
        if safety_negative:
            neg_frags.extend(t for t in safety_negative if t)

        positive = self.join_positive(pos_frags)
        negative = self.join_negative(neg_frags)

        positive = self._prepend_prefix(positive, self.positive_prefix)
        negative = self._prepend_prefix(negative, self.negative_prefix)

        if not positive.strip():
            raise EmptyPromptError(
                f"Финальный positive prompt пустой "
                f"(renderer_id={self.renderer_id}, choice={choice})"
            )

        if seed is None:
            seed = random.randint(0, 2**63 - 1)

        aspect = choice.aspect or DEFAULT_ASPECT
        width, height = aspect_to_dimensions(aspect)

        return AssembledPrompt(
            positive=positive,
            negative=negative,
            seed=seed,
            width=width,
            height=height,
            filename_prefix=filename_prefix or "",
        )

    def assemble_freeform(
        self,
        *,
        base_positive: str = "",
        base_negative: str = "",
        outfit_positive: str = "",
        outfit_negative: str = "",
        tags: list[str] | None = None,
        framing_level: str | None = None,
        style_tags: list[str] | None = None,
        quality_tags: list[str] | None = None,
        safety_positive: list[str] | None = None,
        safety_negative: list[str] | None = None,
        seed: int | None = None,
        width: int | None = None,
        height: int | None = None,
        filename_prefix: str = "",
    ) -> AssembledPrompt:
        from drawing.zones import filter_fragment

        fixed_csv = ", ".join(f.strip() for f in (base_positive, outfit_positive)
                              if f and f.strip())
        if framing_level is not None and fixed_csv:
            fixed_csv, dropped = filter_fragment(fixed_csv, framing_level)
            if dropped:
                print(f"[zones] freeform framing '{framing_level}': вне кадра "
                      f"({len(dropped)}): {dropped}")
        comp_csv = ", ".join(p for p in [fixed_csv] + [t.strip() for t in (tags or [])
                                                       if t and t.strip()] if p)

        pos_frags: list[str] = []
        if quality_tags:
            pos_frags.extend(t for t in quality_tags if t)
        if comp_csv.strip():
            pos_frags.append(comp_csv)
        if safety_positive:
            pos_frags.extend(t for t in safety_positive if t)
        if style_tags:
            pos_frags.extend(t for t in style_tags if t)

        neg_frags: list[str] = []
        if base_negative and base_negative.strip():
            neg_frags.append(base_negative.strip())
        if outfit_negative and outfit_negative.strip():
            neg_frags.append(outfit_negative.strip())
        if safety_negative:
            neg_frags.extend(t for t in safety_negative if t)

        positive = self.join_positive(pos_frags)
        negative = self.join_negative(neg_frags)
        positive = self._prepend_prefix(positive, self.positive_prefix)
        negative = self._prepend_prefix(negative, self.negative_prefix)

        if not positive.strip():
            raise EmptyPromptError(
                f"freeform positive пуст (renderer_id={self.renderer_id})"
            )

        if seed is None:
            seed = random.randint(0, 2**63 - 1)

        return AssembledPrompt(
            positive=positive,
            negative=negative,
            seed=seed,
            width=width,
            height=height,
            filename_prefix=filename_prefix or "",
            content_tags=comp_csv.strip(),
        )

    @staticmethod
    def _prepend_prefix(body: str, prefix: str) -> str:
        if not prefix:
            return body
        prefix = prefix.strip().rstrip(",").strip()
        if not body:
            return prefix
        return f"{prefix}, {body}"

    def join_positive(self, fragments: list[str]) -> str:
        return ", ".join(dedupe_tags(fragments))

    def join_negative(self, fragments: list[str]) -> str:
        return ", ".join(dedupe_tags(fragments))

    def render(self, prompt: AssembledPrompt) -> RenderResult:
        raise NotImplementedError(
            f"{type(self).__name__}.render не реализован"
        )


class StubRenderer(RendererAdapter):
    renderer_id = "sdxl"

    def __init__(
        self,
        output_dir: Path | str = "stub_renders",
        *,
        positive_prefix: str = "",
        negative_prefix: str = "",
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.positive_prefix = positive_prefix
        self.negative_prefix = negative_prefix

    def render(self, prompt: AssembledPrompt) -> RenderResult:
        start = time.time()

        seed_str = str(prompt.seed if prompt.seed is not None else "noseed")
        path = self.output_dir / f"{seed_str[:16]}_prompt.txt"

        payload = {
            "renderer": "stub",
            "renderer_id": self.renderer_id,
            "positive": prompt.positive,
            "negative": prompt.negative,
            "seed": prompt.seed,
            "extra": prompt.extra,
            "generated_at": time.time(),
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return RenderResult(
            image_path=path,
            prompt_used=prompt,
            duration_sec=time.time() - start,
            extra={"backend": "stub"},
        )
