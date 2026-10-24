from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from drawing.face_crop import detect_face_bbox

CANVAS = (1024, 1536)
FACE_H = 380.0
FACE_CX = 512.0
FACE_CY = 430.0
SCALE_MIN, SCALE_MAX = 0.4, 3.0

MATTE_KEY = "maid_matte"


def compose_list_avatar(img: Image.Image, bbox: tuple[float, float, float, float],
                        alpha: np.ndarray | None = None, *,
                        canvas: tuple[int, int] = CANVAS) -> Image.Image:
    x1, y1, x2, y2 = bbox
    face_h = max(1.0, y2 - y1)
    scale = min(SCALE_MAX, max(SCALE_MIN, FACE_H / face_h))
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0

    rgb = img.convert("RGB")
    w, h = rgb.size
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    rgb = rgb.resize((nw, nh), Image.LANCZOS)
    if alpha is None:
        a = Image.new("L", (nw, nh), 255)
    else:
        a = Image.fromarray(np.asarray(alpha, dtype=np.uint8), mode="L").resize((nw, nh), Image.BILINEAR)
    layer = rgb.copy()
    layer.putalpha(a)

    off_x = int(round(FACE_CX - cx * scale))
    off_y = int(round(FACE_CY - cy * scale))
    out = Image.new("RGBA", canvas, (0, 0, 0, 0))
    out.paste(layer, (off_x, off_y), layer)
    return out


def make_list_avatar(src_path, dst_path, *, model_path: str | None = None,
                     matte_model_path: str | None = None) -> str:
    from drawing.matting import anime_alpha

    src = Path(src_path)
    if not src.exists():
        return "missing"
    bbox = detect_face_bbox(str(src), model_path=model_path)
    if bbox is None:
        return "no_face"
    img = Image.open(src)
    alpha = None
    try:
        alpha = anime_alpha(img, model_path=matte_model_path)
    except Exception as e:
        print(f"[list_avatar] matting failed ({src.name}): {type(e).__name__}: {e}")
    out = compose_list_avatar(img, bbox, alpha)
    meta = PngInfo()
    meta.add_text(MATTE_KEY, "1" if alpha is not None else "0")
    dst = Path(dst_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".png.part")
    out.save(tmp, format="PNG", pnginfo=meta)
    tmp.replace(dst)
    return "ok" if alpha is not None else "ok_opaque"


def has_matte(path) -> bool:
    try:
        with Image.open(path) as im:
            return (im.text or {}).get(MATTE_KEY) == "1"
    except Exception:
        return False


def is_fresh(list_path, portrait_path, *, matte_model_path: str | None = None) -> bool:
    from drawing.matting import matting_available

    lp, pp = Path(list_path), Path(portrait_path)
    if not lp.exists():
        return False
    if pp.exists() and lp.stat().st_mtime < pp.stat().st_mtime:
        return False
    if matting_available(matte_model_path) and not has_matte(lp):
        return False
    return True
