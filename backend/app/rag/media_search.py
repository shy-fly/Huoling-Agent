"""Link indexed figures and tables to RAG papers and original text chunks."""
import re
from pathlib import Path

from app.config import BACKEND_ROOT, settings
from app.rag.media_index import indexPage
from app.rag.retriever import get_all_chunks, retrieve
from app.rag.visual_evidence import indexedCaptions

INDEX_ROOT = BACKEND_ROOT / "data" / "media"
COLLECTIONS = {"literature_inhibition", "literature_theory", "literature_engineering"}
_VISUAL = re.compile(r"(?P<label>fig(?:ure)?\.?|table|图|表)\s*(?P<number>s?\d+[a-z]?(?:\([a-z]\))?)(?![\w(])", re.I)
NAMED_PAPER = re.compile(r"(?<!\w)([a-z]{2,30})\s*(?:等|et\s+al\.?)?\s*[（(]?\s*((?:19|20)\d{2})", re.I)
_STOP = set("show shows showing find with does about what figure figures table tables paper study related from this that and the for of in to a an on during effect effects".split())


def pdfForChunk(chunk: dict) -> Path | None:
    collection, source = chunk.get("collection"), chunk.get("source") or ""
    if collection not in COLLECTIONS or Path(source).name != source or Path(source).suffix.lower() != ".pdf":
        return None
    root = (settings.knowledge_path / "literature_corpus").resolve()
    folder = root / collection.removeprefix("literature_")
    path = (folder / source).resolve()
    return path if path.is_relative_to(folder) and path.is_file() else None


def requestedVisual(question: str) -> tuple[str, str] | None:
    matches = {
        ("table" if match["label"].casefold() in {"表", "table"} else "figure", match["number"].casefold())
        for match in _VISUAL.finditer(question)
    }
    return next(iter(matches)) if len(matches) == 1 else None


def explicitLocalVisual(question: str, chunks: list[dict]) -> tuple[int, dict] | None:
    named, requested = NAMED_PAPER.search(question), requestedVisual(question)
    if not named or not requested:
        return None
    prefix = f"{named[1]}-{named[2]}-".casefold()
    found = {}
    for index, chunk in enumerate(chunks, 1):
        if not chunk.get("page") or not (chunk.get("source") or "").casefold().startswith(prefix):
            continue
        key = (chunk["source_id"], chunk["page"])
        if key in found or not (path := pdfForChunk(chunk)):
            continue
        for item in indexPage(INDEX_ROOT, path, *key)["visuals"]:
            if (item["kind"], item["number"].casefold()) == requested:
                found[key] = (index, item)
    return next(iter(found.values())) if len(found) == 1 else None


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z0-9-]{1,}|[\u4e00-\u9fff]{2,}", text.casefold())) - _STOP


def mediaPayload(item: dict, pageChunks: list[dict]) -> dict:
    first = pageChunks[0]
    mentions = [
        chunk for chunk in pageChunks
        if any(
            (item["kind"], item["number"].casefold()) == requestedVisual(line)
            and " ".join(line.split()) != item["caption"]
            for line in (chunk.get("text") or "").splitlines()
        )
    ]
    siblings = mentions or pageChunks
    return {
        **item, "paperId": first["source_id"], "chunkId": first["id"], "source": first["source"],
        "title": first.get("title") or first["source"], "collection": first["collection"],
        "page": first["page"], "pageIndex": first["page"] - 1,
        "relatedChunks": [
            {"chunkId": chunk["id"], "page": chunk["page"], "relation": "samePage",
             "excerpt": " ".join((chunk.get("text") or "").split())[:650]}
            for chunk in siblings[:3] if chunk.get("text")
        ],
    }


def searchMedia(root: Path, question: str, kind: str | None, number: str | None, paperIds: list[str], limit: int) -> dict:
    ranked = retrieve(question, top_k=28, collections=sorted(COLLECTIONS))
    named = NAMED_PAPER.search(question)
    chunks = get_all_chunks()
    if named:
        prefix = f"{named[1]}-{named[2]}-".casefold()
        namedIds = {chunk["source_id"] for chunk in chunks if (chunk.get("source") or "").casefold().startswith(prefix)}
        if namedIds:
            paperIds = [sourceId for sourceId in paperIds if sourceId in namedIds] if paperIds else sorted(namedIds)
            if not paperIds:
                return {"items": [], "scannedPages": 0, "reviewPages": 0, "failedPages": 0}
    papers = paperIds or list(dict.fromkeys(c["source_id"] for c in ranked if c.get("page")))[:6]
    pages: dict[tuple[str, int], list[dict]] = {}
    for chunk in chunks:
        if chunk.get("source_id") in papers and chunk.get("page"):
            pages.setdefault((chunk["source_id"], chunk["page"]), []).append(chunk)
    exact = requestedVisual(question)
    if exact and not (kind or number):
        kind, number = exact
    queryTerms = _terms(question)
    focusTerms = _terms(re.split(r"\s+in\s+", question, maxsplit=1, flags=re.I)[0])
    ranks = {(c["source_id"], c["page"]): c.get("score", 0) for c in ranked}
    candidates = []
    for key, pageChunks in pages.items():
        body = "\n".join(c.get("text") or "" for c in pageChunks)
        captions = []
        for caption in indexedCaptions(body):
            label = "table" if caption["label"].casefold() in {"表", "table"} else "figure"
            if (not kind or label == kind) and (not number or caption["number"].casefold() == number.casefold()):
                captions.append(caption["body"])
        captionScore = max((len(_terms(caption) & queryTerms) for caption in captions), default=0)
        if key in ranks or captions:
            candidates.append((bool(captions and number), captionScore, ranks.get(key, 0), key))
    result = {"items": [], "scannedPages": 0, "reviewPages": 0, "failedPages": 0}
    scored = []
    for _, _, rank, key in sorted(candidates, reverse=True)[:20]:
        pageChunks = pages[key]
        path = pdfForChunk(pageChunks[0])
        if path is None:
            result["failedPages"] += 1
            continue
        indexed = indexPage(root, path, key[0], key[1])
        result["scannedPages"] += 1
        result["reviewPages"] += indexed["status"] == "needsReview"
        result["failedPages"] += indexed["status"] == "failed"
        for item in indexed["visuals"]:
            if kind and item["kind"] != kind or number and item["number"].casefold() != number.casefold():
                continue
            captionTerms = _terms(item["caption"])
            focusHits = len(captionTerms & focusTerms)
            if not number and len(focusTerms) >= 2 and not focusHits:
                visualKey = (item["kind"], item["number"].casefold())
                if not any(requestedVisual(line) == visualKey and _terms(line) & focusTerms
                           for chunk in pageChunks for line in (chunk.get("text") or "").splitlines()):
                    continue
            captionHits = len(captionTerms & queryTerms)
            bodyHits = max(len(_terms(c.get("text") or "") & queryTerms) for c in pageChunks)
            titleHits = len(_terms(pageChunks[0].get("title") or path.stem) & queryTerms)
            if not (captionHits or bodyHits or titleHits or rank or number):
                continue
            score = focusHits * 4 + captionHits * 3 + bodyHits + titleHits * 0.5 + rank
            scored.append((score, mediaPayload(item, pageChunks)))
    result["items"] = [item for _, item in sorted(scored, key=lambda pair: -pair[0])[:limit]]
    return result
