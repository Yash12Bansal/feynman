# 09 — End-to-end Trace: A Lesson From Click to Resolution

**Branch:** `feat/unify_boardstate` · **Last verified:** 2026-05-28

This doc follows **one concrete student session** from the first browser request to the last spoken word. It cross-references every module so you can use it as a vertical slice through the architecture.

The scenario: **Aanya, a Year 9 IGCSE student, opens the app at home at 8 PM, picks a precomputed chapter on Newton's Laws, watches for two minutes, gets confused, taps "Ask Feynman" to ask a doubt, and resumes.** This exercises both playback modes plus the doubt-resolution path.

For terminology, see the module docs:
- `00-system-overview.md` — system map
- `01-precompute-pipeline.md` — what the manifest contains
- `04-livekit-agent-worker.md` — worker process details
- `07-contracts-and-protocols.md` — wire formats
- `08-frontend-architecture.md` — frontend screens

> **Deeper than this doc:** for the exact file:line control flow (and a verified known-issues list) of the two halves of this trace, read `11-precompute-playback-flow.md` (the lecture playing in sync) and `12-ask-feynman-flow.md` (the doubt pipeline). This doc is the readable narrative; 11 and 12 are the forensic detail.

---

## Step 0 — assumptions

By the time Aanya opens the app:

1. **The precompute pipeline has been run** for the textbook. Specifically, for chapter `chapter_physics_newtons_laws`, Neo4j has:
   - A `Chapter` node with `chapter_manifest` (the ordered event sequence), `board_snapshots` (one per page), and `lecture_plan`.
   - A handful of `Topic` nodes connected via `CONTAINS` + `NEXT`.
   - `Diagram` nodes (HAS_DIAGRAM edges to topics) carrying SVG `render_data`.
   - `Question` nodes for end-of-chapter problems.
2. **Audio artifacts** exist at `data_pre_compute_v2/artifacts/audio/chapter_physics_newtons_laws/*.mp3`, named by `<topic_id>_chapter_<index>.mp3`.
3. **Diagram artifacts** exist at `data_pre_compute_v2/artifacts/diagrams/diagram_*.svg` (and `.png` fallbacks).
4. **All five dev processes are running**: Postgres, Redis, Neo4j, LiveKit, FastAPI, LiveKit worker, frontend (Vite), preview server. In dev, `make dev` brought them up.

---

## Step 1 — Aanya opens the app

Aanya types `http://localhost:5173` into her browser.

### What the browser does

```
GET http://localhost:5173/
  └── Vite serves index.html
  └── Browser loads /src/main.tsx (via Vite HMR)
  └── React mounts <App />

App.tsx:
  - useHashRoute() returns "" (no hash)
  - It's not /dev, not /dev/split-board, etc.
  - Returns <MainEntry />
MainEntry:
  - useLectureChapterParam() returns null (no ?lecture= in URL)
  - Returns <LectureHomeScreen />
```

### What LectureHomeScreen does

`frontend/src/screens/LectureHomeScreen.tsx`:

```tsx
const [chapters, setChapters] = useState<ChapterListEntry[]>([]);
useEffect(() => {
    fetch("/lecture-api/chapters")
        .then(r => r.json())
        .then(setChapters);
}, []);
```

The fetch goes to `/lecture-api/chapters` — but Vite's dev server (`vite.config.ts`) has a proxy: `"/lecture-api": "http://127.0.0.1:8080"`.

### What preview_server.py does

`data_pre_compute_v2/tools/preview_server.py` (FastAPI on `:8080`):

```python
@app.get("/api/chapters")
async def list_chapters():
    with neo4j_driver.session() as session:
        result = session.run("""
            MATCH (c:Chapter)
            RETURN c.chapter_id as id, c.title as title, c.chapter_index as idx,
                   c.chapter_manifest IS NOT NULL as has_manifest
            ORDER BY c.chapter_index
        """)
        return [{"id": r["id"], "title": r["title"], "idx": r["idx"],
                 "has_manifest": r["has_manifest"]} for r in result]
```

It queries Neo4j (`bolt://localhost:7687`), pulls the chapter list, returns it. Among other chapters, it returns `{id: "chapter_physics_newtons_laws", title: "Newton's Laws of Motion", idx: 5, has_manifest: true}`.

### What Aanya sees

A grid of chapter cards. She clicks "Newton's Laws of Motion."

```tsx
onClick={() => {
    window.location.search = `?lecture=${encodeURIComponent(c.id)}`;
}}
```

The URL changes to `http://localhost:5173/?lecture=chapter_physics_newtons_laws`. Browser reloads.

---

## Step 2 — session creation

The reload triggers App.tsx again.

```
App.tsx → MainEntry → useLectureChapterParam() returns "chapter_physics_newtons_laws"
                   → returns <MainApp lectureChapterId="chapter_physics_newtons_laws" />

MainApp:
  - useSession() initial status: "idle"
  - useEffect: startSession({ lecture_chapter_id: "chapter_physics_..." })

useSession.startSession (frontend/src/hooks/useSession.ts):
  - status → "connecting"
  - lib/api.createSession({ lecture_chapter_id: "chapter_..." }):
      POST /api/sessions
      Body: { lecture_chapter_id: "chapter_physics_newtons_laws" }
```

### What FastAPI does

`backend/src/feynman/api/sessions.py:79-105`:

