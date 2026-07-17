import type { LucideIcon } from "lucide-react";
import { Inbox } from "lucide-react";

interface EmptyStateProps { title: string; description: string; icon?: LucideIcon; action?: React.ReactNode; }

export function EmptyState({ title, description, icon: Icon = Inbox, action }: EmptyStateProps) {
  return (
    <div className="flex min-h-[240px] flex-col items-center justify-center rounded-[22px] border border-dashed bg-[#fafbfd] p-8 text-center">
      <span className="grid size-12 place-items-center rounded-full bg-[#eef3fb] text-primary"><Icon className="size-5" /></span>
      <h3 className="mt-4 text-base font-semibold">{title}</h3>
      <p className="mt-1 max-w-sm text-sm leading-6 text-muted-text">{description}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

