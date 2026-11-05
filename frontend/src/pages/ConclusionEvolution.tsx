import { useRef, useState, type FormEvent } from "react";
import { apiPost } from "../api";
import Icon from "../components/Icon";
import EvolutionDetail from "../components/EvolutionDetail";
import { relationLabels, type EvolutionContext, type EvolutionReport, type TimelineEvent, type TimelineRelation } from "../components/evolutionTypes";

export default function ConclusionEvolution({ context, onBack }: { context?: EvolutionContext; onBack: () => void }) {
    const [question, setQuestion] = useState(context?.question.slice(0, 2000) ?? "");
    const [start, setStart] = useState("");
    const [end, setEnd] = useState("");
    const [grouping, setGrouping] = useState("1");
    const [includeAudit, setIncludeAudit] = useState(false);
    const [report, setReport] = useState<EvolutionReport>();
    const [event, setEvent] = useState<TimelineEvent>();
    const [relation, setRelation] = useState<TimelineRelation>();
    const [claimId, setClaimId] = useState<string>();
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const aside = useRef<HTMLElement>(null);

    async function analyze(e: FormEvent) {
        e.preventDefault();
        if (!question.trim() || busy) return;
        if (start && end && Number(start) > Number(end)) {
            setError("起始年份应早于或等于结束年份。");
            return;
        }
        setBusy(true);
        setError("");
        try {
            const result = await apiPost<EvolutionReport>("/v1/research/evolution", {
                question: question.trim(), startYear: start ? Number(start) : null, endYear: end ? Number(end) : null,
                grouping: Number(grouping), paperIds: context?.paperIds ?? [], graphId: context?.graphId,
                claimId: context?.claimId, includeAudit,
            });
            setReport(result);
            setRelation(undefined);
            setClaimId(context?.claimId);
            setEvent(result.events.find(item => item.claims.some(claim => claim.claimId === context?.claimId)) ??
                result.events.find(item => item.claims.length > 0) ?? result.events[0]);
        } catch {
            setError("暂时无法构建时间轴，请核对范围后重试。");
        } finally {
            setBusy(false);
        }
    }

    function focusEvidence() {
        if (window.matchMedia("(max-width: 800px)").matches) aside.current?.scrollIntoView({ block: "start" });
    }

    function download() {
        if (!report) return;
        const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
        const link = document.createElement("a");
        link.href = url;
        link.download = `firefairy-evolution-${report.analysisId}.json`;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    return <section className="compare-workbench evolution-workbench">
        <div>
            {context && <button type="button" className="citation-expand-btn" onClick={onBack}>返回来源</button>}
            <h1>科学结论演化</h1>
            <p>沿发表年份核对观点与证据。</p>
            {context && <p>沿用来源中的论文或图谱范围。</p>}
            <details className="workbench-inputs" open={!report}>
                <summary>研究范围</summary>
                <form className="compare-form" onSubmit={analyze}>
                    <label>研究问题<textarea required maxLength={2000} value={question} onChange={e => setQuestion(e.target.value)}
                        placeholder="厌氧消化氨抑制研究的科学认识是如何演变的？" /></label>
                    <label>起始年份<input type="number" min="1800" max="2099" value={start} onChange={e => setStart(e.target.value)} /></label>
                    <label>结束年份<input type="number" min="1800" max="2099" value={end} onChange={e => setEnd(e.target.value)} /></label>
                    <label>统计分组<select value={grouping} onChange={e => setGrouping(e.target.value)}>
                        <option value="1">逐年</option><option value="5">五年</option><option value="10">十年</option>
                    </select></label>
                    <label className="evolution-audit-check"><input type="checkbox" checked={includeAudit}
                        onChange={e => setIncludeAudit(e.target.checked)} />含可靠性审计</label>
                    <button type="submit" className="secondary-action" disabled={busy}><Icon name="book" />构建时间轴</button>
                </form>
            </details>
            {busy && <p role="status">正在核对出版记录和原文…</p>}
            {error && <p role="alert">{error}</p>}
            {report && <article className="research-reading evolution-report">
                <h2>发表时间轴</h2>
                <p>{report.scope.startYear != null ? `${report.scope.startYear}–${report.scope.endYear}` : "暂无可核对年份"} ·
                    收录 {report.scope.includedPaperCount} / {report.scope.candidateCount} 篇候选论文 ·
                    {report.scope.claimPaperCount} 篇有已核对观点</p>
                <p className="research-reading-note">年份待核 {report.scope.missingYear} · 版本去重 {report.scope.duplicates} ·
                    超出年份范围 {report.scope.outsideRange}</p>
                {report.summary.status === "insufficientTimeline" && <p>不同年份的原文观点不足，暂不能判断变化。</p>}
                <ol className="evolution-timeline">{report.events.map(item => <li key={item.eventId}>
                    <button type="button" aria-pressed={event?.eventId === item.eventId && !relation}
                        onClick={() => { setEvent(item); setClaimId(undefined); setRelation(undefined); focusEvidence(); }}>
                        <time dateTime={String(item.year)}>{item.year}</time>
                        <span><strong>{item.source.replace(/\.pdf$/i, "")}</strong>
                            <span>{item.claims[0]?.statement ?? (item.method?.reference ? "已核对原文方法" : "已核对出版年份")}</span></span>
                    </button>
                </li>)}</ol>
                <h2>已核对关系</h2>
                {report.relations.length > 0 ? <ul className="evolution-relations">{report.relations.map(item => {
                    const left = report.events.find(event => event.eventId === item.sourceEventId);
                    const right = report.events.find(event => event.eventId === item.targetEventId);
                    return <li key={item.relationId}><button type="button" className="citation-expand-btn"
                        onClick={() => { setRelation(item); focusEvidence(); }}>
                        {left?.year}{item.sameYear ? " · 同年" : ` / ${right?.year}`} · {relationLabels[item.type]}
                    </button></li>;
                })}</ul> : <p>当前范围没有可核对的观点关系。</p>}
                <details><summary>分期统计 · 按独立论文</summary>
                    <div className="compare-table"><table><thead><tr><th>年份</th><th>论文</th><th>实验结果记录</th><th>原文证据</th></tr></thead>
                        <tbody>{report.periods.map(period => <tr key={period.startYear}>
                            <td>{period.startYear === period.endYear ? period.startYear : `${period.startYear}–${period.endYear}`}</td>
                            <td>{period.paperCount}</td><td>{period.experimentRecordCount}</td><td>{period.directEvidenceCount}</td>
                        </tr>)}</tbody></table></div>
                </details>
                <h2>证据范围</h2>
                <ul>{report.summary.limitations.map(note => <li key={note}>{note}</li>)}</ul>
                <button type="button" className="citation-expand-btn" onClick={download}>导出 JSON</button>
            </article>}
        </div>
        <aside ref={aside} aria-label="演化原文">
            <h2>证据与出版记录</h2>
            <EvolutionDetail key={relation?.relationId ?? event?.eventId} event={event} relation={relation}
                claimId={claimId} onClaim={setClaimId} />
        </aside>
    </section>;
}
