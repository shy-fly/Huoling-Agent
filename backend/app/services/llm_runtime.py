"""Runtime overlay for DeepSeek / OpenAI-compatible LLM settings.

Only non-connection settings can be overridden by the runtime file.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import BACKEND_ROOT, settings
from app.llm.provider import OpenAICompatibleProvider

RUNTIME_PATH = BACKEND_ROOT / "data" / "llm_runtime.json"
RUNTIME_FIELDS = ("use_llm", "llm_provider", "llm_model")


def llm_status() -> dict[str, Any]:
    return {
        "ok": True,
        "use_llm": settings.use_llm,
        "qa_ready": bool(settings.llm_api_key),
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "llm_api_base": settings.llm_api_base,
        "api_key_configured": bool(settings.llm_api_key),
    }


def load_runtime() -> dict[str, Any]:
    if not RUNTIME_PATH.exists():
        return {}
    try:
        data = json.loads(RUNTIME_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {field: data[field] for field in RUNTIME_FIELDS if field in data} if isinstance(data, dict) else {}


def apply_runtime(data: dict[str, Any] | None = None) -> dict[str, Any]:
    overlay = data if data is not None else load_runtime()
    if overlay.get("use_llm") is not None:
        settings.use_llm = bool(overlay["use_llm"])
    if overlay.get("llm_provider"):
        settings.llm_provider = str(overlay["llm_provider"])
    if overlay.get("llm_model"):
        settings.llm_model = str(overlay["llm_model"])
    return llm_status()


def save_runtime(patch: dict[str, Any]) -> dict[str, Any]:
    current = load_runtime()
    for field in RUNTIME_FIELDS:
        if field in patch and patch[field] is not None:
            current[field] = patch[field]
    RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return apply_runtime(current)


def ping_llm() -> dict[str, Any]:
    if not settings.llm_api_key:
        return {"ok": True, "connected": False, "error": "未配置大模型密钥"}
    try:
        sample = OpenAICompatibleProvider().complete(
            [{"role": "user", "content": "只回复两个字：就绪"}],
            temperature=0,
            max_tokens=128,
        )
        return {
            "ok": True,
            "connected": True,
            "model": settings.llm_model,
            "sample": (sample or "").strip()[:80],
        }
    except Exception:
        return {"ok": True, "connected": False, "model": settings.llm_model, "error": "模型连接失败，请检查启动配置"}
