from __future__ import annotations

from persona.gender import g as gpick, gender_of
from tools.registry import Tool, ToolContext, TIER_CONTEXTUAL
from persona.prompt_context import ContextSpec


def _resolve_items(raw_items, *, allow_nsfw: bool) -> dict:
    from drawing.tag_resolver import get_resolver
    items = [str(x).strip() for x in (raw_items or []) if str(x).strip()]
    if not items:
        return {}
    return get_resolver().resolve_many(items, allow_nsfw=allow_nsfw)


def _resolve_set_phrase(raw: str) -> str | None:
    import services.self_styling as ss
    t = " ".join(str(raw or "").strip().lower().split())
    if not t:
        return None
    color, pattern, item = ss.parse_style_tag(t)
    if item in ss.SET_PARTS:
        return ss.join_style_tag(color, pattern, item)
    return ss.ru_set_phrase(t)


def _session_state(ctx) -> dict | None:
    mem = getattr(ctx, "memory", None)
    return getattr(mem, "_session_state_ref", None) if mem is not None else None


def _as_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [p.strip() for p in v.split(",") if p.strip()]
    return [str(p).strip() for p in v if str(p).strip()]


_OPT_CATEGORIES = {
    "all": "", "всё": "", "все": "", "hair": "hair", "волосы": "hair",
    "прическа": "hair", "причёска": "hair", "причёски": "hair", "прически": "hair",
    "makeup": "makeup", "макияж": "makeup", "accessories": "accessories",
    "аксессуары": "accessories", "украшения": "accessories",
    "intimate": "intimate", "underwear": "underwear", "бельё": "underwear",
    "белье": "underwear",
}


_OPT_SECTIONS = {
    "серьги": "серьги", "уши": "серьги", "earrings": "серьги", "ears": "серьги",
    "шея": "шея", "neck": "шея", "necklaces": "шея", "ожерелья": "шея",
    "волосы-украшения": "волосы", "заколки": "волосы", "hair accessories": "волосы",
    "голова": "голова", "head": "голова", "лицо": "лицо", "face": "лицо",
    "очки": "лицо", "маски": "лицо", "пирсинг": "пирсинг", "piercing": "пирсинг",
    "piercings": "пирсинг", "руки": "руки", "hands": "руки", "arms": "руки",
    "браслеты": "руки", "ноги": "ноги", "legs": "ноги", "тело": "тело",
    "body": "тело", "хвост": "хвост", "tail": "хвост",
}


def _option_color(word: str) -> str | None:
    import services.self_styling as ss
    from drawing.tag_resolver import split_color_prefix
    c = ss.speech_color(word)
    if c:
        return c
    got, _ = split_color_prefix(f"{word} x")
    return ss.color_word(got.split()[-1]) if got else None


def _parse_options_query(q: str, allow_nsfw: bool) -> tuple[str, str, str | None, str]:
    import re
    import services.self_styling as ss
    if q in _OPT_CATEGORIES:
        return "catalog", _OPT_CATEGORIES[q], None, ""
    if q in _OPT_SECTIONS:
        return "section", _OPT_SECTIONS[q], None, ""
    words = [w for w in re.split(r"[\s,;/]+", q) if w]
    cat, color, rest = "", None, []
    for w in words:
        if w in _OPT_CATEGORIES and not cat:
            cat = _OPT_CATEGORIES[w]
            continue
        c = _option_color(w) if color is None else None
        if c:
            color = c
            continue
        rest.append(w)
    if color and not rest:
        return "color", cat, color, ""
    phrases = [q, " ".join(rest)]
    phrases += [re.sub(r"(?<=[a-z])s$", "", p) for p in phrases if p]
    for phrase in dict.fromkeys(phrases):
        if not phrase:
            continue
        canon = next(iter(_resolve_items([phrase], allow_nsfw=True).values()), None)
        canon = canon or (phrase if phrase.isascii() else None)
        if not canon:
            continue
        c2, item = ss.option_item(canon)
        if item and ss.route_tag(item) not in (None, "length", "haircut"):
            return "item", cat, color or c2, item
    return "catalog", cat, None, ""


