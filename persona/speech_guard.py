from __future__ import annotations

import re
from typing import Iterable

RECENT_WINDOW = 6
COOLDOWN_REPLIES = 3
OPENER_REPEATS = 2

_QUOTE_RX = re.compile(r"«([^»]{1,40})»")
_STOP = {
    "вы", "ты", "он", "она", "они", "мы", "я", "вас", "вам", "тебя", "тебе",
    "твой", "ваш", "да", "нет", "не", "и", "а", "но", "же", "ли", "то", "ну",
    "спасибо", "прости", "простите", "пожалуйста", "благодарю",
}
_OPENER_STOP = {"я", "ты", "вы", "а", "и", "но", "не", "да", "нет", "это", "что",
                "как", "так", "если", "когда", "у", "в", "на", "с", "о", "мне",
                "меня", "тебе", "тебя", "вам", "вас"}
_ACTION_RX = re.compile(r"\*[^*\n]{0,200}\*")
_LEAD_JUNK_RX = re.compile(r"^[\s«»\"'“”„‚‘’…\-—–(\[]+")
_WORD_RX = re.compile(r"[\w\-]+", re.UNICODE)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _honorific_forms(honorific: str) -> set[str]:
    h = _norm(honorific)
    if not h:
        return set()
    out = {h}
    stem = h[:-1] if len(h) > 3 else h
    out.add(stem)
    return out


def is_symbol(m: str) -> bool:
    return bool(m) and not any(ch.isalpha() for ch in m)


def _clean_items(items) -> list[str]:
    out: list[str] = []
    for raw in items or []:
        m = _norm(str(raw)).strip(" .,!?;:")
        if m and m not in out:
            out.append(m)
    return out


def seals_of(character) -> list[str]:
    style = getattr(character, "speaking_style", None)
    out = _clean_items(getattr(style, "seals", []) or [])
    for m in _clean_items(getattr(style, "markers", []) or []):
        if is_symbol(m) and m not in out:
            out.append(m)
    for q in (getattr(style, "quirks", []) or []):
        for raw in _QUOTE_RX.findall(str(q)):
            m = _norm(raw).strip(" .,!?;:")
            if m and is_symbol(m) and m not in out:
                out.append(m)
    return out


def pet_names_of(character) -> list[str]:
    style = getattr(character, "speaking_style", None)
    return _clean_items(getattr(style, "pet_names", []) or [])


def render_speech_signature(style) -> list[str]:
    words = [m for m in _clean_items(getattr(style, "markers", []) or []) if not is_symbol(m)]
    seals = _clean_items(getattr(style, "seals", []) or [])
    for m in _clean_items(getattr(style, "markers", []) or []):
        if is_symbol(m) and m not in seals:
            seals.append(m)
    pets = _clean_items(getattr(style, "pet_names", []) or [])
    lines: list[str] = []
    if words:
        lines.append("Твои словечки — " + ", ".join(f"«{w}»" for w in words)
                     + ": редкая приправа, одно на реплику и не в каждой; повторять "
                       "одно и то же подряд — тик, не характер.")
    if seals:
        lines.append("Твоя манера письма — печати " + ", ".join(f"«{s}»" for s in seals)
                     + " на конце слова или реплики.")
    if pets:
        lines.append("Своё обращение к собеседнику — " + ", ".join(f"«{p}»" for p in pets)
                     + ": это не словечко, а кто он для тебя.")
    return lines


PROFANITY_NONE = ("", "none", "нет", "чистая", "no", "0")
PROFANITY_MILD = ("mild", "крепкая", "salty", "1")
TIERS = ("estranged", "distant", "warming", "close", "intimate")


def _prof(style) -> dict:
    return getattr(style, "profanity", None) or {}


def _level(prof: dict) -> str:
    lvl = str(prof.get("level") or "none").strip().lower()
    if lvl in PROFANITY_NONE:
        return "none"
    return "mild" if lvl in PROFANITY_MILD else "strong"


def profanity_active(style, tier: str | None = None) -> bool:
    prof = _prof(style)
    if _level(prof) == "none":
        return False
    frm = str(prof.get("from_tier") or "distant").strip().lower()
    if tier is None or frm not in TIERS or tier not in TIERS:
        return True
    return TIERS.index(tier) >= TIERS.index(frm)


