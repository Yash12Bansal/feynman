/**
 * Renders a design-agent-generated DiagramSpec as SVG + KaTeX overlays.
 *
 * All SVG elements get `data-design-element={id}` for highlight walk support.
 * KaTeX (svg_latex) elements are rendered as absolutely-positioned HTML overlays
 * outside the SVG to avoid foreignObject issues.
 *
 * Supports interactive parameters (slider-driven coordinate expressions) and
 * inset graph elements with axes and curve rendering.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import katex from "katex";
import type {
  DrawDesignDiagramInstruction,
  DesignDiagramElement,
  DesignDiagramSpec,
  DiagramCoord,
  DesignDiagramGraph,
} from "../../../types/visuals";

// ── Math expression evaluator ──────────────────────────────

const MATH_CONTEXT =
  "const {sin,cos,tan,sqrt,abs,PI,E,log,exp,pow,floor,ceil,min,max,atan2,asin,acos,sinh,cosh,tanh}=Math;";

function evalMathExpr(
  expr: string,
  vars: Record<string, number>,
): number {
  try {
    const keys = Object.keys(vars);
    const vals = Object.values(vars);
    // eslint-disable-next-line no-new-func
    const fn = new Function(...keys, `${MATH_CONTEXT}return ${expr};`);
    return fn(...vals) as number;
  } catch {
    return NaN;
  }
}

function resolveValue(
  val: DiagramCoord | undefined,
  params: Record<string, number>,
  fallback = 0,
): number {
  if (val === undefined || val === null) return fallback;
  if (typeof val === "number") return val;
  const result = evalMathExpr(val, params);
  return isNaN(result) ? fallback : result;
}

// ── Arc path helper ────────────────────────────────────────

function arcPath(
  cx: number,
  cy: number,
  r: number,
  startDeg: number,
  endDeg: number,
): string {
  const startRad = (startDeg * Math.PI) / 180;
  const endRad = (endDeg * Math.PI) / 180;
  const x1 = cx + r * Math.cos(startRad);
  const y1 = cy + r * Math.sin(startRad);
  const x2 = cx + r * Math.cos(endRad);
  const y2 = cy + r * Math.sin(endRad);
  const largeArc = Math.abs(endDeg - startDeg) > 180 ? 1 : 0;
  const sweep = endDeg > startDeg ? 1 : 0;
  return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} ${sweep} ${x2} ${y2}`;
}

// ── Graph element (native SVG) ─────────────────────────────

function GraphInset({
  el,
  params,
}: {
  el: DesignDiagramGraph;
  params: Record<string, number>;
}) {
  const x = resolveValue(el.x, params);
  const y = resolveValue(el.y, params);
  const w = resolveValue(el.width, params, 300);
  const h = resolveValue(el.height, params, 200);
  const margin = { top: 10, right: 10, bottom: 35, left: 45 };
  const innerW = w - margin.left - margin.right;
  const innerH = h - margin.top - margin.bottom;

  const xDomain = el.xDomain ?? [-10, 10];
  const yDomain = el.yDomain ?? [-10, 10];

  const scaleX = (v: number) =>
    ((v - xDomain[0]) / (xDomain[1] - xDomain[0])) * innerW;
  const scaleY = (v: number) =>
    innerH - ((v - yDomain[0]) / (yDomain[1] - yDomain[0])) * innerH;

  // Grid lines
  const gridLines = useMemo(() => {
    const lines: { x1: number; y1: number; x2: number; y2: number; axis: string }[] = [];
    const xTicks = 5;
    const yTicks = 5;
    for (let i = 0; i <= xTicks; i++) {
      const v = xDomain[0] + (i / xTicks) * (xDomain[1] - xDomain[0]);
      const px = scaleX(v);
      lines.push({ x1: px, y1: 0, x2: px, y2: innerH, axis: "x" });
    }
    for (let i = 0; i <= yTicks; i++) {
      const v = yDomain[0] + (i / yTicks) * (yDomain[1] - yDomain[0]);
      const py = scaleY(v);
      lines.push({ x1: 0, y1: py, x2: innerW, y2: py, axis: "y" });
    }
    return lines;
  }, [xDomain, yDomain, innerW, innerH]);

  // Curve paths
  const curvePaths = useMemo(() => {
    return (el.curves ?? []).map((curve) => {
      const points: { x: number; y: number }[] = [];
      const numSamples = 200;
      for (let i = 0; i <= numSamples; i++) {
        const xVal =
          xDomain[0] + (i / numSamples) * (xDomain[1] - xDomain[0]);
        const yVal = evalMathExpr(curve.expression, { x: xVal, ...params });
        if (isFinite(yVal)) {
          points.push({ x: scaleX(xVal), y: scaleY(yVal) });
        }
      }
      const d = points
        .map((p, idx) => `${idx === 0 ? "M" : "L"} ${p.x} ${p.y}`)
        .join(" ");
      return { d, color: curve.color ?? "steelblue", strokeWidth: curve.strokeWidth ?? 2 };
    });
  }, [el.curves, xDomain, yDomain, params, innerW, innerH]);

  // Axis tick labels
  const xTickLabels = useMemo(() => {
    const labels: { value: string; x: number }[] = [];
    for (let i = 0; i <= 5; i++) {
      const v = xDomain[0] + (i / 5) * (xDomain[1] - xDomain[0]);
      labels.push({ value: Number.isInteger(v) ? String(v) : v.toFixed(1), x: scaleX(v) });
    }
    return labels;
  }, [xDomain, innerW]);

  const yTickLabels = useMemo(() => {
    const labels: { value: string; y: number }[] = [];
    for (let i = 0; i <= 5; i++) {
      const v = yDomain[0] + (i / 5) * (yDomain[1] - yDomain[0]);
      labels.push({ value: Number.isInteger(v) ? String(v) : v.toFixed(1), y: scaleY(v) });
    }
    return labels;
  }, [yDomain, innerH]);

  return (
    <g
      transform={`translate(${x}, ${y})`}
      data-design-element={el.id ?? undefined}
    >
      <rect
        width={w}
        height={h}
        fill={el.backgroundColor ?? "#f9f9f9"}
        stroke={el.borderColor ?? "#ccc"}
        rx={2}
      />
      <g transform={`translate(${margin.left}, ${margin.top})`}>
        {el.showGrid !== false &&
          gridLines.map((line, i) => (
            <line
              key={`grid-${i}`}
              x1={line.x1}
              y1={line.y1}
              x2={line.x2}
              y2={line.y2}
              stroke="#e0e0e0"
              strokeWidth={0.5}
            />
          ))}
        {/* X axis */}
        <line x1={0} y1={innerH} x2={innerW} y2={innerH} stroke="#333" strokeWidth={1} />
        {xTickLabels.map((t, i) => (
          <text
            key={`xtick-${i}`}
            x={t.x}
            y={innerH + 14}
            textAnchor="middle"
            fontSize={10}
            fill="#666"
          >
            {t.value}
          </text>
        ))}
        {el.xLabel && (
          <text
            x={innerW / 2}
            y={innerH + 28}
            textAnchor="middle"
            fontSize={11}
            fill="#333"
          >
            {el.xLabel}
          </text>
        )}
        {/* Y axis */}
        <line x1={0} y1={0} x2={0} y2={innerH} stroke="#333" strokeWidth={1} />
        {yTickLabels.map((t, i) => (
          <text
            key={`ytick-${i}`}
            x={-8}
            y={t.y}
            textAnchor="end"
            dominantBaseline="central"
            fontSize={10}
            fill="#666"
          >
            {t.value}
          </text>
        ))}
        {el.yLabel && (
          <text
            x={-35}
            y={innerH / 2}
            textAnchor="middle"
            fontSize={11}
            fill="#333"
            transform={`rotate(-90, -35, ${innerH / 2})`}
          >
            {el.yLabel}
          </text>
        )}
        {/* Curves */}
        {curvePaths.map((curve, i) => (
          <path
            key={`curve-${i}`}
            d={curve.d}
            fill="none"
            stroke={curve.color}
            strokeWidth={curve.strokeWidth}
          />
        ))}
      </g>
    </g>
  );
}

