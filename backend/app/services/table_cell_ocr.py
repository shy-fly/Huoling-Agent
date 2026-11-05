"""Confirm damaged plus-minus glyphs using local OCR and independent PDF spans."""
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
import unicodedata

import pymupdf

_NUMBER = re.compile(r"[+-]?\d+(?:\.\d+)?")


def confirmPlusMinus(parts: list[str], readings: list[str]) -> str | None:
    if len(parts) != 3 or not all(_NUMBER.fullmatch(parts[i]) for i in (0, 2)):
        return None
    expected = f"{parts[0]}±{parts[2]}"
    for reading in readings:
        normalized = unicodedata.normalize("NFKC", reading).translate(str.maketrans({"·": ".", ",": "."}))
        if "".join(normalized.split()) == expected:
            return f"{parts[0]} ± {parts[2]}"
    return None


def recoverCells(page: pymupdf.Page, candidates: list[tuple[dict, list[str]]]) -> None:
    if not candidates:
        return
    with TemporaryDirectory() as folder:
        for index, (record, _) in enumerate(candidates):
            for scale in (5, 7):
                image = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale),
                                        clip=pymupdf.Rect(record["cellBox"]), alpha=False)
                image.save(Path(folder) / f"{index}-{scale}.png")
        try:
            response = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-File",
                 str(Path(__file__).with_name("cell_ocr.ps1")), "-Directory", folder],
                capture_output=True, encoding="utf-8", timeout=30, check=True,
            )
            readings = json.loads(response.stdout)
        except (OSError, subprocess.SubprocessError, ValueError):
            return
        for index, (record, parts) in enumerate(candidates):
            value = confirmPlusMinus(parts, [readings.get(f"{index}-{scale}", "") for scale in (5, 7)])
            if value is not None:
                record["verifiedValue"] = value
                record["valueProvenance"] = "ocr_plus_pdf_digits"

