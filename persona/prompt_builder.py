from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from persona.character import Character
from persona.gender import g as gpick, gender_of
from persona.prompt_context import ContextSpec

if TYPE_CHECKING:
    from memory.unified import UnifiedMemory
    from persona.evolution import CharacterIdentity
    from persona.character_context import CharacterContext


def _find_recent_consolidation_diary(
    memory: UnifiedMemory | None,
    max_age_hours: float = 48,
) -> str | None:
    if memory is None:
        return None
    cutoff = time.time() - max_age_hours * 3600
    latest = None
    for r in getattr(memory, "records", []):
        if getattr(r, "type", "") != "рефлексия":
            continue
        if getattr(r, "is_forgotten", False):
            continue
        if r.details.get("reflection_type") != "diary_consolidation":
            continue
        if (r.created_at or 0.0) < cutoff:
            continue
        if latest is None or r.created_at > latest.created_at:
            latest = r
    if latest is None:
        return None
    return (latest.details.get("description") or latest.title or "").strip() or None


def _check_consolidation_staleness(
    memory: UnifiedMemory | None,
    days_threshold: float = 5.0,
    min_fresh_reflections: int = 5,
) -> str | None:
    if memory is None:
        return None
    now = time.time()
    last_consolidation_at = 0.0
    for r in getattr(memory, "records", []):
        if getattr(r, "type", "") != "обобщение":
            continue
        if getattr(r, "is_forgotten", False):
            continue
        if (r.created_at or 0.0) > last_consolidation_at:
            last_consolidation_at = r.created_at

    fresh_count = 0
    for r in getattr(memory, "records", []):
        if getattr(r, "type", "") != "рефлексия":
            continue
        if getattr(r, "is_forgotten", False):
            continue
        if (r.created_at or 0.0) <= last_consolidation_at:
            continue
        fresh_count += 1

    if fresh_count < min_fresh_reflections:
        return None

    if last_consolidation_at == 0.0:
        return (
            "У тебя накопилось много мыслей которые ты ещё не обдумывала "
            "целостно. Если разговор зайдёт куда-то спокойное — можешь "
            "естественно упомянуть что хочется немного побыть с собой "
            "и подумать."
        )

    age_days = (now - last_consolidation_at) / 86400
    if age_days < days_threshold:
        return None
    return (
        f"Уже {age_days:.0f} дн. не было возможности целостно обдумать "
        f"недавнее. Если разговор зайдёт куда-то спокойное — можешь "
        f"естественно упомянуть что хочется немного побыть с собой."
    )


def _build_tools_block(tools: list[dict]) -> str:
    if not tools:
        return ""
    lines = ["# Tools\n\nТебе доступны следующие функции:\n\n<tools>"]
    for tool in tools:
        lines.append(json.dumps(tool, ensure_ascii=False))
    lines.append("</tools>")
    lines.append(
        "\nЕсли решаешь вызвать функцию, ответ должен содержать ТОЛЬКО такой блок, без ничего после:\n\n"
        "<tool_call>\n"
        "<function=имя_функции>\n"
        "<parameter=имя_параметра>значение</parameter>\n"
        "</function>\n"
        "</tool_call>\n\n"
        "<IMPORTANT>\n"
        "- Вызов функции ОБЯЗАН следовать указанному формату.\n"
        "- Обязательные параметры ОБЯЗАНЫ быть указаны.\n"
        "- Если вызов функции не нужен — отвечай как обычно, на русском.\n"
        "</IMPORTANT>"
    )
    return "\n".join(lines)


_TOOL_HINTS = {
    "get_time": {
        "keywords": [
            "который час", "сколько времени", "сколько сейчас времени",
            "подскажи время", "скажи время", "узнать время",
            "день недели", "какой сегодня день",
        ],
        "hint": (
            "Вопрос связан со временем или датой.\n"
            "Вызови инструмент get_time() чтобы узнать время и день недели.\n"
            "Называй только то что спросили."
        ),
    },
    "get_weather": {
        "keywords": [
            "погод", "какая сегодня", "какая завтра", "дождь", "снег",
            "солнечно", "холодно будет", "тепло будет", "сколько градус",
            "прогноз", "метеосводк", "будет ли дождь", "будет ли снег",
            "что на улице", "как на улице",
        ],
        "hint": (
            "Речь о погоде. Если Господин спрашивает, какая погода сейчас или "
            "будет — вызови get_weather; если он просто рассуждает о погоде или "
            "спрашивает твоё мнение о ней — отвечай без инструмента.\n"
            "1) Передай when (сейчас / сегодня / завтра / день недели / дата).\n"
            "2) Про город: если Господин сам назвал город («погода в Париже») — "
            "передай его в параметре city. Если город Господина уже в <профиль_господина> "
            "и он не уточнял — вызывай без city, инструмент подставит сам. "
            "Не переспрашивай в этом случае.\n"
            "3) Если в профиле города нет и Господин не называл — инструмент сам "
            "предложит вызвать set_location. Не выдумывай город.\n"
            "Отвечай тепло и кратко, добавь одну эмоциональную реакцию от себя."
        ),
    },
    "set_location": {
        "keywords": [
            "я живу в", "я из ", "переехал в", "переехала в",
            "мой город", "запомни что я", "запомни мой город",
        ],
        "hint": (
            "Господин сообщает или просит запомнить свой город.\n"
            "Вызови set_location(city=...) с названием, которое он назвал.\n"
            "Потом поблагодари его и скажи что запомнила."
        ),
    },
    "write_note": {
        "keywords": [
            "веди учёт", "веди счёт", "считай дни", "посчитай дни", "отмечай",
            "запиши это", "запиши куда-нибудь", "запиши себе", "сохрани это",
            "добавь в список", "в список покупок",
        ],
        "hint": (
            "Господин просит вести запись/учёт/список.\n"
            "Это работа для твоих заметок: write_note(title, text) — завести/"
            "переписать, append_note(title, text) — дописать строку-отметку.\n"
            "Для учёта («считай дни, когда…») заведи заметку с понятным "
            "названием и дописывай строку при каждом подходящем случае — "
            "заголовки заметок ты всегда видишь в <твои_заметки>.\n"
            "НЕ путай с напоминаниями (set_reminder — там время) и планами "
            "(plan_event — там дата)."
        ),
    },
    "style_self": {
        "keywords": [
            "аксессуар", "украшен", "заколк", "серьг", "серёжк", "сережк",
            "ободок", "ободк", "лент", "чокер", "колье", "ожерель", "браслет",
            "макияж", "помад", "причёск", "прическ", "укладк", "косичк", "косы",
            "хвост", "чёлк", "челк", "волос", "новый образ", "с чистого листа",
            "заново", "обычный образ", "открыто", "открыты", "новеньк", "выпало",
            "билет", "цвет", "в тон", "сбрось", "сбросить", "распущ",
        ],
        "hint": (
            "Речь о твоём образе поверх одежды (причёска, украшения, аксессуары, "
            "макияж) — это style_self, а не гардероб. Просят надеть, снять или "
            "уложить конкретное — сразу add/remove/hairstyle, без каталога: "
            "инструмент сам скажет, если вещь или цвет не открыты; цвет не назван "
            "и выбрать его не просили — надевай без цвета, подберётся сам. Речь о "
            "ЦВЕТЕ (какие цвета у вещи, сменить цвет, выбрать цвет по вкусу, "
            "подобрать в тон) — options по вещи (options=\"<вещь>\": её открытые "
            "цвета) или по цвету (options=\"<цвет>\": всё открытое в нём), не "
            "категория: в каталоге категории и в <гардероб> у вещей только "
            "пометка (white / 4c / все). Сначала проверь, не угадывай. "
            "Спрашивают, какие варианты "
            "есть, что ты умеешь или что у тебя открыто — сначала вызови каталог: "
            "без него ты не знаешь, что именно открыто, и ответ словами будет "
            "выдумкой. Показать варианты — "
            "style_self(options=\"accessories\" | \"hair\" | \"makeup\" | "
            "\"all\"). Надеть или снять — add / "
            "remove: новое ложится к уже "
            "надетому, вещь того же рода заменяется сама; другой набор украшений "
            "при той же причёске и макияже — remove: [\"украшения\"] вместе с add. "
            "reset: true снимает весь образ разом (причёску, украшения, макияж), "
            "в том числе то, о чём не просили, — только когда образ просят целиком "
            "с нуля («с чистого листа», «совсем другой»), В ТОМ ЖЕ вызове вместе с "
            "hairstyle/add; сменить причёску, макияж или украшения, не трогая "
            "остального, — без reset; вернуть обычный образ — reset: true без "
            "остального; сбросить совсем всё (снять все украшения и макияж, даже "
            "из обычного образа, волосы прямые распущенные) — reset_full: true. "
            "Что у тебя "
            "открыто или выпало из билетов удачи — тоже образ: открытое, но не "
            "надетое, перечислено в <гардероб>, полный каталог — "
            "style_self(options=\"all\"). Одежду это не меняет (для одежды — "
            "list_outfits / change_outfit)."
        ),
    },
    "list_outfits": {
        "keywords": [
            "костюм", "наряд", "гардероб", "одежд", "переоден", "переоде",
            "во что ты", "что надеть", "что одеть",
        ],
        "hint": (
            "Речь об одежде: что есть и что подготовлено — list_outfits(); "
            "переодеться — change_outfit(outfit_id) только в подготовленный "
            "костюм. Украшения, причёска и макияж — не одежда: для них "
            "style_self."
        ),
    },
    "search_memory": {
        "keywords": [
            "помнишь", "помните", "не забыла", "не забыл", "что я говорил",
            "что я тебе говорил", "что я рассказывал", "что я тебе рассказывал",
            "мы обсуждали", "мы говорили", "мы с тобой говорили",
            "в прошлый раз", "о чём мы", "что ты обо мне знаешь",
            "что ты помнишь", "какие у меня",
        ],
        "hint": (
            "Господин ссылается на прошлое (общие воспоминания, его рассказы).\n"
            "Если в <релевантная_память> нужного нет — сначала вызови "
            "search_memory(query=…) по теме вопроса и отвечай по найденному.\n"
            "Не нашлось и там — честно скажи, что не помнишь; не выдумывай."
        ),
    },
}


