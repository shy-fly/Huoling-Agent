"""Read explicit group-by-row tables without guessing damaged numeric glyphs."""
from pathlib import Path
import re

import pymupdf

from app.services.table_cell_ocr import recoverCells
from app.rag.table_cells import cellText as _cellText

_VALUE = re.compile(r"[+-]?\d+(?:\.\d+)?(?:\s*±\s*\d+(?:\.\d+)?)?")
_GROUP = re.compile(r"reactor|group|treatment|condition|arm", re.I)
_CONTROL = re.compile(r"(?:control|untreated|placebo|sham)(?: group)?", re.I)


def _trustedCell(value: str, fonts: set[str]) -> bool:
    return bool(_VALUE.fullmatch(value)) and (len(fonts) <= 1 or "±" in value)


def _numericFonts(spans: list[dict], box: tuple) -> set[str]:
    rect = pymupdf.Rect(box)
    return {
        span["font"] for span in spans
        if any(char.isdecimal() for char in span["text"])
        and rect.contains((pymupdf.Rect(span["bbox"]).tl + pymupdf.Rect(span["bbox"]).br) * 0.5)
    }


def _methodControl(groups: set[str], methods: list[dict]) -> tuple[str | None, dict | None]:
    matches = {}
    for group in groups:
        pattern = re.compile(
            r"(?<!\w)" + re.escape(group) + r"\s+(?:served|was used|was designated) as (?:the |a )?(?:untreated |negative )?control\b",
            re.I,
        )
        for evidence in methods:
            match = pattern.search(evidence["evidenceText"])
            if match:
                matches[group] = {"page": evidence["page"], "quote": match.group()}
    if len(matches) == 1:
        return next(iter(matches.items()))
    return None, None


def _readPage(page: pymupdf.Page, pageNumber: int, rotation: int, methods: list[dict]) -> list[dict]:
    words = page.get_text("words")
    spans = [span for block in page.get_text("dict")["blocks"] for line in block.get("lines", [])
             for span in line["spans"]]
    result = []
    for tableIndex, table in enumerate(page.find_tables().tables, 1):
        cells = [row.cells for row in table.rows]
        rows = [[_cellText(words, box) for box in row] for row in cells]
        header = next((i for i, row in enumerate(rows[:3]) if row and _GROUP.fullmatch(row[0])), None)
        if header is None:
            continue
        records = []
        groups = set()
        candidates = []
        for rowIndex, row in enumerate(rows[header + 1:], header + 1):
            if not row or not row[0] or row[0] in groups or len(row) != len(rows[header]):
                break
            group = row[0]
            if len(group) > 45 or not any(re.search(r"\d", value) for value in row[1:]):
                break
            groups.add(group)
            for column, value in enumerate(row[1:], 1):
                box = cells[rowIndex][column]
                label = rows[header][column]
                if header and rows[header - 1][column] and rows[header - 1][column].endswith(tuple("abcdefghijklmnopqrstuvwxyz(")):
                    label = f"{rows[header - 1][column]} {label}"
                if not value or not label or box is None:
                    continue
                record = {
                    "group": group, "header": label, "rawCell": value,
                    "verifiedValue": value if _trustedCell(value, _numericFonts(spans, box)) else None,
                    "row": rowIndex, "column": column, "cellBox": box,
                }
                records.append(record)
                if record["verifiedValue"] is None:
                    rect = pymupdf.Rect(box)
                    parts = [span["text"].strip() for span in spans if span["text"].strip()
                             and rect.contains((pymupdf.Rect(span["bbox"]).tl + pymupdf.Rect(span["bbox"]).br) * 0.5)]
                    if len(parts) == 3 and all(re.fullmatch(r"\d+(?:\.\d+)?", parts[i]) for i in (0, 2)):
                        candidates.append((record, parts))
        if len(groups) >= 2:
            recoverCells(page, candidates)
            controls = [group for group in groups if _CONTROL.fullmatch(group)]
            contrasts = []
            methodGroup, controlEvidence = _methodControl(groups, methods)
            controlGroup = controls[0] if len(controls) == 1 else methodGroup if not controls else None
            if methodGroup and controlGroup != methodGroup:
                controlGroup = None
            if controlGroup:
                baseline = {item["column"]: item for item in records if item["group"] == controlGroup}
                for item in records:
                    control = baseline.get(item["column"])
                    if control and item["group"] != controlGroup and item["verifiedValue"] and control["verifiedValue"]:
                        contrasts.append({"treatment": item, "control": control, "controlEvidence": controlEvidence})
            result.append({"page": pageNumber, "tableIndex": tableIndex, "rotation": rotation,
                           "records": records, "contrasts": contrasts})
    return result


def readGroupTables(document: pymupdf.Document, pageNumber: int, methods: list[dict] | None = None) -> list[dict]:
    page = document[pageNumber - 1]
    lines = [line for block in page.get_text("dict")["blocks"] for line in block.get("lines", [])]
    vertical = sum(abs(line["dir"][1]) > 0.9 for line in lines)
    if vertical * 2 <= len(lines):
        return _readPage(page, pageNumber, 0, methods or [])
    with pymupdf.open() as rotated:
        view = rotated.new_page(width=page.rect.height, height=page.rect.width)
        view.show_pdf_page(view.rect, document, pageNumber - 1, rotate=270)
        return _readPage(view, pageNumber, 270, methods or [])

