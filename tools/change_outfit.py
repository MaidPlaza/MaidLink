from __future__ import annotations

from tools.registry import Tool, ToolContext, TIER_CONTEXTUAL
from persona.gender import g as gpick, gender_of, pair_allows, pair_of
from persona.prompt_context import ContextSpec
from drawing.assets import tier_ge, effective_required_tier


def _change_outfit_handler(args: dict, ctx: ToolContext) -> str:
    _cg = gender_of(getattr(getattr(ctx, "persona", None), "character", None))
    outfit_id = (args.get("outfit_id") or "").strip()
    if not outfit_id:
        return ("Ошибка: пустой outfit_id. Укажи ID костюма (узнай через "
                "list_outfits если не помнишь).")

    for existing in ctx.pending_actions:
        if existing.get("kind") == "change_outfit":
            return ("Переодевание УЖЕ принято по первому вызову — повторный "
                    "change_outfit не нужен и проигнорирован.")

    catalog = ctx.drawing_catalog
    if catalog is None:
        return "Ошибка: каталог костюмов не инициализирован."

    persona = ctx.persona
    if persona is None:
        return "Ошибка: персонаж не инициализирован."
    current_tier = persona.tier
    policy = persona.outfit_policy
    tag_gates = dict(policy.tag_tier_gates) if policy else {}
    blocked_tags = list(policy.blocked_tags) if policy else []

    outfit = catalog.outfits.get(outfit_id)
    if outfit is None:
        return (f"Костюма с id={outfit_id!r} нет в каталоге. "
                f"Узнай доступные через list_outfits().")

    if not pair_allows(getattr(outfit, "pairs", ()),
                       pair_of(getattr(persona, "character", None))):
        return (f"Наряда {outfit.name!r} нет в твоём гардеробе — это не из "
                f"твоей коллекции. Выбери что-то из list_outfits().")

    current_oid = getattr(ctx, "current_outfit_id", "") or ""
    if current_oid and outfit_id == current_oid:
        return (f"Ты УЖЕ в этом наряде ({outfit.name!r}) — переодеваться не "
                f"нужно, change_outfit не вызывай. Ответь словами в характере; "
                f"если хочется сменить образ — выбери ДРУГОЙ наряд из "
                f"list_outfits().")

    if not tier_ge(current_tier, ctx.drawing_outfit_change_min_tier):
        return (
            f"[вход в характер] Сменить костюм по просьбе пользователя — это "
            f"близкое взаимодействие. Вы пока ещё в самом начале знакомства "
            f"({current_tier!r}); требуется минимум "
            f"{ctx.drawing_outfit_change_min_tier!r}. Скажи мягко словами — "
            f"тебе пока не комфортно так переодеваться по чужой просьбе, "
            f"вам нужно больше узнать друг друга. Не вызывай change_outfit "
            f"повторно. Просто ответь в характере, без tool_call."
        )

    blocked_set = set(blocked_tags or [])
    hit_blocked = [t for t in outfit.tags if t in blocked_set]
    if hit_blocked:
        return (
            f"[вход в характер] Этот наряд {outfit.name!r} имеет теги "
            f"{', '.join(hit_blocked)} — ты НЕ носишь такой стиль вообще "
            f"(это часть твоей идентичности, не зависит от уровня отношений). "
            f"Откажись в характере, естественно объяснив что это не твоё. "
            f"Не вызывай change_outfit повторно."
        )

    eff_tier = effective_required_tier(
        outfit.required_tier, list(outfit.tags),
        character_tag_gates=tag_gates,
        character_blocked_tags=list(blocked_set),
    )
    _own = bool(getattr(catalog, "is_own_outfit", lambda _o: False)(outfit.id))
    if eff_tier is not None and not _own and not tier_ge(current_tier, eff_tier):
        gates = tag_gates or {}
        sensitive_tags = [
            t for t in outfit.tags
            if t in gates and not tier_ge(current_tier, gates[t])
        ]
        if sensitive_tags:
            hint = (
                f"теги {', '.join(sensitive_tags)} для тебя личностно значимы — "
                f"ты не хочешь надевать что-то такое на текущем уровне отношений "
                f"({current_tier!r})"
            )
        else:
            hint = (
                f"костюм для тебя слишком {outfit.tags[0] if outfit.tags else 'особенный'} "
                f"на текущий момент"
            )
        return (
            f"[вход в характер] Ты НЕ хочешь сейчас надевать {outfit.name!r} — "
            f"{hint}. Откажись в характере, мягко и естественно — это не "
            f"«система не позволяет», а твоё личное «не время», "
            f"«не {gpick(_cg, 'готова', 'готов')}», "
            f"«стесняюсь». НЕ вызывай change_outfit повторно. "
            f"Не используй слово «заблокирован»."
        )

    wardrobe = getattr(ctx, "wardrobe", None)
    if wardrobe is not None and not wardrobe.is_prepared(outfit_id):
        if wardrobe.is_queued(outfit_id):
            return (
                f"[вход в характер] Наряд {outfit.name!r} уже ГОТОВИТСЯ — "
                f"Господин поставил его на подготовку («подгонку»: система "
                f"заранее отрисовывает полный набор твоих портретов в нём). "
                f"Прямо сейчас переодеться не выйдет. Скажи мягко в характере: "
                f"наденешь его, как только он будет готов; если Господину не "
                f"терпится — подготовку можно ускорить в панели гардероба. "
                f"НЕ вызывай change_outfit повторно. Не используй слова "
                f"«система» и «заблокирован»."
            )
        return (
            f"[вход в характер] Наряд {outfit.name!r} ещё НЕ подготовлен — его "
            f"нужно «подогнать» заранее (отрисовать полный набор твоих портретов "
            f"в нём, ~10 минут). Запустить подготовку можешь НЕ ты — только "
            f"Господин, в панели гардероба (кнопка с вешалкой рядом с "
            f"настройками). ПОПРОСИ его мягко и в характере отправить наряд на "
            f"подготовку в панели гардероба — а ты переоденешься, как только он "
            f"будет готов. НЕ вызывай change_outfit повторно. Не используй "
            f"слова «система» и «заблокирован»."
        )

    ctx.pending_actions.append({
        "kind": "change_outfit",
        "outfit_id": outfit_id,
    })

    return (f"Принято: ты {gpick(_cg, 'ушла', 'ушёл')} переодеваться. "
            "Портрет сменится к твоему "
            "возвращению; реплику-возвращение ты напишешь следующим ходом. "
            "Отдельный снимок (draw) для показа наряда не нужен.")


