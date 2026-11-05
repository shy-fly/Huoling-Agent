import type { getPdfUrl } from "../api";
import type { GraphMedia } from "./evidenceGraphTypes";

export type EvolutionOrigin = "compare" | "graph" | "gaps" | "design" | "audit";
export type EvolutionContext = {
    question: string; returnTo: EvolutionOrigin; paperIds?: string[]; graphId?: string; claimId?: string;
};
export type EvidenceRef = Parameters<typeof getPdfUrl>[0] & { id?: string; evidenceId?: string; excerpt: string };
export type TimelineClaim = {
    claimId: string; statement: string; conditions: Record<string, string>; references: EvidenceRef[]; media: GraphMedia[];
};
export type TimelineEvent = {
    eventId: string; paperId: string; year: number; source: string; collection: string;
    publication: { year: number; excerpt: string; doi?: string; onlineYear?: number; onlineExcerpt?: string };
    claims: TimelineClaim[];
    method?: { studyType: string; reference: EvidenceRef | null };
    audit?: { auditId: string; status: string; findings: Record<string, number> };
};
export type TimelineRelation = {
    relationId: string; sourceEventId: string; targetEventId: string; type: string; sameYear: boolean;
    references: EvidenceRef[]; basis: string[];
};
export type EvolutionReport = {
    analysisId: string; events: TimelineEvent[]; relations: TimelineRelation[];
    periods: { startYear: number; endYear: number; paperCount: number; experimentRecordCount: number; directEvidenceCount: number }[];
    scope: { candidateCount: number; includedPaperCount: number; claimPaperCount: number; claimYears: number[];
        missingYear: number; duplicates: number; outsideRange: number; startYear: number | null; endYear: number | null };
    summary: { status: string; relations: Record<string, number>; limitations: string[] };
};
export const relationLabels: Record<string, string> = {
    notComparableWith: "可比性不足", supports: "支持", contradicts: "反对", qualifies: "条件限定",
};
