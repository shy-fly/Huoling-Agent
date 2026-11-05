"""Extract explicitly paired control and ordered treatment values from prose."""
import re

_NUMBER = r"\d+(?:\.\d+)?"
_LIST = rf"{_NUMBER}(?:(?:,\s*(?:and\s+)?|\s+and\s+){_NUMBER})+"
_PATTERN = re.compile(
    rf"\bthe (?P<metric>[a-zA-Z][a-zA-Z0-9 /-]{{1,55}}?) of [^.]+? "
    rf"(?P<direction>increased|decreased) from (?P<controlValue>{_NUMBER})(?P<unit>%) "
    rf"in the (?P<control>[a-zA-Z0-9 -]{{1,45}}control group) to "
    rf"(?P<values>{_LIST})% when (?P<doses>{_LIST}) "
    rf"(?P<doseUnit>mg|g|mL|L) of (?P<treatment>[a-zA-Z0-9 -]{{1,40}}), respectively, "
    r"(?:were|was) added\.",
    re.I,
)


def readProseContrasts(text: str, page: int) -> list[dict]:
    normalized = " ".join(text.split())
    reports = []
    for index, match in enumerate(_PATTERN.finditer(normalized), 1):
        fields = match.groupdict()
        values = re.findall(_NUMBER, fields["values"])
        doses = re.findall(_NUMBER, fields["doses"])
        if len(values) != len(doses) or len(set(doses)) != len(doses):
            continue
        control = {
            "group": fields["control"], "header": fields["metric"],
            "verifiedValue": fields["controlValue"] + fields["unit"], "column": 1,
        }
        contrasts = [{
            "control": control,
            "treatment": {
                "group": f'{dose} {fields["doseUnit"]} {fields["treatment"]}',
                "header": fields["metric"], "verifiedValue": value + fields["unit"], "column": 1,
            },
            "controlEvidence": {"page": page, "quote": match.group()},
        } for dose, value in zip(doses, values)]
        reports.append({"page": page, "tableIndex": -index, "rotation": 0,
                        "records": [], "contrasts": contrasts, "provenance": "explicit_prose"})
    return reports

