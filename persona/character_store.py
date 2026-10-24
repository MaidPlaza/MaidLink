from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

from persona import crypto
from persona.character import CURRENT_GENERATION, Character, registry_number
from persona.evolution import CharacterIdentity
from persona.maid_archive import (
    CHARACTER_EXTS, FEATURE_MEMORY_ENCRYPTION, MaidArchive, MaidArchiveError,
    UI_LIST_AVATAR_ENTRY, UI_THEME_DARK_ENTRY, UI_THEME_ENTRY,
    character_ext, find_character_file, iter_character_files,
)


class CharacterNotFoundError(KeyError):
    pass


class CharacterLockedError(Exception):
    def __init__(self, character_id: str):
        self.character_id = character_id
        super().__init__(f"{character_id}: персонаж защищён паролем")


class CharacterStore:
    def __init__(
        self,
        characters_dir: Path | str,
        baseline_dir: Path | str | None = None,
        runtime_cache_dir: Path | str | None = None,
        *,
        app_version: str = "dev",
    ):
        self.characters_dir = Path(characters_dir)
        self.baseline_dir = Path(baseline_dir) if baseline_dir else None
        self.runtime_cache_dir = (
            Path(runtime_cache_dir) if runtime_cache_dir else None
        )
        self.app_version = app_version

        self._archives: dict[str, MaidArchive] = {}
        self._showcase: dict[Path, tuple[tuple[int, int], dict]] = {}
        self._memory_records: dict[str, list[dict]] = {}
        self._deks: dict[str, bytes] = {}
        self._identities: dict[str, CharacterIdentity] = {}
        self.pending_renames: list[tuple[str, str]] = []

    VISUAL_AVATAR_ENTRY = "visual/avatar_chat.png"
    VISUAL_PORTRAIT_PREFIX = "visual/portraits/"

    def _extract_visual_assets(self, archive: MaidArchive, character_id: str) -> None:
        vdir = self.characters_dir / character_id
        pairs = [
            (self.VISUAL_PORTRAIT_PREFIX + "default.png", vdir / "portrait_default.png"),
            (self.VISUAL_AVATAR_ENTRY, vdir / "avatar_chat.png"),
        ]
        prefix = self.VISUAL_PORTRAIT_PREFIX
        for entry in archive.list_entries():
            if not (entry.startswith(prefix) and entry.endswith(".png")):
                continue
            key = entry[len(prefix):-len(".png")]
            if not key or key == "default" or key.startswith("default_"):
                continue
            pairs.append((entry, vdir / f"portrait_{key}.png"))
        for entry, dst in pairs:
            if dst.exists() or not archive.has_entry(entry):
                continue
            vdir.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(archive.read_bytes(entry))
            print(f"[store] {character_id}: распакован {entry} → {dst.name}")

    _INSTANCE_ID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

    @classmethod
    def _new_instance_id(cls, taken: set[str]) -> str:
        import secrets
        while True:
            raw = "".join(secrets.choice(cls._INSTANCE_ID_ALPHABET) for _ in range(8))
            iid = f"{raw[:4]}-{raw[4:]}"
            if iid not in taken:
                return iid

    def _known_instance_ids(self, exclude: Path | None = None) -> set[str]:
        ids: set[str] = set()
        if not self.characters_dir.exists():
            return ids
        ex = exclude.resolve() if exclude is not None else None
        for p in iter_character_files(self.characters_dir):
            if ex is not None and p.resolve() == ex:
                continue
            try:
                with MaidArchive.peek(p, (), verify=False) as a:
                    iid = str(a.manifest.get("instance_id") or "").strip()
            except (MaidArchiveError, zipfile.BadZipFile, OSError):
                continue
            if iid:
                ids.add(iid)
        return ids

    def _ensure_instance_id(self, archive: MaidArchive, maid_path: Path) -> str:
        current = str(archive.manifest.get("instance_id") or "").strip()
        taken = self._known_instance_ids(exclude=maid_path)
        if current and current not in taken:
            return current
        iid = self._new_instance_id(taken)
        archive.manifest["instance_id"] = iid
        archive.save()
        dup = f" (дубликат {current} другого сейва)" if current else ""
        print(f"[store] {maid_path.stem}: выдан instance_id {iid}{dup}")
        return iid

    @staticmethod
    def _expected_stem(baseline_id: str, passport: str) -> str:
        return f"{baseline_id}~{passport.split('-')[0]}"

    def _normalize_filenames(self) -> None:
        for p in iter_character_files(self.characters_dir):
            old_id = p.stem
            if old_id in self._archives:
                continue
            row = self.showcase(p)
            if row is None:
                continue
            baseline_id = str(row.get("baseline_id") or "").strip()
            passport = str(row.get("instance_id") or "").strip()
            gender = str(row.get("gender") or "").strip()
            if not baseline_id or not passport:
                continue
            new_id = self._expected_stem(baseline_id, passport)
            want_name = f"{new_id}{character_ext(gender)}"
            if p.name == want_name:
                continue
            dst = self.characters_dir / want_name
            if dst.exists():
                print(f"[store] normalize: {p.name} → {want_name}: имя занято — пропуск")
                continue
            try:
                p.rename(dst)
            except OSError as e:
                print(f"[store] normalize {old_id}: rename не удался ({e}) — пропуск")
                continue
            if old_id != new_id:
                for base in (self.characters_dir, self.runtime_cache_dir):
                    if base is None:
                        continue
                    d = base / old_id
                    if d.is_dir() and not (base / new_id).exists():
                        try:
                            d.rename(base / new_id)
                        except OSError as e:
                            print(f"[store] normalize {old_id}: {d.name}/ → {new_id}/ "
                                  f"не удался ({e})")
                self.pending_renames.append((old_id, new_id))
            print(f"[store] normalize: {p.name} → {want_name} "
                  f"(паспорт {passport})")

    def consume_renames(self) -> list[tuple[str, str]]:
        out = list(self.pending_renames)
        self.pending_renames.clear()
        return out

    _CRYPTO_MANIFEST_KEY = "crypto"

    @staticmethod
    def _keyslots(archive: MaidArchive) -> list[dict]:
        block = (archive.manifest or {}).get(CharacterStore._CRYPTO_MANIFEST_KEY) or {}
        return list(block.get("keyslots") or [])

    @staticmethod
    def _archive_is_protected(archive: MaidArchive) -> bool:
        return (archive.requires_feature(FEATURE_MEMORY_ENCRYPTION)
                and bool(CharacterStore._keyslots(archive)))

    def is_protected(self, character_id: str) -> bool:
        archive = self._archives.get(character_id)
        if archive is not None:
            return self._archive_is_protected(archive)
        path = find_character_file(self.characters_dir, character_id)
        if path is None:
            return False
        row = self.showcase(path)
        return bool(row and row.get("is_protected"))

    _SHOWCASE_ENTRIES = ("baseline.yaml", "identity.json",
                         UI_THEME_ENTRY, UI_THEME_DARK_ENTRY, UI_LIST_AVATAR_ENTRY)

    def showcase(self, path: Path) -> dict | None:
        try:
            st = path.stat()
        except OSError:
            self._showcase.pop(path, None)
            return None
        key = (st.st_mtime_ns, st.st_size)
        hit = self._showcase.get(path)
        if hit is not None and hit[0] == key:
            return hit[1]
        try:
            with MaidArchive.peek(path, self._SHOWCASE_ENTRIES) as a:
                row = self._showcase_row(a, path)
        except (MaidArchiveError, zipfile.BadZipFile, OSError) as e:
            print(f"[store] skip {path.name}: {type(e).__name__}: {e}")
            self._showcase.pop(path, None)
            return None
        row["etag"] = f'"{st.st_mtime_ns:x}-{st.st_size:x}"'
        self._showcase[path] = (key, row)
        return row

    def _showcase_row(self, a: MaidArchive, path: Path) -> dict:
        baseline = a.read_yaml("baseline.yaml") if a.has_entry("baseline.yaml") else {}
        baseline = baseline or {}
        try:
            idj = a.read_json("identity.json") if a.has_entry("identity.json") else {}
        except (KeyError, ValueError):
            idj = {}
        fm = (((idj or {}).get("event_log") or {}).get("first_meeting") or {}).get("last_fired_at")

        def _json_entry(name: str):
            if not a.has_entry(name):
                return None
            try:
                return a.read_json(name)
            except ValueError as e:
                print(f"[store] {path.name}: {name} не json: {e}")
                return None

        return {
            "id": path.stem,
            "baseline_id": a.manifest["character_id"],
            "instance_id": (str(a.manifest.get("instance_id") or "").strip() or None),
            "name": baseline.get("name", a.manifest["character_id"]),
            "gender": a.manifest.get("character_gender", "female"),
            "subtitle": baseline.get("subtitle", ""),
            "short_description": baseline.get("short_description", ""),
            "accent_color": baseline.get("accent_color", ""),
            "number": registry_number(baseline.get("number")),
            "generation": str(baseline.get("generation") or "").strip() or CURRENT_GENERATION,
            "is_pristine": a.manifest.get("is_pristine", False),
            "app_version_created": a.manifest.get("app_version_created", ""),
            "training": _training_row(a.manifest),
            "is_protected": self._archive_is_protected(a),
            "first_meeting_at": float(fm) if fm else None,
            "file": str(path),
            "ui": {
                "structure": _json_entry(UI_THEME_ENTRY),
                "dark": _json_entry(UI_THEME_DARK_ENTRY),
                "list_avatar": (a.read_bytes(UI_LIST_AVATAR_ENTRY)
                                if a.has_entry(UI_LIST_AVATAR_ENTRY) else None),
            },
        }

    def ui_bundle(self, character_id: str) -> dict | None:
        path = find_character_file(self.characters_dir, character_id)
        if path is None:
            return None
        row = self.showcase(path)
        if row is None:
            return None
        return dict(row["ui"], etag=row["etag"])

    def is_unlocked(self, character_id: str) -> bool:
        return character_id in self._deks

    def verify_secret(self, character_id: str, secret: str) -> bool:
        path = find_character_file(self.characters_dir, character_id)
        if path is None:
            raise CharacterNotFoundError(
                f"{character_id}: не найден в {self.characters_dir}")
        with MaidArchive.open(path, verify=False) as a:
            if not self._archive_is_protected(a):
                return True
            try:
                crypto.unlock_dek(self._keyslots(a), secret)
                return True
            except crypto.WrongPasswordError:
                return False

    def session_key(self, character_id: str) -> bytes | None:
        return self._deks.get(character_id)

    def _write_crypto_block(self, archive: MaidArchive, keyslots: list[dict]) -> None:
        archive.manifest[self._CRYPTO_MANIFEST_KEY] = {
            "v": crypto.CRYPTO_VERSION,
            "sealed": ["memory.jsonl", "identity.json", "gallery/*"],
            "keyslots": keyslots,
        }
        archive.manifest["memory_encrypted"] = True
        archive.declare_feature(FEATURE_MEMORY_ENCRYPTION)

    def _clear_crypto_block(self, archive: MaidArchive) -> None:
        archive.manifest.pop(self._CRYPTO_MANIFEST_KEY, None)
        archive.manifest["memory_encrypted"] = False
        archive.manifest["encryption_kdf"] = None
        archive.manifest["encryption_kdf_salt"] = None
        archive.revoke_feature(FEATURE_MEMORY_ENCRYPTION)

    def protect(self, character_id: str, password: str, *,
                kdf_n: int = crypto.SCRYPT_N) -> str:
        archive = self._archives.get(character_id)
        if archive is None:
            raise RuntimeError(f"{character_id}: сначала load(), потом protect()")
        if self._archive_is_protected(archive):
            raise RuntimeError(f"{character_id}: защита уже включена")
        if not password:
            raise ValueError("пустой пароль")

        dek = crypto.new_dek()
        recovery_slot, code = crypto.make_recovery_slot(dek, n=kdf_n)
        self._write_crypto_block(archive, [
            crypto.make_password_slot(dek, password, n=kdf_n),
            recovery_slot,
        ])
        self._deks[character_id] = dek
        self._rewrite_state(character_id, archive, dek_in=None, dek_out=dek)
        self._bind_identity_seal(character_id)
        print(f"[store] {character_id}: защита включена")
        return code

    def unprotect(self, character_id: str, secret: str) -> None:
        archive = self._archives.get(character_id)
        if archive is None:
            raise RuntimeError(f"{character_id}: сначала load(), потом unprotect()")
        if not self._archive_is_protected(archive):
            return
        dek = crypto.unlock_dek(self._keyslots(archive), secret)
        self._clear_crypto_block(archive)
        self._deks.pop(character_id, None)
        self._rewrite_state(character_id, archive, dek_in=dek, dek_out=None)
        self._bind_identity_seal(character_id)
        print(f"[store] {character_id}: защита снята")

    def change_password(self, character_id: str, old_secret: str,
                        new_password: str, *, kdf_n: int = crypto.SCRYPT_N) -> None:
        archive = self._archives.get(character_id)
        if archive is None:
            raise RuntimeError(f"{character_id}: сначала load(), потом смена пароля")
        if not self._archive_is_protected(archive):
            raise RuntimeError(f"{character_id}: защита не включена")
        if not new_password:
            raise ValueError("пустой пароль")
        slots = crypto.rewrap_slots(self._keyslots(archive), old_secret,
                                    new_password, n=kdf_n)
        self._write_crypto_block(archive, slots)
        archive.save(app_version=self.app_version)

    def _rewrite_state(self, character_id: str, archive: MaidArchive, *,
                       dek_in: bytes | None, dek_out: bytes | None) -> None:
        records = self._memory_records.get(character_id, [])
        archive.write_jsonl(
            "memory.jsonl",
            crypto.seal_records(records, dek_out) if dek_out else records,
        )
        try:
            data = archive.read_json("identity.json")
        except KeyError:
            data = None
        if data is not None:
            opened = crypto.open_identity(data, dek_in)
            archive.write_json(
                "identity.json",
                crypto.seal_identity(opened, dek_out) if dek_out else opened,
            )
        from persona import gallery as gallery_mod
        n = gallery_mod.reseal(archive, dek_in=dek_in, dek_out=dek_out)
        if n:
            print(f"[store] {character_id}: галерея "
                  f"{'запечатана' if dek_out else 'распечатана'} ({n} entries)")
        archive.save(app_version=self.app_version)
        self._write_shadow(character_id, records)

    def _bind_identity_seal(self, character_id: str) -> None:
        identity = self._identities.get(character_id)
        if identity is None:
            return
        dek = self._deks.get(character_id)
        identity._maid_seal = (
            (lambda data, _dek=dek: crypto.seal_identity(data, _dek))
            if dek else None
        )

    def list_available(self) -> list[dict]:
        if not self.characters_dir.exists():
            return []
        self._normalize_filenames()
        files = iter_character_files(self.characters_dir)
        for stale in [p for p in self._showcase if p not in files]:
            del self._showcase[stale]
        result = []
        for path in files:
            row = self.showcase(path)
            if row is None:
                continue
            result.append({k: v for k, v in row.items() if k not in ("ui", "etag")})
        return result

    def import_character(self, src_path: Path | str) -> dict:
        import shutil
        src = Path(src_path)
        if not src.is_file() or src.suffix.lower() not in CHARACTER_EXTS:
            return {"ok": False, "error": "нужен файл .maid или .butler"}
        try:
            with MaidArchive.open(src) as a:
                baseline_id = str(a.manifest.get("character_id") or "").strip()
                src_passport = str(a.manifest.get("instance_id") or "").strip()
                gender = str(a.manifest.get("character_gender") or "").strip()
                name = (a.read_yaml("baseline.yaml") or {}).get("name", baseline_id)
        except MaidArchiveError as e:
            return {"ok": False, "error": f"не похоже на файл персонажа: {e}"}
        if not baseline_id:
            return {"ok": False, "error": "в архиве нет character_id"}

        self.characters_dir.mkdir(parents=True, exist_ok=True)
        taken = self._known_instance_ids()
        passport = (src_passport if src_passport and src_passport not in taken
                    else self._new_instance_id(taken))

        instance_id = self._expected_stem(baseline_id, passport)
        while find_character_file(self.characters_dir, instance_id) is not None:
            passport = self._new_instance_id(taken | {passport})
            instance_id = self._expected_stem(baseline_id, passport)

        dst = self.characters_dir / f"{instance_id}{character_ext(gender)}"
        shutil.copy2(src, dst)
        try:
            with MaidArchive.open(dst) as a:
                if str(a.manifest.get("instance_id") or "").strip() != passport:
                    a.manifest["instance_id"] = passport
                    a.save()
        except MaidArchiveError as e:
            print(f"[store] import {instance_id}: паспорт не вписан: {e}")
        print(f"[store] import: {src.name} → {dst.name} (паспорт {passport})")
        base_visual = self.characters_dir / baseline_id
        if base_visual.is_dir() and instance_id != baseline_id:
            try:
                shutil.copytree(base_visual, self.characters_dir / instance_id)
            except OSError as e:
                print(f"[store] visual copy {baseline_id}->{instance_id}: {e}")
        return {"ok": True, "id": instance_id, "baseline_id": baseline_id,
                "instance_id": passport, "name": name}

    def load(self, character_id: str, *, secret: str | None = None) -> dict:
        maid_path = find_character_file(self.characters_dir, character_id)
        if maid_path is None:
            raise CharacterNotFoundError(
                f"{character_id}: не найден в {self.characters_dir}"
            )
        return self._open_existing_maid(maid_path, character_id, secret=secret)

    def _open_existing_maid(self, maid_path: Path, character_id: str,
                            *, secret: str | None = None) -> dict:
        known_dek = self._deks.get(character_id)
        if character_id in self._archives:
            self._archives[character_id].close()
            del self._archives[character_id]
            self._memory_records.pop(character_id, None)
            self._deks.pop(character_id, None)
            self._identities.pop(character_id, None)

        archive = MaidArchive.open(maid_path)

        dek: bytes | None = None
        if self._archive_is_protected(archive):
            if secret:
                try:
                    dek = crypto.unlock_dek(self._keyslots(archive), secret)
                except crypto.WrongPasswordError:
                    archive.close()
                    raise
            elif known_dek is not None:
                dek = known_dek
            else:
                archive.close()
                raise CharacterLockedError(character_id)

        try:
            self._ensure_instance_id(archive, maid_path)
        except Exception as e:
            print(f"[store] {character_id}: instance_id не выдан: {e}")

        try:
            from persona.training import ensure_training_section
            if ensure_training_section(archive.manifest):
                archive.save(app_version=self.app_version)
        except Exception as e:
            print(f"[store] {character_id}: раздел training не дописан: {e}")

        try:
            self._extract_visual_assets(archive, character_id)
        except Exception as e:
            print(f"[store] {character_id}: visual extract failed: {e}")

        character = self._character_from_archive(archive)
        identity = self._identity_from_archive(archive, character, dek)
        try:
            from persona.evolution import sync_base_statements
            _synced = sync_base_statements(identity, character)
            if _synced:
                print(f"[store] {character_id}: снапшот дизайна в identity освежён: "
                      f"{', '.join(_synced)}")
        except Exception as e:
            print(f"[store] {character_id}: sync base statements failed: {e}")
        try:
            from persona.axis_dynamics import migrate_axes_to_band
            _moved = migrate_axes_to_band(identity, character)
            if _moved:
                print(f"[store] {character_id}: оси возвращены в полосу дуги: {', '.join(_moved)}")
        except Exception as e:
            print(f"[store] {character_id}: axis band migration failed: {e}")
        memory_records = crypto.open_records(archive.read_jsonl("memory.jsonl"), dek)

        memory_records = self._recover_or_init_shadow(
            character_id, archive, memory_records, dek
        )

        if dek is not None:
            try:
                from persona import gallery as gallery_mod
                n = gallery_mod.reseal(archive, dek_in=dek, dek_out=dek)
                if n:
                    archive.save(app_version=self.app_version)
                    print(f"[store] {character_id}: галерея запечатана при "
                          f"разблокировке ({n} entries)")
            except Exception as e:
                print(f"[store] {character_id}: галерея не запечатана: {e}")

        self._archives[character_id] = archive
        self._memory_records[character_id] = memory_records
        self._identities[character_id] = identity
        if dek is not None:
            self._deks[character_id] = dek

        identity._maid_archive = archive
        identity._maid_pre_save_hook = lambda arc: self._flush_memory_to_archive(
            character_id, arc
        )
        self._bind_identity_seal(character_id)

        return {
            "character": character,
            "identity": identity,
            "memory_records": memory_records,
            "archive": archive,
            "is_legacy": False,
        }

    def _character_from_archive(self, archive: MaidArchive) -> Character:
        baseline_text = archive.read_text("baseline.yaml")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(baseline_text)
            tmp_path = f.name
        try:
            return Character.from_yaml(tmp_path)
        finally:
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass

    def _identity_from_archive(
        self, archive: MaidArchive, character: Character,
        dek: bytes | None = None,
    ) -> CharacterIdentity:
        identity = CharacterIdentity(f"<maid:{archive.path.name}>")
        try:
            data = crypto.open_identity(archive.read_json("identity.json"), dek)
        except KeyError:
            data = None

        if data:
            identity.apply_loaded(data)
        else:
            identity.bootstrap_from_character(character)

        return identity

    def _shadow_path(self, character_id: str) -> Path | None:
        if self.runtime_cache_dir is None:
            return None
        return self.runtime_cache_dir / character_id / "memory.jsonl"

    def _recover_or_init_shadow(
        self,
        character_id: str,
        archive: MaidArchive,
        archive_records: list[dict],
        dek: bytes | None = None,
    ) -> list[dict]:
        shadow = self._shadow_path(character_id)
        if shadow is None or not shadow.exists():
            self._write_shadow(character_id, archive_records, dek=dek)
            return archive_records

        try:
            archive_saved_unix = self._iso_to_unix(
                archive.manifest.get("last_saved_at", "")
            )
        except Exception:
            archive_saved_unix = 0.0

        shadow_mtime = shadow.stat().st_mtime
        if shadow_mtime <= archive_saved_unix + 1.0:
            self._write_shadow(character_id, archive_records, dek=dek)
            return archive_records

        try:
            with open(shadow, "r", encoding="utf-8") as f:
                lines = [line for line in f if line.strip()]
            recovered = crypto.open_records(
                [json.loads(line) for line in lines], dek,
            )
        except (OSError, json.JSONDecodeError, crypto.CryptoError) as e:
            print(f"[store] shadow recovery failed ({e}); using archive copy")
            self._write_shadow(character_id, archive_records, dek=dek)
            return archive_records

        if len(recovered) == len(archive_records):
            return archive_records

        delta = len(recovered) - len(archive_records)
        print(
            f"[store] shadow recovery for {character_id}: "
            f"{len(archive_records)} (archive) → {len(recovered)} (shadow) "
            f"[+{delta} несохранённых записей]"
        )
        return recovered

    def _write_shadow(self, character_id: str, records: list[dict], *,
                      dek: bytes | None = None) -> None:
        shadow = self._shadow_path(character_id)
        if shadow is None:
            return
        if dek is None:
            dek = self._deks.get(character_id)
        rows = crypto.seal_records(records, dek) if dek else records
        shadow.parent.mkdir(parents=True, exist_ok=True)
        text = "".join(
            json.dumps(r, ensure_ascii=False) + "\n" for r in rows
        )
        shadow.write_text(text, encoding="utf-8")

    def _append_shadow(self, character_id: str, record: dict) -> None:
        shadow = self._shadow_path(character_id)
        if shadow is None:
            return
        dek = self._deks.get(character_id)
        row = crypto.seal_record(record, dek) if dek else record
        shadow.parent.mkdir(parents=True, exist_ok=True)
        with open(shadow, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    @staticmethod
    def _iso_to_unix(iso: str) -> float:
        from datetime import datetime, timezone
        if not iso:
            return 0.0
        if iso.endswith("Z"):
            iso = iso[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(iso).timestamp()
        except ValueError:
            return 0.0

    def add_memory_record(self, character_id: str, record: dict) -> None:
        self._memory_records.setdefault(character_id, []).append(record)
        self._append_shadow(character_id, record)

    def set_memory_records(self, character_id: str, records: list[dict]) -> None:
        self._memory_records[character_id] = list(records)
        self._write_shadow(character_id, records)

    def get_memory_records(self, character_id: str) -> list[dict]:
        return self._memory_records.get(character_id, [])

    def save(
        self,
        character_id: str,
        *,
        identity: CharacterIdentity | None = None,
        memory_records: list[dict] | None = None,
        with_identity: bool = True,
        with_memory: bool = True,
    ) -> None:
        archive = self._archives.get(character_id)
        if archive is None:
            raise RuntimeError(
                f"{character_id}: archive не открыт; вызови load() перед save()"
            )

        dek = self._deks.get(character_id)
        if with_identity and identity is not None:
            data = identity._serialize()
            archive.write_json(
                "identity.json",
                crypto.seal_identity(data, dek) if dek else data,
            )
        if with_memory:
            records = (
                memory_records if memory_records is not None
                else self._memory_records.get(character_id, [])
            )
            self._memory_records[character_id] = list(records)
            archive.write_jsonl(
                "memory.jsonl",
                crypto.seal_records(records, dek) if dek else records,
            )

        archive.save(app_version=self.app_version)
        if with_memory:
            self._write_shadow(character_id, self._memory_records.get(character_id, []))

    def _flush_memory_to_archive(self, character_id: str, archive: MaidArchive) -> None:
        records = self._memory_records.get(character_id, [])
        dek = self._deks.get(character_id)
        archive.write_jsonl(
            "memory.jsonl",
            crypto.seal_records(records, dek) if dek else records,
        )

    def reset_from_baseline(self, character_id: str) -> None:
        if self.baseline_dir is None:
            raise RuntimeError("baseline_dir не задан в CharacterStore")
        src = find_character_file(self.baseline_dir, character_id)
        if src is None:
            raise FileNotFoundError(
                f"эталон {character_id} не найден в {self.baseline_dir}")
        dst = self.characters_dir / src.name

        self.unload(character_id)

        old = find_character_file(self.characters_dir, character_id)
        if old is not None:
            backup_dir = self.characters_dir / ".backups"
            backup_dir.mkdir(exist_ok=True)
            backup = backup_dir / f"{old.name}.before_reset.{_today_iso()}"
            old.rename(backup)
            print(f"[store] backup runtime → .backups/{backup.name}")

        import shutil
        shutil.copy2(src, dst)
        with MaidArchive.open(dst) as a:
            a.manifest["is_pristine"] = False
            a.manifest["applied_migrations"].append({
                "from": 1,
                "to": 1,
                "at": _now_iso(),
                "describe": f"reset from baseline ({src.name})",
            })
            a.save(app_version=self.app_version)

    def reset_in_place(self, character_id: str) -> None:
        maid_path = find_character_file(self.characters_dir, character_id)
        if maid_path is None:
            raise CharacterNotFoundError(
                f"{character_id}: не найден в {self.characters_dir}")

        dek = self._deks.get(character_id)

        self.unload(character_id)

        import shutil
        backup_dir = self.characters_dir / ".backups"
        backup_dir.mkdir(exist_ok=True)
        backup = backup_dir / f"{maid_path.name}.before_reset.{_today_iso()}"
        shutil.copy2(maid_path, backup)
        print(f"[store] backup runtime → .backups/{backup.name}")

        with MaidArchive.open(maid_path) as a:
            character = self._character_from_archive(a)
            identity = CharacterIdentity(":memory:")
            identity.bootstrap_from_character(character)
            data = identity._serialize()
            if dek is None and self._archive_is_protected(a):
                self._clear_crypto_block(a)
                print(f"[store] {character_id}: защита снята при сбросе")
            a.write_json("identity.json",
                         crypto.seal_identity(data, dek) if dek else data)
            a.write_jsonl("memory.jsonl", [])
            a.manifest["is_pristine"] = False
            a.manifest["applied_migrations"].append({
                "from": 1,
                "to": 1,
                "at": _now_iso(),
                "describe": "reset in place (self baseline)",
            })
            log = a.read_text("migrations.log") if a.has_entry("migrations.log") else ""
            a.write_text("migrations.log",
                         log + f"{_now_iso()}  v1 reset in place (self baseline)\n")
            a.save(app_version=self.app_version)

        self._write_shadow(character_id, [])

    def unload(self, character_id: str) -> bool:
        archive = self._archives.pop(character_id, None)
        self._memory_records.pop(character_id, None)
        self._identities.pop(character_id, None)
        self._deks.pop(character_id, None)
        if archive is None:
            return False
        try:
            archive.close()
        except Exception:
            pass
        return True

    def is_loaded(self, character_id: str) -> bool:
        return character_id in self._archives

    def loaded_ids(self) -> list[str]:
        return list(self._archives.keys())

    def close_all(self) -> None:
        for archive in list(self._archives.values()):
            try:
                archive.close()
            except Exception:
                pass
        self._archives.clear()
        self._memory_records.clear()
        self._identities.clear()
        self._deks.clear()

    def get_archive(self, character_id: str) -> MaidArchive | None:
        return self._archives.get(character_id)


def _training_row(manifest: dict | None) -> dict:
    from persona.training import compare_with_required, read_training
    v = read_training(manifest)
    return {"version": str(v), "level": v.level, "step": v.step, "letter": v.letter,
            "label": v.label, "status": compare_with_required(v),
            "history": list(((manifest or {}).get("training") or {}).get("history") or [])[-5:]}


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_iso() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d_%H%M%S")
