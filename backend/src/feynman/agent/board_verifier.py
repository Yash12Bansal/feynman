"""Board Visual Verification — async perception loop via vision model.

Four verification modes share one screenshot-capture path and Haiku backend:

* **Layout quality** — overlaps, spacing, unreadable labels. Audit-only by
  default; severe scores (<=2) can route through ``on_feedback`` to enqueue a
  ``PerceptionFeedback`` suggesting a ``modify_design_diagram`` fix.
* **Annotation accuracy** (Phase 5a-1) — did the annotation land on the
  claimed element? Routes through ``on_feedback`` on score <= 2 with a usable
  ``suggested_target``.
* **Diagram intent** (Phase 5a-2) — does the rendered diagram match the
  agent's claim (the ``prompt`` for draw or ``modification`` for modify)?
  Routes through ``on_feedback`` on score <= 2 with a ``suggested_modification``.
* **Drift check** (Phase 5a-3) — is the board still consistent with the
  current concept AND with each diagram's ORIGINAL claim across modifications?
  Driven by a periodic 30s loop in worker.py rather than a tool event. Routes
  through ``on_feedback`` when ``is_consistent`` is False with a
  ``suggested_action`` referencing ``modify_design_diagram`` or board cleanup.

NOT in the hot path — every mode runs in a fire-and-forget background task.
Feedback applies on the next LLM turn via ``drain_perception_feedback``.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import structlog

from feynman.agent.session_audit import SessionAudit

logger = structlog.get_logger()

# ── Dataclasses ─────────────────────────────────────────────


@dataclass(frozen=True)
class VerificationResult:
    """Layout quality assessment from the vision model."""

    score: int  # 1-5 (1=broken, 5=perfect)
    issues: list[str]  # Human-readable issue descriptions
    element_id: str  # Which element triggered this verification
    concept_index: int


@dataclass(frozen=True)
class FixAction:
    """Actionable fix suggestion derived from a verification issue."""

    element_id: str
    action: str  # "move", "resize", "remove_overlap"
    detail: str  # e.g. "move eq-2 right by 50px to avoid overlap with design-1"


# Phase 5a-1: annotation-accuracy verification result. Distinct from the
# layout-quality ``VerificationResult`` above; same screenshot path, different
# prompt + parse fields.
@dataclass(frozen=True)
class AnnotationVerificationResult:
    """Annotation-accuracy assessment from the vision model."""

    score: int  # 1-5 (1=wrong element, 5=perfect)
    intent_match: bool
    issue: str  # human-readable
    suggested_target: str | None  # role/id vision thinks was actually correct
    tool_name: str  # which annotation tool fired
    original_claim: str  # role/id the agent passed in
    original_target_id: str  # what the resolver landed on
    concept_index: int


# Phase 5a-2: diagram-intent verification result. Asks "does the rendered
# diagram match the agent's claim?" rather than "is the annotation on the
# right element?". Same screenshot path; different prompt + parse fields.
@dataclass(frozen=True)
class DiagramIntentVerificationResult:
    """Diagram-intent assessment from the vision model."""

    score: int  # 1-5 (1=clearly wrong, 5=perfect match)
    intent_match: bool
    issue: str
    suggested_modification: str | None  # natural-language fix, if any
    tool_name: str  # "draw_design_diagram" | "modify_design_diagram"
    original_claim: str  # the prompt for draw, modification for modify
    target_diagram_id: str
    diagram_version: int
    concept_index: int


# Phase 5a-3: periodic drift-check result. Asks "is the board still consistent
# with the current concept AND each diagram's original claim?" rather than
# inspecting a single just-fired event. Driven by the worker's 30s timer.
_VALID_DRIFT_KINDS = frozenset({"concept_fit", "cumulative_integrity", "both"})


@dataclass(frozen=True)
class DriftCheckResult:
    """Periodic drift assessment from the vision model.

    ``state_hash`` carries the (concept, sorted element_ids, versions) hash the
    caller computed before the screenshot capture, so the caller can dedup
    repeat checks against an unchanged board.
    """

    is_consistent: bool
    drift_kind: str | None  # "concept_fit" | "cumulative_integrity" | "both" | None
    affected_element_id: str | None
    issue: str
    suggested_action: str
    concept_index: int
    concept_title: str
    state_hash: str


@dataclass(frozen=True)
class PerceptionFeedback:
    """Structured feedback note delivered to the LLM via chat_ctx injection.

    Three flavours share one dataclass:

    * **Annotation** (5a-1) — ``tool_name`` is one of the annotation tools
      (``highlight_pulse``, ``pin_label_near``, ``draw_callout``, ``bracket``)
      or an action-tag verb; ``suggested_target`` + ``suggested_tag_syntax``
      drive the inline re-point hint.
    * **Diagram** (5a-2) — ``tool_name`` is ``draw_design_diagram`` or
      ``modify_design_diagram``; ``suggested_modification`` +
      ``target_diagram_id`` drive a re-call of ``modify_design_diagram``.
    * **Drift** (5a-3) — ``tool_name`` is ``periodic_drift_check``;
      ``original_claim`` carries the concept_title, ``drift_kind`` selects the
      remediation phrasing, ``suggested_action`` is a free-form directive
      (often a pre-baked ``modify_design_diagram(...)`` call).

    ``as_chat_note`` branches on ``tool_name`` so the LLM sees a format
    matched to the recovery path it should take.
    """

    tool_name: str
    original_claim: str
    score: int
    issue: str
    # Annotation fields (5a-1) — None/empty when this is a diagram/drift feedback.
    suggested_target: str | None = None
    suggested_tag_syntax: str = ""
    # Diagram fields (5a-2) — None when this is an annotation/drift feedback.
    suggested_modification: str | None = None
    target_diagram_id: str | None = None
    # Drift fields (5a-3) — None/empty when this is an annotation/diagram feedback.
    drift_kind: str | None = None  # "concept_fit" | "cumulative_integrity" | "both"
    suggested_action: str = ""

    def as_chat_note(self) -> str:
        """Format for injection into chat_ctx as a single user-role note."""
        if self.tool_name == "periodic_drift_check":
            return self._as_drift_chat_note()
        if self.tool_name in ("draw_design_diagram", "modify_design_diagram"):
            return self._as_diagram_chat_note()
        return self._as_annotation_chat_note()

    def _as_annotation_chat_note(self) -> str:
        suggestion = self.suggested_target or "<no suggestion>"
        return (
            "[PERCEPTION_FEEDBACK] Your previous "
            f"{self.tool_name} on '{self.original_claim}' missed "
            f"(score {self.score}/5). Issue: {self.issue}. "
            f"Suggested target: {suggestion}. "
            f"Re-point now: {self.suggested_tag_syntax}"
        )

    def _as_diagram_chat_note(self) -> str:
        diagram_id = self.target_diagram_id or "<unknown>"
        modification = self.suggested_modification or "<no suggestion>"
        return (
            "[PERCEPTION_FEEDBACK] Your previous "
            f"{self.tool_name} missed (score {self.score}/5). "
            f'Claim: "{self.original_claim}". Issue: {self.issue}. '
            "Fix it now: "
            f'modify_design_diagram(target_id="{diagram_id}", '
            f'modification="{modification}")'
        )

    def _as_drift_chat_note(self) -> str:
        # original_claim carries concept_title for drift feedback to keep the
        # dataclass compact (a field used only by one variant is dead weight
        # in the other two).
        kind = self.drift_kind or "unspecified"
        action = self.suggested_action or "<no suggestion>"
        return (
            "[PERCEPTION_FEEDBACK] Drift detected during concept "
            f"'{self.original_claim}'. Kind: {kind}. {self.issue}. "
            f"Suggested: {action}"
        )


# Maps tool name (or action-tag verb) → inline tag syntax for the retry hint.
_RETRY_TAG_SYNTAX: dict[str, str] = {
    "highlight_pulse": '<highlight target="{target}"/>',
    "pin_label_near": '<pin near="{target}" label="..."/>',
    "draw_callout": '<callout from="{target}" text="..."/>',
    "bracket": '<bracket between="{target}" label="..."/>',
}


def _build_retry_tag_syntax(tool_name: str, suggested_target: str | None) -> str:
    """Render the retry-tag string the LLM should re-emit."""
    if not suggested_target:
        return f"(use the right element for {tool_name})"
    template = _RETRY_TAG_SYNTAX.get(tool_name, '<highlight target="{target}"/>')
    return template.format(target=suggested_target)


# ── Verification prompt ────────────────────────────────────

_VERIFY_PROMPT = """\
You are checking a classroom whiteboard screenshot for layout issues.

