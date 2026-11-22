"""Input/output token counting used for request and model usage statistics."""

from functools import lru_cache

import tiktoken


@lru_cache(maxsize=1)
def _get_default_encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens with an offline-safe fallback."""
    content = (text or "").strip()
    if not content:
        return 0
    try:
        return len(_get_default_encoding().encode(content))
    except Exception:
        words = content.split()
        extra_subwords = sum(max(0, (len(word) - 1) // 5) for word in words)
        return max(1, len(words) + extra_subwords)
