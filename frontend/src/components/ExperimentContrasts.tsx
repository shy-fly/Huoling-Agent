import { useState, type ReactNode } from "react";
import { getPdfUrl } from "../api";

export type ContrastSource = Pick<Parameters<typeof getPdfUrl>[0], "source" | "collection">;
type Cell = { group: string; header: string; verifiedValue: string; column: number };
type Table = { page: number; tableIndex: number; provenance?: string; contrasts: Array<{ treatment: Cell; control: Cell; controlEvidence?: { page: number; quote: string } }> };
export type GroupTables = Record<string, Table[]>;

export default function ExperimentContrasts({ tables, sources, challenge }: {
    tables: GroupTables;
    sources: Record<string, ContrastSource>;
    challenge?: (claim: string, id: string, page: number, reportHost: HTMLElement | null) => ReactNode;
}) {
    const [reportHost, setReportHost] = useState<HTMLDivElement | null>(null);
    const matched = Object.entries(tables).flatMap(([id, items]) => items.filter(table => table.contrasts.length)
        .map(table => ({ id, table, source: sources[id] })));
    if (!matched.length) return null;
    return <section aria-label="实验组对照">
        <h3>原文实验对照</h3>
        <p>这里展示原文报告的数值。是否构成反证仍需审查。</p>
        {matched.map(({ id, table, source }) => <div key={`${id}:${table.page}:${table.tableIndex}`}>
            <a href={getPdfUrl({ ...source, page: table.page })} target="_blank" rel="noreferrer">{source.source} · 第 {table.page} 页</a>
            <div className="compare-table" tabIndex={0}>
                <table><thead><tr><th>原文指标</th><th>处理组</th><th>对照组</th></tr></thead>
                    <tbody>{table.contrasts.map(({ treatment, control }) => (
                        <tr key={`${treatment.group}:${treatment.column}`}>
                            <td>{treatment.header}</td><td>{treatment.group} · {treatment.verifiedValue}</td>
                            <td>{control.group} · {control.verifiedValue}
                                {challenge?.(`${treatment.header}: ${treatment.group} ${treatment.verifiedValue} vs ${control.group} ${control.verifiedValue}. Does the reported treatment change this outcome under the experimental conditions?`, id, table.page, reportHost)}
                            </td>
                        </tr>
                    ))}</tbody>
                </table>
            </div>
            {table.contrasts[0].controlEvidence && <p>{table.contrasts[0].controlEvidence.quote} · PDF 第 {table.contrasts[0].controlEvidence.page} 页</p>}
        </div>)}
        {challenge && <div className="contrast-reports" ref={setReportHost} />}
    </section>;
}