Board context:
{board_context}

Analyze the screenshot and check for:
- Overlapping elements (text over diagrams, equations over other content)
- Awkward spacing (elements too close together or unevenly distributed)
- Unreadable labels (too small, cut off, or obscured)
- Content cut off at board edges

Respond ONLY with JSON (no markdown, no explanation):
{{"score": N, "issues": ["issue description 1", "issue description 2"]}}

Score guide: 1=broken/unreadable, 2=significant issues, 3=acceptable, 4=good, 5=perfect.
If no issues: {{"score": 5, "issues": []}}"""


# ── Annotation-accuracy verification prompt (Phase 5a-1) ───

_VERIFY_ANNOTATION_PROMPT = """\
You are checking whether a classroom-board annotation landed on the right element.

The teacher just applied a {tool_name} annotation:
- Claimed target: "{claim}"
- Resolved to element ID: "{target_id}"
- Spoken context: "{spoken_context}"

Board dictionary (semantic roles available):
{dictionary_lines}

Look at the screenshot. Did the annotation actually point at something matching
the claim? If the annotation is on the wrong element, suggest the role from the
dictionary that the agent SHOULD have targeted.

Respond ONLY with JSON (no markdown, no explanation):
{{"score": N, "intent_match": true|false, "issue": "...", "suggested_target": "role_or_id"}}

