from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

_FROZEN = getattr(sys, "frozen", False)


def _run_hidden(cmd, **kw):
    if _FROZEN and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kw["creationflags"] = kw.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
    return subprocess.run(cmd, **kw)


COMFY_ROOT = "image_gen/ComfyUI_windows_portable"
_PY_EMBED = f"{COMFY_ROOT}/python_embeded/python.exe"
_CN = f"{COMFY_ROOT}/ComfyUI/custom_nodes"
_MODELS = f"{COMFY_ROOT}/ComfyUI/models"


@dataclass
class IGComponent:
    key: str
    kind: str
    dest: str
    license: str
    title: str
    agpl: bool = False
    size: int = 0
    url: str = ""
    sha256: str = ""
    user_provided: bool = False
    source: str = ""
    repo_id: str = ""
    filename: str = ""
    revision: str = "main"


MANIFEST: list[IGComponent] = [
    IGComponent(
        key="comfyui", kind="archive7z", dest=COMFY_ROOT,
        title="ComfyUI (движок генерации, portable)",
        license="GNU GPL-3.0",
        url="https://github.com/Comfy-Org/ComfyUI/releases/download/v0.19.3/ComfyUI_windows_portable_nvidia.7z",
    ),
    IGComponent(
        key="impact-pack", kind="node",
        url="https://github.com/ltdrdata/ComfyUI-Impact-Pack/archive/refs/heads/Main.zip",
        dest=f"{_CN}/comfyui-impact-pack",
        title="ComfyUI Impact Pack (детейлер)",
        license="GNU GPL-3.0",
    ),
    IGComponent(
        key="impact-subpack", kind="node",
        url="https://github.com/ltdrdata/ComfyUI-Impact-Subpack/archive/refs/heads/main.zip",
        dest=f"{_CN}/comfyui-impact-subpack",
        title="ComfyUI Impact Subpack (YOLO-провайдер)",
        license="GNU AGPL-3.0", agpl=True,
    ),
    IGComponent(
        key="checkpoint", kind="file", user_provided=True,
        dest=f"{_MODELS}/checkpoints/JANKUTrainedChenkinNoobai_v777.safetensors",
        title="Чекпойнт рисования (.safetensors — ваш файл)",
        license="NoobAI/FAIPL — некоммерческая; файл предоставляете вы",
    ),
    IGComponent(
        key="yolo-face", kind="hf",
        repo_id="Bingsu/adetailer", filename="face_yolov8m.pt",
        dest=f"{_MODELS}/ultralytics/bbox/face_yolov8m.pt",
        title="YOLO-детектор лица (для FaceDetailer)",
        license="AGPL-3.0 (Ultralytics)", agpl=True,
    ),
    IGComponent(
        key="yolo-hand", kind="hf",
        repo_id="Bingsu/adetailer", filename="hand_yolov8s.pt",
        dest=f"{_MODELS}/ultralytics/bbox/hand_yolov8s.pt",
        title="YOLO-детектор рук (для FaceDetailer рук)",
        license="AGPL-3.0 (Ultralytics)", agpl=True,
    ),
    IGComponent(
        key="sam", kind="hf",
        repo_id="segments-arnaud/sam_vit_h", filename="sam_vit_h_4b8939.pth",
        sha256="a7bf3b02f3ebf1267aba913ff637d9a2d5c33d3173bb679e46d9f338c26f262e",
        dest=f"{_MODELS}/sams/sam_vit_h_4b8939.pth",
        title="SAM (сегментация для детейлера)",
        license="Apache-2.0 (Meta)",
    ),
    IGComponent(
        key="isnet-anime", kind="file",
        url="https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-anime.onnx",
        dest=f"{_MODELS}/onnx/isnet-anime.onnx",
        size=176_069_933,
        sha256="f15622d853e8260172812b657053460e20806f04b9e05147d49af7bed31a6e99",
        title="ISNet-anime (вырезание фона для аватарок списка)",
        license="Apache-2.0 (SkyTNT anime-segmentation; сборка rembg, MIT)",
    ),
    IGComponent(
        key="embeddings", kind="bundled", source="image_gen/embeddings",
        dest=f"{_MODELS}/embeddings",
        title="Эмбеддинги lazypos/neg/hand/wet",
        license="Fair AI Public License 1.0-SD (бандлим)",
    ),
]


def _present(comp: IGComponent, project_root: Path) -> bool:
    p = project_root / comp.dest
    if comp.kind == "archive7z":
        return (project_root / _PY_EMBED).exists()
    if comp.kind == "node":
        return p.is_dir() and any(p.iterdir()) if p.exists() else False
    if comp.kind == "bundled":
        return p.is_dir() and (any(p.glob("*.safetensors")) or any(p.glob("*.pt")))
    return p.exists()