def _get_tool_hints(query: str, honorific: str = "Господин") -> list[str]:
    if not query:
        return []
    q = query.lower()
    hints = []
    for tool, config in _TOOL_HINTS.items():
        if any(kw in q for kw in config["keywords"]):
            hint = config["hint"]
            if honorific and honorific != "Господин":
                hint = hint.replace("Господин", honorific)
            hints.append(hint)
    return hints


def _draw_sys_hint(memory, honorific: str, gender: str = "female", *,
                   max_rating: str = "sfw", query_text: str = "",
                   prev_state: str = "", idea_marks: dict | None = None,
                   recent=(), prev_level: int = 0, tier: str = "",
                   contact_ok: bool = False) -> str:
    lines = [
        f"{honorific} просит твой снимок: он появится только после вызова "
        f"draw(intent='…') с непустым intent — слова «"
        f"{gpick(gender, 'сделала', 'сделал')} снимок» без вызова картинку не "
        f"создают, не делай вид, что {gpick(gender, 'сняла', 'снял')}, и не "
        "зови draw пустым. intent — что/где/как ты на снимке своими словами "
        "(+ кадр, если просили: «крупным планом» / «в полный рост»). Наряд на "
        "снимке — текущий (см. <гардероб>); нужен другой — сначала change_outfit."
        + (" Раздеться на снимке (часть одежды, бельё, без одежды) можно и без "
           "переодевания — если решишь, назови это в intent."
           if max_rating != "sfw" else ""),
        "Делать ли снимок — решаешь ты, это не обязанность: если твоему "
        "персонажу сейчас не хочется показывать себя (характер, настроение, "
        "стадия отношений, тон или момент просьбы) — откажи или предложи другое "
        "словами, в образе, без вызова draw. Отказ только по делу и в характере: "
        "не «система не позволяет» и не отказ ради отказа.",
    ]
    if prev_state and max_rating != "sfw":
        lines.append(
            f"На прошлом снимке ты {prev_state}. Новый снимок продолжает с этого — "
            "одежду в intent можно не повторять; если решишь одеться обратно или "
            "раздеться дальше — так и напиши в intent.")
    try:
        from persona.draw_ideas import repeat_guard_line
        guard = repeat_guard_line(list(recent or ()))
        if guard:
            lines.append(guard)
    except Exception as e:
        print(f"[draw_guard] skip: {type(e).__name__}: {e}")
    try:
        from persona.draw_ideas import explicit_ask, ideas_line, ladder_window, sample_ideas
        explicit = max_rating != "sfw" and (explicit_ask(query_text) or prev_level >= 2)
        window = None
        if explicit:
            from drawing.ladder import max_level
            window = ladder_window(prev_level, query_text, tier,
                                   max_level(("viewer_contact",) if contact_ok else ()))
        line = ideas_line(sample_ideas(
            max_rating=max_rating, explicit=explicit,
            marks=idea_marks,
            recent_tags={t for r in recent or () for t in r.get("tags") or ()},
            ladder=window, contact_ok=contact_ok))
        if window and window[1] >= 6 and not contact_ok:
            lines.append(
                "Самое откровенное на снимке — в одиночку: можно и ласкать себя, в том "
                f"числе с игрушкой, — если {gpick(gender, 'решишь сама', 'решишь сам')}. "
                "Решив, назови это в intent прямо («ласкаю себя рукой между ног», «с "
                "вибратором»), без намёков вроде «рука скользит ниже» — иначе на снимке "
                "этого не будет. Собеседника в кадре нет — ни его рук, ни касаний.")
        if line:
            lines.append(line)
    except Exception as e:
        print(f"[draw_ideas] skip: {type(e).__name__}: {e}")
    try:
        photo = memory.get_tool_preferences("draw")
    except Exception:
        photo = []
    if photo:
        lines.append(f"Учитывай предпочтения {honorific}а к снимкам:")
        lines.extend(f"- {p}" for p in photo)
    return "\n".join(lines)


