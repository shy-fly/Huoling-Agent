"""LLM provider abstraction for OpenAI-compatible model services."""
import json
import threading
import time
from collections.abc import AsyncIterator
from typing import Protocol

import httpx

from app.agents.project_recorder import EventCategory, recorder
from app.config import settings
from app.observability.logging_config import get_logger

logger = get_logger("app.llm")

# 进程级共享连接池：httpx.Client 官方支持多线程；连接失效由 httpx 自动重连。
# 单例不主动关闭（随进程生命周期）；请求级 timeout 覆盖 client 级默认值，
# 以保留每个 provider 实例自定义 timeout_seconds 的语义。
_CLIENT_LOCK = threading.Lock()
_CLIENT: httpx.Client | None = None


def _shared_client() -> httpx.Client:
    global _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is None or _CLIENT.is_closed:
            _CLIENT = httpx.Client(timeout=settings.llm_timeout_ms / 1000.0)
        return _CLIENT


class LLMProvider(Protocol):
    def complete(
        self,
        messages: list[dict],
        temperature: float = 0.2,
        *,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str: ...


class OpenAICompatibleProvider:
    def __init__(self, *, timeout_seconds: float | None = None, attempts: int = 2):
        self.base = settings.llm_api_base.rstrip("/")
        self.key = settings.llm_api_key
        self.model = settings.llm_model
        self.timeout = timeout_seconds if timeout_seconds is not None else settings.llm_timeout_ms / 1000.0
        self.attempts = max(1, min(attempts, 2))

    def _payload(self, messages: list[dict], temperature: float, max_tokens: int | None) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or settings.llm_max_tokens_polish,
        }
        if ("v4" in self.model or self.model == "deepseek-flash") and not settings.llm_thinking_enabled:
            payload["thinking"] = {"type": "disabled"}
        return payload

    async def stream(
        self, messages: list[dict], temperature: float = 0.2, *, max_tokens: int | None = None
    ) -> AsyncIterator[str]:
        payload = self._payload(messages, temperature, max_tokens)
        payload["stream"] = True
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base}/chat/completions",
                headers={"Authorization": f"Bearer {self.key}"},
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    event = json.loads(data)
                    if event.get("error"):
                        raise RuntimeError("model stream reported an error")
                    choices = event.get("choices") or []
                    if choices:
                        content = choices[0].get("delta", {}).get("content")
                        if isinstance(content, str) and content:
                            yield content
        raise RuntimeError("model stream ended without completion")

    def complete(
        self,
        messages: list[dict],
        temperature: float = 0.2,
        *,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        if not self.key:
            raise RuntimeError("LLM_API_KEY not configured")
        start = time.perf_counter()
        payload = self._payload(messages, temperature, max_tokens)
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            last_error: Exception | None = None
            content = ""
            for attempt in range(self.attempts):
                try:
                    client = _shared_client()
                    resp = client.post(
                        f"{self.base}/chat/completions",
                        headers={"Authorization": f"Bearer {self.key}"},
                        json=payload,
                        timeout=self.timeout,
                    )
                    resp.raise_for_status()
                    content = resp.json()["choices"][0]["message"]["content"]
                    break
                except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                    last_error = exc
                    if attempt + 1 < self.attempts:
                        time.sleep(0.35)
            if not content:
                raise last_error or RuntimeError("empty model response")
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            recorder.record(
                EventCategory.LLM,
                "api_call",
                f"model={self.model}",
                detail={"duration_ms": duration_ms, "model": self.model},
            )
            logger.info("LLM complete %s ms", duration_ms)
            return content
        except Exception as exc:
            recorder.record(EventCategory.ERROR, "llm_error", type(exc).__name__, level="error")
            logger.warning("LLM call failed (%s)", type(exc).__name__)
            raise


class TemplateProvider:
    def complete(
        self,
        messages: list[dict],
        temperature: float = 0.2,
        *,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        logger.debug("template provider fallback")
        return messages[-1]["content"][:200] + "…（模板模式，未调用大模型）"


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "template" or not settings.llm_api_key:
        return TemplateProvider()
    return OpenAICompatibleProvider()
