"""Validate per-arm experiment contrasts against indexed PDF excerpts."""
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class QuotedResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    chunkId: int
    quote: str = Field(min_length=1)
    group: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    rawValue: str = Field(min_length=1)
    rawUnit: str = Field(min_length=1)


class ExperimentContrast(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    treatment: QuotedResult
    control: QuotedResult
    designQuote: str = Field(min_length=1)
    designChunkId: int


def verifyContrast(proposal: object, evidence: list[dict]) -> dict | None:
    from app.services.research_compare_extraction import _contains

    try:
        contrast = ExperimentContrast.model_validate(proposal)
    except ValidationError:
        return None
    chunks = {item["id"]: item for item in evidence if item.get("id") and item.get("page")}
    treatment, control = contrast.treatment, contrast.control
    if treatment.group.casefold() == control.group.casefold():
        return None
    design = " ".join(contrast.designQuote.split())
    designChunk = chunks.get(contrast.designChunkId)
    if not designChunk or design not in designChunk["evidenceText"]:
        return None
    if not all(_contains(design, arm.group) for arm in (treatment, control)):
        return None
    result = {}
    for label, arm in (("treatment", treatment), ("control", control)):
        chunk = chunks.get(arm.chunkId)
        quote = " ".join(arm.quote.split())
        if not chunk or quote not in chunk["evidenceText"]:
            return None
        if not all(_contains(quote, field) for field in (arm.group, arm.outcome, f"{arm.rawValue} {arm.rawUnit}")):
            return None
        other = control if arm is treatment else treatment
        if _contains(quote, other.group):
            return None
        result[label] = {**arm.model_dump(), "quote": quote, "page": chunk["page"]}
    return {
        **result, "designQuote": design, "designPage": designChunk["page"],
        "compatible": treatment.outcome.casefold() == control.outcome.casefold() and treatment.rawUnit == control.rawUnit,
    }