def comfy_installed(project_root: Path) -> bool:
    return (project_root / _PY_EMBED).exists()


def checkpoint_installed(project_root: Path) -> bool:
    comp = next((c for c in MANIFEST if c.key == "checkpoint"), None)
    return bool(comp) and _present(comp, project_root)


def status(project_root: Path) -> dict:
    comps = [{
        "key": c.key, "title": c.title, "license": c.license, "agpl": c.agpl,
        "user_provided": c.user_provided,
        "present": _present(c, project_root),
    } for c in MANIFEST]
    missing = [c["key"] for c in comps if not c["present"]]
    return {
        "installed": not missing,
        "components": comps,
        "missing": missing,
        "agpl_components": [c.key for c in MANIFEST if c.agpl],
        "installing": is_installing(),
        "progress": get_progress(),
    }


@dataclass
class CompProgress:
    key: str
    status: str = "pending"
    downloaded: int = 0
    total: int = 0
    error: str = ""


_progress: dict[str, CompProgress] = {}
_lock = threading.Lock()
_thread: threading.Thread | None = None


def get_progress() -> list[dict]:
    with _lock:
        return [vars(p) for p in _progress.values()]


def is_installing() -> bool:
    return _thread is not None and _thread.is_alive()


def _download(url: str, dest: Path, prog: CompProgress) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    existing = part.stat().st_size if part.exists() else 0
    prog.status, prog.downloaded = "downloading", existing
    headers = {"Range": f"bytes={existing}-"} if existing else {}
    with httpx.stream("GET", url, headers=headers, timeout=None,
                      follow_redirects=True) as r:
        r.raise_for_status()
        if not prog.total:
            prog.total = existing + int(r.headers.get("content-length", 0))
        with open(part, "ab" if existing else "wb") as f:
            for chunk in r.iter_bytes(chunk_size=1024 * 1024):
                f.write(chunk)
                prog.downloaded += len(chunk)
    part.replace(dest)


def _sha256_ok(path: Path, expected: str) -> bool:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().lower() == expected.lower()


def _install_one(comp: IGComponent, project_root: Path) -> None:
    prog = _progress[comp.key]
    try:
        if comp.kind == "bundled":
            from app_paths import ASSETS_ROOT
            src_dir = ASSETS_ROOT / comp.source
            dest_dir = project_root / comp.dest
            dest_dir.mkdir(parents=True, exist_ok=True)
            prog.status = "copying"
            files = list(src_dir.glob("*.safetensors")) + list(src_dir.glob("*.pt"))
            for f in files:
                shutil.copy2(f, dest_dir / f.name)
            prog.status = "done" if files else "error"
            if not files:
                prog.error = f"нет файлов-эмбеддингов в {comp.source}"
            return
        if comp.kind == "hf":
            url = f"https://huggingface.co/{comp.repo_id}/resolve/{comp.revision}/{comp.filename}"
            _download(url, project_root / comp.dest, prog)
            if comp.sha256 and not _sha256_ok(project_root / comp.dest, comp.sha256):
                prog.status, prog.error = "error", "sha256 не совпал — файл повреждён/подменён"
                return
            prog.status = "done"
            return
        if comp.kind in ("file", "archive7z") and not comp.url:
            prog.status, prog.error = "error", "нет URL — заполни MANIFEST (services/image_gen_setup.py)"
            return
        if comp.kind == "file":
            _download(comp.url, project_root / comp.dest, prog)
            prog.status = "done"
        elif comp.kind == "archive7z":
            tmp = project_root / "image_gen" / "_comfyui_download.7z"
            _download(comp.url, tmp, prog)
            prog.status = "extracting"
            _extract_7z(tmp, project_root / "image_gen", project_root)
            tmp.unlink(missing_ok=True)
            prog.status = "done"
        elif comp.kind == "node":
            if not comp.url:
                prog.status, prog.error = "error", "нет URL для kind=node"
                return
            tmp = project_root / "image_gen" / f"_{comp.key}.zip"
            _download(comp.url, tmp, prog)
            prog.status = "extracting"
            dest = project_root / comp.dest
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            _extract_zip_into(tmp, dest)
            tmp.unlink(missing_ok=True)
            req = dest / "requirements.txt"
            py = project_root / _PY_EMBED
            if req.exists() and py.exists():
                prog.status = "pip"
                pkgs = [
                    s for s in (
                        ln.strip()
                        for ln in req.read_text(encoding="utf-8", errors="replace").splitlines()
                    )
                    if s and not s.startswith("#") and "git+" not in s
                ]
                if pkgs:
                    _run_hidden([str(py), "-s", "-m", "pip", "install", *pkgs],
                                cwd=str(dest), check=False)
            prog.status = "done"
    except Exception as e:
        prog.status, prog.error = "error", f"{type(e).__name__}: {e}"


