from __future__ import annotations

import hashlib
import io
import os
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b"MAIDLINK"
CONTAINER_VERSION = 1
HEADER_LEN = 32
_NONCE_OFF = 16
_BLOCK = 16
_KEY = hashlib.sha256(b"MAIDLINK container v1 / not a security boundary").digest()


class ContainerError(Exception):
    pass


def is_container(head: bytes) -> bool:
    return head[:len(MAGIC)] == MAGIC


def _counter(nonce: bytes, offset: int) -> bytes:
    n = (int.from_bytes(nonce, "big") + offset // _BLOCK) % (1 << 128)
    return n.to_bytes(16, "big")


def _xcrypt(nonce: bytes, offset: int, data: bytes) -> bytes:
    skip = offset % _BLOCK
    c = Cipher(algorithms.AES(_KEY), modes.CTR(_counter(nonce, offset))).encryptor()
    if skip:
        c.update(b"\0" * skip)
    return c.update(data) + c.finalize()


def seal(zip_bytes: bytes) -> bytes:
    nonce = os.urandom(16)
    header = MAGIC + bytes([CONTAINER_VERSION]) + b"\0" * 7 + nonce
    return header + _xcrypt(nonce, 0, zip_bytes)


def _parse_header(head: bytes) -> bytes:
    if len(head) < HEADER_LEN or not is_container(head):
        raise ContainerError("не файл персонажа MaidLink")
    if head[len(MAGIC)] != CONTAINER_VERSION:
        raise ContainerError(
            f"версия контейнера {head[len(MAGIC)]} новее этого билда — обновите приложение")
    return head[_NONCE_OFF:HEADER_LEN]


def unseal(blob: bytes) -> bytes:
    if blob[:2] == b"PK":
        return blob
    nonce = _parse_header(blob[:HEADER_LEN])
    return _xcrypt(nonce, 0, blob[HEADER_LEN:])


class _CtrReader(io.RawIOBase):
    def __init__(self, f: BinaryIO, nonce: bytes, size: int):
        self._f = f
        self._nonce = nonce
        self._size = size
        self._pos = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._pos, io.SEEK_END: self._size}[whence]
        self._pos = max(0, base + offset)
        return self._pos

    def readinto(self, b) -> int:
        n = min(len(b), max(0, self._size - self._pos))
        if n <= 0:
            return 0
        self._f.seek(HEADER_LEN + self._pos)
        data = self._f.read(n)
        plain = _xcrypt(self._nonce, self._pos, data)
        b[:len(plain)] = plain
        self._pos += len(plain)
        return len(plain)

    def close(self) -> None:
        try:
            self._f.close()
        finally:
            super().close()


@contextmanager
def open_zip(path: Path | str) -> Iterator[zipfile.ZipFile]:
    f = open(path, "rb")
    try:
        head = f.read(HEADER_LEN)
        if head[:2] == b"PK":
            f.seek(0)
            src: BinaryIO = f
        else:
            nonce = _parse_header(head)
            size = os.fstat(f.fileno()).st_size - HEADER_LEN
            src = io.BufferedReader(_CtrReader(f, nonce, size), buffer_size=1 << 16)
    except BaseException:
        f.close()
        raise
    try:
        with zipfile.ZipFile(src, "r") as zf:
            yield zf
    finally:
        src.close()
        f.close()


def write_zip_bytes(entries) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as zf:
        for name, data, ctype in entries:
            zf.writestr(name, data, compress_type=ctype)
    return buf.getvalue()


def file_format(path: Path | str) -> str:
    with open(path, "rb") as f:
        head = f.read(HEADER_LEN)
    if is_container(head):
        return "container"
    if head[:2] == b"PK":
        return "zip"
    return "unknown"
