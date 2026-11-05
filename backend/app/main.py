"""fireFairyContest — 科研智能体比赛版 API 入口。"""
import json
from contextlib import aclosing, asynccontextmanager
from pathlib import Path
from secrets import compare_digest
from typing import Annotated, Literal, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, StringConstraints

from app.agents.project_recorder import EventCategory, recorder
from app.config import settings
from app.services.design_evidence import suggestFromEvidence
from app.services.experiment_design import DesignRequest, planExperiment
from app.services.research_gap_coverage import collectPhaseRecords
from app.services.research_gap_records import collectGroupRecords
from app.research_gaps_api import router as gapsRouter
from app.media_api import router as mediaRouter
from app.evidence_graph_api import router as evidenceGraphRouter
from app.reliability_audit_api import router as reliabilityAuditRouter
from app.evolution_api import router as evolutionRouter
from app.services.llm_runtime import apply_runtime
from app.services.qa_compare_context import QaCompareContext, resolveQaContext

apply_runtime()
from app.services.falsification_search import HypothesisSearch, searchHypothesis
from app.graph.research_compare import buildResearchCompareGraph
from app.graph.graphs import build_research_qa_graph
from app.graph.nodes.explain import stream_research_qa
from app.graph.state import ResearchState
from app.models.db import KnowledgeChunk, SessionLocal, init_db
from app.rag.visual_evidence import getVisualEvidence
from app.observability.logging_config import LOG_DIR, setup_logging, get_logger

logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    recorder.record(EventCategory.SYSTEM, "app_start", f"env={settings.app_env}")
    logger.info("fireFairyContest research agent started env=%s log_dir=%s", settings.app_env, LOG_DIR)
    yield
    recorder.record(EventCategory.SYSTEM, "app_stop", "shutdown")
    logger.info("fireFairyContest research agent stopped")


app = FastAPI(title="fireFairyContest 科研智能体 API", version="4.0.0", lifespan=lifespan)
app.include_router(gapsRouter)
app.include_router(mediaRouter)
app.include_router(evidenceGraphRouter)
app.include_router(reliabilityAuditRouter)
app.include_router(evolutionRouter)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

researchQaGraph = build_research_qa_graph()


class ResearchTurn(BaseModel):
    question: str = Field(max_length=1000)
    answer: str = Field(max_length=4000)


class ResearchQARequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    top_k: int = Field(default=5, ge=1, le=20)
    history: list[ResearchTurn] = Field(default_factory=list, max_length=4)


class LLMConfigRequest(BaseModel):
    use_llm: bool | None = None
    llm_provider: str | None = None
    llm_model: str | None = None


class ProjectNoteRequest(BaseModel):
    message: str
    detail: dict | None = None
    category: str = "dev"


def _check_admin_token(x_admin_token: str | None) -> None:
    if not settings.admin_token:
        raise HTTPException(status_code=503, detail="管理操作尚未启用")
    if not x_admin_token or not compare_digest(x_admin_token.encode("utf-8"), settings.admin_token.encode("utf-8")):
        raise HTTPException(status_code=403, detail="需要工程师权限")


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    _check_admin_token(x_admin_token)


# ---- 健康检查 ----

@app.get("/health")
def health():
    return {
        "status": "ok",
        "release": settings.app_release,
        "use_llm": settings.use_llm,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model if settings.use_llm else None,
        "log_dir": str(LOG_DIR),
    }


# ---- 日志与项目上下文 ----

@app.get("/v1/logs/audit", dependencies=[Depends(require_admin)])
def list_audit_logs(category: Optional[str] = None, trace_id: Optional[str] = None, limit: int = Query(100, le=500)):
    return {"items": recorder.query(category=category, trace_id=trace_id, limit=limit)}


@app.get("/v1/logs/trace/{trace_id}", dependencies=[Depends(require_admin)])
def get_trace_logs(trace_id: str):
    return {"trace_id": trace_id, "items": recorder.query(trace_id=trace_id, limit=200)}


@app.post("/v1/logs/note", dependencies=[Depends(require_admin)])
def add_project_note(req: ProjectNoteRequest):
    rid = recorder.record(req.category, "project_note", req.message, detail=req.detail, level="info")
    return {"ok": True, "id": rid}


