"""Conservative figure and table previews for cited PDF pages."""
import re
from base64 import b64encode
from pathlib import Path
from threading import Lock

import pymupdf

from app.observability.logging_config import get_logger
from app.rag.table_cells import cellText

logger = get_logger("rag.visual_evidence")
# PyMuPDF page operations must not run concurrently in request threads.
pdfLock = Lock()
CAPTION = re.compile(
    r"^(?P<label>(?:supplementary\s+)?fig(?:ure)?\.?|table|图|表)\s*"
    r"(?P<number>s?\d+[a-z]?(?:\([a-z]\))?)"
    r"(?:[.:：]\s*|\s+)(?P<body>.+)$",
    re.IGNORECASE,
)
BODY_MENTION = re.compile(
    r"^(?:cont\.?|continued\b|(?:shows?|illustrates?|presents?|summarizes?|depicts?)\b|续表|所示)",
    re.IGNORECASE,
)
_CAPTION_HEAD = re.compile(r"^(?:(?:supplementary\s+)?fig(?:ure)?\.?|table|图|表)\s*s?\d+[a-z]?(?:\([a-z]\))?[.:：]?$", re.I)
_FOOTNOTE = re.compile(r"^(?:[*†‡§]|notes?\s*[:.]|abbreviations?\s*:)", re.I)


def indexedCaptions(text: str):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if _CAPTION_HEAD.fullmatch(line) and index + 1 < len(lines):
            line += " " + lines[index + 1]
        match = CAPTION.match(line)
        if match and not BODY_MENTION.match(match["body"]):
            yield match


def _nearCaption(region: pymupdf.Rect, caption: pymupdf.Rect, kind: str, *, above: bool = False) -> bool:
    overlap = min(region.x1, caption.x1) - max(region.x0, caption.x0)
    if overlap < 0.5 * min(region.width, caption.width):
        return False
    if kind == "table" or above:
        return -3 <= region.y0 - caption.y1 <= 60
    return region.y0 < caption.y0 - 24 and -40 <= caption.y0 - region.y1 <= 64


def detectPageVisuals(page: pymupdf.Page) -> dict:
    if page.rotation:
        return {"status": "needsReview", "visuals": []}
    images = [pymupdf.Rect(item["bbox"]) & page.rect for item in page.get_image_info()]
    if any(image.get_area() > 0.8 * page.rect.get_area() for image in images):
        return {"status": "needsReview", "visuals": []}

    captions: dict[str, list[tuple[str, str, str, pymupdf.Rect]]] = {"figure": [], "table": []}
    blocks = page.get_text("blocks")
    for block in blocks:
        if block[6] != 0:
            continue
        caption = " ".join(block[4].split())
        match = CAPTION.match(caption)
        if not match:
            continue
        label = match["label"].lower()
        kind = "table" if label in {"table", "表"} else "figure"
        captions[kind].append((match["number"], caption, match["body"], pymupdf.Rect(block[:4])))

    visuals = []
    captionCount = 0
    for kind, matches in captions.items():
        matches = [item for item in matches if not BODY_MENTION.match(item[2])]
        captionCount += len(matches)
        tables = {}
        if kind == "table":
            tables = {tuple(table.bbox): table for table in page.find_tables().tables} if matches else {}
            regions = [pymupdf.Rect(box) for box in tables]
        else:
            drawings = page.cluster_drawings() if matches else []
            regions = images + [
                drawing for drawing in drawings
                if not any((drawing & image).get_area() >= .95 * image.get_area()
                           and drawing.get_area() > 3 * image.get_area() for image in images if not image.is_empty)
            ]
        pairs = []
        for number, caption, _, captionBox in matches:
            if sum(item[0].lower() == number.lower() for item in matches) != 1:
                continue
            candidates = [region for region in regions if region.width >= 60 and region.height >= 36]
            above = False
            nearby = [region for region in candidates if _nearCaption(region, captionBox, kind)]
            if not nearby and kind == "figure":
                above = True
                nearby = [region for region in candidates if _nearCaption(region, captionBox, kind, above=True)]
            if len(nearby) == 1:
                pairs.append((number, caption, captionBox, nearby[0], above))
        for number, caption, captionBox, region, above in pairs:
            if sum(pair[3] == region for pair in pairs) != 1 or sum(
                _nearCaption(region, item[3], kind, above=above) for item in matches
            ) != 1:
                continue
            box = region | captionBox
            footnotes = []
            if kind == "table":
                for block in blocks:
                    text = block[4].strip()
                    if (block[6] == 0 and 0 <= block[1] - region.y1 <= 14
                            and region.x0 - 10 <= block[0] < region.x1
                            and block[2] <= region.x1 + 12 and block[3] - block[1] <= 38
                            and _FOOTNOTE.match(text)):
                        box |= pymupdf.Rect(block[:4])
                        footnotes.append(text)
            crop = pymupdf.Rect(box.x0 - 5, box.y0 - 5, box.x1 + 5, box.y1 + 5) & page.rect
            item = {
                "kind": kind,
                "number": number,
                "caption": caption,
                "region": [round(value, 2) for value in crop],
                "captionRegion": [round(value, 2) for value in captionBox],
                "extractionMethod": "caption-layout",
                "extractionStatus": "extracted",
                "verificationStatus": "needsReview",
            }
            if kind == "table":
                table = tables[tuple(region)]
                words = page.get_text("words")
                rows = [[cellText(words, box) if box else None for box in row.cells] for row in table.rows
                        ] if table.row_count * table.col_count <= 500 else []
                item["rawFootnotes"] = footnotes
                rectangular = rows and all(len(row) == table.col_count and None not in row for row in rows)
                # A sparse first row often represents spanning headers that the grid could not resolve.
                if (rectangular and 2 * sum(bool(cell.strip()) for cell in rows[0]) >= table.col_count
                        and not any(re.search(r"[\x00-\x08\x0e-\x1f]", cell) for row in rows for cell in row)):
                    item.update(tableStatus="extracted", rawRows=rows)
                else:
                    item["tableStatus"] = "needsReview"
            visuals.append(item)
    return {"status": "needsReview" if len(visuals) < captionCount else "indexed", "visuals": visuals}


def renderVisual(page: pymupdf.Page, region: list[float], maxSide: int, maxScale: float) -> bytes | None:
    crop = pymupdf.Rect(region) & page.rect
    if crop.is_empty:
        return None
    scale = min(maxScale, maxSide / max(crop.width, crop.height))
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=crop, alpha=False)
    return None if pixmap.is_unicolor else pixmap.tobytes("png")


def getVisualEvidence(path: Path, pageNumber: int) -> list[dict]:
    try:
        with pdfLock, pymupdf.open(path) as document:
            if document.is_pdf and 1 <= pageNumber <= len(document):
                page = document[pageNumber - 1]
                return [
                    {**item, "png": b64encode(png).decode("ascii")}
                    for item in detectPageVisuals(page)["visuals"]
                    if (png := renderVisual(page, item["region"], 1100, 1.6))
                ]
    except (RuntimeError, ValueError, OSError) as error:
        logger.warning("PDF visual preview unavailable (%s)", type(error).__name__)
    return []
