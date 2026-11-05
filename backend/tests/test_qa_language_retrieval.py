from app.graph.nodes.explain import _retrieve_evidence


def test_named_paper_question_keeps_original_source():
    state = _retrieve_evidence({"question": "Yang 2018 中温和高温游离氨有何区别？", "rag_top_k": 8})
    chunks = state["rag_chunks"]
    assert chunks
    assert all(chunk["source"].startswith("Yang-2018-") for chunk in chunks)


def test_unknown_named_paper_does_not_substitute_unrelated_research():
    state = _retrieve_evidence({"question": "Nobodyauthor 2099 氨抑制有显著影响吗？", "rag_top_k": 5})
    assert state["rag_chunks"] == []


def test_bilingual_terms_share_search_representation():
    from app.rag.qa_query import searchQuestion
    chinese = searchQuestion("中温 高温 游离氨 总氨氮 抑制阈值")
    english = searchQuestion("mesophilic thermophilic free ammonia total ammonia nitrogen inhibition threshold")
    assert set(chinese.split()) == set(english.split())
