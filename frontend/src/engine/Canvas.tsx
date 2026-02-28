import { useRef, useEffect, useCallback } from "react";
import type { VisualInstruction } from "../types/visuals";
import { renderInstruction, resetRenderer } from "./renderer";

interface CanvasProps {
  instructions: VisualInstruction[];
}

export function Canvas({ instructions }: CanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const redraw = useCallback((instrs: VisualInstruction[]) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    ctx.clearRect(0, 0, rect.width, rect.height);
    resetRenderer();
    for (const instruction of instrs) {
      renderInstruction(ctx, instruction);
    }
  }, []);

  useEffect(() => {
    redraw(instructions);
  }, [instructions, redraw]);

  useEffect(() => {
    const handleResize = () => redraw(instructions);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [instructions, redraw]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: "100%", height: "100%", background: "#0a0a0a" }}
    />
  );
}
