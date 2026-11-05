"""Rebuild figure and table metadata for explicitly selected knowledge-base papers."""
import argparse
import json

from app.rag.media_index import indexPage
from app.rag.media_search import INDEX_ROOT, pdfForChunk
from app.rag.retriever import get_all_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paperIds", nargs="+", metavar="PAPER_ID")
    args = parser.parse_args()
    paperIds = set(args.paperIds)
    if len(paperIds) > 10:
        parser.error("select at most ten papers per run")
    pages = {}
    for chunk in get_all_chunks():
        if chunk["source_id"] in paperIds and chunk.get("page"):
            pages.setdefault((chunk["source_id"], chunk["page"]), chunk)
    if {paperId for paperId, _ in pages} != paperIds:
        parser.error("each paper must be indexed in the knowledge base")
    stats = {"pages": 0, "media": 0, "review": 0, "failed": 0}
    for (paperId, page), chunk in pages.items():
        stats["pages"] += 1
        if not (path := pdfForChunk(chunk)):
            stats["failed"] += 1
            continue
        result = indexPage(INDEX_ROOT, path, paperId, page, refresh=True)
        stats["media"] += len(result["visuals"])
        stats["review"] += result["status"] == "needsReview"
        stats["failed"] += result["status"] == "failed"
    print(json.dumps(stats))
    if stats["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
