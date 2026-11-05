import { designSourcePages, type DesignContext } from "./ExperimentDesign";
import { useEffect, useRef, useState, type FormEvent } from "react";
import type { EvolutionContext } from "../components/evolutionTypes";
import { apiPost, getPdfUrl } from "../api";

type RecordRow = Parameters<typeof getPdfUrl>[0] & { id: string; sourceId: string; group: string; rawCells?: Record<string, string>; fields: Record<string, [string, string] | null> };
type Cell = { x: string; y: string; paperCount: number; recordCount: number; paperIds: string[]; recordIds: string[]; state: string };
type Report = {
    researchQuestion: string; axisDefinitions: { field: string; unit: string }[]; scope: string; labels: [string[], string[]]; coverageMatrix: Cell[]; experimentRecords: RecordRow[];
    verifiedPaperCount: number; analyzedPaperCount: number; retrievedPaperCount: number;
    unclassifiedCount: number; missingData: Record<string, number>; unmatchedData: Record<string, number>;
    researchQuestions: string[];
};
const rowLabels: Record<string, string> = { regime: "原文温区", phase: "实验阶段", group: "实验组" };
const defaultQuestion = "厌氧消化氨抑制研究中，哪些温度、pH 和 TAN/FAN 条件组合缺少充分研究？";

export type GapContext = {
    question: string;
    paperIds: string[];
    sourcePages: Record<string, number[]>;
};

