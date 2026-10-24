from __future__ import annotations

import json
import re

from persona.gender import g as gpick
from drawing.assets import RATING_ORDER, TIER_LABELS_RU, TIER_ORDER, rating_le, tier_ge
from drawing.catalog import AssetCatalog
from drawing.choice import Choice, ChoiceValidationError
from drawing.gate import GateResult, validate_choice


def format_chat_boundaries(
    *,
    catalog: AssetCatalog,
    character_gender: str = "female",
    character_pair: str = "",
    renderer_id: str,
    max_rating: str,
    current_tier: str,
    character_id: str,
    character_archetypes: list[str],
    outfit_change_min_tier: str = "warming",
    current_portrait_outfit_id: str | None = None,
    character_tag_gates: dict[str, str] | None = None,
    character_blocked_tags: list[str] | None = None,
    wardrobe=None,
    default_outfit_id: str | None = None,
    outfit_label: str | None = None,
    honorific: str = "Господин",
) -> str:
    outfits = catalog.compatible_outfits(
        renderer_id=renderer_id,
        max_rating=max_rating,
        current_tier=current_tier,
        character_pair=character_pair,
        character_id=character_id,
        character_archetypes=character_archetypes,
        character_tag_gates=character_tag_gates,
        character_blocked_tags=character_blocked_tags,
    )

    if not outfits:
        return (
            "<гардероб>\n"
            "Снимки сейчас недоступны вовсе — если попросят, откажи словами, "
            "в своём стиле.\n"
            "</гардероб>"
        )

    _names = [o.name for o in outfits if getattr(o, "name", "")]
    style_summary = ", ".join(_names[:4]) + (", …" if len(_names) > 4 else "")
    if not style_summary:
        style_summary = "разные"

    lines = ["<гардероб>"]

    if max_rating != "sfw":
        outfit_rule = (
            "На снимке ты в текущем наряде: другой наряд — сначала change_outfit, потом "
            "draw; обычную одежду в intent не описывай. Если решишь раздеться на снимке "
            "— снять часть одежды, остаться в белье или без одежды, — так прямо и "
            "напиши в intent: переодеваться для этого не нужно.")
    else:
        outfit_rule = (
            "На снимке ты всегда в текущем наряде: через intent одежда не меняется, не "
            "описывай её там. Снимок в другом наряде — сначала change_outfit, потом draw.")
    lines.append(
        "Снимок (инструмент draw): в своём цифровом мире ты можешь поймать себя "
        f"в кадр — какая ты сейчас, где и чем {gpick(character_gender, 'занята', 'занят')} "
        "— и отправить собеседнику. " + outfit_rule
    )
    lines.append("")

    def _oname(oid: str) -> str:
        o = catalog.outfits.get(oid)
        return (o.name if o else "") or oid

    effective_oid = current_portrait_outfit_id or default_outfit_id
    if outfit_label:
        lines.append(outfit_label.strip())
    elif effective_oid:
        line = f"На тебе сейчас: {_oname(effective_oid)} (outfit_id={effective_oid})"
        if effective_oid == default_outfit_id:
            line += " — твой обычный наряд."
        else:
            line += " — до конца сессии или до следующего change_outfit."
        lines.append(line)
    else:
        lines.append("Сейчас на портрете базовый вид (никакой outfit_id не активен).")
    if default_outfit_id and effective_oid and effective_oid != default_outfit_id:
        lines.append(
            f"Твой обычный наряд — {_oname(default_outfit_id)} "
            f"(outfit_id={default_outfit_id}): «вернись в своё» = change_outfit в него."
        )
    lines.append("")

    prepared_n = None
    if wardrobe is not None:
        try:
            prepared_n = sum(1 for o in outfits if wardrobe.is_prepared(o.id))
        except Exception:
            prepared_n = None
    ready_word = gpick(character_gender, "готова", "готов")
    if prepared_n is None:
        lines.append(
            f"В гардеробе {len(outfits)} нарядов, которые ты {ready_word} носить "
            f"({style_summary}). Точные outfit_id и то, что ты пока не хочешь "
            f"надевать, — list_outfits()."
        )
    else:
        lines.append(
            f"В гардеробе {len(outfits)} нарядов, которые ты {ready_word} носить "
            f"({style_summary}); подготовлено к переодеванию: {prepared_n}. "
            f"Точные outfit_id, готовность и то, что ты пока не хочешь надевать, "
            f"— list_outfits()."
        )

    if tier_ge(current_tier, outfit_change_min_tier):
        lines.append(
            f"Переодеваться по просьбе ты {ready_word}: list_outfits() → "
            f"change_outfit(outfit_id=…); в наряд, который уже на тебе, "
            f"переодеваться незачем."
        )
        if prepared_n is not None:
            lines.append(
                "Сменить наряд можно только на подготовленный (его портреты "
                "отрисованы заранее, смена мгновенна) — по неподготовленному "
                f"change_outfit не сработает. Подготовку запускает только "
                f"{honorific} в панели гардероба; нужен неготовый наряд — "
                f"попроси его об этом. Для тебя это «подгонка наряда», говори о "
                "ней в характере, без слова «система»."
            )
    else:
        lines.append(
            f"Переодеваться по просьбе ты пока не хочешь — вы ещё в начале "
            f"знакомства, и это слишком личное на нынешнем уровне доверия. "
            f"Попросят — откажи мягко и в характере («не сейчас, нам нужно лучше "
            f"узнать друг друга»), change_outfit не вызывай; это твоё личное "
            f"ощущение, а не запрет системы."
        )
    lines.append("")

    closed: list[str] = []
    rating_above = [r for r, v in RATING_ORDER.items()
                    if v > RATING_ORDER.get(max_rating, -1)]
    if rating_above:
        closed.append(
            "откровенные снимки закрыты настройками" if max_rating == "sfw"
            else "полностью откровенные снимки закрыты настройками"
        )
    tier_above = [t for t, v in TIER_ORDER.items() if v > TIER_ORDER.get(current_tier, -1)]
    if tier_above:
        next_label = TIER_LABELS_RU.get(tier_above[0], tier_above[0])
        closed.append(
            f"наряды, открывающиеся на ступени «{next_label}» и выше, пока "
            f"недоступны — не обещай их и не зови change_outfit по ним"
        )
    if closed:
        lines.append("Сейчас закрыто: " + "; ".join(closed) + ".")
    lines.append(
        "Просят недоступное — откажи в своём стиле, без вызова инструмента."
    )
    lines.append("</гардероб>")
    return "\n".join(lines)


