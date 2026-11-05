"""Independent, rebuildable metadata and PNG cache for indexed PDF pages."""
import json
import sqlite3
from contextlib import closing
from functools import lru_cache
from hashlib import file_digest, sha256
from pathlib import Path
from tempfile import NamedTemporaryFile

import pymupdf

from app.observability.logging_config import get_logger
from app.rag.visual_evidence import detectPageVisuals, pdfLock, renderVisual

logger = get_logger("rag.media_index")
_MAX_FILE_BYTES = 128 * 1024 * 1024
_MAX_PAGES = 2000
_VERSION = "4"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS media_pages (
    paperId TEXT NOT NULL, page INTEGER NOT NULL, fingerprint TEXT NOT NULL,
    metadata TEXT NOT NULL, PRIMARY KEY (paperId, page)
)
"""


@lru_cache(maxsize=64)
def _fingerprint(path: Path, size: int, modified: int, changed: int) -> str:
    with path.open("rb") as pdf:
        return file_digest(pdf, "sha256").hexdigest()


def indexPage(root: Path, path: Path, paperId: str, page: int, *, refresh: bool = False) -> dict:
    try:
        info = path.stat()
        if page < 1 or info.st_size > _MAX_FILE_BYTES:
            return {"status": "failed", "visuals": []}
        fingerprint = _fingerprint(path, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        revision = f"{_VERSION}:{fingerprint}"
        root.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(root / "index.sqlite3")) as db:
            db.execute(_SCHEMA)
            cached = db.execute(
                "SELECT metadata FROM media_pages WHERE paperId=? AND page=? AND fingerprint=?",
                (paperId, page, revision),
            ).fetchone()
            if cached and not refresh:
                return json.loads(cached[0])
            with pdfLock, pymupdf.open(path) as pdf:
                if not pdf.is_pdf or pdf.needs_pass or not page <= len(pdf) <= _MAX_PAGES:
                    return {"status": "failed", "visuals": []}
                result = detectPageVisuals(pdf[page - 1])
            for item in result["visuals"]:
                identity = json.dumps([paperId, page, item["kind"], item["number"].lower(), revision])
                item.update(mediaId=sha256(identity.encode()).hexdigest()[:32], sourceFingerprint=fingerprint)
            with db:
                db.execute(
                    "INSERT INTO media_pages VALUES (?, ?, ?, ?) ON CONFLICT (paperId, page) "
                    "DO UPDATE SET fingerprint=excluded.fingerprint, metadata=excluded.metadata",
                    (paperId, page, revision, json.dumps(result, ensure_ascii=False)),
                )
            return result
    except (RuntimeError, ValueError, OSError, sqlite3.Error) as error:
        logger.warning("PDF media indexing failed (%s)", type(error).__name__)
        return {"status": "failed", "visuals": []}


def mediaImage(root: Path, path: Path, page: int, item: dict, size: str) -> Path | None:
    name = item["mediaId"]
    destination = root / f"{name}-{size}.png"
    try:
        if not destination.resolve().is_relative_to(root.resolve()):
            return None
        if destination.is_file():
            return destination
        maxSide, maxScale = (2200, 3.2) if size == "full" else (480, 1.0)
        with pdfLock, pymupdf.open(path) as pdf:
            png = renderVisual(pdf[page - 1], item["region"], maxSide, maxScale)
        if not png:
            return None
        with NamedTemporaryFile(dir=root, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
        try:
            temporary.write_bytes(png)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination
    except (IndexError, RuntimeError, ValueError, OSError) as error:
        logger.warning("PDF media rendering failed (%s)", type(error).__name__)
        return None