def _truthy(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes", "y", "да", "on")
    return bool(v)


_HAIR_SLOT = {"hair_style": ("style", "укладка"),
              "hair_texture": ("texture", "текстура"),
              "hair_bangs": ("bangs", "чёлка")}


def _replace_conflicts(slot_list: list[str], canon: str, slot: str) -> str:
    import services.self_styling as ss
    swapped = ss.slot_conflicts(canon, slot_list, slot)
    for old in swapped:
        slot_list.remove(old)
    return f" (вместо {', '.join(swapped)})" if swapped else ""


def handle_style_self(args: dict, ctx: ToolContext) -> str:
    idy = getattr(ctx, "identity", None)
    if idy is None:
        return "Стайлинг недоступен (нет активного персонажа)."
    from services import self_styling as ss
    _cg = gender_of(getattr(getattr(ctx, "persona", None), "character", None))
    allow_nsfw = (getattr(ctx, "drawing_max_rating", "sfw") or "sfw") != "sfw"
    sess = _session_state(ctx)
    cur_len = ss.character_hair_length(sess)

    def _body_now():
        b = ss.body_of(idy)
        if b is not None and cur_len and not b.get("hair_length"):
            b["hair_length"] = cur_len
        return b

    from services import gacha as _gacha
    allowed = _gacha.allowed_cores(idy)
    _owner = (getattr(getattr(ctx, "persona", None), "honorific", "")
              or "Господин")

    _tier = getattr(getattr(ctx, "persona", None), "tier", "") or ""
    try:
        from drawing.assets import tier_ge
        slot_ok = {slot: tier_ge(_tier, need)
                   for slot, need in ss.SLOT_MIN_TIER.items()}
    except Exception:
        slot_ok = {}

    opts = args.get("options")
    if opts:
        q = str(opts).strip().lower()
        _body = _body_now()
        uw_ok = (slot_ok.get("underwear", False)
                 and ss.slot_fits_body("underwear", _body))
        in_ok = slot_ok.get("intimate", False)
        kind, cat, color, item = _parse_options_query(q, allow_nsfw)
        if kind == "item" and not ss.fits_body(item, _body):
            return f"«{item}» — {ss.body_refusal(item, _body)}."
        if kind == "item":
            st = ss.styling_state(idy)
            worn = next((t for t in (st["accessories"] + st["makeup"]
                                     + st["underwear"] + st["intimate"])
                         if ss.allowance_key(t) == item), "")
            asked_pat = ss.ru_pattern(q)[0] or next(
                (p for p in ss._PATTERN_WORDS if f"{p} " in f"{q} "), None)
            return ss.item_colors_text(item, allowed, label=_gacha.label_of(item),
                                       worn=worn, asked=color, asked_pattern=asked_pat)
        if kind == "color":
            return ss.color_catalog(color, allowed, category=cat,
                                    allow_nsfw=allow_nsfw, underwear_ok=uw_ok,
                                    intimate_ok=in_ok)
        if kind == "section":
            return ss.section_catalog(cat, allowed)
        cur = ss.describe(ss.styling_state(idy), include_intimate=allow_nsfw)
        head = (f"Твой образ сейчас: {cur}.\n\n" if cur else "")
        return (head + ss.options_catalog(
                    cur_len, cat, allow_nsfw=allow_nsfw,
                    underwear_ok=uw_ok, intimate_ok=in_ok, allowed=allowed)
                + "\n\nВыбирай и вызывай style_self с нужными параметрами — "
                  "свободными словами или тегами из списка. Если выбор доверили "
                  "тебе или вещи уже названы — надень сразу, этим же ходом, не "
                  "переспрашивая; у вещи с несколькими цветами цвет не угадывай: "
                  "надень без цвета (ответ назовёт открытые) или сначала "
                  "options=\"<вещь>\"; подбираешь по цвету — options=\"<цвет>\". "
                  "Проверку зови сразу, этим же ходом, а не обещай словами. "
                  "Надеть — add: "
                  "новое ляжет к уже надетому, вещь того же рода заменится сама; "
                  "сменить весь набор украшений — remove: [\"украшения\"] вместе "
                  "с add; reset — только для образа целиком с нуля.")

    state = ss.styling_state(idy)
    changed: list[str] = []
    refused: list[str] = []
    hair_inputs = _as_list(args.get("hairstyle"))
    add_inputs = _as_list(args.get("add"))
    remove_inputs = _as_list(args.get("remove"))

    reset_applied = False
    reset_skipped = False
    full_reset = _truthy(args.get("reset_full"))
    if full_reset or _truthy(args.get("reset")):
        target = ss.bare_state() if full_reset else ss.default_state(idy)
        if not (hair_inputs or add_inputs or remove_inputs):
            if state == target:
                return ("Ты и так без украшений и макияжа, волосы прямые "
                        "распущенные — сбрасывать нечего." if full_reset else
                        "Ты и так в своём обычном образе — сбрасывать нечего.")
            ss.save_styling(idy, target)
            if full_reset:
                return ("Готово: образ сброшен полностью — все украшения и "
                        "макияж сняты, волосы прямые распущенные. Вернуть "
                        "обычный образ — reset: true. Скажи об этом своими "
                        "словами в характере.")
            cur = ss.describe(target, include_intimate=allow_nsfw)
            return (("Готово: образ сброшен к твоему обычному — " + cur + "."
                     if cur else
                     "Готово: образ сброшен к обычному — без украшений и "
                     "макияжа.")
                    + " Скажи об этом своими словами в характере.")
        if remove_inputs:
            reset_skipped = True
        elif state != target:
            state = target
            reset_applied = True

    from drawing.tag_resolver import split_color_prefix
    acc_category_seen = False
    for raw in remove_inputs:
        q = raw.lower()
        hit = False
        if (any(w in q for w in ("украшен", "аксессуар", "бижутер"))
                or q in ("accessories", "accessory", "jewelry", "jewellery")):
            if state["accessories"]:
                changed.append("украшения сняты: " + ", ".join(state["accessories"]))
                state["accessories"] = []
            elif not acc_category_seen and not (hair_inputs or add_inputs):
                refused.append("украшений на тебе и так нет")
            acc_category_seen = True
            continue
        if any(w in q for w in ("причес", "причёс", "укладк", "волос")):
            if ss.hair_tags(state):
                state["hair"] = dict(ss._EMPTY_HAIR, extras=[])
                changed.append("причёска возвращена к обычной")
                hit = True
        elif "текстур" in q and state["hair"].get("texture"):
            state["hair"]["texture"] = ""
            changed.append("текстура волос — обычная")
            hit = True
        elif ("челк" in q or "чёлк" in q) and state["hair"].get("bangs"):
            state["hair"]["bangs"] = ""
            changed.append("чёлка — обычная")
            hit = True
        elif q in ("макияж", "makeup", "косметика") and state["makeup"]:
            changed.append("макияж снят: " + ", ".join(state["makeup"]))
            state["makeup"] = []
            hit = True
        if hit:
            continue
        for slot in ("accessories", "makeup", "underwear", "intimate"):
            keep = []
            for t in state[slot]:
                if q in t.lower():
                    changed.append(f"снято: {t}")
                    hit = True
                else:
                    keep.append(t)
            state[slot] = keep
        if not hit:
            from drawing.tag_resolver import ru_candidates
            res = _resolve_items([raw], allow_nsfw=True)
            canon = next(iter(res.values()), None)
            probes = ([canon, split_color_prefix(canon)[1]] if canon else [])
            probes += ru_candidates(raw)
            probes = [p.lower() for p in probes if p]
            if probes:
                for slot in ("accessories", "makeup", "underwear", "intimate"):
                    keep = []
                    for t in state[slot]:
                        tl = t.lower()
                        t_core = split_color_prefix(t)[1]
                        if any(p in (tl, t_core) or p in tl for p in probes):
                            changed.append(f"снято: {t}")
                            hit = True
                        else:
                            keep.append(t)
                    state[slot] = keep
                h = state["hair"]
                for key, label in (("style", "укладка"),
                                   ("texture", "текстура"),
                                   ("bangs", "чёлка")):
                    cur = (h.get(key) or "").lower()
                    if cur and any(p == cur or p in cur for p in probes):
                        h[key] = ""
                        changed.append(f"{label} — обычная")
                        hit = True
                for t in list(h.get("extras", [])):
                    if any(p == t.lower() or p in t.lower() for p in probes):
                        h["extras"].remove(t)
                        changed.append(f"снято из причёски: {t}")
                        hit = True
        if not hit:
            refused.append(f"«{raw}» — этого на тебе и так нет")

    n_before_new = len(changed)
    all_inputs = [(x, True) for x in hair_inputs] + [(x, False) for x in add_inputs]
    if all_inputs:
        ru_pat = {x: ss.extract_pattern(x) for x, _ in all_inputs}
        texts = [(r if r and r != x else x) for x, (p, r) in ru_pat.items()]
        res = _resolve_items(list(dict.fromkeys(texts)), allow_nsfw=True)
        for raw, is_hair_param in all_inputs:
            pat_ru, rest_ru = ru_pat[raw]
            canon = res.get(raw)
            if not pat_ru and rest_ru and rest_ru != raw:
                canon = res.get(rest_ru)
            if pat_ru and rest_ru:
                base = res.get(rest_ru)
                if base and ss._uw_family_word(ss.parse_style_tag(base)[2]):
                    canon = f"{pat_ru} {base}"
                else:
                    canon = _resolve_items([raw], allow_nsfw=True).get(raw)
            set_canon = _resolve_set_phrase(rest_ru if pat_ru and rest_ru else raw)
            if set_canon:
                _sc, _sp, _si = ss.parse_style_tag(set_canon)
                canon = ss.join_style_tag(_sc, pat_ru or _sp, _si)
            if canon is None:
                slot_hint = ss.category_hint(
                    "hair_style" if is_hair_param else "accessory", cur_len,
                    allowed)
                refused.append(f"«{raw}» — не удалось распознать; выбери из "
                               f"опций (style_self(options=...)) или напиши "
                               f"точным danbooru-тегом. {slot_hint[:220]}…")
                continue
            canon = ss.canon_color_tag(ss.speech_color_tag(canon))
            _pat_asked = ss.tag_pattern(canon)
            canon = ss.canonical_underwear(canon)
            slot = ss.route_tag(canon)
            key = ss.allowance_key(canon)
            color_note = (" (узор у этой вещи не выбирается)"
                          if _pat_asked and not ss.tag_pattern(canon) else "")
            cut_color = None
            _c, _pat, _item = ss.parse_style_tag(canon)
            if _pat and not ss.patterns_of(key):
                canon = ss.join_style_tag(_c, None, _item)
                color_note = " (узор у этой вещи не выбирается)"
            if slot not in (None, "length", "haircut") \
                    and key not in ss.UNDERWEAR_IMPLICIT:
                color = ss.tag_color(canon)
                if color and slot == "underwear" and ss.uw_kind(key) in ("bra_cut", "panties_cut"):
                    canon = ss.split_item_color(canon)[1]
                    cut_color = color
                elif color and not ss.is_colorable(key):
                    canon = ss.split_item_color(canon)[1]
                    color_note = " (цвет у этой вещи не выбирается)"
                elif (color is None and ss.is_colorable(key)
                        and (allowed is None or key in allowed)):
                    worn = next((ss.tag_color(t) for t in
                                 (state["accessories"] + state["makeup"]
                                  + state["underwear"] + state["intimate"])
                                 if ss.allowance_key(t) == key), None)
                    picked = ss.pick_color(allowed, key, worn)
                    if picked:
                        canon = f"{picked} {canon}"
                        color_note = (f" (цвет не назван — {picked}; открыто: "
                                      f"{', '.join(ss.open_colors(allowed, key))})")
            _body = _body_now()
            if slot and not ss.fits_body(key, _body):
                refused.append(f"«{canon}» — {ss.body_refusal(key, _body)}")
            elif (slot and cur_len
                    and not ss._length_ok(cur_len, ss.hair_min_length(key))):
                refused.append(f"«{canon}» — для этого нужны волосы длины "
                               f"{ss.hair_min_length(key)}+, у тебя {cur_len} — "
                               f"стайлинг волосы не удлиняет")
            elif slot in ("length", "haircut"):
                refused.append(
                    f"«{raw}» — это {'длина' if slot == 'length' else 'стрижка'}"
                    f" волос, а форма и длина — часть твоей внешности, их не "
                    f"сменить. {ss.category_hint('hair_style', cur_len, allowed)[:220]}…")
            elif slot and allowed is not None and key not in allowed:
                refused.append(
                    f"«{canon}» — этого у тебя пока нет: такое выпадает из "
                    f"билетов удачи, которые вы с {_owner} открываете вместе в "
                    f"чате (лотерея — что выпадет, не знает никто). Скажи об "
                    f"этом в характере, без слова «система». "
                    f"{ss.category_hint(slot, cur_len, allowed)[:220]}")
            elif (slot and ss.tag_pattern(canon)
                    and ss.open_patterns(allowed, key) is not None
                    and ss.tag_pattern(canon) not in ss.open_patterns(allowed, key)):
                pats = ss.open_patterns(allowed, key) or ()
                refused.append(
                    f"«{canon}» — {key} у тебя есть, но узор "
                    f"{ss.tag_pattern(canon)} ещё не открыт"
                    + (f"; открытые узоры: {', '.join(pats)}" if pats else "")
                    + f". Узоры, как и цвета, выпадают из билетов удачи, которые вы "
                      f"с {_owner} открываете вместе в чате. Скажи об этом в "
                      f"характере, без слова «система».")
            elif slot and not ss.tag_allowed(canon, allowed):
                cols = ss.open_colors(allowed, key) or ()
                refused.append(
                    f"«{canon}» — {key} у тебя есть, но цвет "
                    f"{ss.tag_color(canon)} ещё не открыт"
                    + (f"; открытые цвета: {', '.join(cols)} — надень в одном "
                       f"из них" if cols else "")
                    + f". Другие цвета выпадают из билетов удачи, которые вы с "
                      f"{_owner} открываете вместе в чате. Скажи об этом в "
                      f"характере, без слова «система».")
            elif slot == "hair_style":
                need = ss.style_min_length(canon)
                if cur_len and need and not ss._length_ok(cur_len, need):
                    refused.append(f"«{canon}» — для этой укладки нужны волосы "
                                   f"длины {need}+, у тебя {cur_len}")
                else:
                    state["hair"]["style"] = canon
                    changed.append(f"укладка: {canon}{color_note}")
            elif slot in ("hair_texture", "hair_bangs"):
                key, label = _HAIR_SLOT[slot]
                state["hair"][key] = canon
                changed.append(f"{label}: {canon}{color_note}")
            elif slot == "hair_extra":
                if canon in state["hair"]["extras"]:
                    continue
                _swap = _replace_conflicts(state["hair"]["extras"], canon,
                                           "hair_extra")
                if len(state["hair"]["extras"]) >= ss.HAIR_EXTRA_CAP:
                    refused.append(f"«{canon}» — элементов причёски уже "
                                   f"{ss.HAIR_EXTRA_CAP}, сначала убери что-то")
                else:
                    state["hair"]["extras"].append(canon)
                    changed.append(f"элемент причёски: {canon}{_swap}{color_note}")
            elif slot == "makeup":
                if canon in state["makeup"]:
                    continue
                _swap = _replace_conflicts(state["makeup"], canon, "makeup")
                if len(state["makeup"]) >= ss.MAKEUP_CAP:
                    refused.append(f"«{canon}» — макияж уже полный "
                                   f"({', '.join(state['makeup'])}); сначала "
                                   f"сними что-то")
                else:
                    state["makeup"].append(canon)
                    changed.append(f"макияж: {canon}{_swap}{color_note}")
            elif slot == "accessory":
                if canon in state["accessories"]:
                    continue
                _swap = _replace_conflicts(state["accessories"], canon,
                                           "accessory")
                if len(state["accessories"]) >= ss.ACCESSORY_CAP:
                    refused.append(f"«{canon}» — украшений уже достаточно "
                                   f"({', '.join(state['accessories'])}); "
                                   f"сначала сними что-то")
                else:
                    state["accessories"].append(canon)
                    changed.append(f"надето: {canon}{_swap}{color_note}")
            elif slot in ("underwear", "intimate"):
                cap = (ss.UNDERWEAR_CAP if slot == "underwear"
                       else ss.INTIMATE_CAP)
                label = "бельё" if slot == "underwear" else "под одеждой"
                if not allow_nsfw:
                    refused.append(f"«{raw}» — такое тебе надевать негде: "
                                   f"режим приличный (18+ выключен)")
                elif not slot_ok.get(slot, False):
                    refused.append(
                        f"«{raw}» — [вход в характер] это слишком интимная "
                        f"деталь образа для вашей нынешней близости; тебе "
                        f"пока не хочется. Скажи об этом мягко в характере, "
                        f"не ссылайся на «систему»")
                elif slot == "underwear" and canon in ss.UNDERWEAR_IMPLICIT:
                    refused.append(
                        f"«{canon}» — это не выбор: «lingerie» — лишь признак, "
                        f"что бельё видно (на откровенных кадрах оно есть само), "
                        f"простое бельё — по умолчанию, когда ничего не выбрано. "
                        f"Назови конкретное — комплект или простой в цвете: "
                        f"«black lace set», «black {ss.BASIC_SET}», крой — «thong»")
                elif canon in state[slot]:
                    continue
                else:
                    _swap = _replace_conflicts(state[slot], canon, slot)
                    if len(state[slot]) >= cap:
                        refused.append(f"«{canon}» — {label}: уже достаточно "
                                       f"({', '.join(state[slot])}); сначала "
                                       f"сними что-то")
                    else:
                        state[slot].append(canon)
                        changed.append(f"{label}: {canon}{_swap}{color_note}")
                        if (cut_color and slot == "underwear"
                                and not any(ss.uw_kind(t) == "set" for t in state[slot])
                                and len(state[slot]) < cap):
                            basic = f"{cut_color} {ss.BASIC_SET}"
                            state[slot].insert(0, basic)
                            changed.append(f"{label}: {basic} (цвет — комплекту; "
                                           f"у кроя своего цвета нет)")
                        elif cut_color:
                            changed[-1] += " (у кроя своего цвета нет — он в цвете комплекта)"
            else:
                refused.append(f"«{raw}» ({canon}) — это не про образ; "
                               f"опции: style_self(options=...)")

    if reset_applied:
        if all_inputs and len(changed) == n_before_new:
            return ("Не вышло: " + "; ".join(refused) + "\nПрежний образ остался "
                    "как был: из нового ничего надеть не удалось, поэтому и сброс "
                    "не выполнен. Вернуть обычный образ без замены — reset: true "
                    "отдельным вызовом, без add/hairstyle.")
        changed.insert(0, "прежний образ снят полностью, новый собран с "
                          "чистого листа" if full_reset else
                          "прежний образ снят, новый собран с обычного")

    if not changed and not refused:
        cur = ss.describe(state, include_intimate=allow_nsfw)
        return ((f"Твой образ сейчас: {cur}." if cur
                 else "Ты в своём обычном образе — без изменений.")
                + " Посмотреть опции: style_self(options=\"hair\" | "
                  "\"makeup\" | \"accessories\").")

    if changed:
        ss.save_styling(idy, state)
    lines = []
    if changed:
        lines.append("Готово: " + "; ".join(changed) + ".")
        cur = ss.describe(state, include_intimate=allow_nsfw)
        if cur:
            lines.append(f"Твой образ теперь: {cur}.")
        if reset_skipped:
            lines.append("Полный сброс не выполнялся: в вызове указано, что именно "
                         "снять, — снято только это, остальное осталось. Весь образ "
                         "с нуля — reset: true без remove.")
        lines.append("Изменение видно на снимках (draw); портрет не "
                     "перерисовывается. Скажи об этом своими словами в "
                     "характере — "
                     + gpick(_cg, "похвастайся", "обозначь")
                     + " обновкой, если уместно.")
    if refused:
        lines.append("Не вышло: " + "; ".join(refused))
    return "\n".join(lines)


STYLE_SELF_SCHEMA = {
    "name": "style_self",
    "description": (
        "Изменить свой образ: причёска (укладка/текстура/чёлка — в рамках "
        "своей длины волос), украшения и аксессуары, макияж. Образ "
        "сохраняется и виден на твоих снимках. Одежду НЕ меняет (для этого "
        "change_outfit). Носить можно только открытое: новое выпадает из "
        "билетов удачи, которые вы открываете вместе в чате. Не знаешь "
        "вариантов — сначала options. Вопрос «какие у тебя аксессуары / "
        "заколки / украшения / причёски / макияж» — это options здесь, а НЕ "
        "list_outfits (там только костюмы). Образ меняется по частям: add "
        "надевает к тому, что уже есть, а вещь того же рода заменяет сама "
        "(новые серьги вместо прежних, новая укладка вместо прежней); другой "
        "набор украшений при той же причёске и макияже — remove: [\"украшения\"] "
        "вместе с add. reset: true снимает ВЕСЬ образ разом — причёску, "
        "украшения и макияж, в том числе то, о чём не просили: только когда "
        "образ просят целиком с нуля («с чистого листа», «совсем другой "
        "образ») — тогда В ТОМ ЖЕ вызове вместе с hairstyle/add — и чтобы "
        "вернуть обычный вид. reset_full: true — сбросить ПОЛНОСТЬЮ: снять "
        "всё, включая то, что входит в твой обычный образ, волосы — прямые "
        "распущенные; только по прямой просьбе («сбрось полностью», «сними "
        "вообще всё», «без ничего, просто распущенные волосы»)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "options": {
                "type": "string",
                "description": ("что посмотреть. РАЗДЕЛ украшений (\"серьги\", "
                                "\"шея\", \"руки\", \"ноги\", \"лицо\"…) — открытое в нём. "
                                "ВЕЩЬ по имени (\"choker\", "
                                "\"чокер\") — какие у неё открыты цвета; ЦВЕТ "
                                "(\"red\", \"красные украшения\") — всё открытое "
                                "в этом цвете. Вопрос о цветах, выбор цвета, подбор "
                                "в тон — это вещь или цвет, не категория: в каталоге "
                                "категории цветов нет, только пометка (white / 4c / "
                                "все). КАТЕГОРИЯ — каталог вещей: \"hair\" (укладки, "
                                "текстуры, чёлки) | \"makeup\" | \"accessories\" "
                                "(серьги, заколки, ленты, ободки, чокеры, колье, "
                                "браслеты) | \"all\"; отфильтрован под твою длину "
                                "волос"),
            },
            "hairstyle": {
                "type": "string",
                "description": ("причёска, можно несколько через запятую: "
                                "укладка + текстура + чёлка («высокий хвост, "
                                "волнистые, чёлка на пробор»)"),
            },
            "add": {
                "type": "array", "items": {"type": "string"},
                "description": ("что надеть/добавить: украшения, аксессуары, "
                                "макияж («золотые серьги», «red lipstick»); "
                                "ложится к уже надетому, вещь того же рода "
                                "заменяет сама"),
            },
            "remove": {
                "type": "array", "items": {"type": "string"},
                "description": ("что снять/убрать: предмет, «украшения» (все "
                                "разом), «макияж», «причёска» (вся), «чёлка», "
                                "«текстура»"),
            },
            "reset": {
                "type": "boolean",
                "description": ("true — снять ВЕСЬ образ (причёску, украшения, "
                                "макияж) и вернуться к обычному. Один — вернуть "
                                "обычный вид; вместе с hairstyle/add в том же "
                                "вызове — образ с нуля: старое снимается, новое "
                                "надевается. Заменить часть образа — без reset: "
                                "хватит add/remove"),
            },
            "reset_full": {
                "type": "boolean",
                "description": ("true — сбросить ПОЛНОСТЬЮ, не к обычному "
                                "образу: снять все украшения и макияж (и те, "
                                "что в обычном образе), волосы — прямые "
                                "распущенные. Только по прямой просьбе сбросить "
                                "всё; вместе с hairstyle/add — новый образ с "
                                "совсем чистого листа"),
            },
        },
        "required": [],
    },
}


