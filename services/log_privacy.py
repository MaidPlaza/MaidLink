from __future__ import annotations

import sys


_IS_FROZEN = bool(getattr(sys, "frozen", False))


def priv(value, limit: int | None = None) -> str:
    if value is None:
        return "‹пусто›"
    text = value if isinstance(value, str) else str(value)
    if not text:
        return "‹пусто›"
    if _IS_FROZEN:
        return f"‹скрыто, {len(text)} симв›"
    if limit and len(text) > limit:
        return text[:limit] + "…"
    return text
