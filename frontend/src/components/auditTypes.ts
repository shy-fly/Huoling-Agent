import type { getPdfUrl } from "../api";

export type AuditTarget =
    | { type: "paper"; paperId: string }
    | { type: "claim" | "relation"; graphId: string; entityId: string }
    | { type: "hypothesis"; paperId: string; page: number; claim: string };
export type AuditContext = { target: AuditTarget; label: string; returnTo: "graph" | "compare" };
export type Paper = { paperId: string; source: string; title: string };
export type Reference = Parameters<typeof getPdfUrl>[0] & {
    evidenceId: string; excerpt: string; visual?: { kind: "figure" | "table"; number: string; chunkId: number } | null;
};
export type Finding = {
    findingId: string; ruleId: string; category: string; label: string; status: string;
    observation: string; evidenceIds: string[]; checkedSections: string[]; uncertainty: string;
};
export type Study = {
    paperId: string; source: string; studyType: string; status: string;
    classificationEvidenceId: string | null; objectiveEvidenceId: string | null; methodEvidenceId: string | null;
    scope: { pages: number[]; sections: string[]; available: boolean; truncated: boolean };
    findings: Finding[];
};
export type AuditReport = {
    auditId: string; status: string; studies: Study[]; references: Reference[];
    claimAssessments: { claimId: string; statement: string; status: string; evidenceIds: string[];
        conditions: Record<string, string>; limitations: string[] }[];
};

export const auditRoute = "/v1/research/reliability-audit";
export const statusLabels: Record<string, string> = {
    reported: "已报告", notReported: "检查范围内未见", unclear: "仍不明确",
    notApplicable: "不适用", potentialIssue: "潜在问题", needsReview: "待复核",
    sourceReported: "原文报告", limitedComparability: "可比性有限",
};
export const studyLabels: Record<string, string> = {
    experimental: "实验研究", observational: "观察研究", review: "综述",
    computational: "计算或模拟", methodological: "方法学研究", unknown: "类型待确认",
};
export const sectionLabels: Record<string, string> = {
    front: "前文", methods: "方法", results: "结果", discussion: "讨论", limitations: "局限", conclusion: "结论",
};
