import {
  ArrowUpRight,
  BookOpenCheck,
  Brain,
  Compass,
  Database,
  Plus,
} from "lucide-react";
import { agents } from "@/data/demo-data";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { ProgressIndicator } from "@/components/ui/progress-indicator";
import { PageHeader } from "@/components/layout/page-header";

const icons = [Compass, BookOpenCheck, Brain, Database];
const tones = [
  "bg-soft-peach",
  "bg-soft-blue",
  "bg-soft-grey",
  "bg-soft-green",
];

export function AgentsView() {
  return (
    <>
      <PageHeader
        eyebrow="Intelligence network"
        title="Agents"
        description="Meet the specialists that plan, investigate, challenge, and remember for AION."
        action={
          <Button>
            <Plus className="mr-2 size-4" />
            New Agent
          </Button>
        }
      />
      <div className="grid gap-5 p-4 sm:grid-cols-2 sm:p-6 lg:p-7">
        {agents.map((agent, index) => {
          const Icon = icons[index];
          return (
            <article
              key={agent.name}
              className="rounded-[24px] border bg-white p-5 sm:p-6"
            >
              <div className="flex items-start gap-4">
                <span
                  className={`grid size-12 shrink-0 place-items-center rounded-[18px] ${tones[index]}`}
                >
                  <Icon className="size-5 text-navy" />
                </span>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-lg font-semibold tracking-[-0.02em]">
                      {agent.name}
                    </h2>
                    <StatusBadge status={agent.status} />
                  </div>
                  <p className="mt-2 text-sm leading-6 text-muted-text">
                    {agent.description}
                  </p>
                </div>
              </div>
              <div className="mt-6 grid grid-cols-2 gap-3 rounded-[18px] bg-[#f7f9fc] p-4">
                <div>
                  <p className="text-[10px] uppercase tracking-[0.12em] text-muted-text">
                    Specialty
                  </p>
                  <p className="mt-1 text-xs font-semibold">
                    {agent.specialty}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-[0.12em] text-muted-text">
                    Confidence
                  </p>
                  <p className="mt-1 text-xs font-semibold">
                    {agent.confidence}%
                  </p>
                </div>
              </div>
              <div className="mt-5">
                <ProgressIndicator
                  value={agent.confidence}
                  label="Demo confidence"
                />
              </div>
              <button
                type="button"
                className="mt-5 flex h-10 w-full items-center justify-center gap-2 rounded-full bg-navy text-xs font-medium text-white hover:bg-[#25334b]"
              >
                View agent <ArrowUpRight className="size-4" />
              </button>
            </article>
          );
        })}
      </div>
    </>
  );
}