```python
@router.post("", response_model=CreateSessionResponse)
async def create_session(request: Request, body: SessionCreate | None = None):
    manager = _get_manager(request)
    create = body or SessionCreate()
    info = await manager.create_session(create)
    await _create_livekit_room(
        info.room_name,
        topic=create.topic or "",
        subject=create.subject,
        grade_level=create.grade_level,
        lecture_chapter_id=create.lecture_chapter_id,    # "chapter_physics_..."
    )
    token = await _create_livekit_token(info.room_name)
    return CreateSessionResponse(
        session_id=info.id,
        token=token,
        livekit_url=settings.livekit_url,
        room_name=info.room_name,
        lecture_chapter_id=create.lecture_chapter_id,
    )
```

`SessionManager.create_session()` does three things:

1. **Generate IDs**: `session_id = uuid4()`, `room_name = f"feynman-{uuid.hex[:12]}"` (e.g., `feynman-a1b2c3d4e5f6`).
2. **Postgres write** via `SessionRepository.create(SessionModel(...))`:
   ```sql
   INSERT INTO sessions (id, room_name, subject, status, teaching_state, created_at, updated_at)
   VALUES ('<uuid>', 'feynman-a1b2c3d4e5f6', NULL, 'pending', 'idle', now(), now());
   ```
3. **Redis seed** via `SessionRedisStore.seed(...)`:
   ```
   HSET session:<uuid> status=pending teaching_state=idle room_name=feynman-... ...
   EXPIRE session:<uuid> 86400
   ```

Then `_create_livekit_room` does:

```python
lkapi = api.LiveKitAPI(settings.livekit_url, settings.livekit_api_key, settings.livekit_api_secret)
meta = json.dumps({
    "topic": "",
    "subject": None,
    "grade_level": None,
    "lecture_chapter_id": "chapter_physics_newtons_laws",
})
await lkapi.room.create_room(api.CreateRoomRequest(name="feynman-a1b2c3d4e5f6", metadata=meta))
```

This pre-creates the room in the LiveKit server with the chapter ID embedded in metadata. **This is how the worker will know what to play.**

Then `_create_livekit_token` mints a JWT with `room_join, room=feynman-..., can_publish, can_subscribe, can_publish_data` grants.

Response goes back to the frontend.

### What the frontend does next

```typescript
// useSession.ts
const result = await createSession({ lecture_chapter_id: "chapter_..." });
setSessionId(result.session_id);
setToken(result.token);
setLivekitUrl(result.livekit_url);
setLectureChapterId(result.lecture_chapter_id);
setStatus("connected");
```

MainApp re-renders. Status is "connected" now.

```tsx
return (
    <RoomProvider token={token} serverUrl={livekitUrl}>
        <ClassroomScreen lectureChapterId={lectureId} />
    </RoomProvider>
);
```

---

## Step 3 — WebRTC connection establishes

`<LiveKitRoom>` from `@livekit/components-react`:

```tsx
<LiveKitRoom token={token} serverUrl={livekitUrl} connect={true} audio={true} video={false}>
    <RoomAudioRenderer />
    {children}
</LiveKitRoom>
```

WebRTC negotiation happens with the LiveKit server (`ws://localhost:7880`). The browser:

1. Exchanges SDP offer/answer over WebSocket.
2. ICE-establishes peer connections.
3. Subscribes to all participants' tracks (RoomAudioRenderer hooks audio elements up).
4. `onConnected()` fires (`console.log("LK connected")`).

Simultaneously, the LiveKit server notices a new participant joined `feynman-a1b2c3d4e5f6` and dispatches a job to a registered agent. **The worker's `@server.rtc_session()` decorator gets invoked.**

---

## Step 4 — worker enters the room

`backend/src/feynman/livekit/worker.py:819`:

```python
@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    logger.info("worker.session_start", room_name=ctx.room.name)
    await ctx.connect()
    meta = _parse_room_metadata(ctx)
    # meta == {"topic": "", "subject": None, "grade_level": None,
    #          "lecture_chapter_id": "chapter_physics_newtons_laws"}

    lecture_chapter_id = meta.get("lecture_chapter_id")
    if lecture_chapter_id:
        logger.info("worker.lecture_playback_mode", chapter_id=lecture_chapter_id)
        await _run_lecture_mode(ctx, chapter_id=lecture_chapter_id)
        return
    # ... interactive mode (not taken in this trace) ...
```

`_parse_room_metadata` reads `ctx.room.metadata` (the JSON string the FastAPI handler set). Sees `lecture_chapter_id` is set → branches to lecture mode.

### `_run_lecture_mode` setup

```python
async def _run_lecture_mode(ctx: JobContext, *, chapter_id: str) -> None:
    # 1. Load chapter context from Neo4j
    doubt_session = await LectureDoubtSession.from_chapter_id(chapter_id)
    
    # 2. Set up TTS for doubt delivery
    tts = create_tts()      # Cartesia sonic-3
    doubt_delivery = DoubtDelivery(tts)
    await doubt_delivery.start(ctx.room)
    # ↑ Publishes a LocalAudioTrack named "feynman-voice" — silent until DoubtDelivery.speak()

    # 3. Register listener for the "doubt_signal" topic
    def _on_data_received(packet: rtc.DataPacket) -> None:
        if packet.topic != "doubt_signal": return
        msg = json.loads(packet.data)
        if msg["type"] == "doubt_intent":
            asyncio.create_task(_handle_doubt_intent(ctx, msg, doubt_session, doubt_delivery))
        elif msg["type"] == "satisfaction_choice":
            asyncio.create_task(_handle_satisfaction_choice(ctx, msg, doubt_session, doubt_delivery))
        elif msg["type"] == "clarification":
            # ... etc
    ctx.room.on("data_received", _on_data_received)

    # 4. Sit and wait. Lecture is driven by the frontend's manifest playback.
    try:
        await asyncio.Event().wait()    # never sets unless we cancel
    finally:
        await doubt_delivery.stop()
```

