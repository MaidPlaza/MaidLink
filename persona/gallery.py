from __future__ import annotations

import io
import secrets
import time

from PIL import Image

from persona import crypto
from persona.maid_archive import GALLERY_INDEX_ENTRY, GALLERY_PREFIX, MaidArchive

GALLERY_MAX = 100
THUMB_MAX = 320
QUALITY_FULL = 90
QUALITY_THUMB = 80


class GalleryFullError(Exception):
    def __init__(self, limit: int):
        self.limit = limit
        super().__init__(f"галерея полна: максимум {limit} снимков")


def load_index(archive: MaidArchive, dek: bytes | None = None) -> list[dict]:
    if archive is None or not archive.has_entry(GALLERY_INDEX_ENTRY):
        return []
    try:
        data = archive.read_json(GALLERY_INDEX_ENTRY)
    except ValueError:
        return []
    items = crypto.open_gallery_index(data, dek)
    return [dict(it) for it in items if isinstance(it, dict) and it.get("id")]


def _save_index(archive: MaidArchive, items: list[dict],
                dek: bytes | None = None) -> None:
    archive.write_json(GALLERY_INDEX_ENTRY,
                       crypto.seal_gallery_index(items, dek) if dek else items)


def _write_entry(archive: MaidArchive, name: str, data: bytes,
                 dek: bytes | None) -> None:
    archive.write_bytes(name, crypto.seal_blob(data, dek, name) if dek else data)


def _to_webp(img: Image.Image, quality: int) -> bytes:
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=quality, method=4)
    return buf.getvalue()


def _thumb(img: Image.Image, max_side: int) -> Image.Image:
    t = img.copy()
    t.thumbnail((max_side, max_side), Image.LANCZOS)
    return t


def add_image(archive: MaidArchive, png: bytes, *, source: str = "",
              intent: str = "", rating: str = "", prompt: str = "",
              now: float | None = None, dek: bytes | None = None,
              created_at: float | None = None) -> dict:
    items = load_index(archive, dek)
    if source:
        for it in items:
            if it.get("source") == source:
                return it
    if len(items) >= GALLERY_MAX:
        raise GalleryFullError(GALLERY_MAX)
    img = Image.open(io.BytesIO(png))
    img.load()
    w, h = img.size
    full = _to_webp(img, QUALITY_FULL)
    thumb = _to_webp(_thumb(img, THUMB_MAX), QUALITY_THUMB)
    ts = float(now if now is not None else time.time())
    gid = f"{time.strftime('%Y%m%dT%H%M%S', time.gmtime(ts))}_{secrets.token_hex(2)}"
    item = {
        "id": gid,
        "entry": f"{GALLERY_PREFIX}{gid}.webp",
        "thumb_entry": f"{GALLERY_PREFIX}{gid}.thumb.webp",
        "source": source or "",
        "intent": (intent or "")[:300],
        "rating": rating or "",
        "prompt": (prompt or "")[:300],
        "added_at": ts,
        "created_at": float(created_at) if created_at else ts,
        "width": w,
        "height": h,
        "bytes": len(full),
    }
    _write_entry(archive, item["entry"], full, dek)
    _write_entry(archive, item["thumb_entry"], thumb, dek)
    items.append(item)
    _save_index(archive, items, dek)
    return item


def remove_image(archive: MaidArchive, gid: str, *,
                 dek: bytes | None = None) -> bool:
    items = load_index(archive, dek)
    keep = [it for it in items if it.get("id") != gid]
    if len(keep) == len(items):
        return False
    for it in items:
        if it.get("id") == gid:
            for name in (it.get("entry"), it.get("thumb_entry")):
                if name and archive.has_entry(name):
                    archive.delete_entry(name)
    _save_index(archive, keep, dek)
    return True


def find_item(archive: MaidArchive, gid: str, *,
              dek: bytes | None = None) -> dict | None:
    for it in load_index(archive, dek):
        if it.get("id") == gid:
            return it
    return None


def read_image(archive: MaidArchive, gid: str, *, thumb: bool = False,
               dek: bytes | None = None) -> bytes | None:
    it = find_item(archive, gid, dek=dek)
    if it is None:
        return None
    name = it.get("thumb_entry" if thumb else "entry") or ""
    if not name or not archive.has_entry(name):
        return None
    return crypto.open_blob(archive.read_bytes(name), dek, name)


def reseal(archive: MaidArchive, *, dek_in: bytes | None,
           dek_out: bytes | None) -> int:
    if archive is None:
        return 0
    changed = 0
    for name in list(archive.list_entries()):
        if not name.startswith(GALLERY_PREFIX) or name == GALLERY_INDEX_ENTRY:
            continue
        raw = archive.read_bytes(name)
        sealed = crypto.is_sealed_blob(raw)
        if (dek_out is not None) == sealed:
            continue
        opened = crypto.open_blob(raw, dek_in, name)
        _write_entry(archive, name, opened, dek_out)
        changed += 1
    if archive.has_entry(GALLERY_INDEX_ENTRY):
        try:
            data = archive.read_json(GALLERY_INDEX_ENTRY)
        except ValueError:
            data = []
        index_sealed = isinstance(data, dict)
        if (dek_out is not None) != index_sealed:
            items = crypto.open_gallery_index(data, dek_in)
            _save_index(archive, items, dek_out)
            changed += 1
    return changed
