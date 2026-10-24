from __future__ import annotations

import hashlib
import json
import os
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from persona import maid_container


CURRENT_FORMAT_VERSION = 1

FEATURE_MEMORY_ENCRYPTION = "memory_encryption"
SUPPORTED_FEATURES = frozenset({FEATURE_MEMORY_ENCRYPTION})


class MaidArchiveError(Exception):
    pass


class NotAMaidFileError(MaidArchiveError):
    pass


class MalformedManifestError(MaidArchiveError):
    pass


class FormatVersionTooNewError(MaidArchiveError):
    pass


class FormatVersionTooOldError(MaidArchiveError):
    def __init__(self, current: int, found: int):
        self.current = current
        self.found = found
        super().__init__(
            f"format_version={found} < current={current} — требуется миграция"
        )


class UnsupportedFeatureError(MaidArchiveError):
    def __init__(self, unknown: list[str]):
        self.unknown = list(unknown)
        super().__init__(
            f"сейв требует возможностей, которых нет в этой версии: "
            f"{', '.join(self.unknown)} — обновите приложение"
        )


class IntegrityError(MaidArchiveError):
    pass


UI_THEME_ENTRY = "ui/UIStructure.json"

UI_THEME_DARK_ENTRY = "ui/UIStructure_dark.json"
UI_LIST_AVATAR_ENTRY = "ui/list_avatar.png"

GALLERY_PREFIX = "gallery/"
GALLERY_INDEX_ENTRY = "gallery/index.json"

_STORED_EXTS = (".png", ".webp", ".jpg", ".jpeg")

CHARACTER_LORE_ENTRY = "lore/entries.yaml"


CHARACTER_EXTS = (".maid", ".butler")


def character_ext(gender: str) -> str:
    return ".butler" if (gender or "").strip().lower() == "male" else ".maid"


def find_character_file(directory: Path, character_id: str) -> Path | None:
    for ext in CHARACTER_EXTS:
        p = directory / f"{character_id}{ext}"
        if p.exists():
            return p
    return None