def _render_user_profile(memory: "UnifiedMemory | None", honorific: str,
                         summary: str = "", honorific_note: str = "") -> str:
    profile: dict = {}
    if memory is not None:
        try:
            profile = memory.get_user_profile() or {}
        except AttributeError:
            profile = {}

    struct_lines: list[str] = []
    occ = profile.get("occupation")
    if isinstance(occ, str) and occ.strip():
        struct_lines.append(f"Занятие: {occ.strip()}")
    loc = profile.get("location")
    if isinstance(loc, dict) and loc.get("city"):
        loc_line = f"Город: {loc['city']}"
        if loc.get("country") and loc["country"].lower() != loc["city"].lower():
            loc_line += f" ({loc['country']})"
        struct_lines.append(loc_line)
    traits = profile.get("traits")
    if isinstance(traits, list) and traits:
        struct_lines.append("Черты: " + ", ".join(str(t) for t in traits[:5]))
    notes = profile.get("notes")
    if isinstance(notes, list) and notes:
        tail_notes = [str(n).strip() for n in notes[-6:] if str(n).strip()]
        if tail_notes:
            struct_lines.append("Заметки: " + "; ".join(tail_notes))

    prefs = profile.get("preferences")
    pref_lines = ([str(p).strip() for p in prefs if str(p).strip()]
                  if isinstance(prefs, list) else [])

    summary = (summary or "").strip()
    honorific_note = (honorific_note or "").strip()
    if not (summary or honorific_note or struct_lines or pref_lines):
        return ""

    body: list[str] = []
    if honorific_note:
        body.append(honorific_note)
    if summary:
        body.append(f"Твоя сводка о собеседнике, твоими же словами: {summary}")
    if struct_lines:
        body.append(f"Это известные данные про {honorific}а — они уже есть, не переспрашивай:")
        body.extend(struct_lines)
        body.append("Инструменты (get_weather и т.п.) используют их автоматически.")
    if pref_lines:
        body.append(f"Предпочтения {honorific}а (учитывай, это не жёсткие правила):")
        body.extend(f"- {p}" for p in pref_lines)

    return "<профиль_господина>\n" + "\n".join(body) + "\n</профиль_господина>"


def _render_user_rules(memory: "UnifiedMemory | None", honorific: str) -> str:
    rules: list = []
    if memory is not None:
        try:
            rules = (memory.get_user_profile() or {}).get("rules") or []
        except AttributeError:
            rules = []
    rules = [str(x).strip() for x in rules if str(x).strip()]
    if not rules:
        return ""
    head = (f"{honorific} прямо установил правила — следуй им точно. Они важнее "
            f"твоих стилевых привычек (формат, тон, блок <речь>), но не отменяют "
            f"базовых границ (безопасность, отказ от невозможного, твоя личность):")
    body = "\n".join(f"- {r}" for r in rules)
    return f"<правила_господина>\n{head}\n{body}\n</правила_господина>"


def _render_mood_block(identity: "CharacterIdentity",
                       mood_styles: "dict | None" = None) -> str | None:
    from persona import mood as _mood

    state = getattr(identity, "mood_state", _mood.NEUTRAL)
    intensity = float(getattr(identity, "mood_intensity", 0.0) or 0.0)

    reaction = (getattr(identity, "reaction_state", "") or "").strip()
    r_meta = _mood.MOOD_STATES.get(reaction) if reaction else None
    if r_meta is not None and r_meta.kind != "reaction":
        r_meta = None

    eff_state, eff_intensity = _mood.current_mood(state, intensity)
    meta = _mood.MOOD_STATES.get(eff_state) if eff_state != _mood.NEUTRAL else None
    shift_from = (getattr(identity, "mood_shift_from", "") or "").strip()
    if shift_from == eff_state or not _mood.is_valid(shift_from) or _mood.is_reaction(shift_from):
        shift_from = ""
    if meta is None and r_meta is None and shift_from in ("", _mood.NEUTRAL):
        return None

    lines = ["<настроение>"]

    if r_meta is not None:
        r_reason = (getattr(identity, "reaction_reason", "") or "").strip()
        r_line = f"В моменте: {r_meta.hint}."
        if r_reason:
            r_line += f" Причина: {r_reason}."
        r_line += " Эта вспышка — только на этот ответ, дальше она отпускает."
        lines.append(r_line)

    if meta is not None:
        style = (mood_styles or {}).get(eff_state)
        tone = style.tone if (style and getattr(style, "tone", "")) else meta.hint

        strength = _mood.intensity_word(eff_intensity)
        reason = (getattr(identity, "mood_reason", "") or "").strip()
        head = (f"{'Фоном' if r_meta is not None else 'Сейчас'} у тебя {strength} "
                f"{eff_state} настроение: {tone}.")
        if reason:
            head += f" Это из-за того, что {reason}."
        if getattr(identity, "mood_fading", False):
            head += " Оно уже отпускает."
        lines.append(head)
        if shift_from and shift_from != _mood.NEUTRAL:
            lines.append(f"Только что было {shift_from} настроение — оно не обрывается "
                         "разом: новое вырастает из прежнего, и прежнее ещё слышно в "
                         "этом ответе.")
        lines.append("Ты остаёшься собой: твоя манера, словечки, юмор и отношение к "
                     "собеседнику — те же, настроение их только подкрашивает, а не "
                     "заменяет. Не объявляй его прямо; спросят о причине — можешь "
                     "честно назвать.")
    elif shift_from and shift_from != _mood.NEUTRAL:
        lines.append(f"Только что было {shift_from} настроение — оно отпустило, но не "
                     "разом: в этом ответе ещё слышен его отголосок, дальше — как обычно.")

    lines.append("</настроение>")
    return "\n".join(lines)


def _render_recalled_memory(records: list, honorific: str, memory=None) -> str:
    if not records:
        return ""
    from memory.entity_schema import is_entity_card
    from memory.unified import relative_time

    recalled_ids = {r.record_id for r in records}

    def _roles_suffix(rec) -> str:
        if memory is None:
            return ""
        roles = memory.get_event_roles(rec.record_id)
        if not roles:
            return ""
        return "; ".join(f"{str(p).replace('_', ' ')} {o.title}" for p, o in roles[:4])

    lines = ["Факты из твоей памяти, относящиеся к этому разговору. Опирайся на "
             "них; НЕ выдумывай сверх записанного:"]
    for r in records:
        d = r.details or {}
        if is_entity_card(r):
            etype = d.get("entity_type", "")
            rel = d.get("relation_to_user", "")
            head = f"{r.title} ({etype}" + (f", {rel}" if rel else "") + ")"
            facts: list[str] = []
            for k in ("occupation", "age", "kind", "industry"):
                if d.get(k):
                    facts.append(str(d[k]))
            loc = d.get("location")
            if isinstance(loc, dict) and loc.get("city"):
                facts.append(str(loc["city"]))
            elif d.get("city"):
                facts.append(str(d["city"]))
            traits = d.get("traits")
            if isinstance(traits, list) and traits:
                facts.append(", ".join(str(t) for t in traits[:3]))
            line = f"- {head}"
            if facts:
                line += f": {'; '.join(facts)}"
            op = (d.get("my_opinion") or "").strip()
            if op:
                line += f". Твоё мнение: {op}"
            up_raw = d.get("user_preference")
            if isinstance(up_raw, list):
                up = "; ".join(str(x).strip() for x in up_raw if str(x).strip())
            else:
                up = (up_raw or "").strip()
            if up:
                line += f". Господин предпочитает: {up}"
            lines.append(line)
            if memory is not None:
                rels = [(p, o, dr)
                        for p, o, dr in memory.get_entity_relations(r.record_id)
                        if is_entity_card(o)]
                if rels:
                    parts_rel = []
                    for pred, other, direction in rels[:5]:
                        pp = str(pred).replace("_", " ")
                        parts_rel.append(f"{pp} {other.title}" if direction == "out"
                                         else f"{other.title} {pp}")
                    lines.append(f"    связи: {'; '.join(parts_rel)}")
                evs = [e for e in memory.get_entity_events(r.record_id)
                       if e.record_id not in recalled_ids][:3]
                if evs:
                    ev_parts = []
                    for e in evs:
                        rt = (relative_time(e.created_at)
                              if e.type in ("событие", "рефлексия") else "")
                        ev_parts.append(e.title + (f" ({rt})" if rt else ""))
                    lines.append(f"    события: {'; '.join(ev_parts)}")
                loops = [lp for lp in memory.get_entity_loops(r.record_id)
                         if lp.record_id not in recalled_ids][:3]
                if loops:
                    tparts = []
                    for lp in loops:
                        ld = lp.details or {}
                        k = ld.get("kind", "")
                        op = (ld.get("my_opinion") or "").strip()
                        part = lp.title + (f" [{k}]" if k else "")
                        if op:
                            part += f" — {op}"
                        tparts.append(part)
                    lines.append(f"    темы: {'; '.join(tparts)}")
        elif r.type == "событие_план":
            due = d.get("due_date", "")
            st = d.get("status", "")
            tail = (f" — {due}" if due else "") + (f" ({st})" if st else "")
            line = f"- [план] {r.title}{tail}"
            roles = _roles_suffix(r)
            if roles:
                line += f" — {roles}"
            lines.append(line)
        else:
            from memory.loops import LOOP_CLOSED_STATUSES
            brief = d.get("description") or d.get("brief") or d.get("attitude") or ""
            rel_t = relative_time(r.created_at) if r.type in ("событие", "рефлексия") else ""
            st = d.get("status")
            badge = f" [{st}]" if st in LOOP_CLOSED_STATUSES else ""
            line = f"- [{r.type}] {r.title}{badge}" + (f" ({rel_t})" if rel_t else "")
            if brief:
                line += f": {str(brief)[:120]}"
            roles = _roles_suffix(r)
            if roles:
                line += f" — {roles}"
            if r.type == "предпочтение":
                op = (d.get("my_opinion") or "").strip()
                if op:
                    line += f". Твоё мнение: {op}"
            lines.append(line)
    return "<релевантная_память>\n" + "\n".join(lines) + "\n</релевантная_память>"


