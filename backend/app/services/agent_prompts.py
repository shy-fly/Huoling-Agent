"""智能体独立 Prompt 存储与渲染。"""
from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from jinja2 import Template

from app.prompts.registry import render_prompt

AGENTS_DATA = Path(__file__).resolve().parents[2] / "data" / "agents"
GLOBAL_PROMPTS = Path(__file__).resolve().parents[1] / "prompts"

PROMPT_KEYS = (
    "system/research_guardrails",
    "tasks/research_qa",
)

_PROMPT_KEY_RE = re.compile(r"^[a-z][a-z0-9_/\-]{0,120}$")


def _validate_prompt_key(prompt_key: str) -> str:
    key = prompt_key.replace("..", "").strip("/")
    if not key or not _PROMPT_KEY_RE.match(key):
        raise HTTPException(status_code=400, detail="无效的 prompt_key")
    return key


def agent_dir(agent_id: str) -> Path:
    return AGENTS_DATA / agent_id


def prompts_dir(agent_id: str) -> Path:
    return agent_dir(agent_id) / "prompts"


def versions_dir(agent_id: str, prompt_key: str) -> Path:
    safe = prompt_key.replace("/", "__")
    return prompts_dir(agent_id) / ".versions" / safe


def prompt_path(agent_id: str, prompt_key: str) -> Path:
    key = _validate_prompt_key(prompt_key)
    return prompts_dir(agent_id) / f"{key}.jinja"


def seed_agent_prompts(agent_id: str) -> None:
    """新建智能体时从全局模板复制 Prompt。"""
    dest = prompts_dir(agent_id)
    dest.mkdir(parents=True, exist_ok=True)
    for key in PROMPT_KEYS:
        src = GLOBAL_PROMPTS / f"{key}.jinja"
        target = dest / f"{key}.jinja"
        if src.exists() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def remove_agent_data(agent_id: str) -> None:
    path = agent_dir(agent_id)
    if path.exists():
        shutil.rmtree(path)


def render_agent_prompt(agent_id: str | None, name: str, **kwargs) -> str:
    """优先使用智能体目录下的 Prompt，否则回退全局模板。"""
    rel = name if name.endswith(".jinja") else f"{name}.jinja"
    key = rel.replace(".jinja", "")
    if agent_id:
        path = prompts_dir(agent_id) / rel
        if path.exists():
            return Template(path.read_text(encoding="utf-8")).render(**kwargs)
    return render_prompt(key, **kwargs)


def list_agent_prompts(agent_id: str) -> list[dict[str, Any]]:
    seed_agent_prompts(agent_id)
    items: list[dict[str, Any]] = []
    for key in PROMPT_KEYS:
        path = prompt_path(agent_id, key)
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        items.append(
            {
                "id": key,
                "lines": len(text.splitlines()) if text else 0,
                "preview": text[:120].replace("\n", " ") if text else "",
                "customized": path.exists(),
            }
        )
    return items


def get_agent_prompt(agent_id: str, prompt_key: str) -> dict[str, Any]:
    seed_agent_prompts(agent_id)
    key = _validate_prompt_key(prompt_key)
    path = prompt_path(agent_id, key)
    if not path.exists():
        global_path = GLOBAL_PROMPTS / f"{key}.jinja"
        if global_path.exists():
            content = global_path.read_text(encoding="utf-8")
            return {"ok": True, "prompt": {"id": key, "content": content, "source": "global"}}
        raise HTTPException(status_code=404, detail=f"Prompt 不存在: {key}")
    return {
        "ok": True,
        "prompt": {
            "id": key,
            "content": path.read_text(encoding="utf-8"),
            "source": "agent",
        },
    }


def save_agent_prompt(agent_id: str, prompt_key: str, content: str, *, snapshot_version: bool = True) -> dict[str, Any]:
    if not content or not content.strip():
        raise HTTPException(status_code=400, detail="content 不能为空")
    key = _validate_prompt_key(prompt_key)
    path = prompt_path(agent_id, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    if snapshot_version and path.exists():
        _snapshot_version(agent_id, key, path.read_text(encoding="utf-8"))
    path.write_text(content, encoding="utf-8")
    return {"ok": True, "prompt": {"id": key, "content": content}}


def reset_agent_prompt(agent_id: str, prompt_key: str) -> dict[str, Any]:
    key = _validate_prompt_key(prompt_key)
    global_path = GLOBAL_PROMPTS / f"{key}.jinja"
    if not global_path.exists():
        raise HTTPException(status_code=404, detail="全局模板不存在")
    content = global_path.read_text(encoding="utf-8")
    return save_agent_prompt(agent_id, key, content)


def _snapshot_version(agent_id: str, prompt_key: str, content: str) -> Path:
    vdir = versions_dir(agent_id, prompt_key)
    vdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = vdir / f"{ts}.jinja"
    path.write_text(content, encoding="utf-8")
    return path


def list_prompt_versions(agent_id: str, prompt_key: str, limit: int = 10) -> list[dict[str, Any]]:
    key = _validate_prompt_key(prompt_key)
    vdir = versions_dir(agent_id, key)
    if not vdir.exists():
        return []
    files = sorted(vdir.glob("*.jinja"), reverse=True)[:limit]
    return [{"version": p.stem, "path": str(p.name)} for p in files]
