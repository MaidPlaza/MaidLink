from __future__ import annotations

import hashlib
import os
import shutil
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from app_paths import ASSETS_ROOT
from services.background.nvml_probe import get_vram_info


@dataclass
class ModelEntry:
    key: str
    rel_path: str
    size: int
    sha256: str
    role: str = ""
    quant: str = ""
    repo_id: str = ""
    filename: str = ""
    revision: str = "main"
    url: str = ""
    required: bool = True
    group: str = ""
    legacy_sizes: tuple[int, ...] = ()
    title: str = ""
    unpack_to: str = ""
    members: tuple[tuple[str, int], ...] = ()
    bundled_rel: str = ""


MANIFEST: list[ModelEntry] = [
    ModelEntry(
        key="cuda-runtime", role="runtime", title="Библиотеки NVIDIA CUDA",
        rel_path="runtime/cudart-llama-bin-win-cuda-13.4-x64.zip",
        size=423535356,
        sha256="738f8c251ac22b70c3ae6f83a10cf222725df0395246a2cf58f32bdb85fbe668",
        url="https://github.com/ggml-org/llama.cpp/releases/download/b11324/"
            "cudart-llama-bin-win-cuda-13.4-x64.zip",
        revision="b11324",
        unpack_to="runtime/cuda-13.4",
        members=(("cudart64_13.dll", 551024),
                 ("cublas64_13.dll", 54942320),
                 ("cublasLt64_13.dll", 492752496)),
        bundled_rel="llama-server",
    ),
    ModelEntry(
        key="gemma", role="llm", quant="qat-q4_0", group="gemma",
        rel_path="models/llm/gemma-4-12b-it-qat-q4_0.gguf",
        size=6975879296,
        sha256="93567e57a8fe10b23569b9d9ec38cd005deedf71e29477c421a4b83f418a538b",
        repo_id="google/gemma-4-12B-it-qat-q4_0-gguf",
        filename="gemma-4-12b-it-qat-q4_0.gguf",
        revision="29d097773436b69ff9feafd636ab4cf873786537",
        legacy_sizes=(6975877728,),
    ),
    ModelEntry(
        key="gemma-mmproj", role="mmproj", group="gemma",
        rel_path="models/mmproj/mmproj-gemma-4-12b-it-qat-q4_0.gguf",
        size=175115616,
        sha256="cb018338a7538a9814d994bfe54644c71eb7ed54e31eae2f721e45fd3c260da7",
        repo_id="google/gemma-4-12B-it-qat-q4_0-gguf",
        filename="mmproj-gemma-4-12b-it-qat-q4_0.gguf",
        revision="29d097773436b69ff9feafd636ab4cf873786537",
        legacy_sizes=(175115264,),
    ),
    ModelEntry(
        key="embed", role="embed",
        rel_path="models/embed/nomic-embed-text-v1.5.Q4_K_M.gguf",
        size=84106624,
        sha256="d4e388894e09cf3816e8b0896d81d265b55e7a9fff9ab03fe8bf4ef5e11295ac",
        repo_id="nomic-ai/nomic-embed-text-v1.5-GGUF",
        filename="nomic-embed-text-v1.5.Q4_K_M.gguf",
        revision="0188c9bf409793f810680a5a431e7b899c46104c",
    ),
    ModelEntry(
        key="gemma-mtp", role="mtp", group="gemma",
        rel_path="models/llm/mtp-gemma-4-12b-it-Q8_0.gguf",
        size=465109248,
        sha256="145db9094bc0f85f1701e255a2ed216dcc9800fc8bc8631ad00905b456bd451b",
        repo_id="unsloth/gemma-4-12b-it-GGUF",
        filename="MTP/mtp-gemma-4-12b-it-Q8_0.gguf",
        revision="fc034cfff751157913579611efad8462ac1be606",
    ),
    ModelEntry(
        key="gemma-strong", role="llm", quant="UD-Q3_K_XL",
        required=False, group="gemma-strong",
        rel_path="models/llm/gemma-4-31B-it-UD-Q3_K_XL.gguf",
        size=15380222912,
        sha256="73f1de2bde15da19362e5760febc01cd31e4e72f5c29561b7ead63ee2a28c716",
        repo_id="unsloth/gemma-4-31B-it-GGUF",
        filename="gemma-4-31B-it-UD-Q3_K_XL.gguf",
        revision="c1ac76e99d5513b141e8adde7288b85c3f9c32ec",
    ),
    ModelEntry(
        key="gemma-strong-mtp", role="mtp", required=False, group="gemma-strong",
        rel_path="models/llm/mtp-gemma-4-31B-it-Q8_0.gguf",
        size=514687104,
        sha256="5ae8b0117bed601e8924c6305bd5b0585de361d51f0e77091bcb4252cf1f27de",
        repo_id="unsloth/gemma-4-31B-it-GGUF",
        filename="MTP/mtp-gemma-4-31B-it-Q8_0.gguf",
        revision="c1ac76e99d5513b141e8adde7288b85c3f9c32ec",
    ),
    ModelEntry(
        key="gemma-strong-fast", role="llm", quant="UD-IQ3_XXS",
        required=False, group="gemma-strong-fast",
        rel_path="models/llm/gemma-4-31B-it-UD-IQ3_XXS.gguf",
        size=11837782976,
        sha256="beb8b6e69da5d3778d781664d376f94962528c84982e1bf5aa7453d9b2d739b8",
        repo_id="unsloth/gemma-4-31B-it-GGUF",
        filename="gemma-4-31B-it-UD-IQ3_XXS.gguf",
        revision="c1ac76e99d5513b141e8adde7288b85c3f9c32ec",
    ),
    ModelEntry(
        key="gemma-mid", role="llm", quant="UD-IQ4_XS",
        required=False, group="gemma-mid",
        rel_path="models/llm/gemma-4-26B-A4B-it-UD-IQ4_XS.gguf",
        size=13597177568,
        sha256="babd1e389d386352f71600765d37390f7dc993fbfad6725caccf996ffe34aecf",
        repo_id="unsloth/gemma-4-26B-A4B-it-GGUF",
        filename="gemma-4-26B-A4B-it-UD-IQ4_XS.gguf",
        revision="c099eb48e663fd284577b04978a94ffccb261841",
    ),
    ModelEntry(
        key="gemma-mid-mmproj", role="mmproj",
        required=False, group="gemma-mid",
        rel_path="models/mmproj/mmproj-gemma-4-26B-A4B-it-F16.gguf",
        size=1193058784,
        sha256="418a6d8723067cd712235facbbc5cba6c8fbbd413fc1292d2aace5a027d5a42f",
        repo_id="unsloth/gemma-4-26B-A4B-it-GGUF",
        filename="mmproj-F16.gguf",
        revision="c099eb48e663fd284577b04978a94ffccb261841",
    ),
    ModelEntry(
        key="gemma-mid-q4", role="llm", quant="UD-Q4_K_XL",
        required=False, group="gemma-mid-q4",
        rel_path="models/llm/gemma-4-26B-A4B-it-UD-Q4_K_XL.gguf",
        size=17010980576,
        sha256="ef728c8e0c337fd1067b947af006e38a9ef2419e56feced4fd29b4bf0636e30c",
        repo_id="unsloth/gemma-4-26B-A4B-it-GGUF",
        filename="gemma-4-26B-A4B-it-UD-Q4_K_XL.gguf",
        revision="c099eb48e663fd284577b04978a94ffccb261841",
    ),
]

