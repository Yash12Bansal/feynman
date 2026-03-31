# Beat Orchestration System: Enforced Voice-Visual Choreography

## The Gap

We've added timing infrastructure (tools respect `sync_mode`, tools have `timing` parameter) and prompt guidance (beat patterns in the system prompt). But **the LLM has no enforced beat structure** — it still generates free-form speech + ad-hoc tool calls. The "beats" are just prompt suggestions it can ignore.

The prompt says "teach in beats" but nothing prevents the LLM from:
- Showing three visuals without speaking about any of them
- Speaking for 60 seconds without showing anything
- Calling tools in random order with no rhythm
- Ignoring timing parameters entirely

**We need structural enforcement, not just suggestions.**

---

## The Solution: Two-Mode Teaching System

Planned concept teaching uses pre-generated beat sequences executed by an orchestrator. Doubt handling uses the existing conversational pipeline. Mode switching happens on student interruption.

```
BEAT MODE (planned teaching)              CONVERSATIONAL MODE (doubts)
-----------------------------              ----------------------------

 ConceptNode                               Student speaks
     |                                         |
     v                                         v
 generate_beat_sequence()                  Normal LiveKit pipeline
 (Anthropic SDK structured output)         STT -> LLM (with tools) -> TTS
     |                                         |
     v                                         v
 BeatSequence [beat1, beat2, ...]         LLM calls tools as needed
     |                                    (existing behavior, unchanged)
     v
 BeatOrchestrator.run_sequence()
     |
     +-- VISUAL_FIRST beat:
     |   publish visual -> generate_reply -> wait_for_playout
     |
     +-- SPEECH_FIRST beat:
     |   generate_reply -> wait_for_playout -> publish visual
     |
     +-- SIMULTANEOUS beat (term_sync):
     |   publish visual (term_sync) -> generate_reply -> SyncManager matches
     |
     +-- PAUSE beat:
         wait_for_playout -> asyncio.sleep

 Student interrupts? --> Switch to CONVERSATIONAL MODE
 Doubt resolved?     --> Resume BEAT MODE from stored position
```

---

## Key Design Decisions

### 1. `speech_intent` not `speech_text`

`session.generate_reply(instructions=...)` is the only way to make the agent speak programmatically in LiveKit Agents SDK. It goes through LLM -> TTS. **The LLM will paraphrase.**

So beats carry speech INTENT, not exact text:
- Intent: "Explain that F=ma means force equals mass times acceleration. Mention the word 'force' early in your explanation."
- LLM might say: "So the force acting on an object is just its mass multiplied by how fast it speeds up."

This is fine because:
- The SyncManager's fuzzy word matching handles equation term reveals regardless of exact phrasing
- The visual timing is controlled by the orchestrator AROUND the speech, not WITHIN it
- Natural-sounding paraphrasing is actually better than robotic exact text

### 2. Visual instructions embedded directly

Beats contain fully-formed `_BaseInstruction` Pydantic objects — the same types used by our existing tools. The orchestrator publishes them directly to the LiveKit data channel, bypassing tool functions entirely.

This means during beat execution:
- No tool calls from the LLM
- No `_publish_visual` wrapper needed (orchestrator publishes directly)
- Full timing control in the orchestrator

### 3. Tool stripping during beats

During beat execution, visual tools are REMOVED from the agent. Only state tools remain (`start_doubt_branch`, `resolve_doubt`). This prevents the LLM from making its own visual decisions during `generate_reply` speech.

After beats complete or on interrupt, full tools are restored.

### 4. Per-concept generation

Generate beats for one concept at a time, not the whole lesson. Why:
- Keeps latency manageable (~2-4s per concept with Sonnet)
- Allows adapting later concepts based on how teaching went
- Can generate next concept's beats WHILE current one is teaching (pipeline overlap)

### 5. Structured output pattern

Beat generation uses the exact same Anthropic SDK pattern as `lesson_plan.py`:
```python
response = await client.messages.create(
    model="claude-sonnet-4-20250514",
    system=BEAT_GENERATION_PROMPT,
    messages=[{"role": "user", "content": concept_details}],
    tools=[{
        "name": "create_beat_sequence",
        "input_schema": BeatSequence.model_json_schema(),
    }],
    tool_choice={"type": "tool", "name": "create_beat_sequence"},
)
```

