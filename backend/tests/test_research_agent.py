"""科研知识挖掘智能体（research）：注册、Prompt、检索边界、无运行数据问答、API 结构。"""
from fastapi.testclient import TestClient

from app.config import settings
from app.graph.graphs import build_research_qa_graph
from app.main import app
from app.rag.retriever import retrieve
from app.services import agent_prompts, agent_registry as reg

client = TestClient(app)
RESEARCH_COLLECTIONS = ["literature_inhibition", "literature_theory", "literature_engineering"]


def test_research_agent_registered():
    agent = reg.get_agent("research")
    assert agent["id"] == "research"
    assert sorted(agent["rag_collections"]) == sorted(RESEARCH_COLLECTIONS)
    rag = reg.resolve_rag_collections("research")
    assert sorted(rag) == sorted(RESEARCH_COLLECTIONS)


def test_research_prompt_loaded():
    guard = agent_prompts.get_agent_prompt("research", "system/research_guardrails")
    assert guard["ok"] is True
    assert guard["prompt"]["source"] == "agent"
    assert "研究结论" in guard["prompt"]["content"]
    qa = agent_prompts.get_agent_prompt("research", "tasks/research_qa")
    assert qa["ok"] is True
    assert qa["prompt"]["source"] == "agent"
    for section in ("研究结论", "文献证据对照", "机理与差异解释", "证据局限"):
        assert section in qa["prompt"]["content"]


def test_research_retrieve_scoped_to_literature():
    chunks = retrieve("游离氨对产甲烷菌的抑制机理", top_k=6, collections=reg.resolve_rag_collections("research"))
    assert chunks
    assert all(c.get("collection", "").startswith("literature_") for c in chunks)
    assert all(c.get("collection") in RESEARCH_COLLECTIONS for c in chunks)
    assert all(c.get("page") is not None or c.get("source") for c in chunks)


def test_research_qa_without_reactor_data(monkeypatch):
    monkeypatch.setattr(settings, "use_llm", False)
    graph = build_research_qa_graph()
    result = graph.invoke(
        {
            "mode": "qa",
            "question": "游离氨抑制产甲烷菌的机理是什么？",
            "agent_id": "research",
            "rag_collections": reg.resolve_rag_collections("research"),
            "trace_id": "test-research-no-data",
        }
    )
    narrative = result["narrative"]
    for section in ("研究结论", "文献证据对照", "机理与差异解释", "证据局限"):
        assert section in narrative
    assert not any(t in narrative for t in ("本班怎么做", "复测与升级", "现场依据"))
    assert len(result["citations"]) == len(result["rag_chunks"])
    for chunk in result["rag_chunks"]:
        assert chunk.get("collection") in RESEARCH_COLLECTIONS


def test_research_api_response_structure(monkeypatch):
    monkeypatch.setattr(settings, "use_llm", False)
    response = client.post("/v1/research/qa", json={"question": "厌氧消化中氨氮的抑制作用研究进展"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["agent_id"] == "research"
    assert isinstance(body["trace_id"], str) and body["trace_id"]
    assert isinstance(body["answer"], str) and body["answer"]
    assert isinstance(body["citations"], list)
    assert isinstance(body["chunks"], list)
    assert len(body["citations"]) == len(body["chunks"])
    for chunk in body["chunks"]:
        assert chunk["collection"] in RESEARCH_COLLECTIONS
        assert "source" in chunk and "page" in chunk and "score" in chunk
        assert "citation" in chunk
    assert "answer_mode" in body["runtime"]
    assert body["runtime"]["knowledge_hits"] == len(body["chunks"])


def test_research_rag_top_k_enters_state_and_caps_chunks(monkeypatch):
    monkeypatch.setattr(settings, "use_llm", False)
    graph = build_research_qa_graph()
    result = graph.invoke(
        {
            "mode": "qa",
            "question": "游离氨抑制产甲烷机理与文献对照",
            "agent_id": "research",
            "rag_collections": reg.resolve_rag_collections("research"),
            "rag_top_k": 1,
            "trace_id": "test-topk-state",
        }
    )
    assert len(result["rag_chunks"]) == 1
    assert len(result["citations"]) == 1