from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from services.background.analyzer import (
    AnalyzerConfig,
    Decision,
    DecisionVerdict,
    analyzer_tick,
)
from services.background.busy import busy_with, session_engaged
from services.background.jobs.base import (
    BackgroundJob,
    JobContext,
    JobResult,
    JobStatus,
)
from services.background.model_lifecycle import ModelLifecycle


@dataclass
class JobRunRecord:
    last_run_at: float = 0.0
    last_status: str = ""
    last_details: dict = field(default_factory=dict)
    last_error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "last_run_at": self.last_run_at,
            "last_status": self.last_status,
            "last_details": self.last_details,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "JobRunRecord":
        return cls(
            last_run_at=d.get("last_run_at", 0.0),
            last_status=d.get("last_status", ""),
            last_details=d.get("last_details", {}),
            last_error=d.get("last_error"),
        )


@dataclass
class JobRunsState:
    path: Path
    records: dict[str, JobRunRecord] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "JobRunsState":
        state = cls(path=path)
        if not path.exists():
            return state
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            state.records = {
                name: JobRunRecord.from_dict(rec)
                for name, rec in data.items()
                if isinstance(rec, dict)
            }
        except Exception as e:
            print(f"[runner] WARN: failed to load {path}: {e!r}; starting empty")
        return state

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        data = {name: rec.to_dict() for name, rec in self.records.items()}
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def get(self, name: str) -> JobRunRecord:
        if name not in self.records:
            self.records[name] = JobRunRecord()
        return self.records[name]


@dataclass(frozen=True)
class JobRunnerConfig:
    tick_sec: float = 30.0
    state_path: Path = Path("data/job_runs.json")


class JobRunner:
    def __init__(
        self,
        lifecycle: ModelLifecycle,
        config: JobRunnerConfig = JobRunnerConfig(),
        analyzer_config: AnalyzerConfig = AnalyzerConfig(),
    ) -> None:
        self._lifecycle = lifecycle
        self._config = config
        self._analyzer_config = analyzer_config
        self._jobs: list[BackgroundJob] = []
        self._state: Optional[JobRunsState] = None
        self._current_decision: Optional[Decision] = None
        self._engaged_logged: Optional[bool] = None

    def register(self, job: BackgroundJob) -> None:
        for existing in self._jobs:
            if existing.name == job.name:
                raise ValueError(
                    f"Job with name {job.name!r} already registered"
                )
        self._jobs.append(job)
        print(f"[runner] registered job: {job.name} "
              f"(interval={job.min_interval_sec}s, llm={job.requires_llm})")

    def _last_run_at(self, job: BackgroundJob) -> float:
        if not self._state:
            return 0.0
        rec = self._state.get(job.name)
        return rec.last_run_at

    def _make_ctx_for_should_run(self, job: BackgroundJob, state: dict) -> JobContext:
        return JobContext(
            state=state,
            save_memory=lambda: None,
            should_abort=lambda: False,
            log=lambda _msg: None,
            last_run_at=self._last_run_at(job),
        )

    def _pick_job(self, state: dict,
                  engaged: bool = False) -> Optional[BackgroundJob]:
        for job in self._jobs:
            if engaged and not job.session_safe:
                continue
            ctx = self._make_ctx_for_should_run(job, state)
            try:
                if job.should_run(ctx):
                    return job
            except Exception as e:
                print(f"[runner] should_run({job.name}) raised: {e!r}; skipping")
                continue
        return None

    async def _execute_job(
        self,
        job: BackgroundJob,
        ctx: JobContext,
    ) -> JobResult:
        from services.background.persona_status import persona_status

        persona_status.set_busy(
            actor=f"job:{job.name}",
            label=job.status_label,
            reason=job.status_reason or job.name,
            priority=job.status_priority,
        )
        try:
            if job.requires_llm:
                async with self._lifecycle.using():
                    return await job.run(ctx)
            else:
                return await job.run(ctx)
        except Exception as e:
            return JobResult.failed(f"{type(e).__name__}: {e}")
        finally:
            persona_status.set_idle(f"job:{job.name}")

    def _make_should_abort(self, job: Optional[BackgroundJob] = None,
                           state: Optional[dict] = None) -> Callable[[], bool]:
        def should_abort() -> bool:
            if (job is not None and state is not None
                    and not job.session_safe and session_engaged(state)):
                return True
            decision = analyzer_tick(self._analyzer_config,
                                     llm_loaded=bool(self._lifecycle and self._lifecycle.is_loaded))
            self._current_decision = decision
            return decision.verdict is DecisionVerdict.STOP
        return should_abort

    async def run_loop(
        self,
        state_provider: Callable[[], Optional[dict]],
        save_memory: Callable[[], None],
    ) -> None:
        self._state = JobRunsState.load(self._config.state_path)
        registered = ", ".join(j.name for j in self._jobs) or "(none)"
        print(f"[runner] loop started (tick={self._config.tick_sec}s, "
              f"jobs=[{registered}], state_file={self._config.state_path})")

        while True:
            try:
                await asyncio.sleep(self._config.tick_sec)
            except asyncio.CancelledError:
                print("[runner] loop cancelled")
                return

            try:
                await self._tick(state_provider, save_memory)
            except Exception as e:
                print(f"[runner] tick error: {e!r}")

    async def _tick(
        self,
        state_provider: Callable[[], Optional[dict]],
        save_memory: Callable[[], None],
    ) -> None:
        state = state_provider()
        if state is None:
            return

        if busy_with(state) is not None:
            return

        decision = analyzer_tick(self._analyzer_config,
                                 llm_loaded=bool(self._lifecycle and self._lifecycle.is_loaded))
        self._current_decision = decision
        if decision.verdict is DecisionVerdict.STOP:
            return

        engaged = session_engaged(state)
        if engaged != self._engaged_logged:
            self._engaged_logged = engaged
            print("[runner] живая сессия — тяжёлые job-ы ждут её конца"
                  if engaged else "[runner] сессия завершена — фоновые job-ы разрешены")

        job = self._pick_job(state, engaged)
        if job is None:
            return

        prefix = f"[job:{job.name}]"
        def _log(msg: str) -> None:
            print(f"{prefix} {msg}")

        ctx = JobContext(
            state=state,
            save_memory=save_memory,
            should_abort=self._make_should_abort(job, state),
            log=_log,
            last_run_at=self._last_run_at(job),
        )

        _log(f"start (decision={decision.short()})")
        t0 = time.time()
        state["background_job_running"] = job.name
        try:
            result = await self._execute_job(job, ctx)
        finally:
            state["background_job_running"] = None
        elapsed = time.time() - t0

        rec = self._state.get(job.name)
        rec.last_status = result.status.value
        rec.last_details = result.details
        rec.last_error = result.error

        if result.status is JobStatus.ABORTED:
            _log(f"ABORTED after {elapsed:.1f}s (won't update last_run_at)")
        else:
            rec.last_run_at = time.time()
            if result.status is JobStatus.FAILED:
                _log(f"FAILED after {elapsed:.1f}s: {result.error}")
            elif result.status is JobStatus.SKIPPED:
                _log(f"skipped after {elapsed:.1f}s ({result.details.get('reason', '')})")
            else:
                _log(f"OK after {elapsed:.1f}s ({result.details})")

        try:
            self._state.save()
        except Exception as e:
            print(f"[runner] WARN: failed to persist {self._config.state_path}: {e!r}")
