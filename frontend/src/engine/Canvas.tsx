import { useRef, useEffect } from "react";
import type { VisualInstruction } from "../types/visuals";
import { renderInstruction, resetRenderer } from "./renderer";

interface CanvasProps {
  instructions: VisualInstruction[];
}

export function Canvas({ instructions }: CanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const ctxRef = useRef<CanvasRenderingContext2D | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctxRef.current = ctx;

    const resize = () => {
      canvas.width = canvas.offsetWidth * window.devicePixelRatio;
      canvas.height = canvas.offsetHeight * window.devicePixelRatio;
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    };
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);

  useEffect(() => {
    const ctx = ctxRef.current;
    const canvas = canvasRef.current;
    if (!ctx || !canvas) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    resetRenderer();
    for (const instruction of instructions) {
      renderInstruction(ctx, instruction);
    }
  }, [instructions]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: "100%", height: "100%", background: "#111" }}
    />
  );
}
