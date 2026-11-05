#!/usr/bin/env python3
"""Docker 首次启动：按需全量 RAG 入库、启动科研问答服务。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# repo layout: /app in container
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def seed_knowledge_if_empty() -> None:
    from app.models.db import KnowledgeChunk, SessionLocal, init_db

    if os.environ.get("DOCKER_SEED_KNOWLEDGE", "true").lower() in ("0", "false", "no"):
        print("[entrypoint] DOCKER_SEED_KNOWLEDGE=false, skip RAG ingest")
        return
    init_db()
    db = SessionLocal()
    try:
        reference_count = db.query(KnowledgeChunk).filter(
            KnowledgeChunk.collection.notin_(("user_uploads",))
        ).count()
    finally:
        db.close()
    if reference_count > 0:
        print(f"[entrypoint] knowledge already present: references={reference_count}")
        return
    print("[entrypoint] knowledge missing, running full ingest (may take 1-3 min)...")
    from app.rag.ingest import ingest_all

    report = ingest_all(clear_existing=False, extract_literature=False, rebuild_index=True)
    inserted = report.get("chunks_inserted", 0)
    print(
        f"[entrypoint] ingest done: chunks={inserted} "
        f"sources={report.get('sources_processed')} ok={report.get('ok')}"
    )
    if not report.get("ok") or inserted == 0:
        errors = report.get("errors") or []
        print(f"[entrypoint] WARN: knowledge ingest incomplete: {errors[:5]}")


def main() -> None:
    seed_knowledge_if_empty()
    os.execvp("uvicorn", ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"])


if __name__ == "__main__":
    main()