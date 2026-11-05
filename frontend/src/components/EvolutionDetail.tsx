import { getMediaImageUrl, getPdfUrl } from "../api";
import CitationVisuals from "./CitationVisuals";
import { statusLabels, studyLabels } from "./auditTypes";
import { relationLabels, type EvidenceRef, type TimelineEvent, type TimelineRelation } from "./evolutionTypes";

const conditionLabels: Record<string, string> = { group: "实验组", metric: "指标", control: "对照" };

function Quote({ item }: { item: EvidenceRef }) {
    return <section className="graph-source-quote">
        <p>{item.excerpt}</p>
        <a href={getPdfUrl(item)} target="_blank" rel="noreferrer">{item.source} · PDF 第 {item.page} 页</a>
    </section>;
}

export default function EvolutionDetail({ event, relation, claimId, onClaim }: {
    event?: TimelineEvent; relation?: TimelineRelation; claimId?: string; onClaim: (id: string) => void;
}) {
    if (relation) return <section aria-label="演化关系详情">
        <h3>{relationLabels[relation.type]}</h3>
        <p>{relation.sameYear ? "同年发表，先后顺序未判定。" : "按发表年排列。关系依据来自原文。"}</p>
        {!!relation.basis.length && <ul>{relation.basis.map(note => <li key={note}>{note}</li>)}</ul>}
        {relation.references.map(ref => <Quote key={ref.id} item={ref} />)}
    </section>;
    if (!event) return <p>选择时间轴上的论文，核对发表年和原文。</p>;
    const claim = event.claims.find(item => item.claimId === claimId) ?? event.claims[0];
    return <section aria-label="时间事件详情">
        <h3>{event.year} · {event.source}</h3>
        {event.method && <p>{studyLabels[event.method.studyType]}</p>}
        <details>
            <summary>出版年份依据</summary>
            <p>{event.publication.excerpt}</p>
            {event.publication.onlineYear && <p>在线记录 · {event.publication.onlineYear}<br />{event.publication.onlineExcerpt}</p>}
            {event.publication.doi && <p>DOI {event.publication.doi}</p>}
            <a href={getPdfUrl({ ...event, page: 1 })} target="_blank" rel="noreferrer">打开 PDF 首页</a>
        </details>
        {event.claims.length > 1 && <label className="evolution-claim-choice">选择原文观点
            <select value={claim?.claimId ?? ""} onChange={e => onClaim(e.target.value)}>
                {event.claims.map(item => <option key={item.claimId} value={item.claimId}>{item.statement}</option>)}
            </select>
        </label>}
        {claim && <>
            <h3>原文观点</h3>
            <p>{claim.statement}</p>
            {Object.entries(claim.conditions).filter(([key,value]) => conditionLabels[key] && value).map(([key,value]) =>
                <p key={key} className="research-reading-note">{conditionLabels[key]} · {value}</p>)}
            {claim.references.map(ref => <Quote key={ref.id} item={ref} />)}
            {claim.media.map(item => <section key={item.mediaId}>
                <CitationVisuals chunkId={item.chunkId} pdfUrl={getPdfUrl(item)} kind={item.kind} number={item.number} />
                <a href={getMediaImageUrl(item, "full")} target="_blank" rel="noreferrer">打开高清图表</a>
            </section>)}
        </>}
        {event.method?.reference && <details><summary>原文测量方法</summary><Quote item={event.method.reference} /></details>}
        {event.audit && <details><summary>可靠性审计 · {event.audit.status === "completed" ? "已检查" : "范围不足"}</summary>
            {Object.entries(event.audit.findings).map(([status,count]) => <p key={status}>{statusLabels[status]} · {count} 项</p>)}
        </details>}
    </section>;
}
