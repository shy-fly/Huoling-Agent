"""LangGraph 科研问答状态定义。"""
from typing import Any, Optional, TypedDict


class ResearchState(TypedDict, total=False):
    agent_id: str
    rag_collections: Optional[list[str]]
    rag_top_k: int
    timestamp: str
    mode: str
    question: str
    history: list[dict[str, str]]
    rag_query: Optional[str]
    rag_chunks: list[dict[str, Any]]
    narrative: Optional[str]
    citations: list[str]
    answer_mode: str
    warnings: list[str]
    errors: list[str]
    trace_id: str
    ok: bool