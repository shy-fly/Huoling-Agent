import base64

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.db import KnowledgeChunk, SessionLocal


@pytest.mark.parametrize(
    ("pattern", "page", "expected"),
    [
        ("AD_FoodWaste*", 2, ("figure", "1")),
        ("AD_FoodWaste*", 4, ("table", "1")),
        ("Methanogens_biochemical*", 4, ("figure", "1")),
        ("Fotidis-2013*", 3, ("table", "1")),
        ("Koster-1987*", 2, None),
        ("AnMBR_LCA_cost_analysis*", 13, None),
        ("AD_FoodWaste*", 12, None),
        ("Biogas_Upgrading_SingleMembrane*", 2, None),
    ],
)
def test_retrieved_page_visual_evidence(pattern, page, expected):
    source = next((settings.knowledge_path / "literature_corpus").rglob(pattern))
    with SessionLocal() as session:
        chunk = session.query(KnowledgeChunk).filter_by(
            source=source.name, collection=f"literature_{source.parent.name}", page=page
        ).first()
        assert chunk is not None
        chunkId = chunk.id

    response = TestClient(app).get(f"/v1/research/chunks/{chunkId}/visuals")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == page
    assert data["source"] == source.name
    if expected is None:
        assert data["visuals"] == []
        return
    item, = data["visuals"]
    assert (item["kind"], item["number"]) == expected
    assert item["caption"]
    assert len(item["region"]) == 4
    assert base64.b64decode(item["png"]).startswith(b"\x89PNG\r\n\x1a\n")


def test_visual_evidence_missing_chunk():
    assert TestClient(app).get("/v1/research/chunks/999999999/visuals").status_code == 404



def test_numbered_visuals_select_kind_on_same_page():
    with SessionLocal() as session:
        chunk = session.query(KnowledgeChunk).filter(
            KnowledgeChunk.source.like("Yang-2018-%"), KnowledgeChunk.page == 4
        ).first()
        assert chunk is not None
        url = f"/v1/research/chunks/{chunk.id}/visuals"

    client = TestClient(app)
    def visuals(**params):
        response = client.get(url, params=params)
        assert response.status_code == 200
        assert response.json()["page"] == 4
        return [(item["kind"], item["number"]) for item in response.json()["visuals"]]

    assert set(visuals()) == {("figure", "1"), ("table", "1")}
    assert visuals(kind="figure", number="1") == [("figure", "1")]
    assert visuals(kind="table", number="1") == [("table", "1")]
    assert visuals(kind="figure", number="999") == []
    assert client.get(url, params={"number": "1"}).status_code == 422

