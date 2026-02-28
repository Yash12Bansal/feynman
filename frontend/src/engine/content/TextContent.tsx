import type { ShowTextInstruction, TextStyle } from "../../types/visuals";
import { COLORS } from "../theme";

const STYLE_ACCENTS: Record<TextStyle, string> = {
  default: COLORS.accentBlue,
  definition: COLORS.accentBlue,
  key_point: COLORS.accentAmber,
  example: COLORS.accentGreen,
};

export function TextContent({
  instruction,
}: {
  instruction: ShowTextInstruction;
}) {
  const style = instruction.style ?? "default";
  const accent = STYLE_ACCENTS[style];

  return (
    <div>
      {instruction.title && (
        <h3
          style={{
            margin: 0,
            marginBottom: 8,
            fontSize: 34,
            fontWeight: 700,
            lineHeight: "44px",
            color: accent,
          }}
        >
          {instruction.title}
        </h3>
      )}
      <p
        style={{
          margin: 0,
          fontSize: 24,
          lineHeight: "36px",
          color: COLORS.textPrimary,
        }}
      >
        {instruction.text}
      </p>
    </div>
  );
}
