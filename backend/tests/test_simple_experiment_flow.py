import pymupdf

from app.services.falsification_search import HypothesisSearch, searchHypothesis


def test_same_table_control_flows_to_falsification_report(tmp_path):
    folder = tmp_path / "test"
    folder.mkdir()
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        for x in (40, 150, 260):
            page.draw_line((x, 50), (x, 140))
        for y in (50, 80, 110, 140):
            page.draw_line((40, y), (260, y))
        for index, (group, value) in enumerate((("Group", "Yield (mL)"), ("Control", "10"), ("Treated", "15"))):
            page.insert_text((50, 69 + index * 30), group)
            page.insert_text((160, 69 + index * 30), value)
        pdf.save(folder / "experiment.pdf")
    chunk = {"id": 1, "source_id": "study", "source": "experiment.pdf",
             "collection": "literature_test", "page": 1, "text": "Control"}
    report = searchHypothesis(HypothesisSearch(hypothesis="Does treatment increase yield?"), tmp_path,
                              lambda question, top_k: [chunk])
    contrast, = report["groupTables"]["study"][0]["contrasts"]
    assert (contrast["treatment"]["verifiedValue"], contrast["control"]["verifiedValue"]) == ("15", "10")
    assert report["contrastSources"]["study"]["source"] == "experiment.pdf"
    assert report["hypothesisRevision"]["revisedClaim"] is None
