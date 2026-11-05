"""Request-scoped context for log correlation."""
from contextvars import ContextVar
from typing import Any

_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_digester_id: ContextVar[str | None] = ContextVar("digester_id", default=None)


def set_trace_id(trace_id: str) -> None:
    _trace_id.set(trace_id)


def get_trace_id() -> str | None:
    return _trace_id.get()


def set_digester_id(digester_id: str) -> None:
    _digester_id.set(digester_id)


def get_digester_id() -> str | None:
    return _digester_id.get()


def log_extra(**kwargs: Any) -> dict[str, Any]:
    extra = dict(kwargs)
    if _trace_id.get():
        extra["trace_id"] = _trace_id.get()
    if _digester_id.get():
        extra["digester_id"] = _digester_id.get()
    return extra
