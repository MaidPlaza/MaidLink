from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

LLAMA = "llama"
COMFY = "comfy"
LLAMA_KEY_ENV = "LLAMA_API_KEY"
COMFY_TOKEN_ENV = "MAIDLINK_COMFY_TOKEN"

_secret: str | None = None
_keys: dict[str, str] = {}


def _base_secret() -> str:
    global _secret
    if _secret is None:
        from api import local_guard
        token = local_guard.current_token() or local_guard.read_tool_token()
        _secret = token if local_guard.valid_token(token) else secrets.token_urlsafe(32)
    return _secret


def key(service: str) -> str:
    value = _keys.get(service)
    if value is None:
        digest = hmac.new(_base_secret().encode("utf-8"),
                          f"maidlink-{service}-v1".encode("utf-8"), hashlib.sha256).digest()
        value = _keys[service] = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return value


def headers(service: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key(service)}"}


def reset() -> None:
    global _secret
    _secret = None
    _keys.clear()
