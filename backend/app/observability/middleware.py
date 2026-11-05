"""FastAPI middleware for request/response logging."""
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.agents.project_recorder import EventCategory, recorder
from app.observability.context import set_trace_id
from app.observability.logging_config import get_logger

logger = get_logger("app.http")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
        set_trace_id(trace_id)
        start = time.perf_counter()
        path = request.url.path
        method = request.method

        logger.info("%s %s", method, path, extra={"trace_id": trace_id, "event": "request_start"})

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            recorder.record(
                EventCategory.API,
                "http_request",
                f"{method} {path} -> {response.status_code}",
                detail={"method": method, "path": path, "status": response.status_code, "duration_ms": duration_ms},
                trace_id=trace_id,
                level="info" if response.status_code < 400 else "warning",
            )
            response.headers["X-Trace-Id"] = trace_id
            return response
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            recorder.record(
                EventCategory.ERROR,
                "http_error",
                type(exc).__name__,
                detail={"method": method, "path": path, "duration_ms": duration_ms},
                trace_id=trace_id,
                level="error",
            )
            raise
