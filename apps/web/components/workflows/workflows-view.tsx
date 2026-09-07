"use client";

import { useEffect, useState } from "react";
import { ArrowUpRight, Lock, Network, Route } from "lucide-react";
import { getWorkflows } from "@/services/api";
import type { WorkflowData } from "@/types";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState } from "@/components/ui/empty-state";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import { PageHeader } from "@/components/layout/page-header";
import { Tooltip } from "@/components/ui/tooltip";

export function WorkflowsView() {
  const [workflows, setWorkflows] = useState<WorkflowData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    getWorkflows()
      .then((response) => {
        if (mounted) {
          setWorkflows(response.items);
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
        eyebrow="Agent orchestration"
        title="Workflows"
        description="Reusable paths that coordinate specialists from first request to reviewed result."
        action={
          <Tooltip content="Custom workflow creation coming soon">
            <Button disabled>
              <Lock className="mr-2 size-3.5" />
              New Workflow
            </Button>
          </Tooltip>
        }
      />
      <div className="p-4 sm:p-6 lg:p-7">
        {loading ? (
          <div aria-label="Loading workflows" className="grid gap-5 lg:grid-cols-3">
            {[0, 1, 2].map((item) => <LoadingSkeleton key={item} className="h-[260px]" />)}
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
          <div className="grid gap-5 lg:grid-cols-3">
            {workflows.map((workflow, index) => (
              <article key={workflow.id ?? workflow.name} className="flex flex-col rounded-[24px] border bg-white p-5 sm:p-6">
                <div className="flex items-start justify-between">
                  <span className={`grid size-12 place-items-center rounded-[18px] ${index === 0 ? "bg-soft-blue" : index === 1 ? "bg-soft-peach" : "bg-soft-green"}`}>
                    {index === 0 ? <Network className="size-5" /> : <Route className="size-5" />}
                  </span>
                  <StatusBadge status={workflow.state} />
                </div>
                <h2 className="mt-5 text-lg font-semibold tracking-[-0.02em]">{workflow.name}</h2>
                <p className="mt-2 text-sm leading-6 text-muted-text">{workflow.description}</p>
                <div className="mt-5 flex flex-wrap gap-1.5">
                  {workflow.agents.map((agent, agentIndex) => (
                    <span key={agent} className="rounded-full border bg-[#fafbfd] px-2.5 py-1 text-[10px] font-medium">
                      {agentIndex + 1}. {agent}
                    </span>
                  ))}
                </div>
                <div className="mt-auto flex items-center border-t pt-5 text-xs text-muted-text">
                  <span>{workflow.runs} total runs</span>
                  <Tooltip content="Workflow execution coming soon">
                    <button
                      type="button"
                      disabled
                      className="ml-auto grid size-9 place-items-center rounded-full bg-[#c6ccd5] text-white cursor-not-allowed"
                      aria-label={`Open ${workflow.name} (coming soon)`}
                    >
                      <ArrowUpRight className="size-4" />
                    </button>
                  </Tooltip>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
