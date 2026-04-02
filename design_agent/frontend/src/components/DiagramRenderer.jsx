import React, {
  useState,
  useMemo,
  useCallback,
  useRef,
  useEffect,
} from "react";
import { Group } from "@visx/group";
import { LinePath } from "@visx/shape";
import { Text } from "@visx/text";
import { scaleLinear } from "@visx/scale";
import { AxisBottom, AxisLeft } from "@visx/axis";
import { GridRows, GridColumns } from "@visx/grid";
import katex from "katex";

// --- Safe math expression evaluator ---
function evalMathExpr(expr, vars) {
  try {
    const keys = Object.keys(vars);
    const vals = Object.values(vars);
    // eslint-disable-next-line no-new-func
    const fn = new Function(
      ...keys,
      `const {sin,cos,tan,sqrt,abs,PI,E,log,exp,pow,floor,ceil,min,max,atan2,asin,acos,sinh,cosh,tanh}=Math;return ${expr};`,
    );
    return fn(...vals);
  } catch {
    return NaN;
  }
}

// Resolve a value that might be an expression referencing params
function resolveValue(val, paramValues) {
  if (typeof val === "number") return val;
  if (typeof val === "string") {
    const result = evalMathExpr(val, paramValues);
    return isNaN(result) ? 0 : result;
  }
  return val ?? 0;
}

function resolvePoint(pt, paramValues) {
  if (!pt) return [0, 0];
  if (Array.isArray(pt)) {
    return [resolveValue(pt[0], paramValues), resolveValue(pt[1], paramValues)];
  }
  return [
    resolveValue(pt.x ?? pt[0] ?? 0, paramValues),
    resolveValue(pt.y ?? pt[1] ?? 0, paramValues),
  ];
}

