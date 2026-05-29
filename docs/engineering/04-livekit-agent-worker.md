# 04 — LiveKit Agent Worker (`backend/src/feynman/livekit/`)

**Branch:** `feat/unify_boardstate` · **Last verified:** 2026-05-28

## TL;DR

The LiveKit agent worker is a **separate Python process** from the FastAPI server. It is the real-time path. It:

1. Connects to LiveKit as an `AgentServer`.
2. Reads room metadata (set by FastAPI at create-session time) to learn what to do.
3. Branches into **interactive teaching mode** (live STT → Claude → TTS loop with the full teaching state machine) or **lecture-playback mode** (silent until the student taps "Ask Feynman," then runs the doubt-resolution pipeline).
4. Publishes visual instructions to the frontend over the LiveKit data channel topic `"visuals"`.
5. Subscribes to data-channel messages from the frontend on topics `"bounds"`, `"board_capture"`, `"doubt_signal"`.

Started by `make dev-worker` which runs `cd backend && uv run python -m feynman.livekit.worker dev`. The FastAPI server doesn't know it exists — they communicate through the **LiveKit room** (audio + data channels) and **Postgres/Redis** (session state).

```
                      ┌─────────────────────┐
                      │  FastAPI            │
                      │  POST /api/sessions │
                      │  - persist session  │
                      │  - create LK room   │
                      │  - mint JWT         │
                      │  - return token     │
                      └────────┬────────────┘
                               │ (HTTP)
                               ▼
                      ┌─────────────────────┐
                      │  Browser            │ ──┐
                      └────────┬────────────┘   │
                               │                │
                       WebRTC  │                │ (HTTP API)
                               │                │
                               ▼                │
                      ┌─────────────────────┐   │
                      │  LiveKit server     │◀──┘
                      │  (room hosting)     │
                      └────────┬────────────┘
                               │ (WebRTC + data)
                               ▼
                      ┌─────────────────────┐
                      │  LiveKit Worker     │  ──── this doc
                      │  (separate process) │
                      │  ────────────────── │
                      │  AgentServer        │
                      │  ↳ rtc_session()    │
                      │    ↳ entrypoint()   │
                      │      ↳ mode branch  │
                      └─────────────────────┘
```

---

## 1. Entry point — `worker.py`

`worker.py` is 959 lines. The bottom of the file:

```python
if __name__ == "__main__":                          # worker.py:958
    cli.run_app(server)
```

`server` is a module-level `AgentServer` (`worker.py:812-816`):

```python
server = AgentServer(
    ws_url=settings.livekit_url,
    api_key=settings.livekit_api_key,
    api_secret=settings.livekit_api_secret,
)
```

`cli.run_app(server)` is the LiveKit Agents SDK's standard CLI. `dev` arg picks development mode (auto-restart, verbose logging).

The actual work is decorated:

```python
@server.rtc_session()                               # worker.py:819
async def entrypoint(ctx: JobContext) -> None:
    logger.info("worker.session_start", room_name=ctx.room.name)
    await ctx.connect()
    meta = _parse_room_metadata(ctx)
    lecture_chapter_id = meta.get("lecture_chapter_id")
    if lecture_chapter_id:
        await _run_lecture_mode(ctx, chapter_id=lecture_chapter_id)
        return
    # ... interactive teaching mode ...
```

### Room metadata parsing

`_parse_room_metadata()` (`worker.py:520-529`) reads `ctx.room.metadata`, which was set by FastAPI's `_create_livekit_room()` at session creation:

```python
{
  "topic": "Kinematics in 1D",
  "subject": "physics",
  "grade_level": "9",
  "lecture_chapter_id": null      // or "chapter_physics_..."
}
```

If `lecture_chapter_id` is set → lecture-playback mode. Otherwise → interactive teaching mode with the given `topic` + `subject`.

### Interactive teaching mode (the live path)

