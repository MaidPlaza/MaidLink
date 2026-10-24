from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from memory.entity_schema import is_entity_card

MAX_INDEX_ENTITIES = 80
MAX_INDEX_RECENT = 10
MAX_RECALL_RECORDS = 8
MAX_AUX_LOOPS = 30
RAW_SEARCH_TOP_K = 5
RECALL_HEAD = 2
RECALL_CHAR_BUDGET = 2800


def _record_weight_chars(rec) -> int:
    d = getattr(rec, "details", None) or {}
    total = len(getattr(rec, "title", "") or "")
    for v in d.values():
        if isinstance(v, str):
            total += len(v)
        elif isinstance(v, list):
            total += sum(len(str(x)) for x in v[:6])
    return total


def build_memory_index(memory) -> str:
    from memory.entity_schema import PINNED_RELATIONS, normalize_relation
    cards = []
    for r in getattr(memory, "records", []):
        if not is_entity_card(r) or getattr(r, "is_forgotten", False):
            continue
        etype = (r.details or {}).get("entity_type", "")
        if etype == "профиль":
            continue
        rel = (r.details or {}).get("relation_to_user", "")
        pinned = normalize_relation(rel) in PINNED_RELATIONS
        cards.append((pinned, getattr(r, "created_at", 0.0) or 0.0, r, etype, rel))
    cards.sort(key=lambda c: (c[0], c[1]), reverse=True)
    lines: list[str] = []
    for _pinned, _ts, r, etype, rel in cards[:MAX_INDEX_ENTITIES]:
        tag = f"{etype}, {rel}" if rel else etype
        lines.append(f"  - [{r.record_id}] {r.title} ({tag})")
    return "\n".join(lines)


def build_recent_index(memory) -> str:
    pool = [r for r in getattr(memory, "records", [])
            if r.type in ("событие", "событие_план", "рефлексия")
            and not getattr(r, "is_forgotten", False)]
    pool.sort(key=lambda r: r.created_at, reverse=True)
    lines: list[str] = []
    for r in pool[:MAX_INDEX_RECENT]:
        when = _coarse_when(r.created_at)
        lines.append(f"  - [{r.record_id}] {r.title} ({r.type}"
                     + (f", {when}" if when else "") + ")")
    return "\n".join(lines)


def _coarse_when(ts: float) -> str:
    if not ts:
        return ""
    import datetime as _dt
    days = (_dt.date.today() - _dt.date.fromtimestamp(ts)).days
    if days <= 0:
        return "сегодня"
    if days == 1:
        return "вчера"
    if days == 2:
        return "позавчера"
    if days < 7:
        return f"{days} дн. назад"
    if days < 30:
        return f"{days // 7} нед. назад"
    return f"{days // 30} мес. назад"


@dataclass
class RetrievalPlan:
    recall: list = field(default_factory=list)
    queries: list = field(default_factory=list)
    absent: list = field(default_factory=list)


def build_aux_index(memory) -> str:
    from memory.loops import LOOP_SUBJ_MINE, LOOP_TYPE, is_open
    prefs = [r for r in getattr(memory, "records", [])
             if r.type == "предпочтение"
             and not getattr(r, "is_forgotten", False)]
    if hasattr(memory, "get_open_loops"):
        loops = list(memory.get_open_loops())
    else:
        loops = [r for r in getattr(memory, "records", [])
                 if r.type == LOOP_TYPE and is_open(r)
                 and not getattr(r, "is_forgotten", False)]
        loops.sort(key=lambda r: (getattr(r, "importance", 0.5),
                                  getattr(r, "created_at", 0.0) or 0.0), reverse=True)
    lines: list[str] = []
    for r in prefs[:15]:
        lines.append(f"  - [{r.record_id}] {r.title} (предпочтение)")
    for r in loops[:MAX_AUX_LOOPS]:
        d = r.details or {}
        kind = d.get("kind") or "петля"
        owner = "ассистента" if d.get("subject") == LOOP_SUBJ_MINE else "собеседника"
        lines.append(f"  - [{r.record_id}] {r.title} (петля: {kind} {owner})")
    return "\n".join(lines)


