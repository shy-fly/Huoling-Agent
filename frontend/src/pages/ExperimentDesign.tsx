import { useState, type FormEvent } from "react";
import { apiPost, getPdfUrl } from "../api";
import type { EvolutionContext } from "../components/evolutionTypes";

type Reference = Parameters<typeof getPdfUrl>[0] & { sourceId: string; chunkId: number; excerpt: string };
type Draft = {
    proposalBasis: { rationale: string; page: number } | null;
    designType: string; combinationCount: number; totalExperimentalUnits: number | null;
    groups: { id: string; levels: Record<string, string>; isControl: boolean }[];
    hypotheses: { null: string | null; alternative: string | null };
    exceedsLimit: boolean; pending: string[]; statisticalPlan: string; references: Reference[];
};

export type DesignContext = {
    origin: "compare" | "falsification" | "gaps";
    question: string;
    paperIds: string[];
    recordIds?: string[];
    sourcePages?: Record<string, number[]>;
    conditions?: Record<string, string>;
};

export function designSourcePages(records: { sourceId: string; page: number }[]) {
    const pages: Record<string, number[]> = Object.create(null);
    for (const { sourceId, page } of records) {
        const current = (pages[sourceId] ??= []);
        if (!current.includes(page)) current.push(page);
    }
    return pages;
}

export default function ExperimentDesign({ context, onEvolution }: {
    context?: DesignContext; onEvolution: (context: EvolutionContext) => void;
}) {
    const [question, setQuestion] = useState(context?.question ?? "");
    const [factor, setFactor] = useState("");
    const [levels, setLevels] = useState("");
    const [control, setControl] = useState("");
    const [outcome, setOutcome] = useState("");
    const [replicates, setReplicates] = useState("");
    const [maxUnits, setMaxUnits] = useState("");
    const [draft, setDraft] = useState<Draft>();
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");

    async function submit(event: FormEvent) {
        event.preventDefault();
        setDraft(undefined);
        setBusy(true);
        setError("");
        try {
            setDraft(await apiPost<Draft>("/v1/research/experiment-design", {
                question: question.trim(), outcome: outcome.trim(), context,
                factors: factor.trim() ? [{ name: factor.trim(), levels: levels.split(/[,，]/).map(value => value.trim()) }] : [],
                control: factor.trim() && control.trim() ? { [factor.trim()]: control.trim() } : null,
                replicates: replicates ? Number(replicates) : null, maxUnits: maxUnits ? Number(maxUnits) : null,
            }));
        } catch {
            setError("生成失败。请检查因素水平和对照设置。");
        } finally {
            setBusy(false);
        }
    }

    return <section className="compare-workbench design-workbench">
        <div>
            <h1>智能实验设计</h1>
            <p className="design-lead">先拟草案，再核对文献和实验条件。</p>
            {context && <p>已带入 {context.paperIds.length} 篇论文、{context.recordIds?.length ?? 0} 条记录。
                {Object.entries(context.conditions ?? {}).map(([key,value]) => ` ${key} ${value}`).join(" · ")}</p>}
            <details className="workbench-inputs" open={!draft}>
                <summary>研究问题与实验条件</summary>
                <form className="compare-form" onSubmit={submit}>
                    <label>研究问题<textarea required maxLength={2000} value={question} onChange={e => setQuestion(e.target.value)} /></label>
                    <label>因素<input value={factor} onChange={e => setFactor(e.target.value)} /></label>
                    <label>水平（逗号分隔）<input value={levels} onChange={e => setLevels(e.target.value)} /></label>
                    <label>基准对照水平<input value={control} onChange={e => setControl(e.target.value)} /></label>
                    <label>主要响应<input value={outcome} onChange={e => setOutcome(e.target.value)} /></label>
                    <label>每组独立重复<input type="number" min="1" max="30" value={replicates} onChange={e => setReplicates(e.target.value)} /></label>
                    <label>实验单位上限<input type="number" min="1" max="1000" value={maxUnits} onChange={e => setMaxUnits(e.target.value)} /></label>
                    <button className="secondary-action" disabled={busy}>生成草案</button>
                </form>
            </details>
            {busy && <p role="status">正在核对文献和生成矩阵…</p>}
            {error && <p role="alert">{error}</p>}
            {draft && <article className="research-reading design-draft">
                <header>
                    <span>实验草案</span>
                    <h2>{question}</h2>
                    <p>{draft.combinationCount} 个组合 · {draft.totalExperimentalUnits ?? "待定"} 个实验单位</p>
                </header>
                {draft.references.length > 0 && <button type="button" className="citation-expand-btn"
                    onClick={() => onEvolution({ question, paperIds: [...new Set(draft.references.map(ref => ref.sourceId))],
                        returnTo: "design" })}>查看设计依据的时间轴</button>}
                {draft.proposalBasis && <p>{draft.proposalBasis.rationale} 依据见 PDF 第 {draft.proposalBasis.page} 页。</p>}
                {draft.hypotheses.null && <h3>研究假设</h3>}
                {draft.hypotheses.null && <p>零假设 · {draft.hypotheses.null}</p>}
                {draft.hypotheses.alternative && <p>备择假设 · {draft.hypotheses.alternative}</p>}
                {draft.exceedsLimit && <p role="alert">超过实验单位或组合上限，未生成矩阵。</p>}
                {!!draft.groups.length && <><h3>实验矩阵</h3><div className="compare-table"><table><thead><tr><th>编号</th><th>{draft.proposalBasis ? "建议水平（待确认）" : "用户指定水平"}</th><th>角色</th></tr></thead>
                    <tbody>{draft.groups.map(group => <tr key={group.id}><td>{group.id}</td><td>{Object.entries(group.levels).map(([k,v]) => `${k} · ${v}`).join(" / ")}</td><td>{group.isControl ? "基准对照" : "实验组合"}</td></tr>)}</tbody>
                </table></div></>}
                <h3>统计与待确认项</h3>
                <p>{draft.statisticalPlan}</p>
                <ul>{draft.pending.map(item => <li key={item}>{item}</li>)}</ul>
            </article>}
        </div>
        <aside aria-label="设计参考文献">
            <h2>文献原页</h2>
            <p>检索片段供核对实验背景和条件。</p>
            {draft?.references.map(item => <details key={item.chunkId}>
                <summary>{item.source} · 第 {item.page} 页</summary>
                <p>{item.excerpt}</p>
                <a href={getPdfUrl(item)} target="_blank" rel="noreferrer">打开 PDF 原页</a>
            </details>)}
        </aside>
    </section>;
}

