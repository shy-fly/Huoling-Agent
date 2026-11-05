import { useEffect, useRef, useState } from "react";
import Icon from "./Icon";

interface HistoryItem {
    id: string;
    title: string;
    running?: boolean;
}

interface ChatHistoryProps {
    open: boolean;
    items: HistoryItem[];
    activeId: string | null;
    onClose: () => void;
    onNew: () => void;
    onOpen: (id: string) => void;
    onRename: (id: string, title: string) => void;
    onDelete: (id: string) => void;
}

export default function ChatHistory({ open, items, activeId, onClose, onNew, onOpen, onRename, onDelete }: ChatHistoryProps) {
    const dialog = useRef<HTMLDialogElement>(null);
    const [width, setWidth] = useState(250);
    function resize(value: number) {
        const next = Math.min(360, Math.max(200, value));
        setWidth(next);
        dialog.current?.closest<HTMLElement>(".research-workspace")?.style.setProperty("--history-width", `${next}px`);
    }
    const [editId, setEditId] = useState<string | null>(null);
    const [title, setTitle] = useState("");
    const [deleteId, setDeleteId] = useState<string | null>(null);

    useEffect(() => {
        const panel = dialog.current;
        if (!panel) return;
        if (open && !panel.open) panel.show();
        if (!open && panel.open) panel.close();
    }, [open]);

    useEffect(() => {
        if (!open) return;
        const closeOnEscape = (event: KeyboardEvent) => {
            if (event.key === "Escape") dialog.current?.close();
        };
        window.addEventListener("keydown", closeOnEscape);
        return () => window.removeEventListener("keydown", closeOnEscape);
    }, [open]);

    return (
        <dialog id="chat-history" className="chat-history" ref={dialog} aria-label="聊天记录" onClose={() => {
            setEditId(null);
            setDeleteId(null);
            onClose();
        }}>
            <div className="history-resize" role="separator" tabIndex={0} aria-label="调整侧栏宽度" aria-orientation="vertical"
                aria-valuemin={200} aria-valuemax={360} aria-valuenow={width}
                onPointerDown={event => {
                    event.currentTarget.setPointerCapture(event.pointerId);
                    dialog.current?.closest(".research-workspace")?.classList.add("history-resizing");
                }}
                onPointerMove={event => {
                    if (event.currentTarget.hasPointerCapture(event.pointerId)) resize(event.clientX);
                }}
                onLostPointerCapture={() => dialog.current?.closest(".research-workspace")?.classList.remove("history-resizing")}
                onKeyDown={event => {
                    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
                    event.preventDefault();
                    resize(width + (event.key === "ArrowRight" ? 10 : -10));
                }} />
            <div className="history-heading">
                <span className="history-brand">火灵</span>
                <button type="button" className="workspace-icon" aria-label="收起聊天记录" title="收起聊天记录" onClick={() => dialog.current?.close()}>
                    <Icon name="sidebar" size={20} />
                </button>
            </div>
            <button type="button" className="history-new" onClick={onNew}>
                <Icon name="edit" size={18} /> 新对话
            </button>
            <h2 className="history-section-title">最近问答</h2>
            {items.length === 0 && <p className="history-empty">回答结束后，会保存在这个浏览器里。</p>}
            <ul className="history-list">
                {items.map((item) => (
                    <li key={item.id} className="history-item">
                        {editId === item.id ? (
                            <form className="history-edit" onSubmit={(event) => {
                                event.preventDefault();
                                if (!title.trim()) return;
                                onRename(item.id, title.trim());
                                setEditId(null);
                            }}>
                                <input autoFocus aria-label="对话名称" maxLength={100} value={title} onChange={(event) => setTitle(event.target.value)} />
                                <button type="submit" className="history-text" disabled={!title.trim()}>保存</button>
                                <button type="button" className="history-text" onClick={() => setEditId(null)}>取消</button>
                            </form>
                        ) : (
                            <>
                                <div className="history-row">
                                <button type="button" className="history-item-open" aria-current={item.id === activeId ? "true" : undefined}
                                    onClick={() => onOpen(item.id)}><span>{item.title}</span>{item.running && <small>生成中</small>}</button>
                                {deleteId !== item.id && (
                                    <details className="history-menu">
                                        <summary aria-label={`管理 ${item.title}`}>···</summary>
                                        <div className="history-item-actions">
                                            <button type="button" className="history-text history-rename" onClick={() => {
                                                setTitle(item.title);
                                                setEditId(item.id);
                                                setDeleteId(null);
                                            }}>重命名</button>
                                            <button type="button" className="history-text history-delete" onClick={() => {
                                                setDeleteId(item.id);
                                                setEditId(null);
                                            }}>删除</button>
                                        </div>
                                    </details>
                                )}
                                </div>
                                {deleteId === item.id ? (
                                    <div className="history-item-actions">
                                        <span>删除这条问答？</span>
                                        <button type="button" className="history-text history-confirm-delete" onClick={() => {
                                            onDelete(item.id);
                                            setDeleteId(null);
                                        }}>删除</button>
                                        <button type="button" className="history-text" onClick={() => setDeleteId(null)}>取消</button>
                                    </div>
                                ) : null}
                            </>
                        )}
                    </li>
                ))}
            </ul>
        </dialog>
    );
}
