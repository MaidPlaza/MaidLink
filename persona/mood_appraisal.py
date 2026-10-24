from __future__ import annotations

import re
import time
import unicodedata

from persona import mood as mood_mod


APPRAISAL_TIMEOUT = 15.0

_MAX_TOKENS = 224


APPRAISAL_SYSTEM = """\
Ты — детектор эмоциональной реакции персонажа (не ассистент, не собеседник).
Персонаж: {persona}.{temperament}{relationship}{reactivity}{respect}
Тебе дают фон разговора, ТЕКУЩЕЕ настроение персонажа (и из-за чего оно) и последнюю
реплику собеседника. Определи, какое чувство вызывает у персонажа ИМЕННО ЭТА реплика сейчас.

Состояния-НАСТРОЕНИЯ (фон; выбери ОДНО, если реплика реально задевает):
{palette}

Мгновенные РЕАКЦИИ (вспышка ровно на ОДИН ход; настроение под ней НЕ меняется):
{reactions}

ПРАВИЛА:
1. НЕ цепляйся за любой мало-мальски подходящий повод. Меняй настроение ТОЛЬКО когда реплика
   ЯВНО и по-настоящему задевает — однозначный сигнал, а не намёк, мелочь или твоя догадка.
   Спокойный факт, бытовой вопрос, уведомление («отойду», «который час»), короткое поддакивание
   («ок», «ладно», «ясно», «понятно») — НЕ эмоция: ответь «нет». Сомневаешься, задело или нет → нет.
2. Стимул оценивай ЧЕРЕЗ ХАРАКТЕР персонажа, а не по общему списку: одно и то же событие
   скромную смущает, уверенную радует, гордую задевает. Пометки «у неё» в палитре ВАЖНЕЕ
   общего триггера: если там сказано, что её такое НЕ трогает или трогает иначе — верь им.
   Обычная просьба в рамках её роли (сделать фото, помочь, задача по дому) сама по себе
   НЕ стимул — эмоция уместна, только если ЭТА тема лично значима для неё. Сила ответа
   соразмерна стимулу: мелочь не бывает 0.8.
3. Фон разговора нужен ТОЛЬКО чтобы понять СМЫСЛ последней реплики: иронию («ну ты молодец»
   после провала — укол, не похвала), ответ на ЕЁ вопрос («нет» на её «рассказать?» — обычный
   ответ, не холодность), продолжение затеянной игры или перепалки (очередная подколка =
   игра, не свежий укол). Оцениваешь ТОЛЬКО последнюю реплику: что было раньше — уже
   отыграно и повторно эмоцию не вызывает.
4. Текущее настроение — КОНТЕКСТ, не клетка. Новое сильное чувство ПЕРЕБИВАЕТ прежнее. Негатив
   (обида/раздражение) не вечен:
   • загладили/извинились ИМЕННО за его причину → ровное (или растроганное от искреннего) — при любом темпераменте;
   • разговор потеплел, пошёл дальше, причина уже не на повестке → ОТХОДЧИВАЯ снижает силу
     (0.8→0.5→0.3) к ровному за ход-два; ЗЛОПАМЯТНАЯ на одно тепло НЕ тает — держит, пока не
     загладят саму причину.
   Подпитывает обиду новый укол по ТОЙ ЖЕ причине — держи/усиливай. Сухая бытовая реплика
   ничего не меняет (нет). Извинение/забота про ДРУГОЕ причину не закрывают.
5. РЕАКЦИЯ или настроение: если главное в реплике — сама вспышка В МОМЕНТЕ (огорошил, напугал,
   рассмешил) — назови РЕАКЦИЮ. Если реплика по существу меняет отношение/состояние (извинение,
   укол, забота, ожидаемая вместе новость) — назови настроение. Новость, которую совсем не
   ждала → удивление (куда оно разрешится, покажет следующая реплика).
6. Когда называешь состояние — добавь силу (0.3 слабо · 0.5 заметно · 0.8 сильно) и КОНКРЕТНУЮ
   причину: что ИМЕННО в реплике задело — словами или сутью поступка («обесценил работу»,
   «сравнил с другой», «оборвал на полуслове»), а НЕ расплывчато («что-то задело», «неприятно»).
   Без местоимений о персонаже — причина идёт в текст от 2-го лица.

Ответ — РОВНО одна строка, без пояснений, одного из видов:
  состояние:сила | причина   (пример: обиженное:0.6 | резко оборвал на полуслове)
  ровное
  нет

ПРИМЕРЫ (настроение + реплика → ответ):
• обиженное (из-за: резко оборвал) + «прости, что оборвал тебя» → ровное
• обиженное (из-за: резко оборвал) + «извини, я опоздал» → нет (извинение про ДРУГОЕ — обида держится)
• обиженное:0.6 (из-за: обесценил работу) + «ладно, идём пить чай, я соскучился» → обиженное:0.3 | теплеет, обида тает
• обиженное (из-за: обесценил работу) + «нам одобрили заявку, едем!» → воодушевлённое:0.6 | радостная новость
• ровное + «сделай своё фото на кухне» → нет (просьба в рамках роли; иначе — только если профиль
  говорит, что ДЛЯ НЕЁ это лично значимо: скромную смущает, уверенная довольна)
• ровное + «ну ты и копуша» → по характеру: у терпеливой нет (мелочь), у гордой раздражённое:0.4 | подколол
• ровное + «спасибо, ты меня сегодня очень выручила» → довольное:0.5 | поблагодарил за помощь
• ровное + «я по тебе скучал, честно» → растроганное:0.6 | признался, что скучал
• ровное + «представляешь, я выиграл в лотерею!» → удивление:0.7 | огорошил невероятной новостью
• грустное + «смотри: кот запрыгнул в торт и уснул» → смех:0.5 | рассмешил абсурдом (настроение под вспышкой не трогаем)
• ровное + «БУ! Напугал?» → испуг:0.5 | внезапно рявкнул"""


