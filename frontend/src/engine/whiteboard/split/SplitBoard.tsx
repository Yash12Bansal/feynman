/**
 * Composition of Slide + Notebook into a split-panel board.
 *
 * Mode switches (split / slide_full / notebook_full) are driven entirely by
 * a CSS data-attribute and CSS transitions — no JS animation needed.
 */

import "./SplitBoard.css";
import type { NotebookState, PanelMode, SlideState } from "./types";
import { SlidePanel } from "./SlidePanel";
import { Notebook } from "./Notebook";

interface SplitBoardProps {
  readonly slide: SlideState;
  readonly notebook: NotebookState;
  readonly mode?: PanelMode;
  readonly notebookTitle?: string;
  /**
   * "preview" pins the board to fixed 1600×900 dimensions and absolute
   * child sizes so it matches the Phase 3 precompute layout pipeline's
   * measured placements byte-for-byte. The default "responsive" mode is
   * the live agent path (flex-fractional).
   */
  readonly viewport?: "responsive" | "preview";
  /**
   * Workstream A4: when true, design diagrams expose draggable parameter
   * sliders (an interactive playground surface). Lecture/doubt playback omits
   * it — parameters are driven by `set_parameter` events, not the student.
   */
  readonly interactive?: boolean;
}

export function SplitBoard({
  slide,
  notebook,
  mode = "split",
  notebookTitle,
  viewport = "responsive",
  interactive,
}: SplitBoardProps) {
  const className =
    viewport === "preview" ? "sb-root sb-root--preview" : "sb-root";
  return (
    <div className={className} data-mode={mode}>
      <SlidePanel state={slide} interactive={interactive} />
      <Notebook state={notebook} title={notebookTitle} />
    </div>
  );
}
