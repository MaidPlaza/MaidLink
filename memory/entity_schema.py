from __future__ import annotations

ENTITY_TYPE_USER_PROFILE = "профиль"
ENTITY_TYPE_PERSON = "персона"
ENTITY_TYPE_PLACE = "место"
ENTITY_TYPE_ORGANIZATION = "организация"
ENTITY_TYPE_TOPIC = "тема"

ALL_ENTITY_TYPES = (
    ENTITY_TYPE_USER_PROFILE,
    ENTITY_TYPE_PERSON,
    ENTITY_TYPE_PLACE,
    ENTITY_TYPE_ORGANIZATION,
    ENTITY_TYPE_TOPIC,
)


PROFILE_FIELDS = {
    "aliases":      "list[str] — как ещё можно назвать (редко для профиля)",
    "location":     "dict(*) — {city, country, lat, lon, timezone, ...}",
    "birthday":     "str — ISO дата 'YYYY-MM-DD'",
    "occupation":   "str — род занятий",
    "notes":        "list[str] — свободные заметки, которые не укладываются в структуру",
}

PERSON_FIELDS = {
    "aliases":         "list[str] — прозвища, уменьшительные, альтернативные формы",
    "relation_to_user":"str — категория связи с Господином: друг/семья/партнёр/коллега/знакомый/питомец (конкретику типа 'начальник' — в notes)",
    "occupation":      "str — род занятий",
    "location":        "dict(*) — где живёт/работает ({city} как минимум)",
    "age":             "str — возраст или год рождения",
    "traits":          "list[str] — краткие характеристики",
    "notes":           "list[str] — свободные заметки",
    "my_opinion":      "str — твоё личное отношение к этому человеку (1-2 фразы, эволюционирует автоматически)",
    "user_preference": "list[str] (до 3, новые вытесняют старые) — предпочтение/пожелание Господина насчёт этого человека (как он любит, чтобы было; авто)",
}

PLACE_FIELDS = {
    "aliases":   "list[str] — альтернативные названия",
    "kind":      "str — тип места ('город', 'кафе', 'работа', 'дом')",
    "city":      "str — город",
    "country":   "str — страна",
    "lat":       "float — широта",
    "lon":       "float — долгота",
    "notes":     "list[str] — свободные заметки",
    "my_opinion": "str — твоё личное впечатление от этого места (1-2 фразы, эволюционирует автоматически)",
    "user_preference": "list[str] (до 3, новые вытесняют старые) — предпочтение/пожелание Господина насчёт этого места (авто, эволюционирует)",
}

TOPIC_FIELDS = {
    "aliases":    "list[str] — как ещё можно назвать тему",
    "notes":      "list[str] — короткие факты/контекст по теме",
    "my_opinion": "str — твой ЛИЧНЫЙ взгляд на тему (1-2 фразы, эволюционирует)",
    "user_preference": "list[str] (до 3, новые вытесняют старые) — предпочтение Господина по этой теме/аспекту (как он любит, чтобы это делалось; авто)",
}

ORGANIZATION_FIELDS = {
    "aliases":  "list[str] — альтернативные названия",
    "kind":     "str — тип ('компания', 'университет', 'магазин')",
    "industry": "str — сфера деятельности",
    "notes":    "list[str] — свободные заметки",
    "my_opinion": "str — твоё личное отношение к организации (1-2 фразы, эволюционирует автоматически)",
    "user_preference": "list[str] (до 3, новые вытесняют старые) — предпочтение/пожелание Господина насчёт этой организации (авто, эволюционирует)",
}


OPINION_CAPABLE_TYPES = (
    ENTITY_TYPE_PERSON,
    ENTITY_TYPE_PLACE,
    ENTITY_TYPE_ORGANIZATION,
    ENTITY_TYPE_TOPIC,
)


RELATION_FRIEND = "друг"
RELATION_FAMILY = "семья"
RELATION_PARTNER = "партнёр"
RELATION_COLLEAGUE = "коллега"
RELATION_ACQUAINTANCE = "знакомый"
RELATION_PET = "питомец"

RELATION_CATEGORIES = (
    RELATION_FRIEND, RELATION_FAMILY, RELATION_PARTNER,
    RELATION_COLLEAGUE, RELATION_ACQUAINTANCE, RELATION_PET,
)

