/**
 * Drafting-marks loading animation for the Slide panel.
 *
 * A grid fades in, 4 neon lines draw themselves toward a center point,
 * a compass arc sweeps, dimension ticks pulse. The loop runs until the
 * real slide spec arrives, then the loader fades out.
 *
 * Pedagogically honest: signals "the AI is drafting a diagram", not a generic
 * spinner. Minimal (SVG + CSS only, no libs). Respects prefers-reduced-motion.
 */

interface DraftingLoaderProps {
  readonly caption?: string;
}

export function DraftingLoader({
  caption = "Sketching…",
}: DraftingLoaderProps) {
  return (
    <div className="sb-loader" aria-live="polite" aria-label="Sketching diagram">
      <svg
        className="sb-loader-svg"
        viewBox="0 0 480 320"
        preserveAspectRatio="xMidYMid meet"
        aria-hidden="true"
      >
        {/* Faint drafting grid */}
        <g className="sb-loader-grid">
          <defs>
            <pattern
              id="sb-loader-grid-pattern"
              width="20"
              height="20"
              patternUnits="userSpaceOnUse"
            >
              <path
                className="sb-loader-grid-line"
                d="M 20 0 L 0 0 0 20"
                fill="none"
                strokeWidth="0.4"
              />
            </pattern>
          </defs>
          <rect
            x="0"
            y="0"
            width="480"
            height="320"
            fill="url(#sb-loader-grid-pattern)"
          />
        </g>

        {/* Four converging neon lines */}
        <line
          className="sb-loader-line sb-loader-line-1"
          x1="40"
          y1="60"
          x2="240"
          y2="160"
        />
        <line
          className="sb-loader-line sb-loader-line-2"
          x1="440"
          y1="60"
          x2="240"
          y2="160"
        />
        <line
          className="sb-loader-line sb-loader-line-3"
          x1="40"
          y1="260"
          x2="240"
          y2="160"
        />
        <line
          className="sb-loader-line sb-loader-line-4"
          x1="440"
          y1="260"
          x2="240"
          y2="160"
        />

        {/* Compass arc */}
        <path
          className="sb-loader-arc"
          d="M 170 160 A 70 70 0 0 1 310 160"
        />

        {/* Dimension ticks */}
        <line
          className="sb-loader-tick sb-loader-tick-1"
          x1="60"
          y1="80"
          x2="70"
          y2="80"
        />
        <line
          className="sb-loader-tick sb-loader-tick-2"
          x1="420"
          y1="80"
          x2="410"
          y2="80"
        />
        <line
          className="sb-loader-tick sb-loader-tick-3"
          x1="60"
          y1="240"
          x2="70"
          y2="240"
        />
        <line
          className="sb-loader-tick sb-loader-tick-4"
          x1="420"
          y1="240"
          x2="410"
          y2="240"
        />

        {/* Centerpoint pulse */}
        <circle className="sb-loader-center" cx="240" cy="160" r="3" />
      </svg>

      <div className="sb-loader-caption">{caption}</div>
    </div>
  );
}
