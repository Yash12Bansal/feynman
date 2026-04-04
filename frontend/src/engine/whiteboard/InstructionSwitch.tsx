/**
 * Whiteboard-specific instruction router.
 *
 * Routes draw_diagram → RoughDiagramContent (hand-drawn).
 * Routes show_graph → RoughGraphContent (hand-drawn SVG charts).
 * Routes show_text → TextContent (clean HTML, Inter font).
 * All other types fall through to existing clean renderers.
 *
 * Explicitly lists all cases (no delegation to shared InstructionSwitch)
 * to avoid circular imports and keep the upgrade path clear.
 */

import type { VisualInstruction } from "../../types/visuals";
import { RoughDiagramContent } from "./content/RoughDiagramContent";
import { RoughGraphContent } from "./content/RoughGraphContent";
import { DesignDiagramContent } from "./content/DesignDiagramContent";
import { TextContent } from "../content/TextContent";
import { SceneContent } from "./scene/SceneContent";
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
    case "draw_design_diagram":
      return <DesignDiagramContent instruction={instruction} />;
    case "show_text":
      return <TextContent instruction={instruction} />;
    case "show_equation":
      return <EquationContent instruction={instruction} />;
    case "step_equation":
      return <StepEquationContent instruction={instruction} />;
    case "show_graph":
      return <RoughGraphContent instruction={instruction} />;
    case "draw_scene":
      return <SceneContent instruction={instruction} />;
    default:
      return null;
  }
}
