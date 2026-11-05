"""PDF / Markdown 上传解析测试。"""
from pathlib import Path

import pymupdf
import pytest

from app.rag.parsers import parse_markdown, parse_pdf_with_meta


def test_parse_markdown_without_headings(tmp_path: Path):
    path = tmp_path / "note.md"
    path.write_text("厌氧 UASB 酸化预警：VFA/碱度比超过 0.3 需关注。\n\n第二段说明文字。", encoding="utf-8")
    chunks = parse_markdown(path, "user_uploads")
    assert len(chunks) >= 1
    assert "VFA" in chunks[0]["text"]


def test_parse_pdf_text_layer(tmp_path: Path):
    path = tmp_path / "sample.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "UASB digester acidification early warning test paragraph for RAG upload.")
    doc.save(str(path))
    doc.close()

    chunks, meta = parse_pdf_with_meta(path, "user_uploads")
    assert meta["text_chars"] > 20
    assert len(chunks) >= 1
    assert "UASB" in chunks[0]["text"]


@pytest.mark.skipif(
    __import__("shutil").which("tesseract") is None,
    reason="tesseract not installed",
)
def test_parse_pdf_ocr_on_blank_scan(tmp_path: Path):
    path = tmp_path / "scan.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Scanned OCR fallback test content for knowledge upload.")
    pix = page.get_pixmap(dpi=150)
    page.clean_contents()
    page.insert_image(page.rect, pixmap=pix)
    doc.save(str(path))
    doc.close()

    chunks, meta = parse_pdf_with_meta(path, "user_uploads")
    assert meta["text_chars"] > 10
    assert len(chunks) >= 1