Score guide: 1=wrong element, 2=ambiguous/partially wrong, 3=acceptable, 4=correct, 5=perfect.
If intent_match is true, set suggested_target to null."""


# ── Diagram-intent verification prompt (Phase 5a-2) ────────

_VERIFY_DIAGRAM_INTENT_PROMPT = """\
You are checking whether a classroom diagram matches the teacher's stated intent.

The teacher just called {tool_name} on the board:
- Claim: "{claim}"
- Diagram contains semantic roles:
{role_list}

Look at the screenshot. Does the diagram actually depict what the claim says?

If something CLAIMED is missing or visibly wrong, suggest a natural-language
modification that would fix it (executable via modify_design_diagram).

Respond ONLY with JSON (no markdown, no explanation):
{{"score": N, "intent_match": true|false, "issue": "...", "suggested_modification": "...|null"}}

Score guide:
- 1 = clearly wrong / missing key claimed elements
- 2 = mostly wrong, partially matches
- 3 = acceptable, minor gaps
- 4 = correct
- 5 = perfect match

If intent_match is true, set suggested_modification to null."""


# ── Drift-check verification prompt (Phase 5a-3) ───────────

_VERIFY_DRIFT_PROMPT = """\
You are checking whether the current classroom board is still consistent with
what the teacher is teaching RIGHT NOW.

Current concept: "{concept_title}"
Concept description: {concept_description}
Lesson progress: concept {current_index} of {total_concepts}

Diagrams currently on the board (originals and version counts):
{element_summary}

Look at the screenshot. Two questions:

1. CONCEPT FIT — Does the board content still belong to the current concept?
   Or is there a stale diagram from a previous concept that should be erased
   or repurposed?

2. CUMULATIVE INTEGRITY — For each diagram listed above, does its current
   rendering still reflect its ORIGINAL claim, given any modifications since?
   A diagram should evolve through modifications but never lose the core
   intent it was drawn for.

Respond ONLY with JSON (no markdown):
{{"is_consistent": true|false, "drift_kind": "concept_fit"|"cumulative_integrity"|"both"|null, "affected_element_id": "..."|null, "issue": "...", "suggested_action": "..."}}

Drift kind guide:
- "concept_fit" = a diagram is stale/irrelevant for the current concept
- "cumulative_integrity" = a diagram has drifted from its original intent
- "both" = both problems apply
- null = no drift, is_consistent=true

If is_consistent is true, set drift_kind/affected_element_id to null and
issue/suggested_action to empty strings.

