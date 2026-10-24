from __future__ import annotations

import os
import shutil
from pathlib import Path

_MIGRATE_DIRS = (
    "characters",
    "data",
    "runtime_cache",
    "addons",
    "models",
    "portraits",
    "image_gen/ComfyUI_windows_portable",
    "image_gen/generated",
)


def _same_root(a: Path, b: Path) -> bool:
    return os.path.normcase(str(a)) == os.path.normcase(str(b))


def _has_content(p: Path) -> bool:
    try:
        return p.is_dir() and any(p.iterdir())
    except OSError:
        return False


def ensure_data_root(assets_root: Path | None = None,
                     data_root: Path | None = None) -> list[str]:
    if assets_root is None or data_root is None:
        from app_paths import ASSETS_ROOT, PROJECT_ROOT
        assets_root = assets_root or ASSETS_ROOT
        data_root = data_root or PROJECT_ROOT
    if _same_root(assets_root, data_root):
        return []

    lines: list[str] = []
    data_root.mkdir(parents=True, exist_ok=True)
    for rel in _MIGRATE_DIRS:
        src = assets_root / rel
        if not _has_content(src):
            continue
        dst = data_root / rel
        if _has_content(dst):
            lines.append(f"[migrate] SKIP {rel}: на новом месте уже есть данные "
                         f"(старая копия оставлена в {src})")
            continue
        try:
            if dst.is_dir():
                dst.rmdir()
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            lines.append(f"[migrate] {rel} → {dst}")
        except OSError as e:
            lines.append(f"[migrate] FAIL {rel}: {e} (данные остались в {src})")

    old_styles = assets_root / "content" / "styles" / "user"
    if _has_content(old_styles):
        new_styles = data_root / "data" / "styles"
        new_styles.mkdir(parents=True, exist_ok=True)
        for f in sorted(old_styles.glob("*.yaml")):
            target = new_styles / f.name
            if target.exists():
                lines.append(f"[migrate] SKIP styles/{f.name}: уже есть")
                continue
            try:
                shutil.move(str(f), str(target))
                lines.append(f"[migrate] стиль {f.name} → data/styles/")
            except OSError as e:
                lines.append(f"[migrate] FAIL styles/{f.name}: {e}")

    return lines


POINTER_NAME = "data_location.txt"
_SKIP_ITEMS = frozenset({POINTER_NAME, "logs"})
_FREE_MARGIN = 512 * 1024 * 1024


def _tree_size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    total = 0
    for root, _dirs, files in os.walk(p):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except OSError:
                pass
    return total


def _same_volume(a: Path, b: Path) -> bool:
    try:
        return os.stat(a).st_dev == os.stat(b).st_dev
    except OSError:
        return os.path.splitdrive(str(a))[0].lower() == os.path.splitdrive(str(b))[0].lower()


def relocation_plan(data_root: Path, legacy_root: Path | None) -> list[tuple[Path, Path]]:
    sources: list[Path] = []
    if legacy_root is not None and not _same_root(legacy_root, data_root):
        sources.append(legacy_root)
        ptr = legacy_root / POINTER_NAME
        if ptr.is_file():
            try:
                target = Path(ptr.read_text(encoding="utf-8").strip())
            except OSError:
                target = None
            if (target and not _same_root(target, data_root)
                    and not any(_same_root(target, s) for s in sources)):
                sources.append(target)
    plan: list[tuple[Path, Path]] = []
    taken: set[str] = set()
    for src_root in sources:
        if not src_root.is_dir():
            continue
        for item in sorted(src_root.iterdir()):
            if item.name in _SKIP_ITEMS or item.name in taken:
                continue
            if item.is_dir() and not _has_content(item):
                continue
            dst = data_root / item.name
            if _has_content(dst) or (dst.is_file()):
                continue
            plan.append((item, dst))
            taken.add(item.name)
    return plan


def relocate_data(data_root: Path, legacy_root: Path | None, *,
                  progress=None) -> tuple[bool, list[str]]:
    plan = relocation_plan(data_root, legacy_root)
    lines: list[str] = []
    if not plan:
        _write_pointer(legacy_root, data_root)
        return True, lines
    data_root.mkdir(parents=True, exist_ok=True)
    same = all(_same_volume(src.parent, data_root) for src, _ in plan)
    if same:
        for src, dst in plan:
            try:
                if dst.is_dir():
                    dst.rmdir()
                os.replace(src, dst)
                lines.append(f"[relocate] {src} → {dst}")
            except OSError as e:
                lines.append(f"[relocate] FAIL {src.name}: {e}")
                return False, lines
        _write_pointer(legacy_root, data_root)
        return True, lines

    total = sum(_tree_size(src) for src, _ in plan)
    free = shutil.disk_usage(data_root).free
    if free < total + _FREE_MARGIN:
        lines.append(f"[relocate] SKIP: на новом месте свободно {free >> 20} МБ, "
                     f"нужно {total >> 20} МБ — данные остаются в {legacy_root}")
        return False, lines
    done = 0

    def _copy(s, d):
        nonlocal done
        shutil.copy2(s, d)
        done += os.path.getsize(d)
        if progress:
            progress(done, total)

    copied: list[Path] = []
    try:
        for src, dst in plan:
            if dst.is_dir():
                dst.rmdir()
            if src.is_dir():
                shutil.copytree(src, dst, copy_function=_copy)
            else:
                _copy(src, dst)
            copied.append(dst)
            lines.append(f"[relocate] скопировано {src} → {dst}")
    except OSError as e:
        for dst in copied + [plan[len(copied)][1]]:
            _remove(dst)
        lines.append(f"[relocate] FAIL копирования: {e} — новое место очищено, "
                     f"данные остаются в {legacy_root}")
        return False, lines
    for src, _ in plan:
        try:
            _remove(src, strict=True)
        except OSError as e:
            lines.append(f"[relocate] не удалось убрать старую копию {src}: {e}")
    _write_pointer(legacy_root, data_root)
    return True, lines


def _remove(p: Path, *, strict: bool = False) -> None:
    if p.is_dir():
        shutil.rmtree(p, ignore_errors=not strict)
    elif p.exists():
        p.unlink()


def _write_pointer(legacy_root: Path | None, data_root: Path) -> None:
    if legacy_root is None or _same_root(legacy_root, data_root):
        return
    try:
        legacy_root.mkdir(parents=True, exist_ok=True)
        (legacy_root / POINTER_NAME).write_text(str(data_root), encoding="utf-8")
    except OSError:
        pass
