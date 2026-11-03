"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

const THEME_STORAGE_KEY = "aion-theme";

/** User-facing preference: light, dark, or follow the OS. */
export type Theme = "light" | "dark" | "system";
/** The concrete theme actually painted on <html data-theme>. */
export type ResolvedTheme = "light" | "dark";

interface ThemeContextValue {
  /** The stored preference (may be "system"). */
  theme: Theme;
  /** The concrete theme currently applied to the DOM. */
  resolvedTheme: ResolvedTheme;
  setTheme: (theme: Theme) => void;
  /** Flip between light and dark based on what is painted right now. */
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function systemPreference(): ResolvedTheme {
  if (typeof window === "undefined" || !window.matchMedia) return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function readStoredTheme(): Theme {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "light" || stored === "dark" || stored === "system") {
      return stored;
    }
  } catch {
    // Storage unavailable (private mode): fall back to system preference.
  }
  return "system";
}

function resolve(theme: Theme): ResolvedTheme {
  return theme === "system" ? systemPreference() : theme;
}

function applyToDom(resolved: ResolvedTheme) {
  document.documentElement.dataset.theme = resolved;
  // Keep the native color-scheme in sync so scrollbars/form controls match.
  document.documentElement.style.colorScheme = resolved;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("system");
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>("light");

  // Hydrate from what the no-flash script already painted + stored preference.
  useEffect(() => {
    const stored = readStoredTheme();
    const resolved = resolve(stored);
    setThemeState(stored);
    setResolvedTheme(resolved);
    applyToDom(resolved);
  }, []);

  // When following the system, react to live OS theme changes.
  useEffect(() => {
    if (theme !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      const resolved = resolve("system");
      setResolvedTheme(resolved);
      applyToDom(resolved);
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    const resolved = resolve(next);
    setThemeState(next);
    setResolvedTheme(resolved);
    applyToDom(resolved);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // Appearance still changes for this session even if storage fails.
    }
  }, []);

  const toggleTheme = useCallback(() => {
    // Read what is actually painted, not possibly-stale state. After a reload
    // the no-flash script sets data-theme before React hydrates, so the state
    // can lag — toggling off the DOM never flips to the wrong theme.
    const current: ResolvedTheme =
      typeof document !== "undefined" &&
      document.documentElement.dataset.theme === "dark"
        ? "dark"
        : "light";
    setTheme(current === "dark" ? "light" : "dark");
  }, [setTheme]);

  const value = useMemo<ThemeContextValue>(
    () => ({ theme, resolvedTheme, setTheme, toggleTheme }),
    [theme, resolvedTheme, setTheme, toggleTheme],
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return context;
}
