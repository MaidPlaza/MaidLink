from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from services.nsfw_extra import CONTENT_KEY, CODE_ENTRY, SEPARATOR
CODEBOOK_FILE = "codebook.yaml"
DEFAULT_FILE = "_default"

LAYERS = ("figure", "chest", "groin")


@dataclass(frozen=True)
class AnatomyProfile:
    figure: tuple[str, ...] = ()
    chest: tuple[str, ...] = ()
    groin: tuple[str, ...] = ()
    negative: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return not (self.figure or self.chest or self.groin or self.negative)


EMPTY = AnatomyProfile()


@dataclass(frozen=True)
class Codebook:
    version: int
    by_code: dict[str, tuple[str, str]]
    by_tag: dict[str, str]
    order: dict[str, int]
    base: dict[str, tuple[str, ...]] = field(default_factory=dict)
    anchors: dict[str, str] = field(default_factory=dict)
    desc: dict[str, str] = field(default_factory=dict)
    trigger_rx: object | None = None
    window: int = 4

    def layer_of(self, tag: str) -> str | None:
        code = self.by_tag.get(tag)
        return self.by_code[code][0] if code else None

    def base_tags(self, layer: str, *, gender: str = "female") -> tuple[str, ...]:
        if layer == "groin" and gender == "male":
            return self.base.get("groin_male") or self.base.get("groin") or ()
        return self.base.get(layer) or ()

    def is_base(self, tag: str) -> bool:
        return any(tag in v for v in self.base.values())

    def all_base(self) -> set[str]:
        return {t for v in self.base.values() for t in v}

    def mentions_body(self, *texts) -> bool:
        if self.trigger_rx is None:
            return False
        for t in texts:
            if t and self.trigger_rx.search(str(t).lower().replace("ё", "е")):
                return True
        return False


def _anatomy_dirs(project_root: Path, *, enabled_only: bool = True) -> list[Path]:
    from services import addons
    if enabled_only:
        return addons.content_dirs(project_root, CONTENT_KEY)
    out: list[Path] = []
    for a in addons.discover(project_root):
        rel = a.content.get(CONTENT_KEY)
        if rel and a.root is not None and (a.root / rel).exists():
            out.append(a.root / rel)
    return out


_CACHE: dict[tuple, Codebook | None] = {}


def codebook(project_root: Path, *, enabled_only: bool = True) -> Codebook | None:
    paths = [d / CODEBOOK_FILE
             for d in _anatomy_dirs(project_root, enabled_only=enabled_only)]
    paths = [p for p in paths if p.is_file()]
    if not paths:
        return None
    key = tuple((str(p), p.stat().st_mtime_ns) for p in paths)
    if key in _CACHE:
        return _CACHE[key]
    book = _parse_codebook(paths[-1])
    _CACHE[key] = book
    return book


def _parse_codebook(path: Path) -> Codebook | None:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        print(f"[anatomy] кодовая книга не прочитана ({path.name}): {e}")
        return None
    if not isinstance(data, dict):
        return None
    by_code: dict[str, tuple[str, str]] = {}
    by_tag: dict[str, str] = {}
    order: dict[str, int] = {}
    desc: dict[str, str] = {}
    for layer in LAYERS:
        for item in data.get(layer) or ():
            code, _, rest = str(item).strip().partition(" ")
            tag, _, human = rest.partition("|")
            code, tag, human = code.strip(), tag.strip(), human.strip()
            if not code or not tag:
                continue
            if human:
                desc[tag] = human
            if code in by_code:
                print(f"[anatomy] дубль кода «{code}» в книге — пропущен")
                continue
            by_code[code] = (layer, tag)
            by_tag[tag] = code
            order[tag] = len(order)
    if not by_code:
        return None
    try:
        version = int(data.get("version") or 1)
    except Exception:
        version = 1
    base: dict[str, tuple[str, ...]] = {}
    for key, tags in (data.get("base") or {}).items():
        vals = tuple(str(t).strip() for t in (tags or ()) if str(t).strip())
        unknown = [t for t in vals if t not in by_tag]
        if unknown:
            print(f"[anatomy] base.{key}: нет в книге — {unknown}")
        base[str(key).strip()] = tuple(t for t in vals if t in by_tag)
    anchors = {str(k).strip(): str(v).strip()
               for k, v in (data.get("anchors") or {}).items()
               if str(k).strip() in by_tag and str(v).strip() in by_tag}
    trig = data.get("triggers") or {}
    stems = [str(x).strip().lower().replace("ё", "е")
             for x in (trig.get("stems") or []) if str(x).strip()]
    rx = None
    if stems:
        parts = [re.escape(st[:-1]) + r"\b" if st.endswith("$")
                 else re.escape(st) for st in stems]
        rx = re.compile(r"\b(?:" + "|".join(parts) + ")")
    try:
        window = max(1, int(trig.get("window") or 4))
    except Exception:
        window = 4
    return Codebook(version=version, by_code=by_code, by_tag=by_tag,
                    order=order, base=base, anchors=anchors, desc=desc,
                    trigger_rx=rx, window=window)


