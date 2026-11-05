"""Candidate retrieval for hypothesis review using the existing comparison graph."""
from collections.abc import Callable
from itertools import zip_longest
from pathlib import Path

from pydantic import BaseModel, Field

from app.graph.research_compare import buildResearchCompareGraph
from app.rag.experiment_retrieval import retrieveExperimentEvidence
from app.services.reported_outcomes import reviewReportedOutcomes
from app.services.falsification_report import reviseHypothesis
from app.services.falsification_review import classifyPrimaryEndpoints, reviewProfile


class HypothesisSearch(BaseModel):
    hypothesis: str = Field(min_length=1, max_length=2000)
    sourceId: str | None = Field(default=None, max_length=256)
    sourcePage: int | None = Field(default=None, ge=1)
    context: str = Field(default="", max_length=1000)
    paperLimit: int = Field(default=5, ge=2, le=10)
    includeIds: list[str] | None = None
    excludeIds: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)


def searchHypothesis(
    request: HypothesisSearch, corpusRoot: Path,
    search: Callable[..., list[dict]] = retrieveExperimentEvidence,
) -> dict:
    topic = " ".join(filter(None, (request.hypothesis.strip(), request.context.strip())))
    profile = reviewProfile(request.hypothesis)
    if profile:
        topic = f"{topic} {profile[1]}"
    counterDirections = (
        "无显著差异 反例 no significant effect unchanged",
        "适用范围 阈值 boundary conditions threshold",
        "测量口径 对照 混杂 endpoint confounding control",
    )
    queries = [profile[1] if profile else topic, *(f"{topic} {direction}" for direction in counterDirections)]
    ranked = [search(query, top_k=request.paperLimit * 4) for query in queries]
    candidates = {}
    for batch in zip_longest(*ranked):
        for chunk in batch:
            if chunk is not None:
                candidates.setdefault(chunk["id"], chunk)
    ordered = sorted(candidates.values(), key=lambda chunk: not (
        chunk.get("source_id") == request.sourceId and chunk.get("page") == request.sourcePage
    ))
    comparison = buildResearchCompareGraph(
        corpusRoot, lambda question, top_k: ordered,
        expandPages=search is retrieveExperimentEvidence,
    )
    reviewed = comparison.invoke({
        "question": topic, "paperLimit": request.paperLimit,
        "includeIds": request.includeIds, "excludeIds": request.excludeIds,
        "dimensions": request.dimensions,
    })
    evidence = classifyPrimaryEndpoints(profile[0], reviewed["thresholdComparison"]["records"]) if profile else []
    evidence.extend(reviewReportedOutcomes(request.hypothesis, reviewed["thresholdComparison"]["records"]))
    for item in evidence:
        item["evidenceId"] = f'{item["sourceId"]}:{item["page"]}:{item["qualifier"]}'
    revision = reviseHypothesis(evidence, reviewPending=bool(candidates) or profile is None or profile[0] != "tan")
    accepted = {item["sourceId"] for item in evidence}
    return {
        "evidence": evidence,
        "groupTables": {
            key: [table for table in tables if table["contrasts"]]
            for key, tables in reviewed["groupTables"].items()
            if any(table["contrasts"] for table in tables)
        },
        "contrastSources": {
            key: {"source": chunks[0]["source"], "collection": chunks[0]["collection"]}
            for key, chunks in reviewed["papers"].items()
            if any(table["contrasts"] for table in reviewed["groupTables"].get(key, []))
        },
        "hypothesisRevision": revision.model_dump(),
        "excludedPaperCount": reviewed["verifiedPaperCount"] - len(accepted),
        "hypothesis": request.hypothesis,
        "searches": [
            {"track": "support" if index == 0 else "counter", "query": query,
             "paperIds": list(dict.fromkeys(chunk["source_id"] for chunk in ranked[index] if chunk.get("source_id")))}
            for index, query in enumerate(queries)
        ],
        "verifiedPaperCount": reviewed["verifiedPaperCount"],
        "papers": {key: value for key, value in reviewed["papers"].items() if key in accepted},
        "tableRecords": {key: value for key, value in reviewed["tableRecords"].items() if key in accepted},
        "thresholdComparison": {"records": evidence},
        "status": revision.status,
    }