Suggested action format:
- For cumulative_integrity: 'modify_design_diagram(target_id="X", modification="...")'
- For concept_fit: 'Erase or repurpose design-X — it no longer fits the current concept'
- For both: lead with the more pressing fix"""


# Cap on how much of the agent's claim we forward to the verifier. Very long
# prompts dilute Haiku's focus; 250 chars covers any reasonable claim.
_CLAIM_MAX_CHARS = 250


def _truncate_claim(claim: str) -> str:
    """Truncate a verbose claim for the verification prompt."""
    claim = claim.strip()
    if len(claim) <= _CLAIM_MAX_CHARS:
        return claim
    return claim[:_CLAIM_MAX_CHARS].rstrip() + "…"


def _format_role_list(roles: list[str]) -> str:
    """One ``- role`` line per entry; cap at 20 for prompt size sanity."""
    capped = [r for r in roles if r][:20]
    if not capped:
        return "(no roles)"
    return "\n".join(f"- {r}" for r in capped)


def _format_element_summary(rows: list[tuple[str, str, int]]) -> str:
    """One ``- element_id (modified Nx): "original claim"`` line per row.

    Truncates each claim with :func:`_truncate_claim` (250 char cap) so the
    drift prompt never balloons when an early ``draw_design_diagram`` prompt
    was unusually long.
    """
    if not rows:
        return "(no diagrams)"
    lines: list[str] = []
    for element_id, original_claim, modify_count in rows:
        claim = _truncate_claim(original_claim)
        if modify_count == 0:
            modifier = "original"
        elif modify_count == 1:
            modifier = "modified 1x"
        else:
            modifier = f"modified {modify_count}x"
        lines.append(f'- {element_id} ({modifier}): "{claim}"')
    return "\n".join(lines)


# ── Element ID pattern for fix extraction ──────────────────

_ELEMENT_ID_RE = re.compile(r"\b(design-\d+|text-\d+|eq-\d+|scene-\d+|graph-\d+|steps-\d+)\b")


# ── BoardVerifier ──────────────────────────────────────────


PublishFn = Callable[[str, str], Coroutine[Any, Any, None]]
# Phase 5a-2: handler accepts any verification result type (annotation,
# diagram intent, or layout) because the closure typically only needs the
# feedback itself; the result is provided for callers that want to introspect.
PerceptionFeedbackHandler = Callable[[PerceptionFeedback, Any], None]


def _format_dictionary_lines(dictionary: dict[str, Any]) -> str:
    """One ``role → id`` line per dictionary entry for the vision prompt."""
    lines: list[str] = []
    for elem_id, meta in dictionary.items():
        role = getattr(meta, "role", None)
        if role is None and isinstance(meta, dict):
            role = meta.get("role")
        semantic = getattr(meta, "semantic", None)
        if semantic is None and isinstance(meta, dict):
            semantic = meta.get("semantic")
        if role:
            lines.append(f"- {role} → {elem_id} ({semantic or '...'})")
        else:
            lines.append(f"- {elem_id} ({semantic or '...'})")
    return "\n".join(lines) if lines else "(no roles)"


class BoardVerifier:
    """Async visual verification of the classroom board.

    Captures a board screenshot via data channel round-trip, sends to a fast
    vision model (Haiku), and routes results to audit + (optionally) the LLM
    feedback queue. Four verification modes share this class:

    * **Layout quality** — :meth:`request_verification`. Audit-only by default;
      pass ``on_feedback`` to enqueue a recovery hint on severe scores.
    * **Annotation accuracy** — :meth:`request_annotation_verification`
      (Phase 5a-1). Routes through ``on_feedback`` on score <= 2 with a
      usable ``suggested_target``.
    * **Diagram intent** — :meth:`request_diagram_intent_verification`
      (Phase 5a-2). Routes through ``on_feedback`` on score <= 2 with a
      ``suggested_modification`` referencing ``modify_design_diagram``.
    * **Drift check** — :meth:`request_drift_check` (Phase 5a-3). Driven by
      a periodic 30s timer in worker.py. Routes through ``on_feedback`` when
      ``is_consistent`` is False with a ``suggested_action``.

    Triggers (Phases 5a-1/5a-2 — continuous): every ``draw_design_diagram``,
    ``modify_design_diagram``, ``draw_scene``, and annotation event. Per-
    ``(element_id, version, concept)`` dedup at the caller prevents thrash;
    the 2-per-concept feedback budget caps LLM-visible noise. Drift checks
    (Phase 5a-3) use a separate 1-per-concept budget and state-hash dedup.
    """

    def __init__(self, publish_fn: PublishFn, audit: SessionAudit) -> None:
        self._publish = publish_fn
        self._audit = audit
        self._pending: dict[str, asyncio.Future[str]] = {}

    # ── Public API ──────────────────────────────────────────

    async def request_verification(
        self,
        element_id: str,
        concept_index: int,
        board_context: str,
        on_feedback: PerceptionFeedbackHandler | None = None,
        original_claim: str | None = None,
    ) -> VerificationResult | None:
        """Full verification flow — screenshot capture → vision model → audit.

        Called as background task via asyncio.create_task(). Never blocks teaching.
        Returns the result for testing; callers don't need to use it.

        Phase 5a-2: when ``on_feedback`` is provided and ``score <= 2`` with at
        least one actionable :class:`FixAction`, build a
        :class:`PerceptionFeedback` of variant ``modify_design_diagram`` and
        invoke the callback. Audit logging remains unchanged.
        """
        try:
            # 1. Request screenshot from frontend.
            screenshot = await self._request_screenshot()
            if screenshot is None:
                self._audit.record(
                    "visual_verification",
                    "screenshot_timeout",
                    f"element_id={element_id}, concept={concept_index}",
                )
                logger.warning(
                    "visual_verification.screenshot_timeout",
                    element_id=element_id,
                    concept=concept_index,
                )
                return None

            # 2. Send to vision model.
            result = await self._verify_with_vision(
                screenshot,
                board_context,
                element_id,
                concept_index,
            )

            # 3. Log to audit.
            self._audit.record(
                "visual_verification",
                "result",
                f"score={result.score}, issues={len(result.issues)}, element_id={element_id}",
            )
            logger.info(
                "visual_verification.result",
                score=result.score,
                issues=len(result.issues),
                element_id=element_id,
                concept=concept_index,
            )

            # 4. Suggest fixes if score is low; audit-log every suggestion and,
            # when on_feedback is wired, surface severe issues to the LLM.
            fixes: list[FixAction] = []
            if result.score <= 3:
                fixes = suggest_fixes(result)
                for fix in fixes:
                    self._audit.record(
                        "visual_verification",
                        "fix_suggested",
                        f"{fix.action}: {fix.detail}",
                    )

            if on_feedback is not None and result.score <= 2 and fixes:
                primary_fix = fixes[0]
                issue_summary = ", ".join(result.issues) if result.issues else "layout issues"
                if len(issue_summary) > 200:
                    issue_summary = issue_summary[:200].rstrip() + "…"
                claim_label = original_claim or "last diagram event"
                feedback = PerceptionFeedback(
                    tool_name="modify_design_diagram",
                    original_claim=f"layout: {claim_label}",
                    score=result.score,
                    issue=issue_summary,
                    suggested_modification=primary_fix.detail,
                    target_diagram_id=element_id,
                )
                on_feedback(feedback, result)

            return result

        except Exception:
            logger.exception(
                "visual_verification.error",
                element_id=element_id,
                concept=concept_index,
            )
            self._audit.record(
                "visual_verification",
                "error",
                f"element_id={element_id}, concept={concept_index}",
            )
            return None

    async def request_annotation_verification(
        self,
        *,
        tool_name: str,
        original_claim: str,
        target_id: str,
        spoken_context: str,
        dictionary: dict[str, Any],
        concept_index: int,
        on_feedback: PerceptionFeedbackHandler | None = None,
    ) -> AnnotationVerificationResult | None:
        """Phase 5a-1: vision check that an annotation landed on the right element.

        Fire-and-forget. Captures the screen, asks Haiku to compare the
        annotation against the claim + dictionary, and if the score is low
        + a usable suggestion exists, calls ``on_feedback`` with a
        :class:`PerceptionFeedback` ready to inject into ``chat_ctx``.
        """
        try:
            screenshot = await self._request_screenshot()
            if screenshot is None:
                self._audit.record(
                    "annotation_verification",
                    "screenshot_timeout",
                    f"tool={tool_name}, target={target_id}, concept={concept_index}",
                )
                logger.warning(
                    "annotation_verification.screenshot_timeout",
                    tool=tool_name,
                    target=target_id,
                    concept=concept_index,
                )
                return None

            result = await self._verify_annotation_with_vision(
                screenshot,
                tool_name=tool_name,
                original_claim=original_claim,
                target_id=target_id,
                spoken_context=spoken_context,
                dictionary=dictionary,
                concept_index=concept_index,
            )

            self._audit.record(
                "annotation_verification",
                "result",
                f"tool={tool_name}, target={target_id}, "
                f"score={result.score}, intent_match={result.intent_match}",
            )
            logger.info(
                "annotation_verification.result",
                tool=tool_name,
                claim=original_claim,
                target=target_id,
                score=result.score,
                intent_match=result.intent_match,
                suggested=result.suggested_target,
                concept=concept_index,
            )

            if result.score <= 2 and result.suggested_target and on_feedback is not None:
                feedback = PerceptionFeedback(
                    tool_name=tool_name,
                    original_claim=original_claim,
                    score=result.score,
                    issue=result.issue,
                    suggested_target=result.suggested_target,
                    suggested_tag_syntax=_build_retry_tag_syntax(
                        tool_name, result.suggested_target
                    ),
                )
                on_feedback(feedback, result)

            return result

        except Exception:
            logger.exception(
                "annotation_verification.error",
                tool=tool_name,
                target=target_id,
                concept=concept_index,
            )
            self._audit.record(
                "annotation_verification",
                "error",
                f"tool={tool_name}, target={target_id}, concept={concept_index}",
            )
            return None

    async def request_diagram_intent_verification(
        self,
        *,
        tool_name: str,
        original_claim: str,
        target_diagram_id: str,
        diagram_version: int,
        role_list: list[str],
        concept_index: int,
        on_feedback: PerceptionFeedbackHandler | None = None,
    ) -> DiagramIntentVerificationResult | None:
        """Phase 5a-2: vision check that the diagram matches the agent's intent.

        Fire-and-forget. Captures the screen, asks Haiku to compare the
        rendered diagram against the agent's claim + role list, and if the
        score is low + a usable suggestion exists, calls ``on_feedback`` with
        a :class:`PerceptionFeedback` of variant ``draw_design_diagram`` or
        ``modify_design_diagram`` ready to inject into ``chat_ctx``.
        """
        try:
            screenshot = await self._request_screenshot()
            if screenshot is None:
                self._audit.record(
                    "diagram_intent_verification",
                    "screenshot_timeout",
                    f"tool={tool_name}, diagram={target_diagram_id}, "
                    f"version={diagram_version}, concept={concept_index}",
                )
                logger.warning(
                    "diagram_intent_verification.screenshot_timeout",
                    tool=tool_name,
                    diagram=target_diagram_id,
                    version=diagram_version,
                    concept=concept_index,
                )
                return None

            result = await self._verify_diagram_intent_with_vision(
                screenshot,
                tool_name=tool_name,
                original_claim=original_claim,
                target_diagram_id=target_diagram_id,
                diagram_version=diagram_version,
                role_list=role_list,
                concept_index=concept_index,
            )

            self._audit.record(
                "diagram_intent_verification",
                "result",
                f"tool={tool_name}, diagram={target_diagram_id}, "
                f"version={diagram_version}, score={result.score}, "
                f"intent_match={result.intent_match}",
            )
            logger.info(
                "diagram_intent_verification.result",
                tool=tool_name,
                claim=result.original_claim,
                diagram=target_diagram_id,
                version=diagram_version,
                score=result.score,
                intent_match=result.intent_match,
                suggested=result.suggested_modification,
                concept=concept_index,
            )

            if result.score <= 2 and result.suggested_modification and on_feedback is not None:
                feedback = PerceptionFeedback(
                    tool_name=tool_name,
                    original_claim=original_claim,
                    score=result.score,
                    issue=result.issue,
                    suggested_modification=result.suggested_modification,
                    target_diagram_id=target_diagram_id,
                )
                on_feedback(feedback, result)

            return result

        except Exception:
            logger.exception(
                "diagram_intent_verification.error",
                tool=tool_name,
                diagram=target_diagram_id,
                version=diagram_version,
                concept=concept_index,
            )
            self._audit.record(
                "diagram_intent_verification",
                "error",
                f"tool={tool_name}, diagram={target_diagram_id}, "
                f"version={diagram_version}, concept={concept_index}",
            )
            return None

    async def request_drift_check(
        self,
        *,
        concept_index: int,
        concept_title: str,
        concept_description: str,
        total_concepts: int,
        element_summary: list[tuple[str, str, int]],
        state_hash: str,
        on_feedback: PerceptionFeedbackHandler | None = None,
    ) -> DriftCheckResult | None:
        """Phase 5a-3: vision check that the board still fits the lesson.

        Driven by a periodic 30s timer in worker.py rather than a tool event.
        Captures the screen, asks Haiku to compare board contents against the
        current concept context AND each diagram's original claim, and if
        drift is found, calls ``on_feedback`` with a drift-flavoured
        :class:`PerceptionFeedback`.

        Returns ``None`` when there's nothing meaningful to check (empty board
        with no concept description), when the screenshot times out, or when
        Haiku errors. The caller uses this to decide whether to commit the
        ``state_hash`` for dedup.
        """
        # Skip when there's nothing to verify against — saves a Haiku call.
        if not element_summary and not concept_description.strip():
            self._audit.record(
                "drift_check",
                "skipped_no_context",
                f"concept={concept_index}",
            )
            return None

        try:
            screenshot = await self._request_screenshot()
            if screenshot is None:
                self._audit.record(
                    "drift_check",
                    "screenshot_timeout",
                    f"concept={concept_index}, hash={state_hash}",
                )
                logger.warning(
                    "drift_check.screenshot_timeout",
                    concept=concept_index,
                    state_hash=state_hash,
                )
                return None

            result = await self._verify_drift_with_vision(
                screenshot,
                concept_index=concept_index,
                concept_title=concept_title,
                concept_description=concept_description,
                total_concepts=total_concepts,
                element_summary=element_summary,
                state_hash=state_hash,
            )

            self._audit.record(
                "drift_check",
                "completed",
                f"concept={concept_index}, is_consistent={result.is_consistent}, "
                f"drift_kind={result.drift_kind}, hash={state_hash}",
            )
            logger.info(
                "drift_check.completed",
                concept=concept_index,
                concept_title=concept_title,
                is_consistent=result.is_consistent,
                drift_kind=result.drift_kind,
                affected=result.affected_element_id,
                state_hash=state_hash,
            )

            if not result.is_consistent and on_feedback is not None:
                feedback = PerceptionFeedback(
                    tool_name="periodic_drift_check",
                    original_claim=concept_title,
                    score=0,
                    issue=result.issue,
                    drift_kind=result.drift_kind,
                    suggested_action=result.suggested_action,
                    target_diagram_id=result.affected_element_id,
                )
                on_feedback(feedback, result)

            return result

        except Exception:
            logger.exception(
                "drift_check.error",
                concept=concept_index,
                state_hash=state_hash,
            )
            self._audit.record(
                "drift_check",
                "error",
                f"concept={concept_index}, hash={state_hash}",
            )
            return None

    def resolve_capture(self, request_id: str, image_b64: str) -> None:
        """Called by data channel handler when frontend responds with screenshot."""
        future = self._pending.get(request_id)
        if future and not future.done():
            future.set_result(image_b64)

    # ── Internal ────────────────────────────────────────────

    async def _request_screenshot(self) -> str | None:
        """Send capture request via data channel, await response with timeout."""
        request_id = str(uuid4())
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._pending[request_id] = future

        await self._publish(
            json.dumps(
                {
                    "type": "capture_board",
                    "request_id": request_id,
                    "max_width": 512,
                    "max_height": 288,
                }
            ),
            "board_capture",
        )

        try:
            async with asyncio.timeout(5.0):
                return await future
        except TimeoutError:
            return None
        finally:
            self._pending.pop(request_id, None)

    async def _verify_with_vision(
        self,
        screenshot_b64: str,
        board_context: str,
        element_id: str,
        concept_index: int,
    ) -> VerificationResult:
        """Call Haiku vision model for layout quality check."""
        import anthropic

        from feynman.config import settings

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        prompt_text = _VERIFY_PROMPT.format(board_context=board_context)

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_b64,
                            },
                        },
                        {"type": "text", "text": prompt_text},
                    ],
                }
            ],
        )

        return _parse_vision_response(
            response.content[0].text if response.content else "{}",
            element_id,
            concept_index,
        )

    async def _verify_annotation_with_vision(
        self,
        screenshot_b64: str,
        *,
        tool_name: str,
        original_claim: str,
        target_id: str,
        spoken_context: str,
        dictionary: dict[str, Any],
        concept_index: int,
    ) -> AnnotationVerificationResult:
        """Call Haiku vision model for annotation-accuracy check."""
        import anthropic

        from feynman.config import settings

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        prompt_text = _VERIFY_ANNOTATION_PROMPT.format(
            tool_name=tool_name,
            claim=original_claim,
            target_id=target_id,
            spoken_context=spoken_context or "(none)",
            dictionary_lines=_format_dictionary_lines(dictionary),
        )

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_b64,
                            },
                        },
                        {"type": "text", "text": prompt_text},
                    ],
                }
            ],
        )

        return _parse_annotation_response(
            response.content[0].text if response.content else "{}",
            tool_name=tool_name,
            original_claim=original_claim,
            target_id=target_id,
            concept_index=concept_index,
        )

    async def _verify_diagram_intent_with_vision(
        self,
        screenshot_b64: str,
        *,
        tool_name: str,
        original_claim: str,
        target_diagram_id: str,
        diagram_version: int,
        role_list: list[str],
        concept_index: int,
    ) -> DiagramIntentVerificationResult:
        """Call Haiku vision model for diagram-intent check."""
        import anthropic

        from feynman.config import settings

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        truncated_claim = _truncate_claim(original_claim)
        prompt_text = _VERIFY_DIAGRAM_INTENT_PROMPT.format(
            tool_name=tool_name,
            claim=truncated_claim,
            role_list=_format_role_list(role_list),
        )

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_b64,
                            },
                        },
                        {"type": "text", "text": prompt_text},
                    ],
                }
            ],
        )

        return _parse_diagram_intent_response(
            response.content[0].text if response.content else "{}",
            tool_name=tool_name,
            original_claim=truncated_claim,
            target_diagram_id=target_diagram_id,
            diagram_version=diagram_version,
            concept_index=concept_index,
        )

    async def _verify_drift_with_vision(
        self,
        screenshot_b64: str,
        *,
        concept_index: int,
        concept_title: str,
        concept_description: str,
        total_concepts: int,
        element_summary: list[tuple[str, str, int]],
        state_hash: str,
    ) -> DriftCheckResult:
        """Call Haiku vision model for periodic drift check."""
        import anthropic

        from feynman.config import settings

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        # Cap to top 10 for prompt sanity — caller's build_element_summary
        # should already enforce, but defensive truncation lives here too.
        capped = element_summary[:10]
        prompt_text = _VERIFY_DRIFT_PROMPT.format(
            concept_title=concept_title,
            concept_description=concept_description.strip() or "(no description)",
            current_index=concept_index,
            total_concepts=total_concepts,
            element_summary=_format_element_summary(capped),
        )

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_b64,
                            },
                        },
                        {"type": "text", "text": prompt_text},
                    ],
                }
            ],
        )

        return _parse_drift_response(
            response.content[0].text if response.content else "{}",
            concept_index=concept_index,
            concept_title=concept_title,
            state_hash=state_hash,
        )


# ── Response parsing ───────────────────────────────────────


def _parse_vision_response(
    text: str,
    element_id: str,
    concept_index: int,
) -> VerificationResult:
    """Parse the vision model's JSON response with graceful fallback."""
    try:
        # Strip markdown fences if present.
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"```(?:json)?\s*\n?", "", cleaned)
            cleaned = cleaned.rstrip("`").strip()

        data = json.loads(cleaned)
        score = int(data.get("score", 3))
        score = max(1, min(5, score))  # Clamp to 1-5.
        issues = data.get("issues", [])
        if not isinstance(issues, list):
            issues = [str(issues)]
        issues = [str(i) for i in issues]
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("visual_verification.parse_failed", raw=text[:200])
        score = 3
        issues = [f"Could not parse verification response: {text[:100]}"]

    return VerificationResult(
        score=score,
        issues=issues,
        element_id=element_id,
        concept_index=concept_index,
    )


