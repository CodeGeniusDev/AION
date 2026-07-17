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
  name: string;
  description: string;
  status: AgentState;
  confidence: number;
  specialty: string;
}

export interface WorkflowData {
  name: string;
  description: string;
  agents: string[];
  runs: number;
  state: "Ready" | "Running";
}
