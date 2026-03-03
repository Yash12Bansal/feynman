/**
 * Layout engine entry point — thin orchestrator.
 *
 * Looks up a registered strategy by scene_type, calls it with the
 * semantic elements and context, returns SceneGeometry.
 *
 * Strategy modules are imported for their side-effect registration.
 */

import type { SemanticSceneElement } from "../../../../types/visuals";
import type { SceneGeometry } from "../scene-types";
import type { LayoutContext } from "../components/types";
import { defaultLayoutContext } from "../components/types";
import { getStrategy } from "./registry";

// Side-effect imports: register all strategies
import "./strategies/free-body-layout";
import "./strategies/optics-layout";
import "./strategies/circuit-layout";
import "./strategies/geometry-layout";

/**
 * Resolve a semantic spec into SceneGeometry via the matching strategy.
 * Returns null if no strategy is registered for the given sceneType.
 */
export function resolveLayout(
  sceneType: string,
  elements: SemanticSceneElement[],
  context?: LayoutContext,
): SceneGeometry | null {
  const strategy = getStrategy(sceneType);
  if (!strategy) return null;
  return strategy(elements, context ?? defaultLayoutContext());
}
