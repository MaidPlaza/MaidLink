from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from persona.maid_archive import (
    CURRENT_FORMAT_VERSION,
    FormatVersionTooOldError,
    MaidArchive,
)
from persona.maid_migrations.base import Migration


MIGRATIONS: dict[int, Migration] = {}


def register(migration: Migration) -> None:
    if migration.from_version in MIGRATIONS:
        raise ValueError(
            f"миграция from_version={migration.from_version} уже зарегистрирована"
        )
    MIGRATIONS[migration.from_version] = migration


def load_with_migration(path: Path | str) -> MaidArchive:
    path = Path(path)
    try:
        return MaidArchive.open(path)
    except FormatVersionTooOldError as exc:
        return _run_migrations(path, exc.found)


def _run_migrations(path: Path, from_version: int) -> MaidArchive:
    backup = path.with_name(
        f"{path.name}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    shutil.copy2(path, backup)

    archive = _open_skip_version_check(path)

    v = from_version
    while v < CURRENT_FORMAT_VERSION:
        if v not in MIGRATIONS:
            raise RuntimeError(
                f"нет зарегистрированной миграции для v{v} → ...; "
                f"проверь persona/maid_migrations/__init__.py"
            )
        mig = MIGRATIONS[v]
        mig.upgrade(archive)
        archive.manifest["applied_migrations"].append({
            "from": v,
            "to": mig.to_version,
            "at": _now_iso(),
            "describe": mig.describe(),
        })
        _append_log(archive, f"v{v} -> v{mig.to_version}: {mig.describe()}")
        v = mig.to_version

    archive.manifest["format_version"] = CURRENT_FORMAT_VERSION
    archive.save()
    return archive


def _open_skip_version_check(path: Path) -> MaidArchive:
    import json

    from persona.maid_container import open_zip

    with open_zip(path) as zf:
        raw_manifest = json.loads(zf.read("manifest.json").decode("utf-8"))

    original_version = raw_manifest["format_version"]
    raw_manifest["format_version"] = CURRENT_FORMAT_VERSION

    archive = MaidArchive(path)
    archive.manifest = raw_manifest
    with open_zip(path) as zf:
        for name in zf.namelist():
            archive._entries[name] = zf.read(name)
    archive.manifest["format_version"] = original_version
    archive._opened = True
    archive._verify_checksums()
    return archive


def _append_log(archive: MaidArchive, line: str) -> None:
    existing = ""
    if archive.has_entry("migrations.log"):
        existing = archive.read_text("migrations.log")
    new_line = f"{_now_iso()}  {line}\n"
    archive.write_text("migrations.log", existing + new_line)


def _now_iso() -> str:
    from datetime import timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