This gives us validated JSON output with Pydantic models. Proven pattern.

---

## Data Models

### File: `backend/src/feynman/agent/beats.py`

```python
class BeatTiming(StrEnum):
    VISUAL_FIRST = "visual_first"    # show visual, then speak
    SPEECH_FIRST = "speech_first"    # speak, then show visual
    SIMULTANEOUS = "simultaneous"    # show visual + speak (term_sync/highlights)
    SPEECH_ONLY = "speech_only"      # no visual, just speech
    VISUAL_ONLY = "visual_only"      # no speech (e.g., clear_board)
    PAUSE = "pause"                  # silence for absorption

class TeachingBeat(BaseModel):
    speech_intent: str | None = None       # instructions for generate_reply
    visual_type: str | None = None         # "show_equation", "draw_scene", etc.
    visual_payload: dict | None = None     # serialized instruction fields
    timing: BeatTiming = BeatTiming.VISUAL_FIRST
    pause_seconds: float = 0.0             # pause after beat completes
    zone: str = ""                         # board zone for visual

class BeatSequence(BaseModel):
    concept_title: str
    beats: list[TeachingBeat]
```

### Example Beat Sequence (Photosynthesis)

```json
{
  "concept_title": "Photosynthesis Equation",
  "beats": [
    {
      "speech_intent": "Introduce photosynthesis as how plants make food from sunlight. Keep it to one sentence.",
      "timing": "speech_only"
    },
    {
      "speech_intent": "Say 'Let me draw out what happens inside a leaf' as the diagram appears.",
      "visual_type": "draw_scene",
      "visual_payload": {
        "scene_type": "biology",
        "elements": [...plant cell components...],
        "title": "Inside a Plant Cell"
      },
      "timing": "visual_first"
    },
    {
      "speech_intent": "Point out the chloroplast as the green structure where food is made. Use the word 'green' early.",
      "visual_type": "highlight",
      "visual_payload": {
        "target_id": "scene-1",
        "sub_element_ids": ["chloroplast"],
        "style": "glow",
        "color": "#4ade80"
      },
      "timing": "simultaneous"
    },
    {
      "timing": "pause",
      "pause_seconds": 2.0
    },
    {
      "speech_intent": "Now introduce the chemical equation. Say 'Here is the equation' then read each term.",
      "visual_type": "show_equation",
      "visual_payload": {
        "latex": "\\htmlId{co2}{6CO_2} + \\htmlId{h2o}{6H_2O} \\rightarrow \\htmlId{glucose}{C_6H_{12}O_6} + \\htmlId{o2}{6O_2}",
        "animation": "term_by_term",
        "term_hints": [
          {"term_id": "co2", "trigger_words": ["carbon", "dioxide", "CO2"]},
          {"term_id": "h2o", "trigger_words": ["water", "H2O"]},
          {"term_id": "glucose", "trigger_words": ["glucose", "sugar", "food"]},
          {"term_id": "o2", "trigger_words": ["oxygen", "O2"]}
        ]
      },
      "timing": "simultaneous"
    },
    {
      "speech_intent": "Ask the class: what does the plant take in from outside? Wait for an answer.",
      "timing": "speech_only"
    }
  ]
}
```

---

## Beat Orchestrator

### File: `backend/src/feynman/agent/beat_orchestrator.py`

