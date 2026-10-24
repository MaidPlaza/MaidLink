from __future__ import annotations

import re

from services.log_privacy import priv
from tools.registry import ToolContext
from tools.semantic import SemanticDeps, SemanticResult, make_semantic_tool


_RECORD_ID_RE = re.compile(r"^r\d+$")


def _resolve_participants(raw, mem, debug: bool = False) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        tokens = re.split(r"[,;]|\.(?=\s|$)", raw)
    else:
        tokens = list(raw)

    resolved: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        tok = str(tok).strip().strip("«»\"'")
        if not tok:
            continue
        if _RECORD_ID_RE.match(tok):
            rid = tok
        else:
            found = mem.find_entity(tok)
            if found is None:
                if debug:
                    print(f"[MEM] participants: «{priv(tok)}» не найден в памяти, пропускаю")
                continue
            rid = found.record_id
        if rid not in seen:
            resolved.append(rid)
            seen.add(rid)
    return resolved


def handle_plan_event(args: dict, ctx: ToolContext) -> str:
    mem = ctx.memory
    if mem is None:
        return "Память недоступна."
    text = (args.get("text") or "").strip()
    date = (args.get("date") or "").strip()
    where = (args.get("where") or "").strip()
    notes = (args.get("notes") or "").strip()
    participants_raw = args.get("participants", "")
    if not text or not date:
        return "Нужно указать что запланировано (text) и когда (date)."

    links = _resolve_participants(participants_raw, mem, debug=ctx.debug)

    details = {"description": text, "due_date": date, "status": "ожидает"}
    if where:
        details["where"] = where
    if notes:
        details["notes"] = notes
    title = text[:50]
    mem.add_record(
        "событие_план", title, details,
        importance=0.7,
        embed_text=f"{text} {date} {where}",
        links=links,
    )
    mem.save()

    result = f"Запланировано: {title}\nКогда: {date}"
    if where:
        result += f"\nГде: {where}"
    if links:
        names = []
        for rid in links:
            rec = next((r for r in mem.records if r.record_id == rid), None)
            if rec:
                names.append(rec.title)
        if names:
            result += f"\nУчастники: {', '.join(names)}"
    if ctx.debug:
        print(f"[MEM] plan_event: {priv(title)} → {date} links={links}")
    return result


def handle_update_event(args: dict, ctx: ToolContext) -> str:
    mem = ctx.memory
    if mem is None:
        return "Память недоступна."
    title = (args.get("title") or "").strip().strip("«»\"'")
    if not title:
        return "Нужно указать название события."
    record = mem.get_by_title(title)
    if not record or record.type != "событие_план":
        return (f"Запланированное событие '{title}' не найдено. "
                "Попробуй search_memory(query='тип:событие_план').")

    new_date = (args.get("new_date") or "").strip()
    status = (args.get("status") or "").strip()
    notes = (args.get("notes") or "").strip()
    participants_raw = args.get("participants", "")

    changes: list[str] = []
    if new_date:
        record.details["due_date"] = new_date
        changes.append(f"Новая дата: {new_date}")
    if status:
        old_status = record.details.get("status", "ожидает")
        record.details["status"] = status
        changes.append(f"Статус: {old_status} → {status}")
        if status in ("свершилось", "отменено"):
            record.type = "событие"
            changes.append("Событие перенесено в историю")
    if notes:
        record.details["notes"] = notes
        changes.append("Заметки обновлены")
    if participants_raw:
        new_links = _resolve_participants(participants_raw, mem, debug=ctx.debug)
        if new_links:
            merged = list(dict.fromkeys((record.links or []) + new_links))
            record.links = merged
            mem._link_episode_to_entities(record, new_links)
            changes.append(f"Участники обновлены: {', '.join(new_links)}")

    mem.save()
    if ctx.debug:
        print(f"[MEM] update_event: {priv(title)} → {priv(', '.join(changes))}")
    if not changes:
        return "Ничего не изменено."
    return f"Обновлено: {title}\n" + "\n".join(changes)


