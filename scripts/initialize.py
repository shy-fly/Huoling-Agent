"""Initialize a new local evidence database from user-supplied legal PDFs."""
import os
import sys
from pathlib import Path

projectRoot = Path(__file__).resolve().parents[1]
backendRoot = projectRoot / "backend"
(backendRoot / "data").mkdir(exist_ok=True)
os.chdir(backendRoot)
sys.path.insert(0, str(backendRoot))

from app.config import settings
from app.models.db import KnowledgeChunk, SessionLocal, init_db
from app.rag.parsers import parse_pdf_directory
from app.rag.vector_index import build_index
from app.rag.retriever import load_knowledge_base, get_all_chunks

def initialize():
    init_db()
    with SessionLocal() as db:
        if db.query(KnowledgeChunk).first() is not None:
            raise SystemExit("Database already has evidence. Initialization refused.")
    records = []
    for group in ("inhibition", "theory", "engineering"):
        folder = settings.knowledge_path / "literature_corpus" / group
        folder.mkdir(parents=True, exist_ok=True)
        files = list(folder.glob("*.pdf"))
        parsed = parse_pdf_directory(folder, f"literature_{group}", f"literature_zip:{group}")
        if {file.name for file in files} != {row["source"] for row in parsed}:
            raise SystemExit("Some PDFs could not be parsed. No evidence was written.")
        records.extend(parsed)
    if not records:
        raise SystemExit("Place legally obtained PDFs in knowledge/literature_corpus first.")
    with SessionLocal() as db:
        if db.query(KnowledgeChunk).first() is not None:
            raise SystemExit("Database changed during initialization.")
        db.add_all([KnowledgeChunk(**row) for row in records])
        db.commit()
    load_knowledge_base(force_db=True)
    result = build_index(get_all_chunks())
    print(f"Imported {len(records)} chunks. Index ready: {result['ok']}")

if __name__ == "__main__":
    initialize()
