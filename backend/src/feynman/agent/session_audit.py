"""Session audit — tracks what each system ACTUALLY DID during a teaching session.

Every system logs its decisions here — not just successes, but fallbacks,
skips, and degradations. The summary report makes silent failures visible.

Built incrementally: each phase adds its own audit events.

Systems tracked:
- curriculum:       graph_loaded, graph_missing_fallback_runtime, plan_failed
- anticipation:     source_graph, source_plan, pre_generated, cache_hit, cache_miss
- routing:          tool_call (with tool name, zone, concept_index)
- board_graph:      edge_declared, orphan_element
- concept_context:  graph_hint_shown, missing, no_graph_node_match, graph_node_no_edges
- layout:           zone_missing
- modify_diagram:   modified (with timing)
- doubt:            background_gen_fired, visual_ready_before_needed, fallback_to_scene
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class AuditEvent:
    """A single auditable event."""

    system: str  # e.g. "anticipation", "board_graph", "layout"
    event: str  # e.g. "cache_hit", "cache_miss", "fallback"
    detail: str = ""  # human-readable context
    timestamp: float = field(default_factory=time.monotonic)
    metadata: dict[str, Any] = field(default_factory=dict)


class SessionAudit:
    """Tracks what each system actually did during a teaching session.

    Every system logs its decisions here. The summary report makes silent
    failures visible — especially graceful fallbacks that mask degradation.

    Usage:
        audit = SessionAudit()
        audit.record("anticipation", "cache_hit", "concept=2, prompt='free body...'")
        audit.record("anticipation", "cache_miss", "concept=3, fell back to real-time gen")
        print(audit.summary_text())
    """

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._start_time: float = time.monotonic()

    def record(
        self,
        system: str,
        event: str,
        detail: str = "",
        **metadata: Any,
    ) -> None:
        """Record an audit event."""
        entry = AuditEvent(
            system=system,
            event=event,
            detail=detail,
            metadata=metadata,
        )
        self._events.append(entry)
        logger.debug(
            "audit.event",
            audit_system=system,
            audit_event=event,
            detail=detail[:120],
        )

    def events_for(self, system: str) -> list[AuditEvent]:
        """Get all events for a specific system."""
        return [e for e in self._events if e.system == system]

    def count(self, system: str, event: str) -> int:
        """Count occurrences of a specific event type."""
        return sum(1 for e in self._events if e.system == system and e.event == event)

    def summary(self) -> dict[str, Any]:
        """Produce a structured audit summary.

        Returns a dict suitable for logging or API response. Groups events
        by system and provides counts for key metrics.
        """
        elapsed = time.monotonic() - self._start_time
        systems: dict[str, dict[str, Any]] = {}

        for evt in self._events:
            if evt.system not in systems:
                systems[evt.system] = {"events": {}, "details": []}
            sys_data = systems[evt.system]
            sys_data["events"][evt.event] = sys_data["events"].get(evt.event, 0) + 1
            if evt.detail:
                sys_data["details"].append(f"[{evt.event}] {evt.detail}")

        # ── Curriculum source ─────────────────────────────────────
        curr = systems.get("curriculum", {}).get("events", {})
        curriculum_summary = None
        if curr:
            curriculum_summary = {
                "source": (
                    "ConceptGraph" if curr.get("graph_loaded", 0) > 0
                    else "LessonPlan (runtime)" if curr.get("graph_missing_fallback_runtime", 0) > 0
                    else "FAILED" if curr.get("plan_failed", 0) > 0
                    else "unknown"
                ),
            }

        # ── Anticipation ──────────────────────────────────────────
        ant = systems.get("anticipation", {}).get("events", {})
        anticipation_summary = None
        if ant:
            hits = ant.get("cache_hit", 0)
            misses = ant.get("cache_miss", 0)
            total = hits + misses
            anticipation_summary = {
                "pre_generated": ant.get("pre_generated", 0),
                "cache_hits": hits,
                "cache_misses": misses,
                "hit_rate": f"{hits / total * 100:.0f}%" if total > 0 else "N/A",
                "source": (
                    "ConceptGraph" if ant.get("source_graph", 0) > 0
                    else "LessonPlan" if ant.get("source_plan", 0) > 0
                    else "none"
                ),
            }

        # ── Tool routing ──────────────────────────────────────────
        routing_events = [e for e in self._events if e.system == "routing"]
        routing_summary = None
        if routing_events:
            tool_counts: dict[str, int] = {}
            for evt in routing_events:
                tool_name = evt.metadata.get("tool", "unknown")
                tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
            routing_summary = {
                "total_tool_calls": len(routing_events),
                "by_tool": tool_counts,
            }

        # ── Board graph ───────────────────────────────────────────
        bg = systems.get("board_graph", {}).get("events", {})
        board_graph_summary = None
        if bg:
            board_graph_summary = {
                "edges_declared": bg.get("edge_declared", 0),
                "orphan_elements": bg.get("orphan_element", 0),
            }

        # ── Concept context ───────────────────────────────────────
        cc = systems.get("concept_context", {}).get("events", {})
        concept_context_summary = None
        if cc:
            concept_context_summary = {
                "hints_shown": cc.get("graph_hint_shown", 0),
                "missing_no_graph": cc.get("missing", 0),
                "no_node_match": cc.get("no_graph_node_match", 0),
                "node_no_edges": cc.get("graph_node_no_edges", 0),
            }

        # ── Layout ────────────────────────────────────────────────
        lay = systems.get("layout", {}).get("events", {})
        layout_summary = None
        if lay:
            layout_summary = {
                "zone_missing_warnings": lay.get("zone_missing", 0),
            }

        # ── Modify diagram ────────────────────────────────────────
        mod = systems.get("modify_diagram", {}).get("events", {})
        modify_summary = None
        if mod:
            mod_count = mod.get("modified", 0)
            mod_events = [
                e for e in self._events
                if e.system == "modify_diagram" and e.event == "modified"
            ]
            elapsed_values = [
                e.metadata["elapsed_ms"]
                for e in mod_events
                if e.metadata.get("elapsed_ms")
            ]
            avg_ms = (
                sum(elapsed_values) / len(elapsed_values)
                if elapsed_values
                else 0
            )
            modify_summary = {
                "modifications": mod_count,
                "avg_time_ms": round(avg_ms),
            }

        # ── Doubt ─────────────────────────────────────────────────
        dbt = systems.get("doubt", {}).get("events", {})
        doubt_summary = None
        if dbt:
            doubt_summary = {
                "background_gen_fired": dbt.get("background_gen_fired", 0),
                "visual_ready_before_needed": dbt.get("visual_ready_before_needed", 0),
                "fallback_to_scene": dbt.get("fallback_to_scene", 0),
            }

        return {
            "elapsed_seconds": round(elapsed, 1),
            "total_events": len(self._events),
            "curriculum": curriculum_summary,
            "anticipation": anticipation_summary,
            "routing": routing_summary,
            "board_graph": board_graph_summary,
            "concept_context": concept_context_summary,
            "layout": layout_summary,
            "modify": modify_summary,
            "doubt": doubt_summary,
            "systems": systems,
        }

    def summary_text(self) -> str:
        """Human-readable audit summary for logs."""
        data = self.summary()
        lines = [
            "",
            "══════════════════════════════════════════════════════════",
            "  SESSION AUDIT REPORT",
            f"  Elapsed: {data['elapsed_seconds']}s | Events: {data['total_events']}",
            "══════════════════════════════════════════════════════════",
        ]

        # Curriculum source — the single most important thing.
        if data.get("curriculum"):
            src = data["curriculum"]["source"]
            status = "OK" if src == "ConceptGraph" else "DEGRADED"
            lines.append(f"CURRICULUM: {src} [{status}]")
        else:
            lines.append("CURRICULUM: not initialized [DEGRADED]")

        # Anticipation
        if data.get("anticipation"):
            ant = data["anticipation"]
            lines.append(
                f"ANTICIPATION: {ant['cache_hits']} hits / "
                f"{ant['cache_misses']} misses ({ant['hit_rate']}) | "
                f"Pre-generated: {ant['pre_generated']} | Source: {ant['source']}"
            )
        else:
            lines.append("ANTICIPATION: no events [DEGRADED — no pre-generation happened]")

        # Tool routing
        if data.get("routing"):
            rt = data["routing"]
            tool_str = ", ".join(f"{k}={v}" for k, v in sorted(rt["by_tool"].items()))
            lines.append(f"ROUTING: {rt['total_tool_calls']} calls — {tool_str}")
        else:
            lines.append("ROUTING: no tool calls [DEGRADED — nothing drawn]")

        # Board graph
        if data.get("board_graph"):
            bg = data["board_graph"]
            orphan_status = f" [WARNING: {bg['orphan_elements']} orphans]" if bg["orphan_elements"] else ""
            lines.append(
                f"BOARD GRAPH: {bg['edges_declared']} edges declared, "
                f"{bg['orphan_elements']} orphan elements{orphan_status}"
            )

        # Concept context
        if data.get("concept_context"):
            cc = data["concept_context"]
            total_missing = cc["missing_no_graph"] + cc["no_node_match"] + cc["node_no_edges"]
            status = "OK" if cc["hints_shown"] > 0 else "DEGRADED"
            lines.append(
                f"CONCEPT CONTEXT: {cc['hints_shown']} hints shown, "
                f"{total_missing} missing [{status}]"
            )

        # Layout
        if data.get("layout"):
            lay = data["layout"]
            if lay["zone_missing_warnings"] > 0:
                lines.append(
                    f"LAYOUT: {lay['zone_missing_warnings']} spatial elements without zone "
                    f"[WARNING — LLM not specifying zones]"
                )

        # Modify
        if data.get("modify"):
            mod = data["modify"]
            lines.append(
                f"MODIFY: {mod['modifications']} modifications | "
                f"Avg time: {mod['avg_time_ms']}ms"
            )

        # Doubt
        if data.get("doubt"):
            dbt = data["doubt"]
            lines.append(
                f"DOUBT: bg_gen={dbt['background_gen_fired']}, "
                f"ready_before_needed={dbt['visual_ready_before_needed']}, "
                f"fallback={dbt['fallback_to_scene']}"
            )

        lines.append("══════════════════════════════════════════════════════════")
        return "\n".join(lines)
