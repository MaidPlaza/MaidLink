from __future__ import annotations

from tools.change_outfit import CHANGE_OUTFIT_TOOL
from tools.draw import DRAW_TOOL
from tools.list_outfits import LIST_OUTFITS_TOOL
from tools.end_session import END_SESSION_TOOL
from tools.entity_tool import handle_upsert_entity
from tools.help_tool import make_get_help_handler
from tools.memory_tools import handle_search_memory, handle_get_details
from tools.planning import PLAN_EVENT_TOOL, UPDATE_EVENT_TOOL
from tools.reminder import (CANCEL_REMINDER_TOOL, LIST_REMINDERS_TOOL,
                            SET_REMINDER_TOOL)
from tools.registry import (
    TIER_CONTEXTUAL,
    TIER_CORE,
    Tool,
    ToolRegistry,
)
from tools.time_tool import handle_get_time
from tools.weather_handlers import handle_get_weather, handle_set_location


def register_builtin_tools(registry: ToolRegistry) -> None:
    from memory.unified import SEARCHABLE_TYPES

    registry.register(Tool(
        name="search_memory",
        tier=TIER_CORE,
        capability="память",
        schema={
            "name": "search_memory",
            "description": (
                "Поиск в твоей долговременной памяти: люди, места и организации "
                "(сущности), события, планы, предпочтения Господина, твои "
                "дневниковые записи (рефлексии), навыки, незакрытые обещания (петли)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": ("Что искать: имя, тема, ключевые слова. Можно "
                                        "опустить, если задан type — тогда вернутся "
                                        "свежие записи этого типа."),
                    },
                    "type": {
                        "type": "string",
                        "enum": list(SEARCHABLE_TYPES),
                        "description": ("Фильтр по типу записи. рефлексия — твои "
                                        "дневники (мысли после прошлых встреч); "
                                        "событие_план — планы; сущность — карточки "
                                        "людей/мест/организаций; петля — незакрытые "
                                        "обещания и цели."),
                    },
                },
                "required": [],
            },
        },
        handler=handle_search_memory,
        summary=("search_memory(query, type) — поиск по памяти; type=рефлексия — "
                 "твои дневники, событие_план — планы, сущность — люди/места"),
        help=(
            "search_memory(query, type) — поиск записей в твоей долговременной памяти\n\n"
            "Параметры (нужен хотя бы один):\n"
            "  query — что искать: имя, тема, ключевые слова\n"
            f"  type  — фильтр по типу записи: {', '.join(SEARCHABLE_TYPES)}\n"
            "          (рефлексия = твои дневники; событие_план = планы; сущность = "
            "карточки людей/мест/организаций; петля = незакрытые обещания/цели)\n\n"
            "Примеры аргументов:\n"
            "  query=\"Виктор\" — всё о Викторе (карточка + связанные события)\n"
            "  type=\"рефлексия\" — твои последние дневниковые записи\n"
            "  query=\"поездка\", type=\"событие_план\" — планы про поездку\n"
            "  query=\"связь:друг\" — все люди этой категории отношений "
            "(связь:семья, связь:коллега)\n"
            "  query=\"когда:вчера\" — записи за период (сегодня/вчера/"
            "позавчера/неделя/месяц), можно с темой: \"когда:неделя прогулки\"\n\n"
            "Подробности конкретной записи — get_details(title) по названию из результатов."
        ),
    ))

    registry.register(Tool(
        name="get_details",
        tier=TIER_CORE,
        capability="память",
        schema={
            "name": "get_details",
            "description": "Узнать подробности о конкретной записи из памяти по её названию",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Название записи из результатов поиска"},
                },
                "required": ["title"],
            },
        },
        handler=handle_get_details,
        summary="get_details(title) — подробности записи",
        help=(
            "get_details(title) — подробности о конкретной записи\n\n"
            "title — название записи или её ID (r1, r2...) из результатов search_memory\n\n"
            "Примеры аргументов:\n"
            "  title=\"Анализ информации\"\n"
            "  title=\"r5\""
        ),
    ))

    registry.register(Tool(
        name="get_time",
        tier=TIER_CORE,
        capability="время",
        schema={
            "name": "get_time",
            "description": "Узнать текущее время, день недели и время суток",
            "parameters": {"type": "object", "properties": {}},
        },
        handler=handle_get_time,
        summary="get_time() — текущее время и день недели",
        help=(
            "get_time() — текущее время и день недели\n\n"
            "Вызывай когда спрашивают время или день. Параметров нет."
        ),
    ))

    registry.register(Tool(
        name="get_help",
        tier=TIER_CORE,
        capability="справка",
        schema={
            "name": "get_help",
            "description": "Получить инструкцию по инструменту. Без аргумента — список всех.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string", "description": "Название инструмента (опционально)"},
                },
            },
        },
        handler=make_get_help_handler(registry),
        summary="get_help(tool) — справка и схема параметров",
        help=(
            "get_help(tool) — справка по инструменту\n\n"
            "Без аргумента — список всех инструментов (включая редкие).\n"
            "С аргументом — текст + JSON-схема параметров.\n\n"
            "Пример аргументов: tool=\"plan_event\""
        ),
    ))

    registry.register(Tool(
        name="get_weather",
        tier=TIER_CONTEXTUAL,
        capability="погода_и_локация",
        triggers=[
            "погод", "дождь", "снег", "солнечно", "холодно", "тепло",
            "сколько градус", "прогноз", "метеосводк", "что на улице",
            "как на улице",
        ],
        schema={
            "name": "get_weather",
            "description": "Погода сейчас или прогноз до недели.",
            "parameters": {
                "type": "object",
                "properties": {
                    "when": {
                        "type": "string",
                        "description": "когда — 'сейчас'/'сегодня'/'завтра', день недели или дата (опц)",
                    },
                    "city": {
                        "type": "string",
                        "description": "город (опц, иначе из профиля)",
                    },
                },
            },
        },
        handler=handle_get_weather,
        summary=(
            "get_weather(when, city) — погода сейчас и прогноз на неделю "
            "(when: 'сейчас'/'завтра'/'в пятницу'/дата; city — опц., иначе из профиля)"
        ),
        help=(
            "get_weather(when, city) — погода сейчас или прогноз на ближайшие дни\n\n"
            "Параметры (оба опциональные):\n"
            "  when — 'сейчас' / пусто, 'сегодня', 'завтра', 'послезавтра',\n"
            "         день недели ('в пятницу'), 'на выходных',\n"
            "         дата ('20 апреля', '2026-04-20'),\n"
            "         можно уточнить время суток: 'завтра утром', 'вечером'.\n"
            "  city — город для РАЗОВОГО запроса (не сохраняется в профиль).\n"
            "         Передавай когда Господин сам назвал город в реплике.\n"
            "         Если пусто — берётся город из профиля.\n\n"
            "Логика:\n"
            "  - Город известен из профиля и Господин не уточнял → вызывай без city.\n"
            "  - Господин назвал город в реплике → передай его в city.\n"
            "  - Профиля нет и город не назван → инструмент сам предложит\n"
            "    вызвать set_location. Не выдумывай город.\n\n"
            "Примеры аргументов:\n"
            "  when=\"завтра вечером\"\n"
            "  when=\"сейчас\", city=\"Париж\""
        ),
    ))

    registry.register(Tool(
        name="set_location",
        tier=TIER_CONTEXTUAL,
        capability="погода_и_локация",
        triggers=[
            "я живу в", "я из ", "переехал в", "переехала в",
            "мой город", "запомни что я", "запомни мой город",
        ],
        schema={
            "name": "set_location",
            "description": "Сохранить домашний город Господина в профиль.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "название города",
                    },
                },
                "required": ["city"],
            },
        },
        handler=handle_set_location,
        summary="set_location(city) — запомнить домашний город",
        help=(
            "set_location(city) — запомнить домашний город Господина\n\n"
            "Вызывай когда Господин:\n"
            "  - говорит где он живёт («я из Москвы», «переехал в Питер»)\n"
            "  - сам просит запомнить\n"
            "  - инструмент get_weather сообщил что город неизвестен,\n"
            "    и Господин только что его назвал\n\n"
            "Перезаписывает предыдущее значение — подтверждать у Господина\n"
            "не нужно, просто сохраняй.\n\n"
            "Пример аргументов: city=\"Санкт-Петербург\""
        ),
    ))

    registry.register(PLAN_EVENT_TOOL)

    registry.register(UPDATE_EVENT_TOOL)

    _UNREGISTERED_upsert_entity = (Tool(
        name="upsert_entity",
        tier=TIER_CONTEXTUAL,
        capability="карточки_сущностей",
        triggers=[
            "друг", "подруг", "подруж",
            "коллег",
            "мам", "пап", "сестр", "брат",
            "муж", "жен", "парн", "парень", "девушк",
            "сын", "доч",
            "начальник", "босс",
            "родител", "семь",
            "знаком",
            "моего ", "моему ", "моим ", "моём ", "моей ", "мою ",
            "со своим ", "со своей ", "своего ", "своей ", "своим ",
            "работаю в", "работает в", "учусь в", "учится в",
            "живу в", "живёт в", "живет в", "переехал в",
            "наш офис", "наша компания", "моя фирма",
        ],
        schema={
            "name": "upsert_entity",
            "description": "Создать/обновить карточку (персона/место/организация). Дубликаты по name+aliases объединяются.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_type": {"type": "string", "description": "'персона' / 'место' / 'организация'"},
                    "name": {"type": "string", "description": "основное имя"},
                    "aliases": {"type": "string", "description": "варианты имени через запятую (опц)"},
                    "relation_to_user": {"type": "string", "description": "кем приходится Господину — для персоны (опц)"},
                    "occupation": {"type": "string", "description": "род занятий (опц)"},
                    "city": {"type": "string", "description": "город (опц)"},
                    "country": {"type": "string", "description": "страна (опц)"},
                    "kind": {"type": "string", "description": "тип места/организации (опц)"},
                    "industry": {"type": "string", "description": "сфера — для организации (опц)"},
                    "traits": {"type": "string", "description": "короткие характеристики через запятую (опц)"},
                    "notes": {"type": "string", "description": "короткие устойчивые факты через запятую (опц)"},
                },
                "required": ["entity_type", "name"],
            },
        },
        handler=handle_upsert_entity,
        summary=(
            "upsert_entity(entity_type, name, …) — создать/обновить карточку "
            "(entity_type: 'персона'|'место'|'организация'; для персоны: "
            "relation_to_user, occupation, traits, notes)"
        ),
        help=(
            "upsert_entity(entity_type, name, …) — создать или обновить карточку сущности\n\n"
            "Зачем: чтобы у каждого упомянутого человека, места или организации была одна "
            "карточка с атрибутами (отношение к Господину, профессия, город, заметки). "
            "Тогда события и предпочтения могут ссылаться на карточку через поле `links`, "
            "и search_memory при запросе по имени будет возвращать карточку + связанные события.\n\n"
            "Обязательные параметры:\n"
            "  entity_type — 'персона' / 'место' / 'организация'\n"
            "  name        — основное имя\n\n"
            "Опциональные поля:\n"
            "  aliases            — через запятую: 'Витя, Витек'\n"
            "  relation_to_user   — для персоны: 'друг', 'коллега', 'мама'\n"
            "  occupation         — род занятий\n"
            "  city / country     — для места\n"
            "  kind               — для места/организации: 'кафе', 'дом', 'компания'\n"
            "  industry           — сфера для организации\n"
            "  traits             — короткие характеристики через запятую: 'весёлый, умный'\n"
            "  notes              — короткие факты через запятую: 'любит кофе, ходит в зал'\n\n"
            "ВАЖНО: перед созданием новой карточки сначала вызови search_memory(имя) — "
            "если карточка уже есть, upsert_entity обновит её. Не плоди дубликаты. "
            "Списковые поля (aliases/traits/notes) сливаются как уникальное объединение, "
            "так что повторный вызов с новым элементом просто добавит его к существующим.\n\n"
            "ПРАВИЛА ЗАПОЛНЕНИЯ:\n"
            "  • Пропускай неизвестное. Не пиши 'не указано', 'нет данных', '—' — просто не передавай поле.\n"
            "  • notes = короткие УСТОЙЧИВЫЕ факты через запятую, каждый — одна мысль.\n"
            "    ✓ 'любит кофе, ходит в зал по вторникам, аллергия на орехи'\n"
            "    ✗ 'Друг Хозяина. Встреча запланирована на завтра в 22:00.'\n"
            "      (два факта в одном элементе + эпизод про встречу — это отдельная запись)\n"
            "  • aliases = варианты ИМЕНИ: прозвища, уменьшительные, фамилии.\n"
            "    ✓ 'Витя, Витек, Виктор Петров'\n"
            "    ✗ 'Егор (друг)'  (это не имя, а описание роли — роль идёт в relation_to_user)\n\n"
            "Куда класть факты о сущности:\n"
            "  • Короткая характеристика (одно-два слова, устойчивое свойство) → в `traits`.\n"
            "    Пример: «Виктор весёлый» → traits=весёлый.\n"
            "  • Короткий устойчивый факт (привычка, вкус, особенность) → в `notes`.\n"
            "    Пример: «любит кофе» → notes=любит кофе.\n"
            "  • Развёрнутое предпочтение с деталями → отдельная запись `предпочтение`\n"
            "    с `links=[имя_карточки]` (в post-session extraction).\n"
            "  • Эпизод с датой/временем (встреча, звонок, поездка) → `plan_event` ИЛИ\n"
            "    запись `событие` с `links`. НЕ пихай эпизоды в notes — они устареют.\n\n"
            "Пример аргументов:\n"
            "  entity_type=\"персона\", name=\"Виктор\", relation_to_user=\"друг Господина\",\n"
            "  occupation=\"программист в Яндексе\", aliases=\"Витя\", traits=\"весёлый\",\n"
            "  notes=\"любит кофе\""
        ),
    ))

    registry.register(DRAW_TOOL)
    registry.register(CHANGE_OUTFIT_TOOL)
    registry.register(LIST_OUTFITS_TOOL)

    registry.register(END_SESSION_TOOL)
    from tools.scenario_end import SCENARIO_END_TOOL
    registry.register(SCENARIO_END_TOOL)

    registry.register(SET_REMINDER_TOOL)
    registry.register(LIST_REMINDERS_TOOL)
    registry.register(CANCEL_REMINDER_TOOL)
    from tools.timer import SET_TIMER_TOOL
    registry.register(SET_TIMER_TOOL)

    from tools.notes import (APPEND_NOTE_TOOL, DELETE_NOTE_TOOL,
                             LIST_NOTES_TOOL, WRITE_NOTE_TOOL)
    registry.register(WRITE_NOTE_TOOL)
    registry.register(APPEND_NOTE_TOOL)
    registry.register(DELETE_NOTE_TOOL)
    registry.register(LIST_NOTES_TOOL)

    from tools.web_tools import (OPEN_ANIME_ART_TOOL, OPEN_URL_TOOL,
                                 PLAY_VIDEO_TOOL, SEARCH_ANIME_ART_TOOL,
                                 SEARCH_IMAGES_TOOL, SET_IMAGE_SOURCE_TOOL,
                                 SHOW_IMAGE_TOOL, WEB_SEARCH_TOOL)
    registry.register(WEB_SEARCH_TOOL)
    registry.register(OPEN_URL_TOOL)
    registry.register(PLAY_VIDEO_TOOL)
    registry.register(SEARCH_IMAGES_TOOL)
    registry.register(SEARCH_ANIME_ART_TOOL)
    registry.register(SHOW_IMAGE_TOOL)
    registry.register(OPEN_ANIME_ART_TOOL)
    registry.register(SET_IMAGE_SOURCE_TOOL)

    from tools.app_tool import OPEN_APP_TOOL
    registry.register(OPEN_APP_TOOL)

    from tools.document_tool import SEARCH_DOCUMENT_TOOL
    registry.register(SEARCH_DOCUMENT_TOOL)

    from services import assistant_brief as _ab
    from tools.assistant_brief_tool import (CONFIGURE_BRIEF_SCHEMA,
                                            handle_configure_brief)
    if _ab.ENABLED:
        registry.register(Tool(
          name="configure_brief",
          tier=TIER_CONTEXTUAL,
          capability="ассистент",
          schema=CONFIGURE_BRIEF_SCHEMA,
          handler=handle_configure_brief,
          summary=("configure_brief(enabled, weather, plans, reminders, promises) — "
                   "включить/выключить/настроить утреннюю сводку дня (ТОЛЬКО по "
                   "явной просьбе/согласию Господина)"),
          help=(
              "configure_brief — подписка Господина на утреннюю сводку дня\n\n"
              "Вызывай ТОЛЬКО когда он ЯВНО согласился («да, давай»), попросил "
              "выключить или поменять состав.\n"
              "Параметры (все опциональны, меняются только переданные):\n"
              "  enabled  — true включить / false выключить\n"
              "  weather / plans / reminders / promises — состав сводки\n\n"
              "Примеры аргументов:\n"
              "  enabled=true — согласился на сводку\n"
              "  weather=false — «погода мне не интересна»\n"
              "  enabled=false — «не присылай больше сводку»"
          ),
        ))

    from tools.style_self import STYLE_SELF_TOOL
    registry.register(STYLE_SELF_TOOL)

    from tools.lore_tool import GET_LORE_SCHEMA, handle_get_lore
    registry.register(Tool(
        name="get_lore",
        tier=TIER_CONTEXTUAL,
        capability="лор",
        schema=GET_LORE_SCHEMA,
        handler=handle_get_lore,
        summary=("get_lore(topic) — достать свой личный канон или справку "
                 "приложения по теме из индекса в промпте"),
        help=(
            "get_lore — твой личный канон (лор) и справка приложения\n\n"
            "Темы, по которым канон существует, перечислены в промпте "
            "(«канон по темам: …», «справка: …»). Совпавшие темы приходят "
            "в ход сами; get_lore — когда просят ПОДРОБНЕЕ или нужной темы "
            "в контексте нет. Пересказывай своими словами, не цитируй."
        ),
    ))