def _build_plan_extract_system(deps: SemanticDeps) -> str:
    return (
        "Ты — точный парсер запросов на планирование события. Извлеки структуру и "
        "верни СТРОГО JSON, без пояснений.\n\n"
        "Верни ровно такой вид:\n"
        '{"description": "<что за событие, кратко>", "date": "<когда, человеческой '
        'фразой как сказано>", "where": "<где, если указано, иначе пусто>", '
        '"participants": ["<имена явно упомянутых людей/мест/организаций>"], '
        '"notes": "<доп. детали или пусто>"}\n\n'
        "Правила:\n"
        "- description и date обязательны.\n"
        "- date оставляй ЧЕЛОВЕЧЕСКОЙ фразой, как сказал пользователь («в субботу "
        "вечером», «20 апреля в 15:00») — НЕ переводи в ISO/числа.\n"
        "- participants — ТОЛЬКО явно названные люди/места/организации (Виктор, мама, "
        "кафе «Заварка»), без выдумок. Никого не названо → [].\n"
        "Только JSON."
    )


def _plan_executor(parsed: dict, deps: SemanticDeps) -> SemanticResult:
    mem = deps.memory
    if mem is None:
        return SemanticResult(ok=False, message="Память недоступна — не смогла запланировать.")
    description = str(parsed.get("description") or "").strip()
    date = str(parsed.get("date") or "").strip()
    where = str(parsed.get("where") or "").strip()
    notes = str(parsed.get("notes") or "").strip()
    participants = parsed.get("participants") or []
    if not description or not date:
        return SemanticResult(ok=False,
                              message="Не поняла, что и когда запланировать — скажи подробнее?")

    links = _resolve_participants(participants, mem, debug=deps.debug)
    details = {"description": description, "due_date": date, "status": "ожидает"}
    if where:
        details["where"] = where
    if notes:
        details["notes"] = notes
    record = mem.add_record(
        "событие_план", description[:50], details, importance=0.7,
        embed_text=f"{description} {date} {where}", links=links)

    names = []
    for rid in links:
        rec = next((r for r in mem.records if r.record_id == rid), None)
        if rec:
            names.append(rec.title)
    facts = f"Событие запланировано: «{description}», {date}."
    if where:
        facts += f" Место: {where}."
    if names:
        facts += f" Связаны участники: {', '.join(names)}."
    if deps.debug:
        print(f"[semantic:plan_event] «{priv(description)}» @ {date} links={links} "
              f"→ id={record.record_id}")
    return SemanticResult(message=facts, facts=facts,
                          data={"record_id": record.record_id, "links": links})


PLAN_EVENT_HELP = """plan_event(intent) — запланировать будущее событие.

Опиши ОДНОЙ фразой: что, когда, где и с кем. Раскладку по полям (участники, дата,
место) сделает отдельный обработчик — тебе оформлять структуру НЕ нужно.

Примеры intent:
  - «ужин с Виктором в субботу вечером в кафе Заварка»
  - «созвон с мамой завтра в 18:00»
  - «запиши встречу с врачом 20 апреля в 15:00»

Что происходит:
  1. Запоминается твой intent.
  2. После реплики система извлекает что/когда/где/участников, связывает
     упомянутых людей/места из памяти и создаёт запись-план.
  3. Приходит подтверждение с разобранными деталями.

Изменить/перенести/отменить уже созданное событие — update_event.
"""


