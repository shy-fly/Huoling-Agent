"""Complete indexed evidence for explicitly named paper figure/table questions."""
import re

from app.rag.media_search import NAMED_PAPER, requestedVisual
from app.rag.visual_evidence import indexedCaptions
from app.rag.retriever import get_all_chunks

_TERMS = {
    "甲烷产量": "methane production",
    "挥发性脂肪酸": "tvfa",
    "阶段": "phase",
    "中温": "mesophilic",
    "高温": "thermophilic",
}


def completeNamedVisualEvidence(question: str, ranked: list[dict], limit: int) -> list[dict]:
    named = NAMED_PAPER.search(question)
    if not named or not re.search(r"图|表|\b(?:fig(?:ure)?|table)\b", question, re.I):
        return ranked
    author, year = named.groups()
    prefix = f"{author}-{year}-".lower()
    sources = {chunk["source_id"] for chunk in ranked if (chunk.get("source") or "").lower().startswith(prefix)}
    if len(sources) != 1:
        return ranked
    sourceId = next(iter(sources))
    pages = {}
    for chunk in get_all_chunks():
        if chunk.get("source_id") == sourceId and chunk.get("page"):
            pages.setdefault(chunk["page"], []).append(chunk)
    query = question.lower()
    terms = {word for word in ("tan", "fan", "tvfa") if re.search(rf"\b{word}\b", query)}
    terms.update(english for chinese, english in _TERMS.items() if chinese in query)
    explicit = requestedVisual(question)
    wanted = explicit[0] if explicit else "figure" if re.search(r"哪张图|原图|\bfig(?:ure)?\b", query) else "table"
    candidates = []
    for page, chunks in pages.items():
        captions = []
        for chunk in chunks:
            for match in indexedCaptions(chunk["text"]):
                if not match["body"][0].isalnum():
                    continue
                kind = "table" if match["label"].lower() in {"table", "表"} else "figure"
                if kind == wanted and (not explicit or match["number"].casefold() == explicit[1]):
                    captions.append(match.group())
        if captions:
            body = " ".join(chunk["text"].lower() for chunk in chunks)
            captionText = " ".join(captions).lower()
            score = bool(explicit) + sum(3 * (term in captionText) + (term in body) for term in terms)
            if score:
                candidates.append((score, page, chunks))
    if not candidates:
        return ranked
    candidates.sort(key=lambda item: item[0], reverse=True)
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        return ranked
    _, page, chunks = candidates[0]
    # Keep one citation for a page so its caption and adjacent data share a number.
    combined = {**chunks[0], "text": "\n".join(chunk["text"] for chunk in chunks), "score": 1.0}
    return [combined, *[chunk for chunk in ranked if not (
        chunk.get("source_id") == sourceId and chunk.get("page") == page
    )]][:limit]