@app.get("/v1/project/context")
def get_project_context(write: bool = False, x_admin_token: str | None = Header(default=None)):
    if write:
        _check_admin_token(x_admin_token)
    from app.services.project_context import build_project_context, persist_project_context
    payload = build_project_context()
    file_path = None
    if write:
        payload, file_path = persist_project_context()
        recorder.record(EventCategory.SYSTEM, "project_context_persisted", "更新 project_agent_context.json", detail={"path": file_path})
    return {"ok": True, "stored_at": file_path, "payload": payload}


# ---- LLM 配置 ----

@app.get("/v1/llm/status")
def llm_status():
    from app.services.llm_runtime import llm_status as status
    return status()


@app.put("/v1/llm/config", dependencies=[Depends(require_admin)])
def update_llm_config(req: LLMConfigRequest):
    from app.services.llm_runtime import save_runtime
    return save_runtime(req.model_dump(exclude_none=True))


@app.post("/v1/llm/ping", dependencies=[Depends(require_admin)])
def ping_llm_endpoint():
    from app.services.llm_runtime import ping_llm
    return ping_llm()


# ---- Agent 管理（科研智能体） ----

@app.get("/v1/agents")
def list_agents():
    from app.services.agent_registry import get_default_agent_id, list_agent_profiles
    return {"ok": True, "default_agent_id": get_default_agent_id(), "agents": list_agent_profiles()}


@app.get("/v1/agents/{agent_id}")
def get_agent_profile(agent_id: str):
    from app.services.agent_registry import get_agent_profile as _get
    return {"ok": True, "agent": _get(agent_id)}


@app.get("/v1/agents/{agent_id}/prompts")
def list_agent_prompts_api(agent_id: str):
    from app.services.agent_prompts import list_agent_prompts
    return {"ok": True, "items": list_agent_prompts(agent_id)}


# ---- 科研文献 PDF 静态服务 ----

LITERATURE_COLLECTIONS = {"literature_inhibition", "literature_theory", "literature_engineering"}
LITERATURE_DIRS = {"literature_inhibition": "inhibition", "literature_theory": "theory", "literature_engineering": "engineering"}
LITERATURE_PDF_ROOT = settings.knowledge_path / "literature_corpus"
compareGraph = buildResearchCompareGraph(LITERATURE_PDF_ROOT)


class ResearchCompareRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    paperLimit: int = Field(default=3, ge=2, le=10)
    dimensions: list[str] = Field(default_factory=list, max_length=20)
    includeIds: list[str] | None = Field(default=None, max_length=20)
    excludeIds: list[str] = Field(default_factory=list, max_length=20)
    qaContext: QaCompareContext | None = None



def _literaturePdfPath(filename: str, collection: str) -> Path:
    if collection not in LITERATURE_COLLECTIONS:
        raise HTTPException(status_code=403, detail="collection not allowed")
    if any(separator in filename for separator in ("/", "\\", ":", "\x00")) or Path(filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=404, detail="pdf not found")
    root = LITERATURE_PDF_ROOT.resolve()
    directory = (root / LITERATURE_DIRS[collection]).resolve()
    safe_path = (directory / filename).resolve()
    if directory == root or not directory.is_relative_to(root) or safe_path.parent != directory:
        raise HTTPException(status_code=403, detail="path traversal denied")
    if not safe_path.is_file():
        raise HTTPException(status_code=404, detail="pdf not found")
    return safe_path


@app.get("/v1/research/literature/{filename:path}")
def serve_literature_pdf(filename: str, collection: str = Query("literature_inhibition"), page: int = Query(0, ge=0)):
    safe_path = _literaturePdfPath(filename, collection)
    headers = {}
    if page > 0:
        headers["X-PDF-Page"] = str(page)
    return FileResponse(safe_path, media_type="application/pdf", headers=headers, filename=safe_path.name, content_disposition_type="inline")


