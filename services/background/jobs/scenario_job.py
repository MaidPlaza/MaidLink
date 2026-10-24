from __future__ import annotations

import asyncio
import time

from services.background.jobs.base import BackgroundJob, JobContext, JobResult


class ScenarioJob(BackgroundJob):
    name = "proactive_scenarios"
    requires_llm = False
    min_interval_sec = 30 * 60
    estimated_duration_sec = 15.0
    status_label = "AWAY"
    status_priority = 1
    status_reason = "пишет по своей инициативе"

    def should_run(self, ctx: JobContext) -> bool:
        age = time.time() - ctx.last_run_at
        if age < self.min_interval_sec:
            return False

        state = ctx.state
        if state.get("active_ws") is None:
            return False
        if state.get("identity") is None:
            return False
        hist = state.get("history")
        if hist is not None and getattr(hist, "messages", None):
            return False
        if state.get("session_processing"):
            return False

        try:
            import api.server as server
            if server._reflection_pending_for(state):
                return False
            return server._select_proactive_scenario(state, peek_only=True) is not None
        except Exception as e:
            print(f"[job:{self.name}] should_run peek error: {e!r}")
            return False

    async def run(self, ctx: JobContext) -> JobResult:
        import api.server as server

        state = ctx.state
        ws = state.get("active_ws")
        if ws is None:
            return JobResult.skipped(reason="ws disappeared")
        hist = state.get("history")
        if hist is not None and getattr(hist, "messages", None):
            return JobResult.skipped(reason="session became active")
        if server._reflection_pending_for(state):
            return JobResult.skipped(reason="reflection pending — не лезем до неё")
        if ctx.should_abort():
            return JobResult.aborted("analyzer stop before dispatch")

        sc = server._select_proactive_scenario(state, peek_only=False)
        if sc is None:
            return JobResult.skipped(reason="no proactive scenario fired (chance miss)")

        ctx.log(f"firing proactive scenario {sc.id!r} (action={sc.action or 'text'})")
        loop = asyncio.get_event_loop()
        try:
            if getattr(sc, "action", "") == "decision":
                delivered = await server._dispatch_proactive_decision(
                    state, ws, loop, hook=(sc.params or {}).get("hook"))
            else:
                delivered = await server._dispatch_proactive_scenario(state, ws, loop, sc)
        except Exception as e:
            return JobResult.failed(f"dispatch {sc.id}: {type(e).__name__}: {e}")

        if not delivered:
            return JobResult.skipped(reason=f"{sc.id} not delivered (gen/ws/skip)")

        try:
            server._stats_bump(state, "proactive_sent")
        except Exception:
            pass
        return JobResult.ok(scenario_id=sc.id, action=sc.action or "text")
