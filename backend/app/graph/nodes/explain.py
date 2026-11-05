"""科研问答节点：文献检索 + DeepSeek 生成 + 降级模板回答。"""
import re
from collections.abc import AsyncIterator
from contextlib import aclosing

from starlette.concurrency import run_in_threadpool

from app.agents.project_recorder import EventCategory, recorder
from app.config import settings
from app.graph.state import ResearchState
from app.llm.provider import OpenAICompatibleProvider, get_llm_provider
from app.observability.logging_config import get_logger
from app.services.agent_prompts import render_agent_prompt
from app.services.reported_outcomes import extractReportedOutcomes
from app.services.answer_citations import validateAnswer
from app.rag.retriever import QUERY_ALIASES, get_all_chunks, retrieve
from app.rag.named_visual_retrieval import completeNamedVisualEvidence
from app.rag.media_search import explicitLocalVisual
from app.rag.qa_query import includeMethods, namedPaperIds, searchQuestion

logger = get_logger("graph.explain")


def _localResultSummary(question: str, chunks: list[dict]) -> list[str]:
    terms = {"ammonia": "氨", "relative abundance": "相对丰度", "methane production": "甲烷产量"}
    query = _expandedQuestion(question)
    asksSignificance = re.search(r"显著|\bsignificant\b", query)
    lines = []
    for index, chunk in enumerate(chunks, start=1):
        if not chunk.get("source_id") or not chunk.get("page"):
            continue
        location = f'第 {chunk["page"]} 页 [{index}]'
        for record in extractReportedOutcomes([{**chunk, "evidenceText": chunk.get("text") or ""}]):
            if asksSignificance and not _matchesOutcome(record, query):
                continue
            metric = terms.get(record["metric"].casefold(), record["metric"])
            if record["qualifier"] == "no_significant_effect":
                endpoint = terms.get(record["endpoint"].casefold(), record["endpoint"])
                summary = f'在论文测试的{metric}水平下，{record["group"]} 的{endpoint}未见显著变化（{record["value"]}）。'
            else:
                summary = f'该实验报告{metric}浓度为 {record["value"]} {record["unit"]} 时，达到 {record["endpoint"]}。'
            lines.append(f"{summary} {location}。")
        if len(lines) >= 3:
            break
    return lines[:3]


def _research_template_answer(question: str, chunks: list[dict]) -> str:
    if not chunks:
        return (
            f"### 研究结论\n针对「{question}」，本库未检索到命中分块，无法给出有原文依据的结论。\n\n"
            "### 文献证据对照\n无命中文献，未引用任何编号。\n\n"
            "### 机理与差异解释\n此处为模型推断：请调整关键词或改用更具体的研究边界后重试检索。\n\n"
            "### 证据局限\n以上为模型提示，不代表本库存在对应文献，未编造论文、DOI、作者或数值。"
        )
    summary = _localResultSummary(question, chunks) if re.search(r"[\u3400-\u9fff]", question) else []
    if not summary:
        summary = [f"本次检索到 {len(chunks)} 条分块。以下为原文摘录，具体结论需核对全文。"]
    lines = ["### 研究结论", *summary, "### 文献证据对照"]
    for i, c in enumerate(chunks, start=1):
        citation = c.get("citation") or c.get("source", "")
        text = (c.get("text") or "").strip().replace("\n", " ")
        lines.append(f"[{i}]（{citation}）{text[:220]}{'…' if len(text) > 220 else ''}")
    if match := explicitLocalVisual(question, chunks):
        index, visual = match
        label = "图" if visual["kind"] == "figure" else "表"
        lines.append(f'原文图表 [{index}]（{label} {visual["number"]}）\n\n{visual["caption"]}')
    lines.append("### 机理与差异解释\n以上为原文直接摘录，未做跨文献机理推断。")
    lines.append("### 证据局限\n本模式未调用外部大模型，仅整理明确报告的结果和原文摘录；页码与出处以 citation 标注为准，未推测文献元数据。")
    return "\n\n".join(lines)


def _expandedQuestion(question: str) -> str:
    normalized = question.casefold()
    aliases = [term for label, terms in QUERY_ALIASES.items() if label in normalized for term in terms]
    return " ".join([normalized, *aliases])


def _matchesOutcome(record: dict, terms: str) -> bool:
    return all(re.search(rf"\b{re.escape(record[field].casefold())}\b", terms)
               for field in ("metric", "endpoint"))


def _focusOnReportedResult(question: str, chunks: list[dict], collections: list[str], limit: int) -> list[dict]:
    terms = _expandedQuestion(question)
    if not re.search(r"显著|\bsignificant\b", terms):
        return chunks
    focused = []
    for chunk in get_all_chunks():
        if chunk["collection"] not in collections or not chunk.get("page"):
            continue
        text = chunk["text"] or ""
        if "no significant effect" not in " ".join(text.casefold().split()):
            continue
        for record in extractReportedOutcomes([{**chunk, "evidenceText": text}]):
            if _matchesOutcome(record, terms):
                focused.append(chunk)
                break
    focusedIds = {chunk["id"] for chunk in focused}
    return (focused + [chunk for chunk in chunks if chunk["id"] not in focusedIds])[:limit]


