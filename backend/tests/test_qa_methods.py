from app.rag.qa_query import includeMethods


def test_method_evidence_is_preserved_within_budget():
    result = {"id": 1, "source_id": "a", "page": 4, "text": "TAN affected methane yield."}
    method = {"id": 2, "source_id": "a", "page": 2, "text": "2. Materials and methods\nContinuous stirred tank reactor."}
    other = {"id": 3, "source_id": "b", "page": 1, "text": "A review of ammonia."}
    found = includeMethods([result, other], [result, method, other], 2)
    assert [item["id"] for item in found] == [1, 2]


def test_method_enrichment_does_not_add_unrelated_papers():
    result = {"id": 1, "source_id": "a", "page": 4, "text": "Reported results."}
    unrelated = {"id": 2, "source_id": "b", "page": 2, "text": "Materials and methods\nAn unrelated study."}
    assert includeMethods([result], [unrelated], 2) == [result]


def test_method_heading_keeps_same_page_continuation():
    result = {"id": 1, "source_id": "a", "page": 4, "text": "Reported results."}
    heading = {"id": 2, "source_id": "a", "page": 2, "text": "Introduction tail.\n2. Materials and methods\n2.1 Inoculum"}
    continuation = {"id": 3, "source_id": "a", "page": 2, "text": "Continuous stirred tank reactor at two temperatures."}
    found = includeMethods([result], [heading, continuation], 2)
    assert "Continuous stirred tank reactor" in found[-1]["text"]
    assert found[-1]["id"] == 2 and found[-1]["page"] == 2