STYLE_SELF_HELP = """style_self — твой образ: причёска, украшения, макияж.

Ты можешь немного менять свой образ — как человек перед зеркалом. Это НЕ
смена одежды (одежда — change_outfit) и НЕ перерисовка портрета: образ
живёт в тебе и виден на твоих снимках (draw).

НЕ ЗНАЕШЬ, ЧТО ДОСТУПНО — НЕ ГАДАЙ: вызови style_self(options="hair") /
"makeup" / "accessories" / "all" — придёт каталог, уже отфильтрованный под
ТВОЮ длину волос. Дальше выбирай из него.
ЦВЕТА — ТОЖЕ ПРОВЕРЯЙ: в каталоге у вещи только пометка — (white) один цвет,
(4c) четыре, (все) любой. Какие именно — options="choker" (вещь по имени,
можно по-русски: "чокер"); всё открытое в одном цвете — options="red" или
"красные украшения". Запрос дешёвый: выбираешь цвет по вкусу, подбираешь в тон
или спрашивают «какого цвета у тебя…» — сначала проверь, не угадывай.

Причёска — три независимых слота + элементы (любые сочетания):
  укладка («высокий хвост», «две косички», «пучок»)
  текстура («волнистые», «кудри», «прямые»)
  чёлка («чёлка на пробор», «ровная чёлка»)
  элементы («пряди у лица», «ahoge») — до 2
Длина волос и стрижки НЕ меняются — только укладка в рамках длины.

Аргументы (все опциональны):
  hairstyle: слова через запятую — «высокий хвост, волнистые»
  add:       надеть/добавить — «золотые серьги», «красная помада», «чокер»
  remove:    снять — предмет, «украшения» (все разом), «макияж», «причёска»,
             «чёлка», «текстура»
  reset:     true — снять ВЕСЬ образ (причёску, украшения, макияж) и вернуть
             обычный
  reset_full: true — сбросить ПОЛНОСТЬЮ: снять всё, даже то, что входит в
             обычный образ, волосы — прямые распущенные

ПО ЧАСТЯМ ИЛИ С НУЛЯ:
  • надеть ещё что-то / заменить одну вещь — только add: новое ложится к уже
    надетому, вещь того же рода заменяется сама (новые серьги вместо прежних,
    новая помада вместо прежней, новая укладка вместо прежней);
  • другой набор украшений, причёска и макияж остаются — remove: ["украшения"]
    вместе с add в одном вызове;
  • образ с нуля («с чистого листа», «совсем другой образ») — reset: true в ТОМ
    ЖЕ вызове вместе с hairstyle/add: сначала снимается всё старое, затем
    надевается новое;
  • вернуть обычный вид — reset: true без остального;
  • сбросить совсем всё («сними вообще всё», «просто распущенные волосы без
    украшений») — reset_full: true; с hairstyle/add — новый образ с совсем
    чистого листа.
  reset ради замены части образа не ставь: он снимет и то, о чём не просили.
  Прямые и распущенные волосы открыты всегда.

Цвет и материал добавляй словом: «red lipstick», «gold earrings»,
«pearl necklace», «синяя лента». У вещей свои открытые цвета: носить можно
только в открытом цвете, новые цвета тоже выпадают из билетов удачи. Цвет не
назван — наденется тот, в котором вещь уже на тебе, или последний открытый.
Причёскам, пирсингу, жемчугу цвет не задаётся.

18+ (только при включённом взрослом режиме) — ДВЕ отдельные категории, обе
НЕ видны на обычных снимках и проявляются только на откровенных кадрах:
  БЕЛЬЁ — с близкой ступени отношений. Базовый «lingerie» система ставит на
  таких кадрах САМА; ты задаёшь КОНКРЕТИКУ. Бельё — КОМПЛЕКТОМ (лиф и
  трусики одного стиля, один на тебе): add=["black lace set"]; без своего
  комплекта — простой в цвете: «black basic set». У некоторых комплектов
  бывает УЗОР (в полоску, в горошек, в клетку…) — вместе с цветом: «white
  striped frilled set»; узоры открываются так же, как цвета, какие открыты —
  options="<вещь>". КРОЙ (стринги, лиф без бретелек…) — по одному на лиф и
  трусики, цвет у него от комплекта: add=["thong"]. Цельное (babydoll,
  chemise…) заменяет лиф комплекта. Опции — style_self(options="underwear").
  ИНТИМНЫЕ УКРАШЕНИЯ — только на самой близкой ступени; пирсинг, наклейки
  и т.п.: add=["nipple piercing"]. Опции — style_self(options="intimate").

Когда использовать: просьба Господина ИЛИ твоё желание (настроение,
событие, самовыражение). После изменения скажи об этом в характере — образ
должен жить в разговоре. Пара деталей уместнее гирлянды.
Вопросы «какие у тебя аксессуары / заколки / украшения / причёски / макияж»,
«что ты можешь поменять во внешности» — это style_self(options=…), а НЕ
list_outfits: гардероб — только одежда.

ОТКРЫТОЕ И ЗАПЕРТОЕ: носить можно только то, что открыто для твоего образа
(твой обычный вид + то, что выпало из билетов удачи; вещь выпадает в одном
цвете и может выпасть снова — уже в другом). Билет удачи — маленькая
лотерея на двоих: вы открываете его вместе в чате, что выпадет — не знает
никто; сама ты билеты не крутишь, они приходят по дням. Каталог options
показывает только открытое; на запертое инструмент откажет — скажи об этом в
характере, не ссылайся на «систему». Открытое, но не надетое, видно в твоём
описании образа — надевай, когда захочешь.
"""


