import { describe, it, expect } from "vitest";
import {
  computeBoardLayout,
  computeElementPlacement,
  queryFreeSpace,
  allZones,
  DEFAULT_ZONE_CONFIG,
} from "../zone-layout";
import type { BoardZone, PlacedElement } from "../types";
import { BOARD_WIDTH, BOARD_HEIGHT } from "../types";

// ── Helpers ──────────────────────────────────────────────────

function makePlacedElement(
  id: string,
  zone: BoardZone,
  x: number,
  y: number,
  width: number,
  height: number,
): PlacedElement {
  return { id, zone, bounds: { x, y, width, height } };
}

// ── computeBoardLayout ───────────────────────────────────────

describe("computeBoardLayout", () => {
  const layout = computeBoardLayout();

  it("produces all 9 zones", () => {
    const zones = allZones();
    expect(zones).toHaveLength(9);
    for (const zone of zones) {
      expect(layout.zones[zone]).toBeDefined();
    }
  });

  it("board dimensions match 1920x1080", () => {
    expect(layout.width).toBe(BOARD_WIDTH);
    expect(layout.height).toBe(BOARD_HEIGHT);
  });

  it("no zone outer rects overlap", () => {
    const zones = allZones();
    for (let i = 0; i < zones.length; i++) {
      for (let j = i + 1; j < zones.length; j++) {
        const a = layout.zones[zones[i]].outer;
        const b = layout.zones[zones[j]].outer;
        const overlapX = a.x < b.x + b.width && a.x + a.width > b.x;
        const overlapY = a.y < b.y + b.height && a.y + a.height > b.y;
        expect(overlapX && overlapY, `${zones[i]} overlaps ${zones[j]}`).toBe(
          false,
        );
      }
    }
  });

  it("all zones fit within board bounds", () => {
    for (const zone of allZones()) {
      const { outer } = layout.zones[zone];
      expect(outer.x).toBeGreaterThanOrEqual(0);
      expect(outer.y).toBeGreaterThanOrEqual(0);
      expect(outer.x + outer.width).toBeLessThanOrEqual(BOARD_WIDTH);
      expect(outer.y + outer.height).toBeLessThanOrEqual(BOARD_HEIGHT);
    }
  });

  it("center column is wider than side columns", () => {
    const left = layout.zones["center-left"].outer.width;
    const center = layout.zones["center-center"].outer.width;
    const right = layout.zones["center-right"].outer.width;
    expect(center).toBeGreaterThan(left);
    expect(center).toBeGreaterThan(right);
  });

  it("center row is taller than top and bottom rows", () => {
    const top = layout.zones["top-center"].outer.height;
    const center = layout.zones["center-center"].outer.height;
    const bottom = layout.zones["bottom-center"].outer.height;
    expect(center).toBeGreaterThan(top);
    expect(center).toBeGreaterThan(bottom);
  });

  it("inner bounds contained within outer and respect padding", () => {
    const padding = DEFAULT_ZONE_CONFIG.zonePadding;
    for (const zone of allZones()) {
      const { outer, inner } = layout.zones[zone];
      expect(inner.x).toBe(outer.x + padding);
      expect(inner.y).toBe(outer.y + padding);
      expect(inner.width).toBe(outer.width - padding * 2);
      expect(inner.height).toBe(outer.height - padding * 2);
    }
  });

  it("custom config overrides work — zero padding/margin/gutter gives perfect tiling", () => {
    const config = {
      ...DEFAULT_ZONE_CONFIG,
      boardMargin: 0,
      gutter: 0,
      zonePadding: 0,
      columnRatios: [1 / 3, 1 / 3, 1 / 3] as [number, number, number],
      rowRatios: [1 / 3, 1 / 3, 1 / 3] as [number, number, number],
    };
    const customLayout = computeBoardLayout(config);

    // Zones should tile the entire board
    let totalOuterArea = 0;
    for (const zone of allZones()) {
      const { outer } = customLayout.zones[zone];
      totalOuterArea += outer.width * outer.height;
    }
    expect(totalOuterArea).toBe(BOARD_WIDTH * BOARD_HEIGHT);
  });

  it("column widths + gutters + margins = board width", () => {
    const cfg = DEFAULT_ZONE_CONFIG;
    const leftW = layout.zones["top-left"].outer.width;
    const centerW = layout.zones["top-center"].outer.width;
    const rightW = layout.zones["top-right"].outer.width;
    const total =
      cfg.boardMargin * 2 + cfg.gutter * 2 + leftW + centerW + rightW;
    expect(total).toBe(BOARD_WIDTH);
  });

  it("row heights + gutters + margins = board height", () => {
    const cfg = DEFAULT_ZONE_CONFIG;
    const topH = layout.zones["top-left"].outer.height;
    const centerH = layout.zones["center-left"].outer.height;
    const bottomH = layout.zones["bottom-left"].outer.height;
    const total =
      cfg.boardMargin * 2 + cfg.gutter * 2 + topH + centerH + bottomH;
    expect(total).toBe(BOARD_HEIGHT);
  });
});

// ── computeElementPlacement ──────────────────────────────────

