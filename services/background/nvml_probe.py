from __future__ import annotations

import threading
from dataclasses import dataclass


_nvml_lock = threading.Lock()
_nvml_initialized = False
_nvml_available = False


def _try_init() -> bool:
    global _nvml_initialized, _nvml_available
    with _nvml_lock:
        if _nvml_initialized:
            return _nvml_available
        try:
            import pynvml
            pynvml.nvmlInit()
            _nvml_available = True
        except Exception as e:
            print(f"[nvml] init failed: {e!r} — analyzer will always STOP")
            _nvml_available = False
        _nvml_initialized = True
        return _nvml_available


def shutdown() -> None:
    global _nvml_initialized, _nvml_available
    with _nvml_lock:
        if not _nvml_initialized or not _nvml_available:
            return
        try:
            import pynvml
            pynvml.nvmlShutdown()
        except Exception:
            pass
        _nvml_initialized = False
        _nvml_available = False


@dataclass(frozen=True)
class VramSnapshot:
    available: bool
    gpu_index: int
    free_mb: int
    used_mb: int
    total_mb: int
    name: str

    @property
    def free_pct(self) -> float:
        if self.total_mb <= 0:
            return 0.0
        return self.free_mb / self.total_mb * 100.0


_UNAVAILABLE = VramSnapshot(
    available=False,
    gpu_index=-1,
    free_mb=0,
    used_mb=0,
    total_mb=0,
    name="(no GPU)",
)


def get_vram_info(gpu_index: int = 0) -> VramSnapshot:
    if not _try_init():
        return _UNAVAILABLE
    try:
        import pynvml
        with _nvml_lock:
            handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_index)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            raw_name = pynvml.nvmlDeviceGetName(handle)
            name = raw_name.decode() if isinstance(raw_name, bytes) else raw_name
        return VramSnapshot(
            available=True,
            gpu_index=gpu_index,
            free_mb=int(info.free // 1024 // 1024),
            used_mb=int(info.used // 1024 // 1024),
            total_mb=int(info.total // 1024 // 1024),
            name=name,
        )
    except Exception as e:
        print(f"[nvml] query failed (gpu_index={gpu_index}): {e!r}")
        return _UNAVAILABLE
