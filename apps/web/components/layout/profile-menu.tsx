"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Keyboard,
  Monitor,
  Moon,
  Settings,
  Sun,
  UserRound,
  X,
  AlertTriangle,
  ChevronDown,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";
import { getHealth, getPendingApprovals } from "@/services/api";
import { Dropdown } from "@/components/ui/dropdown";
import { useTheme, type Theme } from "@/components/layout/theme-provider";
import {
  AVATAR_CLASS,
  initialsFrom,
  useProfile,
} from "@/components/profile/profile-provider";
import { cn } from "@/utils/cn";

const THEMES: Array<{ value: Theme; label: string; icon: LucideIcon }> = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];

function ShortcutsDialog({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const shortcuts: Array<{ keys: string; action: string }> = [
    { keys: "⌘ / Ctrl + K", action: "Focus global search" },
    { keys: "↑ / ↓", action: "Navigate search results" },
    { keys: "↵", action: "Open selected result" },
    { keys: "Esc", action: "Close search or menu" },
  ];

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
      className="fixed inset-0 z-[60] grid place-items-center bg-navy/40 p-4"
      onClick={onClose}>
      <div
        className="w-full max-w-md rounded-3xl border bg-surface p-5 text-foreground shadow-2xl"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">Keyboard shortcuts</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close shortcuts"
            className="grid size-8 place-items-center rounded-full text-muted-text hover:bg-muted">
            <X className="size-4" />
          </button>
        </div>
        <ul className="mt-4 space-y-2">
          {shortcuts.map((s) => (
            <li
              key={s.keys}
              className="flex items-center justify-between text-sm">
              <span className="text-muted-text">{s.action}</span>
              <kbd className="rounded-md border bg-muted px-2 py-0.5 text-xs font-medium">
                {s.keys}
              </kbd>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

interface MenuItemProps {
  href?: string;
  icon: LucideIcon;
  label: string;
  onClick?: () => void;
}

function MenuItem({ href, icon: Icon, label, onClick }: MenuItemProps) {
  const content = (
    <>
      <Icon className="size-4 shrink-0 text-muted-text" />
      <span>{label}</span>
    </>
  );
  const className =
    "flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm hover:bg-muted";
  if (href) {
    return (
      <Link href={href} className={className} onClick={onClick}>
        {content}
      </Link>
    );
  }
  return (
    <button type="button" className={className} onClick={onClick}>
      {content}
    </button>
  );
}

export function ProfileMenu() {
  const { theme, setTheme } = useTheme();
  const { configured, profile } = useProfile();
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  // Real signals refreshed each time the menu opens; null until first load.
  const [pendingApprovals, setPendingApprovals] = useState<number | null>(null);
  const [appVersion, setAppVersion] = useState<string | null>(null);

  function refreshLiveMeta() {
    getPendingApprovals()
      .then((r) => setPendingApprovals(r.total))
      .catch(() => setPendingApprovals(null));
    getHealth()
      .then((h) => setAppVersion(h.version))
      .catch(() => setAppVersion(null));
  }

  function handleThemeChange(next: Theme) {
    // ThemeProvider owns persistence: localStorage + best-effort /api/settings.
    setTheme(next);
  }

  const displayName = configured && profile ? profile.display_name : "";
  const avatarClass = profile ? AVATAR_CLASS[profile.avatar_color] : "bg-navy";

  return (
    <>
      <Dropdown
        label="Account menu"
        className="shrink-0"
        panelClassName="w-64"
        trigger={({ open, toggle }) => (
          <button
            type="button"
            onClick={() => {
              if (!open) refreshLiveMeta();
              toggle();
            }}
            aria-label="Open user menu"
            aria-expanded={open}
            className={cn(
              "flex h-10 items-center gap-2 rounded-full border bg-surface p-1 pr-2 shadow-[0_2px_10px_rgba(25,36,56,0.035)] hover:bg-muted sm:h-11 sm:p-1.5 sm:pr-2.5",
              open && "bg-muted",
            )}>
            <span
              className={cn(
                "grid size-7 place-items-center rounded-full text-xs font-semibold text-white sm:size-8",
                avatarClass,
              )}>
              {displayName ? (
                initialsFrom(displayName)
              ) : (
                <UserRound className="size-4" />
              )}
            </span>
            <span className="hidden max-w-[8rem] truncate text-xs font-medium xl:block">
              {displayName || "Set up profile"}
            </span>
          </button>
        )}>
        {({ close }) => (
          <div className="p-2">
            <div className="flex items-center gap-3 border-b px-2 pb-3 pt-1">
              <span
                className={cn(
                  "grid size-9 place-items-center rounded-full text-sm font-semibold text-white",
                  avatarClass,
                )}>
                {displayName ? (
                  initialsFrom(displayName)
                ) : (
                  <UserRound className="size-4" />
                )}
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium">
                  {displayName || "Set up profile"}
                </span>
                <span className="block truncate text-xs text-muted-text">
                  {profile?.role ||
                    (profile?.username
                      ? `@${profile.username}`
                      : "Local workspace")}
                </span>
              </span>
              <ChevronDown className="ml-auto size-3 text-muted-text" />
            </div>

            <div className="space-y-0.5 py-2">
              <MenuItem
                href="/profile"
                icon={UserRound}
                label="Profile"
                onClick={close}
              />
              <MenuItem
                href="/settings"
                icon={Settings}
                label="Account settings"
                onClick={close}
              />
              <Link
                href="/desktop"
                onClick={close}
                className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm hover:bg-muted">
                <ShieldAlert className="size-4 shrink-0 text-muted-text" />
                <span>Desktop approvals</span>
                {pendingApprovals !== null && pendingApprovals > 0 ? (
                  <span className="ml-auto rounded-full bg-warning-soft px-2 py-0.5 text-[11px] font-semibold text-warning-text">
                    {pendingApprovals}
                  </span>
                ) : null}
              </Link>
              <MenuItem
                icon={Keyboard}
                label="Keyboard shortcuts"
                onClick={() => {
                  close();
                  setShortcutsOpen(true);
                }}
              />
            </div>

            <div className="border-t py-2">
              <p className="px-3 pb-2 pt-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-text">
                Theme
              </p>
              <div className="grid grid-cols-3 gap-1 px-1">
                {THEMES.map(({ value, label, icon: Icon }) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => handleThemeChange(value)}
                    aria-pressed={theme === value}
                    className={cn(
                      "flex flex-col items-center gap-1 rounded-xl border px-2 py-2 text-[11px] font-medium",
                      theme === value
                        ? "border-primary bg-soft-blue/40 text-foreground ring-1 ring-primary/30"
                        : "hover:bg-muted",
                    )}>
                    <Icon className="size-4" />
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div className="border-t py-2">
              <div className="flex items-center gap-3 px-3 py-2">
                <div className="flex size-6 items-center justify-center rounded-full bg-destructive/10">
                  <AlertTriangle className="size-3.5 text-destructive" />
                </div>
                <span className="text-xs text-muted-text">
                  Sign out is unavailable: AION runs as a single-tenant local
                  web UI without an auth backend.
                </span>
              </div>
            </div>

            {appVersion !== null ? (
              <p className="px-3 pb-1 text-center text-[10px] text-muted-text">
                AION v{appVersion}
              </p>
            ) : null}
          </div>
        )}
      </Dropdown>
      {shortcutsOpen ? (
        <ShortcutsDialog onClose={() => setShortcutsOpen(false)} />
      ) : null}
    </>
  );
}
