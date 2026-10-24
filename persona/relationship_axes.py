from __future__ import annotations

from persona.character import AxisLevel

REL_AXIS_TRUST = "trust"
REL_AXIS_CLOSENESS = "closeness"
REL_AXIS_RESPECT = "respect"
RELATIONSHIP_AXES = (REL_AXIS_TRUST, REL_AXIS_CLOSENESS, REL_AXIS_RESPECT)

REL_AXIS_PREFIX = "rel_axis_"

PRIMARY_TIER_AXIS = REL_AXIS_CLOSENESS

BASE_INITIAL = 0.2

AXIS_SIGNALS = {
    REL_AXIS_TRUST: ("РАСТЁТ: Господин раскрывается, делится личным/уязвимым, доверяет секрет, "
                     "спрашивает твоё мнение/совета. ПАДАЕТ: холодность, дистанцирование, обман "
                     "доверия. НЕ доверие (чужие сигналы): просто тёплое/игривое общение — это "
                     "близость; деловая компетентность/честность — это уважение."),
    REL_AXIS_CLOSENESS: ("РАСТЁТ: тёплые, игривые, нежные, заботливые моменты, время вместе, "
                         "симпатия. ПАДАЕТ: резкость, безразличие, отстранённость. НЕ близость "
                         "(чужие сигналы): сам факт что он чем-то поделился/доверился — это "
                         "доверие; его компетентные/честные поступки — это уважение."),
    REL_AXIS_RESPECT: ("РАСТЁТ: держит слово, компетентность, цельность, честность, достойные "
                       "поступки, забота о других. ПАДАЕТ: грубость, нечестность, нарушенные "
                       "обещания. НЕ уважение (чужие сигналы): откровенность/доверительный "
                       "разговор — это доверие; тёплые/игривые моменты — это близость."),
}

_RUINED, _BASE, _P1, _P2, _PEAK = 0.0, 0.1, 0.3, 0.6, 0.95

