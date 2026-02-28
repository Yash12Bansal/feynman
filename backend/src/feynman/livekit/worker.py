"""LiveKit agent worker entrypoint. Run as separate process.

cd backend && uv run python -m feynman.livekit.worker dev
"""

import structlog
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli

from feynman.agent.prompts import TEACHING_SYSTEM_PROMPT
from feynman.agent.tools import clear_board, draw_diagram, show_equation, show_text
from feynman.common.logging import setup_logging
from feynman.config import settings
from feynman.livekit.pipeline import create_llm, create_stt, create_tts, create_vad

setup_logging(settings.log_level)
logger = structlog.get_logger()


class FeynmanAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=TEACHING_SYSTEM_PROMPT,
            tools=[show_text, show_equation, draw_diagram, clear_board],
        )

    async def on_enter(self) -> None:
        logger.info("agent.entered_room")
        self.session.generate_reply(
            instructions=(
                "Greet the class warmly. Introduce yourself as Feynman, their AI teacher. "
                "Keep it brief and enthusiastic — two or three sentences max. "
                "Use the show_text tool to display a welcome message on the board."
            ),
        )


server = AgentServer(
    ws_url=settings.livekit_url,
    api_key=settings.livekit_api_key,
    api_secret=settings.livekit_api_secret,
)


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    logger.info("worker.session_start", room_name=ctx.room.name)
    await ctx.connect()

    agent = FeynmanAgent()
    session = AgentSession(
        stt=create_stt(),
        llm=create_llm(),
        tts=create_tts(),
        vad=create_vad(),
    )

    await session.start(agent=agent, room=ctx.room)
    logger.info("worker.session_started", room_name=ctx.room.name)


if __name__ == "__main__":
    cli.run_app(server)