The worker is now silent in the room. Its only job until further notice: wait for a `doubt_signal` message from the frontend.

---

## Step 5 — frontend fetches the manifest and starts playback

Back in the frontend, ClassroomScreen sees `lectureChapterId` and renders `<LectureViewer chapterId="chapter_physics_newtons_laws" />`.

```tsx
// LectureViewer.tsx
const [chapter, setChapter] = useState<ChapterPayload | null>(null);
useEffect(() => {
    fetch(`/lecture-api/chapter/${encodeURIComponent(chapterId)}`)
        .then(r => r.json())
        .then(setChapter);
}, [chapterId]);
```

### What preview_server.py returns

```python
@app.get("/api/chapter/{chapter_id}")
async def get_chapter(chapter_id: str):
    with neo4j_driver.session() as session:
        record = session.run(
            "MATCH (c:Chapter {chapter_id: $cid}) RETURN c.chapter_manifest, c.board_snapshots, c.title",
            cid=chapter_id,
        ).single()
        if not record: raise HTTPException(404)
        manifest_json = record["c.chapter_manifest"]
        manifest = json.loads(manifest_json)
        # Rewrite all file:// URLs to /lecture-artifacts/
        for event in manifest["events"]:
            if event["type"] == "audio":
                event["url"] = rewrite_url(event["url"])    # file://./artifacts/audio/... → /lecture-artifacts/audio/...
        return {
            "id": chapter_id,
            "title": record["c.title"],
            "events": manifest["events"],
            "board_snapshots": json.loads(record["c.board_snapshots"]),
        }
```

So `chapter.events` is a list like:

```json
[
    { "type": "topic_start", "topic_id": "topic_physics_newtons_laws_5.1" },
    { "type": "show_diagram", "diagram_id": "diagram_intro_force",
      "placement": { "x": 80, "y": 100, "w": 800, "h": 600 },
      "presentation_mode": "overview" },
    { "type": "audio", "url": "/lecture-artifacts/audio/chapter_physics_newtons_laws/topic_...5.1_chapter_0.mp3",
      "duration_ms": 4500 },
    { "type": "focus", "diagram_id": "diagram_intro_force",
      "target_element_id": "force-arrow", "text": "" },
    { "type": "audio", "url": "/lecture-artifacts/audio/...", "duration_ms": 3200 },
    { "type": "trace", "diagram_id": "diagram_intro_force",
      "element_id": "object-1", "duration_ms": 1500 },
    { "type": "write_section", "id": "sec-1", "title": "Newton's First Law" },
    { "type": "write_equation", "id": "eq-1", "latex": "\\sum F = 0", "boxed": false },
    ...
]
```

### Playback starts

```tsx
const { slide, notebook, cursor, currentTopicId, currentSnapshot,
        pause, play, applyDoubtBeat } = useExtractionPlayback({ chapter, autoStart: true });
```

`useExtractionPlayback` initialises state and fires `play()`. The loop body:

```typescript
async function playOne() {
    if (cursor >= chapter.events.length) return;
    const event = chapter.events[cursor];

    switch (event.type) {
        case "audio": {
            audioElement.src = event.url;
            await audioElement.play();
            await new Promise(r => audioElement.addEventListener("ended", r, { once: true }));
            // (or interrupted by pause())
            break;
        }
        case "pause":         await sleep(event.duration_ms); break;
        case "topic_start":   setCurrentTopicId(event.topic_id); break;
        case "show_diagram":  setSlide({ ...prev, active: lookupDiagram(event.diagram_id, chapter),
                                          status: "ready", focusedElementId: null }); break;
        case "focus":         setSlide(prev => ({ ...prev, focusedElementId: event.target_element_id })); break;
        case "trace":         setSlide(prev => ({ ...prev, traces: [...prev.traces, event] })); break;
        case "mark_point":    setSlide(prev => ({ ...prev, markPoints: [...prev.markPoints, event] })); break;
        case "point_at":      setSlide(prev => ({ ...prev, pointers: [...prev.pointers, event] })); break;
        case "write_margin":  setSlide(prev => ({ ...prev, marginNotes: [...prev.marginNotes, event] })); break;
        case "write_equation":
        case "write_step":
        case "write_text":
        case "write_section":
        case "write_answer":  appendNotebookEntry(event); break;
        case "strikethrough": markStruck(event.target_id); break;
        case "new_page":      turnPage(event.carry_forward_ids); break;
        case "clear_annotations": clearAnnotations(event.diagram_id); break;
    }
    setCursor(c => c + 1);
    setTimeout(playOne, 0);    // tail-call
}
```

The first event is `topic_start` (sets `currentTopicId`), then `show_diagram` (mounts the diagram on the slide panel), then `audio` (plays MP3 of the agent saying "Today we'll explore Newton's First Law of Motion..."), then `focus` (spotlights the force arrow as the agent says "force"), etc.

