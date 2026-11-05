"""API for scoped PDF media search, detail and cached PNGs."""
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.rag.media_index import indexPage, mediaImage
from app.rag.media_search import INDEX_ROOT, mediaPayload, pdfForChunk, searchMedia
from app.rag.retriever import get_all_chunks

router = APIRouter(prefix="/v1/research/media")
MediaId = Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")]


class MediaSearch(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    kind: Literal["figure", "table"] | None = None
    number: str | None = Field(default=None, pattern=r"^[sS]?\d{1,5}[A-Za-z]?(?:\([A-Za-z]\))?$")
    paperIds: list[str] = Field(default_factory=list, max_length=10)
    limit: int = Field(default=10, ge=1, le=20)


@router.post("/search")
def search(req: MediaSearch):
    return searchMedia(INDEX_ROOT, req.question.strip(), req.kind, req.number, req.paperIds, req.limit)


def _lookup(chunkId: int, mediaId: str):
    chunks = get_all_chunks()
    chunk = next((entry for entry in chunks if entry["id"] == chunkId), None)
    if not chunk or not chunk.get("page") or not (path := pdfForChunk(chunk)):
        raise HTTPException(404, "media source not found")
    page, paperId = chunk["page"], chunk["source_id"]
    item = next((item for item in indexPage(INDEX_ROOT, path, paperId, page)["visuals"]
                 if item["mediaId"] == mediaId), None)
    if item is None:
        raise HTTPException(404, "media not found")
    return path, chunk, item, chunks


@router.get("/{chunkId}/{mediaId}")
def detail(chunkId: int, mediaId: MediaId):
    _, chunk, item, chunks = _lookup(chunkId, mediaId)
    siblings = [entry for entry in chunks if entry["id"] != chunkId and
                entry["source_id"] == chunk["source_id"] and entry["page"] == chunk["page"]]
    return mediaPayload(item, [chunk, *siblings])


@router.get("/{chunkId}/{mediaId}/image")
def image(chunkId: int, mediaId: MediaId, size: Literal["thumb", "full"] = Query("thumb")):
    path, chunk, item, _ = _lookup(chunkId, mediaId)
    asset = mediaImage(INDEX_ROOT, path, chunk["page"], item, size)
    if asset is None:
        raise HTTPException(404, "media image unavailable")
    return FileResponse(asset, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})
