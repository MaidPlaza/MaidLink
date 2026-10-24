from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

import httpx

from services import child_auth


class ComfyUIClient:
    def __init__(self, base_url: str, output_dir: Path,
                 comfy_output_dir: Path | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.comfy_output_dir = comfy_output_dir
        self._client = httpx.Client(timeout=30.0,
                                    headers=child_auth.headers(child_auth.COMFY))

    def probe(self, timeout_sec: float = 1.0, auth: bool = True) -> int:
        try:
            r = httpx.get(f"{self.base_url}/system_stats", timeout=timeout_sec,
                          headers=child_auth.headers(child_auth.COMFY) if auth else None)
            return r.status_code
        except Exception:
            return -1

    def is_responsive(self, timeout_sec: float = 1.0) -> bool:
        return self.probe(timeout_sec) == 200

    def submit(self, workflow: dict) -> str:
        r = self._client.post(
            f"{self.base_url}/prompt",
            json={"prompt": workflow},
            timeout=10.0,
        )
        r.raise_for_status()
        data = r.json()
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI не вернул prompt_id: {data}")
        return prompt_id

    def queue_state(self, prompt_id: str) -> str:
        try:
            r = self._client.get(f"{self.base_url}/queue", timeout=5.0)
            r.raise_for_status()
            q = r.json()
        except Exception:
            return "unknown"
        for key, state in (("queue_running", "running"), ("queue_pending", "pending")):
            for item in q.get(key) or []:
                try:
                    if item[1] == prompt_id:
                        return state
                except (IndexError, TypeError):
                    continue
        return "absent"

    def interrupt(self) -> None:
        try:
            self._client.post(f"{self.base_url}/interrupt", timeout=5.0)
        except Exception as e:
            print(f"[comfy] /interrupt failed (не критично): {e}")

    def wait_until_idle(self, prompt_id: str, timeout_sec: float = 20.0,
                        poll_interval_sec: float = 1.0) -> bool:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            if self.queue_state(prompt_id) in ("absent", "unknown"):
                return True
            time.sleep(poll_interval_sec)
        return False

    def _abort(self, prompt_id: str, why: str) -> None:
        print(f"[comfy] {why} — прерываю рендер (prompt_id={prompt_id})")
        self.interrupt()
        if not self.wait_until_idle(prompt_id):
            print(f"[comfy] prompt {prompt_id} не ушёл из очереди за 20с — "
                  f"своп на llama пойдёт поверх (риск спилла)")

    def wait_for_completion(
        self,
        prompt_id: str,
        timeout_sec: int = 180,
        poll_interval_sec: float = 0.5,
        hard_timeout_sec: float | None = None,
    ) -> list[dict[str, str]]:
        hard = float(hard_timeout_sec) if hard_timeout_sec else float(timeout_sec) * 3
        hard = max(hard, float(timeout_sec))
        t0 = time.time()
        soft_deadline = t0 + timeout_sec
        hard_deadline = t0 + hard
        soft_logged = False
        last_queue_check = 0.0
        absent_since: float | None = None

        while True:
            now = time.time()
            r = self._client.get(f"{self.base_url}/history/{prompt_id}", timeout=5.0)
            r.raise_for_status()
            history = r.json()

            entry = history.get(prompt_id)
            if entry:
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    msgs = status.get("messages", [])
                    raise RuntimeError(f"ComfyUI execution error: {msgs}")

                outputs = entry.get("outputs", {})
                images: list[dict[str, str]] = []
                for node_outputs in outputs.values():
                    for img in node_outputs.get("images", []):
                        images.append({
                            "filename": img["filename"],
                            "subfolder": img.get("subfolder", ""),
                            "type": img.get("type", "output"),
                        })
                if images and status.get("completed"):
                    print(f"[comfy] рендер завершён за {now - t0:.0f}s "
                          f"(prompt_id={prompt_id[:8]})")
                    return images

            if now >= hard_deadline:
                self._abort(prompt_id, f"жёсткий потолок {int(hard)}s")
                raise TimeoutError(
                    f"ComfyUI не закончил генерацию за {int(hard)}s "
                    f"(prompt_id={prompt_id}); рендер прерван. Если кадр честно "
                    f"такой тяжёлый — увеличь ImageGenConfig.generation_hard_timeout_sec."
                )
            if now >= soft_deadline and now - last_queue_check >= 2.0:
                last_queue_check = now
                state = self.queue_state(prompt_id)
                if state == "absent":
                    if absent_since is None:
                        absent_since = now
                    elif now - absent_since >= 4.0:
                        raise RuntimeError(
                            f"ComfyUI потерял prompt {prompt_id}: нет ни в очереди, "
                            f"ни в истории (перезапуск ComfyUI?)")
                else:
                    absent_since = None
                if not soft_logged:
                    soft_logged = True
                    print(f"[comfy] рендер идёт дольше {timeout_sec}s (prompt "
                          f"{state}) — жду до {int(hard)}s")

            time.sleep(poll_interval_sec)

    def download(self, image_meta: dict[str, str], dest_path: Path) -> Path:
        params = {
            "filename": image_meta["filename"],
            "subfolder": image_meta["subfolder"],
            "type": image_meta["type"],
        }
        r = self._client.get(f"{self.base_url}/view", params=params, timeout=30.0)
        r.raise_for_status()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(r.content)
        return dest_path

    def free_memory(self, unload_models: bool = True, free_memory: bool = True) -> None:
        try:
            self._client.post(
                f"{self.base_url}/free",
                json={
                    "unload_models": unload_models,
                    "free_memory": free_memory,
                },
                timeout=10.0,
            )
        except Exception as e:
            print(f"[comfy] /free failed (не критично): {e}")

    def close(self) -> None:
        self._client.close()

    def generate(
        self,
        workflow: dict,
        timeout_sec: int = 180,
        poll_interval_sec: float = 0.5,
        hard_timeout_sec: float | None = None,
    ) -> list[Path]:
        prompt_id = self.submit(workflow)
        images = self.wait_for_completion(prompt_id, timeout_sec, poll_interval_sec,
                                          hard_timeout_sec=hard_timeout_sec)
        downloaded: list[Path] = []
        for img in images:
            local_name = f"{prompt_id[:8]}_{img['filename']}"
            local_path = self.output_dir / local_name
            self.download(img, local_path)
            downloaded.append(local_path)
            self._drop_comfy_copy(img)
        return downloaded

    def _drop_comfy_copy(self, image_meta: dict[str, str]) -> None:
        root = self.comfy_output_dir
        if root is None or image_meta.get("type", "output") != "output":
            return
        try:
            base = Path(root).resolve()
            path = (base / (image_meta.get("subfolder") or "")
                    / image_meta["filename"]).resolve()
            path.relative_to(base)
            path.unlink(missing_ok=True)
        except (ValueError, OSError, KeyError):
            pass
