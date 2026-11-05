from app.rag.paper_page_search import supplementPaperPages


def test_supplements_methods_results_and_table_without_changing_paper():
    def chunk(page, text, source="target"):
        return {"id": page, "page": page, "text": text, "source_id": source}

    abstract = chunk(1, "Abstract")
    index = [
        chunk(2, "Materials and Methods\nreactors"),
        chunk(3, "Results and Discussion\nmethane yield"),
        chunk(4, "Table 3. Methane yield"),
        chunk(5, "References"),
        chunk(6, "Table 4. Methane yield"),
        chunk(7, "Results\nMethane yield", "other"),
    ]
    assert [item["page"] for item in supplementPaperPages("methane yield", [abstract], index)] == [1, 2, 3, 4]


def test_supplements_siblings_only_on_selected_non_reference_pages():
    ranked = {"id": 1, "page": 3, "source_id": "study", "text": "Results."}
    caption = {**ranked, "id": 2, "text": "Figure caption."}
    otherPaper = {**caption, "id": 3, "source_id": "another"}
    otherPage = {**caption, "id": 4, "page": 4}
    rows = supplementPaperPages("results", [ranked], [ranked, caption, otherPaper, otherPage],
                                includePageSiblings=True)
    assert rows == [ranked, caption]
