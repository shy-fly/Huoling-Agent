"""科研智能体配置作用域（只读）。"""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.services import agent_registry as reg

client = TestClient(app)
RESEARCH_COLLECTIONS = ["literature_inhibition", "literature_theory", "literature_engineering"]


def test_default_agent_is_research():
    assert reg.get_default_agent_id() == "research"


def test_research_scope_is_literature_only():
    profile = reg.get_agent_profile("research")
    assert profile["id"] == "research"
    assert sorted(profile["rag_collections"]) == sorted(RESEARCH_COLLECTIONS)
    assert reg.resolve_rag_collections("research") == RESEARCH_COLLECTIONS


def test_list_agent_profiles():
    agents = reg.list_agent_profiles()
    assert len(agents) >= 1
    first = agents[0]
    assert "id" in first and "name" in first
    assert "rag_collections" in first


def test_unknown_agent_404():
    with pytest.raises(HTTPException) as exc:
        reg.get_agent("unknown-agent")
    assert exc.value.status_code == 404


def test_api_list_agents():
    r = client.get("/v1/agents")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["default_agent_id"] == "research"
    assert len(body["agents"]) >= 1