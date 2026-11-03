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
  // Phase 2 enhanced telemetry
  task_counts: TaskCounts;
  agent_stats: AgentStats;
  memory_stats: MemoryStats;
  system_health_detail: SystemHealthDetail | null;
}

export interface TaskCounts {
  total: number;
  completed: number;
  running: number;
  pending: number;
  failed: number;
}

export interface AgentStats {
  total_registered: number;
  executing: number;
  idle: number;
  standby: number;
  offline: number;
}

export interface MemoryStats {
  total_records: number;
  episodic_count: number;
  semantic_count: number;
  procedural_count: number;
  status: string;
  provider: string;
}

export interface SystemHealthDetail {
  score: number;
  status: "healthy" | "degraded" | "unhealthy";
  uptime_seconds: number;
  calculation: string;
  components: HealthComponent[];
}

export type ChatMode = "auto" | "quick" | "research" | "manual";

// --- Profile (Phase 1D, GET/PUT /api/profile) ---

export type AvatarColor =
  | "navy"
  | "blue"
  | "teal"
  | "violet"
  | "amber"
  | "rose";

export interface Profile {
  display_name: string;
  username: string;
  email: string;
  role: string;
  timezone: string;
  bio: string;
  avatar_color: AvatarColor;
}

export interface ProfileResponse {
  configured: boolean;
  profile: Profile | null;
  created_at: string | null;
  updated_at: string | null;
}
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
  theme: "light" | "dark" | "system" | "dim";
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
  // Additive Phase 1C fields from GET /api/alerts.
  created_at?: string;
  link?: string | null;
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

/** GET /api/desktop/health — bridge connectivity, never credentials. */
export interface DesktopHealth {
  reachable: boolean;
  status: string | null;
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

// --- Scheduled desktop actions (scheduler integration) ---

/** A schedule is a promise to *ask*, not a promise to do: when it fires it
 * creates a pending approval that only a human decision can execute. */
export type ScheduleStatus = "active" | "paused" | "completed" | "canceled";

export interface Schedule {
  id: string;
  name: string;
  tool: string;
  parameters: Record<string, unknown>;
  interval_seconds: number; // 0 = one-shot
  status: ScheduleStatus;
  next_run_at: string | null; // ISO-8601 UTC; null once finalized
  last_run_at: string | null;
  last_approval_id: string | null;
  last_error: string | null;
  fire_count: number;
  created_at: string;
  updated_at: string;
}

export interface SchedulesResponse {
  items: Schedule[];
}

export interface ScheduleCreateRequest {
  name: string;
  tool: string;
  parameters?: Record<string, unknown>;
  interval_seconds?: number;
  delay_seconds?: number;
}

// --- Voice bridge (optional backends, graceful degradation) ---

export interface VoiceBackendStatus {
  available: boolean;
  backend: string;
  install_hint: string | null;
}

export interface VoiceStatus {
  stt: VoiceBackendStatus;
  tts: VoiceBackendStatus;
}

/** POST /api/voice/say — audio for browser playback, or an honest
 * "not installed" state. Never an execution, never a crash shape. */
export interface VoiceSayResponse {
  available: boolean;
  audio_base64: string | null;
  mime: string | null;
  reason: string | null;
  install_hint: string | null;
}

// --- Global search (Phase 1E) ---

/** Mirrors apps/api/models/search.py — a pointer into an existing store. */
export type GlobalSearchResultType =
  | "task"
  | "approval"
  | "agent"
  | "workflow"
  | "memory"
  | "conversation"
  | "alert"
  | "schedule";

export interface GlobalSearchResult {
  type: GlobalSearchResultType;
  id: string;
  title: string;
  subtitle: string;
  href: string;
  snippet: string;
  score: number;
}

export interface GlobalSearchResponse {
  query: string;
  total: number;
  /** Grouped by source (tasks, approvals, …). Only non-empty groups. */
  groups: Record<string, GlobalSearchResult[]>;
}