```python
# worker.py:847-944 (heavily abbreviated)
topic   = meta.get("topic", "")
subject = Subject(meta["subject"]) if meta.get("subject") else None

session_id = uuid4()
state_machine = TeachingStateMachine(session_id=session_id)
teaching_ctx  = TeachingContext(session_id=session_id, state_machine=state_machine)

# Wire BoardVerifier with a publish callback that uses the LiveKit data channel
async def _publish_capture(data: str, topic: str) -> None:
    await ctx.room.local_participant.publish_data(data.encode(), reliable=True, topic=topic)

teaching_ctx.board_verifier = BoardVerifier(publish_fn=_publish_capture, audit=teaching_ctx.audit)

# Register data-channel listeners for bounds + board_capture
def _on_data_received(packet: rtc.DataPacket) -> None:
    if packet.topic == "bounds":
        report = BoundsReportPayload.model_validate_json(packet.data)
        teaching_ctx.board_manager.update_bounds(report.board_id, report)
    elif packet.topic == "board_capture":
        teaching_ctx.board_verifier.handle_capture_response(packet.data)
ctx.room.on("data_received", _on_data_received)

# Construct the LiveKit Agent + session
agent = FeynmanAgent(teaching_ctx)
session = AgentSession(
    stt=create_stt(),
    llm=create_llm(),
    tts=create_tts(),
    vad=create_vad(),
    userdata=teaching_ctx,
    use_tts_aligned_transcript=True,
    max_tool_steps=30,
)

# Start handling audio
await session.start(agent=agent, room=ctx.room)
```

After `session.start()`:

- LiveKit captures the student's audio and routes it through `create_stt()` → transcript.
- Transcript appended to `chat_ctx.messages`.
- LLM (`create_llm()`) generates response chunks + tool calls.
- Tools execute with `ctx.userdata` = `teaching_ctx` (the `TeachingContext`).
- Response text flows through `Agent.tts_node` override (action tag parser strips inline tags) → `create_tts()` → audio frames → room audio track.

### `FeynmanAgent` (subclass of `livekit.agents.Agent`)

Defined inside `worker.py`. Key overrides:

| Method | Purpose |
|---|---|
| `on_enter()` (line 358–517) | Run at session start. Load curriculum from Neo4j (`load_curriculum`), build a `LessonPlan`, fire anticipation warm-up for the first 3 concepts, async-plan concepts 0 and 1 via `plan_concept`, then `update_instructions()` with the assembled `TEACHING_SYSTEM_PROMPT`. |
| `llm_node` override (~line 250) | Before each LLM call, drain `teaching_ctx.perception_feedback_queue` and inject any items as `[PERCEPTION_FEEDBACK] ...` synthetic user messages. |
| `tts_node` override (line 282–311) | Wrap the LLM text stream with `strip_action_tags()` from `livekit/action_tag_dispatch.py` — inline `<highlight>`, `<pulse>`, `<callout>`, `<bracket>`, `<pin>` tags are stripped from the TTS-bound text and dispatched as visual instructions in parallel. |
| Drift check task (line 337–356) | Background `asyncio.Task` started in `on_enter`; sleeps 30s and runs `_run_drift_check(teaching_ctx)` which captures the board and feeds it to `BoardVerifier`. Cancelled in `finally`. |

---

## 2. STT/LLM/TTS pipeline — `pipeline.py`

68 lines. Four factory functions, each chooses a provider with fallbacks.

```python
def create_stt() -> stt.STT:                        # pipeline.py:18
    if settings.deepgram_api_key:
        return deepgram.STT(model="nova-3", language="en", api_key=settings.deepgram_api_key)
    return openai.STT(model="gpt-4o-mini-transcribe", language="en",
                      api_key=_key_or_none(settings.openai_api_key))

def create_llm() -> anthropic.LLM:                  # pipeline.py:34
    return anthropic.LLM(model="claude-sonnet-4-20250514",
                         api_key=_key_or_none(settings.anthropic_api_key))

def create_tts() -> tts.TTS:                        # pipeline.py:43
    if settings.cartesia_api_key:
        return cartesia.TTS(
            model="sonic-3",
            voice="91925fe5-42ee-4ebe-96c1-c84b12a85a32",  # voice "amit"
            language="en",
            api_key=settings.cartesia_api_key,
        )
    return openai.TTS(model="gpt-4o-mini-tts", voice="ash",
                      api_key=_key_or_none(settings.openai_api_key))

def create_vad() -> vad.VAD:                        # pipeline.py:62
    return silero.VAD.load()
```

