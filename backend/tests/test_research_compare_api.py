from fastapi.testclient import TestClient

from app import main


def test_compare_route_passes_filters_and_hides_internal_ranked_chunks(monkeypatch):
    class Graph:
        def invoke(self, state):
            assert state["dimensions"] == ["TAN"]
            assert state["excludeIds"] == ["review"]
            return {
                "status": "insufficient_evidence", "retrievedPaperCount": 1,
                "selectedPaperCount": 0, "verifiedPaperCount": 0, "papers": {},
                "tableRecords": {}, "rankedChunks": ["internal"],
            }
    monkeypatch.setattr(main, "compareGraph", Graph())
    client = TestClient(main.app)
    response = client.post("/v1/research/compare", json={
        "question": "ammonia", "dimensions": ["TAN"], "excludeIds": ["review"],
    })
    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_evidence"
    assert "rankedChunks" not in response.json()
    assert client.post("/v1/research/compare", json={"question": "ammonia", "paperLimit": 1}).status_code == 422

