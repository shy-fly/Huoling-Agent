from app.services.falsification_search import HypothesisSearch, searchHypothesis


def test_searches_support_and_counter_independently(tmp_path):
    calls = []
    def search(question, top_k):
        calls.append(question)
        return []
    result = searchHypothesis(HypothesisSearch(hypothesis="TAN 升高会使甲烷产量下降吗？"), tmp_path, search)
    assert len(set(calls)) == 4
    assert all("TAN" in query for query in calls)
    assert [item["track"] for item in result["searches"]] == ["support", "counter", "counter", "counter"]
    assert result["status"] == "insufficient_evidence"
    assert result["papers"] == {}


def test_primary_review_does_not_treat_missing_ic50_as_contradiction():
    from app.services.falsification_review import classifyPrimaryEndpoints

    endpoint = {"metric": "TAN", "endpoint": "甲烷产量 IC₅₀"}
    records = [
        {**endpoint, "qualifier": "lower_bound"},
        {**endpoint, "qualifier": "not_reached"},
        {**endpoint, "metric": "FAN", "qualifier": "lower_bound"},
    ]
    assert [item["classification"] for item in classifyPrimaryEndpoints("tan", records)] == [
        "support", "conditional",
    ]
    assert classifyPrimaryEndpoints("microplastic", records) == []

