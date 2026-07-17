"use client";

import { useMemo, useState } from "react";
import { Plus, Search } from "lucide-react";
import { taskRows } from "@/data/demo-data";
import type { TaskStatus } from "@/types";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/layout/page-header";
import { RecentTaskRow } from "@/components/dashboard/recent-task-row";
import { cn } from "@/utils/cn";

type Filter = "all" | TaskStatus;

export function TasksView() {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const tasks = useMemo(() => taskRows.filter((task) => (filter === "all" || task.status === filter) && task.title.toLowerCase().includes(query.toLowerCase())), [filter, query]);
  return <><PageHeader eyebrow="Execution queue" title="Tasks" description="Track every request moving through the AION agent network." action={<Button><Plus className="mr-2 size-4" />New Task</Button>} /><div className="p-4 sm:p-6 lg:p-7"><section className="rounded-[24px] border bg-white p-5 sm:p-6"><div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between"><div className="flex flex-wrap gap-1 rounded-full bg-[#f2f4f7] p-1">{(["all", "completed", "running", "failed"] as Filter[]).map((item) => <button type="button" key={item} onClick={() => setFilter(item)} className={cn("rounded-full px-4 py-2 text-[11px] font-medium capitalize", filter === item ? "bg-white shadow-sm" : "text-muted-text")}>{item}</button>)}</div><label className="relative"><Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-text" /><span className="sr-only">Search tasks</span><input value={query} onChange={(event) => setQuery(event.target.value)} className="h-10 w-full rounded-full border pl-9 pr-4 text-xs md:w-64" placeholder="Search tasks" /></label></div><div className="mt-5 divide-y">{tasks.length ? tasks.map((task, index) => <RecentTaskRow key={task.id} task={task} index={index} />) : <EmptyState title="No tasks found" description="Try a different search or status filter." />}</div></section></div></>;
}

