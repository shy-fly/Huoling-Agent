"""Research coverage API."""
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field, model_validator

from app.config import settings
from app.graph.research_compare import buildResearchCompareGraph
from app.services.research_gap_records import collectGroupRecords
from app.services.research_gap_coverage import CoverageAxis, buildCoverage, collectPhaseRecords

router = APIRouter()
graph = buildResearchCompareGraph(settings.knowledge_path / "literature_corpus")


class GapRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    xAxis: CoverageAxis
    yAxis: CoverageAxis
    paperLimit: int = Field(default=5, ge=2, le=10)
    sparseLimit: int = Field(default=1, ge=1, le=5)
    includeIds: list[str] | None = Field(default=None, max_length=20)
    excludeIds: list[str] = Field(default_factory=list, max_length=20)
    sourcePages: dict[str, Annotated[list[Annotated[int, Field(ge=1)]], Field(max_length=16)]] = Field(
        default_factory=dict, max_length=20,
    )

    @model_validator(mode="after")
    def distinctAxes(self):
        if self.xAxis.field == self.yAxis.field:
            raise ValueError("Coverage axes must be distinct")
        return self


@router.post("/v1/research/gaps")
def researchGaps(req: GapRequest):
    result = graph.invoke({
        "question": req.question, "paperLimit": req.paperLimit,
        "includeIds": req.includeIds, "excludeIds": req.excludeIds,
        "dimensions": sorted({req.xAxis.field, req.yAxis.field}),
        "priorityPages": {sourceId: pages for sourceId, pages in req.sourcePages.items()
                          if sourceId in (req.includeIds or [])},
    })
    records = collectPhaseRecords(result) + collectGroupRecords(result)
    axisFields = {req.xAxis.field, req.yAxis.field}
    records = [record for record in records if axisFields.intersection(record["fields"])]
    coverage = buildCoverage(records, req.xAxis, req.yAxis, req.sparseLimit)
    gaps = [cell for cell in coverage["coverageMatrix"] if cell["state"] != "observed"]
    used = {record["sourceId"] for record in records}
    return {
        **coverage, "researchQuestion": req.question, "scope": "仅限本次检索并成功提取的本地记录",
        "traceId": str(uuid4()), "axisDefinitions": [req.xAxis, req.yAxis],
        "retrievedPaperCount": result["retrievedPaperCount"], "verifiedPaperCount": result["verifiedPaperCount"],
        "analyzedPaperCount": len(used), "experimentRecords": records,
        "papers": [{"sourceId": key, "source": chunks[0]["source"], "analyzed": key in used}
                   for key, chunks in result["papers"].items()],
        "identifiedGaps": gaps,
        "researchQuestions": [
            f'在 {req.xAxis.field} {cell["x"]} 和 {req.yAxis.field} {cell["y"]} 下，进一步实验会观察到怎样的响应？'
            for cell in gaps[:3]
        ],
    }

