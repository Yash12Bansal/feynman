"""LiveKit agent worker entrypoint. Run as separate process.

cd backend && uv run python -m feynman.livekit.worker dev
"""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import structlog
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli
from livekit.rtc import DataPacket

from feynman.agent.anticipation import load_concept_graph
from feynman.agent.lesson_plan import generate_lesson_plan, lesson_plan_from_graph
from feynman.agent.prompts import TEACHING_SYSTEM_PROMPT, build_teaching_prompt
from feynman.agent.scene_graph import BoundsReportPayload
from feynman.agent.state_machine import TeachingStateMachine
from feynman.agent.teaching_context import TeachingContext
from feynman.agent.tools import (
    advance_concept,
    annotate,
    clear_board,
    clear_cluster,
    draw_design_diagram,
    draw_diagram,
    draw_scene,
    highlight_diagram_part,
    highlight_walk,
    modify_design_diagram,
    resolve_doubt,
    scroll_board,
    set_lesson_topic,
    show_equation,
    show_graph,
    show_text,
    start_doubt_branch,
    step_equation,
    switch_board,
    teach_pause,
)
from feynman.common.logging import setup_logging
from feynman.common.types import Subject
from feynman.config import settings
from feynman.livekit.pipeline import create_llm, create_stt, create_tts, create_vad

setup_logging(settings.log_level)
logger = structlog.get_logger()

# All tools the agent can use — visual + state management
ALL_TOOLS = [
    show_text,
    show_equation,
    draw_design_diagram,
    modify_design_diagram,
    draw_diagram,
    draw_scene,
    step_equation,
    show_graph,
    annotate,
    highlight_diagram_part,
    highlight_walk,
    clear_board,
    clear_cluster,
    teach_pause,
    advance_concept,
    start_doubt_branch,
    resolve_doubt,
    switch_board,
    scroll_board,
    set_lesson_topic,
]


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

    async def on_enter(self) -> None:
        logger.info("agent.entered_room", topic=self._topic)

        # Generate lesson plan if a topic was provided
        if self._topic:
            try:
                # Try to load pre-computed ConceptGraph for richer curriculum data.
                graph = await load_concept_graph(self._topic)

                if graph:
                    # Derive lesson plan from graph (richer than runtime generation).
                    plan = lesson_plan_from_graph(
                        graph,
                        grade_level=self._grade_level,
                        subject=self._subject,
                    )
                    self._teaching_ctx.concept_graph = graph
                    logger.info(
                        "agent.using_concept_graph",
                        topic=self._topic,
                        graph_nodes=len(graph.nodes),
                    )
                    self._teaching_ctx.audit.record(
                        "curriculum",
                        "graph_loaded",
                        f"topic='{self._topic}', nodes={len(graph.nodes)}",
                        source="ConceptGraph",
                    )
                else:
                    # Fallback: runtime generation (current behavior).
                    plan = await generate_lesson_plan(
                        topic=self._topic,
                        subject=self._subject,
                        grade_level=self._grade_level,
                    )
                    self._teaching_ctx.audit.record(
                        "curriculum",
                        "graph_missing_fallback_runtime",
                        f"topic='{self._topic}' — no pre-computed graph found, "
                        f"fell back to runtime LLM generation",
                        source="LessonPlan",
                    )

                self._teaching_ctx.lesson_plan = plan
                # Label the initial board with the first concept title.
                first_concept = plan.concept_at(0)
                if first_concept:
                    self._teaching_ctx.board_manager.active_board.label = (
                        first_concept.title
                    )
                logger.info(
                    "agent.lesson_plan_ready",
                    topic=self._topic,
                    num_concepts=plan.total_concepts,
                    source="graph" if graph else "runtime",
                )

                # Fire anticipation pre-generation for first 3 concepts.
                self._warm_task = asyncio.create_task(
                    self._teaching_ctx.anticipation.warm(
                        plan,
                        start=0,
                        count=3,
                        graph=self._teaching_ctx.concept_graph,
                    )
                )

                # Rebuild prompt once warm completes — initial prompt goes out
                # immediately (fast session start), then gets updated with
                # pre-rendered visual prompts for the agent to use.
                async def _update_after_warm() -> None:
                    try:
                        await self._warm_task
                    except Exception:
                        logger.warning("agent.warm_task_failed", exc_info=True)
                        return
                    prompt = build_teaching_prompt(
                        self._teaching_ctx.lesson_plan,
                        self._teaching_ctx,
                    )
                    await self.update_instructions(prompt)
                    logger.info(
                        "agent.prompt_updated_post_warm",
                        cache_size=self._teaching_ctx.anticipation.cache_size,
                    )

                self._prompt_rebuild_task = asyncio.create_task(
                    _update_after_warm()
                )

            except Exception:
                logger.exception("agent.lesson_plan_failed", topic=self._topic)
                self._teaching_ctx.audit.record(
                    "curriculum",
                    "plan_failed",
                    f"topic='{self._topic}' — exception during plan generation, "
                    f"falling back to free-form teaching",
                )
                # Continue without a plan — free-form teaching mode

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

    # Listen for bounds reports from the frontend
    @ctx.room.on("data_received")
    def _on_data_received(packet: DataPacket) -> None:
        if packet.topic != "bounds":
            return
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
        max_tool_steps=10,
    )

    await session.start(agent=agent, room=ctx.room)
    logger.info(
        "worker.session_started",
        room_name=ctx.room.name,
        topic=topic,
        subject=subject,
    )


if __name__ == "__main__":
    cli.run_app(server)