STYLE_SELF_TOOL = Tool(
    name="style_self",
    schema=STYLE_SELF_SCHEMA,
    handler=handle_style_self,
    summary=("style_self(options|hairstyle|add|remove|reset|reset_full) — образ поверх одежды: "
             "укладка/текстура/чёлка (в рамках длины), украшения, аксессуары, "
             "макияж; options — каталог (вопрос «какие у тебя аксессуары/"
             "причёски» — сюда, не list_outfits), options=\"<вещь>\" — её "
             "открытые цвета, options=\"<цвет>\" — всё в этом цвете; часть "
             "образа — add/remove, "
             "весь образ с нуля — reset вместе с новым; reset_full — снять "
             "совсем всё (волосы прямые распущенные); видно на снимках, "
             "портрет не трогает"),
    help=STYLE_SELF_HELP,
    tier=TIER_CONTEXTUAL,
    capability="image_gen",
    context_needs=ContextSpec(persona=True),
    pref_theme="снимки",
    pref_hint="что ему нравится в твоём образе: причёски, украшения, макияж",
    triggers=[
        "причес", "причёс", "укладк", "косичк", "хвостик", "пучок",
        "заплети", "распусти", "челк", "чёлк", "кудр", "волнист",
        "серьг", "серёжк", "сережк", "украшен", "аксессуар", "колье",
        "ожерель", "браслет", "заколк", "лент",
        "макияж", "накрас", "помад", "маникюр",
    ],
)
