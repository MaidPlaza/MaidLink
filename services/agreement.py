from __future__ import annotations

import json
import time
from pathlib import Path

TERMS_VERSION = "2026-10-24"
AGREEMENT_FILE = "agreement.json"


def _path(project_root: Path) -> Path:
    return Path(project_root) / "data" / AGREEMENT_FILE


def accepted(project_root: Path) -> bool:
    try:
        rec = json.loads(_path(project_root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return (isinstance(rec, dict) and rec.get("version") == TERMS_VERSION
            and rec.get("adult") is True)


def accept(project_root: Path) -> dict:
    p = _path(project_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {"version": TERMS_VERSION, "adult": True, "accepted_at": time.time()}
    tmp = p.with_name(p.name + ".part")
    tmp.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)
    return rec