// ── Render single SVG element ──────────────────────────────

function renderSvgElement(
  el: DesignDiagramElement,
  idx: number,
  params: Record<string, number>,
): React.ReactNode {
  try {
    const dataAttr = el.id ? { "data-design-element": el.id } : {};

    switch (el.type) {
      case "svg_line": {
        const x1 = resolveValue(el.x1, params);
        const y1 = resolveValue(el.y1, params);
        const x2 = resolveValue(el.x2, params);
        const y2 = resolveValue(el.y2, params);
        return (
          <line
            key={idx}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke={el.stroke ?? "#000"}
            strokeWidth={el.strokeWidth ?? 2}
            strokeDasharray={el.strokeDasharray || undefined}
            {...dataAttr}
          />
        );
      }
      case "svg_rect": {
        const x = resolveValue(el.x, params);
        const y = resolveValue(el.y, params);
        const w = resolveValue(el.width, params, 100);
        const h = resolveValue(el.height, params, 50);
        const rx = resolveValue(el.rx, params);
        return (
          <rect
            key={idx}
            x={x}
            y={y}
            width={w}
            height={h}
            fill={el.fill ?? "none"}
            stroke={el.stroke ?? "#000"}
            strokeWidth={el.strokeWidth ?? 2}
            rx={rx}
            {...dataAttr}
          />
        );
      }
      case "svg_circle": {
        const cx = resolveValue(el.cx, params);
        const cy = resolveValue(el.cy, params);
        const r = resolveValue(el.r, params, 10);
        return (
          <circle
            key={idx}
            cx={cx}
            cy={cy}
            r={r}
            stroke={el.stroke ?? "#000"}
            fill={el.fill ?? "none"}
            strokeWidth={el.strokeWidth ?? 2}
            strokeDasharray={el.strokeDasharray || undefined}
            {...dataAttr}
          />
        );
      }
      case "svg_ellipse": {
        const cx = resolveValue(el.cx, params);
        const cy = resolveValue(el.cy, params);
        const rx = resolveValue(el.rx, params, 10);
        const ry = resolveValue(el.ry, params, 5);
        return (
          <ellipse
            key={idx}
            cx={cx}
            cy={cy}
            rx={rx}
            ry={ry}
            stroke={el.stroke ?? "#000"}
            fill={el.fill ?? "none"}
            strokeWidth={el.strokeWidth ?? 2}
            {...dataAttr}
          />
        );
      }
      case "svg_path":
        return (
          <path
            key={idx}
            d={el.d ?? ""}
            stroke={el.stroke ?? "#000"}
            strokeWidth={el.strokeWidth ?? 2}
            fill={el.fill ?? "none"}
            strokeDasharray={el.strokeDasharray || undefined}
            {...dataAttr}
          />
        );
      case "svg_text": {
        const x = resolveValue(el.x, params);
        const y = resolveValue(el.y, params);
        const anchor = el.textAnchor ?? "middle";
        const baseline =
          el.verticalAnchor === "start"
            ? "hanging"
            : el.verticalAnchor === "end"
              ? "alphabetic"
              : "central";
        return (
          <text
            key={idx}
            x={x}
            y={y}
            fontSize={el.fontSize ?? 14}
            fill={el.fill ?? "#000"}
            textAnchor={anchor}
            dominantBaseline={baseline}
            fontWeight={el.fontWeight ?? "normal"}
            fontFamily={el.fontFamily ?? "Inter, system-ui, sans-serif"}
            transform={el.angle ? `rotate(${el.angle}, ${x}, ${y})` : undefined}
            {...dataAttr}
          >
            {el.text ?? ""}
          </text>
        );
      }
      case "svg_arc": {
        const cx = resolveValue(el.cx, params);
        const cy = resolveValue(el.cy, params);
        const r = resolveValue(el.r, params, 50);
        const startAngle = resolveValue(el.startAngle, params);
        const endAngle = resolveValue(el.endAngle, params, 90);
        const d = arcPath(cx, cy, r, startAngle, endAngle);
        return (
          <path
            key={idx}
            d={d}
            stroke={el.stroke ?? "#000"}
            strokeWidth={el.strokeWidth ?? 2}
            fill={el.fill ?? "none"}
            strokeDasharray={el.strokeDasharray || undefined}
            {...dataAttr}
          />
        );
      }
      case "svg_group":
        return (
          <g
            key={idx}
            transform={el.transform || undefined}
            {...dataAttr}
          >
            {(el.elements ?? []).map((child, ci) =>
              renderSvgElement(child, ci, params),
            )}
          </g>
        );
      case "svg_latex":
        // Rendered as HTML overlay, not inside SVG
        return null;
      case "svg_arrow": {
        const x1 = resolveValue(el.x1, params);
        const y1 = resolveValue(el.y1, params);
        const x2 = resolveValue(el.x2, params);
        const y2 = resolveValue(el.y2, params);
        const color = el.stroke ?? "#000";
        const markerId = `da-arrow-${idx}`;
        return (
          <g key={idx} {...dataAttr}>
            <defs>
              <marker
                id={markerId}
                markerWidth="10"
                markerHeight="7"
                refX="9"
                refY="3.5"
                orient="auto"
              >
                <polygon points="0 0, 10 3.5, 0 7" fill={color} />
              </marker>
            </defs>
            <line
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke={color}
              strokeWidth={el.strokeWidth ?? 2}
              strokeDasharray={el.strokeDasharray || undefined}
              markerEnd={`url(#${markerId})`}
            />
          </g>
        );
      }
      case "graph":
        return <GraphInset key={idx} el={el} params={params} />;
      default:
        return null;
    }
  } catch (err) {
    console.warn(`[DesignDiagramContent] Error rendering element:`, err);
    return null;
  }
}