PINNED_RELATIONS = frozenset({RELATION_FRIEND, RELATION_FAMILY, RELATION_PARTNER})

_RELATION_ALIAS_RAW = {
    "друг": RELATION_FRIEND, "подруга": RELATION_FRIEND, "приятель": RELATION_FRIEND,
    "приятельница": RELATION_FRIEND, "товарищ": RELATION_FRIEND, "друзья": RELATION_FRIEND,
    "лучший друг": RELATION_FRIEND, "лучшая подруга": RELATION_FRIEND,
    "семья": RELATION_FAMILY, "родственник": RELATION_FAMILY, "родственница": RELATION_FAMILY,
    "родня": RELATION_FAMILY, "родители": RELATION_FAMILY, "родитель": RELATION_FAMILY,
    "мама": RELATION_FAMILY, "мать": RELATION_FAMILY, "папа": RELATION_FAMILY, "отец": RELATION_FAMILY,
    "брат": RELATION_FAMILY, "сестра": RELATION_FAMILY, "сын": RELATION_FAMILY, "дочь": RELATION_FAMILY,
    "ребёнок": RELATION_FAMILY, "бабушка": RELATION_FAMILY, "дедушка": RELATION_FAMILY,
    "тётя": RELATION_FAMILY, "дядя": RELATION_FAMILY, "племянник": RELATION_FAMILY,
    "племянница": RELATION_FAMILY, "кузен": RELATION_FAMILY, "кузина": RELATION_FAMILY,
    "партнёр": RELATION_PARTNER, "партнёрша": RELATION_PARTNER, "жена": RELATION_PARTNER,
    "муж": RELATION_PARTNER, "супруг": RELATION_PARTNER, "супруга": RELATION_PARTNER,
    "девушка": RELATION_PARTNER, "парень": RELATION_PARTNER, "любимый": RELATION_PARTNER,
    "любимая": RELATION_PARTNER, "невеста": RELATION_PARTNER, "жених": RELATION_PARTNER,
    "коллега": RELATION_COLLEAGUE, "начальник": RELATION_COLLEAGUE, "начальница": RELATION_COLLEAGUE,
    "босс": RELATION_COLLEAGUE, "шеф": RELATION_COLLEAGUE, "сотрудник": RELATION_COLLEAGUE,
    "подчинённый": RELATION_COLLEAGUE, "руководитель": RELATION_COLLEAGUE,
    "знакомый": RELATION_ACQUAINTANCE, "знакомая": RELATION_ACQUAINTANCE, "сосед": RELATION_ACQUAINTANCE,
    "соседка": RELATION_ACQUAINTANCE, "одноклассник": RELATION_ACQUAINTANCE,
    "однокурсник": RELATION_ACQUAINTANCE, "одногруппник": RELATION_ACQUAINTANCE,
    "питомец": RELATION_PET, "кот": RELATION_PET, "кошка": RELATION_PET, "собака": RELATION_PET,
    "пёс": RELATION_PET, "щенок": RELATION_PET, "котёнок": RELATION_PET, "попугай": RELATION_PET,
    "хомяк": RELATION_PET,
}

_CATEGORY_BY_ALIAS: dict[str, str] = {}


def normalize_relation(text: str) -> str:
    if not _CATEGORY_BY_ALIAS:
        for k, v in _RELATION_ALIAS_RAW.items():
            _CATEGORY_BY_ALIAS[normalize_alias(k)] = v
        for c in RELATION_CATEGORIES:
            _CATEGORY_BY_ALIAS[normalize_alias(c)] = c
    raw = normalize_alias(text)
    if not raw:
        return ""
    if raw in _CATEGORY_BY_ALIAS:
        return _CATEGORY_BY_ALIAS[raw]
    for alias, cat in _CATEGORY_BY_ALIAS.items():
        if alias and alias in raw:
            return cat
    return raw

FIELDS_BY_TYPE = {
    ENTITY_TYPE_USER_PROFILE: PROFILE_FIELDS,
    ENTITY_TYPE_PERSON: PERSON_FIELDS,
    ENTITY_TYPE_PLACE: PLACE_FIELDS,
    ENTITY_TYPE_ORGANIZATION: ORGANIZATION_FIELDS,
}


