from __future__ import annotations

import hmac
import importlib.abc
import importlib.machinery
import logging
import os
import re
import runpy
import sys

TOKEN_ENV = "MAIDLINK_COMFY_TOKEN"
LOCAL_HOSTNAMES = ("127.0.0.1", "localhost")
DEFAULT_PORT = 8188
_TOKEN_RX = re.compile(r"[A-Za-z0-9._~-]{16,256}")


def valid_token(token: str | None) -> bool:
    return bool(token) and _TOKEN_RX.fullmatch(token) is not None


def host_allowed(host: str | None, port: int) -> bool:
    return bool(host) and host.strip().lower() in {f"{h}:{port}" for h in LOCAL_HOSTNAMES}


def bearer_matches(header: str | None, token: str) -> bool:
    if not header or not token or not header.startswith("Bearer "):
        return False
    return hmac.compare_digest(header[len("Bearer "):].strip().encode("utf-8"),
                               token.encode("utf-8"))


def port_from_args(args: list[str]) -> int:
    for i, a in enumerate(args):
        value = None
        if a == "--port" and i + 1 < len(args):
            value = args[i + 1]
        elif a.startswith("--port="):
            value = a.split("=", 1)[1]
        if value is not None:
            try:
                return int(value)
            except ValueError:
                break
    return DEFAULT_PORT


def make_middleware(token: str, default_port: int):
    from aiohttp import web

    @web.middleware
    async def maidlink_guard(request, handler):
        port = default_port
        transport = request.transport
        sock = transport.get_extra_info("sockname") if transport is not None else None
        if sock and len(sock) > 1:
            port = sock[1]
        host = request.headers.get("Host")
        if not host_allowed(host, port):
            logging.warning("[MaidLink guard] foreign Host %r (%s %s) -> 400",
                            host, request.method, request.path)
            return web.json_response({"error": "invalid host"}, status=400)
        if not bearer_matches(request.headers.get("Authorization"), token):
            logging.warning("[MaidLink guard] no launch token (%s %s) -> 401",
                            request.method, request.path)
            return web.json_response({"error": "unauthorized"}, status=401)
        return await handler(request)

    return maidlink_guard


def guard_prompt_server(server_module, token: str, default_port: int) -> None:
    cls = server_module.PromptServer
    original_init = cls.__init__

    def __init__(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.app.middlewares.insert(0, make_middleware(token, default_port))
        logging.info("[MaidLink guard] ComfyUI port locked: local Host + launch token")

    cls.__init__ = __init__


def _inside(path: str | None, folder: str) -> bool:
    if not path:
        return False
    path = os.path.normcase(os.path.abspath(path))
    return os.path.dirname(path) == folder


class GuardServerImport(importlib.abc.MetaPathFinder):
    def __init__(self, comfy_dir: str, on_import):
        self.comfy_dir = os.path.normcase(os.path.abspath(comfy_dir))
        self.on_import = on_import
        self.fired = False

    def find_spec(self, fullname, path=None, target=None):
        if fullname != "server" or self.fired:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None or not _inside(spec.origin, self.comfy_dir):
            return None
        self.fired = True
        if self in sys.meta_path:
            sys.meta_path.remove(self)
        exec_module = spec.loader.exec_module
        on_import = self.on_import

        def exec_and_guard(module):
            exec_module(module)
            on_import(module)

        spec.loader.exec_module = exec_and_guard
        return spec


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or not argv[0].lower().endswith(".py"):
        sys.exit("comfy_guard: usage: comfy_guard.py <ComfyUI/main.py> [ComfyUI args]")
    token = os.environ.pop(TOKEN_ENV, "").strip()
    if not valid_token(token):
        sys.exit(f"comfy_guard: no launch token in {TOKEN_ENV} - refusing to start "
                 f"ComfyUI unprotected")
    main_py = os.path.abspath(argv[0])
    comfy_dir = os.path.dirname(main_py)
    port = port_from_args(argv[1:])
    sys.meta_path.insert(0, GuardServerImport(
        comfy_dir, lambda module: guard_prompt_server(module, token, port)))
    sys.argv = [main_py] + argv[1:]
    if comfy_dir not in sys.path:
        sys.path.insert(0, comfy_dir)
    runpy.run_path(main_py, run_name="__main__")


if __name__ == "__main__":
    main()
