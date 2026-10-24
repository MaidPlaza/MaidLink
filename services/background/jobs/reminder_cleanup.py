from __future__ import annotations

import time
from typing import Any

from services.background.jobs.base import (
    BackgroundJob,
    JobContext,
    JobResult,
)


HISTORY_RETENTION_SEC = 24 * 3600


class ReminderHistoryCleanupJob(BackgroundJob):
    name = "reminder_history_cleanup"
    requires_llm = False
    session_safe = True
    min_interval_sec = 6 * 3600
    estimated_duration_sec = 1.0

    def __init__(self, retention_sec: float = HISTORY_RETENTION_SEC):
        self.retention_sec = retention_sec

    async def run(self, ctx: JobContext) -> JobResult:
        memory = ctx.state.get("memory")
        if memory is None or not getattr(memory, "records", None):
            return JobResult.skipped(reason="no memory or empty records")

        now = time.time()
        cutoff = now - self.retention_sec

        keep: list[Any] = []
        removed_acknowledged = 0
        removed_expired = 0

        for r in memory.records:
            if getattr(r, "type", "") != "напоминание":
                keep.append(r)
                continue

            if r.details.get("acknowledged", False):
                ack_at = r.details.get("acknowledged_at", 0)
                if isinstance(ack_at, (int, float)) and ack_at > 0 and ack_at < cutoff:
                    removed_acknowledged += 1
                    continue

            if r.details.get("expired", False):
                exp_at = r.details.get("expired_at", 0)
                if isinstance(exp_at, (int, float)) and exp_at > 0 and exp_at < cutoff:
                    removed_expired += 1
                    continue

            if r.details.get("delivered", False) and not r.details.get("acknowledged"):
                created_at = getattr(r, "created_at", 0)
                if isinstance(created_at, (int, float)) and created_at > 0 and created_at < cutoff:
                    removed_acknowledged += 1
                    continue

            keep.append(r)

        total_removed = removed_acknowledged + removed_expired
        if total_removed == 0:
            return JobResult.skipped(reason="no old reminders to clean")

        if ctx.should_abort():
            return JobResult.aborted("analyzer signaled stop mid-cleanup")

        memory.records = keep
        try:
            ctx.save_memory()
        except Exception as e:
            ctx.log(f"WARN save_memory failed (records pruned in-memory): {e}")

        ctx.log(
            f"removed {total_removed} reminder(s): "
            f"{removed_acknowledged} acknowledged, {removed_expired} expired"
        )
        return JobResult.ok(
            removed=total_removed,
            removed_acknowledged=removed_acknowledged,
            removed_expired=removed_expired,
            remaining=len(keep),
        )