`<SplitBoard slide={slide} notebook={notebook}>` re-renders on every state update.

### What Aanya sees

- Left panel (Slide): a diagram of an object with a force arrow. Initially shown in `overview` mode (all elements visible). When `focus` events fire, the spotlight moves.
- Right panel (Notebook): a section header "Newton's First Law" appears, then equations and steps get written down line by line as the agent narrates.
- Bottom-right: a floating "Ask Feynman" button (idle state).
- Audio plays from her speakers — the agent's voice narrating the lesson.

This continues for ~2 minutes.

### `currentSnapshot` stays current

`useExtractionPlayback` also tracks `currentSnapshot: BoardSnapshot | null`. It's set whenever a `new_page` or `page_break` event fires, indexing into `chapter.board_snapshots[page_index]`. This is what the doubt-resolution path will use.

A `BoardSnapshot` has shape (from `01-precompute-pipeline.md` §10):

```typescript
interface BoardSnapshot {
    page_index: number;
    topic_id: string;
    elements: BoardElement[];     // diagrams + diagram_elements + notebook_blocks
}
```

It is the **authoritative answer to "what is on the board right now"** — the precompute pipeline computed it during Phase 3 (layout planning), and now it's hot in memory.

---

## Step 6 — Aanya gets confused

After two minutes, the agent has covered the First Law and is moving to discuss the Second Law (F=ma). Aanya doesn't see why force equals mass times acceleration "for real" — the agent had said something about an experiment but she missed it. She taps the "Ask Feynman" button.

### `AskFeynmanButton` invokes `onAskFeynman`

```tsx
// frontend/src/screens/LectureViewer.tsx:258
async function onAskFeynman() {
    pause();                                                  // stops the playback loop
    setDoubtState("listening");
    armStuckTimeout(12000, "Listening timed out...");          // 12s budget for STT capture

    const payload: DoubtIntentPayload = {
        type:           "doubt_intent",
        chapter_id:     chapterId,
        cursor:          cursor,                              // current event index, e.g. 47
        topic_id:        currentTopicId,                       // "topic_physics_..._5.2"
        board_snapshot:  currentSnapshot,                      // authoritative board state
    };

    await room.localParticipant.publishData(
        new TextEncoder().encode(JSON.stringify(payload)),
        { topic: "doubt_signal", reliable: true },
    );
}
```

### What `pause()` does

`useExtractionPlayback.pause()`:

```typescript
function pause() {
    audioElement.pause();
    isPlayingRef.current = false;
    setCursor(c => Math.max(c - 1, 0));      // rewind one event so resume includes the current one
}
```

Audio stops. Cursor rewinds. The slide and notebook state are preserved.

### The wire payload

The bytes that flow over the LiveKit data channel:

```json
{
    "type": "doubt_intent",
    "chapter_id": "chapter_physics_newtons_laws",
    "cursor": 47,
    "topic_id": "topic_physics_newtons_laws_5.2",
    "board_snapshot": {
        "page_index": 2,
        "topic_id": "topic_physics_newtons_laws_5.2",
        "elements": [
            { "element_id": "diagram_F_ma_intro", "kind": "diagram",
              "rect": { "x": 80, "y": 100, "w": 800, "h": 600 } },
            { "element_id": "force-arrow", "kind": "diagram_element",
              "parent_id": "diagram_F_ma_intro", "role": "force_vector",
              "semantic": "the applied force, F",
              "rect": { "x": 200, "y": 300, "w": 150, "h": 50 } },
            { "element_id": "eq-1", "kind": "notebook_block", "block_type": "equation",
              "rect": { "x": 1000, "y": 150, "w": 400, "h": 40 } }
        ]
    }
}
```

This crosses the WebRTC data channel and arrives at the worker.

---

## Step 7 — worker resolves the doubt

`_on_data_received` in the worker fires:

```python
def _on_data_received(packet: rtc.DataPacket) -> None:
    if packet.topic != "doubt_signal": return
    msg = json.loads(packet.data)
    if msg["type"] == "doubt_intent":
        asyncio.create_task(_handle_doubt_intent(ctx, msg, doubt_session, doubt_delivery))
```

The async task starts.

### Step 7.1 — STT captures Aanya's spoken question

```python
async def _handle_doubt_intent(ctx, msg, doubt_session, doubt_delivery):
    # 1. Immediately acknowledge — frontend shows "thinking" UI
    await _publish_doubt_signal(ctx, { "type": "thinking", "stage": "capturing" })

    # 2. Capture audio via STT (12s budget)
    stt = create_stt()    # Deepgram nova-3
    utterance = await capture_one_utterance(ctx.room, stt, max_duration_s=12)
    # capture_one_utterance subscribes to the student's audio track, waits for
    # speech start, accumulates transcript until VAD detects end-of-speech, returns text.

    # 3. Tell frontend we heard the question
    await _publish_doubt_signal(ctx, {
        "type": "doubt_captured",
        "text": utterance.text,
        "duration_ms": utterance.duration_ms,
    })

    # 4. Update UI: "Feynman is thinking..."
    await _publish_doubt_signal(ctx, { "type": "thinking", "stage": "planning" })
```

Aanya said: *"I don't get why force equals mass times acceleration. Like, why those specific quantities?"*

