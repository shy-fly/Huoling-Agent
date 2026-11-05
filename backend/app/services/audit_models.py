"""Typed contracts for source-scoped reliability audit reports."""
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

PaperId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]
EntityId = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{24}$")]
Status = Literal["reported", "notReported", "unclear", "notApplicable", "potentialIssue", "needsReview"]
StudyType = Literal["experimental", "observational", "review", "computational", "methodological", "unknown"]


class PaperTarget(BaseModel):
    type: Literal["paper"]
    paperId: PaperId


class GraphTarget(BaseModel):
    type: Literal["claim", "relation"]
    graphId: EntityId
    entityId: EntityId


class HypothesisTarget(BaseModel):
    type: Literal["hypothesis"]
    paperId: PaperId
    page: int = Field(ge=1, le=2000)
    claim: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


AuditTarget = Annotated[PaperTarget | GraphTarget | HypothesisTarget, Field(discriminator="type")]


class VisualReference(BaseModel):
    kind: Literal["figure", "table"]
    number: str
    chunkId: int


class Reference(BaseModel):
    evidenceId: str
    paperId: str
    source: str
    collection: str
    page: int
    excerpt: str
    chunkId: int | None = None
    visual: VisualReference | None = None


class Finding(BaseModel):
    findingId: str
    ruleId: str
    category: str
    label: str
    status: Status
    observation: str
    checkedSections: list[str]
    uncertainty: str
    evidenceIds: list[str]
    sourcePages: list[int]
    requiresHumanReview: bool


class AuditScope(BaseModel):
    sections: list[str]
    pages: list[int]
    pageLimit: int
    truncated: bool
    supplementsChecked: bool
    available: bool


class StudyAudit(BaseModel):
    paperId: str
    source: str
    studyType: StudyType
    classificationEvidenceId: str | None
    objectiveEvidenceId: str | None
    methodEvidenceId: str | None
    status: Literal["completed", "insufficientScope"]
    scope: AuditScope
    findings: list[Finding]


class ClaimAssessment(BaseModel):
    claimId: str
    statement: str
    status: Literal["sourceReported", "limitedComparability", "needsReview"]
    evidenceIds: list[str]
    conditions: dict[str, str] = Field(default_factory=dict)
    limitations: list[str]


class AuditReport(BaseModel):
    auditId: str
    traceId: str
    target: AuditTarget
    status: Literal["completed", "insufficientScope"]
    studies: list[StudyAudit]
    claimAssessments: list[ClaimAssessment]
    references: list[Reference]
