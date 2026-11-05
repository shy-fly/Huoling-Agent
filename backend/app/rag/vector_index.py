"""TF-IDF 向量索引 — 与关键词检索混合。"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.config import settings

INDEX_PATH = Path(__file__).resolve().parents[2] / "data" / "knowledge" / "tfidf_index.joblib"
META_PATH = INDEX_PATH.with_suffix(".meta.json")

_index: dict[str, Any] | None = None


def _blob(chunk: dict) -> str:
    return f"{chunk.get('title', '')} {chunk.get('text', '')} {chunk.get('collection', '')}"


def corpusFingerprint(chunks: list[dict]) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(json.dumps([chunk.get("id"), chunk.get("source"), _blob(chunk)],
                                 ensure_ascii=False).encode("utf-8"))
    return digest.hexdigest()


def ensure_index(chunks: list[dict]) -> None:
    if chunks:
        index = _load_index(chunks)
        if index is None or index.get("fingerprint") != corpusFingerprint(chunks):
            build_index(chunks)


def build_index(chunks: list[dict]) -> dict[str, Any]:
    if not chunks:
        return {"ok": False, "error": "no chunks"}
    texts = [_blob(c) for c in chunks]
    chunk_ids = [c.get("id") for c in chunks]
    vectorizer = TfidfVectorizer(
        max_features=12000,
        token_pattern=r"(?u)\b\w\w+\b|[\u4e00-\u9fff]{2,}",
        sublinear_tf=True,
    )
    matrix = vectorizer.fit_transform(texts)
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    fingerprint = corpusFingerprint(chunks)
    joblib.dump({"vectorizer": vectorizer, "matrix": matrix, "chunk_ids": chunk_ids,
                "fingerprint": fingerprint}, INDEX_PATH)
    meta = {
        "n_chunks": len(chunks),
        "n_features": matrix.shape[1],
        "index_path": str(INDEX_PATH),
    }
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    global _index
    _index = {"vectorizer": vectorizer, "matrix": matrix, "chunk_ids": chunk_ids, "fingerprint": fingerprint}
    return {"ok": True, **meta}


def _load_index(chunks: list[dict] | None = None) -> dict[str, Any] | None:
    global _index
    if _index is not None:
        return _index
    if not INDEX_PATH.exists():
        if chunks:
            build_index(chunks)
            return _index
        return None
    data = joblib.load(INDEX_PATH)
    chunks_by_id = {}
    if chunks:
        chunks_by_id = {c.get("id"): c for c in chunks}
    _index = {
        "fingerprint": data.get("fingerprint"),
        "vectorizer": data["vectorizer"],
        "matrix": data["matrix"],
        "chunk_ids": data["chunk_ids"],
        "chunks_by_id": chunks_by_id,
    }
    return _index


def vector_search(query: str, chunks: list[dict], top_k: int = 10) -> list[tuple[float, dict]]:
    idx = _load_index(chunks)
    if idx is None:
        return []
    scopedChunks = {c.get("id"): c for c in chunks}
    vectorizer = idx["vectorizer"]
    matrix = idx["matrix"]
    chunk_ids = idx["chunk_ids"]
    qv = vectorizer.transform([query])
    sims = cosine_similarity(qv, matrix).flatten()
    order = np.argsort(-sims)
    out: list[tuple[float, dict]] = []
    for i in order:
        if sims[i] <= 0.01:
            continue
        cid = chunk_ids[i]
        chunk = scopedChunks.get(cid)
        if chunk:
            out.append((float(sims[i]), chunk))
            if len(out) >= top_k:
                break
    return out


def invalidate_index() -> None:
    global _index
    _index = None
