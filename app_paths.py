import os
import sys
from pathlib import Path


def _compute_assets_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


DATA_DIR_NAME = "userdata"


def install_dir(assets_root: Path) -> Path | None:
    if assets_root.parent.name.lower() == "resources":
        return assets_root.parent.parent
    return None


def legacy_data_root() -> Path | None:
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "MaidLink" if base else None


def _writable(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _compute_data_root(assets_root: Path) -> Path:
    env = os.environ.get("MAIDLINK_HOME")
    if env:
        return Path(env).expanduser().resolve()
    if getattr(sys, "frozen", False):
        inst = install_dir(assets_root)
        if inst is not None and _writable(inst / DATA_DIR_NAME):
            return inst / DATA_DIR_NAME
        return legacy_data_root() or assets_root
    return assets_root


ASSETS_ROOT: Path = _compute_assets_root()
PROJECT_ROOT: Path = _compute_data_root(ASSETS_ROOT)


def content_base(root: "Path | str | None" = None) -> Path:
    base = Path(root) if root is not None else ASSETS_ROOT
    grouped = base / "content"
    return grouped if grouped.is_dir() else base
