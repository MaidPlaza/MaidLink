from __future__ import annotations

from memory.entity_schema import RELATION_PREDICATES, normalize_predicate
from services.log_privacy import priv
from tools.semantic import SemanticDeps, SemanticResult, make_semantic_tool


def _build_link_extract_system(deps: SemanticDeps) -> str:
    preds = ", ".join(RELATION_PREDICATES)
    return (
        "Ты — точный парсер связи между двумя сущностями. Из фразы извлеки тройку "
        "subject–predicate–object и верни СТРОГО JSON, без пояснений.\n\n"
        "Верни ровно такой вид:\n"
        '{"subject": "<имя сущности-кто>", "predicate": "<предикат>", '
        '"object": "<имя сущности-с кем/чем>"}\n\n'
        f"predicate — ОДИН из: {preds}. Близкие слова приводи к ним: брат/сестра/"
        "мама → родственник; «работает в» → работает_в; «живёт в» → живёт_в; "
        "директор → руководит.\n"
        "Правила:\n"
        "- subject и object — ИМЕНА реальных сущностей (людей/мест/организаций) из "
        "фразы, как названы.\n"
        "- Только если в фразе ЕСТЬ связь между двумя названными сущностями. Если "
        "связи нет — верни пустые строки.\n"
        "Только JSON."
    )


def _link_executor(parsed: dict, deps: SemanticDeps) -> SemanticResult:
    mem = deps.memory
    if mem is None:
        return SemanticResult(ok=False, message="Память недоступна — не смогла связать.")
    subj_name = str(parsed.get("subject") or "").strip()
    obj_name = str(parsed.get("object") or "").strip()
    predicate = str(parsed.get("predicate") or "").strip()
    if not subj_name or not obj_name or not predicate:
        return SemanticResult(ok=False,
                              message="Не разобрала связь — скажи: кто, с кем и как связан?")

    pred = normalize_predicate(predicate)
    if not pred:
        return SemanticResult(ok=False, message=f"Не поняла тип связи «{predicate}».")

    subj = mem.find_entity(subj_name)
    obj = mem.find_entity(obj_name)
    missing = []
    if subj is None:
        missing.append(subj_name)
    if obj is None:
        missing.append(obj_name)
    if missing:
        return SemanticResult(
            ok=False,
            message=f"Не нашла в памяти: {', '.join(missing)} — сначала расскажи о них.")
    if subj.record_id == obj.record_id:
        return SemanticResult(ok=False, message="Это одна и та же запись — связать нельзя.")

    if not mem.add_relation(subj.record_id, pred, obj.record_id):
        return SemanticResult(ok=False, message="Не удалось записать связь.")

    pretty = pred.replace("_", " ")
    facts = f"Связь записана: {subj.title} — {pretty} — {obj.title}."
    if deps.debug:
        print(f"[semantic:link_entities] {priv(subj.title)} -{pred}-> {priv(obj.title)}")
    return SemanticResult(
        message=facts, facts=facts,
        data={"subject": subj.record_id, "predicate": pred, "object": obj.record_id})


LINK_ENTITIES_HELP = """link_entities(intent) — связать две известные сущности.

Опиши ОДНОЙ фразой связь между двумя людьми/местами/организациями — тип связи
и кого с кем разберёт система.

Примеры intent:
  - «Виктор работает в Авито»
  - «Аня — сестра Виктора»
  - «Олег живёт в Питере»
  - «Виктор дружит с Олегом»

Типы связей: работает_в, учится_в, живёт_в, родом_из, родственник, дружит_с,
знаком_с, руководит, владеет.

Важно: обе сущности должны уже быть в памяти (сначала upsert_entity на каждую,
потом link_entities). Если кого-то нет — система честно скажет.
"""


LINK_ENTITIES_TOOL = make_semantic_tool(
    name="link_entities",
    description=(
        "Связать две УЖЕ известные сущности типизированной связью — например "
        "«Виктор работает в Авито», «Аня — сестра Виктора», «Олег живёт в Питере». "
        "Сначала сущности должны быть заведены (upsert_entity)."
    ),
    intent_arg_desc=(
        "Связь одной фразой: «Виктор работает в Авито», «Аня сестра Виктора», "
        "«Олег живёт в Питере»."
    ),
    summary=(
        "link_entities(intent) — связать две сущности (работает_в/родственник/"
        "живёт_в…). Скажи фразой кто с кем и как связан."
    ),
    help=LINK_ENTITIES_HELP,
    build_extract_system=_build_link_extract_system,
    executor=_link_executor,
    triggers=[
        "работает в", "работает на", "учится в", "живёт в", "живет в",
        "родом из", "брат", "сестра", "дружит", "родственник", "знаком",
        "руководит", "директор", "владеет", "коллег",
    ],
    capability="карточки_сущностей",
    ack=("Связь ПРИНЯТА и сейчас записывается (подтверждение с итогом придёт "
         "СЛЕДУЮЩЕЙ репликой через пару секунд). СЕЙЧАС ответь ОЧЕНЬ коротко в "
         "характере — ТОЛЬКО что приняла и сейчас свяжешь: например «Момент~», "
         "«Сейчас свяжу~». НЕ говори, что уже сохранено/записано, и НЕ называй "
         "сущности — это скажет следующая реплика. НЕ вызывай link_entities снова."),
    fail_message="Не разобрала связь — скажи иначе: кто, с кем и как связан?",
    empty_hint=("link_entities вызван без intent. Впиши одной фразой связь — "
                "например «Виктор работает в Авито». Если связывать нечего — ответь словами."),
)
