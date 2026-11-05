import { designSourcePages, type DesignContext } from "./ExperimentDesign";
import type { GapContext } from "./ResearchGaps";
import type { MediaContext } from "./MediaEvidence";
import type { GraphContext } from "../components/evidenceGraphTypes";
import type { AuditContext } from "../components/auditTypes";
import type { EvolutionContext } from "../components/evolutionTypes";
import ExperimentContrasts, { type GroupTables } from "../components/ExperimentContrasts";
import ChallengeConclusion from "../components/ChallengeConclusion";
import FanChart from "../components/FanChart";
import CitationVisuals from "../components/CitationVisuals";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { apiPost, getPdfUrl } from "../api";
import Icon from "../components/Icon";
import type { QaCompareContext } from "../components/qaCompareContext";

type Evidence = Parameters<typeof getPdfUrl>[0] & { evidenceText: string; title: string; id?: number };
type Cell = { page: number; observation: { regime: string; group: string; phase: string; dimension: string; rawValue: string; rawUnit: string } };
type Endpoint = Evidence & { provenance?: string; sourceId: string; group: string; metric: string; unit: string; endpoint: string; value: string };
type EndpointPair = { left: Endpoint; right: Endpoint; reasons: string[] };
type CompareResult = {
    groupTables: GroupTables;
    verifiedPaperCount: number;
    retrievedPaperCount: number;
    experimentalPaperCount: number;
    limitations: string[];
    thresholdComparison: { records: Endpoint[]; comparable: EndpointPair[]; incompatible: EndpointPair[]; explanations: string[] };
    papers: Record<string, Evidence[]>;
    tableRecords: Record<string, Cell[]>;
};

