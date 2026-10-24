from __future__ import annotations

import re
import time

STIMULI_CAP = 60
STIMULI_TTL_SEC = 2 * 86400

_PATTERNS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "confidence": (
        (r"реши\s+сам[аи]?", r"решай\s+сам[аи]?", r"на\s+тво[йё]\s+(?:вкус|усмотрение|выбор)",
         r"тебе\s+решать", r"как\s+(?:сочтёшь|считаешь)\s+нужным", r"(?:я\s+)?тебе\s+доверяю",
         r"выбери\s+сам[аи]?", r"выбирай\s+сам[аи]?", r"полагаюсь\s+на\s+тебя",
         r"сделай\s+как\s+(?:знаешь|считаешь)"),
        (r"ты\s+ошиб(?:лась|ся)", r"ты\s+(?:напутал|перепутал)[аи]?", r"это\s+(?:неверно|неправильно|не\s+так)",
         r"сделаем\s+по-моему", r"отмен(?:яю|яем|и)\s+тво[её]\s+решение", r"я\s+(?:перерешу|решу\s+сам[аи]?)",
         r"не\s+выдумывай", r"так\s+нельзя\s+было"),
    ),
    "warmth": (
        (r"я\s+(?:так\s+)?уста[лв]\w*", r"мне\s+(?:плохо|тяжело|грустно|тревожно|одиноко)",
         r"тяж[её]лый\s+день", r"(?:я\s+)?вымота\w+", r"не\s+выспал\w+", r"(?:я\s+)?болею",
         r"мне\s+нездоровится", r"(?:я\s+)?(?:совсем\s+)?без\s+сил", r"голова\s+болит"),
        (r"не\s+надо,?\s+я\s+сам[аи]?", r"я\s+сам[аи]?\s+(?:сделаю|справлюсь|разберусь)",
         r"не\s+опекай", r"не\s+нянчись", r"мне\s+не\s+нужна\s+помощь", r"дай\s+мне\s+(?:пространство|побыть\s+одному)",
         r"оставь\s+меня", r"не\s+лезь", r"давай\s+по\s+делу"),
    ),
    "openness": (
        (r"смотри,?\s+что\s+(?:нашёл|нашла|откопал\w*)", r"хочу\s+(?:тебе\s+)?показать", r"давай\s+(?:попробуем|разберёмся)",
         r"попробуем\s+(?:что-то\s+)?ново\w+", r"расскажу\s+тебе\s+про", r"а\s+ты\s+(?:знаешь|слышала|слышал)\s+про",
         r"хочу\s+показать\s+тебе", r"разберёмся\s+вместе"),
        (r"верн[её]мся\s+к\s+(?:теме|делу)", r"не\s+отвлекайся", r"сначала\s+(?:доделай|закончи)",
         r"давай\s+по\s+порядку", r"закончи\s+(?:сначала|одно)", r"по\s+одному\s+делу"),
    ),
    "cheerfulness": (
        (r"у\s+меня\s+хорошая\s+новость", r"давай\s+(?:отпразднуем|отметим)", r"сегодня\s+(?:отличный|хороший)\s+день",
         r"порадуйся\s+со\s+мной", r"давай\s+(?:повеселимся|порадуемся)"),
        (r"не\s+(?:надо\s+)?(?:меня\s+)?(?:подбадривай|веселить|веселить\s+меня|подбадривать)",
         r"не\s+до\s+веселья", r"плохие\s+новости", r"мне\s+не\s+до\s+(?:смеха|шуток|веселья)",
         r"не\s+ищи\s+плюсы", r"просто\s+выслушай"),
    ),
    "playfulness": (
        (r"давай\s+поиграем", r"поиграем\??", r"а\s+слабо", r"спорим,?", r"подколи\s+меня",
         r"пошути", r"шути\s+(?:больше|дальше)", r"сыграем"),
        (r"я\s+серь[её]зно", r"без\s+шуток", r"давай\s+серь[её]зно", r"не\s+до\s+шуток",
         r"серь[её]зный\s+разговор", r"хватит\s+шутить", r"перестань\s+шутить", r"не\s+шути"),
    ),
    "energy": (
        (r"действуй\s+сам[аи]?", r"не\s+спрашивай,?\s+(?:просто\s+)?делай", r"можешь\s+не\s+спрашивать",
         r"возьми\s+(?:это\s+)?на\s+себя", r"займись\s+(?:этим|сам[аи]?)", r"напомни\s+мне",
         r"поставь\s+напоминание", r"делай\s+без\s+спроса", r"молодец,?\s+что\s+(?:сама|сам)\s+"),
        (r"давай\s+передохн[её]м", r"не\s+торопи", r"не\s+спеши", r"подожди", r"одно\s+дело,?\s+не\s+больше",
         r"хватит\s+предлагать", r"не\s+надо\s+больше\s+предложений", r"сделай\s+паузу", r"давай\s+помедленнее",
         r"не\s+суетись"),
    ),
    "expressiveness": (
        (r"мне\s+страшно", r"я\s+так\s+рад[аи]?", r"я\s+счастлив[аи]?", r"что\s+ты\s+чувствуешь",
         r"расскажи,?\s+что\s+чувствуешь", r"мне\s+больно", r"я\s+в\s+восторге", r"я\s+тронут[аи]?"),
        (r"ответь\s+по\s+существу", r"давай\s+по\s+делу", r"без\s+эмоций", r"спокойно,?\s+по\s+делу",
         r"не\s+драматизируй", r"ровнее", r"без\s+лишних\s+эмоций", r"по\s+существу,?\s+пожалуйста"),
    ),
    "diligence": (
        (r"проверь", r"перепроверь", r"сверь", r"выверь", r"не\s+забудь", r"напомни\s+мне\s+потом",
         r"проследи", r"убедись,?\s+что"),
        (r"достаточно", r"и\s+так\s+сойд[её]т", r"не\s+заморачивайся", r"черновик\s+сойд[её]т",
         r"как\s+есть", r"не\s+надо\s+идеально", r"не\s+проверяй", r"быстро,?\s+не\s+проверяй", r"сойд[её]т\s+и\s+так"),
    ),
    "directness": (
        (r"скажи\s+(?:честно|прямо)", r"не\s+смягчай", r"как\s+есть,?\s+без\s+прикрас", r"тво[её]\s+честное\s+мнение",
         r"что\s+(?:ты\s+)?думаешь\s+на\s+самом\s+деле", r"честно\??", r"без\s+обиняков", r"говори\s+прямо"),
        (r"это\s+было\s+резко", r"ты\s+меня\s+задел[аи]?", r"помягче", r"аккуратнее\s+в\s+словах",
         r"(?:мне\s+)?обидно", r"не\s+руби", r"выбирай\s+слова", r"это\s+грубо"),
    ),
}

