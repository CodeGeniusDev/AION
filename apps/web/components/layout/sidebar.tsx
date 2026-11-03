"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BrainCircuit,
  ChevronLeft,
  CircleHelp,
  Plus,
  Server,
  X,
} from "lucide-react";
import { getHealth } from "@/services/api";
import { NAV_GROUPS } from "@/components/layout/nav";
import { cn } from "@/utils/cn";

interface SidebarProps {
  collapsed: boolean;
  mobileOpen: boolean;
  onCollapse: () => void;
  onMobileClose: () => void;
}

export function Sidebar({
  collapsed,
  mobileOpen,
  onCollapse,
  onMobileClose,
}: SidebarProps) {
  const pathname = usePathname();
  const [modelName, setModelName] = useState("");
  const [systemStatus, setSystemStatus] = useState<
    "healthy" | "degraded" | "unhealthy" | "unknown"
  >("unknown");

  useEffect(() => {
    getHealth()
      .then((h) => {
        setModelName(h.model_name || "");
        setSystemStatus(h.status);
      })
      .catch(() => {
        setModelName("");
        setSystemStatus("unknown");
      });
  }, []);

  const statusLabel = {
    healthy: "System online",
    degraded: "System degraded",
    unhealthy: "System unhealthy",
    unknown: "Status unknown",
  }[systemStatus];
  const statusDot =
    systemStatus === "healthy"
      ? "bg-success-solid"
      : systemStatus === "unknown"
        ? "bg-neutral-solid"
        : "bg-warning-solid";

  const renderContent = (isCollapsed: boolean) => (
    <>
      <div
        data-sidebar-header
        className={cn(
          "flex h-[76px] items-center border-b border-border",
          isCollapsed ? "justify-center px-3" : "px-5",
        )}
      >
        <Link
          href="/dashboard"
          className="flex min-w-0 items-center gap-3 rounded-full"
          aria-label="AION dashboard"
        >
          <span className="grid size-10 shrink-0 place-items-center rounded-full bg-primary text-white shadow-[0_5px_14px_rgba(23,105,243,0.24)]">
            <BrainCircuit aria-hidden="true" className="size-5" />
          </span>
          {!isCollapsed && (
            <span
              data-sidebar-expanded
              className="text-lg font-semibold tracking-[-0.03em]"
            >
              AION
            </span>
          )}
        </Link>
        <button
          type="button"
          onClick={onCollapse}
          data-sidebar-collapse-button
          className={cn(
            "ml-auto hidden size-8 place-items-center rounded-full border bg-surface text-muted-text hover:text-foreground lg:grid",
            isCollapsed && "absolute left-[70px]",
          )}
          aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <ChevronLeft
            data-sidebar-collapse-icon
            className={cn(
              "size-4 transition-transform",
              isCollapsed && "rotate-180",
            )}
          />
        </button>
        <button
          type="button"
          onClick={onMobileClose}
          className="ml-auto grid size-9 place-items-center rounded-full border bg-surface lg:hidden"
          aria-label="Close navigation"
        >
          <X className="size-4" />
        </button>
      </div>

      <div
        data-sidebar-body
        className={cn(
          "flex-1 overflow-y-auto py-5 scrollbar-subtle",
          isCollapsed ? "px-3" : "px-4",
        )}
      >
        <Link
          data-sidebar-item
          href="/chat"
          onClick={onMobileClose}
          className={cn(
            "mb-6 flex h-12 items-center rounded-full bg-primary text-sm font-medium text-primary-foreground shadow-[0_7px_18px_rgba(23,105,243,0.2)] transition-colors hover:bg-primary-hover",
            isCollapsed ? "justify-center" : "gap-3 px-4",
          )}
        >
          <Plus className="size-4" />
          {!isCollapsed && <span data-sidebar-expanded>New Task</span>}
        </Link>
        <nav aria-label="Primary navigation" className="space-y-6">
          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              {!isCollapsed && (
                <p
                  data-sidebar-expanded
                  className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-text"
                >
                  {group.label}
                </p>
              )}
              <div className="space-y-1">
                {group.items.map((item) => {
                  const active = pathname === item.href;
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.href}
                      data-sidebar-item
                      href={item.href}
                      onClick={onMobileClose}
                      title={isCollapsed ? item.label : undefined}
                      className={cn(
                        "flex h-10 items-center rounded-full border border-transparent text-[13px] font-medium transition-colors",
                        isCollapsed ? "justify-center" : "gap-3 px-3",
                        active
                          ? "border-border bg-muted text-foreground shadow-[0_2px_7px_rgba(25,36,56,0.04)]"
                          : "text-muted-text hover:bg-muted hover:text-foreground",
                      )}
                    >
                      <Icon
                        className="size-[17px] shrink-0"
                        strokeWidth={1.8}
                      />
                      {!isCollapsed && (
                        <span data-sidebar-expanded>{item.label}</span>
                      )}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
          <hr />
        </nav>
      </div>

      <div
        data-sidebar-footer
        className={cn("border-t border-border", isCollapsed ? "p-3" : "p-4")}
      >
        <div
          data-sidebar-collapsed-only
          className={cn(
            "place-items-center rounded-2xl bg-surface py-3",
            isCollapsed ? "grid" : "hidden",
          )}
          title={statusLabel}
        >
          <span
            className={cn(
              "size-2.5 rounded-full shadow-[0_0_0_4px_rgba(53,185,120,0.12)]",
              statusDot,
            )}
          />
        </div>
        <div
          data-sidebar-expanded
          className={cn(
            "rounded-[20px] border bg-surface p-4 shadow-[0_4px_14px_rgba(25,36,56,0.04)]",
            isCollapsed && "hidden",
          )}
        >
          <div className="flex items-center gap-2 text-xs font-semibold">
            <span className={cn("size-2 rounded-full", statusDot)} />
            {statusLabel}
            <Server className="ml-auto size-3.5 text-primary" />
          </div>
          <div className="mt-3 flex items-center justify-between text-[10px]">
            <span className="text-muted-text">Current model</span>
            <span className="font-medium">{modelName || "—"}</span>
          </div>
          <Link
            href="/settings"
            className="mt-3 flex h-8 items-center justify-center gap-2 rounded-full bg-navy text-[10px] font-medium text-white hover:opacity-90"
          >
            <CircleHelp className="size-3.5" /> System details
          </Link>
        </div>
      </div>
    </>
  );

  return (
    <>
      <aside
        data-sidebar-desktop
        className={cn(
          "relative hidden shrink-0 flex-col bg-sidebar transition-[width] duration-200 lg:flex",
          collapsed ? "w-[88px]" : "w-[252px]",
        )}
      >
        {renderContent(collapsed)}
      </aside>
      {mobileOpen && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-navy/35 lg:hidden"
          onClick={onMobileClose}
          aria-label="Close navigation overlay"
        />
      )}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-[276px] flex-col bg-sidebar shadow-2xl transition-transform duration-200 lg:hidden",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
        aria-hidden={!mobileOpen}
      >
        {renderContent(false)}
      </aside>
    </>
  );
}
