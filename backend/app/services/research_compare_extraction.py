"""Validate per-paper observations against PDF-verified excerpts."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ProposedObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)

    group: str = Field(min_length=1)
    dimension: str = Field(min_length=1)
    rawValue: str = Field(min_length=1)
    rawUnit: str = ""
    chunkId: int
    quote: str = Field(min_length=1)
    sourceKind: Literal["primary", "secondary", "uncertain"]


class VerifiedObservation(ProposedObservation):
    sourceId: str
    page: int


def _contains(text: str, value: str) -> bool:
    return re.search(r"(?<![\w.])" + re.escape(value) + r"(?!\w|\.\d)", text) is not None


def validateExperiments(
    sourceId: str, evidence: list[dict], proposals: list[object],
) -> tuple[list[VerifiedObservation], int]:
    chunks = {item["id"]: item for item in evidence if "id" in item}
    verified = []
    rejected = 0
    for raw in proposals:
        try:
            proposal = ProposedObservation.model_validate(raw)
        except ValidationError:
            rejected += 1
            continue
        chunk = chunks.get(proposal.chunkId)
        quote = " ".join(proposal.quote.split())
        valueWithUnit = f"{proposal.rawValue} {proposal.rawUnit}".strip()
        joinedValueWithUnit = proposal.rawValue + proposal.rawUnit
        if (
            chunk is None or quote not in chunk["evidenceText"]
            or not _contains(quote, proposal.group)
            or not _contains(quote, proposal.dimension)
            or not any(_contains(quote, value) for value in (valueWithUnit, joinedValueWithUnit))
        ):
            rejected += 1
            continue
        observation = proposal.model_dump()
        observation["quote"] = quote
        verified.append(VerifiedObservation(
            **observation, sourceId=sourceId, page=chunk["page"],
        ))
    return verified, rejected