### Step 7.2 — DoubtClassifier + ResolutionPlanner + DiagramFitMatcher

```python
    # 5. Resolve the doubt
    plan = await doubt_session.resolve(
        text=utterance.text,
        cursor=msg["cursor"],
        topic_id=msg["topic_id"],
        board_snapshot=BoardSnapshot.model_validate(msg["board_snapshot"]),
    )
```

`LectureDoubtSession.resolve` (in `backend/src/feynman/agent/doubt_resolution/lecture_session.py`) runs:

```
1. DoubtClassifier (LLM call, Haiku):
   - Classify as one of: conceptual / procedural / prerequisite / perceptual / strategic
   - Result: "conceptual" (she's asking why, not how)

2. prereq_walker (BFS Neo4j PREREQ edges):
   - For topic_id "topic_physics_newtons_laws_5.2", walk back through PREREQs
   - Result: ["mass", "acceleration", "force_intuition", ...]

3. ResolutionPlanner (LLM call, Sonnet, structured output → ResolutionPlan):
   System prompt + user message including:
     - doubt_text: "I don't get why force equals mass times acceleration..."
     - classification: "conceptual"
     - chapter_context: hydrated topics + their our_understanding text
     - current_topic_id: "topic_..._5.2"
     - prior_doubts: []
     - prior_resolution_summary: None
     - board_snapshot: serialised
     - different_angle: False
   Forced tool call: create_resolution_plan
   Output: ResolutionPlan with 3 beats:
     - Beat 1: "Bridge to intuition" — point at the existing force-arrow,
               narrate: "You already know force is what makes things speed up..."
     - Beat 2: "Why mass specifically" — annotate with a mark_point on the object,
               narrate: "...heavier object means it speeds up less for the same push..."
     - Beat 3: "Confirm understanding" — focus on the F=ma equation in notebook,
               narrate: "...so F equals m times a falls out of this ratio."

4. DiagramFitMatcher (LLM call, Haiku, per (beat × candidate_diagram)):
   - For each beat: which precomputed diagram fits best?
   - Beat 1: target_diagram_id = "diagram_F_ma_intro" (the one already on screen)
   - Beat 2: target_diagram_id = "diagram_F_ma_intro" (same)
   - Beat 3: target_diagram_id = "diagram_F_ma_intro" (still the same)
   - All beats annotate the same diagram. Good fit.

5. Return ResolutionPlan
```

### Step 7.3 — publish "resolution_ready" + start delivery

```python
    # 6. Tell frontend the plan is ready (with summary of beats and diagram IDs)
    await _publish_doubt_signal(ctx, {
        "type": "resolution_ready",
        "beats": [{ "beat_index": i, "narration_summary": b.narration_text[:80] + "..." } for i, b in enumerate(plan.beats)],
        "matched_diagram_ids": ["diagram_F_ma_intro"],
    })

    # 7. Deliver the plan beat by beat
    await doubt_delivery.deliver_resolution(
        plan=plan,
        chapter_context=doubt_session.chapter_context,
        publish_data=lambda payload: _publish_doubt_signal(ctx, payload),
        on_first_frame=None,
    )
```

`DoubtDelivery.deliver_resolution` (`backend/src/feynman/livekit/doubt_delivery.py:145`):

```python
async def deliver_resolution(self, *, plan, chapter_context, publish_data, on_first_frame=None):
    for index, beat in enumerate(plan.beats):
        # Publish "doubt_beat_start" — frontend swaps visuals
        await publish_data({
            "type": "doubt_beat_start",
            "beat_index": index,
            "target_diagram_id": beat.target_diagram_id,
            "annotation_actions": [a.model_dump() for a in beat.annotation_actions],
        })
        # Wait 150ms for frontend to apply visuals
        await asyncio.sleep(0.15)
        # Speak the narration
        await self.speak(beat.narration_text)
```

### Step 7.4 — frontend applies beat visuals + plays beat audio

Back in the frontend, `useDataChannel("doubt_signal", ...)` callback fires for each message:

```tsx
useDataChannel("doubt_signal", useCallback(msg => {
    const data = JSON.parse(new TextDecoder().decode(msg.payload));
    switch (data.type) {
        case "thinking":
            clearStuckTimeout();
            setDoubtState("thinking");
            armStuckTimeout(75000, "Feynman is taking too long...");
            break;

        case "doubt_captured":
            // UI shows: "Heard: '<text>'"
            break;

        case "resolution_ready":
            clearStuckTimeout();
            armStuckTimeout(60000, "Feynman is processing...");
            break;

        case "doubt_beat_start":
            // Apply visuals: focused element, traces, mark points, pointers, margin notes
            applyDoubtBeat(data, chapter);
            break;

        case "satisfaction_prompt":
            setSatisfactionOptions(data.options);
            break;

        case "lecture_resume":
            setDoubtState("idle");
            clearDoubtAnnotations();
            play();
            break;
    }
}, [chapter, applyDoubtBeat, play]));
```

`applyDoubtBeat(beat, chapter)` mutates the SlideState:

