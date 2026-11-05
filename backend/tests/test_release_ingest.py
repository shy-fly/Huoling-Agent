"""Protect existing evidence when release ingestion has no usable input."""
import pytest
from app.models.db import KnowledgeChunk, SessionLocal
from app.rag import ingest

@pytest.mark.parametrize("sources", [[], [{"path": "missing-release-file.pdf", "type": "pdf"}]])
def test_ingest_failure_preserves_existing_rows(monkeypatch, sources):
    monkeypatch.setattr(ingest, "load_sources_manifest", lambda: sources)
    with SessionLocal() as session:
        before = session.query(KnowledgeChunk).count()
    report = ingest.ingest_all(extract_literature=False)
    assert report["ok"] is False
    with SessionLocal() as session:
        assert session.query(KnowledgeChunk).count() == before
