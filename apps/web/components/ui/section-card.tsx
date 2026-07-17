import type { ReactNode } from "react";
import { cn } from "@/utils/cn";

interface SectionCardProps { title?: string; description?: string; action?: ReactNode; children: ReactNode; className?: string; }

export function SectionCard({ title, description, action, children, className }: SectionCardProps) {
  return (
    <section className={cn("rounded-[24px] border bg-white p-5 sm:p-6", className)}>
      {(title || action) && <div className="mb-5 flex items-start justify-between gap-4"><div>{title && <h2 className="text-lg font-semibold tracking-[-0.02em]">{title}</h2>}{description && <p className="mt-1 text-xs leading-5 text-muted-text">{description}</p>}</div>{action}</div>}
      {children}
    </section>
  );
}

