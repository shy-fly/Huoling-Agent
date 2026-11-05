from app.services.publication_dates import publicationFromFront
from app.services.conclusion_evolution import selectPublications


def test_issue_year_is_distinct_from_online_receipt_and_doi():
    metadata = publicationFromFront(
        "Bioresource Technology 250 (2018) 390–397\n"
        "Received 8 October 2017\nAvailable online 24 November 2017\n"
        "https://doi.org/10.1016/j.biortech.2017.11.081"
    )
    assert metadata["year"] == 2018
    assert metadata["onlineYear"] == 2017
    assert metadata["doi"] == "10.1016/j.biortech.2017.11.081"
    assert publicationFromFront("Received 1998\nAvailable online 4 April 1999")["year"] is None


def test_duplicate_doi_and_unknown_year():
    date = {"doi": "10.1000/test", "year": 2020, "kind": "issue"}
    rows = {"a": date, "b": {**date, "year": None, "kind": "unknown"},
            "c": {"doi": None, "year": 2020, "kind": "issue"},
            "d": {"doi": None, "year": None, "kind": "unknown"}}
    selected, skipped = selectPublications(rows, None, None)
    assert list(selected) == ["a", "c"]
    assert skipped == {"duplicates": 1, "missingYear": 1, "outsideRange": 0}


def test_conflicting_imprint_dates_and_preprints_are_not_dated():
    assert publicationFromFront("Science Journal 20 (2018) 100\nScience Journal 21 (2019) 102")["kind"] == "conflict"
    assert publicationFromFront("arXiv: 0000.0000\nPublished: August 27, 2020")["year"] is None
    assert publicationFromFront("CreationDate: 20200104\nAccepted December 2018")["year"] is None


def test_same_year_papers_preserve_distinct_claims_and_unverified_stances_are_omitted():
    from app.services.conclusion_evolution import timelineFromGraph

    publications = {key: {**publicationFromFront("Science Journal 20 (2018) 100")}
                    for key in ("a", "b")}
    papers = [{"id": key, "type": "paper", "paperId": key, "source": key + ".pdf",
               "collection": "literature_inhibition"} for key in publications]
    claims = [{"id": "claim-" + key, "type": "claim", "paperId": key, "label": "same language",
               "attributes": {"metric": "TAN" if key == "a" else "FAN"}} for key in publications]
    refs = [{"id": "quote-" + key, "paperId": key, "page": 3, "excerpt": key} for key in publications]
    edges = [{"id": "proof-" + key, "source": "claim-" + key, "target": "quote-" + key,
              "type": "derivedFrom", "verificationStatus": "sourceChecked", "evidence": [ref]}
             for key, ref in zip(publications, refs)]
    edges.append({"id": "invented", "source": "claim-a", "target": "claim-b", "type": "contradicts",
                  "verificationStatus": "sourceChecked", "evidence": refs})
    timeline = timelineFromGraph({"nodes": [*papers, *claims], "edges": edges}, publications, 5)
    assert [event["claims"][0]["claimId"] for event in timeline["events"]] == ["claim-a", "claim-b"]
    assert timeline["periods"][0]["paperCount"] == 2
    assert timeline["periods"][0]["experimentRecordCount"] == 2
    assert timeline["relations"] == []


def test_real_default_timeline_has_three_dated_claim_years(caplog):
    import logging
    import unicodedata
    import pymupdf
    from fastapi.testclient import TestClient
    from app.config import settings
    from app.main import app

    caplog.set_level(logging.ERROR, logger="pypdf")
    client = TestClient(app)
    route = "/v1/research/evolution"
    response = client.post(route, json={"question": "厌氧消化氨抑制研究的科学认识是如何演变的？"})
    assert response.status_code == 200
    data = response.json()
    assert {2015, 2018, 2019} <= set(data["scope"]["claimYears"])
    assert data["relations"] and {item["type"] for item in data["relations"]} == {"notComparableWith"}
    assert sum(row["paperCount"] for row in data["periods"]) == len({item["paperId"] for item in data["events"]})
    assert sum(row["experimentRecordCount"] for row in data["periods"]) == sum(len(item["claims"]) for item in data["events"])
    for event in data["events"]:
        root = settings.knowledge_path / "literature_corpus"
        path = root / event["collection"].removeprefix("literature_") / event["source"]
        with pymupdf.open(path) as pdf:
            assert event["publication"]["excerpt"] in pdf[0].get_text()
            for claim in event["claims"]:
                for ref in claim["references"]:
                    normalize = lambda value: " ".join(unicodedata.normalize("NFKC", value).split())
                    assert normalize(ref["excerpt"]) in normalize(pdf[ref["page"]-1].get_text())
    empty = client.post(route, json={"question": "zzzzzqzxq", "paperIds": ["no-such-paper"]}).json()
    assert empty["events"] == [] and empty["summary"]["status"] == "insufficientTimeline"
    assert client.post(route, json={"question": "scope", "startYear": 2020, "endYear": 2000}).status_code == 422
