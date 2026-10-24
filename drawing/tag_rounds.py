from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from drawing import zones
from drawing.assets import RATING_ORDER
from app_paths import ASSETS_ROOT

_ROOT = ASSETS_ROOT
_TAGMAP = _ROOT / "drawing" / "danbooru_tags" / "tag_map.json"

FRAMING_TAG_LEVEL = {
    "close-up": "face",
    "portrait": "head_shoulders",
    "upper body": "upper_body",
    "cowboy shot": "cowboy",
    "full body": "full",
    "wide shot": "full",
    "very wide shot": "full",
}

FRAMING_HEADLESS: dict[str, tuple[str, str]] = {
    "lower body": ("full", "cowboy"),
    "legs": ("full", "cowboy"),
    "feet": ("full", "full"),
}

HEAD_OUT_TAG = "head out of frame"

FRAMING_FOCUS: dict[str, str] = {
    "leg focus": "full body",
    "feet focus": "full body",
    "foot focus": "full body",
    "thigh focus": "cowboy shot",
    "hip focus": "cowboy shot",
    "ass focus": "cowboy shot",
    "pussy focus": "cowboy shot",
    "back focus": "upper body",
    "breast focus": "upper body",
    "hand focus": "upper body",
    "armpit focus": "upper body",
}


_FRAME_OF_LEVEL = {"face": "close-up", "head_shoulders": "portrait",
                   "upper_body": "upper body", "cowboy": "cowboy shot",
                   "full": "full body"}


def _is_framing(tag: str | None) -> bool:
    return bool(tag) and (tag in FRAMING_TAG_LEVEL or tag in FRAMING_HEADLESS)


def _framing_level_of(tag: str) -> tuple[str | None, str | None, bool]:
    if tag in FRAMING_TAG_LEVEL:
        return FRAMING_TAG_LEVEL[tag], None, False
    if tag in FRAMING_HEADLESS:
        lvl, flr = FRAMING_HEADLESS[tag]
        return lvl, flr, True
    return None, None, False


_FRAMING_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("feet", ("крупным планом ступни", "кадр на ступни", "кадр на стопы",
              "только ступни", "одни ступни")),
    ("lower body", ("только ноги", "одни ноги", "кадр на ноги",
                    "крупным планом ноги", "нижняя часть тела",
                    "от пояса и ниже", "lower body", "legs only")),
    ("full body", ("полный рост", "во весь рост", "целиком", "с ног до головы",
                   "с головы до ног", "всю фигуру", "full body", "full-body", "fullbody")),
    ("cowboy shot", ("по бёдра", "по бедра", "ковбойск", "cowboy")),
    ("upper body", ("по пояс", "до пояса", "поясной", "по грудь", "upper body")),
    ("portrait", ("портрет", "по плечи", "плечи и голова", "голова и плечи", "portrait")),
    ("close-up", ("крупн", "вблизи", "close-up", "close up", "closeup", "макросъ")),
]

_FOCUS_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("feet focus", ("ступн", "стопы", "стопа", "пальцы ног", "пятк",
                    "feet focus", "foot focus")),
    ("pussy focus", ("лобк", "лобок", "половых губ", "половые губ", "киск", "промежн",
                     "клитор", "pussy focus")),
    ("thigh focus", ("бедр", "бёдр", "ляжк", "thigh focus")),
    ("ass focus", ("попк", "попой", "ягодиц", "задниц", "ass focus")),
    ("leg focus", ("ножк", "ножек", "ноги в кадре", "ноги в кадр", " ног", "leg focus")),
    ("breast focus", ("груд", "бюст", "breast focus")),
    ("back focus", ("спин", "back focus")),
    ("hand focus", (" рук", "ладон", "кист", "пальц", "hand focus")),
]


_LOWER_PART_RE = re.compile(
    r"\bног(?:[иаеуяойм]|\b)|\bножк|\bножек|\bступн|\bстопы|\bстопа|\bпятк|пальц\w* ног"
    r"|\bб[её]др|\bляжк|\bягодиц|\bпопк|\bпопу\b"
    r"|\bлоб(?:ок|ка|ке|ком)\b|половы\w* губ|\bкиск|\bпромежн|\bпах(?:а|у|е)?\b|\bклитор"
    r"|\bвагин|\bвульв", re.I)
_FEET_RE = re.compile(r"\bступн|\bстопы|\bстопа|\bпятк|пальц\w* ног", re.I)

_LOWER_NEAR_RE = re.compile(
    r"колен|лодыж|щиколот|туфл|туфел|обув|сапог|ботин|кроссов|чулк|чулок|колгот")
_SHOES_RE = re.compile(r"туфл|туфел|обув|сапог|ботин|кроссов")
_OTHER_PART_RE = re.compile(
    r"ше[яиюей]$|шейк|ключиц|плеч|локот|локт|подмыш|хвост|ожерел|кулон|колье|чокер"
    r"|браслет|кольц|перчат|манжет|бант|ворот|пояс|юбк|подол|фартук|корсет|бель[её]$"
    r"|трусик|лифчик|татуир|тату$|родинк|шрам")
_NEAR_SIGNALS = ("крупн", "вблизи", "поближе", "макро", "close", "только", "лишь", "одни")


def _near_part(t: str, part_re: re.Pattern) -> str | None:
    for c in _clauses(t):
        if _FACE_WORDS_RE.search(c) and not _NO_FACE_RE.search(c):
            continue
        toks = re.findall(r"[\w-]+|,", c.lower())
        sig = [i for i, w in enumerate(toks) if w.startswith(_NEAR_SIGNALS)]
        for j, w in enumerate(toks):
            if w == "," or not part_re.match(w):
                continue
            for i in sig:
                lo, hi = sorted((i, j))
                if hi - lo <= 3 and "," not in toks[lo:hi]:
                    return w
    return None
_CROP_SIGNALS = ("крупн", "только", "лишь ", "вблизи", "поближе", "одни ", "остальное скрыт",
                 "ничего лишн", "focus", "макро", "close")
HEADLESS_TORSO = "torso"
HEADLESS_TORSO_BAND = ("upper_body", "head_shoulders")
_UPPER_PART_RE = re.compile(
    r"\bгруд|\bбюст|\bрук[иуа]?\b|\bрукам|\bладон|\bкист[ьи]|\bпальц(?!\w*\s+ног)|маникюр"
    r"|\bногт|\bспин[уаые]|\bживот|\bталия|\bталию|\bпупок|\bпупк|\bдекольте"
    r"|\bсос(?:ок|ки|ков|кам|ками|ках)\b|\bареол", re.I)
_NO_FACE_RE = re.compile(
    r"без\s+(?:лица|головы)|лиц\w*\s+(?:можно\s+)?не\s+(?:показ|нужн|видн|над)"
    r"|не\s+показ\w*\s+лиц|голов\w*\s+(?:можно\s+)?не\s+(?:показ|нужн)", re.I)
_FACE_WORDS_RE = re.compile(r"\bлиц[оаеу]\b|\bглаз|\bулыб|\bвзгляд"
                            r"|(?<!половых )(?<!половые )(?<!половыми )\bгуб[аыу]?\b", re.I)


_SIZE_ADJ_RX = re.compile(r"крупн(?!о\b|ее\b|\w*\s+план)\w*")


def _no_size_adj(t: str) -> str:
    return _SIZE_ADJ_RX.sub("большой", t)


def _clauses(t: str) -> list[str]:
    return [f" {c} " for c in re.split(r"[.;:!?—\n]", t) if c.strip()]


_BARE_CROP_RX = re.compile(r"крупн\w*\s+план|\bкрупно\b|close-?up|\bмакро")
_FOCUS_ON_RX = re.compile(r"фокус|акцент|в центре внимания")


def _bare_crop(t: str) -> bool:
    return not _FACE_WORDS_RE.search(t) and any(
        _BARE_CROP_RX.search(c) and not _LOWER_PART_RE.search(c)
        and not _UPPER_PART_RE.search(c) for c in _clauses(t))


def _crop_part(t: str, part_re: re.Pattern) -> bool:
    no_face = bool(_NO_FACE_RE.search(t))
    bare = _bare_crop(t)
    for c in _clauses(t):
        if not part_re.search(c):
            continue
        if _FACE_WORDS_RE.search(c) and not _NO_FACE_RE.search(c):
            continue
        if bare and _FOCUS_ON_RX.search(c):
            return True
        if no_face or any(s in c for s in _CROP_SIGNALS):
            return True
    return False


