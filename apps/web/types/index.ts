export type TaskStatus = "completed" | "running" | "failed";
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

export type ResearchNoteType = "Architecture note" | "Experiment" | "Working draft";

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
