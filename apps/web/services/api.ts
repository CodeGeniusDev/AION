import type {
  AgentsResponse,
  AlertsResponse,
  AppSettings,
  ApprovalExecuteResponse,
  ApprovalRecord,
  ApprovalsResponse,
  AuditResponse,
  ChatRequest,
  ChatResponse,
  ConversationSummary,
  DashboardData,
  DesktopHealth,
  HealthData,
  MemoryRecordsResponse,
  MemoryResponse,
  ResearchResponse,
  StoredMessage,
  TaskDetail,
  TasksResponse,
  WorkflowCreatePayload,
  WorkflowData,
  WorkflowRunResponse,
  WorkflowsResponse,
} from "@/types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Default timeout for GET requests (fast, backend should respond instantly). */
const DEFAULT_TIMEOUT_MS = 8_000;

/**
 * Chat pipeline runs sequential agents × 30 s Gemini timeout each + synthesis
 * + possible revision, so a live request can legitimately take 60-120 s.
 * 120 s covers the worst case without hanging indefinitely.
 */
const CHAT_TIMEOUT_MS = 120_000;

async function request<T>(
  path: string,
  init?: RequestInit & { timeout?: number },
): Promise<T> {
  const controller = new AbortController();
  const fetchInit = init ?? {};
  window.setTimeout(
    () => controller.abort(),
    fetchInit.timeout ?? DEFAULT_TIMEOUT_MS,
  );

  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...fetchInit,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...fetchInit.headers },
    });
    if (!response.ok) throw new Error(`AION API returned ${response.status}`);
    return (await response.json()) as T;
  } finally {
    window.clearTimeout(fetchInit.timeout);
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

export function createWorkflow(payload: WorkflowCreatePayload): Promise<WorkflowData> {
  return request<WorkflowData>("/api/workflows", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Runs a workflow through the real WorkflowRunner (manual mode). Live agent
 * runs can take as long as a chat request, so it uses the long chat timeout. */
export function runWorkflow(id: string, input: string): Promise<WorkflowRunResponse> {
  return request<WorkflowRunResponse>(`/api/workflows/${encodeURIComponent(id)}/run`, {
    method: "POST",
    body: JSON.stringify({ input }),
    timeout: CHAT_TIMEOUT_MS,
  });
}

export function getResearch(): Promise<ResearchResponse> {
  return request<ResearchResponse>("/api/research");
}

// --- Health ---

export function getHealth(): Promise<HealthData> {
  return request<HealthData>("/health");
}

// --- Conversations ---

export function getConversations(): Promise<ConversationSummary[]> {
  return request<ConversationSummary[]>("/api/conversations");
}

export function getConversationMessages(
  conversationId: string,
): Promise<StoredMessage[]> {
  return request<StoredMessage[]>(
    `/api/conversations/${conversationId}/messages`,
  );
}

export function deleteConversation(
  conversationId: string,
): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/api/conversations/${conversationId}`, {
    method: "DELETE",
  });
}

// --- Memory Records ---

export function listMemoryRecords(params?: {
  memory_type?: string;
  limit?: number;
  offset?: number;
}): Promise<MemoryRecordsResponse> {
  const search = new URLSearchParams();
  if (params?.memory_type) search.set("memory_type", params.memory_type);
  if (params?.limit) search.set("limit", String(params.limit));
  if (params?.offset) search.set("offset", String(params.offset));
  const qs = search.toString();
  return request<MemoryRecordsResponse>(
    `/api/memories/records${qs ? `?${qs}` : ""}`,
  );
}

export function searchMemoryRecords(
  query: string,
  params?: { memory_type?: string; limit?: number },
): Promise<MemoryRecordsResponse> {
  const search = new URLSearchParams({ q: query });
  if (params?.memory_type) search.set("memory_type", params.memory_type);
  if (params?.limit) search.set("limit", String(params.limit));
  return request<MemoryRecordsResponse>(
    `/api/memories/records/search?${search.toString()}`,
  );
}

export function deleteMemoryRecord(
  memoryId: string,
): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/api/memories/records/${memoryId}`, {
    method: "DELETE",
  });
}

// --- Task Detail ---

export function getTask(taskId: string): Promise<TaskDetail> {
  return request<TaskDetail>(`/api/tasks/${taskId}`);
}

// --- Settings ---

export function getSettings(): Promise<AppSettings> {
  return request<AppSettings>("/api/settings");
}

export function updateSettings(settings: AppSettings): Promise<AppSettings> {
  return request<AppSettings>("/api/settings", {
    method: "PUT",
    body: JSON.stringify(settings),
  });
}

// --- Feedback ---

export function submitFeedback(
  taskId: string,
  sentiment: "up" | "down",
  comment?: string,
): Promise<{ accepted: boolean }> {
  return request<{ accepted: boolean }>("/api/feedback", {
    method: "POST",
    body: JSON.stringify({
      task_id: taskId,
      sentiment,
      comment: comment ?? "",
    }),
  });
}

// --- Save to Memory ---

export function saveToMemory(
  content: string,
  taskId?: string,
): Promise<{ saved: boolean; memory_id: string }> {
  return request<{ saved: boolean; memory_id: string }>(
    "/api/memories/save-content",
    {
      method: "POST",
      body: JSON.stringify({ content, task_id: taskId ?? "manual-save" }),
    },
  );
}

// --- SSE ---

/** URL for the SSE event stream for a given task. */
export function getEventsUrl(taskId: string): string {
  return `${API_URL}/api/events/${taskId}`;
}

// --- Alerts / Notifications ---

export function getAlerts(params?: {
  unread_only?: boolean;
  limit?: number;
}): Promise<AlertsResponse> {
  const search = new URLSearchParams();
  if (params?.unread_only) search.set("unread_only", "true");
  if (params?.limit) search.set("limit", String(params.limit));
  const qs = search.toString();
  return request<AlertsResponse>(`/api/alerts${qs ? `?${qs}` : ""}`);
}

export function markAlertsRead(
  alertIds: string[],
): Promise<{ updated: number }> {
  return request<{ updated: number }>("/api/alerts/mark-read", {
    method: "POST",
    body: JSON.stringify({ alert_ids: alertIds }),
  });
}

export function markAllAlertsRead(): Promise<{ updated: number }> {
  return request<{ updated: number }>("/api/alerts/mark-all-read", {
    method: "POST",
  });
}

export function deleteAlert(alertId: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/api/alerts/${alertId}`, {
    method: "DELETE",
  });
}

// --- Desktop tool approvals (human-in-the-loop) ---

/** Request a desktop tool execution. Creates a pending approval —
 * nothing runs until a human approves it via approveAction(). */
export function requestDesktopExecution(payload: {
  tool: string;
  parameters: Record<string, unknown>;
  title?: string;
  task_id?: string;
}): Promise<ApprovalExecuteResponse> {
  return request<ApprovalExecuteResponse>("/api/desktop/execute", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getPendingApprovals(): Promise<ApprovalsResponse> {
  return request<ApprovalsResponse>("/api/approvals?status=pending_approval");
}

/** All approvals for the tenant, newest first (Desktop tab history). */
export function getApprovals(params?: {
  status?: string;
  limit?: number;
}): Promise<ApprovalsResponse> {
  const search = new URLSearchParams();
  if (params?.status) search.set("status", params.status);
  if (params?.limit) search.set("limit", String(params.limit));
  const qs = search.toString();
  return request<ApprovalsResponse>(`/api/approvals${qs ? `?${qs}` : ""}`);
}

/** Append-only execution audit trail (sanitized server-side, read-only). */
export function getAudit(limit = 12): Promise<AuditResponse> {
  return request<AuditResponse>(`/api/audit?limit=${limit}`);
}

/** Desktop bridge connectivity. Offline bridge is data, not an error. */
export function getDesktopHealth(): Promise<DesktopHealth> {
  return request<DesktopHealth>("/api/desktop/health");
}

/** Explicit human approval — the backend claims the request exactly once
 * and dispatches it under a one-time grant. 409 = already decided. */
export function approveAction(
  approvalId: string,
): Promise<ApprovalExecuteResponse> {
  return request<ApprovalExecuteResponse>(
    `/api/approvals/${approvalId}/approve`,
    {
      method: "POST",
    },
  );
}

/** Reject a pending action. Terminal: it can never execute afterwards. */
export function rejectAction(approvalId: string): Promise<ApprovalRecord> {
  return request<ApprovalRecord>(`/api/approvals/${approvalId}/reject`, {
    method: "POST",
  });
}