VRAM_Q8_THRESHOLD_GB = 12

WIZARD_PRESETS: list[dict] = [
    {"key": "gemma",
     "hint": "Рекомендуется: быстрая, с анализом картинок и MTP-ускорением."},
    {"key": "gemma-strong-fast",
     "hint": "Умнее 12B и заметно быстрее самой тяжёлой; без анализа картинок."},
    {"key": "gemma-strong",
     "hint": "Самая умная и медленная; если видеопамяти меньше рекомендованного, "
             "часть весов уедет в оперативную память. Без анализа картинок."},
]
DEFAULT_WIZARD_PRESET = "gemma"


def wizard_preset_keys() -> list[str]:
    return [p["key"] for p in WIZARD_PRESETS]


def wizard_presets(project_root: Path, current: str = "") -> list[dict]:
    from config import LLM_MODELS, model_label
    out: list[dict] = []
    for p in WIZARD_PRESETS:
        spec = LLM_MODELS.get(p["key"]) or {}
        files = group_models(p["key"])
        out.append({
            "key": p["key"],
            "label": model_label(p["key"]),
            "hint": p["hint"],
            "size": sum(m.size for m in files),
            "missing_size": sum(m.size for m in files if not is_present(m, project_root)),
            "vision": bool(spec.get("mmproj")),
            "vram_gb": spec.get("vram_gb") or 0,
            "current": p["key"] == current,
        })
    return out


def resolve_wizard_choice(choice: str | None) -> str:
    c = (choice or "").strip().lower()
    return c if c in wizard_preset_keys() else DEFAULT_WIZARD_PRESET


def nominal_vram_gb(total_mb: float) -> int:
    return int(round(total_mb / 1024)) if total_mb else 0


