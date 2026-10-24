from __future__ import annotations

import base64
import json
import re
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class StyleError(Exception):
    pass


class StyleCodeError(StyleError):
    pass


class StyleValidationError(StyleError):
    pass


@dataclass(frozen=True)
class StylePack:
    id: str
    name: str
    renderer_id: str
    tags: tuple[str, ...]
    description: str = ""
    author: str = ""
    source: str = "builtin"
    exclude: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict, *, source: str = "builtin") -> "StylePack":
        return cls(
            id=str(data["id"]).strip(),
            name=str(data.get("name", data["id"])).strip(),
            renderer_id=str(data.get("renderer_id", "sdxl")).strip(),
            tags=tuple(str(t).strip() for t in (data.get("tags") or []) if str(t).strip()),
            description=str(data.get("description", "")).strip(),
            author=str(data.get("author", "")).strip(),
            source=source,
            exclude=tuple(str(e).strip().lower()
                          for e in (data.get("exclude") or []) if str(e).strip()),
        )

    def to_payload(self) -> dict:
        out: dict = {
            "id": self.id,
            "name": self.name,
            "renderer_id": self.renderer_id,
            "tags": list(self.tags),
        }
        if self.description:
            out["description"] = self.description
        if self.author:
            out["author"] = self.author
        if self.exclude:
            out["exclude"] = list(self.exclude)
        return out


EMPTY_STYLE = StylePack(
    id="default", name="Без стиля", renderer_id="sdxl", tags=(),
    description="Финальный fallback — стиль не задан", source="builtin",
)


_TAG_CHARS_RE = re.compile(r"^[a-zA-Z0-9_,:.() ]+$")

_FORBIDDEN_TAG_PREFIXES = ("lora:", "embedding:", "<", "break", "and ", "or ")

_ALLOWED_RENDERERS = {"sdxl", "flux", "nai"}

_ID_RE = re.compile(r"^[a-zA-Z0-9_]{1,40}$")
MAX_NAME_LEN = 60
MAX_DESC_LEN = 200
MAX_AUTHOR_LEN = 60

MAX_TAGS = 20
MAX_TAG_LEN = 50
MAX_TOTAL_TAG_CHARS = 500


def validate_pack(pack: StylePack) -> None:
    if not _ID_RE.match(pack.id):
        raise StyleValidationError(
            f"id {pack.id!r} не соответствует [a-zA-Z0-9_] длиной 1-40"
        )
    if len(pack.name) > MAX_NAME_LEN:
        raise StyleValidationError(f"name длиннее {MAX_NAME_LEN}")
    if len(pack.description) > MAX_DESC_LEN:
        raise StyleValidationError(f"description длиннее {MAX_DESC_LEN}")
    if len(pack.author) > MAX_AUTHOR_LEN:
        raise StyleValidationError(f"author длиннее {MAX_AUTHOR_LEN}")
    if pack.renderer_id not in _ALLOWED_RENDERERS:
        raise StyleValidationError(
            f"renderer_id {pack.renderer_id!r} не в whitelist {sorted(_ALLOWED_RENDERERS)}"
        )
    if len(pack.tags) > MAX_TAGS:
        raise StyleValidationError(
            f"слишком много тегов: {len(pack.tags)} > {MAX_TAGS}"
        )

    total_chars = 0
    for tag in pack.tags:
        if not tag:
            raise StyleValidationError("пустой тег")
        if len(tag) > MAX_TAG_LEN:
            raise StyleValidationError(
                f"тег {tag!r} длиннее {MAX_TAG_LEN}"
            )
        if not _TAG_CHARS_RE.match(tag):
            raise StyleValidationError(
                f"тег {tag!r} содержит запрещённые символы "
                f"(разрешены: a-z A-Z 0-9 _ , : ( ) пробел)"
            )
        low = tag.lower()
        for forbidden in _FORBIDDEN_TAG_PREFIXES:
            if low.startswith(forbidden):
                raise StyleValidationError(
                    f"тег {tag!r} начинается с запрещённого {forbidden!r}"
                )
        total_chars += len(tag)
    if total_chars > MAX_TOTAL_TAG_CHARS:
        raise StyleValidationError(
            f"суммарная длина тегов {total_chars} > {MAX_TOTAL_TAG_CHARS}"
        )


CODE_PREFIX = "artstyle:v1:"


