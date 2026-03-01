import { describe, it, expect } from "vitest";
import { viewportToBoard } from "../board-coords";

function makeDOMRect(
  x: number,
  y: number,
  width: number,
  height: number,
): DOMRect {
  return {
    x,
    y,
    width,
    height,
    left: x,
    top: y,
    right: x + width,
    bottom: y + height,
    toJSON: () => ({}),
  };
}

describe("viewportToBoard", () => {
  it("converts at scale 1 with no offset", () => {
    const elRect = makeDOMRect(100, 200, 300, 50);
    const boardRect = makeDOMRect(0, 0, 1920, 1080);
    const result = viewportToBoard(elRect, boardRect, 1);

    expect(result.x).toBe(100);
    expect(result.y).toBe(200);
    expect(result.width).toBe(300);
    expect(result.height).toBe(50);
  });

  it("converts at scale 0.5", () => {
    // Element at viewport (50, 100) with board at (0, 0) and scale 0.5
    const elRect = makeDOMRect(50, 100, 150, 25);
    const boardRect = makeDOMRect(0, 0, 960, 540);
    const result = viewportToBoard(elRect, boardRect, 0.5);

    expect(result.x).toBe(100); // 50 / 0.5
    expect(result.y).toBe(200); // 100 / 0.5
    expect(result.width).toBe(300); // 150 / 0.5
    expect(result.height).toBe(50); // 25 / 0.5
  });

  it("accounts for board offset", () => {
    // Board is offset 100px from left, 50px from top
    const elRect = makeDOMRect(200, 150, 100, 40);
    const boardRect = makeDOMRect(100, 50, 1920, 1080);
    const result = viewportToBoard(elRect, boardRect, 1);

    expect(result.x).toBe(100); // 200 - 100
    expect(result.y).toBe(100); // 150 - 50
    expect(result.width).toBe(100);
    expect(result.height).toBe(40);
  });
});
