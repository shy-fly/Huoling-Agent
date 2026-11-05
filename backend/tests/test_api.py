from urllib.parse import quote

from fastapi.testclient import TestClient

from app.main import app
from conftest import ADMIN_HEADERS

client = TestClient(app)


def test_health_endpoint():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "log_dir" in data


def test_audit_logs_endpoint():
    assert client.post("/v1/logs/note", json={"message": "blocked"}).status_code == 403
    assert client.get("/v1/logs/audit").status_code == 403
    assert client.get("/v1/logs/trace/test").status_code == 403
    note = client.post("/v1/logs/note", json={"message": "api test note"}, headers=ADMIN_HEADERS)
    assert note.status_code == 200
    r = client.get("/v1/logs/audit?limit=5", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    assert len(r.json()["items"]) >= 1


def test_llm_status():
    r = client.get("/v1/llm/status")
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok")


def test_agents_endpoint():
    r = client.get("/v1/agents")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"]
    assert data["default_agent_id"] == "research"
    assert len(data["agents"]) >= 1


def test_knowledge_stats():
    r = client.get("/v1/knowledge/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"]
    assert data["total_chunks"] >= 4000


def test_knowledge_collections():
    r = client.get("/v1/knowledge/collections")
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok")


def test_research_qa_endpoint(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "use_llm", False)
    r = client.post("/v1/research/qa", json={
        "question": "VFA accumulation and pH relationship in anaerobic digestion",
        "top_k": 3,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["ok"]
    assert data.get("answer")
    assert data.get("trace_id")
    assert data.get("runtime", {}).get("knowledge_hits", 0) >= 0

def test_research_pdf_is_inline(monkeypatch, tmp_path):
    corpus = tmp_path / "inhibition"
    corpus.mkdir()
    document = corpus / "source paper.pdf"
    document.write_bytes(b"%PDF-test")
    monkeypatch.setattr("app.main.LITERATURE_PDF_ROOT", tmp_path)

    response = client.get(
        "/v1/research/literature/" + quote(document.name),
        params={"collection": "literature_inhibition", "page": 3},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.headers["x-pdf-page"] == "3"
    assert response.content == b"%PDF-test"


def test_research_pdf_rejects_non_pdf_and_path_segments(monkeypatch, tmp_path):
    corpus = tmp_path / "inhibition"
    corpus.mkdir()
    (corpus / "paper.pdf").write_bytes(b"%PDF-test")
    (corpus / "private.txt").write_text("private")
    monkeypatch.setattr("app.main.LITERATURE_PDF_ROOT", tmp_path)

    for invalid in ("private.txt", "folder%2Fpaper.pdf", "folder%5Cpaper.pdf", "%2E%2E%2Fpaper.pdf"):
        assert client.get(f"/v1/research/literature/{invalid}").status_code in (403, 404)
    assert client.get("/v1/research/literature/paper.pdf?page=-1").status_code == 422


def test_local_chinese_summary_preserves_reported_null_and_source():
    from app.graph.nodes.explain import _research_template_answer

    chunk = {
        "source_id": "paper-a", "source": "paper.pdf", "collection": "literature_inhibition",
        "page": 3, "text": "In this work, the tested ammonia levels had no significant effect "
        "(P > 0.05) on relative abundance for Methanosarcina (Fig. 2).",
    }
    answer = _research_template_answer("氨会影响菌群吗？", [chunk])
    assert "相对丰度未见显著变化" in answer
    assert "P > 0.05" in answer
    assert "第 3 页 [1]" in answer
    assert "未见显著变化" not in _research_template_answer(
        "氨会影响菌群吗？", [{**chunk, "text": "References: ammonia levels."}]
    )


def test_research_stream_rejects_empty_question_and_unbounded_retrieval():
    for body in ({"question": "   "}, {"question": "What is TAN?", "top_k": 100000}):
        assert client.post("/v1/research/qa/stream", json=body).status_code == 422
