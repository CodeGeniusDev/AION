"use client";

import { useState } from "react";
import { Sidebar } from "./sidebar";
import { useSidebarState } from "./sidebar-state-provider";
import { TopNavigation } from "./top-navigation";

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const { collapsed, toggleCollapsed } = useSidebarState();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="min-h-screen overflow-x-hidden bg-background p-0 sm:p-4 lg:p-6">
      <div className="mx-auto flex min-h-screen max-w-[1680px] overflow-hidden bg-shell sm:min-h-[calc(100vh-2rem)] sm:rounded-[30px] sm:border sm:shadow-[0_10px_40px_rgba(25,36,56,0.08)] lg:min-h-[calc(100vh-3rem)]">
        <Sidebar
          collapsed={collapsed}
          mobileOpen={mobileOpen}
          onCollapse={toggleCollapsed}
          onMobileClose={() => setMobileOpen(false)}
        />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopNavigation onMenuOpen={() => setMobileOpen(true)} />
          <main className="min-w-0 flex-1 p-3 pt-0 sm:p-4 sm:pt-0 lg:p-5 lg:pt-0">
            <div className="min-h-full overflow-hidden rounded-[24px] border border-white bg-surface shadow-[0_3px_18px_rgba(25,36,56,0.04)] sm:rounded-[28px]">
              {children}
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
