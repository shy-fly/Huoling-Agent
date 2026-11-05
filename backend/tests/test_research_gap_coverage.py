from app.services.research_gap_coverage import CoverageAxis, buildCoverage


def test_counts_papers_separately_and_excludes_missing_or_different_units():
    x = CoverageAxis(field="concentration", unit="mg/L", edges=[0, 100, 200])
    y = CoverageAxis(field="group")
    def record(id, source, concentration):
        return {"id": id, "sourceId": source, "fields": {"concentration": concentration, "group": ["A", ""]}}
    result = buildCoverage([
        record("1", "paper", ["10", "mg/L"]), record("2", "paper", ["99", "mg/L"]),
        record("3", "paper", ["10", "mg N/L"]), record("4", "other", None),
    ], x, y, 1)
    observed, empty = result["coverageMatrix"]
    assert (observed["paperCount"], observed["recordCount"], observed["recordIds"]) == (1, 2, ["1", "2"])
    assert empty["state"] == "no_valid_records"
    assert result["missingData"] == {"concentration": 1}
    assert result["unmatchedData"] == {"concentration": 1}
    assert result["unclassifiedCount"] == 2
    assert not buildCoverage([], x, y, 1)["coverageMatrix"]
