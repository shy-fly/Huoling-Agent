"""Conservative extraction of explicitly reported experimental outcomes."""
import re
import unicodedata

_THRESHOLD = re.compile(
    r"\bthe (?P<metric>[a-z][a-z -]+? acid) concentration of (?P<value>\d+(?:\.\d+)?) "
    r"(?P<unit>mM|µM|mg/L|g/L) resulting in (?P<percent>\d+)% inhibition in our experiments",
    re.I,
)
_NULL = re.compile(
    r"the tested (?P<metric>[a-z ]+?) levels had no significant effect "
    r"\(P\s*>\s*(?P<p>0\.\d+)\) on (?P<endpoint>[a-z ]+?) for\s*(?P<group>[^()]+?) \(",
    re.I,
)


def extractReportedOutcomes(evidence: list[dict]) -> list[dict]:
    records = []
    for chunk in evidence:
        quote = " ".join(unicodedata.normalize("NFKC", chunk["evidenceText"]).split())
        for match in _THRESHOLD.finditer(quote):
            fields = match.groupdict()
            metric = fields["metric"].removeprefix("the ")
            records.append(_record(chunk, match.group(), metric, "未在引句中报告",
                                   f'{fields["percent"]}% 抑制', fields["value"], fields["unit"], "exact"))
        for match in _NULL.finditer(quote):
            fields = match.groupdict()
            records.append(_record(chunk, match.group()[:-2], fields["metric"], fields["group"],
                                   fields["endpoint"], f'P > {fields["p"]}', "无量纲", "no_significant_effect"))
    return records


def _record(chunk, quote, metric, group, endpoint, value, unit, qualifier):
    return {
        "sourceId": chunk["source_id"], "source": chunk["source"], "collection": chunk["collection"],
        "page": chunk["page"], "evidenceText": quote, "group": group, "metric": metric,
        "endpoint": endpoint, "value": value, "unit": unit, "qualifier": qualifier,
        "provenance": "automatic_explicit_result",
    }


def reviewReportedOutcomes(claim: str, records: list[dict]) -> list[dict]:
    normalized = claim.casefold()
    if not re.search(r"\b(?:always|necessarily)\b.*\b(?:reduce|decrease|inhibit)\b", normalized):
        return []
    evidence = []
    for record in records:
        metric = record["metric"].casefold()
        endpoint = record["endpoint"].casefold()
        if metric not in normalized or endpoint not in normalized:
            continue
        if record["qualifier"] == "no_significant_effect":
            evidence.append({**record, "classification": "conditional", "reason": (
                f'{record["group"]}：在作者测试范围内，{record["metric"]} 对 '
                f'{record["endpoint"]} 未见显著影响（{record["value"]}）。'
                "这项结果限定了可观察到的效应，仍无法排除较小效应。"
            )})
    return evidence