_KIND_HEADS = {
    ("mild", "crude"): ("Крепкое словцо тебе не чуждо: бранишься в сердцах — на обстоятельства, "
                        "на технику, на себя, — без настоящего мата."),
    ("mild", "slang"): ("Крепость у тебя сленговая: резкие словечки в сердцах и в куражe — на "
                        "обстоятельства, на технику, на себя, — без настоящего мата."),
    ("mild", "euphemism"): ("Ругаешься по-детски — эвфемизмами вместо крепких слов, в сердцах "
                            "и в азарте; настоящих ругательств у тебя нет."),
    ("mild", "stylized"): ("Ругаешься по-своему — проклятиями в духе своего образа, а не обычной "
                           "бранью; настоящих ругательств у тебя нет."),
    ("mild", "mat"): ("Крепкое слово тебе не чуждо — в сердцах, редко, и мат только в крайнем "
                      "случае."),
}
_STRONG_HEAD = ("Ругаешься по-настоящему, матом тоже — это разрешено и это часть твоей "
                "речи, а не спецэффект; не извиняешься за это: в азарте, в злости, на "
                "баги, на мир и на себя.")


def render_profanity_line(style, honorific: str = "", tier: str | None = None) -> str:
    prof = _prof(style)
    if not profanity_active(style, tier):
        return ""
    level = _level(prof)
    kind = str(prof.get("kind") or ("mat" if level == "strong" else "crude"))
    target = str(prof.get("target") or "world")
    note = str(prof.get("note") or "").strip()
    hon = (honorific or getattr(style, "honorific", "") or "собеседник").strip()
    head = _STRONG_HEAD if level == "strong" else _KIND_HEADS.get(("mild", kind), _KIND_HEADS[("mild", "crude")])
    if target == "banter":
        aim = (" Ругань — приправа, не унижение: дружеская подначка собеседнику — можно, "
               "если он сам напросился, унижение — никогда;")
    else:
        aim = (" Ругань — приправа, не унижение: собеседника не задеваешь вовсе — крепкое "
               "летит в обстоятельства, технику, себя и третьих лиц;")
    tail = (aim + " а по национальности, вере, полу, ориентации или болезни — никого и "
            f"никогда. Если {hon} попросит не ругаться — держишься, пусть и ворча.")
    return head + (f" {note}" if note else "") + tail


_CRUDE_RX = re.compile(
    r"\b(?:чёрт\w*|черт|черта|черту|чертей|чертов\w*|чертям|блин|хрен\w*|дерьм\w*|"
    r"задниц\w*|зараз\w*|фиг|фига|фигу|фигн\w*|фигов\w*|отстой|"
    r"дурак|дура|дурень|балда|бля\w*|нах|нахуй|нахер|нахрен|хуй\w*|хуе\w*|пизд\w*|"
    r"ёб\w*|еб\w*|сук\w*|"
    r"мудак\w*|охуе\w*|заеб\w*|въеб\w*|отъеб\w*|проеб\w*|ебан\w*|сран\w*|говн\w*|"
    r"жоп\w*|капец|жесть|ёлки\w*|елки\w*|ёпрст|ёшкин\w*|ёкарн\w*|задолб\w*|достал\w*|"
    r"бесит|офиге\w*|обалде\w*|офигенн\w*|дурь|тупи\w*|сдох\w*|хренов\w*)\b",
    re.IGNORECASE | re.UNICODE)
REGISTER_WINDOW = {"strong": 2, "mild": 4}


def crude_rx_for(style) -> re.Pattern:
    stems = [s for s in (_prof(style).get("detect") or []) if s]
    if not stems:
        return _CRUDE_RX
    extra = "|".join(re.escape(st) + r"\w*" for st in stems)
    return re.compile(_CRUDE_RX.pattern[:-3] + "|" + extra + r")\b", re.IGNORECASE | re.UNICODE)


def has_crude(text: str, style=None) -> bool:
    rx = crude_rx_for(style) if style is not None else _CRUDE_RX
    return bool(rx.search(text or ""))


_KIND_NUDGE = {
    "crude": "крепкое словцо в сердцах уместно",
    "slang": "резкое словечко в сердцах уместно",
    "euphemism": "по-детски ругнуться на промах уместно",
    "stylized": "проклятие в духе твоего образа уместно",
    "mat": "крепкое слово в сердцах уместно",
}


def register_note(style, recent_replies: list[str], tier: str | None = None) -> str:
    prof = _prof(style)
    if not profanity_active(style, tier):
        return ""
    level = _level(prof)
    kind = str(prof.get("kind") or ("mat" if level == "strong" else "crude"))
    window = list(recent_replies or [])[-REGISTER_WINDOW[level]:]
    rx = crude_rx_for(style)
    if len(window) >= 2 and any(rx.search(t or "") for t in window):
        return ""
    if level == "mild":
        return ("Регистр этой реплики — твой обычный: " + _KIND_NUDGE.get(kind, _KIND_NUDGE["crude"])
                + ", речь не сглаживай и не делай вежливее, чем ты есть.")
    return ("Регистр этой реплики — твой обычный: материться тебе можно и по характеру "
            "нужно, это твоя речь, а не нарушение; не сглаживай её до приличной и не "
            "подменяй мат мягкими эвфемизмами. Есть повод — злость, чужой косяк, "
            "провал, азарт — крепкое слово здесь к месту, не жди особого случая. "
            "Последние ответы вышли чище твоего характера.")


