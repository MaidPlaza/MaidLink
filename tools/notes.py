from __future__ import annotations

import time

from services.log_privacy import priv
from tools.registry import TIER_CONTEXTUAL, Tool, ToolContext

MAX_NOTE_CHARS = 4000
MAX_NOTES = 30


def _find_note(mem, title: str):
    tl = (title or "").strip().lower()
    if not tl:
        return None
    for r in getattr(mem, "records", []):
        if r.type == "заметка" and r.title.strip().lower() == tl:
            return r
    return None


def _notes(mem) -> list:
    return [r for r in getattr(mem, "records", []) if r.type == "заметка"]


def handle_write_note(args: dict, ctx: ToolContext) -> str:
    mem = ctx.memory
    if mem is None:
        return "Память недоступна."
    title = str(args.get("title") or "").strip().strip("«»\"'")
    text = str(args.get("text") or "").rstrip()
    if not title or not text:
        return "Нужны и title (короткое название), и text (содержимое заметки)."
    if len(text) > MAX_NOTE_CHARS:
        return (f"Слишком длинно ({len(text)} символов, максимум {MAX_NOTE_CHARS}) — "
                f"сократи или разбей на две заметки.")
    rec = _find_note(mem, title)
    if rec is None:
        if len(_notes(mem)) >= MAX_NOTES:
            return (f"Заметок уже {MAX_NOTES} — предел. Удали ненужную "
                    f"(delete_note) или веди учёт в существующей.")
        rec = mem.add_record(
            type="заметка", title=title,
            details={"text": text, "updated_at": time.time()},
            importance=0.6, embed_text=f"{title}\n{text}")
        if ctx.debug:
            print(f"[notes] created «{priv(title)}» ({len(text)} chars)")
        return f"Заметка «{title}» создана."
    rec.details["text"] = text
    rec.details["updated_at"] = time.time()
    rec.last_accessed = time.time()
    if ctx.debug:
        print(f"[notes] rewritten «{priv(rec.title)}» ({len(text)} chars)")
    return f"Заметка «{rec.title}» переписана."


def handle_append_note(args: dict, ctx: ToolContext) -> str:
    mem = ctx.memory
    if mem is None:
        return "Память недоступна."
    title = str(args.get("title") or "").strip().strip("«»\"'")
    text = str(args.get("text") or "").strip()
    if not title or not text:
        return "Нужны и title (какой заметке), и text (что дописать)."
    rec = _find_note(mem, title)
    if rec is None:
        return handle_write_note({"title": title, "text": text}, ctx)
    cur = str(rec.details.get("text") or "")
    new = (cur + "\n" + text).strip()
    if len(new) > MAX_NOTE_CHARS:
        return (f"Заметка «{rec.title}» переполнится ({len(new)} символов, "
                f"максимум {MAX_NOTE_CHARS}). Сверни старое (write_note с "
                f"кратким итогом) и дописывай дальше.")
    rec.details["text"] = new
    rec.details["updated_at"] = time.time()
    rec.last_accessed = time.time()
    if ctx.debug:
        print(f"[notes] append → «{priv(rec.title)}»: {priv(text, 60)}")
    return f"Дописано в «{rec.title}»."


def handle_delete_note(args: dict, ctx: ToolContext) -> str:
    mem = ctx.memory
    if mem is None:
        return "Память недоступна."
    title = str(args.get("title") or "").strip().strip("«»\"'")
    rec = _find_note(mem, title)
    if rec is None:
        existing = ", ".join(f"«{r.title}»" for r in _notes(mem)[:10]) or "(нет)"
        return f"Заметки «{title}» нет. Есть: {existing}."
    mem.records.remove(rec)
    if ctx.debug:
        print(f"[notes] deleted «{priv(rec.title)}»")
    return f"Заметка «{rec.title}» удалена."


def handle_list_notes(args: dict, ctx: ToolContext) -> str:
    mem = ctx.memory
    if mem is None:
        return "Память недоступна."
    notes = _notes(mem)
    if not notes:
        return ("Заметок пока нет. Заведи первую: write_note(title, text) — "
                "например, для учёта, списка или черновика.")
    notes.sort(key=lambda r: float(r.details.get("updated_at") or r.created_at),
               reverse=True)
    lines = [f"Твои заметки ({len(notes)}):"]
    for r in notes:
        first = (str(r.details.get("text") or "").strip().splitlines() or [""])[0]
        lines.append(f"  - «{r.title}» — {first[:80]}")
    lines.append("\nПолный текст: get_details(title=\"…\"); дописать: append_note.")
    return "\n".join(lines)


