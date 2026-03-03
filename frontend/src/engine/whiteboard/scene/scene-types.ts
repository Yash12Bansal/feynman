/**
 * Core types for the scene system — scientific diagrams and apparatus.
 *
 * Pure data. No React, no DOM, no rendering logic.
 * Components return SceneGeometry; the renderer (SceneContent) draws it.
 */

import type { Options as RoughOptions } from "roughjs/bin/core";

/** A single SVG path to render via rough.path(d, options). */
export interface ScenePath {
  /** data-scene-path attribute for GSAP targeting */
  id: string;
  /** SVG path data string */
  d: string;
  /** Override default rough options per path */
  roughOptions?: Partial<RoughOptions>;
  /** "rough" gets alive filter (default), "clean" doesn't */
  layer?: "rough" | "clean";
}

/** A text label positioned in scene coordinates. */
export interface SceneLabel {
  id: string;
  text: string;
  x: number;
  y: number;
  anchor?: "start" | "middle" | "end";
  fontSize?: number;
  color?: string;
}

/** Output of a component or template — pure geometry, no rendering. */
export interface SceneGeometry {
  paths: ScenePath[];
  labels: SceneLabel[];
  bounds: { x: number; y: number; width: number; height: number };
  /** Named anchor points for composing components in templates */
  anchors?: Record<string, { x: number; y: number }>;
}
