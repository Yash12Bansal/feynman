"""LiveKit agent worker entrypoint. Run as separate process.

cd backend && uv run python -m feynman.livekit.worker dev
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator, AsyncIterable, Callable
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog
from feynman_teaching_kernel import plan_concept
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli
from livekit.rtc import DataPacket

from feynman.agent.action_tag_parser import ActionTag, ActionTagParser
from feynman.agent.board_verifier import BoardVerifier, PerceptionFeedback
from feynman.agent.curriculum_loader import load_curriculum
from feynman.agent.drift_state import build_element_summary, compute_drift_state_hash
from feynman.agent.lesson_plan import lesson_plan_from_curriculum
from feynman.agent.prompts import TEACHING_SYSTEM_PROMPT, build_teaching_prompt
from feynman.livekit.action_tag_dispatch import dispatch_action_tag

if TYPE_CHECKING:
    from livekit import rtc
    from livekit.agents.llm import (
        ChatChunk,
        ChatContext,
        FunctionTool,
        ModelSettings,
    )
from feynman.agent.scene_graph import BoundsReportPayload
from feynman.agent.state_machine import TeachingStateMachine
from feynman.agent.states import TeachingState
from feynman.agent.teaching_context import TeachingContext
from feynman.agent.tools import (
    advance_concept,
    annotate,
    bracket,
    clear_board,
    clear_cluster,
    draw_callout,
    draw_design_diagram,
    draw_diagram,
    draw_scene,
    highlight_diagram_part,
    highlight_pulse,
    highlight_walk,
    mark_doubt_step_complete,
    modify_design_diagram,
    new_page,
    pin_label_near,
    resolve_doubt,
    scroll_board,
    set_lesson_topic,
    show_equation,
    show_graph,
    # show_text,
    start_doubt_branch,
    step_equation,
    strikethrough,
    switch_board,
    teach_pause,
    write_answer,
    write_equation,
    write_section,
    write_step,
    write_text,
)
from feynman.common.logging import setup_logging
from feynman.common.types import Subject
from feynman.config import settings
from feynman.livekit.pipeline import create_llm, create_stt, create_tts, create_vad

setup_logging(settings.log_level)
logger = structlog.get_logger()

# Phase 5a-3: periodic drift-check cadence. 30s balances detection latency
# (caught within one student utterance window) against Haiku cost — combined
# with the state-hash dedup in _should_run_drift_check, typical hourly call
# count stays around 25-30 (~$0.05-0.10/hr).
DRIFT_CHECK_INTERVAL_SECS = 30.0
DRIFT_FEEDBACK_BUDGET_PER_CONCEPT = 1

# All tools the agent can use — visual + state management
ALL_TOOLS = [
    # show_text,
    show_equation,
    draw_design_diagram,
    modify_design_diagram,
    draw_diagram,
    draw_scene,
    step_equation,
    show_graph,
    # Notebook write-tools (split-board Phase 5 native surface)
    write_equation,
    write_step,
    write_text,
    write_section,
    write_answer,
    strikethrough,
    new_page,
    annotate,
    highlight_diagram_part,
    highlight_walk,
    # Slide annotation overlays (diagram awareness)
    pin_label_near,
    draw_callout,
    bracket,
    highlight_pulse,
    clear_board,
    clear_cluster,
    teach_pause,
    advance_concept,
    start_doubt_branch,
    resolve_doubt,
    mark_doubt_step_complete,
    switch_board,
    scroll_board,
    set_lesson_topic,
]


async def strip_action_tags(
    text: AsyncIterable[str],
    on_tag: Callable[[ActionTag], None],
) -> AsyncGenerator[str]:
    """Strip inline action tags from a streaming text iterable.

    Yields TTS-bound chunks with action tags removed. Each parsed tag is
    handed to ``on_tag`` synchronously (the worker schedules an async
    dispatch task there). Orphan tag fragments at stream end are dropped
    by ``ActionTagParser.finalize``.
    """
    parser = ActionTagParser()
    async for chunk in text:
        clean, tags = parser.feed(chunk)
        for tag in tags:
            on_tag(tag)
        if clean:
            yield clean
    tail = parser.finalize()
    if tail:
        yield tail


def drain_perception_feedback(
    teaching_ctx: TeachingContext,
    chat_ctx: ChatContext,
) -> int:
    """Drain Phase 5a-1 perception-feedback queue into ``chat_ctx``.

    Appends each ``PerceptionFeedback`` as a single ``role="user"`` note
    using ``[PERCEPTION_FEEDBACK]`` as the system-signal prefix the prompt
    teaches the LLM to recognize. Returns the number of feedbacks drained
    so the caller can log it.
    """
    queue = teaching_ctx.perception_feedback_queue
    if not queue:
        return 0
    count = len(queue)
    for fb in queue:
        chat_ctx.add_message(role="user", content=fb.as_chat_note())
    queue.clear()
    logger.info(
        "perception_feedback.injected",
        count=count,
        concept=teaching_ctx.current_concept_index,
    )
    return count


# ── Phase 5a-3: periodic drift check helpers ──────────────────


def _should_run_drift_check(tc: TeachingContext) -> bool:
    """Cheap pre-flight before spending a Haiku call on a drift check.

    Audits each skip reason so the session summary can attribute Haiku-call
    misses correctly (state-hash dedup vs no diagrams vs doubt branch etc.).
    """
    if tc.board_verifier is None:
        return False
    if tc.state_machine.depth > 1:
        tc.audit.record("drift_check", "skipped_doubt_branch", "")
        return False
    if tc.current_concept is None:
        tc.audit.record("drift_check", "skipped_no_concept", "")
        return False
    design_ids = list(tc.board_manager.active_board.state._design_specs.keys())
    if not design_ids:
        tc.audit.record("drift_check", "skipped_no_diagrams", "")
        return False
    used = tc.drift_feedback_budget_used.get(tc.current_concept_index, 0)
    if used >= DRIFT_FEEDBACK_BUDGET_PER_CONCEPT:
        tc.audit.record("drift_check", "skipped_budget", "")
        return False
    state_hash = compute_drift_state_hash(tc.current_concept_index, design_ids, tc.diagram_version)
    if state_hash == tc.last_drift_check_hash:
        tc.audit.record("drift_check", "skipped_unchanged", state_hash)
        return False
    return True


async def _run_drift_check(tc: TeachingContext) -> None:
    """Run one drift check against the current active-board state.

    Snapshots concept context + element summary before the screenshot await
    so a mid-flight concept advance can't corrupt the prompt. The on_feedback
    closure re-checks ``current_concept_index`` at fire time as a stale guard.
    """
    concept = tc.current_concept
    if concept is None:
        return  # belt-and-suspenders; _should_run_drift_check already gated this
    concept_index = tc.current_concept_index
    concept_title = concept.title
    concept_description = getattr(concept, "description", "") or ""
    total_concepts = tc.lesson_plan.total_concepts if tc.lesson_plan else 1
    design_ids = list(tc.board_manager.active_board.state._design_specs.keys())
    state_hash = compute_drift_state_hash(concept_index, design_ids, tc.diagram_version)
    element_summary = build_element_summary(
        design_ids, tc.original_diagram_claims, tc.diagram_version
    )

    def _on_feedback(fb: PerceptionFeedback, _result: Any) -> None:
        # Stale-guard: the concept may have advanced while vision was running.
        if tc.current_concept_index != concept_index:
            tc.audit.record("drift_check", "feedback_stale", "")
            return
        used = tc.drift_feedback_budget_used.get(concept_index, 0)
        if used >= DRIFT_FEEDBACK_BUDGET_PER_CONCEPT:
            tc.audit.record("drift_check", "feedback_budget_full", "")
            return
        tc.perception_feedback_queue.append(fb)
        tc.drift_feedback_budget_used[concept_index] = used + 1

    result = await tc.board_verifier.request_drift_check(
        concept_index=concept_index,
        concept_title=concept_title,
        concept_description=concept_description,
        total_concepts=total_concepts,
        element_summary=element_summary,
        state_hash=state_hash,
        on_feedback=_on_feedback,
    )
    # Only commit the dedup hash on a successful result. On timeout/exception
    # result is None and the next tick retries against the same board state.
    if result is not None:
        tc.last_drift_check_hash = state_hash


class FeynmanAgent(Agent):
    def __init__(
        self,
        teaching_ctx: TeachingContext,
        topic: str = "",
        subject: Subject | None = None,
        grade_level: str = "",
    ) -> None:
        self._teaching_ctx = teaching_ctx
        self._topic = topic
        self._subject = subject
        self._grade_level = grade_level

        super().__init__(
            instructions=TEACHING_SYSTEM_PROMPT,
            tools=ALL_TOOLS,
        )

    async def tts_node(
        self,
        text: AsyncIterable[str],
        model_settings: ModelSettings,
    ) -> AsyncGenerator[rtc.AudioFrame]:
        """Intercept the text stream pre-TTS to strip inline action tags.

        Phase 4 of the diagram-awareness re-architecture: the LLM emits
        self-closing tags inside narration (``<highlight target="x"/>``)
        as a lightweight alternative to pointing-tool calls. This override
        feeds each chunk through :class:`ActionTagParser`, dispatches the
        parsed tags as visual instructions (fire-and-forget), and yields
        only the cleaned text to TTS.

        Because ``AgentSession`` is created with
        ``use_tts_aligned_transcript=True``, the user-facing transcription
        automatically mirrors the cleaned TTS text — no separate
        ``transcription_node`` override is required.
        """
        session = self.session

        def schedule(tag: ActionTag) -> None:
            asyncio.create_task(  # noqa: RUF006
                dispatch_action_tag(session, tag),
                name="action_tag_dispatch",
            )

        cleaned = strip_action_tags(text, schedule)
        async for frame in Agent.default.tts_node(self, cleaned, model_settings):
            yield frame

    async def llm_node(
        self,
        chat_ctx: ChatContext,
        tools: list[FunctionTool],
        model_settings: ModelSettings,
    ) -> AsyncGenerator[ChatChunk | str]:
        """Drain perception-feedback queue into chat_ctx before the LLM call.

        Phase 5a-1: background vision verification (per-annotation) enqueues
        :class:`PerceptionFeedback` on the teaching context when an annotation
        misses. Just before the next LLM turn fires, we append each feedback
        as a synthetic ``role="user"`` note prefixed with
        ``[PERCEPTION_FEEDBACK]`` — the agent's prompt teaches it to interpret
        the prefix as a system signal, acknowledge briefly, and re-point with
        the suggested target via an inline action tag.

        Mutating ``chat_ctx`` here persists because livekit-agents' LLM
        pipeline uses the same underlying ``session.history`` object the
        next turn will read from.
        """
        drain_perception_feedback(self._teaching_ctx, chat_ctx)
        async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
            yield chunk

    async def _periodic_drift_check(self) -> None:
        """Phase 5a-3: every 30s, ask vision if the board still fits the lesson.

        Long-running background task — survives until the session shuts down
        (cancelled in the ``finally`` block around ``session.start``). One bad
        check never kills the loop; only ``CancelledError`` propagates out.
        """
        tc = self._teaching_ctx
        while True:
            try:
                await asyncio.sleep(DRIFT_CHECK_INTERVAL_SECS)
                if not _should_run_drift_check(tc):
                    continue
                await _run_drift_check(tc)
            except asyncio.CancelledError:
                logger.info("drift_check.cancelled")
                raise
            except Exception:
                logger.warning("drift_check.failed", exc_info=True)
                # Don't break — one bad check shouldn't kill the loop.

    async def on_enter(self) -> None:
        logger.info(
            "agent.entered_room",
            topic=self._topic,
            use_neo4j_curriculum=settings.use_neo4j_curriculum,
        )

        # Curriculum is loaded only when the Neo4j-backed lesson graph is
        # enabled. With `USE_NEO4J_CURRICULUM=false` we skip the load entirely
        # and run in free-form mode (no plan, no pre-gens, no checklist).
        if self._topic and settings.use_neo4j_curriculum:
            # Load curriculum from Neo4j. Raises CurriculumNotFoundError if not found.
            curriculum = await load_curriculum(
                self._topic, self._subject.value if self._subject else None
            )
            self._teaching_ctx.curriculum = curriculum

            plan = lesson_plan_from_curriculum(
                curriculum,
                grade_level=self._grade_level,
                subject=self._subject,
            )

            self._teaching_ctx.lesson_plan = plan
            self._teaching_ctx.audit.record(
                "curriculum",
                "loaded_from_neo4j",
                f"topic='{self._topic}', chapter='{curriculum.chapter_title}', "
                f"concepts={len(curriculum.concepts)}, visuals={len(curriculum.pre_generated_visuals)}",
                source="Neo4j",
            )

            # Label the initial board with the first concept title.
            first_concept = plan.concept_at(0)
            if first_concept:
                self._teaching_ctx.board_manager.active_board.label = first_concept.title

            logger.info(
                "agent.lesson_plan_ready",
                topic=self._topic,
                chapter=curriculum.chapter_title,
                num_concepts=plan.total_concepts,
                pre_generated_visuals=len(curriculum.pre_generated_visuals),
                source="neo4j",
            )

            # Fire anticipation pre-generation for first 3 concepts.
            # With pre-generated visuals from Neo4j, many will be instant cache hits.
            self._warm_task = asyncio.create_task(
                self._teaching_ctx.anticipation.warm(
                    plan,
                    start=0,
                    count=3,
                    curriculum=curriculum,
                )
            )

            # Plan concept 0 (current) + fire async planning for concept 1.
            # Concept 1 receives concept 0's plan for continuity.
            async def _plan_concepts() -> None:
                plan0 = await plan_concept(
                    0,
                    curriculum,
                    plan,
                    audit=self._teaching_ctx.audit,
                    api_key=settings.anthropic_api_key,
                )
                if plan0:
                    self._teaching_ctx.concept_plans[0] = plan0
                    logger.info("agent.concept_0_planned", beats=len(plan0.beats))

                # Fire concept 1 planning — pass plan0 so it knows how concept 0 ends.
                if plan.total_concepts > 1:

                    async def _plan_next() -> None:
                        plan1 = await plan_concept(
                            1,
                            curriculum,
                            plan,
                            audit=self._teaching_ctx.audit,
                            prev_plan=self._teaching_ctx.concept_plans.get(0),
                            api_key=settings.anthropic_api_key,
                        )
                        if plan1:
                            self._teaching_ctx.concept_plans[1] = plan1
                            logger.info("agent.concept_1_planned", beats=len(plan1.beats))

                    asyncio.create_task(_plan_next())  # noqa: RUF006

            self._plan_task = asyncio.create_task(_plan_concepts())

            # Rebuild prompt once warm + planning complete
            async def _update_after_warm() -> None:
                try:
                    await self._warm_task
                except Exception:
                    logger.warning("agent.warm_task_failed", exc_info=True)
                try:
                    await self._plan_task
                except Exception:
                    logger.warning("agent.plan_task_failed", exc_info=True)
                prompt = build_teaching_prompt(
                    self._teaching_ctx.lesson_plan,
                    self._teaching_ctx,
                )
                await self.update_instructions(prompt)
                logger.info(
                    "agent.prompt_updated_post_warm",
                    cache_size=self._teaching_ctx.anticipation.cache_size,
                    plans_ready=len(self._teaching_ctx.concept_plans),
                )

            self._prompt_rebuild_task = asyncio.create_task(_update_after_warm())

            # --- COMMENTED OUT: Old fallback paths. ---
            # Previously: if graph not found → generate_lesson_plan() via LLM
            # Previously: if exception → continue without plan (free-form teaching)
            # Now: CurriculumNotFoundError propagates — session fails with clear error.
            # --- END COMMENTED OUT ---

        # Phase 5a-3: periodic drift check runs in BOTH curriculum and
        # free-form modes — _should_run_drift_check skips when there's no
        # active concept, so the loop is a no-op until teaching begins.
        self._drift_check_task = asyncio.create_task(
            self._periodic_drift_check(),
            name="periodic_drift_check",
        )

        # Update instructions with lesson context
        prompt = build_teaching_prompt(
            self._teaching_ctx.lesson_plan,
            self._teaching_ctx,
        )
        await self.update_instructions(prompt)

        # Generate greeting
        plan = self._teaching_ctx.lesson_plan
        if plan:
            greeting_instructions = (
                f"Greet the class warmly. Introduce yourself as Feynman, their AI teacher. "
                f"Tell them today's topic is '{plan.topic}' and briefly share the objective: "
                f"'{plan.objective}'. Keep it enthusiastic — two or three sentences max. "
                f"Use the show_text tool to display a welcome message with today's topic."
            )
        elif self._topic:
            # Free-form mode but the user passed a topic — let the agent know it
            # and teach without a Neo4j-backed plan.
            greeting_instructions = (
                f"Greet the class warmly. Introduce yourself as Feynman, their AI teacher. "
                f"Tell them today's topic is '{self._topic}' and that you'll guide them "
                f"through it interactively. Keep it enthusiastic — two or three sentences max."
            )
        else:
            greeting_instructions = (
                "Greet the class warmly. Introduce yourself as Feynman, their AI teacher. "
                "Keep it brief and enthusiastic — two or three sentences max. "
                "Use the show_text tool to display a welcome message on the board."
            )

        self.session.generate_reply(instructions=greeting_instructions)


def _parse_room_metadata(ctx: JobContext) -> dict:
    """Extract topic/subject/grade_level from room metadata set by the API."""
    raw = ctx.room.metadata
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("worker.invalid_room_metadata", raw=raw)
        return {}


server = AgentServer(
    ws_url=settings.livekit_url,
    api_key=settings.livekit_api_key,
    api_secret=settings.livekit_api_secret,
)


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    logger.info("worker.session_start", room_name=ctx.room.name)
    await ctx.connect()

    # Parse room metadata for lesson configuration
    meta = _parse_room_metadata(ctx)

    # Lecture playback mode: precomputed lecture is driven by the frontend
    # client-side; the agent stays connected to the room but silent. Phase 3+
    # will reactivate STT/LLM/TTS on a "doubt_intent" data-channel message
    # from the Ask Feynman button.
    lecture_chapter_id = meta.get("lecture_chapter_id")
    if lecture_chapter_id:
        logger.info(
            "worker.lecture_playback_mode",
            room_name=ctx.room.name,
            chapter_id=lecture_chapter_id,
        )
        # Idle in the room until disconnect. asyncio.Event().wait() never
        # resolves — the room shutting down terminates the task.
        await asyncio.Event().wait()
        return

    topic = meta.get("topic", "")
    subject_str = meta.get("subject")
    subject = Subject(subject_str) if subject_str else None
    grade_level = meta.get("grade_level", "")

    # Create teaching state machine and context
    session_id = uuid4()
    state_machine = TeachingStateMachine(session_id=session_id)
    teaching_ctx = TeachingContext(
        session_id=session_id,
        state_machine=state_machine,
    )

    # Initialize board verifier for async visual quality checks.
    async def _publish_capture(data: str, topic: str) -> None:
        await ctx.room.local_participant.publish_data(
            data.encode(),
            reliable=True,
            topic=topic,
        )

    teaching_ctx.board_verifier = BoardVerifier(
        publish_fn=_publish_capture,
        audit=teaching_ctx.audit,
    )

    # Listen for bounds reports from the frontend
    @ctx.room.on("data_received")
    def _on_data_received(packet: DataPacket) -> None:
        if packet.topic == "bounds":
            try:
                payload = json.loads(packet.data)
                report = BoundsReportPayload.model_validate(payload)
                teaching_ctx.board_manager.update_bounds(report.board_id, report)
                logger.debug(
                    "bounds.received",
                    board_id=report.board_id,
                    element_count=len(report.elements),
                )
            except Exception:
                logger.warning("bounds.parse_failed", exc_info=True)
        elif packet.topic == "board_capture":
            try:
                payload = json.loads(packet.data)
                if payload.get("type") == "capture_response" and teaching_ctx.board_verifier:
                    teaching_ctx.board_verifier.resolve_capture(
                        payload["request_id"],
                        payload["image_data"],
                    )
            except (json.JSONDecodeError, KeyError):
                logger.warning("board_capture.invalid_response")

    # Create agent with teaching context
    agent = FeynmanAgent(
        teaching_ctx=teaching_ctx,
        topic=topic,
        subject=subject,
        grade_level=grade_level,
    )

    # Start the session with teaching context as userdata
    session = AgentSession(
        stt=create_stt(),
        llm=create_llm(),
        tts=create_tts(),
        vad=create_vad(),
        userdata=teaching_ctx,
        use_tts_aligned_transcript=True,
        # Bumped from 10 → 30 so a dense teaching beat (write_section + several
        # write_equation + draw_design_diagram + write_answer) can complete in
        # one turn. 30 still catches runaway loops.
        max_tool_steps=30,
    )

    # Voice-keyword auto-tick: every committed assistant message inside a
    # doubt branch is forwarded to the orchestrator, which substring-matches
    # the transcript against each pending checklist item's `keywords`.
    @session.on("conversation_item_added")
    def _on_conversation_item(event) -> None:
        item = getattr(event, "item", None)
        if item is None:
            return
        role = getattr(item, "role", None)
        if role != "assistant":
            return
        text = getattr(item, "text_content", None)
        if callable(text):
            text = text()
        if not isinstance(text, str) or not text:
            return
        branch = teaching_ctx.state_machine.current
        if branch is None or branch.state != TeachingState.HANDLING_DOUBT:
            return
        teaching_ctx.doubt_orchestrator.on_voice_emitted(text, branch.id)

    try:
        await session.start(agent=agent, room=ctx.room)
        logger.info(
            "worker.session_started",
            room_name=ctx.room.name,
            topic=topic,
            subject=subject,
        )
    finally:
        # Phase 5a-3: the drift-check loop is the only background task that
        # runs forever — cancel it explicitly so a session shutdown doesn't
        # leak the asyncio task. The warm/plan/rebuild tasks are one-shot
        # and exit naturally.
        drift_task = getattr(agent, "_drift_check_task", None)
        if drift_task is not None and not drift_task.done():
            drift_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await drift_task


if __name__ == "__main__":
    cli.run_app(server)
