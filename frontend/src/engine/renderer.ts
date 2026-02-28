/**
 * @deprecated Phase 2 replaced Canvas rendering with VisualScene.tsx (React components).
 * Kept as design token reference and rollback safety net until Phase 3 is verified.
 * Do not add new functionality here — use theme.ts for tokens, VisualScene for rendering.
 *
 * Original: Canvas 2D renderer for visual instructions.
 */

import type {
  DrawDiagramInstruction,
  ShowEquationInstruction,
  ShowTextInstruction,
  VisualInstruction,
} from "../types/visuals";

// ---------------------------------------------------------------------------
// Design tokens
// ---------------------------------------------------------------------------

const COLORS = {
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
} as const;

const LAYOUT = {
  marginX: 48,
  cardPadding: 32,
  cardGap: 20,
  cardRadius: 16,
  topMargin: 48,
  maxContentWidth: 1200,
} as const;

const FONTS = {
  title: "bold 34px 'Inter', system-ui, -apple-system, sans-serif",
  body: "24px 'Inter', system-ui, -apple-system, sans-serif",
  equationLabel: "italic 20px 'Inter', system-ui, -apple-system, sans-serif",
  equation:
    "32px 'JetBrains Mono', 'SF Mono', 'Fira Code', 'Cascadia Code', monospace",
  diagramLabel: "italic 22px 'Inter', system-ui, -apple-system, sans-serif",
  diagramDesc: "20px 'Inter', system-ui, -apple-system, sans-serif",
  badge: "bold 11px 'Inter', system-ui, -apple-system, sans-serif",
} as const;

const LINE_HEIGHTS = {
  title: 44,
  body: 36,
  equation: 44,
  diagramDesc: 32,
} as const;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let cursorY = LAYOUT.topMargin;

export function resetRenderer(): void {
  cursorY = LAYOUT.topMargin;
}

// ---------------------------------------------------------------------------
// Drawing primitives
// ---------------------------------------------------------------------------

function roundedRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
): void {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.arcTo(x + w, y, x + w, y + r, r);
  ctx.lineTo(x + w, y + h - r);
  ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
  ctx.lineTo(x + r, y + h);
  ctx.arcTo(x, y + h, x, y + h - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
  ctx.closePath();
}

function drawCard(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  options?: {
    fillColor?: string;
    borderColor?: string;
    accentColor?: string;
  },
): void {
  const fill = options?.fillColor ?? COLORS.cardBg;
  const border = options?.borderColor ?? COLORS.cardBorder;
  const accent = options?.accentColor;

  // Card background
  roundedRect(ctx, x, y, w, h, LAYOUT.cardRadius);
  ctx.fillStyle = fill;
  ctx.fill();

  // Subtle border
  ctx.strokeStyle = border;
  ctx.lineWidth = 1;
  ctx.stroke();

  // Left accent stripe
  if (accent) {
    const stripeR = 4;
    ctx.beginPath();
    ctx.moveTo(x + LAYOUT.cardRadius, y);
    ctx.lineTo(x + LAYOUT.cardRadius, y);
    ctx.arcTo(x, y, x, y + LAYOUT.cardRadius, LAYOUT.cardRadius);
    ctx.lineTo(x, y + h - LAYOUT.cardRadius);
    ctx.arcTo(x, y + h, x + LAYOUT.cardRadius, y + h, LAYOUT.cardRadius);
    ctx.lineTo(x + stripeR, y + h);
    ctx.lineTo(x + stripeR, y);
    ctx.closePath();
    ctx.fillStyle = accent;
    ctx.globalAlpha = 0.5;
    ctx.fill();
    ctx.globalAlpha = 1;
  }
}

function wrapLines(
  ctx: CanvasRenderingContext2D,
  text: string,
  font: string,
  maxWidth: number,
  lineHeight: number,
): { lines: string[]; height: number } {
  ctx.font = font;
  const words = text.split(" ");
  const lines: string[] = [];
  let current = "";

  for (const word of words) {
    const test = current + (current ? " " : "") + word;
    if (ctx.measureText(test).width > maxWidth && current) {
      lines.push(current);
      current = word;
    } else {
      current = test;
    }
  }
  if (current) lines.push(current);
  if (lines.length === 0) lines.push("");

  return { lines, height: lines.length * lineHeight };
}

// ---------------------------------------------------------------------------
// Compute layout dimensions
// ---------------------------------------------------------------------------

function contentArea(logicalWidth: number): {
  x: number;
  width: number;
} {
  const available = logicalWidth - LAYOUT.marginX * 2;
  const width = Math.min(available, LAYOUT.maxContentWidth);
  const x = (logicalWidth - width) / 2;
  return { x, width };
}

// ---------------------------------------------------------------------------
// Instruction renderers
// ---------------------------------------------------------------------------

function renderShowText(
  ctx: CanvasRenderingContext2D,
  instr: ShowTextInstruction,
  logicalWidth: number,
): void {
  const { x: cardX, width: cardWidth } = contentArea(logicalWidth);
  const innerWidth = cardWidth - LAYOUT.cardPadding * 2;

  let contentHeight = 0;
  if (instr.title) {
    contentHeight += LINE_HEIGHTS.title + 8;
  }
  const wrapped = wrapLines(
    ctx,
    instr.text,
    FONTS.body,
    innerWidth,
    LINE_HEIGHTS.body,
  );
  contentHeight += wrapped.height;

  const cardHeight = contentHeight + LAYOUT.cardPadding * 2;

  drawCard(ctx, cardX, cursorY, cardWidth, cardHeight, {
    accentColor: COLORS.accentBlue,
  });

  let textY = cursorY + LAYOUT.cardPadding;
  const textX = cardX + LAYOUT.cardPadding;

  if (instr.title) {
    ctx.fillStyle = COLORS.accentBlue;
    ctx.font = FONTS.title;
    ctx.fillText(instr.title, textX, textY + 26);
    textY += LINE_HEIGHTS.title + 8;
  }

  ctx.fillStyle = COLORS.textPrimary;
  ctx.font = FONTS.body;
  for (const line of wrapped.lines) {
    ctx.fillText(line, textX, textY + 20);
    textY += LINE_HEIGHTS.body;
  }

  cursorY += cardHeight + LAYOUT.cardGap;
}

function renderShowEquation(
  ctx: CanvasRenderingContext2D,
  instr: ShowEquationInstruction,
  logicalWidth: number,
): void {
  const { x: cardX, width: cardWidth } = contentArea(logicalWidth);

  let contentHeight = 0;
  if (instr.label) {
    contentHeight += 28 + 12;
  }
  contentHeight += LINE_HEIGHTS.equation + 16;

  const cardHeight = contentHeight + LAYOUT.cardPadding * 2;

  drawCard(ctx, cardX, cursorY, cardWidth, cardHeight, {
    fillColor: COLORS.equationBg,
    accentColor: COLORS.accentAmber,
  });

  let textY = cursorY + LAYOUT.cardPadding;
  const textX = cardX + LAYOUT.cardPadding;

  if (instr.label) {
    ctx.fillStyle = COLORS.accentPurple;
    ctx.font = FONTS.equationLabel;
    ctx.fillText(instr.label, textX, textY + 16);
    textY += 28 + 12;
  }

  // Render LaTeX as monospace text (KaTeX rendering comes in Phase 3)
  ctx.fillStyle = COLORS.accentAmber;
  ctx.font = FONTS.equation;
  const eqWidth = ctx.measureText(instr.latex).width;
  const eqX = cardX + (cardWidth - eqWidth) / 2;
  ctx.fillText(instr.latex, eqX, textY + 26);

  cursorY += cardHeight + LAYOUT.cardGap;
}

function renderDrawDiagram(
  ctx: CanvasRenderingContext2D,
  instr: DrawDiagramInstruction,
  logicalWidth: number,
): void {
  const description = instr.description ?? instr.title ?? "";
  const { x: cardX, width: cardWidth } = contentArea(logicalWidth);
  const innerWidth = cardWidth - LAYOUT.cardPadding * 2;

  const placeholderHeight = 160;

  const wrapped = wrapLines(
    ctx,
    description,
    FONTS.diagramDesc,
    innerWidth,
    LINE_HEIGHTS.diagramDesc,
  );

  const cardHeight =
    LAYOUT.cardPadding * 2 + placeholderHeight + 16 + wrapped.height;

  drawCard(ctx, cardX, cursorY, cardWidth, cardHeight, {
    fillColor: COLORS.diagramBg,
    borderColor: COLORS.diagramBorder,
    accentColor: COLORS.accentGreen,
  });

  const textX = cardX + LAYOUT.cardPadding;
  let innerY = cursorY + LAYOUT.cardPadding;

  // Diagram placeholder area
  const phX = textX;
  const phWidth = innerWidth;
  roundedRect(ctx, phX, innerY, phWidth, placeholderHeight, 8);
  ctx.strokeStyle = COLORS.accentGreen;
  ctx.globalAlpha = 0.3;
  ctx.lineWidth = 2;
  ctx.setLineDash([8, 6]);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.globalAlpha = 1;

  // Diagram icon (simple box/lines to suggest a diagram)
  const iconCX = phX + phWidth / 2;
  const iconCY = innerY + placeholderHeight / 2;
  ctx.strokeStyle = COLORS.accentGreen;
  ctx.globalAlpha = 0.4;
  ctx.lineWidth = 2;

  const nodeR = 6;
  const spread = 30;
  ctx.beginPath();
  ctx.arc(iconCX, iconCY - spread, nodeR, 0, Math.PI * 2);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(iconCX - spread, iconCY + spread * 0.6, nodeR, 0, Math.PI * 2);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(iconCX + spread, iconCY + spread * 0.6, nodeR, 0, Math.PI * 2);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(iconCX, iconCY - spread + nodeR);
  ctx.lineTo(iconCX - spread, iconCY + spread * 0.6 - nodeR);
  ctx.moveTo(iconCX, iconCY - spread + nodeR);
  ctx.lineTo(iconCX + spread, iconCY + spread * 0.6 - nodeR);
  ctx.moveTo(iconCX - spread + nodeR, iconCY + spread * 0.6);
  ctx.lineTo(iconCX + spread - nodeR, iconCY + spread * 0.6);
  ctx.stroke();

  ctx.globalAlpha = 1;

  // "DIAGRAM" badge
  ctx.fillStyle = COLORS.accentGreen;
  ctx.globalAlpha = 0.6;
  ctx.font = FONTS.badge;
  const badgeText = "DIAGRAM";
  const badgeWidth = ctx.measureText(badgeText).width + 16;
  roundedRect(
    ctx,
    iconCX - badgeWidth / 2,
    iconCY + spread * 0.6 + 20,
    badgeWidth,
    20,
    4,
  );
  ctx.fill();
  ctx.globalAlpha = 1;
  ctx.fillStyle = COLORS.diagramBg;
  ctx.fillText(
    badgeText,
    iconCX - badgeWidth / 2 + 8,
    iconCY + spread * 0.6 + 35,
  );

  innerY += placeholderHeight + 16;

  ctx.fillStyle = COLORS.textSecondary;
  ctx.font = FONTS.diagramDesc;
  for (const line of wrapped.lines) {
    ctx.fillText(line, textX, innerY + 16);
    innerY += LINE_HEIGHTS.diagramDesc;
  }

  cursorY += cardHeight + LAYOUT.cardGap;
}

function renderHighlight(
  ctx: CanvasRenderingContext2D,
  _instr: VisualInstruction & { type: "highlight" },
  logicalWidth: number,
): void {
  // Highlight targets an existing element by target_id — placeholder rendering
  // for now until incremental rendering (Phase 2) enables element lookup.
  const text = `Highlight: ${_instr.target_id}`;
  const { x: cardX, width: cardWidth } = contentArea(logicalWidth);
  const innerWidth = cardWidth - LAYOUT.cardPadding * 2;

  const wrapped = wrapLines(
    ctx,
    text,
    FONTS.body,
    innerWidth,
    LINE_HEIGHTS.body,
  );
  const cardHeight = wrapped.height + LAYOUT.cardPadding * 2;

  drawCard(ctx, cardX, cursorY, cardWidth, cardHeight, {
    fillColor: "#1a1a10",
    borderColor: "#3a3a20",
    accentColor: COLORS.accentAmber,
  });

  const textX = cardX + LAYOUT.cardPadding;
  let textY = cursorY + LAYOUT.cardPadding;
  ctx.fillStyle = COLORS.accentAmber;
  ctx.font = FONTS.body;
  for (const line of wrapped.lines) {
    ctx.fillText(line, textX, textY + 20);
    textY += LINE_HEIGHTS.body;
  }

  cursorY += cardHeight + LAYOUT.cardGap;
}

// ---------------------------------------------------------------------------
// Main render entry point
// ---------------------------------------------------------------------------

export function renderInstruction(
  ctx: CanvasRenderingContext2D,
  instruction: VisualInstruction,
): void {
  const logicalWidth = ctx.canvas.width / (window.devicePixelRatio || 1);

  switch (instruction.type) {
    case "clear":
      ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
      cursorY = LAYOUT.topMargin;
      break;
    case "show_text":
      renderShowText(ctx, instruction, logicalWidth);
      break;
    case "show_equation":
      renderShowEquation(ctx, instruction, logicalWidth);
      break;
    case "draw_diagram":
      renderDrawDiagram(ctx, instruction, logicalWidth);
      break;
    case "highlight":
      renderHighlight(ctx, instruction, logicalWidth);
      break;
    case "show_graph":
      console.warn(`Visual type "${instruction.type}" not yet implemented`);
      break;
    default:
      console.warn(
        `Unknown visual type: ${(instruction as { type: string }).type}`,
      );
  }
}
