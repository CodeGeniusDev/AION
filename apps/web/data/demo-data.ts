import type {
  AgentCardData,
  DashboardData,
  RecentTask,
  WorkflowData,
  ChatResponse,
} from "@/types";

export const dashboardFallback: DashboardData = {
  total_tasks: 128,
  active_agents: 4,
  saved_memories: 24,
  system_health: 98,
  recent_tasks: [
    {
      id: "task-001",
      title: "Summarize product research",
      agent: "Research Agent",
      status: "completed",
      confidence: 94,
      created: "12 min ago",
    },
    {
      id: "task-002",
      title: "Plan the next development sprint",
      agent: "Planner Agent",
      status: "running",
      confidence: 89,
      created: "28 min ago",
    },
    {
      id: "task-003",
      title: "Review system assumptions",
      agent: "Critic Agent",
      status: "completed",
      confidence: 91,
      created: "1 hr ago",
    },
    {
      id: "task-004",
      title: "Index architecture notes",
      agent: "Memory Agent",
      status: "failed",
      confidence: 76,
      created: "2 hrs ago",
    },
  ],
  agent_activity: [
    { name: "Planner Agent", status: "online", workload: 72 },
    { name: "Research Agent", status: "online", workload: 58 },
    { name: "Critic Agent", status: "standby", workload: 24 },
    { name: "Memory Agent", status: "online", workload: 41 },
  ],
};

export const taskRows: RecentTask[] = [
  ...dashboardFallback.recent_tasks,
  {
    id: "task-005",
    title: "Map launch dependencies",
    agent: "Planner Agent",
    status: "running",
    confidence: 87,
    created: "Yesterday",
  },
  {
    id: "task-006",
    title: "Compare retrieval strategies",
    agent: "Research Agent",
    status: "completed",
    confidence: 96,
    created: "Yesterday",
  },
];

export const agents: AgentCardData[] = [
  {
    name: "Planner Agent",
    description:
      "Turns broad goals into clear steps, dependencies, and execution plans.",
    status: "online",
    confidence: 94,
    specialty: "Strategy",
  },
  {
    name: "Research Agent",
    description:
      "Finds, organizes, and synthesizes information for active tasks.",
    status: "online",
    confidence: 96,
    specialty: "Discovery",
  },
  {
    name: "Critic Agent",
    description:
      "Challenges assumptions and reviews outputs before they move forward.",
    status: "standby",
    confidence: 91,
    specialty: "Quality",
  },
  {
    name: "Memory Agent",
    description:
      "Maintains useful context and connects knowledge across the system.",
    status: "online",
    confidence: 89,
    specialty: "Context",
  },
];

export const workflows: WorkflowData[] = [
  {
    name: "Deep Research",
    description:
      "Investigate a question, challenge the findings, and save the useful context.",
    agents: ["Planner", "Research", "Critic", "Memory"],
    runs: 42,
    state: "Running",
  },
  {
    name: "Decision Brief",
    description:
      "Turn complex inputs into a focused recommendation with reviewed evidence.",
    agents: ["Research", "Critic", "Planner"],
    runs: 18,
    state: "Ready",
  },
  {
    name: "Knowledge Capture",
    description:
      "Structure new information and route it into the appropriate memory layer.",
    agents: ["Memory", "Critic"],
    runs: 76,
    state: "Ready",
  },
];

export const chatHistory = [
  {
    id: "chat-1",
    title: "Product research plan",
    preview: "Create a structured research approach...",
    time: "12m",
  },
  {
    id: "chat-2",
    title: "Architecture review",
    preview: "Compare the current service boundaries...",
    time: "1h",
  },
  {
    id: "chat-3",
    title: "Weekly synthesis",
    preview: "Summarize this week’s saved context...",
    time: "Mon",
  },
];

export const starterAionResponse: ChatResponse = {
  task_id: "task-demo",
  conversation_id: "chat-1",
  author: "AION",
  answer: "I’ve organized the milestone into discovery, validation, and delivery tracks, then checked the sequence for gaps. The next step is to define the target user outcome before beginning research.",
  mode: "auto",
  status: "completed",
  used_agents: [
    { id: "planner", name: "Planner Agent", status: "completed", summary: "Created a concise task plan" },
    { id: "critic", name: "Critic Agent", status: "completed", summary: "Checked the response for gaps and contradictions" },
  ],
  confidence: 0.9,
  processing_time_ms: 1840,
  selection_summary: "Planning and review agents were selected for this structured milestone request.",
  sources: [],
  error: null,
  development_mode: true,
  revision_count: 0,
};