def headless_asked(text: str | None) -> bool:
    t = _no_size_adj((text or "").lower())
    if not t:
        return False
    if _crop_part(t, _LOWER_PART_RE) or _near_part(t, _LOWER_NEAR_RE):
        return True
    return any(_LOWER_PART_RE.search(c) and any(s in c for s in _FOCUS_SIGNALS)
               and not _FACE_WORDS_RE.search(c) for c in _clauses(t))


_BAND_STATE_TAGS = frozenset({
    "nude", "completely nude", "underwear only", "topless female", "topless male",
    "bottomless", "no bra", "no panties", "breasts out", "naked apron", "naked towel",
    "naked shirt", "naked ribbon", "naked sheet"})


def band_exempt(tag: str) -> bool:
    t = (tag or "").lower()
    return t.endswith(" focus") or "nail" in t or t in _BAND_STATE_TAGS


def detect_framing(text: str | None) -> str | None:
    if not text:
        return None
    t = _no_size_adj(text.lower())
    if _crop_part(t, _LOWER_PART_RE):
        return "feet" if _FEET_RE.search(t) else "lower body"
    near_low = _near_part(t, _LOWER_NEAR_RE)
    if near_low:
        return "feet" if _SHOES_RE.match(near_low) else "lower body"
    if _crop_part(t, _UPPER_PART_RE):
        return HEADLESS_TORSO
    if _near_part(t, _OTHER_PART_RE):
        return None
    if any(s in t for s in _CROP_SIGNALS) and detect_focus(t):
        return None
    for tag, kws in _FRAMING_KEYWORDS:
        if any(k in t for k in kws):
            return tag
    return None


def detect_focus(text: str | None) -> str | None:
    if not text:
        return None
    for clause in re.split(r"[.,;:!?—\n]", _no_size_adj(text.lower())):
        c = f" {clause} "
        if not any(s in c for s in _FOCUS_SIGNALS):
            continue
        for tag, kws in _FOCUS_KEYWORDS:
            if any(k in c for k in kws):
                return tag
    return None


_FOCUS_SIGNALS = ("крупн", "акцент", "фокус", "focus", "подчеркн", "покаж", "показ",
                  "в кадре", "в кадр", "макро", "вблизи", "только ", "лишь ",
                  "сфот", "сним", "любу")


_HAIR_DOWN_KEYWORDS = ("распущен", "распусти", "распустив", "hair down")


def detect_hair_down(text: str | None) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in _HAIR_DOWN_KEYWORDS)


_I_NUDE_RX = re.compile(
    r"без (?:одежды|всего(?! лишн)|ничего)|\b(?:обнаж[её]нн(?:ая|ой|ую)|обнажена"
    r"|голышом|нагишом|нагая|нагой|догола)\b"
    r"|\b(?:совсем|полностью|совершенно) (?:голая|голой|раздета|обнажена)\b"
    r"|\bголая\b(?! (?:спин|кож|ног|рук|плеч|ше))"
    r"|\bнет (?:никакой |ни )?одежды|\bни (?:одной )?нитки|\bничего (?:нет|не надето)\b")
_I_PANTIES_ONLY_RX = re.compile(r"\b(?:только|одни|одних|лишь) (?:\w+ ){0,2}трусик")
_I_BREASTS_OUT_RX = re.compile(
    r"груд\w*\s+(?:\w+\s+)?(?:открыт|обнаж|оголен|наружу|голая|выставлен)"
    r"|(?:открыв|открыл|обнаж|оголи|оголя|выпуст|вывали|высвобод)\w*\s+(?:\w+\s+)?грудь"
    r"|открытой грудью|\bтоплес|\btopless|breasts out")
_I_WORN = (
    (re.compile(r"трусик"), "panties"),
    (re.compile(r"стринг"), "thong"),
    (re.compile(r"лифчик|бюстгальтер"), "bra"),
    (re.compile(r"сорочк|ночнушк|ночной рубашк"), "nightgown"),
    (re.compile(r"пеньюар|неглиже"), "negligee"),
)
_I_SAME = {"nude": {"nude", "completely nude"}, "panties": {"panties", "thong"},
           "thong": {"thong"}, "bra": {"bra", "cupless bra"},
           "nightgown": {"nightgown", "negligee", "babydoll", "chemise"},
           "negligee": {"negligee", "nightgown", "babydoll"},
           "breasts out": {"breasts out", "topless", "topless female"},
           "topless": {"topless", "topless female", "breasts out"}}
BREAST_BARE_TAGS = frozenset({"breast slip", "breasts out", "nipple slip", "one breast out",
                              "topless", "topless female", "nipples", "areolae",
                              "areola slip"})
_I_BREASTS_RX = re.compile(
    r"груд|сос(?:ок|ки|ков|кам)|ареол|топлес|без (?:лифчик|бюстгальтер|верха)"
    r"|(?:снял|снима|стянул)\w* (?:лифчик|бюстгальтер|верх)|под \w+ ничего|ничего под"
    r"|без белья|topless|nipple|breast")


LIFT_TAGS = frozenset({"skirt lift", "dress lift", "clothes lift", "pantyshot", "upskirt"})
_I_UNDER_RX = re.compile(r"трусик|бель(?:[её]|я|ём)|стринг|panties|pantyshot|upskirt|ягодиц|попк")
_I_SOFT_LIFT_RX = re.compile(r"\b(?:чуть|немного|слегка|едва)\b|колен")
_I_WEARS_UNDER_RX = re.compile(
    r"\bв (?:\w+ ){0,2}(?:бель(?:е|ё)|сорочк|ночнушк|ночной рубашк|пеньюар|неглиже|трусик)"
    r"|на мне (?:только |лишь |одн\w+ )?(?:\w+ ){0,2}(?:бель(?:е|ё)|сорочк|ночнушк|пеньюар"
    r"|неглиже|трусик|комплект)")


_POSE_PHRASES: tuple[tuple[re.Pattern, str, frozenset], ...] = (
    (re.compile(r"колен\w*\s+(?:плотно\s+)?(?:сведен|вместе|сдвинут|сжат)"
                r"|(?:свед|сдвинув|сжав|сомкн)\w*\s+колен"),
     "legs together", frozenset({"legs apart", "spread legs", "knees apart feet together"})),
)
_COVER_PHRASES: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"(?:прикры|закры|прячу|пряча)\w*\s+(?:\w+\s+){0,2}груд"), "covering breasts"),
    (re.compile(r"(?:прикры|закры|прячу|пряча)\w*\s+(?:\w+\s+){0,2}(?:низ|пах|лобок|между\s+ног)"),
     "covering crotch"),
)


_I_ACT_STRONG_RX = re.compile(r"ласка\w* себя|мастурб|удовлетвор\w* себя|трога\w* себя"
                              r"|довод\w* себя|себя ласк")
_I_ACT_HAND_RX = re.compile(r"(?:рук|ладон|пальц)\w*\s+(?:\w+\s+){0,3}?(?:между (?:ног|бёдер|бедер)"
                            r"|под (?:ткань|бель|трусик)|скользнул\w* под"
                            r"|к (?:самому )?центру|к низу живота|вниз по животу)")
_I_ACT_CONTEXT_RX = re.compile(r"тяжело дыш|стон|возбужд|влажн|томн|сладк|жар|дрож"
                               r"|без одежды|обнаж|голая|голой|в (?:одном )?бель|трусик")
_I_UNDER_FABRIC_RX = re.compile(r"под (?:ткань|бель|трусик)|скользнул\w* под")
_I_OVER_FABRIC_RX = re.compile(r"поверх (?:одежды|ткани|белья|трусик|юбк|плать)")
_I_FINGERS_RX = re.compile(r"пальц\w* (?:внутр|между ног|в себ)")
_I_TOYS = (
    (re.compile(r"вибратор"), "vibrator"),
    (re.compile(r"дилдо|фаллоимитатор"), "dildo"),
)
_I_TOY_RX = re.compile(r"игрушк")
_I_TOPLESS_RX = re.compile(r"без (?:верха|лифчика|бюстгальтера)|\bтоплес")
_I_GRAB_BREAST_RX = re.compile(r"(?:сжима|мн[уё]|тиска|ласка)\w* (?:себе |свою |свои )?груд")
_I_PANTIES_ASIDE_RX = re.compile(r"отодвига\w* (?:\w+ ){0,2}(?:трусик|бель)")
_STUFFED = frozenset({"stuffed toy", "holding stuffed toy", "stuffed animal", "teddy bear"})


