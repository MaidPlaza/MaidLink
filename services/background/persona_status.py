from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Optional


LABEL_AWAY = "AWAY"
LABEL_SLEEPING = "SLEEPING"

PRIORITY_AWAY = 1
PRIORITY_SLEEPING = 2


@dataclass(frozen=True)
class Claim:
    actor: str
    label: str
    reason: str
    priority: int


StatusChangeCallback = Callable[[Optional[Claim]], None]


class PersonaStatus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._claims: dict[str, Claim] = {}
        self._listeners: list[StatusChangeCallback] = []
        self._last_broadcast_key: Optional[tuple] = None

    def set_busy(
        self,
        actor: str,
        label: str = LABEL_AWAY,
        reason: str = "",
        priority: int = PRIORITY_AWAY,
    ) -> None:
        with self._lock:
            claim = Claim(
                actor=actor, label=label,
                reason=reason or actor, priority=priority,
            )
            self._claims[actor] = claim
        self._maybe_broadcast()

    def set_idle(self, actor: str) -> None:
        with self._lock:
            self._claims.pop(actor, None)
        self._maybe_broadcast()

    def get_current(self) -> Optional[Claim]:
        with self._lock:
            if not self._claims:
                return None
            return max(
                self._claims.values(),
                key=lambda c: (c.priority, c.actor),
            )

    def get_diagnostic(self) -> dict:
        with self._lock:
            current = (
                max(self._claims.values(), key=lambda c: (c.priority, c.actor))
                if self._claims else None
            )
            return {
                "current": {
                    "actor": current.actor, "label": current.label,
                    "reason": current.reason, "priority": current.priority,
                } if current else None,
                "active_claims": [
                    {"actor": c.actor, "label": c.label, "reason": c.reason,
                     "priority": c.priority}
                    for c in self._claims.values()
                ],
            }

    def add_listener(self, callback: StatusChangeCallback) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(callback)

        def unsubscribe() -> None:
            with self._lock:
                if callback in self._listeners:
                    self._listeners.remove(callback)
        return unsubscribe

    def _maybe_broadcast(self) -> None:
        current = self.get_current()
        key = (current.actor, current.label, current.reason, current.priority) if current else None
        with self._lock:
            if key == self._last_broadcast_key:
                return
            self._last_broadcast_key = key
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(current)
            except Exception as e:
                print(f"[persona_status] listener error: {e!r}")


persona_status = PersonaStatus()
