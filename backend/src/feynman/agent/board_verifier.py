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


# ── Element ID pattern for fix extraction ──────────────────

_ELEMENT_ID_RE = re.compile(r"\b(design-\d+|text-\d+|eq-\d+|scene-\d+|graph-\d+|steps-\d+)\b")


# ── BoardVerifier ──────────────────────────────────────────


PublishFn = Callable[[str, str], Coroutine[Any, Any, None]]


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
                screenshot, board_context, element_id, concept_index,
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
            json.dumps({
                "type": "capture_board",
                "request_id": request_id,
                "max_width": 512,
                "max_height": 288,
            }),
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
            messages=[{
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
            }],
        )

        return _parse_vision_response(
            response.content[0].text if response.content else "{}",
            element_id,
            concept_index,
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
            fixes.append(FixAction(
                element_id=target_id,
                action="remove_overlap",
                detail=issue,
            ))
        elif "spacing" in issue_lower or "close" in issue_lower or "cramped" in issue_lower:
            fixes.append(FixAction(
                element_id=target_id,
                action="move",
                detail=issue,
            ))
        elif (
            "cut off" in issue_lower
            or "truncat" in issue_lower
            or "edge" in issue_lower
            or "small" in issue_lower
            or "unreadable" in issue_lower
            or "tiny" in issue_lower
        ):
            fixes.append(FixAction(
                element_id=target_id,
                action="resize",
                detail=issue,
            ))
        else:
            # Generic fix for unrecognized issues.
            fixes.append(FixAction(
                element_id=target_id,
                action="move",
                detail=issue,
            ))

    return fixes
