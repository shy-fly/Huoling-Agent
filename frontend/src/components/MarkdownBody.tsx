import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getPdfUrl } from "../api";
import CitationVisuals from "./CitationVisuals";

type Citation = Omit<Parameters<typeof getPdfUrl>[0], "page"> & { page: number | null; chunk_id: number };

export default function MarkdownBody({
    text, className = "", citations,
}: {
    text: string;
    className?: string;
    citations?: Citation[];
}) {
    return (
        <div className={`markdown-body ${className}`.trim()}>
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
                p: ({ node, children }) => {
                    const start = node?.position?.start.offset ?? 0;
                    const end = node?.position?.end.offset ?? start;
                    const sources = new Map<string, { url: string; citation: Citation; kind: "figure" | "table"; number: string }>();
                    for (const match of text.slice(start, end).matchAll(/\[(\d+)\]\s*[（(]\s*(图|表)\s*(s?\d+[a-z]?(?:\([a-z]\))?)\s*[）)]/gi)) {
                        const citation = citations?.[Number(match[1]) - 1];
                        if (!citation?.page) continue;
                        const url = getPdfUrl({ ...citation, page: citation.page });
                        const kind = match[2] === "图" ? "figure" : "table";
                        const number = match[3].toLowerCase();
                        sources.set(`${url}:${kind}:${number}`, { url, citation, kind, number });
                    }
                    return <><p>{children}</p>{[...sources].map(([key, { url, citation, kind, number }]) => (
                        <CitationVisuals key={key} chunkId={citation.chunk_id} pdfUrl={url} kind={kind} number={number} quiet />
                    ))}</>;
                },
            }}>{text}</ReactMarkdown>
        </div>
    );
}