```typescript
function applyDoubtBeat(beat, chapter) {
    const diagram = lookupDiagram(beat.target_diagram_id, chapter);
    setSlide(prev => ({
        ...prev,
        active: diagram,
        focusedElementId: null,    // reset
        annotations: [], traces: [], markPoints: [], pointers: [], marginNotes: [],
    }));
    // Then for each annotation_action in the beat:
    for (const action of beat.annotation_actions) {
        switch (action.type) {
            case "focus":      setSlide(prev => ({...prev, focusedElementId: action.target_element_id})); break;
            case "trace":      setSlide(prev => ({...prev, traces: [...prev.traces, action]})); break;
            case "mark_point": setSlide(prev => ({...prev, markPoints: [...prev.markPoints, action]})); break;
            case "point_at":   setSlide(prev => ({...prev, pointers: [...prev.pointers, action]})); break;
        }
    }
}
```

Right after `doubt_beat_start` arrives, `doubt_delivery.speak()` starts TTS:

```python
# doubt_delivery.py:95
async def speak(self, text, on_first_frame=None):
    async with self._lock:
        stream = self._tts.synthesize(text)
        first = True
        async for frame in stream:
            if first:
                if on_first_frame: on_first_frame()
                first = False
            await self._audio_source.capture_frame(frame)
```

`self._tts` is Cartesia. It streams audio frames into the `LocalAudioTrack` Aanya is subscribed to. She **hears the agent's voice**: "You already know that force is what makes things speed up..."

This loops for all 3 beats.

### Step 7.5 — satisfaction prompt

After the last beat:

```python
    # 8. Ask for satisfaction
    await _publish_doubt_signal(ctx, {
        "type": "satisfaction_prompt",
        "options": [
            {"key": "crystal_clear",    "label": "Crystal clear!",         "description": "Got it, ready to continue."},
            {"key": "counter_doubt",    "label": "I have another question", "description": "I want to ask a follow-up."},
            {"key": "somewhat_cleared", "label": "Somewhat — can you simplify?", "description": "Need a clearer version."},
            {"key": "start_over",       "label": "Try a different angle",   "description": "Same question, fresh approach."},
        ],
    })
```

The frontend's `setSatisfactionOptions(data.options)` triggers `<SatisfactionPrompt>` to render — a modal overlay with four buttons.

Aanya thinks for a moment, decides she gets it now, and taps "Crystal clear!"

### Step 7.6 — satisfaction choice → lecture resume

```tsx
async function onSatisfactionChoose(key: string) {
    setSatisfactionOptions(null);
    await room.localParticipant.publishData(
        new TextEncoder().encode(JSON.stringify({ type: "satisfaction_choice", option: key })),
        { topic: "doubt_signal", reliable: true },
    );
}
```

Worker receives it:

```python
async def _handle_satisfaction_choice(ctx, msg, doubt_session, doubt_delivery):
    option = msg["option"]
    if option == "crystal_clear":
        await _publish_doubt_signal(ctx, { "type": "lecture_resume" })
    elif option == "counter_doubt":
        # Capture another question, run resolve() again
        await _handle_doubt_intent(ctx, { ... }, doubt_session, doubt_delivery)
    elif option == "somewhat_cleared":
        await _publish_doubt_signal(ctx, { "type": "thinking", "stage": "simplifying" })
        # Run a clarification capture → re-resolve
        # ...
    elif option == "start_over":
        # Re-resolve with different_angle=True
        plan2 = await doubt_session.resolve(
            text=last_doubt_text,
            different_angle=True,
            prior_resolution_summary=summary,
            ...
        )
        await doubt_delivery.deliver_resolution(plan=plan2, ...)
```

For Aanya's case, `crystal_clear` → publish `lecture_resume`.

### Step 7.7 — frontend resumes playback

The frontend `useDataChannel` callback handles `lecture_resume`:

```tsx
case "lecture_resume":
    setDoubtState("idle");
    clearDoubtAnnotations();
    play();    // resumes useExtractionPlayback from rewound cursor
    break;
```

`play()`:

```typescript
function play() {
    if (isPlayingRef.current) return;
    isPlayingRef.current = true;
    playOne();
}
```

The playback loop restarts. The slide goes back to its pre-doubt state (since the cursor was rewound by 1, the first event re-played is the same `show_diagram` or `audio` that was interrupted). Audio resumes mid-sentence (technically slightly before — the rewind means the agent will repeat the last 4500ms of audio, which is intentional — picks up the context).

---

## Step 8 — the lesson continues

Aanya watches the rest of the chapter. Cursor advances through `chapter.events` one event at a time. Eventually `cursor === chapter.events.length` and `playOne()` returns. The lesson is over.

At this point Aanya could close the tab, or click another chapter. If she closes the tab:
- LiveKit detects the participant disconnect.
- The worker's `entrypoint()` returns (the `asyncio.Event().wait()` is interrupted by job termination).
- `doubt_delivery.stop()` runs in the `finally`, unpublishing the audio track.
- The room is empty; LiveKit eventually deletes it.

If she clicks `POST /api/sessions/{id}/end` (not exposed in the UI today, but conceptually):
- Backend reads Redis to capture the final `teaching_state`.
- Writes `status=ended, ended_at=now()` to Postgres.
- Deletes the Redis key.

---

## Cross-references — every file involved

Roughly in execution order:

