from __future__ import annotations

import asyncio
import time
from typing import Callable, Optional

from services.background.state_mirror import app_state_mirror


_NOTIFY_STATES: frozenset[str] = frozenset({"IDLE_FOREGROUND", "BACKGROUND"})

ONE_SHOT_TTL_SEC: float = 10 * 60
PRE_EVENT_REFIRE_SEC: float = 10 * 60


async def reminder_notify_loop(
    state_provider: Callable[[], Optional[dict]],
    save_memory: Callable[[], None],
    tick_sec: float = 60.0,
) -> None:
    print(f"[reminder-notify] loop started (tick={tick_sec}s, "
          f"one_shot_ttl={ONE_SHOT_TTL_SEC}s, "
          f"pre_event_refire={PRE_EVENT_REFIRE_SEC}s)")
    while True:
        try:
            await asyncio.sleep(tick_sec)
        except asyncio.CancelledError:
            print("[reminder-notify] loop cancelled")
            return
        try:
            await _tick(state_provider, save_memory)
        except Exception as e:
            print(f"[reminder-notify] tick error: {e!r}")


async def _tick(
    state_provider: Callable[[], Optional[dict]],
    save_memory: Callable[[], None],
) -> None:
    s = state_provider()
    if s is None:
        return

    memory = s.get("memory")
    character = s.get("character")
    if memory is None or character is None:
        return

    cur_state = app_state_mirror.get_current()
    can_notify_state = cur_state in _NOTIFY_STATES
    ws = s.get("active_ws")
    can_notify = can_notify_state and ws is not None

    now = time.time()
    char_name = getattr(character, "name", "MaidLink")

    notifications_sent = 0
    expired_count = 0
    save_needed = False

    for record in getattr(memory, "records", []):
        if getattr(record, "type", "") != "напоминание":
            continue
        if record.details.get("acknowledged", False):
            continue
        if record.details.get("expired", False):
            continue
        if record.details.get("delivered", False):
            continue

        fire_at = record.details.get("fire_at", 0)
        if not isinstance(fire_at, (int, float)) or fire_at <= 0:
            continue
        if fire_at > now:
            continue

        kind = record.details.get("kind", "one_shot")

        if kind == "one_shot":
            if now - fire_at >= ONE_SHOT_TTL_SEC:
                record.details["expired"] = True
                record.details["expired_at"] = now
                expired_count += 1
                save_needed = True
                continue
        elif kind == "pre_event":
            event_at = record.details.get("event_at", 0)
            if isinstance(event_at, (int, float)) and event_at > 0 and now >= event_at:
                record.details["expired"] = True
                record.details["expired_at"] = now
                expired_count += 1
                save_needed = True
                continue

        hist = s.get("history")
        in_active_session = (cur_state in ("ACTIVE_CHAT", "FOREGROUND")
                             and ws is not None
                             and hist is not None
                             and bool(getattr(hist, "messages", None)))
        if in_active_session and kind != "timer":
            import api.server as _srv
            description = record.details.get("description") or record.title
            if kind == "recurring":
                from services.recurring_schedule import (describe_schedule,
                                                         is_overdue,
                                                         mark_delivered,
                                                         reschedule_record)
                if is_overdue(record):
                    reschedule_record(record)
                    save_needed = True
                    continue
                mark_delivered(record)
                save_needed = True
                trig = (f"(Служебное: время твоего регулярного напоминания — "
                        f"«{description}» ({describe_schedule(record.details['schedule'])}). "
                        f"Напомни об этом СВОИМИ словами прямо в текущем "
                        f"разговоре, коротко и к месту — без «уведомления».)")
                ev = {"kind": "recurring", "trigger": trig, "card": None}
            else:
                record.details["card_shown"] = True
                record.details["card_shown_at"] = now
                record.details["message_sent"] = True
                save_needed = True
                card = {"type": "reminder_card", "record_id": record.record_id,
                        "kind": kind, "title": description}
                if kind == "pre_event" and record.details.get("event_at_iso"):
                    card["event_at_iso"] = record.details["event_at_iso"]
                trig = (f"(Служебное: только что сработало твоё напоминание — "
                        f"«{description}». Панельку он уже видит. Скажи об этом "
                        f"в текущем разговоре коротко и естественно, в своём "
                        f"тоне — не «системным уведомлением».)")
                ev = {"kind": kind, "trigger": trig, "card": card}
            s["last_reminder_delivered_at"] = now
            try:
                await _srv._interject_event(s, ws, ev)
            except Exception as e:
                print(f"[reminder-notify] interject fail: {type(e).__name__}: {e}")
            continue

        if kind == "recurring":
            continue
        if not can_notify:
            continue

        notification_count = record.details.get("notification_count", 0)
        last_notification_at = record.details.get("last_notification_at", 0.0)

        send_now = False
        if notification_count == 0:
            send_now = True
        elif kind == "pre_event":
            if now - last_notification_at >= PRE_EVENT_REFIRE_SEC:
                send_now = True

        if not send_now:
            continue

        description = record.details.get("description") or record.title
        try:
            await ws.send_json({
                "type": "notification",
                "title": f"{char_name}: напоминание",
                "body": description,
            })
        except Exception as e:
            print(f"[reminder-notify] send failed for [{record.record_id}]: {e!r}")
            break

        record.details["notification_shown"] = True
        record.details["last_notification_at"] = now
        record.details["notification_count"] = notification_count + 1
        notifications_sent += 1
        save_needed = True

        s["last_reminder_delivered_at"] = now

    if save_needed:
        try:
            save_memory()
        except Exception as e:
            print(f"[reminder-notify] save_memory failed: {e!r}")

    if notifications_sent > 0 or expired_count > 0:
        print(
            f"[reminder-notify] tick: {notifications_sent} sent, "
            f"{expired_count} expired"
        )
