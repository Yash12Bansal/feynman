import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  VisualInstruction,
  HighlightInstruction,
} from "../../types/visuals";
import type { BoardLayout, BoardZone } from "./types";
import { BOARD_WIDTH, BOARD_HEIGHT } from "./types";
import { computeBoardLayout, allZones } from "./zone-layout";
import { BoardLayoutContext } from "./board-layout-context";
import { ElementRegistryContext, useCreateElementRegistry } from "../elements";
import { injectThemeVars } from "../theme";
import { WhiteboardCard } from "./WhiteboardCard";
import { InstructionSwitch } from "./InstructionSwitch";
import { HighlightOverlay } from "../content/HighlightOverlay";
import { AliveFilter } from "./AliveFilter";
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

const DEFAULT_ZONE: BoardZone = "center-center";

export interface WhiteboardSceneProps {
  instructions: VisualInstruction[];
  debugZones?: boolean;
}

export function WhiteboardScene({
  instructions,
  debugZones,
}: WhiteboardSceneProps) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const registry = useCreateElementRegistry();
  const layout = useMemo(() => computeBoardLayout(), []);
  const { scale, offsetX, offsetY } = useBoardScale(viewportRef);

  // Separate renderable elements from effects
  const { elements, highlights } = useMemo(() => {
    const elems: VisualInstruction[] = [];
    const hlights: HighlightInstruction[] = [];

    for (const instr of instructions) {
      if (instr.type === "highlight") {
        hlights.push(instr);
      } else if (instr.type !== "clear") {
        elems.push(instr);
      }
    }

    return { elements: elems, highlights: hlights };
  }, [instructions]);

  // Group elements by zone
  const zoneGroups = useMemo(() => {
    const groups = new Map<BoardZone, VisualInstruction[]>();

    for (const instr of elements) {
      const zone = instr.zone ?? DEFAULT_ZONE;
      let list = groups.get(zone);
      if (!list) {
        list = [];
        groups.set(zone, list);
      }
      list.push(instr);
    }

    return groups;
  }, [elements]);

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
              <AliveFilter />
              {debugZones && <ZoneDebugOverlay layout={layout} />}
              {Array.from(zoneGroups.entries()).map(
                ([zone, zoneInstructions]) => {
                  const { inner } = layout.zones[zone];
                  return (
                    <div
                      key={zone}
                      className="wb-zone"
                      data-zone={zone}
                      style={{
                        left: inner.x,
                        top: inner.y,
                        width: inner.width,
                        height: inner.height,
                      }}
                    >
                      {zoneInstructions.map((instr, idx) => (
                        <WhiteboardCard
                          key={instr.element_id ?? `wb-${zone}-${idx}`}
                          instruction={instr}
                        >
                          <InstructionSwitch instruction={instr} />
                        </WhiteboardCard>
                      ))}
                    </div>
                  );
                },
              )}
            </div>
          </div>
        </div>
        {highlights.map((h, idx) => (
          <HighlightOverlay
            key={`highlight-${h.target_id}-${idx}`}
            instruction={h}
          />
        ))}
      </ElementRegistryContext.Provider>
    </BoardLayoutContext.Provider>
  );
}
