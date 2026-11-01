export type TaskStatus =
  | "completed"
  | "running"
  | "failed"
  | "pending"
  | "pending_approval";
export type AgentState = "online" | "standby" | "offline";

export interface RecentTask {
  id: string;
  title: string;
  agent: string;
  status: TaskStatus;
  confidence: number;
  created?: string;
}

export interface AgentActivity {
  name: string;
  status: AgentState;
  workload: number;
}

export interface DashboardData {
  total_tasks: number;
  active_agents: number;
  saved_memories: number;
  system_health: number;
  recent_tasks: RecentTask[];
  agent_activity: AgentActivity[];
}

export type ChatMode = "auto" | "quick" | "research" | "manual";
export type AgentId = "planner" | "researcher" | "critic" | "memory";

export interface UsedAgent {
  id: AgentId;
  name: string;
  status: "completed" | "failed";
  summary: string;
}

export interface ChatRequest {
  message: string;
  mode: ChatMode;
  selected_agents: AgentId[];
  conversation_id?: string;
  memory_enabled: boolean;
  verification_enabled: boolean;
}

export interface PendingApprovalInfo {
  approval_id: string;
  task_id: string;
  tool: string;
  status: "pending_approval";
  expires_at: string;
  requires: "human_approval";
  queue_path: string;
}

export interface ChatResponse {
  task_id: string;
  conversation_id: string;
  author: "AION";
  answer: string;
  mode: ChatMode;
  status: "completed" | "failed";
  used_agents: UsedAgent[];
  confidence: number;
  processing_time_ms: number;
  selection_summary: string;
  sources: string[];
  error: string | null;
  development_mode: boolean;
  revision_count: number;
  // Phase 2: present when the message queued a pending desktop approval.
  // Optional so reconstructed history (no live approval) stays type-safe.
  pending_approval?: PendingApprovalInfo | null;
}

export type ChatMessage =
  | { id: string; role: "user"; content: string }
  | { id: string; role: "assistant"; response: ChatResponse };

export interface AgentCardData {
  id?: string;
  name: string;
  description: string;
  status: AgentState;
  confidence: number;
  specialty: string;
}

export interface WorkflowData {
  id?: string;
  name: string;
  description: string;
  agents: string[];
  runs: number;
  state: "Ready" | "Running";
}

export interface AgentsResponse {
  items: AgentCardData[];
  total: number;
}

export interface TasksResponse {
  items: RecentTask[];
  total: number;
}

export interface WorkflowsResponse {
  items: WorkflowData[];
  total: number;
}

export interface WorkflowCreatePayload {
  name: string;
  description: string;
  agents: string[];
}

export interface WorkflowRunResult {
  task_id: string;
  status: string;
  answer: string;
  confidence: number;
  processing_time_ms: number;
  error: string | null;
}

export interface WorkflowRunResponse {
  workflow: WorkflowData;
  run: WorkflowRunResult;
}

export type MemoryType = "short_term" | "long_term" | "vector";

export interface MemoryCategory {
  id: string;
  title: string;
  description: string;
  type: MemoryType;
  count: string;
  usage: number;
}

export interface MemoryResponse {
  categories: MemoryCategory[];
  policies: string[];
}

export type ResearchNoteType =
  | "Architecture note"
  | "Experiment"
  | "Working draft";

export interface ResearchNote {
  id: string;
  title: string;
  type: ResearchNoteType;
  date: string;
}

export interface ResearchResponse {
  items: ResearchNote[];
  total: number;
}

// --- Health ---

export interface HealthComponent {
  status: "ok" | "degraded" | "error";
  detail: string;
}

export interface HealthData {
  status: "healthy" | "degraded" | "unhealthy";
  service: string;
  version: string;
  model_name: string;
  gemini: HealthComponent;
  memory: HealthComponent;
  agents: HealthComponent;
}

// --- Conversations ---

export interface ConversationSummary {
  conversation_id: string;
  title: string;
  message_count: number;
  last_message_at: string;
  created_at: string;
}

export interface StoredMessage {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  task_id: string | null;
  created_at: string;
}

// --- Memory Records ---

export interface MemoryRecordOut {
  memory_id: string;
  type: string;
  content: string;
  task_id: string;
  source_agent: string;
  verification_state: string;
  tags: string[];
  created_at: string;
}

export interface MemoryRecordsResponse {
  items: MemoryRecordOut[];
  total: number;
}

// --- Task Detail ---

export interface TaskDetail {
  id: string;
  title: string;
  agent: string;
  status: TaskStatus;
  confidence: number;
  created: string;
  output?: {
    tool_id: string;
    task_id: string;
    success: boolean;
    content?: string;
    error?: string;
    data?: Record<string, unknown>;
  };
  updated?: string;
}

// --- Settings ---

export interface AppSettings {
  workspace_name: string;
  default_view: string;
  preferred_model: string;
  theme: "light" | "system" | "dim";
  memory_enabled: boolean;
  verification_enabled: boolean;
  notify_task_completions: boolean;
  notify_system_health: boolean;
  notify_weekly_summary: boolean;
}

// --- Alerts / Notifications ---

export type AlertCategory = "task" | "agent" | "system" | "memory" | "approval";
export type AlertTone = "info" | "success" | "warning" | "error";

export interface AlertItem {
  id: string;
  title: string;
  description: string;
  time: string;
  category: AlertCategory;
  unread: boolean;
  tone: AlertTone;
}

export interface AlertsResponse {
  items: AlertItem[];
  total: number;
  unread_count: number;
}

// --- Desktop tool approvals (human-in-the-loop) ---

export type ApprovalStatus =
  | "pending_approval"
  | "approved"
  | "running"
  | "completed"
  | "failed"
  | "rejected"
  | "expired";

/** API-facing approval record. Parameters are sanitized server-side:
 * secret-like keys and file content never reach the browser. */
export interface ApprovalRecord {
  id: string;
  task_id: string;
  tool: string;
  parameters: Record<string, unknown>;
  status: ApprovalStatus;
  created_at: string;
  expires_at: string;
  approved_at?: string | null;
  approved_by_key_id?: string | null;
  claimed_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
}

export interface ApprovalsResponse {
  items: ApprovalRecord[];
  total: number;
}

/** 202 envelope from POST /api/desktop/execute and .../approve. */
export interface ApprovalExecuteResponse {
  approval_id: string;
  task_id: string;
  status: ApprovalStatus;
  expires_at: string;
  requires: string;
}

export interface AuditEvent {
  seq: number;
  ts: string;
  event: string;
  approval_id: string;
  task_id?: string | null;
  actor_key_id?: string | null;
  detail?: string | null;
}

export interface AuditResponse {
  items: AuditEvent[];
  total: number;
}
