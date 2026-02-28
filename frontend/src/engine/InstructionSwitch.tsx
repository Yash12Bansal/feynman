import type { VisualInstruction } from "../types/visuals";
import { TextContent } from "./content/TextContent";
import { EquationContent } from "./content/EquationContent";
import { StepEquationContent } from "./content/StepEquationContent";
import { DiagramContent } from "./content/DiagramContent";
import { GraphContent } from "./content/GraphContent";

export function InstructionSwitch({
  instruction,
}: {
  instruction: VisualInstruction;
}) {
  switch (instruction.type) {
    case "show_text":
      return <TextContent instruction={instruction} />;
    case "show_equation":
      return <EquationContent instruction={instruction} />;
    case "step_equation":
      return <StepEquationContent instruction={instruction} />;
    case "draw_diagram":
      return <DiagramContent instruction={instruction} />;
    case "show_graph":
      return <GraphContent instruction={instruction} />;
    default:
      return null;
  }
}
