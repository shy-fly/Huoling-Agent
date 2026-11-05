import { getMediaImageUrl, getPdfUrl } from "../api";
import CitationVisuals from "./CitationVisuals";
import { kinds, relations, type GraphEdge, type GraphNode, type Source } from "./evidenceGraphTypes";

const attributeLabels: Record<string, string> = {
    group: "实验组", metric: "指标", endpoint: "终点", value: "原始结果", unit: "单位",
    control: "对照", originalTerm: "原始术语", alignment: "术语对齐",
};
const methods: Record<string, string> = {
    curated_pdf_anchor: "人工标注，重新核对 PDF", automatic_explicit_result: "自动读取原文结果",
    explicit_prose: "原文对照与对应数值", explicit_same_page_caption: "原文明确提及同页图表",
    reported_endpoint_comparison: "比较原文指标、单位与终点",
};

function SourceQuote({ source }: { source: Source }) {
    return <section className="graph-source-quote">
        <p>{source.excerpt}</p>
        <a href={getPdfUrl(source)} target="_blank" rel="noreferrer">{source.source} · PDF 第 {source.page} 页</a>
    </section>;
}

export default function EvidenceGraphDetail({ item, connected, onExpand, onEdge, onAudit }: {
    item?: GraphNode | GraphEdge; connected: GraphEdge[];
    onExpand: (nodeId: string) => void; onEdge: (edge: GraphEdge) => void;
    onAudit?: () => void;
}) {
    if (!item) return <p>点节点或关系，核对证据。</p>;
    if ("target" in item) return <section aria-label="关系详情">
        <h3>{relations[item.type]}</h3>
        {onAudit && <button type="button" className="citation-expand-btn" onClick={onAudit}>审查证据关系</button>}
        <p>已核对来源 · {methods[item.method] ?? "原文关联"}</p>
        {!!item.notes.length && <ul>{item.notes.map(note => <li key={note}>{note}</li>)}</ul>}
        {item.evidence.map(source => <SourceQuote key={source.id} source={source} />)}
    </section>;
    const source = connected.find(edge => edge.type !== "notComparableWith")?.evidence[0];
    return <section aria-label="节点详情">
        <p>{kinds[item.type]}</p>
        <h3>{item.label}</h3>
        {onAudit && item.type === "claim" && <button type="button" className="citation-expand-btn" onClick={onAudit}>检查这个结论</button>}
        {item.attributes && <dl className="graph-attributes">{Object.entries(item.attributes).filter(([,value]) => value)
            .map(([name, value]) => <div key={name}><dt>{attributeLabels[name] ?? name}</dt><dd>{value}</dd></div>)}</dl>}
        {item.page && item.source && item.collection && item.excerpt && <SourceQuote
            source={{ id: item.id, source: item.source, collection: item.collection, page: item.page, excerpt: item.excerpt }} />}
        {!item.excerpt && !item.media && source && <SourceQuote source={source} />}
        {item.media && <>
            <CitationVisuals chunkId={item.media.chunkId} pdfUrl={getPdfUrl(item.media)} kind={item.media.kind} number={item.media.number} />
            <a href={getMediaImageUrl(item.media, "full")} target="_blank" rel="noreferrer">打开高清原图</a>
        </>}
        <button type="button" className="citation-expand-btn" onClick={() => onExpand(item.id)}>展开相邻关系</button>
        {connected.length > 0 && <ul className="graph-edge-list">{connected.map(edge =>
            <li key={edge.id}><button type="button" className="citation-expand-btn" onClick={() => onEdge(edge)}>
                {relations[edge.type]} · {edge.evidence.map(source => `第 ${source.page} 页`).join(" / ")}
            </button></li>)}</ul>}
    </section>;
}
