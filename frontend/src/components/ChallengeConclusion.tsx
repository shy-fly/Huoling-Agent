import { designSourcePages, type DesignContext } from "../pages/ExperimentDesign";
import ExperimentContrasts, { type GroupTables, type ContrastSource } from "./ExperimentContrasts";
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { apiPost, getPdfUrl } from "../api";
import type { GraphContext } from "./evidenceGraphTypes";
import type { AuditContext } from "./auditTypes";
import type { EvolutionContext } from "./evolutionTypes";
import type { GapContext } from "../pages/ResearchGaps";

type Evidence = Parameters<typeof getPdfUrl>[0] & {
    evidenceId: string; sourceId: string; group: string; classification: string; reason: string; evidenceText: string;
};
type Report = {
    groupTables: GroupTables;
    contrastSources: Record<string, ContrastSource>;
    evidence: Evidence[];
    hypothesisRevision: { status: string; revisedClaim: string | null; unresolvedQuestions: string[] };
};

export default function ChallengeConclusion({ claim, sourceId, page, onDesign, onGraph, onAudit, onEvolution, onGaps, reportHost }: {
    claim: string; sourceId: string; page: number; onDesign?: (context: DesignContext) => void; reportHost?: HTMLElement | null;
    onGraph?: (context: GraphContext) => void;
    onAudit?: (context: AuditContext) => void;
    onEvolution?: (context: EvolutionContext) => void;
    onGaps?: (context: GapContext) => void;
}) {
    const reportId = useId();
    const [report, setReport] = useState<Report>();
    const [status, setStatus] = useState("");
    const active = useRef<AbortController | null>(null);
    useEffect(() => () => active.current?.abort(), []);
    async function challenge() {
        const request = new AbortController();
        active.current = request;
        setStatus("正在查找支持与反对证据…");
        setReport(undefined);
        try {
            const data = await apiPost<Report>("/v1/research/falsification", {
                hypothesis: claim, sourceId, sourcePage: page,
            }, request.signal);
            if (!request.signal.aborted) {
                setReport(data);
                setStatus("");
            }
        } catch {
            setStatus(request.signal.aborted ? "已停止等待。" : "检索失败，请重试。");
        } finally {
            active.current = null;
        }
    }
    const sources = report ? [{ sourceId, page }, ...report.evidence] : [];
    const sourcePages = designSourcePages(sources);
    const paperIds = Object.keys(sourcePages);
    const content = report && <section className="research-reading" id={reportId} aria-label="反证报告">
            <h3>反证报告</h3>
            {onDesign && <button type="button" className="citation-expand-btn" onClick={() => onDesign({
                origin: "falsification", question: claim,
                paperIds: paperIds,
                recordIds: report.evidence.map(item => item.evidenceId),
                sourcePages: sourcePages,
            })}>设计反证实验</button>}
            {onGraph && <button type="button" className="citation-expand-btn" onClick={() => onGraph({
                question: claim, paperIds: paperIds,
                sourcePages: sourcePages,
            })}>查看反证图谱</button>}
            {onAudit && <button type="button" className="citation-expand-btn" onClick={() => onAudit({
                target: { type: "hypothesis", paperId: sourceId, page, claim }, label: claim, returnTo: "compare",
            })}>审计此观点</button>}
            {onEvolution && <button type="button" className="citation-expand-btn" onClick={() => onEvolution({
                question: claim, paperIds: paperIds,
                returnTo: "compare",
            })}>追踪观点历史</button>}
            {onGaps && <button type="button" className="citation-expand-btn"
                onClick={() => onGaps({ question: claim, paperIds, sourcePages })}>查看证据覆盖</button>}
            <p>{claim}</p>
            <p>{report.hypothesisRevision.revisedClaim || (report.hypothesisRevision.status === "not_reviewed" ? "尚未完成原始实验证据审查。" : "本轮未检索到可审查证据。")}</p>
            {report.evidence.length > 0 && <p>已核验记录中未见直接反证。其他候选尚未完成审查。</p>}
            {report.evidence.map(item => <article key={item.evidenceId}>
                <strong>{item.classification === "support" ? "支持" : "条件性"} · {item.group}</strong>
                <p>{item.reason}</p>
                <a href={getPdfUrl(item)} target="_blank" rel="noreferrer">PDF 第 {item.page} 页</a>
            </article>)}
            <ExperimentContrasts tables={report.groupTables} sources={report.contrastSources} />
            <ul>{report.hypothesisRevision.unresolvedQuestions.map(question => <li key={question}>{question}</li>)}</ul>
        </section>;
    return <div className="challenge-conclusion">
        <button type="button" className="citation-expand-btn" disabled={active.current != null} onClick={() => void challenge()}>挑战这个结论</button>
        {active.current && <button type="button" className="citation-expand-btn" onClick={() => active.current?.abort()}>取消</button>}
        {status && <p role="status">{status}</p>}
        {content && reportHost && <button type="button" className="citation-expand-btn" aria-controls={reportId}
            onClick={() => document.getElementById(reportId)?.scrollIntoView({ block: "start" })}>查看反证报告</button>}
        {content && (reportHost ? createPortal(content, reportHost) : content)}
    </div>;
}

