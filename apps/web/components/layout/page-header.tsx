import type { ReactNode } from "react";

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  description: string;
  action?: ReactNode;
}

export function PageHeader({ eyebrow = "AION Workspace", title, description, action }: PageHeaderProps) {
  return (
    <header className="flex flex-col gap-5 border-b px-5 py-6 sm:px-7 sm:py-7 lg:flex-row lg:items-end lg:justify-between lg:px-8">
      <div>
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-primary">{eyebrow}</p>
        <h1 className="text-[32px] font-semibold leading-[1.08] tracking-[-0.04em] text-aion-text sm:text-[38px]">{title}</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-text sm:text-[15px]">{description}</p>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </header>
  );
}