def decode(code: str, book: Codebook | None, *,
           gender: str = "female") -> AnatomyProfile:
    if book is None:
        return EMPTY
    code = (code or "").strip()
    if not code:
        return EMPTY
    if code[0] != str(book.version):
        print(f"[anatomy] код версии «{code[0]}», книга версии {book.version} — "
              f"пропущен")
        return EMPTY
    body = code[1:]
    _seg = body.split(SEPARATOR)
    pos = _seg[0] if _seg else ""
    neg = _seg[1] if len(_seg) > 1 else ""
    sep = len(_seg) > 1
    buckets: dict[str, list[str]] = {k: [] for k in LAYERS + ("negative",)}
    for chunk, forced in ((pos, None), (neg if sep else "", "negative")):
        if len(chunk) % 2:
            print(f"[anatomy] нечётная длина участка кода «{chunk}» — пропущен")
            continue
        for i in range(0, len(chunk), 2):
            pair = chunk[i:i + 2]
            known = book.by_code.get(pair)
            if known is None:
                print(f"[anatomy] неизвестная пара «{pair}» — пропущена")
                continue
            layer, tag = known
            buckets[forced or layer].append(tag)
    return _profile(buckets, book, gender=gender)


def encode(layers: dict, book: Codebook) -> str:
    pos: list[str] = []
    neg: list[str] = []
    anchors_only = set(book.anchors.values())
    for layer in LAYERS:
        for tag in layers.get(layer) or ():
            tag = str(tag).strip()
            code = book.by_tag.get(tag)
            if code is None:
                raise KeyError(f"тега «{tag}» нет в кодовой книге")
            if book.is_base(tag):
                raise ValueError(
                    f"«{tag}» — индикатор видимости, а не особенность: он идёт "
                    f"всем автоматически, убери из набора персонажа")
            if tag in anchors_only:
                raise ValueError(
                    f"«{tag}» — якорь особенности: его ставит сама особенность "
                    f"(см. anchors в книге), убери из набора персонажа")
            if book.by_code[code][0] != layer:
                raise ValueError(
                    f"«{tag}» — слой «{book.by_code[code][0]}», а записан в "
                    f"«{layer}»: слой задаёт книга, не файл персонажа")
            pos.append(code)
    for tag in layers.get("negative") or ():
        tag = str(tag).strip()
        code = book.by_tag.get(tag)
        if code is None:
            raise KeyError(f"тега «{tag}» нет в кодовой книге")
        neg.append(code)
    return f"{book.version}{''.join(pos)}{SEPARATOR}{''.join(neg)}"


_MALE_WORDS = frozenset({"penis", "foreskin", "testicles"})
_MALE_EXACT = frozenset({"male pubic hair"})


def _looks_male(tags) -> bool:
    for t in tags:
        t = str(t).strip().lower()
        if t in _MALE_EXACT or (_MALE_WORDS & set(t.split())):
            return True
    return False


