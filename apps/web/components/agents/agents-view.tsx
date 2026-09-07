"use client";

import { useEffect, useState } from "react";
import {
  ArrowUpRight,
  BookOpenCheck,
  Brain,
  ChevronUp,
  Compass,
  Database,
  Lock,
} from "lucide-react";
import { getAgents } from "@/services/api";
import type { AgentCardData } from "@/types";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { ProgressIndicator } from "@/components/ui/progress-indicator";
import { EmptyState } from "@/components/ui/empty-state";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import { PageHeader } from "@/components/layout/page-header";
import { Tooltip } from "@/components/ui/tooltip";

const icons = [Compass, BookOpenCheck, Brain, Database];
const tones = ["bg-soft-peach", "bg-soft-blue", "bg-soft-grey", "bg-soft-green"];

export function AgentsView() {
  const [agents, setAgents] = useState<AgentCardData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    getAgents()
      .then((response) => {
        if (mounted) {
          setAgents(response.items);
          setError(false);
        }
      })
      .catch(() => {
        if (mounted) setError(true);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [loadAttempt]);

  return (
    <>
      <PageHeader
        eyebrow="Intelligence network"
        title="Agents"
        description="Meet the specialists that plan, investigate, challenge, and remember for AION."
        action={
          <Tooltip content="Custom agent creation coming soon">
            <Button disabled>
              <Lock className="mr-2 size-3.5" />
              New Agent
            </Button>
          </Tooltip>
        }
      />
      <div className="p-4 sm:p-6 lg:p-7">
        {loading ? (
          <div aria-label="Loading agents" className="grid gap-5 sm:grid-cols-2">
            {[0, 1, 2, 3].map((item) => <LoadingSkeleton key={item} className="h-[320px]" />)}
          </div>
        ) : error ? (
          <EmptyState
            title="Unable to load data"
            description="AION could not reach the backend API. Check that the server is running, then retry."
            action={
              <Button variant="outline" size="sm" onClick={() => setLoadAttempt((attempt) => attempt + 1)}>
                Retry
              </Button>
            }
          />
        ) : (
          <div className="grid gap-5 sm:grid-cols-2">
            {agents.map((agent, index) => {
              const Icon = icons[index % icons.length];
              const isExpanded = expandedAgent === (agent.id ?? agent.name);
              return (
                <article key={agent.id ?? agent.name} className="rounded-[24px] border bg-white p-5 sm:p-6">
                  <div className="flex items-start gap-4">
                    <span className={`grid size-12 shrink-0 place-items-center rounded-[18px] ${tones[index % tones.length]}`}>
                      <Icon className="size-5 text-navy" />
                    </span>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-lg font-semibold tracking-[-0.02em]">{agent.name}</h2>
                        <StatusBadge status={agent.status} />
                      </div>
                      <p className="mt-2 text-sm leading-6 text-muted-text">{agent.description}</p>
                    </div>
                  </div>
                  <div className="mt-6 grid grid-cols-2 gap-3 rounded-[18px] bg-[#f7f9fc] p-4">
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.12em] text-muted-text">Specialty</p>
                      <p className="mt-1 text-xs font-semibold">{agent.specialty}</p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.12em] text-muted-text">Confidence</p>
                      <p className="mt-1 text-xs font-semibold">{agent.confidence}%</p>
                    </div>
                  </div>
                  <div className="mt-5">
                    <ProgressIndicator value={agent.confidence} label="Confidence" />
                  </div>

                  {isExpanded && (
                    <div className="mt-4 rounded-[18px] border border-[#e8ecf2] bg-[#fafbfd] p-4">
                      <h3 className="text-xs font-semibold uppercase tracking-[0.1em] text-muted-text">Agent Details</h3>
                      <dl className="mt-3 space-y-2.5">
                        <div className="flex items-center justify-between text-xs">
                          <dt className="text-muted-text">Agent ID</dt>
                          <dd className="font-mono font-medium text-navy">{agent.id ?? "—"}</dd>
                        </div>
                        <div className="flex items-center justify-between text-xs">
                          <dt className="text-muted-text">Status</dt>
                          <dd><StatusBadge status={agent.status} /></dd>
                        </div>
                        <div className="flex items-center justify-between text-xs">
                          <dt className="text-muted-text">Specialty</dt>
                          <dd className="font-medium">{agent.specialty}</dd>
                        </div>
                        <div className="flex items-center justify-between text-xs">
                          <dt className="text-muted-text">Confidence</dt>
                          <dd className="font-medium">{agent.confidence}%</dd>
                        </div>
                      </dl>
                      <p className="mt-3 text-[11px] leading-5 text-muted-text">
                        {agent.description}
                      </p>
                    </div>
                  )}

                  <button
                    type="button"
                    onClick={() => setExpandedAgent(isExpanded ? null : (agent.id ?? agent.name))}
                    className="mt-5 flex h-10 w-full items-center justify-center gap-2 rounded-full bg-navy text-xs font-medium text-white hover:bg-[#25334b] transition-colors"
                  >
                    {isExpanded ? (
                      <>Hide details <ChevronUp className="size-4" /></>
                    ) : (
                      <>View agent <ArrowUpRight className="size-4" /></>
                    )}
                  </button>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
