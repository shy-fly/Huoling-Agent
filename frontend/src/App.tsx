import { useEffect, useRef, useState } from "react";
import Icon from "./components/Icon";
import MediaEvidence, { type MediaContext } from "./pages/MediaEvidence";
import ExperimentDesign, { type DesignContext } from "./pages/ExperimentDesign";
import ResearchGaps, { type GapContext } from "./pages/ResearchGaps";
import ResearchCompare from "./pages/ResearchCompare";
import ResearchQA from "./pages/ResearchQA";
import type { QaCompareContext } from "./components/qaCompareContext";
import EvidenceGraph from "./pages/EvidenceGraph";
import type { GraphContext } from "./components/evidenceGraphTypes";
import ReliabilityAudit from "./pages/ReliabilityAudit";
import type { AuditContext } from "./components/auditTypes";
import ConclusionEvolution from "./pages/ConclusionEvolution";
import type { EvolutionContext } from "./components/evolutionTypes";

export default function App() {
    const [historyOpen, setHistoryOpen] = useState(false);
    const [mode, setMode] = useState<"qa" | "compare" | "gaps" | "design" | "media" | "graph" | "audit" | "evolution">("qa");
    const [gapContext, setGapContext] = useState<GapContext>();
    const [compareContext, setCompareContext] = useState<QaCompareContext>();
    const [designContext, setDesignContext] = useState<DesignContext>();
    const [mediaContext, setMediaContext] = useState<MediaContext>();
    const [graphContext, setGraphContext] = useState<GraphContext>();
    const [auditContext, setAuditContext] = useState<AuditContext>();
    const [evolutionContext, setEvolutionContext] = useState<EvolutionContext>();
    const nav = useRef<HTMLElement>(null);
    useEffect(() => {
        nav.current?.querySelector("[aria-current=page]")?.scrollIntoView({ block: "nearest", inline: "nearest" });
    }, [mode]);
    function openGaps(context?: GapContext) {
        setHistoryOpen(false);
        setGapContext(context);
        setMode("gaps");
    }
    function openCompare(context: QaCompareContext) {
        setHistoryOpen(false);
        setCompareContext(context);
        setMode("compare");
    }
    function openDesign(context: DesignContext) {
        setHistoryOpen(false);
        setDesignContext(context);
        setMode("design");
    }
    function openMedia(context?: MediaContext) {
        setHistoryOpen(false);
        setMediaContext(context);
        setMode("media");
    }
    function openGraph(context?: GraphContext) {
        setHistoryOpen(false);
        setGraphContext(context);
        setMode("graph");
    }
    function openAudit(context?: AuditContext) {
        setHistoryOpen(false);
        setAuditContext(context);
        setMode("audit");
    }
    function openEvolution(context?: EvolutionContext) {
        setHistoryOpen(false);
        setEvolutionContext(context);
        setMode("evolution");
    }
    const evolutionOrigin = mode === "evolution" ? evolutionContext?.returnTo : undefined;
    const showAudit = mode === "audit" || evolutionOrigin === "audit";
    const showGraph = mode === "graph" || evolutionOrigin === "graph" || (showAudit && auditContext?.returnTo === "graph");
    const showGaps = mode === "gaps" || evolutionOrigin === "gaps" || (mode === "design" && designContext?.origin === "gaps");
    const showCompare = mode === "compare" || (showGaps && gapContext) || (mode === "media" && mediaContext) ||
        (showGraph && graphContext) || (showAudit && auditContext?.returnTo === "compare") || evolutionOrigin === "compare";
    return (
        <div className="research-workspace">
            <header className="workspace-bar">
                <div className="workspace-bar-inner">
                    <button type="button" className="history-trigger workspace-icon" aria-haspopup="dialog"
                        aria-label={historyOpen ? "收起聊天记录" : "打开聊天记录"} title="聊天记录"
                        aria-controls="chat-history" aria-expanded={historyOpen} onClick={() => {
                            setMode("qa");
                            setHistoryOpen(!historyOpen);
                        }}>
                        <Icon name="sidebar" size={20} />
                    </button>
                    <div className="workspace-brand">
                        <span className="workspace-wordmark">火灵</span>
                        <span className="workspace-label">研究笔记</span>
                    </div>
                    <nav className="workspace-nav" aria-label="研究工作区" ref={nav}>
                        <button type="button" aria-current={mode === "qa" ? "page" : undefined} onClick={() => setMode("qa")}>科研问答</button>
                        <button type="button" aria-current={mode === "compare" ? "page" : undefined} onClick={() => {
                            setHistoryOpen(false);
                            setMode("compare");
                        }}>文献比较</button>
                        <button type="button" aria-current={mode === "gaps" ? "page" : undefined} onClick={() => openGaps()}>空白雷达</button>
                        <button type="button" aria-current={mode === "design" ? "page" : undefined} onClick={() => {
                            setHistoryOpen(false);
                            setDesignContext(undefined);
                            setMode("design");
                        }}>实验设计</button>
                        <button type="button" aria-current={mode === "media" ? "page" : undefined} onClick={() => openMedia()}>图表证据</button>
                        <button type="button" aria-current={mode === "graph" ? "page" : undefined} onClick={() => openGraph()}>证据图谱</button>
                        <button type="button" aria-current={mode === "audit" ? "page" : undefined} onClick={() => openAudit()}>可靠性审计</button>
                        <button type="button" aria-current={mode === "evolution" ? "page" : undefined} onClick={() => openEvolution()}>结论演化</button>
                    </nav>
                </div>
            </header>
            <main>
                <div hidden={mode !== "qa"}><ResearchQA onCompare={openCompare} historyOpen={historyOpen} closeHistory={() => setHistoryOpen(false)} /></div>
                {showCompare && <div hidden={mode !== "compare"}><ResearchCompare key={compareContext?.traceId ?? "default"} context={compareContext} onDesign={openDesign} onMedia={openMedia}
                    onGraph={openGraph} onAudit={openAudit} onEvolution={openEvolution} onGaps={openGaps} /></div>}
                {showGaps && <div hidden={mode !== "gaps"}>
                    <ResearchGaps key={gapContext ? JSON.stringify(gapContext) : "all"} context={gapContext}
                        onBack={() => setMode("compare")} onDesign={openDesign} onEvolution={openEvolution} /></div>}
                {(mode === "design" || evolutionOrigin === "design") && <div hidden={mode !== "design"}>
                    <ExperimentDesign key={designContext ? JSON.stringify(designContext) : "all"} context={designContext} onEvolution={openEvolution} /></div>}
                {mode === "media" && <MediaEvidence key={mediaContext?.paperIds.join(",") ?? "all"} context={mediaContext} onBack={() => setMode("compare")} />}
                {showGraph && <div hidden={mode !== "graph"}><EvidenceGraph key={graphContext?.question ?? "all"}
                    context={graphContext} onBack={() => setMode("compare")} onAudit={openAudit} onEvolution={openEvolution} /></div>}
                {showAudit && <div hidden={mode !== "audit"}><ReliabilityAudit context={auditContext}
                    onBack={() => setMode(auditContext?.returnTo ?? "qa")} onEvolution={openEvolution} /></div>}
                {mode === "evolution" && <ConclusionEvolution context={evolutionContext}
                    onBack={() => setMode(evolutionContext?.returnTo ?? "qa")} />}
            </main>
        </div>
    );
}
