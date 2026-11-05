import logging
import sqlite3
import unicodedata

import pymupdf
from fastapi.testclient import TestClient

from app.main import app
from app.services.evidence_graph import projectEvidenceGraph


def test_unrelated_papers_do_not_get_scientific_stance_edges():
    chunk = dict(id=9, source="A.pdf", source_id="a", title="A", page=2,
                 collection="literature_inhibition", evidenceText="Only a shared topic.")
    result = {"papers": {"a": [chunk], "b": [{**chunk, "id": 10, "source_id": "b", "source": "B.pdf"}]},
              "thresholdComparison": {"records": [], "incompatible": []}, "groupTables": {}}
    graph = projectEvidenceGraph(result, 32, includeMedia=False)
    assert {node["type"] for node in graph["nodes"]} == {"paper"}
    assert graph["edges"] == []


def test_real_graph_build_and_lookup(tmp_path, monkeypatch, caplog):
    from app import evidence_graph_api

    monkeypatch.setattr(evidence_graph_api, "GRAPH_DB", tmp_path / "graphs.sqlite3")
    caplog.set_level(logging.ERROR, logger="pypdf")
    client = TestClient(app)
    route = "/v1/research/knowledge-graph"
    request = {"question": "Why do ammonia inhibition thresholds differ across studies of anaerobic digestion?",
               "paperLimit": 6}
    response = client.post(route + "/build", json=request)
    assert response.status_code == 200
    built = response.json()
    graphId = built["graphId"]
    graph = client.get(f"{route}/{graphId}?limit=100").json()
    nodes = {node["id"]: node for node in graph["nodes"]}
    assert len(nodes) == len(graph["nodes"])
    assert len({node["paperId"] for node in nodes.values() if node["type"] == "claim"}) >= 2
    edge = next(edge for edge in graph["edges"] if edge["type"] == "notComparableWith")
    assert {nodes[edge[k]]["type"] for k in ("source", "target")} == {"claim"}
    assert len(edge["evidence"]) == 2 and all(ref["page"] > 0 and ref["excerpt"] for ref in edge["evidence"])
    from app.config import settings

    for ref in edge["evidence"]:
        path = (settings.knowledge_path / "literature_corpus" / ref["collection"].removeprefix("literature_")
                / ref["source"])
        with pymupdf.open(path) as pdf:
            normalize = lambda value: " ".join(unicodedata.normalize("NFKC", value).split())
            assert normalize(ref["excerpt"]) in normalize(pdf[ref["page"] - 1].get_text())
    assert not {"supports", "contradicts"} & {edge["type"] for edge in graph["edges"]}
    related = client.get(f'{route}/{graphId}/nodes/{edge["source"]}/neighbors?relation=notComparableWith').json()
    assert edge["target"] in {node["id"] for node in related["nodes"]}
    assert client.get(f'{route}/{graphId}/edges/{edge["id"]}').json() == edge
    assert client.get(f"{route}/{graphId}/path", params={"source": edge["source"], "target": edge["target"]}).json() == {
        "found": True, "edges": [edge],
    }
    filtered = client.get(f"{route}/{graphId}", params={"relation": "notComparableWith", "limit": 2}).json()
    assert len(filtered["nodes"]) == 2 and len(filtered["edges"]) == 1
    media = next(node["media"] for node in graph["nodes"] if node["type"] == "media")
    assert (media["page"], media["kind"], media["number"]) == (4, "table", "1")
    image = client.get(f'/v1/research/media/{media["chunkId"]}/{media["mediaId"]}/image')
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    assert client.get(f'{route}/{graphId}/nodes/{"0"*24}').status_code == 404
    assert client.post(route + "/build", json=request).json() == built
    assert client.get(f"{route}/{graphId}?limit=100").json() == graph
    with sqlite3.connect(evidence_graph_api.GRAPH_DB) as db:
        assert db.execute("SELECT COUNT(*) FROM graph_snapshots").fetchone()[0] == 1


def test_aliases_keep_tan_fan_units_and_original_groups_distinct():
    quote = "Three arms measured total ammonia nitrogen and free ammonia nitrogen."
    chunk = dict(id=5, source="A.pdf", source_id="a", title="A", page=2,
                 collection="literature_inhibition", evidenceText=quote)
    entries = [
        ("A", "TAN", "mg N/L"), ("B", "Total ammonia nitrogen", "mg N/L"),
        ("C", "游离氨氮", "mg N/L"), ("D", "总氨氮", "mg/L"),
    ]
    records = [
        dict(sourceId="a", page=2, group=group, metric=metric, unit=unit,
             endpoint="measured result", value="1", evidenceText=quote)
        for group, metric, unit in entries
    ]
    data = projectEvidenceGraph({"papers": {"a": [chunk]}, "thresholdComparison": {"records": records}},
                                40, includeMedia=False)
    variables = {(node["label"], node["attributes"]["unit"]) for node in data["nodes"] if node["type"] == "variable"}
    assert variables == {("TAN", "mg N/L"), ("TAN", "mg/L"), ("FAN", "mg N/L")}
    assert len([node for node in data["nodes"] if node["type"] == "experiment"]) == 4
    assert all(edge["evidence"][0]["chunkId"] == 5 for edge in data["edges"])
