from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import struct

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


CRYPTO_VERSION = 1

SEALED_MEMORY_FIELDS = ("title", "details", "embedding")
SEALED_IDENTITY_FIELDS = ("master_summary", "last_session_summary")

SCRYPT_N = 1 << 17
SCRYPT_R = 8
SCRYPT_P = 1
_SCRYPT_MAXMEM = 512 * 1024 * 1024
_DEK_LEN = 32

_AAD_KEY = b"maid-dek-v1"
_AAD_IDENTITY = b"maid-identity-v1"
_AAD_RECORD_PREFIX = b"maid-rec-v1:"
_AAD_SESSION_PREFIX = b"maid-session-v1:"

_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_CODE_GROUPS = 4
_CODE_GROUP_LEN = 4


class CryptoError(Exception):
    pass


class WrongPasswordError(CryptoError):
    pass


class SealedDataError(CryptoError):
    pass


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(text: str) -> bytes:
    try:
        return base64.b64decode(text.encode("ascii"), validate=True)
    except Exception as e:
        raise SealedDataError(f"не base64: {e}") from e


def new_dek() -> bytes:
    return os.urandom(_DEK_LEN)


def _derive_kek(secret: str, salt: bytes, *, n: int, r: int, p: int) -> bytes:
    if not isinstance(secret, str) or not secret:
        raise WrongPasswordError("пустой пароль")
    return hashlib.scrypt(
        secret.encode("utf-8"), salt=salt, n=n, r=r, p=p,
        dklen=_DEK_LEN, maxmem=_SCRYPT_MAXMEM,
    )


def _wrap(dek: bytes, secret: str, *, slot_type: str, n: int) -> dict:
    salt = os.urandom(32)
    kek = _derive_kek(secret, salt, n=n, r=SCRYPT_R, p=SCRYPT_P)
    nonce = os.urandom(12)
    wrapped = AESGCM(kek).encrypt(nonce, dek, _AAD_KEY)
    return {
        "type": slot_type,
        "kdf": "scrypt",
        "n": n, "r": SCRYPT_R, "p": SCRYPT_P,
        "salt": _b64e(salt),
        "nonce": _b64e(nonce),
        "wrapped": _b64e(wrapped),
    }


def make_password_slot(dek: bytes, password: str, *, n: int = SCRYPT_N) -> dict:
    return _wrap(dek, password, slot_type="password", n=n)


def generate_recovery_code() -> str:
    groups = [
        "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_GROUP_LEN))
        for _ in range(_CODE_GROUPS)
    ]
    return "-".join(groups)


def normalize_recovery_code(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch in _CODE_ALPHABET)


def make_recovery_slot(dek: bytes, *, n: int = SCRYPT_N) -> tuple[dict, str]:
    code = generate_recovery_code()
    slot = _wrap(dek, normalize_recovery_code(code), slot_type="recovery", n=n)
    return slot, code


def unlock_dek(keyslots: list[dict], secret: str) -> bytes:
    if not keyslots:
        raise WrongPasswordError("в сейве нет ни одного слота ключа")
    candidates = [secret]
    normalized = normalize_recovery_code(secret)
    if normalized and normalized != secret:
        candidates.append(normalized)

    for slot in keyslots:
        if slot.get("kdf") != "scrypt":
            continue
        try:
            salt = _b64d(str(slot["salt"]))
            nonce = _b64d(str(slot["nonce"]))
            wrapped = _b64d(str(slot["wrapped"]))
            n = int(slot.get("n", SCRYPT_N))
            r = int(slot.get("r", SCRYPT_R))
            p = int(slot.get("p", SCRYPT_P))
        except (KeyError, ValueError, SealedDataError):
            continue
        for candidate in candidates:
            try:
                kek = _derive_kek(candidate, salt, n=n, r=r, p=p)
                return AESGCM(kek).decrypt(nonce, wrapped, _AAD_KEY)
            except (InvalidTag, WrongPasswordError):
                continue
    raise WrongPasswordError("пароль не подошёл ни к одному слоту")


