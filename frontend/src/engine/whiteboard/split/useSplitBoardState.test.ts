/**
 * Phase 3 adapter tests.
 *
 * Pure-function tests — the hook's entire body is a `useMemo` over the
 * instructions array, so we exercise the derivation by rendering the hook
 * with @testing-library's `renderHook`.
 */

import { describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";
import { useSplitBoardState } from "./useSplitBoardState";
import type {
  AnnotateInstruction,
  DrawDesignDiagramInstruction,
  DrawDiagramInstruction,
  HighlightInstruction,
  NewPageInstruction,
  ShowEquationInstruction,
  ShowGraphInstruction,
  ShowTextInstruction,
  StepEquationInstruction,
  StrikethroughInstruction,
  VisualInstruction,
  WriteAnswerInstruction,
  WriteEquationInstruction,
  WriteSectionInstruction,
  WriteStepInstruction,
  WriteTextInstruction,
} from "../../../types/visuals";

function eq(
  latex: string,
  extra: Partial<ShowEquationInstruction> = {},
): ShowEquationInstruction {
  return { type: "show_equation", latex, panel: "notebook", ...extra };
}

function txt(
  text: string,
  extra: Partial<ShowTextInstruction> = {},
): ShowTextInstruction {
  return { type: "show_text", text, panel: "notebook", ...extra };
}

function stepEq(
  steps: { latex: string }[],
  extra: Partial<StepEquationInstruction> = {},
): StepEquationInstruction {
  return {
    type: "step_equation",
    steps,
    panel: "notebook",
    ...extra,
  };
}

function graph(
  extra: Partial<ShowGraphInstruction> = {},
): ShowGraphInstruction {
  return {
    type: "show_graph",
    graph_type: "line",
    series: [{ label: "s", points: [{ x: 0, y: 0 }] }],
    panel: "notebook",
    ...extra,
  };
}

function designDiagram(
  id: string,
  extra: Partial<DrawDesignDiagramInstruction> = {},
): DrawDesignDiagramInstruction {
  return {
    type: "draw_design_diagram",
    spec: { title: id, elements: [] },
    element_id: id,
    panel: "slide",
    ...extra,
  };
}

function diagram(
  extra: Partial<DrawDiagramInstruction> = {},
): DrawDiagramInstruction {
  return {
    type: "draw_diagram",
    nodes: [{ id: "n1", label: "A" }],
    panel: "slide",
    ...extra,
  };
}

// ── Phase 5 helpers: notebook write-tool instruction builders ──

function writeEq(
  latex: string,
  extra: Partial<WriteEquationInstruction> = {},
): WriteEquationInstruction {
  return { type: "write_equation", latex, panel: "notebook", ...extra };
}

function writeStep(
  text: string,
  extra: Partial<WriteStepInstruction> = {},
): WriteStepInstruction {
  return { type: "write_step", text, panel: "notebook", ...extra };
}

function writeTextInstr(
  text: string,
  extra: Partial<WriteTextInstruction> = {},
): WriteTextInstruction {
  return { type: "write_text", text, panel: "notebook", ...extra };
}

function writeSection(
  title: string,
  extra: Partial<WriteSectionInstruction> = {},
): WriteSectionInstruction {
  return { type: "write_section", title, panel: "notebook", ...extra };
}

function writeAnswer(
  extra: Partial<WriteAnswerInstruction> = {},
): WriteAnswerInstruction {
  return { type: "write_answer", panel: "notebook", ...extra };
}

function strike(target_id: string): StrikethroughInstruction {
  return { type: "strikethrough", target_id, panel: "notebook" };
}

function newPage(carry_forward_ids?: readonly string[]): NewPageInstruction {
  const instr: NewPageInstruction = { type: "new_page", panel: "notebook" };
  if (carry_forward_ids !== undefined) {
    return { ...instr, carry_forward_ids };
  }
  return instr;
}

describe("useSplitBoardState", () => {
  it("returns empty slide + notebook when no instructions", () => {
    const { result } = renderHook(() => useSplitBoardState([]));
    expect(result.current.slide.status).toBe("empty");
    expect(result.current.slide.liveInstruction).toBeUndefined();
    expect(result.current.notebook.page.entries).toHaveLength(0);
    expect(result.current.notebook.page.pageNum).toBe(1);
  });

  it("maps a single show_equation to one equation entry", () => {
    const { result } = renderHook(() =>
      useSplitBoardState([eq("F = ma", { element_id: "e1" })]),
    );
    expect(result.current.slide.status).toBe("empty");
    const entries = result.current.notebook.page.entries;
    expect(entries).toHaveLength(1);
    expect(entries[0].kind).toBe("equation");
    if (entries[0].kind === "equation") {
      expect(entries[0].latex).toBe("F = ma");
    }
  });

  it("routes a draw_design_diagram to slide, not notebook", () => {
    const instr = designDiagram("d1");
    const { result } = renderHook(() => useSplitBoardState([instr]));
    expect(result.current.slide.status).toBe("ready");
    expect(result.current.slide.liveInstruction).toBe(instr);
    expect(result.current.notebook.page.entries).toHaveLength(0);
  });

  it("keeps only the latest slide instruction (latest-wins)", () => {
    const a = designDiagram("d1");
    const b = designDiagram("d2");
    const { result } = renderHook(() => useSplitBoardState([a, b]));
    expect(result.current.slide.liveInstruction).toBe(b);
  });

  it("expands step_equation with title into section_header + N step equations", () => {
    const s = stepEq(
      [{ latex: "a" }, { latex: "b" }, { latex: "c" }],
      { title: "Solve", element_id: "s1" },
    );
    const { result } = renderHook(() => useSplitBoardState([s]));
    const entries = result.current.notebook.page.entries;
    expect(entries).toHaveLength(4);
    expect(entries[0].kind).toBe("section_header");
    if (entries[0].kind === "section_header") {
      expect(entries[0].title).toBe("Solve");
    }
    expect(entries[1].kind).toBe("equation");
    expect(entries[2].kind).toBe("equation");
    expect(entries[3].kind).toBe("equation");
  });

  it("maps show_graph to a graph entry carrying the instruction", () => {
    const g = graph({ element_id: "g1", title: "speed vs. time" });
    const { result } = renderHook(() => useSplitBoardState([g]));
    const entries = result.current.notebook.page.entries;
    expect(entries).toHaveLength(1);
    expect(entries[0].kind).toBe("graph");
    if (entries[0].kind === "graph") {
      expect(entries[0].instr).toBe(g);
    }
  });

  it("infers panel by type when the field is missing (type-based fallback)", () => {
    const textWithoutPanel: VisualInstruction = {
      type: "show_text",
      text: "hello",
      // no panel field
    } as ShowTextInstruction;
    const diagWithoutPanel: VisualInstruction = diagram({ panel: undefined });

    const { result } = renderHook(() =>
      useSplitBoardState([textWithoutPanel, diagWithoutPanel]),
    );
    expect(result.current.slide.status).toBe("ready");
    expect(result.current.slide.liveInstruction).toBe(diagWithoutPanel);
    expect(result.current.notebook.page.entries).toHaveLength(1);
    expect(result.current.notebook.page.entries[0].kind).toBe("text");
  });

  it("drops reference instructions (highlight, annotate) from both panels", () => {
    const highlight: HighlightInstruction = {
      type: "highlight",
      target_id: "e1",
      panel: "reference",
    };
    const annotate: AnnotateInstruction = {
      type: "annotate",
      action: "circle",
      target_id: "e1",
      panel: "reference",
    };
    const e = eq("E = mc^2");
    const { result } = renderHook(() =>
      useSplitBoardState([e, highlight, annotate]),
    );
    expect(result.current.slide.status).toBe("empty");
    expect(result.current.notebook.page.entries).toHaveLength(1);
    expect(result.current.notebook.page.entries[0].kind).toBe("equation");
  });

  it("maps show_text style=key_point to a key_point entry", () => {
    const t = txt("Newton's Second Law governs motion.", {
      style: "key_point",
      element_id: "t1",
    });
    const { result } = renderHook(() => useSplitBoardState([t]));
    const entries = result.current.notebook.page.entries;
    expect(entries).toHaveLength(1);
    expect(entries[0].kind).toBe("key_point");
  });

  it("maps show_text style=definition to section_header + text entries", () => {
    const t = txt("A vector is a quantity with magnitude and direction.", {
      title: "Vector",
      style: "definition",
      element_id: "t1",
    });
    const { result } = renderHook(() => useSplitBoardState([t]));
    const entries = result.current.notebook.page.entries;
    expect(entries).toHaveLength(2);
    expect(entries[0].kind).toBe("section_header");
    expect(entries[1].kind).toBe("text");
  });

  // ── Phase 4: loading state ──────────────────────────────

  it("surfaces loading status when pending is set and no slide instructions", () => {
    const { result } = renderHook(() =>
      useSplitBoardState([], { title: "Newton's 2nd Law" }),
    );
    expect(result.current.slide.status).toBe("loading");
    expect(result.current.slide.pendingTitle).toBe("Newton's 2nd Law");
    expect(result.current.slide.liveInstruction).toBeUndefined();
  });

  it("ignores pending when a slide instruction has already arrived", () => {
    const instr = designDiagram("d1");
    const { result } = renderHook(() =>
      useSplitBoardState([instr], { title: "stale loader title" }),
    );
    // A real slide trumps any leftover pending — the loader should not show.
    expect(result.current.slide.status).toBe("ready");
    expect(result.current.slide.liveInstruction).toBe(instr);
  });

  it("returns empty (not loading) when no pending and no slide instructions", () => {
    // Phase 3 baseline preserved: no pending → empty, not loading.
    const { result } = renderHook(() => useSplitBoardState([]));
    expect(result.current.slide.status).toBe("empty");
    expect(result.current.slide.pendingTitle).toBeUndefined();
  });

  // ── Phase 5: notebook write-tool mappings ───────────────

  it("maps write_equation to an equation entry with align_group and indent", () => {
    const w = writeEq("F = m a", {
      element_id: "e1",
      align_group: "g1",
      indent: 1,
    });
    const { result } = renderHook(() => useSplitBoardState([w]));
    const entries = result.current.notebook.page.entries;
    expect(entries).toHaveLength(1);
    expect(entries[0].kind).toBe("equation");
    if (entries[0].kind === "equation") {
      expect(entries[0].latex).toBe("F = m a");
      expect(entries[0].alignGroup).toBe("g1");
      expect(entries[0].indent).toBe(1);
    }
  });

  it("maps write_step to a step entry with number and indent", () => {
    const w = writeStep("Solve for a", {
      element_id: "s1",
      number: 2,
      indent: 1,
    });
    const { result } = renderHook(() => useSplitBoardState([w]));
    const entries = result.current.notebook.page.entries;
    expect(entries).toHaveLength(1);
    expect(entries[0].kind).toBe("step");
    if (entries[0].kind === "step") {
      expect(entries[0].text).toBe("Solve for a");
      expect(entries[0].number).toBe(2);
      expect(entries[0].indent).toBe(1);
    }
  });

  it("maps write_text default style to a text entry", () => {
    const w = writeTextInstr("Remember this", {
      element_id: "t1",
      style: "default",
    });
    const { result } = renderHook(() => useSplitBoardState([w]));
    const entries = result.current.notebook.page.entries;
    expect(entries).toHaveLength(1);
    expect(entries[0].kind).toBe("text");
  });

  it("maps write_text style=key_point to a key_point entry", () => {
    const w = writeTextInstr("Key idea", {
      element_id: "t2",
      style: "key_point",
    });
    const { result } = renderHook(() => useSplitBoardState([w]));
    const entries = result.current.notebook.page.entries;
    expect(entries).toHaveLength(1);
    expect(entries[0].kind).toBe("key_point");
  });

  it("maps write_section to a section_header entry", () => {
    const w = writeSection("Newton's Second Law", { element_id: "h1" });
    const { result } = renderHook(() => useSplitBoardState([w]));
    const entries = result.current.notebook.page.entries;
    expect(entries).toHaveLength(1);
    expect(entries[0].kind).toBe("section_header");
    if (entries[0].kind === "section_header") {
      expect(entries[0].title).toBe("Newton's Second Law");
    }
  });

  it("maps write_answer (latex) to a boxed answer entry", () => {
    const w = writeAnswer({ element_id: "a1", latex: "a = 5" });
    const { result } = renderHook(() => useSplitBoardState([w]));
    const entries = result.current.notebook.page.entries;
    expect(entries).toHaveLength(1);
    expect(entries[0].kind).toBe("answer");
    if (entries[0].kind === "answer") {
      expect(entries[0].latex).toBe("a = 5");
      expect(entries[0].boxed).toBe(true);
    }
  });

  it("maps write_answer (text) to a boxed answer entry with text", () => {
    const w = writeAnswer({ element_id: "a2", text: "pH = 7.0" });
    const { result } = renderHook(() => useSplitBoardState([w]));
    const entries = result.current.notebook.page.entries;
    expect(entries).toHaveLength(1);
    if (entries[0].kind === "answer") {
      expect(entries[0].text).toBe("pH = 7.0");
    }
  });

  it("segments entries by page on new_page — only current page renders", () => {
    const first = writeEq("x = 1", { element_id: "e1" });
    const second = writeEq("y = 2", { element_id: "e2" });
    const { result } = renderHook(() =>
      useSplitBoardState([first, newPage(), second]),
    );
    expect(result.current.notebook.page.pageNum).toBe(2);
    const entries = result.current.notebook.page.entries;
    expect(entries).toHaveLength(1);
    if (entries[0].kind === "equation") {
      expect(entries[0].latex).toBe("y = 2");
    }
  });

  it("applies strikethrough to a matching entry on the current page", () => {
    const wrong = writeEq("a = 10/4", { element_id: "bad-1" });
    const right = writeEq("a = 5", { element_id: "good-1" });
    const { result } = renderHook(() =>
      useSplitBoardState([wrong, strike("bad-1"), right]),
    );
    const entries = result.current.notebook.page.entries;
    expect(entries).toHaveLength(2);
    const struckEntry = entries.find((e) => e.id === "bad-1");
    const unstruckEntry = entries.find((e) => e.id === "good-1");
    expect(struckEntry?.struck).toBe(true);
    expect(unstruckEntry?.struck).toBeFalsy();
  });

  it("retains pageNum=1 when no new_page arrives (Phase 5 default behavior)", () => {
    const w = writeEq("x = 1", { element_id: "e1" });
    const { result } = renderHook(() => useSplitBoardState([w]));
    expect(result.current.notebook.page.pageNum).toBe(1);
  });

  // ── Phase 6: carry-forward reminders ───────────────────

  it("synthesizes a carried copy at the top of the next page", () => {
    const first = writeEq("F = m a", { element_id: "eq-1" });
    const second = writeEq("a = 5", { element_id: "eq-2" });
    const { result } = renderHook(() =>
      useSplitBoardState([first, newPage(["eq-1"]), second]),
    );
    const entries = result.current.notebook.page.entries;
    // Page 2 shows the carried reminder first, then the new equation.
    expect(entries).toHaveLength(2);
    expect(entries[0].carriedForward).toBe(true);
    expect(entries[0].id).toBe("eq-1__carried__p2");
    expect(entries[0].kind).toBe("equation");
    if (entries[0].kind === "equation") {
      expect(entries[0].latex).toBe("F = m a");
    }
    expect(entries[1].carriedForward).toBeFalsy();
    expect(entries[1].id).toBe("eq-2");
  });

  it("carried copy reflects the struck state of the original", () => {
    const orig = writeEq("wrong", { element_id: "bad" });
    const { result } = renderHook(() =>
      useSplitBoardState([orig, strike("bad"), newPage(["bad"])]),
    );
    const entries = result.current.notebook.page.entries;
    const carried = entries.find((e) => e.carriedForward);
    expect(carried).toBeDefined();
    expect(carried?.struck).toBe(true);
    // The carried copy's derived id is not itself a strikethrough target —
    // it only mirrors the original's struck flag.
    expect(carried?.id).toBe("bad__carried__p2");
  });

  it("silently drops carry_forward_ids that don't match any prior entry", () => {
    const { result } = renderHook(() =>
      useSplitBoardState([newPage(["ghost"])]),
    );
    expect(result.current.notebook.page.pageNum).toBe(2);
    expect(result.current.notebook.page.entries).toHaveLength(0);
  });
});
