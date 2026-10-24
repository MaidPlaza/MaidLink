import logging
import os
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _setup_file_logging() -> None:
    if not getattr(sys, "frozen", False):
        return
    try:
        from app_paths import PROJECT_ROOT
        log_dir = PROJECT_ROOT / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "backend.log"
        if log_file.exists() and log_file.stat().st_size > 5 * 1024 * 1024:
            bak = log_dir / "backend.log.1"
            try:
                bak.unlink()
            except OSError:
                pass
            try:
                log_file.rename(bak)
            except OSError:
                pass
        f = open(log_file, "a", buffering=1, encoding="utf-8", errors="replace")
    except Exception:
        return

    class _Tee:
        def __init__(self, stream, fileobj):
            self._streams = [s for s in (stream, fileobj) if s is not None]

        def write(self, data):
            for s in self._streams:
                try:
                    s.write(data)
                    s.flush()
                except Exception:
                    pass

        def flush(self):
            for s in self._streams:
                try:
                    s.flush()
                except Exception:
                    pass

        def isatty(self):
            return False

        def fileno(self):
            for s in self._streams:
                try:
                    return s.fileno()
                except Exception:
                    pass
            raise OSError("Tee: нет базового fileno")

        encoding = "utf-8"

    sys.stdout = _Tee(sys.stdout, f)
    sys.stderr = _Tee(sys.stderr, f)
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    from datetime import datetime
    print(f"\n===== MaidLink backend start {datetime.now():%Y-%m-%d %H:%M:%S} "
          f"pid={os.getpid()} =====", flush=True)


class _RelocationStatus:
    def __init__(self) -> None:
        self.done = self.total = 0
        self._srv = None

    def update(self, done: int, total: int) -> None:
        self.done, self.total = done, total
        if self._srv is None:
            self._start()

    def _start(self) -> None:
        import http.server
        import json
        import threading
        from api import local_guard as guard
        status = self
        token = guard.resolve_api_token()
        try:
            port = int(os.environ.get("MAIDLINK_PORT", "8001"))
        except ValueError:
            port = 8001

        class _Handler(http.server.BaseHTTPRequestHandler):
            def _reply(self, code: int, payload: dict | None = None, extra=()):
                body = json.dumps(payload).encode("utf-8") if payload is not None else b""
                origin = self.headers.get("Origin")
                self.send_response(code)
                if guard.cors_origin_allowed(origin):
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Vary", "Origin")
                for name, value in extra:
                    self.send_header(name, value)
                if payload is not None:
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def _refused(self, need_token: bool) -> bool:
                if not guard.host_allowed(self.headers.get("Host"), port):
                    self._reply(400, {"error": "invalid host"})
                elif not guard.origin_allowed(self.headers.get("Origin"), port):
                    self._reply(403, {"error": "origin not allowed"})
                elif need_token and not guard.token_matches(
                        self.headers.get(guard.TOKEN_HEADER), token):
                    self._reply(401, {"error": "unauthorized"})
                else:
                    return False
                return True

            def do_OPTIONS(self):
                if self._refused(need_token=False):
                    return
                if not guard.cors_origin_allowed(self.headers.get("Origin")):
                    self._reply(400, {"error": "not a preflight from the app"})
                    return
                self._reply(204, None, (
                    ("Access-Control-Allow-Methods", "GET, OPTIONS"),
                    ("Access-Control-Allow-Headers", f"Content-Type, {guard.TOKEN_HEADER}"),
                    ("Access-Control-Max-Age", "600"),
                ))

            def do_GET(self):
                if self._refused(need_token=True):
                    return
                self._reply(200 if self.path.startswith("/api/migration") else 503,
                            {"migrating": True, "done": status.done, "total": status.total})

            def log_message(self, *args):
                pass

        try:
            host = os.environ.get("MAIDLINK_HOST", "127.0.0.1")
            self._srv = http.server.ThreadingHTTPServer((host, port), _Handler)
            threading.Thread(target=self._srv.serve_forever, daemon=True).start()
        except OSError:
            self._srv = False

    def close(self) -> None:
        if self._srv:
            self._srv.shutdown()
            self._srv.server_close()


def _migrate_data_root() -> None:
    if not getattr(sys, "frozen", False):
        return
    try:
        import app_paths
        from services.data_migration import _has_content, ensure_data_root, relocate_data
        legacy = app_paths.legacy_data_root()
        status = _RelocationStatus()
        try:
            ok, lines = relocate_data(app_paths.PROJECT_ROOT, legacy, progress=status.update)
        finally:
            status.close()
        for line in lines:
            print(line, flush=True)
        if not ok and legacy is not None and _has_content(legacy):
            app_paths.PROJECT_ROOT = legacy
            print(f"[relocate] этот запуск — со старого места: {legacy}", flush=True)
        for line in ensure_data_root(data_root=app_paths.PROJECT_ROOT):
            print(line, flush=True)
    except Exception as e:
        print(f"[migrate] ошибка миграции данных: {type(e).__name__}: {e}",
              flush=True)


_setup_file_logging()
_migrate_data_root()


def main() -> None:
    import uvicorn
    from api.server import app

    host = os.environ.get("MAIDLINK_HOST", "127.0.0.1")
    port = int(os.environ.get("MAIDLINK_PORT", "8001"))
    print(f"[backend] uvicorn -> http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
