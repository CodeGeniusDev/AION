import type {
  AgentsResponse,
  ChatRequest,
  ChatResponse,
  DashboardData,
  MemoryResponse,
  ResearchResponse,
  TasksResponse,
  WorkflowsResponse,
} from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Default timeout for GET requests (fast, backend should respond instantly). */
const DEFAULT_TIMEOUT_MS = 8_000;

/**
 * Chat pipeline runs sequential agents × 30 s Gemini timeout each + synthesis
 * + possible revision, so a live request can legitimately take 60-120 s.
 * 120 s covers the worst case without hanging indefinitely.
 */
const CHAT_TIMEOUT_MS = 120_000;

async function request<T>(path: string, init?: RequestInit & { timeout?: number }): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), init?.timeout ?? DEFAULT_TIMEOUT_MS);

  const { timeout: _timeout, ...fetchInit } = init ?? {};

  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...fetchInit,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...fetchInit?.headers },
    });
    if (!response.ok) throw new Error(`AION API returned ${response.status}`);
    return (await response.json()) as T;
  } finally {
    window.clearTimeout(timeout);
  }
}

export function getDashboard(): Promise<DashboardData> {
  return request<DashboardData>("/api/dashboard");
}

export function sendChatMessage(payload: ChatRequest): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify(payload),
    timeout: CHAT_TIMEOUT_MS,
  });
}

export function getAgents(): Promise<AgentsResponse> {
  return request<AgentsResponse>("/api/agents");
}

export function getTasks(): Promise<TasksResponse> {
  return request<TasksResponse>("/api/tasks");
}

export function getMemory(): Promise<MemoryResponse> {
  return request<MemoryResponse>("/api/memory");
}

export function getWorkflows(): Promise<WorkflowsResponse> {
  return request<WorkflowsResponse>("/api/workflows");
}

export function getResearch(): Promise<ResearchResponse> {
  return request<ResearchResponse>("/api/research");
}
