"use client";

// Single source of truth for the notification bell + popover.
//
// Transport is deliberately isolated behind `fetchSnapshot()`: Phase 2
// swaps the 15s poll for the existing SSE stream by replacing that one
// function — components consuming this hook stay untouched.
//
// Behavior required by the Phase 1 spec:
// - poll every 15s while the tab is visible; pause when hidden;
// - refetch immediately when the tab regains focus/visibility;
// - refetch after local mutations (mark read, mark all, delete).

import { useCallback, useEffect, useRef, useState } from "react";
import {
  deleteAlert,
  getAlerts,
  markAlertsRead,
  markAllAlertsRead,
} from "@/services/api";
import type { AlertItem } from "@/types";

const POLL_INTERVAL_MS = 15_000;

export interface NotificationsSnapshot {
  items: AlertItem[];
  unreadCount: number;
}

export interface UseNotifications {
  alerts: AlertItem[];
  unreadCount: number;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  markRead: (alert: AlertItem) => Promise<void>;
  markAllRead: () => Promise<void>;
  remove: (alert: AlertItem) => Promise<void>;
}

/** Fetch the current notification state from the transport. */
async function fetchSnapshot(): Promise<NotificationsSnapshot> {
  const response = await getAlerts({ limit: 50 });
  return { items: response.items, unreadCount: response.unread_count };
}

export function useNotifications(): UseNotifications {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Monotonic guard so a slow poll response cannot clobber a newer
  // optimistic state applied after it started.
  const revision = useRef(0);

  const refresh = useCallback(async () => {
    const ticket = ++revision.current;
    try {
      const snapshot = await fetchSnapshot();
      if (revision.current === ticket) {
        setAlerts(snapshot.items);
        setUnreadCount(snapshot.unreadCount);
        setError(null);
      }
    } catch {
      if (revision.current === ticket) {
        setError("Could not load notifications.");
      }
    } finally {
      if (revision.current === ticket) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh();
    }, POLL_INTERVAL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [refresh]);

  const markRead = useCallback(async (alert: AlertItem) => {
    if (!alert.unread) return;
    revision.current += 1;
    setAlerts((prev) =>
      prev.map((a) => (a.id === alert.id ? { ...a, unread: false } : a)),
    );
    setUnreadCount((n) => Math.max(0, n - 1));
    try {
      await markAlertsRead([alert.id]);
    } catch {
      void refresh();
    }
  }, [refresh]);

  const markAllRead = useCallback(async () => {
    revision.current += 1;
    setAlerts((prev) => prev.map((a) => ({ ...a, unread: false })));
    setUnreadCount(0);
    try {
      await markAllAlertsRead();
    } catch {
      void refresh();
    }
  }, [refresh]);

  const remove = useCallback(async (alert: AlertItem) => {
    const wasUnread = alert.unread;
    revision.current += 1;
    setAlerts((prev) => prev.filter((a) => a.id !== alert.id));
    if (wasUnread) setUnreadCount((n) => Math.max(0, n - 1));
    try {
      await deleteAlert(alert.id);
    } catch {
      void refresh();
    }
  }, [refresh]);

  return { alerts, unreadCount, loading, error, refresh, markRead, markAllRead, remove };
}
