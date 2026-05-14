"""Board Visual Verification — async layout quality checks via vision model.

After rendering expensive visuals (design diagrams, scenes), captures a board
screenshot and sends it to a fast vision model (Haiku) to check for layout
issues: overlapping text, awkward spacing, unreadable labels.

NOT in the hot path — runs in background, at most once per concept.
Fix suggestions are logged to audit, not auto-applied.
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


@dataclass(frozen=True)
class PerceptionFeedback:
    """Structured feedback note delivered to the LLM via chat_ctx injection.

    Built by ``request_annotation_verification`` when a low-score verification
    has a usable ``suggested_target``. The ``llm_node`` override in
    ``FeynmanAgent`` drains these onto the next LLM turn as user-role notes.
    """

    tool_name: str
    original_claim: str
    score: int
    issue: str
    suggested_target: str | None
    suggested_tag_syntax: str  # pre-baked retry tag, e.g. <highlight target="side_AB"/>

    def as_chat_note(self) -> str:
        """Format for injection into chat_ctx as a single user-role note."""
        suggestion = self.suggested_target or "<no suggestion>"
        return (
            "[PERCEPTION_FEEDBACK] Your previous "
            f"{self.tool_name} on '{self.original_claim}' missed "
            f"(score {self.score}/5). Issue: {self.issue}. "
            f"Suggested target: {suggestion}. "
            f"Re-point now: {self.suggested_tag_syntax}"
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


# ── Element ID pattern for fix extraction ──────────────────

_ELEMENT_ID_RE = re.compile(r"\b(design-\d+|text-\d+|eq-\d+|scene-\d+|graph-\d+|steps-\d+)\b")


# ── BoardVerifier ──────────────────────────────────────────


PublishFn = Callable[[str, str], Coroutine[Any, Any, None]]
PerceptionFeedbackHandler = Callable[[PerceptionFeedback, "AnnotationVerificationResult"], None]


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
    """Async visual verification of board layout quality.

    Captures a board screenshot via data channel round-trip, sends to
    a fast vision model (Haiku), and logs quality assessment to audit.

    Triggers: only after draw_design_diagram or draw_scene.
    Frequency: at most once per concept (guarded by TeachingContext._verified_this_concept).
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
    ) -> VerificationResult | None:
        """Full verification flow — screenshot capture → vision model → audit.

        Called as background task via asyncio.create_task(). Never blocks teaching.
        Returns the result for testing; callers don't need to use it.
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

            # 4. Suggest fixes if score is low.
            if result.score <= 3:
                fixes = suggest_fixes(result)
                for fix in fixes:
                    self._audit.record(
                        "visual_verification",
                        "fix_suggested",
                        f"{fix.action}: {fix.detail}",
                    )

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
