// TODO(DEADCODE): file unused in active pipelines (lecture-playback / ask-feynman) — interactive live-agent rendering (parked). See docs/engineering/13-redundant-code-audit.md Group 1/2. Safe to delete.
// /**
//  * Pure zone layout engine — no React, no DOM, no side effects.
//  *
//  * Computes 9-zone grid layout for a 1920x1080 board and places
//  * elements within zones using vertical stacking + horizontal centering.
//  */

// import type {
//   BoardZone,
//   BoardLayout,
//   Rect,
//   ZoneBounds,
//   PlacedElement,
//   PlacementResult,
//   FreeSpace,
// } from "./types";
// import { BOARD_WIDTH, BOARD_HEIGHT } from "./types";

// // ── Configuration ────────────────────────────────────────────

// export interface ZoneConfig {
//   boardWidth: number;
//   boardHeight: number;
//   /** Outer edge breathing room. */
//   boardMargin: number;
//   /** Space between zone cells. */
//   gutter: number;
//   /** Inner padding within each zone. */
//   zonePadding: number;
//   /** Column width ratios (must sum to 1). */
//   columnRatios: [number, number, number];
//   /** Row height ratios (must sum to 1). */
//   rowRatios: [number, number, number];
// }

// export const DEFAULT_ZONE_CONFIG: ZoneConfig = {
//   boardWidth: BOARD_WIDTH,
//   boardHeight: BOARD_HEIGHT,
//   boardMargin: 24,
//   gutter: 16,
//   zonePadding: 16,
//   columnRatios: [0.25, 0.5, 0.25],
//   rowRatios: [0.28, 0.44, 0.28],
// };

// const DEFAULT_ELEMENT_GAP = 12;

// // ── Zone ordering ────────────────────────────────────────────

// const ZONE_GRID: [BoardZone, number, number][] = [
//   ["top-left", 0, 0],
//   ["top-center", 0, 1],
//   ["top-right", 0, 2],
//   ["center-left", 1, 0],
//   ["center-center", 1, 1],
//   ["center-right", 1, 2],
//   ["bottom-left", 2, 0],
//   ["bottom-center", 2, 1],
//   ["bottom-right", 2, 2],
// ];

// // ── Internal helpers ─────────────────────────────────────────

// /**
//  * Distribute `total` pixels across 3 segments by ratios.
//  * All values are Math.floor'd; the last segment absorbs remainder.
//  */
// function distributeByRatios(
//   total: number,
//   ratios: [number, number, number],
// ): [number, number, number] {
//   const first = Math.floor(total * ratios[0]);
//   const second = Math.floor(total * ratios[1]);
//   const third = total - first - second;
//   return [first, second, third];
// }

// function computeZoneBounds(
//   row: number,
//   col: number,
//   zone: BoardZone,
//   colWidths: [number, number, number],
//   rowHeights: [number, number, number],
//   config: ZoneConfig,
// ): ZoneBounds {
//   // Compute outer x: margin + preceding columns + preceding gutters
//   let outerX = config.boardMargin;
//   for (let c = 0; c < col; c++) {
//     outerX += colWidths[c] + config.gutter;
//   }

//   // Compute outer y: margin + preceding rows + preceding gutters
//   let outerY = config.boardMargin;
//   for (let r = 0; r < row; r++) {
//     outerY += rowHeights[r] + config.gutter;
//   }

//   const outerWidth = colWidths[col];
//   const outerHeight = rowHeights[row];

//   const outer: Rect = {
//     x: outerX,
//     y: outerY,
//     width: outerWidth,
//     height: outerHeight,
//   };

//   const inner: Rect = {
//     x: outerX + config.zonePadding,
//     y: outerY + config.zonePadding,
//     width: outerWidth - config.zonePadding * 2,
//     height: outerHeight - config.zonePadding * 2,
//   };

//   return { zone, outer, inner };
// }

// // ── Public API ───────────────────────────────────────────────

// /**
//  * Compute all 9 zone bounds for the board. Called once, memoized by caller.
//  */
// export function computeBoardLayout(
//   config: ZoneConfig = DEFAULT_ZONE_CONFIG,
// ): BoardLayout {
//   // Available space after margins and gutters between zones
//   const availableWidth =
//     config.boardWidth - config.boardMargin * 2 - config.gutter * 2;
//   const availableHeight =
//     config.boardHeight - config.boardMargin * 2 - config.gutter * 2;

//   const colWidths = distributeByRatios(availableWidth, config.columnRatios);
//   const rowHeights = distributeByRatios(availableHeight, config.rowRatios);

//   const zones = {} as Record<BoardZone, ZoneBounds>;

//   for (const [zone, row, col] of ZONE_GRID) {
//     zones[zone] = computeZoneBounds(
//       row,
//       col,
//       zone,
//       colWidths,
//       rowHeights,
//       config,
//     );
//   }

//   return {
//     width: config.boardWidth,
//     height: config.boardHeight,
//     zones,
//   };
// }

// /**
//  * Compute placement for a new element in a zone.
//  *
//  * Stacks vertically (top-to-bottom), centers horizontally,
//  * clamps width if wider than zone. Returns the placement rect
//  * and whether the element fits vertically within the zone.
//  */
// export function computeElementPlacement(
//   zone: BoardZone,
//   elementSize: { width: number; height: number },
//   existingElements: PlacedElement[],
//   layout: BoardLayout,
//   elementGap: number = DEFAULT_ELEMENT_GAP,
// ): PlacementResult {
//   const { inner } = layout.zones[zone];

//   // Filter to elements in this zone
//   const zoneElements = existingElements.filter((el) => el.zone === zone);

//   // Find the lowest y-extent among zone elements
//   let nextY = inner.y;
//   if (zoneElements.length > 0) {
//     let maxBottom = 0;
//     for (const el of zoneElements) {
//       const bottom = el.bounds.y + el.bounds.height;
//       if (bottom > maxBottom) maxBottom = bottom;
//     }
//     nextY = maxBottom + elementGap;
//   }

//   // Clamp width to zone inner width
//   const clampedWidth = Math.min(elementSize.width, inner.width);

//   // Center horizontally within zone
//   const x = inner.x + (inner.width - clampedWidth) / 2;

//   const bounds: Rect = {
//     x,
//     y: nextY,
//     width: clampedWidth,
//     height: elementSize.height,
//   };

//   // Does it fit vertically?
//   const fits = nextY + elementSize.height <= inner.y + inner.height;

//   return { bounds, fits };
// }

// /**
//  * Query remaining free space in a zone.
//  */
// export function queryFreeSpace(
//   zone: BoardZone,
//   existingElements: PlacedElement[],
//   layout: BoardLayout,
//   elementGap: number = DEFAULT_ELEMENT_GAP,
// ): FreeSpace {
//   const { inner } = layout.zones[zone];

//   const zoneElements = existingElements.filter((el) => el.zone === zone);

//   let nextY = inner.y;
//   let usedArea = 0;

//   if (zoneElements.length > 0) {
//     let maxBottom = 0;
//     for (const el of zoneElements) {
//       const bottom = el.bounds.y + el.bounds.height;
//       if (bottom > maxBottom) maxBottom = bottom;
//       usedArea += el.bounds.width * el.bounds.height;
//     }
//     nextY = maxBottom + elementGap;
//   }

//   const totalArea = inner.width * inner.height;
//   const remainingHeight = Math.max(0, inner.y + inner.height - nextY);

//   return { zone, totalArea, usedArea, remainingHeight, nextY };
// }

// /**
//  * Returns the 9 zone IDs in reading order (top-left → bottom-right).
//  * Fresh array each call.
//  */
// export function allZones(): BoardZone[] {
//   return ZONE_GRID.map(([zone]) => zone);
// }
