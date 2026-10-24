from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

from services.log_privacy import priv
from tools.registry import (
    TIER_CONTEXTUAL,
    Tool,
    ToolContext,
)
from tools.semantic import (
    SemanticDeps,
    SemanticResult,
    make_semantic_tool,
)


_RELATIVE_RE = re.compile(r"^\+?\s*(\d+)\s*([smhdwсмчдн])$", re.IGNORECASE)

_RELATIVE_DAYS_TIME_RE = re.compile(
    r"^\+?\s*(\d+)\s*([dдн])\s+(\d{1,2}):(\d{2})$", re.IGNORECASE
)

_TIME_ONLY_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::\d{2})?$")

_DATE_ONLY_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")


def parse_fire_at(s: str, now: Optional[datetime] = None) -> datetime:
    s = (s or "").strip()
    if not s:
        raise ValueError("пустое значение")
    now = now or datetime.now()

    m = _DATE_ONLY_RE.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(y, mo, d, 12, 0)
        except ValueError as e:
            raise ValueError(f"некорректная дата {s!r}: {e}")

    m = _TIME_ONLY_RE.match(s)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if not (0 <= h < 24 and 0 <= mi < 60):
            raise ValueError(f"некорректное время {s!r}")
        target = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target

    m = _RELATIVE_DAYS_TIME_RE.match(s)
    if m:
        days = int(m.group(1))
        h, mi = int(m.group(3)), int(m.group(4))
        if not (0 <= h < 24 and 0 <= mi < 60):
            raise ValueError(f"некорректное время в {s!r}")
        target_date = (now + timedelta(days=days)).date()
        return datetime.combine(
            target_date,
            datetime.min.time().replace(hour=h, minute=mi),
        )

    m = _RELATIVE_RE.match(s)
    if m:
        amount = int(m.group(1))
        unit = m.group(2).lower()
        seconds_per_unit = {
            "s": 1, "с": 1,
            "m": 60, "м": 60,
            "h": 3600, "ч": 3600,
            "d": 86400, "д": 86400,
            "w": 604800, "н": 604800,
        }
        return now + timedelta(seconds=amount * seconds_per_unit[unit])

    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt
    except ValueError:
        pass

    raise ValueError(
        f"не могу разобрать время {s!r}. Используй ISO ('2026-05-10T15:00'), "
        f"relative ('+30m', '+2h', '+1d') или время '15:00'"
    )


_WEEKDAYS_ACC = ["понедельник", "вторник", "среду", "четверг",
                 "пятницу", "субботу", "воскресенье"]
_MONTHS_GEN = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
               "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def _human_when(now: datetime, when: datetime) -> str:
    delta_days = (when.date() - now.date()).days
    hhmm = f"{when:%H:%M}"
    if delta_days == 0:
        day = "сегодня"
    elif delta_days == 1:
        day = "завтра"
    elif 2 <= delta_days <= 6:
        day = f"в {_WEEKDAYS_ACC[when.weekday()]}"
    else:
        day = f"{when.day} {_MONTHS_GEN[when.month]}"
    return f"{day} в {hhmm}"