def intent_act_tags(intent: str | None) -> list[str]:
    low = (intent or "").lower().replace("ё", "е")
    out: list[str] = []
    hand = bool(_I_ACT_HAND_RX.search(low))
    act = bool(_I_ACT_STRONG_RX.search(low)) or (hand and bool(_I_ACT_CONTEXT_RX.search(low)))
    toy_named = [tag for rx, tag in _I_TOYS if rx.search(low)]
    if _I_TOY_RX.search(low) and (act or hand):
        toy_named = toy_named or ["sex toy"]
    if act or toy_named:
        if _I_OVER_FABRIC_RX.search(low):
            out.append("masturbation through clothes")
        elif _I_UNDER_FABRIC_RX.search(low):
            out += ["masturbation", "hand in own panties"]
        else:
            out.append("masturbation")
        if _I_FINGERS_RX.search(low):
            out.append("fingering")
        out += toy_named
    if _I_TOPLESS_RX.search(low):
        out.append("topless")
    if _I_GRAB_BREAST_RX.search(low):
        out.append("grabbing own breast")
    if _I_PANTIES_ASIDE_RX.search(low):
        out.append("panties aside")
    return list(dict.fromkeys(out))


def apply_intent_acts(tags: list[str], intent: str | None) -> tuple[list[str], list[str]]:
    add = [t for t in intent_act_tags(intent) if t not in tags]
    out = list(tags) + add
    if {"sex toy", "vibrator", "dildo"} & set(out):
        out = [t for t in out if t not in _STUFFED]
    return out, add


def apply_intent_details(tags: list[str], intent: str | None, *, allow_nsfw: bool
                         ) -> tuple[list[str], list[str]]:
    low = (intent or "").lower()
    out, added = list(tags), []
    for rx, tag, opposite in _POSE_PHRASES:
        if rx.search(low) and tag not in out:
            out = [t for t in out if t not in opposite] + [tag]
            added.append(tag)
    if allow_nsfw:
        for rx, tag in _COVER_PHRASES:
            if rx.search(low) and tag not in out:
                out.append(tag)
                added.append(tag)
    return out, added


_TUG_TAGS = frozenset({"skirt tug", "dress tug"})


def drop_lift_tug(tags: list[str]) -> list[str]:
    if not set(tags) & LIFT_TAGS:
        return list(tags)
    return [t for t in tags if t not in _TUG_TAGS]


_I_DRESSED_RX = re.compile(
    r"\bоде(?:лась|лся|ла|л|та|т|ваюсь|ваю|вается|нь|вшись)\b|\bнадела|\bнадел\b|\bнадеваю"
    r"|\bнакину|\bнакидыва"
    r"|\b(?:в|во|свою|своей|мою|моей|эту|этой|ту|той)\s+форм[аеуыо]?\b|\bформ\w*\s+горнич"
    r"|\bуниформ|\bнаряд|\bплать|\bфартук|\bпередник|\bкимоно|\bрубашк|\bблузк|\bюбк"
    r"|\bбрюк|\bштан|\bжилет|\bпиджак|\bкуртк|\bхалат|\bсвитер|\bзаст[её]г")


def intent_dressed(intent: str | None) -> bool:
    return bool(_I_DRESSED_RX.search((intent or "").lower()))


def intent_wears_underwear(intent: str | None) -> bool:
    return bool(_I_WEARS_UNDER_RX.search((intent or "").lower()))


_I_GENITAL_RX = re.compile(r"половы\w* губ|\bлоб(?:ок|ка|ке|ком)\b|\bкиск|\bклитор|\bвагин"
                           r"|\bвульв|\bпромежн")
_I_UNDER_ON_RX = re.compile(r"трусик|стринг|бель(?:[её]|я|ём)|panties|сквозь|через ткань")


def intent_state_tags(intent: str | None, guess: bool = True) -> tuple[list[str], bool]:
    low = (intent or "").lower()
    add: list[str] = []
    nude = bool(_I_NUDE_RX.search(low))
    panties_only = bool(_I_PANTIES_ONLY_RX.search(low))
    if nude:
        add.append("nude")
    elif guess and _I_GENITAL_RX.search(low) and not _I_UNDER_ON_RX.search(low):
        add.append("bottomless")
    if not nude:
        if panties_only:
            add += ["topless", "panties"]
        for rx, tag in _I_WORN:
            m = rx.search(low)
            if m and not re.search(r"без\s+(?:\w+\s+)?$", low[:m.start()]) and tag not in add:
                add.append(tag)
        if _I_BREASTS_OUT_RX.search(low) and "topless" not in add:
            add.append("breasts out")
    breasts_ok = nude or panties_only or bool(_I_BREASTS_RX.search(low))
    return add, breasts_ok


def gendered_topless(tags: list[str], appearance_tags=()) -> list[str]:
    male = "1boy" in {zones._norm(t) for t in appearance_tags or ()}
    real = "topless male" if male else "topless female"
    out: list[str] = []
    for t in tags:
        t = real if t == "topless" else t
        if t not in out:
            out.append(t)
    return out


_FEMALE_ONLY_ACTS = frozenset({"fingering", "clitoral stimulation", "spread pussy",
                               "vaginal object insertion", "female masturbation"})


def gendered_acts(tags: list[str], appearance_tags=()) -> list[str]:
    male = "1boy" in {zones._norm(t) for t in appearance_tags or ()}
    out: list[str] = []
    for t in tags:
        if male:
            if t in _FEMALE_ONLY_ACTS:
                continue
            t = "male masturbation" if t == "masturbation" else t
        elif t == "male masturbation":
            t = "masturbation"
        if t not in out:
            out.append(t)
    if not male and "masturbation" in out and "female masturbation" not in out:
        out.insert(out.index("masturbation") + 1, "female masturbation")
    return out


def apply_intent_state(tags: list[str], intent: str | None) -> tuple[list[str], list[str], list[str]]:
    add, breasts_ok = intent_state_tags(intent)
    have = set(tags)
    added = [t for t in add if not have & _I_SAME.get(t, {t})]
    out = list(tags) + added
    dropped: list[str] = []
    if not breasts_ok:
        dropped = [t for t in out if t in BREAST_BARE_TAGS]
        out = [t for t in out if t not in BREAST_BARE_TAGS]
    low = (intent or "").lower()
    if (not _I_UNDER_RX.search(low) and not _I_NUDE_RX.search(low)
            and _I_SOFT_LIFT_RX.search(low)):
        dropped += [t for t in out if t in LIFT_TAGS]
        out = [t for t in out if t not in LIFT_TAGS]
    return out, added, dropped

DOMAIN_GROUPS = {
    "location": ["locations"],
    "background": ["backgrounds"],
    "lighting": ["lighting"],
    "weather": ["water", "fire"],
    "scene": ["locations", "backgrounds", "lighting", "water", "fire"],
    "pose": ["posture"],
    "gesture": ["gestures"],
    "props": ["holding", "objects", "accessories"],
    "food": ["food_tags"],
}


def parse_exclude(entries) -> tuple[set[str], set[str], set[str]]:
    groups: set[str] = set()
    tags: set[str] = set()
    labels: set[str] = set()
    for e in entries or ():
        e = str(e).strip().lower()
        if not e:
            continue
        if e.startswith("tag:"):
            tags.add(e[4:].strip())
        elif e.startswith("label:"):
            labels.add(e[6:].strip())
        else:
            groups.update(DOMAIN_GROUPS.get(e, [e]))
    return groups, tags, labels


@dataclass
class Round:
    key: str
    title: str
    instruct: str
    groups: list[str]
    cap: int
    min_zone: str | None = None
    min_rating: str = "sfw"
    mood: bool = False