def detect_gpu() -> dict:
    snap = get_vram_info(0)
    return {
        "has_gpu": snap.available,
        "name": snap.name,
        "vram_gb": nominal_vram_gb(snap.total_mb),
    }


def recommended_quant(vram_gb: float) -> str:
    return "Q8_0" if vram_gb >= VRAM_Q8_THRESHOLD_GB else "Q4_K_M"


def _hf_url(entry: ModelEntry) -> str:
    return (f"https://huggingface.co/{entry.repo_id}"
            f"/resolve/{entry.revision}/{entry.filename}")


def required_models(project_root: Path, choice: str | None = None) -> list[ModelEntry]:
    key = resolve_wizard_choice(choice)
    common = [m for m in MANIFEST if m.required and not m.group]
    return common + group_models(key)


def group_models(key: str) -> list[ModelEntry]:
    return [m for m in MANIFEST if m.group == key]


def is_present(entry: ModelEntry, project_root: Path) -> bool:
    if entry.members:
        return (_members_in(project_root / entry.unpack_to, entry, check_size=True)
                or _bundled(entry))
    p = project_root / entry.rel_path
    try:
        return p.exists() and p.stat().st_size in (entry.size, *entry.legacy_sizes)
    except OSError:
        return False


def _members_in(folder: Path, entry: ModelEntry, check_size: bool) -> bool:
    try:
        for name, size in entry.members:
            p = folder / name
            if not p.is_file() or (check_size and p.stat().st_size != size):
                return False
        return True
    except OSError:
        return False


def _bundled(entry: ModelEntry, assets_root: Path | None = None) -> bool:
    if not entry.bundled_rel:
        return False
    root = assets_root if assets_root is not None else ASSETS_ROOT
    return _members_in(root / entry.bundled_rel, entry, check_size=False)


def runtime_entries() -> list[ModelEntry]:
    return [m for m in MANIFEST if m.role == "runtime"]


def runtime_env(project_root: Path, binary_dir: Path) -> dict | None:
    dirs: list[str] = []
    for e in runtime_entries():
        if _members_in(binary_dir, e, check_size=False):
            continue
        folder = project_root / e.unpack_to
        if _members_in(folder, e, check_size=True):
            dirs.append(str(folder))
        else:
            print(f"[setup] {e.title or e.key}: нет ни рядом с llama-server, "
                  f"ни в {folder} — llama-server запустится без видеокарты")
    if not dirs:
        return None
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(dirs + [env.get("PATH", "")])
    return env


def resolve_llm_model(project_root: Path, configured_rel: str) -> str:
    if (project_root / configured_rel).exists():
        return configured_rel
    llms = [m for m in MANIFEST if m.role == "llm" and is_present(m, project_root)]
    llms.sort(key=lambda m: m.size, reverse=True)
    return llms[0].rel_path if llms else configured_rel


@dataclass
class DownloadProgress:
    key: str
    status: str = "pending"
    downloaded: int = 0
    total: int = 0
    error: str = ""


_progress: dict[str, DownloadProgress] = {}
_progress_lock = threading.Lock()
_setup_thread: threading.Thread | None = None


def get_progress() -> list[dict]:
    with _progress_lock:
        return [vars(p) for p in _progress.values()]


def is_downloading() -> bool:
    return _setup_thread is not None and _setup_thread.is_alive()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _download_one(entry: ModelEntry, project_root: Path) -> None:
    prog = _progress[entry.key]
    dest = project_root / entry.rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    url = entry.url or (_hf_url(entry) if entry.repo_id else "")
    if not url:
        prog.status, prog.error = "error", "нет источника (repo_id/url) в MANIFEST"
        return
    existing = part.stat().st_size if part.exists() else 0
    prog.total, prog.downloaded, prog.status = entry.size, existing, "downloading"
    headers = {"Range": f"bytes={existing}-"} if existing else {}
    try:
        with httpx.stream("GET", url, headers=headers, timeout=None,
                          follow_redirects=True) as r:
            r.raise_for_status()
            with open(part, "ab" if existing else "wb") as f:
                for chunk in r.iter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
                    prog.downloaded += len(chunk)
        prog.status = "verifying"
        if _sha256(part) != entry.sha256:
            prog.status, prog.error = "error", "sha256 не совпал (битая загрузка)"
            part.unlink(missing_ok=True)
            return
        if entry.unpack_to:
            prog.status = "extracting"
            try:
                _unpack(entry, part, project_root)
            finally:
                part.unlink(missing_ok=True)
        else:
            part.replace(dest)
        prog.status = "done"
    except Exception as e:
        prog.status, prog.error = "error", f"{type(e).__name__}: {e}"


