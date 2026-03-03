/**
 * Component registry — module-level singleton for dynamic component lookup.
 *
 * Components self-register via import side effects:
 *   import { registerComponent } from "./registry";
 *   registerComponent(myDef);
 *
 * Templates and the layout engine look up components by kind string.
 */

import type { ComponentDef } from "./types";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyComponentDef = ComponentDef<any>;

/** Module-level singleton registry. */
const registry = new Map<string, AnyComponentDef>();

/**
 * Register a component definition. Throws on duplicate kind
 * to catch accidental collisions early.
 */
export function registerComponent(def: AnyComponentDef): void {
  if (registry.has(def.kind)) {
    throw new Error(
      `Component "${def.kind}" is already registered. Duplicate registration is a bug.`,
    );
  }
  registry.set(def.kind, def);
}

/** Look up a component by kind. Returns undefined if not registered. */
export function getComponent(kind: string): AnyComponentDef | undefined {
  return registry.get(kind);
}

/** Check if a component kind is registered. */
export function hasComponent(kind: string): boolean {
  return registry.has(kind);
}

/** List all registered component kinds. */
export function listComponents(): readonly string[] {
  return [...registry.keys()];
}

/** Clear the registry. Test-only — do not use in production code. */
export function _resetRegistry(): void {
  registry.clear();
}
