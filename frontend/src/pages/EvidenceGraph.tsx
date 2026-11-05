import { useRef, useState, type FormEvent } from "react";
import { apiGet, apiPost } from "../api";
import EvidenceGraphMap from "../components/EvidenceGraphMap";
import EvidenceGraphDetail from "../components/EvidenceGraphDetail";
import type { AuditContext } from "../components/auditTypes";
import type { EvolutionContext } from "../components/evolutionTypes";
import { graphRoute, kinds, relations, type GraphContext, type GraphData, type GraphEdge, type GraphNode, type GraphSummary } from "../components/evidenceGraphTypes";

function mergeItems<T extends { id: string }>(first: T[], second: T[]): T[] {
    return [...new Map([...first, ...second].map(item => [item.id, item])).values()];
}

export default function EvidenceGraph({ context, onBack, onAudit, onEvolution }: {
    context?: GraphContext; onBack: () => void; onAudit: (context: AuditContext) => void;
    onEvolution: (context: EvolutionContext) => void;
}) {
    const [question, setQuestion] = useState(context?.question ?? "");
    const [paperLimit, setPaperLimit] = useState("6");
    const [summary, setSummary] = useState<GraphSummary>();
    const [data, setData] = useState<GraphData>();
    const [selection, setSelection] = useState<GraphNode | GraphEdge>();
    const [term, setTerm] = useState("");
    const [relation, setRelation] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const detail = useRef<HTMLElement>(null);

    async function build(event: FormEvent) {
        event.preventDefault();
        if (!question.trim() || busy) return;
        setBusy(true);
        setError("");
        setSelection(undefined);
        setRelation("");
        setTerm("");
        try {
            const stats = await apiPost<GraphSummary>(graphRoute + "/build", {
                question: question.trim(), paperLimit: Number(paperLimit), paperIds: context?.paperIds ?? [], sourcePages: context?.sourcePages,
            });
            const graph = await apiGet<GraphData>(`${graphRoute}/${stats.graphId}`);
            setSummary(stats);
            setData(graph);
        } catch {
            setError("图谱构建失败，请重试。");
        } finally {
            setBusy(false);
        }
    }

    async function filter(value: string) {
        if (!summary || busy) return;
        setBusy(true);
        setError("");
        try {
            const query = value ? "?" + new URLSearchParams({ relation: value }) : "";
            setData(await apiGet<GraphData>(`${graphRoute}/${summary.graphId}${query}`));
            setRelation(value);
            setSelection(undefined);
        } catch {
            setError("关系筛选失败，请重试。");
        } finally {
            setBusy(false);
        }
    }

    async function expand(nodeId: string) {
        if (!summary || busy) return;
        setBusy(true);
        setError("");
        try {
            const query = relation ? "?" + new URLSearchParams({ relation }) : "";
            const neighbors = await apiGet<GraphData>(`${graphRoute}/${summary.graphId}/nodes/${nodeId}/neighbors${query}`);
            setData(current => current && {
                nodes: mergeItems(current.nodes, neighbors.nodes), edges: mergeItems(current.edges, neighbors.edges),
            });
        } catch {
            setError("暂时无法展开相邻关系。");
        } finally {
            setBusy(false);
        }
    }

    function pick(item: GraphNode | GraphEdge) {
        setSelection(item);
        if (window.matchMedia("(max-width: 800px)").matches) detail.current?.scrollIntoView({ block: "start" });
    }

    const matches = data?.nodes.filter(node => !term.trim() ||
        `${kinds[node.type]} ${node.label}`.toLowerCase().includes(term.trim().toLowerCase())) ?? [];
    const connected = data?.edges.filter(edge => selection && [edge.source, edge.target].includes(selection.id)) ?? [];

    return <section className="compare-workbench graph-workbench">
        <div>
            {context && <button type="button" className="citation-expand-btn" onClick={onBack}>返回文献比较</button>}
            <h1>科学证据图谱</h1>
            <p>从研究主张追到实验和原文。</p>
            {context && <p>已带入 {context.paperIds.length} 篇论文。</p>}
            <details className="workbench-inputs" open={!summary}>
                <summary>研究范围</summary>
                <form className="compare-form" onSubmit={build}>
                    <label>研究问题<textarea required maxLength={2000} value={question}
                        onChange={event => setQuestion(event.target.value)} placeholder="不同论文为何报告不同的氨抑制阈值？" /></label>
                    <label>候选论文数<input required type="number" min={2} max={10} value={paperLimit}
                        onChange={event => setPaperLimit(event.target.value)} /></label>
                    <button type="submit" className="secondary-action" disabled={busy}>构建图谱</button>
                </form>
            </details>
            {busy && <p role="status">正在处理图谱…</p>}
            {error && <p role="alert">{error}</p>}
            {summary && data && <article className="research-reading">
                <h2>证据关系</h2>
                <button type="button" className="citation-expand-btn" onClick={() => onEvolution({
                    question, graphId: summary.graphId, returnTo: "graph",
                    claimId: selection && !("target" in selection) && selection.type === "claim" ? selection.id : undefined,
                })}>查看图谱时间轴</button>
                <p>{summary.verifiedPaperCount} 篇论文 · {summary.nodeCount} 个节点 · {summary.edgeCount} 条关系</p>
                {summary.truncated && <p>已达本次构建上限。</p>}
                <div className="graph-filters">
                    <label>关系<select value={relation} disabled={busy} onChange={event => void filter(event.target.value)}>
                        <option value="">全部关系</option>
                        {Object.entries(relations).map(([value,label]) => <option key={value} value={value}>{label}</option>)}
                    </select></label>
                    <label>搜索当前子图<input value={term} onChange={event => setTerm(event.target.value)} /></label>
                </div>
                {data.nodes.length ? <EvidenceGraphMap data={data} selected={selection} onPick={pick} /> : <p>当前范围没有匹配节点。</p>}
                <details className="graph-node-list" open={term.trim() ? true : undefined}>
                    <summary>节点索引 · {matches.length} 项</summary>
                    <ul>{matches.map(node => <li key={node.id}><button type="button" className="citation-expand-btn"
                        aria-pressed={selection?.id === node.id} onClick={() => pick(node)}>{kinds[node.type]} · {node.label}</button></li>)}</ul>
                </details>
            </article>}
        </div>
        <aside ref={detail} aria-label="图谱证据">
            <h2>关系与原文</h2>
            <EvidenceGraphDetail item={selection} connected={connected} onExpand={nodeId => void expand(nodeId)} onEdge={pick}
                onAudit={summary && selection ? () => onAudit({
                    target: { type: "target" in selection ? "relation" : "claim", graphId: summary.graphId, entityId: selection.id },
                    label: "target" in selection ? relations[selection.type] : selection.label, returnTo: "graph",
                }) : undefined} />
        </aside>
    </section>;
}
