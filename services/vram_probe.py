from __future__ import annotations

import subprocess
import sys


_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def gpu_snapshot() -> dict | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.used,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        )
        if out.returncode != 0:
            return None
        total, used, free = (int(x.strip())
                             for x in out.stdout.splitlines()[0].split(","))
        return {"total_mb": total, "used_mb": used, "free_mb": free}
    except Exception:
        return None


def process_gpu_mem(pid: int) -> dict | None:
    if sys.platform != "win32":
        return None
    script = (
        "$d=(Get-Counter '\\GPU Process Memory(pid_{pid}_*)\\Dedicated Usage'"
        " -ErrorAction Stop).CounterSamples |"
        " Measure-Object CookedValue -Sum;"
        "$s=(Get-Counter '\\GPU Process Memory(pid_{pid}_*)\\Shared Usage'"
        " -ErrorAction Stop).CounterSamples |"
        " Measure-Object CookedValue -Sum;"
        "Write-Output ([math]::Round($d.Sum/1MB));"
        "Write-Output ([math]::Round($s.Sum/1MB))"
    ).format(pid=int(pid))
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
        lines = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
        if out.returncode != 0 or len(lines) < 2:
            return None
        return {"dedicated_mb": int(float(lines[-2])),
                "shared_mb": int(float(lines[-1]))}
    except Exception:
        return None


def slow_turn_verdict(pid: int | None, gen_tps: float,
                      expected_tps: float) -> str:
    parts = [f"gen {gen_tps:.1f} t/s vs expected ~{expected_tps:.0f}"]
    snap = gpu_snapshot()
    if snap:
        parts.append(f"vram free {snap['free_mb']} of {snap['total_mb']} MiB")
    proc = process_gpu_mem(pid) if pid else None
    if proc:
        parts.append(f"llama-server dedicated {proc['dedicated_mb']} MiB, "
                     f"shared {proc['shared_mb']} MiB")
        if proc["shared_mb"] > 512:
            parts.append("VERDICT: SPILL - model buffers pushed to system RAM "
                         "(VRAM taken by another app); model restart re-fits "
                         "layers to current free VRAM")
        elif proc["shared_mb"] > 128:
            parts.append("VERDICT: partial spill - borderline VRAM pressure")
        else:
            parts.append("VERDICT: no spill - slowdown is NOT vram "
                         "(thermal/CPU load/long context?)")
    else:
        parts.append("per-process counters unavailable")
    return "[vram] slow turn: " + "; ".join(parts)
