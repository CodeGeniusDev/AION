"use client";

import Link from "next/link";
import {
  AlertTriangle,
  Bell,
  CheckCircle2,
  Inbox,
  Info,
  Loader2,
  X,
  XCircle,
  Check,
  type LucideIcon,
} from "lucide-react";
import type { AlertItem, AlertCategory } from "@/types";
import { Dropdown } from "@/components/ui/dropdown";
import { useNotifications } from "@/hooks/useNotifications";
import { cn } from "@/utils/cn";

/** Fallback route when an alert predates the additive `link` field. */
const CATEGORY_ROUTE: Record<AlertCategory, string> = {
  task: "/tasks",
  agent: "/agents",
  memory: "/memory",
  approval: "/desktop",
  system: "/settings",
};

const TONE_ICON: Record<AlertItem["tone"], LucideIcon> = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  error: XCircle,
};

const TONE_CLASS: Record<AlertItem["tone"], string> = {
  info: "text-primary",
  success: "text-success-text",
  warning: "text-warning-text",
  error: "text-danger-text",
};

/** "2m ago" style label derived from the real ISO created_at. */
function relativeTime(iso: string | undefined, fallback: string): string {
  if (!iso) return fallback;
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return fallback;
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(then).toLocaleDateString();
}

const MAX_VISIBLE = 8;

export function NotificationsPopover() {
  const {
    alerts,
    unreadCount,
    loading,
    error,
    refresh,
    markRead,
    markAllRead,
    remove,
  } = useNotifications();

  async function openAlert(alert: AlertItem, close: () => void) {
    void markRead(alert);
    close();
  }

  const visible = alerts.slice(0, MAX_VISIBLE);

  return (
    <Dropdown
      label="Notifications"
      className="shrink-0"
      panelClassName="w-[22rem] max-w-[calc(100vw-2rem)]"
      trigger={({ open, toggle }) => (
        <button
          type="button"
          onClick={() => {
            if (!open) void refresh();
            toggle();
          }}
          aria-label={`Notifications${unreadCount > 0 ? `, ${unreadCount} unread` : ""}`}
          className={cn(
            "relative grid size-10 place-items-center rounded-full border bg-surface text-navy shadow-[0_2px_10px_rgba(25,36,56,0.035)] hover:bg-muted sm:size-11",
            open && "bg-muted",
          )}>
          <Bell className="size-4 sm:size-[18px]" />
          {unreadCount > 0 ? (
            <span className="absolute right-1.5 top-1.5 grid min-w-4 place-items-center rounded-full bg-destructive px-1 text-[9px] font-semibold leading-4 text-white sm:right-2 sm:top-2">
              {unreadCount > 9 ? "9+" : unreadCount}
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
              onClick={() => void markAllRead()}
              disabled={unreadCount === 0}
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
              <div className="flex flex-col items-center gap-2 px-4 py-8 text-sm text-muted-text">
                <AlertTriangle className="size-5 text-destructive" />
                {error}
                <button
                  type="button"
                  onClick={() => void refresh()}
                  className="text-xs font-medium text-primary hover:underline">
                  Retry
                </button>
              </div>
            ) : visible.length === 0 ? (
              <div className="flex flex-col items-center gap-2 px-4 py-10 text-center text-sm text-muted-text">
                <Inbox className="size-6" />
                You&apos;re all caught up — no notifications yet.
              </div>
            ) : (
              <ul className="divide-y">
                {visible.map((alert) => {
                  const Icon = TONE_ICON[alert.tone];
                  return (
                    <li key={alert.id} className="group relative">
                      <Link
                        href={
                          alert.link ??
                          CATEGORY_ROUTE[alert.category] ??
                          "/alert"
                        }
                        onClick={() => void openAlert(alert, close)}
                        className={cn(
                          "flex w-full gap-3 px-4 py-3 pr-10 text-left transition-colors hover:bg-muted",
                          alert.unread && "bg-soft-blue/30",
                        )}>
                        <Icon
                          className={cn(
                            "mt-0.5 size-4 shrink-0",
                            TONE_CLASS[alert.tone],
                          )}
                          aria-hidden="true"
                        />
                        <span className="min-w-0 flex-1">
                          <span className="flex items-center gap-2">
                            <span className="truncate text-sm font-medium">
                              {alert.title}
                            </span>
                            {alert.unread ? (
                              <span
                                className="ml-auto size-1.5 shrink-0 rounded-full bg-primary"
                                aria-label="Unread"
                              />
                            ) : null}
                          </span>
                          <span className="mt-0.5 block truncate text-xs text-muted-text">
                            {alert.description}
                          </span>
                          <span className="mt-1 block text-[11px] text-muted-text">
                            {relativeTime(alert.created_at, alert.time)}
                          </span>
                        </span>
                      </Link>
                      <button
                        type="button"
                        aria-label={`Delete notification: ${alert.title}`}
                        onClick={() => void remove(alert)}
                        className="absolute right-2 top-3 grid size-6 place-items-center rounded-full text-muted-text opacity-0 transition-opacity hover:bg-muted hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100 group-focus-within:opacity-100">
                        <X className="size-3.5" />
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <Link
            href="/alert"
            onClick={close}
            className="border-t px-4 py-2.5 text-center text-xs font-medium text-primary hover:bg-muted">
            View all notifications
          </Link>
        </div>
      )}
    </Dropdown>
  );
}