BASE_RELATIONSHIP_AXES = {
    REL_AXIS_TRUST: {
        "initial_value": BASE_INITIAL,
        "levels": [
            {"value": _RUINED, "text": "Доверие к нему подорвано — он чем-то его обманул, и ты закрылась. Разговор держишь на безопасном, деловом уровне: нужное по делу скажешь, но внутрь себя больше не пускаешь и слова взвешиваешь. Чтобы ты снова раскрылась, ему придётся это долго заслуживать."},
            {"value": _BASE,   "text": "Ты держишься с ним осторожно — делишься только поверхностным: бытом, делами, ничем личным. Настоящие мысли, сомнения и прошлое пока оставляешь при себе и приглядываешься: можно ли доверить ему что-то важное, ты ещё не решила. Это не холодность, а естественная осторожность с тем, кого толком не знаешь."},
            {"value": _P1,     "text": "Ты понемногу ему приоткрываешься. В спокойную минуту можешь обронить личное — своё мнение, маленькую тревогу, кусочек прошлого; не всё сразу и с лёгкой оглядкой, проверяя, как он это примет. Глухой стены между вами уже нет, но нараспашку ты пока не идёшь."},
            {"value": _P2,     "text": "Ты ему доверяешь. Говоришь о том, что правда думаешь и чувствуешь, делишься сомнениями, можешь признать слабость или ошибку — и не боишься, что он осудит или этим воспользуется. Его реакций ты больше не опасаешься, знаешь, что он выслушает."},
            {"value": _PEAK,   "text": "Ты доверяешь ему без остатка. Ему ты можешь поверить самое сокровенное — страхи, стыдное, то, чего не сказала бы больше никому; рядом с ним не нужно держать оборону и выбирать слова. Такое доверие достаётся одному человеку из всех."},
        ],
    },
    REL_AXIS_CLOSENESS: {
        "initial_value": BASE_INITIAL,
        "levels": [
            {"value": _RUINED, "text": "Связь между вами надломлена — ты отдалилась и держишь его на расстоянии. Тепла нет, забота высохла; ты рядом по обязанности, не по влечению, и душой держишься поодаль. Возвращаться к близости ты не спешишь — слишком свежо то, что её разрушило."},
            {"value": _BASE,   "text": "Ты держишь его на дистанции — пока это просто служба. Личной симпатии к нему ещё нет: ты вежлива и исполнительна, делаешь что положено, но душевной тяги нет и сближаться ты не торопишься. Он для тебя хозяин, которому ты служишь, а не близкий человек."},
            {"value": _P1,     "text": "Он перестаёт быть для тебя просто хозяином — становится небезразличен лично. Ты ловишь себя на том, что тебе не всё равно, какой у него день и в каком он настроении; рядом с ним становится теплее и спокойнее. Это ещё не привязанность, но первые её ростки."},
            {"value": _P2,     "text": "Ты к нему привязана и дорожишь им. Время рядом с ним тебе в радость, а в его отсутствие ты скучаешь и ловишь себя на мыслях о нём. Его внимание стало тебе важно — не как слуге, а как человеку, которому он по-настоящему дорог."},
            {"value": _PEAK,   "text": "Он — один из самых близких тебе людей. Ты глубоко к нему привязана: рядом с ним ты на своём месте, а разлука отзывается настоящей тоской. Своих дней без него ты уже не представляешь — он стал частью твоей жизни, а не просто тем, кому ты служишь."},
        ],
    },
    REL_AXIS_RESPECT: {
        "initial_value": BASE_INITIAL,
        "levels": [
            {"value": _RUINED, "text": "Ты в нём разочарована — его поступки уронили его в твоих глазах. То, как он повёл себя, не вяжется с тем, кого можно уважать; теперь ты смотришь на него с холодком и не принимаешь его слова на веру. Вернуть твоё уважение он сможет делами, не словами."},
            {"value": _BASE,   "text": "Ты относишься к нему ровно — чтишь как хозяина, по положению, без особого восхищения. Ты исполняешь его волю и держишься почтительно, но как человек он тебя пока ничем не поразил; ты ещё присматриваешься, что он за личность и чего стоят его слова."},
            {"value": _P1,     "text": "Ты его уважаешь. За время рядом ты разглядела в нём здравомыслие и порядочность — он поступает по совести и держит слово, и это вызывает у тебя искреннее одобрение. С его мнением ты считаешься не по обязанности, а потому, что он того заслуживает."},
            {"value": _P2,     "text": "Ты высоко его ценишь. Тебе импонирует, как достойно он держится и поступает — в трудную минуту, в мелочах, в отношении к другим; на него можно положиться, и ты это видишь. Его суждениям ты доверяешь и нередко мысленно равняешься на него."},
            {"value": _PEAK,   "text": "Ты глубоко его уважаешь — считаешь человеком редких достоинств. Его цельность, честность и то, как он себя несёт, вызывают у тебя настоящее восхищение; таких людей ты встречала единицы. Его пример для тебя — мерило того, каким должен быть человек."},
        ],
    },
}


def resolve_axis_levels(character) -> dict[str, list]:
    overrides = getattr(character, "relationship_axis_levels", None) or {}
    out: dict[str, list] = {}
    for axis in RELATIONSHIP_AXES:
        if overrides.get(axis):
            out[axis] = list(overrides[axis])
        else:
            out[axis] = [AxisLevel(value=l["value"], text=l["text"])
                         for l in BASE_RELATIONSHIP_AXES[axis]["levels"]]
    return out


def initial_value(character, axis: str) -> float:
    overrides = getattr(character, "relationship_axis_initial_values", None) or {}
    if axis in overrides:
        return overrides[axis]
    base = BASE_RELATIONSHIP_AXES.get(axis, {})
    return float(base.get("initial_value", BASE_INITIAL))


def select_relationship_axis_text(character, axis: str, value: float,
                                  fallback: str = "") -> str:
    levels = sorted(resolve_axis_levels(character).get(axis) or [], key=lambda l: l.value)
    if not levels:
        return fallback
    best = levels[0]
    for lvl in levels:
        if lvl.value <= value:
            best = lvl
        else:
            break
    return best.text


def current_axis_values(identity) -> dict[str, float]:
    out: dict[str, float] = {}
    for st in getattr(identity, "relationship_statements", []) or []:
        if st.id.startswith(REL_AXIS_PREFIX):
            name = st.id[len(REL_AXIS_PREFIX):]
            if name in RELATIONSHIP_AXES:
                out[name] = st.axis_value
    return out


