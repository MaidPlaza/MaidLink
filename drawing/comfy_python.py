from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import numpy as np

PY_EMBED = "image_gen/ComfyUI_windows_portable/python_embeded/python.exe"
TIMEOUT_SEC = 180
_NO_MODULE = 3

_WORKER = r"""
import json, sys
task, job = sys.argv[1], json.loads(sys.stdin.read())
try:
    if task == "faces":
        from ultralytics import YOLO
    else:
        import numpy as np
        import cv2
except ImportError as e:
    print(f"{type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(3)
if task == "faces":
    model, result = YOLO(job["model"]), []
    for path in job["images"]:
        boxes = []
        for r in model(path, verbose=False, device="cpu"):
            for b in (r.boxes if r.boxes is not None else ()):
                boxes.append([float(v) for v in b.xyxy[0]] + [float(b.conf[0])])
        result.append(boxes)
else:
    net = cv2.dnn.readNetFromONNX(job["model"])
    net.setInput(np.load(job["input"]))
    np.save(job["output"], net.forward())
    result = None
print("\n" + json.dumps(result))
"""

_LOCK = threading.Lock()
_FAILED: dict[str, str] = {}


def python_exe() -> Path:
    import app_paths
    return app_paths.PROJECT_ROOT / PY_EMBED


def available(task: str) -> bool:
    return task not in _FAILED and python_exe().is_file()


def face_boxes(images, model) -> list[list[list[float]]]:
    _need_file(model)
    return _run("faces", {"model": str(Path(model).resolve()),
                          "images": [str(Path(p).resolve()) for p in images]})


def isnet_forward(x: np.ndarray, model) -> np.ndarray:
    _need_file(model)
    with tempfile.TemporaryDirectory(prefix="maidlink-isnet-") as tmp:
        inp, out = Path(tmp) / "x.npy", Path(tmp) / "y.npy"
        np.save(inp, x)
        _run("isnet", {"model": str(Path(model).resolve()), "input": str(inp),
                       "output": str(out)})
        return np.load(out)


def _need_file(model) -> None:
    if not Path(model).is_file():
        raise FileNotFoundError(f"нет модели: {model}")


def _run(task: str, job: dict):
    if task in _FAILED:
        raise RuntimeError(f"питон ComfyUI ({task}): {_FAILED[task]}")
    exe = python_exe()
    if not exe.is_file():
        raise FileNotFoundError(f"нет питона ComfyUI: {exe}")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
               CUDA_VISIBLE_DEVICES="",
               YOLO_OFFLINE="true", YOLO_VERBOSE="false")
    kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    with _LOCK:
        try:
            r = subprocess.run([str(exe), "-I", "-c", _WORKER, task], input=json.dumps(job),
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=TIMEOUT_SEC, cwd=str(exe.parent),
                               env=env, **kw)
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"питон ComfyUI ({task}): не уложился в {TIMEOUT_SEC} с") from None
    if r.returncode != 0:
        lines = [ln.strip() for ln in (r.stderr or "").splitlines() if ln.strip()]
        reason = lines[-1] if lines else f"код выхода {r.returncode}"
        if r.returncode == _NO_MODULE:
            _FAILED[task] = reason
        raise RuntimeError(f"питон ComfyUI ({task}): {reason}")
    return json.loads(r.stdout.strip().splitlines()[-1])
