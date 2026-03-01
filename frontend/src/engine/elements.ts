/**
 * Element registry for the visual scene.
 *
 * Tracks mounted VisualCard DOM nodes by element_id so that
 * HighlightOverlay (and future GSAP animations) can look up
 * target elements without causing React re-renders.
 *
 * Uses useRef<Map> internally — mutations don't trigger renders.
 */

import { createContext, useContext, useRef, useCallback, useMemo } from "react";
import type { VisualInstruction } from "../types/visuals";

export interface ElementEntry {
  id: string;
  ref: HTMLDivElement;
  instruction: VisualInstruction;
}

export interface ElementRegistry {
  register: (
    id: string,
    ref: HTMLDivElement,
    instruction: VisualInstruction,
  ) => void;
  unregister: (id: string) => void;
  get: (id: string) => ElementEntry | undefined;
  entries: () => IterableIterator<[string, ElementEntry]>;
}

export const ElementRegistryContext = createContext<ElementRegistry | null>(
  null,
);

export function useElementRegistry(): ElementRegistry {
  const ctx = useContext(ElementRegistryContext);
  if (!ctx) {
    throw new Error(
      "useElementRegistry must be used within an ElementRegistryProvider",
    );
  }
  return ctx;
}

export function useCreateElementRegistry(): ElementRegistry {
  const mapRef = useRef<Map<string, ElementEntry>>(new Map());

  const register = useCallback(
    (id: string, ref: HTMLDivElement, instruction: VisualInstruction) => {
      mapRef.current.set(id, { id, ref, instruction });
    },
    [],
  );

  const unregister = useCallback((id: string) => {
    mapRef.current.delete(id);
  }, []);

  const get = useCallback((id: string) => {
    return mapRef.current.get(id);
  }, []);

  const entries = useCallback(() => {
    return mapRef.current.entries();
  }, []);

  return useMemo(
    () => ({ register, unregister, get, entries }),
    [register, unregister, get, entries],
  );
}