CHANGE_OUTFIT_SCHEMA = {
    "name": "change_outfit",
    "description": (
        "Переодеться в указанный костюм на портрете (до конца сессии). "
        "Доступно с warming+ tier. Работает ТОЛЬКО для ПОДГОТОВЛЕННОГО "
        "костюма (см. list_outfits); неподготовленный надеть нельзя — "
        "подготовку запускает пользователь в панели гардероба (попроси его)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "outfit_id": {
                "type": "string",
                "description": (
                    "ID костюма из <гардероб> → доступные outfits "
                    "(например maid_classic)."
                ),
            },
        },
        "required": ["outfit_id"],
    },
}


CHANGE_OUTFIT_HELP = """change_outfit — переодеться на портрете.

Аргументы:
  outfit_id (str): ID костюма из доступных (точный id и ГОТОВНОСТЬ смотри
                   через list_outfits).

Механика готовности (ВАЖНО):
  - ПОДГОТОВЛЕННЫЙ костюм (полный набор твоих портретов отрисован заранее) →
    смена МГНОВЕННАЯ: портрет в UI обновится через пару секунд, до конца сессии.
  - НЕПОДГОТОВЛЕННЫЙ костюм надеть НЕЛЬЗЯ, и самостоятельно запустить подготовку
    ты НЕ можешь — её запускает только Господин в панели гардероба (кнопка с
    вешалкой). Попроси его об этом мягко в характере; наденешь, как наряд
    будет готов. Повторный вызов change_outfit не нужен.

Когда использовать:
  - Пользователь просит переодеться: «надень форму», «смени наряд»
  - В roleplay-контексте уместна смена костюма
  - Просят ПОДГОТОВИТЬ наряд (не надевая) → это НЕ вызов инструмента:
    попроси Господина запустить подготовку в панели гардероба

Когда НЕ использовать:
  - Если tier ещё distant — система откажет (твоя реплика-отказ)
  - Если пользователь не просил — не предлагай без повода
  - Если уже в этом костюме — не нужно
  - ПОСЛЕ переодевания НЕ вызывай draw отдельно: портрет уже обновлён и
    показывает новый костюм, дополнительный снимок не нужен

Если outfit недоступен, не подготовлен или tier недостаточен — система ответит
подсказкой для реплики в характере; не дублируй tool-call.
"""


CHANGE_OUTFIT_TOOL = Tool(
    name="change_outfit",
    schema=CHANGE_OUTFIT_SCHEMA,
    handler=_change_outfit_handler,
    summary=(
        "change_outfit(outfit_id) — переодеться на портрете (до конца сессии). "
        "Доступно со ступени «потепление». outfit_id — из list_outfits (сводка в <гардероб>)."
    ),
    help=CHANGE_OUTFIT_HELP,
    tier=TIER_CONTEXTUAL,
    capability="image_gen",
    context_needs=ContextSpec(persona=True),
    triggers=[
        "переоден", "переоде", "одень", "одеть",
        "сменим костюм", "смени костюм", "смени наряд",
        "надень", "наденешь",
        "форму", "в форме", "в наряде", "в костюме",
        "change outfit", "wear", "dress",
    ],
)
