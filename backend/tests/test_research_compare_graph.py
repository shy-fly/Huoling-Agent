from app.graph.research_compare import buildResearchCompareGraph


def test_graph_backfills_rejected_papers_and_reports_verified_count(tmp_path):
    import pymupdf

    folder = tmp_path / "inhibition"
    folder.mkdir()
    body = "Ammonia inhibition was measured at 35 degrees."
    for name in ("a", "b", "c"):
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((60, 60), body)
            pdf.new_page().insert_text((60, 60), "References")
            pdf.new_page().insert_text((60, 60), body)
            pdf.save(folder / f"{name}.pdf")
    def chunk(name, page=1, quote=body):
        return dict(id=1, source_id=name, source=f"{name}.pdf", collection="literature_inhibition",
                    page=page, text=quote)
    ranked = [chunk("missing"), chunk("a", 4), chunk("a", 3),
              chunk("a", quote="Invented number"), chunk("a"), chunk("b"), chunk("c")]
    def extractPaper(question, sourceId, evidence):
        assert sourceId != "missing"
        return [dict(group="Ammonia", dimension="inhibition", rawValue="35",
                     rawUnit="degrees", chunkId=1, quote=body, sourceKind="uncertain")]

    graph = buildResearchCompareGraph(tmp_path, lambda question, top_k: ranked, extractPaper=extractPaper)
    result = graph.invoke({"question": "ammonia inhibition", "paperLimit": 3})
    assert result["retrievedPaperCount"] == 4
    assert result["verifiedPaperCount"] == 3
    assert result["experimentRecords"]["a"][0]["sourceId"] == "a"
    assert result["rejectedObservationCount"] == 0
    assert list(result["papers"]) == ["a", "b", "c"]
    assert [item["page"] for item in result["papers"]["a"]] == [1]
    assert result["papers"]["a"][0]["evidenceText"] == body


def test_graph_reports_insufficient_evidence(tmp_path):
    graph = buildResearchCompareGraph(tmp_path, lambda question, top_k: [])
    result = graph.invoke({"question": "unrelated", "paperLimit": 3})
    assert result["status"] == "insufficient_evidence"



def test_handoff_prioritizes_indexed_page_outside_search_results(tmp_path, monkeypatch):
    import pymupdf

    folder = tmp_path / "inhibition"
    folder.mkdir()
    body = "Observed results with a control."
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((60, 60), "Background.")
        pdf.new_page().insert_text((60, 60), body)
        pdf.save(folder / "study.pdf")
    indexed = dict(id=2, source_id="study", source="study.pdf", collection="literature_inhibition",
                   page=2, text=body)
    monkeypatch.setattr("app.graph.research_compare.get_all_chunks", lambda: [indexed])
    graph = buildResearchCompareGraph(tmp_path, lambda question, top_k: [])
    result = graph.invoke({"question": "Follow up", "includeIds": ["study"],
                           "priorityPages": {"study": [2, 3]}})
    assert result["retrievedPaperCount"] == 0
    assert [item["page"] for item in result["papers"]["study"]] == [2]
    assert result["papers"]["study"][0]["evidenceText"] == body
