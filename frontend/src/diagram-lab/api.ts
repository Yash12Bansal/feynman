/**
 * Thin fetch wrappers for the /api/diagtest/* surface.
 *
 * No retries, no caching — single-user testbed where every retry is a user
 * decision. The vite proxy ("/api" → :8000) handles the dev server hop.
 */

import type {
  AnnotationInjectResponse,
  HistoryEntry,
  MathsLibrary,
  RunResponse,
  StrategyDescriptor,
} from "./types";
import type { LabDiagramSpec } from "./types";

const BASE = "/api/diagtest";

async function jsonOrThrow<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const body = (await resp.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      try {
        detail = await resp.text();
      } catch {
        /* keep status */
      }
    }
    throw new Error(detail);
  }
  return (await resp.json()) as T;
}

export async function fetchStrategies(): Promise<StrategyDescriptor[]> {
  const resp = await fetch(`${BASE}/strategies`);
  return jsonOrThrow<StrategyDescriptor[]>(resp);
}

export async function fetchMathsLibrary(): Promise<MathsLibrary> {
  const resp = await fetch(`${BASE}/maths-library`);
  return jsonOrThrow<MathsLibrary>(resp);
}

export async function fetchHistory(): Promise<HistoryEntry[]> {
  const resp = await fetch(`${BASE}/history`);
  return jsonOrThrow<HistoryEntry[]>(resp);
}

export async function fetchHistoryEntry(runId: string): Promise<{
  run_id: string;
  strategy_id: string;
  model: string;
  prompt: string;
  label: string | null;
  total_ms: number;
  element_count: number;
  success: boolean;
  error?: string | null;
  result?: RunResponse["result"];
}> {
  const resp = await fetch(`${BASE}/history/${runId}`);
  return jsonOrThrow(resp);
}

export async function runStrategy(body: {
  strategy_id: string;
  model: string;
  prompt: string;
  options: Record<string, unknown>;
  label?: string | null;
}): Promise<RunResponse> {
  const resp = await fetch(`${BASE}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<RunResponse>(resp);
}

export async function injectAnnotation(body: {
  spec: LabDiagramSpec;
  intent: string;
  model?: string;
}): Promise<AnnotationInjectResponse> {
  const resp = await fetch(`${BASE}/annotate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<AnnotationInjectResponse>(resp);
}
