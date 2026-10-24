from __future__ import annotations

from services.background.jobs.base import BackgroundJob, JobContext, JobResult


class OutfitPrepareJob(BackgroundJob):
    name = "outfit_prepare"
    min_interval_sec = 0.0
    requires_llm = False
    estimated_duration_sec = 90.0
    status_label = "SEWING"
    status_priority = 2
    status_reason = "готовит наряд (рендер портретов)"

    def should_run(self, ctx: JobContext) -> bool:
        try:
            from api.server import _get_wardrobe
            w = _get_wardrobe(ctx.state)
            return (w is not None and w.head() is not None
                    and not ctx.state.get("wardrobe_preparing"))
        except Exception:
            return False

    async def run(self, ctx: JobContext) -> JobResult:
        from api.server import prepare_outfit_background_step
        try:
            res = await prepare_outfit_background_step(
                ctx.state, ctx.should_abort, ctx.log)
        except Exception as e:
            return JobResult.failed(f"{type(e).__name__}: {e}")
        status = res.pop("status", "skipped")
        if status == "aborted":
            return JobResult.aborted("пользователь вернулся")
        if status == "skipped":
            return JobResult.skipped(res.pop("reason", ""), **res)
        return JobResult.ok(step_status=status, **res)
