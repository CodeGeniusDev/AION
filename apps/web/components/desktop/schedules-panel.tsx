"use client";

import { useCallback, useEffect, useState } from "react";
import { AlarmClock, Plus, X } from "lucide-react";
import {
  cancelSchedule,
  createSchedule,
  getSchedules,
  pauseSchedule,
  resumeSchedule,
} from "@/services/api";
import type { Schedule } from "@/types";
import { SectionCard } from "@/components/ui/section-card";
import { EmptyState } from "@/components/ui/empty-state";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import { Button } from "@/components/ui/button";

/** Poll cadence matches the rest of the Desktop tab. Schedules fire into
 * the approval queue — decisions themselves stay on the faster queue poll. */
const POLL_INTERVAL_MS = 10_000;

/** Tools the backend accepts for scheduling (its known_desktop_tools set).
 * Everything here is still approval-gated at fire time — this list only
 * drives the form; the server re-validates on create and at fire. */
const SCHEDULABLE_TOOLS = [
  "file_write",
  "file_read",
  "file_copy",
  "desktop_screenshot",
  "desktop_open_app",
  "browser_navigate",
  "browser_screenshot",
  "desktop_list_apps",
  "voice_say",
  "voice_listen",
];

function formatTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

function intervalLabel(seconds: number): string {
  if (seconds <= 0) return "one-shot";
  if (seconds < 60) return `every ${seconds}s`;
  if (seconds < 3600) return `every ${Math.round(seconds / 60)}min`;
  if (seconds < 86400) return `every ${Math.round(seconds / 3600)}h`;
  return `every ${Math.round(seconds / 86400)}d`;
}

type SectionState = "loading" | "ready" | "error";

