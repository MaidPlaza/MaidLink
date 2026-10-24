import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Generator

from rich.console import Console

_console = Console()

import httpx

from config import LLMConfig
from services import child_auth
from llm.backends import (
    LLMBackend,
    QwenBackend,
    get_backend,
    parse_xml_tool_calls,
    strip_tool_calls,
)


_COMPLEX_RE = re.compile(
    r"люб(лю|ишь|и\b)|скуч|красив|нрав|целу|обним|ласк|нежн|грустн|обид|одинок|"
    r"страшно|больно|тоск|ревн|чувств|ненавиж|"
    r"расскаж|объясн|почему|зачем|как (ты )?(счита|думаеш)|что ты дума|"
    r"мнени|посоветуй|что (мне )?делать|как (мне )?быть|помоги мне",
    re.IGNORECASE)


STREAM_RESET = object()


class _SilenceWatchdog:
    def __init__(self, resp, budget_s: float):
        self.resp = resp
        self.budget_s = float(budget_s)
        self.fired = False
        self._last = time.perf_counter()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def touch(self) -> None:
        self._last = time.perf_counter()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="llm-silence-watchdog",
                                        daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(0.25):
            if time.perf_counter() - self._last > self.budget_s:
                self.fired = True
                try:
                    self.resp.close()
                except Exception:
                    pass
                return

    def stop(self) -> None:
        self._stop.set()

STREAM_SPLIT = object()


def is_simple_message(text) -> bool:
    if not isinstance(text, str):
        return False
    t = text.strip()
    if not t:
        return True
    if len(t) > 60:
        return False
    if _COMPLEX_RE.search(t):
        return False
    if len(t.split()) > 8:
        return False
    return True


LANGUAGE_GUARD_RU = """<язык>
Все ответы — ТОЛЬКО на русском языке. Это касается:
- свободного текста (дневник, сводки, мнения, рассуждения),
- текстовых полей внутри JSON (reason, ideas, secrets, описания и т.п.),
- внутренних рассуждений в режиме thinking.
Никакого английского, китайского, японского, корейского — даже отдельных
слов или служебных пометок. Если по привычке хочется написать «Note:» или
「思考」 — пиши «Заметка:» / «Размышление». Имена собственные на латинице
оставляй как есть (Python, Qwen, OpenAI), всё остальное — кириллицей.
</язык>"""


_TRAILING_FILLER_PATTERNS: list[re.Pattern] = [
    re.compile(r"\s*А\s+(вы|ты)\s+(как|что|сами|сам)\s*\??[\s.!?]*$", re.IGNORECASE),
    re.compile(r"\s*А\s+(у\s+(вас|тебя)|сами|сам)\s*\??[\s.!?]*$", re.IGNORECASE),
    re.compile(r"\s*Как\s+(у\s+)?(вас|тебя)\s+дела\s*\??[\s.!?]*$", re.IGNORECASE),
    re.compile(r"\s*Как\s+(ваши|твои)\s+дела\s*\??[\s.!?]*$", re.IGNORECASE),
    re.compile(r"\s*Как\s+(вы|ты)\s+сам[аи]?\s*\??[\s.!?]*$", re.IGNORECASE),
    re.compile(r"\s*Как\s+(вы|ты)\s+поживаете?\s*\??[\s.!?]*$", re.IGNORECASE),
    re.compile(r"\s*Как\s+(ваше|твоё)\s+(самочувствие|настроение)\s*\??[\s.!?]*$", re.IGNORECASE),
    re.compile(r"\s*Чем\s+(я\s+)?мог(у|ла\s+бы)\s+(помочь|служить|быть\s+полезн[аыой])\s*\??[\s.!?]*$", re.IGNORECASE),
    re.compile(r"\s*Что\s+(я\s+)?мог(у|ла\s+бы)\s+(для\s+(вас|тебя)\s+)?сделать\s*\??[\s.!?]*$", re.IGNORECASE),
    re.compile(r"\s*Что[-\s]*то\s+ещ[её]\s*(нужно|хотите|нужно\s+сделать)?\s*\??[\s.!?]*$", re.IGNORECASE),
    re.compile(r"\s*Есть\s+(ли\s+)?ещ[её]\s+(какие[-\s]?то\s+)?вопросы\s*\??[\s.!?]*$", re.IGNORECASE),
    re.compile(r"\s*Хотите\s+узнать\s+что[-\s]?то\s+ещ[её]\s*\??[\s.!?]*$", re.IGNORECASE),
    re.compile(r"\s*Если\s+что[-\s]?то\s+(понадобится|нужно)\s*[,—-]?\s*(просто\s+)?спрашивайте\s*[?!.]*[\s.!?]*$", re.IGNORECASE),
    re.compile(r"\s*Если\s+что\s*[,—-]?\s*(просто\s+)?обращайтесь\s*[?!.]*[\s.!?]*$", re.IGNORECASE),
    re.compile(r"\s*Всегда\s+рад(?:а)?\s+помочь\s*[?!.]*[\s.!?]*$", re.IGNORECASE),
]


