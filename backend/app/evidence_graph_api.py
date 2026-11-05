"""Build and inspect a bounded source-checked scientific evidence graph."""
from collections import deque
import sqlite3
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field, StringConstraints

from app.config import BACKEND_ROOT, settings
from app.graph.research_compare import buildResearchCompareGraph
from app.rag.retriever import get_all_chunks
from app.services.evidence_graph import projectEvidenceGraph, stableId
from app.services.evidence_graph_store import loadGraph, saveGraph

router = APIRouter(prefix="/v1/research/knowledge-graph")
GRAPH_DB = BACKEND_ROOT / "data" / "evidence-graphs.sqlite3"
compare = buildResearchCompareGraph(settings.knowledge_path / "literature_corpus")
Id = Annotated[str, Path(pattern=r"^[a-f0-9]{24}$")]
PaperId = Annotated[str, StringConstraints(min_length=1, max_length=256)]
PageNumber = Annotated[int, Field(ge=1)]
Relation = Literal["reports", "derivedFrom", "usesVariable", "citesMedia", "notComparableWith"]


class BuildRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    paperLimit: int = Field(default=6, ge=2, le=10)
    paperIds: list[PaperId] = Field(default_factory=list, max_length=10)
    sourcePages: dict[PaperId, Annotated[list[PageNumber], Field(max_length=16)]] = Field(default_factory=dict, max_length=10)
    maxNodes: int = Field(default=48, ge=12, le=120)


@router.post("/build")
def build(req: BuildRequest):
    paperIds = sorted(set(req.paperIds))
    priority = {key: sorted(set(pages)) for key, pages in req.sourcePages.items() if key in paperIds and pages}
    graphId = stableId("evidence-graph", " ".join(req.question.split()), req.paperLimit, req.maxNodes, paperIds, priority)
    result = compare.invoke({
        "question": req.question, "paperLimit": req.paperLimit, "includeIds": paperIds or None,
        "priorityPages": priority, "includePageSiblings": True,
    })
    graph = projectEvidenceGraph(result, req.maxNodes, indexed=get_all_chunks() if result["papers"] else [])
    stats = {
        "graphId": graphId, "nodeCount": len(graph["nodes"]), "edgeCount": len(graph["edges"]),
        "verifiedPaperCount": result["verifiedPaperCount"], "truncated": graph["truncated"],
    }
    try:
        saveGraph(GRAPH_DB, graphId, {**graph, **stats, "question": req.question})
    except (OSError, sqlite3.Error) as error:
        raise HTTPException(503, "graph storage unavailable") from error
    return stats


def _load(graphId: str) -> dict:
    try:
        graph = loadGraph(GRAPH_DB, graphId)
    except (OSError, sqlite3.Error, ValueError) as error:
        raise HTTPException(503, "graph storage unavailable") from error
    if graph is None:
        raise HTTPException(404, "graph not found")
    return graph


def _entry(items: list[dict], entryId: str) -> dict:
    item = next((item for item in items if item["id"] == entryId), None)
    if item is None:
        raise HTTPException(404, "graph item not found")
    return item


@router.get("/{graphId}")
def overview(graphId: Id, limit: int = Query(18, ge=1, le=120), relation: Relation | None = None):
    graph = _load(graphId)
    edges = [edge for edge in graph["edges"] if relation is None or edge["type"] == relation]
    visible = {}
    for edge in sorted(edges, key=lambda edge: edge["type"] != "notComparableWith"):
        endpoints = [edge["source"], edge["target"]]
        if len(visible) + sum(node not in visible for node in endpoints) <= limit:
            visible.update(dict.fromkeys(endpoints))
    if relation is None:
        for node in graph["nodes"]:
            if len(visible) == limit:
                break
            visible.setdefault(node["id"], None)
    return {
        **graph,
        "nodes": [node for node in graph["nodes"] if node["id"] in visible],
        "edges": [edge for edge in edges if edge["source"] in visible and edge["target"] in visible],
    }


@router.get("/{graphId}/nodes/{nodeId}")
def node(graphId: Id, nodeId: Id):
    return _entry(_load(graphId)["nodes"], nodeId)


@router.get("/{graphId}/edges/{edgeId}")
def edge(graphId: Id, edgeId: Id):
    return _entry(_load(graphId)["edges"], edgeId)


@router.get("/{graphId}/nodes/{nodeId}/neighbors")
def neighbors(graphId: Id, nodeId: Id, relation: Relation | None = None, limit: int = Query(12, ge=1, le=25)):
    graph = _load(graphId)
    _entry(graph["nodes"], nodeId)
    edges = [edge for edge in graph["edges"] if nodeId in (edge["source"], edge["target"])
             and (relation is None or edge["type"] == relation)][:limit]
    ids = {nodeId, *(edge[key] for edge in edges for key in ("source", "target"))}
    return {"nodes": [node for node in graph["nodes"] if node["id"] in ids], "edges": edges}


@router.get("/{graphId}/path")
def path(graphId: Id, source: str = Query(pattern=r"^[a-f0-9]{24}$"), target: str = Query(pattern=r"^[a-f0-9]{24}$")):
    graph = _load(graphId)
    _entry(graph["nodes"], source)
    _entry(graph["nodes"], target)
    queue = deque([(source, [])])
    seen = {source}
    while queue:
        current, route = queue.popleft()
        if current == target:
            return {"found": True, "edges": route}
        for edge in graph["edges"]:
            if current not in (edge["source"], edge["target"]):
                continue
            other = edge["target"] if current == edge["source"] else edge["source"]
            if other not in seen:
                seen.add(other)
                queue.append((other, [*route, edge]))
    return {"found": False, "edges": []}
