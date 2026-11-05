import sqlite3

import pymupdf
from fastapi.testclient import TestClient

from app.main import app
from app.models.db import KnowledgeChunk, SessionLocal
from app.rag.media_index import indexPage


def test_media_search_serves_verified_originals_without_duplicate_index(monkeypatch, tmp_path):
    from app import media_api

    monkeypatch.setattr(media_api, "INDEX_ROOT", tmp_path)
    with SessionLocal() as session:
        chunk = session.query(KnowledgeChunk).filter(
            KnowledgeChunk.source.like("Yang-2018-%"), KnowledgeChunk.page == 4,
        ).first()
        paperId = chunk.source_id
    client = TestClient(app)
    query = {"question": "Yang 2018 Figure 1 methane production pathways",
             "paperIds": [paperId], "kind": "figure", "number": "1"}
    response = client.post("/v1/research/media/search", json=query)
    assert response.status_code == 200
    item, = response.json()["items"]
    assert (item["paperId"], item["page"], item["kind"], item["number"]) == (paperId, 4, "figure", "1")
    assert item["caption"] and item["relatedChunks"] and len(item["captionRegion"]) == 4
    url = f'/v1/research/media/{item["chunkId"]}/{item["mediaId"]}'
    assert client.get(url).json()["mediaId"] == item["mediaId"]
    for size in ("thumb", "full"):
        image = client.get(url + "/image", params={"size": size})
        assert image.status_code == 200
        assert image.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert client.post("/v1/research/media/search", json=query).json()["items"][0]["mediaId"] == item["mediaId"]
    assert client.post("/v1/research/media/search", json={**query, "number": "999"}).json()["items"] == []
    assert client.get(url.replace(item["mediaId"], "0" * 32) + "/image").status_code == 404
    assert client.get(url + "/image?size=../../file").status_code == 422
    with sqlite3.connect(tmp_path / "index.sqlite3") as db:
        assert db.execute("select count(*) from media_pages where page=4 and paperId=?", (paperId,)).fetchone()[0] == 1
    table, = client.post("/v1/research/media/search", json={**query, "question": "Yang 2018 Table 1 TAN and FAN", "kind": "table"}).json()["items"]
    assert table["mediaId"] != item["mediaId"]
    assert table["tableStatus"] in {"extracted", "needsReview"}


def test_index_above_caption_and_unpaired_mention(tmp_path):
    path = tmp_path / "document.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((70, 80), "Fig. 2. Growth across samples.")
        page.draw_rect((70, 100, 280, 260), color=(0, 0, 0))
        page.insert_text((70, 360), "Figure 3 shows an example in a different study.")
        pdf.save(path)
    result = indexPage(tmp_path / "cache", path, "plant-paper", 1)
    item, = result["visuals"]
    assert item["number"] == "2"
    assert item["region"][1] < item["captionRegion"][1]
    assert item["region"][3] > 250


def test_missing_pdf_and_regenerated_cache(tmp_path):
    from app.rag.media_index import mediaImage

    source = tmp_path / "source.pdf"
    cache = tmp_path / "cache"
    assert indexPage(cache, source, "paper", 1)["status"] == "failed"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.draw_rect((70, 100, 280, 260), color=(0, 0, 0))
        page.insert_text((70, 275), "Figure S1. Growth by treatment.")
        pdf.save(source)
    result = indexPage(cache, source, "paper", 1)
    item, = result["visuals"]
    assert item["number"] == "S1"
    path = mediaImage(cache, source, 1, item, "thumb")
    assert path is not None
    path.unlink()
    assert mediaImage(cache, source, 1, item, "thumb") == path
    assert path.is_file()
    assert indexPage(cache, source, "paper", 1, refresh=True) == result
    assert indexPage(cache, source, "paper", 2)["status"] == "failed"


def test_local_qa_numbers_only_a_real_named_visual(monkeypatch, tmp_path):
    import re

    from app.config import settings
    from app.rag import media_search

    monkeypatch.setattr(media_search, "INDEX_ROOT", tmp_path)
    monkeypatch.setattr(settings, "use_llm", False)
    client = TestClient(app)
    question = "Yang 2018 Figure 1 methane production"
    data = client.post("/v1/research/qa", json={"question": question}).json()
    marker = re.search(r"原文图表 \[(\d+)\]（图 1）", data["answer"])
    assert marker
    cited = data["chunks"][int(marker[1]) - 1]
    assert cited["source"].startswith("Yang-2018") and cited["page"] == 4
    assert "原文图表" not in client.post("/v1/research/qa", json={
        "question": question.replace("Figure 1", "Figure 999"),
    }).json()["answer"]



def test_grouped_headers_are_not_exposed_as_unambiguous_raw_columns(tmp_path):
    from app.config import settings

    source = next((settings.knowledge_path / "literature_corpus").rglob("*Loftin*.pdf"))
    result = indexPage(tmp_path, source, "loftin-test", 5)
    table, = [item for item in result["visuals"] if item["kind"] == "table" and item["number"] == "4"]
    assert table["tableStatus"] == "needsReview"
    assert "rawRows" not in table


def test_topic_search_uses_more_than_the_paper_scope(tmp_path):
    from app.rag.media_search import searchMedia

    result = searchMedia(tmp_path, "Find figures showing methane production during ammonia inhibition in anaerobic digestion.",
                         "figure", None, [], 10)
    assert any("methane" in item["caption"].lower() for item in result["items"])
    assert all("The number of AD-related publications" not in item["caption"] for item in result["items"])
