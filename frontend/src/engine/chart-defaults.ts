/**
 * Chart.js global configuration for the classroom display.
 *
 * Side-effect module — import once at the app entry point.
 * Registers only the components we use (tree-shaking) and sets
 * global defaults for the dark classroom theme.
 */

import {
  Chart,
  LineController,
  BarController,
  ScatterController,
  LineElement,
  BarElement,
  PointElement,
  LinearScale,
  CategoryScale,
  Title,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";
import { COLORS } from "./theme";

Chart.register(
  LineController,
  BarController,
  ScatterController,
  LineElement,
  BarElement,
  PointElement,
  LinearScale,
  CategoryScale,
  Title,
  Tooltip,
  Legend,
  Filler,
);

// ── Global defaults ──────────────────────────────────────────

Chart.defaults.color = COLORS.textPrimary;
Chart.defaults.font.family = "'Inter', system-ui, -apple-system, sans-serif";
Chart.defaults.font.size = 16;
Chart.defaults.responsive = true;
Chart.defaults.maintainAspectRatio = true;
Chart.defaults.aspectRatio = 1.6;
Chart.defaults.devicePixelRatio = 2;

// Grid lines
Chart.defaults.scale.grid = {
  ...Chart.defaults.scale.grid,
  color: `${COLORS.cardBorder}66`, // 40% opacity
};

// Axis title font
Chart.defaults.scale.title = {
  ...Chart.defaults.scale.title,
  font: { size: 18, family: "'Inter', system-ui, -apple-system, sans-serif" },
  color: COLORS.textPrimary,
};

// Points
Chart.defaults.elements.point.radius = 4;
Chart.defaults.elements.point.hoverRadius = 7;

// Lines
Chart.defaults.elements.line.borderWidth = 3;

// Legend
Chart.defaults.plugins.legend = {
  ...Chart.defaults.plugins.legend,
  position: "bottom" as const,
  labels: {
    ...Chart.defaults.plugins.legend.labels,
    color: COLORS.textPrimary,
    font: { size: 14, family: "'Inter', system-ui, -apple-system, sans-serif" },
    padding: 16,
    usePointStyle: true,
  },
};

// Tooltip
Chart.defaults.plugins.tooltip = {
  ...Chart.defaults.plugins.tooltip,
  backgroundColor: "#1e1e30ee",
  titleColor: COLORS.textPrimary,
  bodyColor: COLORS.textSecondary,
  borderColor: COLORS.cardBorder,
  borderWidth: 1,
  cornerRadius: 8,
  padding: 12,
  titleFont: {
    size: 14,
    family: "'Inter', system-ui, -apple-system, sans-serif",
  },
  bodyFont: {
    size: 13,
    family: "'Inter', system-ui, -apple-system, sans-serif",
  },
};
