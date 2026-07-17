"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

const SIDEBAR_STORAGE_KEY = "aion-sidebar-collapsed";

interface SidebarStateContextValue {
  collapsed: boolean;
  toggleCollapsed: () => void;
}

const SidebarStateContext = createContext<SidebarStateContextValue | null>(null);

export function SidebarStateProvider({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    try {
      const savedState = window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === "true";
      setCollapsed(savedState);
      document.documentElement.dataset.sidebarCollapsed = String(savedState);
    } catch {
      document.documentElement.dataset.sidebarCollapsed = "false";
    }
  }, []);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((currentState) => {
      const nextState = !currentState;

      document.documentElement.dataset.sidebarCollapsed = String(nextState);
      try {
        window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(nextState));
      } catch {
        // The sidebar still works when storage is unavailable.
      }

      return nextState;
    });
  }, []);

  return (
    <SidebarStateContext.Provider value={{ collapsed, toggleCollapsed }}>
      {children}
    </SidebarStateContext.Provider>
  );
}

export function useSidebarState() {
  const context = useContext(SidebarStateContext);

  if (!context) {
    throw new Error("useSidebarState must be used within SidebarStateProvider");
  }

  return context;
}
