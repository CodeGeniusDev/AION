"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Plus } from "lucide-react";
import { dashboardFallback } from "@/data/demo-data";
import { getDashboard } from "@/services/api";
import type { DashboardData, TaskStatus } from "@/types";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import { PageHeader } from "@/components/layout/page-header";
import { SummaryCard } from "./summary-card";
import { AionStatusBanner } from "./aion-status-banner";
import { SystemHealthCard } from "./system-health-card";
import { RecentTaskRow } from "./recent-task-row";
import { AgentActivityRow } from "./agent-activity-row";
import { cn } from "@/utils/cn";

type Filter = "all" | TaskStatus;

export function DashboardView() {
  const [data, setData] = useState<DashboardData>(dashboardFallback);
  const [loading, setLoading] = useState(true);
  const [usingFallback, setUsingFallback] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");

  useEffect(() => {
    let mounted = true;
    getDashboard()
      .then((response) => { if (mounted) { setData({ ...response, recent_tasks: response.recent_tasks.map((task, index) => ({ ...task, created: dashboardFallback.recent_tasks[index]?.created ?? "Recently" })) }); setUsingFallback(false); } })
      .catch(() => { if (mounted) { setData(dashboardFallback); setUsingFallback(true); } })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, []);

  const visibleTasks = useMemo(() => filter === "all" ? data.recent_tasks : data.recent_tasks.filter((task) => task.status === filter), [data.recent_tasks, filter]);

  return (
    <>
      <PageHeader
        eyebrow="Command center"
        title="Hello, Abdullah"
        description="Manage your Artificial Intelligence Operating Nervous System."
        action={<Button><Plus className="mr-2 size-4" />New Task</Button>}
      />
      <div className="p-4 sm:p-6 lg:p-7">
        {usingFallback && <div role="status" className="mb-5 flex items-center gap-2 rounded-full border border-[#ead7af] bg-[#fff9eb] px-4 py-2 text-xs text-[#7d621e]"><AlertCircle className="size-4" />Live API unavailable — showing a safe demo snapshot.</div>}
        {loading ? (
          <div aria-label="Loading dashboard" className="grid gap-5 lg:grid-cols-[minmax(0,1.9fr)_minmax(280px,1fr)]">
            <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">{[0, 1, 2].map((item) => <LoadingSkeleton key={item} className="h-[190px]" />)}</div>
            <LoadingSkeleton className="h-[360px] lg:row-span-2" />
            <LoadingSkeleton className="h-[360px]" />
          </div>
        ) : (
          <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,1.9fr)_minmax(280px,1fr)]">
            <div className="min-w-0 space-y-5">
              <div className="grid min-w-0 gap-5 sm:grid-cols-2 xl:grid-cols-3">
                <SummaryCard title="Total Tasks" description="Tasks coordinated across your workspace" value={data.total_tasks} tone="peach" />
                <SummaryCard title="Active Agents" description="Specialists ready to collaborate" value={data.active_agents} tone="blue" />
                <SummaryCard title="Saved Memories" description="Useful context retained by AION" value={data.saved_memories} tone="grey" />
              </div>
              <section id="recent-tasks" className="min-w-0 rounded-[24px] border bg-white p-5 sm:p-6">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div><h2 className="text-lg font-semibold tracking-[-0.02em]">Recent Tasks</h2><p className="mt-1 text-xs text-muted-text">View recent AI tasks and results</p></div><div className="flex flex-wrap gap-1 rounded-full bg-[#f2f4f7] p-1">{(["all", "completed", "running", "failed"] as Filter[]).map((item) => <button key={item} type="button" onClick={() => setFilter(item)} className={cn("rounded-full px-3 py-1.5 text-[10px] font-medium capitalize", filter === item ? "bg-white text-aion-text shadow-sm" : "text-muted-text hover:text-aion-text")}>{item}</button>)}</div></div>
                <div className="mt-4 divide-y">{visibleTasks.length ? visibleTasks.map((task, index) => <RecentTaskRow key={task.id} task={task} index={index} />) : <EmptyState title="No matching tasks" description="Tasks with this status will appear here." />}</div>
              </section>
            </div>
            <div className="min-w-0 space-y-5">
              <SystemHealthCard value={data.system_health} />
              <AionStatusBanner />
              <section className="rounded-[24px] border bg-white p-5"><h2 className="text-lg font-semibold tracking-[-0.02em]">Agent Activity</h2><p className="mt-1 text-xs text-muted-text">Current agent workload</p><div className="mt-3 divide-y">{data.agent_activity.map((agent) => <AgentActivityRow key={agent.name} agent={agent} />)}</div></section>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
