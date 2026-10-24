from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class JobStatus(Enum):
    OK = "ok"
    SKIPPED = "skipped"
    ABORTED = "aborted"
    FAILED = "failed"


@dataclass
class JobResult:
    status: JobStatus
    details: dict = field(default_factory=dict)
    error: Optional[str] = None

    @classmethod
    def ok(cls, **details: Any) -> "JobResult":
        return cls(status=JobStatus.OK, details=dict(details))

    @classmethod
    def skipped(cls, reason: str = "", **details: Any) -> "JobResult":
        d = dict(details)
        if reason:
            d["reason"] = reason
        return cls(status=JobStatus.SKIPPED, details=d)

    @classmethod
    def aborted(cls, reason: str = "") -> "JobResult":
        return cls(status=JobStatus.ABORTED, details={"reason": reason} if reason else {})

    @classmethod
    def failed(cls, error: str) -> "JobResult":
        return cls(status=JobStatus.FAILED, error=error)


@dataclass
class JobContext:
    state: dict
    save_memory: Callable[[], None]
    should_abort: Callable[[], bool]
    log: Callable[[str], None]
    last_run_at: float = 0.0


class BackgroundJob(ABC):
    name: str = "abstract_job"

    min_interval_sec: float = 24 * 3600

    requires_llm: bool = False

    estimated_duration_sec: float = 30.0

    status_label: str = "AWAY"
    status_priority: int = 1
    status_reason: str = ""

    session_safe: bool = False

    def should_run(self, ctx: JobContext) -> bool:
        age = time.time() - ctx.last_run_at
        return age >= self.min_interval_sec

    @abstractmethod
    async def run(self, ctx: JobContext) -> JobResult:
        raise NotImplementedError
