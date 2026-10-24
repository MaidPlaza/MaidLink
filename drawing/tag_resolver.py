from __future__ import annotations

import json
import re
import threading

from app_paths import ASSETS_ROOT, PROJECT_ROOT

_INDEX_PATH = ASSETS_ROOT / "drawing" / "danbooru_tags" / "tag_index.json"
_VEC_CACHE = PROJECT_ROOT / "data" / "tag_index_vecs.npz"

SIM_THRESHOLD = 0.74

_NSFW_WORDS = frozenset({
    "nude", "naked", "sex", "penis", "pussy", "vagina", "vaginal", "anal",
    "anus", "nipple", "nipples", "areolae", "cum", "semen", "orgasm",
    "fellatio", "cunnilingus", "paizuri", "irrumatio", "handjob", "footjob",
    "gangbang", "rape", "bukkake", "creampie", "topless", "bottomless",
    "underwear", "panties", "bra", "lingerie", "thong", "dildo", "vibrator",
    "bondage", "shibari", "bdsm", "hentai", "erection", "futanari",
    "pantyshot", "cameltoe", "undressing", "nsfw",
})
_NSFW_STEMS = ("masturbat", "penetrat", "ejaculat", "fondl", "grop")

_EXPLICIT_WORDS = frozenset({
    "nude", "naked", "sex", "penis", "pussy", "vagina", "vaginal", "anal",
    "anus", "nipple", "nipples", "areolae", "cum", "semen", "orgasm",
    "fellatio", "cunnilingus", "paizuri", "irrumatio", "handjob", "footjob",
    "gangbang", "rape", "bukkake", "creampie", "topless", "bottomless",
    "dildo", "vibrator", "erection", "futanari", "hentai",
})
_EXPLICIT_STEMS = ("masturbat", "penetrat", "ejaculat")

_WORD_RE = re.compile(r"[a-z0-9']+")


def _norm(tag: str) -> str:
    return " ".join((tag or "").lower().replace("_", " ").split())


def _sfw_ok(tag: str) -> bool:
    t = _norm(tag)
    if any(stem in t for stem in _NSFW_STEMS):
        return False
    return not any(w in _NSFW_WORDS for w in _WORD_RE.findall(t))


def explicit_by_words(tag: str) -> bool:
    t = _norm(tag)
    if any(stem in t for stem in _EXPLICIT_STEMS):
        return True
    return any(w in _EXPLICIT_WORDS for w in _WORD_RE.findall(t))


_EN_COLORS = frozenset({
    "red", "blue", "green", "yellow", "black", "white", "pink", "purple",
    "orange", "brown", "grey", "gray", "aqua", "teal", "navy", "beige",
    "cream", "crimson", "gold", "golden", "silver", "blonde", "magenta",
    "cyan", "azure", "tan", "ivory", "dark", "light", "pale",
    "pearl", "lace", "velvet", "silk", "satin", "leather", "fishnet",
})
_RU_COLOR_RULES: tuple[tuple[str, str], ...] = (
    ("серебр", "silver"), ("золот", "gold"), ("красн", "red"),
    ("бордов", "crimson"), ("розов", "pink"), ("оранжев", "orange"),
    ("желт", "yellow"), ("жёлт", "yellow"), ("зелен", "green"),
    ("зелён", "green"), ("голуб", "light blue"), ("син", "blue"),
    ("фиолетов", "purple"), ("лилов", "purple"), ("пурпурн", "purple"),
    ("сиренев", "purple"), ("черн", "black"), ("чёрн", "black"),
    ("бел", "white"), ("коричнев", "brown"), ("бежев", "beige"),
    ("кремов", "cream"), ("бирюзов", "teal"),
    ("жемчужн", "pearl"), ("кружевн", "lace"), ("бархатн", "velvet"),
    ("шёлков", "silk"), ("шелков", "silk"),
)
_RU_ADJ_END = re.compile(
    r"(ый|ая|ое|ые|ой|ого|ому|ым|ыми|их|им|ий|яя|ее|ей|его|ему|ую|юю|ие|ими)$")
