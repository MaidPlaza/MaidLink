from __future__ import annotations

import time

from services.log_privacy import priv
from tools.registry import ToolContext


def handle_search_memory(args: dict, ctx: ToolContext) -> str:
    mem = ctx.memory
    if mem is None:
        return "Память недоступна."
    from memory.unified import SEARCHABLE_TYPES, normalize_search_type

    query = (args.get("query") or "").strip()
    raw_type = (args.get("type") or args.get("record_type")
                or args.get("filter") or "").strip()
    types_line = ", ".join(SEARCHABLE_TYPES)

    type_filter = None
    if raw_type:
        type_filter = normalize_search_type(raw_type)
        if type_filter is None:
            return (f"Неизвестный тип {raw_type!r}. Доступные типы: {types_line}. "
                    f"Дневники — это type=\"рефлексия\".")
    if not query and not type_filter:
        return ("Укажи query (что искать) и/или type (тип записей). "
                f"Типы: {types_line}.")

    results = mem.search(query, type_filter=type_filter)
    if ctx.debug:
        print(f"\n[MEM] search_memory(«{priv(query)}», type={type_filter!r}) "
              f"→ {len(results)} results")
    if not results:
        if query.startswith("тип:"):
            return f"Такого типа нет. Доступные типы: {types_line}"
        if type_filter and not query:
            return f"Записей типа «{type_filter}» в памяти пока нет."
        if type_filter:
            return (f"Среди записей типа «{type_filter}» по запросу «{query}» "
                    f"ничего нет. Попробуй без query — покажу свежие записи типа.")
        return ("Ничего не найдено. Попробуй другой запрос, фильтр по типу "
                "(type=\"рефлексия\" — твои дневники, type=\"сущность\" — люди и "
                "места), по связи (query=\"связь:друг\") или по времени "
                "(query=\"когда:вчера\" — периоды: сегодня/вчера/позавчера/"
                "неделя/месяц, можно с текстом: \"когда:вчера прогулка\").")

    from memory.unified import relative_time
    from memory.entity_schema import is_entity_card

    lines: list[str] = []
    shown_events: set[str] = set()

    for r in results:
        brief = (r.details.get("brief", "")
                 or r.details.get("description", "")
                 or r.details.get("attitude", ""))
        rel = relative_time(r.created_at)
        time_str = f", {rel}" if rel and r.type in ("событие", "рефлексия", "сущность") else ""
        etype = r.details.get("entity_type")
        type_label = f"{r.type}: {etype}" if etype else r.type
        line = f"- [{r.record_id}] «{r.title}» ({type_label}{time_str})"
        if brief:
            line += f" — {brief[:120]}"
        lines.append(line)
        opinion = r.details.get("my_opinion")
        if opinion and is_entity_card(r):
            lines.append(f"    ♥ моё мнение: {opinion[:200]}")

        if is_entity_card(r):
            related = mem.get_entity_events(r.record_id)[:3]
            for ev in related:
                if ev.record_id in shown_events:
                    continue
                shown_events.add(ev.record_id)
                ev_rel = relative_time(ev.created_at)
                ev_time = f", {ev_rel}" if ev_rel else ""
                ev_brief = (ev.details.get("description", "")
                            or ev.details.get("brief", ""))
                sub = f"    ↳ [{ev.record_id}] {ev.title} ({ev.type}{ev_time})"
                if ev_brief:
                    sub += f" — {ev_brief[:120]}"
                lines.append(sub)

    first_title = results[0].title if results else "название"
    lines.append(f"\nДля подробностей вызови: get_details(title=\"{first_title}\")")
    return "\n".join(lines)


def handle_get_details(args: dict, ctx: ToolContext) -> str:
    mem = ctx.memory
    if mem is None:
        return "Память недоступна."
    title = (args.get("title") or "").strip().strip("«»\"'")
    if not title:
        title = mem._get_self_name()
    if ctx.debug:
        print(f"\n[MEM] get_details(«{priv(title)}»)")
    tl = title.lower()
    exact = next((r for r in mem.records
                  if (r.record_id and r.record_id.lower() == tl)
                  or r.title.lower() == tl), None)
    if exact is not None:
        exact.last_accessed = time.time()
        exact.access_count += 1
        if ctx.debug:
            print(f"[MEM] → найдено (точно): {priv(exact.title)}")
        return exact.format_details()

    partial = [r for r in mem.records if not r.is_forgotten
               and (tl in r.title.lower() or r.title.lower() in tl)]
    if len(partial) == 1:
        rec = partial[0]
        rec.last_accessed = time.time()
        rec.access_count += 1
        return (f"(точного «{title}» нет; ближайшая запись — «{rec.title}»)\n"
                + rec.format_details())
    if partial:
        options = "\n".join(f"- «{r.title}» ({r.type})" for r in partial[:5])
        return (f"Под «{title}» подходит несколько записей:\n{options}\n"
                f"Вызови get_details с точным названием из списка.")

    near = mem.search(title, top_k=3)
    if ctx.debug and not near:
        print(f"[MEM] → НЕ найдено. Доступные: "
              f"{priv(', '.join(r.title for r in mem.records[:10]), 300)}")
    if len(near) == 1:
        return (f"(точного «{title}» нет; ближайшая запись — "
                f"«{near[0].title}»)\n" + near[0].format_details())
    if near:
        options = "\n".join(f"- «{r.title}» ({r.type})" for r in near)
        return (f"Запись «{title}» не найдена. Похожие:\n{options}\n"
                f"Вызови get_details с точным названием из списка.")
    return f"Запись '{title}' не найдена. Попробуй search_memory чтобы найти нужную запись."
