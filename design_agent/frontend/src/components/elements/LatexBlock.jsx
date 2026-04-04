import React, { useMemo } from "react";
import katex from "katex";

function LatexBlock({ expression, fontSize, displayMode }) {
  const html = useMemo(() => {
    try {
      return katex.renderToString(expression || "", {
        throwOnError: false,
        displayMode: displayMode !== false,
        macros: {
          "\\ce": "\\text{#1}",
        },
      });
    } catch (err) {
      console.warn("KaTeX render error:", err);
      return `<span style="color:#ff6b6b;">${expression || ""}</span>`;
    }
  }, [expression, displayMode]);

  return (
    <div
      className="latex-block"
      dangerouslySetInnerHTML={{ __html: html }}
      style={{
        fontSize: fontSize || "1.2em",
        textAlign: "center",
        padding: "8px 0",
      }}
    />
  );
}

export default LatexBlock;
