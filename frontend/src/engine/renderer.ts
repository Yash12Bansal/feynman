/**
 * Visual instruction renderer.
 *
 * Takes typed visual instructions from the backend and renders them
 * onto the Canvas. This is the core rendering engine for the classroom screen.
 */

import type { VisualInstruction } from "../types/visuals";

export function renderInstruction(
  ctx: CanvasRenderingContext2D,
  instruction: VisualInstruction,
): void {
  switch (instruction.type) {
    case "clear":
      ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
      break;
    case "show_text":
      ctx.fillStyle = "#fafafa";
      ctx.font = "24px system-ui";
      ctx.fillText((instruction.payload?.text as string) ?? "", 40, 60);
      break;
    default:
      console.warn(`Unknown visual instruction type: ${instruction.type}`);
  }
}