describe("computeElementPlacement", () => {
  const layout = computeBoardLayout();
  const zone: BoardZone = "center-center";
  const inner = layout.zones[zone].inner;

  it("first element placed at zone inner top, horizontally centered", () => {
    const result = computeElementPlacement(
      zone,
      { width: 200, height: 50 },
      [],
      layout,
    );
    expect(result.bounds.y).toBe(inner.y);
    // Centered: inner.x + (inner.width - 200) / 2
    expect(result.bounds.x).toBe(inner.x + (inner.width - 200) / 2);
    expect(result.bounds.width).toBe(200);
    expect(result.bounds.height).toBe(50);
    expect(result.fits).toBe(true);
  });

  it("second element stacks below first with gap", () => {
    const firstHeight = 60;
    const gap = 12; // default
    const existing: PlacedElement[] = [
      makePlacedElement("a", zone, inner.x, inner.y, 200, firstHeight),
    ];
    const result = computeElementPlacement(
      zone,
      { width: 200, height: 40 },
      existing,
      layout,
    );
    expect(result.bounds.y).toBe(inner.y + firstHeight + gap);
  });

  it("narrow element is centered; wide element clamped to zone width", () => {
    // Narrow
    const narrow = computeElementPlacement(
      zone,
      { width: 100, height: 30 },
      [],
      layout,
    );
    expect(narrow.bounds.width).toBe(100);
    expect(narrow.bounds.x).toBe(inner.x + (inner.width - 100) / 2);

    // Wide — wider than zone
    const wide = computeElementPlacement(
      zone,
      { width: inner.width + 500, height: 30 },
      [],
      layout,
    );
    expect(wide.bounds.width).toBe(inner.width);
    expect(wide.bounds.x).toBe(inner.x);
  });

  it("fits: true when space available; fits: false when zone full", () => {
    // Small element in empty zone — fits
    const small = computeElementPlacement(
      zone,
      { width: 100, height: 30 },
      [],
      layout,
    );
    expect(small.fits).toBe(true);

    // Element taller than zone — does not fit
    const tall = computeElementPlacement(
      zone,
      { width: 100, height: inner.height + 100 },
      [],
      layout,
    );
    expect(tall.fits).toBe(false);
  });

  it("elements in different zones don't affect each other", () => {
    const otherZone: BoardZone = "top-left";
    const existing: PlacedElement[] = [
      makePlacedElement("x", otherZone, 0, 0, 200, 200),
    ];
    const result = computeElementPlacement(
      zone,
      { width: 100, height: 30 },
      existing,
      layout,
    );
    // Should be placed at zone inner top, ignoring other-zone element
    expect(result.bounds.y).toBe(inner.y);
  });

  it("custom elementGap = 0 means no spacing", () => {
    const firstHeight = 60;
    const existing: PlacedElement[] = [
      makePlacedElement("a", zone, inner.x, inner.y, 200, firstHeight),
    ];
    const result = computeElementPlacement(
      zone,
      { width: 200, height: 40 },
      existing,
      layout,
      0,
    );
    expect(result.bounds.y).toBe(inner.y + firstHeight);
  });

  it("multiple stacked elements accumulate correctly", () => {
    const h1 = 50;
    const h2 = 40;
    const gap = 12;
    const existing: PlacedElement[] = [
      makePlacedElement("a", zone, inner.x, inner.y, 200, h1),
      makePlacedElement("b", zone, inner.x, inner.y + h1 + gap, 200, h2),
    ];
    const result = computeElementPlacement(
      zone,
      { width: 200, height: 30 },
      existing,
      layout,
    );
    expect(result.bounds.y).toBe(inner.y + h1 + gap + h2 + gap);
  });
});

// ── queryFreeSpace ───────────────────────────────────────────

describe("queryFreeSpace", () => {
  const layout = computeBoardLayout();
  const zone: BoardZone = "center-center";
  const inner = layout.zones[zone].inner;

  it("empty zone: full remainingHeight, zero usedArea, nextY = inner.y", () => {
    const space = queryFreeSpace(zone, [], layout);
    expect(space.remainingHeight).toBe(inner.height);
    expect(space.usedArea).toBe(0);
    expect(space.nextY).toBe(inner.y);
    expect(space.zone).toBe(zone);
  });

  it("partially filled: correct remaining height", () => {
    const elemHeight = 80;
    const gap = 12;
    const existing: PlacedElement[] = [
      makePlacedElement("a", zone, inner.x, inner.y, 200, elemHeight),
    ];
    const space = queryFreeSpace(zone, existing, layout);
    const expectedNextY = inner.y + elemHeight + gap;
    expect(space.nextY).toBe(expectedNextY);
    expect(space.remainingHeight).toBe(inner.y + inner.height - expectedNextY);
  });

  it("usedArea = sum of actual element areas, not zone-width strips", () => {
    const existing: PlacedElement[] = [
      makePlacedElement("a", zone, inner.x, inner.y, 100, 50),
      makePlacedElement("b", zone, inner.x, inner.y + 62, 150, 30),
    ];
    const space = queryFreeSpace(zone, existing, layout);
    expect(space.usedArea).toBe(100 * 50 + 150 * 30);
  });

  it("totalArea equals inner width * inner height", () => {
    const space = queryFreeSpace(zone, [], layout);
    expect(space.totalArea).toBe(inner.width * inner.height);
  });

  it("remainingHeight never goes negative", () => {
    // Element that exceeds the zone
    const existing: PlacedElement[] = [
      makePlacedElement("a", zone, inner.x, inner.y, 200, inner.height + 100),
    ];
    const space = queryFreeSpace(zone, existing, layout);
    expect(space.remainingHeight).toBe(0);
  });
});

// ── allZones ─────────────────────────────────────────────────

describe("allZones", () => {
  it("returns 9 zones", () => {
    expect(allZones()).toHaveLength(9);
  });

  it("returns a fresh array each call", () => {
    const a = allZones();
    const b = allZones();
    expect(a).not.toBe(b);
    expect(a).toEqual(b);
  });

  it("returns zones in reading order (top-left to bottom-right)", () => {
    const zones = allZones();
    expect(zones).toEqual([
      "top-left",
      "top-center",
      "top-right",
      "center-left",
      "center-center",
      "center-right",
      "bottom-left",
      "bottom-center",
      "bottom-right",
    ]);
  });
});