def _build_system(index: str, recent: str = "", aux: str = "") -> str:
    return (
        "Ты — система памяти ассистента. По реплике собеседника (придёт "
        "сообщением, с фоном разговора для понимания местоимений и отсылок; "
        "планируешь память ТОЛЬКО для последней реплики) реши, что ассистенту "
        "нужно ВСПОМНИТЬ, и отметь упоминания того, чего в памяти НЕТ. "
        "Ты НЕ отвечаешь собеседнику — только планируешь память. Верни СТРОГО JSON.\n\n"
        "Известные ассистенту сущности (карточки в памяти):\n"
        + (index or "  (пусто)") + "\n\n"
        "Недавние записи (события/планы/дневник — свежие сверху):\n"
        + (recent or "  (пусто)") + "\n\n"
        "Предпочтения и открытые петли — незакрытые обещания, цели, тянущиеся "
        "ситуации (важные и свежие сверху; «ассистента» — её собственное "
        "обещание, «собеседника» — его дело):\n"
        + (aux or "  (пусто)") + "\n\n"
        "Формат ответа:\n"
        '{"recall": ["<имя или [id] записи из списков выше, релевантной реплике>"], '
        '"queries": ["<короткий запрос про прошлые события/предпочтения, если нужно>"], '
        '"absent": ["<человек/место/факт, на который собеседник ссылается КАК НА '
        'ИЗВЕСТНЫЙ, но которого НЕТ в списках выше>"]}\n\n'
        "Правила:\n"
        "- recall: только реально релевантные реплике записи из СПИСКОВ выше — "
        "сущности (упомянуты прямо или явно подразумеваются «а как у него дела»), "
        "недавние записи (реплика продолжает недавнюю тему: «как договорились», "
        "«насчёт вчерашнего»), открытые петли (реплика про обещание, план или "
        "дело: «ты обещала…», «что я должен был…», «как там с…», «что у меня "
        "в субботу») и предпочтения, если реплика их касается. Обычно это 1-3 "
        "записи; НЕ перечисляй списки целиком. Если ничего — [].\n"
        "- absent: ТОЛЬКО когда собеседник говорит о ком-то/чём-то как об уже "
        "ИЗВЕСТНОМ тебе («помнишь Машу?», «как там твой проект?»), а этого нет в "
        "списках. НЕ помечай, если собеседник ЗНАКОМИТ с новым («это мой друг "
        "Виктор») — это не отсутствие, а новый факт.\n"
        "- queries: 0-2 коротких запроса, если реплика касается прошлых событий или "
        "предпочтений, которых не видно в списках. Для вопросов про КАТЕГОРИЮ людей "
        "(«все мои друзья», «кто мои коллеги», «вся семья») добавь сюда "
        "«связь:<категория>» — категории: друг/семья/партнёр/коллега/знакомый/питомец. "
        "Реплика про ПРОШЛОЕ с привязкой ко времени («что было вчера», «чем занимались "
        "на неделе») — начни query с «когда:<период>» (ТОЛЬКО сегодня/вчера/позавчера/"
        "неделя/месяц), можно с текстом после: «когда:вчера прогулка». Вопрос про то, "
        "ЧТО ПРОИСХОДИЛО / куда ходил / чем занимался — добавь тип: «тип:событие "
        "когда:неделя» (иначе период забьют дневник и открытые дела). Про БУДУЩЕЕ и "
        "дни недели («что у меня в субботу», «в среду собеседование») «когда:» не "
        "подходит — обычный запрос словами: «суббота планы». "
        "Иначе [].\n"
        "Только JSON, без пояснений."
    )


def _strlist(x) -> list[str]:
    if not isinstance(x, list):
        return []
    return [str(i).strip() for i in x if str(i).strip()]