| Component | Primary | Fallback |
|---|---|---|
| STT | Deepgram nova-3 | OpenAI gpt-4o-mini-transcribe |
| LLM | Claude Sonnet 4 | (none — error if API key missing) |
| TTS | Cartesia sonic-3 (voice "amit", UUID `91925fe5...`) | OpenAI gpt-4o-mini-tts (voice "ash") |
| VAD | Silero (loaded locally, offline) | — |
| Turn detection | `livekit-plugins-turn-detector` | — |

> The `livekit/CLAUDE.md` mentions "OpenAI GPT (sub-tasks)" for LLM but pipeline.py always returns Claude. The sub-task LLM calls (planning, design generation, judges) bypass this pipeline and use their own clients via `feynman_teaching_kernel.planner` and `feynman/agent/design_bridge.py`.

---

## 3. Room lifecycle — `room.py`

The file is a stub (one-line docstring). All room logic lives on `JobContext.ctx.room` from the LiveKit SDK. There is no Feynman-specific room abstraction layer. The worker uses:

- `ctx.room.metadata` — the session config JSON.
- `ctx.room.local_participant.publish_data(...)` — to send visuals + capture requests.
- `ctx.room.on("data_received", ...)` — to receive bounds reports, capture responses, doubt signals.
- `ctx.room.local_participant.publish_track(...)` — only in lecture mode (DoubtDelivery publishes its own audio track).

---

## 4. Action tag dispatch — `action_tag_dispatch.py` (285 lines)

Inline action tags (`<highlight target="weight"/>`, `<pulse target="..."/>`, `<callout from="..." text="..." direction="up-right"/>`, `<bracket between="a,b" label="..." side="above"/>`, `<pin near="..." label="..." position="above"/>`) are emitted by the LLM mid-stream and converted into visual instructions in parallel with TTS.

### Strip + dispatch

```python
async def strip_action_tags(text: AsyncIterable[str], on_tag) -> AsyncGenerator[str]:
    # worker.py:282-311 — used as the tts_node middleware
    parser = ActionTagParser()
    async for chunk in text:
        clean, tags = parser.feed(chunk)
        for tag in tags:
            on_tag(tag)                # synchronously, schedules dispatch task
        if clean:
            yield clean
    tail = parser.finalize()
    if tail:
        yield tail
```

The `on_tag` callback schedules `dispatch_action_tag(session, tag)` (async):

```python
async def dispatch_action_tag(session, tag):       # action_tag_dispatch.py:107-123
    try:
        ctx = _ActionTagContext(session)
        instruction = _build_instruction(ctx, tag)
        if instruction is None: return
        await _publish_visual(ctx, instruction, wait_for_speech=False)
        _schedule_verification_from_tag(ctx, tag, instruction)
    except Exception:
        logger.warning("action_tag.dispatch_failed", verb=tag.verb, attrs=tag.attrs, exc_info=True)
```

### Instruction builders (one per verb)

| Verb | Builds | Default `duration_ms` |
|---|---|---|
| `<highlight target="X"/>` | `HighlightPulseInstruction` | 1500 |
| `<pulse target="X"/>` | `HighlightPulseInstruction` | 800 |
| `<callout from="X" text="..." direction="..."/>` | `DrawCalloutInstruction` | — |
| `<bracket between="X,Y" label="..." side="..."/>` | `BracketInstruction` | — |
| `<pin near="X" label="..." position="..."/>` | `PinLabelInstruction` | — |

