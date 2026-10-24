from __future__ import annotations

import collections
import os
import signal
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import httpx

from config import FIT_SLACK_MIB, LLMConfig, VRAM_FREE_MIB, VRAM_RESERVE_MIB
from services import child_auth

_FROZEN = getattr(sys, "frozen", False)

LOG_MAX_BYTES = 5 * 1024 * 1024
TAIL_LINES = 40


class LlamaServerManager:
    def __init__(self, config: LLMConfig, project_root: Path,
                 assets_root: Path | None = None, log_name: str = "llama-server") -> None:
        self.config = config
        self.project_root = project_root
        self.assets_root = assets_root if assets_root is not None else project_root
        self.log_name = log_name
        self._proc: Optional[subprocess.Popen] = None
        self._log_file = None
        self._tail: collections.deque = collections.deque(maxlen=TAIL_LINES)
        self._pump: Optional[threading.Thread] = None

    @property
    def pid(self) -> Optional[int]:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc.pid
        return None

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def exit_code(self) -> Optional[int]:
        if self._proc is not None and self._proc.poll() is not None:
            return self._proc.returncode
        return None

    def crash_report(self) -> str:
        if self._pump is not None:
            self._pump.join(timeout=1.0)
        code = self.exit_code()
        text = "exit=?" if code is None else f"exit={code} (0x{code & 0xFFFFFFFF:08X})"
        tail = [ln for ln in self._tail if ln.strip()][-12:]
        if tail:
            text += "; последние строки вывода:\n    " + "\n    ".join(tail)
        return text

    def take_crash_report(self) -> Optional[str]:
        if self.exit_code() is None:
            return None
        report = self.crash_report()
        self._proc = None
        return report

    def _open_app_log(self):
        try:
            log_dir = Path(self.project_root) / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            path = log_dir / f"{self.log_name}.log"
            if path.exists() and path.stat().st_size > LOG_MAX_BYTES:
                bak = log_dir / f"{self.log_name}.log.1"
                bak.unlink(missing_ok=True)
                path.rename(bak)
            f = open(path, "a", encoding="utf-8", errors="replace", buffering=1)
            f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} запуск =====\n")
            return f
        except OSError:
            return None

    def _pump_output(self, stream, fileobj) -> None:
        echo = not _FROZEN
        try:
            for raw in iter(stream.readline, b""):
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                self._tail.append(line)
                if fileobj is not None:
                    try:
                        fileobj.write(line + "\n")
                    except Exception:
                        pass
                if echo:
                    try:
                        sys.stdout.write(line + "\n")
                        sys.stdout.flush()
                    except Exception:
                        pass
        finally:
            if fileobj is not None:
                try:
                    fileobj.close()
                except Exception:
                    pass

    def _probe(self, timeout_sec: float = 1.0, auth: bool = True) -> int:
        try:
            r = httpx.get(f"{self.config.base_url}/v1/models", timeout=timeout_sec,
                          headers=child_auth.headers(child_auth.LLAMA) if auth else None)
            return r.status_code
        except Exception:
            return -1

    def is_responsive(self, timeout_sec: float = 1.0) -> bool:
        return self._probe(timeout_sec) == 200

    def _check_locked(self) -> None:
        status = self._probe(timeout_sec=5.0, auth=False)
        if status != 401:
            self.stop()
            raise RuntimeError(
                f"llama-server ответил без ключа (HTTP {status}) — защита порта "
                f"не встала, сервер остановлен. Проверь LLAMA_API_KEY у сборки "
                f"{self.config.server_binary}.")
        print("[llama-mgr] Порт закрыт ключом запуска (без ключа — 401)")

    def _has_auto_ngl(self) -> bool:
        args = list(self.config.server_launch_args) + list(
            getattr(self.config, "server_extra_args", []) or [])
        for i, a in enumerate(args[:-1]):
            if a in ("-ngl", "--gpu-layers", "--n-gpu-layers"):
                return str(args[i + 1]).lower() == "auto"
        return False

    @staticmethod
    def _bump_fit_target(extra: list[str], side_files: list[Path],
                         extra_mib: int = 0, reserve: int | None = None) -> list[str]:
        base_reserve = VRAM_RESERVE_MIB if reserve is None else max(0, int(reserve))
        add = max(0, int(extra_mib or 0))
        for p in side_files:
            try:
                add += -(-p.stat().st_size // (1024 * 1024))
            except OSError:
                pass
        out = list(extra)
        for i, a in enumerate(out[:-1]):
            if a in ("--fit-target", "-fitt"):
                if add <= 0:
                    return out
                try:
                    base = int(str(out[i + 1]).split(",")[0])
                except ValueError:
                    base = base_reserve
                out[i + 1] = str(base + add)
                print(f"[llama-mgr] fit-target {base} + {add} МиБ "
                      f"(проектор/драфтер после fit + слепое пятно CUDA) = {base + add}")
                return out
        target = base_reserve + add
        out += ["--fit-target", str(target)]
        print(f"[llama-mgr] fit-target: запас {base_reserve} + {add} МиБ "
              f"(проектор/драфтер после fit + слепое пятно CUDA) = {target}")
        return out

    def _reserve_total(self) -> int:
        free = getattr(self.config, "vram_free_mib", None)
        free = VRAM_FREE_MIB if free is None else max(0, int(free))
        print(f"[llama-mgr] запас VRAM: свободно после загрузки ≥{free} МиБ "
              f"+ промах fit {FIT_SLACK_MIB} МиБ")
        return free + FIT_SLACK_MIB

    @staticmethod
    def _parse_cuda_free_mib(text: str) -> int:
        for line in (text or "").splitlines():
            m = re.search(r"CUDA\d+:.*?\(\s*\d+\s*MiB,\s*(\d+)\s*MiB free\)", line)
            if m:
                return int(m.group(1))
        return -1

    def _cuda_free_gap_mib(self) -> int:
        try:
            out = subprocess.run(
                [str(self.assets_root / self.config.server_binary), "--list-devices"],
                capture_output=True, text=True, timeout=30,
                creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
                env=self._child_env(),
            )
            cuda_free = self._parse_cuda_free_mib((out.stdout or "") + (out.stderr or ""))
        except Exception:
            return 0
        nvml_free = self._vram_free_mb()
        if cuda_free < 0 or nvml_free < 0:
            return 0
        gap = max(0, cuda_free - nvml_free)
        print(f"[llama-mgr] VRAM: CUDA видит свободными {cuda_free} MiB, реально "
              f"свободно {nvml_free} MiB → +{gap} МиБ к запасу fit")
        return gap

    @staticmethod
    def _vram_free_mb() -> int:
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.free",
                 "--format=csv,noheader,nounits"],
                text=True, timeout=5,
            )
            return int(out.strip().splitlines()[0])
        except Exception:
            return -1

    @staticmethod
    def _vram_used_mb() -> int:
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.used",
                 "--format=csv,noheader,nounits"],
                text=True, timeout=5,
            )
            return int(out.strip().splitlines()[0])
        except Exception:
            return -1

    def _wait_vram_settle(self, timeout_sec: float = 20.0,
                          poll_sec: float = 0.7, delta_mb: int = 100,
                          query=None) -> None:
        q = query or self._vram_used_mb
        prev = None
        t0 = time.time()
        while time.time() - t0 < timeout_sec:
            used = q()
            if used < 0:
                return
            if prev is not None and prev - used < delta_mb:
                if prev != used:
                    print(f"[llama-mgr] VRAM устаканилась: {used} MB занято")
                return
            prev = used
            time.sleep(poll_sec)
        print(f"[llama-mgr] VRAM settle timeout ({timeout_sec}s) — стартуем как есть")

    def wait_vram_released(self) -> None:
        self._wait_vram_settle()

    def _child_env(self) -> dict | None:
        from services.setup import runtime_env
        binary = self.assets_root / self.config.server_binary
        return runtime_env(self.project_root, binary.parent)

    def start(self, log_path=None) -> None:
        if self.is_running():
            print("[llama-mgr] Уже запущен (наш процесс)")
            return
        report = self.take_crash_report()
        if report:
            print(f"[llama-mgr] Прошлый запуск завершился сам: {report}")

        status = self._probe(timeout_sec=0.5)
        if status == 200:
            print("[llama-mgr] Уже отвечает на " + self.config.base_url
                  + " (запущен извне) — принимаем как готовый")
            return
        if status == 401:
            raise RuntimeError(
                f"На {self.config.base_url} отвечает llama-server с чужим ключом "
                f"(остался от прошлого запуска?) — закройте его и повторите.")

        binary = self.assets_root / self.config.server_binary
        if not binary.exists():
            raise FileNotFoundError(
                f"llama-server бинарь не найден: {binary}. "
                f"Проверь LLMConfig.server_binary."
            )

        if self._has_auto_ngl():
            self._wait_vram_settle()

        cmd = [
            str(binary),
            "-m", str(self.project_root / self.config.model),
        ]
        mmproj_rel = getattr(self.config, "server_mmproj", "") or ""
        if mmproj_rel:
            mmproj_abs = self.project_root / mmproj_rel
            if mmproj_abs.exists():
                cmd += ["--mmproj", str(mmproj_abs)]
            else:
                print(f"[llama-mgr] WARN: mmproj не найден ({mmproj_abs}), "
                      f"vision будет недоступен")
        cmd += list(self.config.server_launch_args)
        extra = list(getattr(self.config, "server_extra_args", []) or [])
        for i, a in enumerate(extra[:-1]):
            if a == "--chat-template-file":
                p = Path(extra[i + 1])
                if not p.is_absolute():
                    cand = self.assets_root / p
                    if cand.is_file():
                        extra[i + 1] = str(cand)
                    else:
                        print(f"[llama-mgr] WARN: chat-шаблон не найден ({cand}) "
                              f"— используем встроенный в GGUF")
                        extra[i:i + 2] = []
                break
        mtp_args: list[str] = []
        mtp_abs = None
        mtp_rel = getattr(self.config, "server_mtp_draft", "") or ""
        if mtp_rel:
            mtp_abs = self.project_root / mtp_rel
            if mtp_abs.exists():
                n_max = int(getattr(self.config, "mtp_draft_n_max", 3) or 3)
                mtp_args = ["-md", str(mtp_abs),
                            "--spec-type", "draft-mtp",
                            "--spec-draft-n-max", str(n_max)]
            else:
                print(f"[llama-mgr] MTP-драфтер не найден ({mtp_abs}) — "
                      f"генерация без спекуляции")
                mtp_abs = None
        if self._has_auto_ngl():
            side = [p for p in (
                (self.project_root / mmproj_rel) if mmproj_rel else None, mtp_abs)
                if p is not None and p.exists()]
            extra = self._bump_fit_target(
                extra, side, self._cuda_free_gap_mib(),
                reserve=self._reserve_total())
        cmd += extra
        cmd += mtp_args
        if not any(a in ("--ui", "--webui", "--no-ui", "--no-webui") for a in cmd):
            cmd.append("--no-ui")
        print(f"[llama-mgr] Запуск: {' '.join(cmd)}")

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            if _FROZEN:
                creationflags |= subprocess.CREATE_NO_WINDOW

        out = None
        app_log = None
        if log_path is not None:
            out = open(log_path, "w", encoding="utf-8", errors="replace")
            self._log_file = out
        else:
            out = subprocess.PIPE
            app_log = self._open_app_log()
        self._tail.clear()
        env = self._child_env() or dict(os.environ)
        env[child_auth.LLAMA_KEY_ENV] = child_auth.key(child_auth.LLAMA)
        self._proc = subprocess.Popen(
            cmd,
            cwd=str(self.project_root),
            creationflags=creationflags,
            stdout=out,
            stderr=subprocess.STDOUT,
            env=env,
        )
        if out is subprocess.PIPE:
            self._pump = threading.Thread(
                target=self._pump_output, args=(self._proc.stdout, app_log),
                name=f"{self.log_name}-log", daemon=True)
            self._pump.start()

        self.wait_for_ready()
        self._check_locked()

    def wait_for_ready(self, timeout_sec: Optional[int] = None) -> None:
        timeout = timeout_sec or self.config.server_startup_timeout_sec
        deadline = time.time() + timeout

        while time.time() < deadline:
            if self.is_responsive():
                elapsed = timeout - (deadline - time.time())
                print(f"[llama-mgr] Готов за {elapsed:.1f}s")
                return
            if self._proc and self._proc.poll() is not None:
                raise RuntimeError(
                    f"llama-server упал при старте: {self.crash_report()}. "
                    f"Полный вывод — logs/{self.log_name}.log (модель не найдена? CUDA?)"
                )
            time.sleep(0.5)

        self.stop()
        raise TimeoutError(
            f"llama-server не ответил за {timeout}s. "
            f"Возможно модель грузится дольше обычного — увеличь "
            f"LLMConfig.server_startup_timeout_sec."
        )

    def stop(self) -> None:
        if not self.is_running():
            report = self.take_crash_report()
            print(f"[llama-mgr] Уже завершился сам: {report}" if report
                  else "[llama-mgr] Уже остановлен")
            return

        proc = self._proc
        timeout = self.config.server_shutdown_timeout_sec

        print(f"[llama-mgr] Остановка (PID {proc.pid})...")

        try:
            if os.name == "nt" and not _FROZEN:
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                proc.terminate()
        except Exception as e:
            print(f"[llama-mgr] Сигнал остановки не отправился: {e}")

        try:
            proc.wait(timeout=timeout)
            print(f"[llama-mgr] Завершился, exit={proc.returncode}")
        except subprocess.TimeoutExpired:
            print(f"[llama-mgr] Не завершился за {timeout}s — убиваем kill()")
            proc.kill()
            proc.wait(timeout=5)

        self._proc = None

    def restart(self) -> None:
        self.stop()
        time.sleep(1.0)
        self.start()