def strip_trailing_filler(text: str) -> str:
    changed = True
    while changed:
        changed = False
        for pat in _TRAILING_FILLER_PATTERNS:
            m = pat.search(text)
            if m and m.end() == len(text):
                text = text[:m.start()].rstrip()
                changed = True
                break
    text = re.sub(r"(?:^|[\s,—-])(И|Или|А)\s*[.!?]*$", "", text, flags=re.IGNORECASE).rstrip()
    return text


@dataclass
class GenerationStats:
    tokens: int = 0
    elapsed_seconds: float = 0.0
    time_to_first_token: float = 0.0
    prefill_tps: float = 0.0
    gen_tps: float = 0.0
    prompt_n: int = 0
    cache_n: int = 0

    @property
    def tokens_per_second(self) -> float:
        if self.elapsed_seconds == 0:
            return 0.0
        return self.tokens / self.elapsed_seconds

    def summary(self) -> str:
        return (
            f"{self.tokens} tok | "
            f"{self.tokens_per_second:.1f} tok/s | "
            f"TTFT {self.time_to_first_token:.2f}s | "
            f"total {self.elapsed_seconds:.1f}s"
        )


class LlamaClient:
    def __init__(self, config: LLMConfig):
        self.config = config
        self.base_url = config.base_url
        _fam = ((getattr(config, "family", "") or "").strip().lower()
                or ("gemma" if "gemma" in (config.model or "").lower() else "qwen"))
        self.backend: LLMBackend = get_backend(_fam)
        self.last_stats: GenerationStats | None = None
        self.debug_thinking: bool = False
        self.last_reasoning: str = ""
        self.reasoning_mode: str = "deep"
        self.fast_post_session: bool = False
        self.system_suffix: str = ""
        self.cancel_requested: bool = False
        self._active_stream_resp = None
        self.silence_budget_s: float | None = None
        self.last_tool_trace: list[dict] = []
        self.prompt_observer = None

    @staticmethod
    def _auth() -> dict:
        return child_auth.headers(child_auth.LLAMA)

    def _sampling_params(self, thinking: bool) -> dict:
        return self.backend.sampling_params(thinking=thinking)

    def _mk_stats(self, result: dict, tokens: int, elapsed: float,
                  ttft: float) -> GenerationStats:
        t = result.get("timings") or {}
        st = GenerationStats(
            tokens=tokens,
            elapsed_seconds=elapsed,
            time_to_first_token=ttft,
            prefill_tps=float(t.get("prompt_per_second") or 0.0),
            gen_tps=float(t.get("predicted_per_second") or 0.0),
            prompt_n=int(t.get("prompt_n") or 0),
            cache_n=int(t.get("cache_n") or 0),
        )
        if t:
            total = st.prompt_n + st.cache_n
            _lbl = getattr(self, "_call_label", "") or ""
            print(f"[llm] prefill{(' [' + _lbl + ']') if _lbl else ''}: "
                  f"computed {st.prompt_n} + cached {st.cache_n} "
                  f"= {total} tok ({st.prefill_tps:.0f} tok/s, "
                  f"{float(t.get('prompt_ms') or 0) / 1000:.1f}s)")
        return st

    def _thinking_on(self, messages) -> bool:
        mode = self.reasoning_mode
        if mode == "fast":
            return False
        if mode != "auto":
            return True
        user_text = ""
        for m in reversed(messages or []):
            if m.get("role") == "user":
                user_text = m.get("content")
                break
        return not is_simple_message(user_text)

    def live_thinking(self, want: bool = True) -> bool:
        if not want or self.fast_post_session:
            return False
        return self.reasoning_mode == "deep"

    def load(self):
        if self.is_available():
            print(f"[LLM] Server connected at {self.base_url}")
        else:
            print(f"[LLM] WARNING: Server not available at {self.base_url}")

    def _post(self, data: dict, timeout: float = 600.0) -> dict:
        result = self._post_once(data, timeout)
        if (result.get("choices") or [{}])[0].get("finish_reason") == "silence_abort":
            print("[llm] silent runaway aborted in internal round, retrying once")
            result = self._post_once(data, timeout)
        return result

    def _post_once(self, data: dict, timeout: float = 600.0) -> dict:
        req = dict(data)
        req["stream"] = True
        req["stream_options"] = {"include_usage": True}
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_frags: dict[int, dict] = {}
        usage: dict = {}
        timings: dict = {}
        finish_reason = None
        t0 = time.perf_counter()
        wd: _SilenceWatchdog | None = None
        with httpx.stream("POST", f"{self.base_url}/v1/chat/completions",
                          json=req, timeout=timeout, headers=self._auth()) as r:
            r.raise_for_status()
            lines_iter = r.iter_lines()
            try:
                while True:
                    try:
                        line = next(lines_iter)
                    except StopIteration:
                        break
                    except Exception:
                        if wd is not None and wd.fired:
                            break
                        raise
                    if not line or not line.startswith("data: "):
                        continue
                    payload = line[len("data: "):].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except Exception:
                        continue
                    if wd is None:
                        wd = _SilenceWatchdog(r, self._silence_budget())
                        wd.start()
                    else:
                        wd.touch()
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    if chunk.get("timings"):
                        timings = chunk["timings"]
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    ch = choices[0]
                    if ch.get("finish_reason"):
                        finish_reason = ch["finish_reason"]
                    delta = ch.get("delta") or {}
                    if delta.get("reasoning_content"):
                        reasoning_parts.append(delta["reasoning_content"])
                    for tf in delta.get("tool_calls") or []:
                        idx = tf.get("index", 0)
                        slot = tool_frags.setdefault(idx, {
                            "id": tf.get("id"), "type": "function",
                            "function": {"name": "", "arguments": ""}})
                        if tf.get("id"):
                            slot["id"] = tf["id"]
                        fn = tf.get("function") or {}
                        if fn.get("name"):
                            slot["function"]["name"] += fn["name"]
                        if fn.get("arguments"):
                            slot["function"]["arguments"] += fn["arguments"]
                    if delta.get("content"):
                        content_parts.append(delta["content"])
            finally:
                if wd is not None:
                    wd.stop()
        took = time.perf_counter() - t0
        if wd is not None and wd.fired:
            finish_reason = "silence_abort"
            print(f"[llm] silent runaway aborted (internal round): {took:.0f}s, "
                  f"budget={wd.budget_s:.0f}s, content_chars={sum(map(len, content_parts))}")
        n_out = int(usage.get("completion_tokens") or 0)
        if finish_reason == "length" or took > 90:
            print(f"[llm] slow internal round: {took:.0f}s, {n_out} tok, "
                  f"finish={finish_reason}, think_chars={sum(map(len, reasoning_parts))}")
        message: dict = {"role": "assistant", "content": "".join(content_parts)}
        if reasoning_parts:
            message["reasoning_content"] = "".join(reasoning_parts)
        if tool_frags:
            message["tool_calls"] = [tool_frags[i] for i in sorted(tool_frags)]
        return {
            "choices": [{"message": message, "finish_reason": finish_reason}],
            "usage": usage,
            "timings": timings,
        }

    def _silence_budget(self) -> float:
        if self.silence_budget_s is not None:
            return float(self.silence_budget_s)
        try:
            from config import LLM_MODELS
            tps = float(LLM_MODELS.get(getattr(self.config, "model_choice", "") or "",
                                       {}).get("expected_tps") or 0)
        except Exception:
            tps = 0.0
        return max(12.0, 400.0 / tps) if tps > 0 else 20.0

    def request_cancel(self) -> None:
        self.cancel_requested = True
        r = self._active_stream_resp
        if r is not None:
            try:
                r.close()
            except Exception:
                pass

    def _post_stream_events(self, data: dict, timeout: float = 600.0):
        req = dict(data)
        req["stream"] = True
        req["stream_options"] = {"include_usage": True}
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_frags: dict[int, dict] = {}
        usage: dict = {}
        timings: dict = {}
        finish_reason = None
        self._last_stream_ttft = None
        self._last_stream_precall_len = None
        _diag = {"chunks": 0, "empty_deltas": 0, "max_gap_s": 0.0, "first_chunk_s": None}
        self.last_stream_diag = _diag
        _t_prev = None
        wd: _SilenceWatchdog | None = None
        t0 = time.perf_counter()
        with httpx.stream("POST", f"{self.base_url}/v1/chat/completions",
                          json=req, timeout=timeout, headers=self._auth()) as r:
            r.raise_for_status()
            self._active_stream_resp = r
            try:
                lines_iter = r.iter_lines()
            except Exception:
                self._active_stream_resp = None
                raise
            while True:
                if self.cancel_requested:
                    break
                try:
                    line = next(lines_iter)
                except StopIteration:
                    break
                except Exception:
                    if self.cancel_requested or (wd is not None and wd.fired):
                        break
                    self._active_stream_resp = None
                    if wd is not None:
                        wd.stop()
                    raise
                if not line or not line.startswith("data: "):
                    continue
                payload = line[len("data: "):].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except Exception:
                    continue
                _now = time.perf_counter()
                _diag["chunks"] += 1
                if wd is None:
                    wd = _SilenceWatchdog(r, self._silence_budget())
                    wd.start()
                else:
                    wd.touch()
                if _t_prev is None:
                    _diag["first_chunk_s"] = round(_now - t0, 3)
                else:
                    _gap = _now - _t_prev
                    if _gap > _diag["max_gap_s"]:
                        _diag["max_gap_s"] = round(_gap, 3)
                _t_prev = _now
                if chunk.get("usage"):
                    usage = chunk["usage"]
                if chunk.get("timings"):
                    timings = chunk["timings"]
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                ch = choices[0]
                if ch.get("finish_reason"):
                    finish_reason = ch["finish_reason"]
                delta = ch.get("delta") or {}
                if not (delta.get("content") or delta.get("reasoning_content")
                        or delta.get("tool_calls")):
                    _diag["empty_deltas"] += 1
                rc = delta.get("reasoning_content")
                if rc:
                    reasoning_parts.append(rc)
                for tf in delta.get("tool_calls") or []:
                    if self._last_stream_precall_len is None:
                        self._last_stream_precall_len = sum(
                            map(len, content_parts))
                    idx = tf.get("index", 0)
                    slot = tool_frags.setdefault(idx, {
                        "id": tf.get("id"), "type": "function",
                        "function": {"name": "", "arguments": ""}})
                    if tf.get("id"):
                        slot["id"] = tf["id"]
                    fn = tf.get("function") or {}
                    if fn.get("name"):
                        slot["function"]["name"] += fn["name"]
                    if fn.get("arguments"):
                        slot["function"]["arguments"] += fn["arguments"]
                tok = delta.get("content")
                if tok:
                    if self._last_stream_ttft is None:
                        self._last_stream_ttft = time.perf_counter() - t0
                    content_parts.append(tok)
                    yield ("token", tok)
        self._active_stream_resp = None
        if wd is not None:
            wd.stop()
            if wd.fired:
                finish_reason = "silence_abort"
                _diag["silence_abort"] = True
                print(f"[llm] silent runaway aborted: {time.perf_counter() - t0:.0f}s, "
                      f"budget={wd.budget_s:.0f}s, chunks={_diag['chunks']}, "
                      f"content_chars={sum(map(len, content_parts))}")
        _diag["finish_reason"] = finish_reason
        _diag["predicted_n"] = int((timings or {}).get("predicted_n") or 0)
        _diag["elapsed_s"] = round(time.perf_counter() - t0, 2)
        if finish_reason == "length" or _diag["predicted_n"] >= 2000:
            print(f"[llm] stream anomaly: finish={finish_reason} predicted={_diag['predicted_n']} "
                  f"chunks={_diag['chunks']} empty_deltas={_diag['empty_deltas']} "
                  f"content_chars={sum(map(len, content_parts))} "
                  f"reasoning_chars={sum(map(len, reasoning_parts))} "
                  f"tool_frags={len(tool_frags)} max_gap={_diag['max_gap_s']}s "
                  f"elapsed={_diag['elapsed_s']}s")
        message: dict = {"role": "assistant", "content": "".join(content_parts)}
        if reasoning_parts:
            message["reasoning_content"] = "".join(reasoning_parts)
        if tool_frags:
            message["tool_calls"] = [tool_frags[i] for i in sorted(tool_frags)]
        yield ("result", {
            "choices": [{"message": message, "finish_reason": finish_reason}],
            "usage": usage,
            "timings": timings,
        })

    def _build_messages(self, messages: list[dict], system: str | None = None) -> list[dict]:
        full = [{k: v for k, v in m.items() if k != "mood"} for m in messages]
        merged: list[dict] = []
        for m in full:
            prev = merged[-1] if merged else None
            if (prev is not None
                    and m.get("role") == "user" and prev.get("role") == "user"
                    and isinstance(m.get("content"), str)
                    and isinstance(prev.get("content"), str)
                    and not prev.get("tool_calls") and not m.get("tool_calls")):
                prev["content"] = f"{prev['content']}\n{m['content']}"
                continue
            merged.append(dict(m))
        full = merged
        suffix = getattr(self, "system_suffix", "") or ""
        if suffix:
            system = f"{system}\n\n{suffix}" if system else suffix
        if system:
            full = [{"role": "system", "content": system}] + full
        return full

    @staticmethod
    def _log_request_fingerprint(request_body: dict) -> None:
        import hashlib
        import json as _json
        import os
        path = os.environ.get("MAID_PROMPT_FPRINT")
        if not path:
            return
        try:
            def _h(obj) -> str:
                return hashlib.md5(_json.dumps(obj, ensure_ascii=False,
                                               sort_keys=True).encode()).hexdigest()[:8]
            lines = ["--- request"]
            for m in request_body.get("messages", []):
                c = m.get("content")
                clen = len(c) if isinstance(c, str) else len(_json.dumps(c, ensure_ascii=False)) if c else 0
                extra = ""
                if m.get("tool_calls"):
                    extra = f" tool_calls={_h(m['tool_calls'])}"
                if m.get("reasoning_content"):
                    extra += f" reasoning={_h(m['reasoning_content'])}"
                lines.append(f"{m.get('role')}:{clen}:{_h(c)}{extra}")
            if request_body.get("tools") is not None:
                lines.append(f"tools:{len(request_body['tools'])}:{_h(request_body['tools'])}")
            for k in ("chat_template_kwargs",):
                if k in request_body:
                    lines.append(f"{k}:{_h(request_body[k])}")
            with open(path, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except Exception:
            pass

    @staticmethod
    def _append_turn_context(full_messages: list[dict], tail: str, anchor: str) -> None:
        blocks = [b.strip() for b in (tail, anchor) if b and b.strip()]
        if not blocks:
            return
        extra = "\n\n".join(blocks)
        last = full_messages[-1] if full_messages else None
        if last is not None and last.get("role") == "user" and not last.get("tool_calls"):
            content = last.get("content")
            if isinstance(content, str):
                last["content"] = (content + "\n\n" + extra) if content.strip() else extra
                return
            if isinstance(content, list):
                content.append({"type": "text", "text": extra})
                return
        full_messages.append({"role": "user", "content": extra})


    activity_observer = None

    def _begin_activity(self, label: str) -> None:
        self._call_label = label
        cb = getattr(self, "activity_observer", None)
        if cb:
            try:
                cb(label)
            except Exception:
                pass

    def _end_activity(self) -> None:
        cb = getattr(self, "activity_observer", None)
        if cb:
            try:
                cb(None)
            except Exception:
                pass

    def chat_stream(self, messages, system=None, think=None):
        self._begin_activity("chat_stream")
        try:
            yield from self._chat_stream_impl(messages, system, think)
        finally:
            self._end_activity()

    def chat_with_tools(self, messages, system=None, tools=None, tool_handler=None,
                        max_tool_rounds=8, char_name="", char_gender="",
                        deferred_pending=None, verbose_style=False, tail=""):
        self._begin_activity("main chat")
        try:
            yield from self._chat_with_tools_impl(
                messages, system, tools, tool_handler, max_tool_rounds, char_name,
                char_gender, deferred_pending, verbose_style, tail)
        finally:
            self._end_activity()

    def chat(self, messages, system=None, thinking=True, label="", max_tokens=8192,
             live_turn=False, lang_guard=True):
        self._begin_activity(label or "chat")
        try:
            return self._chat_impl(messages, system, thinking, label, max_tokens,
                                   live_turn, lang_guard)
        finally:
            self._end_activity()

    def _chat_stream_impl(
        self,
        messages: list[dict],
        system: str | None = None,
        think: bool | None = None,
    ) -> Generator[str, None, None]:
        self._call_label = "chat_stream"
        full_messages = self._build_messages(messages, system)

        stats = GenerationStats()
        start_time = time.perf_counter()
        first_token = True

        _think = self._thinking_on(messages) if think is None else think
        request_body = {
            "messages": full_messages,
            "stream": True,
            "max_tokens": 8192,
            **self._sampling_params(_think),
        }
        request_body.update(self.backend.thinking_kwargs(enable=_think))

        with httpx.stream(
            "POST",
            f"{self.base_url}/v1/chat/completions",
            json=request_body,
            timeout=600.0,
            headers=self._auth(),
        ) as response:
            response.raise_for_status()
            reasoning_parts = []
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0].get("delta", {})
                    reasoning_token = delta.get("reasoning_content", "")
                    if reasoning_token:
                        reasoning_parts.append(reasoning_token)
                        continue
                    token = delta.get("content", "")
                    if token:
                        if first_token:
                            stats.time_to_first_token = time.perf_counter() - start_time
                            first_token = False
                        stats.tokens += 1
                        yield token
                except json.JSONDecodeError:
                    continue

            if reasoning_parts:
                self.last_reasoning = "".join(reasoning_parts)
                if self.debug_thinking:
                    _console.print(f"\n[dim italic][THINK] ({len(self.last_reasoning)} chars):[/]")
                    for line in self.last_reasoning.strip().split("\n"):
                        _console.print(f"[dim italic]  {line}[/]")
                    _console.print()

        stats.elapsed_seconds = time.perf_counter() - start_time
        self.last_stats = stats

    def _chat_with_tools_impl(
        self,
        messages: list[dict],
        system: str | None = None,
        tools: list[dict] | None = None,
        tool_handler: Callable[[str, dict], str] | None = None,
        max_tool_rounds: int = 8,
        char_name: str = "",
        char_gender: str = "",
        deferred_pending: Callable[[], bool] | None = None,
        verbose_style: bool = False,
        tail: str = "",
    ) -> Generator[str, None, None]:
        self._call_label = "main chat"
        full_messages = self._build_messages(messages, system)
        start_time = time.perf_counter()
        _think = self._thinking_on(messages)

        native = self.backend.uses_native_tools
        self._char_gender = char_gender
        anchor = self.backend.tool_anchor(char_name=char_name, reason_in_russian=_think,
                                          char_gender=char_gender,
                                          verbose_style=verbose_style)
        if native:
            self._append_turn_context(full_messages, tail, anchor)
        else:
            self._append_turn_context(full_messages, tail, "")
            full_messages.append({"role": "assistant", "content": self.backend.priming_tool_call()})
            full_messages.append({"role": "user", "content": self.backend.wrap_tool_result(anchor)})

        _seen_calls: set[tuple] = set()
        self.last_tool_trace = []
        self.cancel_requested = False
        _silence_retried = False
        from llm.backends import register_tools
        register_tools(tools)
        for _round in range(max_tool_rounds):
            if self.cancel_requested:
                return
            if not tools or not tool_handler:
                break

            request_body = {
                "messages": full_messages,
                "max_tokens": 8192,
                **self._sampling_params(_think),
            }
            request_body.update(self.backend.thinking_kwargs(enable=_think))
            _streamed_this_round = 0
            if native:
                request_body["tools"] = tools
                self._log_request_fingerprint(request_body)
                result = None
                for _ev, _payload in self._post_stream_events(request_body):
                    if _ev == "token":
                        _streamed_this_round += 1
                        yield _payload
                    else:
                        result = _payload
            else:
                result = self._post(request_body)

            if self.cancel_requested or result is None:
                return

            if (result.get("choices") or [{}])[0].get("finish_reason") == "silence_abort":
                if not _silence_retried:
                    _silence_retried = True
                    print("[llm] silent runaway aborted, retrying the round")
                    if _streamed_this_round:
                        yield STREAM_RESET
                    continue
                print("[llm] silent runaway aborted twice, giving up on the round")
                break

            msg = result["choices"][0]["message"]
            content = msg.get("content", "")
            reasoning = msg.get("reasoning_content", "")

            if reasoning:
                self.last_reasoning = reasoning
                if self.debug_thinking:
                    _console.print(f"\n[dim italic][THINK] ({len(reasoning)} chars):[/]")
                    for line in reasoning.strip().split("\n"):
                        _console.print(f"[dim italic]  {line}[/]")
                    _console.print()

            if native:
                tool_calls = self.backend.normalize_tool_calls(msg)
            else:
                tool_calls = self.backend.parse_tool_calls(content)
                if not tool_calls and reasoning:
                    tool_calls = self.backend.parse_tool_calls(reasoning)
                    if tool_calls:
                        print(f"[LLM] Tool calls found in reasoning (rescued)")
                        content = ""

            if not tool_calls and not native:
                has_broken = self.backend.has_broken_tool_call(content, reasoning)
                if has_broken:
                    print(f"[LLM] Broken tool call detected, sending error feedback")
                    full_messages.append({"role": "assistant", "content": content})
                    full_messages.append({
                        "role": "user",
                        "content": self.backend.broken_tool_feedback(),
                    })
                    continue

            if not tool_calls:
                clean = self.backend.strip_tool_calls(content)
                elapsed = time.perf_counter() - start_time
                tokens = result.get("usage", {}).get("completion_tokens", 0)
                if native and _streamed_this_round:
                    self.last_stats = self._mk_stats(
                        result, tokens, elapsed,
                        getattr(self, "_last_stream_ttft", None) or elapsed)
                    return
                if clean:
                    self.last_stats = self._mk_stats(result, tokens, elapsed, elapsed)
                    yield clean
                    return
                break

            _ctx_content = self._round_context_content(
                content, native,
                self._last_stream_precall_len if _streamed_this_round else None)

            self._dispatch_tool_round(full_messages, tool_calls, _ctx_content, native,
                                      tool_handler, _seen_calls, reasoning)

            _deferred_round = any(tc["name"] in self.DEFERRED_ACTION_TOOLS
                                  for tc in tool_calls)
            if not _deferred_round and any(tc["name"] in self.TERMINAL_AFTER_REPLY_TOOLS
                                           for tc in tool_calls):
                _deferred_round = bool(self._precall_prolog(
                    content,
                    getattr(self, "_last_stream_precall_len", None)
                    if _streamed_this_round else None))
            if _deferred_round and (deferred_pending is None
                                    or deferred_pending()):
                elapsed = time.perf_counter() - start_time
                self.last_stats = self._mk_stats(
                    result, result.get("usage", {}).get("completion_tokens", 0),
                    elapsed,
                    ((getattr(self, "_last_stream_ttft", None) or elapsed)
                     if _streamed_this_round else elapsed))
                prolog = self._precall_prolog(
                    content,
                    getattr(self, "_last_stream_precall_len", None)
                    if _streamed_this_round else None)
                if _streamed_this_round:
                    if prolog != (content or "").strip():
                        yield STREAM_RESET
                        if prolog:
                            yield prolog
                elif prolog:
                    yield prolog
                return

            if _streamed_this_round:
                _raw = (content or "").strip()
                if _deferred_round or not _ctx_content:
                    yield STREAM_RESET
                elif _ctx_content != _raw:
                    yield STREAM_RESET
                    yield _ctx_content
                    yield STREAM_SPLIT
                else:
                    yield STREAM_SPLIT

        if self.cancel_requested:
            return
        yield from self._finalize_after_rounds(full_messages, tools, tool_handler,
                                               native, _seen_calls, start_time, _think,
                                               deferred_pending)

    DEFERRED_ACTION_TOOLS = frozenset({"draw", "change_outfit"})
    TERMINAL_AFTER_REPLY_TOOLS = frozenset({"end_session"})

    def _precall_prolog(self, content: str, precall_len: int | None) -> str:
        src = content or ""
        if precall_len is not None:
            src = src[:precall_len]
        pos = self.backend.tool_call_marker_pos(src)
        if pos is not None:
            src = src[:pos]
        return self.backend.strip_tool_calls(src).strip()

    def _round_context_content(self, content: str, native: bool,
                               precall_len: int | None) -> str:
        if native:
            return self._precall_prolog(content, precall_len)
        src = content or ""
        close = src.rfind("</tool_call>")
        if close != -1:
            return src[:close + len("</tool_call>")]
        return src

    def _dispatch_tool_round(self, full_messages, tool_calls, content, native,
                             tool_handler, seen, reasoning=""):
        print(f"[LLM] Tool calls detected: {[tc['name'] for tc in tool_calls]}")
        if native:
            _native_tcs = [{"id": tc.get("id"), "type": "function",
                            "function": {"name": tc["name"],
                                         "arguments": tc.get("arguments") or {}}}
                           for tc in tool_calls]
            _deferred = any(tc["name"] in self.DEFERRED_ACTION_TOOLS
                            for tc in tool_calls)
            _suppress_content = _deferred
            asst_msg = {"role": "assistant",
                        "content": (None if _suppress_content else
                                    self.backend.strip_tool_calls(content) or None),
                        "tool_calls": _native_tcs}
            if reasoning and not _deferred:
                asst_msg["reasoning_content"] = reasoning
            full_messages.append(asst_msg)
        else:
            full_messages.append({"role": "assistant", "content": content})

        for tc in tool_calls:
            key = (tc["name"], json.dumps(tc.get("arguments") or {}, sort_keys=True,
                                          ensure_ascii=False, default=str))
            if tc["name"] == "prepare":
                tool_result = "Подготовка уже выполнена. Отвечай Господину без повторного вызова."
            elif key in seen:
                from persona.gender import g as _gpick
                _cg = getattr(self, "_char_gender", "") or ""
                tool_result = (f"Ты уже {_gpick(_cg, 'вызывала', 'вызывал')} "
                               f"{tc['name']} с теми же аргументами — "
                               "результат выше, он не изменился. НЕ повторяй вызов: отвечай "
                               "Господину или вызови ДРУГОЙ инструмент (например draw, если "
                               f"{_gpick(_cg, 'собиралась', 'собирался')} рисовать).")
            else:
                seen.add(key)
                tool_result = tool_handler(tc["name"], tc["arguments"])
                _res_short = (tool_result or "").strip()
                if len(_res_short) > 200:
                    _res_short = _res_short[:200] + "…"
                self.last_tool_trace.append({
                    "name": tc["name"],
                    "arguments": tc.get("arguments") or {},
                    "result_short": _res_short,
                })
            if native:
                full_messages.append({"role": "tool", "tool_call_id": tc.get("id"),
                                      "content": tool_result})
            else:
                full_messages.append({"role": "user",
                                      "content": self.backend.wrap_tool_result(tool_result)})

    def _finalize_after_rounds(self, full_messages, tools, tool_handler, native, seen,
                               start_time, think, deferred_pending=None):
        if not (tools and tool_handler):
            yield from self.chat_stream(full_messages, think=think)
            return
        body = {"messages": full_messages, "max_tokens": 8192, **self._sampling_params(think)}
        body.update(self.backend.thinking_kwargs(enable=think))
        if native:
            body["tools"] = tools
        result = self._post(body)
        msg = result["choices"][0]["message"]
        content = msg.get("content", "") or ""
        reasoning = msg.get("reasoning_content", "") or ""
        if native:
            calls = self.backend.normalize_tool_calls(msg)
        else:
            calls = (self.backend.parse_tool_calls(content)
                     or self.backend.parse_tool_calls(msg.get("reasoning_content", "") or ""))
        if calls:
            self._dispatch_tool_round(full_messages, calls,
                                      self._round_context_content(content, native, None),
                                      native, tool_handler, seen, reasoning)
            _deferred = any(c["name"] in self.DEFERRED_ACTION_TOOLS for c in calls)
            if _deferred and (deferred_pending is None or deferred_pending()):
                clean = self._precall_prolog(content, None)
                elapsed = time.perf_counter() - start_time
                self.last_stats = self._mk_stats(
                    result, result.get("usage", {}).get("completion_tokens", 0),
                    elapsed, elapsed)
                if clean:
                    yield clean
                return
            result = self._post({"messages": full_messages, "max_tokens": 8192,
                                 **self._sampling_params(think),
                                 **self.backend.thinking_kwargs(enable=think)})
            content = result["choices"][0]["message"].get("content", "") or ""
        clean = self.backend.strip_tool_calls(content)
        if not clean:
            print("[LLM] финал пуст — повтор без thinking/инструментов")
            result = self._post({"messages": full_messages, "max_tokens": 2048,
                                 **self._sampling_params(False),
                                 **self.backend.thinking_kwargs(enable=False)})
            content = result["choices"][0]["message"].get("content", "") or ""
            clean = self.backend.strip_tool_calls(content)
        elapsed = time.perf_counter() - start_time
        self.last_stats = self._mk_stats(
            result, result.get("usage", {}).get("completion_tokens", 0),
            elapsed, elapsed)
        if clean:
            yield clean

    def _chat_impl(
        self,
        messages: list[dict],
        system: str | None = None,
        thinking: bool = True,
        label: str = "",
        max_tokens: int = 8192,
        live_turn: bool = False,
        lang_guard: bool = True,
    ) -> str:
        if thinking and self.fast_post_session and not live_turn:
            thinking = False

        self._call_label = label or "chat"
        if label and system and lang_guard:
            system = LANGUAGE_GUARD_RU + "\n\n" + system

        full_messages = self._build_messages(messages, system)

        if self.prompt_observer is not None:
            try:
                self.prompt_observer(label, system or "", list(messages))
            except Exception as exc:
                print(f"[LLM] prompt_observer raised: {exc}")

        if thinking:
            anchor_text = "Рассуждай на русском. Ответь кратко."
        else:
            anchor_text = "Отвечай на русском. Ответь кратко."
        if self.backend.uses_native_tools:
            if full_messages and full_messages[0].get("role") == "system":
                full_messages[0]["content"] = "Ответь кратко.\n\n" + full_messages[0]["content"]
            else:
                full_messages.insert(0, {"role": "system", "content": "Ответь кратко."})
        else:
            anchor_text += " prepare — служебный шаг, уже выполнен, повторно вызывать не нужно."
            full_messages.append({"role": "assistant", "content": self.backend.priming_tool_call()})
            full_messages.append({"role": "user", "content": self.backend.wrap_tool_result(anchor_text)})

        data = {
            "messages": full_messages,
            "max_tokens": max_tokens,
        }

        data.update(self.backend.sampling_params(thinking=thinking))
        data.update(self.backend.thinking_kwargs(enable=thinking))

        _t0 = time.perf_counter()
        result = self._post(data)
        _elapsed = time.perf_counter() - _t0

        msg = result["choices"][0]["message"]
        content = msg.get("content", "")
        reasoning = msg.get("reasoning_content", "")

        usage = result.get("usage", {}) or {}
        self.last_stats = self._mk_stats(
            result, int(usage.get("completion_tokens") or 0), _elapsed, _elapsed)
        if label:
            print(f"[LLM] «{label}»: {_elapsed:.1f}s "
                  f"(prompt {usage.get('prompt_tokens', '?')} tok, "
                  f"gen {usage.get('completion_tokens', '?')} tok, "
                  f"think={'on' if thinking else 'off'})")

        if reasoning:
            self.last_reasoning = reasoning

        return self.backend.strip_tool_calls(content)

    def complete(
        self,
        messages: list[dict],
        system: str | None = None,
        *,
        thinking: bool = False,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        label: str = "",
    ) -> str:
        full_messages = self._build_messages(messages, system)
        if self.prompt_observer is not None:
            try:
                self.prompt_observer(label, system or "", list(messages))
            except Exception as exc:
                print(f"[LLM] prompt_observer raised: {exc}")
        data = {"messages": full_messages, "max_tokens": max_tokens}
        data.update(self.backend.sampling_params(deterministic_temp=temperature))
        data.update(self.backend.thinking_kwargs(enable=thinking))
        result = self._post(data)
        content = result["choices"][0]["message"].get("content", "")
        return self.backend.strip_tool_calls(content)

    def embed(self, text: str) -> list[float]:
        out = self.embed_batch([text])
        return out[0] if out else []

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = httpx.post(
                f"{self.config.embed_base_url}/v1/embeddings",
                json={"input": texts},
                timeout=60.0,
                headers=self._auth(),
            )
            response.raise_for_status()
            data = response.json().get("data", [])
            data = sorted(data, key=lambda d: d.get("index", 0))
            return [d.get("embedding", []) for d in data]
        except Exception:
            return []

    def is_available(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/v1/models", timeout=5.0, headers=self._auth())
            return r.status_code == 200
        except httpx.ConnectError:
            return False

    def has_model(self, model: str | None = None) -> bool:
        return self.is_available()
