"""文本切块工具。"""
from __future__ import annotations

import re


def split_markdown_sections(text: str, min_len: int = 80) -> list[tuple[str, str]]:
    """按 ## 标题切分，返回 (heading, body)。"""
    parts = re.split(r"(?m)^##\s+", text)
    out: list[tuple[str, str]] = []
    for i, part in enumerate(parts):
        if not part.strip():
            continue
        lines = part.strip().split("\n", 1)
        heading = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else heading
        blob = f"{heading}\n{body}"
        if len(blob) >= min_len:
            out.append((heading, blob))
    return out


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    if len(text) <= max_chars:
        return [text] if text else []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks
