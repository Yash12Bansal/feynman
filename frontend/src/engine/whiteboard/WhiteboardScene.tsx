import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import gsap from "gsap";
import type {
  VisualInstruction,
  HighlightInstruction,
  AnnotateInstruction,
  HighlightWalkInstruction,
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
import { HighlightWalkOverlay } from "../content/HighlightWalkOverlay";
import { AnnotationLayer } from "./content/AnnotationLayer";
import { AliveFilter } from "./AliveFilter";
import { BoundsReporter } from "./BoundsReporter";
import { BoardNavigator } from "./BoardNavigator";
import type { BoardTransition, BoardMeta, CameraState } from "./useBoardStore";
import "./WhiteboardScene.css";

// ── Scale hook ────────────���───────────────────────────────

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

// ── Tile key helpers ──────────────────────────────────────

/** Encode tile coordinates to a stable string key. */
function tileKey(tx: number, ty: number): string {
  return `${tx},${ty}`;
}

// ── WhiteboardScene ─────────��─────────────────────────────

const DEFAULT_ZONE: BoardZone = "center-center";
const SCROLL_DURATION = 0.7;

export interface WhiteboardSceneProps {
  instructions: VisualInstruction[];
  /** Highlight walks — passed separately to avoid re-rendering diagram cards. */
  walks?: HighlightWalkInstruction[];
  debugZones?: boolean;
  /** Active board ID — enables BoundsReporter when provided. */
  activeBoardId?: string;
  /** Board navigation — all optional. When absent, renders exactly as before. */
  activeBoardMeta?: BoardMeta | null;
  pendingTransition?: BoardTransition | null;
  /** Camera position for infinite canvas scrolling. */
  cameraState?: CameraState;
  onTransitionComplete?: () => void;
  getBoardInstructions?: (boardId: string) => VisualInstruction[];
}

export function WhiteboardScene({
  instructions,
  walks = [],
  debugZones,
  activeBoardId,
  activeBoardMeta,
  pendingTransition,
  cameraState,
  onTransitionComplete,
  getBoardInstructions,
}: WhiteboardSceneProps) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const registry = useCreateElementRegistry();
  const layout = useMemo(() => computeBoardLayout(), []);
  const { scale, offsetX, offsetY } = useBoardScale(viewportRef);

  const boardSurfaceRef = useRef<HTMLDivElement>(null);
  const boardElRef = useRef<HTMLDivElement>(null);
  const cameraTweenRef = useRef<gsap.core.Tween | null>(null);
  const prevCameraRef = useRef<CameraState>({ tileX: 0, tileY: 0 });

  // Separate renderable elements from effects
  const { elements, highlights, annotations } = useMemo(() => {
    const elems: VisualInstruction[] = [];
    const hlights: HighlightInstruction[] = [];
    const anns: AnnotateInstruction[] = [];

    for (const instr of instructions) {
      if (instr.type === "highlight") {
        hlights.push(instr);
      } else if (instr.type === "annotate") {
        anns.push(instr);
      } else if (
        instr.type !== "clear" &&
        instr.type !== "switch_board" &&
        instr.type !== "scroll_view"
      ) {
        elems.push(instr);
      }
    }

    return { elements: elems, highlights: hlights, annotations: anns };
  }, [instructions]);

  // Group elements by tile, then by zone within each tile
  const tileGroups = useMemo(() => {
    const tiles = new Map<
      string,
      { tx: number; ty: number; zones: Map<BoardZone, VisualInstruction[]> }
    >();

    for (const instr of elements) {
      const tx = instr._tileX ?? 0;
      const ty = instr._tileY ?? 0;
      const key = tileKey(tx, ty);
      let tile = tiles.get(key);
      if (!tile) {
        tile = { tx, ty, zones: new Map() };
        tiles.set(key, tile);
      }
      const zone = instr.zone ?? DEFAULT_ZONE;
      let list = tile.zones.get(zone);
      if (!list) {
        list = [];
        tile.zones.set(zone, list);
      }
      list.push(instr);
    }

    return tiles;
  }, [elements]);

  // Inject theme CSS variables on mount
  const themeRef = useCallback((el: HTMLDivElement | null) => {
    if (el) injectThemeVars(el);
  }, []);

  // ── Compute board transform ───────────────────────────────

  const camTileX = cameraState?.tileX ?? 0;
  const camTileY = cameraState?.tileY ?? 0;

  const boardTransform = `translate(${-(camTileX * BOARD_WIDTH) * scale + offsetX}px, ${-(camTileY * BOARD_HEIGHT) * scale + offsetY}px) scale(${scale})`;

  // ── Animate camera pan ────────────────────────────────────
  // Uses useLayoutEffect so GSAP overrides the style before paint,
  // preventing a flash of the final position.

  useLayoutEffect(() => {
    const el = boardElRef.current;
    if (!el) return;

    const cameraChanged =
      prevCameraRef.current.tileX !== camTileX ||
      prevCameraRef.current.tileY !== camTileY;

    if (!cameraChanged) {
      // No camera change — just update prev ref (handles initial render)
      prevCameraRef.current = { tileX: camTileX, tileY: camTileY };
      // Clear any GSAP inline overrides so React's style prop takes effect
      gsap.set(el, { clearProps: "transform" });
      return;
    }

    // Kill any in-progress tween
    if (cameraTweenRef.current) {
      cameraTweenRef.current.kill();
      cameraTweenRef.current = null;
    }

    const prefersReduced = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    if (prefersReduced) {
      prevCameraRef.current = { tileX: camTileX, tileY: camTileY };
      return;
    }

    // Compute old and new pixel positions
    const oldX =
      -(prevCameraRef.current.tileX * BOARD_WIDTH) * scale + offsetX;
    const oldY =
      -(prevCameraRef.current.tileY * BOARD_HEIGHT) * scale + offsetY;
    const newX = -(camTileX * BOARD_WIDTH) * scale + offsetX;
    const newY = -(camTileY * BOARD_HEIGHT) * scale + offsetY;

    prevCameraRef.current = { tileX: camTileX, tileY: camTileY };

    // Animate from old position to new position.
    // GSAP overrides React's style.transform during animation.
    // On complete, clear GSAP props so React's style prop takes over.
    cameraTweenRef.current = gsap.fromTo(
      el,
      {
        x: oldX,
        y: oldY,
        scale,
      },
      {
        x: newX,
        y: newY,
        scale,
        duration: SCROLL_DURATION,
        ease: "power2.inOut",
        onComplete: () => {
          cameraTweenRef.current = null;
          gsap.set(el, { clearProps: "transform" });
        },
      },
    );

    return () => {
      if (cameraTweenRef.current) {
        cameraTweenRef.current.kill();
        cameraTweenRef.current = null;
      }
    };
  }, [camTileX, camTileY, scale, offsetX, offsetY]);

  const hasBoardNav =
    onTransitionComplete !== undefined && getBoardInstructions !== undefined;

  const boardSurface = (
    <div ref={boardSurfaceRef} className="wb-board-surface">
      <AliveFilter />
      {debugZones && <ZoneDebugOverlay layout={layout} />}
      {Array.from(tileGroups.values()).map(({ tx, ty, zones: zoneMap }) => (
        <div
          key={tileKey(tx, ty)}
          className="wb-tile"
          style={{
            position: "absolute",
            left: tx * BOARD_WIDTH,
            top: ty * BOARD_HEIGHT,
            width: BOARD_WIDTH,
            height: BOARD_HEIGHT,
          }}
        >
          {Array.from(zoneMap.entries()).map(([zone, zoneInstructions]) => {
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
          })}
        </div>
      ))}
      <AnnotationLayer
        annotations={annotations}
        boardRef={boardSurfaceRef}
        scale={scale}
      />
      {activeBoardId && (
        <BoundsReporter
          boardSurfaceRef={boardSurfaceRef}
          scale={scale}
          activeBoardId={activeBoardId}
          activeInstructions={elements}
        />
      )}
    </div>
  );

  return (
    <BoardLayoutContext.Provider value={layout}>
      <ElementRegistryContext.Provider value={registry}>
        <div ref={viewportRef} className="wb-viewport">
          <div
            ref={(el) => {
              boardElRef.current = el;
              themeRef(el);
            }}
            className="wb-board"
            style={{
              width: BOARD_WIDTH,
              height: BOARD_HEIGHT,
              transform: boardTransform,
            }}
          >
            {hasBoardNav ? (
              <BoardNavigator
                activeBoardMeta={activeBoardMeta ?? null}
                pendingTransition={pendingTransition ?? null}
                onTransitionComplete={onTransitionComplete}
                getBoardInstructions={getBoardInstructions}
              >
                {boardSurface}
              </BoardNavigator>
            ) : (
              boardSurface
            )}
          </div>
        </div>
        {highlights.map((h, idx) => (
          <HighlightOverlay
            key={`highlight-${h.target_id}-${idx}`}
            instruction={h}
          />
        ))}
        {walks.map((w, idx) => (
          <HighlightWalkOverlay
            key={`walk-${w.target_id}-${idx}`}
            instruction={w}
          />
        ))}
      </ElementRegistryContext.Provider>
    </BoardLayoutContext.Provider>
  );
}
