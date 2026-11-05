import pytest

from app.rag.named_visual_retrieval import completeNamedVisualEvidence
from app.rag.retriever import retrieve


@pytest.mark.parametrize("question,expected", [
    ("Yang 等 2018 第 4 阶段中温高温 FAN 原表", ("Table 1", "156.89", "195.53")),
    ("Yang 等 2018 哪张图同时展示各阶段的甲烷产量与总挥发性脂肪酸？请引用原图。", ("Fig. 1.", "TVFA")),
    ("Yang 等 2018 论文第 7 阶段的 TAN 与 FAN 原表", ("Table 1", "293.29", "426.14")),
])
def test_named_paper_visual_evidence_keeps_caption_and_data(question, expected):
    ranked = completeNamedVisualEvidence(question, retrieve(question, top_k=5), 5)
    assert ranked[0]["source"].startswith("Yang-2018-")
    assert ranked[0]["page"] == 4
    assert all(term in ranked[0]["text"] for term in expected)
    assert len(ranked) <= 5

