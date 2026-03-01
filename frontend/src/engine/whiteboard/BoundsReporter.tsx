/**
 * Headless component that measures rendered element bounds and publishes
 * them to the backend via LiveKit data channel.
 *
 * Closes the spatial feedback loop: frontend reports actual pixel bounds →
 * backend builds a SceneGraph → LLM gets rich spatial context.
 *
 * Returns null — no DOM output.
 */

import { useEffect, useRef } from "react";
import type { RefObject } from "react";
import { useRoomContext } from "@livekit/components-react";
import type { VisualInstruction } from "../../types/visuals";
import { useElementRegistry } from "../elements";
import { viewportToBoard } from "./board-coords";

export interface BoundsReporterProps {
  boardSurfaceRef: RefObject<HTMLDivElement | null>;
  scale: number;
  activeBoardId: string;
  activeInstructions: VisualInstruction[];
}

interface BoundsEntry {
  element_id: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

interface BoundsReport {
  type: "bounds_report";
  board_id: string;
  timestamp: number;
  elements: BoundsEntry[];
}

/** Simple hash of a report for deduplication. */
function hashReport(elements: BoundsEntry[]): string {
  // Fast fingerprint: concat id + rounded coords
  return elements
    .map(
      (e) =>
        `${e.element_id}:${Math.round(e.x)},${Math.round(e.y)},${Math.round(e.width)},${Math.round(e.height)}`,
    )
    .join("|");
}

export function BoundsReporter({
  boardSurfaceRef,
  scale,
  activeBoardId,
  activeInstructions,
}: BoundsReporterProps) {
  const registry = useElementRegistry();
  const lastHashRef = useRef<string>("");
  const scaleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Always call the hook (rules of hooks), store result in ref via effect.
  const room = useRoomContext();
  const roomRef = useRef(room);

  useEffect(() => {
    roomRef.current = room;
  }, [room]);

  const measureAndSend = useRef(() => {});

  // Keep the closure fresh
  useEffect(() => {
    measureAndSend.current = () => {
      const boardEl = boardSurfaceRef.current;
      const currentRoom = roomRef.current;
      if (!boardEl || !currentRoom) return;

      const boardRect = boardEl.getBoundingClientRect();
      const elements: BoundsEntry[] = [];

      for (const [id, entry] of registry.entries()) {
        const elRect = entry.ref.getBoundingClientRect();
        if (elRect.width === 0 && elRect.height === 0) continue;

        const rect = viewportToBoard(elRect, boardRect, scale);
        elements.push({
          element_id: id,
          x: rect.x,
          y: rect.y,
          width: rect.width,
          height: rect.height,
        });
      }

      // Deduplicate — skip if identical to last report
      const hash = hashReport(elements);
      if (hash === lastHashRef.current) return;
      lastHashRef.current = hash;

      const report: BoundsReport = {
        type: "bounds_report",
        board_id: activeBoardId,
        timestamp: Date.now(),
        elements,
      };

      const data = new TextEncoder().encode(JSON.stringify(report));
      currentRoom.localParticipant
        .publishData(data, { topic: "bounds", reliable: false })
        .catch(() => {
          // Swallow — bounds reports are best-effort
        });
    };
  }, [boardSurfaceRef, scale, activeBoardId, registry]);

  // Measure after instructions change — wait 2 rAF frames for layout/paint
  useEffect(() => {
    const frame1 = requestAnimationFrame(() => {
      frame2 = requestAnimationFrame(() => {
        measureAndSend.current();
      });
    });
    let frame2: number | undefined;

    return () => {
      cancelAnimationFrame(frame1);
      if (frame2 != null) cancelAnimationFrame(frame2);
    };
  }, [activeInstructions]);

  // Re-measure on scale change (debounced 300ms)
  useEffect(() => {
    if (scaleTimerRef.current) clearTimeout(scaleTimerRef.current);
    scaleTimerRef.current = setTimeout(() => {
      measureAndSend.current();
    }, 300);

    return () => {
      if (scaleTimerRef.current) clearTimeout(scaleTimerRef.current);
    };
  }, [scale]);

  return null;
}
