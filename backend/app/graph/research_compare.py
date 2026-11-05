"""Local retrieval and provenance stages for Research Compare."""
from dataclasses import asdict
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict

import pymupdf
from langgraph.graph import END, START, StateGraph
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.rag.paper_page_search import supplementPaperPages
from app.rag.retriever import get_all_chunks
from app.rag.experiment_retrieval import retrieveExperimentEvidence
from app.services.research_compare_endpoints import compareStudyEndpoints, loadStudyEndpoints
from app.services.experiment_contrast import verifyContrast
from app.services.prose_contrasts import readProseContrasts
from app.services.group_table_evidence import readGroupTables
from app.services.reported_outcomes import extractReportedOutcomes
from app.services.research_compare_tables import extractPdfPhaseTables
from app.services.research_compare_extraction import validateExperiments
from app.services.research_compare_selection import _REFERENCE_HEADING, selectPapers


class CompareState(TypedDict, total=False):
    question: str
    paperLimit: int
    includeIds: list[str]
    excludeIds: list[str]
    priorityPages: dict[str, list[int]]
    includePageSiblings: bool
    rankedChunks: list[dict]
    retrievedPaperCount: int
    selectedPaperCount: int
    verifiedPaperCount: int
    papers: dict[str, list[dict]]
    status: str
    dimensions: list[str]
    groupTables: dict[str, list[dict]]
    tableRecords: dict[str, list[dict]]
    thresholdComparison: dict
    experimentContrasts: dict[str, list[dict]]
    experimentRecords: dict[str, list[dict]]
    rejectedObservationCount: int


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _verifyPaper(root: Path, chunks: list[dict]) -> list[dict]:
    source = chunks[0]["source"]
    collection = chunks[0].get("collection", "")
    if not collection.startswith("literature_") or Path(source).name != source:
        return []
    path = (root / collection.removeprefix("literature_") / source).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return []
    try:
        reader = PdfReader(path)
        pages = [page.extract_text() or "" for page in reader.pages]
        with pymupdf.open(path) as document:
            alternate = [page.get_text() for page in document]
    except (OSError, PdfReadError, ValueError, RuntimeError):
        return []
    referenceStart = next(
        (index for index, (primary, fallback) in enumerate(zip(pages, alternate), 1)
         if _REFERENCE_HEADING.search(primary) or _REFERENCE_HEADING.search(fallback)),
        len(pages) + 1,
    )
    verified = []
    for chunk in chunks:
        page = chunk["page"]
        if chunk["source"] != source or chunk.get("collection") != collection:
            continue
        if not 1 <= page <= len(pages) or page >= referenceStart:
            continue
        quote = _normalize(chunk["text"])
        if quote and any(quote in _normalize(text) for text in (pages[page - 1], alternate[page - 1])):
            verified.append({**chunk, "evidenceText": quote})
    return verified


