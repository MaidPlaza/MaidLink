from __future__ import annotations

from services.log_privacy import priv
from tools.semantic import SemanticDeps, SemanticResult, make_semantic_tool


def _build_event_extract_system(deps: SemanticDeps) -> str:
    return (
        "Ты — точный парсер ПРОИЗОШЕДШЕГО события. Из фразы извлеки суть эпизода и "
        "верни СТРОГО JSON, без пояснений.\n\n"
        "Верни ровно такой вид:\n"
        '{"title": "<краткое название события>", "description": "<детали, кратко>", '
        '"participants": ["<имя человека>", ...], "location": "<место или пусто>"}\n\n'
        "Правила:\n"
        "- title — короткое название в прошедшем времени («Поход в кафе с Виктором»).\n"
        "- participants — ИМЕНА других людей-участников. НЕ включай самого "
        "пользователя/Господина/«я»/«меня». Нет людей → пустой список [].\n"
        "- location — название места (кафе, заведение, город), если есть; иначе \"\".\n"
        "- description — что произошло, кратко и без выдумок. Нечего — \"\".\n"
        "- ТОЛЬКО если в фразе есть реально произошедшее событие. Если это мнение/"
        "вопрос/план на будущее — верни пустой title \"\".\n"
        "Только JSON."
    )


def _resolve_or_create(name: str, entity_type: str, mem, debug: bool = False):
    name = (name or "").strip().strip("«»\"'").strip()
    if not name:
        return None, ""
    found = mem.find_entity(name)
    if found is not None:
        return found.record_id, found.title
    try:
        rec = mem.upsert_entity(entity_type, name)
        if debug:
            print(f"[semantic:record_event] создана карточка [{entity_type}] {priv(name)}")
        return rec.record_id, rec.title
    except Exception as e:
        if debug:
            print(f"[semantic:record_event] не удалось создать «{priv(name)}»: {e}")
        return None, ""


def _event_executor(parsed: dict, deps: SemanticDeps) -> SemanticResult:
    mem = deps.memory
    if mem is None:
        return SemanticResult(ok=False, message="Память недоступна — не смогла записать событие.")

    title = str(parsed.get("title") or "").strip()
    if not title:
        return SemanticResult(ok=False,
                              message="Не разобрала событие — что именно произошло?")
    description = str(parsed.get("description") or "").strip()
    participants = parsed.get("participants") or []
    if isinstance(participants, str):
        participants = [participants]
    location = str(parsed.get("location") or "").strip()

    links: list[str] = []
    named: list[str] = []
    for p in participants:
        rid, ttl = _resolve_or_create(str(p), "персона", mem, deps.debug)
        if rid and rid not in links:
            links.append(rid)
            named.append(ttl)
    loc_title = ""
    if location:
        rid, ttl = _resolve_or_create(location, "место", mem, deps.debug)
        if rid and rid not in links:
            links.append(rid)
            loc_title = ttl

    details = {"description": description} if description else {}
    rec = mem.add_record("событие", title[:60], details, importance=0.5,
                         embed_text=f"{title} {description}".strip(), links=links)
    mem.save()
    if deps.debug:
        print(f"[semantic:record_event] «{priv(title)}» links={links} → id={rec.record_id}")

    bits = []
    if named:
        bits.append("с участием " + ", ".join(named))
    if loc_title:
        bits.append(f"в «{loc_title}»")
    tail = f" ({'; '.join(bits)})" if bits else ""
    facts = f"Событие записано: «{title}»{tail}."
    return SemanticResult(message=facts, facts=facts,
                          data={"record_id": rec.record_id, "links": links})


RECORD_EVENT_HELP = """record_event(intent) — записать ПРОИЗОШЕДШЕЕ событие.

Опиши ОДНОЙ фразой эпизод, который случился — кто, что, где. Система сама создаст
запись и свяжет её с людьми/местом (если их ещё нет в памяти — заведёт карточки).

Примеры intent:
  - «Виктор водил меня в кафе Пушкин, классно посидели»
  - «вчера встретился с Аней в парке»
  - «съездили с Олегом на рыбалку на выходных»

Чем отличается от соседей:
  - plan_event   — БУДУЩЕЕ (план/встреча с датой).
  - record_event — ПРОШЛОЕ/общее (что уже произошло).
  - upsert_entity — карточка человека/места (не эпизод).

Событие попадёт в граф: при упоминании участника/места всплывёт автоматически
(«где был Виктор» → кафе; recall Виктора покажет это событие).
"""


RECORD_EVENT_TOOL = make_semantic_tool(
    name="record_event",
    description=(
        "Записать ПРОИЗОШЕДШЕЕ событие/эпизод — «Виктор водил меня в кафе Пушкин», "
        "«встретился с Аней в парке». Система свяжет его с участниками и местом "
        "(заведёт карточки, если их нет). Для БУДУЩИХ планов — plan_event."
    ),
    intent_arg_desc=(
        "Что произошло, одной фразой: «Виктор водил меня в кафе Пушкин», «вчера "
        "встретился с Аней в парке». Кто/где разберёт система."
    ),
    summary=(
        "record_event(intent) — записать произошедшее событие (кто/что/где); "
        "свяжет с участниками и местом. Для будущего — plan_event."
    ),
    help=RECORD_EVENT_HELP,
    build_extract_system=_build_event_extract_system,
    executor=_event_executor,
    triggers=[
        "вчера", "позавчера", "на выходных", "недавно", "сегодня утром",
        "сходил", "сходили", "ходил", "ходили", "съездил", "съездили",
        "побывал", "встретил", "встретился", "встретились", "посидел",
        "посидели", "посмотрел", "посмотрели", "отметил", "отметили",
        "случилось", "произошло", "сводил", "водил", "погуляли",
    ],
    capability="карточки_сущностей",
    ack=("Событие ПРИНЯТО и сейчас записывается (подтверждение с итогом придёт "
         "СЛЕДУЮЩЕЙ репликой через пару секунд). СЕЙЧАС ответь ОЧЕНЬ коротко в "
         "характере — ТОЛЬКО что приняла и сейчас запишу: например «Момент~», "
         "«Сейчас запишу~». НЕ говори, что уже записано, и НЕ перечисляй детали — "
         "это скажет следующая реплика. НЕ вызывай record_event снова."),
    fail_message="Не разобрала событие — скажи иначе: что произошло, с кем и где?",
    empty_hint=("record_event вызван без intent. Впиши одной фразой, что произошло — "
                "например «Виктор водил меня в кафе Пушкин». Если события нет — ответь словами."),
)
