"""Resolve a QA handoff against current evidence instead of trusting client metadata."""
from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.models.db import KnowledgeChunk, SessionLocal


class QaEvidenceRef(BaseModel):
    chunkId: int = Field(gt=0)
    source: str = Field(min_length=1, max_length=512)
    collection: str = Field(min_length=1, max_length=80)
    page: int = Field(gt=0)


class QaCompareContext(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    traceId: str = Field(min_length=1, max_length=128)
    evidence: list[QaEvidenceRef] = Field(min_length=1, max_length=20)


def resolveQaContext(context: QaCompareContext) -> tuple[dict, dict]:
    references = {ref.chunkId: ref for ref in context.evidence}
    pages: dict[str, list[int]] = {}
    evidence = []
    with SessionLocal() as session:
        rows = {row.id: row for row in session.query(KnowledgeChunk).filter(
            KnowledgeChunk.id.in_(references),
        ).all()}
        for chunkId, reference in references.items():
            row = rows.get(chunkId)
            if row is None or (row.source, row.collection, row.page) != (
                reference.source, reference.collection, reference.page,
            ) or not row.source_id or not row.source.lower().endswith(".pdf"):
                raise HTTPException(status_code=409, detail="问答证据已失效，请重新提问后比较。")
            if row.page not in pages.setdefault(row.source_id, []):
                pages[row.source_id].append(row.page)
            evidence.append({**reference.model_dump(), "paperId": row.source_id})
    return (
        {"includeIds": list(pages), "priorityPages": pages},
        {"question": context.question, "traceId": context.traceId, "evidence": evidence},
    )
