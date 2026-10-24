from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sys
from pathlib import Path
from urllib.parse import parse_qsl

API_TOKEN_ENV = "MAIDLINK_API_TOKEN"
TOKEN_HEADER = "X-MaidLink-Token"
MEDIA_PARAM = "mt"
WS_PROTOCOL = "maidlink"
WS_TOKEN_PREFIX = "maidlink-token."
MEDIA_LABEL = b"maidlink-media-v1"
_TOKEN_RX = re.compile(r"[A-Za-z0-9._~-]{16,256}")

APP_ORIGINS = ("file://", "null", "http://localhost:5173", "http://127.0.0.1:5173")
LOCAL_HOSTNAMES = ("127.0.0.1", "localhost")

MEDIA_PATHS = tuple(re.compile(p) for p in (
    r"/media/generated/.+",
    r"/api/webimg",
    r"/api/avatar/[^/]+",
    r"/api/characters/[^/]+/avatar/[^/]+",
    r"/api/characters/[^/]+/ui/list-avatar",
    r"/api/gallery/[A-Za-z0-9_-]+",
))

_IS_FROZEN = bool(getattr(sys, "frozen", False))


def valid_token(token: str | None) -> bool:
    return bool(token) and _TOKEN_RX.fullmatch(token) is not None


def media_token(token: str) -> str:
    digest = hmac.new(token.encode("utf-8"), MEDIA_LABEL, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


_TOKEN: str | None = None


def resolve_api_token() -> str:
    global _TOKEN
    if _TOKEN is None:
        token = os.environ.pop(API_TOKEN_ENV, "").strip()
        if not valid_token(token):
            if token:
                print(f"[auth] {API_TOKEN_ENV} не годится (нужно 16+ символов "
                      f"A-Z a-z 0-9 . _ ~ -) — завожу свой токен", flush=True)
            token = secrets.token_urlsafe(32)
        _TOKEN = token
    return _TOKEN


def current_token() -> str | None:
    return _TOKEN


def token_matches(provided: str | None, expected: str) -> bool:
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def token_file(root: Path | str | None = None) -> Path:
    if root is None:
        from app_paths import PROJECT_ROOT as root
    return Path(root) / "runtime_cache" / "api_token"


def publish_token_file(token: str, root: Path | str | None = None) -> Path | None:
    if _IS_FROZEN:
        return None
    path = token_file(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(token, encoding="utf-8")
    except OSError as e:
        print(f"[auth] файл токена не записан ({path}): {e}", flush=True)
        return None
    return path


def retract_token_file(token: str, root: Path | str | None = None) -> None:
    path = token_file(root)
    try:
        if path.read_text(encoding="utf-8").strip() == token:
            path.unlink()
    except OSError:
        pass


def read_tool_token(root: Path | str | None = None) -> str:
    token = os.environ.get(API_TOKEN_ENV, "").strip()
    if valid_token(token):
        return token
    try:
        token = token_file(root).read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return token if valid_token(token) else ""


def tool_headers(root: Path | str | None = None) -> dict[str, str]:
    token = read_tool_token(root)
    return {TOKEN_HEADER: token} if token else {}


def allowed_hosts(port: int) -> frozenset[str]:
    hosts = {f"{h}:{port}" for h in LOCAL_HOSTNAMES}
    if port == 80:
        hosts.update(LOCAL_HOSTNAMES)
    return frozenset(hosts)


def host_allowed(host: str | None, port: int) -> bool:
    return bool(host) and host.strip().lower() in allowed_hosts(port)


def cors_origin_allowed(origin: str | None) -> bool:
    return origin is not None and origin.strip().lower() in APP_ORIGINS


def origin_allowed(origin: str | None, port: int) -> bool:
    if origin is None:
        return True
    o = origin.strip().lower()
    return o in APP_ORIGINS or o in {f"http://{h}:{port}" for h in LOCAL_HOSTNAMES}


def is_media_path(path: str) -> bool:
    return any(rx.fullmatch(path) for rx in MEDIA_PATHS)


def _scope_headers(scope) -> dict[str, str]:
    return {k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in (scope.get("headers") or ())}


def _server_port(scope) -> int:
    server = scope.get("server")
    if server and len(server) > 1 and server[1]:
        return int(server[1])
    try:
        return int(os.environ.get("MAIDLINK_PORT", "8001"))
    except ValueError:
        return 8001


async def _deny(scope, receive, send, status: int, error: str) -> None:
    body = json.dumps({"error": error}).encode("utf-8")
    headers = [(b"content-type", b"application/json"),
               (b"content-length", str(len(body)).encode("ascii"))]
    if scope["type"] == "http":
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})
        return
    message = await receive()
    if message.get("type") != "websocket.connect":
        return
    if "websocket.http.response" in (scope.get("extensions") or {}):
        await send({"type": "websocket.http.response.start", "status": status,
                    "headers": headers})
        await send({"type": "websocket.http.response.body", "body": body})
    else:
        await send({"type": "websocket.close", "code": 1008})


class HostGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            host = _scope_headers(scope).get("host")
            if not host_allowed(host, _server_port(scope)):
                await _deny(scope, receive, send, 400, "invalid host")
                return
        await self.app(scope, receive, send)


class TokenGuard:
    def __init__(self, app, token: str):
        if not valid_token(token):
            raise ValueError("токен локального API не годится")
        self.app = app
        self.token = token
        self.media = media_token(token)

    def _authorized(self, scope, headers: dict[str, str]) -> bool:
        if token_matches(headers.get(TOKEN_HEADER.lower()), self.token):
            return True
        if scope["type"] == "websocket":
            for proto in scope.get("subprotocols") or ():
                if (proto.startswith(WS_TOKEN_PREFIX)
                        and token_matches(proto[len(WS_TOKEN_PREFIX):], self.token)):
                    return True
            return False
        if scope.get("method") in ("GET", "HEAD") and is_media_path(scope.get("path", "")):
            query = (scope.get("query_string") or b"").decode("latin-1")
            for key, value in parse_qsl(query, keep_blank_values=True):
                if key == MEDIA_PARAM and token_matches(value, self.media):
                    return True
        return False

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = _scope_headers(scope)
        if not origin_allowed(headers.get("origin"), _server_port(scope)):
            await _deny(scope, receive, send, 403, "origin not allowed")
            return
        if not self._authorized(scope, headers):
            await _deny(scope, receive, send, 401, "unauthorized")
            return
        if scope["type"] == "websocket" and WS_PROTOCOL in (scope.get("subprotocols") or ()):
            send = _accept_with_protocol(send)
        await self.app(scope, receive, send)


def _accept_with_protocol(send):
    async def wrapped(message):
        if message.get("type") == "websocket.accept" and not message.get("subprotocol"):
            message = {**message, "subprotocol": WS_PROTOCOL}
        await send(message)
    return wrapped


def install(app, token: str) -> None:
    from starlette.middleware.cors import CORSMiddleware
    app.add_middleware(TokenGuard, token=token)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(APP_ORIGINS),
        allow_methods=["*"],
        allow_headers=["Content-Type", TOKEN_HEADER],
    )
    app.add_middleware(HostGuard)


_MEDIA_IN_URL_RX = re.compile(r"([?&]" + MEDIA_PARAM + r"=)[^&\s\"']+")


class RedactMediaToken(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(_MEDIA_IN_URL_RX.sub(r"\1‹скрыт›", a) if isinstance(a, str) else a
                                for a in record.args)
        if isinstance(record.msg, str) and MEDIA_PARAM + "=" in record.msg:
            record.msg = _MEDIA_IN_URL_RX.sub(r"\1‹скрыт›", record.msg)
        return True


def install_log_redaction() -> None:
    for name in ("uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, RedactMediaToken) for f in logger.filters):
            logger.addFilter(RedactMediaToken())
