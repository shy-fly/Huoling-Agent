"""Read numeric cells from PDF tables with explicit phase and group headers."""
from dataclasses import dataclass
from pathlib import Path
import re

import pymupdf
from app.rag.table_cells import cellText as _cellText

_PHASE = re.compile(r"Phase\s+\d+", re.IGNORECASE)
_GROUP = re.compile(r"[A-Za-z]+\d+")
_METRIC = re.compile(r"(.+?)\s*\(([^()]+)\)")
_NUMBER = re.compile(r"[+-]?\d+(?:\.\d+)?")


@dataclass(frozen=True)
class PhaseObservation:
    regime: str
    group: str
    phase: str
    dimension: str
    rawValue: str
    rawUnit: str
    row: int
    column: int


@dataclass(frozen=True)
class PdfTableObservation:
    observation: PhaseObservation
    page: int
    tableIndex: int
    cellBox: tuple[float, float, float, float]


def extractPhaseRows(rows: list[list[str]], dimensions: set[str]) -> list[PhaseObservation]:
    if not rows or len(rows[0]) < 2:
        return []
    phases = rows[0][1:]
    if len(set(phases)) != len(phases) or not all(_PHASE.fullmatch(phase) for phase in phases):
        return []
    result = []
    groups: list[str] = []
    regime = ""
    for rowIndex, row in enumerate(rows[1:], 1):
        if not row or len(row) != len(phases) + 1:
            groups = []
            continue
        label, *values = row
        metric = _METRIC.fullmatch(label)
        if metric is None:
            regime = label
            groups = values if (
                label and len(set(values)) == len(values) and all(_GROUP.fullmatch(value) for value in values)
            ) else []
            continue
        dimension, rawUnit = metric.groups()
        if dimension not in dimensions or not groups:
            continue
        for column, (phase, group, rawValue) in enumerate(zip(phases, groups, values), 1):
            if _NUMBER.fullmatch(rawValue):
                result.append(PhaseObservation(regime, group, phase, dimension, rawValue, rawUnit, rowIndex, column))
    return result


def extractPdfPhaseTables(path: Path, pageNumber: int, dimensions: set[str]) -> list[PdfTableObservation]:
    with pymupdf.open(path) as document:
        if not 1 <= pageNumber <= len(document):
            return []
        page = document[pageNumber - 1]
        words = page.get_text("words")
        result = []
        for tableIndex, table in enumerate(page.find_tables().tables, 1):
            cells = [row.cells for row in table.rows]
            rows = [[_cellText(words, box) for box in row] for row in cells]
            for observation in extractPhaseRows(rows, dimensions):
                box = cells[observation.row][observation.column]
                result.append(PdfTableObservation(observation, pageNumber, tableIndex, box))
        return result