```python
class BeatOrchestrator:
    def __init__(self, session: AgentSession, teaching_ctx: TeachingContext):
        self._session = session
        self._ctx = teaching_ctx
        self._interrupted = False
        self._current_beat_index = 0
        self._sequence: BeatSequence | None = None

    async def run_sequence(self, sequence: BeatSequence) -> None:
        """Execute beats sequentially. Can be interrupted."""
        self._sequence = sequence
        self._interrupted = False

        for i in range(self._current_beat_index, len(sequence.beats)):
            if self._interrupted:
                self._current_beat_index = i
                return
            await self._execute_beat(sequence.beats[i])

        self._current_beat_index = 0  # sequence complete

    async def _execute_beat(self, beat: TeachingBeat) -> None:
        visual = self._build_visual(beat) if beat.visual_type else None

        match beat.timing:
            case BeatTiming.VISUAL_FIRST:
                if visual:
                    await self._publish_visual(visual)
                if beat.speech_intent:
                    await self._speak(beat.speech_intent)

            case BeatTiming.SPEECH_FIRST:
                if beat.speech_intent:
                    await self._speak(beat.speech_intent)
                if visual:
                    await self._publish_visual(visual)

            case BeatTiming.SIMULTANEOUS:
                if visual:
                    await self._publish_visual(visual)  # fires immediately
                if beat.speech_intent:
                    await self._speak(beat.speech_intent)  # SyncManager handles matching

            case BeatTiming.SPEECH_ONLY:
                if beat.speech_intent:
                    await self._speak(beat.speech_intent)

            case BeatTiming.VISUAL_ONLY:
                if visual:
                    await self._publish_visual(visual)

            case BeatTiming.PAUSE:
                await self._session.wait_for_playout()
                await asyncio.sleep(beat.pause_seconds)

        if beat.pause_seconds > 0 and beat.timing != BeatTiming.PAUSE:
            await asyncio.sleep(beat.pause_seconds)

    async def _speak(self, intent: str) -> None:
        """Use generate_reply to make the agent speak."""
        handle = self._session.generate_reply(
            instructions=intent,
            tool_choice="none",  # prevent tool calls during speech
            allow_interruptions=True,
        )
        await handle.wait_for_playout()

    async def _publish_visual(self, instruction) -> None:
        """Publish visual instruction directly to data channel."""
        # Same as _publish_visual in tools.py but without RunContext
        data = instruction.model_dump_json().encode()
        room = self._session.room
        await room.local_participant.publish_data(data, reliable=True, topic="visuals")

    def interrupt(self) -> None:
        """Called when student speaks during beats."""
        self._interrupted = True

    @property
    def has_remaining(self) -> bool:
        return (self._sequence is not None
                and self._current_beat_index < len(self._sequence.beats))

    async def resume(self) -> None:
        """Resume from stored position after doubt resolution."""
        if self.has_remaining:
            await self.run_sequence(self._sequence)
```

---

## Mode Switching: Beat <-> Conversational

### TeachingMode enum (added to teaching_context.py)

```python
class TeachingMode(StrEnum):
    BEAT = "beat"                  # orchestrator executing planned beats
    CONVERSATIONAL = "conversational"  # normal pipeline (doubts, Q&A)
```

### Flow

```
1. Lesson starts
   -> Generate beats for concept 1
   -> mode = BEAT
   -> orchestrator.run_sequence(beats)

2. Student speaks during beat execution
   -> STT detects user speech
   -> orchestrator.interrupt()
   -> mode = CONVERSATIONAL
   -> Restore all tools to the agent
   -> Normal pipeline handles student question

3. LLM calls start_doubt_branch()
   -> Doubt branch pushed
   -> LLM teaches conversationally (with full tools)

4. LLM calls resolve_doubt()
   -> Doubt branch popped
   -> Check: orchestrator.has_remaining?
   -> If yes: mode = BEAT, strip tools, orchestrator.resume()
   -> If no: mode = CONVERSATIONAL (concept done)

5. LLM calls advance_concept() (or orchestrator finishes all beats)
   -> Generate beats for concept 2 (async)
   -> mode = BEAT
   -> orchestrator.run_sequence(new_beats)
```

### Interrupt Detection

In `worker.py`, listen for user state changes:

```python
@ctx.room.on("user_state_changed")
def on_user_state(state):
    if state == "speaking" and teaching_ctx.mode == TeachingMode.BEAT:
        orchestrator.interrupt()
        teaching_ctx.mode = TeachingMode.CONVERSATIONAL
        agent.update_tools(ALL_TOOLS)  # restore full tool set
```

---

## Beat Generation Prompt

