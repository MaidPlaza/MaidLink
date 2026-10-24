IMAGE_TOKENS_ESTIMATE = 512


def estimate_tokens(content) -> int:
    if isinstance(content, str):
        return max(1, len(content) // 3)
    if isinstance(content, list):
        total = 0
        for chunk in content:
            if not isinstance(chunk, dict):
                continue
            if chunk.get("type") == "text":
                total += max(1, len(chunk.get("text") or "") // 3)
            elif chunk.get("type") == "image_url":
                total += IMAGE_TOKENS_ESTIMATE
        return max(1, total)
    return max(1, len(str(content)) // 3)


def tail_by_tokens(messages: list[dict], budget: int, min_keep: int = 2) -> list[dict]:
    out: list[dict] = []
    total = 0
    for m in reversed(messages or []):
        t = estimate_tokens(m.get("content", ""))
        if len(out) >= min_keep and total + t > budget:
            break
        out.append(m)
        total += t
    out.reverse()
    return out


class ConversationHistory:
    MIN_KEEP = 6

    def __init__(self, max_messages: int = 200, max_tokens: int = 12000):
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self.messages: list[dict] = []
        self.session_log: list[dict] = []

    def add(self, role: str, content: str, mood: dict | None = None):
        msg = {"role": role, "content": content}
        if mood:
            msg["mood"] = mood
        self.messages.append(msg)
        self.session_log.append(msg)
        self._trim()

    def _trim(self):
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]
        total = self.window_tokens()
        while total > self.max_tokens and len(self.messages) > self.MIN_KEEP:
            total -= estimate_tokens(self.messages[0].get("content", ""))
            self.messages.pop(0)

    def add_message(self, msg: dict):
        if msg.get("content") is None:
            msg = dict(msg)
            msg["content"] = ""
        self.messages.append(msg)
        self.session_log.append(msg)
        self._trim()

    def window_tokens(self) -> int:
        return sum(estimate_tokens(m.get("content", "")) for m in self.messages)

    def get_messages(self) -> list[dict]:
        return list(self.messages)

    def get_session_log(self) -> list[dict]:
        return list(self.session_log)

    def get_last_n(self, n: int) -> list[dict]:
        return self.messages[-n:]

    def clear(self):
        self.messages.clear()
        self.session_log.clear()
