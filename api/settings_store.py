from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SETTINGS_FILENAME = "settings.json"

_MANAGED: dict[str, tuple[str, type]] = {
    "image_gen.enabled": ("image_gen.enabled", bool),
    "image_gen.keep_generated": ("image_gen.keep_generated", bool),
    "drawing.vision_critic_enabled": ("drawing.vision_critic_enabled", bool),
    "drawing.mood_portraits_enabled": ("drawing.mood_portraits_enabled", bool),
    "session.idle_timeout_minutes": ("session.idle_timeout_minutes", int),
    "session.proactive_enabled": ("session.proactive_enabled", bool),
    "image_gen.workflow_default": ("image_gen.workflow_default", str),
    "drawing.max_rating": ("drawing.max_rating", str),
    "llm.model_choice": ("llm.model_choice", str),
    "llm.ctx_overrides": ("llm.ctx_overrides", dict),
    "llm.reasoning_mode": ("llm.reasoning_mode", str),
    "llm.vram_free_mib": ("llm.vram_free_mib", int),
    "llm.preset": ("llm.preset", str),
}


_DEV_ONLY = frozenset({"image_gen.keep_generated"})


def _managed() -> dict[str, tuple[str, type]]:
    import sys
    if getattr(sys, "frozen", False):
        return {k: v for k, v in _MANAGED.items() if k not in _DEV_ONLY}
    return _MANAGED


def _settings_path(project_root: Path) -> Path:
    return project_root / "data" / SETTINGS_FILENAME


def _coerce(typ: type, value: Any) -> Any:
    if typ is bool:
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)
    if typ is int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0
    if typ is dict:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return {}
        if not isinstance(value, dict):
            return {}
        out = {}
        for k, v in value.items():
            try:
                out[str(k)] = int(float(v))
            except (TypeError, ValueError):
                continue
        return out
    return value


def _get_attr(config: Any, path: str) -> Any:
    obj = config
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj


def _set_attr(config: Any, path: str, value: Any) -> None:
    parts = path.split(".")
    obj = config
    for part in parts[:-1]:
        obj = getattr(obj, part)
    setattr(obj, parts[-1], value)


def read_current(config: Any) -> dict[str, Any]:
    return {key: _get_attr(config, cfg_path) for key, (cfg_path, _t) in _managed().items()}


def load_overlay(config: Any, project_root: Path) -> None:
    path = _settings_path(project_root)
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[settings] не удалось прочитать {path}: {e}")
        return
    if not isinstance(data, dict):
        return
    if "llm.fast_mode" in data and "llm.reasoning_mode" not in data:
        config.llm.reasoning_mode = "fast" if _coerce(bool, data["llm.fast_mode"]) else "deep"
    managed = _managed()
    for key, raw in data.items():
        spec = managed.get(key)
        if spec is None:
            continue
        cfg_path, typ = spec
        _set_attr(config, cfg_path, _coerce(typ, raw))


def apply_and_save(config: Any, patch: dict, project_root: Path) -> dict[str, Any]:
    managed = _managed()
    for key, raw in (patch or {}).items():
        spec = managed.get(key)
        if spec is None:
            continue
        cfg_path, typ = spec
        _set_attr(config, cfg_path, _coerce(typ, raw))
    current = read_current(config)
    path = _settings_path(project_root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as e:
        print(f"[settings] не удалось сохранить {path}: {e}")
    return current
