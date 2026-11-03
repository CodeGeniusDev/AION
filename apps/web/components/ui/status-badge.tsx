import { cn } from "@/utils/cn";
import type {
  AgentState,
  ApprovalStatus,
  ScheduleStatus,
  TaskStatus,
} from "@/types";

interface StatusBadgeProps {
  status:
    | TaskStatus
    | AgentState
    | ApprovalStatus
    | ScheduleStatus
    | "Ready"
    | "Running";
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const normalized = status.toLowerCase();
  return (
    <span
      className={cn(
        "inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold capitalize",
        ["completed", "online", "ready", "approved"].includes(normalized) &&
          "border-success-border bg-success-soft text-success-text",
        ["running", "active"].includes(normalized) &&
          "border-info-border bg-soft-blue text-info-text",
        ["standby", "pending", "pending_approval"].includes(normalized) &&
          "border-warning-border bg-warning-soft text-warning-text",
        ["failed", "offline", "rejected"].includes(normalized) &&
          "border-danger-border bg-danger-soft text-danger-text",
        ["expired", "paused", "canceled"].includes(normalized) &&
          "border-border bg-muted text-muted-text",
      )}>
      <span className="size-1.5 rounded-full bg-current" />
      {status.replace("_", " ")}
    </span>
  );
}