ROUNDS: list[Round] = [
    Round("framing", "кадр и ракурс",
          "ОБЯЗАТЕЛЬНО выбери ОДИН crop-тег. ПО УМОЛЧАНИЮ бери ТЕСНЫЙ кадр — "
          "close-up (лицо) или portrait (голова и плечи): модель лучше всего "
          "рисует крупные планы, дальние выходят плохо. Шире (upper body / "
          "cowboy shot / full body) бери ТОЛЬКО если запрос этого явно требует: "
          "полный рост, действие телом/руками, реквизит в руках или акцент на "
          "окружении. При нужде добавь ОДИН ракурс — для портрета предпочитай "
          "«three-quarter view» (3/4), он выгоднее плоского «from side»/профиля.",
          ["image_composition/framing", "image_composition/view_angle"], cap=2),
    Round("scene", "фон и свет",
          "Фон + освещение/время суток под запрос. Конкретное место (комната, "
          "улица, здание) не задаётся.",
          ["backgrounds", "lighting", "water", "fire"], cap=5,
          min_zone="upper_body"),
    Round("pose", "поза и действие",
          "Положение тела и действие. НЕ выбирай противоречивые (стоит И лежит).",
          ["posture", "activities"], cap=4, mood=True),
    Round("exposure", "обнажённость",
          "Уровень раздетости персонажа под запрос: от белья / просвечивающей "
          "одежды до полной наготы, плюс видимые части тела, если уместно. "
          "Выбирай строго по смыслу запроса, без противоречий. Если запрос НЕ про "
          "наготу — пустая строка.",
          ["nudity", "attire/revealing", "breasts", "pussy/anatomy", "ass/anatomy"],
          cap=4, min_rating="nsfw"),
    Round("face", "выражение и взгляд",
          "Выражение лица и взгляд — ДОЛЖНЫ отражать текущее настроение персонажа "
          "и его характер. Сдержанному/строгому — сдержанные выражения; НЕ бери "
          "наигранные или несвойственные ему (blush, pout и т.п.), если они не в "
          "его натуре и не следуют прямо из настроения.",
          ["face_tags", "eyes_tags/gaze_direction", "eyes_tags/eye_state",
           "eyes_tags/tears"], cap=4, mood=True),
    Round("hands", "жест руками",
          "Жест руками, ЕСЛИ уместен и руки свободны.",
          ["gestures", "hands"], cap=2, min_zone="head_shoulders", mood=True),
    Round("props", "реквизит в руках",
          "Предмет в руках — ТОЛЬКО если он ПРЯМО следует из запроса (читает → "
          "книга, пьёт чай → чашка, готовит → утварь). НЕ придумывай предмет, "
          "которого в запросе нет, — лишний реквизит почти всегда не в тему. По "
          "умолчанию предмета НЕТ: пустая строка.",
          ["holding", "objects"], cap=1, min_zone="head_shoulders"),
]

SIMPLE_BACKGROUND_ONLY = True
SIMPLE_BACKGROUND_TAGS = ["simple background"]

LOCATION_GROUPS = ("locations",)
SCENERY_BACKGROUND_TAGS = frozenset({
    "horizon", "sky", "blue sky", "cloud", "cloudy sky", "night sky", "starry sky",
})
_ENV_EXCLUDED_CACHE: frozenset | None = None


def environment_excluded_tags(tagmap=None) -> frozenset:
    global _ENV_EXCLUDED_CACHE
    if _ENV_EXCLUDED_CACHE is None:
        tm = tagmap if tagmap is not None else _load_tagmap()
        out: set[str] = set(SCENERY_BACKGROUND_TAGS)
        for gname in LOCATION_GROUPS:
            for sub in (tm.get(gname) or {}).values():
                out.update(sub)
        _ENV_EXCLUDED_CACHE = frozenset(out)
    return _ENV_EXCLUDED_CACHE

OUTFIT_REPLACING = {
    "nude", "completely nude", "underwear only",
    "naked apron", "naked towel", "naked shirt", "naked ribbon", "naked sheet",
    "micro bikini", "thong bikini", "slingshot swimsuit", "see-through leotard",
    "strapless leotard",
}


def _load_tagmap() -> dict:
    return json.loads(_TAGMAP.read_text(encoding="utf-8"))


def _vocab_for(round_: Round, tagmap: dict, *, max_rating: str,
               excluded_groups=frozenset(), excluded_tags=frozenset(),
               excluded_labels=frozenset()) -> list[str]:
    allow_nsfw = max_rating != "sfw"
    out: list[str] = []
    seen: set[str] = set()
    for path in round_.groups:
        gname, _, sub = path.partition("/")
        if gname in excluded_groups:
            continue
        grp = tagmap.get(gname)
        if not grp:
            continue
        subs = [sub] if sub else list(grp.keys())
        for s in subs:
            for t in grp.get(s, []):
                if t in seen or t in excluded_tags:
                    continue
                if not allow_nsfw and zones.rating_of(t) == "nsfw":
                    continue
                if excluded_labels and (zones.labels_of(t) & excluded_labels):
                    continue
                seen.add(t)
                out.append(t)
    return out


def _round_messages(round_: Round, intent: str, context: list[str],
                    vocab: list[str], persona_hint: str | None = None,
                    mood_hint: str | None = None,
                    reference_tags: list[str] | None = None
                    ) -> tuple[str, str]:
    persona_line = (
        f" Персонаж на снимке: {persona_hint}. Среди ПОДХОДЯЩИХ запросу тегов "
        f"предпочитай те, что вяжутся с её характером и манерой держаться."
        if persona_hint else "")
    mood_line = (
        f" Сейчас её настроение: {mood_hint} — выражение, поза и жест пусть его "
        f"отражают (в рамках её характера)."
        if (round_.mood and mood_hint) else "")
    system = (
        f"Ты выбираешь danbooru-теги для области «{round_.title}» аниме-картинки. "
        f"{round_.instruct}{persona_line}{mood_line} Выбирай ТОЛЬКО из данного списка теги, "
        f"которые СООТВЕТСТВУЮТ запросу. Максимум {round_.cap}. Лучше меньше "
        f"точных, чем много лишних — каждый лишний тег портит композицию. Отвечай "
        f"ТОЛЬКО выбранными тегами через запятую, строго из списка. Ничего не "
        f"подходит — пустая строка."
    )
    ctx = f"Уже выбрано в других областях: {', '.join(context)}\n" if context else ""
    ref = (f"Теги картинки-референса (вы обсуждали её в чате) из этой области: "
           f"{', '.join(reference_tags)} — если запрос ссылается на ту картинку "
           f"(«как на ней», «в такой же позе»), предпочитай именно их.\n"
           if reference_tags else "")
    user = (
        f"Запрос пользователя: {intent}\n"
        f"{ctx}{ref}"
        f"Доступные теги ({round_.title}):\n{', '.join(vocab)}"
    )
    return system, user


def _parse_selection(resp: str, vocab_set: set[str], cap: int) -> list[str]:
    resp = re.sub(r"<think>.*?</think>", "", resp, flags=re.S)
    picked: list[str] = []
    for chunk in resp.replace("\n", ",").split(","):
        t = zones._norm(chunk)
        if t in vocab_set and t not in picked:
            picked.append(t)
            if len(picked) >= cap:
                break
    return picked


def select_tags(intent: str, llm_chat, *, max_rating: str = "sfw",
                exclude_domains=None, persona_hint: str | None = None,
                framing_override: str | None = None,
                mood_hint: str | None = None, reference_tags=None) -> dict:
    tagmap = _load_tagmap()
    ex_groups, ex_tags, ex_labels = parse_exclude(exclude_domains)
    ref_norm: list[str] = []
    for r in reference_tags or ():
        t = zones._norm(r)
        if t and t not in ref_norm:
            ref_norm.append(t)
    rounds_out: dict[str, list[str]] = {}
    context: list[str] = []
    framing_tag: str | None = None
    level: str | None = None
    forced_framing = framing_override or detect_framing(intent)
    if forced_framing not in FRAMING_TAG_LEVEL:
        forced_framing = None

    for rnd in ROUNDS:
        if rnd.key == "scene" and SIMPLE_BACKGROUND_ONLY:
            rounds_out[rnd.key] = []
            continue
        if rnd.key == "framing" and forced_framing:
            rounds_out[rnd.key] = [forced_framing]
            context.append(forced_framing)
            framing_tag = forced_framing
            level = FRAMING_TAG_LEVEL[forced_framing]
            continue
        if RATING_ORDER.get(max_rating, 0) < RATING_ORDER.get(rnd.min_rating, 0):
            rounds_out[rnd.key] = []
            continue
        if rnd.min_zone and level is not None and \
                zones._IDX[level] < zones._IDX[rnd.min_zone]:
            rounds_out[rnd.key] = []
            continue
        vocab = _vocab_for(rnd, tagmap, max_rating=max_rating,
                           excluded_groups=ex_groups, excluded_tags=ex_tags,
                           excluded_labels=ex_labels)
        if not vocab:
            rounds_out[rnd.key] = []
            continue
        vocab_set = set(vocab)
        ref_in_round = [t for t in ref_norm if t in vocab_set]
        system, user = _round_messages(rnd, intent, context, vocab, persona_hint,
                                       mood_hint, reference_tags=ref_in_round)
        try:
            resp = llm_chat(system, user)
        except Exception as e:
            rounds_out[rnd.key] = []
            print(f"[rounds] {rnd.key}: LLM fail: {type(e).__name__}: {e}")
            continue
        sel = _parse_selection(resp, set(vocab), rnd.cap)
        rounds_out[rnd.key] = sel
        context.extend(sel)
        if rnd.key == "framing":
            for t in sel:
                if t in FRAMING_TAG_LEVEL:
                    framing_tag = t
                    level = FRAMING_TAG_LEVEL[t]
                    break

    output_order = ["exposure", "face", "pose", "hands", "props", "framing", "scene"]
    final: list[str] = []
    for key in output_order:
        for t in rounds_out.get(key, []):
            if t not in final:
                final.append(t)
    if not forced_framing and level is not None:
        deepest = level
        for t in final:
            if _is_framing(t):
                continue
            z = zones.zone_of(t)
            if zones._IDX.get(z, 0) > zones._IDX[deepest]:
                deepest = z
        if deepest != level:
            new_frame = _FRAME_OF_LEVEL[deepest]
            final = [new_frame if _is_framing(t) else t for t in final]
            if new_frame not in final:
                final.append(new_frame)
            framing_tag, level = new_frame, deepest

    if SIMPLE_BACKGROUND_ONLY:
        for t in SIMPLE_BACKGROUND_TAGS:
            if t not in final:
                final.append(t)

    return {
        "framing": framing_tag,
        "framing_level": level,
        "rounds": rounds_out,
        "tags": final,
    }


