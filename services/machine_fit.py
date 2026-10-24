from __future__ import annotations

import ctypes
import os
import sys
import time
from pathlib import Path

GPU_OTHER_MIB = 1536
COMPUTE_OVERHEAD_MIB = 1024
SWA_FIXED_MIB = 350
RAM_OS_RESERVE_MIB = 8192
GPU_MIN_BUDGET_MIB = 2048
POOR_SPILL_SHARE = 0.4
KV_KIB_DEFAULT = 16

_GPU_CACHE_SEC = 20.0
_gpu_cache: tuple[float, dict] | None = None


def ram_total_mib() -> int:
    try:
        if sys.platform == "win32":
            class _MemStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            st = _MemStatus()
            st.dwLength = ctypes.sizeof(_MemStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return int(st.ullTotalPhys // (1024 * 1024))
            return 0
        pages = os.sysconf("SC_PHYS_PAGES")
        page = os.sysconf("SC_PAGE_SIZE")
        return int(pages * page // (1024 * 1024))
    except Exception:
        return 0


def gpu_info() -> dict:
    global _gpu_cache
    now = time.monotonic()
    if _gpu_cache is not None and now - _gpu_cache[0] < _GPU_CACHE_SEC:
        return dict(_gpu_cache[1])
    try:
        from services.background.nvml_probe import get_vram_info
        snap = get_vram_info(0)
        info = {"available": bool(snap.available), "name": snap.name,
                "total_mib": int(snap.total_mb), "free_mib": int(snap.free_mb)}
    except Exception:
        info = {"available": False, "name": "(no GPU)", "total_mib": 0, "free_mib": 0}
    _gpu_cache = (now, info)
    return dict(info)


def _file_mib(project_root: Path, rel: str) -> int:
    if not rel:
        return 0
    try:
        p = project_root / rel
        if p.exists():
            return int(p.stat().st_size // (1024 * 1024))
    except OSError:
        pass
    try:
        from services.setup import MANIFEST
        for m in MANIFEST:
            if m.rel_path == rel:
                return int(m.size // (1024 * 1024))
    except Exception:
        pass
    return 0


def weights_mib(spec: dict, project_root: Path) -> int:
    return sum(_file_mib(project_root, spec.get(k, "") or "")
               for k in ("model", "mmproj", "mtp"))


def kv_mib(spec: dict, ctx: int) -> int:
    kib = float(spec.get("kv_kib_per_token") or KV_KIB_DEFAULT)
    extra = spec.get("extra_args") or []
    if "q8_0" in extra:
        kib *= 0.5
    fixed = SWA_FIXED_MIB if spec.get("family", "gemma") == "gemma" else 0
    return int(ctx * kib / 1024) + fixed


def estimate_need_mib(spec: dict, ctx: int, project_root: Path) -> dict:
    w = weights_mib(spec, project_root)
    k = kv_mib(spec, ctx)
    return {"weights_mib": w, "kv_mib": k, "overhead_mib": COMPUTE_OVERHEAD_MIB,
            "need_mib": w + k + COMPUTE_OVERHEAD_MIB}


def fit_verdict(need_mib: int, gpu: dict, ram_mib: int, free_after_mib: int) -> dict:
    total = int(gpu.get("total_mib") or 0)
    if not gpu.get("available") or total <= 0:
        return {"fit": "none", "note": "Нужна видеокарта NVIDIA", "spill_mib": 0}
    budget = total - int(free_after_mib or 0) - GPU_OTHER_MIB
    if need_mib <= budget:
        return {"fit": "full", "note": "Целиком в видеопамяти", "spill_mib": 0}
    spill = need_mib - max(budget, 0)
    ram_budget = ram_mib - RAM_OS_RESERVE_MIB if ram_mib > 0 else None
    if budget < GPU_MIN_BUDGET_MIB or (ram_budget is not None and spill > ram_budget):
        return {"fit": "none", "note": "Не хватит памяти", "spill_mib": spill}
    gb = spill / 1024
    if spill > need_mib * POOR_SPILL_SHARE:
        return {"fit": "poor", "spill_mib": spill,
                "note": f"Большая часть (~{gb:.0f} ГБ) в оперативной памяти — очень медленно"}
    return {"fit": "partial", "spill_mib": spill,
            "note": f"Часть (~{gb:.1f} ГБ) в оперативной памяти — медленнее"}


def machine_info() -> dict:
    g = gpu_info()
    return {"gpu": g.get("name", ""), "gpu_available": bool(g.get("available")),
            "vram_mib": int(g.get("total_mib") or 0),
            "vram_free_mib": int(g.get("free_mib") or 0),
            "ram_mib": ram_total_mib()}