def _parse_annotation_response(
    text: str,
    *,
    tool_name: str,
    original_claim: str,
    target_id: str,
    concept_index: int,
) -> AnnotationVerificationResult:
    """Parse the annotation-accuracy JSON response with graceful fallback.

    On parse failure: conservatively return score=3, intent_match=True,
    suggested_target=None — so a malformed Haiku response never triggers
    a false-positive retry.
    """
    try:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"```(?:json)?\s*\n?", "", cleaned)
            cleaned = cleaned.rstrip("`").strip()

        data = json.loads(cleaned)
        score = int(data.get("score", 3))
        score = max(1, min(5, score))
        intent_match = bool(data.get("intent_match", True))
        issue_raw = data.get("issue", "")
        issue = str(issue_raw) if issue_raw is not None else ""
        suggested_raw = data.get("suggested_target")
        suggested_target: str | None
        if suggested_raw is None or suggested_raw == "":
            suggested_target = None
        else:
            suggested_target = str(suggested_raw)
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("annotation_verification.parse_failed", raw=text[:200])
        score = 3
        intent_match = True
        issue = f"Could not parse verification response: {text[:100]}"
        suggested_target = None

    return AnnotationVerificationResult(
        score=score,
        intent_match=intent_match,
        issue=issue,
        suggested_target=suggested_target,
        tool_name=tool_name,
        original_claim=original_claim,
        original_target_id=target_id,
        concept_index=concept_index,
    )


