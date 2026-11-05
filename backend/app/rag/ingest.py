"""从 knowledge/manifests/sources.yaml 入库 knowledge_chunks。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from app.agents.project_recorder import EventCategory, recorder
from app.config import settings
from app.models.db import KnowledgeChunk, SessionLocal, init_db
from app.rag.literature_extract import extract_literature_zips
from app.rag.parsers import parse_pdf_directory, parse_source
from app.rag.retriever import invalidate_cache, load_knowledge_base
from app.rag.sanitize import sanitize_chunk
from app.rag.vector_index import build_index, invalidate_index

MANIFEST_PATH = settings.knowledge_path / "manifests" / "sources.yaml"


def resolve_source_path(path_str: str) -> Path:
    """manifest 中 path 相对 manifests 目录或 knowledge 根目录。"""
    manifests_dir = settings.knowledge_path / "manifests"
    p = Path(path_str)
    if path_str.startswith("../"):
        return (manifests_dir / path_str).resolve()
    return (settings.knowledge_path / path_str).resolve()


def load_sources_manifest() -> list[dict[str, Any]]:
    if not MANIFEST_PATH.exists():
        return []
    data = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    return data.get("sources", [])


def ingest_all(
    clear_existing: bool = True,
    extract_literature: bool = True,
    rebuild_index: bool = True,
) -> dict[str, Any]:
    init_db()
    sources = load_sources_manifest()
    report: dict[str, Any] = {
        "ok": True,
        "sources_processed": 0,
        "chunks_inserted": 0,
        "by_source": [],
        "errors": [],
    }

    if extract_literature:
        report["literature_extract"] = extract_literature_zips()

    all_chunks: list[dict[str, Any]] = []

    for src in sources:
        path_str = src.get("path", "")
        collection = src.get("collection", "general")
        typ = src.get("type", "markdown")
        source_id = src.get("source_id")
        try:
            path = resolve_source_path(path_str)
            if typ == "pdf_dir":
                chunks = parse_pdf_directory(path, collection, source_id)
            else:
                chunks = parse_source(path, collection, typ, source_id=source_id)
            all_chunks.extend(chunks)
            report["by_source"].append({
                "path": path_str,
                "collection": collection,
                "type": typ,
                "chunks": len(chunks),
                "resolved": str(path),
            })
            report["sources_processed"] += 1
        except Exception as exc:
            report["errors"].append({"path": path_str, "error": str(exc)})

    if report["errors"] or not all_chunks:
        report["ok"] = False
        return report
    db = SessionLocal()
    try:
        if clear_existing:
            db.query(KnowledgeChunk).filter(
                KnowledgeChunk.collection.notin_(("user_uploads",))
            ).delete(synchronize_session=False)
        else:
            source_ids = {c.get("source_id") for c in all_chunks if c.get("source_id")}
            if source_ids:
                db.query(KnowledgeChunk).filter(
                    KnowledgeChunk.source_id.in_(source_ids)
                ).delete(synchronize_session=False)
        for c in all_chunks:
            c = sanitize_chunk(c)
            db.add(
                KnowledgeChunk(
                    collection=c["collection"],
                    source=c["source"],
                    source_id=c.get("source_id"),
                    chunk_index=c.get("chunk_index", 0),
                    title=c.get("title"),
                    text=c["text"],
                    page=c.get("page"),
                    section=c.get("section"),
                    meta_json=c.get("meta_json"),
                )
            )
        db.commit()
        report["chunks_inserted"] = len(all_chunks)
    except Exception as exc:
        db.rollback()
        report["ok"] = False
        report["errors"].append({"path": "_db", "error": str(exc)})
    finally:
        db.close()

    invalidate_cache()
    invalidate_index()
    if rebuild_index and report["chunks_inserted"] > 0:
        load_knowledge_base(force_db=True)
        from app.rag.retriever import get_all_chunks

        report["vector_index"] = build_index(get_all_chunks())

    recorder.record(
        EventCategory.DATA,
        "knowledge_ingest",
        f"chunks={report['chunks_inserted']}",
        detail={"chunks": report["chunks_inserted"], "sources": report["sources_processed"]},
    )
    return report


if __name__ == "__main__":
    print(json.dumps(ingest_all(), ensure_ascii=False, indent=2, default=str))