// ── KaTeX overlay (outside SVG) ────────────────────────────

function LatexOverlay({
  el,
  params,
}: {
  el: DesignDiagramElement & { type: "svg_latex" };
  params: Record<string, number>;
}) {
  const x = resolveValue(el.x, params);
  const y = resolveValue(el.y, params);

  let tex = el.expression ?? "";
  for (const [k, v] of Object.entries(params)) {
    tex = tex.replace(new RegExp(`\\{\\{${k}\\}\\}`, "g"), v.toFixed(2));
  }

  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    try {
      katex.render(tex, ref.current, {
        throwOnError: false,
        displayMode: false,
      });
    } catch {
      if (ref.current) ref.current.textContent = tex;
    }
  }, [tex]);

  return (
    <div
      ref={ref}
      data-design-element={el.id ?? undefined}
      style={{
        position: "absolute",
        left: x,
        top: y,
        fontSize: el.fontSize ?? 16,
        color: el.color ?? "#000",
        pointerEvents: "none",
        whiteSpace: "nowrap",
      }}
    />
  );
}

// ── Main component ─────────────────────────────────────────

export function DesignDiagramContent({
  instruction,
}: {
  instruction: DrawDesignDiagramInstruction;
}) {
  const spec: DesignDiagramSpec = instruction.spec ?? {};
  const elements = spec.elements ?? [];
  const width = spec.width ?? 900;
  const height = spec.height ?? 650;

  // Parameter state for interactive sliders
  const paramDefaults = useMemo(() => {
    const defaults: Record<string, number> = {};
    for (const p of spec.parameters ?? []) {
      defaults[p.name] = p.default ?? p.min ?? 0;
    }
    return defaults;
  }, [spec.parameters]);

  const [paramValues, setParamValues] = useState(paramDefaults);

  useEffect(() => {
    setParamValues(paramDefaults);
  }, [paramDefaults]);

  const handleParamChange = useCallback((name: string, value: string) => {
    setParamValues((prev) => ({ ...prev, [name]: parseFloat(value) }));
  }, []);

  // Separate latex elements for HTML overlay rendering
  const latexElements = useMemo(
    () => elements.filter((el) => el.type === "svg_latex"),
    [elements],
  );

  // Fingerprint triggers a CSS fade-in when the spec changes (e.g. modify_design_diagram).
  const specFingerprint = useMemo(() => {
    const els = spec.elements ?? [];
    return `${spec.title ?? ""}-${els.length}-${els[0]?.id ?? ""}`;
  }, [spec]);

  return (
    <div
      className="design-diagram-content"
      key={specFingerprint}
      style={{ animation: "diagram-fade-in 0.3s ease-out" }}
    >
      {/* Parameter sliders */}
      {(spec.parameters ?? []).length > 0 && (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 16,
            marginBottom: 12,
            padding: "8px 0",
          }}
        >
          {(spec.parameters ?? []).map((p) => (
            <label
              key={p.name}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontSize: 13,
                color: "#9ca3af",
              }}
            >
              {p.label ?? p.name}: {paramValues[p.name]?.toFixed(2)}
              <input
                type="range"
                min={p.min ?? 0}
                max={p.max ?? 10}
                step={p.step ?? 0.1}
                value={paramValues[p.name] ?? p.default ?? 0}
                onChange={(e) => handleParamChange(p.name, e.target.value)}
                style={{ width: 120 }}
              />
            </label>
          ))}
        </div>
      )}

      {/* SVG + KaTeX overlay container */}
      <div style={{ position: "relative", width: "100%", overflow: "visible" }}>
        <svg
          width="100%"
          viewBox={`0 0 ${width} ${height}`}
          overflow="visible"
          style={{
            display: "block",
            fontFamily: "Inter, system-ui, sans-serif",
            borderRadius: 8,
            background: spec.backgroundColor ?? "#ffffff",
          }}
        >
          {elements.map((el, i) => renderSvgElement(el, i, paramValues))}
        </svg>

        {/* KaTeX overlays — rendered as HTML on top of SVG */}
        {latexElements.map((el, i) => (
          <LatexOverlay
            key={`latex-${el.id ?? i}`}
            el={el as DesignDiagramElement & { type: "svg_latex" }}
            params={paramValues}
          />
        ))}
      </div>
    </div>
  );
}
