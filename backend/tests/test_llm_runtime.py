from pathlib import Path
from app.config import settings
from app.services import llm_runtime


def test_runtime_overlay_cannot_change_connection(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings, "llm_api_base", "https://example.test")
    monkeypatch.setattr(settings, "llm_api_key", "fixture")
    monkeypatch.setattr(llm_runtime, "RUNTIME_PATH", tmp_path / "runtime.json")
    llm_runtime.RUNTIME_PATH.write_text(
        '{"llm_api_base":"https://other.test","llm_api_key":"legacy"}',
        encoding="utf-8",
    )

    llm_runtime.apply_runtime()

    assert settings.llm_api_base == "https://example.test"
    assert settings.llm_api_key == "fixture"


def test_runtime_save_drops_legacy_connection_fields(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings, "llm_model", "original")
    monkeypatch.setattr(llm_runtime, "RUNTIME_PATH", tmp_path / "runtime.json")
    llm_runtime.RUNTIME_PATH.write_text(
        '{"llm_api_base":"https://other.test","llm_api_key":"legacy"}',
        encoding="utf-8",
    )

    llm_runtime.save_runtime({"llm_model": "updated"})

    assert llm_runtime.load_runtime() == {"llm_model": "updated"}
    assert "llm_api_key" not in llm_runtime.RUNTIME_PATH.read_text(encoding="utf-8")
    assert "llm_api_base" not in llm_runtime.RUNTIME_PATH.read_text(encoding="utf-8")
