"""RAG 知识块管理（查询、创建、更新、删除、上传、索引重建）。"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import or_

from app.agents.project_recorder import EventCategory, recorder
from app.config import settings
from app.models.db import KnowledgeChunk, SessionLocal, init_db
from app.rag.parsers import parse_docx, parse_markdown, parse_pdf_with_meta
from app.rag.retriever import get_all_chunks, invalidate_cache, load_knowledge_base
from app.rag.sanitize import sanitize_chunk
from app.rag.vector_index import build_index, invalidate_index

REFERENCE_COLLECTIONS = (
    "literature_inhibition",
    "literature_theory",
    "literature_engineering",
)

MANAGED_COLLECTIONS = REFERENCE_COLLECTIONS + ("user_uploads",)

UPLOADS_DIR = settings.uploads_path

_EXT_TYPE = {
    ".pdf": "pdf",
    ".md": "markdown",
    ".markdown": "markdown",
    ".docx": "docx",
    ".txt": "text",
}


def list_managed_collections() -> dict[str, Any]:
    return {"ok": True, "collections": list(MANAGED_COLLECTIONS), "reference_collections": list(REFERENCE_COLLECTIONS)}


def knowledge_chunk_stats() -> dict[str, Any]:
    """知识块总数与按集合分布统计（/v1/knowledge/stats 与 /v1/llm/overview 共用）。"""
    init_db()
    db = SessionLocal()
    total = db.query(KnowledgeChunk).count()
    by_coll: dict[str, int] = {}
    for row in db.query(KnowledgeChunk.collection).distinct():
        c = row[0]
        by_coll[c] = db.query(KnowledgeChunk).filter(KnowledgeChunk.collection == c).count()
    db.close()
    return {"total_chunks": total, "by_collection": by_coll}


def _chunk_row(row: KnowledgeChunk, *, include_text: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": row.id,
        "collection": row.collection,
        "source": row.source,
        "source_id": row.source_id,
        "chunk_index": row.chunk_index,
        "title": row.title,
        "page": row.page,
        "section": row.section,
        "text_preview": (row.text or "")[:200],
    }
    if include_text:
        data["text"] = row.text
        data["meta_json"] = row.meta_json
    return data


def rebuild_rag_index() -> dict[str, Any]:
    invalidate_cache()
    invalidate_index()
    load_knowledge_base(force_db=True)
    report = build_index(get_all_chunks())
    recorder.record(EventCategory.RAG, "index_rebuild", str(report.get("n_chunks", 0)))
    return {"ok": True, **report}


def list_chunks(
    collection: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    init_db()
    db = SessionLocal()
    query = db.query(KnowledgeChunk).order_by(KnowledgeChunk.id.desc())
    if collection:
        query = query.filter(KnowledgeChunk.collection == collection)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                KnowledgeChunk.title.like(like),
                KnowledgeChunk.text.like(like),
                KnowledgeChunk.source.like(like),
            )
        )
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    items = [_chunk_row(r) for r in rows]
    db.close()
    return {"ok": True, "total": total, "items": items}


def list_references(
    collection: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    init_db()
    db = SessionLocal()
    query = db.query(KnowledgeChunk).order_by(KnowledgeChunk.collection, KnowledgeChunk.id.desc())
    if collection:
        query = query.filter(KnowledgeChunk.collection == collection)
    else:
        query = query.filter(KnowledgeChunk.collection.in_(REFERENCE_COLLECTIONS))
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                KnowledgeChunk.title.like(like),
                KnowledgeChunk.text.like(like),
                KnowledgeChunk.source.like(like),
            )
        )
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    items = [_chunk_row(r) for r in rows]
    db.close()
    return {"ok": True, "total": total, "items": items, "collections": list(REFERENCE_COLLECTIONS)}


def get_chunk(chunk_id: int) -> dict[str, Any]:
    init_db()
    db = SessionLocal()
    row = db.query(KnowledgeChunk).filter(KnowledgeChunk.id == chunk_id).first()
    if not row:
        db.close()
        return {"ok": False, "error": "chunk not found"}
    out = _chunk_row(row, include_text=True)
    db.close()
    return {"ok": True, "chunk": out}


def delete_chunk(chunk_id: int) -> dict[str, Any]:
    init_db()
    db = SessionLocal()
    row = db.query(KnowledgeChunk).filter(KnowledgeChunk.id == chunk_id).first()
    if not row:
        db.close()
        return {"ok": False, "error": "chunk not found"}
    meta = {"id": chunk_id, "collection": row.collection, "source_id": row.source_id}
    db.delete(row)
    db.commit()
    db.close()
    index_report = rebuild_rag_index()
    recorder.record(EventCategory.RAG, "chunk_deleted", f"id={chunk_id}", detail=meta)
    return {"ok": True, "id": chunk_id, "index": index_report}


def _validate_collection(collection: str) -> str:
    collection = (collection or "").strip()
    if not collection or not re.match(r"^[a-z][a-z0-9_]{0,63}$", collection):
        raise ValueError("invalid collection name")
    return collection


def _insert_chunk_records(records: list[dict[str, Any]]) -> list[int]:
    init_db()
    db = SessionLocal()
    ids: list[int] = []
    for rec in records:
        row = KnowledgeChunk(**sanitize_chunk(rec))
        db.add(row)
        db.flush()
        ids.append(row.id)
    db.commit()
    db.close()
    return ids


def create_chunk(
    *,
    collection: str,
    text: str,
    source: str | None = None,
    title: str | None = None,
    source_id: str | None = None,
    section: str | None = None,
    page: int | None = None,
) -> dict[str, Any]:
    try:
        collection = _validate_collection(collection)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    text = (text or "").strip()
    if len(text) < 10:
        return {"ok": False, "error": "text too short (min 10 chars)"}
    sid = source_id or f"manual:{uuid.uuid4().hex[:12]}"
    rec = {
        "collection": collection,
        "source": source or "manual",
        "source_id": sid,
        "chunk_index": 0,
        "title": (title or source or "手动知识")[:256],
        "text": text,
        "section": (section or title or "manual")[:256],
        "page": page,
        "meta_json": json.dumps({"type": "manual", "source": "frontend"}, ensure_ascii=False),
    }
    ids = _insert_chunk_records([rec])
    index_report = rebuild_rag_index()
    recorder.record(EventCategory.RAG, "chunk_created", f"id={ids[0]} collection={collection}")
    return {"ok": True, "chunk": get_chunk(ids[0])["chunk"], "index": index_report}


def update_chunk(
    chunk_id: int,
    *,
    text: str | None = None,
    title: str | None = None,
    collection: str | None = None,
    source: str | None = None,
    section: str | None = None,
    page: int | None = None,
) -> dict[str, Any]:
    init_db()
    db = SessionLocal()
    row = db.query(KnowledgeChunk).filter(KnowledgeChunk.id == chunk_id).first()
    if not row:
        db.close()
        return {"ok": False, "error": "chunk not found"}
    if text is not None:
        text = text.strip()
        if len(text) < 10:
            db.close()
            return {"ok": False, "error": "text too short (min 10 chars)"}
        row.text = text
    if title is not None:
        row.title = title[:256]
    if collection is not None:
        try:
            row.collection = _validate_collection(collection)
        except ValueError as exc:
            db.close()
            return {"ok": False, "error": str(exc)}
    if source is not None:
        row.source = source[:256]
    if section is not None:
        row.section = section[:256]
    if page is not None:
        row.page = page
    db.commit()
    db.close()
    index_report = rebuild_rag_index()
    recorder.record(EventCategory.RAG, "chunk_updated", f"id={chunk_id}")
    out = get_chunk(chunk_id)
    return {"ok": True, "chunk": out["chunk"], "index": index_report}


def _write_upload_bytes(dest: Path, content: bytes) -> tuple[Path, str | None]:
    """写入上传文件；若同名文件无写权限（常见于 Docker root 遗留），改用唯一文件名。"""
    try:
        dest.write_bytes(content)
        return dest, None
    except OSError as exc:
        if dest.exists():
            alt = dest.with_name(f"{dest.stem}_{uuid.uuid4().hex[:8]}{dest.suffix}")
            try:
                alt.write_bytes(content)
                return alt, f"原文件不可覆盖，已另存为 {alt.name}"
            except OSError as exc2:
                hint = (
                    f"cannot write upload file: {exc2}。"
                    f"若为 Docker 遗留 root 文件，请删除 {dest.parent} 下同名文件或执行 "
                    f"chown -R $USER {dest.parent}"
                )
                return dest, hint
        return dest, f"cannot write upload file: {exc}"


def _parse_plain_text(path: Path, collection: str, source_id: str) -> list[dict[str, Any]]:
    from app.rag.chunking import chunk_text

    text = path.read_text(encoding="utf-8", errors="replace")
    chunks: list[dict[str, Any]] = []
    for i, part in enumerate(chunk_text(text, max_chars=1500)):
        chunks.append({
            "collection": collection,
            "source": path.name,
            "source_id": source_id,
            "chunk_index": i,
            "title": path.stem[:200],
            "text": part,
            "section": "text",
            "page": None,
            "meta_json": json.dumps({"type": "text", "upload": True}, ensure_ascii=False),
        })
    return chunks


def ingest_uploaded_file(
    content: bytes,
    filename: str,
    *,
    collection: str,
    title: str | None = None,
    replace_source_id: str | None = None,
) -> dict[str, Any]:
    collection = _validate_collection(collection)
    ext = Path(filename).suffix.lower()
    typ = _EXT_TYPE.get(ext)
    if not typ:
        return {"ok": False, "error": f"unsupported file type: {ext}"}

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w.\-]", "_", Path(filename).name)[:120]
    dest = UPLOADS_DIR / safe_name
    dest, write_note = _write_upload_bytes(dest, content)
    if write_note and write_note.startswith("cannot write"):
        return {"ok": False, "error": write_note}
    safe_name = dest.name

    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "_", Path(safe_name).stem)[:64]
    source_id = replace_source_id or f"upload:{collection}:{slug}"

    pdf_meta: dict[str, Any] = {}
    if typ == "text":
        records = _parse_plain_text(dest, collection, source_id)
    elif typ == "markdown":
        records = parse_markdown(dest, collection, source_id)
    elif typ == "pdf":
        records, pdf_meta = parse_pdf_with_meta(dest, collection, source_id)
    elif typ == "docx":
        records = parse_docx(dest, collection, source_id)
    else:
        return {"ok": False, "error": "unsupported type"}

    if not records:
        if ext == ".pdf":
            meta = pdf_meta if typ == "pdf" else {}
            if meta.get("extract_method") == "empty":
                return {
                    "ok": False,
                    "error": (
                        "PDF 为扫描版/图片页，未能 OCR 出文字。"
                        "请执行 docker compose up --build -d api 确保镜像含 Tesseract；"
                        "或上传可复制文字的 PDF / txt / docx。"
                    ),
                }
            return {
                "ok": False,
                "error": (
                    f"PDF 未生成知识块（{meta.get('page_count', '?')} 页，"
                    f"提取 {meta.get('text_chars', 0)} 字）。"
                ),
            }
        if ext in (".md", ".markdown"):
            return {"ok": False, "error": "Markdown 文件为空或无法读取"}
        if ext == ".docx":
            return {"ok": False, "error": "Word 文档未提取到正文（可能为纯图片）"}
        if ext == ".txt":
            return {"ok": False, "error": "文本文件为空"}
        return {"ok": False, "error": "no text extracted from file"}

    if title and records:
        for rec in records:
            rec["title"] = title[:200]

    init_db()
    db = SessionLocal()
    db.query(KnowledgeChunk).filter(KnowledgeChunk.source_id == source_id).delete()
    db.commit()
    db.close()

    ids = _insert_chunk_records(records)
    index_report = rebuild_rag_index()
    extract_note = ""
    if typ == "pdf" and pdf_meta.get("extract_method") == "ocr":
        extract_note = " (OCR)"
    recorder.record(
        EventCategory.RAG,
        "knowledge_upload",
        f"file={safe_name} chunks={len(ids)}{extract_note}",
        detail={"collection": collection, "source_id": source_id, "ids": ids[:5]},
    )
    return {
        "ok": True,
        "filename": safe_name,
        "collection": collection,
        "source_id": source_id,
        "chunks_created": len(ids),
        "chunk_ids": ids,
        "index": index_report,
        **({"note": write_note} if write_note else {}),
    }
