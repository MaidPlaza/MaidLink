from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ADDONS_DIRNAME = "addons"
STATE_FILE = "addons.json"


@dataclass
class Addon:
    id: str
    name: str = ""
    description: str = ""
    default_enabled: bool = False
    capabilities: list[str] = field(default_factory=list)
    max_rating_ceiling: str = "sfw"
    content: dict = field(default_factory=dict)
    prompt_fragment: str = ""
    reflection_prompt_fragment: str = ""
    root: Path | None = None


def _addons_dir(project_root: Path) -> Path:
    return project_root / ADDONS_DIRNAME


def _state_path(project_root: Path) -> Path:
    return project_root / "data" / STATE_FILE


def discover(project_root: Path) -> list[Addon]:
    out: list[Addon] = []
    d = _addons_dir(project_root)
    if not d.is_dir():
        return out
    for sub in sorted(d.iterdir()):
        manifest = sub / "addon.yaml"
        if not manifest.is_file():
            continue
        try:
            data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        except Exception as e:
            print(f"[addons] не прочитан манифест {manifest}: {e}")
            continue
        out.append(Addon(
            id=str(data.get("id") or sub.name),
            name=str(data.get("name") or sub.name),
            description=str(data.get("description") or ""),
            default_enabled=bool(data.get("default_enabled", False)),
            capabilities=list(data.get("capabilities") or []),
            max_rating_ceiling=str(data.get("max_rating_ceiling") or "sfw"),
            content=dict(data.get("content") or {}),
            prompt_fragment=str(data.get("prompt_fragment") or ""),
            reflection_prompt_fragment=str(
                data.get("reflection_prompt_fragment") or ""),
            root=sub,
        ))
    return out


def _state(project_root: Path) -> dict:
    p = _state_path(project_root)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")) or {}
        except Exception:
            pass
    return {}


def _is_enabled(addon: Addon, state: dict) -> bool:
    return bool(state.get(addon.id, addon.default_enabled))


def enabled_addons(project_root: Path) -> list[Addon]:
    state = _state(project_root)
    return [a for a in discover(project_root) if _is_enabled(a, state)]


def capabilities(project_root: Path) -> set[str]:
    caps: set[str] = set()
    for a in enabled_addons(project_root):
        caps.update(a.capabilities)
    return caps


def content_dirs(project_root: Path, catalog_key: str) -> list[Path]:
    out: list[Path] = []
    for a in enabled_addons(project_root):
        rel = a.content.get(catalog_key)
        if rel and a.root is not None:
            p = a.root / rel
            if p.exists():
                out.append(p)
    return out


def max_rating_ceiling(project_root: Path) -> str:
    from drawing.assets import RATING_ORDER
    best = "sfw"
    for a in enabled_addons(project_root):
        if RATING_ORDER.get(a.max_rating_ceiling, 0) > RATING_ORDER.get(best, 0):
            best = a.max_rating_ceiling
    return best


def apply_rating_ceiling(config, project_root: Path) -> None:
    from drawing.assets import RATING_ORDER
    ceiling = max_rating_ceiling(project_root)
    cur = getattr(config.drawing, "max_rating", "sfw")
    if RATING_ORDER.get(cur, 0) > RATING_ORDER.get(ceiling, 0):
        config.drawing.max_rating = ceiling


def prompt_fragments(project_root: Path) -> list[str]:
    out: list[str] = []
    for a in enabled_addons(project_root):
        if a.prompt_fragment and a.root is not None:
            f = a.root / a.prompt_fragment
            if f.is_file():
                try:
                    out.append(f.read_text(encoding="utf-8").strip())
                except Exception:
                    pass
    return out


def reflection_fragments(project_root: Path) -> list[str]:
    out: list[str] = []
    for a in enabled_addons(project_root):
        if a.reflection_prompt_fragment and a.root is not None:
            f = a.root / a.reflection_prompt_fragment
            if f.is_file():
                try:
                    out.append(f.read_text(encoding="utf-8").strip())
                except Exception:
                    pass
    return out


def set_enabled(project_root: Path, addon_id: str, enabled: bool) -> dict:
    state = _state(project_root)
    state[addon_id] = bool(enabled)
    p = _state_path(project_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


def install_from_zip(project_root: Path, zip_path: str) -> dict:
    p = Path(zip_path)
    if not p.is_file() or p.suffix.lower() not in (".zip", ".maidaddon"):
        return {"ok": False, "error": "Нужен .zip-пакет аддона"}
    try:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            with zipfile.ZipFile(p) as z:
                for name in z.namelist():
                    if name.startswith("/") or ".." in Path(name).parts:
                        return {"ok": False, "error": "Небезопасный архив (path traversal)"}
                z.extractall(tmp)
            manifest = tmp / "addon.yaml"
            if not manifest.is_file():
                manifest = None
                for sub in sorted(tmp.iterdir()):
                    if sub.is_dir() and (sub / "addon.yaml").is_file():
                        manifest = sub / "addon.yaml"
                        break
            if manifest is None:
                return {"ok": False, "error": "В пакете нет addon.yaml"}
            data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
            addon_id = str(data.get("id") or "").strip()
            if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", addon_id):
                return {"ok": False, "error": "Некорректный id аддона в манифесте"}
            dst = _addons_dir(project_root) / addon_id
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(manifest.parent, dst)
        return {"ok": True, "addon": {
            "id": addon_id,
            "name": str(data.get("name") or addon_id),
            "description": str(data.get("description") or ""),
        }}
    except Exception as e:
        return {"ok": False, "error": f"Не удалось установить аддон: {e}"}


def list_for_api(project_root: Path) -> list[dict]:
    state = _state(project_root)
    return [{
        "id": a.id, "name": a.name, "description": a.description,
        "enabled": _is_enabled(a, state), "capabilities": a.capabilities,
    } for a in discover(project_root)]
