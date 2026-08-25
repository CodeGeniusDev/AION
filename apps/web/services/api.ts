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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 5000);

  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...init?.headers },
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
