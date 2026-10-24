from __future__ import annotations

import re

from services.log_privacy import priv
from tools.registry import ToolContext


_ALLOWED = ("персона", "место", "организация")

_STUB_VALUES = {
    "не указано", "не указан", "не указана",
    "не известно", "не известен", "неизвестно", "неизвестен",
    "нет данных", "нет данных.", "нет", "нету",
    "—", "-", "--", "n/a", "na", "none", "null", "unknown",
    "?", "??",
}

_LIST_SPLIT_RE = re.compile(r",|\.(?=\s|$)")


def _is_stub(value: str) -> bool:
    return value.strip().lower() in _STUB_VALUES


def handle_upsert_entity(args: dict, ctx: ToolContext) -> str:
    mem = ctx.memory
    if mem is None:
        return "Память недоступна."

    entity_type = (args.get("entity_type") or "").strip()
    name = (args.get("name") or "").strip()

    if entity_type not in _ALLOWED:
        return (f"Нужен entity_type: одно из {', '.join(_ALLOWED)}. "
                "Для профиля Господина используй set_location и подобные.")
    if not name:
        return "Нужно имя сущности — параметр `name` пустой."

    field_keys = (
        "aliases", "relation_to_user", "occupation", "location",
        "age", "traits", "notes", "kind", "city", "country",
        "lat", "lon", "industry",
    )
    fields: dict = {}
    for k in field_keys:
        if k not in args:
            continue
        v = args[k]
        if v in ("", None, []):
            continue
        if isinstance(v, str) and _is_stub(v):
            continue
        fields[k] = v

    dropped_stubs: list[str] = []
    for list_key in ("aliases", "traits", "notes"):
        v = fields.get(list_key)
        if v is None:
            continue
        if isinstance(v, str):
            items = [s.strip() for s in _LIST_SPLIT_RE.split(v)]
        else:
            items = [str(s).strip() for s in v]
        cleaned: list[str] = []
        for it in items:
            if not it:
                continue
            if _is_stub(it):
                dropped_stubs.append(f"{list_key}:{it}")
                continue
            cleaned.append(it)
        if cleaned:
            fields[list_key] = cleaned
        else:
            fields.pop(list_key, None)

    try:
        rec = mem.upsert_entity(entity_type, name, **fields)
    except ValueError as e:
        return f"Не получилось: {e}"

    if ctx.debug:
        print(f"[MEM] upsert_entity({entity_type!r}, «{priv(name)}») → {rec.record_id}")

    summary = f"Карточка «{rec.title}» ({entity_type}, id={rec.record_id}) сохранена."
    bits: list[str] = []
    if "relation_to_user" in fields:
        bits.append(f"связь: {fields['relation_to_user']}")
    if "occupation" in fields:
        bits.append(f"род занятий: {fields['occupation']}")
    if "location" in fields:
        loc = fields["location"]
        if isinstance(loc, dict) and loc.get("city"):
            bits.append(f"город: {loc['city']}")
    if "aliases" in fields:
        bits.append(f"алиасы: {', '.join(rec.details.get('aliases', []))}")
    if bits:
        summary += " " + "; ".join(bits) + "."
    return summary
