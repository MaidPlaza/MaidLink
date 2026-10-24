from __future__ import annotations

import json

from tools.registry import ToolContext, ToolRegistry


def make_get_help_handler(registry: ToolRegistry):
    def handle(args: dict, ctx: ToolContext) -> str:
        name = (args.get("tool") or args.get("name") or "").strip()
        if ctx.debug:
            print(f"[MEM] get_help({name!r})")

        if not name:
            lines = ["=== Доступные инструменты ===\n"]
            for t in registry.all():
                marker = "…" if t.tier == "rare" else " "
                lines.append(f"{marker} {t.summary}")
            lines.append(
                "\n… — редкий инструмент: в твоём наборе вызова его нет, "
                "сначала уточни детали через get_help(tool=...)."
            )
            lines.append("Для подробностей: get_help(tool=\"имя_инструмента\")")
            return "\n".join(lines)

        tool = registry.get(name)
        if not tool:
            return (f"Инструмент «{name}» не найден. "
                    "Вызови get_help() без аргумента чтобы увидеть список.")

        schema_json = json.dumps(tool.schema, ensure_ascii=False, indent=2)
        return (
            f"=== {tool.name} ===\n"
            f"Категория: {tool.capability} · тир: {tool.tier}\n\n"
            f"{tool.help}\n\n"
            f"--- JSON-схема параметров ---\n{schema_json}"
        )

    return handle
