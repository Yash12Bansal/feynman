import type { VisualInstruction } from "../types/visuals";

let nextY = 60;

export function resetRenderer(): void {
  nextY = 60;
}

function wrapText(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  maxWidth: number,
): void {
  const words = text.split(" ");
  let line = "";
  for (const word of words) {
    const test = line + (line ? " " : "") + word;
    if (ctx.measureText(test).width > maxWidth && line) {
      ctx.fillText(line, x, nextY);
      nextY += 30;
      line = word;
    } else {
      line = test;
    }
  }
  if (line) {
    ctx.fillText(line, x, nextY);
    nextY += 30;
  }
}

export function renderInstruction(
  ctx: CanvasRenderingContext2D,
  instruction: VisualInstruction,
): void {
  const logicalWidth = ctx.canvas.width / (window.devicePixelRatio || 1);

  switch (instruction.type) {
    case "clear":
      ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
      nextY = 60;
      break;
    case "show_text": {
      const title = (instruction.payload?.title as string) ?? "";
      const text = (instruction.payload?.text as string) ?? "";
      if (title) {
        ctx.fillStyle = "#60a5fa";
        ctx.font = "bold 28px system-ui";
        ctx.fillText(title, 40, nextY);
        nextY += 40;
      }
      ctx.fillStyle = "#fafafa";
      ctx.font = "22px system-ui";
      wrapText(ctx, text, 40, logicalWidth - 80);
      nextY += 16;
      break;
    }
    case "show_equation": {
      const equation = (instruction.payload?.equation as string) ?? "";
      const label = (instruction.payload?.label as string) ?? "";
      if (label) {
        ctx.fillStyle = "#a78bfa";
        ctx.font = "italic 18px system-ui";
        ctx.fillText(label, 40, nextY);
        nextY += 28;
      }
      ctx.fillStyle = "#fde68a";
      ctx.font = "bold 30px 'Courier New', monospace";
      ctx.fillText(equation, 60, nextY);
      nextY += 50;
      break;
    }
    case "draw_diagram": {
      const desc = (instruction.payload?.description as string) ?? "";
      ctx.fillStyle = "#86efac";
      ctx.font = "italic 20px system-ui";
      ctx.fillText(`[Diagram: ${desc}]`, 40, nextY);
      nextY += 40;
      break;
    }
    default:
      if (["highlight", "show_graph", "animate"].includes(instruction.type)) {
        console.warn(`Visual type "${instruction.type}" not yet implemented`);
      } else {
        console.warn(`Unknown visual type: ${instruction.type}`);
      }
  }
}
