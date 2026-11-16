from __future__ import annotations

from pathlib import Path

THRESHOLD = 0.06
SIDES = ("right", "left")
NO_FLIP_TAGS = frozenset({"from side", "profile"})


def detect_side(path: str | Path) -> tuple[str | None, float | None]:
    from PIL import Image

    from drawing.face_crop import detect_face_bbox
    from drawing.list_avatar import head_shift
    from drawing.matting import anime_alpha, matting_available

    if not matting_available():
        return None, None
    bbox = detect_face_bbox(str(path))
    if bbox is None:
        return None, None
    with Image.open(path) as im:
        alpha = anime_alpha(im.convert("RGB"))
    if alpha is None:
        return None, None
    shift = head_shift(alpha, bbox)
    if abs(shift) < THRESHOLD:
        return None, shift
    return ("right" if shift > 0 else "left"), shift


def normalize_side(path: str | Path, want: str, tags=()) -> bool:
    if want not in SIDES or NO_FLIP_TAGS & {str(t).strip().lower() for t in tags}:
        return False
    side, _shift = detect_side(path)
    if side is None or side == want:
        return False
    from PIL import Image, ImageOps
    from PIL.PngImagePlugin import PngInfo

    path = Path(path)
    with Image.open(path) as im:
        info = {k: v for k, v in (im.info or {}).items() if isinstance(v, str)}
        flipped = ImageOps.mirror(im.copy())
    meta = PngInfo()
    for k, v in info.items():
        meta.add_text(k, v)
    tmp = path.with_suffix(path.suffix + ".part")
    flipped.save(tmp, format="PNG", pnginfo=meta)
    tmp.replace(path)
    return True
