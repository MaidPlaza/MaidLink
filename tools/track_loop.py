from __future__ import annotations

from memory.loops import (
    LOOP_KINDS, LOOP_KIND_SITUATION, LOOP_STATUS_OPEN, LOOP_SUBJ_MINE,
    default_salience, importance_from_word, normalize_loop_kind,
    normalize_loop_salience, normalize_loop_subject,
)
from services.log_privacy import priv
from tools.semantic import SemanticDeps, SemanticResult, make_semantic_tool


def _build_loop_extract_system(deps: SemanticDeps) -> str:
    return (
        "Ты — точный парсер открытой «петли»: незакрытой ЦЕЛИ, ОБЕЩАНИЯ или "
        "тянущейся СИТУАЦИИ. Из фразы извлеки структуру и верни СТРОГО JSON.\n\n"
        "Верни ровно такой вид:\n"
        '{"kind": "цель|обещание|ситуация", "subject": "пользователь|моё", '
        '"title": "<кратко суть>", "description": "<детали или пусто>", '
        '"about": ["<имя сущности, кого/чего касается>", ...], '
        '"target": "<имя ЧЕЛОВЕКА, КОМУ дано обещание; иначе пусто>", '
        '"salience": "активная|фоновая", "importance": "низкая|средняя|высокая"}\n\n'
        "subject — смотри, КТО действующее лицо во фразе:\n"
        "- Назван ПОЛЬЗОВАТЕЛЬ («Господин», «он», «у него», «ему») → subject "
        "«пользователь» ВСЕГДА. Любые ЕГО цели/дела/обещания — включая «обещал "
        "помочь брату», «обещал маме позвонить», «хочет накопить», «у него переезд». "
        "Не важно, что за действие — раз делает пользователь, это «пользователь».\n"
        "- Действующее лицо — сам АССИСТЕНТ («я», «сама», «буду», «обещаю», «хочу "
        "научиться»):\n"
        "   • ЦИФРОВОЕ действие (запомнить и вернуться к теме, спросить позже, "
        "сделать селфи/картинку, поддержать словом, сформулировать мнение, лучше "
        "понимать пользователя) → «моё».\n"
        "   • ФИЗИЧЕСКОЕ действие (связать, приготовить, позвонить, сходить, "
        "принести, починить, обнять) — ассистент так НЕ может. Это НЕ петля: верни "
        "пустой title \"\".\n"
        "- Неясно, кто действует → «пользователь».\n\n"
        "Остальное:\n"
        "- kind: цель — мечта/стремление («хочет», «мечтает»); ситуация — уже "
        "идущий процесс («идёт переезд», «ищет работу», «ремонт», «отпуск»); "
        "обещание — взятое обязательство кому-то.\n"
        "- target — имя ЧЕЛОВЕКА-бенефициара, КОМУ дано обещание; НЕ сам "
        "обещающий и НЕ «Господин» по умолчанию. Не назван явно — пусто.\n"
        "- about — имена людей/мест/организаций, которых петля касается (если есть).\n"
        "- importance — насколько важно: обязательства и явные цели — выше; "
        "фоновые ситуации — ниже.\n"
        "- salience: «активная» если требует возвратов/действий; «фоновая» если это "
        "просто фон-контекст (тянущаяся ситуация — обычно фоновая).\n"
        "- Только если в фразе ЕСТЬ незакрытое. Иначе title \"\".\n"
        "Только JSON."
    )


def _find_similar_open_loop(mem, title: str, subject: str):
    from memory.loops import LOOP_STATUS_OPEN, LOOP_TYPE, same_loop_title
    if not (title or "").strip():
        return None
    for r in getattr(mem, "records", []):
        if getattr(r, "type", "") != LOOP_TYPE:
            continue
        d = r.details or {}
        if d.get("status", LOOP_STATUS_OPEN) != LOOP_STATUS_OPEN:
            continue
        if subject and d.get("subject") and d.get("subject") != subject:
            continue
        if same_loop_title(r.title or "", title):
            return r
    return None


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
            print(f"[semantic:track_loop] создана карточка [{entity_type}] {priv(name)}")
        return rec.record_id, rec.title
    except Exception as e:
        if debug:
            print(f"[semantic:track_loop] не удалось создать «{priv(name)}»: {e}")
        return None, ""


