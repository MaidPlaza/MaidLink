from __future__ import annotations

import threading
import time
from typing import Literal, Optional

AppComputeState = Literal[
    "ACTIVE_CHAT",
    "FOREGROUND",
    "IDLE_FOREGROUND",
    "BACKGROUND",
]

STALE_AFTER_SEC = 90.0


class StateMirror:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: Optional[AppComputeState] = None
        self._updated_at: float = 0.0
        self._state_since: float = 0.0

    def set(self, state: AppComputeState) -> None:
        if state not in ("ACTIVE_CHAT", "FOREGROUND", "IDLE_FOREGROUND", "BACKGROUND"):
            print(f"[state_mirror] ignored unknown state: {state!r}")
            return
        with self._lock:
            now = time.time()
            if self._state != state:
                self._state_since = now
            self._state = state
            self._updated_at = now

    def get_current(self) -> Optional[AppComputeState]:
        with self._lock:
            if self._state is None:
                return None
            if self.is_stale():
                return None
            return self._state

    def is_stale(self) -> bool:
        if self._updated_at <= 0.0:
            return True
        return (time.time() - self._updated_at) > STALE_AFTER_SEC

    def time_in_state(self) -> Optional[float]:
        with self._lock:
            if self._state_since <= 0.0:
                return None
            return time.time() - self._state_since

    def get_diagnostic(self) -> dict:
        with self._lock:
            now = time.time()
            return {
                "state": self._state,
                "updated_at": self._updated_at,
                "state_since": self._state_since,
                "age_sec": (now - self._updated_at) if self._updated_at > 0 else None,
                "time_in_state_sec": (now - self._state_since) if self._state_since > 0 else None,
                "is_stale": self.is_stale(),
            }


app_state_mirror = StateMirror()