def _parse_diagram_intent_response(
    text: str,
    *,
    tool_name: str,
    original_claim: str,
    target_diagram_id: str,
    diagram_version: int,
    concept_index: int,
) -> DiagramIntentVerificationResult:
    """Parse the diagram-intent JSON response with graceful fallback.

    On parse failure: conservatively return score=3, intent_match=True,
    suggested_modification=None — so a malformed Haiku response never
    triggers a false-positive modify retry.
    """
    try:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"```(?:json)?\s*\n?", "", cleaned)
            cleaned = cleaned.rstrip("`").strip()

        data = json.loads(cleaned)
        score = int(data.get("score", 3))
        score = max(1, min(5, score))
        intent_match = bool(data.get("intent_match", True))
        issue_raw = data.get("issue", "")
        issue = str(issue_raw) if issue_raw is not None else ""
        suggested_raw = data.get("suggested_modification")
        suggested_modification: str | None
        if suggested_raw is None or suggested_raw == "":
            suggested_modification = None
        else:
            suggested_modification = str(suggested_raw)
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("diagram_intent_verification.parse_failed", raw=text[:200])
        score = 3
        intent_match = True
        issue = f"Could not parse verification response: {text[:100]}"
        suggested_modification = None

    return DiagramIntentVerificationResult(
        score=score,
        intent_match=intent_match,
        issue=issue,
        suggested_modification=suggested_modification,
        tool_name=tool_name,
        original_claim=original_claim,
        target_diagram_id=target_diagram_id,
        diagram_version=diagram_version,
        concept_index=concept_index,
    )