export function SchedulesPanel() {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [state, setState] = useState<SectionState>("loading");

  // ── Create form (hidden until toggled) ──
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [tool, setTool] = useState(SCHEDULABLE_TOOLS[0]);
  const [intervalText, setIntervalText] = useState("3600");
  const [delayText, setDelayText] = useState("0");
  const [params, setParams] = useState("{}");
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    try {
      const response = await getSchedules();
      // Newest first; terminal rows stay visible as history.
      setSchedules(
        [...response.items].sort((a, b) => b.created_at.localeCompare(a.created_at)),
      );
      setState("ready");
    } catch {
      setState("error");
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    const refresh = () => {
      if (mounted && document.visibilityState === "visible") void load();
    };
    refresh();
    const timer = window.setInterval(refresh, POLL_INTERVAL_MS);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      await load();
    } catch {
      setState("error");
    }
  };

  const submit = async () => {
    setFormError(null);
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(params || "{}") as Record<string, unknown>;
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed))
        throw new Error("not an object");
    } catch {
      setFormError("Parameters must be a JSON object, e.g. {\"path\": \"a.txt\"}");
      return;
    }
    const intervalSeconds = Number(intervalText);
    if (!Number.isFinite(intervalSeconds) || intervalSeconds < 0) {
      setFormError("Interval must be a non-negative number of seconds (0 = one-shot).");
      return;
    }
    const delaySeconds = Number(delayText || 0);
    if (!Number.isFinite(delaySeconds) || delaySeconds < 0) {
      setFormError("First-fire delay must be a non-negative number of seconds.");
      return;
    }
    setSubmitting(true);
    try {
      await createSchedule({
        name: name.trim(),
        tool,
        parameters: parsed,
        interval_seconds: intervalSeconds,
        delay_seconds: delaySeconds,
      });
      setShowForm(false);
      setName("");
      setParams("{}");
      await load();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Could not create the schedule.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SectionCard
      title="Scheduled actions"
      description="Recurring desktop requests. When one fires it lands in the approval queue above — a schedule can never execute anything by itself."
      action={
        <Button
          size="sm"
          variant="outline"
          onClick={() => setShowForm((v) => !v)}
          aria-expanded={showForm}>
          {showForm ? <X className="mr-2 size-4" /> : <Plus className="mr-2 size-4" />}
          {showForm ? "Close" : "New schedule"}
        </Button>
      }>
      {showForm && (
        <div className="mb-4 rounded-[16px] border bg-[#fafbfd] p-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-xs font-medium">
              Name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Nightly backup request"
                className="mt-2 h-11 w-full rounded-full border px-4 text-sm"
              />
            </label>
            <label className="block text-xs font-medium">
              Tool
              <select
                value={tool}
                onChange={(e) => setTool(e.target.value)}
                className="mt-2 h-11 w-full rounded-full border bg-white px-4 text-sm">
                {SCHEDULABLE_TOOLS.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </label>
            <label className="block text-xs font-medium">
              Repeat every (seconds, 0 = one-shot)
              <input
                value={intervalText}
                onChange={(e) => setIntervalText(e.target.value)}
                inputMode="numeric"
                className="mt-2 h-11 w-full rounded-full border px-4 text-sm"
              />
            </label>
            <label className="block text-xs font-medium">
              First fire after (seconds)
              <input
                value={delayText}
                onChange={(e) => setDelayText(e.target.value)}
                inputMode="numeric"
                className="mt-2 h-11 w-full rounded-full border px-4 text-sm"
              />
            </label>
          </div>
          <label className="mt-4 block text-xs font-medium">
            Parameters (JSON)
            <textarea
              value={params}
              onChange={(e) => setParams(e.target.value)}
              rows={3}
              placeholder='{"path": "report.txt", "content": "hello"}'
              className="mt-2 w-full rounded-[16px] border px-4 py-3 font-mono text-xs"
            />
          </label>
          {formError && (
            <p role="alert" className="mt-2 text-xs text-red-600">{formError}</p>
          )}
          <div className="mt-3 flex items-center gap-2">
            <Button
              size="sm"
              disabled={!name.trim() || submitting}
              onClick={() => void submit()}>
              {submitting ? "Creating…" : "Create schedule"}
            </Button>
            <p className="text-[11px] text-muted-text">
              Creates approvals on a timer. Each one still needs your explicit approval.
            </p>
          </div>
        </div>
      )}

      {state === "loading" ? (
        <div aria-label="Loading schedules" className="space-y-3">
          {[0, 1].map((i) => (
            <LoadingSkeleton key={i} className="h-14" />
          ))}
        </div>
      ) : state === "error" ? (
        <EmptyState
          title="Unable to load schedules"
          description="AION could not reach the schedule store. Check that the backend is running, then retry."
          action={
            <Button variant="outline" size="sm" onClick={() => void load()}>
              Retry
            </Button>
          }
        />
      ) : schedules.length === 0 ? (
        <EmptyState
          title="No schedules yet"
          description="Create a schedule to have AION regularly ask your permission — screenshots, exports, backups. Nothing ever runs without you."
        />
      ) : (
        <ul className="space-y-3">
          {schedules.map((s) => (
            <li key={s.id} className="rounded-[16px] border p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-semibold">{s.name}</p>
                <StatusBadge status={s.status} />
              </div>
              <p className="mt-0.5 text-[11px] text-muted-text">
                <AlarmClock className="mr-1 inline size-3" />
                {s.tool} · {intervalLabel(s.interval_seconds)} · fired {s.fire_count}×
              </p>
              <p className="mt-1 text-[11px] text-muted-text">
                {s.status === "active" && s.next_run_at
                  ? `Next request: ${formatTime(s.next_run_at)}`
                  : s.last_run_at
                    ? `Last fired: ${formatTime(s.last_run_at)}`
                    : `Created: ${formatTime(s.created_at)}`}
              </p>
              {s.last_error && (
                <p className="mt-1 text-xs text-red-600">{s.last_error}</p>
              )}
              <div className="mt-2 flex flex-wrap gap-2">
                {s.status === "active" && (
                  <Button size="sm" variant="outline" onClick={() => void act(() => pauseSchedule(s.id))}>
                    Pause
                  </Button>
                )}
                {s.status === "paused" && (
                  <Button size="sm" variant="outline" onClick={() => void act(() => resumeSchedule(s.id))}>
                    Resume
                  </Button>
                )}
                {(s.status === "active" || s.status === "paused") && (
                  <Button size="sm" variant="outline" onClick={() => void act(() => cancelSchedule(s.id))}>
                    Cancel
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