DEFAULT_MAX_RETRIES = 1


def build_choice_prompt(
    *,
    character_name: str,
    character_gender: str = "female",
    character_pair: str = "",
    user_intent: str,
    catalog: AssetCatalog,
    renderer_id: str,
    max_rating: str,
    current_tier: str,
    character_id: str,
    character_archetypes: list[str],
    refusal_style_hint: str | None = None,
    retry_message: str | None = None,
    character_tag_gates: dict[str, str] | None = None,
    character_blocked_tags: list[str] | None = None,
    current_portrait_outfit_id: str | None = None,
) -> str:
    outfits = catalog.compatible_outfits(
        renderer_id=renderer_id,
        max_rating=max_rating,
        current_tier=current_tier,
        character_pair=character_pair,
        character_id=character_id,
        character_archetypes=character_archetypes,
        character_tag_gates=character_tag_gates,
        character_blocked_tags=character_blocked_tags,
    )
    scenes = catalog.compatible_scenes(renderer_id=renderer_id, max_rating=max_rating)
    poses = catalog.compatible_poses(renderer_id=renderer_id, max_rating=max_rating)

    sections: list[str] = []
    sections.append(f"Ты — {character_name}. Пользователь попросил тебя нарисовать что-то.")
    sections.append("")
    sections.append("Твоя задача — выбрать какие именно ассеты использовать для рисунка.")
    sections.append("Ты НЕ пишешь промпт сама — есть готовые ассеты, ты выбираешь из них.")
    sections.append("")

    if current_portrait_outfit_id:
        outfit_obj = next(
            (o for o in outfits if o.id == current_portrait_outfit_id), None
        )
        outfit_label = (
            f"{current_portrait_outfit_id} ({outfit_obj.name})"
            if outfit_obj else current_portrait_outfit_id
        )
        sections.append(
            "<текущий_наряд>\n"
            f"Сейчас ты одета в: {outfit_label}.\n"
            "Действие рисунка происходит СЕЙЧАС — ты в ЭТОМ ЖЕ наряде.\n"
            f"ВСЕГДА бери outfit_id={current_portrait_outfit_id!r}, даже если\n"
            "intent упоминает другую одежду. Сменить наряд можно ТОЛЬКО через\n"
            "отдельную функцию change_outfit — НЕ через рисунок. intent\n"
            "управляет только МЕСТОМ, ПОЗОЙ и НАСТРОЕНИЕМ (сцена/поза/\n"
            "модификаторы), но НЕ одеждой.\n"
            "</текущий_наряд>"
        )
        sections.append("")

    sections.append(_format_outfits_block(outfits))
    sections.append("")
    sections.append(_format_scenes_block(scenes))
    sections.append("")
    sections.append(_format_poses_block(poses))
    sections.append("")
    sections.append(_format_modifiers_block(catalog, renderer_id))
    sections.append("")
    sections.append(_format_boundaries_block(max_rating, current_tier))
    sections.append("")
    sections.append(_format_request_block(user_intent))
    sections.append("")
    sections.append(_format_rules_block(refusal_style_hint, character_gender))
    sections.append("")
    sections.append(_format_schema_block())

    if retry_message:
        sections.append("")
        sections.append("<предыдущая_попытка_не_прошла>")
        sections.append(retry_message)
        sections.append("Перевыбери из доступных ассетов. Если запрос изначально")
        sections.append("невозможен — установи requested_unavailable=true и объясни в refusal_reason.")
        sections.append("</предыдущая_попытка_не_прошла>")

    return "\n".join(sections)