| Step | File | Why |
|---|---|---|
| 1 | `frontend/index.html`, `src/main.tsx`, `src/App.tsx` | Bootstrap. |
| 1 | `frontend/src/screens/LectureHomeScreen.tsx` | Chapter picker. |
| 1 | `data_pre_compute_v2/tools/preview_server.py` | `/lecture-api/chapters`. |
| 2 | `frontend/src/hooks/useSession.ts` | startSession. |
| 2 | `frontend/src/lib/api.ts::createSession` | Calls `POST /api/sessions`. |
| 2 | `backend/src/feynman/api/sessions.py:create_session` | The handler. |
| 2 | `backend/src/feynman/session/manager.py:create_session` | DB + Redis write. |
| 2 | `backend/src/feynman/api/sessions.py:_create_livekit_room` | LK room with metadata. |
| 2 | `backend/src/feynman/api/sessions.py:_create_livekit_token` | JWT mint. |
| 3 | `frontend/src/livekit/RoomProvider.tsx` | LiveKit connection. |
| 4 | `backend/src/feynman/livekit/worker.py:entrypoint` | Job entry. |
| 4 | `backend/src/feynman/livekit/worker.py:_parse_room_metadata` | Routes by mode. |
| 4 | `backend/src/feynman/livekit/worker.py:_run_lecture_mode` | Lecture mode setup. |
| 4 | `backend/src/feynman/agent/doubt_resolution/lecture_session.py:LectureDoubtSession.from_chapter_id` | Loads chapter from Neo4j. |
| 4 | `backend/src/feynman/livekit/doubt_delivery.py:DoubtDelivery.start` | Publishes silent audio track. |
| 4 | `backend/src/feynman/livekit/pipeline.py:create_tts` | Cartesia setup. |
| 5 | `frontend/src/screens/ClassroomScreen.tsx` | Mode branch. |
| 5 | `frontend/src/screens/LectureViewer.tsx` | Manifest playback host. |
| 5 | `data_pre_compute_v2/tools/preview_server.py:get_chapter` | Manifest fetch. |
| 5 | `frontend/src/hooks/useExtractionPlayback.ts` | Event-walker. |
| 5 | `frontend/src/engine/whiteboard/split/SplitBoard.tsx` | Two-panel rendering. |
| 6 | `frontend/src/components/AskFeynmanButton.tsx` | The button. |
| 6 | `frontend/src/screens/LectureViewer.tsx:onAskFeynman` | Publish `doubt_intent`. |
| 7 | `backend/src/feynman/livekit/worker.py:_on_data_received` | Data channel handler. |
| 7 | `backend/src/feynman/livekit/worker.py:_handle_doubt_intent` | Doubt orchestration. |
| 7 | `backend/src/feynman/agent/doubt_resolution/doubt_classifier.py` | LLM classification. |
| 7 | `backend/src/feynman/agent/doubt_resolution/prereq_walker.py` | BFS Neo4j. |
| 7 | `backend/src/feynman/agent/doubt_resolution/resolution_planner.py:plan_resolution` | Sonnet structured-output call. |
| 7 | `backend/src/feynman/agent/doubt_resolution/diagram_fit_matcher.py` | Haiku per-beat fit check. |
| 7 | `backend/src/feynman/agent/doubt_resolution/models.py` | ResolutionPlan, ResolutionBeat, AnnotationAction. |
| 7 | `backend/src/feynman/livekit/doubt_delivery.py:deliver_resolution` | Beat loop. |
| 7 | `backend/src/feynman/livekit/doubt_delivery.py:speak` | TTS push to audio track. |
| 7 | `frontend/src/screens/LectureViewer.tsx:onDoubtMessage` | Doubt signal handler. |
| 7 | `frontend/src/hooks/useExtractionPlayback.ts:applyDoubtBeat` | Beat → slide annotations. |
| 7 | `frontend/src/components/SatisfactionPrompt.tsx` | Modal UI. |
| 8 | `frontend/src/hooks/useExtractionPlayback.ts:play` | Resume. |

---

## Variant — Mode A live agent trace

If Aanya had picked `#/dev/live-teacher` instead and entered the topic "Newton's Laws" in the WaitingScreen, Step 1-3 would be identical except the session has `topic="Newton's Laws"` and no `lecture_chapter_id`. Step 4 would branch differently:

```python
# worker.py:847+
topic = meta.get("topic", "")     # "Newton's Laws"
session_id = uuid4()
state_machine = TeachingStateMachine(session_id=session_id)
teaching_ctx = TeachingContext(session_id=session_id, state_machine=state_machine)
teaching_ctx.board_verifier = BoardVerifier(publish_fn=..., audit=...)
ctx.room.on("data_received", _on_data_received)

agent = FeynmanAgent(teaching_ctx)
session = AgentSession(stt=create_stt(), llm=create_llm(), tts=create_tts(),
                       vad=create_vad(), userdata=teaching_ctx,
                       use_tts_aligned_transcript=True, max_tool_steps=30)
await session.start(agent=agent, room=ctx.room)
```

In `FeynmanAgent.on_enter`:

1. `curriculum = await load_curriculum(subject=Subject.PHYSICS, topic="Newton's Laws", neo4j_session=...)` — pulls chapter + topic data from Neo4j.
2. `lesson_plan = lesson_plan_from_curriculum(curriculum)` — flattens into `LessonPlan`.
3. Stores `teaching_ctx.lesson_plan = lesson_plan`, `teaching_ctx.curriculum = curriculum`.
4. `anticipation.warm_for_concepts(lesson_plan.concepts[:3])` — pre-fires `design_bridge.generate_design_diagram(...)` for the first three expected diagrams in the background.
5. `asyncio.create_task(plan_concept(0, curriculum, lesson_plan, api_key=settings.anthropic_api_key))` and the same for concept 1 — fires `feynman_teaching_kernel.plan_concept` in the background. The `ConceptTeachingPlan` lands in `teaching_ctx.concept_plans[0]` and `[1]` shortly.
6. Build the system prompt via `build_teaching_prompt(teaching_ctx)`:
   - `TEACHING_SYSTEM_PROMPT` from `agent/prompts.py`
   - `format_plan_for_prompt(teaching_ctx.concept_plans[0])` from the kernel
   - Empty board snapshot (nothing on board yet)
   - Empty notebook reconstruction
