"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  Bot,
  BrainCircuit,
  ChevronLeft,
  CircleHelp,
  FlaskConical,
  LayoutDashboard,
  ListTodo,
  MemoryStick,
  MessageCircleMore,
  Network,
  Plus,
  Settings,
  X,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/utils/cn";

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
}

const groups: Array<{ label: string; items: NavItem[] }> = [
  { label: "Overview", items: [
    { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
    { label: "AI Chat", href: "/chat", icon: MessageCircleMore },
    { label: "Tasks", href: "/tasks", icon: ListTodo },
  ] },
  { label: "Intelligence", items: [
    { label: "Agents", href: "/agents", icon: Bot },
    { label: "Workflows", href: "/workflows", icon: Network },
    { label: "Memory", href: "/memory", icon: MemoryStick },
  ] },
  { label: "System", items: [
    { label: "Research", href: "/research", icon: FlaskConical },
    { label: "Settings", href: "/settings", icon: Settings },
  ] },
];

interface SidebarProps {
  collapsed: boolean;
  mobileOpen: boolean;
  onCollapse: () => void;
  onMobileClose: () => void;
}

export function Sidebar({ collapsed, mobileOpen, onCollapse, onMobileClose }: SidebarProps) {
  const pathname = usePathname();

  const renderContent = (isCollapsed: boolean) => (
    <>
      <div data-sidebar-header className={cn("flex h-[76px] items-center border-b border-[#d9e0e8]", isCollapsed ? "justify-center px-3" : "px-5")}>
        <Link href="/dashboard" className="flex min-w-0 items-center gap-3 rounded-full" aria-label="AION dashboard">
          <span className="grid size-10 shrink-0 place-items-center rounded-full bg-primary text-white shadow-[0_5px_14px_rgba(23,105,243,0.24)]">
            <BrainCircuit aria-hidden="true" className="size-5" />
          </span>
          {!isCollapsed && <span data-sidebar-expanded className="text-lg font-semibold tracking-[-0.03em]">AION</span>}
        </Link>
        <button
          type="button"
          onClick={onCollapse}
          data-sidebar-collapse-button
          className={cn("ml-auto hidden size-8 place-items-center rounded-full border bg-white text-muted-text hover:text-aion-text lg:grid", isCollapsed && "absolute left-[70px]")}
          aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <ChevronLeft data-sidebar-collapse-icon className={cn("size-4 transition-transform", isCollapsed && "rotate-180")} />
        </button>
        <button type="button" onClick={onMobileClose} className="ml-auto grid size-9 place-items-center rounded-full border bg-white lg:hidden" aria-label="Close navigation">
          <X className="size-4" />
        </button>
      </div>

      <div data-sidebar-body className={cn("flex-1 overflow-y-auto py-5 scrollbar-subtle", isCollapsed ? "px-3" : "px-4")}>
        <Link data-sidebar-item href="/tasks" onClick={onMobileClose} className={cn("mb-6 flex h-12 items-center rounded-full bg-primary text-sm font-medium text-white shadow-[0_7px_18px_rgba(23,105,243,0.2)] transition-colors hover:bg-[#0f5ce0]", isCollapsed ? "justify-center" : "gap-3 px-4")}>
          <Plus className="size-4" />
          {!isCollapsed && <span data-sidebar-expanded>New Task</span>}
        </Link>
        <nav aria-label="Primary navigation" className="space-y-6">
          {groups.map((group) => (
            <div key={group.label}>
              {!isCollapsed && <p data-sidebar-expanded className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-[#9299a4]">{group.label}</p>}
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
                        active ? "border-[#d7dee7] bg-[#f8fafc] text-aion-text shadow-[0_2px_7px_rgba(25,36,56,0.04)]" : "text-[#666d78] hover:bg-white/70 hover:text-aion-text",
                      )}
                    >
                      <Icon className="size-[17px] shrink-0" strokeWidth={1.8} />
                      {!isCollapsed && <span data-sidebar-expanded>{item.label}</span>}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
      </div>

      <div data-sidebar-footer className={cn("border-t border-[#d9e0e8]", isCollapsed ? "p-3" : "p-4")}>
        <div data-sidebar-collapsed-only className={cn("place-items-center rounded-2xl bg-white py-3", isCollapsed ? "grid" : "hidden")} title="System Online">
          <span className="size-2.5 rounded-full bg-[#35b978] shadow-[0_0_0_4px_rgba(53,185,120,0.12)]" />
        </div>
        <div data-sidebar-expanded className={cn("rounded-[20px] border bg-white p-4 shadow-[0_4px_14px_rgba(25,36,56,0.04)]", isCollapsed && "hidden")}>
          <div className="flex items-center gap-2 text-xs font-semibold">
            <span className="size-2 rounded-full bg-[#35b978]" />
            System Online
            <Activity className="ml-auto size-3.5 text-primary" />
          </div>
          <div className="mt-4 flex items-center justify-between text-[10px] text-muted-text"><span>System usage</span><span>68%</span></div>
          <progress className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full accent-primary" value="68" max="100">68%</progress>
          <div className="mt-3 flex items-center justify-between text-[10px]"><span className="text-muted-text">Current model</span><span className="font-medium">Gemini 2.5</span></div>
          <Link href="/settings" className="mt-3 flex h-8 items-center justify-center gap-2 rounded-full bg-navy text-[10px] font-medium text-white hover:bg-[#25334b]">
            <CircleHelp className="size-3.5" /> System details
          </Link>
        </div>
      </div>
    </>
  );

  return (
    <>
      <aside data-sidebar-desktop className={cn("relative hidden shrink-0 flex-col bg-sidebar transition-[width] duration-200 lg:flex", collapsed ? "w-[88px]" : "w-[252px]")}>{renderContent(collapsed)}</aside>
      {mobileOpen && <button type="button" className="fixed inset-0 z-40 bg-navy/35 lg:hidden" onClick={onMobileClose} aria-label="Close navigation overlay" />}
      <aside className={cn("fixed inset-y-0 left-0 z-50 flex w-[276px] flex-col bg-sidebar shadow-2xl transition-transform duration-200 lg:hidden", mobileOpen ? "translate-x-0" : "-translate-x-full")} aria-hidden={!mobileOpen}>{renderContent(false)}</aside>
    </>
  );
}