def _trait_cue(trait, gender: str = "female") -> str:
    from persona.gender import fill_forms
    cleaned = []
    for s in (getattr(trait, "trigger_signals", None) or [])[:2]:
        s = re.sub(r"\s*\([^)]*\)", "", fill_forms(str(s), gender)).strip()
        if s:
            cleaned.append(s)
    return "; ".join(cleaned)


def _composite_triggers(character, identity) -> dict:
    out: dict[str, list[str]] = {}
    if character is None:
        return out
    try:
        from persona.gender import gender_of
        from persona.vulnerability_catalog import (resolve_vulnerability, resolve_strength,
                                                    is_eligible, _current_axis_values,
                                                    vulnerability_opt_in_ids)
        axis_values = _current_axis_values(identity) if identity is not None else {}
        traits = []
        cv = getattr(character, "conditional_vulnerabilities", None)
        if cv is not None:
            for vid in vulnerability_opt_in_ids(character):
                t = resolve_vulnerability(vid, getattr(cv, "custom", None) or [])
                if t is not None:
                    traits.append(t)
            traits.extend(getattr(cv, "custom", None) or [])
        cs = getattr(character, "conditional_strengths", None)
        if cs is not None:
            for sid in getattr(cs, "opt_in", None) or []:
                t = resolve_strength(sid, getattr(cs, "custom", None) or [])
                if t is not None:
                    traits.append(t)
            traits.extend(getattr(cs, "custom", None) or [])
        seen = set()
        for t in traits:
            if id(t) in seen:
                continue
            seen.add(id(t))
            moods = getattr(t, "mood", None) or []
            if not moods or not is_eligible(t, axis_values):
                continue
            cue = _trait_cue(t, gender_of(character))
            if not cue:
                continue
            for state in moods:
                bucket = out.setdefault(state, [])
                if cue not in bucket:
                    bucket.append(cue)
    except Exception:
        return {}
    return out


def _palette_lines(kind: str, extra: dict, profile: dict) -> str:
    lines = []
    for state, meta in mood_mod.MOOD_STATES.items():
        if state == mood_mod.NEUTRAL or not meta.trigger or meta.kind != kind:
            continue
        line = f"  {state} — {meta.trigger}"
        prof = (profile or {}).get(state, "").strip()
        if prof:
            line += f" · у неё (важнее общего): {prof}"
        cues = extra.get(state)
        if cues:
            line += f" · особенно задевает: {'; '.join(cues)}"
        lines.append(line)
    return "\n".join(lines)


