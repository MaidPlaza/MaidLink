from __future__ import annotations

from tools.registry import Tool, ToolContext, TIER_CONTEXTUAL
from persona.gender import g as gpick, gender_of, pair_allows, pair_of
from persona.prompt_context import ContextSpec
from drawing.assets import (
    RATING_ORDER, TIER_ORDER, rating_le, tier_ge,
    effective_required_tier,
)


def _list_outfits_handler(args: dict, ctx: ToolContext) -> str:
    _cg = gender_of(getattr(getattr(ctx, "persona", None), "character", None))
    catalog = ctx.drawing_catalog
    if catalog is None:
        return ("Ошибка: каталог костюмов не инициализирован (drawing не активен).")

    persona = ctx.persona
    if persona is None:
        return ("Ошибка: персонаж не инициализирован (drawing не активен).")
    current_tier = persona.tier
    character_id = persona.character_id
    character_archetypes = persona.archetypes
    policy = persona.outfit_policy
    tag_gates = dict(policy.tag_tier_gates) if policy else {}
    blocked_tags = list(policy.blocked_tags) if policy else []

    _pair = pair_of(getattr(getattr(ctx, "persona", None), "character", None))
    available = catalog.compatible_outfits(
        renderer_id=ctx.drawing_renderer_id,
        max_rating=ctx.drawing_max_rating,
        current_tier=current_tier,
        character_id=character_id,
        character_archetypes=character_archetypes,
        character_tag_gates=tag_gates,
        character_blocked_tags=blocked_tags,
        character_pair=_pair,
    )
    available_ids = {o.id for o in available}

    blocked_tags_set = set(blocked_tags or [])
    blocked: list[tuple[str, str, str]] = []
    for o in catalog.outfits.values():
        if o.id in available_ids:
            continue
        if not pair_allows(o.pairs, _pair):
            continue
        if not o.supports_renderer(ctx.drawing_renderer_id):
            reason = "технически не поддерживается текущим рендером"
        elif not rating_le(o.rating, ctx.drawing_max_rating):
            reason = (
                f"наряд для уровня {o.rating!r}, а ты сейчас работаешь "
                f"в режиме {ctx.drawing_max_rating!r} — настолько откровенно "
                f"показываться ты не {gpick(_cg, 'готова', 'готов')}"
            )
        else:
            hit_blocked = [t for t in o.tags if t in blocked_tags_set]
            if hit_blocked:
                reason = (
                    f"теги {', '.join(hit_blocked)} — это не твой стиль вообще, "
                    f"ты такое не носишь как часть своей идентичности"
                )
            else:
                eff_tier = effective_required_tier(
                    o.required_tier, list(o.tags),
                    character_tag_gates=tag_gates,
                    character_blocked_tags=blocked_tags,
                )
                if eff_tier is not None and not tier_ge(current_tier, eff_tier):
                    gates = tag_gates or {}
                    sensitive = [
                        t for t in o.tags
                        if t in gates and not tier_ge(current_tier, gates[t])
                    ]
                    if sensitive:
                        reason = (
                            f"теги {', '.join(sensitive)} для тебя личностно "
                            f"значимы — не хочется надевать что-то такое на "
                            f"{current_tier!r} (нужно ближе)"
                        )
                    else:
                        reason = (
                            f"всё хорошо, но рано — наряд особенный, "
                            f"вам с пользователем нужно больше времени"
                        )
                else:
                    cr = o.character_restrictions
                    blocks = cr.block_list if cr else []
                    req_arch = cr.required_archetypes if cr else []
                    if character_id in blocks:
                        reason = "этот наряд тебе не подходит по характеру"
                    elif req_arch and not any(a in character_archetypes for a in req_arch):
                        reason = (
                            f"этот наряд для другого типажа "
                            f"({', '.join(req_arch)}), не твой"
                        )
                    else:
                        reason = "что-то в этом наряде тебе сейчас не по душе"
        blocked.append((o.id, o.name, reason))

    can_change = tier_ge(current_tier, ctx.drawing_outfit_change_min_tier)

    wardrobe = getattr(ctx, "wardrobe", None)
    prepared: list = []
    queued: list = []
    unprepared: list = []
    if wardrobe is not None:
        for o in available:
            try:
                if wardrobe.is_prepared(o.id):
                    prepared.append(o)
                elif wardrobe.is_queued(o.id):
                    queued.append(o)
                else:
                    unprepared.append(o)
            except Exception:
                unprepared.append(o)

    current_oid = getattr(ctx, "current_outfit_id", "") or ""
    default_oid = getattr(ctx, "default_outfit_id", "") or ""

    def _outfit_name(oid: str) -> str:
        o = catalog.outfits.get(oid)
        return (o.name if o else "") or oid

    lines = []
    if wardrobe is not None:
        lines.append(f"=== Твой гардероб: {len(available)} готовы носить "
                     f"(подготовлено {len(prepared)}), {len(blocked)} пока не хочется ===")
    else:
        lines.append(f"=== Твой гардероб: {len(available)} готовы носить, "
                     f"{len(blocked)} пока не хочется ===")
    if current_oid:
        cur_line = f"СЕЙЧАС НА ТЕБЕ: {current_oid} — {_outfit_name(current_oid)}"
        if current_oid == default_oid:
            cur_line += " (это твой обычный, дефолтный наряд)"
        lines.append(cur_line)
    if default_oid and default_oid != current_oid:
        lines.append(
            f"Твой ОБЫЧНЫЙ (дефолтный) наряд: {default_oid} — "
            f"{_outfit_name(default_oid)}. В него ты возвращаешься, когда "
            f"просят «вернись в своё» или сессия заканчивается."
        )
    lines.append("")

    if can_change:
        lines.append(
            f"Менять портретный наряд по просьбе — сейчас ты на это "
            f"{gpick(_cg, 'согласна', 'согласен')} "
            f"({current_tier!r}). При желании вызывай change_outfit(outfit_id=...) "
            f"со строго одним из ID ниже. Выбирая наряд "
            f"{gpick(_cg, 'сама', 'сам')} (на свой вкус) — "
            f"бери ДРУГОЙ, не тот, что уже на тебе: переодеваться в текущий "
            f"незачем."
        )
        if wardrobe is not None:
            lines.append(
                "Переодеться СРАЗУ можно только в ПОДГОТОВЛЕННЫЙ наряд (смена "
                "мгновенна). Неподготовленный сперва «подгоняется»: система "
                "заранее отрисовывает полный набор твоих портретов в нём. "
                "Запустить подготовку можешь НЕ ты — только Господин, в панели "
                "гардероба (кнопка с вешалкой). Нужен неподготовленный наряд "
                "или просят его подготовить → ПОПРОСИ Господина запустить "
                "подготовку в панели; change_outfit по неподготовленному не "
                "переоденет."
            )
    else:
        lines.append(
            f"Менять портретный наряд по просьбе ты пока НЕ хочешь — "
            f"вы ещё в самом начале знакомства ({current_tier!r}); "
            f"тебе нужно больше доверия. Откажись словами если попросят, "
            f"НЕ вызывай change_outfit."
        )
    lines.append("")

    def _fmt(o) -> str:
        tags_short = ", ".join(o.tags[:3]) if o.tags else "—"
        line = f"  {o.id} — {o.name} [{tags_short}]"
        if o.id == current_oid:
            line += "   ← СЕЙЧАС НА ТЕБЕ"
        elif o.id == default_oid:
            line += "   (твой дефолтный)"
        return line

    if available and wardrobe is not None:
        if prepared:
            lines.append("ПОДГОТОВЛЕНЫ — можно переодеться прямо сейчас:")
            lines.extend(_fmt(o) for o in prepared)
            lines.append("")
        if queued:
            lines.append("В ОЧЕРЕДИ ПОДГОТОВКИ — наденешь, когда наряд будет готов "
                         "(повторный change_outfit не нужен):")
            lines.extend(_fmt(o) for o in queued)
            lines.append("")
        if unprepared:
            lines.append("НЕ ПОДГОТОВЛЕНЫ — сразу переодеться нельзя; попроси "
                         "Господина запустить подготовку в панели гардероба:")
            lines.extend(_fmt(o) for o in unprepared)
            lines.append("")
    elif available:
        lines.append(f"ТЫ {gpick(_cg, 'ГОТОВА', 'ГОТОВ')} НОСИТЬ (outfit_id — название — теги):")
        lines.extend(_fmt(o) for o in available)
        lines.append("")
    else:
        lines.append(
            f"Сейчас ты не {gpick(_cg, 'готова', 'готов')} показаться "
            "ни в одном из имеющихся костюмов — "
            "вы слишком мало знакомы или режим SFW слишком строгий."
        )
        lines.append("")

    if blocked:
        lines.append(
            "ТЕБЕ НЕ ХОЧЕТСЯ ЭТО НАДЕВАТЬ СЕЙЧАС "
            "(если попросят — откажись в характере, мягко, без слова "
            "«заблокирован»; объясни своими словами через причину):"
        )
        for oid, name, reason in blocked:
            lines.append(f"  {oid} — {name}")
            lines.append(f"      причина (для тебя): {reason}")

    return "\n".join(lines)