def buildResearchCompareGraph(
    corpusRoot: Path,
    search: Callable[..., list[dict]] = retrieveExperimentEvidence,
    *,
    expandPages: bool | None = None,
    extractPaper: Callable[[str, str, list[dict]], list[object]] | None = None,
):
    root = corpusRoot.resolve()

    def retrieveCandidates(state: CompareState) -> dict:
        paperLimit = state.get("paperLimit", 3)
        if not 2 <= paperLimit <= 10:
            raise ValueError("paperLimit must be between 2 and 10")
        ranked = search(state["question"], top_k=max(24, paperLimit * 8))
        return {"rankedChunks": ranked, "retrievedPaperCount": len({
            chunk["source_id"] for chunk in ranked if chunk.get("source_id")
        })}

    def verifyCandidates(state: CompareState) -> dict:
        ranked = state["rankedChunks"]
        included = state.get("includeIds")
        priorityPages = state.get("priorityPages", {})
        expand = (search is retrieveExperimentEvidence) if expandPages is None else expandPages
        indexed = get_all_chunks() if priorityPages or (expand and ranked) else []
        if priorityPages:
            pinned = {
                chunk["id"]: chunk for chunk in indexed
                if chunk["page"] in priorityPages.get(chunk["source_id"], ())
            }
            ranked = [*pinned.values(), *(chunk for chunk in ranked if chunk["id"] not in pinned)]
        selected = selectPapers(
            ranked, len(ranked),
            includeIds=set(included) if included is not None else None,
            excludeIds=set(state.get("excludeIds", [])),
        )
        papers = {}
        for sourceId, chunks in selected.items():
            candidates = supplementPaperPages(
                state["question"], chunks, indexed if expand else [],
                includePageSiblings=state.get("includePageSiblings", False),
            )
            evidence = _verifyPaper(root, candidates)
            if evidence:
                papers[sourceId] = evidence
            if len(papers) >= state.get("paperLimit", 3):
                break
        return {
            "selectedPaperCount": len(selected),
            "verifiedPaperCount": len(papers),
            "papers": papers,
            "status": "evidence_verified" if len(papers) >= 2 else "insufficient_evidence",
        }

    def extractExperiments(state: CompareState) -> dict:
        records = {}
        rejectedCount = 0
        contrasts = {}
        for sourceId, evidence in state["papers"].items():
            proposals = extractPaper(state["question"], sourceId, [dict(chunk) for chunk in evidence])
            contrastProposals = [item for item in proposals if isinstance(item, dict) and "treatment" in item]
            contrasts[sourceId] = [verified for item in contrastProposals if (verified := verifyContrast(item, evidence))]
            observations, rejected = validateExperiments(
                sourceId, evidence, [item for item in proposals if item not in contrastProposals],
            )
            rejected += len(contrastProposals) - len(contrasts[sourceId])
            records[sourceId] = [observation.model_dump() for observation in observations]
            rejectedCount += rejected
        return {"experimentRecords": records, "experimentContrasts": contrasts, "rejectedObservationCount": rejectedCount}

    def extractTables(state: CompareState) -> dict:
        dimensions = set(state.get("dimensions", []))
        records = {}
        endpoints = []
        groupTables = {}
        ammoniaQuestion = any(term in state["question"].lower() for term in ("氨", "ammonia"))
        for sourceId, evidence in state["papers"].items():
            chunk = evidence[0]
            path = (root / chunk["collection"].removeprefix("literature_") / chunk["source"]).resolve()
            entries = []
            if dimensions:
                for page in sorted({item["page"] for item in evidence}):
                    entries.extend(asdict(item) for item in extractPdfPhaseTables(path, page, dimensions))
            groupTables[sourceId] = []
            with pymupdf.open(path) as pdf:
                for page in sorted({item["page"] for item in evidence}):
                    groupTables[sourceId].extend(readGroupTables(pdf, page, evidence))
                    groupTables[sourceId].extend(readProseContrasts(pdf[page - 1].get_text(), page))
                    endpoints.extend(extractReportedOutcomes([{
                        **chunk, "page": page, "evidenceText": pdf[page - 1].get_text(),
                    }]))
            if ammoniaQuestion:
                endpoints.extend(loadStudyEndpoints(path, sourceId, chunk["collection"]))
            records[sourceId] = entries
        return {"tableRecords": records, "groupTables": groupTables, "thresholdComparison": compareStudyEndpoints(endpoints)}

    graph = StateGraph(CompareState)
    graph.add_node("retrieve_candidates", retrieveCandidates)
    graph.add_node("verify_candidates", verifyCandidates)
    graph.add_edge(START, "retrieve_candidates")
    graph.add_edge("retrieve_candidates", "verify_candidates")
    graph.add_node("extract_tables", extractTables)
    graph.add_edge("verify_candidates", "extract_tables")
    if extractPaper is None:
        graph.add_edge("extract_tables", END)
    else:
        graph.add_node("extract_experiments", extractExperiments)
        graph.add_edge("extract_tables", "extract_experiments")
        graph.add_edge("extract_experiments", END)
    return graph.compile()

