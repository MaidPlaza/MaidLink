from __future__ import annotations

import time
from datetime import datetime, timedelta

ENABLED = False

MIN_GAP_SEC = 6 * 3600
COOLDOWN_SEC = 16 * 3600
REOFFER_AFTER_SEC = 30 * 86400

_DEFAULT_INCLUDE = {"weather": True, "plans": True, "reminders": True,
                    "promises": True}


def brief_state(identity) -> dict:
    raw = (getattr(identity, "assistant_prefs", None) or {}).get(
        "morning_brief") or {}
    include = dict(_DEFAULT_INCLUDE)
    include.update({k: bool(v) for k, v in (raw.get("include") or {}).items()
                    if k in _DEFAULT_INCLUDE})
    return {
        "enabled": bool(raw.get("enabled", False)),
        "offered_at": float(raw.get("offered_at", 0.0) or 0.0),
        "last_brief_at": float(raw.get("last_brief_at", 0.0) or 0.0),
        "include": include,
    }


def set_brief(identity, *, enabled: bool | None = None,
              include_patch: dict | None = None,
              offered_at: float | None = None,
              last_brief_at: float | None = None) -> dict:
    st = brief_state(identity)
    if enabled is not None:
        st["enabled"] = bool(enabled)
    if include_patch:
        for k, v in include_patch.items():
            if k in _DEFAULT_INCLUDE and v is not None:
                st["include"][k] = bool(v)
    if offered_at is not None:
        st["offered_at"] = float(offered_at)
    if last_brief_at is not None:
        st["last_brief_at"] = float(last_brief_at)
    prefs = dict(getattr(identity, "assistant_prefs", None) or {})
    prefs["morning_brief"] = st
    identity.assistant_prefs = prefs
    try:
        identity.save()
    except Exception as e:
        print(f"[brief] identity.save fail: {type(e).__name__}: {e}")
    return st


def silence_gap_sec(state: dict, now: float | None = None) -> float:
    now = now or time.time()
    idy = state.get("identity")
    marks = [float(state.get("last_user_message_at") or 0.0),
             float(getattr(idy, "last_evolution", 0.0) or 0.0)]
    last = max(marks)
    return (now - last) if last > 0 else float("inf")


def should_brief(state: dict, now: float | None = None) -> bool:
    if not ENABLED:
        return False
    now = now or time.time()
    idy = state.get("identity")
    if idy is None or state.get("character") is None:
        return False
    st = brief_state(idy)
    if not st["enabled"]:
        return False
    if now - st["last_brief_at"] < COOLDOWN_SEC:
        return False
    if silence_gap_sec(state, now) < MIN_GAP_SEC:
        return False
    hist = state.get("history")
    if hist is not None and getattr(hist, "messages", None):
        return False
    return True


def should_offer(state: dict, now: float | None = None) -> bool:
    if not ENABLED:
        return False
    now = now or time.time()
    idy = state.get("identity")
    if idy is None or state.get("character") is None:
        return False
    st = brief_state(idy)
    if st["enabled"]:
        return False
    if st["offered_at"] and now - st["offered_at"] < REOFFER_AFTER_SEC:
        return False
    if is_first_meeting(idy):
        return True
    return silence_gap_sec(state, now) >= MIN_GAP_SEC


def is_first_meeting(identity) -> bool:
    return float(getattr(identity, "last_evolution", 0.0) or 0.0) <= 0


def offered_at_for(identity, now: float | None = None) -> float:
    now = now or time.time()
    if is_first_meeting(identity):
        return now - (REOFFER_AFTER_SEC - 7 * 86400)
    return now


OFFER_HINT = (
    "Ты давно не встречала {honorific}а в начале его дня. Если в разговоре "
    "будет уместно — МОЖЕШЬ разово предложить ему свою услугу: короткая "
    "сводка дня при его первом появлении (планы, напоминания, погода). "
    "Предложи СВОИМИ словами, не настаивай. Согласится — вызови "
    "configure_brief(enabled=true). Откажется или промолчит — просто прими, "
    "больше не поднимай."
)

OFFER_HINT_FIRST = (
    "Вы только знакомитесь. Среди прочего ты умеешь встречать {honorific}а "
    "короткой сводкой дня (планы, напоминания, погода) при его первом "
    "появлении. НЕ предлагай это в первых репликах — дай знакомству "
    "состояться; упомяни СВОИМИ словами позже и только если разговор сам "
    "зайдёт о том, чем ты можешь быть полезна. Не было повода — не предлагай "
    "вовсе. Согласится — вызови configure_brief(enabled=true)."
)


def _fmt_hhmm(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%H:%M")
    except Exception:
        return ""


def collect_brief_lines(state: dict, now: float | None = None) -> list[str]:
    now = now or time.time()
    mem = state.get("memory")
    if mem is None:
        return []
    idy_include = brief_state(state["identity"])["include"]
    lines: list[str] = []
    today = datetime.fromtimestamp(now).date()

    if idy_include["reminders"]:
        for r in getattr(mem, "records", []):
            if r.type != "напоминание" or r.is_forgotten:
                continue
            d = r.details or {}
            if d.get("acknowledged") or d.get("expired"):
                continue
            fire_at = float(d.get("fire_at") or 0.0)
            if not (now - 3600 <= fire_at <= now + 24 * 3600):
                continue
            when = _fmt_hhmm(float(d.get("event_at") or 0.0) or fire_at)
            lines.append(f"напоминание на {when}: "
                         f"{d.get('description') or r.title}")

    if idy_include["plans"]:
        for r in getattr(mem, "records", []):
            if r.type != "событие_план" or r.is_forgotten:
                continue
            d = r.details or {}
            if str(d.get("status") or "ожидает") not in ("ожидает", "", "planned"):
                continue
            due_raw = str(d.get("due_date") or "").strip()
            if not due_raw:
                continue
            due = None
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
                try:
                    due = datetime.strptime(due_raw[:len(fmt) + 2], fmt).date()
                    break
                except ValueError:
                    continue
            if due is None:
                continue
            if due < today:
                lines.append(f"просроченный план ({due_raw}): {r.title}")
            elif due <= today + timedelta(days=1):
                mark = "сегодня" if due == today else "завтра"
                lines.append(f"план на {mark}: {r.title}")

    if idy_include["promises"]:
        try:
            from memory.loops import LOOP_SUBJ_MINE
            loops = [lp for lp in mem.get_open_loops()
                     if (lp.details or {}).get("subject") != LOOP_SUBJ_MINE]
            for lp in loops[:2]:
                lines.append(f"он держит в голове: {lp.title}")
        except Exception:
            pass

    return lines


def fetch_weather_line(state: dict) -> str:
    if not brief_state(state["identity"])["include"]["weather"]:
        return ""
    try:
        from tools.weather_handlers import handle_get_weather
        ctx = state["memory"]._build_tool_context()
        out = handle_get_weather({"when": "сегодня"}, ctx) or ""
        out = out.strip()
        if not out or "set_location" in out or "не знаю" in out.lower():
            return ""
        return out if len(out) < 220 else out[:217] + "…"
    except Exception as e:
        print(f"[brief] weather fail: {type(e).__name__}: {e}")
        return ""


def mark_briefed(identity, now: float | None = None) -> None:
    set_brief(identity, last_brief_at=(now or time.time()))