COMPOSE_BODY_EXCLUDE = frozenset({
    "wide hips", "hip dips", "hips", "narrow waist", "abs", "belly", "stomach",
    "navel", "linea alba", "thick thighs", "long legs", "slim legs", "thigh gap",
    "thick arms", "biceps", "pectorals", "ribs", "breasts",
    "arms", "hands", "legs", "shoulders", "neck", "eyebrows", "eyelashes",
    "forehead", "nose", "lips", "palms", "joints",
})

IDLE_TWO_HANDS = frozenset({"own hands clasped", "own hands together",
                            "interlocked fingers", "hands on own thighs"})
_HAND_BUSY_GROUPS = ("gestures/", "hands/", "holding/", "posture/arms",
                     "posture/hugging", "posture/hands")
_HAND_GROUP_CACHE: dict[str, str] | None = None


def _exposure_hint(outfit_tags) -> str:
    if not outfit_tags:
        return ""
    from drawing import exposure as _ex
    return _ex.hint_line(_ex.exposed(", ".join(outfit_tags)))


def drop_idle_hands(tags: list[str], tagmap=None) -> list[str]:
    idle = [t for t in tags if t in IDLE_TWO_HANDS]
    if not idle:
        return tags
    global _HAND_GROUP_CACHE
    if _HAND_GROUP_CACHE is None:
        tm = tagmap or _load_tagmap()
        _HAND_GROUP_CACHE = {t: f"{g}/{s}" for g, subs in tm.items()
                             if isinstance(subs, dict) and g != "_meta"
                             for s, lst in subs.items() for t in lst}
    busy = [t for t in tags if t not in IDLE_TWO_HANDS
            and _HAND_GROUP_CACHE.get(t, "").startswith(_HAND_BUSY_GROUPS)]
    if not busy:
        return tags
    print(f"[compose] руки заняты ({busy}) — праздный жест убран: {idle}")
    return [t for t in tags if t not in IDLE_TWO_HANDS]


_COMPOSE_CATEGORIES: list[tuple[str, list[str], str]] = [
    ("КАДР И РАКУРС", ["image_composition/framing", "image_composition/view_angle",
                       "image_composition/other_framing", "focus_tags"], "sfw"),
    ("ПОЗА И ДЕЙСТВИЕ", ["posture", "activities"], "sfw"),
    ("РУКИ И ЖЕСТЫ", ["gestures", "hands"], "sfw"),
    ("СОСТОЯНИЕ ОДЕЖДЫ (только для вещей, которые есть в наряде)",
     ["attire/clothing_state"], "sfw"),
    ("ВЫРАЖЕНИЕ И ВЗГЛЯД", ["face_tags", "eyes_tags/gaze_direction",
                            "eyes_tags/eye_state", "eyes_tags/tears"], "sfw"),
    ("ЧАСТИ ТЕЛА В КАДРЕ", ["body_parts/anatomy", "body_parts/arms_hands",
        "body_parts/head", "body_parts/legs_feet", "body_parts/torso",
        "body_parts/upper", "body_parts/appendages"], "sfw"),
    ("ФОН, МЕБЕЛЬ, СРЕДА", ["locations", "backgrounds", "furniture", "water", "fire"], "sfw"),
    ("СВЕТ И ВРЕМЯ СУТОК", ["lighting"], "sfw"),
    ("РЕКВИЗИТ И ПРЕДМЕТЫ", ["holding", "objects", "food_tags"], "sfw"),
    ("ОТКРЫТО БЕЗ РАЗДЕВАНИЯ — плечо, спина, живот, ноги (наряд на месте)",
     ["body_parts/exposure"], "nsfw"),
    ("БЕЛЬЁ 18+ (только при явном намерении показать)", ["attire/underwear"], "nsfw"),
    ("ОБНАЖЁННОСТЬ И АНАТОМИЯ (18+, только когда запрос прямо открывает грудь или низ)",
     ["nudity", "attire/revealing", "breasts", "pussy", "ass", "penis", "feet"], "nsfw"),
    ("ОТКРОВЕННЫЕ ДЕЙСТВИЯ (18+)", ["sex_acts", "sex_objects"], "nsfw"),
]

_CORE_COVER_KW = ("dress", "shirt", "top", "blouse", "bra", "panty", "panties",
                  "thong", "bikini", "leotard", "swimsuit", "bottom", "skirt",
                  "shorts", "pant", "underwear", "lingerie", "babydoll", "camisole",
                  "bodysuit", "kimono", "robe", "gown")


def _is_core_cover(tag: str) -> bool:
    t = tag.lower()
    if "headdress" in t or "headband" in t:
        return False
    return any(k in t for k in _CORE_COVER_KW)


_EXPLICIT_GROUP_PATHS = (
    "nudity", "sex_acts", "sex_objects",
    "attire/underwear", "attire/revealing",
    "breasts/nipples", "pussy/anatomy", "pussy/states", "pussy/fluids",
    "pussy/adornments", "ass/anus", "hair/sexual", "feet/fetish",
    "breasts/marks", "breasts/lactation", "breasts/adornments",
    "penis/size", "penis/parts", "penis/condition", "penis/appearance",
    "penis/acts",
)
_EXPLICIT_EXTRA_TAGS = frozenset({
    "penis", "testicles",
    "ahegao", "fucked silly", "afterglow", "torogao",
})
_EXPLICIT_TAGS_CACHE: frozenset | None = None


def _explicit_tag_set() -> frozenset:
    global _EXPLICIT_TAGS_CACHE
    if _EXPLICIT_TAGS_CACHE is None:
        tagmap = _load_tagmap()
        out: set[str] = set()
        for path in _EXPLICIT_GROUP_PATHS:
            gname, _, sub = path.partition("/")
            grp = tagmap.get(gname) or {}
            for s in ([sub] if sub else list(grp.keys())):
                out.update(grp.get(s, []))
        out.update(_EXPLICIT_EXTRA_TAGS)
        _EXPLICIT_TAGS_CACHE = frozenset(
            t for t in out if zones.rating_of(t) == "nsfw")
    return _EXPLICIT_TAGS_CACHE


def is_explicit_selection(tags, remove=()) -> bool:
    expl = _explicit_tag_set()
    for t in (tags or ()):
        if zones._norm(t) in expl:
            return True
    try:
        from drawing.tag_resolver import explicit_by_words
        if any(explicit_by_words(t) for t in (tags or ())):
            return True
    except Exception:
        pass
    return any(_is_core_cover(r) for r in (remove or ()))


from drawing.exposure import bare_zones, underwear_zones


_SCENE_GROUPS = ("locations", "backgrounds", "furniture", "lighting", "water", "fire")
_SCENE_TAGS_CACHE: frozenset | None = None


def _scene_wide_tags(tagmap) -> frozenset:
    global _SCENE_TAGS_CACHE
    if _SCENE_TAGS_CACHE is None:
        out: set[str] = set()
        for gname in _SCENE_GROUPS:
            grp = tagmap.get(gname)
            if grp:
                for sub in grp.values():
                    out.update(sub)
        _SCENE_TAGS_CACHE = frozenset(out)
    return _SCENE_TAGS_CACHE


