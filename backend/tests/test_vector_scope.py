from app.rag import vector_index


def test_vector_results_use_only_current_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(vector_index, "INDEX_PATH", tmp_path / "index.joblib")
    monkeypatch.setattr(vector_index, "META_PATH", tmp_path / "index.json")
    monkeypatch.setattr(vector_index, "_index", None)
    first = {"id": 1, "text": "ammonia methane experiment", "source": "first.pdf"}
    second = {"id": 2, "text": "ammonia methane experiment", "source": "second.pdf"}
    vector_index.build_index([first, second])
    found = vector_index.vector_search("ammonia", [second])
    assert found and {chunk["id"] for _, chunk in found} == {2}


def test_changed_corpus_rebuilds_index(tmp_path, monkeypatch):
    monkeypatch.setattr(vector_index, "INDEX_PATH", tmp_path / "index.joblib")
    monkeypatch.setattr(vector_index, "META_PATH", tmp_path / "index.json")
    monkeypatch.setattr(vector_index, "_index", None)
    vector_index.build_index([{"id": 1, "text": "ammonia methane experiment"}])
    replacement = [{"id": 1, "text": "photosynthesis chlorophyll ecology"}]
    vector_index.ensure_index(replacement)
    assert vector_index.vector_search("chlorophyll", replacement)