_RU_WORD_END = re.compile(
    r"^(|а|я|о|е|ё|ы|и|у|ю|ой|ей|ёй|ах|ях|ам|ям|ами|ями|ов|ев|ёв|ик|ика|"
    r"ики|иков|иком|ью|ье|ья|ок|ках|ки|ку|кой|"
    r"ый|ая|ое|ые|ого|ому|ым|ыми|их|им|ий|яя|ее|его|ему|ую|юю)$")
_RU_SHADE = {"темно": "dark", "тёмно": "dark", "светло": "light",
             "бледно": "pale"}

_RU_CORE_RULES: tuple[tuple[str, str], ...] = (
    ("помад", "lipstick"), ("серьг", "earrings"), ("сережк", "earrings"),
    ("серёжк", "earrings"), ("лент", "ribbon"), ("бант", "bow"),
    ("ожерель", "necklace"), ("колье", "necklace"), ("кулон", "pendant"),
    ("браслет", "bracelet"), ("кольц", "ring"), ("заколк", "hairclip"),
    ("шпильк", "hair ornament"), ("чокер", "choker"), ("диадем", "tiara"),
    ("корон", "crown"), ("вуал", "veil"), ("очк", "glasses"),
    ("подводк", "eyeliner"), ("тушь", "mascara"), ("туш", "mascara"),
    ("тен", "eyeshadow"), ("маникюр", "nail polish"),
    ("зонт", "umbrella"), ("веер", "hand fan"), ("пирсинг", "piercing"),
    ("хвостик", "ponytail"), ("хвост", "ponytail"),
    ("косичк", "braid"), ("кос", "braid"), ("пучк", "hair bun"),
    ("пучок", "hair bun"), ("ободк", "hairband"), ("ободок", "hairband"),
    ("чёлк", ("bangs", "blunt bangs")), ("челк", ("bangs", "blunt bangs")),
    ("кудр", "curly hair"),
    ("волнист", "wavy hair"), ("прям", "straight hair"),
    ("распущенн", "hair down"), ("распущен", "hair down"), ("распуст", "hair down"),
    ("пробор", "parted bangs"), ("растрёпан", "messy hair"),
    ("растрепан", "messy hair"), ("пушист", "fluffy hair"),
    ("локон", "wavy hair"), ("бус", "bead necklace"),
    ("бель", "lingerie"), ("трусик", "panties"), ("стринг", "thong"),
    ("лифчик", "bra"),
    ("бюстгальтер", "bra"), ("пеньюар", "negligee"),
    ("подвязк", "garter belt"), ("ошейник", "collar"),
    ("цветок", "flower"), ("цветк", "flower"), ("цветоч", "flower"),
)
_RU_NOUN_END = re.compile(
    r"^(|а|я|о|е|ё|ы|и|у|ю|ой|ей|ёй|ах|ях|ам|ям|ами|ями|ов|ев|ёв|ик|ика|"
    r"ики|иков|иком|ью|ье|ья|ок|ках|ки|ку|кой)$")
_RU_CORE_BLACKLIST = frozenset({"лакей", "лакея", "теннис"})
_RU_TWIN_FORMS = frozenset({"хвостики", "хвостиков", "хвостиками", "хвостика"})


_RU_PAIR_WORDS = frozenset({"две", "два", "пара", "двойные", "двойной"})
_PAIR_VARIANT = {"braid": "twin braids", "ponytail": "twintails"}


def _ru_core_to_en(core: str) -> list[str]:
    words = core.split()
    if not words:
        return []
    cands: list[str] = []
    best_len = -1
    for w in words:
        if w in _RU_CORE_BLACKLIST:
            return []
        if w in _RU_TWIN_FORMS and best_len < 99:
            cands, best_len = ["twintails"], 99
            continue
        for stem, cand in _RU_CORE_RULES:
            if (len(stem) > best_len and w.startswith(stem)
                    and _RU_WORD_END.match(w[len(stem):])):
                cands = [cand] if isinstance(cand, str) else list(cand)
                best_len = len(stem)
    if not cands:
        return []
    if any(w in _RU_PAIR_WORDS for w in words):
        cands = [_PAIR_VARIANT.get(c, c) for c in cands]
    rest = " ".join(words[1:])
    if rest in ("в волосах", "для волос", "на волосах"):
        cands = [f"hair {c}" for c in cands] + cands
    return cands


