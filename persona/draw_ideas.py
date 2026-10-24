from __future__ import annotations

import random
import re
from collections import deque
from pathlib import Path

import yaml

IDEAS_PER_HINT = 3
FIT_WEIGHT = 3.0
RECENT_TAG_WEIGHT = 0.2
_RECENT: deque[str] = deque(maxlen=18)
_cache: dict[tuple, list[dict]] = {}


def _dirs(content_dir: Path | None) -> list[Path]:
    base = content_dir
    if base is None:
        from app_paths import content_base
        base = content_base()
    out = [Path(base) / "draw_ideas"]
    if content_dir is None:
        try:
            from app_paths import PROJECT_ROOT
            from services.addons import content_dirs
            out += content_dirs(PROJECT_ROOT, "draw_ideas")
        except Exception as e:
            print(f"[draw_ideas] аддоны: {type(e).__name__}: {e}")
    return out


def load_ideas(content_dir: Path | None = None, force_reload: bool = False) -> list[dict]:
    dirs = _dirs(content_dir)
    key = tuple(str(d) for d in dirs)
    if key in _cache and not force_reload:
        return _cache[key]
    merged: dict[str, dict] = {}
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.yaml"), key=lambda f: (f.name != "core.yaml", f.name)):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except Exception as e:
                print(f"[draw_ideas] {f.name} не прочитался: {type(e).__name__}: {e}")
                continue
            default_rating = str(data.get("rating") or "sfw")
            for it in data.get("ideas") or []:
                if isinstance(it, dict) and it.get("id") and it.get("text"):
                    merged[str(it["id"])] = {
                        "id": str(it["id"]), "text": str(it["text"]).strip(),
                        "rating": str(it.get("rating") or default_rating),
                        "tags": [str(t) for t in it.get("tags") or [] if t],
                        "level": int(it.get("level") or (0 if str(
                            it.get("rating") or default_rating) == "sfw" else 1)),
                        "contact": str(it.get("contact") or "")}
    ideas = list(merged.values())
    _cache[key] = ideas
    return ideas


_EXPLICIT_RX = re.compile(
    r"(?<!постельн)(?<!постельное )\bбель[еяю]|\bоткровен|\bпикантн|\bэроти|\bсексуальн"
    r"|\bсоблазн|\bинтим|\bраздет|\bразден|\bразде(?:ва|л)|\bголая|\bголой|\bголышом|\bнагиш"
    r"|\bнагот|\bобнаж|\bтрусик|\bлифчик|\bбюстгальт|\bтоплес|\bнюд|\bnsfw|\bnude|\blingerie")


def explicit_ask(text: str | None) -> bool:
    low = (text or "").lower().replace("ё", "е")
    if not low:
        return False
    if _EXPLICIT_RX.search(low):
        return True
    try:
        from app_paths import PROJECT_ROOT
        from services.nsfw_anatomy import codebook
        book = codebook(PROJECT_ROOT)
        return bool(book and book.mentions_body(low))
    except Exception:
        return False


_ASK_LEVELS = (
    (6, re.compile(r"ласка\w* себя|мастурб|трога\w* себя|игрушк|вибратор|дилдо"
                   r"|удовлетвор\w* себя|доведи себя|пальц\w* между ног")),
    (5, re.compile(r"разведи ноги|раздвинь|ноги (?:шире|врозь)|во всей красе"
                   r"|как никому|покажи вс[её]\b|самое откровенн")),
    (4, re.compile(r"без (?:одежды|всего)|\bголая|\bголой|голышом|обнаж|разденься|догола"
                   r"|нагишом|совсем без")),
    (3, re.compile(r"топлес|без лифчика|без трусиков|покажи грудь|сними верх|сними лифчик")),
    (2, re.compile(r"(?<!постельн)(?<!постельное )\bбель[еяю]|трусик|лифчик|кружевн|пеньюар")),
)
_MORE_RX = re.compile(r"смелее|откровеннее|ещ[её] (?:смелее|откровенн|больше|дальше)|дальше"
                      r"|продолж|сними ещ[её]|сними что-нибудь")
_TIER_CAP = {"close": 5, "intimate": 6}
_TIER_CAP_DEFAULT = 4


def asked_level(text: str | None) -> int:
    low = (text or "").lower().replace("ё", "е")
    for lvl, rx in _ASK_LEVELS:
        if rx.search(low):
            return lvl
    return 0


def ladder_window(prev_level: int, text: str | None, tier: str = "",
                  max_level: int = 6) -> tuple[int, int]:
    low = (text or "").lower().replace("ё", "е")
    step = prev_level + 1 if prev_level > 0 or _MORE_RX.search(low) else 2
    target = max(asked_level(text), step, 1)
    cap = min(max_level, _TIER_CAP.get(tier, _TIER_CAP_DEFAULT) if tier else max_level)
    if max_level > 6 and tier == "intimate":
        cap = max_level
    target = min(target, cap)
    return max(1, target - 1), target


