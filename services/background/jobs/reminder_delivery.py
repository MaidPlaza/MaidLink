from __future__ import annotations

import asyncio
import time
from typing import Any

from services.background.jobs.base import (
    BackgroundJob,
    JobContext,
    JobResult,
)


from prompts.reflection import (
    DELIVERY_USER_PROMPT,
    RECURRING_DELIVERY_USER_PROMPT,
    RECURRING_FIRST_INFERRED_NOTE,
)


def _fallback_message(description: str, gender: str = "female") -> str:
    verb = "Хотел" if (gender or "female").lower() == "male" else "Хотела"
    return f"{verb} вам напомнить: {description}"


class ReminderDeliveryJob(BackgroundJob):
    name = "reminder_delivery"
    requires_llm = True
    session_safe = True
    min_interval_sec = 60
    estimated_duration_sec = 10.0
    status_label = "AWAY"
    status_priority = 1
    status_reason = "отвечает на напоминание"

    def should_run(self, ctx: JobContext) -> bool:
        age = time.time() - ctx.last_run_at
        if age < self.min_interval_sec:
            return False

        state = ctx.state
        if state.get("active_ws") is None:
            return False

        return self._find_ready_reminder(ctx) is not None

    async def run(self, ctx: JobContext) -> JobResult:
        state = ctx.state
        memory = state.get("memory")
        character = state.get("character")
        identity = state.get("identity")
        client = state.get("client")
        ws = state.get("active_ws")

        if not all([memory, character, client, ws]):
            return JobResult.skipped(reason="state incomplete")

        record = self._find_ready_reminder(ctx)
        if record is None:
            return JobResult.skipped(reason="no ready reminder (race?)")
        if state.get("active_ws") is None:
            return JobResult.skipped(reason="ws disappeared")

        if ctx.should_abort():
            return JobResult.aborted("analyzer stop before delivery")

        description = record.details.get("description") or record.title
        fire_at_iso = record.details.get("fire_at_iso", "(время не указано)")
        kind = record.details.get("kind", "one_shot")
        event_at_iso = record.details.get("event_at_iso") if kind == "pre_event" else None

        if kind == "recurring":
            from services.recurring_schedule import is_overdue, reschedule_record
            if is_overdue(record):
                new_fire = reschedule_record(record)
                try:
                    ctx.save_memory()
                except Exception:
                    pass
                ctx.log(f"recurring [{record.record_id}] пропущено (вне grace-окна) "
                        f"→ перенос на {record.details.get('fire_at_iso')}")
                return JobResult.ok(record_id=record.record_id, kind=kind,
                                    skipped_overdue=True, next_fire_at=new_fire)

        sent_llm_message = False
        message_text = record.details.get("message_text", "").strip()
        message_sent = record.details.get("message_sent", False)
        message_failed = record.details.get("message_failed", False)

        if not message_sent and not message_failed:
            from persona.prompt_builder import build_system_prompt
            from persona.prompt_context import ContextSpec
            _hist = state.get("history")
            system_prompt = build_system_prompt(
                state.get("persona"),
                spec=ContextSpec.reminder(),
                memory=memory,
                dialogue=_hist.get_messages() if _hist else None,
            )
            self_a = "" if (character.gender or "female").lower() == "male" else "а"
            if kind == "recurring":
                from services.recurring_schedule import describe_schedule
                first_inferred = (
                    record.details.get("source") == "inferred"
                    and int(record.details.get("delivered_count", 0)) == 0)
                user_prompt = RECURRING_DELIVERY_USER_PROMPT.format(
                    description=description,
                    schedule_human=describe_schedule(
                        record.details.get("schedule") or
                        {"freq": "daily", "time": "12:00"}),
                    first_inferred_note=(RECURRING_FIRST_INFERRED_NOTE
                                         if first_inferred else ""),
                )
            else:
                user_prompt = DELIVERY_USER_PROMPT.format(
                    description=description,
                    fire_at_iso=fire_at_iso,
                    self_a=self_a,
                )

            loop = asyncio.get_event_loop()
            ctx.log(f"generating message for [{record.record_id}]: {description[:60]}")
            try:
                response = await loop.run_in_executor(
                    None,
                    lambda: client.chat(
                        messages=[{"role": "user", "content": user_prompt}],
                        system=system_prompt,
                        thinking=False,
                        label=f"Reminder delivery [{record.record_id}]",
                    ),
                )
                import re
                message_text = (response or "").strip()
                message_text = re.sub(r"[一-鿿㐀-䶿　-〿]+", "", message_text).strip()
                if not message_text or len(message_text) < 5:
                    ctx.log("WARN: пустой/короткий ответ модели — помечаем как failed")
                    record.details["message_failed"] = True
                    message_failed = True
                else:
                    record.details["message_text"] = message_text
                    record.details["message_generated_at"] = time.time()
            except Exception as e:
                ctx.log(f"LLM call failed: {type(e).__name__}: {e} — помечаем failed")
                record.details["message_failed"] = True
                message_failed = True
            try:
                ctx.save_memory()
            except Exception:
                pass

        if message_text and not message_sent:
            ws = state.get("active_ws")
            if ws is None:
                return JobResult.skipped(reason="ws disappeared mid-flow")
            try:
                await ws.send_json({
                    "type": "response",
                    "text": message_text,
                })
                history = state.get("history")
                if history is not None:
                    history.add("assistant", message_text)
                record.details["message_sent"] = True
                sent_llm_message = True
                try:
                    ctx.save_memory()
                except Exception:
                    pass
            except Exception as e:
                return JobResult.skipped(
                    reason=f"ws send (message) failed: {type(e).__name__}: {e}"
                )

        if kind == "recurring":
            from services.recurring_schedule import mark_delivered
            if message_failed and not record.details.get("message_sent"):
                ws = state.get("active_ws")
                if ws is None:
                    return JobResult.skipped(reason="ws disappeared (recurring fallback)")
                fb = _fallback_message(description, character.gender)
                try:
                    await ws.send_json({"type": "response", "text": fb})
                    history = state.get("history")
                    if history is not None:
                        history.add("assistant", fb)
                except Exception as e:
                    return JobResult.skipped(
                        reason=f"ws send (recurring fallback) failed: {e}")
            mark_delivered(record)
            record.last_accessed = time.time()
            state["last_reminder_delivered_at"] = time.time()
            if state.get("session_initiated_by") is None:
                state["session_initiated_by"] = "proactive"
                state["proactive_session_started_at"] = time.time()
                ctx.log("session marked as proactive (recurring reminder)")
            try:
                ctx.save_memory()
            except Exception as e:
                ctx.log(f"WARN: save_memory (recurring) failed: {e!r}")
            ctx.log(f"DELIVERED recurring [{record.record_id}] "
                    f"#{record.details.get('delivered_count')} → next "
                    f"{record.details.get('fire_at_iso')}")
            return JobResult.ok(
                record_id=record.record_id, kind=kind,
                description=description[:80],
                delivered_count=record.details.get("delivered_count", 0),
                next_fire_at_iso=record.details.get("fire_at_iso"),
            )

        ws = state.get("active_ws")
        if ws is None:
            return JobResult.skipped(reason="ws disappeared before card send")

        card_payload: dict = {
            "type": "reminder_card",
            "record_id": record.record_id,
            "kind": kind,
            "title": description,
        }
        if event_at_iso:
            card_payload["event_at_iso"] = event_at_iso
        if message_failed and not message_text:
            card_payload["fallback_text"] = (
                "Не получилось сформулировать сообщение от персонажа "
                "(не хватило памяти для модели). Освободите VRAM и в "
                "следующий раз будет красивее."
            )

        try:
            await ws.send_json(card_payload)
        except Exception as e:
            return JobResult.skipped(
                reason=f"ws send (card) failed: {type(e).__name__}: {e}"
            )

        record.details["card_shown"] = True
        record.details["card_shown_at"] = time.time()
        record.last_accessed = time.time()

        state["last_reminder_delivered_at"] = time.time()

        if state.get("session_initiated_by") is None:
            state["session_initiated_by"] = "proactive"
            state["proactive_session_started_at"] = time.time()
            ctx.log(f"session marked as proactive (started_at={state['proactive_session_started_at']:.0f})")

        try:
            ctx.save_memory()
        except Exception as e:
            ctx.log(f"WARN: final save_memory failed: {e!r}")

        ctx.log(
            f"DELIVERED [{record.record_id}] kind={kind} "
            f"llm={'yes' if sent_llm_message else 'fallback' if message_failed else 'cached'}"
        )
        return JobResult.ok(
            record_id=record.record_id,
            kind=kind,
            description=description[:80],
            llm_message_sent=record.details.get("message_sent", False),
            llm_failed=record.details.get("message_failed", False),
            card_shown=True,
        )

    def _find_ready_reminder(self, ctx: JobContext) -> Any:
        memory = ctx.state.get("memory")
        if memory is None:
            return None
        now = time.time()
        best = None
        best_fire_at = float("inf")
        for r in getattr(memory, "records", []):
            if getattr(r, "type", "") != "напоминание":
                continue
            if r.details.get("kind") == "timer":
                continue
            if r.details.get("card_shown", False):
                continue
            if r.details.get("acknowledged", False):
                continue
            if r.details.get("expired", False):
                continue
            if r.details.get("delivered", False):
                continue
            fire_at = r.details.get("fire_at", 0)
            if not isinstance(fire_at, (int, float)) or fire_at <= 0:
                continue
            if fire_at > now:
                continue
            if fire_at < best_fire_at:
                best = r
                best_fire_at = fire_at
        return best
