from __future__ import annotations

import json
import re
from datetime import datetime


HABIT_EXTRACT_PROMPT = """Ты — аналитик памяти {char_name}. Прочитай диалог и реши, есть ли у {honorific}а ЯВНАЯ РЕГУЛЯРНАЯ потребность, о которой стоит завести повторяющееся напоминание. Верни СТРОГО JSON.

Уже стоят напоминания (НЕ дублируй их и близкие по смыслу):
{existing_list}

Формат ответа:
{{"habits": [{{"description": "<о чём напомнить, инфинитивом>", "schedule": {{"freq": "daily", "time": "HH:MM"}}}}]}}
Для weekly: {{"freq": "weekly", "time": "HH:MM", "days": [0..6]}} (0=пн, 6=вс).

ЖЁСТКИЕ правила (нарушить = навязчивость, это хуже, чем пропустить):
- Потребность должна быть РЕГУЛЯРНОЙ и ЯВНОЙ: он сам говорит, что постоянно забывает/пропускает/жалеет («опять забыл таблетки», «вечно засиживаюсь и пропускаю разминку»). Разовые дела, вкусы, планы — НЕТ.
- Одного упоминания мало, если в нём нет повторяемости («сегодня забыл» ≠ «вечно забываю»).
- Время выбери из контекста (принял таблетки утром → утро ~09:00; разминка вечером → ~21:00); не сказано — разумный час.
- МАКСИМУМ ОДНА привычка. Чаще всего правильный ответ — НИ ОДНОЙ.
- Любое сомнение → {{"habits": []}}.
Только JSON."""


def _existing_list(memory) -> str:
    lines = []
    for r in getattr(memory, "records", []):
        if getattr(r, "type", "") != "напоминание":
            continue
        d = r.details or {}
        if d.get("expired") or d.get("acknowledged") or d.get("delivered"):
            continue
        lines.append(f"  - {d.get('description') or r.title}")
    return "\n".join(lines) or "  (нет)"


def _parse(raw: str) -> list[dict]:
    if not raw:
        return []
    m = re.search(r"\{.*\}", raw, flags=re.S)
    if not m:
        return []
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    out = []
    for h in (d.get("habits") or []):
        if isinstance(h, dict) and str(h.get("description") or "").strip():
            out.append(h)
    return out


def extract_habits_from_session(messages, memory, char_name: str = "",
                                honorific: str = "Господин",
                                gender: str = "female") -> dict:
    from memory.conversation import tail_by_tokens
    from memory.unified import EXTRACT_TOKEN_BUDGET, format_dialogue
    from services.recurring_schedule import (MAX_ACTIVE_RECURRING,
                                             active_recurring, next_fire_at,
                                             parse_schedule)

    res = {"created": 0, "skipped": 0}
    if not getattr(memory, "_client", None) or len(messages or []) < 4:
        return res
    if len(active_recurring(memory)) >= MAX_ACTIVE_RECURRING:
        return res

    convo = format_dialogue(tail_by_tokens(messages, EXTRACT_TOKEN_BUDGET),
                            honorific or "Господин", char_name or "")
    system = HABIT_EXTRACT_PROMPT.format(
        char_name=char_name or "персонажа", honorific=honorific or "Господин",
        existing_list=_existing_list(memory))
    try:
        raw = memory._client.chat(
            messages=[{"role": "user", "content": convo}],
            system=system, thinking=False, label="Habit extraction")
    except Exception as e:
        print(f"[habit] LLM fail: {type(e).__name__}: {e}")
        return res

    items = _parse(raw)[:1]
    now = datetime.now()
    for h in items:
        schedule = parse_schedule(h.get("schedule"))
        if schedule is None:
            res["skipped"] += 1
            continue
        desc = str(h["description"]).strip()
        dl = desc.lower()
        dup = any(dl in ((r.details or {}).get("description") or r.title).lower()
                  or ((r.details or {}).get("description") or r.title).lower() in dl
                  for r in active_recurring(memory))
        if dup:
            res["skipped"] += 1
            continue
        from tools.reminder import _create_reminder_record
        fire_at = next_fire_at(schedule, now)
        _create_reminder_record(memory, desc, fire_at, "recurring", None,
                                schedule=schedule, source="inferred")
        res["created"] += 1
    return res
