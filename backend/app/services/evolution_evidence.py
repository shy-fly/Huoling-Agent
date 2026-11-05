"""Reuse audit and comparison evidence adapters for timeline projection."""
import unicodedata

from app.rag.media_search import pdfForChunk
from app.services.audit_evidence import sourceReference
from app.services.audit_rules import checkAuditRules, classifyStudy
from app.services.prose_contrasts import readProseContrasts
from app.services.reported_outcomes import extractReportedOutcomes
from app.services.research_compare_endpoints import loadStudyEndpoints


def recheckEvolutionEvidence(graph: dict, indexed: dict, documents: dict) -> tuple[dict, dict]:
    studies = {}

    def compact(text: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", text).split())

    for paperId, document in documents.items():
        chunks = indexed[paperId]
        studyType, _ = classifyStudy(document["blocks"])
        checks = checkAuditRules(studyType, document["blocks"])
        measurement = next((check["proof"] for check in checks if check["ruleId"] == "measurement"), None)
        studies[paperId] = {"studyType": studyType, "reference": sourceReference(chunks, measurement) if measurement else None}

    def verified(ref):
        paperId = ref["paperId"]
        if paperId not in documents or studies[paperId]["studyType"] == "review":
            return False
        doc = documents[paperId]
        excerpt = compact(ref["excerpt"])
        return bool(excerpt and ref["source"] == indexed[paperId][0]["source"] and
                    ref["collection"] == indexed[paperId][0]["collection"] and
                    ref["page"] in doc["checkedPages"] and excerpt in compact(doc["pages"].get(ref["page"], "")))

    edges = [edge for edge in graph["edges"] if edge["evidence"] and all(verified(ref) for ref in edge["evidence"])]
    return {**graph, "edges": edges}, studies


def outcomePages(chunks: list[dict], document: dict) -> list[int]:
    source = chunks[0]
    pages = []
    for block in document["blocks"]:
        if block["section"] == "results" and block["page"] not in pages:
            if readProseContrasts(block["text"], block["page"]) or extractReportedOutcomes([
                {**source, "page": block["page"], "evidenceText": block["text"]},
            ]):
                pages.append(block["page"])
    if document["available"] and (path := pdfForChunk(source)):
        pages.extend(item["page"] for item in loadStudyEndpoints(path, source["source_id"], source["collection"]))
    return list(dict.fromkeys(pages))[:3]