def _parse(raw: str) -> RetrievalPlan | None:
    if not raw:
        return None
    m = re.search(r"\{.*\}", raw, flags=re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(d, dict):
        return None
    return RetrievalPlan(
        recall=_strlist(d.get("recall")),
        queries=_strlist(d.get("queries")),
        absent=_strlist(d.get("absent")),
    )


def plan_retrieval(user_text: str, memory, llm_chat,
                   context: str = "") -> RetrievalPlan | None:
    if not (user_text and user_text.strip()) or not getattr(memory, "records", None):
        return None
    from persona.mood_appraisal import _TRIVIAL_RX
    if _TRIVIAL_RX.match(user_text.strip()):
        return None
    system = _build_system(build_memory_index(memory),
                           build_recent_index(memory),
                           build_aux_index(memory))
    user = ""
    if context:
        user += ("Фон разговора (последние реплики — только для понимания "
                 "смысла):\n" + context + "\n\n")
    user += f"Реплика собеседника: {user_text.strip()}"
    try:
        raw = llm_chat(system, user)
    except Exception as e:
        print(f"[retrieval] LLM fail: {type(e).__name__}: {e}")
        return RetrievalPlan()
    plan = _parse(raw)
    if plan is None:
        print(f"[retrieval] план не разобран: {(raw or '')[:80]!r}")
        return RetrievalPlan()
    return plan


def _clean_ref(ref: str) -> str:
    ref = (ref or "").strip()
    m = re.match(r"^\[?r\d+\]?\s+(.+?)(?:\s*\([^)]*\))?\s*$", ref)
    if m and m.group(1).strip():
        return m.group(1).strip().strip("«»\"'")
    m2 = re.fullmatch(r"\[?(r\d+)\]?", ref)
    if m2:
        return m2.group(1)
    return ref.strip("«»\"'[] ").strip()


_REF_ID_RX = re.compile(r"^\[?(r\d+)\]?(?:\s|$)")
_FILTER_ONLY_RX = re.compile(r"^(?:(?:тип|когда|связь):\S+\s*)+$")


def _ref_id(ref: str) -> str:
    m = _REF_ID_RX.match((ref or "").strip())
    return m.group(1) if m else ""


def _resolve_ref(ref: str, memory):
    rid = _ref_id(ref)
    rec = memory.get_by_title(rid) if rid else None
    if rec is None:
        name = _clean_ref(ref)
        if name and name != rid:
            rec = memory.get_by_title(name)
    return rec


def execute_retrieval(plan: RetrievalPlan | None, memory, *,
                      max_records: int = MAX_RECALL_RECORDS,
                      user_text: str = ""):
    plan = plan or RetrievalPlan()
    recalled: list = []
    seen: set[str] = set()

    def _add(rec) -> None:
        if rec is None:
            return
        rid = getattr(rec, "record_id", None)
        if not rid or rid in seen:
            return
        seen.add(rid)
        recalled.append(rec)

    def _recall(refs) -> None:
        for ref in refs:
            rec = _resolve_ref(ref, memory)
            if rec is None:
                continue
            _add(rec)
            if is_entity_card(rec):
                for ev in (memory.get_entity_events(rec.record_id) or [])[:3]:
                    _add(ev)

    refs = list(plan.recall or [])
    _recall(refs[:RECALL_HEAD])

    queries = [q.strip() for q in (plan.queries or []) if q and q.strip()]
    for q in queries:
        if _FILTER_ONLY_RX.match(q):
            for rec in (memory.search(q, top_k=10) or []):
                _add(rec)

    if user_text and user_text.strip():
        for rec in (memory.search(user_text.strip(), top_k=RAW_SEARCH_TOP_K) or []):
            _add(rec)

    for q in queries:
        if not _FILTER_ONLY_RX.match(q):
            for rec in (memory.search(q, top_k=5) or []):
                _add(rec)

    _recall(refs[RECALL_HEAD:])

    confirmed_absent: list[str] = []
    for ref in (plan.absent or []):
        hits = memory.search(str(ref), top_k=1) or []
        if hits:
            _add(hits[0])
        else:
            confirmed_absent.append(str(ref))

    out: list = []
    budget = RECALL_CHAR_BUDGET
    for rec in recalled[:max_records]:
        w = _record_weight_chars(rec)
        if out and budget - w < 0:
            continue
        out.append(rec)
        budget -= w

    return out, confirmed_absent


def retrieve(user_text: str, memory, llm_chat, *,
             max_records: int = MAX_RECALL_RECORDS):
    plan = plan_retrieval(user_text, memory, llm_chat)
    if plan is None:
        return [], []
    return execute_retrieval(plan, memory, max_records=max_records,
                             user_text=user_text)
