"""Group ranked research evidence by its indexed paper identity."""
import re

_REFERENCE_HEADING = re.compile(
    r"^\s*(?:\d+\.?\s+)?(?:references|bibliography|\u53c2\u8003\u6587\u732e)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def selectPapers(
    rankedChunks: list[dict],
    paperLimit: int,
    *,
    includeIds: set[str] | None = None,
    excludeIds: set[str] | None = None,
) -> dict[str, list[dict]]:
    """Keep ranked PDF candidates, without treating bibliography as evidence."""
    papers: dict[str, list[dict]] = {}
    for chunk in rankedChunks:
        sourceId = chunk.get("source_id")
        source = chunk.get("source") or ""
        page = chunk.get("page")
        body = chunk.get("text") or ""
        section = chunk.get("section") or ""
        if not sourceId or not source.lower().endswith(".pdf") or not page or page < 1:
            continue
        if (includeIds is not None and sourceId not in includeIds) or sourceId in (excludeIds or ()):
            continue
        if not body.strip() or _REFERENCE_HEADING.search(body) or _REFERENCE_HEADING.fullmatch(section):
            continue
        if sourceId not in papers and len(papers) >= paperLimit:
            continue
        papers.setdefault(sourceId, []).append(chunk)
    return papers