def _build_compose_catalog(tagmap, *, max_rating: str, ex_groups=frozenset(),
                           ex_tags=frozenset(), ex_labels=frozenset(),
                           allow_contact: bool = False) -> list[tuple[str, list[str]]]:
    allow_nsfw = max_rating != "sfw"
    env_ex = environment_excluded_tags(tagmap) if SIMPLE_BACKGROUND_ONLY else frozenset()
    out: list[tuple[str, list[str]]] = []
    for label, groups, min_rating in _COMPOSE_CATEGORIES:
        if RATING_ORDER.get(max_rating, 0) < RATING_ORDER.get(min_rating, 0):
            continue
        seen: set[str] = set()
        tags: list[str] = []
        for path in groups:
            gname, _, sub = path.partition("/")
            if gname in ex_groups:
                continue
            grp = tagmap.get(gname)
            if not grp:
                continue
            subs = [sub] if sub else list(grp.keys())
            for s in subs:
                for t in grp.get(s, []):
                    if t in seen or t in ex_tags or t in env_ex:
                        continue
                    if not allow_nsfw and zones.rating_of(t) == "nsfw":
                        continue
                    if ex_labels and (zones.labels_of(t) & ex_labels):
                        continue
                    seen.add(t); tags.append(t)
        tags = [t for t in tags if t not in COMPOSE_BODY_EXCLUDE]
        if allow_nsfw and not allow_contact:
            from drawing.ladder import is_partner_tag
            tags = [t for t in tags if not is_partner_tag(t)]
        if tags:
            out.append((label, tags))
    extra = list(FRAMING_HEADLESS) + [
        k for k in FRAMING_FOCUS
        if allow_nsfw or zones.rating_of(k) != "nsfw"]
    for i, (lbl, tg) in enumerate(out):
        if lbl.startswith("КАДР"):
            out[i] = (lbl, tg + [k for k in extra if k not in tg])
            break
    return out


def _parse_compose(resp: str) -> tuple[list[str], list[str]]:
    resp = re.sub(r"<think>.*?</think>", "", resp, flags=re.S)
    tags: list[str] = []
    remove: list[str] = []
    for line in resp.splitlines():
        low = line.strip().lstrip("*-• ").lower()
        head = low.split(":", 1)[0].strip().strip("*") if ":" in low else ""
        if head in _SLOT_KEYS:
            bucket, src = tags, line.split(":", 1)[1]
        elif head in ("remove", "снять"):
            bucket, src = remove, line.split(":", 1)[1]
        else:
            continue
        for chunk in src.replace("\n", ",").split(","):
            t = zones._norm(chunk.strip().strip("*").strip())
            if t and t not in ("—", "-", "нет", "пусто", "none") and t not in bucket:
                bucket.append(t)
    return tags, remove


def _compose_rules(max_rating: str, light: bool = True, allow_contact: bool = False) -> str:
    if max_rating != "sfw":
        undress = (
            "  РАЗДЕВАНИЕ / БЕЛЬЁ / НАГОТА (18+). Откровенность кадра — ровно та, что "
            "названа в запросе: не открывай больше сказанного и не скромничай, если "
            "сказано прямо. Дорабатывая скупой запрос (правило 5), откровенность не "
            "повышай.\n"
            "  • Костюм: части можно СНЯТЬ (строка REMOVE), добавлять нельзя.\n"
            "  • Открытые плечи, ключицы, спина, ноги, ослабленный ворот — это НЕ раздевание: "
            "бери из «ОТКРЫТО БЕЗ РАЗДЕВАНИЯ» и «СОСТОЯНИЕ ОДЕЖДЫ», костюм цел, теги "
            "белья и наготы не нужны.\n"
            "  • Бельё только ВИДНО, одежда на месте — костюм ОСТАЁТСЯ: bra peek / "
            "panty peek или бельё + то, как его видно (skirt lift, cleavage…); грудь и "
            "низ закрыты.\n"
            "  • Бельё НА НЕЙ вместо одежды (запрос говорит, что она в белье или в "
            "ночной одежде) — костюм снят: перечисли его части в REMOVE (или тег "
            "underwear only) И назови бельё тегом (bra, panties, thong, nightgown…). "
            "Названа одна вещь — только она (одна нижняя часть — без лифа).\n"
            "  • Грудь или низ ОТКРЫТЫ — только если запрос так и говорит: topless female "
            "(у мужчины topless male) / breasts out (платье спущено до пояса, низ на "
            "месте), bottomless; костюм в "
            "REMOVE не трогай (максимум верхний слой-помеху вроде фартука).\n"
            "  • ПОЛНАЯ нагота (запрос говорит, что на ней ничего нет): тег nude или "
            "completely nude и сними костюм.\n"
            "  • ДЕЙСТВИЕ В ОДИНОЧКУ — только если запрос прямо о нём: ласкает себя — "
            "masturbation (пальцами — + fingering), игрушка — vibrator / dildo / sex toy; "
            "одежда — как сказано в запросе (без одежды — nude; в белье — hand in own "
            "panties или masturbation through clothes). "
            + ("Действия со зрителем — только если запрос прямо о них."
               if allow_contact else
               "Второго человека в кадре нет: ни партнёра, ни рук или тела зрителя — "
               "действий вдвоём не бери."))
    else:
        undress = (
            "  Режим ПРИЛИЧНЫЙ: костюм НЕ снимается и НЕ задирается, бельё и нагота НЕ "
            "показываются. Снять можно максимум обувь, головной убор, перчатки, чулки, "
            "фартук, верхний слой, аксессуары — основную одежду (платье/верх/низ) не трогай.")
    no_place = (
        "8. МЕСТО ДЕЙСТВИЯ НЕ задаётся: никаких комнат, улиц, зданий, пейзажей, "
        "неба и indoors/outdoors — фон всегда простой (simple background, система "
        "добавит его сама). Из окружения бери только ОТДЕЛЬНЫЕ предметы рядом с "
        "персонажем (мебель, окно, реквизит) — названные в запросе или нужные позе"
        + (", свет и время суток" if light else "") + ".\n"
        if SIMPLE_BACKGROUND_ONLY else "")
    return (
        "ПРАВИЛА:\n"
        "1. Внешность (волосы, цвет и форма глаз, кожа, телосложение) и одежда УЖЕ "
        "заданы и неизменны — НЕ дублируй и не меняй их. Из каталога бери только "
        "сцену/позу/выражение/кадр/части тела и т.п.\n"
        "2. Сначала реши КАДР. Голова В кадре: close-up / portrait / upper body / "
        "cowboy shot / full body. Голова ВНЕ кадра ТОЛЬКО если запрос явно «одни "
        "ноги/ступни/низ»: lower body / legs / feet — тогда выражение лица и взгляд "
        "НЕ бери, их не видно. Если запрос про АКЦЕНТ на части тела, но не «только "
        "она» — возьми фокус-тег (thigh focus, leg focus…) ПЛЮС широкий кадр "
        "(cowboy shot / full body): голова в кадре, лицо видно. Бери ТОЛЬКО то, "
        "что ВИДНО в кадре (в портрете нет ног и обуви; в lower body нет лица и "
        "причёски).\n"
        "3. Теги — предпочтительно из каталога ниже (канон). Если нужного "
        "ПОНЯТИЯ в каталоге нет — напиши точный общепринятый danbooru-тег "
        "по-английски, как он пишется на danbooru (напр. hugging own legs) — "
        "его сверят с базой тегов. НЕ выдумывай теги и не пиши фразы своими "
        "словами: несуществующее будет выброшено.\n"
        "4. Без весов: никаких (tag:1.2).\n"
        "5. Связный ЦЕЛЬНЫЙ образ под запрос + характер + настроение. Запрос обычно "
        "скупой — ДОРАБОТАЙ его сам: как стоят или сложены ноги, что делают руки, "
        "куда направлен взгляд, что из тела видно при этой позе. Каждая строка "
        "ответа — отдельное решение; пустой она остаётся, только если этого в "
        "кадре правда нет (на крупном плане ног не видно). Без противоречий (стоит "
        "И сидит) и без мусора — ориентир 12-20 тегов на все строки. Не повторяй "
        "по привычке одно и то же в каждом кадре: наклон головы или корпуса, "
        "приглушённый свет — только когда они часть именно этого момента.\n"
        "6. Выражение, поза и жест отражают характер и текущее настроение персонажа.\n"
        "7. Одежду можно только СНИМАТЬ (строка REMOVE) — добавлять/менять костюм "
        "нельзя. Например снять обувь, если уместно.\n"
        f"{no_place}"
        f"{undress}\n"
    )


COMPOSE_SLOTS: tuple[tuple[str, str], ...] = (
    ("КАДР", "кадр; ракурс — если он делает кадр живее; фокус-тег — если запрос "
             "про акцент на части тела"),
    ("ПОЗА", "положение тела и ног (сидит — как сложены ноги; стоит — как стоят ноги)"),
    ("РУКИ", "что делают руки, что держат, куда положены; если руки уже заняты "
             "позой (опора, объятие колен) — не добавляй им другого"),
    ("ГОЛОВА", "взгляд и выражение лица"),
    ("ТЕЛО", "что поза и кадр открывают взгляду сверх обычного (разулась — босые "
             "ступни; куртка нараспашку — open jacket); у обычной позы в наряде — пусто"),
    ("ОКРУЖЕНИЕ", "мебель и предметы рядом — только названные в запросе или нужные "
                  "позе (сидит на стуле — chair), иначе пусто; свет и время суток — "
                  "если важны моменту"),
)
_ENV_SLOT_NO_LIGHT = ("мебель и предметы рядом — только названные в запросе или "
                      "нужные позе (сидит на стуле — chair), иначе пусто")