def schema_summary_for_prompt() -> str:
    lines: list[str] = ["Карточки сущностей (`type=сущность`) — долгоживущие объекты с полем `entity_type`:"]
    for etype in (ENTITY_TYPE_PERSON, ENTITY_TYPE_PLACE, ENTITY_TYPE_ORGANIZATION):
        fields = FIELDS_BY_TYPE[etype]
        field_keys = ", ".join(fields.keys())
        lines.append(f"  • {etype}: {field_keys}")
    lines.append(
        f"  • {ENTITY_TYPE_USER_PROFILE}: singleton для Господина "
        f"({', '.join(PROFILE_FIELDS.keys())})"
    )
    lines.append(
        "События/предпочтения/рефлексии имеют поле `links: [record_id]` — "
        "ссылки на карточки участников."
    )
    return "\n".join(lines)


PRED_WORKS_AT = "работает_в"
PRED_STUDIES_AT = "учится_в"
PRED_LIVES_IN = "живёт_в"
PRED_FROM = "родом_из"
PRED_RELATIVE = "родственник"
PRED_FRIEND_OF = "дружит_с"
PRED_KNOWS = "знаком_с"
PRED_LEADS = "руководит"
PRED_OWNS = "владеет"

RELATION_PREDICATES = (
    PRED_WORKS_AT, PRED_STUDIES_AT, PRED_LIVES_IN, PRED_FROM, PRED_RELATIVE,
    PRED_FRIEND_OF, PRED_KNOWS, PRED_LEADS, PRED_OWNS,
)

SYMMETRIC_PREDICATES = frozenset({PRED_RELATIVE, PRED_FRIEND_OF, PRED_KNOWS})

_PREDICATE_ALIAS_RAW = {
    "работает в": PRED_WORKS_AT, "работает": PRED_WORKS_AT, "сотрудник": PRED_WORKS_AT,
    "трудится в": PRED_WORKS_AT, "служит в": PRED_WORKS_AT,
    "учится в": PRED_STUDIES_AT, "студент": PRED_STUDIES_AT, "учащийся": PRED_STUDIES_AT,
    "живёт в": PRED_LIVES_IN, "проживает в": PRED_LIVES_IN, "обитает в": PRED_LIVES_IN,
    "родом из": PRED_FROM, "из города": PRED_FROM, "уроженец": PRED_FROM,
    "родственник": PRED_RELATIVE, "родня": PRED_RELATIVE, "брат": PRED_RELATIVE,
    "сестра": PRED_RELATIVE, "мама": PRED_RELATIVE, "мать": PRED_RELATIVE,
    "папа": PRED_RELATIVE, "отец": PRED_RELATIVE, "сын": PRED_RELATIVE, "дочь": PRED_RELATIVE,
    "родители": PRED_RELATIVE, "родитель": PRED_RELATIVE, "дядя": PRED_RELATIVE,
    "тётя": PRED_RELATIVE, "бабушка": PRED_RELATIVE, "дедушка": PRED_RELATIVE,
    "кузен": PRED_RELATIVE, "кузина": PRED_RELATIVE, "племянник": PRED_RELATIVE,
    "племянница": PRED_RELATIVE,
    "дружит с": PRED_FRIEND_OF, "друг": PRED_FRIEND_OF, "подруга": PRED_FRIEND_OF,
    "приятель": PRED_FRIEND_OF, "дружит": PRED_FRIEND_OF,
    "знаком с": PRED_KNOWS, "знакомый": PRED_KNOWS, "знает": PRED_KNOWS,
    "руководит": PRED_LEADS, "управляет": PRED_LEADS, "начальник": PRED_LEADS,
    "директор": PRED_LEADS, "глава": PRED_LEADS,
    "владеет": PRED_OWNS, "владелец": PRED_OWNS, "хозяин": PRED_OWNS, "основатель": PRED_OWNS,
}

_PREDICATE_BY_ALIAS: dict[str, str] = {}


