import { render } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AliveFilter, ALIVE_FILTER_ID } from "../AliveFilter";

describe("AliveFilter", () => {
  it("renders a hidden SVG with the correct filter ID", () => {
    const { container } = render(<AliveFilter />);
    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
    expect(svg?.getAttribute("aria-hidden")).toBe("true");
    expect(svg?.getAttribute("width")).toBe("0");
    expect(svg?.getAttribute("height")).toBe("0");

    const filter = container.querySelector(`filter#${ALIVE_FILTER_ID}`);
    expect(filter).toBeTruthy();
  });

  it("has feTurbulence with correct params", () => {
    const { container } = render(<AliveFilter />);
    const turbulence = container.querySelector("feTurbulence");
    expect(turbulence).toBeTruthy();
    expect(turbulence?.getAttribute("type")).toBe("fractalNoise");
    expect(turbulence?.getAttribute("baseFrequency")).toBe("0.015");
    expect(turbulence?.getAttribute("numOctaves")).toBe("2");
    expect(turbulence?.getAttribute("seed")).toBe("1");
    expect(turbulence?.getAttribute("result")).toBe("noise");
  });

  it("has feDisplacementMap with correct params", () => {
    const { container } = render(<AliveFilter />);
    const displacement = container.querySelector("feDisplacementMap");
    expect(displacement).toBeTruthy();
    expect(displacement?.getAttribute("in")).toBe("SourceGraphic");
    expect(displacement?.getAttribute("in2")).toBe("noise");
    expect(displacement?.getAttribute("scale")).toBe("3");
    expect(displacement?.getAttribute("xChannelSelector")).toBe("R");
    expect(displacement?.getAttribute("yChannelSelector")).toBe("G");
  });

  it("has SMIL animate with discrete calcMode and 8 seed values", () => {
    const { container } = render(<AliveFilter />);
    const animate = container.querySelector("animate");
    expect(animate).toBeTruthy();
    expect(animate?.getAttribute("attributeName")).toBe("seed");
    expect(animate?.getAttribute("values")).toBe("1;2;3;4;5;6;7;8");
    expect(animate?.getAttribute("dur")).toBe("1.6s");
    expect(animate?.getAttribute("repeatCount")).toBe("indefinite");
    expect(animate?.getAttribute("calcMode")).toBe("discrete");
  });

  it("exports ALIVE_FILTER_ID matching the filter element ID", () => {
    const { container } = render(<AliveFilter />);
    const filter = container.querySelector("filter");
    expect(filter?.id).toBe(ALIVE_FILTER_ID);
    expect(ALIVE_FILTER_ID).toBe("wb-alive");
  });
});
