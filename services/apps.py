from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

_IS_WIN = os.name == "nt"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if _IS_WIN else 0

_CACHE: list["AppEntry"] = []
_CACHE_AT: float = 0.0
_CACHE_TTL = 300.0


@dataclass
class AppEntry:
    name: str
    app_id: str = ""
    lnk_path: str = ""


def _run_get_startapps() -> list["AppEntry"]:
    if not _IS_WIN:
        return []
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
           "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
           "Get-StartApps | ConvertTo-Json -Compress"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=20,
                           creationflags=_NO_WINDOW)
        raw = (r.stdout or b"").decode("utf-8", errors="replace").strip()
        if not raw:
            return []
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        out: list[AppEntry] = []
        for it in data:
            if not isinstance(it, dict):
                continue
            name = str(it.get("Name") or "").strip()
            app_id = str(it.get("AppID") or "").strip()
            if name and app_id:
                out.append(AppEntry(name=name, app_id=app_id))
        return out
    except Exception as e:
        print(f"[apps] Get-StartApps fail: {type(e).__name__}: {e}")
        return []


def _scan_start_menu() -> list["AppEntry"]:
    if not _IS_WIN:
        return []
    seen: dict[str, AppEntry] = {}
    for env in ("ProgramData", "APPDATA"):
        base = os.environ.get(env)
        if not base:
            continue
        root = Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        if not root.is_dir():
            continue
        try:
            for lnk in root.rglob("*.lnk"):
                key = lnk.stem.lower()
                if lnk.stem and key not in seen:
                    seen[key] = AppEntry(name=lnk.stem, lnk_path=str(lnk))
        except OSError:
            continue
    return list(seen.values())


def _dedupe(entries: list["AppEntry"]) -> list["AppEntry"]:
    seen: set[str] = set()
    out: list[AppEntry] = []
    for e in entries:
        k = e.name.lower()
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out


def get_catalog(refresh: bool = False) -> list["AppEntry"]:
    global _CACHE, _CACHE_AT
    now = time.time()
    if _CACHE and not refresh and (now - _CACHE_AT) < _CACHE_TTL:
        return _CACHE
    cat = _run_get_startapps() or _scan_start_menu()
    _CACHE = _dedupe(cat)
    _CACHE_AT = now
    return _CACHE


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def find_app(query: str, catalog: list["AppEntry"] | None = None
             ) -> tuple["AppEntry | None", list["AppEntry"]]:
    q = _norm(query)
    if not q:
        return None, []
    cat = catalog if catalog is not None else get_catalog()
    if not cat:
        return None, []

    exact = [a for a in cat if _norm(a.name) == q]
    if len(exact) == 1:
        return exact[0], []
    if exact:
        return None, exact[:5]

    subs = [a for a in cat if q in _norm(a.name)
            or (len(_norm(a.name)) >= 3 and _norm(a.name) in q)]
    starts = [a for a in subs if _norm(a.name).startswith(q)
              or q.startswith(_norm(a.name))]
    pool = starts or subs
    if len(pool) == 1:
        return pool[0], []
    if pool:
        return None, pool[:5]

    qtok = set(q.split())
    tok = [a for a in cat if qtok & set(_norm(a.name).split())]
    return None, tok[:5]


def launch_app(entry: "AppEntry") -> tuple[bool, str]:
    if not _IS_WIN:
        return False, "запуск приложений доступен только на Windows"
    try:
        if entry.app_id:
            subprocess.Popen(
                ["explorer.exe", f"shell:AppsFolder\\{entry.app_id}"])
            return True, entry.name
        if entry.lnk_path:
            os.startfile(entry.lnk_path)
            return True, entry.name
    except Exception as e:
        return False, type(e).__name__
    return False, "нет способа запуска"
