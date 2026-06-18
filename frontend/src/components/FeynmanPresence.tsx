/**
 * FeynmanPresence — a small, audio-reactive "voice aura" that makes the lecture
 * board feel alive with the teacher's voice.
 *
 * A soft orb + 5 slim bars. While the narration plays, the bars move with the
 * REAL audio amplitude (a Web Audio AnalyserNode tapped off the lecture's
 * <audio> element); paused → they settle to a calm breathing baseline;
 * listening → coral ripple; thinking → an indeterminate wave. Restrained,
 * low-opacity, pointer-events:none — it never gets in the way.
 *
 * All Web Audio is guarded (jsdom/tests + autoplay-blocked browsers degrade to
 * the idle animation, never crash). Styling reads the `--lv-*` lecture tokens,
 * so it themes with the rest of the chrome. Layout/styles live in
 * screens/lecture-viewer.css (`.fp-*`).
 */

import { useEffect, useRef } from "react";
import type { RefObject } from "react";
import type { AskFeynmanState } from "./AskFeynmanButton";

const BAR_COUNT = 5;

// `createMediaElementSource` may be called only ONCE per <audio> element (a
// second call throws), so cache the analyser per element and reuse it.
interface Tap {
  readonly ctx: AudioContext;
  readonly analyser: AnalyserNode;
}
const taps = new WeakMap<HTMLAudioElement, Tap>();

function getTap(el: HTMLAudioElement): Tap | null {
  const existing = taps.get(el);
  if (existing) return existing;
  const Ctor =
    typeof window !== "undefined"
      ? (window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext })
          .webkitAudioContext)
      : undefined;
  if (!Ctor) return null;
  try {
    const ctx = new Ctor();
    const source = ctx.createMediaElementSource(el);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 64;
    analyser.smoothingTimeConstant = 0.82;
    source.connect(analyser);
    analyser.connect(ctx.destination); // keep audio audible
    const tap: Tap = { ctx, analyser };
    taps.set(el, tap);
    return tap;
  } catch {
    return null; // autoplay policy / element already sourced / unsupported
  }
}

function idleWave(t: number): number[] {
  return Array.from(
    { length: BAR_COUNT },
    (_, i) => 0.26 + 0.16 * (0.5 + 0.5 * Math.sin(t * 0.06 + i * 0.7)),
  );
}

function ripple(t: number): number[] {
  return Array.from(
    { length: BAR_COUNT },
    (_, i) => 0.3 + 0.5 * (0.5 + 0.5 * Math.sin(t * 0.18 - i * 0.9)),
  );
}

export function FeynmanPresence({
  audioRef,
  state,
  paused,
}: {
  readonly audioRef: RefObject<HTMLAudioElement | null>;
  readonly state: AskFeynmanState;
  readonly paused: boolean;
}) {
  const barsRef = useRef<(HTMLSpanElement | null)[]>([]);
  const orbRef = useRef<HTMLSpanElement | null>(null);
  const stateRef = useRef(state);
  const pausedRef = useRef(paused);

  useEffect(() => {
    stateRef.current = state;
    pausedRef.current = paused;
  }, [state, paused]);

  useEffect(() => {
    const reduce = window.matchMedia?.(
      "(prefers-reduced-motion: reduce)",
    )?.matches;
    if (reduce) {
      barsRef.current.forEach((b, i) => {
        if (b) b.style.transform = `scaleY(${0.4 + (i % 2) * 0.25})`;
      });
      return;
    }
    if (typeof requestAnimationFrame !== "function") return;

    let raf = 0;
    let t = 0;
    let freq: Uint8Array<ArrayBuffer> | null = null;
    const current: number[] = new Array(BAR_COUNT).fill(0.2);

    const loop = () => {
      t += 1;
      const el = audioRef.current;
      const st = stateRef.current;
      const isPaused = pausedRef.current;

      let targets: number[];
      if (el && !isPaused && st === "idle") {
        const tap = getTap(el);
        if (tap) {
          if (tap.ctx.state === "suspended") void tap.ctx.resume();
          if (!freq || freq.length !== tap.analyser.frequencyBinCount) {
            freq = new Uint8Array(new ArrayBuffer(tap.analyser.frequencyBinCount));
          }
          tap.analyser.getByteFrequencyData(freq);
          targets = Array.from({ length: BAR_COUNT }, (_, i) => {
            const v = (freq?.[1 + i * 2] ?? 0) / 255;
            return 0.16 + Math.min(1, v * 1.7) * 0.84;
          });
        } else {
          targets = idleWave(t);
        }
      } else if (st === "listening") {
        targets = ripple(t);
      } else if (st === "thinking") {
        targets = idleWave(t * 1.7);
      } else {
        targets = idleWave(t);
      }

      let sum = 0;
      for (let i = 0; i < BAR_COUNT; i++) {
        current[i] += (targets[i] - current[i]) * 0.25;
        sum += current[i];
        const b = barsRef.current[i];
        if (b) b.style.transform = `scaleY(${current[i].toFixed(3)})`;
      }
      const orb = orbRef.current;
      if (orb) {
        const avg = sum / BAR_COUNT;
        orb.style.transform = `scale(${(0.85 + avg * 0.4).toFixed(3)})`;
        orb.style.opacity = (0.5 + avg * 0.5).toFixed(3);
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [audioRef]);

  if (state === "error") return null;

  return (
    <div className="fp-presence" data-state={state} aria-hidden>
      <span className="fp-orb" ref={orbRef} />
      <span className="fp-bars">
        {Array.from({ length: BAR_COUNT }, (_, i) => (
          <span
            key={i}
            className="fp-bar"
            ref={(el) => {
              barsRef.current[i] = el;
            }}
          />
        ))}
      </span>
      <span className="fp-label">Feynman</span>
    </div>
  );
}
