const API = import.meta.env.VITE_API_URL || "/api";

type ApiPayload = { ok?: boolean; error?: string };

function adminHeaders(): Record<string, string> {
  const token = typeof window === "undefined" ? "" : window.sessionStorage.getItem("firefairy-admin-token") || "";
  return token ? { "X-Admin-Token": token } : {};
}

async function parseApiResponse<T>(r: Response, opts?: { requireOk?: boolean }): Promise<T> {
  const text = await r.text();
  if (!r.ok) {
    throw new Error(text || r.statusText || `HTTP ${r.status}`);
  }
  let data: T & ApiPayload;
  try {
    data = JSON.parse(text) as T & ApiPayload;
  } catch {
    throw new Error(text || "invalid JSON response");
  }
  if (opts?.requireOk && typeof data === "object" && data !== null && "ok" in data && !(data as ApiPayload).ok) {
    throw new Error((data as ApiPayload).error || "request failed");
  }
  return data;
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(`${API}${path}`, { headers: adminHeaders(), signal });
  return parseApiResponse<T>(r);
}

export async function apiPost<T>(path: string, body: unknown = {}, signal?: AbortSignal): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...adminHeaders() },
    body: JSON.stringify(body),
    signal,
  });
  return parseApiResponse<T>(r, { requireOk: true });
}

type StreamEvent<T, Evidence> =
    | { type: "evidence"; chunks: Evidence[] }
    | { type: "delta"; text: string }
    | { type: "result"; data: T }
    | { type: "error"; message: string };

export async function apiPostStream<T, Evidence = unknown>(
    path: string,
    body: unknown,
    signal: AbortSignal,
    onDelta: (text: string) => void,
    onEvidence?: (chunks: Evidence[]) => void,
): Promise<T> {
    const response = await fetch(`${API}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...adminHeaders() },
        body: JSON.stringify(body),
        signal,
    });
    if (!response.ok) {
        return parseApiResponse<T>(response);
    }
    if (!response.body || !response.headers.get("content-type")?.startsWith("application/x-ndjson")) {
        throw new Error("服务未返回有效的流式响应。");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = "";
    try {
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            const lines = (pending + decoder.decode(value, { stream: true })).split("\n");
            pending = lines.pop() ?? "";
            for (const line of lines) {
                if (!line.trim()) continue;
                const event = JSON.parse(line) as StreamEvent<T, Evidence>;
                if (event.type === "result") return event.data;
                if (event.type === "error") throw new Error(event.message);
                if (event.type === "delta") onDelta(event.text);
                if (event.type === "evidence") onEvidence?.(event.chunks);
            }
        }
        throw new Error("回答中断，请重试。");
    } finally {
        await reader.cancel().catch(() => {});
        reader.releaseLock();
    }
}

export async function apiPostQuery<T>(path: string, params: Record<string, string> = {}): Promise<T> {
  const qs = new URLSearchParams(params);
  const r = await fetch(`${API}${path}?${qs}`, { method: "POST", headers: adminHeaders() });
  return parseApiResponse<T>(r, { requireOk: true });
}

export async function apiDelete<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`, { method: "DELETE", headers: adminHeaders() });
  return parseApiResponse<T>(r, { requireOk: true });
}

export async function apiPut<T>(path: string, body: unknown = {}): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...adminHeaders() },
    body: JSON.stringify(body),
  });
  return parseApiResponse<T>(r, { requireOk: true });
}

export async function apiPatch<T>(path: string, body: unknown = {}): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...adminHeaders() },
    body: JSON.stringify(body),
  });
  return parseApiResponse<T>(r, { requireOk: true });
}

export interface RagCitation {
  chunk_id?: number;
  citation?: string;
  collection?: string;
  title?: string;
  snippet?: string;
  score?: number;
}

export interface ResearchChunk {
  chunk_id: number;
  title: string;
  source: string;
  collection: string;
  citation: string;
  page: number;
  snippet: string;
  score: number;
}

export interface ResearchQAResponse {
  ok: boolean;
  answer: string;
  citations: string[];
  chunks: ResearchChunk[];
  trace_id: string;
  agent_id: string;
  runtime: {
    answer_mode: string;
    provider: string;
    model: string | null;
    knowledge_hits: number;
    qa_ready: boolean;
  };
}

export interface AgentProfile {
  id: string;
  name: string;
  description?: string;
  rag_collections: string[];
  is_default?: boolean;
}

export interface AgentsResponse {
  ok: boolean;
  default_agent_id: string;
  agents: AgentProfile[];
}
export function getPdfUrl(chunk: Pick<ResearchChunk, "source" | "page" | "collection">) {
    const filename = encodeURIComponent(chunk.source || "");
    const page = chunk.page || 1;
    const collection = encodeURIComponent(chunk.collection || "literature_inhibition");
    return `${API}/v1/research/literature/${filename}?collection=${collection}&page=${page}#page=${page}`;
}

export function getMediaImageUrl(item: { chunkId: number; mediaId: string }, size: "thumb" | "full") {
    return `${API}/v1/research/media/${item.chunkId}/${encodeURIComponent(item.mediaId)}/image?size=${size}`;
}
