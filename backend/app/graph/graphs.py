"""LangGraph 科研问答子图定义。"""
from langgraph.graph import END, START, StateGraph

from app.graph.nodes.explain import research_qa_node
from app.graph.state import ResearchState


def build_research_qa_graph():
    g = StateGraph(ResearchState)
    g.add_node("research", research_qa_node)
    g.add_edge(START, "research")
    g.add_edge("research", END)
    return g.compile()