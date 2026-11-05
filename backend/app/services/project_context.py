"""项目上下文快照，用于向其他模型或智能体移交。"""
from __future__ import annotations

import hashlib
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from subprocess import CalledProcessError, TimeoutExpired, check_output
from typing import Any

from app.config import settings
from app.models.db import init_db
from app.services.agent_registry import get_default_agent_id, list_agent_profiles
from app.services.knowledge_admin import knowledge_chunk_stats

# Docker 镜像只复制 backend 到 /app，和本地仓库父级层数不同；由部署环境显式传入根目录。
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[3]))
AGENT_CONTEXT_FILE = PROJECT_ROOT / "project_agent_context.json"
CONTEXT_SCHEMA_VERSION = "firefairy-research-context-v1"


def _git_head() -> str | None:
    try:
        return (
            check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=PROJECT_ROOT,
                stderr=None,
                timeout=2,
                text=True,
            )
            .strip()[:12]
        )
    except (OSError, CalledProcessError, TimeoutExpired):
        return None


def _git_dirty_count() -> int | None:
    try:
        changed = (
            check_output(
                ["git", "status", "--short"],
                cwd=PROJECT_ROOT,
                stderr=None,
                timeout=2,
                text=True,
            )
            .strip()
        )
        return len(changed.splitlines()) if changed else 0
    except (OSError, CalledProcessError, TimeoutExpired):
        return None


def _snapshot_signature(payload: dict[str, Any]) -> tuple[str, int]:
    normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(normalized).hexdigest(), len(normalized)


def build_project_context() -> dict[str, Any]:
    """采集用于模型移交的稳定项目事实。"""
    init_db()
    stats = knowledge_chunk_stats()

    payload = {
        "schema_version": CONTEXT_SCHEMA_VERSION,
        "project": "fireFairyContest",
        "purpose": "厌氧消化科研文献问答智能体",
        "version": settings.app_release,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agent": {
            "default_agent_id": get_default_agent_id(),
            "agents_count": len(list_agent_profiles()),
        },
        "knowledge": {
            "total_chunks": stats.get("total_chunks"),
            "by_collection": stats.get("by_collection"),
        },
        "core_interfaces": [
            "GET /health",
            "POST /v1/research/qa",
            "GET /v1/research/literature/{filename}",
            "GET /v1/agents",
            "GET /v1/knowledge/stats",
            "GET /v1/knowledge/references",
            "GET /v1/project/context",
        ],
        "git": {
            "commit": _git_head(),
            "dirty": _git_dirty_count(),
        },
        "host": {
            "hostname": platform.node(),
            "platform": os.name,
            "project_root": str(PROJECT_ROOT),
        },
    }
    signature, size = _snapshot_signature(payload)
    payload["context_signature"] = signature
    payload["payload_size_bytes"] = size
    return payload


def persist_project_context(output_path: Path | str | None = None) -> tuple[dict[str, Any], str]:
    """把当前上下文快照写入 project_agent_context.json。"""
    payload = build_project_context()
    target = Path(output_path) if output_path else AGENT_CONTEXT_FILE
    payload["persisted_at"] = datetime.now(timezone.utc).isoformat()
    payload["agent_context_file"] = str(target)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload, str(target)