@app.get("/v1/research/chunks/{chunkId}/visuals")
def researchChunkVisuals(
    chunkId: int,
    kind: Literal["figure", "table"] | None = None,
    number: str | None = Query(default=None, pattern=r"^[sS]?\d{1,5}[A-Za-z]?(?:\([A-Za-z]\))?$"),
):
    if (kind is None) != (number is None):
        raise HTTPException(status_code=422, detail="kind and number must be specified together")
    with SessionLocal() as session:
        chunk = session.get(KnowledgeChunk, chunkId)
        if chunk is None or chunk.collection not in LITERATURE_COLLECTIONS:
            raise HTTPException(status_code=404, detail="citation not found")
        source, collection, page = chunk.source, chunk.collection, chunk.page
    visuals = []
    if page and source and Path(source).suffix.lower() == ".pdf":
        path = _literaturePdfPath(source, collection)
        visuals = getVisualEvidence(path, page)
    if kind is not None and number is not None:
        visuals = [item for item in visuals if item["kind"] == kind and item["number"].lower() == number.lower()]
    return {"source": source, "collection": collection, "page": page, "visuals": visuals}


# ---- 科研问答核心接口 ----

def _research_state(req: ResearchQARequest) -> ResearchState:
    from app.services.agent_registry import resolve_rag_collections
    rag_collections = resolve_rag_collections("research")
    trace_id = str(uuid4())
    return {
        "mode": "qa",
        "question": req.question,
        "history": [turn.model_dump() for turn in req.history],
        "agent_id": "research",
        "rag_collections": rag_collections,
        "rag_top_k": req.top_k,
        "trace_id": trace_id,
    }


def _research_chunks(result: ResearchState) -> list[dict]:
    return [{
        "chunk_id": c.get("id") or c.get("chunk_id"),
        "title": c.get("title"),
        "source": c.get("source"),
        "collection": c.get("collection"),
        "citation": c.get("citation") or c.get("source"),
        "page": c.get("page"),
        "snippet": (c.get("text") or "")[:1200],
        "score": c.get("score"),
    } for c in result.get("rag_chunks", [])]


def _research_response(result: ResearchState) -> dict:
    model_answer = (result.get("answer_mode") or "").startswith("model_")
    return {
        "ok": True,
        "answer": result.get("narrative"),
        "citations": result.get("citations", []),
        "chunks": _research_chunks(result),
        "trace_id": result.get("trace_id"),
        "agent_id": "research",
        "runtime": {
            "answer_mode": result.get("answer_mode"),
            "provider": settings.llm_provider if model_answer else "template",
            "model": settings.llm_model if model_answer else None,
            "knowledge_hits": len(result.get("rag_chunks", [])),
            "qa_ready": bool(settings.llm_api_key),
        },
    }


@app.post("/v1/research/qa")
def research_qa(req: ResearchQARequest):
    return _research_response(researchQaGraph.invoke(_research_state(req)))


@app.post("/v1/research/qa/stream")
async def research_qa_stream(req: ResearchQARequest):
    async def events():
        try:
            async with aclosing(stream_research_qa(_research_state(req))) as stream:
                async for item in stream:
                    if isinstance(item, str):
                        event = {"type": "delta", "text": item}
                    elif item.get("answer_mode"):
                        event = {"type": "result", "data": _research_response(item)}
                    else:
                        event = {"type": "evidence", "chunks": _research_chunks(item)}
                    yield json.dumps(event, ensure_ascii=False) + "\n"
        except Exception as exc:
            logger.warning("Research QA stream interrupted (%s)", type(exc).__name__)
            yield json.dumps({"type": "error", "message": "回答中断，请重试。"}, ensure_ascii=False) + "\n"

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


# ---- 知识库管理 ----

@app.post("/v1/research/falsification")
def researchFalsification(req: HypothesisSearch):
    return searchHypothesis(req, LITERATURE_PDF_ROOT)


