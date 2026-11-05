export type QaCompareContext = {
    question: string;
    traceId: string;
    evidence: { chunkId: number; source: string; collection: string; page: number }[];
};

export function qaCompareContext(question: string, response: {
    trace_id: string;
    chunks: { chunk_id: number; source: string; collection: string; page: number | null }[];
}): QaCompareContext | undefined {
    const evidence = response.chunks.filter(chunk => chunk.page != null && chunk.page > 0)
        .map(chunk => ({ chunkId: chunk.chunk_id, source: chunk.source,
            collection: chunk.collection, page: chunk.page as number }));
    return evidence.length ? { question, traceId: response.trace_id, evidence } : undefined;
}