7. `await agent.update_instructions(prompt)`.

Now `session.start()` runs:
- STT captures Aanya's first words. ("Hi, I want to learn about Newton's laws.")
- LLM produces a greeting and tool calls.
- First tool call is probably `set_lesson_topic("Newton's First Law")` or `advance_concept()`.
- Then `draw_design_diagram("an object at rest with no forces")` → cache hit (anticipation pre-fired this) → publish `DrawDesignDiagramInstruction` over topic="visuals".
- TTS speaks "Imagine a ball at rest..." Inline `<focus target="ball"/>` tags get stripped by the action tag parser and dispatched as visuals with `sync_mode=AFTER_NEXT_SENTENCE`.
- Frontend's `useVisualChannel` receives, parses, applies to board store.
- `WhiteboardScene` (or `SplitBoard` if `splitBoardEnabled`) re-renders.

When Aanya interrupts with a doubt:

- STT picks it up.
- LLM decides to invoke `start_doubt_branch(related_concept="Newton's First Law")`.
- Tool body:
  - `state_machine.push_branch()` → new BranchContext with state HANDLING_DOUBT.
  - `board_manager.push_board(label="Doubt: ...", branch_id=...)` → fresh board, mirror push.
  - `doubt_orchestrator.on_push(...)` → snapshot parent state into ReturnAnchor + watchdog timer.
  - Calls `await plan_doubt(doubt_description, parent_concept, board_summary, ..., api_key=...)`.
  - Stores returned `ConceptTeachingPlan` (with `concept_index=-1`) in `teaching_ctx.doubt_plan`.
- Next LLM turn includes the doubt plan via `format_plan_for_prompt(teaching_ctx.doubt_plan)`.
- Agent teaches the doubt on the new board. Tools that would normally `advance_concept`, `start_doubt_branch`, or `switch_board` are blocked by `@state_constrained`.
- DoubtOrchestrator ticks `resolution_checklist` items on each tool call and each spoken word matching a keyword.
- Agent eventually calls `resolve_doubt()`:
  - `is_resolution_allowed()` checks the checklist — if not all done, the tool raises `ToolConstraintError` (surfaced to LLM, which can call `mark_doubt_step_complete` then retry).
  - On allowed: `state_machine.pop_branch()`, `board_manager.pop_board()`, `doubt_orchestrator.on_pop()` restores active highlights / annotations / notebook cursor from the ReturnAnchor.
- State machine is back on main branch. The next turn resumes the original concept.

This is the **interactive mode** trace. It's substantially more LLM work than the lecture-playback mode (every visual generated live, every word LLM-driven) but produces fundamentally different teaching quality — adaptive, in-the-moment.

---

## Critical timings (rough orders of magnitude)

| Action | Latency target | Actual today |
|---|---|---|
| HTTP `POST /api/sessions` | <100ms | ~30-80ms |
| WebRTC connection | <1s | ~500ms-1s |
| Worker `entrypoint` to "ready" | <1s | ~200-500ms |
| First audio event playback | <2s after click | ~500ms-1.5s |
| Live diagram generation (cache miss) | <800ms | **5-15s** — the magic-moment killer; only mitigated by anticipation |
| Live diagram generation (cache hit) | <100ms | ~20-50ms |
| Action tag → visual | <300ms | ~50-100ms via `after_next_sentence` queue |
| STT capture (utterance) | <12s budget | typical 3-8s |
| Doubt classification (Haiku) | <500ms | ~200-400ms |
| Resolution planning (Sonnet) | <3s | ~1.5-2.5s |
| Diagram fit matching (Haiku × N) | <500ms | ~150-350ms |
| Doubt beat audio start | <1s after TTS sentence | ~200-400ms |

These guide where to optimize. The biggest wins are:

1. **Push more diagrams into the precompute** so live cache misses are rarer.
2. **Improve anticipation accuracy** to widen the cache-hit window.
3. **Optimize the resolution planner prompt** to shave LLM latency.

---

## Reading order

If you want to re-trace this on your own:

1. Browser: `frontend/src/App.tsx → src/screens/LectureHomeScreen.tsx`.
2. HTTP call: `frontend/src/lib/api.ts → backend/src/feynman/api/sessions.py:79`.
3. WebRTC: `frontend/src/livekit/RoomProvider.tsx`.
4. Worker dispatch: `backend/src/feynman/livekit/worker.py:819`.
5. Lecture mode: `backend/src/feynman/livekit/worker.py:535-776`.
6. Frontend playback: `frontend/src/screens/LectureViewer.tsx` + `frontend/src/hooks/useExtractionPlayback.ts`.
7. Doubt flow: `backend/src/feynman/agent/doubt_resolution/*` + `backend/src/feynman/livekit/doubt_delivery.py`.
