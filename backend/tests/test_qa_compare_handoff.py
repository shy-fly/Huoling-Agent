from fastapi.testclient import TestClient

from app.main import app
from app.models.db import KnowledgeChunk, SessionLocal


def evidenceRef():
    with SessionLocal() as session:
        row = session.query(KnowledgeChunk).filter(KnowledgeChunk.page > 0).first()
        assert row is not None
        return {"chunkId": row.id, "source": row.source, "collection": row.collection, "page": row.page}


def test_rejects_stale_or_forged_qa_reference():
    reference = evidenceRef()
    reference["source"] = "not-the-original-paper.pdf"
    response = TestClient(app).post("/v1/research/compare", json={
        "question": "Compare ammonia evidence",
        "qaContext": {"question": "Original question", "traceId": "test-trace", "evidence": [reference]},
    })
    assert response.status_code == 409


def test_rejects_empty_handoff():
    response = TestClient(app).post("/v1/research/compare", json={
        "question": "Compare ammonia evidence",
        "qaContext": {"question": "Original question", "traceId": "test-trace", "evidence": []},
    })
    assert response.status_code == 422


def test_resolves_ids_and_pages_from_database(monkeypatch):
    import app.main as main
    captured = {}

    def invoke(state):
        captured.update(state)
        return {"status": "insufficient_evidence", "retrievedPaperCount": 0,
                "selectedPaperCount": 0, "verifiedPaperCount": 0, "papers": {}, "tableRecords": {}}

    monkeypatch.setattr(main.compareGraph, "invoke", invoke)
    reference = evidenceRef()
    response = TestClient(app).post("/v1/research/compare", json={
        "question": "Compare ammonia evidence", "includeIds": ["forged-paper"],
        "qaContext": {"question": "Original question", "traceId": "test-trace",
                      "evidence": [reference, reference]},
    })
    assert response.status_code == 200
    with SessionLocal() as session:
        row = session.get(KnowledgeChunk, reference["chunkId"])
        assert captured["includeIds"] == [row.source_id]
        assert captured["priorityPages"] == {row.source_id: [row.page]}
    assert response.json()["qaContext"]["traceId"] == "test-trace"
    assert len(response.json()["qaContext"]["evidence"]) == 1
