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
}

export function SplitBoard({
  slide,
  notebook,
  mode = "split",
  notebookTitle,
}: SplitBoardProps) {
  return (
    <div className="sb-root" data-mode={mode}>
      <SlidePanel state={slide} />
      <Notebook state={notebook} title={notebookTitle} />
    </div>
  );
}
