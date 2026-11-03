"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Activity,
  RefreshCw,
  ScrollText,
  ShieldCheck,
  WifiOff,
} from "lucide-react";
import {
  getApprovals,
  getAudit,
  getDesktopHealth,
  getTask,
} from "@/services/api";
import type { ApprovalRecord, AuditEvent, DesktopHealth } from "@/types";
import { PageHeader } from "@/components/layout/page-header";
import { usePageSearch } from "@/components/layout/page-search-provider";
import { ApprovalQueue } from "@/components/approvals/approval-queue";
import { SchedulesPanel } from "@/components/desktop/schedules-panel";
import { SectionCard } from "@/components/ui/section-card";
import { EmptyState } from "@/components/ui/empty-state";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/utils/cn";

/** Poll cadence for health/history/audit (ms). The ApprovalQueue owns its
 * own faster poll — decisions must feel live there. */
const POLL_INTERVAL_MS = 10_000;

/** History rows whose task output we additionally fetch (bounded so the
 * page never fans out more than 8 detail requests per refresh). */
const OUTPUT_FETCH_LIMIT = 8;

type SectionState = "loading" | "ready" | "error";

/** Same sanitized preview the approval queue uses: the API only ever
 * returns redacted values for secret-like keys — we render exactly that. */
function parameterSummary(parameters: Record<string, unknown>): string {
  return Object.entries(parameters)
    .map(([key, value]) => {
      if (value && typeof value === "object" && "redacted" in value)
        return `${key}: [redacted]`;
      const text = typeof value === "string" ? value : JSON.stringify(value);
      return `${key}: ${text.length > 64 ? `${text.slice(0, 64)}…` : text}`;
    })
    .join(" · ");
}

function formatTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

