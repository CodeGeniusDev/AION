"use client";

import { useMemo, useState } from "react";
import {
  Archive,
  ArrowUpRight,
  Bell,
  Bot,
  Check,
  CheckCheck,
  CircleAlert,
  Clock3,
  FileCheck2,
  MoreHorizontal,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { cn } from "@/utils/cn";

type AlertFilter = "all" | "unread";

interface AlertItem {
  id: string;
  title: string;
  description: string;
  time: string;
  category: string;
  unread: boolean;
  tone: string;
  icon: typeof Bell;
}

const initialAlerts: AlertItem[] = [
  {
    id: "task-complete",
    title: "Research task completed",
    description: "AION finished the solar energy research brief with a verified confidence score of 92%.",
    time: "12 minutes ago",
    category: "Task update",
    unread: true,
    tone: "bg-soft-blue text-primary",
    icon: FileCheck2,
  },
  {
    id: "agent-connected",
    title: "Research Agent is ready",
    description: "The Research Agent connected successfully and is available for your next workflow.",
    time: "42 minutes ago",
    category: "Agent activity",
    unread: true,
    tone: "bg-soft-green text-[#1d8a5b]",
    icon: Bot,
  },
  {
    id: "memory-saved",
    title: "New memory saved",
    description: "AION saved three useful context items from your latest planning conversation.",
    time: "Yesterday",
    category: "Memory",
    unread: false,
    tone: "bg-soft-peach text-[#b67224]",
    icon: Sparkles,
  },
  {
    id: "health-check",
    title: "System health check passed",
    description: "All connected services are operational. API, memory, and agents are online.",
    time: "Yesterday",
    category: "System",
    unread: false,
    tone: "bg-[#e9e7f6] text-[#6d61b2]",
    icon: ShieldCheck,
  },
  {
    id: "workflow-review",
    title: "Workflow needs your review",
    description: "The Critic Agent flagged one item in the product strategy workflow for confirmation.",
    time: "Monday",
    category: "Action needed",
    unread: false,
    tone: "bg-[#fff0d9] text-[#c37a21]",
    icon: CircleAlert,
  },
];

export function AlertView() {
  const [alerts, setAlerts] = useState(initialAlerts);
  const [filter, setFilter] = useState<AlertFilter>("all");

  const unreadCount = alerts.filter((alert) => alert.unread).length;
  const visibleAlerts = useMemo(
    () => (filter === "unread" ? alerts.filter((alert) => alert.unread) : alerts),
    [alerts, filter],
  );

  function markAllAsRead() {
    setAlerts((current) => current.map((alert) => ({ ...alert, unread: false })));
  }

  function markAsRead(id: string) {
    setAlerts((current) => current.map((alert) => (alert.id === id ? { ...alert, unread: false } : alert)));
  }

  return (
    <>
      <PageHeader
        eyebrow="AION Workspace"
        title="Notifications"
        description="Stay up to date with task results, agent activity, and important system updates."
        action={
          <Button variant="outline" size="sm" onClick={markAllAsRead} disabled={unreadCount === 0}>
            <CheckCheck className="mr-2 size-4" />
            Mark all as read
          </Button>
        }
      />

      <div className="grid gap-5 p-4 sm:p-6 lg:grid-cols-[minmax(0,1fr)_280px] lg:p-7">
        <section className="min-w-0 rounded-[24px] border bg-white p-5 sm:p-6" aria-labelledby="notification-list-title">
          <div className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex items-center gap-2">
                <h2 id="notification-list-title" className="text-lg font-semibold tracking-[-0.02em]">Recent updates</h2>
                {unreadCount > 0 && <span className="rounded-full bg-[#edf3ff] px-2 py-1 text-[10px] font-semibold text-primary">{unreadCount} new</span>}
              </div>
              <p className="mt-1 text-xs leading-5 text-muted-text">Your latest AION workspace activity</p>
            </div>
            <div className="flex rounded-full border bg-[#f8fafc] p-1" role="tablist" aria-label="Notification filters">
              {(["all", "unread"] as AlertFilter[]).map((item) => (
                <button
                  key={item}
                  type="button"
                  role="tab"
                  aria-selected={filter === item}
                  onClick={() => setFilter(item)}
                  className={cn("rounded-full px-3 py-1.5 text-xs font-medium capitalize transition-colors", filter === item ? "bg-white text-aion-text shadow-sm" : "text-muted-text hover:text-aion-text")}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>

          <div className="divide-y">
            {visibleAlerts.length > 0 ? visibleAlerts.map((alert) => {
              const Icon = alert.icon;
              return (
                <article key={alert.id} className={cn("group flex gap-3 py-4 sm:gap-4", alert.unread && "-mx-2 rounded-[18px] bg-[#fbfcff] px-2")}>
                  <span className={cn("grid size-10 shrink-0 place-items-center rounded-[15px] sm:size-11", alert.tone)}>
                    <Icon className="size-[17px]" strokeWidth={1.8} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-start gap-x-2 gap-y-1">
                      <h3 className="text-sm font-semibold text-aion-text">{alert.title}</h3>
                      {alert.unread && <span className="mt-1.5 size-1.5 rounded-full bg-primary" aria-label="Unread" />}
                    </div>
                    <p className="mt-1 max-w-2xl text-xs leading-5 text-muted-text">{alert.description}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-muted-text">
                      <span>{alert.category}</span>
                      <span className="size-1 rounded-full bg-[#c6ccd5]" />
                      <span className="inline-flex items-center gap-1"><Clock3 className="size-3" />{alert.time}</span>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-start gap-1 opacity-100 sm:opacity-0 sm:transition-opacity sm:group-hover:opacity-100">
                    {alert.unread && <button type="button" onClick={() => markAsRead(alert.id)} className="grid size-8 place-items-center rounded-full text-muted-text hover:bg-[#eef3fb] hover:text-primary" aria-label={`Mark ${alert.title} as read`}><Check className="size-4" /></button>}
                    <button type="button" className="grid size-8 place-items-center rounded-full text-muted-text hover:bg-[#eef3fb] hover:text-primary" aria-label={`Open ${alert.title}`}><ArrowUpRight className="size-4" /></button>
                    <button type="button" className="hidden size-8 place-items-center rounded-full text-muted-text hover:bg-[#eef3fb] hover:text-primary sm:grid" aria-label={`More options for ${alert.title}`}><MoreHorizontal className="size-4" /></button>
                  </div>
                </article>
              );
            }) : (
              <div className="flex min-h-[260px] flex-col items-center justify-center px-4 text-center">
                <span className="grid size-12 place-items-center rounded-full bg-[#eef3fb] text-primary"><Bell className="size-5" /></span>
                <h3 className="mt-4 text-base font-semibold">You&apos;re all caught up</h3>
                <p className="mt-1 max-w-xs text-sm leading-6 text-muted-text">There are no unread notifications waiting for you.</p>
              </div>
            )}
          </div>
        </section>

        <aside className="space-y-5">
          <section className="relative overflow-hidden rounded-[24px] border bg-[#f5f7fb] p-6" aria-labelledby="notification-summary-title">
            <div className="absolute -right-9 -top-9 size-32 rounded-full bg-[#e5edff]" aria-hidden="true" />
            <div className="relative">
              <div className="relative mx-auto grid size-[92px] place-items-center rounded-full border-2 border-[#dce2ea] bg-white shadow-[0_8px_22px_rgba(25,36,56,0.06)]">
                <Bell className="size-10 text-navy" strokeWidth={1.6} />
                <span className="absolute right-4 top-4 size-3 rounded-full border-2 border-white bg-primary" />
              </div>
              <h2 id="notification-summary-title" className="mt-5 text-center text-lg font-semibold">AION alerts</h2>
              <p className="mt-1 text-center text-xs leading-5 text-muted-text">Important workspace updates, collected in one place.</p>
            </div>
          </section>

          <section className="rounded-[24px] border bg-white p-5" aria-labelledby="notification-preferences-title">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 id="notification-preferences-title" className="text-sm font-semibold">Notification overview</h2>
                <p className="mt-1 text-xs text-muted-text">Current workspace activity</p>
              </div>
              <Archive className="size-4 text-primary" />
            </div>
            <dl className="mt-5 space-y-4">
              <div className="flex items-center justify-between text-xs"><dt className="text-muted-text">Total updates</dt><dd className="font-semibold">{alerts.length}</dd></div>
              <div className="flex items-center justify-between text-xs"><dt className="text-muted-text">Unread</dt><dd className="font-semibold text-primary">{unreadCount}</dd></div>
              <div className="flex items-center justify-between text-xs"><dt className="text-muted-text">Last update</dt><dd className="font-semibold">12 min ago</dd></div>
            </dl>
            <div className="mt-5 rounded-[17px] bg-[#f6f8fb] p-3 text-[11px] leading-5 text-muted-text"><Sparkles className="mr-1 inline size-3 text-primary" /> AION will keep this space ready for future task and agent alerts.</div>
          </section>
        </aside>
      </div>
    </>
  );
}
