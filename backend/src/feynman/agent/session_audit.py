"""Session audit — tracks what each system ACTUALLY DID during a teaching session.

Every system logs its decisions here — not just successes, but fallbacks,
skips, and degradations. The summary report makes silent failures visible.

Built incrementally: each phase adds its own audit events. Phase 1 covers
anticipation cache hits/misses and curriculum source tracking.
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
        print(audit.summary())
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

        # Phase 1: anticipation-specific summary
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
                "source": (ant.get("source_graph", 0) > 0
                and "ConceptGraph")
                or ((ant.get("source_plan", 0) > 0 and "LessonPlan") or "none"),
            }

        return {
            "elapsed_seconds": round(elapsed, 1),
            "total_events": len(self._events),
            "systems": systems,
            "anticipation": anticipation_summary,
        }

    def summary_text(self) -> str:
        """Human-readable audit summary for logs."""
        data = self.summary()
        lines = [
            "═══ SESSION AUDIT ═══",
            f"Elapsed: {data['elapsed_seconds']}s | Events: {data['total_events']}",
        ]

        if data.get("anticipation"):
            ant = data["anticipation"]
            lines.append(
                f"Anticipation: {ant['cache_hits']} hits / "
                f"{ant['cache_misses']} misses ({ant['hit_rate']}) | "
                f"Pre-generated: {ant['pre_generated']} | Source: {ant['source']}"
            )

        for sys_name, sys_data in data.get("systems", {}).items():
            if sys_name == "anticipation":
                continue  # already covered above
            events_str = ", ".join(f"{k}={v}" for k, v in sys_data["events"].items())
            lines.append(f"{sys_name}: {events_str}")

        return "\n".join(lines)