The `target=` attribute may be:
- An `element_id` (e.g., `target="design-5"`).
- A `role` (resolved via the active diagram dictionary, e.g., `target="hypotenuse"`).
- A `data-attr` (resolved on the frontend's DOM).

`_schedule_verification_from_tag()` bridges to Phase 5a perception verification — fires an async vision check that "is the spotlight actually on the right thing?" and enqueues `PerceptionFeedback` if not.

### Sync behavior

Action-tag instructions are published with `wait_for_speech=False` and `sync_mode=SyncMode.AFTER_NEXT_SENTENCE`. The frontend's `useVisualChannel.ts` holds them in a queue until the next sentence boundary (`.`, `!`, `?`) in the transcribed agent speech, then drains. This makes annotations land *with* the spoken word, not after it.

---

## 5. Doubt delivery (lecture mode) — `doubt_delivery.py` (180 lines)

In **lecture-playback mode**, the worker stays silent until the student taps "Ask Feynman." Then a structured doubt-resolution pipeline runs and `DoubtDelivery` speaks each beat.

### The class

```python
class DoubtDelivery:                                # doubt_delivery.py:45-166
    def __init__(self, tts: tts.TTS):
        self._tts = tts
        self._audio_source: rtc.AudioSource | None = None
        self._track: rtc.LocalAudioTrack | None = None
        self._track_sid: str | None = None
        self._lock = asyncio.Lock()

    async def start(self, room: rtc.Room) -> None:                   # line 59
        self._audio_source = rtc.AudioSource(
            sample_rate=self._tts.sample_rate,
            num_channels=self._tts.num_channels,
        )
        self._track = rtc.LocalAudioTrack.create_audio_track("feynman-voice", self._audio_source)
        publication = await room.local_participant.publish_track(self._track)
        self._track_sid = publication.sid

    async def speak(self, text, on_first_frame=None):                 # line 95
        async with self._lock:
            stream = self._tts.synthesize(text)
            first = True
            async for frame in stream:
                if first:
                    if on_first_frame: on_first_frame()
                    first = False
                await self._audio_source.capture_frame(frame)

    async def deliver_resolution(self, *, plan, chapter_context,
                                  publish_data, on_first_frame=None):  # line 145
        first_voice_callback = on_first_frame
        for index, beat in enumerate(plan.beats):
            await publish_data(_beat_payload(index, beat))            # doubt_beat_start
            await asyncio.sleep(_BEAT_VISUAL_GRACE_MS / 1000)         # 150 ms for frontend
            await self.speak(beat.narration_text, on_first_frame=first_voice_callback)
            first_voice_callback = None
```

`DoubtDelivery` owns a single outbound audio track. It synthesizes TTS frames and pushes them into the audio source frame-by-frame.

### Lecture-mode workflow — `_run_lecture_mode()` (`worker.py:535-776`)

```
1. Set up:
   - LectureDoubtSession from chapter metadata (loads chapter from Neo4j)
   - DoubtDelivery instantiated + started (publishes audio track)
   - Data-channel listener registered for topic "doubt_signal"

2. Wait silently in the room.

3. Frontend publishes a doubt_intent message:
     { type: "doubt_intent", chapter_id, cursor, topic_id, board_snapshot }
   ↓
   _handle_doubt_intent():
   - Pause acknowledgment (publish thinking state)
   - Capture student audio via STT (single utterance)
   - Publish doubt_captured { text, duration_ms }
   - Call doubt_session.resolve(text, classification, board_snapshot)
     ↓ LectureDoubtSession runs:
     - DoubtClassifier (classify type)
     - prereq_walker (BFS context)
     - ResolutionPlanner (3-5 beats via Claude)
     - DiagramFitMatcher (Haiku check each diagram against each beat)
   - Publish resolution_ready { beats: summary, matched_diagram_ids }
   - DoubtDelivery.deliver_resolution(plan):
     - For each beat:
       - Publish doubt_beat_start { beat_index, target_diagram_id, annotation_actions }
       - Sleep 150ms (frontend swaps visuals)
       - Speak narration via TTS
   - Publish satisfaction_prompt { options: [crystal_clear, counter_doubt, somewhat_cleared, start_over] }

4. Frontend publishes satisfaction_choice:
     { type: "satisfaction_choice", option: "crystal_clear" | ... }
   ↓
   _handle_satisfaction_choice():
   - crystal_clear     → publish lecture_resume → frontend resumes playback
   - counter_doubt     → re-capture, run resolve() again
   - somewhat_cleared  → prompt clarification, re-capture
   - start_over        → re-resolve same doubt with different_angle=True
                          (so LLM picks a different framing)
```

The frontend's `LectureViewer` consumes these `doubt_signal` messages and manages its own state machine. See `08-frontend-architecture.md` §"Lecture viewer doubt flow."

### Data channel topics used by the worker

| Topic | Direction | Sender | Receiver | Content |
|---|---|---|---|---|
| `visuals` | Worker → Frontend | `_publish_visual` in `agent/tools.py` + `action_tag_dispatch.py` | `useVisualChannel.ts` | JSON-serialized `VisualInstruction` |
| `bounds` | Frontend → Worker | Frontend's `BoundsReporter` | `_on_data_received` handler in `worker.py:869` | `BoundsReportPayload` (element pixel rects after render) |
| `board_capture` | Bidirectional | Worker requests, frontend responds | Both ends in `worker.py` and frontend `WhiteboardScene` | Capture request from worker; base64 PNG screenshot back |
| `doubt_signal` | Bidirectional | Lecture mode: frontend (intent + satisfaction), worker (captured + ready + beats + resume) | `_handle_doubt_intent` etc. | JSON messages described in §5 |

---

## 6. Imports — what the worker reaches into

From `feynman.agent`:

| Symbol | Source | Use |
|---|---|---|
| `TeachingStateMachine` | `agent/state_machine.py` | Created per session. |
| `TeachingState` | `agent/states.py` | Enum. |
| `TeachingContext` | `agent/teaching_context.py` | `userdata` on the `AgentSession`. |
| `TEACHING_SYSTEM_PROMPT` (+ submodules) | `agent/prompts.py` | Assembled in `on_enter`. |
| (all tools via implicit registration) | `agent/tools.py` | Bound to `FeynmanAgent` via LiveKit's `@function_tool` discovery. |
| `load_curriculum` | `agent/curriculum_loader.py` | Loads Neo4j curriculum at session start. |
| `lesson_plan_from_curriculum` | `agent/lesson_plan.py` | Builds LessonPlan. |
| `BoardVerifier` | `agent/board_verifier.py` | Vision verification. |
| `ActionTag`, `ActionTagParser` | `agent/action_tag_parser.py` | Inline tag streaming parser. |
| `LectureDoubtSession`, `ResolutionPlan`, `load_chapter_by_id` | `agent/doubt_resolution/*` | Lecture-mode doubt pipeline. |

From `feynman_teaching_kernel`:

| Symbol | Use |
|---|---|
| `plan_concept` | Background async planning of upcoming concepts in `on_enter` + on each `advance_concept`. |
| `ConceptTeachingPlan` | Type hint, stored on `TeachingContext.concept_plans`. |
| `ChecklistItem` | Type hint for doubt branch checklists. |

From `livekit`:

| Symbol | Source | Use |
|---|---|---|
| `Agent`, `AgentServer`, `AgentSession`, `JobContext` | `livekit.agents` | Core SDK. |
| `cli.run_app` | `livekit.agents.cli` | CLI entry. |
| `stt`, `tts`, `vad`, `function_tool`, `RunContext` | `livekit.agents` | Plugin protocols. |
| `rtc` | `livekit` | WebRTC primitives. |
| `silero`, `deepgram`, `anthropic`, `cartesia`, `openai` | `livekit.plugins.*` | Provider implementations. |

From config / common:

| Symbol | Use |
|---|---|
| `settings` | API keys, URLs. |
| `Subject` | Enum. |

---

## 7. Control flow — interactive mode

```
worker process started: python -m feynman.livekit.worker dev
  └─ cli.run_app(server) connects to LiveKit ws_url

Frontend joins room (using token from /api/sessions):
  ↓ LiveKit dispatches a new job
  ↓ @server.rtc_session() entrypoint() fires with JobContext

entrypoint:
  await ctx.connect()
  meta = _parse_room_metadata(ctx)
  if meta.lecture_chapter_id:
    return _run_lecture_mode(ctx, chapter_id=...)
  
  # Interactive mode
  state_machine  = TeachingStateMachine(session_id=uuid4())
  teaching_ctx   = TeachingContext(session_id, state_machine)
  teaching_ctx.board_verifier = BoardVerifier(publish_fn=_publish_capture)
  ctx.room.on("data_received", _on_data_received)
  
  agent   = FeynmanAgent(teaching_ctx)
  session = AgentSession(stt=create_stt(), llm=create_llm(),
                         tts=create_tts(), vad=create_vad(),
                         userdata=teaching_ctx,
                         use_tts_aligned_transcript=True,
                         max_tool_steps=30)
  
  await session.start(agent=agent, room=ctx.room)
  
  # session.start() never returns until the room closes
  # During its lifetime:
  #   - Audio in → STT → LLM (with @llm_node override that injects perception feedback)
  #   - LLM → tools → publish_data on "visuals" topic
  #   - LLM text → tts_node (strip_action_tags) → TTS → audio track
  #   - Drift check task runs every 30s

  # On room close:
  if drift_task: drift_task.cancel()
```

---

## 8. Data flow — visual instructions

The single most important data path. The worker is the only writer to topic `"visuals"`.

```
TOOL CALL                              ACTION TAG
(LLM emits a tool call)               (LLM emits inline <highlight target="X"/>)
        │                                          │
        ▼                                          ▼
agent/tools.py::draw_design_diagram   agent/action_tag_parser.py::feed()
        │                              ↓ returns (clean_text, tags)
        ▼                              ↓
agent/tools.py::_publish_visual       livekit/action_tag_dispatch.py::dispatch_action_tag
        │                              ↓ _build_instruction() → HighlightPulseInstruction
        ▼                              ↓
{
  resolve_placement,
  stamp board_id,
  stamp panel,
  board_manager.record() ──────────────┬── BoardState updates (_elements, board_graph, spatial_solver)
                                       │
  audit.record(),                      │
  wait_for_playout (if ON_PLAYOUT),    │
  publish_data(topic="visuals",        │
               reliable=True,          │
               JSON(instruction))      │
}                                      │
        │                              │
        └──────────────┬───────────────┘
                       ▼
              LiveKit data channel
                       │
                       ▼
           Frontend useVisualChannel.ts::onMessage
                       │
                       ▼
           TextDecoder.decode → JSON.parse → VisualInstruction
                       │
                       ├── if sync_mode === "after_next_sentence" → enqueueDeferred
                       └── else → applyInstruction
                                       │
                                       ├── board store (split board / whiteboard)
                                       └── ElementRegistry → render

After frontend renders → ResizeObserver → BoundsReportPayload → publish_data(topic="bounds")
                                                                                  │
                                                                                  ▼
                                                                worker._on_data_received
                                                                                  │
                                                                                  ▼
                                                            board_manager.update_bounds(report)
                                                                                  │
                                                                                  ▼
                                                            BoardState.update_spatial(report)
                                                              │       │       │
                                                              ▼       ▼       ▼
                                                          scene_graph  spatial_solver (refreshed)
```

---

## 9. Data flow — perception feedback (Phase 5a)

```
Every 30 seconds, drift check task:
  await asyncio.sleep(30)
  if _should_run_drift_check(teaching_ctx):
    state_hash = compute_drift_state_hash(concept_index, element_ids, versions)
    if state_hash == last_drift_check_hash: skip   # nothing changed
    
    # Request board screenshot from frontend
    await publish_data(topic="board_capture", { type: "capture_request" })
    # ... frontend responds with topic="board_capture", { type: "capture_response", png_b64 } ...
    
    # Send to BoardVerifier (vision model)
    verdict = await board_verifier.request_drift_check(png_b64, current_concept)
    
    if verdict.drift_detected:
      teaching_ctx.perception_feedback_queue.append(PerceptionFeedback(
        kind="drift",
        message=verdict.message,
        concept_index=current_concept_index,
      ))
    
    last_drift_check_hash = state_hash

Skip conditions:
- No board verifier (lecture mode)
- Inside a doubt branch (depth > 1)
- No current concept
- No diagrams on board
- Budget exhausted (1 feedback per concept)
- State hash unchanged

On next LLM turn:
  Agent.llm_node override:
    while teaching_ctx.perception_feedback_queue:
      fb = queue.pop(0)
      chat_ctx.append({
        role: "user",
        content: f"[PERCEPTION_FEEDBACK] {fb.message}",
      })
```

The agent treats `[PERCEPTION_FEEDBACK]` messages as instruction to correct course — re-draw the diagram, adjust focus, etc.

---

## 10. Lecture mode — full picture

```
                                  ┌─────────────────────────────────┐
                                  │  LectureViewer (frontend)       │
                                  │  - useExtractionPlayback        │
                                  │  - walks chapter.events[]       │
                                  │  - plays audio/diagrams/notebook│
                                  └────────────┬────────────────────┘
                                               │
                                  Student taps "Ask Feynman"
                                               │
                                  publish_data(topic="doubt_signal", {
                                      type: "doubt_intent",
                                      chapter_id, cursor, topic_id,
                                      board_snapshot              ← from feat/unify_boardstate
                                  })
                                               │
                                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Worker (lecture mode)                                               │
│                                                                      │
│  _on_doubt_message() routes by type:                                 │
│                                                                      │
│  type="doubt_intent" → _handle_doubt_intent() → _capture_then_resolve│
│    1. publish_data({type:"thinking"})  (frontend shows spinner)      │
│    2. STT: capture student utterance (up to 12s)                    │
│    3. publish_data({type:"doubt_captured", text, duration_ms})       │
│    4. doubt_session.resolve(text, classification, board_snapshot):   │
│       - DoubtClassifier (LLM)                                        │
│       - prereq_walker (BFS Neo4j prereq graph)                       │
│       - ResolutionPlanner (Claude, structured output)                │
│       - DiagramFitMatcher (Haiku, per beat × per available diagram)  │
│       → ResolutionPlan(beats: list[ResolutionBeat])                  │
│    5. publish_data({type:"resolution_ready",                         │
│                      beats: [...summaries],                          │
│                      matched_diagram_ids: [...]})                    │
│    6. doubt_delivery.deliver_resolution(plan):                       │
│       For each beat:                                                 │
│       - publish_data({type:"doubt_beat_start",                       │
│                       beat_index, target_diagram_id,                 │
│                       annotation_actions: [FocusAction, ...]})       │
│       - sleep(150ms)  # frontend swaps visuals                       │
│       - await tts.speak(beat.narration_text)                         │
│    7. publish_data({type:"satisfaction_prompt",                      │
│                      options: ["crystal_clear", ...]})               │
│                                                                      │
│  type="satisfaction_choice" → _handle_satisfaction_choice():         │
│    - "crystal_clear": publish_data({type:"lecture_resume"})          │
│    - "counter_doubt": _capture_then_resolve again                    │
│    - "somewhat_cleared": prompt clarification, capture, resolve      │
│    - "start_over": resolve same doubt with different_angle=True      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 11. `livekit/CLAUDE.md`

Short summary (27 lines). Key claim:

> "The LiveKit agent worker runs as a **separate process** from the FastAPI server"
> 
> FastAPI = request/response (REST API, WebSocket for visuals)
> LiveKit worker = long-running process (joins rooms, runs STT→LLM→TTS pipeline)

Note: the "WebSocket for visuals" line is **outdated** — visuals go over LiveKit data channels, not WebSocket. `api/ws.py` is a placeholder.

---

## Summary table

| Topic | Producer | Consumer | Payload type | Reliability |
|---|---|---|---|---|
| `visuals` | Worker (`_publish_visual`, `dispatch_action_tag`) | Frontend (`useVisualChannel`) | `VisualInstruction` JSON | reliable |
| `bounds` | Frontend (`BoundsReporter`) | Worker (`_on_data_received`) | `BoundsReportPayload` JSON | reliable |
| `board_capture` | Worker (capture request) / Frontend (capture response) | The opposite end | Capture req/resp JSON + base64 PNG | reliable |
| `doubt_signal` | Lecture-mode flow | Both ends | One of `doubt_intent`, `doubt_captured`, `resolution_ready`, `doubt_beat_start`, `satisfaction_prompt`, `satisfaction_choice`, `lecture_resume` | reliable |

---

## Reading order for a new engineer

1. `livekit/CLAUDE.md`.
2. This doc end-to-end.
3. `worker.py:819-954` — `entrypoint`. Read it twice.
4. `worker.py:535-776` — `_run_lecture_mode`. Read it once.
5. `pipeline.py` — the four factory functions.
6. `action_tag_dispatch.py` — the inline-tag path (it's clever).
7. `doubt_delivery.py` — only ~180 lines.
8. Cross-reference `03-teaching-state-machine.md` for what tools the worker dispatches.