PLAN_EVENT_TOOL = make_semantic_tool(
    name="plan_event",
    description=(
        "Запланировать будущее событие. Опиши ОДНОЙ фразой что, когда, где и с кем "
        "— например «ужин с Виктором в субботу вечером в кафе». Участников, дату и "
        "место разберёт система; раскладывать по полям НЕ нужно."
    ),
    intent_arg_desc=(
        "Что запланировать, одной фразой: что/когда/где/с кем — «ужин с Виктором "
        "в субботу вечером», «созвон с мамой завтра в 18:00»."
    ),
    summary=(
        "plan_event(intent) — запланировать событие: скажи что/когда/где/с кем "
        "обычной фразой; участников и детали разберёт система."
    ),
    help=PLAN_EVENT_HELP,
    build_extract_system=_build_plan_extract_system,
    executor=_plan_executor,
    triggers=[
        "запланируй", "запланировать", "запланирую",
        "договорил", "договорим", "договарива",
        "назнач", "назначу", "назначил", "назначить",
        "забронир", "бронир", "сохрани событие",
        "запиши", "записать", "запис", "записа",
        "встреч", "встрет", "встреча",
        "запись к", "запись на", "приём", "прием",
    ],
    capability="планирование",
    ack=("План ПРИНЯТ и сейчас оформляется (подтверждение с деталями придёт "
         "следующей репликой). СЕЙЧАС ответь ОЧЕНЬ коротко в характере — что приняла "
         "и сейчас оформишь (например «Момент~», «Сейчас запланирую~»). НЕ называй "
         "детали сейчас. НЕ вызывай plan_event снова."),
    fail_message="Не разобрала, что именно запланировать — скажи иначе: что, когда и с кем?",
    empty_hint=("plan_event вызван без intent. Впиши одной фразой, что запланировать "
                "— например «ужин с Виктором в субботу вечером». Если планировать "
                "нечего — просто ответь словами."),
)


def _find_plan_event(mem, target: str):
    t = (target or "").strip().strip("«»\"'")
    if not t:
        return None
    if _RECORD_ID_RE.match(t):
        rec = next((r for r in getattr(mem, "records", []) if r.record_id == t), None)
        if rec is not None and rec.type == "событие_план":
            return rec
    getter = getattr(mem, "get_by_title", None)
    if callable(getter):
        rec = getter(t)
        if rec is not None and getattr(rec, "type", "") == "событие_план":
            return rec
    tl = t.lower()
    for r in getattr(mem, "records", []):
        if getattr(r, "type", "") != "событие_план":
            continue
        title = (r.title or "").lower()
        desc = (r.details.get("description", "") or "").lower()
        if tl in title or tl in desc or (title and title in tl):
            return r
    return None


def _build_update_extract_system(deps: SemanticDeps) -> str:
    return (
        "Ты — точный парсер запроса на ИЗМЕНЕНИЕ запланированного события. Извлеки "
        "структуру и верни СТРОГО JSON, без пояснений.\n\n"
        "Верни ровно такой вид:\n"
        '{"target": "<какое событие меняем — кратко по сути/названию, напр. «ужин с '
        'Виктором»>", "new_date": "<новая дата человеческой фразой, если переносят, '
        'иначе пусто>", "status": "<свершилось | отменено | пусто>", '
        '"participants": ["<доп. участники, если добавляют>"], "notes": "<доп. '
        'заметки или пусто>"}\n\n'
        "Правила:\n"
        "- target обязателен — что именно меняем (по сути события).\n"
        "- status: «состоялось/прошло/уже было/сделано» → \"свершилось\"; «отмени/"
        "отменилось/не будет/убери» → \"отменено\"; иначе пусто.\n"
        "- new_date — ТОЛЬКО если переносят на другое время; человеческой фразой.\n"
        "- Меняй только то, что ЯВНО сказано; остальное — пусто/[].\n"
        "Только JSON."
    )