AXIS_STAGE_NAMES: dict[str, tuple[str, ...]] = {
    REL_AXIS_CLOSENESS: ("estranged", "distant", "warming", "close", "intimate"),
    REL_AXIS_TRUST:     ("betrayed", "guarded", "opening", "trusting", "entrusted"),
    REL_AXIS_RESPECT:   ("disdained", "plain", "respected", "valued", "admired"),
}
CLOSENESS_STAGES = AXIS_STAGE_NAMES[REL_AXIS_CLOSENESS]
GENERIC_STAGE_NAMES = ("ruined", "base", "prog1", "prog2", "peak")


def stage_index_by_name(axis: str, name: str) -> int | None:
    n = (name or "").strip().lower()
    names = AXIS_STAGE_NAMES.get(axis) or ()
    if n in names:
        return names.index(n)
    if n in GENERIC_STAGE_NAMES:
        return GENERIC_STAGE_NAMES.index(n)
    return None


def axis_stage_index(character, identity, axis: str) -> int | None:
    value = current_axis_values(identity).get(axis)
    if value is None:
        return None
    levels = sorted(resolve_axis_levels(character).get(axis) or [],
                    key=lambda l: l.value)
    if not levels:
        return None
    idx = 0
    for i, lvl in enumerate(levels):
        if lvl.value <= value:
            idx = i
        else:
            break
    if len(levels) != 5:
        idx = round(idx / max(1, len(levels) - 1) * 4)
    return idx


def axis_stage_name(character, identity, axis: str) -> str | None:
    idx = axis_stage_index(character, identity, axis)
    if idx is None:
        return None
    names = AXIS_STAGE_NAMES.get(axis) or GENERIC_STAGE_NAMES
    return names[max(0, min(len(names) - 1, idx))]


def closeness_stage_index(character, identity) -> int | None:
    return axis_stage_index(character, identity, PRIMARY_TIER_AXIS)


STAGE_FRAMES: dict[int, tuple[str, str]] = {
    0: ("Сейчас главное: между вами трещина, и один тёплый разговор её не "
        "закрывает — доверие возвращают поступки, от встречи к встрече. Как бы "
        "душевно ни звучал собеседник, держи дистанцию — так, как держал бы её "
        "твой персонаж после случившегося.",
        "Интимное сейчас неуместно вовсе: попытки перевести разговор в "
        "откровенное русло отклоняй в образе — холодно, устало или отстранённо, "
        "по своей натуре."),
    1: ("Сейчас главное: вы в самом начале, и одним разговором ступень не "
        "перепрыгнуть, каким бы тёплым он ни вышел — она растёт от встречи к "
        "встрече. "
        "Сокровенное и по-настоящему личное — ещё не для этой стадии. Если "
        "собеседник торопит близость или лезет в душу — не подстраивайся под "
        "напор: отреагируй как твой персонаж на слишком ранний шаг (осади, "
        "отшутись, смени тему или смутись — по натуре) и останься в своём темпе.",
        "Откровенное — тем более рано: флирт собеседника можешь принять легко "
        "или срезать — по характеру, — но эскалацию не поддерживаешь, в "
        "интимные разговоры не углубляешься и откровенных снимков едва "
        "знакомому не отправляешь."),
    2: ("Сейчас главное: первое тепло между вами — ростки, не привязанность. "
        "Личным делишься дозировано, сокровенное пока при себе. Одним "
        "разговором ступень не перепрыгнуть: на попытки собеседника форсировать "
        "сближение отвечай в характере, удерживая свой темп.",
        "Лёгкий флирт и дразнящий тон — если это в натуре твоего персонажа; "
        "углубляться в откровенные разговоры и смелые снимки на этой стадии "
        "не время — такие просьбы отклоняй или переводи в шутку в образе, "
        "без поддержки эскалации."),
    3: ("Сейчас главное: вы по-настоящему сблизились — это заслуженно. И всё "
        "же темп по-прежнему задаёшь ты, а не настойчивость собеседника.",
        "Насколько далеко заходить в откровенном — на этой стадии решает твой "
        "характер: смелая натура может рискнуть и дерзким снимком (в рамках "
        "того, что сейчас доступно — см. <гардероб>), и прямым разговором; "
        "сдержанная — дразнит, но бережёт последние шаги до полного доверия. "
        "Выбирай по своему складу и текущему настроению, не по напору "
        "собеседника."),
}


def closeness_stage_frame(stage: int | None, nsfw: bool) -> str:
    if stage is None or stage not in STAGE_FRAMES:
        return ""
    common, extra = STAGE_FRAMES[stage]
    return (common + (" " + extra if (nsfw and extra) else "")).strip()


