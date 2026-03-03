import { describe, it, expect, beforeEach } from "vitest";
import {
  registerComponent,
  getComponent,
  hasComponent,
  listComponents,
  _resetRegistry,
} from "../components/registry";
import type { ComponentDef } from "../components/types";
import type { SceneGeometry } from "../scene-types";

/** Minimal stub component for testing the registry. */
function makeStubDef(kind: string): ComponentDef {
  return {
    kind,
    render: (): SceneGeometry => ({
      paths: [],
      labels: [],
      bounds: { x: 0, y: 0, width: 0, height: 0 },
    }),
    anchorNames: ["center"],
  };
}

describe("component registry", () => {
  beforeEach(() => {
    _resetRegistry();
  });

  it("registers and retrieves a component", () => {
    const def = makeStubDef("test-comp");
    registerComponent(def);

    expect(getComponent("test-comp")).toBe(def);
  });

  it("hasComponent returns true for registered kinds", () => {
    registerComponent(makeStubDef("alpha"));

    expect(hasComponent("alpha")).toBe(true);
  });

  it("hasComponent returns false for unregistered kinds", () => {
    expect(hasComponent("nonexistent")).toBe(false);
  });

  it("getComponent returns undefined for unknown kind", () => {
    expect(getComponent("unknown")).toBeUndefined();
  });

  it("listComponents returns all registered kinds", () => {
    registerComponent(makeStubDef("aaa"));
    registerComponent(makeStubDef("bbb"));
    registerComponent(makeStubDef("ccc"));

    const kinds = listComponents();
    expect(kinds).toContain("aaa");
    expect(kinds).toContain("bbb");
    expect(kinds).toContain("ccc");
    expect(kinds).toHaveLength(3);
  });

  it("listComponents returns empty array when registry is empty", () => {
    expect(listComponents()).toHaveLength(0);
  });

  it("throws on duplicate registration", () => {
    registerComponent(makeStubDef("dupe"));

    expect(() => registerComponent(makeStubDef("dupe"))).toThrowError(
      /already registered/,
    );
  });

  it("_resetRegistry clears all registrations", () => {
    registerComponent(makeStubDef("x"));
    registerComponent(makeStubDef("y"));
    expect(listComponents()).toHaveLength(2);

    _resetRegistry();

    expect(listComponents()).toHaveLength(0);
    expect(hasComponent("x")).toBe(false);
  });

  it("allows re-registration after reset", () => {
    registerComponent(makeStubDef("re-reg"));
    _resetRegistry();

    // Should not throw after reset
    registerComponent(makeStubDef("re-reg"));
    expect(hasComponent("re-reg")).toBe(true);
  });
});