def _retrieve_evidence(state: ResearchState) -> ResearchState:
    question = state.get("question") or state.get("rag_query") or ""
    collections = state.get("rag_collections") or ["literature_inhibition", "literature_theory", "literature_engineering"]

    history = state.get("history") or []
    query = question
    if history and re.match(r"^\s*(那|那么|这些|这个|它|上述|what about\b|and what\b)", question, re.IGNORECASE):
        query = " ".join([turn["question"] for turn in history] + [question])
    namedIds = namedPaperIds(query, get_all_chunks())
    chunks = retrieve(
        query,
        search_query=searchQuestion(query),
        top_k=state.get("rag_top_k") or settings.rag_top_k,
        collections=collections,
        source_ids=namedIds,
    )
    limit = state.get("rag_top_k") or settings.rag_top_k
    chunks = _focusOnReportedResult(query, chunks, collections, limit)
    if namedIds is not None:
        chunks = [chunk for chunk in chunks if chunk.get("source_id") in namedIds]
    chunks = includeMethods(chunks, get_all_chunks(), limit)
    chunks = completeNamedVisualEvidence(question, chunks, limit)
    citations = [c.get("citation") or c.get("source", "") for c in chunks]
    recorder.record(
        EventCategory.RAG,
        "research_retrieve",
        "Research evidence retrieved",
        trace_id=state.get("trace_id"),
        detail={"hits": len(chunks), "sources": citations[:5]},
    )

    return {**state, "rag_chunks": chunks, "citations": citations}


def _research_messages(state: ResearchState) -> list[dict]:
    chunks = state["rag_chunks"]
    question = state.get("question") or state.get("rag_query") or ""
    agent_id = state.get("agent_id") or "research"
    reference_context = "\n\n".join(
        f"[{i+1}] ({c.get('citation') or c.get('source', '')}) {c['text']}" for i, c in enumerate(chunks)
    )
    context = (
        f"参考资料：\n{reference_context}" if reference_context else "资料状态：本次未命中任何文献分块，请如实说明并禁止编造论文与数值。"
    )

    system = render_agent_prompt(agent_id, "system/research_guardrails")
    history = state.get("history") or []
    messages = []
    if history:
        system += "\n历史问答只用于理解当前问题。历史回答中的引用编号不属于本轮，引用只能依据本轮检索资料。"
        for turn in history:
            messages.extend([
                {"role": "user", "content": turn["question"]},
                {"role": "assistant", "content": turn["answer"]},
            ])
    return [
        {"role": "system", "content": system},
        *messages,
        {"role": "user", "content": render_agent_prompt(agent_id, "tasks/research_qa", question=question, context=context)},
    ]


def _template_result(state: ResearchState, *, fallback: bool = False) -> ResearchState:
    chunks = state["rag_chunks"]
    question = state.get("question") or state.get("rag_query") or ""
    mode = "template_with_references" if chunks else "template_no_references"
    return {
        **state,
        "narrative": _research_template_answer(question, chunks),
        "answer_mode": "template_fallback" if fallback else mode,
    }


def _model_result(state: ResearchState, narrative: str) -> ResearchState:
    chunks = state["rag_chunks"]
    recorder.record(
        EventCategory.LLM,
        "research_qa_complete",
        f"model={settings.llm_model}",
        trace_id=state.get("trace_id"),
        detail={"chars": len(narrative), "knowledge_hits": len(chunks)},
    )
    return {
        **state,
        "narrative": narrative,
        "answer_mode": "model_with_references" if chunks else "model_general",
    }


def research_qa_node(state: ResearchState) -> ResearchState:
    state = _retrieve_evidence(state)
    provider = get_llm_provider()
    if not settings.use_llm or not isinstance(provider, OpenAICompatibleProvider):
        return _template_result(state)

    messages = _research_messages(state)
    try:
        narrative = provider.complete(
            messages,
            temperature=0.3,
            max_tokens=settings.llm_max_tokens_qa,
        )
        narrative = validateAnswer(narrative, len(state["rag_chunks"]), messages,
                                   lambda revised: provider.complete(revised, temperature=0,
                                                                    max_tokens=settings.llm_max_tokens_qa))
    except Exception as exc:
        logger.warning("Research QA LLM call failed (%s), using local evidence", type(exc).__name__)
        recorder.record(
            EventCategory.ERROR,
            "research_qa_llm_failed",
            type(exc).__name__,
            trace_id=state.get("trace_id"),
            level="error",
        )
        result = _template_result(state, fallback=True)
        result["warnings"] = (state.get("warnings") or []) + ["科研问答外部模型调用失败，已降级为原文摘录回答"]
        return result
    return _model_result(state, narrative)


async def stream_research_qa(state: ResearchState) -> AsyncIterator[str | ResearchState]:
    state = await run_in_threadpool(_retrieve_evidence, state)
    yield state
    provider = get_llm_provider()
    if not settings.use_llm or not isinstance(provider, OpenAICompatibleProvider):
        yield await run_in_threadpool(_template_result, state)
        return

    parts: list[str] = []
    messages = _research_messages(state)
    try:
        async with aclosing(provider.stream(messages, temperature=0.3, max_tokens=settings.llm_max_tokens_qa)) as stream:
            async for text in stream:
                parts.append(text)
                yield text
        if not parts:
            raise RuntimeError("empty model stream")
        narrative = await run_in_threadpool(
            validateAnswer, "".join(parts), len(state["rag_chunks"]), messages,
            lambda revised: provider.complete(revised, temperature=0, max_tokens=settings.llm_max_tokens_qa),
        )
    except Exception as exc:
        logger.warning("Research QA stream failed (%s)", type(exc).__name__)
        if parts:
            raise
        yield await run_in_threadpool(_template_result, state, fallback=True)
        return
    yield await run_in_threadpool(_model_result, state, narrative)
