import { ArrowUpRight, FileSearch, ListChecks, Network, Sparkles } from "lucide-react";
import type { RecentTask } from "@/types";
import { StatusBadge } from "@/components/ui/status-badge";

const icons = [FileSearch, ListChecks, Network, Sparkles];

export function RecentTaskRow({ task, index, onSelect }: { task: RecentTask; index: number; onSelect?: (taskId: string) => void }) {
  const Icon = icons[index % icons.length];
  return (
    <article className="grid cursor-pointer gap-4 py-4 sm:grid-cols-[minmax(220px,1.4fr)_minmax(120px,.8fr)_90px_88px_38px] sm:items-center" onClick={() => onSelect?.(task.id)}>
      <div className="flex min-w-0 items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-[#f0f4fa] text-navy"><Icon className="size-4" /></span>
        <div className="min-w-0"><h3 className="truncate text-[13px] font-semibold">{task.title}</h3><p className="mt-0.5 text-[10px] text-muted-text">{task.created ?? "Recently"}</p></div>
      </div>
      <div className="flex items-center justify-between sm:block"><span className="text-[10px] text-muted-text sm:hidden">Assigned agent</span><span className="text-xs">{task.agent}</span></div>
      <div className="flex items-center justify-between sm:block"><span className="text-[10px] text-muted-text sm:hidden">Confidence</span><span className="text-xs font-semibold">{task.confidence}%</span></div>
      <StatusBadge status={task.status} />
      <button type="button" onClick={(e) => { e.stopPropagation(); onSelect?.(task.id); }} className="grid size-9 place-items-center rounded-full border bg-white text-navy hover:bg-[#f7f9fc]" aria-label={`Open ${task.title}`}><ArrowUpRight className="size-4" /></button>
    </article>
  );
}
