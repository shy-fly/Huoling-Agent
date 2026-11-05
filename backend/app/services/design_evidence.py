"""Propose draft levels from original evidence with an explicit baseline."""
import re
from decimal import Decimal

from app.services.experiment_design import DesignRequest, Factor

_DOSE = re.compile(r"(?P<value>\d+(?:\.\d+)?) (?P<unit>mg|g|mL|L) (?P<factor>.+)")
_NUMBER = r"\d+(?:\.\d+)?"
_CAPTION = re.compile(
    rf"\bFig(?:ure)?\.? \d+[a-z]?\. (?:Curve|Plot) of (?P<metric>[a-z][a-z -]{{1,60}}?) "
    rf"versus time for (?P<factor>[a-z][a-z0-9 -]{{1,45}}?) in [a-z0-9 -]{{1,65}}? "
    rf"at (?:[a-z -]+? )?concentrations of (?P<baseline>0(?:\.0+)?) "
    rf"\((?:positive|untreated|baseline) control(?: \[[a-z]+\])?\)"
    rf"(?P<doses>(?:(?:, (?:and )?| and ){_NUMBER}){{1,7}}) "
    r"(?P<unit>mg/L|g/L|µg/L|mM|µM|%)\.",
    re.I,
)


def _captionSuggestion(req: DesignRequest, papers: dict) -> tuple[DesignRequest, dict | None]:
    question = " ".join(req.question.casefold().split())
    for sourceId, chunks in papers.items():
        for chunk in chunks:
            for match in _CAPTION.finditer(chunk["evidenceText"]):
                factor, metric, unit = match["factor"], match["metric"], match["unit"]
                if not re.search(rf"\b{re.escape(factor.casefold())}\b", question):
                    continue
                if req.outcome:
                    if req.outcome.casefold() != metric.casefold():
                        continue
                elif not re.search(rf"\b{re.escape(metric.casefold())}\b", question):
                    continue
                doses = [match["baseline"], *re.findall(_NUMBER, match["doses"])]
                if len(set(map(Decimal, doses))) != len(doses):
                    continue
                levels = [f"{dose} {unit}" for dose in doses]
                return req.model_copy(update={
                    "factors": [Factor(name=factor, levels=levels)],
                    "control": {factor: levels[0]}, "outcome": req.outcome or metric,
                }), {
                    "sourceType": "proposed", "sourceId": sourceId, "page": chunk["page"],
                    "excerpt": match.group(),
                    "rationale": "候选水平取自原文图注。适用剂量和安全条件待确认。",
                }
    return req, None


def suggestFromEvidence(req: DesignRequest, result: dict) -> tuple[DesignRequest, dict | None]:
    if req.factors or req.control is not None:
        return req, None
    words = re.findall(r"[a-z]+", req.question.casefold())
    abbreviations = {
        "".join(word[0] for word in words[i:i + n])
        for n in (2, 3, 4) for i in range(len(words) - n + 1)
    }
    for sourceId, tables in result.get("groupTables", {}).items():
        for table in tables:
            if table.get("provenance") != "explicit_prose":
                continue
            pairs = table["contrasts"]
            doses = [_DOSE.fullmatch(pair["treatment"]["group"]) for pair in pairs]
            if not doses or any(dose is None for dose in doses) or len(doses) > 7:
                continue
            factor, unit = doses[0]["factor"], doses[0]["unit"]
            if any((dose["factor"], dose["unit"]) != (factor, unit) for dose in doses):
                continue
            if factor.casefold() not in words and factor.casefold() not in abbreviations and factor not in req.question:
                continue
            control = pairs[0]["control"]
            if control["group"].casefold() != f"no-{factor} control group".casefold():
                continue
            metric = control["header"]
            if req.outcome and req.outcome.casefold() != metric.casefold():
                continue
            baseline = f"0 {unit}"
            levels = list(dict.fromkeys([baseline, *[f'{dose["value"]} {unit}' for dose in doses]]))
            if len(levels) < 2:
                continue
            proposal = {
                "sourceType": "proposed", "sourceId": sourceId, "page": table["page"],
                "excerpt": pairs[0]["controlEvidence"]["quote"],
                "rationale": "候选剂量来自原文对照。需确认体系、设备与安全条件后再使用。",
            }
            return req.model_copy(update={
                "factors": [Factor(name=factor, levels=levels)], "control": {factor: baseline},
                "outcome": req.outcome or metric,
            }), proposal
    return _captionSuggestion(req, result.get("papers", {}))