export function DesktopView() {
  const searchParams = useSearchParams();
  const { matches } = usePageSearch();
  // ── Bridge health ──
  const [health, setHealth] = useState<DesktopHealth | null>(null);
  const [healthState, setHealthState] = useState<SectionState>("loading");

  // ── Task history (approvals, all statuses) + per-task output previews ──
  const [history, setHistory] = useState<ApprovalRecord[]>([]);
  const [outputs, setOutputs] = useState<Record<string, string | null>>({});
  const [historyState, setHistoryState] = useState<SectionState>("loading");

  // ── Recent audit events ──
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [auditState, setAuditState] = useState<SectionState>("loading");

  const loadHealth = useCallback(async () => {
    try {
      setHealth(await getDesktopHealth());
      setHealthState("ready");
    } catch {
      setHealthState("error");
    }
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const response = await getApprovals({ limit: 50 });
      const items = [...response.items].sort((a, b) =>
        b.created_at.localeCompare(a.created_at),
      );
      setHistory(items);
      setHistoryState("ready");
      // Fetch task output for the most recent terminal rows so history
      // shows what actually happened, not just that it happened.
      const terminal = items
        .filter((item) => item.status === "completed" || item.status === "failed")
        .slice(0, OUTPUT_FETCH_LIMIT);
      const results = await Promise.allSettled(
        terminal.map((item) => getTask(item.task_id)),
      );
      const next: Record<string, string | null> = {};
      results.forEach((result, index) => {
        const task = terminal[index];
        if (result.status !== "fulfilled") return;
        const output = result.value.output;
        next[task.task_id] = output
          ? output.error ?? output.content ?? (output.success ? "success" : "failed")
          : null;
      });
      setOutputs(next);
    } catch {
      setHistoryState("error");
    }
  }, []);

  const loadAudit = useCallback(async () => {
    try {
      // The API returns the trail chronologically; fetch a wide window and
      // keep the newest rows, rendered oldest→newest inside that window.
      const response = await getAudit(100);
      setAudit(response.items.slice(-12));
      setAuditState("ready");
    } catch {
      setAuditState("error");
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    const refresh = () => {
      if (!mounted) return;
      if (document.visibilityState === "visible") {
        void loadHealth();
        void loadHistory();
        void loadAudit();
      }
    };
    refresh();
    const timer = window.setInterval(refresh, POLL_INTERVAL_MS);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      mounted = false;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [loadHealth, loadHistory, loadAudit]);

  const retryAll = () => {
    setHealthState("loading");
    setHistoryState("loading");
    setAuditState("loading");
    void loadHealth();
    void loadHistory();
    void loadAudit();
  };

  // "This page" scope filters the real history rows by tool, id or status.
  const visibleHistory = useMemo(
    () => history.filter((item) => matches(item.tool, item.id, item.status)),
    [history, matches],
  );

  // Deep links from global search (/desktop?approval=ID) scroll to that
  // ledger row. Pending items are already visible in the live queue above.
  const approvalParam = searchParams.get("approval");
  useEffect(() => {
    if (!approvalParam || historyState !== "ready") return;
    document
      .getElementById(`approval-row-${approvalParam}`)
      ?.scrollIntoView({ block: "center" });
  }, [approvalParam, historyState, visibleHistory]);

  return (
    <>
      <PageHeader
        eyebrow="Local machine"
        title="Desktop"
        description="Approval-gated control of your own computer. Nothing runs here until you approve it — every action is ledgered, executed exactly once and audit-logged."
        action={
          <Button variant="outline" onClick={retryAll}>
            <RefreshCw className="mr-2 size-4" />
            Refresh
          </Button>
        }
      />
      <div className="space-y-5 p-4 sm:p-6 lg:p-7">
        {/* ── Bridge health strip ── */}
        <section
          aria-label="Desktop bridge health"
          className="flex flex-wrap items-center gap-3 rounded-[24px] border bg-surface px-5 py-4">
          {healthState === "loading" ? (
            <LoadingSkeleton className="h-5 w-56" />
          ) : healthState === "error" ? (
            <>
              <WifiOff className="size-4 text-red-500" />
              <span className="text-sm font-medium">
                Health check failed — the AION API is unreachable.
              </span>
              <Button size="sm" variant="outline" onClick={() => void loadHealth()}>
                Retry
              </Button>
            </>
          ) : (
            <>
              <span
                className={cn(
                  "size-2.5 rounded-full",
                  health?.reachable
                    ? "bg-success-solid shadow-[0_0_0_4px_rgba(53,185,120,0.12)]"
                    : "bg-danger-solid shadow-[0_0_0_4px_rgba(181,61,61,0.12)]",
                )}
              />
              <span className="text-sm font-medium">
                {health?.reachable ? "Agent bridge online" : "Agent bridge offline"}
              </span>
              <span className="text-xs text-muted-text">
                {health?.reachable
                  ? "Approved actions can dispatch now. Executions still require you here."
                  : "Start the desktop agent (`python -m aion_desktop.cli run`) — pending approvals stay safely queued until it returns."}
              </span>
              <Activity className="ml-auto size-4 text-primary" aria-hidden="true" />
            </>
          )}
        </section>

        {/* ── Live approval queue (shared with the Tasks page) ── */}
        <ApprovalQueue
          fallback={
            <section
              aria-label="Approval queue empty"
              className="flex items-center gap-3 rounded-[24px] border border-success-border bg-success-soft/50 px-5 py-4">
              <ShieldCheck className="size-4 text-success-text" />
              <p className="text-sm font-medium text-success-text">
                Queue is clear — nothing is waiting for your approval.
              </p>
            </section>
          }
        />

        {/* ── Scheduled actions — fire into the queue above, never past it ── */}
        <SchedulesPanel />

        <div className="grid gap-5 lg:grid-cols-2">
          {/* ── Desktop task history ── */}
          <SectionCard
            title="Desktop task history"
            description="Every protected action ever requested, with its real outcome and stored output.">
            {historyState === "loading" ? (
              <div aria-label="Loading desktop history" className="space-y-3">
                {[0, 1, 2].map((item) => (
                  <LoadingSkeleton key={item} className="h-16" />
                ))}
              </div>
            ) : historyState === "error" ? (
              <EmptyState
                title="Unable to load history"
                description="AION could not reach the approvals ledger. Check that the backend is running, then retry."
                action={
                  <Button variant="outline" size="sm" onClick={() => void loadHistory()}>
                    Retry
                  </Button>
                }
              />
            ) : history.length === 0 ? (
              <EmptyState
                title="No desktop actions yet"
                description="Ask AION in chat to do something on your machine — it will show up here as a pending approval, never as a silent execution."
              />
            ) : visibleHistory.length === 0 ? (
              <EmptyState
                title="No history rows match the search"
                description="Nothing on this page matches the current filter. Clear the search to see the full ledger again."
              />
            ) : (
              <ul className="space-y-3">
                {visibleHistory.map((item) => (
                  <li
                    key={item.id}
                    id={`approval-row-${item.id}`}
                    className={cn(
                      "rounded-[16px] border p-4",
                      approvalParam === item.id && "border-primary bg-soft-blue/40",
                    )}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-semibold">{item.tool}</p>
                      <StatusBadge status={item.status} />
                    </div>
                    <p className="mt-0.5 text-[11px] text-muted-text">
                      {item.id} · {formatTime(item.created_at)}
                    </p>
                    <p className="mt-2 break-all rounded bg-muted px-3 py-2 font-mono text-[11px] text-muted-text">
                      {parameterSummary(item.parameters)}
                    </p>
                    {outputs[item.task_id] != null && (
                      <p
                        title={outputs[item.task_id] ?? undefined}
                        className={cn(
                          "mt-2 line-clamp-2 text-xs",
                          item.status === "completed"
                            ? "text-success-text"
                            : "text-red-600",
                        )}>
                        {outputs[item.task_id]}
                      </p>
                    )}
                    {item.error && item.status !== "completed" && (
                      <p className="mt-2 text-xs text-red-600">{item.error}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>

          {/* ── Recent audit events ── */}
          <SectionCard
            title="Recent audit events"
            description="Append-only trail: requested → approved → claimed → granted → executed. It can never be edited or deleted through the API."
            action={<ScrollText className="size-4 text-muted-text" aria-hidden="true" />}>
            {auditState === "loading" ? (
              <div aria-label="Loading audit events" className="space-y-3">
                {[0, 1, 2].map((item) => (
                  <LoadingSkeleton key={item} className="h-10" />
                ))}
              </div>
            ) : auditState === "error" ? (
              <EmptyState
                title="Unable to load the audit trail"
                description="AION could not reach the audit log. Check that the backend is running, then retry."
                action={
                  <Button variant="outline" size="sm" onClick={() => void loadAudit()}>
                    Retry
                  </Button>
                }
              />
            ) : audit.length === 0 ? (
              <EmptyState
                title="No audit events yet"
                description="The trail starts recording with the first approval request."
              />
            ) : (
              <ol className="space-y-2">
                {audit.map((event) => (
                  <li
                    key={event.seq}
                    className="flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-[14px] bg-muted px-4 py-2.5">
                    <span className="rounded-full bg-surface px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em]">
                      {event.event}
                    </span>
                    <span className="font-mono text-[11px] text-muted-text">
                      {event.approval_id}
                    </span>
                    {event.actor_key_id && (
                      <span className="text-[11px] text-muted-text">
                        by {event.actor_key_id}
                      </span>
                    )}
                    <span className="ml-auto text-[11px] text-muted-text">
                      {formatTime(event.ts)}
                    </span>
                    {event.detail && (
                      <p className="w-full break-all text-[11px] text-muted-text">
                        {event.detail}
                      </p>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </SectionCard>
        </div>
      </div>
    </>
  );
}
