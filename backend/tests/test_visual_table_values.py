import pymupdf

from app.config import settings
from app.rag.visual_evidence import detectPageVisuals


def test_original_table_preserves_decimal_points_and_uncertainty():
    path = next((settings.knowledge_path / "literature_corpus").rglob("Yang-2018-*.pdf"))
    with pymupdf.open(path) as document:
        table = next(item for item in detectPageVisuals(document[3])["visuals"]
                     if item["kind"] == "table" and item["number"] == "1")
    rows = table["rawRows"]
    fan = [row for row in rows if row[0].replace(" ", "") == "FAN(mg/L)"]
    assert fan[0][1] == "3.36"
    assert fan[0][-1] == "293.29"
    assert fan[1][-1] == "426.14"
    methane = [row for row in rows if row[0].replace(" ", "") == "MP(mL/d)"]
    assert methane[0][1].replace(" ", "") == "1716±162"