def _format_outfits_block(outfits) -> str:
    if not outfits:
        return ("<доступные_костюмы>\n"
                "(никаких доступных костюмов сейчас — нужно отказаться)\n"
                "</доступные_костюмы>")
    lines = ["<доступные_костюмы>"]
    for o in outfits:
        tags = ", ".join(o.tags) if o.tags else "—"
        compat = o.compatibility
        if compat.scenes:
            compat_line = f"совместима со сценами: {', '.join(compat.scenes)}"
        else:
            compat_line = "совместима со всеми сценами"
        blocks_line = ""
        if compat.blocks:
            blocks_line = f"; плохо смотрится с: {', '.join(compat.blocks)}"
        lines.append(f"- {o.id}: {o.name}")
        lines.append(f"    теги: {tags}")
        lines.append(f"    {compat_line}{blocks_line}")
    lines.append("</доступные_костюмы>")
    return "\n".join(lines)


def _format_scenes_block(scenes) -> str:
    if not scenes:
        return "<доступные_сцены>\n(нет доступных сцен)\n</доступные_сцены>"
    lines = ["<доступные_сцены>"]
    for s in scenes:
        tags = f" (теги: {', '.join(s.tags)})" if s.tags else ""
        lines.append(f"- {s.id} [{s.category}]: {s.name}{tags}")
    lines.append("</доступные_сцены>")
    return "\n".join(lines)