def _unpack(entry: ModelEntry, archive: Path, project_root: Path) -> None:
    target = project_root / entry.unpack_to
    tmp = target.with_name(target.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        with zipfile.ZipFile(archive) as zf:
            by_name = {Path(i.filename).name.lower(): i
                       for i in zf.infolist() if not i.is_dir()}
            for name, size in entry.members:
                info = by_name.get(name.lower())
                if info is None:
                    raise RuntimeError(f"в архиве нет {name}")
                with zf.open(info) as src, open(tmp / name, "wb") as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
                got = (tmp / name).stat().st_size
                if got != size:
                    raise RuntimeError(f"{name}: {got} байт вместо {size}")
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    shutil.rmtree(target, ignore_errors=True)
    tmp.replace(target)
    family = target.name.split("-", 1)[0] + "-"
    for old in target.parent.iterdir():
        if (old.is_dir() and old != target and old.name.startswith(family)
                and not old.name.endswith(".tmp")):
            shutil.rmtree(old, ignore_errors=True)


def start_downloads(project_root: Path, choice: str | None = None) -> list[str]:
    global _setup_thread
    if is_downloading():
        return [p.key for p in _progress.values() if p.status in ("pending", "downloading")]
    needed = [m for m in required_models(project_root, choice)
              if not is_present(m, project_root)]
    with _progress_lock:
        _progress.clear()
        for m in needed:
            _progress[m.key] = DownloadProgress(key=m.key, total=m.size)

    def _run():
        for m in needed:
            _download_one(m, project_root)

    _setup_thread = threading.Thread(target=_run, daemon=True)
    _setup_thread.start()
    return [m.key for m in needed]


def autostart_runtime(project_root: Path, choice: str | None = None) -> list[str]:
    missing = [m for m in required_models(project_root, choice)
               if not is_present(m, project_root)]
    if not missing or any(m.role != "runtime" for m in missing):
        return []
    return start_downloads(project_root, choice)


def start_group_download(project_root: Path, key: str) -> dict:
    global _setup_thread
    entries = group_models(key)
    if not entries:
        return {"error": f"модель {key!r} не докачивается автоматически"}
    if is_downloading():
        return {"error": "уже идёт другая загрузка — дождись её завершения"}
    needed = [m for m in entries if not is_present(m, project_root)]
    if not needed:
        return {"queued": [], "note": "все файлы уже на месте"}
    with _progress_lock:
        _progress.clear()
        for m in needed:
            _progress[m.key] = DownloadProgress(key=m.key, total=m.size)

    def _run():
        for m in needed:
            _download_one(m, project_root)

    _setup_thread = threading.Thread(target=_run, daemon=True)
    _setup_thread.start()
    return {"queued": [m.key for m in needed]}


def group_download_status(key: str) -> dict | None:
    keys = {m.key for m in group_models(key)}
    if not keys:
        return None
    with _progress_lock:
        rel = [dict(vars(p)) for p in _progress.values() if p.key in keys]
    if not rel:
        return None
    err = next((p["error"] for p in rel if p["status"] == "error"), "")
    active = any(p["status"] in ("pending", "downloading", "verifying") for p in rel)
    if err:
        status = "error"
    elif active and is_downloading():
        status = "downloading"
    elif active:
        status, err = "error", "загрузка прервана — нажми «Скачать» ещё раз"
    else:
        status = "done"
    return {"status": status,
            "downloaded": sum(p["downloaded"] for p in rel),
            "total": sum(p["total"] for p in rel),
            "error": err}


def setup_status(project_root: Path, choice: str | None = None) -> dict:
    gpu = detect_gpu()
    key = resolve_wizard_choice(choice)
    req = required_models(project_root, key)
    quant = next((m.quant for m in req if m.role == "llm"), "")
    models = [{
        "key": m.key, "role": m.role, "quant": m.quant, "title": m.title,
        "filename": Path(m.rel_path).name, "size": m.size,
        "present": is_present(m, project_root), "has_url": bool(m.url or m.repo_id),
    } for m in req]
    missing = [m["key"] for m in models if not m["present"]]
    from services import agreement
    return {
        "needs_setup": bool(missing),
        "agreement_ok": agreement.accepted(project_root),
        "terms_version": agreement.TERMS_VERSION,
        "gpu": gpu,
        "recommended_quant": quant,
        "choice": key,
        "presets": wizard_presets(project_root, key),
        "models": models,
        "missing": missing,
        "downloading": is_downloading(),
        "progress": get_progress(),
    }
