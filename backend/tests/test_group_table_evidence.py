from app.services.group_table_evidence import _trustedCell


def test_numeric_glyphs_fail_closed_when_encoding_is_ambiguous():
    assert _trustedCell("0.37 ± 0.01", {"body", "symbol"})
    assert _trustedCell("2.35", {"body"})
    assert not _trustedCell("0.3760.01", {"body", "symbol"})
    assert not _trustedCell("1160.4", {"body", "symbol"})

def test_ocr_must_confirm_both_numbers_and_symbol():
    from app.services.table_cell_ocr import confirmPlusMinus

    assert confirmPlusMinus(["0.37", "6", "0.01"], ["0 · 37 ± 0 · 01"]) == "0.37 ± 0.01"
    assert confirmPlusMinus(["11", "6", "0.4"], ["1160.4", "11 ± 0.04"]) is None


def test_method_control_needs_explicit_unique_designation():
    from app.services.group_table_evidence import _methodControl

    methods = [{"page": 2, "evidenceText": "R1 served as the untreated control. R2 received the additive."}]
    group, evidence = _methodControl({"R1", "R2"}, methods)
    assert (group, evidence["page"], evidence["quote"]) == ("R1", 2, "R1 served as the untreated control")
    assert _methodControl({"R1", "R2"}, [{"page": 2, "evidenceText": "R1 had a lower dose than R2."}]) == (None, None)
