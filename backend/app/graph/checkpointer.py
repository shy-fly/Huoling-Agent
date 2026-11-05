"""LangGraph checkpointer placeholder — use PostgreSQL in production."""
from typing import Any


class MemoryCheckpointer:
    """In-memory checkpoint store for development."""

    def __init__(self):
        self._store: dict[str, Any] = {}

    def put(self, key: str, state: dict) -> None:
        self._store[key] = state

    def get(self, key: str) -> dict | None:
        return self._store.get(key)
