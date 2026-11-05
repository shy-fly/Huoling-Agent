"""Project Recorder Agent — records project/runtime events for audit and debugging."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.models.db import Base, SessionLocal, engine, init_db
from app.observability.context import get_digester_id, get_trace_id, log_extra
from app.observability.logging_config import get_logger

logger = get_logger("project.recorder")


class EventCategory(str, Enum):
    API = "api"
    DIAGNOSIS = "diagnosis"
    GRAPH = "graph"
    LLM = "llm"
    RAG = "rag"
    DATA = "data"
    ALERT = "alert"
    SYSTEM = "system"
    ERROR = "error"
    DEV = "dev"  # development / project notes


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    category = Column(String(32), index=True)
    event = Column(String(64), index=True)
    trace_id = Column(String(64), index=True, nullable=True)
    digester_id = Column(String(64), index=True, nullable=True)
    level = Column(String(16), default="info")
    message = Column(Text)
    detail_json = Column(Text, nullable=True)


class ProjectRecorder:
    """
    Agent for recording project-related runtime events.
    Writes to: structured log (project_journal.jsonl) + SQLite audit_logs table.
    """

    def __init__(self):
        init_db()
        Base.metadata.create_all(bind=engine)

    def record(
        self,
        category: EventCategory | str,
        event: str,
        message: str,
        level: str = "info",
        detail: dict[str, Any] | None = None,
        trace_id: str | None = None,
        digester_id: str | None = None,
    ) -> int | None:
        cat = category.value if isinstance(category, EventCategory) else str(category)
        tid = trace_id or get_trace_id()
        did = digester_id or get_digester_id()
        detail_json = None
        if detail:
            import json
            detail_json = json.dumps(detail, ensure_ascii=False, default=str)

        logger.log(
            logging_level(level),
            message,
            extra=log_extra(
                event=event,
                component=cat,
                trace_id=tid,
                digester_id=did,
            ),
        )

        db = SessionLocal()
        try:
            row = AuditLog(
                category=cat,
                event=event,
                trace_id=tid,
                digester_id=did,
                level=level,
                message=message,
                detail_json=detail_json,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row.id
        except Exception as exc:
            db.rollback()
            get_logger("app.observability").error("audit persist failed (%s)", type(exc).__name__)
            return None
        finally:
            db.close()

    def query(
        self,
        category: str | None = None,
        trace_id: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        db = SessionLocal()
        q = db.query(AuditLog).order_by(AuditLog.timestamp.desc())
        if category:
            q = q.filter(AuditLog.category == category)
        if trace_id:
            q = q.filter(AuditLog.trace_id == trace_id)
        rows = q.limit(limit).all()
        db.close()
        import json
        return [
            {
                "id": r.id,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "category": r.category,
                "event": r.event,
                "trace_id": r.trace_id,
                "digester_id": r.digester_id,
                "level": r.level,
                "message": r.message,
                "detail": json.loads(r.detail_json) if r.detail_json else None,
            }
            for r in rows
        ]


def logging_level(level: str) -> int:
    import logging
    return {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }.get(level.lower(), logging.INFO)


# Singleton for app-wide use
recorder = ProjectRecorder()