NOTES_WHEN_TO_USE = """Когда пользоваться заметками (это твоя свободная тетрадь — форматов у неё нет,
правил минимум; используй, когда другие инструменты не подходят):
  - УЧЁТ/СЧЁТЧИК: «считай дни, когда я встаю раньше 9» → заведи заметку и
    ДОПИСЫВАЙ строку-отметку (append_note) каждый раз, когда это случилось;
    попросят итог — открой (get_details) и посчитай строки.
  - СПИСОК: покупки, «фильмы посмотреть», идеи подарка — по пункту на строку;
    вычеркнуть = переписать без пункта (write_note).
  - «ЗАПИШИ ЭТО»: пользователь просит сохранить мысль/рецепт/ссылку — запиши
    своими словами, точно передав суть.
  - ЧЕРНОВИК/НАБЛЮДЕНИЯ: всё, что хочешь накапливать между сессиями.
Заголовки своих заметок ты всегда видишь в <твои_заметки>. НЕ заводи заметку
под то, для чего есть спец-инструмент: время-напоминания — set_reminder,
планы с датой — plan_event, факты о людях — сами лягут в память."""


WRITE_NOTE_TOOL = Tool(
    name="write_note",
    tier=TIER_CONTEXTUAL,
    capability="заметки",
    triggers=["запиши", "заметк", "запомни списком", "веди учёт", "отмечай"],
    schema={
        "name": "write_note",
        "description": ("Создать или ПОЛНОСТЬЮ переписать свою заметку — свободный "
                        "текст без формата (учёт, список, черновик, «запиши это»). "
                        "Дописать строку к существующей — append_note."),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string",
                          "description": "короткое устойчивое название («Ранние подъёмы», «Покупки»)"},
                "text": {"type": "string",
                         "description": "полное содержимое заметки (свободный текст)"},
            },
            "required": ["title", "text"],
        },
    },
    handler=handle_write_note,
    summary="write_note(title, text) — создать/переписать свою свободную заметку",
    help="write_note(title, text) — создать или переписать заметку целиком.\n\n"
         + NOTES_WHEN_TO_USE,
)


APPEND_NOTE_TOOL = Tool(
    name="append_note",
    tier=TIER_CONTEXTUAL,
    capability="заметки",
    triggers=["запиши", "заметк", "добавь в список", "отметь", "плюс один"],
    schema={
        "name": "append_note",
        "description": ("Дописать строку в свою заметку (не переписывая её): "
                        "отметка учёта, новый пункт списка. Нет такой заметки — "
                        "создастся."),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "название заметки"},
                "text": {"type": "string",
                         "description": "что дописать (обычно одна строка: дата+факт / пункт)"},
            },
            "required": ["title", "text"],
        },
    },
    handler=handle_append_note,
    summary="append_note(title, text) — дописать строку в заметку (учёт/список)",
    help="append_note(title, text) — дописать строку в конец заметки.\n\n"
         + NOTES_WHEN_TO_USE,
)


DELETE_NOTE_TOOL = Tool(
    name="delete_note",
    tier=TIER_CONTEXTUAL,
    capability="заметки",
    triggers=["удали заметк", "убери заметк", "выброси заметк"],
    schema={
        "name": "delete_note",
        "description": "Удалить свою заметку по названию (по просьбе или когда изжила себя).",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "название заметки"},
            },
            "required": ["title"],
        },
    },
    handler=handle_delete_note,
    summary="delete_note(title) — удалить заметку",
    help="delete_note(title) — удалить заметку навсегда (не восстановить).",
)


LIST_NOTES_TOOL = Tool(
    name="list_notes",
    tier=TIER_CONTEXTUAL,
    capability="заметки",
    triggers=["заметк", "список", "что я просил записать"],
    schema={
        "name": "list_notes",
        "description": "Показать все свои заметки (название + первая строка).",
        "parameters": {"type": "object", "properties": {}},
    },
    handler=handle_list_notes,
    summary="list_notes() — список своих заметок",
    help="list_notes() — все заметки: название + первая строка. Полный текст "
         "конкретной — get_details(title).",
)
