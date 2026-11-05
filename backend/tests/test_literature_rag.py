"""文献语料与混合检索测试（科研）。"""
import pytest

from app.rag.literature_extract import CORPUS_ROOT
from app.rag.retriever import invalidate_cache, load_knowledge_base, retrieve
from app.rag.vector_index import invalidate_index


@pytest.fixture(autouse=True)
def _fresh():
    invalidate_cache()
    invalidate_index()
    yield
    invalidate_cache()
    invalidate_index()


def test_literature_corpus_present():
    for sub in ("inhibition", "theory", "engineering"):
        assert (CORPUS_ROOT / sub).is_dir()
    total = sum(
        len(list((CORPUS_ROOT / sub).rglob("*.pdf")))
        for sub in ("inhibition", "theory", "engineering")
    )
    assert total >= 50


def test_hybrid_retrieve_from_db():
    load_knowledge_base(force_db=True)
    kw = retrieve("游离氨 抑制 产甲烷菌", top_k=3, mode="keyword")
    hybrid = retrieve("游离氨 抑制 产甲烷菌", top_k=3)
    assert len(kw) >= 1
    assert len(hybrid) >= 1
    assert any(c.get("score") is not None for c in hybrid)