def encode_pack(pack: StylePack) -> str:
    validate_pack(pack)
    raw = json.dumps(
        pack.to_payload(), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    compressed = zlib.compress(raw, level=9)
    b64 = base64.urlsafe_b64encode(compressed).decode("ascii").rstrip("=")
    return f"{CODE_PREFIX}{b64}"


def decode_pack(code: str) -> StylePack:
    code = (code or "").strip()
    if not code.startswith(CODE_PREFIX):
        raise StyleCodeError(
            f"код должен начинаться с {CODE_PREFIX!r}; получено: {code[:30]!r}"
        )
    b64 = code[len(CODE_PREFIX):]
    if not b64:
        raise StyleCodeError("после префикса нет payload")

    padding = "=" * ((4 - len(b64) % 4) % 4)
    try:
        compressed = base64.urlsafe_b64decode(b64 + padding)
    except Exception as e:
        raise StyleCodeError(f"не могу распарсить base64: {e}") from e

    try:
        raw = zlib.decompress(compressed)
    except zlib.error as e:
        raise StyleCodeError(f"не могу распаковать zlib: {e}") from e

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise StyleCodeError(f"payload не валидный JSON: {e}") from e
    if not isinstance(payload, dict):
        raise StyleCodeError("payload — не объект")

    if "id" not in payload or "tags" not in payload:
        raise StyleCodeError("payload без обязательных полей id/tags")

    pack = StylePack.from_dict(payload, source="user_imported")
    validate_pack(pack)
    return pack


class StyleCatalog:
    def __init__(
        self,
        builtin_yaml: Path | str,
        user_dir: Path | str | None = None,
    ):
        self.builtin_yaml = Path(builtin_yaml)
        self.user_dir = Path(user_dir) if user_dir else None
        self._packs: dict[str, StylePack] = {}
        self._builtin: dict[str, StylePack] = {}
        self.errors: list[str] = []
        self._load_builtin()
        if self.user_dir is not None:
            self._load_user()

    def _load_builtin(self) -> None:
        if not self.builtin_yaml.exists():
            self.errors.append(f"builtin yaml not found: {self.builtin_yaml}")
            return
        try:
            data = yaml.safe_load(self.builtin_yaml.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            self.errors.append(f"builtin yaml broken: {e}")
            return
        for entry in (data.get("styles") or []):
            if not isinstance(entry, dict):
                continue
            try:
                pack = StylePack.from_dict(entry, source="builtin")
                validate_pack(pack)
            except (StyleError, KeyError) as e:
                self.errors.append(
                    f"builtin '{entry.get('id', '?')}': {type(e).__name__}: {e}"
                )
                continue
            self._packs[pack.id] = pack
            self._builtin[pack.id] = pack

    def _load_user(self) -> None:
        if not self.user_dir.exists():
            return
        for path in sorted(self.user_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                pack = StylePack.from_dict(data, source="user_imported")
                validate_pack(pack)
            except (StyleError, yaml.YAMLError, KeyError) as e:
                self.errors.append(f"user {path.name}: {type(e).__name__}: {e}")
                continue
            self._packs[pack.id] = pack

    def get(self, style_id: str) -> StylePack | None:
        return self._packs.get(style_id)

    def list_all(self) -> list[StylePack]:
        return sorted(
            self._packs.values(),
            key=lambda p: (0 if p.source == "user_imported" else 1, p.id),
        )

    def import_code(self, code: str) -> StylePack:
        if self.user_dir is None:
            raise RuntimeError(
                "StyleCatalog создан без user_dir — импорт невозможен"
            )
        pack = decode_pack(code)
        self.user_dir.mkdir(parents=True, exist_ok=True)
        path = self.user_dir / f"{pack.id}.yaml"
        path.write_text(
            yaml.safe_dump(
                pack.to_payload(),
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        self._packs[pack.id] = pack
        return pack

    def remove_user(self, style_id: str) -> StylePack:
        pack = self._packs.get(style_id)
        if pack is None:
            raise StyleError(f"стиль {style_id!r} не найден")
        if pack.source != "user_imported":
            raise StyleError("встроенный стиль удалить нельзя")
        if self.user_dir is not None and self.user_dir.exists():
            for path in sorted(self.user_dir.glob("*.yaml")):
                try:
                    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                except (OSError, yaml.YAMLError):
                    continue
                if isinstance(data, dict) and str(data.get("id", "")) == style_id:
                    path.unlink()
        del self._packs[style_id]
        if style_id in self._builtin:
            self._packs[style_id] = self._builtin[style_id]
        return pack

    def resolve(
        self,
        *,
        active_style_id: str | None,
        character_override_id: str | None = None,
        renderer_id: str = "sdxl",
    ) -> StylePack:
        candidates: list[str] = []
        if active_style_id and active_style_id != "default":
            candidates.append(active_style_id)
        if character_override_id:
            candidates.append(character_override_id)
        candidates.append("default")

        for sid in candidates:
            pack = self._packs.get(sid)
            if pack is not None and pack.renderer_id == renderer_id:
                return pack
        return EMPTY_STYLE