def _parse_drift_response(
    text: str,
    *,
    concept_index: int,
    concept_title: str,
    state_hash: str,
) -> DriftCheckResult:
    """Parse the drift-check JSON response with graceful fallback.

    On parse failure: conservatively return is_consistent=True so a malformed
    Haiku response never triggers a false-positive drift recovery. Unknown
    ``drift_kind`` values are coerced to None (and flip the result to
    consistent).
    """
    try:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"```(?:json)?\s*\n?", "", cleaned)
            cleaned = cleaned.rstrip("`").strip()

        data = json.loads(cleaned)
        is_consistent = bool(data.get("is_consistent", True))

        drift_kind_raw = data.get("drift_kind")
        if drift_kind_raw in _VALID_DRIFT_KINDS:
            drift_kind: str | None = str(drift_kind_raw)
        else:
            drift_kind = None
            # Unknown kind on an inconsistent result — fall back to consistent.
            if not is_consistent and drift_kind_raw is not None:
                logger.warning(
                    "drift_check.unknown_drift_kind",
                    raw=str(drift_kind_raw)[:50],
                )
                is_consistent = True

        affected_raw = data.get("affected_element_id")
        if affected_raw is None or affected_raw == "":
            affected_element_id: str | None = None
        else:
            affected_element_id = str(affected_raw)

        issue_raw = data.get("issue", "")
        issue = str(issue_raw) if issue_raw is not None else ""
        action_raw = data.get("suggested_action", "")
        suggested_action = str(action_raw) if action_raw is not None else ""

        # Inconsistent claim with no actionable content → treat as consistent.
        if not is_consistent and not issue.strip() and not suggested_action.strip():
            is_consistent = True
            drift_kind = None
            affected_element_id = None
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("drift_check.parse_failed", raw=text[:200])
        is_consistent = True
        drift_kind = None
        affected_element_id = None
        issue = ""
        suggested_action = ""

    return DriftCheckResult(
        is_consistent=is_consistent,
        drift_kind=drift_kind,
        affected_element_id=affected_element_id,
        issue=issue,
        suggested_action=suggested_action,
        concept_index=concept_index,
        concept_title=concept_title,
        state_hash=state_hash,
    )


