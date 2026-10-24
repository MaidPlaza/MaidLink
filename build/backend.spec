import os
import sys

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
sys.path.insert(0, ROOT)

hiddenimports = []
for _pkg in ("api", "persona", "memory", "llm", "drawing", "services", "tools"):
    hiddenimports += collect_submodules(_pkg)
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("ddgs")
hiddenimports += [
    "app_paths", "config",
    "websockets", "websockets.legacy", "websockets.legacy.server",
    "anyio", "h11",
    "pypdf",
]

excludes = [
    "torch", "torchaudio", "torchvision", "fairseq", "infer_rvc_python",
    "numba", "llvmlite", "transformers", "tokenizers", "scipy", "pandas",
    "matplotlib", "sklearn", "tensorboard", "onnxruntime", "librosa",
    "IPython", "notebook", "PyQt5", "PySide2", "tkinter",
]

a = Analysis(
    [os.path.join(ROOT, "run_backend.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="backend",
)