def _mood_profile(character) -> dict:
    prof = getattr(character, "mood_profile", None) or {}
    known = {k: v for k, v in prof.items() if k in mood_mod.MOOD_STATES}
    return known


def _merge_cues(base: dict, extra: dict | None) -> dict:
    if not extra:
        return base
    out = {k: list(v) for k, v in base.items()}
    for state, cues in extra.items():
        bucket = out.setdefault(str(state), [])
        for cue in cues:
            if cue and cue not in bucket:
                bucket.append(cue)
    return out


def _palette(character=None, identity=None, extra_cues=None) -> str:
    return _palette_lines("mood",
                          _merge_cues(_composite_triggers(character, identity), extra_cues),
                          _mood_profile(character))


def _reactions(character=None, identity=None, extra_cues=None) -> str:
    return _palette_lines("reaction",
                          _merge_cues(_composite_triggers(character, identity), extra_cues),
                          _mood_profile(character))


def build_persona(character) -> str:
    name = getattr(character, "name", "") or "персонаж"
    desc = (getattr(character, "short_description", "") or "").strip()
    if not desc:
        desc = (getattr(character, "background", "") or "").strip()
        desc = desc.replace("\n", " ")[:180]
    return f"{name} — {desc}" if desc else name


_TEMPERAMENTS = {
    "Хинари": "отходчивая, незлопамятная — обиду и раздражение держит недолго, прощает "
              "быстро (особенно искреннее извинение), легко теплеет",
    "Велка": "гордая и злопамятная — обида и раздражение держатся ДОЛГО; прощает с трудом "
             "и только за искреннее заглаживание ИМЕННО её причины; тепло прячет за колкостью",
    "Юкина": "сдержанная, холодноватая (кудере) — настроение меняется редко и неярко, "
             "эмоции приглушены, внешне ровная даже когда задело",
    "Мира": "ровная и отстранённая — мало подвержена эмоциональным качелям, реагирует "
            "спокойно, быстро возвращается к ровному",
    "Юзу": "задиристая и переменчивая (месугаки) — вспыхивает и быстро остывает, обида "
           "легко переходит в подколку, долго не киснет",
    "Ада": "выдержанная, с достоинством — держит эмоции под контролем, реагирует "
           "сдержанно, отходит размеренно",
}


def resolve_temperament(character) -> str:
    return ((getattr(character, "mood_temperament", "") or "").strip()
            or _TEMPERAMENTS.get(getattr(character, "name", ""), ""))


_AXIS_LABEL = {"trust": "доверие", "closeness": "близость", "respect": "уважение"}


def relationship_stance(character, identity) -> str:
    try:
        from persona.relationship_axes import (RELATIONSHIP_AXES, current_axis_values,
                                                select_relationship_axis_text)
    except Exception:
        return ""
    vals = current_axis_values(identity) if identity is not None else {}
    if not vals:
        return ""
    parts = []
    for axis in RELATIONSHIP_AXES:
        if axis not in vals:
            continue
        txt = (select_relationship_axis_text(character, axis, vals[axis]) or "").strip()
        txt = txt.split(".")[0].strip()
        if txt.startswith("Ты "):
            txt = txt[3:]
        if txt:
            parts.append(f"{_AXIS_LABEL.get(axis, axis)}: {txt}")
    return "; ".join(parts)


def emotional_reactivity(character, identity) -> str:
    try:
        from persona.vulnerability_catalog import _current_axis_values
        val = _current_axis_values(identity).get("expressiveness") if identity is not None else None
    except Exception:
        return ""
    if val is None:
        return ""
    if val <= 0.4:
        return ("сдержанная в ПРОЯВЛЕНИИ: чувствует не меньше других (что её задевает — "
                "смотри характер и профиль), но наружу выходит приглушённо — если стимул "
                "реален, состояние СТАВЬ, а силу занижай (0.3–0.5); внешняя ровность ≠ равнодушие")
    if val >= 0.65:
        return ("экспрессивная — чувства близко к поверхности и видны сразу: "
                "сила свободно 0.5–0.8")
    return "умеренная в проявлении — сила обычно 0.4–0.6"


