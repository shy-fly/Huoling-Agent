"""Read bounded original-paper sections using the shared PDF source resolver."""
import re

import pymupdf

from app.rag.media_search import pdfForChunk, requestedVisual
from app.rag.visual_evidence import pdfLock
from app.services.evidence_graph import stableId

_HEADINGS = (
    ("references", r"references|bibliography|参考文献"),
    ("methods", r"materials? and methods|methods and materials|methods|methodology|材料与方法|研究方法"),
    ("results", r"results(?: and discussion)?|结果(?:与讨论)?"),
    ("discussion", r"discussion|讨论"),
    ("limitations", r"(?:study )?limitations|研究局限"),
    ("conclusion", r"conclusions?|结论"),
)
_HEADING = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:" + "|".join(f"(?P<{key}>{pattern})" for key, pattern in _HEADINGS) +
    r")\s*[.:：]?$", re.I,
)
_MAX_PAGES = 32


def normalize(text: str) -> str:
    return " ".join(text.split())


def collectAuditEvidence(chunks: list[dict]) -> dict:
    path = pdfForChunk(chunks[0])
    result = {"blocks": [], "pages": {}, "checkedPages": [], "truncated": False, "available": False}
    if path is None:
        return result
    section = "front"
    try:
        if path.stat().st_size > 128 * 1024 * 1024:
            return result
        with pdfLock, pymupdf.open(path) as pdf:
            if not pdf.is_pdf or pdf.needs_pass:
                return result
            for pageNumber in range(1, min(len(pdf), _MAX_PAGES) + 1):
                page = pdf[pageNumber - 1]
                result["pages"][pageNumber] = normalize(page.get_text())
                inScope = False
                for block in page.get_text("blocks", flags=pymupdf.TEXTFLAGS_BLOCKS & ~pymupdf.TEXT_PRESERVE_IMAGES):
                    if block[6] != 0:
                        continue
                    lines = block[4].strip().splitlines()
                    if not lines:
                        continue
                    if heading := _HEADING.fullmatch(lines[0].strip()):
                        section = heading.lastgroup
                        if section == "references":
                            break
                        lines = lines[1:]
                    text = normalize(" ".join(lines))
                    if text:
                        inScope = True
                        result["blocks"].append({"section": section, "page": pageNumber, "text": text})
                if inScope:
                    result["checkedPages"].append(pageNumber)
                if section == "references":
                    break
            result["truncated"] = len(pdf) > _MAX_PAGES and section != "references"
            result["available"] = bool(result["blocks"])
    except (OSError, RuntimeError, ValueError):
        return {**result, "available": False, "blocks": [], "pages": {}, "checkedPages": []}
    return result


def sourceReference(chunks: list[dict], proof: dict, existingId: str | None = None) -> dict:
    paper = chunks[0]
    page, excerpt = proof["page"], proof["text"]
    samePage = [chunk for chunk in chunks if chunk.get("page") == page]
    exact = next((chunk["id"] for chunk in samePage if excerpt in normalize(chunk.get("text") or "")), None)
    ref = {
        "evidenceId": existingId or stableId("audit-evidence", paper["source_id"], page, excerpt),
        "paperId": paper["source_id"], "source": paper["source"], "collection": paper["collection"],
        "page": page, "excerpt": excerpt, "chunkId": exact,
    }
    if samePage and (visual := requestedVisual(excerpt)):
        ref["visual"] = {"kind": visual[0], "number": visual[1], "chunkId": samePage[0]["id"]}
    return ref
