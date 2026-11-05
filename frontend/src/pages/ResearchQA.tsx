import { useCallback, useEffect, useRef, useState } from "react";
import readingBook from "../assets/reading-book.svg";
import literatureChart from "../assets/literature-chart.png";
import literaturePathways from "../assets/literature-pathways.png";
import literatureInocula from "../assets/literature-inocula.png";
import Icon from "../components/Icon";
import ChatHistory from "../components/ChatHistory";
import { apiPostStream } from "../api";
import CitationVisuals from "../components/CitationVisuals";
import MarkdownBody from "../components/MarkdownBody";
import { qaCompareContext, type QaCompareContext } from "../components/qaCompareContext";

interface ResearchChunk {
    chunk_id: number;
    title: string;
    source: string;
    collection: string;
    citation: string;
    page: number | null;
    snippet: string;
    score: number;
}

interface ResearchQAResponse {
    ok: boolean;
    answer: string;
    citations: string[];
    chunks: ResearchChunk[];
    trace_id: string;
    agent_id: string;
    runtime: {
        answer_mode: string;
        provider: string;
        model: string | null;
        knowledge_hits: number;
        qa_ready: boolean;
    };
}

const TIMEOUT_MS = 60000;

const COLLECTION_LABEL: Record<string, string> = {
    literature_inhibition: "抑制研究",
    literature_theory: "理论研究",
    literature_engineering: "工程应用",
};

function makeRefLinksClickable(container: HTMLElement) {
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    const textNodes: Text[] = [];
    while (walker.nextNode()) {
        textNodes.push(walker.currentNode as Text);
    }
    for (const node of textNodes) {
        const text = node.textContent || "";
        if (!/\[\d+\]/.test(text) || node.parentElement?.closest("a, button, code, pre")) continue;
        const frag = document.createDocumentFragment();
        let last = 0;
        const re = /\[(\d+)\]/g;
        let match: RegExpExecArray | null;
        while ((match = re.exec(text)) !== null) {
            if (match.index > last) {
                frag.appendChild(document.createTextNode(text.slice(last, match.index)));
            }
            const target = document.getElementById(`ref-${Number(match[1])}`);
            if (target) {
                const link = document.createElement("button");
                link.type = "button";
                link.className = "inline-ref";
                link.dataset.ref = match[1];
                link.setAttribute("aria-label", `查看文献证据 ${match[1]}`);
                link.textContent = match[0];
                frag.appendChild(link);
            } else {
                frag.appendChild(document.createTextNode(match[0]));
            }
            last = re.lastIndex;
        }
        if (last < text.length) {
            frag.appendChild(document.createTextNode(text.slice(last)));
        }
        if (frag.childNodes.length > 0) {
            node.parentNode?.replaceChild(frag, node);
        }
    }
}

const HISTORY_KEY = "firefairy-chat-history-v1";

interface ChatTurn {
    question: string;
    response: ResearchQAResponse;
}

interface SavedChat extends ChatTurn {
    id: string;
    title: string;
    previous?: ChatTurn[];
}

interface RunningChat {
    id: string;
    title: string;
    question: string;
    controller: AbortController;
    previous: ChatTurn[];
    draft: string;
    chunks: ResearchChunk[] | null;
}

function loadHistory(): SavedChat[] {
    try {
        const data = JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "[]");
        if (!Array.isArray(data)) return [];
        return data.filter((entry) => entry && typeof entry.id === "string" && typeof entry.title === "string"
            && typeof entry.question === "string" && typeof entry.response?.answer === "string"
            && Array.isArray(entry.response.chunks) && entry.response.runtime);
    } catch {
        return [];
    }
}