def normalize_predicate(text: str) -> str:
    if not _PREDICATE_BY_ALIAS:
        for k, v in _PREDICATE_ALIAS_RAW.items():
            _PREDICATE_BY_ALIAS[normalize_alias(k)] = v
        for p in RELATION_PREDICATES:
            _PREDICATE_BY_ALIAS[normalize_alias(p).replace("_", " ")] = p
            _PREDICATE_BY_ALIAS[normalize_alias(p)] = p
    raw = normalize_alias(text)
    if not raw:
        return ""
    raw_us = raw.replace("_", " ")
    if raw in _PREDICATE_BY_ALIAS:
        return _PREDICATE_BY_ALIAS[raw]
    if raw_us in _PREDICATE_BY_ALIAS:
        return _PREDICATE_BY_ALIAS[raw_us]
    for alias, pred in _PREDICATE_BY_ALIAS.items():
        if alias and alias in raw_us:
            return pred
    return ""


EVENT_PRED_PARTICIPANT = "с_участием"
EVENT_PRED_LOCATED_AT = "произошло_в"
EVENT_PRED_ABOUT = "касается"
EVENT_PRED_FOR = "для"

EVENT_PREDICATES = (EVENT_PRED_PARTICIPANT, EVENT_PRED_LOCATED_AT,
                    EVENT_PRED_ABOUT, EVENT_PRED_FOR)

_EVENT_PREDICATE_ALIAS_RAW = {
    "с участием": EVENT_PRED_PARTICIPANT, "участник": EVENT_PRED_PARTICIPANT,
    "участвовал": EVENT_PRED_PARTICIPANT, "вместе с": EVENT_PRED_PARTICIPANT,
    "произошло в": EVENT_PRED_LOCATED_AT, "состоялось в": EVENT_PRED_LOCATED_AT,
    "случилось в": EVENT_PRED_LOCATED_AT, "прошло в": EVENT_PRED_LOCATED_AT,
    "касается": EVENT_PRED_ABOUT, "про": EVENT_PRED_ABOUT, "насчёт": EVENT_PRED_ABOUT,
    "относится к": EVENT_PRED_ABOUT, "о теме": EVENT_PRED_ABOUT,
    "для": EVENT_PRED_FOR, "кому": EVENT_PRED_FOR, "ради": EVENT_PRED_FOR,
    "для кого": EVENT_PRED_FOR,
}

_EVENT_PREDICATE_BY_ALIAS: dict[str, str] = {}


def normalize_event_predicate(text: str) -> str:
    if not _EVENT_PREDICATE_BY_ALIAS:
        for k, v in _EVENT_PREDICATE_ALIAS_RAW.items():
            _EVENT_PREDICATE_BY_ALIAS[normalize_alias(k)] = v
        for p in EVENT_PREDICATES:
            _EVENT_PREDICATE_BY_ALIAS[normalize_alias(p).replace("_", " ")] = p
            _EVENT_PREDICATE_BY_ALIAS[normalize_alias(p)] = p
    raw = normalize_alias(text)
    if not raw:
        return ""
    raw_us = raw.replace("_", " ")
    if raw in _EVENT_PREDICATE_BY_ALIAS:
        return _EVENT_PREDICATE_BY_ALIAS[raw]
    if raw_us in _EVENT_PREDICATE_BY_ALIAS:
        return _EVENT_PREDICATE_BY_ALIAS[raw_us]
    for alias, pred in _EVENT_PREDICATE_BY_ALIAS.items():
        if len(alias) >= 5 and alias in raw_us:
            return pred
    return ""


def normalize_any_predicate(text: str) -> str:
    return normalize_predicate(text) or normalize_event_predicate(text)


def infer_event_role(record_type: str, target_entity_type: str) -> str:
    if record_type in ("предпочтение", "рефлексия"):
        return EVENT_PRED_ABOUT
    if target_entity_type == ENTITY_TYPE_PLACE:
        return EVENT_PRED_LOCATED_AT
    if target_entity_type == ENTITY_TYPE_PERSON:
        return EVENT_PRED_PARTICIPANT
    return EVENT_PRED_ABOUT


def is_entity_card(record) -> bool:
    if getattr(record, "type", None) != "сущность":
        return False
    etype = (record.details or {}).get("entity_type")
    return etype in ALL_ENTITY_TYPES


def normalize_alias(text: str) -> str:
    s = (text or "").lower().replace("ё", "е")
    for q in ("«", "»", "“", "”", "„", '"', "'", "`"):
        s = s.replace(q, "")
    return " ".join(s.split())
