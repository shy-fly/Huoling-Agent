"""Find complementary methods and results pages within an already retrieved paper."""
import re

_METHOD = re.compile(r"(?im)^\s*(?:\d+(?:\.\d+)*\.?\s+)?(?:materials and methods|experimental (?:design|setup)|methods)\b")
_RESULT = re.compile(r"(?im)^\s*(?:\d+(?:\.\d+)*\.?\s+)?results(?: and discussion)?\b")
_TABLE = re.compile(r"(?im)^\s*table\s+\d+[a-z]?(?:[.: ]|$)")
_REFERENCE = re.compile(r"(?im)^\s*(?:references|bibliography)\s*$")


def supplementPaperPages(
    question: str, ranked: list[dict], indexed: list[dict], *, includePageSiblings: bool = False,
) -> list[dict]:
    if not ranked:
        return ranked
    sourceId = ranked[0]["source_id"]
    terms = set(re.findall(r"[a-z][a-z-]{3,}", question.lower())) - {
        "what", "does", "always", "compare", "under", "with", "from", "that", "this",
    }
    seen = {chunk["page"] for chunk in ranked}
    pages: dict[int, list[dict]] = {}
    for chunk in indexed:
        if chunk.get("source_id") == sourceId and chunk.get("page"):
            pages.setdefault(chunk["page"], []).append(chunk)
    referenceStart = min(
        (page for page, chunks in pages.items() if any(_REFERENCE.search(chunk["text"]) for chunk in chunks)),
        default=float("inf"),
    )
    added = []
    for role in (_METHOD, _RESULT, _TABLE):
        candidates = []
        for page, chunks in pages.items():
            if page in seen or page >= referenceStart:
                continue
            body = "\n".join(chunk["text"] for chunk in chunks)
            if role.search(body):
                words = set(re.findall(r"[a-z][a-z-]{3,}", body.lower()))
                candidates.append((len(terms & words), -page, chunks))
        if candidates:
            _, negativePage, chunks = max(candidates, key=lambda item: item[:2])
            seen.add(-negativePage)
            added.extend(chunks)
    if includePageSiblings:
        present = {chunk["id"] for chunk in [*ranked, *added]}
        added.extend(
            chunk for page, chunks in pages.items() if page in seen and page < referenceStart
            for chunk in chunks if chunk["id"] not in present
        )
    return [*ranked, *added]