export default function ResearchQA({ historyOpen, closeHistory, onCompare }: {
    historyOpen: boolean;
    closeHistory: () => void;
    onCompare: (context: QaCompareContext) => void;
}) {
    const [history, setHistory] = useState(loadHistory);
    const [activeId, setActiveId] = useState<string | null>(null);
    const [runningItems, setRunningItems] = useState<{ id: string; title: string; running: true }[]>([]);
    const runningChats = useRef(new Map<string, RunningChat>());
    const selectedChat = useRef<string | null>(null);
    const [historyWarning, setHistoryWarning] = useState(false);
    const initialHistory = useRef(history);
    useEffect(() => {
        if (history === initialHistory.current) return;
        try {
            localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
            setHistoryWarning(false);
        } catch {
            setHistoryWarning(true);
        }
    }, [history]);
    const [input, setInput] = useState("");
    const [question, setQuestion] = useState("");
    const [previousTurns, setPreviousTurns] = useState<ChatTurn[]>([]);
    const [evidenceOpen, setEvidenceOpen] = useState(false);
    const [evidenceTurn, setEvidenceTurn] = useState<number | null>(null);
    const [retrievedChunks, setRetrievedChunks] = useState<ResearchChunk[] | null>(null);
    const [loading, setLoading] = useState(false);
    const [draft, setDraft] = useState("");
    const [response, setResponse] = useState<ResearchQAResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [stopped, setStopped] = useState(false);
    const [topK, setTopK] = useState(5);
    const [expandedChunks, setExpandedChunks] = useState<Set<number>>(new Set());
    const answerRef = useRef<HTMLDivElement>(null);
    const conversationRef = useRef<HTMLDivElement>(null);
    const evidenceRef = useRef<HTMLDivElement>(null);
    const followTail = useRef(true);
    useEffect(() => {
        const conversation = conversationRef.current;
        if (conversation && followTail.current) conversation.scrollTop = conversation.scrollHeight;
    }, [draft, response, question, loading]);
    useEffect(() => {
        if (evidenceRef.current) evidenceRef.current.scrollTop = 0;
    }, [evidenceTurn]);
    useEffect(() => {
        const requests = runningChats.current;
        return () => requests.forEach(({ controller }) => controller.abort());
    }, []);

    const scrollToRef = useCallback((refIndex: number) => {
        setEvidenceTurn(null);
        setEvidenceOpen(true);
        requestAnimationFrame(() => {
            const card = document.getElementById(`ref-${refIndex}`);
            card?.focus({ preventScroll: true });
            card?.scrollIntoView({ block: "nearest" });
        });
    }, []);

    useEffect(() => {
        const container = answerRef.current;
        if (!container || !response) return;
        const timer = setTimeout(() => makeRefLinksClickable(container), 100);
        const onClick = (e: MouseEvent) => {
            const target = e.target as HTMLElement;
            const refEl = target.closest(".inline-ref");
            if (refEl) {
                const num = parseInt(refEl.getAttribute("data-ref") || "", 10);
                if (num > 0) scrollToRef(num);
            }
        };
        container.addEventListener("click", onClick);
        return () => {
            clearTimeout(timer);
            container.removeEventListener("click", onClick);
        };
    }, [response, scrollToRef]);

    const ask = useCallback(async () => {
        const q = input.trim();
        if (!q || runningChats.current.has(selectedChat.current ?? "")) return;
        const saved = history.find((entry) => entry.id === selectedChat.current);
        const id = saved?.id ?? crypto.getRandomValues(new Uint32Array(4)).join("-");
        const previous = saved ? [...(saved.previous ?? []), { question: saved.question, response: saved.response }] : [];
        const controller = new AbortController();
        const chat: RunningChat = { id, title: saved?.title ?? q.slice(0, 100), question: q, controller, previous, draft: "", chunks: null };
        runningChats.current.set(id, chat);
        setRunningItems((items) => [{ id, title: chat.title, running: true }, ...items]);
        selectedChat.current = id;
        setActiveId(id);
        setQuestion(q);
        setPreviousTurns(previous);
        followTail.current = true;
        setEvidenceTurn(null);
        setEvidenceOpen(true);
        setRetrievedChunks(null);
        setExpandedChunks(new Set());
        setLoading(true);
        setError(null);
        setStopped(false);
        setResponse(null);
        setDraft("");

        const isSelected = () => selectedChat.current === id;
        const onTimeout = () => {
            if (controller.signal.aborted) return;
            controller.abort();
            if (isSelected()) setError("等待模型响应超过 60 秒，请稍后重试。");
        };
        let timer = setTimeout(onTimeout, TIMEOUT_MS);
        const resetTimer = () => {
            clearTimeout(timer);
            timer = setTimeout(onTimeout, TIMEOUT_MS);
        };

        try {
            const result = await apiPostStream<ResearchQAResponse, ResearchChunk>("/v1/research/qa/stream", {
                question: q,
                top_k: topK,
                history: previous.slice(-4).map((turn) => ({
                    question: turn.question.slice(0, 1000),
                    answer: turn.response.answer.slice(0, 4000),
                })),
            }, controller.signal, (text) => {
                if (controller.signal.aborted) return;
                resetTimer();
                chat.draft += text;
                if (isSelected()) setDraft(chat.draft);
            }, (chunks) => {
                if (controller.signal.aborted) return;
                resetTimer();
                chat.chunks = chunks;
                if (isSelected()) setRetrievedChunks(chunks);
            });
            if (!controller.signal.aborted) {
                setHistory((items) => [{ id, title: chat.title, question: q, response: result, previous }, ...items.filter((item) => item.id !== id)]);
                if (isSelected()) {
                    setResponse(result);
                    setInput("");
                }
            }
        } catch (error) {
            if (!controller.signal.aborted && isSelected()) {
                const message = (error as Error).message || "请求失败";
                setError(message.includes("Failed to fetch") ? "无法连接后端服务，请确认服务已启动。" : message);
            }
        } finally {
            clearTimeout(timer);
            runningChats.current.delete(id);
            setRunningItems((items) => items.filter((item) => item.id !== id));
            if (isSelected()) {
                setDraft("");
                setLoading(false);
            }
        }
    }, [history, input, topK]);

    const openChat = (id: string | null, dismissHistory = true) => {
        const running = id ? runningChats.current.get(id) : undefined;
        const saved = history.find((entry) => entry.id === id);
        selectedChat.current = id;
        setActiveId(id);
        setInput(running?.question ?? "");
        setQuestion(running?.question ?? saved?.question ?? "");
        setPreviousTurns(running?.previous ?? saved?.previous ?? []);
        setResponse(running ? null : saved?.response ?? null);
        followTail.current = true;
        setEvidenceTurn(null);
        setEvidenceOpen(Boolean(running || saved?.response.chunks.length));
        setRetrievedChunks(running?.chunks ?? null);
        setExpandedChunks(new Set());
        setDraft(running?.draft ?? "");
        setLoading(Boolean(running));
        setStopped(false);
        setError(null);
        if (dismissHistory && !window.matchMedia("(min-width: 1240px)").matches) closeHistory();
    };

    const toggleChunk = (id: number) => {
        setExpandedChunks((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id); else next.add(id);
            return next;
        });
    };

    const getPdfUrl = (chunk: ResearchChunk) => {
        const filename = encodeURIComponent(chunk.source || "");
        const page = chunk.page || 1;
        const col = encodeURIComponent(chunk.collection || "literature_inhibition");
        return `/api/v1/research/literature/${filename}?collection=${col}#page=${page}`;
    };

    const evidenceChunks = evidenceTurn === null
        ? response?.chunks ?? retrievedChunks
        : previousTurns[evidenceTurn]?.response.chunks;
    const viewingPendingEvidence = evidenceTurn === null && loading;
    const showEvidenceTurn = (turn: number | null) => {
        setEvidenceTurn(turn);
        setEvidenceOpen(true);
        setExpandedChunks(new Set());
    };
    return (
        <div className={`research-qa-body ${question ? "has-turn" : "chat-empty"} ${evidenceOpen ? "has-evidence" : ""}`}>
            <ChatHistory open={historyOpen} items={[...runningItems, ...history.filter((item) => !runningItems.some((running) => running.id === item.id))]} activeId={activeId} onClose={closeHistory}
                onNew={() => openChat(null)}
                onOpen={openChat}
                onRename={(id, title) => {
                    const running = runningChats.current.get(id);
                    if (running) {
                        running.title = title;
                        setRunningItems((items) => items.map((item) => item.id === id ? { ...item, title } : item));
                    } else {
                        setHistory((items) => items.map((item) => item.id === id ? { ...item, title } : item));
                    }
                }}
                onDelete={(id) => {
                    runningChats.current.get(id)?.controller.abort();
                    setHistory((items) => items.filter((item) => item.id !== id));
                    if (activeId === id) openChat(null, false);
                }}
            />
            <div className="research-primary">
                {historyWarning && <p className="research-note" role="status">浏览器无法保存聊天记录。</p>}
                {!question && <header className="research-intro">
                    <h1>你想<span className="gradient-heading">查什么？</span></h1>
                    <p className="research-scope">58 篇厌氧消化文献</p>
                </header>}
                {question && <div className="conversation-scroll" ref={conversationRef} aria-label="对话内容" tabIndex={0}
                    onScroll={(event) => {
                        const panel = event.currentTarget;
                        followTail.current = panel.scrollHeight - panel.scrollTop - panel.clientHeight < 48;
                    }}>
                    {previousTurns.map((turn, index) => (
                        <div className="previous-turn" key={index}>
                            <div className="question-turn"><span>你的问题</span><p>{turn.question}</p></div>
                            <section className="research-result" aria-label={`第 ${index + 1} 轮研究回答`}>
                                <MarkdownBody className="research-answer" text={turn.response.answer} citations={turn.response.chunks} />
                                {qaCompareContext(turn.question, turn.response) && <button type="button" className="citation-expand-btn"
                                    onClick={() => onCompare(qaCompareContext(turn.question, turn.response)!)}>比较这轮文献</button>}
                                {turn.response.chunks.length > 0 && (
                                    <button type="button" className="previous-sources" onClick={() => showEvidenceTurn(index)}>
                                        看第 {index + 1} 轮证据
                                    </button>
                                )}
                            </section>
                        </div>
                    ))}
                    {question && <div className="question-turn"><span>你的问题</span><p>{question}</p></div>}
                    {error && <p className="research-error" role="alert"><Icon name="alert" />{error}</p>}
                    {stopped && !loading && <p className="research-note" role="status">已停止生成。可以修改问题后再试。</p>}
                    {(loading || response) && (
                        <section className="research-result" aria-label="科研回答" ref={answerRef}>
                            {(draft || response) && <MarkdownBody className="research-answer" text={response?.answer ?? draft} citations={response?.chunks ?? retrievedChunks ?? undefined} />}
                            {loading && (
                                <div className="research-loading">
                                    <span role="status"><Icon name="loader" className="spin" />{draft ? "正在生成回答…" : "正在检索文献…"}</span>
                                </div>
                            )}
                            {response && !loading && qaCompareContext(question, response) && <button type="button"
                                className="citation-expand-btn" onClick={() => onCompare(qaCompareContext(question, response)!)}>
                                <Icon name="book" size={16} /> 比较本轮文献
                            </button>}
                            {response && (
                                <details className="research-details">
                                    <summary>回答详情</summary>
                                    <div className="research-meta">
                                    <span>{response.runtime.model || "原文摘录模式"}</span>
                                    <span>命中 {response.runtime.knowledge_hits} 条分块</span>
                                    <span title="执行追踪编号">追踪 {response.trace_id}</span>
                                    </div>
                                </details>
                            )}
                        </section>
                    )}
                </div>}
                <form className="research-composer" data-running={loading} onSubmit={(event) => {
                    event.preventDefault();
                    void ask();
                }}>
                    <label className="composer-label" htmlFor="research-question">你的研究问题</label>
                    <textarea
                        id="research-question"
                        className="research-input"
                        rows={question ? 1 : 3}
                        enterKeyHint="send"
                        value={input}
                        placeholder={question ? "接着问…" : "写下你想查的问题…"}
                        onChange={(event) => setInput(event.target.value)}
                        onKeyDown={(event) => {
                            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                                event.preventDefault();
                                void ask();
                            }
                        }}
                        disabled={loading}
                    />
                    <div className="research-controls">
                        <label className="topk-label">
                            <Icon name="book" size={16} />
                            <select aria-label="要找几条证据" value={topK} disabled={loading}
                                onChange={(event) => setTopK(Number(event.target.value))}>
                                {[1, 2, 3, 4, 5, 6, 7, 8].map((count) => (
                                    <option key={count} value={count}>{count} 条证据</option>
                                ))}
                            </select>
                            <Icon name="chevron" size={14} />
                        </label>
                        {loading ? (
                            <button key="stop" type="button" className="research-send-btn research-stop-btn"
                                aria-label="停止生成" title="停止生成" onClick={() => {
                                    runningChats.current.get(selectedChat.current ?? "")?.controller.abort();
                                    setStopped(true);
                                }}>
                                <span aria-hidden="true" />
                            </button>
                        ) : (
                            <button key="send" type="submit" className="research-send-btn" disabled={!input.trim()}>
                                查文献 <Icon name="send" size={17} />
                            </button>
                        )}
                    </div>
                </form>
                {!question && (
                    <section className="reading-index" aria-labelledby="reading-index-title">
                        <div className="reading-index-heading">
                            <h2 id="reading-index-title"><Icon name="book" size={17} /> 翻阅索引</h2>
                            <span>选一个问题开始</span>
                        </div>
                        {[
                            ["抑制", "游离氨如何抑制产甲烷？"],
                            ["机理", "产甲烷有哪几条路径？"],
                            ["工程", "哪些底物更容易产甲烷？"],
                        ].map(([topic, example], index) => (
                            <button key={topic} className="example-question" type="button" onClick={() => {
                                setInput(example);
                                document.getElementById("research-question")?.focus();
                            }}>
                                <span className="example-index">0{index + 1}</span>
                                <span className="example-topic">{topic}</span>
                                <span>{example}</span>
                                <Icon name="external" size={15} />
                            </button>
                        ))}
                    </section>
                )}
                {!question && (
                    <section className="literature-plates" aria-label="文献图表样张">
                        <div className="notebook-spread" aria-hidden="true"><span /><span /></div>
                        <img className="notebook-reader" src={readingBook} alt="" width={642} height={598} />
                        <figure className="notebook-clipping notebook-clipping-top">
                            <img src={literatureChart} alt="研究笔记装饰纸页" width={599} height={384} />
                        </figure>
                        <figure className="notebook-clipping notebook-main">
                            <img src={literaturePathways} alt="研究笔记装饰纸页" width={788} height={636} />
                        </figure>
                        <figure className="notebook-clipping notebook-clipping-bottom">
                            <img src={literatureInocula} alt="研究笔记装饰纸页" width={769} height={144} />
                        </figure>
                        <p className="notebook-note">三条路径，哪条更常见？</p>
                    </section>
                )}
            </div>
            <aside hidden={!question} className="research-evidence" aria-labelledby="evidence-title">
                <div className="evidence-heading">
                    <h2 id="evidence-title">文献证据</h2>
                    <button type="button" className="evidence-toggle citation-expand-btn" aria-expanded={evidenceOpen}
                        aria-controls="chat-evidence" onClick={() => setEvidenceOpen(!evidenceOpen)}>
                        {evidenceOpen ? "收起证据" : "展开证据"} <Icon name="chevron" size={15} />
                    </button>
                </div>
                <div id="chat-evidence" className="evidence-content" hidden={!evidenceOpen}>
                    <span className="evidence-status" role="status">{evidenceChunks ? `${evidenceChunks.length} 条` : viewingPendingEvidence ? "正在查文献" : "未完成"}</span>
                    {previousTurns.length > 0 && (
                        <label className="evidence-turn-picker">
                            查看证据
                            <select value={evidenceTurn ?? "current"} onChange={(event) => showEvidenceTurn(
                                event.target.value === "current" ? null : Number(event.target.value)
                            )}>
                                <option value="current">本轮</option>
                                {previousTurns.map((_, index) => <option key={index} value={index}>第 {index + 1} 轮</option>)}
                            </select>
                        </label>
                    )}
                    <div className="evidence-scroll" aria-label="证据列表" tabIndex={0} ref={evidenceRef}>
                        {!evidenceChunks?.length && (
                            <p className="evidence-empty">
                                {evidenceChunks ? "这次没找到可引用的文献。" : viewingPendingEvidence ? "找到的原文会先显示在这里。" : "本次检索未完成。"}
                            </p>
                        )}
                        {evidenceChunks?.map((chunk, index) => {
                            const isExpanded = expandedChunks.has(chunk.chunk_id);
                            const pdfUrl = getPdfUrl(chunk);
                            const refId = `ref-${index + 1}`;
                            return (
                                <article key={chunk.chunk_id} id={refId} tabIndex={-1} className="research-citation-card">
                                    <span className="citation-ref-num">[{index + 1}]</span>
                                    <h3>{chunk.title || chunk.source}</h3>
                                    <div className="citation-label">
                                        <span>{COLLECTION_LABEL[chunk.collection] || chunk.collection}</span>
                                        {chunk.page != null && <span>第 {chunk.page} 页</span>}
                                    </div>
                                    {chunk.title && chunk.title !== chunk.source && (
                                        <p className="citation-source">{chunk.source}</p>
                                    )}
                                    <div className="citation-card-actions">
                                        <button type="button" className="citation-expand-btn" aria-expanded={isExpanded}
                                            aria-controls={`${refId}-detail`} onClick={() => toggleChunk(chunk.chunk_id)}>
                                            {isExpanded ? "收起摘录" : "看摘录"} <Icon name="chevron" size={15} />
                                        </button>
                                        <a href={pdfUrl} target="_blank" rel="noopener noreferrer" className="citation-pdf-link"
                                            aria-label={`打开 ${chunk.source} PDF 第 ${chunk.page || 1} 页`}>
                                            看原文 <Icon name="external" size={15} />
                                        </a>
                                    </div>
                                    <div id={`${refId}-detail`} hidden={!isExpanded} className="citation-card-snippet">
                                        {isExpanded && <>
                                            <p>{chunk.snippet || "暂无原文片段"}</p>
                                            {chunk.page != null && <CitationVisuals chunkId={chunk.chunk_id} pdfUrl={pdfUrl} />}
                                        </>}
                                    </div>
                                </article>
                            );
                        })}
                    </div>
                </div>
            </aside>
        </div>
    );
}
