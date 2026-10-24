from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memory.unified import UnifiedMemory


_PROFILE_LOCATION_PATTERNS = [
    re.compile(r"^место\s+жительства", re.IGNORECASE),
    re.compile(r"^адрес(\s+господина|\s+хозяина|\s+хозяин)?$", re.IGNORECASE),
    re.compile(r"^где\s+(я|господин|хозяин)\s+жив", re.IGNORECASE),
    re.compile(r"^город\s+(господина|хозяина|пользователя)$", re.IGNORECASE),
]


def _extract_location_from_details(details: dict) -> dict | None:
    if not isinstance(details, dict):
        return None
    out: dict = {}
    for key in ("city", "город", "адрес", "address"):
        val = details.get(key)
        if isinstance(val, str) and val.strip():
            out["city"] = val.strip()
            break
    for key in ("country", "страна"):
        val = details.get(key)
        if isinstance(val, str) and val.strip():
            out["country"] = val.strip()
            break
    for key in ("lat", "latitude", "широта"):
        val = details.get(key)
        if val is not None:
            try:
                out["lat"] = float(val)
                break
            except (TypeError, ValueError):
                continue
    for key in ("lon", "longitude", "долгота"):
        val = details.get(key)
        if val is not None:
            try:
                out["lon"] = float(val)
                break
            except (TypeError, ValueError):
                continue
    return out or None


def migrate_location_records_into_profile(memory: "UnifiedMemory") -> int:
    migrated = 0
    for r in list(memory.records):
        if r.is_forgotten:
            continue
        if not any(p.search(r.title or "") for p in _PROFILE_LOCATION_PATTERNS):
            continue
        loc = _extract_location_from_details(r.details)
        if not loc:
            continue
        current = memory.get_user_profile().get("location") or {}
        if isinstance(current, dict):
            merged = {**loc, **current} if current.get("city") else {**current, **loc}
        else:
            merged = loc
        memory.update_user_profile("location", merged)
        r.details["_migrated_to"] = "profile.location"
        r.details["_migrated_at"] = time.time()
        r.importance = 0.0
        migrated += 1
    return migrated


def run_all(memory: "UnifiedMemory") -> dict:
    counters = {
        "location_records_into_profile": migrate_location_records_into_profile(memory),
    }
    if sum(counters.values()) > 0:
        memory.save()
    return counters
