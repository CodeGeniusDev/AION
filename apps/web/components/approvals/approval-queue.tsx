"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Check, ShieldAlert, X } from "lucide-react";
import {
  approveAction,
  getPendingApprovals,
  rejectAction,
} from "@/services/api";
import type { ApprovalRecord } from "@/types";
import { Button } from "@/components/ui/button";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import { cn } from "@/utils/cn";

/** Poll cadence for the pending-approval queue (ms). */
const POLL_INTERVAL_MS = 5_000;

/** Per-approval in-flight decision state: idle → pending → done/error. */
type DecisionState = "idle" | "pending" | "approved" | "rejected" | "error";

function remainingSeconds(expiresAt: string): number {
  const ms = new Date(expiresAt).getTime() - Date.now();
  return Math.max(0, Math.ceil(ms / 1000));
}

function formatRemaining(seconds: number): string {
  if (seconds <= 0) return "expired";
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

/** Compact, sanitized parameter preview. The API only ever returns
 * redacted values for secret-like keys and file content — this renders
 * exactly that, nothing more. */
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

export function ApprovalQueue({ fallback = null }: { fallback?: ReactNode }) {
  const [approvals, setApprovals] = useState<ApprovalRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(false);
  const [decisions, setDecisions] = useState<Record<string, DecisionState>>({});
  const [decisionErrors, setDecisionErrors] = useState<Record<string, string>>(
    {},
  );
  const [nowTick, setNowTick] = useState(() => Date.now());

  const refresh = useCallback(async () => {
    try {
      const response = await getPendingApprovals();
      setApprovals(response.items);
      setFetchError(false);
    } catch {
      setFetchError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  // Poll while the tab is visible; pause when hidden (no background churn).
  useEffect(() => {
    let mounted = true;
    const poll = () => {
      if (mounted && document.visibilityState === "visible") void refresh();
    };
    poll();
    const timer = window.setInterval(poll, POLL_INTERVAL_MS);
    window.addEventListener("visibilitychange", poll);
    return () => {
      mounted = false;
      window.clearInterval(timer);
      window.removeEventListener("visibilitychange", poll);
    };
  }, [refresh]);

  // 1 s cadence only for the expiry countdown labels.
  useEffect(() => {
    const timer = window.setInterval(() => setNowTick(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const decide = useCallback(
    async (approvalId: string, action: "approve" | "reject") => {
      setDecisions((current) => ({ ...current, [approvalId]: "pending" }));
      setDecisionErrors((current) => ({ ...current, [approvalId]: "" }));
      try {
        if (action === "approve") {
          await approveAction(approvalId);
          setDecisions((current) => ({ ...current, [approvalId]: "approved" }));
        } else {
          await rejectAction(approvalId);
          setDecisions((current) => ({ ...current, [approvalId]: "rejected" }));
        }
        // Drop it from the queue right away; the next poll confirms.
        setApprovals((current) =>
          current.filter((item) => item.id !== approvalId),
        );
      } catch (error) {
        setDecisions((current) => ({ ...current, [approvalId]: "error" }));
        setDecisionErrors((current) => ({
          ...current,
          [approvalId]:
            error instanceof Error ? error.message : "Decision failed",
        }));
      }
    },
    [],
  );

  const visible = approvals;
  void nowTick; // countdown re-render driver; labels read remainingSeconds() at render time

  if (loading) {
    return (
      <section
        aria-label="Loading pending approvals"
        className="mb-5 rounded-[24px] border bg-surface p-5">
        <LoadingSkeleton className="h-6 w-56" />
        <LoadingSkeleton className="mt-4 h-16" />
      </section>
    );
  }

  if (fetchError) {
    return (
      <section className="mb-5 rounded-[24px] border bg-surface p-5">
        <div className="flex items-center gap-2 text-xs text-muted-text">
          <ShieldAlert className="size-4 text-amber-500" />
          The approval queue is unreachable right now. Pending desktop actions
          stay blocked until it responds.
        </div>
      </section>
    );
  }

  if (visible.length === 0) return <>{fallback}</>;

  return (
    <section
      aria-label="Pending desktop tool approvals"
      className="mb-5 rounded-[24px] border border-amber-200 bg-amber-50/40 p-5">
      <div className="flex items-center gap-2">
        <ShieldAlert className="size-4 text-amber-600" />
        <h2 className="text-sm font-semibold">Pending desktop approvals</h2>
        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
          {visible.length}
        </span>
      </div>
      <p className="mt-1 text-xs text-muted-text">
        Nothing runs on your desktop until you approve it here. Each approval
        executes exactly once and expires on its deadline.
      </p>
      <ul className="mt-4 space-y-3">
        {visible.map((approval) => {
          const state = decisions[approval.id] ?? "idle";
          const settled = state === "approved" || state === "rejected";
          const secondsLeft = remainingSeconds(approval.expires_at);
          return (
            <li
              key={approval.id}
              className="rounded-[16px] border bg-surface p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-semibold">{approval.tool}</p>
                  <p className="mt-0.5 text-[11px] text-muted-text">
                    {approval.id} · task {approval.task_id} · expires in{" "}
                    {formatRemaining(secondsLeft)}
                  </p>
                  <p className="mt-2 break-all rounded bg-muted px-3 py-2 font-mono text-[11px] text-muted-text">
                    {parameterSummary(approval.parameters)}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {settled ? (
                    <span
                      className={cn(
                        "rounded-full px-3 py-1 text-[11px] font-semibold",
                        state === "approved"
                          ? "bg-green-100 text-green-700"
                          : "bg-red-100 text-red-700",
                      )}>
                      {state === "approved"
                        ? "Approved — running once"
                        : "Rejected — will never run"}
                    </span>
                  ) : (
                    <>
                      <Button
                        size="sm"
                        onClick={() => void decide(approval.id, "approve")}
                        disabled={state === "pending" || secondsLeft === 0}>
                        <Check className="mr-1.5 size-3.5" />
                        {state === "pending" ? "Approving…" : "Approve"}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void decide(approval.id, "reject")}
                        disabled={state === "pending"}>
                        <X className="mr-1.5 size-3.5" />
                        Reject
                      </Button>
                    </>
                  )}
                </div>
              </div>
              {state === "error" && decisionErrors[approval.id] && (
                <p className="mt-2 text-[11px] text-red-600">
                  {decisionErrors[approval.id]} — the action did not run. Retry
                  or reject it.
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