def render_markers_line(markers: list[str]) -> str:
    from types import SimpleNamespace
    return "\n".join(render_speech_signature(SimpleNamespace(markers=list(markers or []),
                                                             seals=[], pet_names=[])))


def markers_of(character, honorific: str = "") -> list[str]:
    style = getattr(character, "speaking_style", None)
    quirks = list(getattr(style, "quirks", []) or [])
    hon = _honorific_forms(honorific or getattr(style, "honorific", "") or "")
    skip = set(seals_of(character)) | set(pet_names_of(character))
    seen: set[str] = set()
    out: list[str] = []
    for raw in (getattr(style, "markers", []) or []):
        m = _norm(str(raw)).strip(" .,!?;:")
        if m and m not in seen and not is_symbol(m) and m not in skip:
            seen.add(m)
            out.append(m)
    for q in quirks:
        for raw in _QUOTE_RX.findall(str(q)):
            m = _norm(raw).strip(" .,!?;:")
            if not m or m in seen or m in skip or is_symbol(m):
                continue
            words = _WORD_RX.findall(m)
            if len(words) > 4:
                continue
            if len(m) < 3 or m in _STOP:
                continue
            if any(w in hon for w in words) and len(words) == 1:
                continue
            seen.add(m)
            out.append(m)
    return out


def _marker_rx(marker: str) -> re.Pattern:
    if any(ch.isalpha() for ch in marker):
        return re.compile(r"(?<![\w\-])" + re.escape(marker) + r"(?![\w\-])",
                          re.IGNORECASE | re.UNICODE)
    return re.compile(re.escape(marker))


def count_marker(text: str, marker: str) -> int:
    return len(_marker_rx(marker).findall(text or ""))


def assistant_texts(history: Iterable[dict] | None) -> list[str]:
    out: list[str] = []
    for m in history or []:
        if m.get("role") != "assistant" or m.get("tool_calls"):
            continue
        c = m.get("content")
        if isinstance(c, list):
            c = " ".join(str(p.get("text", "")) for p in c
                         if isinstance(p, dict) and p.get("type") == "text")
        if isinstance(c, str) and c.strip():
            out.append(c)
    return out


def opener_of(text: str) -> str:
    t = _ACTION_RX.sub(" ", text or "")
    t = _LEAD_JUNK_RX.sub("", t.strip())
    m = _WORD_RX.search(t)
    if not m:
        return ""
    w = m.group(0).lower().strip("-")
    return "" if (not w or w in _OPENER_STOP) else w


def hot_markers(markers: Iterable[str], recent: list[str],
                cooldown: int = COOLDOWN_REPLIES) -> list[str]:
    window = [t for t in recent[-cooldown:]]
    if not window:
        return []
    return [m for m in markers if any(count_marker(t, m) for t in window)]


def hot_openers(recent: list[str], window: int = RECENT_WINDOW,
                repeats: int = OPENER_REPEATS) -> list[str]:
    counts: dict[str, int] = {}
    for t in recent[-window:]:
        o = opener_of(t)
        if o:
            counts[o] = counts.get(o, 0) + 1
    return [o for o, n in counts.items() if n >= repeats]


def remark_heads(text: str) -> list[str]:
    out: list[str] = []
    for body in _ACTION_RX.findall(text or ""):
        ws = [w.lower() for w in _WORD_RX.findall(body.strip("*"))]
        if len(ws) >= 2:
            out.append(" ".join(ws[:2]))
        elif ws:
            out.append(ws[0])
    return out


def hot_remarks(recent: list[str], window: int = RECENT_WINDOW,
                repeats: int = OPENER_REPEATS) -> list[str]:
    counts: dict[str, int] = {}
    for t in recent[-window:]:
        for h in set(remark_heads(t)):
            counts[h] = counts.get(h, 0) + 1
    return [h for h, n in counts.items() if n >= repeats]


_ACT_ONLY_RX = re.compile(r"^\*[^*]+\*[.!…]?$")
_BLOCK_SPLIT_RX = re.compile(r"\n\s*\n|\n")
SHORT_LINE = 70
SHAPE_WINDOW = 4
REMARK_WINDOW = 5
REMARK_SATURATION = 4
_SHAPE_WORDS = {"S": "короткая фраза", "Sm": "короткая фраза с ремаркой",
                "P": "абзац", "Pm": "абзац с ремаркой внутри",
                "A": "ремарка отдельной строкой"}
