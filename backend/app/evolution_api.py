"""Search historical sources and return a reproducible local timeline."""
from collections import Counter, defaultdict
import re
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.config import settings
from app.evidence_graph_api import _load
from app.graph.research_compare import buildResearchCompareGraph
from app.rag.experiment_retrieval import retrieveExperimentEvidence
from app.rag.media_search import COLLECTIONS
from app.rag.retriever import QUERY_ALIASES, get_all_chunks, retrieve
from app.services.audit_evidence import collectAuditEvidence
from app.services.audit_models import PaperTarget
from app.services.conclusion_evolution import selectPublications, timelineFromGraph
from app.services.evidence_graph import projectEvidenceGraph, stableId
from app.services.evolution_evidence import outcomePages, recheckEvolutionEvidence
from app.services.publication_dates import readPublication
from app.services.reliability_audit import runAudit

router = APIRouter(prefix="/v1/research/evolution")
PaperId = Annotated[str, StringConstraints(min_length=1, max_length=256)]
GraphId = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{24}$")]
Year = Annotated[int, Field(ge=1800, le=2099)]


class EvolutionRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    startYear: Year | None = None
    endYear: Year | None = None
    grouping: Literal[1, 5, 10] = 1
    paperLimit: int = Field(default=10, ge=2, le=10)
    paperIds: list[PaperId] = Field(default_factory=list, max_length=20)
    excludePaperIds: list[PaperId] = Field(default_factory=list, max_length=20)
    graphId: GraphId | None = None
    claimId: GraphId | None = None
    includeAudit: bool = False

    @model_validator(mode="after")
    def checkScope(self):
        if self.startYear and self.endYear and self.startYear > self.endYear:
            raise ValueError("startYear must not exceed endYear")
        if self.claimId and not self.graphId:
            raise ValueError("claimId requires graphId")
        return self


def _candidates(req: EvolutionRequest, indexed: list[dict]) -> tuple[list[dict], dict]:
    ranked = retrieveExperimentEvidence(req.question, top_k=60) if not req.graphId else []
    allowed = set(req.paperIds)
    excluded = set(req.excludePaperIds)
    direct = {chunk["source_id"] for chunk in retrieve(req.question, top_k=60)} if not allowed and not req.graphId else None
    aliases = {word for key, variants in QUERY_ALIASES.items() if key in req.question for word in variants}
    topic = re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, sorted(aliases))) + r")(?!\w)", re.I) if aliases and not allowed else None
    front = defaultdict(list)
    if topic:
        for chunk in indexed:
            if chunk.get("page") == 1:
                front[chunk["source_id"]].append(chunk.get("text") or "")
    candidates = {}
    for chunk in [*ranked, *(indexed if allowed else [])]:
        sourceId = chunk.get("source_id")
        if (sourceId and sourceId not in excluded and (not allowed or sourceId in allowed)
                and chunk.get("collection") in COLLECTIONS and (chunk.get("source") or "").lower().endswith(".pdf")):
            if direct is not None and sourceId not in direct:
                continue
            if topic and not topic.search(" ".join(" ".join(front[sourceId]).split())[:3500]):
                continue
            candidates.setdefault(sourceId, chunk)
        if len(candidates) >= 24:
            break
    return ranked, candidates


