from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

DEFAULT_MODEL_PATH = (
    "image_gen/ComfyUI_windows_portable/ComfyUI/models/onnx/isnet-anime.onnx"
)

_INPUT_SIZE = (1024, 1024)
_MEAN = (0.485, 0.456, 0.406)

_SESSION = None
_SESSION_PATH = None


def _model_file(model_path: str | None = None) -> Path:
    if model_path:
        return Path(model_path)
    import app_paths
    return app_paths.PROJECT_ROOT / DEFAULT_MODEL_PATH


def matting_available(model_path: str | None = None) -> bool:
    return _model_file(model_path).is_file()


def _get_session(model_path: str | None = None):
    global _SESSION, _SESSION_PATH
    path = str(_model_file(model_path))
    if _SESSION is None or _SESSION_PATH != path:
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        _SESSION = ort.InferenceSession(path, sess_options=opts,
                                        providers=["CPUExecutionProvider"])
        _SESSION_PATH = path
    return _SESSION


def anime_alpha(img: Image.Image, *, model_path: str | None = None,
                pockets: bool = True) -> np.ndarray | None:
    if not matting_available(model_path):
        return None
    sess = _get_session(model_path)
    rgb = img.convert("RGB")
    small = rgb.resize(_INPUT_SIZE, Image.LANCZOS)
    arr = np.asarray(small).astype(np.float32)
    arr = arr / max(float(arr.max()), 1e-6)
    x = np.empty_like(arr)
    for i in range(3):
        x[:, :, i] = arr[:, :, i] - _MEAN[i]
    x = np.expand_dims(x.transpose((2, 0, 1)), 0)
    name = sess.get_inputs()[0].name
    pred = sess.run(None, {name: x})[0][:, 0, :, :]
    lo, hi = float(pred.min()), float(pred.max())
    pred = (pred - lo) / max(hi - lo, 1e-6)
    mask = Image.fromarray((np.squeeze(pred) * 255).astype(np.uint8), mode="L")
    mask = mask.resize(rgb.size, Image.LANCZOS)
    alpha = np.asarray(mask)
    if pockets:
        alpha = remove_background_pockets(np.asarray(rgb), alpha)
    return alpha


POCKET_KEY_TOL = 16.0
POCKET_MEAN_TOL = 12.0
POCKET_MAX_STD = 6.6
POCKET_MAX_FRAC = 0.10
POCKET_MIN_AREA = 120
POCKET_RING = 3
POCKET_BG_FLAT_STD = 12.0


def background_color(rgb: np.ndarray) -> np.ndarray:
    return np.median(_corner_pixels(rgb).astype(np.float32), axis=0)


def _corner_pixels(rgb: np.ndarray) -> np.ndarray:
    h, w = rgb.shape[:2]
    ch, cw = max(1, h // 6), max(1, w // 6)
    tl = rgb[:ch, :cw].reshape(-1, 3)
    tr = rgb[:ch, -cw:].reshape(-1, 3)
    return np.concatenate([tl, tr], axis=0)


def remove_background_pockets(rgb: np.ndarray, alpha: np.ndarray, *,
                              key_tol: float = POCKET_KEY_TOL,
                              mean_tol: float = POCKET_MEAN_TOL,
                              max_std: float = POCKET_MAX_STD,
                              max_frac: float = POCKET_MAX_FRAC,
                              min_area: int = POCKET_MIN_AREA,
                              ring: int = POCKET_RING) -> np.ndarray:
    from scipy import ndimage

    corners = _corner_pixels(rgb).astype(np.float32)
    if float(corners.std(axis=0).mean()) > POCKET_BG_FLAT_STD:
        return alpha
    rgbf = rgb.astype(np.float32)
    bg = np.median(corners, axis=0)
    dist = np.sqrt(((rgbf - bg) ** 2).sum(axis=-1))
    labels, n = ndimage.label(dist < key_tol, structure=np.ones((3, 3), dtype=int))
    if n == 0:
        return alpha
    h, w = dist.shape
    max_area = max_frac * h * w
    border = np.zeros(n + 1, dtype=bool)
    for edge in (labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]):
        border[np.unique(edge)] = True
    areas = np.bincount(labels.ravel(), minlength=n + 1)
    pockets = np.zeros(dist.shape, dtype=bool)
    for lab in range(1, n + 1):
        if border[lab] or areas[lab] < min_area or areas[lab] > max_area:
            continue
        comp = labels == lab
        if float(alpha[comp].mean()) < 128:
            continue
        if float(dist[comp].mean()) > mean_tol:
            continue
        if float(rgbf[comp].std(axis=0).mean()) > max_std:
            continue
        pockets |= comp
    if not pockets.any():
        return alpha
    cut = pockets.astype(np.float32)
    if ring > 0:
        halo = ndimage.binary_dilation(pockets, iterations=ring) & ~pockets
        keep = np.clip((dist[halo] - 6.0) / 20.0, 0.0, 1.0)
        cut[halo] = 1.0 - keep
    out = alpha.astype(np.float32) * (1.0 - cut)
    return out.astype(np.uint8)
