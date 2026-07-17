import { ArrowUpRight } from "lucide-react";
import { cn } from "@/utils/cn";

interface SummaryCardProps {
  title: string;
  description: string;
  value: number;
  tone: "peach" | "blue" | "grey";
}

export function SummaryCard({ title, description, value, tone }: SummaryCardProps) {
  return (
    <article className={cn(
      "relative flex min-h-[190px] flex-col overflow-hidden rounded-[24px] border border-black/[0.035] p-5 sm:p-6",
      tone === "peach" && "bg-soft-peach",
      tone === "blue" && "bg-soft-blue",
      tone === "grey" && "bg-soft-grey",
    )}>
      <h2 className="text-[17px] font-semibold tracking-[-0.02em]">{title}</h2>
      <p className="mt-1 max-w-[180px] text-xs leading-5 text-[#5f6269]">{description}</p>
      <div className="mt-auto flex items-end justify-between pt-6">
        <p className="text-[46px] font-semibold leading-none tracking-[-0.055em]">{value}</p>
        <a href="#recent-tasks" className="grid size-11 place-items-center rounded-full bg-navy text-white transition-transform hover:-translate-y-0.5" aria-label={`View ${title.toLowerCase()}`}>
          <ArrowUpRight className="size-[18px]" />
        </a>
      </div>
    </article>
  );
}

