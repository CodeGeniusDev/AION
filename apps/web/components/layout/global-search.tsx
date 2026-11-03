"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Search as SearchIcon,
  X,
  ListTodo,
  Bot,
  BrainCircuit,
  MessageCircleMore,
  Network,
  FileText,
  CornerDownLeft,
  AlertTriangle,
  Users,
  Clock,
  MoreHorizontal,
  type LucideIcon,
} from "lucide-react";
import {
  getTasks,
  getAgents,
  searchMemoryRecords,
  getConversations,
  getWorkflows,
} from "@/services/api";
import { FLAT_NAV, type NavItem } from "@/components/layout/nav";
import { useDismiss } from "@/components/ui/dropdown";
import { cn } from "@/utils/cn";

export interface SearchResult {
  key: string;
  label: string;
  sublabel?: string;
  href: string;
  icon: LucideIcon;
}

interface Category {
  name: string;
  label: string;
  items: SearchResult[];
}

const RESULT_ICON: Record<string, LucideIcon> = {
  Tasks: ListTodo,
  Agents: Bot,
  Memories: BrainCircuit,
  Conversations: MessageCircleMore,
  Workflows: Network,
  Files: FileText,
  People: Users,
  Recent: Clock,
  More: MoreHorizontal,
};

function matches(text: string, query: string) {
  return text.toLowerCase().includes(query.toLowerCase());
}