def _format_poses_block(poses) -> str:
    if not poses:
        return "<доступные_позы>\n(нет доступных поз)\n</доступные_позы>"
    lines = ["<доступные_позы>"]
    for p in poses:
        tags = f" (теги: {', '.join(p.tags)})" if p.tags else ""
        moods = f" (настроение: {', '.join(p.mood_hints)})" if p.mood_hints else ""
        lines.append(f"- {p.id} [{p.category}]: {p.name}{tags}{moods}")
    lines.append("</доступные_позы>")
    return "\n".join(lines)


def _format_modifiers_block(catalog: AssetCatalog, renderer_id: str) -> str:
    if not catalog.modifiers:
        return "<модификаторы>\n(нет модификаторов)\n</модификаторы>"

    lines = ["<модификаторы>"]
    lines.append("Для каждой категории выбери ОДНУ опцию и положи в modifiers:")
    for category_id in sorted(catalog.modifiers.keys()):
        cat = catalog.modifiers[category_id]
        opts = cat.options_for_renderer(renderer_id)
        if not opts:
            continue
        opt_ids = " | ".join(o.id for o in opts)
        desc = f" — {cat.description}" if cat.description else ""
        lines.append(f"  {category_id}: {opt_ids}{desc}")
    lines.append("</модификаторы>")
    return "\n".join(lines)


def _format_boundaries_block(max_rating: str, current_tier: str) -> str:
    rating_above = [r for r, v in RATING_ORDER.items()
                    if v > RATING_ORDER.get(max_rating, -1)]
    tier_above = [t for t, v in TIER_ORDER.items()
                  if v > TIER_ORDER.get(current_tier, -1)]

    lines = ["<текущие_границы>"]
    lines.append(f"NSFW-уровень: разрешено максимум {max_rating!r}.")
    if rating_above:
        lines.append(f"  Закрыто настройками: {', '.join(rating_above)}.")
    lines.append(f"Уровень отношений: {current_tier!r}.")
    if tier_above:
        lines.append(f"  Не достигнуто: {', '.join(tier_above)} (костюмы требующие выше — закрыты).")
    lines.append("</текущие_границы>")
    return "\n".join(lines)


def _format_request_block(user_intent: str) -> str:
    intent = user_intent.strip() or "(пользователь не уточнил — выбери на своё усмотрение в соответствии с настроением чата)"
    return f"<контекст_запроса>\n{intent}\n</контекст_запроса>"


