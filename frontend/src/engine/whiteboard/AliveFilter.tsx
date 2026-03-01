/**
 * Shared SVG filter that gives hand-drawn elements a subtle organic wobble.
 *
 * A hidden <svg> defines a single feTurbulence → feDisplacementMap filter.
 * SMIL <animate> cycles the turbulence seed at ~5 fps for a dreamy breathing
 * effect — zero JS, zero React re-renders. Content renderers reference it
 * via CSS `filter: url(#wb-alive)` on their rough/stroke layers.
 */

/** Filter element ID — use in CSS: `filter: url(#${ALIVE_FILTER_ID})` */
export const ALIVE_FILTER_ID = "wb-alive";

export function AliveFilter() {
  return (
    <svg
      width="0"
      height="0"
      style={{ position: "absolute" }}
      aria-hidden="true"
    >
      <defs>
        <filter id={ALIVE_FILTER_ID}>
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.015"
            numOctaves={2}
            seed={1}
            result="noise"
          >
            <animate
              attributeName="seed"
              values="1;2;3;4;5;6;7;8"
              dur="1.6s"
              repeatCount="indefinite"
              calcMode="discrete"
            />
          </feTurbulence>
          <feDisplacementMap
            in="SourceGraphic"
            in2="noise"
            scale={3}
            xChannelSelector="R"
            yChannelSelector="G"
          />
        </filter>
      </defs>
    </svg>
  );
}