def iter_character_files(directory: Path) -> list[Path]:
    out: list[Path] = []
    for ext in CHARACTER_EXTS:
        out.extend(directory.glob(f"*{ext}"))
    return sorted(out, key=lambda p: p.name)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class MaidArchive:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.manifest: dict | None = None
        self._entries: dict[str, bytes] = {}
        self._dirty: set[str] = set()
        self._opened: bool = False
        self._partial: bool = False
        self._save_lock = threading.Lock()

    @classmethod
    def open(cls, path: Path | str, *, verify: bool = True) -> "MaidArchive":
        return cls._read(path, wanted=None, verify=verify)

    @classmethod
    def peek(cls, path: Path | str, names, *, verify: bool = True) -> "MaidArchive":
        return cls._read(path, wanted=set(names), verify=verify)

    @classmethod
    def _read(cls, path: Path | str, *, wanted: set[str] | None,
              verify: bool) -> "MaidArchive":
        self = cls(path)
        if not self.path.exists():
            raise FileNotFoundError(f".maid файл не найден: {self.path}")
        try:
            with maid_container.open_zip(self.path) as zf:
                self._load_entries(zf, wanted)
        except maid_container.ContainerError as e:
            raise NotAMaidFileError(f"{self.path.name}: {e}") from e

        self._partial = wanted is not None
        self._validate_manifest_basic()
        self._check_version()
        self._check_features()
        if verify:
            self._verify_checksums()
        self._opened = True
        return self

    def _load_entries(self, zf: zipfile.ZipFile, wanted: set[str] | None) -> None:
        names = set(zf.namelist())
        if "manifest.json" not in names:
            raise MalformedManifestError(
                f"manifest.json отсутствует в {self.path}"
            )
        try:
            manifest_bytes = zf.read("manifest.json")
            self.manifest = json.loads(manifest_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise MalformedManifestError(
                f"manifest.json невалиден: {e}"
            ) from e
        self._entries["manifest.json"] = manifest_bytes
        take = (names - {"manifest.json"}) if wanted is None else (wanted & names)
        for name in take:
            self._entries[name] = zf.read(name)

    @classmethod
    def create(
        cls,
        path: Path | str,
        *,
        character_id: str,
        character_gender: str = "female",
        depicts_adult: bool = True,
        app_version: str = "dev",
    ) -> "MaidArchive":
        self = cls(path)
        now = _now_iso()
        self.manifest = {
            "format": "maid",
            "format_version": CURRENT_FORMAT_VERSION,
            "character_id": character_id,
            "character_gender": character_gender,
            "depicts_adult": depicts_adult,
            "created_at": now,
            "last_saved_at": now,
            "app_version_created": app_version,
            "app_version_last_saved": app_version,
            "applied_migrations": [],
            "signature": None,
            "requires_features": [],
            "memory_encrypted": False,
            "encryption_kdf": None,
            "encryption_kdf_salt": None,
            "entries": {},
        }
        self._opened = True
        self._dirty.add("__init__")
        return self

    def _validate_manifest_basic(self) -> None:
        if not isinstance(self.manifest, dict):
            raise MalformedManifestError("manifest.json — не dict")
        if self.manifest.get("format") != "maid":
            raise NotAMaidFileError(
                f"manifest.format={self.manifest.get('format')!r}, ожидалось 'maid'"
            )
        if "format_version" not in self.manifest:
            raise MalformedManifestError("manifest.format_version отсутствует")
        if "entries" not in self.manifest:
            raise MalformedManifestError("manifest.entries отсутствует")

    def _check_version(self) -> None:
        v = self.manifest["format_version"]
        if v > CURRENT_FORMAT_VERSION:
            raise FormatVersionTooNewError(
                f"format_version={v} > current={CURRENT_FORMAT_VERSION}; "
                "обновите приложение"
            )
        if v < CURRENT_FORMAT_VERSION:
            raise FormatVersionTooOldError(CURRENT_FORMAT_VERSION, v)

    def _check_features(self) -> None:
        raw = self.manifest.get("requires_features") or []
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, (list, tuple)):
            raise MalformedManifestError(
                f"manifest.requires_features — не список: {type(raw).__name__}"
            )
        unknown = [str(f) for f in raw if str(f) not in SUPPORTED_FEATURES]
        if unknown:
            raise UnsupportedFeatureError(unknown)

    def requires_feature(self, feature: str) -> bool:
        raw = (self.manifest or {}).get("requires_features") or []
        if isinstance(raw, str):
            raw = [raw]
        return feature in {str(f) for f in raw}

    def declare_feature(self, feature: str) -> None:
        if feature not in SUPPORTED_FEATURES:
            raise ValueError(f"неизвестная возможность: {feature}")
        raw = list(self.manifest.get("requires_features") or [])
        if feature not in raw:
            raw.append(feature)
            self.manifest["requires_features"] = raw
            self._dirty.add("manifest.json")

    def revoke_feature(self, feature: str) -> None:
        raw = [f for f in (self.manifest.get("requires_features") or [])
               if f != feature]
        self.manifest["requires_features"] = raw
        self._dirty.add("manifest.json")

    def _verify_checksums(self) -> None:
        problems: list[str] = []
        entries_meta: dict = self.manifest.get("entries", {})
        for name, info in entries_meta.items():
            data = self._entries.get(name)
            if data is None:
                if self._partial:
                    continue
                problems.append(f"missing entry: {name}")
                continue
            expected = info.get("sha256")
            actual = _sha256_hex(data)
            if expected != actual:
                problems.append(
                    f"checksum mismatch ({name}): "
                    f"manifest={expected[:8]}… actual={actual[:8]}…"
                )
        if problems:
            raise IntegrityError("\n".join(problems))

    def list_entries(self) -> list[str]:
        return sorted(n for n in self._entries.keys() if n != "manifest.json")

    def has_entry(self, name: str) -> bool:
        return name in self._entries and name != "manifest.json"

    def read_bytes(self, name: str) -> bytes:
        if name == "manifest.json":
            raise KeyError("используй .manifest напрямую для manifest.json")
        if name not in self._entries:
            raise KeyError(f"entry не найден: {name}")
        return self._entries[name]

    def read_text(self, name: str, encoding: str = "utf-8") -> str:
        return self.read_bytes(name).decode(encoding)

    def read_json(self, name: str):
        return json.loads(self.read_text(name))

    def read_yaml(self, name: str):
        return yaml.safe_load(self.read_text(name))

    def read_jsonl(self, name: str) -> list:
        text = self.read_text(name)
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    def write_bytes(self, name: str, data: bytes) -> None:
        if name == "manifest.json":
            raise KeyError("manifest.json пересобирается автоматически при save()")
        self._entries[name] = data
        self._dirty.add(name)

    def write_text(self, name: str, text: str, encoding: str = "utf-8") -> None:
        self.write_bytes(name, text.encode(encoding))

    def write_json(self, name: str, obj, *, indent: int = 2) -> None:
        text = json.dumps(obj, ensure_ascii=False, indent=indent)
        self.write_text(name, text)

    def write_yaml(self, name: str, obj) -> None:
        text = yaml.safe_dump(
            obj, allow_unicode=True, sort_keys=False, default_flow_style=False
        )
        self.write_text(name, text)

    def write_jsonl(self, name: str, records: list) -> None:
        if not records:
            self.write_text(name, "")
            return
        text = "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n"
        self.write_text(name, text)

    def append_memory_record(self, record: dict) -> None:
        existing = self._entries.get("memory.jsonl", b"")
        line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
        self._entries["memory.jsonl"] = existing + line
        self._dirty.add("memory.jsonl")

    def delete_entry(self, name: str) -> None:
        if name == "manifest.json":
            raise KeyError("manifest.json удалять нельзя")
        if name in self._entries:
            del self._entries[name]
            self._dirty.add(name)

    def save(self, *, app_version: str = "dev") -> None:
        if not self._opened or self.manifest is None:
            raise RuntimeError("archive не открыт / не создан")
        if self._partial:
            raise RuntimeError(
                "архив открыт частично (peek) — сохранять нельзя: в памяти не "
                "все entries, запись потеряла бы остальные")

        entries_meta: dict = {}
        for name, data in self._entries.items():
            if name == "manifest.json":
                continue
            entries_meta[name] = {
                "sha256": _sha256_hex(data),
                "size": len(data),
            }

        self.manifest["entries"] = entries_meta
        self.manifest["last_saved_at"] = _now_iso()
        self.manifest["app_version_last_saved"] = app_version
        self.manifest["format_version"] = CURRENT_FORMAT_VERSION

        manifest_bytes = json.dumps(
            self.manifest, ensure_ascii=False, indent=2
        ).encode("utf-8")
        self._entries["manifest.json"] = manifest_bytes

        tmp_path = self.path.with_name(self.path.name + ".new")
        with self._save_lock:
            try:
                zip_bytes = maid_container.write_zip_bytes(
                    [("manifest.json", manifest_bytes, zipfile.ZIP_DEFLATED)]
                    + [(name, self._entries[name],
                        zipfile.ZIP_STORED if name.lower().endswith(_STORED_EXTS)
                        else zipfile.ZIP_DEFLATED)
                       for name in sorted(entries_meta.keys())])
                with open(tmp_path, "wb") as f:
                    f.write(maid_container.seal(zip_bytes))
                os.replace(tmp_path, self.path)
            except Exception:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass
                raise

        self._dirty.clear()

    def close(self) -> None:
        self._opened = False
        self._entries.clear()
        self.manifest = None
        self._dirty.clear()

    def __enter__(self) -> "MaidArchive":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False

    def __repr__(self) -> str:
        if self.manifest is None:
            return f"<MaidArchive {self.path} (not opened)>"
        return (
            f"<MaidArchive {self.path} "
            f"id={self.manifest.get('character_id')!r} "
            f"v{self.manifest.get('format_version')} "
            f"entries={len(self._entries) - 1}>"
        )
