"""多格式知识源解析为统一 chunk 记录。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.observability.logging_config import get_logger
from app.rag.chunking import chunk_text, split_markdown_sections

logger = get_logger("app.rag.parsers")

ChunkRecord = dict[str, Any]


def _slug(name: str) -> str:
    s = Path(name).stem
    return re.sub(r"[^\w\u4e00-\u9fff]+", "_", s)[:64]


def parse_markdown(path: Path, collection: str, source_id: str | None = None) -> list[ChunkRecord]:
    text = path.read_text(encoding="utf-8", errors="replace")
    sid = source_id or f"{collection}:{_slug(path.name)}"
    chunks: list[ChunkRecord] = []
    idx = 0
    for heading, body in split_markdown_sections(text):
        for part in chunk_text(body, max_chars=1500):
            chunks.append({
                "collection": collection,
                "source": path.name,
                "source_id": sid,
                "chunk_index": idx,
                "title": heading[:200],
                "text": part,
                "section": heading[:256],
                "page": None,
                "meta_json": json.dumps({"type": "markdown", "path": str(path)}, ensure_ascii=False),
            })
            idx += 1
    if not chunks and text.strip():
        for part in chunk_text(text, max_chars=1500):
            chunks.append({
                "collection": collection,
                "source": path.name,
                "source_id": sid,
                "chunk_index": idx,
                "title": path.stem[:200],
                "text": part,
                "section": path.stem[:256],
                "page": None,
                "meta_json": json.dumps({"type": "markdown", "path": str(path)}, ensure_ascii=False),
            })
            idx += 1
    return chunks


def parse_docx(path: Path, collection: str, source_id: str | None = None) -> list[ChunkRecord]:
    from docx import Document

    doc = Document(str(path))
    sid = source_id or f"{collection}:{_slug(path.name)}"
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    full = "\n".join(paragraphs)
    chunks: list[ChunkRecord] = []
    idx = 0
    current_heading = path.stem
    buffer: list[str] = []
    for para in paragraphs:
        if len(para) < 80 and not para.endswith("。") and not para.endswith("."):
            if buffer:
                blob = "\n".join(buffer)
                for part in chunk_text(blob, max_chars=1200):
                    chunks.append({
                        "collection": collection,
                        "source": path.name,
                        "source_id": sid,
                        "chunk_index": idx,
                        "title": current_heading[:200],
                        "text": part,
                        "section": current_heading[:256],
                        "page": None,
                        "meta_json": json.dumps({"type": "docx"}, ensure_ascii=False),
                    })
                    idx += 1
                buffer = []
            current_heading = para
        else:
            buffer.append(para)
    if buffer:
        blob = "\n".join(buffer)
        for part in chunk_text(blob, max_chars=1200):
            chunks.append({
                "collection": collection,
                "source": path.name,
                "source_id": sid,
                "chunk_index": idx,
                "title": current_heading[:200],
                "text": part,
                "section": current_heading[:256],
                "page": None,
                "meta_json": json.dumps({"type": "docx"}, ensure_ascii=False),
            })
            idx += 1
    if not chunks and full:
        for part in chunk_text(full, max_chars=1200):
            chunks.append({
                "collection": collection,
                "source": path.name,
                "source_id": sid,
                "chunk_index": idx,
                "title": path.stem[:200],
                "text": part,
                "section": path.stem[:256],
                "page": None,
                "meta_json": json.dumps({"type": "docx"}, ensure_ascii=False),
            })
            idx += 1
    return chunks


def _ocr_page_text(page) -> str:
    """OCR 单页；按已安装语言包依次尝试。"""
    for language in ("eng+chi_sim", "eng", "chi_sim"):
        try:
            tp = page.get_textpage_ocr(full=True, language=language)
            text = (page.get_text(textpage=tp) or "").strip()
            if len(text) >= 5:
                return text
        except Exception:
            continue
    return ""


def _pdf_pages_text(path: Path) -> tuple[list[tuple[int, str]], str]:
    """
    提取 PDF 每页文本。先 pypdf，再 pymupdf；仍为空则 OCR（扫描版 PDF）。
    返回 (pages, method)，method 为 text|pymupdf|ocr|empty。
    """
    pages: list[tuple[int, str]] = []

    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages = [
            (page_num, (page.extract_text() or "").strip())
            for page_num, page in enumerate(reader.pages, start=1)
        ]
        if sum(len(t) for _, t in pages) >= 20:
            return pages, "text"
    except Exception:
        pages = []

    try:
        import pymupdf

        doc = pymupdf.open(str(path))
        pages = [(i + 1, (doc[i].get_text() or "").strip()) for i in range(len(doc))]
        doc.close()
        if sum(len(t) for _, t in pages) >= 20:
            return pages, "pymupdf"
    except Exception:
        if not pages:
            pages = []

    try:
        import pymupdf

        logger.info("PDF text empty, running OCR (may take 1-3 min): %s", path.name)
        doc = pymupdf.open(str(path))
        ocr_pages: list[tuple[int, str]] = []
        for i in range(len(doc)):
            page = doc[i]
            text = _ocr_page_text(page)
            ocr_pages.append((i + 1, text))
        doc.close()
        if sum(len(t) for _, t in ocr_pages) >= 20:
            return ocr_pages, "ocr"
        pages = ocr_pages
    except Exception:
        pass

    return pages, "empty" if sum(len(t) for _, t in pages) < 20 else "ocr"


def _pdf_pages_to_chunks(
    pages: list[tuple[int, str]],
    *,
    path: Path,
    collection: str,
    sid: str,
    extract_method: str,
) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    idx = 0
    for page_num, text in pages:
        if len(text) < 5:
            continue
        for part in chunk_text(text, max_chars=1200):
            chunks.append({
                "collection": collection,
                "source": path.name,
                "source_id": sid,
                "chunk_index": idx,
                "title": f"{path.stem} 第{page_num}页",
                "text": part,
                "section": f"page_{page_num}",
                "page": page_num,
                "meta_json": json.dumps(
                    {"type": "pdf", "page": page_num, "extract": extract_method},
                    ensure_ascii=False,
                ),
            })
            idx += 1
    if chunks:
        return chunks
    combined = "\n\n".join(t for _, t in pages if t.strip())
    if len(combined) < 10:
        return []
    for part in chunk_text(combined, max_chars=1200):
        chunks.append({
            "collection": collection,
            "source": path.name,
            "source_id": sid,
            "chunk_index": idx,
            "title": path.stem[:200],
            "text": part,
            "section": path.stem[:256],
            "page": None,
            "meta_json": json.dumps({"type": "pdf", "extract": extract_method}, ensure_ascii=False),
        })
        idx += 1
    return chunks


def parse_pdf(path: Path, collection: str, source_id: str | None = None) -> list[ChunkRecord]:
    sid = source_id or f"{collection}:{_slug(path.name)}"
    pages, method = _pdf_pages_text(path)
    return _pdf_pages_to_chunks(pages, path=path, collection=collection, sid=sid, extract_method=method)


def parse_pdf_with_meta(path: Path, collection: str, source_id: str | None = None) -> tuple[list[ChunkRecord], dict[str, Any]]:
    sid = source_id or f"{collection}:{_slug(path.name)}"
    pages, method = _pdf_pages_text(path)
    chunks = _pdf_pages_to_chunks(pages, path=path, collection=collection, sid=sid, extract_method=method)
    return chunks, {
        "extract_method": method,
        "page_count": len(pages),
        "text_chars": sum(len(t) for _, t in pages),
    }


def parse_pdf_directory(path: Path, collection: str, source_id_prefix: str | None = None) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    prefix = source_id_prefix or collection
    for pdf in sorted(path.rglob("*.pdf")):
        if "__MACOSX" in pdf.parts or pdf.name.startswith("._"):
            continue
        sid = f"{prefix}:{_slug(pdf.name)}"
        try:
            chunks.extend(parse_pdf(pdf, collection, sid))
        except Exception:
            continue
    return chunks


def parse_source(path: Path, collection: str, typ: str, source_id: str | None = None) -> list[ChunkRecord]:
    if not path.exists():
        raise FileNotFoundError(path)
    if typ == "pdf_dir":
        return parse_pdf_directory(path, collection, source_id)
    if typ == "markdown":
        return parse_markdown(path, collection, source_id)
    if typ == "docx":
        return parse_docx(path, collection, source_id)
    if typ == "pdf":
        return parse_pdf(path, collection, source_id)
    raise ValueError(f"unsupported type: {typ}")
