/**
 * Strategy registry — module-level singleton for layout strategy lookup.
 *
 * Strategies self-register via import side effects, same pattern as
 * the component registry.
 */

import type { LayoutStrategy } from "./types";

/** Module-level singleton registry. */
const registry = new Map<string, LayoutStrategy>();

/**
 * Register a layout strategy for a scene type.
 * Throws on duplicate to catch accidental collisions early.
 */
export function registerStrategy(sceneType: string, fn: LayoutStrategy): void {
  if (registry.has(sceneType)) {
    throw new Error(
      `Strategy "${sceneType}" is already registered. Duplicate registration is a bug.`,
    );
  }
  registry.set(sceneType, fn);
}

/** Look up a strategy by scene type. Returns undefined if not registered. */
export function getStrategy(sceneType: string): LayoutStrategy | undefined {
  return registry.get(sceneType);
}

/** List all registered scene type strings. */
export function listStrategies(): readonly string[] {
  return [...registry.keys()];
}

/** Clear the registry. Test-only — do not use in production code. */
export function _resetStrategies(): void {
  registry.clear();
}