export default function ResearchCompare({ context, onDesign, onMedia, onGraph, onAudit, onEvolution, onGaps }: {
    context?: QaCompareContext;
    onDesign: (context: DesignContext) => void;
    onMedia: (context: MediaContext) => void;
    onGraph: (context: GraphContext) => void;
    onAudit: (context: AuditContext) => void;
    onEvolution: (context: EvolutionContext) => void;
    onGaps: (context: GapContext) => void;
}) {
    const [question, setQuestion] = useState(context?.question ?? "");
    const [dimensions, setDimensions] = useState("TAN, FAN");
    const [paperLimit, setPaperLimit] = useState(Math.min(10, Math.max(3,
        new Set(context?.evidence.map(item => item.collection + "/" + item.source)).size)));
    const [useQaEvidence, setUseQaEvidence] = useState(!!context);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [result, setResult] = useState<CompareResult>();
    const [selected, setSelected] = useState<Evidence>();
    const request = useRef<AbortController>();
    useEffect(() => () => request.current?.abort(), []);
    useEffect(() => {
        let active = true;
        queueMicrotask(() => {
            if (active && context) void runComparison();
        });
        return () => {
            active = false;
            request.current?.abort();
        };
    }, [context]);
    async function runComparison() {
        if (!question.trim() || busy) return;
        const controller = new AbortController();
        request.current = controller;
        setBusy(true);
        setError("");
        setResult(undefined);
        setSelected(undefined);
        try {
            setResult(await apiPost<CompareResult>("/v1/research/compare", {
                question: question.trim(), paperLimit,
                dimensions: dimensions.split(/[,，]/).map(value => value.trim()).filter(Boolean),
                qaContext: useQaEvidence ? context : undefined,
            }, controller.signal));
        } catch {
            if (!controller.signal.aborted) setError("比较失败。请重试。");
        } finally {
            if (request.current === controller) setBusy(false);
        }
    }
    function compare(event: FormEvent) {
        event.preventDefault();
        void runComparison();
    }
    const yang = Object.entries(result?.papers ?? {}).find(([, items]) => items.some(
        item => item.source === "Yang-2018-Effect-of-ammonia-on-methane-produc.pdf" && item.page === 4,
    ));
    const yangPage = yang?.[1].find(item => item.page === 4);
    const fanCells = (yang ? result?.tableRecords[yang[0]] ?? [] : []).filter(({ page, observation }) =>
        page === 4 && observation.dimension === "FAN" && observation.rawUnit === "mg/L",
    );
    const points = (regime: string) => fanCells.filter(({ observation }) => observation.regime === regime)
        .map(({ observation }) => ({ phase: Number(observation.phase.replace("Phase ", "")), value: Number(observation.rawValue) }))
        .sort((a, b) => a.phase - b.phase);
    const meso = points("Mesophilic");
    const thermo = points("Thermophilic");
    const complete = (series: typeof meso) => series.length === 8 &&
        series.every((point, index) => point.phase === index && Number.isFinite(point.value) && point.value > 0);
    return (
        <section className="compare-workbench">
            <div>
                <h1>文献观点比较</h1>
                {useQaEvidence && context && <p className="research-note">已带入本轮原文证据。
                    <button className="citation-expand-btn" type="button" disabled={busy}
                        onClick={() => setUseQaEvidence(false)}>改用全库检索</button>
                </p>}
                <details className="workbench-inputs" open={!result}>
                    <summary>比较条件</summary>
                    <form onSubmit={compare} className="compare-form">
                        <label>研究问题<textarea required maxLength={2000} value={question} onChange={event => setQuestion(event.target.value)} placeholder="为什么论文报告的氨抑制阈值不同？" /></label>
                        <label>表格指标<input value={dimensions} onChange={event => setDimensions(event.target.value)} /></label>
                        <label>候选论文数<input type="number" min={2} max={10} value={paperLimit} onChange={event => setPaperLimit(Number(event.target.value))} /></label>
                        <button className="secondary-action" type="submit" disabled={busy}><Icon name="book" />开始比较</button>
                        {busy && <button className="secondary-action" type="button" onClick={() => request.current?.abort()}>停止等待</button>}
                    </form>
                </details>
                {busy && <p role="status">正在检索并核对 PDF…</p>}
                {error && <p role="alert">{error}</p>}
                {result && <article className="research-reading">
                    <h2>原文报告的阈值与响应</h2>
                    {result.verifiedPaperCount > 0 && <div className="research-result-actions">
                        <button type="button" className="citation-expand-btn"
                            onClick={() => onMedia({ question, paperIds: Object.keys(result.papers) })}>查看相关图表证据</button>
                        <button type="button" className="citation-expand-btn" onClick={() => onGraph({
                            question, paperIds: Object.keys(result.papers),
                            sourcePages: designSourcePages(result.thresholdComparison.records),
                        })}>查看证据图谱</button>
                        <button type="button" className="citation-expand-btn"
                            onClick={() => onEvolution({ question, paperIds: Object.keys(result.papers), returnTo: "compare" })}>查看观点演变</button>
                    </div>}
                    <p>记录按来源区分自动提取和人工核对。未识别的结果仍需审查。</p>
                    <p>{result.thresholdComparison.comparable.length
                        ? `${result.thresholdComparison.comparable.length} 组可比终点`
                        : "已核验终点中没有可直接比较的跨论文阈值。"}</p>
                    {result.thresholdComparison.records.length > 0 && <div className="compare-table" tabIndex={0} aria-label="研究终点">
                        <table><thead><tr><th>论文</th><th>实验组</th><th>指标</th><th>响应终点</th><th>原文结果</th></tr></thead>
                            <tbody>{result.thresholdComparison.records.map((record, index) => (
                                <tr key={`${record.sourceId}-${index}`}><td>{record.source}<br /><small>{record.provenance === "automatic_explicit_result" ? "原文自动提取" : "人工核对"}</small></td><td>{record.group}</td><td>{record.metric}</td>
                                    <td>{record.endpoint}</td><td><button className="citation-expand-btn" type="button" onClick={() => setSelected(record)}>{record.value} · {record.unit}</button></td></tr>
                            ))}</tbody>
                        </table>
                    </div>}
                    {result.thresholdComparison.records.map((record, index) => (
                        <section className="challenge-finding" key={`${record.sourceId}-${index}`}>
                            <p>{record.group} · {record.metric} · {record.endpoint} · {record.value} {record.unit}</p>
                            <ChallengeConclusion onDesign={onDesign} onGraph={onGraph} onAudit={onAudit} onEvolution={onEvolution} onGaps={onGaps} sourceId={record.sourceId} page={record.page}
                                claim={`${record.group}：${record.metric} ${record.endpoint} ${record.value} ${record.unit}。这一结果如何限定甲烷产量下降的结论？`} />
                        </section>
                    ))}
                    {result.thresholdComparison.incompatible.length > 0 && <ul>{result.thresholdComparison.incompatible.map((pair, index) => (
                        <li key={index}>{pair.left.group} / {pair.right.group} · {pair.reasons.join("、")}不同
                            <button type="button" className="citation-expand-btn" onClick={() => onDesign({
                                origin: "compare", question, paperIds: [...new Set([pair.left.sourceId, pair.right.sourceId])],
                                sourcePages: designSourcePages([pair.left, pair.right]),
                                conditions: { 左侧终点: pair.left.endpoint, 右侧终点: pair.right.endpoint },
                            })}>设计验证实验</button></li>
                    ))}</ul>}
                    {result.thresholdComparison.explanations.length > 0 && <>
                        <h2>差异与证据边界</h2>
                        <ul>{result.thresholdComparison.explanations.map(note => <li key={note}>{note}</li>)}</ul>
                    </>}
                    <ExperimentContrasts challenge={(claim, sourceId, page, reportHost) => <ChallengeConclusion onDesign={onDesign} onGraph={onGraph} onAudit={onAudit} onEvolution={onEvolution} onGaps={onGaps}
                        claim={claim} sourceId={sourceId} page={page} reportHost={reportHost} />} tables={result.groupTables} sources={Object.fromEntries(
                        Object.entries(result.papers).map(([key, entries]) => [key, entries[0]]),
                    )} />
                    <h2>自动提取的实验表格</h2>
                    <p>检索 {result.retrievedPaperCount} 篇 · 核验 {result.verifiedPaperCount} 篇</p>
                    <p>{result.verifiedPaperCount < 2 ? "相关证据不足两篇。" : "以下数值保留原单位。"}</p>
                    {yangPage && complete(meso) && complete(thermo) && <section className="compare-visuals">
                        <h3>同一阶段的 FAN 对照</h3>
                        <p>Yang 表 1 的第 4 阶段，中温 FAN 为 {meso[4].value} mg/L，高温为 {thermo[4].value} mg/L。</p>
                        {yangPage.id != null && <CitationVisuals chunkId={yangPage.id} pdfUrl={getPdfUrl(yangPage)} kind="table" number="1" quiet />}
                        <FanChart series={[meso, thermo]} pdfUrl={getPdfUrl(yangPage)} />
                        <p>图中数值为阶段浓度，不代表抑制阈值。</p>
                    </section>}
                    <div className="compare-table" tabIndex={0} aria-label="实验记录">
                        <table><thead><tr><th>论文</th><th>实验组</th><th>阶段</th><th>指标</th><th>原始数值</th></tr></thead>
                            <tbody>{Object.entries(result.tableRecords).flatMap(([sourceId, cells]) => cells.map(({page, observation: cell}, index) => {
                                const evidence = result.papers[sourceId].find(item => item.page === page);
                                return <tr key={sourceId + index}><td>{evidence?.source}</td><td>{cell.regime} · {cell.group}</td><td>{cell.phase}</td><td>{cell.dimension}</td>
                                    <td><button type="button" className="citation-expand-btn" onClick={() => setSelected(evidence)}>{cell.rawValue} {cell.rawUnit}</button></td></tr>;
                            }))}</tbody>
                        </table>
                    </div>
                    {!result.experimentalPaperCount && <p>未找到可按实验组读取的表格。</p>}
                    <h2>证据边界</h2>
                    <p>{result.experimentalPaperCount < 2 ? "可读取实验表格的论文不足两篇。" : "已读取多篇论文的实验表格。"}</p>
                    <ul>{result.limitations.map(note => <li key={note}>{note}</li>)}</ul>
                </article>}
            </div>
            <aside aria-label="文献证据">
                <h2>文献证据</h2>
                {selected ? <><h3>{selected.title || selected.source}</h3><p>{selected.evidenceText}</p><a href={getPdfUrl(selected)} target="_blank" rel="noreferrer">打开 PDF 第 {selected.page} 页</a></> :
                    result && Object.entries(result.papers).map(([id, entries]) => <p key={id}>
                        <button type="button" className="citation-expand-btn" onClick={() => setSelected(entries[0])}>{entries[0].source}</button>
                        <button type="button" className="citation-expand-btn" onClick={() => onAudit({
                            target: { type: "paper", paperId: id }, label: entries[0].source, returnTo: "compare",
                        })}>审计此论文</button>
                    </p>)}
            </aside>
        </section>
    );
}