def sample_ideas(n: int = IDEAS_PER_HINT, *, max_rating: str = "sfw", explicit: bool = False,
                 rng: random.Random | None = None, ideas: list[dict] | None = None,
                 remember: bool = True, marks: dict | None = None,
                 recent_tags=(), ladder: tuple[int, int] | None = None,
                 contact_ok: bool = False) -> list[str]:
    allp = ideas if ideas is not None else load_ideas()
    pool = []
    if explicit and max_rating != "sfw":
        pool = [i for i in allp if i["rating"] != "sfw"
                and (contact_ok or i.get("contact") != "viewer")]
        if ladder is not None:
            lo, hi = ladder
            win = [i for i in pool if lo <= i.get("level", 1) <= hi]
            pool = win or [i for i in pool if i.get("level", 1) <= hi]
    if not pool:
        pool = [i for i in allp if i["rating"] == "sfw"]
    if not pool:
        return []
    avoid = set((marks or {}).get("avoid") or ())
    fits = set((marks or {}).get("fits") or ())
    pool = [i for i in pool if i["id"] not in avoid] or pool
    recent = set(recent_tags or ())
    rng = rng or random.SystemRandom()
    fresh = [i for i in pool if i["id"] not in _RECENT]
    if len(fresh) < n:
        fresh = pool

    def weight(i: dict) -> float:
        w = FIT_WEIGHT if i["id"] in fits else 1.0
        if recent and recent & set(i.get("tags") or ()):
            w *= RECENT_TAG_WEIGHT
        return w
    keyed = sorted(fresh, key=lambda i: rng.random() ** (1.0 / weight(i)), reverse=True)
    picked = keyed[:min(n, len(fresh))]
    if remember:
        _RECENT.extend(i["id"] for i in picked)
    return [i["text"] for i in picked]


GUARD_TAG_NAMES = {
    "sitting": "сидя", "on chair": "на стуле", "on floor": "на полу",
    "on table": "на столе", "on desk": "на столе", "standing": "стоя",
    "leaning forward": "наклон вперёд", "leaning back": "откинувшись назад",
    "head tilt": "наклон головы", "hugging own legs": "обхватив колени",
    "knees to chest": "колени к груди", "crossed legs": "нога на ногу",
    "seiza": "сидя на пятках", "kneeling": "на коленях", "lying": "лёжа",
    "on stomach": "на животе", "on back": "на спине", "on side": "на боку",
    "hand on own cheek": "рука у щеки", "hand on own chin": "рука у подбородка",
    "head rest": "подперев голову", "hands on own knees": "руки на коленях",
    "hands on lap": "руки на коленях", "own hands together": "сложенные руки",
    "own hands clasped": "сцепленные руки", "arms behind back": "руки за спиной",
    "hand on own chest": "рука на груди", "looking to the side": "взгляд в сторону",
    "looking away": "взгляд в сторону", "three-quarter view": "вполоборота",
    "from side": "в профиль", "window": "у окна", "holding cup": "с чашкой",
    "chair": "стул", "desk": "стол", "armchair": "кресло",
}
_GUARD_STOP = frozenset({
    "смотр", "камер", "прямо", "снимо", "кадре", "кадр", "своей", "своем", "своём",
    "форме", "горни", "тебя", "тебе", "слегк", "чуть", "немно", "очень", "которы",
    "будто", "словн", "котор"})
GUARD_INTENT_WORDS = 12


def repeated_details(intents: list[str], min_count: int = 2, limit: int = 3) -> list[str]:
    from collections import Counter
    seen: Counter = Counter()
    forms: dict[tuple, str] = {}
    for text in intents:
        words = re.findall(r"[а-яё]+", (text or "").lower())
        grams = set()
        for a, b in zip(words, words[1:]):
            if len(a) < 4 or len(b) < 4 or a[:5] in _GUARD_STOP or b[:5] in _GUARD_STOP:
                continue
            key = (a[:5], b[:5])
            grams.add(key)
            forms[key] = f"{a} {b}"
        seen.update(grams)
    out, used = [], set()
    for key, v in seen.most_common():
        if v < min_count or len(out) >= limit:
            break
        if used & set(key):
            continue
        used.update(key)
        out.append(forms[key])
    return out


def repeated_tags(tag_lists: list, min_count: int = 2, limit: int = 4) -> list[str]:
    from collections import Counter
    c = Counter(t for tags in tag_lists for t in set(tags or ()) if t in GUARD_TAG_NAMES)
    out: list[str] = []
    for t, v in c.most_common():
        name = GUARD_TAG_NAMES[t]
        if v >= min_count and name not in out and len(out) < limit:
            out.append(name)
    return out


def repeat_guard_line(recent: list[dict]) -> str:
    intents = [str(r.get("intent") or "").strip() for r in recent or ()]
    intents = [t for t in intents if t]
    if not intents:
        return ""
    short = ["«" + " ".join(t.split()[:GUARD_INTENT_WORDS]).rstrip(",.;") + "…»"
             if len(t.split()) > GUARD_INTENT_WORDS else f"«{t.strip().rstrip('.')}»"
             for t in intents]
    rep = repeated_tags([r.get("tags") for r in recent])
    rep += [d for d in repeated_details(intents) if d not in rep][:max(0, 5 - len(rep))]
    return ("Недавние снимки в этом разговоре: " + "; ".join(short) + ". Если просьба "
            "не задаёт кадр, сделай новый непохожим: другая поза, ракурс и что делают руки"
            + (f"; уже повторялось — {', '.join(rep)}, не бери это снова" if rep else "")
            + ".")


def ideas_line(ideas: list[str]) -> str:
    if not ideas:
        return ""
    return ("Идеи для кадра на этот раз: "
            + "; ".join(f"«{t}»" for t in ideas)
            + ". Если просьба не задаёт позу — возьми одну из них за основу, но "
            "впиши в момент (время, настроение, о чём сейчас говорили) и перескажи "
            "своими словами; своя поза — только если ни одна не подходит. Поза и "
            "ракурс — часть intent.")