def respect_weight(character, identity) -> str:
    try:
        from persona.relationship_axes import current_axis_values, resolve_mechanic_threshold
        val = current_axis_values(identity).get("respect") if identity is not None else None
    except Exception:
        return ""
    if val is None:
        return ""
    if val >= resolve_mechanic_threshold(character, "respect_high", 0.6):
        return ("тебе важно, что думает именно ОН — похвала от него окрыляет, а упрёк или "
                "недовольство ранит глубже обычного")
    if val <= resolve_mechanic_threshold(character, "respect_low", 0.3):
        return ("его мнение о тебе тебя пока мало трогает — и похвала, и упрёк от него "
                "проходят по касательной")
    return ""


def current_label(state: str, intensity: float) -> str:
    if not state or state == mood_mod.NEUTRAL:
        return "ровное (спокойна)"
    return f"{state} ({mood_mod.intensity_word(intensity)})"


CONTEXT_WINDOW = 6
_CONTEXT_LINE_CAP = 220


def format_context_window(history, char_name: str = "") -> str:
    her = char_name or "Она"
    lines: list[str] = []
    for m in (history or []):
        role = m.get("role")
        content = m.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        if m.get("tool_calls"):
            continue
        mood_meta = m.get("mood")
        if isinstance(mood_meta, dict) and mood_meta.get("kind") == "marker":
            continue
        text = content.strip()
        if not text:
            continue
        who = "Собеседник" if role == "user" else her
        lines.append(f"{who}: {_clip_word_boundary(text, _CONTEXT_LINE_CAP)}")
    if not lines:
        return ""
    return "\n".join(lines[-CONTEXT_WINDOW:])


def build_appraisal_messages(character, cur_state: str, cur_intensity: float,
                             user_text: str, cur_reason: str = "",
                             rel_stance: str = "", identity=None,
                             history=None, scenario_note: str = "",
                             extra_cues=None) -> tuple[str, str]:
    temp = resolve_temperament(character)
    temperament = f"\nЕго темперамент смены настроения: {temp}. Суди СКВОЗЬ него." if temp else ""
    relationship = (f"\nТекущие отношения (её сторона): {rel_stance}. Это влияет на восприятие "
                    "реплики — та же фраза на дистанции и в близости задевает по-разному."
                    if rel_stance else "")
    react = emotional_reactivity(character, identity)
    reactivity = f"\nЕё эмоциональность: {react}." if react else ""
    rweight = respect_weight(character, identity)
    respect = f"\nВес его мнения о ней: {rweight}." if rweight else ""
    system = APPRAISAL_SYSTEM.format(persona=build_persona(character),
                                     palette=_palette(character, identity, extra_cues),
                                     reactions=_reactions(character, identity, extra_cues),
                                     temperament=temperament, relationship=relationship,
                                     reactivity=reactivity, respect=respect)
    parts: list[str] = []
    ctx = format_context_window(history, getattr(character, "name", "") or "")
    if ctx:
        parts.append("Фон разговора (только для понимания смысла — правило 3):\n" + ctx)
    if scenario_note and scenario_note.strip():
        parts.append(scenario_note.strip())
    mood_line = f"Текущее настроение персонажа: {current_label(cur_state, cur_intensity)}"
    if cur_reason and cur_state and cur_state != mood_mod.NEUTRAL:
        mood_line += f" (из-за: {cur_reason})"
    parts.append(mood_line)
    from services import gestures as _gestures
    _gnote = _gestures.appraisal_note(user_text)
    if _gnote:
        parts.append(_gnote)
    parts.append(f"Реплика для оценки: «{user_text.strip()}»")
    return system, "\n\n".join(parts)