function getPageResults(term: string): SearchResult[] {
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

export function GlobalSearch({ className }: { className?: string }) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const activeItemRef = useRef<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);

  const containerRef = useDismiss<HTMLDivElement>(open, () => setOpen(false));

  // Cmd/Ctrl+K focuses the field from any page and opens the panel.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
        setOpen(true);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // Debounce typing to avoid a request per keystroke.
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query.trim()), 150);
    return () => window.clearTimeout(timer);
  }, [query]);

  const runSearch = useCallback(async (term: string) => {
    if (!term) {
      setCategories([
        { name: "Pages", label: "Pages", items: getPageResults(term) },
      ]);
      setError(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    const settled = await Promise.allSettled([
      getTasks(),
      getAgents(),
      searchMemoryRecords(term, { limit: 6 }),
      getConversations(),
      getWorkflows(),
    ]);

    const cats: Category[] = [];

    // Tasks
    if (settled[0].status === "fulfilled") {
      const items = (
        settled[0] as PromiseFulfilledResult<{
          items: { title: string; agent: string }[];
        }>
      ).value.items
        .filter((t) => matches(t.title, term) || matches(t.agent, term))
        .slice(0, 5)
        .map((t) => ({
          key: `task-${t.title}`,
          label: t.title,
          sublabel: "task",
          href: "/tasks",
          icon: RESULT_ICON.Tasks,
        }));
      if (items.length > 0) {
        cats.push({ name: "Tasks", label: "Tasks", items });
      }
    }

    // Agents
    if (settled[1].status === "fulfilled") {
      const items = (
        settled[1] as PromiseFulfilledResult<{
          items: { name: string; specialty: string }[];
        }>
      ).value.items
        .filter((a) => matches(a.name, term) || matches(a.specialty, term))
        .slice(0, 5)
        .map((a) => ({
          key: `agent-${a.name}`,
          label: a.name,
          sublabel: a.specialty,
          href: "/agents",
          icon: RESULT_ICON.Agents,
        }));
      if (items.length > 0) {
        cats.push({ name: "Agents", label: "Agents", items });
      }
    }

    // Memories
    if (settled[2].status === "fulfilled") {
      const items = (
        settled[2] as PromiseFulfilledResult<{
          items: { content: string; type: string }[];
        }>
      ).value.items
        .slice(0, 5)
        .map((m) => ({
          key: `memory-${m.content.slice(0, 40)}`,
          label:
            m.content.length > 40 ? `${m.content.slice(0, 40)}…` : m.content,
          sublabel: m.type.replace("_", " "),
          href: "/memory",
          icon: RESULT_ICON.Memories,
        }));
      if (items.length > 0) {
        cats.push({ name: "Memories", label: "Memories", items });
      }
    }

    // Conversations
    if (settled[3].status === "fulfilled") {
      const items = (
        settled[3] as PromiseFulfilledResult<
          { title: string; message_count: number }[]
        >
      ).value
        .filter((c) => matches(c.title, term))
        .slice(0, 5)
        .map((c) => ({
          key: `convo-${c.title}`,
          label: c.title,
          sublabel: `${c.message_count} messages`,
          href: "/chat",
          icon: RESULT_ICON.Conversations,
        }));
      if (items.length > 0) {
        cats.push({ name: "Conversations", label: "Conversations", items });
      }
    }

    // Workflows
    if (settled[4].status === "fulfilled") {
      const items = (
        settled[4] as PromiseFulfilledResult<{
          items: { name: string; description: string }[];
        }>
      ).value.items
        .filter((w) => matches(w.name, term) || matches(w.description, term))
        .slice(0, 5)
        .map((w) => ({
          key: `workflow-${w.name}`,
          label: w.name,
          sublabel: w.description,
          href: "/workflows",
          icon: RESULT_ICON.Workflows,
        }));
      if (items.length > 0) {
        cats.push({ name: "Workflows", label: "Workflows", items });
      }
    }

    // Pages are always present (local, no API call).
    const pageItems = getPageResults(term);
    if (pageItems.length > 0) {
      cats.unshift({ name: "Pages", label: "Pages", items: pageItems });
    }

    // If every network source failed, surface an honest error state.
    const allFailed = [
      settled[0],
      settled[1],
      settled[2],
      settled[3],
      settled[4],
    ].every((r) => r.status === "rejected");
    if (allFailed) {
      setError("Search is unavailable — the AION API is not reachable.");
    }

    setCategories(cats);
    setLoading(false);
  }, []);

  useEffect(() => {
    if (!open) return;
    void runSearch(debounced);
  }, [debounced, open, runSearch]);

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
  }, [debounced]);

  // Keep the focused keyboard selection visible within scrollable results.
  useEffect(() => {
    if (open && activeItemRef.current) {
      activeItemRef.current.scrollIntoView({ block: "nearest" });
    }
  }, [activeIndex, open]);

  function navigate(result: SearchResult) {
    setOpen(false);
    setQuery("");
    router.push(result.href);
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
      setOpen(false);
      inputRef.current?.blur();
    }
  }

  // Render items grouped, tracking a running flat index for the active row.
  let runningIndex = -1;

  return (
    <div ref={containerRef} className={cn("relative min-w-0", className)}>
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
          className="absolute left-0 right-0 top-full z-50 mt-2 max-h-[70vh] overflow-y-auto rounded-2xl border bg-surface p-2 text-foreground shadow-[0_18px_50px_rgba(15,25,45,0.22)] scrollbar-subtle">
          {loading && flat.length === 0 ? (
            <div className="space-y-2 p-2" aria-hidden="true">
              {Array.from({ length: 4 }).map((_, i) => (
                <div
                  key={i}
                  className="h-9 animate-pulse rounded-xl bg-muted"
                />
              ))}
            </div>
          ) : flat.length === 0 ? (
            error ? (
              <div className="flex items-start gap-3 p-4 text-sm text-muted-text">
                <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
                <span>{error}</span>
              </div>
            ) : (
              <div className="p-6 text-center text-sm text-muted-text">
                No matches for &quot;{debounced}&quot;. Try a different term.
              </div>
            )
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
                              "flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm",
                              isActive
                                ? "bg-muted text-foreground"
                                : "hover:bg-muted",
                            )}>
                            <item.icon className="size-4 shrink-0 text-primary" />
                            <span className="min-w-0 flex-1">
                              <span className="block truncate">
                                {item.label}
                              </span>
                              {item.sublabel ? (
                                <span className="block truncate text-xs text-muted-text">
                                  {item.sublabel}
                                </span>
                              ) : null}
                            </span>
                            {isActive ? (
                              <CornerDownLeft className="size-3.5 shrink-0 text-muted-text" />
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
          </div>
        </div>
      )}
    </div>
  );
}
