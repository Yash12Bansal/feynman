import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { BoardLayout, BoardZone } from "./types";
import { BOARD_WIDTH, BOARD_HEIGHT } from "./types";
import { computeBoardLayout, allZones } from "./zone-layout";
import { BoardLayoutContext } from "./board-layout-context";
import { ElementRegistryContext, useCreateElementRegistry } from "../elements";
import { injectThemeVars } from "../theme";
import "./WhiteboardScene.css";

// ── Scale hook ────────────────────────────────────────────

interface BoardScale {
  scale: number;
  offsetX: number;
  offsetY: number;
}

function useBoardScale(
  viewportRef: React.RefObject<HTMLDivElement | null>,
): BoardScale {
  const [size, setSize] = useState<{ width: number; height: number }>({
    width: BOARD_WIDTH,
    height: BOARD_HEIGHT,
  });

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0) {
          setSize({ width, height });
        }
      }
    });

    observer.observe(el);
    return () => observer.disconnect();
  }, [viewportRef]);

  return useMemo(() => {
    const scale = Math.min(
      size.width / BOARD_WIDTH,
      size.height / BOARD_HEIGHT,
    );
    const offsetX = (size.width - BOARD_WIDTH * scale) / 2;
    const offsetY = (size.height - BOARD_HEIGHT * scale) / 2;
    return { scale, offsetX, offsetY };
  }, [size.width, size.height]);
}

// ── Zone debug overlay (internal) ─────────────────────────

function ZoneDebugOverlay({ layout }: { layout: BoardLayout }) {
  const zones = allZones();

  return (
    <>
      {zones.map((zone: BoardZone) => {
        const { outer, inner } = layout.zones[zone];
        return (
          <div key={zone}>
            <div
              className="wb-zone-debug"
              data-zone={zone}
              style={{
                left: outer.x,
                top: outer.y,
                width: outer.width,
                height: outer.height,
              }}
            >
              <span className="wb-zone-debug-label">{zone}</span>
            </div>
            <div
              className="wb-zone-debug-inner"
              style={{
                left: inner.x,
                top: inner.y,
                width: inner.width,
                height: inner.height,
              }}
            />
          </div>
        );
      })}
    </>
  );
}

// ── WhiteboardScene ───────────────────────────────────────

export interface WhiteboardSceneProps {
  debugZones?: boolean;
  children?: ReactNode;
}

export function WhiteboardScene({
  debugZones,
  children,
}: WhiteboardSceneProps) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const registry = useCreateElementRegistry();
  const layout = useMemo(() => computeBoardLayout(), []);
  const { scale, offsetX, offsetY } = useBoardScale(viewportRef);

  // Inject theme CSS variables on mount
  const boardRef = useCallback((el: HTMLDivElement | null) => {
    if (el) injectThemeVars(el);
  }, []);

  const boardTransform = `translate(${offsetX}px, ${offsetY}px) scale(${scale})`;

  return (
    <BoardLayoutContext.Provider value={layout}>
      <ElementRegistryContext.Provider value={registry}>
        <div ref={viewportRef} className="wb-viewport">
          <div
            ref={boardRef}
            className="wb-board"
            style={{
              width: BOARD_WIDTH,
              height: BOARD_HEIGHT,
              transform: boardTransform,
            }}
          >
            <div className="wb-board-surface">
              {debugZones && <ZoneDebugOverlay layout={layout} />}
              {children}
            </div>
          </div>
        </div>
      </ElementRegistryContext.Provider>
    </BoardLayoutContext.Provider>
  );
}