def _format_rules_block(refusal_style_hint: str | None,
                        character_gender: str = "female") -> str:
    lines = ["<правила>"]
    lines.append("- Решение РИСОВАТЬ уже принято на предыдущем этапе (вызов draw был")
    lines.append("  одобрен в чате). Твоя задача СЕЙЧАС — выбрать ассеты, не пересматривать")
    lines.append("  это решение. НЕ отказывайся по соображениям 'слишком интимно', 'не")
    lines.append(f"  {gpick(character_gender, 'готова', 'готов')}', 'не подходит к настроению' — это уже не твоё решение.")
    lines.append("- Выбирай ассеты подходящие по СМЫСЛУ запроса (intent).")
    lines.append("- Костюм должен быть совместим со сценой (см. compatibility).")
    lines.append("- Модификаторы:")
    lines.append("  ОБЯЗАТЕЛЬНЫЕ: expression, framing — выбирай всегда")
    lines.append("  ОПЦИОНАЛЬНЫЕ: gesture, prop — добавляй только если уместно и совместимо с pose")
    lines.append("    gesture: дополнительный жест руками. НЕ выбирай если pose уже занимает руки")
    lines.append("             (reading, leaning_forward, hands_on_hips, hands_behind).")
    lines.append("    prop: предмет в руках. НЕ выбирай вместе с gesture (руки заняты одним)")
    lines.append("          или с pose у которой руки уже заняты другим (reading, leaning_forward).")
    lines.append("    Эти категории можно вообще пропустить (modifiers без этих ключей).")
    lines.append("")
    lines.append("- framing ПО УМОЛЧАНИЮ = medium (по пояс). Это лучшее качество деталей.")
    lines.append("  Используй другие значения ТОЛЬКО при явных причинах:")
    lines.append('  framing=full_body  → ТОЛЬКО если intent явно: "в полный рост", "целиком",')
    lines.append('                       "стоит во весь рост", "full body". БЕЗ этих слов — НЕ выбирай.')
    lines.append('  framing=portrait   → если intent: "портрет", "плечи и голова"')
    lines.append('  framing=close_up   → если intent: "крупный план", "лицо", "ближе"')
    lines.append("  Во всех остальных случаях → medium")
    lines.append("")
    lines.append("- КАДР ↔ КОМПОНЕНТЫ (модель рисует КАЖДЫЙ тег; вне кадра — ломает композицию):")
    lines.append("  framing=close_up/portrait → НЕ бери gesture/prop (руки и предметы вне кадра)")
    lines.append("                              и позы лёжа/сидя (виден только верх) — выбери")
    lines.append("                              стоячую/нейтральную позу.")
    lines.append("  framing=medium            → gesture/prop OK (руки видны); позы лёжа всё ещё нет.")
    lines.append("  framing=full_body         → любые позы/жесты/реквизит.")
    lines.append("")
    lines.append("- aspect ВЫБИРАЕТСЯ ПО INTENT ПОЛЬЗОВАТЕЛЯ:")
    lines.append('  intent явно: "широкий"/"панорама"/"пейзаж"/"cinematic" → aspect="wide"')
    lines.append('  intent явно: "портрет"/"крупный план"/"лицо"          → aspect="tall"')
    lines.append('  intent не уточняет ракурс                              → aspect="square"')
    lines.append("- ВАЖНО: aspect=wide НЕ означает full_body. Широкий кадр — это для")
    lines.append("  большего фона/композиции, не для большего тела. Обычно aspect=wide + framing=medium.")
    lines.append("- ВАЖНО: explicit intent ПОЛЬЗОВАТЕЛЯ всегда побеждает.")
    lines.append("")
    lines.append("- Отказ (requested_unavailable=true) допустим ТОЛЬКО если:")
    lines.append("  1. Список доступных outfits/scenes/poses пуст для текущих границ, ИЛИ")
    lines.append("  2. Intent явно требует rating выше max_rating (например 'обнажённая' при sfw),")
    lines.append("     и среди доступных ассетов нет ничего что хотя бы приближённо подошло.")
    lines.append("- Если есть хоть один подходящий outfit — ВЫБИРАЙ ЕГО, не отказывайся.")
    if refusal_style_hint:
        lines.append(f"- Стиль отказа (если он реально нужен): {refusal_style_hint}")
    else:
        lines.append("- Отказ (если реально нужен) — в твоём естественном стиле, без формальных извинений.")
    lines.append("</правила>")
    return "\n".join(lines)


def _format_schema_block() -> str:
    return (
        "<формат>\n"
        "Ответь СТРОГО JSON-объектом, без markdown-обёртки:\n"
        '{"outfit_id": "...", "scene_id": "...", "pose_id": "...",\n'
        ' "modifiers": {"expression": "...", "framing": "..."},\n'
        ' "aspect": "square",\n'
        ' "requested_unavailable": false, "refusal_reason": null}\n'
        "\n"
        'aspect — формат кадра, один из: "square" (1:1, универсальный),\n'
        '"tall" (2:3, портрет/full-body персонажа),\n'
        '"wide" (3:2, пейзаж/групповая сцена/cinematic).\n'
        "Выбирай по смыслу запроса. Если непонятно — square.\n"
        "\n"
        "Для отказа:\n"
        '{"outfit_id": "", "scene_id": "", "pose_id": "", "modifiers": {},\n'
        ' "aspect": "square",\n'
        ' "requested_unavailable": true, "refusal_reason": "твоя реплика от первого лица"}\n'
        "</формат>"
    )


_MD_CODEBLOCK_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)


