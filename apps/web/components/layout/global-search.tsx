"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowRight,
  Bell,
  BrainCircuit,
  Bot,
  Clock,
  CornerDownLeft,
  ListTodo,
  MessageCircleMore,
  Moon,
  Network,
  Plus,
  Search as SearchIcon,
  ShieldCheck,
  X,
  type LucideIcon,
} from "lucide-react";
import { globalSearch } from "@/services/api";
import type { GlobalSearchResult } from "@/types";
import { FLAT_NAV, type NavItem } from "@/components/layout/nav";
import { usePageSearch } from "@/components/layout/page-search-provider";
import { useTheme } from "@/components/layout/theme-provider";
import { useDismiss } from "@/components/ui/dropdown";
import { cn } from "@/utils/cn";

/** One selectable row in the dropdown: a page, a quick action, or a real
 * result from GET /api/search. Everything here either navigates or runs a
 * real client action — nothing decorative is rendered. */
interface Row {
  key: string;
  label: string;
  sublabel?: string;
  snippet?: string;
  href?: string;
  icon: LucideIcon;
  onSelect?: () => void;
}

interface Category {
  name: string;
  label: string;
  items: Row[];
}

/** Backend group key → display label + icon (mirrors routes/search.py). */
const GROUP_META: Record<string, { label: string; icon: LucideIcon }> = {
  tasks: { label: "Tasks", icon: ListTodo },
  approvals: { label: "Approvals", icon: ShieldCheck },
  agents: { label: "Agents", icon: Bot },
  workflows: { label: "Workflows", icon: Network },
  memory: { label: "Memory", icon: BrainCircuit },
  conversations: { label: "Conversations", icon: MessageCircleMore },
  alerts: { label: "Alerts", icon: Bell },
  schedules: { label: "Schedules", icon: Clock },
};

const RECENT_KEY = "aion-recent-searches";
const DEBOUNCE_MS = 200;

function matches(text: string, query: string) {
  return text.toLowerCase().includes(query.toLowerCase());
}

function getPageResults(term: string): Row[] {
  if (!term) return [];
  return FLAT_NAV.filter((nav: NavItem) => matches(nav.label, term))
    .slice(0, 8)
    .map((nav) => ({
      key: `page-${nav.href}`,
      label: nav.label,
      sublabel: nav.href,
      href: nav.href,
      icon: nav.icon,
    }));
}

/** Wrap every case-insensitive occurrence of the query in the text. */
function highlight(text: string, needle: string) {
  if (!needle) return text;
  const lower = text.toLowerCase();
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  let index = lower.indexOf(needle);
  while (index >= 0) {
    if (index > cursor) parts.push(text.slice(cursor, index));
    parts.push(
      <mark
        key={`${index}-${parts.length}`}
        className="rounded-sm bg-soft-blue px-0.5 font-semibold text-foreground">
        {text.slice(index, index + needle.length)}
      </mark>,
    );
    cursor = index + needle.length;
    index = lower.indexOf(needle, cursor);
  }
  parts.push(text.slice(cursor));
  return parts;
}

