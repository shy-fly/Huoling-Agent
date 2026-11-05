"""RAG retriever — 关键词 + TF-IDF 向量混合检索。"""
from __future__ import annotations

import re

from app.config import settings
from app.models.db import KnowledgeChunk, SessionLocal, init_db
from app.rag.vector_index import build_index, ensure_index, invalidate_index, vector_search

_chunks: list[dict] = []
_loaded_from_db = False

QUERY_ALIASES = {
    "氨抑制": ("ammonia inhibition", "ammonia", "inhibition"),
    "游离氨": ("free ammonia", "nh3", "fan"),
    "总氨氮": ("total ammonia nitrogen", "tan"),
    "总氨": ("total ammonia nitrogen", "tan"),
    "氨氮": ("ammonia nitrogen", "tan", "ammonia"),
    "氨水平": ("ammonia levels", "ammonia"),
    "氨浓度": ("ammonia concentration", "ammonia"),
    "抑制阈值": ("inhibition threshold", "inhibition thresholds"),
    "显著影响": ("significant effect",),
    "相对丰度": ("relative abundance",),
    "颗粒活性炭": ("granular activated carbon", "gac"),
    "厌氧消化": ("anaerobic digestion",),
    "硫化物": ("sulfide", "hydrogen sulfide"),
    "挥发性脂肪酸": ("volatile fatty acids", "vfa"),
    "产甲烷菌": ("methanogens", "methanogenic archaea"),
    "甲烷产量": ("methane production", "methane yield"),
    "产甲烷": ("methanogenesis", "methane production")
}


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[\w\u4e00-\u9fff]+", text.lower()))


def _row_to_chunk(row: KnowledgeChunk) -> dict:
    citation = row.source or ""
    if row.page:
        citation = f"{citation} 第{row.page}页"
    elif row.section:
        citation = f"{citation} §{row.section}"
    return {
        "id": row.id,
        "collection": row.collection,
        "source": row.source,
        "source_id": row.source_id,
        "title": row.title,
        "text": row.text,
        "page": row.page,
        "section": row.section,
        "citation": citation,
    }


def load_knowledge_base(force_db: bool = False) -> None:
    global _chunks, _loaded_from_db
    if _chunks and not force_db:
        return
    init_db()
    db = SessionLocal()
    try:
        rows = db.query(KnowledgeChunk).order_by(KnowledgeChunk.id).all()
        if rows:
            _chunks = [_row_to_chunk(r) for r in rows]
            if settings.rag_use_vector:
                ensure_index(_chunks)
            _loaded_from_db = True
            return
    finally:
        db.close()

    _chunks = []
    _loaded_from_db = False


def _collection_allowed(coll: str, collections: list[str] | None) -> bool:
    if not collections:
        return True
    if "*" in collections:
        return True
    for pattern in collections:
        if pattern.endswith("*") and coll.startswith(pattern[:-1]):
            return True
        if coll == pattern or coll.startswith(f"{pattern}_"):
            return True
    return False