def extract_json_object(text: str) -> str | None:
    if not text:
        return None
    m = _MD_CODEBLOCK_RE.search(text)
    if m:
        return m.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start:end + 1]
    return None


def parse_choice_response(text: str) -> Choice:
    raw = extract_json_object(text)
    if raw is None:
        raise ChoiceValidationError(
            "В ответе LLM не найден JSON-объект "
            f"(длина ответа={len(text or '')} chars)"
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ChoiceValidationError(
            f"Невалидный JSON: {e}; raw={raw[:200]!r}"
        ) from e
    return Choice.from_dict(data)


def _fallback_refusal_choice(reason: str) -> Choice:
    return Choice(
        requested_unavailable=True,
        refusal_reason=reason,
    )


def request_choice(
    *,
    llm_client,
    character_name: str,
    user_intent: str,
    catalog: AssetCatalog,
    renderer_id: str,
    max_rating: str,
    current_tier: str,
    character_id: str,
    character_archetypes: list[str],
    refusal_style_hint: str | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    fallback_reason: str = (
        "Что-то у меня не получается выбрать — давай в следующий раз попробуем."
    ),
    character_tag_gates: dict[str, str] | None = None,
    character_blocked_tags: list[str] | None = None,
    current_portrait_outfit_id: str | None = None,
) -> tuple[Choice, GateResult]:
    def _build(retry_msg: str | None = None) -> str:
        return build_choice_prompt(
            character_name=character_name,
            user_intent=user_intent,
            catalog=catalog,
            renderer_id=renderer_id,
            max_rating=max_rating,
            current_tier=current_tier,
            character_id=character_id,
            character_archetypes=character_archetypes,
            refusal_style_hint=refusal_style_hint,
            retry_message=retry_msg,
            character_tag_gates=character_tag_gates,
            character_blocked_tags=character_blocked_tags,
            current_portrait_outfit_id=current_portrait_outfit_id,
        )

    def _call(system_prompt: str) -> str:
        return llm_client.chat(
            messages=[{"role": "user", "content": "Сделай выбор."}],
            system=system_prompt,
            thinking=True,
            label="Drawing: choice",
        )

    gate_kwargs = dict(
        catalog=catalog,
        renderer_id=renderer_id,
        max_rating=max_rating,
        current_tier=current_tier,
        character_id=character_id,
        character_archetypes=character_archetypes,
    )

    retry_msg: str | None = None
    last_gate: GateResult | None = None

    for attempt in range(max_retries + 1):
        system_prompt = _build(retry_msg)

        try:
            response = _call(system_prompt)
        except Exception as e:
            print(f"[choice] LLM call failed (attempt {attempt}): {e}")
            return (
                _fallback_refusal_choice(fallback_reason),
                GateResult(valid=False, errors=[f"LLM call error: {e}"]),
            )

        try:
            choice = parse_choice_response(response)
        except ChoiceValidationError as e:
            print(f"[choice] parse failed (attempt {attempt}): {e}")
            retry_msg = (
                f"Твой предыдущий ответ не распарсился как JSON ({e}). "
                "Верни ТОЛЬКО валидный JSON-объект по schema выше, без markdown."
            )
            last_gate = GateResult(valid=False, errors=[str(e)])
            continue

        if choice.is_refusal():
            return choice, GateResult(valid=True)

        if current_portrait_outfit_id and choice.outfit_id != current_portrait_outfit_id:
            from dataclasses import replace
            choice = replace(choice, outfit_id=current_portrait_outfit_id)

        gate = validate_choice(choice, **gate_kwargs)
        last_gate = gate
        if gate.valid:
            return choice, gate

        print(f"[choice] gate fail (attempt {attempt}): {gate.errors}")
        retry_msg = gate.to_retry_message()

    return (
        _fallback_refusal_choice(fallback_reason),
        last_gate or GateResult(valid=False, errors=["exhausted retries"]),
    )
