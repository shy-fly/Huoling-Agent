def test_import_main():
    from app.main import app
    assert app is not None


def test_import_graphs():
    from app.graph.graphs import build_research_qa_graph
    g = build_research_qa_graph()
    assert g is not None


def test_import_rag():
    from app.rag.retriever import retrieve
    from app.rag.chunking import chunk_text
    assert callable(retrieve)
    assert callable(chunk_text)


def test_import_llm():
    from app.llm.provider import get_llm_provider
    assert callable(get_llm_provider)