HABIT_MIN_FRAMES = 2
_HABIT_SKIP_GROUPS = ("image_composition/framing", "face_tags", "eyes_tags")
_HABIT_SKIP = frozenset({"looking at viewer", "simple background", "sitting", "standing",
                         "kneeling", "lying", "solo", "1girl", "1boy"})


def composer_habits(recent_frames, tagmap=None, limit: int = 6) -> list[str]:
    from collections import Counter
    tm = tagmap if tagmap is not None else _load_tagmap()
    group_of: dict[str, str] = {}
    for g, subs in tm.items():
        if isinstance(subs, dict):
            for sname, ts in subs.items():
                for t in ts or []:
                    group_of.setdefault(t, f"{g}/{sname}")
    c = Counter(t for f in recent_frames or () for t in set(f))
    out = []
    for t, v in c.most_common():
        if v < HABIT_MIN_FRAMES or len(out) >= limit:
            break
        g = group_of.get(t, "")
        if t in _HABIT_SKIP or t in FRAMING_HEADLESS or g.startswith(_HABIT_SKIP_GROUPS):
            continue
        if not g:
            continue
        out.append(t)
    return out


def _compose_slots(light: bool) -> tuple[tuple[str, str], ...]:
    if light:
        return COMPOSE_SLOTS
    return tuple((k, _ENV_SLOT_NO_LIGHT if k == "ОКРУЖЕНИЕ" else d) for k, d in COMPOSE_SLOTS)


def _compose_examples(excluded: set[str]) -> str:
    if not excluded:
        return _COMPOSE_EXAMPLES
    out = []
    for line in _COMPOSE_EXAMPLES.split("\n"):
        if line.startswith("ОКРУЖЕНИЕ:"):
            keep = [t.strip() for t in line[len("ОКРУЖЕНИЕ:"):].split(",")
                    if t.strip() and t.strip() not in excluded]
            line = "ОКРУЖЕНИЕ:" + (" " + ", ".join(keep) if keep else "")
        out.append(line)
    return "\n".join(out)
_SLOT_KEYS = tuple(k.lower() for k, _ in COMPOSE_SLOTS) + (
    "frame", "pose", "hands", "head", "body", "scene", "tags", "теги")

_COMPOSE_EXAMPLES = (
    "ПРИМЕРЫ (как отвечать):\n"
    "Запрос: сидит у окна дождливым вечером, читает\n"
    "КАДР: cowboy shot, three-quarter view\n"
    "ПОЗА: sitting, crossed legs\n"
    "РУКИ: holding book, open book\n"
    "ГОЛОВА: looking down, light smile\n"
    "ТЕЛО:\n"
    "ОКРУЖЕНИЕ: window, rain, evening\n"
    "REMOVE:\n"
    "---\n"
    "Запрос: развалилась на диване после смены, скинула туфли\n"
    "КАДР: full body\n"
    "ПОЗА: sitting, on couch, leaning back, arm support\n"
    "РУКИ: hand on own thigh\n"
    "ГОЛОВА: head back, closed eyes, smile\n"
    "ТЕЛО: barefoot\n"
    "ОКРУЖЕНИЕ: couch, evening\n"
    "REMOVE: mary janes\n"
    "---\n"
    "Запрос: показать, как изящно она стоит — кадр на ноги\n"
    "КАДР: lower body\n"
    "ПОЗА: standing, crossed ankles\n"
    "РУКИ:\n"
    "ГОЛОВА:\n"
    "ТЕЛО: legs\n"
    "ОКРУЖЕНИЕ: day\n"
    "REMOVE:\n"
    "---\n"
    "Запрос: селфи, подчеркнуть бёдра\n"
    "КАДР: cowboy shot, selfie, from above, thigh focus\n"
    "ПОЗА: standing, contrapposto\n"
    "РУКИ: holding phone, hand on own hip\n"
    "ГОЛОВА: looking at viewer, smirk\n"
    "ТЕЛО: thighs\n"
    "ОКРУЖЕНИЕ: day\n"
    "REMOVE:\n"
)