LIST_OUTFITS_SCHEMA = {
    "name": "list_outfits",
    "description": (
        "Получить полный список костюмов со статусами: подготовленные "
        "(переодеться можно мгновенно), в очереди подготовки, неподготовленные, "
        "заблокированные (с причиной). Возвращает outfit_id для change_outfit. "
        "Вызывай ПЕРЕД переодеванием (узнать готовность) и когда юзер просит "
        "показать гардероб. Только ОДЕЖДА: причёска, украшения, аксессуары, "
        "заколки, макияж — это образ, не гардероб, их каталог — "
        "style_self(options=…), не этот инструмент."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


LIST_OUTFITS_HELP = """list_outfits — получить полный гардероб со статусами готовности.

Без аргументов. Возвращает:
  - Сводку: сколько доступно (и сколько из них ПОДГОТОВЛЕНО) / заблокировано
  - Статус change_outfit (доступен ли на текущем tier)
  - Доступные костюмы по группам готовности (outfit_id + название + теги):
      ПОДГОТОВЛЕНЫ            — переодеться можно прямо сейчас (мгновенно)
      В ОЧЕРЕДИ ПОДГОТОВКИ    — наденешь, когда набор дорисуется
      НЕ ПОДГОТОВЛЕНЫ         — надеть нельзя; подготовку запускает Господин
                                в панели гардероба (попроси его)
  - Заблокированные костюмы (id + название + причина блока)

Механика подготовки: у подготовленного наряда заранее отрисован полный набор
твоих портретов — поэтому смена мгновенна. Запустить подготовку можешь не ты,
а только Господин — в панели гардероба (наряд рисуется в свободное время между
вашими встречами, либо сразу, если Господин поторопит).

Когда использовать:
  - Юзер просит «покажи что у тебя есть», «какие костюмы», «гардероб»
  - ПЕРЕД change_outfit — узнать точный outfit_id и подготовлен ли наряд
  - Юзер просит переодеться, но ты не уверена в названии id или готовности

Когда НЕ использовать:
  - Если outfit_id и его готовность уже известны из недавнего вызова
  - Если юзер не упоминает костюмы
  - Вопрос про украшения, аксессуары, заколки, ленты, причёску или макияж —
    это образ поверх одежды: style_self(options="accessories"|"hair"|
    "makeup"|"all"), а не гардероб
"""


LIST_OUTFITS_TOOL = Tool(
    name="list_outfits",
    schema=LIST_OUTFITS_SCHEMA,
    handler=_list_outfits_handler,
    summary=(
        "list_outfits() — гардероб (ТОЛЬКО костюмы) со статусами: подготовленные "
        "(смена мгновенна) / в очереди / неподготовленные / заблокированные. "
        "outfit_id для change_outfit. Украшения, причёска, макияж — не сюда: "
        "style_self(options)."
    ),
    help=LIST_OUTFITS_HELP,
    tier=TIER_CONTEXTUAL,
    capability="image_gen",
    context_needs=ContextSpec(persona=True),
    triggers=[
        "костюм", "костюмы", "костюмчик", "наряд", "наряды", "гардероб",
        "что у тебя", "какие у тебя", "что есть",
        "одежд", "форм", "переоден", "переоде", "одень",
        "что одеть", "что надеть",
    ],
)
