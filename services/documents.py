from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED_EXTS = (".txt", ".md", ".pdf")
MAX_FILE_MB = 20
SMALL_DOC_TOKENS = 12000
CHUNK_TOKENS = 1500
CHUNK_OVERLAP_TOKENS = 200
RAG_TOP_K = 3
HEAD_CHARS = 600


@dataclass
class DocAttachment:
    name: str
    path: str
    mode: str
    tokens: int
    pages: int = 0
    text: str = ""
    chunks: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @property
    def head(self) -> str:
        src = self.text or (self.chunks[0]["text"] if self.chunks else "")
        return src[:HEAD_CHARS]


class DocumentError(ValueError):
    pass


def _read_text_file(p: Path) -> str:
    raw = p.read_bytes()
    for enc in ("utf-8", "cp1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_document(path: str | Path) -> tuple[str, dict]:
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise DocumentError(f"Файл не найден: {p.name}")
    ext = p.suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise DocumentError(
            f"Формат {ext or '(без расширения)'} не поддерживается — "
            f"принимаю {', '.join(SUPPORTED_EXTS)}.")
    if p.stat().st_size > MAX_FILE_MB * 1024 * 1024:
        raise DocumentError(f"Файл больше {MAX_FILE_MB} МБ — не возьмусь.")

    if ext in (".txt", ".md"):
        text = _read_text_file(p)
        pages = 0
    else:
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(p))
            pages = len(reader.pages)
            parts = []
            for pg in reader.pages:
                try:
                    parts.append(pg.extract_text() or "")
                except Exception:
                    parts.append("")
            text = "\n\n".join(parts)
        except DocumentError:
            raise
        except Exception as e:
            raise DocumentError(f"Не смогла открыть PDF ({type(e).__name__}).")
    text = text.strip()
    if not text:
        if ext == ".pdf":
            raise DocumentError(
                "В этом PDF нет текстового слоя (похоже, скан) — читать не могу.")
        raise DocumentError("Файл пустой.")
    return text, {"pages": pages}


def chunk_text(text: str, chunk_tokens: int = CHUNK_TOKENS,
               overlap_tokens: int = CHUNK_OVERLAP_TOKENS) -> list[str]:
    from memory.conversation import estimate_tokens
    paras = [pp for pp in (s.strip() for s in text.split("\n\n")) if pp]
    chunks: list[str] = []
    cur: list[str] = []
    cur_tok = 0
    for para in paras:
        pt = estimate_tokens(para)
        if pt > chunk_tokens:
            step = chunk_tokens * 3
            for i in range(0, len(para), step):
                piece = para[i:i + step]
                if cur:
                    chunks.append("\n\n".join(cur))
                    cur, cur_tok = [], 0
                chunks.append(piece)
            continue
        if cur_tok + pt > chunk_tokens and cur:
            chunks.append("\n\n".join(cur))
            tail = cur[-1]
            from memory.conversation import estimate_tokens as _et
            cur = [tail] if _et(tail) <= overlap_tokens else []
            cur_tok = _et(tail) if cur else 0
        cur.append(para)
        cur_tok += pt
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def _cache_path(project_root: Path, digest: str) -> Path:
    return project_root / "runtime_cache" / "documents" / f"{digest}.json"


def attach_document(path: str | Path, *, embed_fn, project_root: Path) -> DocAttachment:
    from memory.conversation import estimate_tokens
    p = Path(path)
    text, meta = parse_document(p)
    tokens = estimate_tokens(text)
    att = DocAttachment(name=p.name, path=str(p), mode="full", tokens=tokens,
                        pages=int(meta.get("pages") or 0))
    if tokens <= SMALL_DOC_TOKENS:
        att.text = text
        return att

    att.mode = "rag"
    digest = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:16]
    cache = _cache_path(project_root, digest)
    if cache.exists():
        try:
            att.chunks = json.loads(cache.read_text(encoding="utf-8"))["chunks"]
            return att
        except Exception:
            pass
    chunks = chunk_text(text)
    out = []
    for c in chunks:
        emb = []
        try:
            emb = embed_fn(c) or []
        except Exception:
            emb = []
        out.append({"text": c, "embedding": emb})
    att.chunks = out
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"name": p.name, "chunks": out},
                                    ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        print(f"[docs] cache write fail: {e}")
    return att


def search_chunks(att: DocAttachment, *, query: str = "",
                  query_embedding: list | None = None,
                  top_k: int = RAG_TOP_K) -> list[str]:
    if att is None or att.mode != "rag" or not att.chunks:
        return []
    if query_embedding:
        from memory.unified import cosine_similarity
        scored = [(cosine_similarity(query_embedding, c["embedding"]), c)
                  for c in att.chunks if c.get("embedding")]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c["text"] for s, c in scored[:top_k] if s > 0.3]
    ql = (query or "").lower().strip()
    if not ql:
        return []
    hits = [c["text"] for c in att.chunks if ql in c["text"].lower()]
    return hits[:top_k]


def document_block(att: DocAttachment | None) -> str | None:
    if att is None:
        return None
    pages = f", {att.pages} стр." if att.pages else ""
    if att.mode == "full":
        return (f"<документ>\n{att.name}{pages} — приложен к разговору; полный "
                f"текст ниже. Отвечай по нему точно, не выдумывай сверх "
                f"написанного.\n---\n{att.text}\n---\n</документ>")
    return (f"<документ>\nК разговору приложен объёмный документ: {att.name}"
            f"{pages} (~{att.tokens} токенов) — целиком в контекст не помещается, "
            f"но он у тебя под рукой.\nНачало:\n«{att.head}…»\n"
            f"Релевантные куски подкладываются в <из_документа> автоматически; "
            f"если нужно найти конкретное место — инструмент "
            f"search_document(query).\n</документ>")


def excerpts_block(excerpts: list[str]) -> str | None:
    if not excerpts:
        return None
    joined = "\n---\n".join(e.strip()[:2500] for e in excerpts)
    return ("<из_документа>\nКуски приложенного документа, похожие на текущую "
            "реплику (автоподбор — могут быть неточными):\n"
            + joined + "\n</из_документа>")