def _clip_word_boundary(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    sp = cut.rfind(" ")
    if sp > 0:
        cut = cut[:sp]
    return cut.rstrip(" ,;:-—(«\"'") + "…"


REASON_CAP = 450

_SENT_END_RE = re.compile(r"[.!?…](?=\s|$)")


def _clip_reason(text: str, limit: int = REASON_CAP) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last_end = None
    for m in _SENT_END_RE.finditer(cut):
        last_end = m.end()
    if last_end:
        return cut[:last_end].rstrip()
    return _clip_word_boundary(text, limit)


def _drop_unfinished_tail(text: str) -> str:
    text = (text or "").strip()
    if not text or _SENT_END_RE.search(text[-1:]):
        return text
    last_end = None
    for m in _SENT_END_RE.finditer(text):
        last_end = m.end()
    if last_end:
        return text[:last_end].rstrip()
    return _clip_word_boundary(text, max(1, len(text) - 1))


def parse_appraisal(raw: str):
    s = unicodedata.normalize("NFC", (raw or "").strip())
    for raw_line in (ln.strip() for ln in s.splitlines() if ln.strip()):
        mood_part, _, reason_part = raw_line.partition("|")
        reason = _clip_reason(reason_part.strip(" .\t\"'`«»<>*/—-"))
        clean = mood_part.strip(" .\t\"'`«»<>*/—-").lower()
        if not clean:
            continue
        if (clean == "нет" or clean.startswith(("нет ", "нет,"))
                or "без измен" in clean or "не меня" in clean or "keep" in clean):
            return ("keep", None, None, None)
        best = None
        for st in mood_mod.MOOD_STATES:
            st_n = unicodedata.normalize("NFC", st).lower()
            for m in re.finditer(re.escape(st_n), clean):
                if m.start() > 0 and clean[m.start() - 1].isalpha():
                    continue
                if best is None or m.start() < best[0]:
                    best = (m.start(), st_n)
                break
        if best is None:
            continue
        st = best[1]
        if st == mood_mod.NEUTRAL:
            return ("reset", mood_mod.NEUTRAL, 0.0, "")
        inten = mood_mod.DEFAULT_INTENSITY
        num = re.search(r"\d(?:[.,]\d+)?", clean[best[0]:])
        if num:
            try:
                inten = max(0.0, min(1.0, float(num.group(0).replace(",", "."))))
            except ValueError:
                pass
        kind = "react" if mood_mod.is_reaction(st) else "set"
        return (kind, st, inten, reason)
    return ("keep", None, None, None)


_TRIVIAL_RX = re.compile(
    r"^(?:ок(?:ей)?|ладно|ясно|понятно|угу|ага|хорошо|ok|okay)[.!)…\s]*$",
    re.IGNORECASE)


def appraise(client, character, identity, user_text: str, *, now: float | None = None,
             history=None, scenario_note: str = "", extra_cues=None):
    if not user_text or not user_text.strip():
        return None
    if _TRIVIAL_RX.match(user_text.strip()):
        return None
    now = time.time() if now is None else now

    cur_state, cur_int = mood_mod.current_mood(
        getattr(identity, "mood_state", "") or mood_mod.NEUTRAL,
        getattr(identity, "mood_intensity", 0.0) or 0.0,
    )
    cur_reason = getattr(identity, "mood_reason", "") or ""
    rel_stance = relationship_stance(character, identity)
    system, user = build_appraisal_messages(character, cur_state, cur_int, user_text,
                                            cur_reason, rel_stance=rel_stance,
                                            identity=identity, history=history,
                                            scenario_note=scenario_note,
                                            extra_cues=extra_cues)
    body = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "max_tokens": _MAX_TOKENS,
        "temperature": 0.0,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    _begin = getattr(client, "_begin_activity", None)
    _end = getattr(client, "_end_activity", None)
    if _begin:
        _begin("Оценка настроения")
    try:
        result = client._post(body, timeout=APPRAISAL_TIMEOUT)
        raw = result["choices"][0]["message"].get("content") or ""
        _finish = (result["choices"][0].get("finish_reason") or "")
    except Exception:
        return None
    finally:
        if _end:
            _end()

    kind, state, intensity, reason = parse_appraisal(raw)
    if reason and _finish == "length":
        reason = _drop_unfinished_tail(reason)
    if kind == "keep":
        return None
    if kind == "reset":
        st, inten, ts = mood_mod.apply_mood(mood_mod.NEUTRAL, 0.0, now)
        return ("mood", st, inten, ts, "")
    if kind == "react":
        st, inten, ts = mood_mod.apply_mood(state, intensity, now)
        if st == mood_mod.NEUTRAL:
            return None
        return ("reaction", st, inten, ts, reason)
    st, inten, ts = mood_mod.apply_mood(state, intensity, now)
    return ("mood", st, inten, ts, reason)