The prompt for generating beats should include:
1. The concept to teach (from ConceptNode: title, description, key_points, visual_suggestions)
2. Available visual instruction types and their schemas
3. Beat structure rules (one visual per beat, timing semantics)
4. Current board state (what's already visible)
5. Examples of good beat sequences

Key constraints in the prompt:
- 4-10 beats per concept
- Each beat has speech OR visual OR both (never neither)
- Visual payloads must be valid instruction JSON
- Speech intent should be 1-3 sentences of guidance, NOT the exact script
- Start with a verbal intro beat, end with a comprehension check beat
- Use VISUAL_FIRST for diagrams, SIMULTANEOUS for equations with term_sync

---

## What This Gives Us vs. The Prompt-Only Approach

| Aspect | Prompt-Only (current) | Beat Orchestrator (proposed) |
|--------|----------------------|------------------------------|
| Beat structure | Suggested, not enforced | Enforced by orchestrator |
| Visual timing | Tool decides (sync_mode param) | Orchestrator controls precisely |
| Speech-visual order | LLM decides | Beat.timing determines |
| Tool calls during teaching | LLM calls freely | Tools stripped, orchestrator publishes |
| Doubt handling | Always conversational | Beat mode pauses, switches to conversational |
| Reproducibility | LLM may teach differently each time | Same beat sequence = consistent structure |
| Adaptability | Full (LLM improvises) | Per-concept (regenerate if needed) |

---

## Prototype Scope (Phase 1)

Build the minimum for a demo:

1. **`TeachingBeat` + `BeatSequence` models** in `beats.py`
2. **`generate_beat_sequence()`** with Anthropic structured output
3. **`BeatOrchestrator`** with three timing modes: VISUAL_FIRST, SPEECH_ONLY, PAUSE
4. **Integration** in `worker.py`: generate beats on enter, run orchestrator
5. **Interrupt detection**: pause on student speech, switch to conversational

Skip for Phase 1:
- SIMULTANEOUS/term_sync timing (SyncManager already handles this)
- Adaptive beat modification
- Beat metrics/analytics
- Automatic resume after doubt (manual for now)

### Phase 2 additions:
- SIMULTANEOUS with term_sync
- Automatic resume after `resolve_doubt()`
- Generate next concept's beats during current concept (overlap)
- Beat validation against visual instruction schemas

### Phase 3 additions:
- Adaptive beats (skip if student already understands)
- Beat modification mid-sequence
- Word-level timing using aligned transcripts
- Effectiveness metrics

---

## Files to Create
1. `backend/src/feynman/agent/beats.py` — Models + generation
2. `backend/src/feynman/agent/beat_orchestrator.py` — Execution engine
3. `backend/tests/unit/test_beats.py` — Model + generation tests
4. `backend/tests/unit/test_beat_orchestrator.py` — Orchestrator tests

## Files to Modify
5. `backend/src/feynman/agent/teaching_context.py` — Add `TeachingMode`, orchestrator ref
6. `backend/src/feynman/livekit/worker.py` — Wire orchestrator, interrupt detection
7. `backend/src/feynman/agent/tools.py` — `advance_concept` and `resolve_doubt` trigger beats
8. `backend/src/feynman/agent/prompts.py` — Beat-mode speech constraint prompt

---

## Decision Points for Yash

1. **Phase 1 scope: how many timing modes?** VISUAL_FIRST + SPEECH_ONLY + PAUSE is minimum for a demo. Adding SIMULTANEOUS requires SyncManager integration (already exists, just needs wiring).

2. **Beat generation model: Sonnet or Haiku?** Sonnet for quality, Haiku for speed (~500ms vs ~2s). Sonnet recommended for prototype — quality matters more than 1.5s latency during concept transitions.

3. **`generate_reply` reliability: how constrained?** The LLM will paraphrase speech_intent. Accept this or try harder to constrain it? Recommendation: accept it. Natural paraphrasing sounds better than forced exact text.

4. **When to generate beats?** During lesson plan generation (parallel) or after lesson plan is ready (sequential)? Sequential is simpler. For the first concept, generate during the greeting (student hears greeting while beats are generated in background).

5. **How to handle beat generation failure?** If Anthropic call fails or returns invalid beats: fall back to CONVERSATIONAL mode (existing behavior). The beat system is an enhancement, not a dependency. System works fine without it — just less choreographed.