def _update_executor(parsed: dict, deps: SemanticDeps) -> SemanticResult:
    mem = deps.memory
    if mem is None:
        return SemanticResult(ok=False, message="Память недоступна — не смогла изменить.")
    target = str(parsed.get("target") or "").strip()
    if not target:
        return SemanticResult(ok=False,
                              message="Не поняла, какое событие изменить — уточни название?")
    record = _find_plan_event(mem, target)
    if record is None:
        return SemanticResult(ok=False,
                              message=f"Не нашла в планах «{target}» — может, оно называется иначе?")

    new_date = str(parsed.get("new_date") or "").strip()
    status = str(parsed.get("status") or "").strip().lower()
    notes = str(parsed.get("notes") or "").strip()
    participants = parsed.get("participants") or []

    changes: list[str] = []
    if new_date:
        record.details["due_date"] = new_date
        changes.append(f"перенесено на {new_date}")
    if status in ("свершилось", "отменено"):
        record.details["status"] = status
        record.type = "событие"
        changes.append("отменено" if status == "отменено" else "состоялось")
    if notes:
        record.details["notes"] = notes
        changes.append("заметки обновлены")
    if participants:
        new_links = _resolve_participants(participants, mem, debug=deps.debug)
        if new_links:
            record.links = list(dict.fromkeys((record.links or []) + new_links))
            mem._link_episode_to_entities(record, new_links)
            changes.append("участники добавлены")

    if not changes:
        return SemanticResult(ok=False,
                              message=f"В «{record.title}» нечего менять — что именно поправить?")
    if deps.debug:
        print(f"[semantic:update_event] «{priv(record.title)}» → {priv(', '.join(changes))}")
    facts = f"Событие «{record.title}» обновлено: {', '.join(changes)}."
    return SemanticResult(message=facts, facts=facts,
                          data={"record_id": record.record_id, "changes": changes})


UPDATE_EVENT_HELP = """update_event(intent) — изменить уже запланированное событие.

Опиши ОДНОЙ фразой, какое событие и что поменять — какое именно и какое изменение
разберёт отдельный обработчик.

Примеры intent:
  - «перенеси ужин с Виктором на воскресенье»
  - «встреча с врачом отменилась»
  - «ужин с Виктором уже состоялся»
  - «добавь Анну к встрече в пятницу»

Можно: перенести (new_date), отметить состоявшимся/отменённым (status — уйдёт в
историю), добавить участников/заметки. Создать НОВОЕ событие — plan_event.
"""


UPDATE_EVENT_TOOL = make_semantic_tool(
    name="update_event",
    description=(
        "Изменить уже запланированное событие: перенести, отметить состоявшимся/"
        "отменённым, добавить участников. Опиши ОДНОЙ фразой — например «перенеси "
        "ужин с Виктором на воскресенье», «встреча с врачом отменилась»."
    ),
    intent_arg_desc=(
        "Что изменить, одной фразой: «перенеси ужин с Виктором на воскресенье», "
        "«встреча с врачом отменилась», «ужин состоялся»."
    ),
    summary=(
        "update_event(intent) — изменить план: перенести / отменить / отметить "
        "состоявшимся / добавить участников. Скажи обычной фразой что и как."
    ),
    help=UPDATE_EVENT_HELP,
    build_extract_system=_build_update_extract_system,
    executor=_update_executor,
    triggers=[
        "перенес", "перенесл", "перенести", "переношу",
        "отмени", "отменить", "отменяю", "отменил",
        "изменить встреч", "изменить событи",
        "уже состоял", "уже прош", "уже был",
        "сдвин", "сдвинуть",
    ],
    capability="планирование",
    ack=("Изменение ПРИНЯТО и сейчас применяется (подтверждение придёт следующей "
         "репликой). СЕЙЧАС ответь ОЧЕНЬ коротко в характере, что приняла и сейчас "
         "поправишь (например «Момент~»). НЕ называй детали. НЕ вызывай update_event снова."),
    fail_message="Не разобрала, какое событие и как изменить — скажи иначе?",
    empty_hint=("update_event вызван без intent. Впиши одной фразой, какое событие и "
                "что поменять — например «перенеси ужин с Виктором на воскресенье». "
                "Если менять нечего — просто ответь словами."),
)


def parse_due_date(raw: str):
    from datetime import datetime
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(raw[:len(fmt) + 2], fmt).date()
        except ValueError:
            continue
    return None


def plan_events_for_day(records, day) -> list:
    out = []
    for r in (records or []):
        if getattr(r, "type", "") != "событие_план" or getattr(r, "is_forgotten", False):
            continue
        d = getattr(r, "details", {}) or {}
        if str(d.get("status") or "ожидает") not in ("ожидает", "", "planned"):
            continue
        if parse_due_date(str(d.get("due_date") or "")) == day:
            out.append(r)
    return out