def _humanize_delta(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    if total < 0:
        return "ВРЕМЯ ПРОШЛО"
    if total < 60:
        return f"через {total} сек."
    if total < 3600:
        return f"через {total // 60} мин."
    if total < 86400:
        h = total // 3600
        m = (total % 3600) // 60
        return f"через {h} ч. {m} мин." if m else f"через {h} ч."
    d = total // 86400
    h = (total % 86400) // 3600
    return f"через {d} дн. {h} ч." if h else f"через {d} дн."


VALID_KINDS = ("one_shot", "pre_event", "recurring")


def _create_reminder_record(mem, description: str, fire_at: datetime,
                            kind: str, event_at: Optional[datetime],
                            schedule: Optional[dict] = None,
                            source: str = "requested"):
    title = description[:50] + ("…" if len(description) > 50 else "")
    details = {
        "kind": kind,
        "description": description,
        "fire_at": fire_at.timestamp(),
        "fire_at_iso": fire_at.strftime("%Y-%m-%d %H:%M"),
        "last_notification_at": 0.0,
        "notification_count": 0,
        "message_text": "",
        "message_sent": False,
        "message_failed": False,
        "card_shown": False,
        "acknowledged": False,
        "expired": False,
    }
    if kind == "pre_event" and event_at is not None:
        details["event_at"] = event_at.timestamp()
        details["event_at_iso"] = event_at.strftime("%Y-%m-%d %H:%M")
    if kind == "recurring" and schedule is not None:
        details["schedule"] = dict(schedule)
        details["source"] = source
        details["delivered_count"] = 0
        details["last_delivered_at"] = 0.0
    return mem.add_record(
        type="напоминание", title=title, details=details,
        importance=0.9, embed_text=description,
    )


_WEEKDAYS_RU = ["понедельник", "вторник", "среда", "четверг",
                "пятница", "суббота", "воскресенье"]


def _build_reminder_extract_system(deps: SemanticDeps) -> str:
    now = datetime.fromtimestamp(deps.now) if deps.now else datetime.now()
    wd = _WEEKDAYS_RU[now.weekday()]
    return (
        "Ты — точный парсер запросов на напоминание. На вход — фраза о том, О ЧЁМ "
        "и КОГДА напомнить. Извлеки структуру и верни СТРОГО JSON, без пояснений.\n\n"
        f"Сейчас: {now:%Y-%m-%d %H:%M} ({wd}). Любые относительные сроки («завтра», "
        "«через 2 часа», «в понедельник», «вечером») считай ОТ ЭТОГО момента и "
        "переводи в АБСОЛЮТНОЕ время.\n\n"
        "Верни JSON ровно такого вида:\n"
        '{"description": "<о чём, кратко, инфинитивом>", '
        '"fire_at": "YYYY-MM-DDTHH:MM", "kind": "one_shot", "event_at": null, '
        '"schedule": null}\n\n'
        "Правила:\n"
        "- fire_at обязателен, строго YYYY-MM-DDTHH:MM, в будущем.\n"
        "- Время суток не указано явно → выбери разумное (утро 09:00, день 14:00, "
        "вечер 19:00; иначе 12:00).\n"
        "- kind=\"pre_event\" ТОЛЬКО если это подготовка к событию с дедлайном — "
        "тогда event_at = время самого события (ISO, строго ПОСЛЕ fire_at). Иначе "
        "kind=\"one_shot\", event_at=null.\n"
        "- «за N до события в HH:MM»: event_at = это HH:MM; fire_at = event_at МИНУС N, "
        "считая ТОЧНО от времени события, НЕ от «сейчас». Пример: «за час до тренировки "
        "в 19:00» → fire_at 18:00, event_at 19:00 (а не 18:NN от текущих минут).\n"
        "- ПОВТОРЯЮЩЕЕСЯ («каждый день/вечер», «по понедельникам», «ежедневно в 22:00»)"
        " → kind=\"recurring\" и schedule: {\"freq\": \"daily\", \"time\": \"HH:MM\"} "
        "либо {\"freq\": \"weekly\", \"time\": \"HH:MM\", \"days\": [0..6]} (0=пн, 6=вс). "
        "fire_at при этом = ПЕРВОЕ будущее вхождение расписания.\n"
        "- description — суть без выдумок (например «проверить почту»).\n"
        "Только JSON."
    )


def _reminder_executor(parsed: dict, deps: SemanticDeps) -> SemanticResult:
    mem = deps.memory
    if mem is None:
        return SemanticResult(ok=False, message="Память недоступна — не смогла поставить напоминание.")

    description = str(parsed.get("description") or "").strip()
    fire_at_raw = str(parsed.get("fire_at") or "").strip()
    kind = str(parsed.get("kind") or "one_shot").strip().lower()
    event_at_raw = str(parsed.get("event_at") or "").strip()
    if event_at_raw.lower() in ("none", "null"):
        event_at_raw = ""

    if not description or not fire_at_raw:
        return SemanticResult(ok=False,
                              message="Не поняла, о чём или когда напомнить — скажи чуть подробнее?")
    if kind not in VALID_KINDS:
        kind = "one_shot"

    try:
        fire_at = parse_fire_at(fire_at_raw)
    except ValueError:
        return SemanticResult(ok=False,
                              message="Не разобрала время — скажи иначе, например «завтра в 15:00»?")

    now = datetime.fromtimestamp(deps.now) if deps.now else datetime.now()
    if fire_at <= now:
        return SemanticResult(ok=False,
                              message="Это время уже прошло — назови момент в будущем.")

    event_at = None
    if kind == "pre_event":
        if event_at_raw:
            try:
                ev = parse_fire_at(event_at_raw)
                if ev > fire_at:
                    event_at = ev
            except ValueError:
                event_at = None
        if event_at is None:
            kind = "one_shot"

    schedule = None
    if kind == "recurring":
        from services.recurring_schedule import (MAX_ACTIVE_RECURRING,
                                                 active_recurring,
                                                 describe_schedule,
                                                 next_fire_at, parse_schedule)
        schedule = parse_schedule(parsed.get("schedule"))
        if schedule is None:
            kind = "one_shot"
        elif len(active_recurring(mem)) >= MAX_ACTIVE_RECURRING:
            return SemanticResult(ok=False, message=(
                "Регулярных напоминаний уже много — давай сначала уберём "
                "какое-нибудь (list_reminders → cancel_reminder)."))
        else:
            fire_at = next_fire_at(schedule, now)

    record = _create_reminder_record(mem, description, fire_at, kind, event_at,
                                     schedule=schedule)
    when_rel = _humanize_delta(fire_at - now)
    when_h = _human_when(now, fire_at)
    if deps.debug:
        print(f"[semantic:set_reminder] «{priv(description)}» @ "
              f"{fire_at:%Y-%m-%d %H:%M} ({when_rel}) kind={kind} → id={record.record_id}")

    if kind == "recurring":
        from services.recurring_schedule import describe_schedule
        sched_h = describe_schedule(schedule)
        facts = (f"Регулярное напоминание поставлено: «{description}», {sched_h} "
                 f"(ближайшее — {when_h}).")
        msg = f"Хорошо, буду напоминать: «{description}» — {sched_h}."
    else:
        facts = f"Напоминание поставлено: «{description}», {when_h} ({when_rel})."
        msg = f"Хорошо, напомню: «{description}» — {when_h} ({when_rel})."
    if event_at is not None:
        tail = f" Само событие — {_human_when(now, event_at)}."
        facts += tail
        msg += tail
    return SemanticResult(
        message=msg, facts=facts,
        data={"record_id": record.record_id, "kind": kind,
              "fire_at": fire_at.isoformat(timespec="minutes")},
    )


def handle_list_reminders(args: dict, ctx: ToolContext) -> str:
    mem = ctx.memory
    if mem is None:
        return "Память недоступна."

    pending = [
        r for r in mem.records
        if r.type == "напоминание"
        and not r.details.get("acknowledged", False)
        and not r.details.get("expired", False)
        and not r.details.get("delivered", False)
    ]
    if not pending:
        return "Активных напоминаний нет."

    pending.sort(key=lambda r: r.details.get("fire_at", 0))
    now = datetime.now()

    lines = [f"Активные напоминания ({len(pending)}):"]
    for r in pending:
        fire_at_ts = r.details.get("fire_at", 0)
        try:
            fire_at = datetime.fromtimestamp(fire_at_ts)
        except (ValueError, OSError, TypeError):
            lines.append(f"  - [{r.record_id}] {r.title} (повреждённое fire_at)")
            continue
        when_human = _humanize_delta(fire_at - now)
        desc = r.details.get("description", r.title)
        kind = r.details.get("kind", "one_shot")
        line = (f"  - [{r.record_id}] ({kind}) {desc}\n"
                f"    Сработает: {fire_at.strftime('%Y-%m-%d %H:%M')} ({when_human})")
        if kind == "recurring" and r.details.get("schedule"):
            try:
                from services.recurring_schedule import describe_schedule
                line += f"\n    Повтор: {describe_schedule(r.details['schedule'])}"
            except Exception:
                pass
        if kind == "pre_event":
            event_at_ts = r.details.get("event_at", 0)
            if event_at_ts:
                try:
                    event_at = datetime.fromtimestamp(event_at_ts)
                    line += f"\n    Событие: {event_at.strftime('%Y-%m-%d %H:%M')}"
                except (ValueError, OSError):
                    pass
        lines.append(line)

    lines.append("\nОтменить: cancel_reminder(record_id=\"rXX\")")
    return "\n".join(lines)


def handle_cancel_reminder(args: dict, ctx: ToolContext) -> str:
    mem = ctx.memory
    if mem is None:
        return "Память недоступна."
    rid = str(args.get("record_id") or "").strip().strip("[]")
    text = str(args.get("text") or args.get("query") or "").strip().lower()

    pending = [
        r for r in mem.records
        if r.type == "напоминание"
        and not r.details.get("acknowledged", False)
        and not r.details.get("expired", False)
        and not r.details.get("delivered", False)
    ]
    target = None
    if rid:
        target = next((r for r in pending
                       if (r.record_id or "").lower() == rid.lower()), None)
        if target is None:
            return (f"Активного напоминания с id {rid!r} нет — проверь "
                    f"list_reminders().")
    elif text:
        hits = [r for r in pending
                if text in (r.details.get("description") or r.title).lower()]
        if not hits:
            return f"Не нашла активного напоминания про «{text}» — посмотри list_reminders()."
        if len(hits) > 1:
            opts = "\n".join(f"  - [{r.record_id}] "
                             f"{r.details.get('description') or r.title}"
                             for r in hits[:5])
            return ("Под это описание подходит несколько — уточни record_id:\n"
                    + opts)
        target = hits[0]
    else:
        return "Скажи, какое напоминание отменить: record_id или текст."

    target.details["expired"] = True
    target.details["cancelled"] = True
    target.details["cancelled_at"] = datetime.now().timestamp()
    target.details["expired_at"] = target.details["cancelled_at"]
    desc = target.details.get("description") or target.title
    kind = target.details.get("kind", "one_shot")
    if ctx.debug:
        print(f"[cancel_reminder] {target.record_id} ({kind}): {priv(desc, 60)}")
    if kind == "recurring":
        return f"Отменено регулярное напоминание: «{desc}». Больше не напоминаю."
    return f"Отменено напоминание: «{desc}»."


SET_REMINDER_HELP = """set_reminder(intent) — поставить напоминание.

Передай ОДНОЙ фразой на естественном языке, О ЧЁМ и КОГДА напомнить — точное
время разберёт система (тебе считать дату/timestamp НЕ нужно).

Примеры intent:
  - «через 20 минут проверить курицу в духовке»
  - «завтра в 15:00 напомнить про врача»
  - «в понедельник утром позвонить маме»
  - «за час до тренировки в 19:00 собрать вещи» (подготовка к событию)
  - «каждый вечер в 21:30 разминка» (повторяющееся — станет регулярным,
    будешь напоминать сама живой репликой; отмена — cancel_reminder)

Что происходит:
  1. Запоминается твой intent.
  2. После твоей реплики система извлекает точное время и ставит напоминание;
     приходит короткое подтверждение с разобранной датой/временем.
  3. Когда время наступит — ты напомнишь сама (отдельным сообщением).

Когда НЕ использовать: если просто спросили который час — это get_time.
Посмотреть активные напоминания — list_reminders().
"""


SET_REMINDER_TOOL = make_semantic_tool(
    name="set_reminder",
    description=(
        "Поставить напоминание. Опиши ОДНОЙ фразой О ЧЁМ и КОГДА — например "
        "«завтра в 15:00 про врача», «через 2 часа проверить почту». Точное время "
        "и формат разберёт система; считать дату самой НЕ нужно."
    ),
    intent_arg_desc=(
        "О чём и когда напомнить, одной фразой по-русски: «завтра в 15:00 про "
        "врача», «через 2 часа проверить почту». Время считать НЕ нужно — система сама."
    ),
    summary=(
        "set_reminder(intent) — поставить напоминание: скажи о чём и когда обычной "
        "фразой («завтра в 15:00 про врача»); точное время разберёт система."
    ),
    help=SET_REMINDER_HELP,
    build_extract_system=_build_reminder_extract_system,
    executor=_reminder_executor,
    triggers=["напомн", "напомин", "не забуд", "remind"],
    capability="reminder",
    ack=("Напоминание ПРИНЯТО и сейчас оформляется (готовность с точной датой/"
         "временем подтвердит СЛЕДУЮЩАЯ реплика через пару секунд). СЕЙЧАС ответь "
         "ОЧЕНЬ коротко в характере — ТОЛЬКО что приняла и сейчас займёшься: "
         "например «Момент~», «Сейчас сделаю~», «Конечно, секунду~». НЕ говори, что "
         "уже готово/настроено, и НЕ называй время — это скажет следующая реплика. "
         "НЕ вызывай set_reminder снова."),
    fail_message="Не разобрала запрос на напоминание — скажи иначе: о чём и когда?",
    empty_hint=("set_reminder вызван без intent. Впиши одной фразой о чём и когда "
                "напомнить — например «завтра в 15:00 про врача». Если напоминание "
                "не нужно — просто ответь словами."),
)


LIST_REMINDERS_TOOL = Tool(
    name="list_reminders",
    tier=TIER_CONTEXTUAL,
    capability="reminder",
    triggers=[
        "напомин", "напоминан",
        "remind",
    ],
    schema={
        "name": "list_reminders",
        "description": "Показать активные напоминания.",
        "parameters": {"type": "object", "properties": {}},
    },
    handler=handle_list_reminders,
    summary="list_reminders() — посмотреть активные напоминания",
    help=(
        "list_reminders() — список pending напоминаний, отсортированный по "
        "времени срабатывания (ближайшее первым). Включает record_id, "
        "описание, fire_at и «через X»-формат."
    ),
)


CANCEL_REMINDER_TOOL = Tool(
    name="cancel_reminder",
    tier=TIER_CONTEXTUAL,
    capability="reminder",
    triggers=[
        "напомин", "не напомин", "отмени", "хватит напоминать", "remind",
    ],
    schema={
        "name": "cancel_reminder",
        "description": ("Отменить напоминание (в т.ч. регулярное — «хватит "
                        "напоминать про…»). Укажи record_id из list_reminders "
                        "ИЛИ текст, о чём оно."),
        "parameters": {
            "type": "object",
            "properties": {
                "record_id": {"type": "string",
                              "description": "id записи из list_reminders (например r12)"},
                "text": {"type": "string",
                         "description": "или текст: о чём напоминание («разминка»)"},
            },
            "required": [],
        },
    },
    handler=handle_cancel_reminder,
    summary=("cancel_reminder(record_id|text) — отменить напоминание "
             "(включая регулярные) по просьбе Господина"),
    help=(
        "cancel_reminder — отменить напоминание.\n\n"
        "Параметры (достаточно одного):\n"
        "  record_id — id из list_reminders (надёжнее)\n"
        "  text      — о чём оно («разминка») — сработает при однозначном "
        "совпадении\n\n"
        "Используй когда Господин просит не напоминать: «хватит напоминать про "
        "разминку», «убери напоминание про таблетки»."
    ),
)
