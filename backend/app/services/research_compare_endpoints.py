"""Curated original-study endpoints, rechecked against local PDF text at runtime."""
from itertools import combinations
from pathlib import Path
import unicodedata

import pymupdf


def _text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


# Source-specific annotations. A matching filename alone never admits a record.
_ENDPOINTS = {
    "Yang-2018-Effect-of-ammonia-on-methane-produc.pdf": [
        (4, "In this research, a 50% inhibition (IC50) of MP occurred with TAN higher than 4 g NH4þ-N/L under mesophilic condition but did not occur within experimental range under thermophilic condition (Table 1).",
         {"group": "中温组", "metric": "TAN", "unit": "g NH₄⁺-N/L", "endpoint": "甲烷产量 IC₅₀", "value": "> 4", "qualifier": "lower_bound"}),
        (4, "In this research, a 50% inhibition (IC50) of MP occurred with TAN higher than 4 g NH4þ-N/L under mesophilic condition but did not occur within experimental range under thermophilic condition (Table 1).",
         {"group": "高温组", "metric": "TAN", "unit": "g NH₄⁺-N/L", "endpoint": "甲烷产量 IC₅₀", "value": "实验范围内未达到", "qualifier": "not_reached"}),
    ],
    "Tian-2018-Effect-of-different-ammonia-sources.pdf": [
        (4, "To be specific, up to threefold longer lag phase periods were in urea reactors compared to NH4Cl reactors (Table 3).",
         {"group": "尿素与氯化铵处理", "metric": "产甲烷滞后期", "unit": "倍（无量纲）", "endpoint": "滞后期相对长度", "value": "最长 3 倍", "qualifier": "relative_response"}),
    ],
}


def loadStudyEndpoints(path: Path, sourceId: str, collection: str) -> list[dict]:
    annotations = _ENDPOINTS.get(path.name)
    if not annotations:
        return []
    records = []
    with pymupdf.open(path) as pdf:
        for page, anchor, fields in annotations:
            if page <= len(pdf) and _text(anchor) in _text(pdf[page - 1].get_text()):
                records.append({**fields, "sourceId": sourceId, "source": path.name,
                                "collection": collection, "page": page, "evidenceText": anchor,
                                "provenance": "curated_pdf_anchor"})
    return records


def compareStudyEndpoints(records: list[dict]) -> dict:
    comparable = []
    incompatible = []
    for left, right in combinations(records, 2):
        if left["sourceId"] == right["sourceId"]:
            continue
        differences = [
            label for key, label in (("metric", "指标"), ("unit", "单位或质量口径"), ("endpoint", "响应终点"))
            if left[key] != right[key]
        ]
        if not differences and (left["qualifier"] != "exact" or right["qualifier"] != "exact"):
            differences.append("至少一项只有边界、未达到终点或报告相对响应")
        pair = {"left": left, "right": right, "reasons": differences}
        (incompatible if differences else comparable).append(pair)
    names = {record["source"] for record in records}
    explanations = []
    if _ENDPOINTS.keys() <= names:
        explanations = [
            "两篇研究的响应终点不同。甲烷产量降至一半和产甲烷延迟变长衡量的是不同现象。",
            "Tian 在相同氨水平下观察到尿素处理的滞后期更长。氨来源可能影响实验响应，但这不能解释两篇研究间的阈值差异。",
            "Yang 的中温与高温结果来自不同实验组。现有记录不足以将温度、pH、微生物组成或驯化的作用单独分离。",
        ]
    return {"records": records, "comparable": comparable, "incompatible": incompatible, "explanations": explanations}

