"""Deterministic coverage of PDF-backed, co-observed experiment conditions."""
from collections import Counter
from decimal import Decimal, InvalidOperation
from itertools import product

from pydantic import BaseModel, Field, model_validator


class CoverageAxis(BaseModel):
    field: str = Field(min_length=1, max_length=60)
    unit: str = Field(default="", max_length=30)
    edges: list[Decimal] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validateEdges(self):
        if self.edges and (len(self.edges) < 2 or not self.unit
                           or any(not edge.is_finite() for edge in self.edges)
                           or any(a >= b for a, b in zip(self.edges, self.edges[1:]))):
            raise ValueError("Numeric axes require a unit and strictly increasing finite edges")
        return self

    def label(self, raw: str, unit: str) -> str | None:
        if unit != self.unit:
            return None
        if not self.edges:
            return raw
        try:
            value = Decimal(raw)
        except InvalidOperation:
            return None
        if not value.is_finite():
            return None
        for a, b in zip(self.edges, self.edges[1:]):
            if a <= value < b:
                return f"[{a}, {b})"
        return None


def collectPhaseRecords(result: dict) -> list[dict]:
    records = {}
    for sourceId, cells in result["tableRecords"].items():
        source = result["papers"][sourceId][0]
        for cell in cells:
            observation = cell["observation"]
            key = (sourceId, cell["page"], cell["tableIndex"], observation["regime"],
                   observation["group"], observation["phase"])
            record = records.setdefault(key, {
                "id": ":".join(map(str, key)), "sourceId": sourceId, "source": source["source"],
                "collection": source["collection"], "page": cell["page"], "group": observation["group"],
                "fields": {"regime": [observation["regime"], ""], "phase": [observation["phase"], ""]},
            })
            field = observation["dimension"]
            value = [observation["rawValue"], observation["rawUnit"]]
            existing = record["fields"].setdefault(field, value)
            if existing != value:
                record["fields"][field] = None
    return list(records.values())


def buildCoverage(records: list[dict], xAxis: CoverageAxis, yAxis: CoverageAxis, sparseLimit: int) -> dict:
    missing = Counter()
    unmatched = Counter()
    counts: dict[tuple[str, str], list[dict]] = {}
    labels = [set(), set()]
    for record in records:
        coordinates = []
        for index, axis in enumerate((xAxis, yAxis)):
            value = record["fields"].get(axis.field)
            label = axis.label(*value) if value else None
            if not value:
                missing[axis.field] += 1
            elif label is None:
                unmatched[axis.field] += 1
            else:
                labels[index].add(label)
            coordinates.append(label)
        x, y = coordinates
        if x is not None and y is not None:
            counts.setdefault((x, y), []).append(record)
    axes = [
        [f"[{a}, {b})" for a, b in zip(axis.edges, axis.edges[1:])] if axis.edges else sorted(labels[index])
        for index, axis in enumerate((xAxis, yAxis))
    ]
    matrix = []
    if counts:
        for x, y in product(*axes):
            items = counts.get((x, y), [])
            ids = sorted({record["sourceId"] for record in items})
            matrix.append({"x": x, "y": y, "paperCount": len(ids), "recordCount": len(items),
                           "paperIds": ids, "recordIds": [record["id"] for record in items],
                           "state": "no_valid_records" if not ids else "sparse" if len(ids) <= sparseLimit else "observed"})
    return {"labels": axes, "coverageMatrix": matrix, "missingData": dict(missing),
            "unmatchedData": dict(unmatched), "unclassifiedCount": len(records) - sum(map(len, counts.values()))}

