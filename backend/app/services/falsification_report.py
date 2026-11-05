"""Summarize only the findings admitted by primary evidence review."""
from typing import Literal

from pydantic import BaseModel


class HypothesisRevision(BaseModel):
    status: Literal["not_reviewed", "insufficient_evidence", "no_counterexample_found"]
    revisedClaim: str | None
    evidenceIds: list[str]
    unresolvedQuestions: list[str]


def reviseHypothesis(evidence: list[dict], *, reviewPending: bool = False) -> HypothesisRevision:
    if not evidence:
        return HypothesisRevision(
            status="not_reviewed" if reviewPending else "insufficient_evidence",
            revisedClaim=None, evidenceIds=[],
            unresolvedQuestions=["是否有原始实验在明确条件下直接检验这条假设？"],
        )
    return HypothesisRevision(
        status="no_counterexample_found",
        revisedClaim=" ".join(item["reason"] for item in evidence),
        evidenceIds=[item["evidenceId"] for item in evidence],
        unresolvedQuestions=["在相同实验条件和响应终点下，其他独立研究能否复现这些结果？"],
    )