def _diverse(publications: dict, limit: int) -> list[str]:
    periods = defaultdict(list)
    for paperId, date in publications.items():
        periods[date["year"] // 5].append(paperId)
    ordered = []
    while any(periods.values()) and len(ordered) < limit:
        for ids in periods.values():
            if ids and len(ordered) < limit:
                ordered.append(ids.pop(0))
    return ordered


@router.post("")
def evolution(req: EvolutionRequest):
    indexed = get_all_chunks()
    graph = _load(req.graphId) if req.graphId else None
    if graph and req.claimId and not any(node["id"] == req.claimId and node["type"] == "claim" for node in graph["nodes"]):
        raise HTTPException(404, "graph claim not found")
    if graph:
        available = {node["paperId"] for node in graph["nodes"] if node["type"] == "paper"}
        wanted = (available & set(req.paperIds) if req.paperIds else available) - set(req.excludePaperIds)
        _, candidates = _candidates(req.model_copy(update={"paperIds": list(wanted)}), indexed) if wanted else ([], {})
        ranked = []
    else:
        ranked, candidates = _candidates(req, indexed)
    metadata = {paperId: readPublication(chunk) for paperId, chunk in candidates.items()}
    publications, skipped = selectPublications(metadata, req.startYear, req.endYear)
    byPaper = defaultdict(list)
    for chunk in indexed:
        paperId = chunk.get("source_id")
        if paperId in publications and chunk["source"] == candidates[paperId]["source"] and chunk["collection"] == candidates[paperId]["collection"]:
            byPaper[paperId].append(chunk)
    documents = {paperId: collectAuditEvidence(byPaper[paperId]) for paperId in publications}
    pins = {}
    if graph:
        preferred = {node["paperId"] for node in graph["nodes"] if node["type"] == "claim"}
    else:
        for paperId, document in documents.items():
            pins[paperId] = outcomePages(byPaper[paperId], document)
        preferred = {paperId for paperId, pages in pins.items() if pages}
    chosen = _diverse({key: value for key, value in publications.items() if key in preferred}, req.paperLimit)
    chosen.extend(_diverse({key: value for key, value in publications.items() if key not in preferred}, req.paperLimit - len(chosen)))
    documents = {paperId: documents[paperId] for paperId in chosen}
    if graph is None and chosen:
        for paperId in chosen:
            first = next((chunk["page"] for chunk in byPaper[paperId] if chunk.get("page")), None)
            pins[paperId] = list(dict.fromkeys([page for page in [first, *pins[paperId]] if page]))
        comparison = buildResearchCompareGraph(
            settings.knowledge_path / "literature_corpus", lambda question, top_k: ranked,
            expandPages=True,
        ).invoke({"question": req.question, "includeIds": chosen, "paperLimit": req.paperLimit,
                  "priorityPages": {key: pins[key] for key in chosen}, "includePageSiblings": True})
        graph = projectEvidenceGraph(comparison, 120, indexed=indexed)
    graph, studies = recheckEvolutionEvidence(graph or {"nodes": [], "edges": []}, byPaper, documents)
    selected = {paperId: publications[paperId] for paperId in chosen}
    timeline = timelineFromGraph(graph, selected, req.grouping, studies)
    if req.includeAudit:
        for event in timeline["events"]:
            paperId = event["paperId"]
            report = runAudit(PaperTarget(type="paper", paperId=paperId), {paperId: byPaper[paperId]})
            event["audit"] = {"auditId": report.auditId, "status": report.status,
                              "findings": dict(Counter(item.status for item in report.studies[0].findings))}
    years = sorted({event["year"] for event in timeline["events"]})
    withClaims = [event for event in timeline["events"] if event["claims"]]
    observedClaimYears = sorted({event["year"] for event in withClaims})
    relations = Counter(item["type"] for item in timeline["relations"])
    return {
        **timeline,
        "analysisId": stableId("evolution", req.model_dump()),
        "question": req.question, "graphId": req.graphId, "claimId": req.claimId,
        "scope": {**skipped, "candidateCount": len(candidates), "includedPaperCount": len(timeline["events"]),
                  "claimPaperCount": len(withClaims), "claimYears": observedClaimYears, "yearCount": len(years),
                  "startYear": years[0] if years else None, "endYear": years[-1] if years else None,
                  "grouping": req.grouping, "outsideLimit": len(publications) - len(chosen),
                  "unverifiedPaperCount": len(chosen) - len(timeline["events"])},
        "summary": {
            "status": "evidenceAvailable" if len(observedClaimYears) >= 2 else "insufficientTimeline",
            "relations": dict(relations),
            "limitations": ["时间轴仅覆盖本地库本次命中且核对过发表年份的论文。",
                            "日期表示发表记录。关系需有原文依据，按年排列不表示引用影响。",
                            "无记录的年份只能说明本次未覆盖。不同指标与单位不连接为数值趋势。"],
        },
    }

