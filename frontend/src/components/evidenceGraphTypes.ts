import type { getPdfUrl } from "../api";

export type GraphContext = { question: string; paperIds: string[]; sourcePages?: Record<string, number[]> };
export type Source = Parameters<typeof getPdfUrl>[0] & { id: string; excerpt: string; chunkId?: number | null };
export type GraphMedia = Parameters<typeof getPdfUrl>[0] & {
    chunkId: number; mediaId: string; caption: string; kind: "figure" | "table"; number: string;
};
export type GraphNode = {
    id: string; type: "paper" | "experiment" | "claim" | "evidence" | "variable" | "media"; label: string;
    attributes?: Record<string, string>; page?: number; source?: string; collection?: string;
    excerpt?: string; media?: GraphMedia;
};
export type GraphEdge = {
    id: string; type: string; source: string; target: string; evidence: Source[];
    method: string; notes: string[]; verificationStatus: string;
};
export type GraphData = { nodes: GraphNode[]; edges: GraphEdge[] };
export type GraphSummary = {
    graphId: string; nodeCount: number; edgeCount: number; verifiedPaperCount: number; truncated: boolean;
};
export const relations: Record<string, string> = {
    reports: "报告", derivedFrom: "来自原文", usesVariable: "研究变量",
    citesMedia: "原句提及图表", notComparableWith: "可比性不足",
};
export const kinds: Record<GraphNode["type"], string> = {
    paper: "论文", experiment: "实验", claim: "研究主张", evidence: "原文", variable: "变量", media: "图表",
};
export const graphRoute = "/v1/research/knowledge-graph";
