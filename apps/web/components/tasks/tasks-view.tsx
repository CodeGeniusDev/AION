"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Plus, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { getTask, getTasks } from "@/services/api";
import type { RecentTask, TaskDetail, TaskStatus } from "@/types";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import { PageHeader } from "@/components/layout/page-header";
import { RecentTaskRow } from "@/components/dashboard/recent-task-row";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/utils/cn";

type Filter = "all" | TaskStatus;

export function TasksView() {
  const router = useRouter();
  const [allTasks, setAllTasks] = useState<RecentTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");

  // Task detail state
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [taskDetail, setTaskDetail] = useState<TaskDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(false);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    getTasks()
      .then((response) => {
        if (mounted) {
          setAllTasks(response.items);
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

  // Fetch task detail when a task is selected
  useEffect(() => {
    if (!selectedTaskId) {
      setTaskDetail(null);
      return;
    }
    let mounted = true;
    setDetailLoading(true);
    setDetailError(false);
    getTask(selectedTaskId)
      .then((detail) => {
        if (mounted) setTaskDetail(detail);
      })
      .catch(() => {
        if (mounted) setDetailError(true);
      })
      .finally(() => {
        if (mounted) setDetailLoading(false);
      });
    return () => { mounted = false; };
  }, [selectedTaskId]);

  const tasks = useMemo(
    () =>
      allTasks.filter(
        (task) =>
          (filter === "all" || task.status === filter) &&
          task.title.toLowerCase().includes(query.toLowerCase())
      ),
    [allTasks, filter, query]
  );

  return (
    <>
      <PageHeader
        eyebrow="Execution queue"
        title="Tasks"
        description="Track every request moving through the AION agent network."
        action={
          <Button onClick={() => router.push("/chat")}>
            <Plus className="mr-2 size-4" />
            New Task
          </Button>
        }
      />
      <div className="p-4 sm:p-6 lg:p-7">
        {selectedTaskId ? (
          /* ── Task Detail View ── */
          <section className="rounded-[24px] border bg-white p-5 sm:p-6">
            <button
              type="button"
              onClick={() => setSelectedTaskId(null)}
              className="mb-5 flex items-center gap-2 text-xs font-medium text-muted-text hover:text-aion-text"
            >
              <ArrowLeft className="size-3.5" /> Back to all tasks
            </button>
            {detailLoading ? (
              <div aria-label="Loading task detail" className="space-y-4">
                <LoadingSkeleton className="h-8 w-64" />
                <LoadingSkeleton className="h-4 w-40" />
                <LoadingSkeleton className="h-32" />
              </div>
            ) : detailError || !taskDetail ? (
              <EmptyState
                title="Task not found"
                description="This task may have been removed or is not available."
                action={
                  <Button variant="outline" size="sm" onClick={() => setSelectedTaskId(null)}>
                    Go back
                  </Button>
                }
              />
            ) : (
              <div className="space-y-6">
                <div>
                  <div className="flex flex-wrap items-center gap-3">
                    <h2 className="text-lg font-semibold">{taskDetail.title}</h2>
                    <StatusBadge status={taskDetail.status} />
                  </div>
                  <p className="mt-1 text-xs text-muted-text">
                    Task ID: {taskDetail.id}
                  </p>
                </div>

                <div className="grid gap-4 sm:grid-cols-3">
                  <div className="rounded-[16px] bg-[#f4f7fb] p-4">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-text">Assigned Agent</p>
                    <p className="mt-1 text-sm font-semibold">{taskDetail.agent}</p>
                  </div>
                  <div className="rounded-[16px] bg-[#f4f7fb] p-4">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-text">Confidence</p>
                    <p className="mt-1 text-sm font-semibold">{taskDetail.confidence}%</p>
                  </div>
                  <div className="rounded-[16px] bg-[#f4f7fb] p-4">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-text">Created</p>
                    <p className="mt-1 text-sm font-semibold">{taskDetail.created ? new Date(taskDetail.created).toLocaleString() : "Unknown"}</p>
                  </div>
                </div>

                <div className="rounded-[16px] border p-4">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-text">Status Detail</p>
                  <p className="mt-2 text-xs leading-6 text-muted-text">
                    This task was recorded as an episodic memory entry in AION&apos;s cognitive store.
                    {taskDetail.status === "completed"
                      ? " The agent pipeline ran successfully and produced a verified response."
                      : taskDetail.status === "failed"
                        ? " One or more agents in the pipeline failed to complete their assigned step."
                        : " The task is currently being processed by the agent pipeline."}
                  </p>
                </div>
              </div>
            )}
          </section>
        ) : (
          /* ── Task List View ── */
          <section className="rounded-[24px] border bg-white p-5 sm:p-6">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div className="flex flex-wrap gap-1 rounded-full bg-[#f2f4f7] p-1">
                {(["all", "completed", "running", "failed"] as Filter[]).map((item) => (
                  <button type="button" key={item} onClick={() => setFilter(item)} className={cn("rounded-full px-4 py-2 text-[11px] font-medium capitalize", filter === item ? "bg-white shadow-sm" : "text-muted-text")}>
                    {item}
                  </button>
                ))}
              </div>
              <label className="relative">
                <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-text" />
                <span className="sr-only">Search tasks</span>
                <input value={query} onChange={(event) => setQuery(event.target.value)} className="h-10 w-full rounded-full border pl-9 pr-4 text-xs md:w-64" placeholder="Search tasks" />
              </label>
            </div>
            {loading ? (
              <div aria-label="Loading tasks" className="mt-5 space-y-3">
                {[0, 1, 2].map((item) => <LoadingSkeleton key={item} className="h-14" />)}
              </div>
            ) : error ? (
              <div className="mt-5">
                <EmptyState
                  title="Unable to load data"
                  description="AION could not reach the backend API. Check that the server is running, then retry."
                  action={
                    <Button variant="outline" size="sm" onClick={() => setLoadAttempt((attempt) => attempt + 1)}>
                      Retry
                    </Button>
                  }
                />
              </div>
            ) : (
              <div className="mt-5 divide-y">
                {tasks.length
                  ? tasks.map((task, index) => (
                      <RecentTaskRow key={task.id} task={task} index={index} onSelect={setSelectedTaskId} />
                    ))
                  : <EmptyState title="No tasks found" description="Try a different search or status filter." />}
              </div>
            )}
          </section>
        )}
      </div>
    </>
  );
}
