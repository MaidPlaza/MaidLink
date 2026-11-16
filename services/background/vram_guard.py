from __future__ import annotations

import asyncio
import time
from typing import Callable, Optional

from services.background.nvml_probe import VramSnapshot, get_vram_info

TICK_SEC = 10.0
LOW_FREE_MB = 512
SPILL_MB = 256
CRIT_FREE_MB = 150
COUNTERS_EVERY_SEC = 30.0
UNLOAD_SETTLE_SEC = 3.0
DEFICIT_SHARE = 0.15
DEFICIT_MIN_MB = 512
WAIT_LOG_EVERY_SEC = 300.0


def is_spill(shared_mb: int, baseline_shared_mb: int) -> bool:
    return shared_mb - baseline_shared_mb >= SPILL_MB


def allowed_deficit_mb(share_mb: int) -> int:
    return max(DEFICIT_MIN_MB, int(share_mb * DEFICIT_SHARE))


def resume_need_mb(ref: dict) -> int:
    return max(0, int(ref["full_free_mb"]) - allowed_deficit_mb(int(ref["share_mb"])))


def reference(state: dict, baseline_free_mb: int, free_before_mb: int,
              free_after_mb: int) -> dict:
    share = max(0, free_after_mb - free_before_mb)
    ref = {"full_free_mb": baseline_free_mb + share, "share_mb": share}
    old = state.get("vram_ref")
    if old and int(old.get("full_free_mb") or 0) >= ref["full_free_mb"]:
        return old
    state["vram_ref"] = ref
    return ref


def _process_shared_mb(pid: int) -> Optional[int]:
    from services.vram_probe import process_gpu_mem
    mem = process_gpu_mem(pid)
    return None if mem is None else int(mem["shared_mb"])


class VramGuard:
    def __init__(self, lifecycle, state: dict, *,
                 probe: Callable[[], VramSnapshot] = get_vram_info,
                 shared_mb: Callable[[int], Optional[int]] = _process_shared_mb,
                 sleep=asyncio.sleep, tick_sec: float = TICK_SEC) -> None:
        self._lc = lifecycle
        self._state = state
        self._probe = probe
        self._shared_of = shared_mb
        self._sleep = sleep
        self._tick = tick_sec
        self.baseline_free: Optional[int] = None
        self.baseline_shared: Optional[int] = None
        self._counters_at = 0.0
        self._crit_streak = 0

    async def watch(self) -> None:
        while True:
            await self._sleep(self._tick)
            if not self._lc.is_loaded:
                continue
            snap = self._probe()
            if not snap.available:
                continue
            reason = await self._check(snap.free_mb)
            if reason:
                await self._pause(reason, snap.free_mb)
                return

    async def _check(self, free_mb: int) -> Optional[str]:
        if self.baseline_free is None:
            self.baseline_free = free_mb
            self.baseline_shared = await self._shared()
            return None
        if free_mb >= LOW_FREE_MB:
            self._crit_streak = 0
            self.baseline_free = max(self.baseline_free, free_mb)
            return None
        self._crit_streak = self._crit_streak + 1 if free_mb < CRIT_FREE_MB else 0
        if self.baseline_shared is None:
            if self._crit_streak >= 2:
                return f"видеопамять кончилась: свободно {free_mb} МиБ"
            return None
        if time.monotonic() - self._counters_at < COUNTERS_EVERY_SEC:
            return None
        shared = await self._shared()
        if shared is not None and is_spill(shared, self.baseline_shared):
            return (f"спилл: {shared - self.baseline_shared} МиБ буферов модели "
                    f"вытеснено в ОЗУ, свободно {free_mb} МиБ")
        return None

    async def _shared(self) -> Optional[int]:
        pid = self._lc.server_pid
        if not pid:
            return None
        self._counters_at = time.monotonic()
        return await asyncio.get_running_loop().run_in_executor(None, self._shared_of, pid)

    async def _pause(self, reason: str, free_before: int) -> None:
        print(f"[vram-guard] {reason} — рефлексия на паузу, модель выгружается")
        self._state["vram_pause"] = reason
        await self._lc.request_unload(f"vram guard: {reason}", force=True)
        await self._sleep(UNLOAD_SETTLE_SEC)
        after = self._probe()
        free_after = after.free_mb if after.available else free_before
        ref = reference(self._state, self.baseline_free or 0, free_before, free_after)
        need = resume_need_mb(ref)
        if free_after >= need:
            short = max(0, int(ref["full_free_mb"]) - free_after)
            print(f"[vram-guard] модель выгружена, свободно {free_after} МиБ — не хватает "
                  f"~{short} МиБ, в пределах допуска: рефлексия продолжит сразу, "
                  f"часть слоёв уйдёт в ОЗУ")
            return
        self._state["vram_wait"] = {"need_free_mb": need, "since": time.time(),
                                    "reason": reason, "logged_at": time.time()}
        print(f"[vram-guard] модель выгружена, свободно {free_after} МиБ; рефлексия "
              f"продолжит, когда свободных станет {need} МиБ")


async def wait_over(state: dict, lifecycle,
                    probe: Callable[[], VramSnapshot] = get_vram_info) -> bool:
    wait = state.get("vram_wait")
    if not wait:
        return True
    if lifecycle.is_loaded:
        if lifecycle.consumer_count == 0:
            await lifecycle.request_unload("рефлексия ждёт видеопамять")
        return False
    if lifecycle.state.name != "UNLOADED":
        return False
    snap = probe()
    if not snap.available:
        return False
    need = int(wait.get("need_free_mb") or 0)
    if snap.free_mb < need:
        now = time.time()
        if now - float(wait.get("logged_at") or 0) >= WAIT_LOG_EVERY_SEC:
            wait["logged_at"] = now
            print(f"[vram-guard] рефлексия ждёт видеопамять: свободно {snap.free_mb} "
                  f"из нужных {need} МиБ")
        return False
    state.pop("vram_wait", None)
    print(f"[vram-guard] видеопамять освободилась ({snap.free_mb} МиБ, ждали "
          f"{time.time() - float(wait.get('since') or time.time()):.0f} с) — рефлексия продолжает")
    return True
