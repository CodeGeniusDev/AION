"use client";

import Link from "next/link";
import { Menu, Moon, Settings, Sun } from "lucide-react";
import { GlobalSearch } from "@/components/layout/global-search";
import { NotificationsPopover } from "@/components/layout/notifications-popover";
import { ProfileMenu } from "@/components/layout/profile-menu";
import { Tooltip } from "@/components/ui/tooltip";
import { useTheme } from "@/components/layout/theme-provider";

interface TopNavigationProps {
  onMenuOpen: () => void;
}

export function TopNavigation({ onMenuOpen }: TopNavigationProps) {
  const { resolvedTheme, toggleTheme } = useTheme();

  return (
    <header className="flex h-[76px] shrink-0 items-center gap-2 px-3 sm:gap-3 sm:px-4 lg:px-5">
      <button
        type="button"
        onClick={onMenuOpen}
        className="grid size-10 shrink-0 place-items-center rounded-full border bg-surface text-navy hover:bg-muted sm:size-11 lg:hidden"
        aria-label="Open navigation">
        <Menu className="size-5" />
      </button>
      <GlobalSearch className="min-w-0 flex-1 sm:max-w-[620px]" />
      <div className="ml-auto flex shrink-0 items-center gap-1.5 sm:gap-2">
        <Tooltip
          content={resolvedTheme === "dark" ? "Light mode" : "Dark mode"}>
          <button
            type="button"
            onClick={toggleTheme}
            aria-pressed={resolvedTheme === "dark"}
            aria-label="Toggle theme"
            className="grid size-10 place-items-center rounded-full border bg-surface text-navy shadow-[0_2px_10px_rgba(25,36,56,0.035)] hover:bg-muted sm:size-11">
            {resolvedTheme === "dark" ? (
              <Sun className="size-4 sm:size-[18px]" />
            ) : (
              <Moon className="size-4 sm:size-[18px]" />
            )}
          </button>
        </Tooltip>
        <NotificationsPopover />
        <Tooltip content="Settings">
          <Link
            href="/settings"
            aria-label="Settings"
            className="hidden size-11 place-items-center rounded-full border bg-surface text-navy shadow-[0_2px_10px_rgba(25,36,56,0.035)] hover:bg-muted md:grid">
            <Settings className="size-[18px]" />
          </Link>
        </Tooltip>
        <ProfileMenu />
      </div>
    </header>
  );
}
