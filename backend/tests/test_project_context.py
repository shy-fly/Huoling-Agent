from fastapi.testclient import TestClient

from app.main import app
from conftest import ADMIN_HEADERS

client = TestClient(app)


def test_project_context_get_and_write(tmp_path, monkeypatch):
    payload = {"project": "fireFairy", "version": "test"}
    payload["schema_version"] = "firefairy-research-context-v1"
    payload["context_signature"] = "abc"
    payload["payload_size_bytes"] = 100
    target = tmp_path / "project_agent_context.json"

    def fake_build():
        return payload

    def fake_persist(_output_path=None):
        target.write_text("{}", encoding="utf-8")
        return payload, str(target)

    monkeypatch.setattr("app.services.project_context.build_project_context", fake_build)
    monkeypatch.setattr("app.services.project_context.persist_project_context", fake_persist)

    r = client.get("/v1/project/context", params={"write": False})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["payload"]["project"] == "fireFairy"
    assert body["payload"]["schema_version"] == "firefairy-research-context-v1"
    assert body["payload"]["context_signature"] == "abc"

    assert client.get("/v1/project/context", params={"write": True}).status_code == 403
    assert not target.exists()
    r2 = client.get("/v1/project/context", params={"write": True}, headers=ADMIN_HEADERS)
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["ok"] is True
    assert body2["stored_at"] == str(target)
    assert target.read_text(encoding="utf-8") == "{}"
