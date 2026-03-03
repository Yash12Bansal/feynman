"""LiveKit agent worker entrypoint. Run as separate process.

cd backend && uv run python -m feynman.livekit.worker dev
"""

from __future__ import annotations

import json
from uuid import uuid4

import structlog
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli
from livekit.rtc import DataPacket

from feynman.agent.lesson_plan import generate_lesson_plan
from feynman.agent.prompts import TEACHING_SYSTEM_PROMPT, build_teaching_prompt
from feynman.agent.scene_graph import BoundsReportPayload
from feynman.agent.state_machine import TeachingStateMachine
from feynman.agent.teaching_context import TeachingContext
from feynman.agent.tools import (
    advance_concept,
    annotate,
    clear_board,
    draw_diagram,
    draw_scene,
    resolve_doubt,
    show_equation,
    show_graph,
    show_text,
    start_doubt_branch,
    step_equation,
    switch_board,
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
    draw_diagram,
    draw_scene,
    step_equation,
    show_graph,
    annotate,
    clear_board,
    advance_concept,
    start_doubt_branch,
    resolve_doubt,
    switch_board,
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
                plan = await generate_lesson_plan(
                    topic=self._topic,
                    subject=self._subject,
                    grade_level=self._grade_level,
                )
                self._teaching_ctx.lesson_plan = plan
                # Label the initial board with the first concept title.
                first_concept = plan.concept_at(0)
                if first_concept:
                    self._teaching_ctx.board_manager.active_board.label = first_concept.title
                logger.info(
                    "agent.lesson_plan_ready",
                    topic=self._topic,
                    num_concepts=plan.total_concepts,
                )
            except Exception:
                logger.exception("agent.lesson_plan_failed", topic=self._topic)
                # Continue without a plan — free-form teaching mode

        # Update instructions with lesson context
        prompt = build_teaching_prompt(
            self._teaching_ctx.lesson_plan,
            self._teaching_ctx,
        )
        self.update_instructions(prompt)

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
