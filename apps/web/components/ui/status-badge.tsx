import { cn } from "@/utils/cn";
import type { AgentState, TaskStatus } from "@/types";

interface StatusBadgeProps { status: TaskStatus | AgentState | "Ready" | "Running"; }

export function StatusBadge({ status }: StatusBadgeProps) {
  const normalized = status.toLowerCase();
  return (
    <span className={cn(
      "inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold capitalize",
      ["completed", "online", "ready"].includes(normalized) && "border-[#b9decf] bg-[#e8f6ef] text-[#247a55]",
      ["running"].includes(normalized) && "border-[#bfd2fa] bg-[#edf3ff] text-[#2761c8]",
      normalized === "standby" && "border-[#e2d4ad] bg-[#fff8e6] text-[#8b6a16]",
      ["failed", "offline"].includes(normalized) && "border-[#efcaca] bg-[#fff0f0] text-[#b53d3d]",
    )}>
      <span className="size-1.5 rounded-full bg-current" />{status}
    </span>
  );
}