def rewrap_slots(keyslots: list[dict], old_secret: str, new_password: str,
                 *, n: int = SCRYPT_N) -> list[dict]:
    dek = unlock_dek(keyslots, old_secret)
    kept = [s for s in keyslots if s.get("type") != "password"]
    return [make_password_slot(dek, new_password, n=n)] + kept


def _pack_payload(fields: dict) -> bytes:
    body = dict(fields)
    emb_bytes = b""
    if "embedding" in body:
        embedding = body.pop("embedding") or []
        if embedding:
            import numpy as np
            emb_bytes = np.asarray(embedding, dtype=np.float32).tobytes()
        body["_emb"] = len(embedding)
    head = json.dumps(body, ensure_ascii=False).encode("utf-8")
    return struct.pack(">I", len(head)) + head + emb_bytes


def _unpack_payload(raw: bytes) -> dict:
    if len(raw) < 4:
        raise SealedDataError("блоб короче заголовка")
    (head_len,) = struct.unpack(">I", raw[:4])
    if head_len > len(raw) - 4:
        raise SealedDataError("длина заголовка вне блоба")
    try:
        body = json.loads(raw[4:4 + head_len].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise SealedDataError(f"payload не JSON: {e}") from e
    if not isinstance(body, dict):
        raise SealedDataError("payload не объект")
    dim = body.pop("_emb", None)
    if dim is not None:
        tail = raw[4 + head_len:]
        if len(tail) != dim * 4:
            raise SealedDataError(
                f"эмбеддинг обрезан: {len(tail)} байт вместо {dim * 4}")
        if dim:
            import numpy as np
            body["embedding"] = np.frombuffer(tail, dtype=np.float32).tolist()
        else:
            body["embedding"] = []
    return body


def _seal_fields(fields: dict, dek: bytes, aad: bytes) -> dict:
    nonce = os.urandom(12)
    blob = AESGCM(dek).encrypt(nonce, _pack_payload(fields), aad)
    return {"v": CRYPTO_VERSION, "n": _b64e(nonce), "c": _b64e(blob)}


def _open_fields(enc: dict, dek: bytes, aad: bytes) -> dict:
    if not isinstance(enc, dict):
        raise SealedDataError("enc не объект")
    version = int(enc.get("v", 0))
    if version > CRYPTO_VERSION:
        raise SealedDataError(
            f"crypto v{version} новее поддерживаемой v{CRYPTO_VERSION} — обновите приложение")
    nonce = _b64d(str(enc.get("n", "")))
    blob = _b64d(str(enc.get("c", "")))
    try:
        raw = AESGCM(dek).decrypt(nonce, blob, aad)
    except InvalidTag as e:
        raise SealedDataError(
            "блоб не расшифровался: другой ключ, повреждение или подмена") from e
    return _unpack_payload(raw)


def is_sealed(record: dict) -> bool:
    return isinstance(record, dict) and isinstance(record.get("enc"), dict)


def _record_aad(record: dict) -> bytes:
    return _AAD_RECORD_PREFIX + str(record.get("record_id") or "").encode("utf-8")


def seal_record(record: dict, dek: bytes) -> dict:
    if is_sealed(record):
        return dict(record)
    out = {k: v for k, v in record.items() if k not in SEALED_MEMORY_FIELDS}
    fields = {k: record[k] for k in SEALED_MEMORY_FIELDS if k in record}
    out["enc"] = _seal_fields(fields, dek, _record_aad(record))
    return out


def open_record(record: dict, dek: bytes | None) -> dict:
    if not is_sealed(record):
        return dict(record)
    if dek is None:
        raise SealedDataError(
            f"запись {record.get('record_id') or '?'} зашифрована, ключ не предоставлен")
    out = {k: v for k, v in record.items() if k != "enc"}
    out.update(_open_fields(record["enc"], dek, _record_aad(record)))
    return out


def seal_records(records: list[dict], dek: bytes) -> list[dict]:
    return [seal_record(r, dek) for r in records]


def open_records(records: list[dict], dek: bytes | None) -> list[dict]:
    return [open_record(r, dek) for r in records]


def seal_identity(data: dict, dek: bytes) -> dict:
    if isinstance(data.get("enc"), dict):
        return dict(data)
    out = {k: v for k, v in data.items() if k not in SEALED_IDENTITY_FIELDS}
    fields = {k: data[k] for k in SEALED_IDENTITY_FIELDS if k in data}
    if not fields:
        return out
    out["enc"] = _seal_fields(fields, dek, _AAD_IDENTITY)
    return out


def open_identity(data: dict, dek: bytes | None) -> dict:
    if not isinstance(data.get("enc"), dict):
        return dict(data)
    if dek is None:
        raise SealedDataError("identity зашифрован, ключ не предоставлен")
    out = {k: v for k, v in data.items() if k != "enc"}
    out.update(_open_fields(data["enc"], dek, _AAD_IDENTITY))
    return out


def seal_session(messages: list[dict], dek: bytes, item_id: str) -> dict:
    return _seal_fields({"messages": messages}, dek,
                        _AAD_SESSION_PREFIX + item_id.encode("utf-8"))


def open_session(enc: dict, dek: bytes, item_id: str) -> list[dict]:
    fields = _open_fields(enc, dek, _AAD_SESSION_PREFIX + item_id.encode("utf-8"))
    return fields.get("messages") or []


BLOB_MAGIC = b"MAIDSEAL"
_BLOB_NONCE_LEN = 12
_BLOB_TAG_LEN = 16
_AAD_BLOB_PREFIX = b"maid-blob-v1:"
_AAD_GALLERY_INDEX = b"maid-gallery-index-v1"


def is_sealed_blob(data: bytes) -> bool:
    return isinstance(data, (bytes, bytearray)) and \
        bytes(data[:len(BLOB_MAGIC)]) == BLOB_MAGIC


def seal_blob(data: bytes, dek: bytes, name: str) -> bytes:
    nonce = os.urandom(_BLOB_NONCE_LEN)
    ct = AESGCM(dek).encrypt(nonce, bytes(data),
                             _AAD_BLOB_PREFIX + name.encode("utf-8"))
    return BLOB_MAGIC + bytes([CRYPTO_VERSION]) + nonce + ct


def open_blob(blob: bytes, dek: bytes | None, name: str) -> bytes:
    if not is_sealed_blob(blob):
        return bytes(blob)
    if dek is None:
        raise SealedDataError(f"{name}: запечатан, ключ не предоставлен")
    head = len(BLOB_MAGIC) + 1
    if len(blob) < head + _BLOB_NONCE_LEN + _BLOB_TAG_LEN:
        raise SealedDataError(f"{name}: блоб короче заголовка")
    version = blob[len(BLOB_MAGIC)]
    if version > CRYPTO_VERSION:
        raise SealedDataError(
            f"{name}: crypto v{version} новее поддерживаемой v{CRYPTO_VERSION} — "
            f"обновите приложение")
    nonce = bytes(blob[head:head + _BLOB_NONCE_LEN])
    ct = bytes(blob[head + _BLOB_NONCE_LEN:])
    try:
        return AESGCM(dek).decrypt(nonce, ct, _AAD_BLOB_PREFIX + name.encode("utf-8"))
    except InvalidTag as e:
        raise SealedDataError(
            f"{name}: блоб не расшифровался: другой ключ, повреждение или подмена") from e


def seal_gallery_index(items: list, dek: bytes) -> dict:
    return _seal_fields({"items": list(items)}, dek, _AAD_GALLERY_INDEX)


def open_gallery_index(data, dek: bytes | None) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("c"), str):
        if dek is None:
            raise SealedDataError("индекс галереи запечатан, ключ не предоставлен")
        return list(_open_fields(data, dek, _AAD_GALLERY_INDEX).get("items") or [])
    return []
