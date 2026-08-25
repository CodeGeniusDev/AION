"""Embedding provider interface.

No real embedding model is wired into this codebase — there is no API key,
no configured provider, nothing. `NullEmbeddingProvider` is honest about
that: it always returns None, and MemoryStore falls back to lexical
relevance scoring when embeddings are unavailable (see memory/store.py).

This exists so a future real provider (OpenAI/Gemini/local embedding model,
matching whatever AION eventually standardizes on) can be dropped in behind
the same interface — MemoryStore.search() already checks `embed()` output
and uses it when present, without any caller code changing.
"""

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float] | None:
        """Return an embedding vector for `text`, or None if unavailable.
        Returning None (not raising) is the documented "no embeddings
        configured" signal that callers check for."""


class NullEmbeddingProvider(EmbeddingProvider):
    """The only provider currently wired in. Always returns None."""

    def embed(self, text: str) -> list[float] | None:
        _ = text
        return None
