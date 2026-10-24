from __future__ import annotations

import json
import re
import shutil
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "dist" / "licenses"
STATIC = ROOT / "build" / "licenses"
LICENSE_NAME = re.compile(r"^(licen[cs]e|copying|notice|authors)", re.I)
PROPRIETARY_FONTS = ("futura", "francy")
TERMS_NAME = "MaidLink-TERMS.txt"


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def python_dists() -> list[metadata.Distribution]:
    seen: dict[str, metadata.Distribution] = {}
    for dist in metadata.distributions():
        name = norm(dist.metadata["Name"] or "")
        if name and name != "pip":
            seen.setdefault(name, dist)
    return sorted(seen.values(), key=lambda d: norm(d.metadata["Name"]))


def python_licenses(out: Path, index: list[str], missing: list[str]) -> None:
    py = out / "python"
    py.mkdir(parents=True)
    base_license = Path(sys.base_prefix) / "LICENSE.txt"
    if base_license.exists():
        shutil.copyfile(base_license, py / "Python-LICENSE.txt")
        index.append(f"python/Python-LICENSE.txt — Python {sys.version.split()[0]} (PSF)")
    else:
        missing.append(f"Python {sys.version.split()[0]}: нет {base_license}")
    for dist in python_dists():
        name, version = dist.metadata["Name"], dist.version
        files = [f for f in dist.files or []
                 if ".dist-info" in str(f) and (
                     "/licenses/" in str(f).replace("\\", "/") or LICENSE_NAME.match(Path(str(f)).name))]
        dest = py / f"{norm(name)}-{version}"
        copied = 0
        for f in files:
            src = Path(dist.locate_file(f))
            if src.is_file():
                dest.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dest / src.name)
                copied += 1
        lic = (dist.metadata.get("License-Expression") or dist.metadata.get("License") or "").strip()
        lic = lic.splitlines()[0][:80] if lic else ""
        if copied:
            index.append(f"python/{dest.name}/ — {name} {version}" + (f" ({lic})" if lic else ""))
        else:
            missing.append(f"{name} {version}: в пакете нет файла лицензии" + (f" (метаданные: {lic})" if lic else ""))


def npm_licenses(out: Path, index: list[str], missing: list[str]) -> None:
    nm = ROOT / "ui" / "node_modules"
    roots = list((json.loads((ROOT / "ui" / "package.json").read_text(encoding="utf-8")).get("dependencies") or {}))
    seen: set[str] = set()
    while roots:
        name = roots.pop()
        if name in seen:
            continue
        seen.add(name)
        pkg_dir = nm / name
        pkg_json = pkg_dir / "package.json"
        if not pkg_json.exists():
            missing.append(f"npm {name}: нет в ui/node_modules (npm ci --prefix ui)")
            continue
        pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
        roots += list((pkg.get("dependencies") or {}))
        dest = out / "npm" / f"{name.replace('/', '__')}-{pkg.get('version', '')}"
        files = [p for p in pkg_dir.iterdir() if p.is_file() and LICENSE_NAME.match(p.name)]
        if not files:
            missing.append(f"npm {name}: в пакете нет файла лицензии ({pkg.get('license', '?')})")
            continue
        dest.mkdir(parents=True, exist_ok=True)
        for f in files:
            shutil.copyfile(f, dest / f.name)
        index.append(f"npm/{dest.name}/ — {name} {pkg.get('version', '')} ({pkg.get('license', '?')})")


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    index: list[str] = []
    missing: list[str] = []

    for src, dst, what in ((ROOT / "LICENSE", "MaidLink-LICENSE.txt", "MaidLink — PolyForm Noncommercial 1.0.0"),
                           (ROOT / "NOTICE.md", "NOTICE.md", "что MaidLink скачивает и откуда"),
                           (ROOT / "THIRD-PARTY-LICENSES.txt", "THIRD-PARTY-LICENSES.txt", "сводка сторонних компонентов")):
        shutil.copyfile(src, OUT / dst)
        index.append(f"{dst} — {what}")
    terms = (ROOT / "TERMS.txt").read_text(encoding="utf-8")
    (OUT / TERMS_NAME).write_text(terms, encoding="utf-8-sig", newline="\r\n")
    index.append(f"{TERMS_NAME} — пользовательское соглашение")

    shutil.copyfile(STATIC / "llama.cpp-LICENSE.txt", OUT / "llama.cpp-LICENSE.txt")
    index.append("llama.cpp-LICENSE.txt — llama.cpp, llama-server.exe и ggml*.dll (MIT)")
    llvm = ROOT / "llama-server" / "LICENSE-LLVM-OpenMP"
    if llvm.exists():
        shutil.copyfile(llvm, OUT / "LLVM-OpenMP-LICENSE.txt")
        index.append("LLVM-OpenMP-LICENSE.txt — libomp.dll (Apache-2.0 WITH LLVM-exception)")
    else:
        missing.append("LLVM OpenMP: нет llama-server/LICENSE-LLVM-OpenMP (py build/fetch_llama_server.py)")
    shutil.copyfile(STATIC / "FAIPL-1.0-SD.txt", OUT / "FAIPL-1.0-SD.txt")
    index.append("FAIPL-1.0-SD.txt — эмбеддинги рисования lazypos/lazyneg/lazyhand/lazywet "
                 "(Lazy Embeddings, civitai.com/models/1302719)")

    fonts = OUT / "fonts"
    shutil.copytree(STATIC / "fonts", fonts)
    for f in sorted(fonts.iterdir()):
        index.append(f"fonts/{f.name} — шрифт {f.name.split('-')[0]} (SIL Open Font License 1.1)")
    dist_assets = ROOT / "ui" / "dist" / "assets"
    if dist_assets.exists():
        bad = [p.name for p in dist_assets.iterdir() if any(k in p.name.lower() for k in PROPRIETARY_FONTS)]
        if bad:
            print(f"[licenses] ВНИМАНИЕ: в сборке проприетарные шрифты {bad} — релиз собирать из публичной копии")

    python_licenses(OUT, index, missing)
    npm_licenses(OUT, index, missing)

    lines = ["Лицензии компонентов MaidLink", "=" * 29, "",
             "Electron и Chromium: LICENSE.electron.txt и LICENSES.chromium.html в папке установки.", ""]
    lines += index
    if missing:
        lines += ["", "Без отдельного файла лицензии (лицензия указана в метаданных пакета):"] + [f"  {m}" for m in missing]
    (OUT / "INDEX.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[licenses] {OUT}: {len(index)} позиций" + (f", без файла лицензии: {len(missing)}" if missing else ""))
    for m in missing:
        print(f"[licenses]   {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