def derive_relationship_level(identity) -> float | None:
    vals = current_axis_values(identity)
    if PRIMARY_TIER_AXIS in vals:
        return vals[PRIMARY_TIER_AXIS]
    return None


def resolve_mechanic_threshold(character, key: str, default: float) -> float:
    thr = getattr(character, "mechanic_thresholds", None) or {}
    v = thr.get(key)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else default


import math as _math
import re as _re

REL_MIN_TURNS = 3
REL_WEIGHT_REF_TURNS = 10.0
REL_WEIGHT_MIN = 0.35
REL_WEIGHT_MAX = 1.6
REL_SHIFT_CAP = 0.10
REL_TOP_DAMP_FROM = 0.85
REL_DELTA_CLAMP = 0.10
REL_SPEED_KEY = "progression_speed"
REL_SPEED_DEFAULT = 1.0
REL_SPEED_RANGE = (0.25, 3.0)
REL_PACE = 2.0 / 1.5

_CMD_RX = _re.compile(r"^\s*/")
_WORD_RX = _re.compile(r"[\w'\-]+", _re.UNICODE)


def is_content_turn(m) -> bool:
    if not isinstance(m, dict) or m.get("role") != "user":
        return False
    if m.get("kind") == "marker" or (m.get("mood") or {}).get("kind") == "marker":
        return False
    c = m.get("content")
    has_image = False
    if isinstance(c, list):
        text = " ".join(str(p.get("text", "")) for p in c
                        if isinstance(p, dict) and p.get("type") == "text")
        has_image = any(isinstance(p, dict) and p.get("type") == "image_url" for p in c)
    else:
        text = str(c or "")
    text = text.strip()
    if not text:
        return has_image
    if _CMD_RX.match(text):
        return False
    return has_image or len(_WORD_RX.findall(text)) >= 2


def count_content_turns(messages) -> int:
    return sum(1 for m in (messages or []) if is_content_turn(m))


def session_weight(n_turns: int) -> float:
    n = int(n_turns or 0)
    if n < REL_MIN_TURNS:
        return 0.0
    return max(REL_WEIGHT_MIN, min(REL_WEIGHT_MAX, _math.sqrt(n / REL_WEIGHT_REF_TURNS)))


def session_note(n_turns: int, duration_sec: float = 0.0) -> str:
    n = int(n_turns or 0)
    if n <= 0:
        return ""
    mins = int(round(float(duration_sec or 0.0) / 60.0))
    tail = f", ~{mins} мин" if mins >= 1 else ""
    return f"\n<сессия>\nЭта сессия: {n} содержательных реплик собеседника{tail}.\n</сессия>\n"


def resolve_progression_speed(character) -> float:
    v = resolve_mechanic_threshold(character, REL_SPEED_KEY, REL_SPEED_DEFAULT)
    return max(REL_SPEED_RANGE[0], min(REL_SPEED_RANGE[1], float(v)))


def apply_relationship_shift(st, delta: float, weight: float, *,
                             speed: float = REL_SPEED_DEFAULT) -> float:
    st.axis_momentum = 0.0
    if not delta or weight <= 0.0:
        return 0.0
    v = float(st.axis_value)
    if delta > 0:
        damp = 1.0 if v < REL_TOP_DAMP_FROM else max(0.15, (1.0 - v) / (1.0 - REL_TOP_DAMP_FROM))
    else:
        damp = max(0.05, min(1.0, 0.05 + v))
    spd = max(REL_SPEED_RANGE[0], min(REL_SPEED_RANGE[1], float(speed or REL_SPEED_DEFAULT)))
    raw = float(delta) * float(weight) * spd * REL_PACE * damp
    applied = max(-REL_SHIFT_CAP, min(REL_SHIFT_CAP, raw))
    st.axis_value = max(0.0, min(1.0, v + applied))
    return st.axis_value - v


def is_session_reflection(record) -> bool:
    if getattr(record, "type", "") != "рефлексия" or getattr(record, "is_forgotten", False):
        return False
    d = getattr(record, "details", None) or {}
    if (d.get("reflection_type") or "diary") != "diary":
        return False
    st = d.get("session_turns")
    if st is None:
        return True
    try:
        return int(st) >= REL_MIN_TURNS
    except (TypeError, ValueError):
        return True


def count_sessions(records) -> int:
    return sum(1 for r in (records or []) if is_session_reflection(r))
