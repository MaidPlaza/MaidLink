from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, Optional

from llm.server_manager import LlamaServerManager
from services.background.state_mirror import (
    AppComputeState,
    StateMirror,
    app_state_mirror,
)


class ModelState(Enum):
    UNLOADED = "UNLOADED"
    LOADING = "LOADING"
    LOADED = "LOADED"
    UNLOADING = "UNLOADING"


@dataclass(frozen=True)
class IdleThresholds:
    foreground_unloaded_after: float = 999_999.0
    idle_foreground_unloaded_after: float = 10 * 60.0
    background_unloaded_after: float = 1 * 60.0


StateChangeCallback = Callable[[ModelState], None]


class ModelLifecycle:
    def __init__(
        self,
        llama_mgr: LlamaServerManager,
        thresholds: IdleThresholds = IdleThresholds(),
        mirror: StateMirror = app_state_mirror,
    ) -> None:
        self._llama_mgr = llama_mgr
        self._thresholds = thresholds
        self._mirror = mirror

        self._op_lock = asyncio.Lock()

        self._state: ModelState = ModelState.UNLOADED

        self._counter: int = 0
        self._counter_zero = asyncio.Event()
        self._counter_zero.set()

        self._loaded_at: Optional[float] = None
        self._idle_since: Optional[float] = None

        self._listeners: list[StateChangeCallback] = []

    @property
    def state(self) -> ModelState:
        return self._state

    @property
    def is_loaded(self) -> bool:
        return self._state is ModelState.LOADED

    @property
    def consumer_count(self) -> int:
        return self._counter

    def add_listener(self, callback: StateChangeCallback) -> Callable[[], None]:
        self._listeners.append(callback)
        return lambda: self._listeners.remove(callback) if callback in self._listeners else None

    async def ensure_loaded(self) -> None:
        if self._state is ModelState.LOADED and not self._server_crashed():
            return

        async with self._op_lock:
            if self._state is ModelState.LOADED:
                if not self._server_crashed():
                    return
                print(f"[lifecycle] llama-server упал сам: "
                      f"{self._llama_mgr.take_crash_report()} — поднимаю заново")
                self._set_state(ModelState.UNLOADED)

            self._set_state(ModelState.LOADING)
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._llama_mgr.start)
                self._loaded_at = time.time()
                self._idle_since = (
                    time.time() if self._counter == 0 else None
                )
                self._set_state(ModelState.LOADED)
            except Exception as e:
                print(f"[lifecycle] start failed: {e!r}")
                self._set_state(ModelState.UNLOADED)
                raise

    def preload(self) -> None:
        if self._state is not ModelState.UNLOADED:
            return
        loop = asyncio.get_event_loop()
        loop.create_task(self._preload_task())

    async def _preload_task(self) -> None:
        try:
            await self.ensure_loaded()
        except Exception as e:
            print(f"[lifecycle] preload failed: {e!r}")

    async def request_unload(self, reason: str = "manual") -> bool:
        if self._state is not ModelState.LOADED:
            return False
        if self._counter > 0:
            return False

        async with self._op_lock:
            if self._state is not ModelState.LOADED:
                return False
            if self._counter > 0:
                return False

            print(f"[lifecycle] unload triggered: {reason}")
            self._set_state(ModelState.UNLOADING)
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._llama_mgr.stop)
                self._loaded_at = None
                self._idle_since = None
                self._set_state(ModelState.UNLOADED)
                return True
            except Exception as e:
                print(f"[lifecycle] unload failed: {e!r}")
                self._set_state(ModelState.LOADED)
                return False

    def use(self) -> "_UseContext":
        return _UseContext(self)

    def using(self) -> "_UsingContext":
        return _UsingContext(self)

    def acquire(self) -> None:
        self._inc_counter()

    def release(self) -> None:
        self._dec_counter()

    def _server_crashed(self) -> bool:
        exit_code = getattr(self._llama_mgr, "exit_code", None)
        return exit_code is not None and exit_code() is not None

    def _set_state(self, new_state: ModelState) -> None:
        if self._state is new_state:
            return
        prev = self._state
        self._state = new_state
        print(f"[lifecycle] {prev.value} -> {new_state.value}")
        for cb in list(self._listeners):
            try:
                cb(new_state)
            except Exception as e:
                print(f"[lifecycle] listener error: {e!r}")

    def _inc_counter(self) -> None:
        self._counter += 1
        self._counter_zero.clear()
        self._idle_since = None

    def _dec_counter(self) -> None:
        self._counter = max(0, self._counter - 1)
        if self._counter == 0:
            self._counter_zero.set()
            self._idle_since = time.time()

    def _idle_timeout_for_state(self, app_state: Optional[AppComputeState]) -> Optional[float]:
        if app_state == "ACTIVE_CHAT":
            return None
        if app_state == "FOREGROUND":
            return self._thresholds.foreground_unloaded_after
        if app_state == "IDLE_FOREGROUND":
            return self._thresholds.idle_foreground_unloaded_after
        if app_state == "BACKGROUND":
            return self._thresholds.background_unloaded_after
        return None

    async def _maybe_unload(self) -> None:
        if self._state is not ModelState.LOADED:
            return
        if self._counter > 0:
            return
        if self._idle_since is None:
            return

        app_state = self._mirror.get_current()
        timeout = self._idle_timeout_for_state(app_state)
        if timeout is None:
            return

        idle_for = time.time() - self._idle_since
        if idle_for >= timeout:
            await self.request_unload(
                reason=f"idle {idle_for:.0f}s in {app_state}, threshold {timeout:.0f}s"
            )


class _UseContext:
    def __init__(self, lifecycle: ModelLifecycle) -> None:
        self._lifecycle = lifecycle

    async def __aenter__(self) -> ModelLifecycle:
        self._lifecycle._inc_counter()
        return self._lifecycle

    async def __aexit__(self, *exc_info) -> None:
        self._lifecycle._dec_counter()


class _UsingContext:
    def __init__(self, lifecycle: ModelLifecycle) -> None:
        self._lifecycle = lifecycle

    async def __aenter__(self) -> ModelLifecycle:
        await self._lifecycle.ensure_loaded()
        self._lifecycle._inc_counter()
        return self._lifecycle

    async def __aexit__(self, *exc_info) -> None:
        self._lifecycle._dec_counter()


async def idle_driver(
    lifecycle: ModelLifecycle,
    tick_sec: float = 15.0,
) -> None:
    print(f"[lifecycle] idle_driver started (tick={tick_sec}s, "
          f"thresholds={lifecycle._thresholds})")
    while True:
        try:
            await asyncio.sleep(tick_sec)
        except asyncio.CancelledError:
            print("[lifecycle] idle_driver cancelled")
            return
        try:
            await lifecycle._maybe_unload()
        except Exception as e:
            print(f"[lifecycle] idle_driver error: {e!r}")


_model_lifecycle: Optional[ModelLifecycle] = None


def set_global(instance: ModelLifecycle) -> None:
    global _model_lifecycle
    _model_lifecycle = instance


def get_global() -> ModelLifecycle:
    if _model_lifecycle is None:
        raise RuntimeError(
            "model_lifecycle not initialized — set_global() not called "
            "from FastAPI lifespan?"
        )
    return _model_lifecycle
