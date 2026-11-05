import { useRef, useState, type KeyboardEvent } from "react";
import { kinds, relations, type GraphData, type GraphEdge, type GraphNode } from "./evidenceGraphTypes";

const columns: GraphNode["type"][][] = [["paper"], ["experiment", "variable"], ["claim"], ["evidence", "media"]];
const short = (value: string) => value.length > 19 ? value.slice(0, 18) + "…" : value;

function activate(event: KeyboardEvent<SVGGElement>, action: () => void) {
    if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        action();
    }
}

export default function EvidenceGraphMap({ data, selected, onPick }: {
    data: GraphData; selected?: GraphNode | GraphEdge; onPick: (item: GraphNode | GraphEdge) => void;
}) {
    const [zoom, setZoom] = useState(1);
    const viewport = useRef<HTMLDivElement>(null);
    const grouped = columns.map(types => data.nodes.filter(node => types.includes(node.type)));
    const rows = Math.max(1, ...grouped.map(group => group.length));
    const height = Math.max(260, rows * 47 + 78);
    const positions = new Map(grouped.flatMap((group, column) => group.map((node, row) =>
        [node.id, { x: 16 + 166 * column, y: 65 + row * 47 + (rows - group.length) * 12 }] as const)));
    const activeIds = selected && "source" in selected && "target" in selected
        ? [selected.source, selected.target] : selected ? [selected.id] : [];
    const activeEdge = (edge: GraphEdge) => selected?.id === edge.id || activeIds.includes(edge.source) || activeIds.includes(edge.target);

    return <div className="graph-map">
        <div className="graph-map-tools" aria-label="图谱视图">
            <button type="button" className="citation-expand-btn" onClick={() => setZoom(Math.max(.8, zoom - .2))} disabled={zoom <= .8}>缩小</button>
            <button type="button" className="citation-expand-btn" onClick={() => setZoom(Math.min(2, zoom + .2))} disabled={zoom >= 2}>放大</button>
            <button type="button" className="citation-expand-btn" onClick={() => { setZoom(1); viewport.current?.scrollTo(0, 0); }}>重置视图</button>
        </div>
        <div className="graph-viewport" ref={viewport} tabIndex={0} aria-label="科学证据网络，可滚动">
            <svg className="graph-svg" viewBox={`0 0 672 ${height}`} style={{ width: `${zoom * 100}%`, minWidth: `${zoom * 600}px` }}
                aria-label="证据节点和关系">
                {["论文", "实验与变量", "研究主张", "原文与图表"].map((label, i) =>
                    <text className="graph-column" key={label} x={16 + i * 166} y={25}>{label}</text>)}
                {data.edges.map(edge => {
                    const start = positions.get(edge.source);
                    const end = positions.get(edge.target);
                    if (!start || !end) return null;
                    const path = start.x === end.x
                        ? `M${start.x},${start.y} C${start.x + 46},${start.y} ${end.x + 46},${end.y} ${end.x},${end.y}`
                        : `M${start.x},${start.y} C${(start.x + end.x) / 2},${start.y} ${(start.x + end.x) / 2},${end.y} ${end.x},${end.y}`;
                    return <g className="graph-edge" key={edge.id} data-active={activeEdge(edge)} data-relation={edge.type}
                        role="button" tabIndex={0} aria-label={relations[edge.type]}
                        onClick={() => onPick(edge)} onKeyDown={event => activate(event, () => onPick(edge))}>
                        <title>{relations[edge.type]}</title>
                        <path d={path} className="graph-edge-line" /><path d={path} className="graph-edge-hit" />
                    </g>;
                })}
                {data.nodes.map(node => {
                    const point = positions.get(node.id);
                    if (!point) return null;
                    return <g className="graph-node" key={node.id} data-type={node.type} data-active={activeIds.includes(node.id)}
                        transform={`translate(${point.x},${point.y})`} role="button" tabIndex={0}
                        aria-label={`${kinds[node.type]} · ${node.label}`} onClick={() => onPick(node)}
                        onKeyDown={event => activate(event, () => onPick(node))}>
                        <title>{node.label}</title>
                        <circle r={7} /><text y={-13}>{short(node.label)}</text>
                    </g>;
                })}
            </svg>
        </div>
    </div>;
}
