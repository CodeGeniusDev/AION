"use client";

import { useState } from "react";
import { Bell, Menu, Moon, Search, Settings, Sun } from "lucide-react";
import { cn } from "@/utils/cn";

interface TopNavigationProps {
  onMenuOpen: () => void;
}

export function TopNavigation({ onMenuOpen }: TopNavigationProps) {
  const [dimmed, setDimmed] = useState(false);
  function toggleTheme() {
    setDimmed((value) => {
      const nextValue = !value;
      document.documentElement.dataset.theme = nextValue ? "dim" : "light";
      return nextValue;
    });
  }
  return (
    <header className="flex h-[76px] shrink-0 items-center gap-3 px-3 sm:px-4 lg:px-5">
      <button
        type="button"
        onClick={onMenuOpen}
        className="grid size-11 shrink-0 place-items-center rounded-full border bg-white text-navy lg:hidden"
        aria-label="Open navigation"
      >
        <Menu className="size-5" />
      </button>
      <label className="relative min-w-0 flex-1 sm:max-w-[620px]">
        <Search className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-[#8b919a]" />
        <span className="sr-only">Search AION</span>
        <input
          type="search"
          placeholder="Search tasks, agents or memory"
          className="h-11 w-full rounded-full border bg-white pl-11 pr-4 text-sm shadow-[0_2px_10px_rgba(25,36,56,0.035)] placeholder:text-[#9a9fa7]"
        />
      </label>
      <div className="ml-auto flex shrink-0 items-center gap-2">
        <button
          type="button"
          onClick={toggleTheme}
          aria-pressed={dimmed}
          className="hidden size-11 place-items-center rounded-full border bg-white text-navy shadow-[0_2px_10px_rgba(25,36,56,0.035)] hover:bg-[#f8fafc] sm:grid"
          aria-label="Toggle theme"
        >
          {dimmed ? (
            <Sun className="size-[18px]" />
          ) : (
            <Moon className="size-[18px]" />
          )}
        </button>
        <a
          href="alert"
          type="button"
          className="relative hidden size-11 place-items-center rounded-full border bg-white text-navy shadow-[0_2px_10px_rgba(25,36,56,0.035)] hover:bg-[#f8fafc] xs:grid sm:grid"
          aria-label="Notifications"
        >
          <Bell className="size-[18px]" />
          <span className="absolute right-2.5 top-2.5 size-1.5 rounded-full bg-primary" />
        </a>
        <a
          href="/settings"
          className="hidden size-11 place-items-center rounded-full border bg-white text-navy shadow-[0_2px_10px_rgba(25,36,56,0.035)] hover:bg-[#f8fafc] md:grid"
          aria-label="Settings"
        >
          <Settings className="size-[18px]" />
        </a>
        <button
          type="button"
          className={cn(
            "flex h-11 items-center gap-2 rounded-full border bg-white p-1.5 pr-2.5 shadow-[0_2px_10px_rgba(25,36,56,0.035)]",
            dimmed && "bg-[#f7f8fb]",
          )}
          aria-label="Open user menu"
        >
          <span className="grid size-8 place-items-center rounded-full bg-navy text-xs font-semibold text-white">
            AA
          </span>
          <span className="hidden text-xs font-medium xl:block">Abdullah</span>
        </button>
      </div>
    </header>
  );
}