export function GlobalSearch({ className }: { className?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const { toggleTheme } = useTheme();
  const { scope, setScope, setQuery: setPageQuery } = usePageSearch();
  const inputRef = useRef<HTMLInputElement>(null);
  const activeItemRef = useRef<HTMLButtonElement | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const [open, setOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [recent, setRecent] = useState<string[]>([]);

  const containerRef = useDismiss<HTMLDivElement>(open, () => setOpen(false));

  // Cmd/Ctrl+K focuses the field from any page; "/" does too while the user
  // is not already typing somewhere. Below sm the field lives in the
  // overlay, so the shortcuts open it first.
  useEffect(() => {
    const enterOverlay = () => {
      if (window.matchMedia("(max-width: 639px)").matches) setMobileOpen(true);
    };
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        enterOverlay();
        requestAnimationFrame(() => {
          inputRef.current?.focus();
          inputRef.current?.select();
        });
        setOpen(true);
      } else if (event.key === "/" && !typing && !event.metaKey && !event.ctrlKey) {
        event.preventDefault();
        enterOverlay();
        requestAnimationFrame(() => inputRef.current?.focus());
        setOpen(true);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // The header owns the query; pages read it through the provider and can
  // filter their own lists live when the scope is "This page".
  useEffect(() => {
    setPageQuery(query);
  }, [query, setPageQuery]);

  // Recent searches persist locally and are clearable.
  useEffect(() => {
    try {
      const stored = localStorage.getItem(RECENT_KEY);
      if (stored) {
        const parsed: unknown = JSON.parse(stored);
        if (Array.isArray(parsed)) {
          setRecent(parsed.filter((item): item is string => typeof item === "string").slice(0, 8));
        }
      }
    } catch {
      // Corrupt storage is ignored — it is only a convenience list.
    }
  }, []);

  function rememberSearch(term: string) {
    if (!term) return;
    setRecent((current) => {
      const next = [term, ...current.filter((item) => item !== term)].slice(0, 8);
      try {
        localStorage.setItem(RECENT_KEY, JSON.stringify(next));
      } catch {
        // Storage failures (private mode) must not break navigation.
      }
      return next;
    });
  }

  // Debounce typing to one request per pause, cancelling any stale one.
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query.trim()), DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [query]);

  const quickActions = useCallback(
    (term: string): Row[] => {
      const actions: Row[] = [
        {
          key: "action-new-chat",
          label: "New conversation",
          sublabel: "/chat",
          href: "/chat?c=new",
          icon: MessageCircleMore,
        },
        {
          key: "action-new-workflow",
          label: "New workflow",
          sublabel: "/workflows",
          href: "/workflows?new=1",
          icon: Plus,
        },
        {
          key: "action-toggle-theme",
          label: "Toggle theme",
          sublabel: "Switches between light and dark",
          icon: Moon,
          onSelect: toggleTheme,
        },
      ];
      return term ? actions.filter((a) => matches(a.label, term)) : actions;
    },
    [toggleTheme],
  );

  const runSearch = useCallback(
    async (term: string) => {
      // Cancel whatever the previous keystroke left in flight.
      controllerRef.current?.abort();
      setError(null);

      const pageRows = getPageResults(term);
      const actionRows = quickActions(term);
      const local: Category[] = [];
      if (pageRows.length > 0) {
        local.push({ name: "Pages", label: "Pages", items: pageRows });
      }
      if (actionRows.length > 0) {
        local.push({ name: "Quick actions", label: "Quick actions", items: actionRows });
      }

      // "This page" scope: the pages below the shell do the filtering, so no
      // global fetch is issued.
      if (scope === "page" || term.length < 2) {
        setCategories(local);
        setLoading(false);
        return;
      }

      const controller = new AbortController();
      controllerRef.current = controller;
      setLoading(true);
      try {
        const response = await globalSearch(term, { signal: controller.signal });
        if (controller.signal.aborted) return;
        const apiCategories: Category[] = Object.entries(response.groups).map(
          ([key, results]) => ({
            name: key,
            label: GROUP_META[key]?.label ?? key,
            items: results.map((result: GlobalSearchResult) => ({
              key: `${key}-${result.id}`,
              label: result.title,
              sublabel: result.subtitle || undefined,
              snippet: result.snippet || undefined,
              href: result.href,
              icon: GROUP_META[key]?.icon ?? ArrowRight,
            })),
          }),
        );
        setCategories([...local, ...apiCategories]);
      } catch (err) {
        if (controller.signal.aborted || (err as Error)?.name === "AbortError") return;
        setCategories(local);
        setError("Search is unavailable — the AION API is not reachable.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    },
    [scope, quickActions],
  );

  useEffect(() => {
    if (!open) return;
    void runSearch(debounced);
  }, [debounced, open, runSearch]);

  useEffect(
    () => () => {
      controllerRef.current?.abort();
    },
    [],
  );

  // Flattened order drives keyboard navigation across all categories.
  const flat = useMemo(
    () =>
      categories.flatMap((c) =>
        c.items.map((item) => ({ ...item, category: c.name })),
      ),
    [categories],
  );

  useEffect(() => {
    setActiveIndex(0);
  }, [debounced, scope]);

  // Keep the focused keyboard selection visible within scrollable results.
  useEffect(() => {
    if (open && activeItemRef.current) {
      activeItemRef.current.scrollIntoView({ block: "nearest" });
    }
  }, [activeIndex, open]);

  // Mobile overlay: opening it must focus the field.
  useEffect(() => {
    if (mobileOpen) inputRef.current?.focus();
  }, [mobileOpen]);

  function close() {
    setOpen(false);
    setMobileOpen(false);
  }

  function navigate(result: Row) {
    if (result.href) {
      rememberSearch(debounced);
      close();
      setQuery("");
      router.push(result.href);
    } else if (result.onSelect) {
      close();
      result.onSelect();
    }
  }

  function onInputKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((i) => (flat.length ? (i + 1) % flat.length : 0));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((i) =>
        flat.length ? (i - 1 + flat.length) % flat.length : 0,
      );
    } else if (event.key === "Enter") {
      event.preventDefault();
      const active = flat[activeIndex];
      if (active) navigate(active);
    } else if (event.key === "Escape") {
      event.preventDefault();
      close();
      inputRef.current?.blur();
    }
  }

  const needle = debounced.toLowerCase();

  // Render items grouped, tracking a running flat index for the active row.
  let runningIndex = -1;

  const resultsPanel = (
    <>
      {loading && flat.length === 0 ? (
        <div className="space-y-2 p-2" aria-hidden="true">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-9 animate-pulse rounded-xl bg-muted" />
          ))}
        </div>
      ) : flat.length === 0 ? (
        error ? (
          <div className="flex items-start gap-3 p-4 text-sm text-muted-text">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
            <span>{error}</span>
          </div>
        ) : query ? (
          <div className="p-6 text-center text-sm text-muted-text">
            No results for &quot;{debounced}&quot;. Try a different term.
          </div>
        ) : null
      ) : (
        <>
          {categories.map((category) => (
            <div key={category.name} className="mb-1 last:mb-0">
              <p className="px-3 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-text">
                {category.label}
              </p>
              <ul>
                {category.items.map((item) => {
                  runningIndex += 1;
                  const isActive = runningIndex === activeIndex;
                  return (
                    <li key={item.key}>
                      <button
                        ref={isActive ? activeItemRef : undefined}
                        type="button"
                        role="option"
                        aria-selected={isActive}
                        onMouseEnter={() =>
                          setActiveIndex(
                            flat.findIndex((f) => f.key === item.key),
                          )
                        }
                        onClick={() => navigate(item)}
                        className={cn(
                          "flex w-full items-start gap-3 rounded-xl px-3 py-2 text-left text-sm",
                          isActive
                            ? "bg-muted text-foreground"
                            : "hover:bg-muted",
                        )}>
                        <item.icon className="mt-0.5 size-4 shrink-0 text-primary" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate">
                            {highlight(item.label, needle)}
                          </span>
                          {item.sublabel ? (
                            <span className="block truncate text-xs text-muted-text">
                              {item.sublabel}
                            </span>
                          ) : null}
                          {item.snippet ? (
                            <span className="mt-0.5 block truncate text-xs text-muted-text">
                              {highlight(item.snippet, needle)}
                            </span>
                          ) : null}
                        </span>
                        {isActive ? (
                          <CornerDownLeft className="mt-0.5 size-3.5 shrink-0 text-muted-text" />
                        ) : null}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
          {error ? (
            <div className="mt-1 flex items-start gap-2 border-t px-3 py-2 text-xs text-muted-text">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-destructive" />
              <span>{error}</span>
            </div>
          ) : null}
        </>
      )}
      {loading && flat.length > 0 ? (
        <p role="status" className="px-3 py-1 text-[10px] text-muted-text">
          Searching AION…
        </p>
      ) : null}
    </>
  );

  return (
    <>
      {/* Mobile: controls collapse to one icon that opens a full-width
          overlay search. */}
      {!mobileOpen && (
        <button
          type="button"
          onClick={() => {
            setMobileOpen(true);
            setOpen(true);
          }}
          aria-label="Open search"
          className="grid size-10 shrink-0 place-items-center rounded-full border bg-surface text-navy hover:bg-muted sm:hidden">
          <SearchIcon className="size-4" />
        </button>
      )}
      <div
        ref={containerRef}
        className={cn(
          "min-w-0",
          className,
          mobileOpen
            ? "fixed inset-0 z-[60] bg-background/95 p-4 backdrop-blur sm:absolute sm:inset-auto sm:bottom-auto sm:left-0 sm:right-0 sm:z-auto sm:bg-transparent sm:p-0 sm:backdrop-blur-none"
            : "relative hidden sm:block",
        )}>
        {mobileOpen && (
          <button
            type="button"
            onClick={() => {
              setMobileOpen(false);
              setOpen(false);
            }}
            aria-label="Close search"
            className="absolute right-4 top-[18px] z-10 grid size-8 place-items-center rounded-full text-muted-text hover:bg-muted sm:hidden">
            <X className="size-4" />
          </button>
        )}
        <div className="relative">
          <SearchIcon className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-muted-text" />
          <input
            ref={inputRef}
            type="search"
            role="combobox"
            aria-label="Search AION"
            aria-expanded={open}
            aria-controls="aion-search-results"
            aria-autocomplete="list"
            placeholder="Search tasks, agents, memory, pages…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setOpen(true)}
            onKeyDown={onInputKeyDown}
            className="h-11 w-full rounded-full border bg-surface pl-11 pr-16 text-sm text-foreground shadow-[0_2px_10px_rgba(25,36,56,0.035)] placeholder:text-muted-text"
          />
          {query ? (
            <button
              type="button"
              onClick={() => {
                setQuery("");
                inputRef.current?.focus();
              }}
              aria-label="Clear search"
              className="absolute right-14 top-1/2 grid size-7 -translate-y-1/2 place-items-center rounded-full text-muted-text hover:bg-muted hover:text-foreground">
              <X className="size-4" />
            </button>
          ) : null}
          <kbd className="pointer-events-none absolute right-3 top-1/2 hidden -translate-y-1/2 rounded-md border bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-text sm:block">
            ⌘K
          </kbd>
        </div>

        {open && (
          <div
            id="aion-search-results"
            role="listbox"
            aria-label="Search results"
            className={cn(
              "z-50 mt-2 max-h-[70vh] overflow-y-auto rounded-2xl border bg-surface p-2 text-foreground shadow-[0_18px_50px_rgba(15,25,45,0.22)] scrollbar-subtle",
              mobileOpen
                ? "fixed left-4 right-4 top-[84px] sm:absolute sm:left-0 sm:right-0 sm:top-full"
                : "absolute left-0 right-0 top-full",
            )}>
            {/* Scope chips: search everything, or filter this page live. */}
            <div
              className="mb-1 flex gap-1 rounded-full bg-muted p-1"
              role="group"
              aria-label="Search scope">
              {(
                [
                  { value: "all", label: "All" },
                  { value: "page", label: "This page" },
                ] as const
              ).map((chip) => (
                <button
                  key={chip.value}
                  type="button"
                  aria-pressed={scope === chip.value}
                  onClick={() => setScope(chip.value)}
                  className={cn(
                    "rounded-full px-3 py-1 text-[11px] font-medium",
                    scope === chip.value
                      ? "bg-surface shadow-sm"
                      : "text-muted-text",
                  )}>
                  {chip.label}
                </button>
              ))}
            </div>

            {scope === "page" ? (
              <p className="px-3 pb-1 text-[10px] text-muted-text">
                Filtering the {pathname} list as you type — pages keep showing
                their real data.
              </p>
            ) : null}

            {/* Recent searches only make sense with an empty field. */}
            {!query && recent.length > 0 && (
              <div className="mb-1 px-3 py-2">
                <div className="flex items-center justify-between">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-text">
                    Recent searches
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      setRecent([]);
                      try {
                        localStorage.removeItem(RECENT_KEY);
                      } catch {
                        // ignore
                      }
                    }}
                    className="text-[10px] font-medium text-primary hover:underline">
                    Clear
                  </button>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {recent.map((term) => (
                    <button
                      key={term}
                      type="button"
                      onClick={() => {
                        setQuery(term);
                        inputRef.current?.focus();
                      }}
                      className="rounded-full border bg-muted px-2.5 py-1 text-[11px] text-muted-text hover:text-foreground">
                      {term}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {resultsPanel}

            <div className="mt-1 flex items-center gap-3 border-t px-3 py-2 text-[10px] text-muted-text">
              <span>
                <kbd className="font-medium">↑↓</kbd> navigate
              </span>
              <span>
                <kbd className="font-medium">↵</kbd> open
              </span>
              <span>
                <kbd className="font-medium">esc</kbd> close
              </span>
              <span className="ml-auto">
                <kbd className="font-medium">/</kbd> to focus
              </span>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
