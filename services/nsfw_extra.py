from __future__ import annotations

CONTENT_KEY = "extra"
CODE_ENTRY = "extra.code"
LEGACY_CODE_ENTRY = "visual/anatomy.code"
SEPARATOR = "."

SEG_POSITIVE, SEG_NEGATIVE, SEG_QUIRKS = 0, 1, 2


def read_code(archive) -> str:
    if archive is None:
        return ""
    try:
        for entry in (CODE_ENTRY, LEGACY_CODE_ENTRY):
            if archive.has_entry(entry):
                return archive.read_text(entry).strip()
    except Exception as e:
        print(f"[extra] код не прочитан: {type(e).__name__}: {e}")
    return ""


def segment(code: str, index: int) -> str:
    parts = (code or "").strip()[1:].split(SEPARATOR)
    return parts[index] if 0 <= index < len(parts) else ""


def version_of(code: str) -> str:
    code = (code or "").strip()
    return code[0] if code else ""
