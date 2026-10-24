import hashlib
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

TAG = "b11324"
URL = (f"https://github.com/ggml-org/llama.cpp/releases/download/{TAG}/"
       f"llama-{TAG}-bin-win-cuda-13.4-x64.zip")
SHA256 = "54afca0cd58cb94c977d18c707ac98e2aee1a53c201eef3517c5fbc533860684"
DEST = Path(__file__).resolve().parent.parent / "llama-server"


def main() -> int:
    exe = DEST / "llama-server.exe"
    if exe.exists() and "--force" not in sys.argv:
        print(f"{exe} уже есть (--force — скачать заново)")
        return 0
    DEST.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "llama.zip"
        print(f"качаю {URL}")
        digest = hashlib.sha256()
        with urllib.request.urlopen(URL) as resp, open(archive, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            got = 0
            while chunk := resp.read(1 << 20):
                out.write(chunk)
                digest.update(chunk)
                got += len(chunk)
                if total:
                    print(f"\r  {got * 100 // total}%", end="", flush=True)
        print()
        if digest.hexdigest() != SHA256:
            print("sha256 не совпал — архив повреждён или подменён", file=sys.stderr)
            return 1
        with zipfile.ZipFile(archive) as z:
            for member in z.infolist():
                if not member.is_dir():
                    (DEST / Path(member.filename).name).write_bytes(z.read(member))
    print(f"готово: {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
