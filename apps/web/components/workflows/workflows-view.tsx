"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowUpRight, Loader2, Network, Plus, Route, X } from "lucide-react";
import { createWorkflow, getWorkflows, runWorkflow } from "@/services/api";
import type { WorkflowData, WorkflowRunResult } from "@/types";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState } from "@/components/ui/empty-state";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import { PageHeader } from "@/components/layout/page-header";
import { usePageSearch } from "@/components/layout/page-search-provider";
import { Tooltip } from "@/components/ui/tooltip";

// Only the model-safe agents the backend workflow whitelist accepts. A
// workflow can never list a desktop/bridge tool — the API rejects those.
const SAFE_AGENTS = ["Planner", "Research", "Critic", "Memory"];

function WorkflowForm({
  onCreated,
  onCancel,
}: {
  onCreated: () => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [agents, setAgents] = useState<string[]>(["Planner"]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleAgent = (agent: string) =>
    setAgents((prev) => (prev.includes(agent) ? prev.filter((a) => a !== agent) : [...prev, agent]));

  const submit = async () => {
    if (!name.trim() || agents.length === 0) {
      setError("Provide a name and at least one agent.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await createWorkflow({ name: name.trim(), description: description.trim(), agents });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create workflow.");
      setSubmitting(false);
    }
  };

  return (
    <div className="rounded-[24px] border bg-surface p-5 sm:p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">New workflow</h2>
        <button type="button" onClick={onCancel} aria-label="Cancel" className="grid size-8 place-items-center rounded-full text-muted-text hover:bg-muted">
          <X className="size-4" />
        </button>
      </div>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <label className="block text-xs font-medium">
          Name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Weekly report"
            className="mt-2 h-11 w-full rounded-full border px-4 text-sm"
          />
        </label>
        <label className="block text-xs font-medium">
          Description
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What this path does"
            className="mt-2 h-11 w-full rounded-full border px-4 text-sm"
          />
        </label>
      </div>
      <div className="mt-4">
        <span className="text-xs font-medium">Agents (model-safe only)</span>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {SAFE_AGENTS.map((agent) => {
            const active = agents.includes(agent);
            return (
              <button
                key={agent}
                type="button"
                onClick={() => toggleAgent(agent)}
                aria-pressed={active}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                  active ? "border-primary bg-primary text-white" : "bg-muted text-muted-text hover:bg-muted"
                }`}
              >
                {agent}
              </button>
            );
          })}
        </div>
      </div>
      {error ? <p className="mt-3 text-xs text-red-600">{error}</p> : null}
      <div className="mt-5 flex items-center gap-2">
        <Button size="sm" onClick={submit} disabled={submitting}>
          {submitting ? <Loader2 className="mr-2 size-3.5 animate-spin" /> : null}
          {submitting ? "Creating..." : "Create workflow"}
        </Button>
        <Button size="sm" variant="outline" onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

function RunPanel({ result }: { result: WorkflowRunResult }) {
  const tone = result.status === "completed" ? "text-success-text" : "text-red-600";
  return (
    <div className="mt-4 rounded-[18px] bg-muted p-4 text-xs leading-5">
      <div className="flex items-center justify-between">
        <span className={`font-semibold ${tone}`}>{result.status}</span>
        <span className="text-muted-text">
          {result.confidence ? `${Math.round(result.confidence * 100)}% confidence · ` : ""}
          {result.processing_time_ms} ms
        </span>
      </div>
      <p className="mt-2 whitespace-pre-wrap text-muted-text">{result.error || result.answer}</p>
    </div>
  );
}

export function WorkflowsView() {
  const searchParams = useSearchParams();
  const { matches } = usePageSearch();
  const [workflows, setWorkflows] = useState<WorkflowData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [creating, setCreating] = useState(false);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [runInput, setRunInput] = useState("");
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<Record<string, WorkflowRunResult>>({});
  const [runError, setRunError] = useState<string | null>(null);

  const visibleWorkflows = useMemo(
    () => workflows.filter((w) => matches(w.name, w.description ?? "")),
    [workflows, matches],
  );

  // Deep links from global search: /workflows?open=ID opens that workflow's
  // run panel; /workflows?new=1 (quick action) opens the real create form.
  useEffect(() => {
    if (searchParams.get("new") === "1") setCreating(true);
    const open = searchParams.get("open");
    if (open) {
      setRunningId(open);
      setRunInput("");
      setRunError(null);
    }
  }, [searchParams]);

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

  const refresh = useCallback(() => {
    setCreating(false);
    setLoadAttempt((attempt) => attempt + 1);
  }, []);

  const startRun = (id: string) => {
    setRunningId(id);
    setRunInput("");
    setRunError(null);
  };

  const submitRun = async (id: string) => {
    if (!runInput.trim()) {
      setRunError("Enter a prompt to run this workflow.");
      return;
    }
    setRunError(null);
    setRunning(true);
    try {
      const response = await runWorkflow(id, runInput.trim());
      setWorkflows((prev) => prev.map((w) => (w.id === id ? response.workflow : w)));
      setResults((prev) => ({ ...prev, [id]: response.run }));
    } catch (err) {
      setRunError(err instanceof Error ? err.message : "Workflow run failed.");
    } finally {
      setRunning(false);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Agent orchestration"
        title="Workflows"
        description="Reusable paths that coordinate specialists from first request to reviewed result."
        action={
          <Button onClick={() => setCreating((v) => !v)} disabled={creating ? false : loading || error}>
            {creating ? <X className="mr-2 size-3.5" /> : <Plus className="mr-2 size-3.5" />}
            {creating ? "Close" : "New Workflow"}
          </Button>
        }
      />
      <div className="p-4 sm:p-6 lg:p-7">
        {creating ? (
          <div className="mb-5">
            <WorkflowForm onCreated={refresh} onCancel={() => setCreating(false)} />
          </div>
        ) : null}

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
        ) : workflows.length === 0 ? (
          <EmptyState
            title="No workflows yet"
            description="Create your first reusable agent path to see it here."
            action={<Button size="sm" onClick={() => setCreating(true)}>New Workflow</Button>}
          />
        ) : visibleWorkflows.length === 0 ? (
          <EmptyState
            title="No workflows match the search"
            description="Nothing on this page matches the current filter. Clear the search to see all workflows again."
          />
        ) : (
          <div className="grid gap-5 lg:grid-cols-3">
            {visibleWorkflows.map((workflow, index) => {
              const result = workflow.id ? results[workflow.id] : undefined;
              const isOpen = runningId === workflow.id;
              return (
                <article key={workflow.id ?? workflow.name} className="flex flex-col rounded-[24px] border bg-surface p-5 sm:p-6">
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
                      <span key={agent} className="rounded-full border bg-muted px-2.5 py-1 text-[10px] font-medium">
                        {agentIndex + 1}. {agent}
                      </span>
                    ))}
                  </div>

                  {isOpen ? (
                    <div className="mt-4">
                      <textarea
                        value={runInput}
                        onChange={(e) => setRunInput(e.target.value)}
                        rows={2}
                        placeholder="Describe the task for this run..."
                        className="w-full rounded-[16px] border px-3 py-2 text-sm"
                      />
                      {runError ? <p className="mt-2 text-xs text-red-600">{runError}</p> : null}
                      <div className="mt-2 flex items-center gap-2">
                        <Button size="sm" onClick={() => submitRun(workflow.id!)} disabled={running}>
                          {running ? <Loader2 className="mr-2 size-3.5 animate-spin" /> : null}
                          Run
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => setRunningId(null)}>
                          Close
                        </Button>
                      </div>
                    </div>
                  ) : null}

                  {result ? <RunPanel result={result} /> : null}

                  <div className="mt-auto flex items-center border-t pt-5 text-xs text-muted-text">
                    <span>{workflow.runs} total runs</span>
                    <Tooltip content={workflow.id ? "Run this workflow" : "Unavailable"}>
                      <button
                        type="button"
                        onClick={() => (workflow.id ? startRun(workflow.id) : undefined)}
                        disabled={!workflow.id}
                        className="ml-auto grid size-9 place-items-center rounded-full bg-primary text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:bg-muted"
                        aria-label={`Run ${workflow.name}`}
                      >
                        <ArrowUpRight className="size-4" />
                      </button>
                    </Tooltip>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
