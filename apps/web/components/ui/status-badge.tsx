import { cn } from "@/utils/cn";
import type { AgentState, ApprovalStatus, TaskStatus } from "@/types";

interface StatusBadgeProps { status: TaskStatus | AgentState | ApprovalStatus | "Ready" | "Running"; }

export function StatusBadge({ status }: StatusBadgeProps) {
  const normalized = status.toLowerCase();
  return (
    <span className={cn(
      "inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold capitalize",
      ["completed", "online", "ready", "approved"].includes(normalized) && "border-[#b9decf] bg-[#e8f6ef] text-[#247a55]",
      ["running"].includes(normalized) && "border-[#bfd2fa] bg-[#edf3ff] text-[#2761c8]",
      ["standby", "pending", "pending_approval"].includes(normalized) && "border-[#e2d4ad] bg-[#fff8e6] text-[#8b6a16]",
      ["failed", "offline", "rejected"].includes(normalized) && "border-[#efcaca] bg-[#fff0f0] text-[#b53d3d]",
      ["expired"].includes(normalized) && "border-[#d7dee7] bg-[#f2f4f7] text-[#666d78]",
    )}>
      <span className="size-1.5 rounded-full bg-current" />{status.replace("_", " ")}
    </span>
  );
}

