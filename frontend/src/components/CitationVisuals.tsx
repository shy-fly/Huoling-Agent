import { useEffect, useState } from "react";
import { apiGet } from "../api";

interface VisualEvidence {
    kind: "figure" | "table";
    number: string;
    caption: string;
    png: string;
}

export default function CitationVisuals({ chunkId, pdfUrl, kind, number, quiet = false }: { chunkId: number; pdfUrl: string; kind?: VisualEvidence["kind"]; number?: string; quiet?: boolean }) {
    const [visuals, setVisuals] = useState<VisualEvidence[] | null>(null);
    const [failed, setFailed] = useState(false);
    useEffect(() => {
        const controller = new AbortController();
        const query = kind && number ? "?" + new URLSearchParams({ kind, number }) : "";
        apiGet<{ visuals: VisualEvidence[] }>(`/v1/research/chunks/${chunkId}/visuals${query}`, controller.signal)
            .then((data) => {
                if (!controller.signal.aborted) setVisuals(data.visuals);
            })
            .catch(() => {
                if (!controller.signal.aborted) setFailed(true);
            });
        return () => controller.abort();
    }, [chunkId, kind, number]);

    if (quiet && (failed || !visuals?.length)) return null;
    if (failed) return <p>预览暂时打不开。可以看原页。</p>;
    if (!visuals) return <p role="status">正在查找本页图表…</p>;
    if (!visuals.length) return <p>这页没有图表预览。可以看原页。</p>;
    return visuals.map((visual) => (
        <figure className="citation-visual" key={`${visual.kind}-${visual.number}`}>
            <a href={pdfUrl} target="_blank" rel="noopener noreferrer">
                <img
                    loading="lazy"
                    src={`data:image/png;base64,${visual.png}`}
                    alt={`${visual.kind === "figure" ? "图" : "表"} ${visual.number}，点击打开原文页`}
                />
            </a>
            <figcaption>{visual.caption}</figcaption>
        </figure>
    ));
}

