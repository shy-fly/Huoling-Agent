from app.config import settings
from app.llm import provider as provider_module


def test_deepseek_disables_thinking_when_configured(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    class FakeClient:
        def __init__(self, *, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, *, headers, json, timeout=None):
            captured.update(url=url, headers=headers, payload=json)
            return FakeResponse()

    monkeypatch.setattr(settings, "llm_api_base", "https://api.deepseek.com")
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_model", "deepseek-flash")
    monkeypatch.setattr(settings, "llm_thinking_enabled", False)
    monkeypatch.setattr(provider_module, "_CLIENT", None)
    monkeypatch.setattr(provider_module.httpx, "Client", FakeClient)
    monkeypatch.setattr(provider_module.recorder, "record", lambda *_args, **_kwargs: None)

    result = provider_module.OpenAICompatibleProvider().complete(
        [{"role": "user", "content": "reply with ok"}],
    )

    assert result == "ok"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["payload"]["model"] == "deepseek-flash"
    assert captured["payload"]["thinking"] == {"type": "disabled"}
    assert "enable_thinking" not in captured["payload"]
    assert captured["headers"]["Authorization"] == "Bearer test-key"