from __future__ import annotations

import functools
import importlib.util
from pathlib import Path

import numpy as np
from PIL import Image


DEFAULT_MODEL_PATH = (
    "image_gen/ComfyUI_windows_portable/ComfyUI/models/ultralytics/bbox/face_yolov8m.pt"
)

_MODEL = None


@functools.lru_cache(maxsize=1)
def _in_process() -> bool:
    return importlib.util.find_spec("ultralytics") is not None


def default_model_path() -> Path:
    import app_paths
    return app_paths.PROJECT_ROOT / DEFAULT_MODEL_PATH


def _get_model(model_path: str | None = None):
    global _MODEL
    if _MODEL is None:
        from ultralytics import YOLO
        _MODEL = YOLO(model_path or str(default_model_path()))
    return _MODEL


def _face_boxes(paths, model_path: str | None) -> list[list[list[float]]]:
    if not _in_process():
        from drawing import comfy_python
        return comfy_python.face_boxes(paths, model_path or default_model_path())
    model = _get_model(model_path)
    out = []
    for p in paths:
        boxes = []
        for r in model(str(p), verbose=False, device="cpu"):
            if r.boxes is None:
                continue
            for b in r.boxes:
                boxes.append([float(v) for v in b.xyxy[0]] + [float(b.conf[0])])
        out.append(boxes)
    return out


def _largest(boxes, min_conf: float) -> tuple[float, float, float, float] | None:
    best_area = -1.0
    best_box = None
    for x1, y1, x2, y2, conf in boxes:
        if conf < min_conf:
            continue
        area = (x2 - x1) * (y2 - y1)
        if area > best_area:
            best_area = area
            best_box = (x1, y1, x2, y2)
    return best_box


def detect_face_bboxes(paths, *, model_path: str | None = None,
                       min_conf: float = 0.3) -> list[tuple[float, float, float, float] | None]:
    paths = list(paths)
    if not paths:
        return []
    return [_largest(b, min_conf) for b in _face_boxes(paths, model_path)]


def detect_face_bbox(image_path: str, *, model_path: str | None = None,
                     min_conf: float = 0.3) -> tuple[float, float, float, float] | None:
    return detect_face_bboxes([image_path], model_path=model_path, min_conf=min_conf)[0]


def align_face_crop(img: Image.Image, bbox: tuple[float, float, float, float], *,
                    scale: float, shift: float,
                    target: tuple[int, int],
                    ref_face_h: float | None = None) -> Image.Image:
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    size_h = max(1.0, ref_face_h if ref_face_h is not None else (y2 - y1))

    tw, th = target
    aspect = tw / th
    crop_h = size_h * scale
    crop_w = crop_h * aspect

    left = cx - crop_w / 2.0
    top = cy - shift * crop_h

    il, it = int(round(left)), int(round(top))
    ir, ib = il + int(round(crop_w)), it + int(round(crop_h))

    arr = np.asarray(img.convert("RGB"))
    h, w = arr.shape[:2]
    pad_l, pad_t = max(0, -il), max(0, -it)
    pad_r, pad_b = max(0, ir - w), max(0, ib - h)
    if pad_l or pad_t or pad_r or pad_b:
        ch = max(1, h // 6)
        cw = max(1, w // 6)
        tl = arr[:ch, :cw].reshape(-1, 3)
        tr = arr[:ch, -cw:].reshape(-1, 3)
        bg = np.median(np.concatenate([tl, tr], axis=0), axis=0).astype(arr.dtype)
        padded = np.empty((h + pad_t + pad_b, w + pad_l + pad_r, 3), dtype=arr.dtype)
        padded[:] = bg
        padded[pad_t:pad_t + h, pad_l:pad_l + w] = arr
        arr = padded
        il += pad_l
        ir += pad_l
        it += pad_t
        ib += pad_t

    crop = arr[it:ib, il:ir]
    return Image.fromarray(crop).resize((tw, th), Image.LANCZOS)


AVATAR_TARGET = (512, 512)
AVATAR_SCALE = 1.11
AVATAR_SHIFT = 0.66


def crop_face_avatar(src_path, dst_path, *, target: tuple[int, int] = AVATAR_TARGET,
                     scale: float = AVATAR_SCALE, shift: float = AVATAR_SHIFT,
                     model_path: str | None = None) -> bool:
    src = Path(src_path)
    if not src.exists():
        return False
    bbox = detect_face_bbox(str(src), model_path=model_path)
    if bbox is None:
        return False
    out = align_face_crop(Image.open(src), bbox, scale=scale, shift=shift,
                          target=target)
    dst = Path(dst_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.save(dst)
    return True


def align_portrait_set(paths, *, scale: float, shift: float,
                       target: tuple[int, int],
                       model_path: str | None = None) -> dict[str, str]:
    results: dict[str, str] = {}
    present = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            results[str(path)] = "missing"
            continue
        present.append(str(path))
    detected = dict(zip(present, detect_face_bboxes(present, model_path=model_path)))

    heights = [b[3] - b[1] for b in detected.values() if b is not None]
    ref_h = float(np.median(heights)) if heights else None

    for sp, bbox in detected.items():
        if bbox is None:
            results[sp] = "no_face"
            continue
        img = Image.open(sp)
        out = align_face_crop(img, bbox, scale=scale, shift=shift,
                              target=target, ref_face_h=ref_h)
        out.save(sp)
        results[sp] = "ok"
    return results
