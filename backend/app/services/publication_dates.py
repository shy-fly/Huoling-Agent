"""Conservative publication metadata from the original first-page imprint."""
import re

import pymupdf

from app.rag.media_search import pdfForChunk
from app.rag.visual_evidence import pdfLock

_YEAR = r"(?:18|19|20)\d{2}"
_ISSUE = (
    re.compile(rf"^[A-Z][A-Za-z .,&:–-]{{4,110}}\s+\d{{1,5}}(?:\(\d+\))?\s+\(({_YEAR})\)\s+[a-z]?\d", re.I),
    re.compile(rf"^[A-Z][A-Za-z .,&:–-]{{4,110}}\s+\(({_YEAR})\)\s+\d{{1,5}}:\s*\d", re.I),
    re.compile(rf"^[A-Z][A-Za-z .,&:–-]{{4,110}},\s+\d{{1,5}},\s+({_YEAR}),\s+[a-z]*\d", re.I),
    re.compile(rf"^[A-Z][A-Za-z .,&:–-]{{4,110}},\s+(?:[A-Za-z]+\.?\s+)?({_YEAR}),\s*\d{{1,5}},\s*\d", re.I),
    re.compile(rf"^[A-Z][A-Za-z .,&:–-]{{4,110}},\s+[A-Za-z]+\.?\s+({_YEAR}),\s*p\.\s*\d", re.I),
)
_ONLINE = re.compile(rf"(?:available online|published online|advance access publication date)\s*[: ]\s*.{{0,38}}?\b({_YEAR})\b", re.I)
_PUBLISHED = re.compile(rf"^(?:Open Access Article\.\s*)?Published(?: on|:)\s*.{{0,35}}?\b({_YEAR})\b", re.I)
_DOI = re.compile(r"(?:\bdoi\s*:\s*|https?://(?:dx\.)?doi\.org/)(10\.\d{4,9}/[-._;()/:a-z0-9]+)", re.I)
_PREPRINT = re.compile(r"^(?:arxiv:\s*\d|(?:bioRxiv|medRxiv) preprint|preprint\b)", re.I)


def publicationFromFront(text: str) -> dict:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    first = lines[:65] + lines[-18:]
    doiMatch = _DOI.search("\n".join(lines[:120]))
    online = next(((int(match[1]), line) for line in lines[:150] if (match := _ONLINE.search(line))), (None, None))
    result = {"year": None, "kind": "unknown", "excerpt": None, "page": 1,
              "doi": doiMatch[1].rstrip(".;,").casefold() if doiMatch else None,
              "onlineYear": online[0], "onlineExcerpt": online[1]}
    if any(_PREPRINT.match(line) for line in first[:24]):
        return {**result, "kind": "preprint"}
    dates = {}
    for line in first:
        for pattern in _ISSUE:
            if match := pattern.match(line):
                dates.setdefault(int(match[1]), line)
    if len(dates) == 1:
        year, excerpt = next(iter(dates.items()))
        return {**result, "year": year, "kind": "issue", "excerpt": excerpt}
    if len(dates) > 1:
        return {**result, "kind": "conflict"}
    published = {int(match[1]): line for line in lines[:180] if (match := _PUBLISHED.match(line))}
    if len(published) == 1:
        year, excerpt = next(iter(published.items()))
        return {**result, "year": year, "kind": "publisherPublished", "excerpt": excerpt}
    return {**result, "kind": "conflict" if published else "unknown"}


def readPublication(chunk: dict) -> dict:
    path = pdfForChunk(chunk)
    if path:
        try:
            if path.stat().st_size <= 128 * 1024 * 1024:
                with pdfLock, pymupdf.open(path) as pdf:
                    if pdf.is_pdf and len(pdf) and not pdf.needs_pass:
                        return publicationFromFront(pdf[0].get_text())
        except (OSError, RuntimeError, ValueError):
            return publicationFromFront("")
    return publicationFromFront("")
