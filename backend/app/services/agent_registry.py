"""科研智能体配置：RAG 可见范围（YAML 持久化，只读）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException

AGENTS_PATH = Path(__file__).resolve().parents[2] / "data" / "agents.yaml"
WILDCARD = "*"


def _load_raw_config() -> dict[str, Any]:
    if not AGENTS_PATH.exists():
        return {
            "default_agent_id": "research",
            "agents": [
                {
                    "id": "research",
                    "name": "科研知识挖掘",
                    "description": "面向科研人员，仅检索厌氧消化文献，不依赖运行装置数据",
                    "rag_collections": [
                        "literature_inhibition",
                        "literature_theory",
                        "literature_engineering",
                    ],
                }
            ],
        }
    with open(AGENTS_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not data.get("agents"):
        data["agents"] = []
    if not data.get("default_agent_id") and data["agents"]:
        data["default_agent_id"] = data["agents"][0]["id"]
    return data


def get_default_agent_id() -> str:
    cfg = _load_raw_config()
    return cfg.get("default_agent_id") or cfg["agents"][0]["id"]


def get_agent(agent_id: str | None) -> dict[str, Any]:
    aid = agent_id or get_default_agent_id()
    for agent in _load_raw_config().get("agents", []):
        if agent.get("id") == aid:
            return dict(agent)
    raise HTTPException(status_code=404, detail=f"未知智能体: {aid}")


def _agent_payload(agent: dict[str, Any], *, default_agent_id: str) -> dict[str, Any]:
    aid = agent["id"]
    return {
        "id": aid,
        "name": agent.get("name", aid),
        "description": agent.get("description", ""),
        "rag_collections": agent.get("rag_collections") or [WILDCARD],
        "is_default": aid == default_agent_id,
    }


def get_agent_profile(agent_id: str) -> dict[str, Any]:
    cfg = _load_raw_config()
    agent = get_agent(agent_id)
    return _agent_payload(agent, default_agent_id=cfg.get("default_agent_id", agent_id))


def resolve_rag_collections(agent_id: str | None) -> list[str] | None:
    """None 表示不限制（全部 collection）。未传 agent_id 时不做限制。"""
    if not agent_id:
        return None
    agent = get_agent(agent_id)
    cols = agent.get("rag_collections") or [WILDCARD]
    if WILDCARD in cols:
        return None
    return list(cols)


def list_agent_profiles() -> list[dict[str, Any]]:
    from app.services.agent_prompts import seed_agent_prompts

    cfg = _load_raw_config()
    default_id = cfg.get("default_agent_id", "")
    for agent in cfg.get("agents", []):
        seed_agent_prompts(agent["id"])
    return [_agent_payload(agent, default_agent_id=default_id) for agent in cfg.get("agents", [])]