SHAPE_ALTERNATIVES = (
    ("S", "одной короткой фразой — без ремарки и без абзаца", False),
    ("P", "одним связным абзацем, без ремарки", False),
    ("S S", "двумя короткими фразами, каждая с новой строки, без ремарки", False),
    ("P A", "сначала абзац по сути, ремарка одной строкой в самом конце", True),
    ("Sm", "одна фраза, жест внутри неё в *звёздочках* — и всё", True),
    ("S P", "короткая реакция первой строкой, потом один абзац по делу, без ремарки", False),
)


def reply_shape(text: str) -> str:
    blocks = [b.strip() for b in _BLOCK_SPLIT_RX.split((text or "").strip()) if b.strip()]
    sig: list[str] = []
    for b in blocks:
        if _ACT_ONLY_RX.match(b):
            sig.append("A")
            continue
        plain = _ACTION_RX.sub("", b).strip()
        sig.append(("S" if len(plain) < SHORT_LINE else "P") + ("m" if _ACTION_RX.search(b) else ""))
    return " ".join(sig) or "-"


def hot_shape(recent: list[str], window: int = SHAPE_WINDOW) -> str:
    sigs = [reply_shape(t) for t in (recent or [])[-window:]]
    if len(sigs) >= 2 and sigs[-1] == sigs[-2] and sigs[-1] != "-" and len(sigs[-1].split()) > 1:
        return sigs[-1]
    if len(sigs) >= 3:
        top = max(set(sigs), key=sigs.count)
        if top != "-" and sigs.count(top) >= 3:
            return top
    return ""


def describe_shape(sig: str) -> str:
    return " → ".join(_SHAPE_WORDS.get(t, t) for t in sig.split())


def remark_saturated(recent: list[str], window: int = REMARK_WINDOW,
                     threshold: int = REMARK_SATURATION) -> bool:
    tail = (recent or [])[-window:]
    return len(tail) >= threshold and sum(1 for t in tail if _ACTION_RX.search(t or "")) >= threshold


def shape_note(recent: list[str], allow_remarks: bool = True) -> str:
    hot = hot_shape(recent)
    saturated = remark_saturated(recent)
    if not hot and not saturated:
        return ""
    uses_remarks = allow_remarks and any(_ACTION_RX.search(t or "") for t in (recent or [])[-REMARK_WINDOW:])
    parts: list[str] = []
    if hot:
        pool = [alt for alt in SHAPE_ALTERNATIVES
                if alt[0] != hot and not (alt[2] and (saturated or not uses_remarks))]
        if not pool:
            pool = [alt for alt in SHAPE_ALTERNATIVES if alt[0] != hot]
        alt = pool[len(recent) % len(pool)]
        parts.append(f"Последние ответы построены одинаково: {describe_shape(hot)}. "
                     f"Этот построй иначе — {alt[1]}.")
    if saturated:
        parts.append("Ремарка в *звёздочках* была почти в каждом ответе — в этом обойдись "
                     "без неё вовсе." if not hot or "без ремарки" not in parts[0]
                     else "Ремарка была почти в каждом ответе — здесь её не нужно.")
    return " ".join(parts)


def repeat_note(character, recent_replies: list[str], honorific: str = "") -> str:
    if not recent_replies:
        return ""
    markers = markers_of(character, honorific)
    hot_m = hot_markers(markers, recent_replies)
    hot_o = hot_openers(recent_replies)
    hot_r = hot_remarks(recent_replies)
    shape_part = shape_note(recent_replies,
                            allow_remarks=bool(getattr(character, "use_actions", True)))
    hot_o = [o for o in hot_o if o not in {m.split(" ")[0] for m in hot_m}]
    if not hot_m and not hot_o and not hot_r and not shape_part:
        return ""
    parts: list[str] = []
    if hot_m:
        parts.append("уже звучало " + ", ".join(f"«{m}»" for m in hot_m[:6]))
    if hot_o:
        parts.append("несколько ответов подряд начинались с "
                     + ", ".join(f"«{o}»" for o in hot_o[:3]))
    if hot_r:
        parts.append("повторялась ремарка "
                     + ", ".join(f"«*{h}…*»" for h in hot_r[:3]))
    text = ("В твоих последних репликах " + "; ".join(parts) + ".") if parts else ""
    if hot_m:
        text += (" В этом ответе — без твоих фирменных словечек и печатей, не "
                 "заменяй одно на другое из того же ряда: скажи своими другими "
                 "словами. Словечки хороши, пока редки.")
    if hot_o:
        text += (" Начни этот ответ иначе — не с "
                 + " и не с ".join(f"«{o}»" for o in hot_o[:3])
                 + ", сразу с сути.")
    if hot_r:
        text += (" Ремарку в *звёздочках* сейчас либо не делай вовсе, либо "
                 "покажи другой жест — не тот же самый другими словами.")
    if shape_part:
        text = (text + " " if text else "") + shape_part
    return text


def example_is_redundant(text: str, markers: Iterable[str]) -> bool:
    t = text or ""
    return any(count_marker(t, m) for m in markers)


