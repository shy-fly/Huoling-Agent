import unicodedata

import pymupdf
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.rag.retriever import get_all_chunks
from app.services.audit_rules import checkAuditRules


def normalized(value):
    return " ".join(unicodedata.normalize("NFKC", value).split())


def test_absence_and_technical_repeats_are_distinct():
    evidence = [
        {"section": "methods", "page": 2, "text": "PCR reactions were performed in triplicate."},
        {"section": "results", "page": 3, "text": "We measured the outcome at ten time points."},
    ]
    findings = {item["ruleId"]: item for item in checkAuditRules("experimental", evidence)}
    assert findings["independentReplication"]["status"] == "unclear"
    assert findings["control"]["status"] == "notReported"
    assert findings["statisticalMethod"]["status"] == "notReported"
    assert not any(item["status"] == "potentialIssue" for item in findings.values())


def test_audit_original_paper_and_repeatable_findings():
    paperId = next(chunk["source_id"] for chunk in get_all_chunks() if chunk["source"].startswith("Florentino-2019"))
    client = TestClient(app)
    req = {"type": "paper", "paperId": paperId}
    response = client.post("/v1/research/reliability-audit", json=req)
    assert response.status_code == 200
    report = response.json()
    study, = report["studies"]
    assert report["status"] == "completed"
    assert study["studyType"] == "experimental"
    assert {"methods", "results"} <= set(study["scope"]["sections"])
    checks = {item["ruleId"]: item for item in study["findings"]}
    assert checks["control"]["status"] == "reported"
    assert checks["independentReplication"]["status"] == "reported"
    assert report["claimAssessments"]
    refs = {source["evidenceId"]: source for source in report["references"]}
    for rule, page in (("control", 2), ("independentReplication", 4)):
        ref = refs[checks[rule]["evidenceIds"][0]]
        assert ref["page"] == page
        file = settings.knowledge_path / "literature_corpus" / ref["collection"].removeprefix("literature_") / ref["source"]
        with pymupdf.open(file) as pdf:
            assert normalized(ref["excerpt"]) in normalized(pdf[page-1].get_text())
    replicationRef = refs[checks["independentReplication"]["evidenceIds"][0]]
    assert replicationRef["visual"]["number"] == "1"
    again = client.post("/v1/research/reliability-audit", json=req).json()
    assert again["studies"] == report["studies"]
    assert again["references"] == report["references"]


def test_graph_claim_and_incomparable_relation_keep_exact_sources(tmp_path, monkeypatch, caplog):
    import logging
    from app import evidence_graph_api

    caplog.set_level(logging.ERROR, logger="pypdf")
    monkeypatch.setattr(evidence_graph_api, "GRAPH_DB", tmp_path / "graphs.sqlite3")
    client = TestClient(app)
    graphRoute = "/v1/research/knowledge-graph"
    built = client.post(graphRoute + "/build", json={
        "question": "Why do ammonia inhibition thresholds differ across studies of anaerobic digestion?",
        "paperLimit": 6,
    }).json()
    graphId = built["graphId"]
    graph = client.get(f"{graphRoute}/{graphId}?limit=120").json()
    claim = next(node for node in graph["nodes"] if node["type"] == "claim" and node["label"].startswith("中温组"))
    route = "/v1/research/reliability-audit"
    data = client.post(route, json={"type": "claim", "graphId": graphId, "entityId": claim["id"]}).json()
    assessment, = data["claimAssessments"]
    assert assessment["claimId"] == claim["id"] and assessment["status"] == "sourceReported"
    refs = {ref["evidenceId"]: ref for ref in data["references"]}
    claimRef = refs[assessment["evidenceIds"][0]]
    assert claimRef["page"] == 4 and claimRef["visual"]["number"] == "1"
    study, = data["studies"]
    findings = {item["ruleId"]: item for item in study["findings"]}
    assert findings["independentReplication"]["status"] == "unclear"
    assert findings["testLabelAmbiguity"]["status"] == "potentialIssue"
    assert refs[findings["testLabelAmbiguity"]["evidenceIds"][0]]["page"] == 3
    edge = next(edge for edge in graph["edges"] if edge["type"] == "notComparableWith")
    relation = client.post(route, json={"type": "relation", "graphId": graphId, "entityId": edge["id"]}).json()
    comparison, = relation["claimAssessments"]
    assert comparison["status"] == "limitedComparability"
    assert set(comparison["evidenceIds"]) == {ref["id"] for ref in edge["evidence"]}
    assert len(relation["studies"]) == 2
    assert client.post(route, json={"type": "claim", "graphId": graphId, "entityId": "0" * 24}).status_code == 404


def test_review_scope_and_falsification_context_are_bounded():
    client = TestClient(app)
    route = "/v1/research/reliability-audit"
    found = client.get(route + "/papers", params={"q": "Florentino"}).json()["items"]
    paperId = next(item["paperId"] for item in found if item["source"].startswith("Florentino-2019"))
    request = {"type": "hypothesis", "paperId": paperId, "page": 4,
               "claim": "BMP: 2 g GAC 52.8% vs no-GAC control group 34.2%. Does the reported treatment change this outcome?"}
    matched = client.post(route, json=request).json()["claimAssessments"][0]
    assert matched["status"] == "needsReview" and matched["evidenceIds"]
    assert matched["conditions"]["处理组"] == "2 g GAC"
    mismatched = client.post(route, json={**request, "page": 5}).json()["claimAssessments"][0]
    assert mismatched["status"] == "needsReview" and not mismatched["evidenceIds"]
    reviewId = next(chunk["source_id"] for chunk in get_all_chunks() if chunk["source"].startswith("Review_AD_FoodWaste"))
    review = client.post(route, json={"type": "paper", "paperId": reviewId}).json()
    assert review["status"] == "insufficientScope" and review["studies"][0]["studyType"] == "review"
    assert not any(item["ruleId"] == "control" for item in review["studies"][0]["findings"])
    assert client.post(route, json={"type": "paper", "paperId": "no-such-paper"}).status_code == 404
