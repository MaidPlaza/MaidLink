from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Pipeline:
    id: str
    name: str
    arch: str
    workflow: str


SUPPORTED_PIPELINES: list[Pipeline] = [
    Pipeline(
        id="sdxl_illustrious",
        name="SDXL (Illustrious / NoobAI-стиль)",
        arch="sdxl",
        workflow="image_gen/workflows/maid_portrait.json",
    ),
]


def _read_header(path: Path) -> tuple[list[str], dict]:
    with open(path, "rb") as f:
        raw = f.read(8)
        if len(raw) < 8:
            return [], {}
        n = struct.unpack("<Q", raw)[0]
        if n <= 0 or n > 100 * 1024 * 1024:
            return [], {}
        header = json.loads(f.read(n).decode("utf-8"))
    meta = header.pop("__metadata__", {}) or {}
    return list(header.keys()), meta


def detect_arch(path: str | Path) -> str:
    try:
        keys, _meta = _read_header(Path(path))
    except Exception:
        return "unknown"
    if not keys:
        return "unknown"
    if any("double_blocks." in k or "single_blocks." in k for k in keys):
        return "flux"
    if any("conditioner.embedders.1" in k for k in keys) or any("label_emb." in k for k in keys):
        return "sdxl"
    if any("model.diffusion_model." in k for k in keys):
        return "sd15"
    return "unknown"


def recognize(path: str | Path) -> Pipeline | None:
    arch = detect_arch(path)
    return next((p for p in SUPPORTED_PIPELINES if p.arch == arch), None)
