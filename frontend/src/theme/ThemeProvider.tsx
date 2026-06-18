/**
 * Lecture theme provider — light (default) / dark, persisted across sessions.
 *
 * Scope: the toggle themes the LECTURE VIEWER (its chrome + the teaching board
 * via a render-time colour remap + `data-theme` CSS variables) and the
 * in-lecture account/feedback chips. The marketing landing page and chapter
 * picker are intentionally light-only and ignore this.
 *
 * The context + `useTheme` hook live in ./themeContext (this file exports only
 * the component).
 */

import { useCallback, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { ThemeContext, type Theme } from "./themeContext";

const STORAGE_KEY = "feynman.theme";

function readStored(): Theme {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "light" || v === "dark") return v;
  } catch {
    /* localStorage unavailable — fall through to the product default */
  }
  return "light";
}

function persist(t: Theme): void {
  try {
    localStorage.setItem(STORAGE_KEY, t);
  } catch {
    /* ignore */
  }
}

export function ThemeProvider({ children }: { readonly children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(readStored);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    persist(t);
  }, []);

  const toggle = useCallback(() => {
    setThemeState((prev) => {
      const next: Theme = prev === "light" ? "dark" : "light";
      persist(next);
      return next;
    });
  }, []);

  const value = useMemo(
    () => ({ theme, toggle, setTheme }),
    [theme, toggle, setTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
