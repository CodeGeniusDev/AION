"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, Check, Loader2, Inbox, AlertTriangle } from "lucide-react";
import { getAlerts, markAlertsRead, markAllAlertsRead } from "@/services/api";
import type { AlertItem, AlertCategory } from "@/types";
import { Dropdown } from "@/components/ui/dropdown";
import { cn } from "@/utils/cn";

const CATEGORY_ROUTE: Record<AlertCategory, string> = {
  task: "/tasks",
  agent: "/agents",
  memory: "/memory",
  approval: "/desktop",
  system: "/settings",
};

const TONE_DOT: Record<AlertItem["tone"], string> = {
  info: "bg-primary",
  success: "bg-success-solid",
  warning: "bg-warning-solid",
  error: "bg-destructive",
};

export function NotificationsPopover() {
  const router = useRouter();
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const response = await getAlerts({ limit: 20 });
      setAlerts(response.items);
      setUnread(response.unread_count);
    } catch {
      setError("Could not load notifications.");
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial read so the badge reflects real unread state on every page.
  useEffect(() => {
    void load();
  }, [load]);

  async function openAlert(alert: AlertItem, close: () => void) {
    if (alert.unread) {
      // Optimistically clear the dot, then confirm against the API.
      setAlerts((prev) =>
        prev.map((a) => (a.id === alert.id ? { ...a, unread: false } : a)),
      );
      setUnread((n) => Math.max(0, n - 1));
      try {
        await markAlertsRead([alert.id]);
      } catch {
        void load();
      }
    }
    close();
    router.push(CATEGORY_ROUTE[alert.category] ?? "/alert");
  }

  async function handleMarkAllRead() {
    if (unread === 0) return;
    setAlerts((prev) => prev.map((a) => ({ ...a, unread: false })));
    setUnread(0);
    try {
      await markAllAlertsRead();
    } catch {
      void load();
    }
  }

  return (
    <Dropdown
      label="Notifications"
      className="shrink-0"
      panelClassName="w-[22rem] max-w-[calc(100vw-2rem)]"
      trigger={({ open, toggle }) => (
        <button
          type="button"
          onClick={() => {
            if (!open) void load();
            toggle();
          }}
          aria-label={`Notifications${unread > 0 ? `, ${unread} unread` : ""}`}
          className={cn(
            "relative grid size-10 place-items-center rounded-full border bg-surface text-navy shadow-[0_2px_10px_rgba(25,36,56,0.035)] hover:bg-muted sm:size-11",
            open && "bg-muted",
          )}>
          <Bell className="size-4 sm:size-[18px]" />
          {unread > 0 ? (
            <span className="absolute right-1.5 top-1.5 grid min-w-4 place-items-center rounded-full bg-destructive px-1 text-[9px] font-semibold leading-4 text-white sm:right-2 sm:top-2">
              {unread > 9 ? "9+" : unread}
            </span>
          ) : null}
        </button>
      )}>
      {({ close }) => (
        <div className="flex flex-col">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <span className="text-sm font-semibold">Notifications</span>
            <button
              type="button"
              onClick={() => void handleMarkAllRead()}
              disabled={unread === 0}
              className="flex items-center gap-1 text-xs font-medium text-primary disabled:cursor-not-allowed disabled:text-muted-text">
              <Check className="size-3.5" /> Mark all read
            </button>
          </div>

          <div className="max-h-[20rem] overflow-y-auto scrollbar-subtle">
            {loading ? (
              <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-text">
                <Loader2 className="size-4 animate-spin" /> Loading…
              </div>
            ) : error ? (
              <div className="flex items-start gap-2 px-4 py-8 text-sm text-muted-text">
                <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
                {error}
              </div>
            ) : alerts.length === 0 ? (
              <div className="flex flex-col items-center gap-2 px-4 py-10 text-center text-sm text-muted-text">
                <Inbox className="size-6" />
                You&apos;re all caught up — no notifications yet.
              </div>
            ) : (
              <ul className="divide-y">
                {alerts.map((alert) => (
                  <li key={alert.id}>
                    <button
                      type="button"
                      onClick={() => void openAlert(alert, close)}
                      className={cn(
                        "flex w-full gap-3 px-4 py-3 text-left transition-colors hover:bg-muted",
                        alert.unread && "bg-soft-blue/30",
                      )}>
                      <span
                        className={cn(
                          "mt-1 size-2 shrink-0 rounded-full",
                          TONE_DOT[alert.tone],
                        )}
                        aria-hidden="true"
                      />
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-2">
                          <span className="truncate text-sm font-medium">
                            {alert.title}
                          </span>
                          {alert.unread ? (
                            <span className="ml-auto size-1.5 shrink-0 rounded-full bg-primary" />
                          ) : null}
                        </span>
                        <span className="mt-0.5 block truncate text-xs text-muted-text">
                          {alert.description}
                        </span>
                        <span className="mt-1 block text-[11px] text-muted-text">
                          {alert.time}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <button
            type="button"
            onClick={() => {
              close();
              router.push("/alert");
            }}
            className="border-t px-4 py-2.5 text-center text-xs font-medium text-primary hover:bg-muted">
            View all notifications
          </button>
        </div>
      )}
    </Dropdown>
  );
}