export default function ResearchGaps({ context, onBack, onDesign, onEvolution }: {
    context?: GapContext; onBack: () => void;
    onDesign: (context: DesignContext) => void; onEvolution: (context: EvolutionContext) => void;
}) {
    const [question, setQuestion] = useState(context?.question ?? defaultQuestion);
    const [metric, setMetric] = useState("FAN");
    const [unit, setUnit] = useState("mg/L");
    const [edges, setEdges] = useState("0,100,300,500");
    const [rowField, setRowField] = useState("regime");
    const [paperLimit, setPaperLimit] = useState(5);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [report, setReport] = useState<Report>();
    const [selected, setSelected] = useState<Cell>();
    const request = useRef<AbortController>();
    useEffect(() => () => request.current?.abort(), []);
    const selectedRecords = report?.experimentRecords.filter(record => selected?.recordIds.includes(record.id)) ?? [];
    async function analyze(event: FormEvent) {
        event.preventDefault();
        if (busy || !question.trim()) return;
        const controller = new AbortController();
        request.current = controller;
        setBusy(true);
        setError("");
        setReport(undefined);
        setSelected(undefined);
        try {
            setReport(await apiPost<Report>("/v1/research/gaps", {
                question: question.trim(), paperLimit,
                includeIds: context?.paperIds, sourcePages: context?.sourcePages,
                xAxis: { field: metric.trim(), unit: unit.trim(), edges: edges.split(/[,，]/).map(value => value.trim()) },
                yAxis: { field: rowField.trim() },
            }, controller.signal));
        } catch {
            if (!controller.signal.aborted) setError("分析失败。请检查区间和单位。");
        } finally {
            setBusy(false);
        }
    }
    return <section className="compare-workbench gap-workbench">
        <div>
            <h1>科研空白雷达</h1>
            {context && <p>沿用反证报告的 {context.paperIds.length} 篇论文。
                <button type="button" className="citation-expand-btn" onClick={onBack}>返回反证报告</button>
            </p>}
            <details className="workbench-inputs" open={!report}>
                <summary>检索与覆盖条件</summary>
                <form className="compare-form" onSubmit={analyze}>
                    <label>研究问题<textarea required maxLength={2000} value={question} onChange={e => setQuestion(e.target.value)} /></label>
                    <label>横轴指标<input required value={metric} onChange={e => setMetric(e.target.value)} /></label>
                    <label>原文单位<input required value={unit} onChange={e => setUnit(e.target.value)} /></label>
                    <label>区间边界<input required value={edges} onChange={e => setEdges(e.target.value)} /></label>
                    <label>纵轴类别<select value={rowField} onChange={e => setRowField(e.target.value)}>
                        <option value="regime">原文温区</option><option value="phase">实验阶段</option><option value="group">原文实验组</option>
                    </select></label>
                    <label>候选论文数<input type="number" min="2" max="10" value={paperLimit} onChange={e => setPaperLimit(Number(e.target.value))} /></label>
                    <button className="secondary-action" disabled={busy}>分析覆盖</button>
                    {busy && <button className="citation-expand-btn" type="button"
                        onClick={() => request.current?.abort()}>停止等待</button>}
                </form>
            </details>
            {busy && <p role="status">正在检索和核对原文…</p>}
            {error && <p role="alert">{error}</p>}
            {report && <article className="research-reading">
                <h2>研究覆盖</h2>
                <p>{report.scope}。检索 {report.retrievedPaperCount} 篇，核验 {report.verifiedPaperCount} 篇，提取 {report.analyzedPaperCount} 篇。</p>
                <div className="gap-chart-key" aria-label="覆盖图例">
                    <span><i data-tone="empty" /> 无有效记录</span>
                    <span><i data-tone="sparse" /> 证据稀疏</span>
                    <span><i data-tone="observed" /> 高于稀疏阈值</span>
                </div>
                {!report.coverageMatrix.length ? <p>没有可同时归入两个坐标轴的记录。</p> :
                    <div className="compare-table gap-matrix" tabIndex={0} aria-label="研究覆盖矩阵">
                        <table><caption>{report.axisDefinitions[0].field} · {report.axisDefinitions[0].unit} <span>按独立论文计</span></caption>
                        <thead><tr><th scope="col">{rowLabels[report.axisDefinitions[1].field] ?? report.axisDefinitions[1].field}</th>{report.labels[0].map(x => <th scope="col" key={x}>{x.replace(/^\[(.*), (.*)\)$/, "$1–<$2")}</th>)}</tr></thead>
                        <tbody>{report.labels[1].map(y => <tr key={y}><th scope="row">{y}</th>{report.coverageMatrix.filter(cell => cell.y === y).map(cell =>
                            <td key={cell.x}><button type="button" className="gap-cell" data-state={cell.state}
                                aria-pressed={selected === cell} aria-label={`${y}，${cell.x}，${cell.paperCount} 篇`}
                                onClick={() => setSelected(cell)}>
                                    <strong>{cell.paperCount || "—"}</strong>
                                    {cell.paperCount > 0 && <small>{cell.recordCount} 条记录</small>}
                                </button></td>)}</tr>)}</tbody>
                    </table></div>}
                <p className="gap-matrix-note">区间左闭右开。带 ± 的数值按中心值归类，证据保留原值。</p>
                <p className="gap-matrix-note">未归类 {report.unclassifiedCount} 条。字段缺失 {Object.entries(report.missingData).map(([key,value]) => `${key} ${value}`).join("、") || "0"}。
                    单位或区间不匹配 {Object.values(report.unmatchedData).reduce((sum,n) => sum+n,0)} 项。</p>
                {!!report.researchQuestions.length && <><h2>待验证问题</h2><ul>{report.researchQuestions.map(item => <li key={item}>{item}</li>)}</ul></>}
            </article>}
        </div>
        <aside aria-label="覆盖证据">
            <h2>覆盖证据</h2>
            {selected && report ? <>
                <p>{selected.y} · {selected.x} · {selected.paperCount} 篇 · {selected.recordCount} 条</p>
                <button className="citation-expand-btn" type="button" onClick={() => onDesign({
                    origin: "gaps", question: report.researchQuestion, paperIds: selected.paperIds, recordIds: selected.recordIds,
                    sourcePages: designSourcePages(selectedRecords),
                    conditions: { [report.axisDefinitions[0].field]: selected.x, [report.axisDefinitions[1].field]: selected.y },
                })}>设计研究方案</button>
                {selected.paperIds.length > 0 && <button type="button" className="citation-expand-btn"
                    onClick={() => onEvolution({ question: report.researchQuestion, paperIds: selected.paperIds,
                        returnTo: "gaps" })}>查看研究时间分布</button>}
                {!selected.recordCount && <p>本次没有可归类记录。</p>}
                {selectedRecords.map(record =>
                    <p key={record.id}><a href={getPdfUrl(record)} target="_blank" rel="noreferrer">{record.group} · PDF 第 {record.page} 页</a><br />
                        {Object.entries(record.fields).map(([name,value]) => value ? `${name} ${(record.rawCells?.[name] ? `${record.rawCells[name]} ${value[1]}` : value.join(" "))}` : `${name} 不一致`).join(" · ")}</p>)}
            </> : <p>点一个区间查看原页。</p>}
        </aside>
    </section>;
}

