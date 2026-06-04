import { describe, it, expect } from "vitest";
import {
  resolveTarget,
  parseTargetString,
  roleGroupForElement,
} from "../resolveTarget";
import type {
  DesignDiagramElement,
  ElementMeta,
} from "../../../../types/visuals";

const dictionary: Record<string, ElementMeta> = {
  v1: { role: "vector", semantic: "force A", position: "center" },
  v2: { role: "vector", semantic: "force B", position: "center" },
  axis: { role: "axis", semantic: "x axis", position: "bottom" },
};

const elements: DesignDiagramElement[] = [
  {
    type: "svg_arrow",
    id: "v1",
    x1: 0,
    y1: 0,
    x2: 10,
    y2: 0,
    stroke: "#7fd4ff",
  },
  {
    type: "svg_arrow",
    id: "v2",
    x1: 0,
    y1: 0,
    x2: 0,
    y2: 10,
    stroke: "#9effc9",
  },
  { type: "svg_text", id: "label", x: 5, y: 5, text: "resultant velocity" },
];

describe("resolveTarget", () => {
  it("id → the id verbatim", () => {
    expect(
      resolveTarget({ kind: "id", value: "v1" }, dictionary, elements),
    ).toEqual(["v1"]);
  });

  it("role → all element ids with that role", () => {
    expect(
      resolveTarget(
        { kind: "role", value: "vector" },
        dictionary,
        elements,
      ).sort(),
    ).toEqual(["v1", "v2"]);
  });

  it("role with no dictionary → []", () => {
    expect(
      resolveTarget({ kind: "role", value: "vector" }, undefined, elements),
    ).toEqual([]);
  });

  it("color → ids whose stroke/fill match", () => {
    expect(
      resolveTarget({ kind: "color", value: "#9effc9" }, dictionary, elements),
    ).toEqual(["v2"]);
  });

  it("near_text → text elements containing the substring", () => {
    expect(
      resolveTarget(
        { kind: "near_text", value: "velocity" },
        dictionary,
        elements,
      ),
    ).toEqual(["label"]);
  });

  it("data_attr → [] (DOM layer handles it)", () => {
    expect(
      resolveTarget(
        { kind: "data_attr", value: "x", attr: "foo" },
        dictionary,
        elements,
      ),
    ).toEqual([]);
  });

  it("recurses into svg_group children", () => {
    const grouped: DesignDiagramElement[] = [
      {
        type: "svg_group",
        id: "g",
        elements: [
          { type: "svg_text", id: "inner", x: 0, y: 0, text: "hidden gem" },
        ],
      },
    ];
    expect(
      resolveTarget({ kind: "near_text", value: "gem" }, dictionary, grouped),
    ).toEqual(["inner"]);
  });
});

describe("parseTargetString", () => {
  it("parses role:/id:/color:/near_text: prefixes", () => {
    expect(parseTargetString("role:vector")).toEqual({
      kind: "role",
      value: "vector",
    });
    expect(parseTargetString("id:foo")).toEqual({ kind: "id", value: "foo" });
    expect(parseTargetString("color:#fff")).toEqual({
      kind: "color",
      value: "#fff",
    });
  });

  it("treats a bare string as an id", () => {
    expect(parseTargetString("foo")).toEqual({ kind: "id", value: "foo" });
  });

  it("treats an unknown prefix as a literal id", () => {
    expect(parseTargetString("fill:#fff")).toEqual({
      kind: "id",
      value: "fill:#fff",
    });
  });
});

describe("roleGroupForElement", () => {
  it("returns all siblings sharing the focused element's role", () => {
    expect(roleGroupForElement("v1", dictionary).sort()).toEqual(["v1", "v2"]);
  });

  it("falls back to [id] when there is no dictionary entry", () => {
    expect(roleGroupForElement("unknown", dictionary)).toEqual(["unknown"]);
    expect(roleGroupForElement("v1", undefined)).toEqual(["v1"]);
  });
});
