from app.services.research_compare_endpoints import compareStudyEndpoints


def record(sourceId, **changes):
    return {"sourceId": sourceId, "source": sourceId, "metric": "TAN",
            "unit": "mg N/L", "endpoint": "methane IC50", "qualifier": "exact"} | changes


def test_matches_only_exact_equivalent_endpoints():
    left = record("a")
    assert len(compareStudyEndpoints([left, record("b")])["comparable"]) == 1
    assert not compareStudyEndpoints([left, record("a")])["comparable"]
    result = compareStudyEndpoints([left, record("b", metric="FAN", unit="mg NH3/L", endpoint="lag")])
    assert result["incompatible"][0]["reasons"] == ["指标", "单位或质量口径", "响应终点"]
    result = compareStudyEndpoints([left, record("b", qualifier="not_reached")])
    assert len(result["incompatible"]) == 1


