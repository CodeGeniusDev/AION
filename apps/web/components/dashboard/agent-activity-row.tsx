import type { AgentActivity } from "@/types";
import { ProgressIndicator } from "@/components/ui/progress-indicator";
import { cn } from "@/utils/cn";

export function AgentActivityRow({ agent }: { agent: AgentActivity }) {
  return (
    <div className="py-3.5">
      <div className="mb-2.5 flex items-center gap-2 text-xs"><span className={cn("size-2 rounded-full", agent.status === "online" ? "bg-[#35b978]" : agent.status === "standby" ? "bg-[#e2ad3e]" : "bg-[#d65a5a]")} /><span className="font-medium">{agent.name}</span><span className="ml-auto text-[10px] capitalize text-muted-text">{agent.status}</span></div>
      <ProgressIndicator value={agent.workload} />
      <div className="mt-1.5 text-right text-[10px] text-muted-text">{agent.workload}% workload</div>
    </div>
  );
}

