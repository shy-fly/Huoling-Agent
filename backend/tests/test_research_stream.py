import json
from contextlib import aclosing

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.mark.parametrize("mode", ["success", "early_failure", "late_failure", "template"])
def test_stream_sends_deltas_then_final_result_or_error(monkeypatch, mode):
    monkeypatch.setattr(settings, "use_llm", mode != "template")
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(settings, "llm_api_key", "test")
    monkeypatch.setattr("app.graph.nodes.explain.retrieve", lambda *_args, **_kwargs: [
        {"id": 1, "text": "Evidence", "source": "paper.pdf", "page": 3},
    ])

    async def fake_stream(self, *_args, **_kwargs):
        if mode == "early_failure":
            raise RuntimeError("upstream detail")
        yield "研究"
        if mode == "late_failure":
            raise RuntimeError("upstream detail")
        yield "结论 [1]"

    monkeypatch.setattr("app.llm.provider.OpenAICompatibleProvider.stream", fake_stream, raising=False)
    response = TestClient(app).post("/v1/research/qa/stream", json={"question": "question"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in response.iter_lines()]
    assert events[0]["type"] == "evidence"
    assert events[0]["chunks"][0]["page"] == 3
    if mode == "late_failure":
        assert [event["type"] for event in events] == ["evidence", "delta", "error"]
        assert "upstream detail" not in response.text
        return
    final = events[-1]
    assert final["type"] == "result"
    assert final["data"]["chunks"] == events[0]["chunks"]
    if mode == "success":
        assert [event["text"] for event in events[1:-1]] == ["研究", "结论 [1]"]
        assert final["data"]["answer"] == "研究结论 [1]"
    else:
        assert len(events) == 2
        assert final["data"]["runtime"]["answer_mode"] == (
            "template_fallback" if mode == "early_failure" else "template_with_references"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("close_early", [False, True])
async def test_provider_reads_sse_and_closes_upstream(monkeypatch, close_early):
    from app.llm.provider import OpenAICompatibleProvider

    class Upstream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b': heartbeat\r\n\r\n'
            yield b'data: {"choices":[{"delta":{"reasoning_content":"hidden"}}]}\n\n'
            yield b'data: {"choices":[{"delta":{"content":"first"}}]}\n\n'
            yield b'data: {"choices":[],"usage":{}}\n\n'
            yield b'data: {"choices":[{"delta":{"content":" second"}}]}\n\n'
            yield b'data: [DONE]\n\n'

        async def aclose(self):
            self.closed = True

    upstream = Upstream()

    def handle(request):
        assert request.url.path.endswith("/chat/completions")
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, stream=upstream)

    async_client = httpx.AsyncClient
    monkeypatch.setattr(settings, "llm_api_key", "test")
    monkeypatch.setattr(settings, "llm_api_base", "https://example.test")
    monkeypatch.setattr(
        "app.llm.provider.httpx.AsyncClient",
        lambda **kwargs: async_client(transport=httpx.MockTransport(handle), **kwargs),
    )

    async with aclosing(OpenAICompatibleProvider().stream([])) as stream:
        assert await anext(stream) == "first"
        if not close_early:
            assert [text async for text in stream] == [" second"]
    assert upstream.closed


@pytest.mark.asyncio
async def test_first_delta_is_sent_before_completion_and_disconnect_closes_stream(monkeypatch):
    import asyncio

    from app.main import ResearchQARequest, research_qa_stream

    first_sent = asyncio.Event()
    closed = asyncio.Event()

    async def blocked_stream(_state):
        try:
            yield "first"
            await asyncio.Event().wait()
        finally:
            closed.set()

    async def receive():
        await first_sent.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body" and message["body"]:
            assert json.loads(message["body"]) == {"type": "delta", "text": "first"}
            assert message["more_body"]
            first_sent.set()

    monkeypatch.setattr("app.main.stream_research_qa", blocked_stream)
    response = await research_qa_stream(ResearchQARequest(question="question"))
    await asyncio.wait_for(
        response({"type": "http", "asgi": {"spec_version": "2.3"}}, receive, send),
        timeout=2,
    )
    assert first_sent.is_set()
    assert closed.is_set()

def test_followup_uses_prior_turn_for_retrieval_and_model(monkeypatch):
    monkeypatch.setattr(settings, "use_llm", True)
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(settings, "llm_api_key", "test")
    captured = {}

    def retrieve(query, **_kwargs):
        captured["query"] = query
        return []

    async def stream(self, messages, **_kwargs):
        captured["messages"] = messages
        yield "低温影响需要本轮证据。"

    monkeypatch.setattr("app.graph.nodes.explain.retrieve", retrieve)
    monkeypatch.setattr("app.llm.provider.OpenAICompatibleProvider.stream", stream)
    response = TestClient(app).post("/v1/research/qa/stream", json={
        "question": "那低温时呢？",
        "history": [{"question": "游离氨如何抑制产甲烷？", "answer": "上一轮证据 [1]。"}],
    })
    assert response.status_code == 200
    assert "游离氨" in captured["query"] and "低温" in captured["query"]
    assert captured["messages"][1]["content"] == "游离氨如何抑制产甲烷？"
    assert captured["messages"][2]["content"] == "上一轮证据 [1]。"
    assert "那低温时呢？" in captured["messages"][-1]["content"]
    assert json.loads(response.text.splitlines()[-1])["data"]["chunks"] == []
