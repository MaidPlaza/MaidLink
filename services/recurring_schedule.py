from __future__ import annotations

import time
from datetime import datetime, timedelta

GRACE_SEC = 3 * 3600

MAX_ACTIVE_RECURRING = 5

_RU_DAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


def parse_schedule(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    freq = str(raw.get("freq") or "").strip().lower()
    t = str(raw.get("time") or "").strip()
    try:
        hh, mm = t.split(":")
        hh, mm = int(hh), int(mm)
        if not (0 <= hh < 24 and 0 <= mm < 60):
            return None
    except (ValueError, AttributeError):
        return None
    tt = f"{hh:02d}:{mm:02d}"
    if freq == "daily":
        return {"freq": "daily", "time": tt}
    if freq == "weekly":
        days = raw.get("days")
        if not isinstance(days, list):
            return None
        norm = sorted({int(d) for d in days if isinstance(d, (int, float))
                       and 0 <= int(d) <= 6})
        if not norm:
            return None
        return {"freq": "weekly", "time": tt, "days": norm}
    return None


def next_fire_at(schedule: dict, after: datetime) -> datetime:
    hh, mm = (int(x) for x in schedule["time"].split(":"))
    candidate = after.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if schedule["freq"] == "daily":
        if candidate <= after:
            candidate += timedelta(days=1)
        return candidate
    days = set(schedule["days"])
    for shift in range(0, 8):
        c = candidate + timedelta(days=shift)
        if c.weekday() in days and c > after:
            return c
    return candidate + timedelta(days=7)


def describe_schedule(schedule: dict) -> str:
    if schedule["freq"] == "daily":
        return f"каждый день в {schedule['time']}"
    days = ", ".join(_RU_DAYS[d] for d in schedule["days"])
    return f"по {days} в {schedule['time']}"


def reschedule_record(record, now_ts: float | None = None) -> float:
    now_ts = now_ts or time.time()
    d = record.details
    nxt = next_fire_at(d["schedule"], datetime.fromtimestamp(now_ts))
    d["fire_at"] = nxt.timestamp()
    d["fire_at_iso"] = nxt.strftime("%Y-%m-%d %H:%M")
    d["message_text"] = ""
    d["message_sent"] = False
    d["message_failed"] = False
    d["card_shown"] = False
    return d["fire_at"]


def mark_delivered(record, now_ts: float | None = None) -> None:
    now_ts = now_ts or time.time()
    d = record.details
    d["delivered_count"] = int(d.get("delivered_count", 0)) + 1
    d["last_delivered_at"] = now_ts
    reschedule_record(record, now_ts)


def is_overdue(record, now_ts: float | None = None) -> bool:
    now_ts = now_ts or time.time()
    fire_at = float(record.details.get("fire_at") or 0.0)
    return fire_at > 0 and (now_ts - fire_at) > GRACE_SEC


def active_recurring(memory) -> list:
    out = []
    for r in getattr(memory, "records", []):
        if getattr(r, "type", "") != "напоминание":
            continue
        d = r.details or {}
        if d.get("kind") != "recurring":
            continue
        if d.get("expired") or d.get("cancelled") or d.get("acknowledged"):
            continue
        out.append(r)
    return out
