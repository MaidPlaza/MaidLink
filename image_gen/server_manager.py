from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from app_paths import ASSETS_ROOT
from config import ImageGenConfig
from image_gen.comfyui_client import ComfyUIClient
from services import child_auth

GUARD_SCRIPT = Path("image_gen") / "comfy_guard.py"

_FROZEN = getattr(sys, "frozen", False)

LOG_NAME = "comfyui"
LOG_MAX_BYTES = 5 * 1024 * 1024


class ComfyUIServerManager:
    def __init__(self, config: ImageGenConfig, project_root: Path,
                 assets_root: Path | None = None) -> None:
        self.config = config
        self.project_root = project_root
        self.assets_root = assets_root if assets_root is not None else ASSETS_ROOT
        self._proc: Optional[subprocess.Popen] = None
        self._log_file = None
        self.missing_nodes: Optional[list[str]] = None
        self.held: Optional[str] = None
        self.comfy_output_dir = project_root / config.comfy_output_dir
        self.client = ComfyUIClient(
            base_url=config.base_url,
            output_dir=project_root / config.output_dir,
            comfy_output_dir=self.comfy_output_dir,
        )

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def is_responsive(self, timeout_sec: float = 1.0) -> bool:
        return self.client.is_responsive(timeout_sec)

    def start(self) -> None:
        if self.is_running():
            print("[comfy-mgr] Уже запущен (наш процесс)")
            return
        if self.held:
            raise RuntimeError(f"ComfyUI остановлен: {self.held}")

        status = self.client.probe(timeout_sec=0.5)
        if status == 200:
            print(f"[comfy-mgr] Уже отвечает на {self.config.base_url} "
                  f"(запущен извне) — принимаем как готовый")
            if self.client.probe(timeout_sec=0.5, auth=False) == 200:
                print("[comfy-mgr] Внешний ComfyUI без защиты порта (запущен не "
                      "приложением) — Host и ключ не проверяет")
            self._check_nodes()
            return
        if status == 401:
            raise RuntimeError(
                f"На {self.config.base_url} отвечает ComfyUI с чужим ключом "
                f"(остался от прошлого запуска?) — закройте его и повторите.")

        guard = self.assets_root / GUARD_SCRIPT
        if not guard.is_file():
            raise FileNotFoundError(
                f"Лаунчер защиты ComfyUI не найден: {guard} — без него не запускаю.")

        cmd = []
        for arg in self.config.launch_command:
            if arg.startswith("image_gen/") or arg.startswith("models/"):
                cmd.append(str(self.project_root / arg))
            else:
                cmd.append(arg)
        if "--output-directory" not in cmd:
            cmd += ["--output-directory", str(self.comfy_output_dir)]
        main_i = next((i for i, a in enumerate(cmd) if a.lower().endswith("main.py")), None)
        if main_i is None:
            raise RuntimeError("В ImageGenConfig.launch_command нет main.py ComfyUI — "
                               "лаунчеру защиты нечего запускать.")
        cmd.insert(main_i, str(guard))

        print(f"[comfy-mgr] Запуск: {' '.join(cmd[:main_i + 2])} ...")

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            if _FROZEN:
                creationflags |= subprocess.CREATE_NO_WINDOW

        env = dict(os.environ)
        env[child_auth.COMFY_TOKEN_ENV] = child_auth.key(child_auth.COMFY)
        out = self._open_log() if _FROZEN else None
        if out is not None:
            env["PYTHONUNBUFFERED"] = "1"
        self._proc = subprocess.Popen(
            cmd,
            cwd=str(self.project_root),
            creationflags=creationflags,
            stdout=out,
            stderr=subprocess.STDOUT if out is not None else None,
            env=env,
        )

        self.wait_for_ready()
        self._check_locked()
        self._check_nodes()

    def _open_log(self):
        self._close_log()
        try:
            log_dir = Path(self.project_root) / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            path = log_dir / f"{LOG_NAME}.log"
            if path.exists() and path.stat().st_size > LOG_MAX_BYTES:
                bak = log_dir / f"{LOG_NAME}.log.1"
                bak.unlink(missing_ok=True)
                path.rename(bak)
            f = open(path, "a", encoding="utf-8", errors="replace", buffering=1)
            f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} запуск =====\n")
            self._log_file = f
            return f
        except OSError:
            return None

    def _close_log(self) -> None:
        if self._log_file is not None:
            try:
                self._log_file.close()
            except OSError:
                pass
            self._log_file = None

    def workflow_node_types(self) -> list[str]:
        try:
            wf = json.loads((self.assets_root / self.config.workflow_default)
                            .read_text(encoding="utf-8"))
            return sorted({n["class_type"] for n in wf.values()
                           if isinstance(n, dict) and n.get("class_type")})
        except (OSError, ValueError, AttributeError):
            return []

    def _check_nodes(self) -> None:
        types = self.workflow_node_types()
        self.missing_nodes = self.client.missing_node_types(types) if types else None
        if self.missing_nodes:
            print(f"[comfy-mgr] ComfyUI не знает узлы workflow: "
                  f"{', '.join(self.missing_nodes)} — рисование выключено до "
                  f"перезапуска (ошибки импорта — в logs/{LOG_NAME}.log)")
        elif self.missing_nodes is None and types:
            print("[comfy-mgr] Узлы workflow проверить не удалось (/object_info не ответил)")

    def _check_locked(self) -> None:
        status = self.client.probe(timeout_sec=5.0, auth=False)
        if status != 401:
            self.stop()
            raise RuntimeError(
                f"ComfyUI ответил без ключа (HTTP {status}) — защита порта не "
                f"встала, ComfyUI остановлен. Смотри «[MaidLink guard]» в его логе "
                f"(в билде — logs/{LOG_NAME}.log).")
        print("[comfy-mgr] Порт закрыт: Host и ключ запуска (без ключа — 401)")

    def wait_for_ready(self, timeout_sec: Optional[int] = None) -> None:
        timeout = timeout_sec or self.config.server_startup_timeout_sec
        deadline = time.time() + timeout

        while time.time() < deadline:
            if self.is_responsive():
                elapsed = timeout - (deadline - time.time())
                print(f"[comfy-mgr] Готов за {elapsed:.1f}s")
                return
            if self._proc and self._proc.poll() is not None:
                raise RuntimeError(
                    f"ComfyUI упал при старте, exit={self._proc.returncode}. "
                    f"Смотри его вывод (в билде — logs/{LOG_NAME}.log): модель не "
                    f"найдена? CUDA? битый custom_node?"
                )
            time.sleep(1.0)

        self.stop()
        raise TimeoutError(
            f"ComfyUI не ответил за {timeout}s. "
            f"При первом запуске custom_nodes могут долго ставить зависимости — "
            f"увеличь ImageGenConfig.server_startup_timeout_sec."
        )

    def stop(self) -> None:
        if not self.is_running():
            return

        proc = self._proc
        timeout = self.config.server_shutdown_timeout_sec

        print(f"[comfy-mgr] Остановка (PID {proc.pid})...")

        try:
            if os.name == "nt" and not _FROZEN:
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                proc.terminate()
        except Exception as e:
            print(f"[comfy-mgr] Сигнал остановки не отправился: {e}")

        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f"[comfy-mgr] Не завершился за {timeout}s — kill()")
            proc.kill()
            proc.wait(timeout=5)

        self._proc = None
        self._close_log()

    def hold(self, reason: str) -> None:
        self.held = reason
        if not self.is_running() and self.is_responsive(timeout_sec=0.5):
            print("[comfy-mgr] ComfyUI запущен не приложением — остановить его "
                  "нечем, установка пойдёт при работающем")
        self.stop()

    def release(self) -> None:
        self.held = None

    def free_vram(self) -> None:
        self.client.free_memory(unload_models=True, free_memory=True)

    def ensure_started(self) -> None:
        if self.is_running():
            return
        if self.is_responsive(timeout_sec=0.5):
            return
        print("[comfy-mgr] ComfyUI не отвечает — поднимаю перед рендером...")
        self.start()
