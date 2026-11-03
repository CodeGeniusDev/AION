"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";

/**
 * Phase 1E: the single link between the header search box and the page the
 * user is standing on. The header writes its query and scope here; list
 * views read it through usePageSearch() and filter their own rows live when
 * the scope is "This page". No fetching happens in the provider — pages
 * always filter the real data they already loaded.
 */

export type SearchScope = "all" | "page";

interface PageSearchValue {
  scope: SearchScope;
  setScope: (scope: SearchScope) => void;
  /** Raw query from the header search input (always current, not debounced). */
  query: string;
  setQuery: (query: string) => void;
  /** True when "This page" is active and a filter query is typed. */
  active: boolean;
  matches: (...values: string[]) => boolean;
  /** Case-insensitive filter for any list of items. */
  filterItems: <T>(
    items: T[],
    textOf: (item: T) => string[],
  ) => T[];
}

const PageSearchContext = createContext<PageSearchValue | null>(null);

export function PageSearchProvider({ children }: { children: React.ReactNode }) {
  const [scope, setScope] = useState<SearchScope>("all");
  const [query, setQuery] = useState("");

  const needle = query.trim().toLowerCase();
  const active = scope === "page" && needle.length > 0;

  const matches = useCallback(
    (...values: string[]) =>
      !active ||
      values.some((value) => value.toLowerCase().includes(needle)),
    [active, needle],
  );

  const filterItems = useCallback(
    <T,>(items: T[], textOf: (item: T) => string[]): T[] =>
      active ? items.filter((item) => matches(...textOf(item))) : items,
    [active, matches],
  );

  const value = useMemo(
    () => ({
      scope,
      setScope,
      query,
      setQuery,
      active,
      matches,
      filterItems,
    }),
    [scope, query, active, matches, filterItems],
  );

  return (
    <PageSearchContext.Provider value={value}>{children}</PageSearchContext.Provider>
  );
}

/** List views call this to honour the header's "This page" scope. */
export function usePageSearch(): PageSearchValue {
  const context = useContext(PageSearchContext);
  if (!context) {
    throw new Error("usePageSearch must be used inside PageSearchProvider");
  }
  return context;
}