_COMPILED: dict[str, tuple[list[re.Pattern], list[re.Pattern]]] = {
    axis: ([re.compile(r"(?<!\w)" + p + r"(?!\w)", re.IGNORECASE) for p in ups],
           [re.compile(r"(?<!\w)" + p + r"(?!\w)", re.IGNORECASE) for p in downs])
    for axis, (ups, downs) in _PATTERNS.items()
}

_HONEST_FRAME_RX = re.compile(r"(?:скажи|ответь|говори)[^.!?\n]{0,30}честно|честно\s*\?", re.IGNORECASE)


def _quote(text: str, m: re.Match, width: int = 60) -> str:
    a = max(0, m.start() - width // 3)
    b = min(len(text), m.end() + width)
    q = text[a:b].strip().replace("\n", " ")
    return ("…" if a > 0 else "") + q + ("…" if b < len(text) else "")


def detect_axis_stimuli(message: str) -> list[dict]:
    msg = (message or "").strip()
    if not msg:
        return []
    out: list[dict] = []
    for axis, (ups, downs) in _COMPILED.items():
        hit = None
        for d, pats in ((1, ups), (-1, downs)):
            for rx in pats:
                m = rx.search(msg)
                if not m:
                    continue
                if axis == "directness" and d == 1 and m.group(0).lower().strip("?") == "честно" \
                        and not _HONEST_FRAME_RX.search(msg):
                    continue
                hit = {"axis": axis, "dir": d, "quote": _quote(msg, m)}
                break
            if hit:
                break
        if hit:
            out.append(hit)
    return out


def record_axis_stimuli(identity, message: str) -> list[dict]:
    found = detect_axis_stimuli(message)
    if not found:
        return []
    lst = getattr(identity, "axis_stimuli", None)
    if lst is None:
        identity.axis_stimuli = lst = []
    now = time.time()
    for f in found:
        lst.append({**f, "ts": now})
    if len(lst) > STIMULI_CAP:
        del lst[:-STIMULI_CAP]
    return found


def session_stimuli(identity) -> list[dict]:
    now = time.time()
    lst = getattr(identity, "axis_stimuli", None) or []
    return [s for s in lst if now - float(s.get("ts") or now) <= STIMULI_TTL_SEC]


def clear_session_stimuli(identity) -> None:
    identity.axis_stimuli = []


def stimulated_dirs(identity) -> dict[str, set[int]]:
    out: dict[str, set[int]] = {}
    for s in session_stimuli(identity):
        try:
            d = int(s.get("dir", 0))
        except (TypeError, ValueError):
            continue
        if d:
            out.setdefault(str(s.get("axis")), set()).add(1 if d > 0 else -1)
    return out


def render_session_stimuli(identity) -> str:
    lines = []
    for s in session_stimuli(identity):
        arrow = "к верхнему полюсу" if int(s.get("dir", 0)) > 0 else "к нижнему полюсу"
        lines.append(f"- {s.get('axis')} ({arrow}): «{s.get('quote', '')}»")
    return "\n".join(lines) if lines else "(механически ничего не замечено — ищи стимулы в рефлексиях сама)"
