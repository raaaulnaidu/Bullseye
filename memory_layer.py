"""
memory_layer.py
---------------
Three-layer memory system for the AI grading pipeline.

  Layer 1 — Short-term  : in-process dict cache (lives for one Python run)
             Caches anonymized text + RAG evidence so retries don't recompute.

  Layer 2 — Long-term   : hash-keyed JSON files in .cache/
             Caches parsed rubric criteria by rubric file hash.
             Re-running on the same rubric skips the Claude Haiku API call entirely.

  Layer 3 — Semantic    : sentence-transformer embeddings in rag_retriever.py
             (model loaded there, not here — this module handles persistence only)

Usage:
    from memory_layer import (
        session_get, session_set, text_hash,   # short-term
        disk_get, disk_set, file_hash,          # long-term
    )
"""

import hashlib
import json
from pathlib import Path

# ── Layer 1: Short-term (in-process session cache) ────────────────────────────

_session_cache: dict = {}


def session_get(key: str):
    """Return cached value for key, or None if not cached."""
    return _session_cache.get(key)


def session_set(key: str, value) -> None:
    """Store value in the session cache under key."""
    _session_cache[key] = value


def session_clear() -> None:
    """Clear the session cache (useful between test runs)."""
    _session_cache.clear()


def text_hash(text: str) -> str:
    """Short MD5 hash of a text string — used as cache keys."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:16]


# ── Layer 2: Long-term (disk-persisted JSON cache) ───────────────────────────

CACHE_DIR = Path(".cache")


def file_hash(path: str) -> str:
    """MD5 hash of a file's raw bytes — changes only when file content changes."""
    return hashlib.md5(Path(path).read_bytes()).hexdigest()[:16]


def disk_get(key: str):
    """Return cached JSON value for key, or None if not on disk."""
    p = CACHE_DIR / f"{key}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def disk_set(key: str, value) -> None:
    """Persist value as JSON under .cache/<key>.json."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.json").write_text(
        json.dumps(value, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def disk_clear() -> None:
    """Delete all files in .cache/ (useful for testing or forced refresh)."""
    if CACHE_DIR.exists():
        for f in CACHE_DIR.glob("*.json"):
            f.unlink()
