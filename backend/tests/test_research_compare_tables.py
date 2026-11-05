from app.services.research_compare_tables import extractPhaseRows


def test_keeps_phase_and_group_columns_separate():
    rows = [
        ["", "Phase 0", "Phase 1"],
        ["Mesophilic", "M0", "M1"],
        ["TAN (g/L)", "0.21", "1"],
        ["FAN (mg/L)", "3.36", "20.07"],
        ["Thermophilic", "T0", "T1"],
        ["TAN (g/L)", "0.39", "1"],
        ["FAN (mg/L)", "15.30", "39.22"],
    ]
    result = extractPhaseRows(rows, {"TAN", "FAN"})
    assert [(r.group, r.phase, r.rawValue) for r in result if r.dimension == "FAN"] == [
        ("M0", "Phase 0", "3.36"), ("M1", "Phase 1", "20.07"),
        ("T0", "Phase 0", "15.30"), ("T1", "Phase 1", "39.22"),
    ]
    assert result[0].rawUnit == "g/L"


def test_skips_ambiguous_and_malformed_cells():
    rows = [["", "Phase 0", "Phase 1"], ["Mesophilic", "M0", "M1"],
            ["FAN (mg/L)", "336 .", "20.07"], ["TAN (g/L)", "7"]]
    assert [r.rawValue for r in extractPhaseRows(rows, {"TAN", "FAN"})] == ["20.07"]