def _color_of_word(word: str) -> str | None:
    if word in _EN_COLORS:
        return word
    if not _RU_ADJ_END.search(word):
        return None
    for stem, en in _RU_COLOR_RULES:
        if word.startswith(stem):
            return en
    return None


def ru_candidates(text: str) -> list[str]:
    color, core = split_color_prefix(_norm(text))
    cands = _ru_core_to_en(core)
    return [f"{color} {c}" for c in cands] + cands if color else cands


def split_color_prefix(tag: str) -> tuple[str | None, str]:
    t = _norm(tag)
    words = t.split()
    if len(words) < 2:
        return None, t
    first = words[0]
    shade = ""
    if "-" in first:
        pre, _, rest_word = first.partition("-")
        if pre in _RU_SHADE:
            shade, first = _RU_SHADE[pre] + " ", rest_word
    color = _color_of_word(first)
    if color is None:
        return None, t
    return (shade + color).strip(), " ".join(words[1:])


def _default_embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    try:
        import httpx
        from config import EmbedderConfig
        from services import child_auth
        url = EmbedderConfig().base_url
        r = httpx.post(f"{url}/v1/embeddings", json={"input": texts}, timeout=60.0,
                       headers=child_auth.headers(child_auth.LLAMA))
        r.raise_for_status()
        data = sorted(r.json().get("data", []), key=lambda d: d.get("index", 0))
        return [d.get("embedding", []) for d in data]
    except Exception:
        return []


