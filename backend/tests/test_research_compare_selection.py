from app.services.research_compare_selection import selectPapers


def chunk(sourceId, page=1, text="Experiment results", source=None):
    return {"source_id": sourceId, "source": source or f"{sourceId}.pdf",
            "page": page, "text": text}


def test_groups_ranked_chunks_by_paper_and_honors_filters():
    ranked = [chunk("a"), chunk("a", 2), chunk("b"), chunk("c")]
    result = selectPapers(ranked, 2, includeIds={"a", "b"}, excludeIds={"b"})
    assert list(result) == ["a"]
    assert [item["page"] for item in result["a"]] == [1, 2]


def test_excludes_invalid_pages_and_reference_sections():
    ranked = [chunk("a", 0), chunk("b", text="References\n1. Example"),
              chunk("c", source="notes.md"), chunk("d"), chunk("e")]
    assert list(selectPapers(ranked, 2)) == ["d", "e"]


def test_keeps_ranked_paper_order_and_limits_papers_not_chunks():
    ranked = [chunk("a"), chunk("b"), chunk("c"), chunk("a", 2)]
    result = selectPapers(ranked, 2)
    assert list(result) == ["a", "b"]
    assert len(result["a"]) == 2

