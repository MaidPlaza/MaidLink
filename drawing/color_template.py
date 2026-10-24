from __future__ import annotations

import re

_PLACEHOLDER_RE = re.compile(r"\{c(\d+)(?::([^}]*))?\}")

SAMPLE_PALETTE: tuple[str, ...] = ("white", "black", "grey")


def has_placeholders(text: str) -> bool:
    return bool(text) and "{c" in text


def apply(text: str, colors) -> str:
    if not has_placeholders(text):
        return text
    cols = [str(c).strip() for c in (colors or [])]

    def _sub(m: "re.Match[str]") -> str:
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(cols) and cols[idx]:
            return cols[idx]
        return (m.group(2) or "").strip()

    out = _PLACEHOLDER_RE.sub(_sub, text)
    parts = [p.strip() for p in out.split(",")]
    return ", ".join(p for p in parts if p)