class TagResolver:
    def __init__(self, embed_fn=None, index_path=None, vec_cache=None):
        self._embed = embed_fn or _default_embed
        self._index_path = index_path or _INDEX_PATH
        self._vec_cache = vec_cache or _VEC_CACHE
        self._index: dict[str, int] | None = None
        self._tags: list[str] | None = None
        self._vecs = None
        self._vec_lock = threading.Lock()
        self._vec_building = False

    def _load_index(self) -> dict[str, int]:
        if self._index is None:
            try:
                raw = json.loads(self._index_path.read_text(encoding="utf-8"))
                self._index = {_norm(k): int(v)
                               for k, v in (raw.get("tags") or {}).items()}
            except Exception as e:
                print(f"[resolver] index unreadable ({type(e).__name__}: {e}) "
                      f"- tag rescue disabled")
                self._index = {}
        return self._index

    @property
    def available(self) -> bool:
        return bool(self._load_index())

    def _vectors_ready(self) -> bool:
        return self._vecs is not None

    def _try_load_cache(self, n_expected: int) -> bool:
        try:
            import numpy as np
            data = np.load(self._vec_cache, allow_pickle=False)
            tags = [str(t) for t in data["tags"]]
            vecs = data["vecs"].astype("float32")
            if len(tags) != n_expected or vecs.shape[0] != n_expected:
                return False
            self._tags, self._vecs = tags, vecs
            return True
        except Exception:
            return False

    def _build_vectors(self):
        try:
            import numpy as np
            index = self._load_index()
            tags = list(index.keys())
            if not tags:
                return
            if self._try_load_cache(len(tags)):
                print(f"[resolver] vectors from cache: {len(tags)}")
                return
            vecs: list[list[float]] = []
            CHUNK = 128
            for i in range(0, len(tags), CHUNK):
                out = self._embed(tags[i:i + CHUNK])
                if len(out) != len(tags[i:i + CHUNK]) or not out or not out[0]:
                    print("[resolver] embedder unavailable - vectors postponed")
                    return
                vecs.extend(out)
            m = np.asarray(vecs, dtype="float32")
            m /= (np.linalg.norm(m, axis=1, keepdims=True) + 1e-8)
            try:
                self._vec_cache.parent.mkdir(parents=True, exist_ok=True)
                np.savez_compressed(self._vec_cache,
                                    tags=np.array(tags), vecs=m.astype("float16"))
            except Exception:
                pass
            self._tags, self._vecs = tags, m
            print(f"[resolver] vectors built: {len(tags)}")
        finally:
            self._vec_building = False

    def ensure_vectors_async(self):
        if self._vectors_ready() or not self.available:
            return
        with self._vec_lock:
            if self._vec_building:
                return
            self._vec_building = True
        threading.Thread(target=self._build_vectors,
                         name="tag-resolver-vecs", daemon=True).start()

    def _gate(self, tag: str, allow_nsfw: bool) -> bool:
        return allow_nsfw or _sfw_ok(tag)

    def extract_from_text(self, text: str, *, allow_nsfw: bool,
                          max_words: int = 4) -> list[str]:
        index = self._load_index()
        if not index or not text:
            return []
        words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'-]*", text)]
        if not words:
            return []
        found: list[str] = []
        used = [False] * len(words)
        for size in range(min(max_words, len(words)), 0, -1):
            for i in range(0, len(words) - size + 1):
                if any(used[i:i + size]):
                    continue
                cand = _norm(" ".join(words[i:i + size]))
                if cand in index and self._gate(cand, allow_nsfw):
                    if cand not in found:
                        found.append(cand)
                    for j in range(i, i + size):
                        used[j] = True
        return found

    def resolve_many(self, raw_tags, *, allow_nsfw: bool) -> dict[str, str | None]:
        index = self._load_index()
        out: dict[str, str | None] = {}
        if not index:
            return {t: None for t in raw_tags}
        pending: list[str] = []
        colors: dict[str, str] = {}
        for raw in raw_tags:
            t = _norm(raw)
            if not t:
                out[raw] = None
                continue
            if t in index:
                out[raw] = t if self._gate(t, allow_nsfw) else None
                continue
            color, core = split_color_prefix(t)
            ru_en = next((c for c in _ru_core_to_en(core) if c in index), None)
            if ru_en is not None:
                if self._gate(ru_en, allow_nsfw):
                    out[raw] = f"{color} {ru_en}" if color else ru_en
                else:
                    out[raw] = None
                continue
            if color:
                if core in index:
                    ok = self._gate(core, allow_nsfw)
                    out[raw] = f"{color} {core}" if ok else None
                    continue
                colors[raw] = color
                pending.append(core)
            else:
                pending.append(raw)
        if not pending:
            return out
        raw_of = {i: r for i, r in enumerate(
            [r for r in raw_tags if r not in out])}
        if not self._vectors_ready():
            self.ensure_vectors_async()
            out.update({r: None for r in raw_of.values()})
            return out
        try:
            import numpy as np
            q = self._embed([_norm(t) for t in pending])
            if len(q) != len(pending) or not q or not q[0]:
                out.update({r: None for r in raw_of.values()})
                return out
            qm = np.asarray(q, dtype="float32")
            qm /= (np.linalg.norm(qm, axis=1, keepdims=True) + 1e-8)
            sims = qm @ self._vecs.T
            for i, row in enumerate(sims):
                raw = raw_of[i]
                best = int(row.argmax())
                cand = self._tags[best]
                ok = row[best] >= SIM_THRESHOLD and self._gate(cand, allow_nsfw)
                if not ok:
                    out[raw] = None
                    continue
                color = colors.get(raw)
                out[raw] = f"{color} {cand}" if color else cand
        except Exception as e:
            print(f"[resolver] embed layer: {type(e).__name__}: {e}")
            out.update({r: None for r in raw_of.values()})
        return out


_RESOLVER: TagResolver | None = None


def get_resolver() -> TagResolver:
    global _RESOLVER
    if _RESOLVER is None:
        _RESOLVER = TagResolver()
    return _RESOLVER
