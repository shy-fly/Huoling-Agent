import { useRef, useState, type FormEvent } from "react";
import { apiGet, apiPost, getPdfUrl } from "../api";
import Icon from "../components/Icon";
import CitationVisuals from "../components/CitationVisuals";
import type { EvolutionContext } from "../components/evolutionTypes";
import { auditRoute, sectionLabels, statusLabels, studyLabels, type AuditContext, type AuditReport, type Paper } from "../components/auditTypes";

export default function ReliabilityAudit({ context, onBack, onEvolution }: {
    context?: AuditContext; onBack: () => void; onEvolution: (context: EvolutionContext) => void;
}) {
    const [query, setQuery] = useState("");
    const [papers, setPapers] = useState<Paper[]>();
    const [selected, setSelected] = useState<Paper>();
    const [report, setReport] = useState<AuditReport>();
    const [referenceIds, setReferenceIds] = useState<string[]>([]);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const evidence = useRef<HTMLElement>(null);
    const target = context?.target ?? (selected ? { type: "paper", paperId: selected.paperId } : undefined);

    async function search(event: FormEvent) {
        event.preventDefault();
        if (busy) return;
        setBusy(true);
        setError("");
        try {
            const response = await apiGet<{ items: Paper[] }>(`${auditRoute}/papers?${new URLSearchParams({ q: query.trim() })}`);
            setPapers(response.items);
        } catch {
            setError("论文查询失败，请重试。");
        } finally {
            setBusy(false);
        }
    }

    async function audit() {
        if (!target || busy) return;
        setBusy(true);
        setError("");
        setReport(undefined);
        setReferenceIds([]);
        try {
            const data = await apiPost<AuditReport>(auditRoute, target);
            setReport(data);
            setReferenceIds(data.claimAssessments[0]?.evidenceIds.length
                ? data.claimAssessments[0].evidenceIds : data.references.slice(0, 1).map(ref => ref.evidenceId));
        } catch {
            setError("审计暂时失败，请核对论文或图谱来源。");
        } finally {
            setBusy(false);
        }
    }

    function showSources(ids: string[]) {
        setReferenceIds(ids);
        if (window.matchMedia("(max-width: 800px)").matches) evidence.current?.scrollIntoView({ block: "start" });
    }

    function sourceButton(ids: (string | null)[], text = "核对原文") {
        const present = ids.filter((id): id is string => !!id);
        return present.length > 0 && <button type="button" className="citation-expand-btn"
            onClick={() => showSources(present)}>{text}</button>;
    }

    function download() {
        if (!report) return;
        const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
        const link = document.createElement("a");
        link.href = url;
        link.download = `firefairy-audit-${report.auditId}.json`;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    const references = report?.references.filter(ref => referenceIds.includes(ref.evidenceId)) ?? [];
    return <section className="compare-workbench audit-workbench">
        <div>
            {context && <button className="citation-expand-btn" type="button" onClick={onBack}>返回{context.returnTo === "graph" ? "证据图谱" : "文献比较"}</button>}
            <h1>研究可靠性审计</h1>
            <p>逐项核对方法、统计和结论。</p>
            <details className="workbench-inputs" open={!report}>
                <summary>审计对象</summary>
                {context ? <p>{context.label}</p> : <>
                    <form className="compare-form" onSubmit={search}>
                        <label>查找本地论文<input value={query} maxLength={150} onChange={event => setQuery(event.target.value)}
                            placeholder="输入作者、年份或文件名" /></label>
                        <button type="submit" className="secondary-action" disabled={busy}><Icon name="book" />查找论文</button>
                    </form>
                    {!!papers?.length && <label className="audit-paper-choice">选择论文
                        <select value={selected?.paperId ?? ""} onChange={event => setSelected(papers.find(paper => paper.paperId === event.target.value))}>
                            <option value="">请选择</option>
                            {papers.map(paper => <option key={paper.paperId} value={paper.paperId}>{paper.source}</option>)}
                        </select>
                    </label>}
                    {papers?.length === 0 && <p>本地库没有匹配论文。</p>}
                </>}
                {target && <button type="button" className="secondary-action audit-submit" disabled={busy}
                    onClick={() => void audit()}>开始审计</button>}
            </details>
            {busy && <p role="status">正在读取和核对原文…</p>}
            {error && <p role="alert">{error}</p>}
            {report && <article className="research-reading audit-report">
                <h2>审计报告</h2>
                {report.status === "insufficientScope" && <p role="status">审计范围不足。需补齐方法和结果原文。</p>}
                <button type="button" className="citation-expand-btn" onClick={download}>导出 JSON</button>
                {report.studies.length > 0 && <button type="button" className="citation-expand-btn"
                    onClick={() => onEvolution({
                        question: report.claimAssessments[0]?.statement ?? report.studies[0].source,
                        paperIds: report.studies.map(study => study.paperId), returnTo: "audit",
                    })}>查看审计论文的时间轴</button>}
                {report.claimAssessments.map(item => <section key={item.claimId} aria-label="结论审查">
                    <h3>结论审查</h3>
                    <p>{item.statement}</p>
                    <p className="research-reading-note">{statusLabels[item.status]}{Object.entries(item.conditions)
                        .filter(([,value]) => value).map(([key,value]) => ` · ${key} ${value}`)}</p>
                    {sourceButton(item.evidenceIds, item.status === "needsReview" ? "核对相关原文" : "核对结论原文")}
                    <ul>{item.limitations.map(note => <li key={note}>{note}</li>)}</ul>
                </section>)}
                {report.studies.map(study => <section key={study.paperId}>
                    <h3>{study.source}</h3>
                    <p>{studyLabels[study.studyType]} · 已检查 {study.scope.pages.length} 页</p>
                    {study.scope.pages.length > 0 && <p className="research-reading-note">
                        PDF 页 {study.scope.pages.join("、")} · {study.scope.sections.map(section => sectionLabels[section]).join("、")}
                    </p>}
                    <p className="research-reading-note">补充材料未纳入。{study.scope.truncated && "已达原文页数上限。"}</p>
                    <div className="research-result-actions">
                        {sourceButton([study.classificationEvidenceId], "研究类型依据")}
                        {sourceButton([study.objectiveEvidenceId], "研究目标")}
                        {sourceButton([study.methodEvidenceId], "方法原文")}
                    </div>
                    <h3>审计清单</h3>
                    {study.findings.map(item => <details className="audit-finding" key={item.findingId} data-rule={item.ruleId}>
                        <summary><span>{item.label}</span><span data-status={item.status}>{statusLabels[item.status]}</span></summary>
                        <p>{item.observation}</p>
                        <p className="research-reading-note">{item.checkedSections.length > 0 &&
                            `检查范围 · ${item.checkedSections.map(section => sectionLabels[section]).join("、")}。 `}{item.uncertainty}</p>
                        {sourceButton(item.evidenceIds)}
                    </details>)}
                </section>)}
            </article>}
        </div>
        <aside ref={evidence} aria-label="审计原文">
            <h2>审计原文</h2>
            {references.length === 0 && <p>展开审计项，查看对应原页。</p>}
            {references.map(ref => <section key={ref.evidenceId} className="graph-source-quote">
                <p>{ref.excerpt}</p>
                <a href={getPdfUrl(ref)} target="_blank" rel="noreferrer">{ref.source} · PDF 第 {ref.page} 页</a>
                {ref.visual && <CitationVisuals chunkId={ref.visual.chunkId} pdfUrl={getPdfUrl(ref)}
                    kind={ref.visual.kind} number={ref.visual.number} quiet />}
            </section>)}
        </aside>
    </section>;
}