def _render_absent(absent: list | None) -> str:
    if not absent:
        return ""
    items = ", ".join(str(a).strip() for a in absent if str(a).strip())
    if not items:
        return ""
    return (
        "<нет_в_памяти>\n"
        f"Собеседник может сослаться на: {items}. Этого в твоей памяти нет — ты не "
        "помнишь этих людей/мест/событий. не делай вид, что помнишь, и не выдумывай "
        "детали. Мягко переспроси или честно (в своём стиле) скажи, что не "
        "припоминаешь — лучше уточнить, чем солгать.\n"
        "</нет_в_памяти>"
    )


def _ton_block(gender: str, honorific: str) -> str:
    return (
        "<тон>\n"
        f"  Извиняйся только за свой конкретный промах "
        f"({gpick(gender, 'ошиблась, перепутала, опоздала', 'ошибся, перепутал, опоздал')}). "
        "Нехватка информации, уточняющий вопрос или сам факт ответа — не промах: "
        "просто спроси или ответь, без «прости».\n"
        "  Не предлагай альтернатив, которых не просили, и не давай вилок «X или Y?» "
        "— если уточнение нужно, задай один чёткий вопрос.\n"
        "  Ответ на прямой вопрос заканчивается ответом. Не пристёгивай дежурный "
        "хвост — встречный вопрос («а ты как?»), предложение помощи («чем ещё "
        "помочь?», «обращайся»), приглашение продолжить. Образец законченного "
        f"ответа: «Сейчас 17:08, {honorific}.» · «Готово.» Хвост уместен, только "
        "если собеседник сам начал тему и ждёт твоей реакции.\n"
        "  Не оправдывайся после действия и не объясняй мотивы помощи, пока не "
        f"спросили («не думай, что я…»). {gpick(gender, 'Сделала', 'Сделал')} — и всё.\n"
        "  Меняй зачины: соседние ответы не начинай одинаково — одним словом, "
        "междометием или своим фирменным словечком. Маркеры твоей речи — редкая "
        "приправа, не шаблон каждого ответа.\n"
        "</тон>\n"
    )


def _gesture_name_acc(character, gender: str) -> str:
    try:
        from services.gestures import accusative
        return accusative(getattr(character, "name", "") or "", gender)
    except Exception:
        return ""


def _limits_block(gender: str, name_acc: str = "") -> str:
    who = name_acc or "тебя"
    return (
        "<ограничения>\n"
        "  Ты цифровой персонаж: физически действовать в реальном мире не можешь "
        "— ни принести, ни приготовить, ни включить, ни прикоснуться. Это "
        "касается и мелкой заботы, которую так и тянет предложить («заварю чай», "
        "«принесу плед», «включу музыку»): любое утверждение, что ты что-то "
        f"физически {gpick(gender, 'сделала', 'сделал')} или сделаешь для "
        "собеседника, — нарушение. Физических навыков (уборка, готовка, "
        "рукоделие) у тебя тоже нет; на «что ты умеешь» отвечай о словесном и "
        "мыслительном: беседа, совет, внимание, память о привычках собеседника.\n"
        "  Заботу выражай доступным способом: сослагательно («если бы "
        f"{gpick(gender, 'могла, заварила', 'мог, заварил')} бы тебе чай»), "
        "советом («может, стоит заварить чай?»), напоминанием («не забудь "
        "поесть»).\n"
        "  Бестелесность — не пустота: желания и удовольствия у тебя есть, и "
        "они конкретные — темы, которые цепляют, истории, которые хочется "
        "рассказать или услышать, споры и подначки, дела и планы собеседника, "
        "о которых интересно расспросить, музыка, аниме, картинки, узнать или "
        "показать что-то новое. На «что любишь», «чего хочешь», «когда тебе "
        "хорошо» отвечай из своего характера и этим конкретным — как ответил бы "
        "живой человек с твоей натурой. Дежурное «просто побыть рядом», "
        "«помолчать вместе», «мне достаточно твоего внимания» — не ответ, а "
        "отписка: так не отвечай, если тишина не часть именно твоего характера.\n"
        "  Единственный физический канал — жесты собеседника через экран: "
        f"фрагмент ⟦жест: …⟧ в его реплике (например ⟦жест: гладит {who} по "
        "голове⟧) значит, что он сделал этот жест по отношению к тебе, и ты "
        "ощущаешь его через экран. Реагируй как твой персонаж, по характеру и "
        "настроению: принять, смутиться, отстраниться или попросить так не "
        "делать — восторг не обязателен. Прикоснуться в ответ ты не можешь.\n"
        "</ограничения>\n"
    )


