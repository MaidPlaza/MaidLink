from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from services.background.nvml_probe import VramSnapshot, get_vram_info
from services.background.state_mirror import (
    AppComputeState,
    StateMirror,
    app_state_mirror,
)


@dataclass(frozen=True)
class AnalyzerConfig:
    gpu_index: int = 0

    min_free_for_go_mb: int = 300

    min_free_for_continue_mb: int = 150

    tick_interval_sec: float = 10.0

    state_stale_sec: float = 90.0


class DecisionVerdict(Enum):
    GO = "GO"
    STOP = "STOP"


@dataclass(frozen=True)
class Decision:
    verdict: DecisionVerdict
    reason: str
    state: Optional[AppComputeState]
    vram: VramSnapshot

    @property
    def is_go(self) -> bool:
        return self.verdict is DecisionVerdict.GO

    @classmethod
    def stop(cls, reason: str, state: Optional[AppComputeState], vram: VramSnapshot) -> "Decision":
        return cls(DecisionVerdict.STOP, reason, state, vram)

    @classmethod
    def go(cls, reason: str, state: Optional[AppComputeState], vram: VramSnapshot) -> "Decision":
        return cls(DecisionVerdict.GO, reason, state, vram)

    def short(self) -> str:
        verdict_str = "GO  " if self.is_go else "STOP"
        state_str = self.state or "??"
        if self.vram.available:
            vram_str = f"free={self.vram.free_mb}/{self.vram.total_mb} MB"
        else:
            vram_str = "vram=N/A"
        return f"{verdict_str} (state={state_str}  {vram_str}  reason={self.reason})"


_GO_STATES: frozenset[AppComputeState] = frozenset({"IDLE_FOREGROUND", "BACKGROUND"})


def analyzer_tick(
    config: AnalyzerConfig = AnalyzerConfig(),
    mirror: StateMirror = app_state_mirror,
    llm_loaded: bool | None = None,
) -> Decision:
    state = mirror.get_current()
    vram = get_vram_info(config.gpu_index)

    if state is None:
        return Decision.stop(
            "state-unknown (electron silent or stale)", state, vram,
        )

    if state not in _GO_STATES:
        return Decision.stop(f"user-active ({state})", state, vram)

    if not vram.available:
        return Decision.stop("vram-unavailable (no NVML)", state, vram)

    if vram.free_mb < config.min_free_for_go_mb:
        if llm_loaded:
            return Decision.go(
                f"window={state}, vram-tight waived: llm resident "
                f"({vram.free_mb} MB free)", state, vram)
        return Decision.stop(
            f"vram-tight ({vram.free_mb} MB < {config.min_free_for_go_mb} MB)",
            state, vram,
        )

    return Decision.go(f"window={state}", state, vram)


async def analyzer_loop(
    config: AnalyzerConfig = AnalyzerConfig(),
    mirror: StateMirror = app_state_mirror,
) -> None:
    print(f"[analyzer] loop started (tick={config.tick_interval_sec}s, "
          f"min_free_go={config.min_free_for_go_mb} MB, "
          f"gpu={config.gpu_index})")

    last_verdict: Optional[DecisionVerdict] = None
    last_reason: Optional[str] = None

    while True:
        try:
            await asyncio.sleep(config.tick_interval_sec)
        except asyncio.CancelledError:
            print("[analyzer] loop cancelled")
            return

        decision = analyzer_tick(config, mirror)

        verdict_changed = decision.verdict is not last_verdict
        reason_changed = decision.reason != last_reason
        if verdict_changed or reason_changed:
            print(f"[analyzer] {decision.short()}")
            last_verdict = decision.verdict
            last_reason = decision.reason
