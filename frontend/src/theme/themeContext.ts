/**
 * Lecture theme context + hook (split from ThemeProvider so the provider file
 * only exports a component — matches the authContext/AuthProvider split and
 * keeps react-refresh happy).
 *
 * Context default is "dark": components reading `useTheme()` outside a provider
 * (unit tests, the standalone preview server) get the board's original dark
 * rendering (identity colour remap) — zero change where the provider isn't
 * mounted. The PROVIDER defaults to "light" (the product default).
 */

import { createContext, useContext } from "react";

export type Theme = "light" | "dark";

export interface ThemeContextValue {
  readonly theme: Theme;
  readonly toggle: () => void;
  readonly setTheme: (t: Theme) => void;
}

export const ThemeContext = createContext<ThemeContextValue>({
  theme: "dark",
  toggle: () => {},
  setTheme: () => {},
});

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