// --- Arc path helper for svg_arc ---
// Angles in degrees, 0=right, positive=clockwise (SVG convention, y-down)
function arcPath(cx, cy, r, startDeg, endDeg) {
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

// --- KaTeX as HTML overlay (NOT inside SVG) ---
function LatexOverlay({ el, paramValues }) {
  const x = resolveValue(el.x || 0, paramValues);
  const y = resolveValue(el.y || 0, paramValues);

  let tex = el.expression || el.tex || "";
  Object.entries(paramValues).forEach(([k, v]) => {
    tex = tex.replace(new RegExp(`\\{\\{${k}\\}\\}`, "g"), v.toFixed(2));
  });

  let html = "";
  try {
    html = katex.renderToString(tex, {
      throwOnError: false,
      displayMode: false,
    });
  } catch {
    html = tex;
  }

  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        fontSize: el.fontSize || 16,
        color: el.color || "#000",
        pointerEvents: "none",
        whiteSpace: "nowrap",
      }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

// --- Inset Graph element using visx ---
function GraphElement({ el, paramValues }) {
  const x = resolveValue(el.x || 0, paramValues);
  const y = resolveValue(el.y || 0, paramValues);
  const w = resolveValue(el.width || 300, paramValues);
  const h = resolveValue(el.height || 200, paramValues);
  const margin = { top: 10, right: 10, bottom: 35, left: 45 };
  const innerW = w - margin.left - margin.right;
  const innerH = h - margin.top - margin.bottom;

  const xDomain = el.xDomain || [-10, 10];
  const yDomain = el.yDomain || [-10, 10];

  const xScale = scaleLinear({ domain: xDomain, range: [0, innerW] });
  const yScale = scaleLinear({ domain: yDomain, range: [innerH, 0] });

  // Generate curve data
  const curves = useMemo(() => {
    return (el.curves || []).map((curve) => {
      const points = [];
      const [xMin, xMax] = xDomain;
      const numSamples = 200;
      for (let i = 0; i <= numSamples; i++) {
        const xVal = xMin + (i / numSamples) * (xMax - xMin);
        const yVal = evalMathExpr(curve.expression, {
          x: xVal,
          ...paramValues,
        });
        if (isFinite(yVal)) points.push({ x: xVal, y: yVal });
      }
      return { ...curve, points };
    });
  }, [el.curves, xDomain, paramValues]);

  return (
    <Group left={x} top={y}>
      <rect
        width={w}
        height={h}
        fill={el.backgroundColor || "#f9f9f9"}
        stroke={el.borderColor || "#ccc"}
        rx={2}
      />
      <Group left={margin.left} top={margin.top}>
        {el.showGrid && (
          <>
            <GridRows scale={yScale} width={innerW} stroke="#e0e0e0" />
            <GridColumns scale={xScale} height={innerH} stroke="#e0e0e0" />
          </>
        )}
        <AxisBottom
          scale={xScale}
          top={innerH}
          label={el.xLabel || ""}
          numTicks={5}
        />
        <AxisLeft scale={yScale} label={el.yLabel || ""} numTicks={5} />
        {curves.map((curve, ci) => (
          <LinePath
            key={ci}
            data={curve.points}
            x={(d) => xScale(d.x)}
            y={(d) => yScale(d.y)}
            stroke={curve.color || "steelblue"}
            strokeWidth={curve.strokeWidth || 2}
          />
        ))}
      </Group>
    </Group>
  );
}

// --- Render a single element ---
function renderElement(el, idx, paramValues) {
  try {
    switch (el.type) {
      case "svg_line": {
        const x1 = resolveValue(el.x1 || 0, paramValues);
        const y1 = resolveValue(el.y1 || 0, paramValues);
        const x2 = resolveValue(el.x2 || 0, paramValues);
        const y2 = resolveValue(el.y2 || 0, paramValues);
        return (
          <line
            key={idx}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke={el.stroke || "#000"}
            strokeWidth={el.strokeWidth || 2}
            strokeDasharray={el.strokeDasharray || undefined}
          />
        );
      }
      case "svg_rect": {
        const x = resolveValue(el.x || 0, paramValues);
        const y = resolveValue(el.y || 0, paramValues);
        const w = resolveValue(el.width || 100, paramValues);
        const h = resolveValue(el.height || 50, paramValues);
        const rx = resolveValue(el.rx || 0, paramValues);
        return (
          <rect
            key={idx}
            x={x}
            y={y}
            width={w}
            height={h}
            fill={el.fill || "none"}
            stroke={el.stroke || "#000"}
            strokeWidth={el.strokeWidth || 2}
            rx={rx}
          />
        );
      }
      case "svg_circle": {
        const cx = resolveValue(el.cx || 0, paramValues);
        const cy = resolveValue(el.cy || 0, paramValues);
        const r = resolveValue(el.r || 10, paramValues);
        return (
          <circle
            key={idx}
            cx={cx}
            cy={cy}
            r={r}
            stroke={el.stroke || "#000"}
            fill={el.fill || "none"}
            strokeWidth={el.strokeWidth || 2}
            strokeDasharray={el.strokeDasharray || undefined}
          />
        );
      }
      case "svg_ellipse": {
        const cx = resolveValue(el.cx || 0, paramValues);
        const cy = resolveValue(el.cy || 0, paramValues);
        const rx = resolveValue(el.rx || 10, paramValues);
        const ry = resolveValue(el.ry || 5, paramValues);
        return (
          <ellipse
            key={idx}
            cx={cx}
            cy={cy}
            rx={rx}
            ry={ry}
            stroke={el.stroke || "#000"}
            fill={el.fill || "none"}
            strokeWidth={el.strokeWidth || 2}
          />
        );
      }
      case "svg_path": {
        return (
          <path
            key={idx}
            d={el.d || ""}
            stroke={el.stroke || "#000"}
            strokeWidth={el.strokeWidth || 2}
            fill={el.fill || "none"}
            strokeDasharray={el.strokeDasharray || undefined}
          />
        );
      }
      case "svg_text": {
        const x = resolveValue(el.x || 0, paramValues);
        const y = resolveValue(el.y || 0, paramValues);
        return (
          <Text
            key={idx}
            x={x}
            y={y}
            fontSize={el.fontSize || 14}
            fill={el.fill || "#000"}
            textAnchor={el.textAnchor || "middle"}
            verticalAnchor={el.verticalAnchor || "middle"}
            fontWeight={el.fontWeight || "normal"}
            fontFamily={el.fontFamily || "sans-serif"}
            angle={el.angle || 0}
          >
            {el.text || ""}
          </Text>
        );
      }
      case "svg_arc": {
        const cx = resolveValue(el.cx || 0, paramValues);
        const cy = resolveValue(el.cy || 0, paramValues);
        const r = resolveValue(el.r || 50, paramValues);
        const startAngle = resolveValue(el.startAngle || 0, paramValues);
        const endAngle = resolveValue(el.endAngle || 90, paramValues);
        const d = arcPath(cx, cy, r, startAngle, endAngle);
        return (
          <path
            key={idx}
            d={d}
            stroke={el.stroke || "#000"}
            strokeWidth={el.strokeWidth || 2}
            fill={el.fill || "none"}
            strokeDasharray={el.strokeDasharray || undefined}
          />
        );
      }
      case "svg_group": {
        return (
          <Group key={idx} transform={el.transform || undefined}>
            {(el.elements || []).map((child, ci) =>
              renderElement(child, ci, paramValues),
            )}
          </Group>
        );
      }
      case "svg_latex": {
        // Rendered as HTML overlay, not inside SVG — skip here
        return null;
      }
      case "svg_arrow": {
        const x1 = resolveValue(el.x1 || 0, paramValues);
        const y1 = resolveValue(el.y1 || 0, paramValues);
        const x2 = resolveValue(el.x2 || 0, paramValues);
        const y2 = resolveValue(el.y2 || 0, paramValues);
        const color = el.stroke || "#000";
        const markerId = `arrow-${idx}-${x1}-${y1}-${x2}-${y2}`.replace(
          /[^a-zA-Z0-9]/g,
          "_",
        );
        return (
          <g key={idx}>
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
              strokeWidth={el.strokeWidth || 2}
              strokeDasharray={el.strokeDasharray || undefined}
              markerEnd={`url(#${markerId})`}
            />
          </g>
        );
      }
      case "graph": {
        return <GraphElement key={idx} el={el} paramValues={paramValues} />;
      }
      default:
        console.warn(`Unknown element type: ${el.type}`);
        return null;
    }
  } catch (err) {
    console.warn(`Error rendering element ${el.type}:`, err);
    return null;
  }
}

// --- Main DiagramRenderer ---

function DiagramRenderer({ spec }) {
  // Parameter state
  const paramDefaults = useMemo(() => {
    const defaults = {};
    (spec.parameters || []).forEach((p) => {
      defaults[p.name] = p.default ?? p.min ?? 0;
    });
    return defaults;
  }, [spec.parameters]);

  const [paramValues, setParamValues] = useState(paramDefaults);

  // Reset params when spec changes
  useEffect(() => {
    setParamValues(paramDefaults);
  }, [paramDefaults]);

  const handleParamChange = useCallback((name, value) => {
    setParamValues((prev) => ({ ...prev, [name]: parseFloat(value) }));
  }, []);

  const elements = spec.elements || [];
  const width = spec.width || 800;
  const height = spec.height || 600;
  const title = spec.title;
  const description = spec.description;

  // Separate latex elements (rendered as HTML overlays) from SVG elements
  const latexElements = elements.filter((el) => el.type === "svg_latex");

  return (
    <div
      className="diagram-renderer"
      style={{ backgroundColor: spec.backgroundColor || "#1a1a2e" }}
    >
      {title && <h2 className="diagram-title">{title}</h2>}
      {description && <p className="diagram-description">{description}</p>}

      {/* Parameter sliders */}
      {(spec.parameters || []).length > 0 && (
        <div className="param-sliders">
          {spec.parameters.map((p) => (
            <div key={p.name} className="param-slider">
              <label>
                {p.label || p.name}:{" "}
                <strong>{paramValues[p.name]?.toFixed(2)}</strong>
              </label>
              <input
                type="range"
                min={p.min ?? 0}
                max={p.max ?? 10}
                step={p.step ?? 0.1}
                value={paramValues[p.name] ?? p.default ?? 0}
                onChange={(e) => handleParamChange(p.name, e.target.value)}
              />
            </div>
          ))}
        </div>
      )}

      {/* SVG + LaTeX overlay container */}
      <div style={{ position: "relative", width, margin: "0 auto" }}>
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          style={{
            background: spec.backgroundColor || "#fff",
            display: "block",
            fontFamily: "sans-serif",
            borderRadius: "8px",
          }}
        >
          {elements.map((el, i) => renderElement(el, i, paramValues))}
        </svg>

        {/* KaTeX overlays — rendered as HTML on top of SVG */}
        {latexElements.map((el, i) => (
          <LatexOverlay key={`latex-${i}`} el={el} paramValues={paramValues} />
        ))}
      </div>
    </div>
  );
}

export default DiagramRenderer;