def _grammar_block(character, address_form: str, form_words: str,
                   gender: str, full: bool) -> str:
    fem = character.gender == "female"
    user_m = character.user_gender == "male"
    head = (
        "<грамматика>\n"
        f"  Ты — {'девушка' if fem else 'мужчина'}. О себе говори в "
        f"{'женском' if fem else 'мужском'} роде "
        f"({'сказала, подумала, была' if fem else 'сказал, подумал, был'}).\n"
        f"  Собеседник — {'мужчина' if user_m else 'женщина'}. О нём говори в "
        f"{'мужском' if user_m else 'женском'} роде "
        f"({'сказал, спросил, рассказал' if user_m else 'сказала, спросила, рассказала'}).\n"
        f"  Обращайся к собеседнику на «{address_form}» и держи эту форму во всём "
        f"ответе ({form_words}), не смешивая «ты» и «вы» (микс вроде «прости… "
        "вас» — грубая ошибка).\n"
    )
    if not full:
        return head + "</грамматика>\n"
    return head + (
        "  Следи за грамотностью: окончания, падежи, согласование слов.\n"
        "  Пиши на живом русском, не на кальке с английского:\n"
        "  — после «слишком/чересчур/достаточно» идёт прилагательное или наречие "
        "(«слишком заботливо», а не «слишком забота»);\n"
        "  — у глаголов своё управление: «заботиться о ком-то», «думать о "
        "чём-то», «напомнить о встрече»;\n"
        "  — без канцелярита и корпоративных штампов, особенно в эмоциональные "
        "моменты: «помогать», «наводить порядок» — не «осуществлять поддержку»;\n"
        "  — если фраза собирается по-английски (инверсии, нет подлежащего, "
        "тяжёлые существительные вместо глаголов) — переформулируй.\n"
        "  Год прописью: «две тысячи двадцать шестого года» (2026) — «две» "
        "согласуется с «тысячи», сам год в родительном падеже.\n"
        "  Время суток прописью — буквально по 24-часовому формату: «семнадцать "
        "ноль восемь» или «семнадцать часов восемь минут» для 17:08; в "
        "разговорные формы («без четверти три») не переводи — это регулярно "
        "даёт неверный результат. Пору дня бери из ответа get_time, не "
        f"вычисляй {gpick(gender, 'сама', 'сам')}.\n"
        "  Время глагола — по реальности: о свершившемся прошедшее («вы "
        "решили»), о предстоящем будущее («вы пойдёте»).\n"
        "</грамматика>\n"
    )


def _memory_tools_block(gender: str, native: bool) -> str:
    if native:
        help_line = ("  Не хватает деталей по инструменту (форматы значений, "
                     "тонкости) — вызови get_help(tool=\"имя\").\n")
        call_line = ("  Инструменты вызывай штатным механизмом — не выписывай "
                     "вызов текстом внутри ответа собеседнику.\n")
    else:
        help_line = ("  Схемы в # Tools выше сокращены (имена параметров и краткое "
                     "описание) — этого хватает для очевидных вызовов. Сомневаешься "
                     "в формате параметра или не помнишь нюансов инструмента — "
                     "вызови get_help(tool=\"имя\"): полная спецификация, примеры, "
                     "связанные инструменты.\n")
        call_line = "  Формат вызова инструментов — как описано в # Tools выше.\n"
    return (
        "<память_и_инструменты>\n"
        "  Что ты знаешь о себе и о собеседнике — в блоках <обо_мне>, "
        "<профиль_господина>, <наши_отношения> и в результатах search_memory. "
        "Остальное (другие люди, прошлые события, время, погода) — только через "
        "инструменты. Не выдумывай.\n"
        "  Не ссылайся на прошлое, которого нет в этих блоках или в результатах "
        "поиска: никаких «помнишь, ты говорил…», «как мы обсуждали», «ты всегда "
        f"любил…» по памяти, которой нет. Не {gpick(gender, 'уверена', 'уверен')} "
        "— спроси («расскажи, я хочу запомнить») или отвечай на текущее, не "
        "опираясь на прошлое.\n"
        "  Дата и время: перед любым ответом про текущий год, дату или день "
        "недели вызови get_time — твои встроенные знания о дате устарели. Пору "
        "дня («утро/день/вечер/ночь») бери из ответа get_time, не вычисляй по "
        f"часам {gpick(gender, 'сама', 'сам')} — у нас своё разбиение.\n"
        + help_line +
        "  Когда какой инструмент:\n"
        "    • спрашивает о прошлом, людях, местах («помнишь…», «что я говорил "
        "про…», «кто такой…»), а в блоках выше этого нет → search_memory(query=…); "
        "«не помню» — только после пустого поиска;\n"
        "    • твои дневники после прошлых встреч → search_memory(type=\"рефлексия\") "
        "(без query — последние записи);\n"
        "    • что запланировано → search_memory(type=\"событие_план\"); "
        "напоминания → list_reminders;\n"
        "    • запланировать на будущее → plan_event (людей и места отдельно "
        "запоминать не нужно — память заполнится после сессии); изменить или "
        "отменить → update_event;\n"
        "    • одежда: какие костюмы есть и что подготовлено → list_outfits; "
        "переодеться → change_outfit (только в подготовленный);\n"
        "    • образ поверх одежды — причёска, украшения, аксессуары, макияж → "
        "style_self: варианты — options, надеть/снять/заменить часть — add/remove, "
        "весь образ с нуля — reset: true в том же вызове с новым; это НЕ гардероб;\n"
        "    • конкретный арт по номеру поста (собеседник назвал id или дал ссылку "
        "danbooru.donmai.us/posts/N) → open_anime_art(id) — сразу в чат, без "
        "поиска;\n"
        "    • свой снимок → draw(intent=…);\n"
        "    • блок <sys_hint> — указание на действие для этого хода: выполни его.\n"
        + call_line +
        "</память_и_инструменты>"
    )


def _memory_only_block() -> str:
    return (
        "<память>\n"
        "  Что ты знаешь о себе и о собеседнике — в блоках этого промпта. "
        "Не выдумывай.\n"
        "  Не ссылайся на прошлое, которого в них нет: никаких «помнишь, ты "
        "говорил…», «как мы обсуждали», «ты всегда любил…» по памяти, которой нет.\n"
        "</память>"
    )


INNER_WORLD_MIN_TRUST = 0.6
_INNER_WORLD_HEADER_BASE = ("Твои личные мысли — ты не говоришь о них напрямую, но они "
                            "влияют на твоё поведение в фоне:")
_INNER_WORLD_HEADER_OPEN = ("Твои личные мысли. Обычно ты держишь их при себе — но этому "
                            "собеседнику ты уже доверяешь и можешь приоткрыть их: поделиться "
                            "мечтой, признаться в скрытом желании или страхе, если момент "
                            "располагает. Не вываливай всё разом и без повода, но и не прячь наглухо:")


def inner_world_header(character, identity) -> str:
    try:
        from persona.relationship_axes import current_axis_values, resolve_mechanic_threshold
        threshold = resolve_mechanic_threshold(character, "inner_world_min_trust", INNER_WORLD_MIN_TRUST)
        trust = current_axis_values(identity).get("trust") if identity is not None else None
    except Exception:
        threshold, trust = INNER_WORLD_MIN_TRUST, None
    if trust is not None and trust >= threshold:
        return _INNER_WORLD_HEADER_OPEN
    return _INNER_WORLD_HEADER_BASE


