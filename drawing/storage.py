from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from drawing.critic import Verdict
from drawing.pipeline import PipelineResult


@dataclass(frozen=True)
class StoredImage:
    character_id: str
    image_path: Path
    sidecar_path: Path
    metadata: dict
    media_url: str

    @property
    def filename(self) -> str:
        return self.image_path.name


class ImageStorage:
    def __init__(
        self,
        root_dir: Path | str,
        *,
        media_url_prefix: str = "/media/generated",
    ):
        self.root_dir = Path(root_dir)
        self.media_url_prefix = media_url_prefix.rstrip("/")
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def save_from_pipeline(
        self,
        result: PipelineResult,
        *,
        character_id: str,
        intent: str,
        rating: str = "",
    ) -> StoredImage:
        if not result.is_success or result.image_path is None:
            raise ValueError("ImageStorage.save_from_pipeline: result не success")
        if result.assembled_prompt is None:
            raise ValueError("ImageStorage.save_from_pipeline: assembled_prompt пуст")

        source = result.image_path
        if not source.exists():
            raise FileNotFoundError(f"source image отсутствует: {source}")

        target_dir = self.root_dir / character_id
        target_dir.mkdir(parents=True, exist_ok=True)

        if source.parent == target_dir:
            target_path = source
            base = source.stem
        else:
            base = self._next_basename(target_dir)
            target_path = target_dir / f"{base}.png"
            shutil.move(str(source), str(target_path))

        sidecar_path = target_dir / f"{base}.json"
        metadata = self._build_metadata(
            character_id=character_id,
            intent=intent,
            rating=rating,
            result=result,
        )
        sidecar_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return StoredImage(
            character_id=character_id,
            image_path=target_path,
            sidecar_path=sidecar_path,
            metadata=metadata,
            media_url=f"{self.media_url_prefix}/{character_id}/{target_path.name}",
        )

    def list_for_character(self, character_id: str) -> list[StoredImage]:
        char_dir = self.root_dir / character_id
        if not char_dir.exists():
            return []
        out: list[StoredImage] = []
        for img_path in sorted(char_dir.glob("*.png")):
            sidecar_path = img_path.with_suffix(".json")
            metadata = {}
            if sidecar_path.exists():
                try:
                    metadata = json.loads(sidecar_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    pass
            out.append(StoredImage(
                character_id=character_id,
                image_path=img_path,
                sidecar_path=sidecar_path,
                metadata=metadata,
                media_url=f"{self.media_url_prefix}/{character_id}/{img_path.name}",
            ))
        return out

    def path_for_media_url(self, url: str) -> Path | None:
        from urllib.parse import unquote
        raw = (url or "").split("?", 1)[0]
        marker = self.media_url_prefix + "/"
        i = raw.find(marker)
        if i < 0:
            return None
        parts = [unquote(p) for p in raw[i + len(marker):].split("/") if p]
        if len(parts) != 2 or any(p in ("..", ".") for p in parts):
            return None
        root = self.root_dir.resolve()
        path = (root / parts[0] / parts[1]).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            return None
        if path.suffix.lower() != ".png" or not path.is_file():
            return None
        return path

    def purge(self, character_id: str | None = None, *, keep=()) -> int:
        keep_set = set(keep or ())
        dirs = ([self.root_dir / character_id] if character_id
                else [self.root_dir] + [d for d in self.root_dir.iterdir() if d.is_dir()])
        removed = 0
        for d in dirs:
            if not d.is_dir():
                continue
            for png in list(d.glob("*.png")):
                if png.name in keep_set:
                    continue
                try:
                    png.unlink()
                    removed += 1
                except OSError:
                    continue
                sc = png.with_suffix(".json")
                if sc.exists():
                    try:
                        sc.unlink()
                    except OSError:
                        pass
        return removed

    def _next_basename(self, char_dir: Path) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        counter = 1
        while counter < 1000:
            base = f"{timestamp}_{counter:03d}"
            if not (char_dir / f"{base}.png").exists():
                return base
            counter += 1
        return f"{timestamp}_999"

    def _build_metadata(
        self,
        *,
        character_id: str,
        intent: str,
        rating: str,
        result: PipelineResult,
    ) -> dict:
        ap = result.assembled_prompt
        choice = result.choice
        verdicts: list[dict] = []
        for v in result.critic_verdicts:
            verdicts.append({
                "verdict": v.verdict,
                "confidence": round(v.confidence, 3),
                "severity": v.severity,
                "issues": list(v.issues),
                "regen_hint": v.regen_hint,
            })

        return {
            "character_id": character_id,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "intent": intent,
            "choice": {
                "outfit_id": choice.outfit_id,
                "scene_id": choice.scene_id,
                "pose_id": choice.pose_id,
                "modifiers": dict(choice.modifiers),
                "aspect": choice.aspect,
            } if not choice.is_refusal() else None,
            "renderer": (result.render_result.extra.get("renderer_id")
                          if result.render_result else ""),
            "seed": ap.seed if ap else None,
            "width": ap.width if ap else None,
            "height": ap.height if ap else None,
            "assembled_positive": (ap.positive if ap else "")[:1500],
            "assembled_negative": (ap.negative if ap else "")[:500],
            "rating": rating,
            "critic_verdicts": verdicts,
            "is_favorite": False,
        }


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".json"}


def _clear_tree(root: Path, *, exts: set[str] | None = None) -> int:
    if not root.is_dir():
        return 0
    removed = 0
    for f in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        try:
            if f.is_file():
                if exts is None or f.suffix.lower() in exts:
                    f.unlink()
                    removed += 1
            elif f.is_dir():
                f.rmdir()
        except OSError:
            continue
    return removed


def legacy_comfy_output_dir(project_root: Path, launch_command) -> Path | None:
    for arg in launch_command or ():
        a = str(arg).replace("\\", "/")
        if a.endswith("ComfyUI/main.py"):
            p = Path(a)
            return (p if p.is_absolute() else project_root / p).parent / "output"
    return None


def purge_session_images(project_root: Path, image_gen, *,
                         frozen: bool | None = None) -> int:
    import sys
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    project_root = Path(project_root)
    removed = 0
    if not getattr(image_gen, "keep_generated", False):
        gen = project_root / image_gen.output_dir
        if gen.is_dir():
            removed += ImageStorage(gen).purge()
    removed += _clear_tree(project_root / image_gen.comfy_output_dir)
    if frozen:
        legacy = legacy_comfy_output_dir(project_root, image_gen.launch_command)
        if legacy is not None:
            removed += _clear_tree(legacy, exts=_IMAGE_EXTS)
    return removed
