"""Resolve real paper and graph IDs before applying local audit rules."""
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Query

from app.evidence_graph_api import _entry, _load
from app.rag.media_search import COLLECTIONS
from app.rag.retriever import get_all_chunks
from app.services.audit_models import AuditReport, AuditTarget, GraphTarget
from app.services.reliability_audit import runAudit

router = APIRouter(prefix="/v1/research/reliability-audit")


@router.get("/papers")
def papers(q: str = Query("", max_length=150), limit: int = Query(12, ge=1, le=30)):
    term = q.strip().casefold()
    items = {}
    for chunk in get_all_chunks():
        sourceId, source = chunk["source_id"], chunk["source"]
        title = chunk.get("title") or source
        if (sourceId and sourceId not in items and chunk["collection"] in COLLECTIONS
                and source.lower().endswith(".pdf") and term in f"{source} {title}".casefold()):
            items[sourceId] = {"paperId": sourceId, "source": source, "title": title}
            if len(items) >= limit:
                break
    return {"items": list(items.values())}


def _graphTarget(target: GraphTarget) -> dict:
    graph = _load(target.graphId)
    if target.type == "relation":
        edge = _entry(graph["edges"], target.entityId)
        ends = [_entry(graph["nodes"], edge[key])["label"] for key in ("source", "target")]
        return {**edge, "label": " / ".join(ends)}
    node = _entry(graph["nodes"], target.entityId)
    if node["type"] != "claim":
        raise HTTPException(422, "graph node must be a claim")
    evidence = [source for edge in graph["edges"] if edge["source"] == node["id"] and edge["type"] == "derivedFrom"
                for source in edge["evidence"]]
    return {**node, "evidence": evidence, "conditions": node.get("attributes", {})}


@router.post("", response_model=AuditReport)
def audit(target: Annotated[AuditTarget, Body()]):
    graphItem = _graphTarget(target) if isinstance(target, GraphTarget) else None
    if graphItem:
        paperIds = {source["paperId"] for source in graphItem["evidence"]}
        if graphItem.get("paperId"):
            paperIds.add(graphItem["paperId"])
    else:
        paperIds = {target.paperId}
    papersById = defaultdict(list)
    for chunk in get_all_chunks():
        if chunk["source_id"] in paperIds and chunk["collection"] in COLLECTIONS and chunk["source"].lower().endswith(".pdf"):
            papersById[chunk["source_id"]].append(chunk)
    if not papersById:
        raise HTTPException(404, "audit source not found")
    report = runAudit(target, dict(papersById), graphItem)
    if paperIds - papersById.keys():
        report.status = "insufficientScope"
    return report