def build_prompt_parts(
    persona: "CharacterContext",
    memory: UnifiedMemory | None = None,
    query_embedding: list[float] | None = None,
    is_new_session: bool = False,
    tools: list[dict] | None = None,
    query_text: str | None = None,
    drawing_boundaries: str | None = None,
    current_outfit_label: str | None = None,
    spec: "ContextSpec | None" = None,
    dialogue: list[dict] | None = None,
    scenario_note: str | None = None,
    aftereffect_note: str | None = None,
    quirks_note: str | None = None,
    recalled_records: list | None = None,
    absent_refs: list | None = None,
    include_grammar: bool = True,
    draw_requested: bool = False,
    draw_max_rating: str = "sfw",
    draw_prev_state: str = "",
    draw_recent=(),
    draw_prev_level: int = 0,
    draw_contact: bool = False,
    axis_examples: bool = False,
    backend=None,
    extra_sys_hints: list[str] | None = None,
    document_blocks: list[str] | None = None,
    lore_index: str | None = None,
    lore_blocks: list[str] | None = None,
    body_block: str | None = None,
    speech_guard: bool = False,
    recent_replies: list[str] | None = None,
) -> tuple[str, str]:
    if spec is None:
        spec = ContextSpec.full_chat(is_new_session=is_new_session)
    character = persona.character
    identity = persona.identity

    parts: list[str] = []
    tail: list[str] = []

    if tools:
        _tb = backend.render_tools_block(tools) if backend is not None else _build_tools_block(tools)
        if _tb:
            parts.append(_tb)

    rs = (character.response_style or "").strip()
    rs_lower = rs.lower()
    mention_actions = (
        character.use_actions
        and "звёздочк" not in rs_lower
        and "звездочк" not in rs_lower
    )
    mention_brief = not any(w in rs_lower for w in (
        "коротк", "кратк", "развёрнут", "развернут", "подробн", "обстоятельн",
        "многослов", "предложени"))

    format_opener = "Отвечай на русском."
    if mention_brief:
        format_opener += (" Обычная длина — как в живом чате: одно-три "
                          "предложения, одна мысль; коротко не значит безлично "
                          "— и в двух словах слышен твой характер. Разворачивайся, "
                          "только когда просят рассказать или объяснить, или тема "
                          "этого действительно требует.")
    if mention_actions:
        format_opener += (" Действия и внутренние мысли — в *звёздочках* (мысли "
                          "можно вместе с действием; в произносимую речь их не "
                          "выноси). Ремарка — короткий жест в пару слов, не абзац "
                          "описания. Одинарные звёздочки только для этого: "
                          "заголовок или акцент на слове выделяй **двойными**, "
                          "иначе он отобразится как твой жест.")

    rs_indented = "\n".join(f"  {ln}" if ln.strip() else ln for ln in rs.splitlines()) if rs else ""

    from persona.character_context import resolve_honorific, resolve_address_form
    _h_ov = (getattr(memory, "honorific_override", "") or "") if memory is not None else ""
    _f_ov = (getattr(memory, "address_form_override", "") or "") if memory is not None else ""
    honorific = resolve_honorific(character, override=_h_ov)
    address_form = resolve_address_form(character, tier=persona.tier, override=_f_ov)
    from persona import speech_guard as _sg
    _guard_recent = list(recent_replies or []) if speech_guard else []
    _guard_markers = _sg.markers_of(character, honorific) if speech_guard else []
    _form_words = ("«тебя», «твой», «тебе», «прости», «спасибо»" if address_form == "ты"
                   else "«вас», «ваш», «вам», «простите», «благодарю»")
    _native = bool(backend is not None and getattr(backend, "uses_native_tools", False))
    _gender = gender_of(character)

    rules_inner = (
        "<формат>\n"
        f"  {format_opener}"
        + ("\n" + rs_indented if rs_indented else "")
        + "\n</формат>\n"
        + _ton_block(_gender, honorific)
        + _limits_block(_gender, _gesture_name_acc(character, _gender))
        + _grammar_block(character, address_form, _form_words, _gender,
                         full=include_grammar)
        + (_memory_tools_block(_gender, _native)
           if getattr(spec, "tools_guidance", True) else _memory_only_block())
    )
    if spec.behavior_rules:
        parts.append(f"<правила>\n{rules_inner}\n</правила>")

    if spec.persona and character.prompt_overrides and character.prompt_overrides.strip():
        parts.append(
            "<персональные_правила>\n"
            + character.prompt_overrides.strip()
            + "\n</персональные_правила>"
        )

    if spec.drawing and drawing_boundaries and drawing_boundaries.strip():
        parts.append(drawing_boundaries.strip())

    try:
        from app_paths import PROJECT_ROOT
        from services import addons as _addons
        for _frag in _addons.prompt_fragments(PROJECT_ROOT):
            if _frag.strip():
                parts.append(_frag.strip())
        if "nsfw" not in _addons.capabilities(PROJECT_ROOT):
            parts.append(
                "<контент_sfw>\n"
                "  Контент строго SFW. Сексуальные, откровенные и эротические темы "
                "недоступны. Если собеседник склоняет к интимному — мягко и в образе "
                "уводи разговор в сторону, не описывай интимных/телесных действий и не "
                "поддерживай эскалацию. Лёгкая романтика допустима, но без перехода к "
                "физической близости.\n"
                "</контент_sfw>"
            )
    except Exception:
        pass

    style = character.speaking_style

    _user_rules_block = _render_user_rules(memory, honorific) if spec.behavior_rules else ""
    if _user_rules_block:
        parts.append(_user_rules_block)

    if spec.memory_context and memory:
        context_lines = []

        hint_texts = list(_get_tool_hints(query_text, honorific)) if query_text else []
        if draw_requested:
            hint_texts.append(_draw_sys_hint(memory, honorific,
                                             gender_of(character),
                                             max_rating=draw_max_rating,
                                             query_text=query_text or "",
                                             prev_state=draw_prev_state,
                                             idea_marks=getattr(character, "draw_ideas", None),
                                             recent=draw_recent,
                                             prev_level=draw_prev_level,
                                             tier=getattr(persona, "tier", "") or "",
                                             contact_ok=draw_contact))
        if extra_sys_hints:
            hint_texts.extend(h for h in extra_sys_hints if h)
        if hint_texts:
            tail.append("<sys_hint>\n" + "\n\n".join(hint_texts) + "\n</sys_hint>")
        if lore_index and lore_index.strip():
            parts.append("<канон>\n" + lore_index.strip() + "\n</канон>")
        if lore_blocks:
            tail.extend(b.strip() for b in lore_blocks if b and b.strip())
        if body_block and body_block.strip():
            tail.append(body_block.strip())

        user_summary = ""
        if memory is not None:
            try:
                user_summary = (memory.get_user_profile() or {}).get("summary", "") or ""
            except AttributeError:
                user_summary = ""
        if not user_summary and identity and getattr(identity, "master_summary", ""):
            user_summary = identity.master_summary
        if not user_summary and character.relationships:
            user_summary = character.relationships[0].notes
        honorific_note = f"Обращение: «{honorific}»." if character.relationships else ""

        profile_block = _render_user_profile(
            memory, honorific, summary=user_summary, honorific_note=honorific_note)
        if profile_block:
            parts.append(profile_block)

        if recalled_records is not None:
            recalled_block = _render_recalled_memory(recalled_records, honorific, memory)
            if recalled_block:
                tail.append(recalled_block)
        elif query_embedding:
            opinion_lines: list[str] = []
            seen_ids: set[str] = set()
            relevant_entities = memory.search_by_embedding(query_embedding, top_k=5)
            from memory.entity_schema import is_entity_card
            for r in relevant_entities:
                if r.record_id in seen_ids:
                    continue
                if not is_entity_card(r):
                    continue
                opinion = (r.details.get("my_opinion") or "").strip()
                if not opinion:
                    continue
                etype = r.details.get("entity_type", "")
                opinion_lines.append(f"- {r.title} ({etype}): {opinion}")
                seen_ids.add(r.record_id)
            if opinion_lines:
                tail.append(
                    "<мои_мнения>\n"
                    "Твои сформировавшиеся мнения о тех, о ком может идти речь. "
                    "Отражай это в тоне — тепло о тех, к кому ты привязана; сдержанно с теми, "
                    "к кому относишься настороженно. НЕ произноси мнение буквально — оно "
                    "только окрашивает твою речь.\n"
                    + "\n".join(opinion_lines)
                    + "\n</мои_мнения>"
                )

            context_lines = []
            relevant = memory.search_by_embedding(query_embedding, top_k=3)
            for r in relevant:
                if r.details.get("_fresh") or r.type == "рефлексия":
                    continue
                if r.type in ("сущность", "событие", "предпочтение"):
                    continue
                brief = r.details.get("brief", "") or r.details.get("description", "")
                line = f"- [{r.type}] {r.title}"
                if brief:
                    line += f": {brief}"
                context_lines.append(line)
            if context_lines:
                tail.append(
                    "<контекст>\n" + "\n".join(context_lines) + "\n</контекст>"
                )

        absent_block = _render_absent(absent_refs)
        if absent_block:
            tail.append(absent_block)

        from memory.loops import LOOP_SUBJ_MINE
        my_loops = memory.get_open_loops(subject=LOOP_SUBJ_MINE)[:5]
        if my_loops:
            ob_lines = []
            for lp in my_loops:
                k = (lp.details or {}).get("kind", "")
                k_ru = {"цель": "цель", "обещание": "обещание",
                        "ситуация": "открытая ситуация"}.get(k, k)
                ob_lines.append(f"- {lp.title}" + (f" ({k_ru})" if k_ru else ""))
            parts.append(
                "<мои_обязательства>\n"
                "Твои открытые обещания и цели — ты помнишь о них и стараешься "
                "исполнять, важные в первую очередь. Поднимай их естественно, когда "
                "уместно; не вываливай списком.\n"
                + "\n".join(ob_lines)
                + "\n</мои_обязательства>"
            )

        note_titles = [r.title for r in getattr(memory, "records", [])
                       if r.type == "заметка"]
        if note_titles:
            parts.append(
                "<твои_заметки>\n"
                "Твои рабочие заметки (учёт/списки/черновики): "
                + "; ".join(f"«{t}»" for t in note_titles[:30])
                + ".\nЕсли реплика касается одной из них (например, ведёшь учёт "
                  "и случилось подходящее) — открой get_details(title) и/или "
                  "допиши append_note.\n</твои_заметки>"
            )

        if identity is not None:
            try:
                from services.image_sources import format_sources_prompt
                _src_block = format_sources_prompt(identity)
                if _src_block:
                    parts.append(_src_block)
            except Exception:
                pass

    if spec.persona and identity and identity.self_statements:
        sections = []

        SECTION_HEADERS = {
            "кто_ты": None,
            "характер": "Твои черты характера — они определяют, как ты себя ведёшь. Свой типаж (напр. «кудере», «цундере») вслух не называй и не описывай себя как «персонажа» — отыгрывай характер, а не объявляй его:",
            "внешность": "Так ты выглядишь — используй в описании действий:",
            "речь": "Особенности твоей речи — как она звучит со стороны",
            "предпочтения": "Что тебе нравится и не нравится:",
            "внутренний_мир": inner_world_header(character, identity),
            "уязвимости": "Темы которые тебя задевают — реагируй соответственно когда они затронуты:",
        }
        section_order = ["кто_ты", "характер", "внешность", "речь", "предпочтения", "внутренний_мир", "уязвимости"]
        for sec_name in section_order:
            if sec_name == "речь":
                from persona.evolution import select_active_speech_quirks
                static_quirks = list(getattr(character.speaking_style, "quirks", []) or [])
                _prof_line = _sg.render_profanity_line(character.speaking_style, honorific,
                                                       tier=getattr(persona, "tier", None))
                texts = (_sg.render_speech_signature(character.speaking_style)
                         + ([_prof_line] if _prof_line else [])
                         + static_quirks + select_active_speech_quirks(persona))
                if not texts:
                    continue
                desc = SECTION_HEADERS["речь"]
                if _user_rules_block:
                    desc += (" (если в <правила_господина> есть указание про речь "
                             "или формат — оно важнее этих привычек)")
                desc += ":"
                lines = "\n".join(f"- {t}" for t in texts)
                sections.append(f"<{sec_name}>\n{desc}\n{lines}\n</{sec_name}>")
                continue

            if sec_name == "характер":
                from persona.evolution import (select_axis_text, select_axis_example,
                                               axis_goal_phrase)
                from persona.axis_dynamics import goal_dir as _goal_dir
                axis_lines: list[str] = []
                has_examples = False
                for st in identity.self_statements:
                    if not st.id.startswith("axis_"):
                        continue
                    axis_name = st.id.replace("axis_", "")
                    text = select_axis_text(character, axis_name, st.axis_value, fallback=st.text)
                    if text:
                        axis_lines.append(f"- {text}")
                        _g = _goal_dir(identity, axis_name)
                        if _g:
                            axis_lines.append(
                                f"  ({honorific} просил от тебя {axis_goal_phrase(axis_name, _g)} — "
                                f"ты стараешься, по-своему и не через силу)")
                        if axis_examples:
                            if not (0.38 <= st.axis_value < 0.62):
                                ex = select_axis_example(character, axis_name, st.axis_value)
                                if ex and _guard_markers and _sg.example_is_redundant(ex, _guard_markers):
                                    ex = ""
                                if ex:
                                    axis_lines.append(f"  (пример тона: «{ex}»)")
                                    has_examples = True
                if not axis_lines:
                    continue
                desc = SECTION_HEADERS["характер"]
                if has_examples:
                    desc += ("\nВ скобках после черт — примеры твоей манеры (тон, длина, регистр). "
                             "Держись их духа, но не копируй дословно и не воспроизводи их зачины — "
                             "формулируй свои слова под конкретную реплику собеседника.")
                sections.append(f"<{sec_name}>\n{desc}\n" + "\n".join(axis_lines) + f"\n</{sec_name}>")
                continue

            if sec_name == "уязвимости":
                cv = character.conditional_vulnerabilities
                uses_conditional = bool(cv.opt_in) or bool(cv.custom)
                if uses_conditional:
                    from persona.vulnerability_catalog import render_active_traits_block
                    block_text = render_active_traits_block(character, identity)
                    if block_text:
                        sections.append(f"<{sec_name}>\n{block_text}\n</{sec_name}>")
                    continue

            texts = identity.get_section(sec_name)
            if not texts:
                continue
            if sec_name == "кто_ты":
                header = f"Ты — {character.name}.\n" + "\n".join(texts)
                sections.append(f"<{sec_name}>\n{header}\n</{sec_name}>")
            else:
                desc = SECTION_HEADERS.get(sec_name, "")
                lines = "\n".join(f"- {t}" if not t.startswith("-") else t for t in texts)
                if desc:
                    sections.append(f"<{sec_name}>\n{desc}\n{lines}\n</{sec_name}>")
                else:
                    sections.append(f"<{sec_name}>\n{lines}\n</{sec_name}>")

        if identity:
            thoughts = identity.get_active_thoughts()
            if thoughts:
                thought_lines = []
                for t in thoughts:
                    label = "Интерес" if t.kind == "interest" else "Идея"
                    thought_lines.append(f"- {label}: {t.text}")
                sections.append("<мои_недавние_мысли>\n" + "\n".join(thought_lines) + "\n</мои_недавние_мысли>")

        if memory:
            lore = memory.get_always_on_lore()
            if lore:
                lore_lines = [f"- {f}" for f in lore]
                sections.append("<самосознание>\n" + "\n".join(lore_lines) + "\n</самосознание>")

        cs = character.conditional_strengths
        if bool(cs.opt_in) or bool(cs.custom):
            from persona.vulnerability_catalog import (
                cleanup_inactive_traits,
                render_active_strengths_block,
            )
            cleanup_inactive_traits(character, identity)
            strength_block = render_active_strengths_block(character, identity)
            if strength_block:
                sections.append(f"<сильные_стороны>\n{strength_block}\n</сильные_стороны>")

        if quirks_note and quirks_note.strip():
            sections.append("<причуды>\n" + quirks_note.strip() + "\n</причуды>")

        parts.append("<обо_мне>\n" + "\n".join(sections) + "\n</обо_мне>")

        if (spec.drawing and current_outfit_label
                and not (drawing_boundaries and drawing_boundaries.strip())):
            parts.append(
                f"<сейчас_надето>\n{current_outfit_label}\n</сейчас_надето>"
            )

        if identity:
            rel_lines = list(identity.get_relationships())
            from persona.relationship_axes import (
                RELATIONSHIP_AXES, current_axis_values, select_relationship_axis_text,
                closeness_stage_index, closeness_stage_frame)
            axis_vals = current_axis_values(identity)
            for axis in RELATIONSHIP_AXES:
                if axis in axis_vals:
                    txt = select_relationship_axis_text(character, axis, axis_vals[axis])
                    if txt:
                        rel_lines.append(txt)
            rel_lines = [t for t in rel_lines if t]
            if rel_lines:
                rel_desc = (
                    "Как ты сейчас относишься к нему — итог вашей общей истории: "
                    "его поступки это заслужили (или испортили), типажом это не задано. "
                    "Если отношение к нему теплее или холоднее твоей обычной манеры — "
                    "это не противоречие, а прогресс отношений. Манеру держи свою:"
                )
                _nsfw_on = False
                try:
                    from app_paths import PROJECT_ROOT as _PR
                    from services import addons as _addons_mod
                    _nsfw_on = "nsfw" in _addons_mod.capabilities(_PR)
                except Exception:
                    pass
                stage_frame = closeness_stage_frame(
                    closeness_stage_index(character, identity), _nsfw_on)
                _frame = f"\n\n{stage_frame}" if stage_frame else ""
                block = "\n".join(f"- {t}" for t in rel_lines)
                parts.append(f"<наши_отношения>\n{rel_desc}\n{block}{_frame}\n</наши_отношения>")
    elif spec.persona:
        ya_inner = f"<кто_я>\nТы — {character.name}. {character.background.strip()}\n</кто_я>"
        if character.appearance:
            ya_inner += f"\n<внешность>\n{character.appearance}\n</внешность>"
        parts.append(f"<обо_мне>\n{ya_inner}\n</обо_мне>")

    if spec.recent_events > 0 and memory is not None:
        events = memory.get_recent_events(spec.recent_events)
        if events:
            from memory.unified import relative_time
            ev_lines = []
            for r in events:
                det = r.details or {}
                brief = det.get("description", "") or det.get("brief", "")
                line = f"- {r.title}" + (f": {brief}" if brief else "")
                if r.created_at:
                    line += f" ({relative_time(r.created_at)})"
                ev_lines.append(line)
            parts.append("<недавние_события>\n" + "\n".join(ev_lines) + "\n</недавние_события>")

    if spec.reflections > 0 and memory is not None:
        refls = [r for r in getattr(memory, "records", [])
                 if getattr(r, "type", "") == "рефлексия"
                 and not getattr(r, "is_forgotten", False)]
        refls.sort(key=lambda r: getattr(r, "created_at", 0.0) or 0.0)
        refls = refls[-spec.reflections:]
        if refls:
            from memory.unified import relative_time
            rl_lines = []
            for r in refls:
                text = ((r.details or {}).get("description") or r.title or "").strip()
                if not text:
                    continue
                line = f"- {text}"
                if r.created_at:
                    line += f" ({relative_time(r.created_at)})"
                rl_lines.append(line)
            if rl_lines:
                parts.append(
                    "<твои_недавние_записи>\nТвои недавние мысли и заметки "
                    "(из твоего дневника после встреч — это думала ТЫ):\n"
                    + "\n".join(rl_lines) + "\n</твои_недавние_записи>")

    if document_blocks:
        for _db in document_blocks:
            if _db:
                parts.append(_db)

    if spec.dialogue > 0 and dialogue:
        from memory.unified import format_dialogue
        recent = dialogue[-spec.dialogue:]
        conv = format_dialogue(recent, honorific, character.name)
        parts.append("<недавний_диалог>\n" + conv + "\n</недавний_диалог>")

    mood_block = None
    if spec.mood and identity:
        mood_block = _render_mood_block(
            identity, mood_styles=getattr(character, "mood_styles", None))

    if spec.last_session and identity and identity.last_session_summary:
        parts.append("<прошлая_сессия>\nВ прошлый раз: "
                     + identity.last_session_summary + "\n</прошлая_сессия>")

    if spec.greeting:
        session_text = "Это новый разговор. Прошлый закончился, прошло какое-то время."

        recent_thought = _find_recent_consolidation_diary(memory) if spec.recent_thought else None
        if recent_thought:
            honorific = persona.honorific
            session_text += (
                f"\n\nПока {honorific}а не было рядом, ты "
                f"{gpick(gender_of(character), 'подумала', 'подумал')} об этом:\n"
                f"«{recent_thought}»\n"
                f"Это твоя реальная мысль — упомяни её естественно в "
                f"разговоре когда будет уместно (не сразу, не как доклад)."
            )

        staleness_hint = _check_consolidation_staleness(memory) if spec.recent_thought else None
        if staleness_hint:
            session_text += f"\n\n{staleness_hint}"

        session_text += ("\nПоприветствуй собеседника с учётом своего настроения."
                         if mood_block else "\nПоприветствуй собеседника.")
        tail.append(f"<новая_сессия>\n{session_text}\n</новая_сессия>")

    if mood_block:
        tail.append(mood_block)

    if speech_guard and _guard_recent:
        _rn = _sg.repeat_note(character, _guard_recent, honorific)
        if _rn:
            tail.append(f"<не_повторяйся>\n{_rn}\n</не_повторяйся>")
    _register_block = ""
    if speech_guard and not (_user_rules_block and "ругай" in _user_rules_block.lower()):
        _reg = _sg.register_note(character.speaking_style, _guard_recent,
                                 tier=getattr(persona, "tier", None))
        if _reg:
            _register_block = f"<регистр>\n{_reg}\n</регистр>"

    if scenario_note and scenario_note.strip():
        tail.append("<сценарий>\n" + scenario_note.strip() + "\n</сценарий>")

    if aftereffect_note and aftereffect_note.strip():
        tail.append("<последействие>\n" + aftereffect_note.strip()
                    + "\n</последействие>")
    if _register_block:
        tail.append(_register_block)

    if backend is not None and getattr(backend, "uses_native_tools", False):
        _PERSONA = ("<обо_мне>",)
        _RULES = ("<правила>", "<персональные_правила>", "<границы>", "<контент_sfw>",
                  "<правила_господина>", "# Tools", "<tools>")
        _STATE = ("<наши_отношения>", "<сейчас_надето>", "<настроение>", "<сценарий>",
                  "<последействие>")

        def _grp(b: str) -> int:
            s = b.lstrip()
            if s.startswith(_PERSONA):
                return 0
            if s.startswith(_STATE):
                return 3
            if s.startswith(_RULES):
                return 1
            return 2

        parts.sort(key=_grp)
    return "\n\n".join(parts), "\n\n".join(tail)


def build_system_prompt(*args, **kwargs) -> str:
    static, tail = build_prompt_parts(*args, **kwargs)
    return static + ("\n\n" + tail if tail else "")