# ── Fix suggestions ────────────────────────────────────────


def suggest_fixes(result: VerificationResult) -> list[FixAction]:
    """Derive actionable fix suggestions from verification issues.

    Simple keyword extraction — not another LLM call.
    """
    fixes: list[FixAction] = []
    for issue in result.issues:
        issue_lower = issue.lower()

        # Extract element IDs mentioned in the issue.
        mentioned_ids = _ELEMENT_ID_RE.findall(issue)
        target_id = mentioned_ids[0] if mentioned_ids else result.element_id

        if "overlap" in issue_lower:
            fixes.append(
                FixAction(
                    element_id=target_id,
                    action="remove_overlap",
                    detail=issue,
                )
            )
        elif "spacing" in issue_lower or "close" in issue_lower or "cramped" in issue_lower:
            fixes.append(
                FixAction(
                    element_id=target_id,
                    action="move",
                    detail=issue,
                )
            )
        elif (
            "cut off" in issue_lower
            or "truncat" in issue_lower
            or "edge" in issue_lower
            or "small" in issue_lower
            or "unreadable" in issue_lower
            or "tiny" in issue_lower
        ):
            fixes.append(
                FixAction(
                    element_id=target_id,
                    action="resize",
                    detail=issue,
                )
            )
        else:
            # Generic fix for unrecognized issues.
            fixes.append(
                FixAction(
                    element_id=target_id,
                    action="move",
                    detail=issue,
                )
            )

    return fixes
