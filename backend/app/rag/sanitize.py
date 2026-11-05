"""RAG 分块文本清洗。"""
from __future__ import annotations


def sanitize_text(value: str | None) -> str | None:
    """移除 NUL 字节，避免数据库写入异常。"""
    if value is None:
        return None
    if "\x00" not in value:
        return value
    return value.replace("\x00", "")


def sanitize_chunk(chunk: dict) -> dict:
    """Return chunk with sanitized string fields for DB insert."""
    out = dict(chunk)
    for key in ("source", "source_id", "title", "text", "section", "meta_json"):
        if key in out and isinstance(out[key], str):
            out[key] = sanitize_text(out[key])
    return out
