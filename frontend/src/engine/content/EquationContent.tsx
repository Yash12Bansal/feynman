import type { ShowEquationInstruction } from "../../types/visuals";
import { COLORS, FONTS } from "../theme";

export function EquationContent({
  instruction,
}: {
  instruction: ShowEquationInstruction;
}) {
  return (
    <div>
      {instruction.label && (
        <div
          style={{
            fontSize: 20,
            fontStyle: "italic",
            lineHeight: "28px",
            color: COLORS.accentPurple,
            marginBottom: 12,
          }}
        >
          {instruction.label}
        </div>
      )}
      <div
        data-katex-target=""
        style={{
          textAlign: "center",
          fontSize: 32,
          lineHeight: "44px",
          fontFamily: FONTS.equation,
          color: COLORS.accentAmber,
        }}
      >
        {instruction.latex}
      </div>
    </div>
  );
}
