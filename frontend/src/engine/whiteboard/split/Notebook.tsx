/**
 * Notebook panel — right ~62% of the split board.
 *
 * Vertical stack of entries. Equations in the same align_group share a visual
 * `=` column (measured post-render, then nudged via per-entry CSS var).
 * Page-turn animation on page number change.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import type { NotebookState } from "./types";
import { NotebookEntryView } from "./NotebookEntry";

interface NotebookProps {
  readonly state: NotebookState;
  readonly title?: string;
}

type PerEntryMeasure = ReadonlyMap<string, number>;
type GroupMeasures = ReadonlyMap<string, PerEntryMeasure>;

const PAGE_TURN_MS = 450;

export function Notebook({ state, title = "Notebook" }: NotebookProps) {
  const { page, turning } = state;
  const [groupMeasures, setGroupMeasures] = useState<GroupMeasures>(
    () => new Map(),
  );

  // Page-turn animation ownership lives here, not in the adapter. When
  // page.pageNum changes, flash `localTurning=true` for PAGE_TURN_MS so the
  // `.sb-notebook-turning` class triggers the CSS flip.
  //
  // We detect the page change during render (React-sanctioned pattern — see
  // https://react.dev/reference/react/useState#storing-information-from-previous-renders)
  // so we don't land in the `set-state-in-effect` antipattern. The timer-based
  // clear is still an effect because it's an external subscription (a timeout).
  const [turnState, setTurnState] = useState<{ page: number; turning: boolean }>(
    () => ({ page: page.pageNum, turning: false }),
  );
  if (turnState.page !== page.pageNum) {
    setTurnState({ page: page.pageNum, turning: true });
  }
  useEffect(() => {
    if (!turnState.turning) return;
    const t = setTimeout(
      () =>
        setTurnState((s) =>
          s.turning && s.page === turnState.page ? { ...s, turning: false } : s,
        ),
      PAGE_TURN_MS,
    );
    return () => clearTimeout(t);
  }, [turnState.turning, turnState.page]);

  const isTurning = turning || turnState.turning;

  // Map entry id → alignGroup for entries currently on the page. Entries from
  // previous pages are filtered out implicitly — their ids are missing here.
  const groupOfEntry = useMemo(() => {
    const map = new Map<string, string>();
    for (const e of page.entries) {
      if (e.kind === "equation" && e.alignGroup) {
        map.set(e.id, e.alignGroup);
      }
    }
    return map;
  }, [page.entries]);

  const handleEqualsOffset = useCallback(
    (id: string, offsetPx: number) => {
      const group = groupOfEntry.get(id);
      if (!group) return;

      setGroupMeasures((prev) => {
        const prevGroup = prev.get(group) ?? new Map<string, number>();
        const existing = prevGroup.get(id);
        if (existing !== undefined && Math.abs(existing - offsetPx) < 1) {
          return prev;
        }
        const nextGroup = new Map(prevGroup);
        nextGroup.set(id, offsetPx);
        const next = new Map(prev);
        next.set(group, nextGroup);
        return next;
      });
    },
    [groupOfEntry],
  );

  // Compute per-entry left-nudge from group measurements, filtering out any
  // entries not on the current page (stale measures from prior pages).
  const alignOffsets = useMemo(() => {
    const currentIds = new Set<string>();
    for (const e of page.entries) currentIds.add(e.id);

    const offsets: Record<string, number> = {};
    for (const [, entryMap] of groupMeasures) {
      let target = 0;
      for (const [id, v] of entryMap) {
        if (currentIds.has(id) && v > target) target = v;
      }
      if (target === 0) continue;
      for (const [id, own] of entryMap) {
        if (!currentIds.has(id)) continue;
        const nudge = Math.max(0, target - own);
        if (nudge >= 1) offsets[id] = nudge;
      }
    }
    return offsets;
  }, [groupMeasures, page.entries]);

  const renderedEntries = useMemo(
    () =>
      page.entries.map((entry) => (
        <NotebookEntryView
          key={entry.id}
          entry={entry}
          alignOffsetPx={alignOffsets[entry.id]}
          onEqualsOffset={handleEqualsOffset}
        />
      )),
    [page.entries, alignOffsets, handleEqualsOffset],
  );

  return (
    <section className="sb-notebook" aria-label="Notebook panel">
      <div className="sb-notebook-header">
        <h2 className="sb-notebook-title">{title}</h2>
        <span className="sb-notebook-page-num">
          page {page.pageNum.toString().padStart(2, "0")}
        </span>
      </div>

      <div
        className={`sb-notebook-body${isTurning ? " sb-notebook-turning" : ""}`}
        key={page.pageNum}
      >
        {renderedEntries}
      </div>
    </section>
  );
}