def _profile(buckets: dict[str, list[str]], book: Codebook, *,
             gender: str = "female") -> AnatomyProfile:
    if gender != "male" and _looks_male(buckets.get("groin") or ()):
        gender = "male"

    def fix(key: str) -> tuple[str, ...]:
        vals = list(buckets.get(key) or ())
        if key != "negative":
            vals += list(book.base_tags(key, gender=gender))
            for t in list(vals):
                anchor = book.anchors.get(t)
                if anchor and book.layer_of(anchor) == key:
                    vals.append(anchor)
        seen, out = set(), []
        for t in sorted(vals, key=lambda x: book.order.get(x, 10_000)):
            if t.lower() in seen:
                continue
            seen.add(t.lower())
            out.append(t)
        return tuple(out)
    return AnatomyProfile(figure=fix("figure"), chest=fix("chest"),
                          groin=fix("groin"), negative=fix("negative"))


def _merge(base: dict, extra: dict) -> None:
    for key in LAYERS + ("negative",):
        add = extra.get(key)
        if add:
            base.setdefault(key, []).extend(str(t).strip() for t in add
                                            if str(t).strip())


def _from_default(project_root: Path, book: Codebook, *, gender: str,
                  appearance_tags) -> AnatomyProfile:
    rules: dict = {}
    for d in _anatomy_dirs(project_root):
        p = d / f"{DEFAULT_FILE}.yaml"
        if p.is_file():
            try:
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception as e:
                print(f"[anatomy] фолбэк не прочитан ({p.name}): {e}")
                continue
            if isinstance(data, dict):
                rules = data
    branch = rules.get(gender) or rules.get("female") or {}
    if not isinstance(branch, dict):
        return EMPTY
    acc: dict = {}
    _merge(acc, branch.get("base") or {})
    by_tag = branch.get("by_tag") or {}
    if isinstance(by_tag, dict):
        have = {str(t).strip().lower() for t in (appearance_tags or ())}
        for tag, layers in by_tag.items():
            if str(tag).strip().lower() in have and isinstance(layers, dict):
                _merge(acc, layers)
    buckets: dict[str, list[str]] = {k: [] for k in LAYERS + ("negative",)}
    for key, tags in acc.items():
        for t in tags:
            if key == "negative":
                buckets["negative"].append(t)
                continue
            layer = book.layer_of(t)
            if layer is None:
                print(f"[anatomy] фолбэк: тега «{t}» нет в книге — пропущен")
                continue
            buckets[layer].append(t)
    return _profile(buckets, book, gender=gender)


def profile_for(project_root: Path, *, anatomy_code: str = "",
                gender: str = "female", appearance_tags=()) -> AnatomyProfile:
    book = codebook(project_root)
    if book is None:
        return EMPTY
    gender = (gender or "female").strip().lower()
    if (anatomy_code or "").strip():
        p = decode(anatomy_code, book, gender=gender)
        if not p.is_empty():
            return p
    return _from_default(project_root, book, gender=gender,
                         appearance_tags=appearance_tags)


def positive_tags(profile: AnatomyProfile | None, *, bare) -> list[str]:
    if profile is None or profile.is_empty():
        return []
    bare = set(bare or ())
    out = list(profile.figure)
    if "top" in bare:
        out += list(profile.chest)
    if "bottom" in bare:
        out += list(profile.groin)
    return out


_LAYER_TITLE = {"figure": "Фигура", "chest": "Грудь", "groin": "Ниже пояса"}


def describe(profile: AnatomyProfile | None, book: Codebook | None) -> str:
    if profile is None or book is None or profile.is_empty():
        return ""
    lines: list[str] = []
    for layer in LAYERS:
        vals = [book.desc[t] for t in getattr(profile, layer)
                if t in book.desc]
        if vals:
            lines.append(f"{_LAYER_TITLE[layer]}: {'; '.join(vals)}.")
    if not lines:
        return ""
    return ("<твоё_тело>\n"
            "Так ты выглядишь без одежды. Это знание о себе, а не тема для "
            "разговора: упоминай, только когда к слову.\n"
            + "\n".join(lines) + "\n</твоё_тело>")


def negative_tags(profile: AnatomyProfile | None) -> list[str]:
    if profile is None or profile.is_empty():
        return []
    return list(profile.negative)
