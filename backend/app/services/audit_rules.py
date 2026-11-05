"""Conservative, section-scoped checks for study reporting."""
from dataclasses import dataclass
import re

_METHODS = ("methods",)
_BODY = ("methods", "results", "discussion", "conclusion", "limitations")
_FRONT = ("front", "methods")
_APOSTROPHE = "['’]"
_INDEPENDENT = (r"\b(?:independent|biological)\s+(?:triplicates?|duplicates?|replicates?)\b"
                r"|\b(?:three|two|\d+)\s+(?:independent|biological)\s+(?:replicates?|experiments?)\b")
_TECHNICAL = (r"\btechnical\s+(?:replicates?|duplicates?|triplicates?)\b"
              r"|\b(?:PCR reactions?|assays?)\b.{0,50}\b(?:in triplicate|in duplicate)\b")
_TEST = rf"\b(?:ANOVA|Student{_APOSTROPHE}s t[- ]test|t[- ]test|Mann[-– ]Whitney|Kruskal[-– ]Wallis|linear (?:regression|mixed[- ]effects)|Cox regression)\b"
_STUDY_TYPES = (
    ("review", r"\b(?:this (?:systematic |scoping |narrative )?review (?:summari[sz]es|examines|provides|aims|discusses)|we conducted a systematic review|review article)\b"),
    ("observational", r"\b(?:this (?:cross[- ]sectional|observational|prospective cohort|retrospective cohort) study|we conducted (?:a |an )(?:cohort|case[- ]control|observational) study)\b"),
    ("computational", r"\b(?:this (?:simulation|computational) study|we (?:performed|conducted) (?:a |an )?(?:computational simulation|numerical simulation))\b"),
    ("methodological", r"\b(?:we developed and validated a (?:new |novel )?(?:method|assay|protocol)|this methodological study)\b"),
)


@dataclass(frozen=True)
class Rule:
    id: str
    category: str
    label: str
    sections: tuple[str, ...]
    pattern: str
    studyType: str = ""


_RULES = (
    Rule("objective", "研究问题", "研究目标", _FRONT, r"\b(?:aim of this study|aim of this work|objective of (?:this|the present) study|this study (?:aimed|evaluated|investigated|examined)|we aimed to)\b|研究目的"),
    Rule("control", "研究设计", "对照安排", _METHODS, r"\b(?:control group|untreated controls?|no[- ]treatment control|vehicle control|control (?:reactor|bottle|arm)s?)\b|对照组", "experimental"),
    Rule("treatment", "研究设计", "处理与实验载体", _METHODS, r"\b(?:experimental units?|bottles were configured|reactors? (?:was|were) (?:operated|run|configured)|treatment groups?)\b|实验单位|处理组", "experimental"),
    Rule("independentReplication", "研究设计", "独立或生物重复", _BODY, _INDEPENDENT, "experimental"),
    Rule("randomization", "研究设计", "随机分配说明", _METHODS, r"\b(?:randomly (?:assigned|allocated)|randomi[sz]ation (?:was|procedure|sequence))\b|随机分[组配]", "experimental"),
    Rule("statisticalMethod", "统计报告", "统计方法名称", _METHODS, _TEST),
    Rule("variability", "统计报告", "变异性或不确定性", _BODY, r"\b(?:standard deviation|standard error|confidence intervals?|interquartile range)\b|标准差|置信区间"),
    Rule("measurement", "可重复性", "测量方法", _METHODS, r"\b(?:was|were) (?:measured|determined)\b[^.!?]{0,48}\b(?:using|with|by|via|according to)\b|采用.{0,45}测定"),
    Rule("limitations", "适用边界", "作者明确说明的局限", _BODY, r"\b(?:(?:a |one |the |main |major )?limitation of (?:this|our|the present) study|this study (?:was limited by|has several limitations))\b|本研究的局限"),
    Rule("reviewSelection", "综述方法", "纳入或排除标准", _METHODS, r"\b(?:inclusion criteria|exclusion criteria|eligibility criteria)\b|纳入标准", "review"),
    Rule("confounders", "观察研究", "混杂因素处理", _METHODS, r"\b(?:adjusted for|confounders included|propensity score)\b", "observational"),
    Rule("modelValidation", "计算研究", "模型验证方法", _BODY, r"\b(?:held[- ]out|external validation|validation dataset|cross[- ]validation)\b", "computational"),
    Rule("methodValidation", "方法学研究", "方法验证", _BODY, r"\b(?:validation cohort|reference method|validated against|inter[- ]rater reliability)\b", "methodological"),
)


def findProof(blocks: list[dict], sections: tuple[str, ...], pattern: str) -> dict | None:
    regex = re.compile(pattern, re.I)
    for block in blocks:
        if block["section"] not in sections:
            continue
        if match := regex.search(block["text"]):
            if len(block["text"]) <= 420:
                return block
            start = max(0, match.start() - 100)
            end = min(len(block["text"]), match.end() + 240)
            return {**block, "text": block["text"][start:end].strip()}
    return None


def classifyStudy(blocks: list[dict]) -> tuple[str, dict | None]:
    for kind, pattern in _STUDY_TYPES:
        if proof := findProof(blocks, ("front",), pattern):
            return kind, proof
    if proof := findProof(blocks, _METHODS, r"\b(?:control group|experimental setup|experimental design|pure cultures? (?:was|were)|batch (?:experiments?|reactors?))\b|对照组|实验设计"):
        return "experimental", proof
    return "unknown", None


def checkAuditRules(studyType: str, blocks: list[dict]) -> list[dict]:
    findings = []
    checked = {block["section"] for block in blocks}
    for rule in _RULES:
        if rule.studyType and rule.studyType != studyType:
            continue
        proof = findProof(blocks, rule.sections, rule.pattern)
        status = "reported" if proof else "notReported" if checked.intersection(rule.sections) else "needsReview"
        note = ("原文明确出现相关说明。需结合研究对象核对适用范围。" if proof else
                "已检查范围内未见明确说明。实施情况仍待核实。" if status == "notReported" else
                "缺少可用的对应正文。此项暂无法审计。")
        if rule.id == "independentReplication" and not proof:
            if proof := findProof(blocks, _BODY, _TECHNICAL):
                status, note = "unclear", "原文描述技术操作的重复。独立实验单位和重复数仍待确认。"
        findings.append({"ruleId": rule.id, "category": rule.category, "label": rule.label,
                         "status": status, "observation": note, "proof": proof,
                         "checkedSections": [section for section in rule.sections if section in checked]})
    combined = findProof(blocks, _METHODS, rf"\bANOVA\s*,\s*Student{_APOSTROPHE}s t[- ]test")
    if combined:
        findings.append({
            "ruleId": "testLabelAmbiguity", "category": "统计报告", "label": "统计检验对应关系",
            "status": "potentialIssue", "observation": "同一处同时列出 ANOVA 和 Student’s t 检验。需核对各检验对应的比较与实验单位。",
            "proof": combined, "checkedSections": ["methods"],
        })
    return findings
