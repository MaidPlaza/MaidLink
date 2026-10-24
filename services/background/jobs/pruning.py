from __future__ import annotations

import time

from services.background.jobs.base import (
    BackgroundJob,
    JobContext,
    JobResult,
)


DEFAULT_AGE_BUFFER_DAYS = 30


class MemoryPruneJob(BackgroundJob):
    name = "memory_prune"
    min_interval_sec = 6 * 3600
    requires_llm = False
    session_safe = True
    estimated_duration_sec = 2.0

    def __init__(self, age_buffer_days: int = DEFAULT_AGE_BUFFER_DAYS):
        self.age_buffer_days = age_buffer_days

    async def run(self, ctx: JobContext) -> JobResult:
        memory = ctx.state.get("memory")
        if memory is None or not getattr(memory, "records", None):
            return JobResult.skipped(reason="no memory or empty records")

        cutoff_time = time.time() - self.age_buffer_days * 86400
        records = memory.records

        keep = []
        pruned_count = 0
        pruned_by_type: dict[str, int] = {}

        for r in records:
            last_touch = max(r.created_at or 0.0, r.last_accessed or 0.0)
            if r.is_forgotten and last_touch and last_touch < cutoff_time:
                pruned_count += 1
                pruned_by_type[r.type] = pruned_by_type.get(r.type, 0) + 1
                continue
            keep.append(r)

        if ctx.should_abort():
            return JobResult.aborted("analyzer signaled stop mid-prune")

        if pruned_count == 0:
            ctx.log(f"nothing to prune (records={len(records)})")
            return JobResult.skipped(
                reason="no eligible forgotten records",
                records_total=len(records),
            )

        memory.records = keep
        try:
            ctx.save_memory()
        except Exception as e:
            ctx.log(f"WARN: save_memory failed (records still pruned in-memory): {e}")

        ctx.log(
            f"pruned {pruned_count} records "
            f"({len(records)} -> {len(keep)}); by type: {pruned_by_type}"
        )
        return JobResult.ok(
            pruned=pruned_count,
            remaining=len(keep),
            by_type=pruned_by_type,
        )
