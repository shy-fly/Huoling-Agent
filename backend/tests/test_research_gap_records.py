from app.services.research_gap_records import collectGroupRecords


def test_group_records_do_not_join_across_tables_or_accept_bad_cells():
    source = {"source": "sample.pdf", "collection": "test"}
    def cell(header, raw, value):
        return {"group": "R1", "row": 2, "header": header, "rawCell": raw, "verifiedValue": value}
    result = {"papers": {"p": [source]}, "groupTables": {"p": [
        {"page": 4, "tableIndex": 1, "records": [cell("X (mg/L)", "6 ± 1", "6 ± 1")]},
        {"page": 4, "tableIndex": 2, "records": [cell("Y (mg/L)", "1160.4", None)]},
    ]}}
    first, second = collectGroupRecords(result)
    assert first["fields"]["X"] == ["6", "mg/L"]
    assert first["rawCells"]["X"] == "6 ± 1"
    assert "Y" not in first["fields"]
    assert second["fields"]["Y"] is None
    assert first["id"] != second["id"]