@app.post("/v1/research/experiment-design")
def researchExperimentDesign(req: DesignRequest):
    try:
        draft = planExperiment(req)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    context = req.context
    paperIds = context.paperIds if context else []
    fromGaps = context is not None and context.origin == "gaps" and bool(context.recordIds)
    if fromGaps and (not paperIds or not context.sourcePages or not context.conditions):
        raise HTTPException(422, "coverage records require scoped paper IDs, pages and axes")
    evidence = compareGraph.invoke({
        "question": req.question, "paperLimit": min(10, max(3, len(set(paperIds)))),
        "includeIds": paperIds or None,
        "priorityPages": {sourceId: pages for sourceId, pages in context.sourcePages.items()
                          if sourceId in paperIds} if context else {},
        "dimensions": list(context.conditions) if fromGaps else [],
        "includePageSiblings": True,
    })
    if fromGaps:
        scoped = collectPhaseRecords(evidence) + collectGroupRecords(evidence)
        verifiedIds = {item["id"] for item in scoped
                       if item["page"] in context.sourcePages.get(item["sourceId"], ())}
        if not set(context.recordIds).issubset(verifiedIds):
            raise HTTPException(422, "coverage record not found in source scope")
    proposed, basis = suggestFromEvidence(req, evidence)
    if basis:
        draft = planExperiment(proposed, sourceType="proposed")
    references = []
    for sourceId, chunks in evidence["papers"].items():
        pages = set(req.context.sourcePages.get(sourceId, ())) if req.context else set()
        quote = basis if basis and sourceId == basis["sourceId"] else None
        selected = {}
        for chunk in chunks:
            page = chunk["page"]
            if page in pages or (quote and page == quote["page"]):
                selected.setdefault(page, chunk)
                if quote and page == quote["page"] and quote["excerpt"] in chunk["evidenceText"]:
                    selected[page] = chunk
        for chunk in selected.values() or [chunks[0]]:
            references.append({
                "sourceId": sourceId, "chunkId": chunk["id"], "source": chunk["source"],
                "collection": chunk["collection"], "page": chunk["page"],
                "excerpt": quote["excerpt"] if quote and chunk["page"] == quote["page"] else chunk["evidenceText"],
            })
    return {
        **draft, "researchQuestion": req.question, "traceId": str(uuid4()), "context": req.context,
        "proposalBasis": basis,
        "references": references,
    }


@app.post("/v1/research/compare")
def researchCompare(req: ResearchCompareRequest):
    state = req.model_dump(exclude={"qaContext"})
    context = None
    if req.qaContext:
        evidenceState, context = resolveQaContext(req.qaContext)
        state.update(evidenceState)
    result = compareGraph.invoke(state)
    payload = {key: result[key] for key in (
        "status", "retrievedPaperCount", "selectedPaperCount", "verifiedPaperCount",
        "papers", "tableRecords",
    )}
    payload["groupTables"] = result.get("groupTables", {})
    payload["qaContext"] = context
    payload["thresholdComparison"] = result.get("thresholdComparison", {})
    payload["experimentalPaperCount"] = sum(bool(cells) for cells in result["tableRecords"].values())
    payload["limitations"] = [
        "表格数值对应原文实验阶段，不能直接作为抑制阈值。",
        "跨论文阈值比较还需核对响应指标、终点定义和单位口径。",
    ]
    return payload


@app.get("/v1/knowledge/stats")
def knowledge_stats():
    from app.services.knowledge_admin import knowledge_chunk_stats
    return {"ok": True, **knowledge_chunk_stats()}


@app.post("/v1/knowledge/ingest")
def knowledge_ingest(clear: bool = True, extract_literature: bool = True, _admin: None = Depends(require_admin)):
    from app.rag.ingest import ingest_all
    from app.rag.retriever import invalidate_cache
    report = ingest_all(clear_existing=clear, extract_literature=extract_literature)
    invalidate_cache()
    return report


@app.get("/v1/knowledge/collections")
def knowledge_collections():
    from app.services.knowledge_admin import list_managed_collections
    return list_managed_collections()


@app.get("/v1/knowledge/chunks")
def knowledge_list_chunks(collection: str | None = None, q: str | None = None, limit: int = Query(50, le=200), offset: int = Query(0, ge=0)):
    from app.services.knowledge_admin import list_chunks
    return list_chunks(collection=collection, q=q, limit=limit, offset=offset)


@app.get("/v1/knowledge/references")
def knowledge_list_references(collection: str | None = None, q: str | None = None, limit: int = Query(50, le=200), offset: int = Query(0, ge=0)):
    from app.services.knowledge_admin import list_references
    return list_references(collection=collection, q=q, limit=limit, offset=offset)


# ---- 管理员会话验证 ----

@app.get("/v1/admin/session", dependencies=[Depends(require_admin)])
def verify_admin_session():
    return {"ok": True}
