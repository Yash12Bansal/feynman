/**
 * Design tokens for the visual rendering engine.
 *
 * Single source of truth — extracted from the Canvas renderer (renderer.ts).
 * All components use these values directly or via CSS custom properties
 * set on the scene viewport.
 */

export const COLORS = {
  background: "#0a0a0a",
  cardBg: "#141420",
  cardBorder: "#1e1e30",
  textPrimary: "#f0f0f0",
  textSecondary: "#9ca3af",
  accentBlue: "#60a5fa",
  accentAmber: "#fbbf24",
  accentGreen: "#4ade80",
  accentPurple: "#a78bfa",
  equationBg: "#1a1a2e",
  diagramBg: "#0f1a14",
  diagramBorder: "#1a3a28",
  graphBg: "#151020",
  graphBorder: "#1e1a35",
} as const;

export const LAYOUT = {
  marginX: 48,
  cardPadding: 32,
  cardGap: 20,
  cardRadius: 16,
  topMargin: 48,
  maxContentWidth: 1200,
} as const;

export const FONTS = {
  title: "'Inter', system-ui, -apple-system, sans-serif",
  body: "'Inter', system-ui, -apple-system, sans-serif",
  equation:
    "'JetBrains Mono', 'SF Mono', 'Fira Code', 'Cascadia Code', monospace",
} as const;

/** Accent color per instruction type. */
export const TYPE_ACCENT: Record<string, string> = {
  show_text: COLORS.accentBlue,
  show_equation: COLORS.accentAmber,
  step_equation: COLORS.accentAmber,
  draw_diagram: COLORS.accentGreen,
  show_graph: COLORS.accentPurple,
};

/** Inject theme as CSS custom properties on a DOM element. */
export function injectThemeVars(el: HTMLElement): void {
  const vars: Record<string, string> = {
    "--color-background": COLORS.background,
    "--color-card-bg": COLORS.cardBg,
    "--color-card-border": COLORS.cardBorder,
    "--color-text-primary": COLORS.textPrimary,
    "--color-text-secondary": COLORS.textSecondary,
    "--color-accent-blue": COLORS.accentBlue,
    "--color-accent-amber": COLORS.accentAmber,
    "--color-accent-green": COLORS.accentGreen,
    "--color-accent-purple": COLORS.accentPurple,
    "--color-equation-bg": COLORS.equationBg,
    "--color-diagram-bg": COLORS.diagramBg,
    "--color-diagram-border": COLORS.diagramBorder,
    "--color-graph-bg": COLORS.graphBg,
    "--color-graph-border": COLORS.graphBorder,
    "--layout-card-padding": `${LAYOUT.cardPadding}px`,
    "--layout-card-gap": `${LAYOUT.cardGap}px`,
    "--layout-card-radius": `${LAYOUT.cardRadius}px`,
    "--layout-max-width": `${LAYOUT.maxContentWidth}px`,
    "--layout-top-margin": `${LAYOUT.topMargin}px`,
  };

  for (const [key, value] of Object.entries(vars)) {
    el.style.setProperty(key, value);
  }
}