def compose_tags(intent: str, llm_chat, *, max_rating: str = "sfw",
                 appearance_tags=(), outfit_tags=(),
                 persona_hint: str | None = None, mood_hint: str | None = None,
                 framing_override: str | None = None,
                 exclude_domains=None, reference_tags=None,
                 resolver=None, underlayer_tags=(), carry: dict | None = None,
                 recent_frames=(), allow_contact: bool = False) -> dict:
    tagmap = _load_tagmap()
    ex_groups, ex_tags, ex_labels = parse_exclude(exclude_domains)
    catalog = _build_compose_catalog(tagmap, max_rating=max_rating, ex_groups=ex_groups,
                                     ex_tags=ex_tags, ex_labels=ex_labels,
                                     allow_contact=allow_contact)
    catalog_set = {t for _, tags in catalog for t in tags}
    outfit_set = {zones._norm(t) for t in outfit_tags}
    style_ex = set(ex_tags)
    for g in ex_groups:
        for sub in (tagmap.get(g) or {}).values():
            style_ex.update(sub)
    light = "lighting" not in ex_groups

    persona_line = f"Персонаж: {persona_hint}. " if persona_hint else ""
    mood_line = f"Настроение сейчас: {mood_hint}. " if mood_hint else ""
    ref_canon = [t for t in (zones._norm(r) for r in (reference_tags or ()))
                 if t in catalog_set]
    ref_block = (
        "РЕФЕРЕНС — теги чужого арта, который вы только что обсуждали в чате:\n"
        f"  {', '.join(ref_canon)}\n"
        "Если запрос ссылается на него («как на той картинке», «в такой же позе», "
        "«повтори это») — воспроизведи композицию референса этими тегами: поза, "
        "кадр, фон, свет, действие. Если запрос про другое — референс ИГНОРИРУЙ.\n\n"
        if ref_canon else "")
    cat_text = "\n".join(f"{label}: {', '.join(tags)}" for label, tags in catalog)
    system = (
        "Ты — художественный директор аниме-иллюстрации. Собери НАБОР danbooru-тегов "
        "для ОДНОЙ картинки персонажа по запросу. Внешность и одежда уже заданы — ты "
        "композируешь сцену, позу, выражение, кадр.\n\n"
        + _compose_rules(max_rating, light, allow_contact) + "\n"
        "ФОРМАТ ОТВЕТА — строки по порядку, теги через запятую (строка пустая, "
        "только если этого в кадре правда нет):\n"
        + "".join(f"{k}: <{d}>\n" for k, d in _compose_slots(light))
        + "REMOVE: <одежда на снятие через запятую, или пусто>\n\n"
        + _compose_examples(style_ex)
    )
    under_line = (
        f"  Под одеждой (видно ТОЛЬКО при раздевании/засвете; система "
        f"добавит сама): {', '.join(underlayer_tags)}\n"
        if underlayer_tags and max_rating != "sfw" else "")
    habits = composer_habits(recent_frames, tagmap)
    habit_block = (
        f"НЕДАВНИЕ КАДРЫ этой серии уже были с: {', '.join(habits)}. Не бери их по "
        "привычке — только если запрос прямо о них (ракурс можно не указывать вовсе).\n\n"
        if habits else "")
    user = (
        f"Запрос: {intent}\n"
        f"{persona_line}{mood_line}\n"
        f"{ref_block}"
        f"{habit_block}"
        "УЖЕ ЗАДАНО (НЕ трогай, для справки):\n"
        f"  Внешность: {', '.join(appearance_tags) or '—'}\n"
        f"  Одежда: {', '.join(outfit_tags) or '—'}\n"
        f"{_exposure_hint(outfit_tags)}"
        f"{under_line}\n"
        f"КАТАЛОГ (выбирай ТОЛЬКО отсюда):\n{cat_text}"
    )
    try:
        resp = llm_chat(system, user)
    except Exception as e:
        print(f"[compose] LLM fail: {type(e).__name__}: {e}")
        return {"framing": None, "framing_level": None, "headless": False,
                "headless_floor": None, "tags": [], "remove": [], "mode": "compose"}

    raw_tags, raw_remove = _parse_compose(resp)
    raw_tags = gendered_topless(raw_tags, appearance_tags)
    allow_nsfw = max_rating != "sfw"
    appearance_set = {zones._norm(t) for t in appearance_tags}
    tags = [t for t in raw_tags if t in catalog_set]
    dropped = [t for t in raw_tags if t not in catalog_set]
    if dropped and resolver is not None:
        try:
            res = resolver.resolve_many(dropped, allow_nsfw=allow_nsfw)
        except Exception as e:
            print(f"[compose] resolver fail: {type(e).__name__}: {e}")
            res = {}
        rescued, by_style = [], []
        for raw, canon in res.items():
            if not canon:
                continue
            if canon in style_ex or (ex_labels and zones.labels_of(canon) & ex_labels):
                by_style.append(canon)
                continue
            if (canon not in tags and canon not in rescued
                    and canon not in appearance_set and canon not in outfit_set):
                rescued.append(canon)
        if by_style:
            print(f"[compose] исключено стилем: {by_style}")
        if rescued:
            print(f"[compose] resolver rescued {len(rescued)}: {rescued} "
                  f"(raw: {[d for d in dropped if res.get(d)]})")
            tags.extend(rescued)
    if resolver is not None:
        try:
            _verbatim = resolver.extract_from_text(intent, allow_nsfw=allow_nsfw)
        except Exception as e:
            print(f"[compose] intent-tags fail: {type(e).__name__}: {e}")
            _verbatim = []
        _added = [t for t in _verbatim
                  if t not in tags and t not in appearance_set
                  and t not in outfit_set]
        if _added:
            print(f"[compose] intent verbatim tags: {_added}")
            tags.extend(_added)
    if not allow_contact:
        from drawing.ladder import is_partner_tag
        _partner = [t for t in tags if is_partner_tag(t)]
        if _partner:
            print(f"[compose] второй человек в кадре закрыт: {_partner}")
            tags = [t for t in tags if t not in _partner]
    tags, _det_add = apply_intent_details(tags, intent, allow_nsfw=allow_nsfw)
    if _det_add:
        print(f"[compose] детали из intent: +{_det_add}")
    if allow_nsfw:
        tags, _st_add, _st_drop = apply_intent_state(tags, intent)
        if _st_add or _st_drop:
            print(f"[compose] intent 18+: +{_st_add} −{_st_drop}")
        tags, _act_add = apply_intent_acts(tags, intent)
        if _act_add:
            print(f"[compose] действие из intent: +{_act_add}")
        tags = gendered_topless(tags, appearance_tags)
        tags = gendered_acts(tags, appearance_tags)
        tags = drop_lift_tug(tags)
        if outfit_tags and intent_wears_underwear(intent):
            from drawing import exposure as _ex
            _valid = [r for r in raw_remove if r in outfit_set]
            *_, _torso_off, _legs_off = _ex._signals(tags, _valid)
            if not (_torso_off or _legs_off or set(tags) & OUTFIT_REPLACING):
                _strip = [o for o in _ex.strip_for_underwear(outfit_tags)
                          if zones._norm(o) not in raw_remove]
                if _strip:
                    print(f"[compose] в белье — снимаю наряд: {_strip}")
                    raw_remove = list(raw_remove) + [zones._norm(o) for o in _strip]
        if carry and not intent_dressed(intent):
            _own_tags = intent_state_tags(intent)[0]
            if (_own_tags and not intent_state_tags(intent, guess=False)[0]
                    and {"nude", "completely nude"} & set(carry.get("tags") or ())):
                tags = [t for t in tags if t not in _own_tags]
                _own_tags = []
            _own_state = bool(_own_tags) or intent_wears_underwear(intent)
            _c_rem = [r for r in carry.get("remove") or ()
                      if r in outfit_set and r not in raw_remove]
            _c_tags = ([] if _own_state else
                       [t for t in carry.get("tags") or () if t not in tags])
            if _c_rem or _c_tags:
                print(f"[compose] как на прошлом снимке: +{_c_tags} снято {_c_rem}")
                raw_remove = list(raw_remove) + _c_rem
                tags = tags + _c_tags
    _fig = [t for t in tags if t in COMPOSE_BODY_EXCLUDE]
    if _fig:
        print(f"[compose] фигура/общие части убраны: {_fig}")
        tags = [t for t in tags if t not in COMPOSE_BODY_EXCLUDE]
    if SIMPLE_BACKGROUND_ONLY:
        env_ex = environment_excluded_tags(tagmap)
        _env_dropped = [t for t in tags if t in env_ex]
        if _env_dropped:
            print(f"[compose] место действия убрано ({len(_env_dropped)}): "
                  f"{_env_dropped}")
            tags = [t for t in tags if t not in env_ex]
    tags = drop_idle_hands(tags, tagmap)
    from drawing import exposure as _ex
    if outfit_tags:
        _rem = {r for r in raw_remove if r in outfit_set}
        _left = [o for o in outfit_tags if zones._norm(o) not in _rem]
        _open = _ex.frame_open(", ".join(_left), tags, sorted(_rem),
                               outfit_gone=bool(set(tags) & OUTFIT_REPLACING))
        _kept = _ex.drop_covered_picks(tags, _open)
        if len(_kept) != len(tags):
            print(f"[compose] закрыто нарядом: {[t for t in tags if t not in _kept]}")
            tags = _kept
    if "straight-on" in tags and not re.search(r"анфас|straight-on|фронтальн",
                                                (intent or "").lower()):
        tags = [t for t in tags if t != "straight-on"]
    def _frame_ok(fr):
        return _is_framing(fr) or fr == HEADLESS_TORSO
    hint_fr = framing_override if _frame_ok(framing_override) else None
    intent_fr = detect_framing(intent)
    intent_fr = intent_fr if _frame_ok(intent_fr) else None
    if intent_fr in FRAMING_HEADLESS or intent_fr == HEADLESS_TORSO:
        forced = intent_fr
    else:
        forced = hint_fr or intent_fr
    model_headless = next((t for t in tags if t in FRAMING_HEADLESS), None)
    if model_headless and not forced and not headless_asked(intent):
        print(f"[compose] кадр без головы не просили: {model_headless} → обычный кадр")
        tags = [t for t in tags if t not in FRAMING_HEADLESS]
        model_headless = None
        if not any(_is_framing(t) for t in tags):
            tags.append("full body")
    framing_tag = (forced or model_headless
                   or next((t for t in tags if _is_framing(t)), None)
                   or "portrait")
    if framing_tag == HEADLESS_TORSO:
        (level, floor), headless = HEADLESS_TORSO_BAND, True
        for t in tags:
            if _is_framing(t) or t in FRAMING_FOCUS or band_exempt(t):
                continue
            z = zones.zone_of(t)
            if zones._IDX[level] < zones._IDX.get(z, 0) <= zones._IDX["cowboy"]:
                level = z
        framing_tag = _FRAME_OF_LEVEL[level]
    else:
        level, floor, headless = _framing_level_of(framing_tag)
    if not headless and HEAD_OUT_TAG in tags:
        tags = [t for t in tags if t != HEAD_OUT_TAG]
    focus_intent = detect_focus(intent)
    if (focus_intent and focus_intent not in tags
            and (allow_nsfw or zones.rating_of(focus_intent) != "nsfw")):
        tags.append(focus_intent)
    if not headless and not forced and level is not None:
        deepest = level
        for t in tags:
            if _is_framing(t):
                continue
            _need = FRAMING_FOCUS.get(t)
            z = FRAMING_TAG_LEVEL[_need] if _need else zones.zone_of(t)
            if zones._IDX.get(z, 0) > zones._IDX[deepest]:
                deepest = z
        if deepest != level:
            level = deepest
            framing_tag = _FRAME_OF_LEVEL[level]
    scene_wide = _scene_wide_tags(tagmap) if headless else frozenset()
    final: list[str] = []
    for t in tags:
        if _is_framing(t):
            continue
        if headless and level is not None:
            flr = None if t in scene_wide else floor
            if not band_exempt(t) and not zones.visible_in_band(t, level, flr):
                continue
        if t not in final:
            final.append(t)
    final.append(framing_tag)
    if headless and HEAD_OUT_TAG not in final:
        final.append(HEAD_OUT_TAG)
    if SIMPLE_BACKGROUND_ONLY:
        for t in SIMPLE_BACKGROUND_TAGS:
            if t not in final:
                final.append(t)
    allow_undress = allow_nsfw
    remove = [r for r in raw_remove if r in outfit_set
              and (allow_undress or not _is_core_cover(r))]

    return {"framing": framing_tag, "framing_level": level, "headless": headless,
            "headless_floor": floor, "tags": final, "remove": remove, "mode": "compose"}
