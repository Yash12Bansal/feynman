"""LiveKit agent worker entrypoint. Run as separate process.

cd backend && uv run python -m feynman.livekit.worker dev
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any

import structlog
from livekit.agents import AgentServer, JobContext, cli
from livekit.rtc import DataPacket

from feynman.agent.doubt_resolution import (
    DoubtType,
    LectureDoubtSession,
    ResolutionPlan,
    load_chapter_by_id,
)
from feynman.agent.doubt_resolution.doubt_capture import capture_student_doubt
from feynman.agent.doubt_resolution.narration_markers import strip_markers
from feynman.common.logging import setup_logging
from feynman.config import settings
from feynman.knowledge import StudentGraphStore
from feynman.livekit.doubt_delivery import DoubtDelivery
from feynman.livekit.pipeline import create_stt, create_tts

setup_logging(settings.log_level)
logger = structlog.get_logger()


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


_DOUBT_TOPIC = "doubt_signal"

# Spoken the instant a doubt is captured, WHILE the multi-second classify+plan
# LLM chain runs in the background — so the student hears Feynman within ~0.5s
# instead of sitting through dead air. Short + varied, picked at RANDOM (never
# the same line twice in a row) so it feels human, not canned.
# GENERIC ONLY: never promise a drawing / board ("let me draw this", "on the
# board", "let me show you") — many doubts are text-only, and a filler that
# promises a diagram we won't draw sets a false expectation.
_ACKNOWLEDGEMENTS = (
    "Good question — give me a second.",
    "Ah, let me think about that one.",
    "Hmm, good one — one moment.",
    "Okay, let me unpack that.",
    "Let me work through that with you.",
    "Let me put this together for you.",
    "Interesting — let me think it through.",
    "Let me help you understand this.",
    "Excellent doubt — let me work it out.",
    "Let me check that for you.",
    "Let me break this down for you.",
    "Let me make this clear for you.",
    "One moment — let me reason this out.",
    "Right, let me work through it.",
)


def _pick_acknowledgement(exclude: str | None = None) -> str:
    """A random acknowledgement, never repeating the immediately previous one."""
    choices = [a for a in _ACKNOWLEDGEMENTS if a != exclude] or list(_ACKNOWLEDGEMENTS)
    return random.choice(choices)


async def _run_lecture_mode(
    ctx: JobContext,
    *,
    chapter_id: str,
    student_id: str | None = None,
    study_session_id: str | None = None,
) -> None:
    """Lecture-mode worker loop.

    The precomputed lecture plays from the frontend; the worker stays in the
    room as a silent participant. When the Ask Feynman button fires a
    `doubt_intent` over the data channel, we capture the student's audio,
    run the (Phase 3 stub) classifier, and emit a `doubt_captured`
    acknowledgement so the frontend can flip to its "thinking" indicator.

    Phase 4 routes captured doubts through the full classifier → planner
    → diagram-matcher chain. Phase 5 will pick up the produced
    `ResolutionPlan` and deliver it as live voice + visuals.
    """
    # Lazy-construct the STT instance; if no doubt is ever raised we don't
    # pay for the Deepgram client setup.
    stt_instance = None
    # Hold strong refs to in-flight doubt tasks so the GC doesn't drop them.
    pending_tasks: set[asyncio.Task[None]] = set()

    # Hydrate the chapter context once for the lifetime of the session. If
    # this fails, the room stays alive so the precompute playback continues,
    # but doubts can't be resolved (and we publish a clear failure on each).
    doubt_session: LectureDoubtSession | None = None
    try:
        chapter_context = await load_chapter_by_id(chapter_id)
        if chapter_context is not None:
            doubt_session = LectureDoubtSession(chapter_context=chapter_context)
            logger.info(
                "worker.lecture_session_ready",
                chapter_id=chapter_id,
                topics=len(chapter_context.topics),
                diagrams=len(chapter_context.diagrams),
            )
        else:
            logger.error(
                "worker.chapter_context_missing",
                chapter_id=chapter_id,
            )
    except Exception as exc:
        logger.exception("worker.chapter_load_failed", chapter_id=chapter_id, error=str(exc))

    # Phase 5: outbound TTS audio track for live doubt-resolution delivery.
    # Constructed once; the AudioSource stays published for the session
    # lifetime so consecutive doubts don't pay re-publish latency.
    doubt_delivery = DoubtDelivery(tts=create_tts())
    if doubt_session is not None:
        try:
            await doubt_delivery.start(ctx.room)
        except Exception:
            logger.exception("worker.doubt_delivery_start_failed")

    # Tracks the most recent doubt so `start_over` can re-resolve with
    # `different_angle=True` carrying the prior framing as context.
    last_doubt_state: dict[str, str] = {"text": "", "summary": "", "topic_id": ""}
    # Last spoken acknowledgement (mutable container so the nested
    # _resolve_and_deliver can update it without `nonlocal`) — used to avoid
    # picking the same random line twice in a row.
    last_ack: dict[str, str] = {"text": ""}

    # Memory layer: the StudySession was already created on lecture-open (the
    # frontend POSTs /students/{id}/sessions and threads `study_session_id`
    # here via room metadata). The worker only RECORDS doubts to it — it never
    # creates the session, so attempts that happen without any doubt still
    # share one session per sitting. Writes are fire-and-forget + guarded so a
    # Neo4j hiccup never touches the live doubt experience.
    memory_store: StudentGraphStore | None = None
    if student_id and study_session_id:
        try:
            memory_store = StudentGraphStore.connect()
        except Exception:
            logger.exception("worker.memory_store_connect_failed")
            memory_store = None

    def _remember_doubt(*, doubt_text: str, response: str, topic_id: str | None) -> None:
        """Fire-and-forget write of a resolved doubt to the student graph."""
        if memory_store is None or study_session_id is None:
            return

        async def _write() -> None:
            try:
                await memory_store.record_doubt(
                    session_id=study_session_id,
                    topic_id=topic_id or "",
                    doubt_text=doubt_text,
                    response=response,
                    created_at=int(time.time() * 1000),
                )
            except Exception:
                logger.warning("worker.remember_doubt_failed", exc_info=True)

        task = asyncio.create_task(_write())
        pending_tasks.add(task)
        task.add_done_callback(pending_tasks.discard)

    async def _resolve_and_deliver(
        *,
        doubt_text: str,
        topic_id: str | None,
        cursor: int | None,
        different_angle: bool,
        prior_resolution_summary: str,
        board_snapshot: dict | None = None,
    ) -> ResolutionPlan | None:
        """Run the pipeline + deliver the result. Returns the plan or None."""
        if doubt_session is None:
            await _publish_doubt(
                ctx,
                {"type": "doubt_resolution_failed", "reason": "chapter_context_unavailable"},
            )
            return None
        t0 = time.monotonic()  # Phase 6: latency clock starts when we begin work.

        # Idempotent: fires on the FIRST audio frame (the acknowledgement's, or
        # beat 0's if the filler was skipped) — the true time-to-first-voice.
        first_voice_logged = False

        def _on_first_frame() -> None:
            nonlocal first_voice_logged
            if first_voice_logged:
                return
            first_voice_logged = True
            ms = int((time.monotonic() - t0) * 1000)
            logger.info("phase6.time_to_first_voice_ms", ms=ms)

        # Run the (multi-second) classify+plan chain in the BACKGROUND and
        # immediately acknowledge out loud, so the student hears Feynman within
        # ~0.5s instead of waiting out the whole LLM chain in silence. The filler
        # streams through the same TTS lock as the beats, so it plays seamlessly
        # right before beat 0. `_on_first_frame` (time-to-first-voice telemetry)
        # fires on the filler's first frame — the true moment Feynman starts.
        resolve_task = asyncio.create_task(
            doubt_session.resolve(
                doubt_text=doubt_text,
                current_topic_id=topic_id,
                cursor=cursor,
                different_angle=different_angle,
                prior_resolution_summary=prior_resolution_summary,
                board_snapshot=board_snapshot,
            )
        )
        if doubt_delivery.is_started:
            ack = _pick_acknowledgement(exclude=last_ack["text"])
            last_ack["text"] = ack
            try:
                await doubt_delivery.speak(ack, on_first_frame=_on_first_frame)
            except Exception:
                logger.warning("worker.acknowledgement_failed", exc_info=True)

        try:
            plan = await resolve_task
        except Exception:
            logger.exception("worker.resolve_failed")
            plan = None
        if plan is None:
            await _publish_doubt(
                ctx, {"type": "doubt_resolution_failed", "reason": "planner_failed"}
            )
            return None

        # Remember this doubt so `start_over` can re-resolve it.
        last_doubt_state["text"] = doubt_text
        last_doubt_state["summary"] = " | ".join(beat.narration_text[:80] for beat in plan.beats)
        last_doubt_state["topic_id"] = topic_id or ""

        # Memory layer: persist the doubt + the answer the student got, so it
        # surfaces on their next-session memory card for this chapter.
        # Strip the inline <<FOCUS>>/<<TRACE>>/<<UNFOCUS>> board markers — the
        # memory card shows the spoken answer as plain prose, not delivery markup.
        _remember_doubt(
            doubt_text=doubt_text,
            response=strip_markers(" ".join(beat.narration_text for beat in plan.beats)),
            topic_id=topic_id,
        )

        # Carry-over (Delta 2): a local clarification about a diagram already on
        # the board → the frontend seeds the doubt board with a copy of the
        # current page (diagram + notebook) so the planner builds directly on it.
        carry_over = False
        if doubt_session.prior_doubts_in_session:
            cls = doubt_session.prior_doubts_in_session[-1].classification
            snap_elements = (board_snapshot or {}).get("elements") or []
            has_board_diagram = any(
                isinstance(el, dict) and el.get("kind") == "diagram" for el in snap_elements
            )
            carry_over = cls.type == DoubtType.LOCAL_CLARIFICATION and has_board_diagram

        await _publish_doubt(
            ctx,
            {
                "type": "resolution_ready",
                "beats": len(plan.beats),
                "carry_over": carry_over,
                "matched_diagram_ids": [
                    b.target_diagram_id for b in plan.beats if b.target_diagram_id
                ],
            },
        )

        async def _publish(payload: dict[str, Any]) -> None:
            await _publish_doubt(ctx, payload)

        if doubt_delivery.is_started:
            try:
                await doubt_delivery.deliver_resolution(
                    plan=plan,
                    chapter_context=doubt_session.chapter_context,
                    publish_data=_publish,
                    on_first_frame=_on_first_frame,
                    spec_cache=doubt_session.generated_specs,
                )
            except Exception:
                logger.exception("worker.doubt_delivery_failed")

        await _publish_doubt(
            ctx,
            {
                "type": "satisfaction_prompt",
                "options": _SATISFACTION_OPTIONS,
            },
        )
        return plan

    async def _capture_then_resolve(intent: dict[str, Any]) -> None:
        """STT → publish doubt_captured → resolve & deliver."""
        nonlocal stt_instance
        if stt_instance is None:
            stt_instance = create_stt()

        def _on_speech_started() -> None:
            # Student has begun talking. Tell the frontend we're actively
            # listening so its short "I didn't hear anything" timeout doesn't
            # fire mid-doubt — capture runs until a short continuous-silence gap.
            t = asyncio.create_task(_publish_doubt(ctx, {"type": "doubt_listening"}))
            pending_tasks.add(t)
            t.add_done_callback(pending_tasks.discard)

        captured = await capture_student_doubt(
            ctx, stt=stt_instance, on_speech_started=_on_speech_started
        )
        if captured is None:
            await _publish_doubt(ctx, {"type": "doubt_capture_failed", "reason": "no_transcript"})
            return
        await _publish_doubt(
            ctx,
            {
                "type": "doubt_captured",
                "text": captured.text,
                "duration_ms": captured.duration_ms,
            },
        )
        snap = intent.get("board_snapshot")
        await _resolve_and_deliver(
            doubt_text=captured.text,
            topic_id=intent.get("topic_id"),
            cursor=intent.get("cursor"),
            different_angle=False,
            prior_resolution_summary="",
            board_snapshot=snap if isinstance(snap, dict) else None,
        )

    async def _handle_doubt_intent(intent: dict[str, Any]) -> None:
        snap = intent.get("board_snapshot")
        snap_dict = snap if isinstance(snap, dict) else None
        logger.info(
            "doubt.intent_received",
            chapter_id=chapter_id,
            cursor=intent.get("cursor"),
            topic_id=intent.get("topic_id"),
            snapshot_page=(snap_dict or {}).get("page_index"),
            snapshot_elements=len((snap_dict or {}).get("elements") or []),
        )
        await _capture_then_resolve(intent)

    async def _handle_satisfaction_choice(payload: dict[str, Any]) -> None:
        choice = payload.get("option", "")
        logger.info("doubt.satisfaction_choice", option=choice)

        if choice == "crystal_clear":
            t0 = time.monotonic()  # Phase 6: time-to-resume from choice receipt.
            if doubt_delivery.is_started:
                await doubt_delivery.speak("Picking up where we left off.")
            await _publish_doubt(ctx, {"type": "lecture_resume"})
            logger.info(
                "phase6.time_to_resume_ms",
                ms=int((time.monotonic() - t0) * 1000),
            )
            return

        if choice == "counter_doubt":
            await _publish_doubt(ctx, {"type": "doubt_capture_ready"})
            await _capture_then_resolve({"topic_id": last_doubt_state["topic_id"] or None})
            return

        if choice == "somewhat_cleared":
            if doubt_delivery.is_started:
                await doubt_delivery.speak("Tell me what specifically is still unclear.")
            await _publish_doubt(ctx, {"type": "doubt_capture_ready"})
            await _capture_then_resolve({"topic_id": last_doubt_state["topic_id"] or None})
            return

        if choice == "start_over":
            if not last_doubt_state["text"]:
                logger.warning("doubt.start_over_without_history")
                await _publish_doubt(ctx, {"type": "lecture_resume"})
                return
            # Drop the just-rejected attempt from history so the matcher
            # doesn't double-penalise its diagrams as "already shown".
            if doubt_session is not None and doubt_session.prior_doubts_in_session:
                doubt_session.prior_doubts_in_session.pop()
            await _resolve_and_deliver(
                doubt_text=last_doubt_state["text"],
                topic_id=last_doubt_state["topic_id"] or None,
                cursor=None,
                different_angle=True,
                prior_resolution_summary=last_doubt_state["summary"],
            )
            return

        logger.warning("doubt.unknown_satisfaction_choice", option=choice)

    @ctx.room.on("data_received")
    def _on_data_received(packet: DataPacket) -> None:
        if packet.topic != _DOUBT_TOPIC:
            return
        try:
            payload = json.loads(packet.data)
        except (json.JSONDecodeError, TypeError):
            logger.warning("doubt.invalid_payload", raw=packet.data)
            return
        msg_type = payload.get("type")
        if msg_type == "doubt_intent":
            task = asyncio.create_task(_handle_doubt_intent(payload))
        elif msg_type == "satisfaction_choice":
            task = asyncio.create_task(_handle_satisfaction_choice(payload))
        else:
            return
        pending_tasks.add(task)
        task.add_done_callback(pending_tasks.discard)

    # Idle in the room until shutdown; handlers run as background tasks
    # above. The Event never resolves — the LiveKit framework cancels this
    # coroutine when the room closes.
    try:
        await asyncio.Event().wait()
    finally:
        await doubt_delivery.stop(ctx.room)
        if memory_store is not None:
            try:
                await memory_store.close()
            except Exception:
                logger.warning("worker.memory_store_close_failed", exc_info=True)


_SATISFACTION_OPTIONS: list[dict[str, str]] = [
    {
        "key": "crystal_clear",
        "label": "Crystal clear",
        "description": "Let's keep going.",
    },
    {
        "key": "counter_doubt",
        "label": "Have a counter-doubt",
        "description": "I want to ask another question.",
    },
    {
        "key": "somewhat_cleared",
        "label": "Somewhat cleared",
        "description": "Some parts are still fuzzy.",
    },
    {
        "key": "start_over",
        "label": "Start over",
        "description": "Try a different angle.",
    },
]


async def _publish_doubt(ctx: JobContext, payload: dict[str, Any]) -> None:
    """Publish a doubt-signal payload back to the frontend over the data channel."""
    await ctx.room.local_participant.publish_data(
        json.dumps(payload).encode(),
        reliable=True,
        topic=_DOUBT_TOPIC,
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

    # Parse room metadata for lesson configuration
    meta = _parse_room_metadata(ctx)

    # Lecture playback mode: precomputed lecture is driven by the frontend
    # client-side; the agent stays connected to the room but silent except
    # when the Ask Feynman button fires a `doubt_intent` data-channel
    # message. Phase 3 wires capture-only STT; Phase 4 adds classifier +
    # planner; Phase 5 adds the live voice + visual resolution delivery.
    lecture_chapter_id = meta.get("lecture_chapter_id")
    if lecture_chapter_id:
        logger.info(
            "worker.lecture_playback_mode",
            room_name=ctx.room.name,
            chapter_id=lecture_chapter_id,
        )
        await _run_lecture_mode(
            ctx,
            chapter_id=lecture_chapter_id,
            student_id=meta.get("student_id"),
            study_session_id=meta.get("study_session_id"),
        )
        return


if __name__ == "__main__":
    cli.run_app(server)