def _find_7z(project_root: Path) -> Path | None:
    cands = [
        project_root / "node_modules" / "7zip-bin" / "win" / "x64" / "7za.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "7-Zip" / "7z.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "7-Zip" / "7z.exe",
    ]
    for c in cands:
        if c.exists():
            return c
    found = shutil.which("7z") or shutil.which("7za")
    return Path(found) if found else None


def _extract_7z(archive: Path, dest_dir: Path, project_root: Path) -> None:
    marker = project_root / _PY_EMBED

    def _seven(exe: Path) -> None:
        _run_hidden([str(exe), "x", str(archive), f"-o{dest_dir}", "-y"],
                    check=False, stdout=subprocess.DEVNULL)

    seven = _find_7z(project_root)
    if seven:
        _seven(seven)
        if marker.exists():
            return
    tar = shutil.which("tar")
    if tar:
        _run_hidden([tar, "-xf", str(archive), "-C", str(dest_dir)], check=False)
        if marker.exists():
            return
    winget = shutil.which("winget")
    if winget:
        _run_hidden([winget, "install", "-e", "--id", "7zip.7zip",
                     "--accept-source-agreements", "--accept-package-agreements"], check=False)
        seven = _find_7z(project_root)
        if seven:
            _seven(seven)
            if marker.exists():
                return
    raise RuntimeError("не удалось распаковать ComfyUI .7z: не найден 7-Zip/tar. "
                       "Установите 7-Zip (7-zip.org) и повторите установку.")


def _extract_zip_into(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        roots = {n.split("/", 1)[0] for n in names if "/" in n}
        strip = (len(roots) == 1)
        root = next(iter(roots)) + "/" if strip else ""
        for n in names:
            if n.endswith("/"):
                continue
            rel = n[len(root):] if strip and n.startswith(root) else n
            if not rel:
                continue
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(n) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def select_todo(project_root: Path, include_agpl: bool = True) -> list[IGComponent]:
    return [c for c in MANIFEST
            if not _present(c, project_root) and not c.user_provided
            and (include_agpl or not c.agpl)]


def start_install(project_root: Path, include_agpl: bool = True) -> list[str]:
    global _thread
    if is_installing():
        return [p.key for p in _progress.values() if p.status not in ("done", "error")]
    todo = select_todo(project_root, include_agpl=include_agpl)
    with _lock:
        _progress.clear()
        for c in todo:
            _progress[c.key] = CompProgress(key=c.key, total=c.size)

    def _run():
        for c in todo:
            _install_one(c, project_root)

    _thread = threading.Thread(target=_run, daemon=True)
    _thread.start()
    return [c.key for c in todo]


def set_checkpoint_from_path(project_root: Path, src: str) -> dict:
    global _thread
    comp = next(c for c in MANIFEST if c.key == "checkpoint")
    srcp = Path(src)
    if not srcp.is_file() or srcp.suffix.lower() != ".safetensors":
        return {"ok": False, "error": "нужен существующий файл .safetensors"}
    from drawing.checkpoint_registry import recognize
    pipeline = recognize(srcp)
    if pipeline is None:
        return {"ok": False, "error": "файл не распознан как поддерживаемый чекпойнт "
                "(нужна архитектура SDXL; другие пайплайны добавим позже)"}
    if is_installing():
        return {"ok": False, "error": "идёт установка — подождите"}
    dest = project_root / comp.dest
    with _lock:
        _progress.clear()
        _progress["checkpoint"] = CompProgress(key="checkpoint", total=srcp.stat().st_size)

    def _run():
        prog = _progress["checkpoint"]
        prog.status = "copying"
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".safetensors.part")
            with open(srcp, "rb") as fsrc, open(tmp, "wb") as fdst:
                while True:
                    chunk = fsrc.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    fdst.write(chunk)
                    prog.downloaded += len(chunk)
            tmp.replace(dest)
            prog.status = "done"
        except Exception as e:
            prog.status, prog.error = "error", f"{type(e).__name__}: {e}"

    _thread = threading.Thread(target=_run, daemon=True)
    _thread.start()
    return {"ok": True, "copying": True,
            "pipeline": {"id": pipeline.id, "name": pipeline.name, "workflow": pipeline.workflow}}