def _loop_executor(parsed: dict, deps: SemanticDeps) -> SemanticResult:
    mem = deps.memory
    if mem is None:
        return SemanticResult(ok=False, message="Память недоступна — не смогла запомнить.")

    title = str(parsed.get("title") or "").strip()
    if not title:
        return SemanticResult(ok=False,
                              message="Не разобрала — что за цель/обещание/ситуация?")

    kind = normalize_loop_kind(parsed.get("kind")) or LOOP_KIND_SITUATION
    subject = normalize_loop_subject(parsed.get("subject"))
    salience = normalize_loop_salience(parsed.get("salience")) or default_salience(kind, subject)
    importance = importance_from_word(parsed.get("importance"), kind, subject)
    description = str(parsed.get("description") or "").strip()

    existing = _find_similar_open_loop(mem, title, subject)
    if existing is not None:
        import time as _t
        from memory.loops import refresh_loop_interest
        refresh_loop_interest(existing, deps.now or _t.time())
        ed = existing.details if existing.details is not None else {}
        if importance > (existing.importance or 0.0):
            existing.importance = importance
        if description and not ed.get("description"):
            ed["description"] = description
        existing.details = ed
        mem.save()
        if deps.debug:
            print(f"[semantic:track_loop] рекиндл «{priv(existing.title)}» (интерес освежён)")
        facts = f"Это уже на заметке — освежила: «{existing.title}»."
        return SemanticResult(message=facts, facts=facts,
                              data={"record_id": existing.record_id, "refreshed": True})

    about = parsed.get("about") or []
    if isinstance(about, str):
        about = [about]
    target = str(parsed.get("target") or "").strip()

    links: list[str] = []
    edges: list[tuple[str, str]] = []
    about_titles: list[str] = []
    for a in about:
        a = str(a).strip().strip("«»\"'").strip()
        if not a:
            continue
        found = mem.find_entity(a)
        if found is not None and found.record_id not in links:
            links.append(found.record_id)
            edges.append(("касается", found.record_id))
            about_titles.append(found.title)
    target_title = ""
    if target:
        rid, ttl = _resolve_or_create(target, "персона", mem, deps.debug)
        if rid and rid not in links:
            links.append(rid)
            edges.append(("для", rid))
            target_title = ttl

    details = {"kind": kind, "subject": subject, "status": LOOP_STATUS_OPEN,
               "salience": salience}
    if description:
        details["description"] = description
    rec = mem.add_record("петля", title[:80], details, importance=importance,
                         embed_text=f"{title} {description}".strip(), links=links)
    for pred, tid in edges:
        mem.add_relation(rec.record_id, pred, tid)
    mem.save()
    if deps.debug:
        print(f"[semantic:track_loop] [{kind}/{subject}/{salience} imp={importance:.2f}] "
              f"«{priv(title)}» edges={edges} → id={rec.record_id}")

    whose = "Моё" if subject == LOOP_SUBJ_MINE else "Пользователя"
    bits = []
    if target_title:
        bits.append(f"для {target_title}")
    if about_titles:
        bits.append("касается " + ", ".join(about_titles))
    tail = f" ({'; '.join(bits)})" if bits else ""
    facts = f"{whose} {kind}: «{title}»{tail}. Открыта, важность {importance:.1f}."
    return SemanticResult(message=facts, facts=facts,
                          data={"record_id": rec.record_id, "kind": kind,
                                "subject": subject, "importance": importance})


TRACK_LOOP_HELP = """track_loop(intent) — открыть «петлю»: незакрытую цель, обещание
или тянущуюся ситуацию, к которой стоит возвращаться.

Опиши ОДНОЙ фразой. Система определит, чьё это и что требует, и встроит в граф.
Цели и ситуации пользователя записывай ТИХО (фоном), без вопроса «записать ли?».

Примеры intent:
  - «Господин хочет накопить на машину»            (цель пользователя → фоллоу-ап)
  - «у Господина сейчас идёт переезд в Москву»     (ситуация → фон)
  - «Господин обещал позвонить маме»               (обещание пользователя → для мамы)
  - «я буду спрашивать, как у него идёт поиск работы»  (МОЁ — то, что я реально могу)

ЧЬЁ обязательство (subject):
  - почти всегда «пользователь» — это его дела/цели/обещания.
  - «моё» — ТОЛЬКО то, что я как цифровая горничная реально могу: помнить и
    вернуться к теме, спросить позже, сделать селфи/картинку, иметь мнение.
    Я НЕ звоню, не вяжу, не готовлю, никуда не хожу — такое не обещаю и в «моё»
    не записываю (если просят физическое — мягко откажи, петлю не заводи).

Чем отличается:
  - record_event — то, что УЖЕ произошло (закрыто).
  - plan_event   — конкретное событие с ДАТОЙ.
  - track_loop   — НЕЗАКРЫТОЕ, тянущееся, без жёсткой даты.

Важность (importance) ставь сам — за важные обязательства берись первым.

Если пользователь ПРОСИТ напомнить в конкретное время — ДОПОЛНИТЕЛЬНО вызови
set_reminder (петля хранит саму тему, напоминание — таймер).
"""


TRACK_LOOP_TOOL = make_semantic_tool(
    name="track_loop",
    description=(
        "Открыть «петлю» — незакрытую ЦЕЛЬ, ОБЕЩАНИЕ или тянущуюся СИТУАЦИЮ "
        "пользователя, к которой стоит возвращаться: «хочет накопить на машину», "
        "«у него идёт переезд», «обещал маме позвонить». Записывай тихо, фоном. "
        "Для УЖЕ случившегося — record_event; для события с датой — plan_event."
    ),
    intent_arg_desc=(
        "Цель/обещание/ситуация одной фразой: «Господин хочет накопить на машину», "
        "«у него идёт переезд», «обещал маме позвонить»."
    ),
    summary=(
        "track_loop(intent) — открыть петлю: цель/обещание/тянущаяся ситуация "
        "(незакрытое, без даты). Важные обязательства — с высокой importance."
    ),
    help=TRACK_LOOP_HELP,
    build_extract_system=_build_loop_extract_system,
    executor=_loop_executor,
    triggers=[
        "хочу", "хочет", "мечта", "мечтает", "цель", "обещаю", "обещал",
        "обещала", "клянусь", "планирует переехать", "переезд", "ремонт",
        "ищет работу", "поиск работы", "ищу работу", "отпуск", "собирается",
        "научиться", "накопить", "хочется",
    ],
    capability="карточки_сущностей",
    ack=("Петля ПРИНЯТА и сейчас открывается (подтверждение с итогом придёт "
         "СЛЕДУЮЩЕЙ репликой через пару секунд). СЕЙЧАС ответь ОЧЕНЬ коротко в "
         "характере — ТОЛЬКО что приняла: например «Запомню~», «Беру на заметку~». "
         "НЕ перечисляй детали — это скажет следующая реплика. НЕ вызывай track_loop снова."),
    fail_message="Не разобрала — это цель, обещание или тянущаяся ситуация? Скажи иначе.",
    empty_hint=("track_loop вызван без intent. Впиши одной фразой цель/обещание/"
                "ситуацию — например «обещаю связать шарф». Если нечего — ответь словами."),
)