def _keyword_scores(query: str, collections: list[str] | None) -> dict[int, float]:
    queryText = query.strip()
    if not queryText:
        return {}
    queryLower = queryText.lower()
    queryTerms = [term.lower() for term in _tokenize(queryText) if term.strip()]
    queryTerms.extend(re.findall(r"[\u4e00-\u9fff]{2,}", queryLower))
    for chineseTerm, englishTerms in QUERY_ALIASES.items():
        if chineseTerm in queryLower:
            queryTerms.extend(englishTerms)

    queryTerms = list(dict.fromkeys(queryTerms))
    if not queryTerms:
        return {}
    abbreviations = {"tan", "fan", "nh3", "vfa", "gac"}
    termMatches = [
        re.compile(rf"\b{term}\b").search if term in abbreviations else
        (lambda text, token=term: token in text)
        for term in queryTerms
    ]
    scores: dict[int, float] = {}
    for chunk in _chunks:
        chunkId = chunk.get("id")
        collectionName = chunk.get("collection", "")
        if chunkId is None or not _collection_allowed(collectionName, collections):
            continue
        text = str(chunk.get("text") or "").lower()
        title = str(chunk.get("title") or "").lower()
        bodyHits = sum(bool(matches(text)) for matches in termMatches)
        titleHits = sum(bool(matches(title)) for matches in termMatches)
        if bodyHits == 0 and titleHits == 0:
            continue
        score = bodyHits * 4.0 + titleHits * 0.5
        if len(queryTerms) > 1 and bodyHits == len(queryTerms):
            score += 3.0
        if len(queryLower) >= 4 and queryLower in text:
            score += 5.0
        if bodyHits > 0:
            if collectionName == "literature_inhibition" and any(
                term in queryLower for term in ("游离氨", "氨抑制", "氨氮", "硫化氢", "硫化物", "抑制", "毒性")
            ):
                score += 3.0
            if collectionName.startswith("literature") and any(
                term in queryLower for term in ("抑制", "甲烷", "机理", "工程")
            ):
                score += 2.0
            if "vfa" in queryLower and ("vfa" in text or "碱度" in text):
                score += 2.0
        isReference = bool(re.search(
            r"(?m)^\s*(references|bibliography|参考文献)\s*$", text
        ))
        referenceCount = len(re.findall(r"\b\d{1,3}\.\s+[a-z][a-z-]+", text))
        if isReference or referenceCount >= 3:
            score *= 0.25
        scores[chunkId] = score
    return scores


def retrieve(
    query: str,
    top_k: int = 5,
    collection: str | None = None,
    collections: list[str] | None = None,
    mode: str | None = None,
    source_ids: set[str] | None = None,
    search_query: str | None = None,
) -> list[dict]:
    load_knowledge_base()
    allowed = collections
    if collection and not allowed:
        allowed = [collection]
    use_vector = (mode == "vector") or (mode != "keyword" and settings.rag_use_vector)

    rankingQuery = search_query or query
    kw = _keyword_scores(rankingQuery, allowed)
    if source_ids is not None:
        matching = {chunk["id"] for chunk in _chunks if chunk.get("source_id") in source_ids}
        kw = {key: value for key, value in kw.items() if key in matching}
    vec: dict[int, float] = {}
    if use_vector and _chunks:
        scoped = [c for c in _chunks if _collection_allowed(c.get("collection", ""), allowed)
                  and (source_ids is None or c.get("source_id") in source_ids)]
        for sim, chunk in vector_search(rankingQuery, scoped, top_k=max(top_k * 3, 15)):
            cid = chunk.get("id")
            if cid is not None:
                vec[cid] = sim

    combined: dict[int, float] = {}
    max_kw = max(kw.values()) if kw else 1.0
    for cid, s in kw.items():
        combined[cid] = 0.4 * (s / max_kw)
    for cid, s in vec.items():
        combined[cid] = combined.get(cid, 0.0) + 0.6 * s

    if not combined:
        return []

    chunksById = {chunk["id"]: chunk for chunk in _chunks}
    ranked = sorted(combined.items(), key=lambda item: item[1], reverse=True)
    out: list[dict] = []
    sourceCounts: dict[str, int] = {}
    for chunkId, score in ranked:
        chunk = chunksById.get(chunkId)
        if chunk is None:
            continue
        sourceName = str(chunk.get("source") or chunkId)
        if sourceCounts.get(sourceName, 0) >= (top_k if source_ids else 2):
            continue
        result = dict(chunk)
        result["score"] = round(score, 4)
        out.append(result)
        sourceCounts[sourceName] = sourceCounts.get(sourceName, 0) + 1
        if len(out) >= top_k:
            break
    return out


def invalidate_cache() -> None:
    global _chunks, _loaded_from_db
    _chunks = []
    _loaded_from_db = False
    invalidate_index()


def get_all_chunks() -> list[dict]:
    load_knowledge_base()
    return list(_chunks)

