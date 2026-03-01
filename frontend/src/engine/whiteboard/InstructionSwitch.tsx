/**
 * Whiteboard-specific instruction router.
 *
 * Routes draw_diagram → RoughDiagramContent (hand-drawn).
 * Routes show_graph → RoughGraphContent (hand-drawn SVG charts).
 * All other types fall through to existing clean renderers.
 *
 * Explicitly lists all cases (no delegation to shared InstructionSwitch)
 * to avoid circular imports and keep the upgrade path clear for future
 * rough renderers (Phase 7: handwritten text, etc.).
 */

import type { VisualInstruction } from "../../types/visuals";
import { RoughDiagramContent } from "./content/RoughDiagramContent";
import { RoughGraphContent } from "./content/RoughGraphContent";
import { TextContent } from "../content/TextContent";
import { EquationContent } from "../content/EquationContent";
import { StepEquationContent } from "../content/StepEquationContent";

export function InstructionSwitch({
  instruction,
}: {
  instruction: VisualInstruction;
}) {
  switch (instruction.type) {
    case "draw_diagram":
      return <RoughDiagramContent instruction={instruction} />;
    case "show_text":
      return <TextContent instruction={instruction} />;
    case "show_equation":
      return <EquationContent instruction={instruction} />;
    case "step_equation":
      return <StepEquationContent instruction={instruction} />;
    case "show_graph":
      return <RoughGraphContent instruction={instruction} />;
    default:
      return null;
  }
}
