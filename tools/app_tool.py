from __future__ import annotations

from tools.registry import TIER_CONTEXTUAL, Tool, ToolContext


def handle_open_app(args: dict, ctx: ToolContext) -> str:
    name = str(args.get("name") or args.get("app") or "").strip()
    if not name:
        return "Скажи, какое приложение открыть (name)."
    from services.apps import find_app, launch_app
    match, candidates = find_app(name)
    if match is None:
        if candidates:
            opts = "\n".join(f"  - {a.name}" for a in candidates)
            return (f"Под «{name}» подходит несколько приложений — уточни, "
                    f"какое именно:\n{opts}")
        return (f"Не нашла «{name}» среди установленных приложений. Проверь "
                f"название (назови так, как оно в системе) или его нужно "
                f"сначала установить.")
    ok, res = launch_app(match)
    if not ok:
        return f"Не смогла запустить «{match.name}»: {res}."
    ctx.pending_actions.append({"kind": "app_opened", "name": match.name})
    if ctx.debug:
        print(f"[apps] launched {match.name!r}")
    return (f"Запустила «{match.name}» для Господина. Скажи ему об этом одной "
            f"фразой, своими словами.")


OPEN_APP_TOOL = Tool(
    name="open_app",
    tier=TIER_CONTEXTUAL,
    capability="приложения",
    triggers=["открой", "запусти", "включи", "open", "launch"],
    schema={
        "name": "open_app",
        "description": (
            "Запустить установленное на компьютере приложение по названию "
            "(по просьбе «открой/запусти …»). Запускается только уже "
            "установленное приложение, без аргументов. Для веб-ссылок — "
            "open_url, не это."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string",
                         "description": ("название приложения как в системе: "
                                         "«Steam», «Блокнот», «Google Chrome», "
                                         "«Discord»")},
            },
            "required": ["name"],
        },
    },
    handler=handle_open_app,
    summary=("open_app(name) — запустить установленное приложение по имени "
             "(Steam, Блокнот…); только запуск, без аргументов"),
    help=(
        "open_app(name) — открыть установленное приложение.\n\n"
        "Назови приложение так, как оно в системе (можешь перевести: «открой "
        "стим» → name=\"Steam\"). Матчинг нестрогий; если под названием "
        "подходит несколько — вернётся список, уточни у Господина.\n\n"
        "Когда НЕ использовать: сайт/ссылка — это open_url; «открой в ютубе "
        "трек» — тоже open_url (страница сервиса), а не приложение.\n"
        "Запускается ТОЛЬКО уже установленное; аргументы/файлы не передаются. "
        "Каждый запуск Господин видит плашкой."
    ),
)
