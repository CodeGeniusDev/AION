import type { AgentId, ChatMode } from "@/types";

const modeDescriptions: Record<ChatMode, string> = {
  auto: "Automatically chooses the best agents",
  quick: "Direct response for simple requests",
  research: "Planner, Researcher, and Critic workflow",
  manual: "Choose one or more agents yourself",
};

const modes: Array<{ value: ChatMode; label: string }> = [
  { value: "auto", label: "AION Auto" },
  { value: "quick", label: "Quick Answer" },
  { value: "research", label: "Research Team" },
  { value: "manual", label: "Manual Agents" },
];

const agents: Array<{ id: AgentId; name: string }> = [
  { id: "planner", name: "Planner Agent" },
  { id: "researcher", name: "Research Agent" },
  { id: "critic", name: "Critic Agent" },
  { id: "memory", name: "Memory Agent" },
];

interface ModeSelectorProps {
  mode: ChatMode;
  selectedAgents: AgentId[];
  disabled: boolean;
  onModeChange: (mode: ChatMode) => void;
  onAgentsChange: (agents: AgentId[]) => void;
}

export function ModeSelector({ mode, selectedAgents, disabled, onModeChange, onAgentsChange }: ModeSelectorProps) {
  function toggleAgent(agent: AgentId) {
    onAgentsChange(selectedAgents.includes(agent) ? selectedAgents.filter((item) => item !== agent) : [...selectedAgents, agent]);
  }

  return (
    <div className="relative ml-auto min-w-[168px]">
      <label>
        <span className="sr-only">Select AION mode</span>
        <select value={mode} disabled={disabled} onChange={(event) => onModeChange(event.target.value as ChatMode)} className="h-9 w-full rounded-full border bg-white px-3 text-[11px] font-semibold disabled:opacity-60">
          {modes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select>
      </label>
      <p className="mt-1 text-right text-[9px] text-muted-text">{modeDescriptions[mode]}</p>
      {mode === "manual" && (
        <fieldset className="absolute right-0 top-[52px] z-20 w-64 rounded-[20px] border bg-white p-4 shadow-[0_14px_35px_rgba(25,36,56,0.14)]">
          <legend className="px-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-text">Select agents</legend>
          <div className="mt-2 space-y-1">
            {agents.map((agent) => <label key={agent.id} className="flex cursor-pointer items-center gap-3 rounded-xl px-2 py-2 text-xs hover:bg-[#f5f7fa]"><input type="checkbox" checked={selectedAgents.includes(agent.id)} onChange={() => toggleAgent(agent.id)} className="size-4 rounded accent-primary" />{agent.name}</label>)}
          </div>
          {!selectedAgents.length && <p className="mt-2 text-[10px] text-[#b14a4a]">Select at least one agent to send.</p>}
        </fieldset>
      )}
    </div>
  );
}

