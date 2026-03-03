import { describe, it, expect, beforeEach } from "vitest";
import {
  registerStrategy,
  getStrategy,
  listStrategies,
  _resetStrategies,
} from "../layout/registry";
import type { LayoutStrategy } from "../layout/types";
import type { SceneGeometry } from "../scene-types";

const stubStrategy: LayoutStrategy = (): SceneGeometry => ({
  paths: [],
  labels: [],
  bounds: { x: 0, y: 0, width: 0, height: 0 },
});

describe("strategy registry", () => {
  beforeEach(() => {
    _resetStrategies();
  });

  it("registers and retrieves a strategy", () => {
    registerStrategy("test_scene", stubStrategy);

    expect(getStrategy("test_scene")).toBe(stubStrategy);
  });

  it("returns undefined for unknown scene_type", () => {
    expect(getStrategy("nonexistent")).toBeUndefined();
  });

  it("throws on duplicate registration", () => {
    registerStrategy("dupe", stubStrategy);

    expect(() => registerStrategy("dupe", stubStrategy)).toThrowError(
      /already registered/,
    );
  });

  it("_resetStrategies clears all registrations", () => {
    registerStrategy("a", stubStrategy);
    registerStrategy("b", stubStrategy);
    expect(listStrategies()).toHaveLength(2);

    _resetStrategies();

    expect(listStrategies()).toHaveLength(0);
    expect(getStrategy("a")).toBeUndefined();
  });

  it("listStrategies returns all registered scene types", () => {
    registerStrategy("alpha", stubStrategy);
    registerStrategy("beta", stubStrategy);

    const types = listStrategies();
    expect(types).toContain("alpha");
    expect(types).toContain("beta");
    expect(types).toHaveLength(2);
  });

  it("allows re-registration after reset", () => {
    registerStrategy("re-reg", stubStrategy);
    _resetStrategies();

    registerStrategy("re-reg", stubStrategy);
    expect(getStrategy("re-reg")).toBe(stubStrategy);
  });
});
