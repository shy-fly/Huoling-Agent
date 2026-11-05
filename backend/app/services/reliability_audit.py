"""Assemble reportable facts, bounded gaps and attributable claim assessments."""
import unicodedata
from uuid import uuid4

from app.rag.media_search import pdfForChunk
from app.services.audit_evidence import collectAuditEvidence, sourceReference
from app.services.audit_models import AuditReport, GraphTarget, HypothesisTarget
from app.services.audit_rules import checkAuditRules, classifyStudy, findProof
from app.services.evidence_graph import stableId
from app.services.prose_contrasts import readProseContrasts
from app.services.reported_outcomes import extractReportedOutcomes
from app.services.research_compare_endpoints import loadStudyEndpoints


def _normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def _present(document: dict, page: int, excerpt: str) -> bool:
    return bool(excerpt and page in document["checkedPages"]
                and _normalized(excerpt) in _normalized(document["pages"].get(page, "")))


def _paperClaim(chunks: list[dict], document: dict, hypothesis: HypothesisTarget | None = None) -> dict | None:
    if "results" not in {block["section"] for block in document["blocks"]}:
        return None
    source = chunks[0]
    for block in document["blocks"]:
        if block["section"] != "results" or (hypothesis and block["page"] != hypothesis.page):
            continue
        for table in readProseContrasts(block["text"], block["page"]):
            for pair in table["contrasts"]:
                if not hypothesis or _matchesContrast(hypothesis.claim, pair):
                    break
            else:
                continue
            treatment, control = pair["treatment"], pair["control"]
            return {
                "label": f'{treatment["header"]}：{treatment["group"]} 为 {treatment["verifiedValue"]}，'
                         f'{control["group"]} 为 {control["verifiedValue"]}。',
                "proof": {"page": block["page"], "text": pair["controlEvidence"]["quote"]},
                "conditions": {"处理组": treatment["group"], "对照组": control["group"]},
            }
    if hypothesis:
        return None
    records = extractReportedOutcomes([
        {**source, "page": block["page"], "evidenceText": block["text"]}
        for block in document["blocks"] if block["section"] == "results"
    ])
    if not records and (path := pdfForChunk(source)):
        records = loadStudyEndpoints(path, source["source_id"], source["collection"])
    for record in records:
        if _present(document, record["page"], record["evidenceText"]):
            return {
                "label": f'{record["group"]} · {record["endpoint"]} · {record["value"]} {record["unit"]}',
                "proof": {"page": record["page"], "text": record["evidenceText"]},
                "conditions": {"实验组": record["group"], "指标": record["metric"]},
            }
    return None


def _matchesContrast(claim: str, pair: dict) -> bool:
    return all(_normalized(f'{row["group"]} {row["verifiedValue"]}').casefold() in _normalized(claim).casefold()
               for row in (pair["treatment"], pair["control"]))


def runAudit(target, papers: dict[str, list[dict]], graphItem: dict | None = None) -> AuditReport:
    auditId = stableId("reliability-audit", target.model_dump())
    references = {}
    documents = {}
    studies = []

    def addRef(paperId: str, proof: dict | None, existingId: str | None = None) -> str | None:
        if not proof or not _present(documents[paperId], proof["page"], proof["text"]):
            return None
        ref = sourceReference(papers[paperId], proof, existingId)
        references[ref["evidenceId"]] = ref
        return ref["evidenceId"]

    for paperId, chunks in papers.items():
        document = documents[paperId] = collectAuditEvidence(chunks)
        blocks = document["blocks"]
        sections = list(dict.fromkeys(block["section"] for block in blocks))
        studyType, classification = classifyStudy(blocks)
        status = "completed" if {"methods", "results"}.issubset(sections) else "insufficientScope"
        checks = checkAuditRules(studyType, blocks) if blocks else []
        findings = []
        for item in checks:
            proof = item.pop("proof")
            evidenceId = addRef(paperId, proof)
            if proof and not evidenceId:
                item.update(status="needsReview", observation="该片段尚未通过原页核对。")
            if status == "insufficientScope" and item["status"] == "notReported":
                item.update(status="needsReview", observation="正文范围不足，无法判断报告情况。")
            findings.append({
                **item, "findingId": stableId(auditId, paperId, item["ruleId"]),
                "evidenceIds": [evidenceId] if evidenceId else [],
                "sourcePages": [proof["page"]] if evidenceId else [],
                "uncertainty": "此项核对论文表述。方法适配性需独立判断。" if evidenceId else "同义表述和补充材料仍需人工核对。",
                "requiresHumanReview": item["status"] != "reported",
            })
        objective = next((item["evidenceIds"][0] for item in findings
                          if item["ruleId"] == "objective" and item["evidenceIds"]), None)
        method = addRef(paperId, findProof(blocks, ("methods",), r"\S"))
        studies.append({
            "paperId": paperId, "source": chunks[0]["source"], "studyType": studyType,
            "classificationEvidenceId": addRef(paperId, classification), "objectiveEvidenceId": objective,
            "methodEvidenceId": method, "status": status, "findings": findings,
            "scope": {"sections": sections, "pages": document["checkedPages"], "pageLimit": 32,
                      "truncated": document["truncated"], "supplementsChecked": False,
                      "available": document["available"]},
        })

    claims = []
    limits = ["结论仅对应所引研究对象、处理组与终点。", "统计匹配和因果解释仍需结合实验单位与原始数据复核。"]
    if isinstance(target, GraphTarget) and graphItem:
        evidence = []
        for source in graphItem["evidence"]:
            paperId = source["paperId"]
            if paperId in documents:
                ref = addRef(paperId, {"page": source["page"], "text": source["excerpt"]}, source["id"])
                if ref and ref not in evidence:
                    evidence.append(ref)
        complete = len(evidence) == len({source["id"] for source in graphItem["evidence"]}) and bool(evidence)
        status = "limitedComparability" if complete and graphItem["type"] == "notComparableWith" else (
            "sourceReported" if complete and target.type == "claim" else "needsReview"
        )
        claims.append({"claimId": target.entityId, "statement": graphItem["label"], "status": status,
                       "evidenceIds": evidence, "conditions": graphItem.get("conditions", {}),
                       "limitations": [*graphItem.get("notes", []), *limits]})
    elif isinstance(target, HypothesisTarget):
        matched = _paperClaim(papers[target.paperId], documents[target.paperId], target)
        ref = addRef(target.paperId, matched["proof"]) if matched else None
        claims.append({"claimId": stableId("audit-hypothesis", target.paperId, target.page, target.claim),
                       "statement": target.claim, "status": "needsReview", "evidenceIds": [ref] if ref else [],
                       "conditions": matched["conditions"] if ref else {},
                       "limitations": ["这是待核查的假设。当前规则只审计原文报告项，语义支持程度需人工核对。"]})
    else:
        for paperId, chunks in papers.items():
            if claim := _paperClaim(chunks, documents[paperId]):
                if ref := addRef(paperId, claim["proof"]):
                    claims.append({"claimId": stableId("audit-claim", ref, claim["label"]), "statement": claim["label"],
                                   "status": "sourceReported", "evidenceIds": [ref],
                                   "conditions": claim["conditions"], "limitations": limits})
    return AuditReport.model_validate({
        "auditId": auditId, "traceId": str(uuid4()), "target": target, "studies": studies, "claimAssessments": claims,
        "status": "completed" if all(item["status"] == "completed" for item in studies) else "insufficientScope",
        "references": list(references.values()),
    })
