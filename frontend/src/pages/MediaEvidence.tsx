import { useRef, useState, type FormEvent } from "react";
import { apiPost, getMediaImageUrl, getPdfUrl } from "../api";
import Icon from "../components/Icon";

export type MediaContext = { question: string; paperIds: string[] };

type Evidence = Parameters<typeof getPdfUrl>[0] & {
    chunkId: number;
    mediaId: string;
    kind: "figure" | "table";
    number: string;
    title: string;
    caption: string;
    relatedChunks: { chunkId: number; page: number; excerpt: string }[];
    tableStatus?: "extracted" | "needsReview";
    rawRows?: string[][];
};

type SearchResult = {
    items: Evidence[];
    scannedPages: number;
    reviewPages: number;
    failedPages: number;
};

const label = (item: Evidence) => `${item.kind === "figure" ? "图" : "表"} ${item.number}`;

export default function MediaEvidence({ context, onBack }: { context?: MediaContext; onBack: () => void }) {
    const [question, setQuestion] = useState(context?.question.slice(0, 500) ?? "");
    const [kind, setKind] = useState("");
    const [result, setResult] = useState<SearchResult>();
    const [selected, setSelected] = useState<Evidence>();
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const detail = useRef<HTMLElement>(null);
    const sources = useRef<HTMLElement>(null);

    async function search(event: FormEvent) {
        event.preventDefault();
        if (busy || !question.trim()) return;
        setBusy(true);
        setError("");
        setResult(undefined);
        setSelected(undefined);
        try {
            const data = await apiPost<SearchResult>("/v1/research/media/search", {
                question: question.trim(), kind: kind || null, paperIds: context?.paperIds ?? [],
            });
            setResult(data);
            setSelected(data.items[0]);
        } catch {
            setError("检索暂时失败。请重试。");
        } finally {
            setBusy(false);
        }
    }

    function showDetail(item: Evidence) {
        setSelected(item);
        detail.current?.scrollIntoView({ block: "start" });
    }

    return <section className="compare-workbench media-workbench">
        <div>
            {context && <button type="button" className="citation-expand-btn" onClick={onBack}>返回文献比较</button>}
            <h1>图表证据</h1>
            <p>从论文里找原图、图注和表格。</p>
            {context && <p>检索范围 · 比较中的 {context.paperIds.length} 篇论文</p>}
            <details className="workbench-inputs" open={!result}>
                <summary>检索条件</summary>
                <form className="compare-form media-search" onSubmit={search}>
                    <label>找什么图表？<textarea required maxLength={500} value={question}
                        onChange={event => setQuestion(event.target.value)} placeholder="例如 Yang 2018 的图 1" /></label>
                    <div className="media-actions">
                        <label>类型<select value={kind} onChange={event => setKind(event.target.value)}>
                            <option value="">图和表</option><option value="figure">图</option><option value="table">表</option>
                        </select></label>
                        <button className="secondary-action" type="submit" disabled={busy}><Icon name="book" />查图表</button>
                    </div>
                </form>
            </details>
            {busy && <p role="status">正在核对论文原页…</p>}
            {error && <p role="alert">{error}</p>}
            {result && <article className="research-reading" ref={detail}>
                <h2>{selected ? `${label(selected)} · PDF 第 ${selected.page} 页` : "检索结果"}</h2>
                {selected && <p className="research-reading-note">{selected.title}</p>}
                <p>找到 {result.items.length} 项 · 查过 {result.scannedPages} 页</p>
                {(result.reviewPages > 0 || result.failedPages > 0) &&
                    <p>版面待核验 {result.reviewPages} 页 · 读取失败 {result.failedPages} 页</p>}
                {result.items.length === 0 && <p>这次没有找到可裁剪的图表。</p>}
                {result.items.length > 1 && <button type="button" className="citation-expand-btn media-index-jump"
                    onClick={() => sources.current?.scrollIntoView({ block: "start" })}>浏览图表索引</button>}
                {selected && <>
                    <figure className="citation-visual media-original">
                        <a className="media-full" href={getMediaImageUrl(selected, "full")} target="_blank" rel="noreferrer"
                            aria-label="打开高清裁剪图"><img src={getMediaImageUrl(selected, "full")} alt={label(selected)} /></a>
                        <figcaption>{selected.caption}</figcaption>
                    </figure>
                    <p className="media-detail-links">
                        <a href={getMediaImageUrl(selected, "full")} target="_blank" rel="noreferrer">打开高清图</a>
                        <a href={getPdfUrl(selected)} target="_blank" rel="noreferrer">打开 PDF 原页 <Icon name="external" size={14} /></a>
                    </p>
                    {selected.tableStatus === "needsReview" && <p>表格结构待核验，请读原图。</p>}
                    {!!selected.rawRows?.length && <details><summary>查看原始表格行列</summary>
                        <p>自动提取，数值请核对原图。</p>
                        <div className="compare-table"><table aria-label="原始表格行列"><tbody>
                            {selected.rawRows.map((row, index) => <tr key={index}>{row.map((cell, col) => <td key={col}>{cell}</td>)}</tr>)}
                        </tbody></table></div></details>}
                </>}
            </article>}
        </div>
        {result && selected && <aside ref={sources} aria-label="图表索引">
            <h2>图表索引</h2>
            <ul className="media-results">
                {result.items.map(item => <li key={item.mediaId}>
                    <button type="button" aria-pressed={item.mediaId === selected.mediaId} onClick={() => showDetail(item)}>
                        <img loading="lazy" src={getMediaImageUrl(item, "thumb")} alt="" />
                        <span><strong>{label(item)} · 第 {item.page} 页</strong><small>{item.title}</small></span>
                    </button>
                </li>)}
            </ul>
            {selected.relatedChunks.length > 0 && <h2>同页正文</h2>}
            {selected.relatedChunks.map(chunk => <details key={chunk.chunkId}>
                <summary>同页正文 · 第 {chunk.page} 页</summary><p>{chunk.excerpt}</p>
            </details>)}
        </aside>}
    </section>;
}
