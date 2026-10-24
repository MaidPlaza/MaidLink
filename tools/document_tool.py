from __future__ import annotations

from tools.registry import TIER_CONTEXTUAL, Tool, ToolContext


def handle_search_document(args: dict, ctx: ToolContext) -> str:
    att = getattr(ctx, "document", None)
    if att is None:
        return ("Сейчас к разговору не приложен ни один документ. Попроси "
                "Господина перетащить файл (.txt/.md/.pdf) в чат.")
    query = str(args.get("query") or "").strip()
    if not query:
        return "Скажи, что искать в документе (query)."
    from services.documents import search_chunks
    if att.mode == "full":
        return (f"Документ «{att.name}» небольшой — его полный текст уже в "
                f"твоём контексте (блок <документ>), ищи глазами.")
    emb = []
    mem = ctx.memory
    client = getattr(mem, "_client", None) if mem is not None else None
    if client is not None:
        try:
            emb = client.embed(query) or []
        except Exception:
            emb = []
    hits = search_chunks(att, query=query, query_embedding=emb)
    if not hits:
        return (f"В «{att.name}» ничего похожего на «{query}» не нашла — "
                f"попробуй другие слова.")
    joined = "\n---\n".join(h[:2000] for h in hits)
    return f"Из «{att.name}» по запросу «{query}»:\n{joined}"


SEARCH_DOCUMENT_TOOL = Tool(
    name="search_document",
    tier=TIER_CONTEXTUAL,
    capability="документы",
    triggers=["документ", "файл", "в тексте", "найди в"],
    schema={
        "name": "search_document",
        "description": ("Найти место в приложенном к разговору документе "
                        "(когда он объёмный и не весь в контексте)."),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string",
                          "description": "что ищем: тема, фраза, термин"},
            },
            "required": ["query"],
        },
    },
    handler=handle_search_document,
    summary=("search_document(query) — найти место в приложенном документе "
             "(объёмные не влезают в контекст целиком)"),
    help=(
        "search_document(query) — поиск по документу, который Господин "
        "перетащил в чат.\n\n"
        "Мелкие документы целиком лежат в <документ> — инструмент нужен для "
        "ОБЪЁМНЫХ (в контексте только начало). Релевантные куски и так "
        "подкладываются в <из_документа> под реплику — инструментом ищи, "
        "когда нужно КОНКРЕТНОЕ место («что там про гарантию?»)."
    ),
)
