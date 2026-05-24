# Feynman: Comprehensive System Design (HLD + LLD)

**Version**: 2026-05-15 (post Phase 5a-3 ship — `87e6957`)
**Audience**: Yash + Claude (co-founders); future engineers
**Purpose**: One document that captures everything Feynman IS, everything it WILL BE, and brutally how far apart those two things are.

---

## 0. How to Read This

This doc is in three concentric circles. Read whichever depth you need:

- **Outer ring (sections 1–3)**: vision + product experience + HLD. ~15 minutes. What we're building and why.
- **Middle ring (sections 4–11)**: the seven subsystems + flow of control. ~45 minutes. The LLD — file paths, class names, the actual machinery.
- **Inner ring (sections 12–16 + appendices)**: principles + open problems + future. ~30 minutes. The reality check + roadmap.

The doc is opinionated. Where things are unsolved we say so; where decisions are deliberate we say why; where parts are aspirational we mark them clearly.

---

## 1. Vision — Real-Time Autonomous Personalized Teaching Agent

Feynman is one sentence: **a real-time autonomous personalized teaching agent for school-age students, voice-driven with rich live visuals**. Every word matters.

### 1.1 Real-time
- Voice round-trips under 2s end-to-end.
- Visuals appear within the latency budget tied to the student's listening attention: **<300ms mid-sentence** for inline pointing, **<800ms at sentence boundaries** for new diagrams, **5–10s acceptable** only when the agent vocally bridges the gap ("let me sketch this for you...").
- Confusion is sensed and acted on in real time — the agent doesn't wait for "I don't get it." Phase 5a perception loop (just shipped) is the first step; VL-JEPA in Phase 5b is the future end-state at ~142ms.
- Interruptions are first-class. LiveKit Agents + Silero VAD handle barge-in. The agent yields, listens, branches.

### 1.2 Autonomous
- The agent **leads the lesson**. It is not a chatbot waiting for prompts; it is a teacher with a plan.
- It decides what to teach next, when to advance, when to slow down, when to spawn a doubt branch, when to revisit fundamentals, when to declare "we'll come back to this next time."
- It SEES the board (Phase 5a perception loop) and recovers from its own mistakes via the `[PERCEPTION_FEEDBACK]` channel.
- It anticipates doubts before they're asked (anticipation engine pre-generates the 4 likeliest doubts for each concept).
- Pedagogical backbone: **Feynman Technique** — explain simply, find gaps, revisit fundamentals, simplify with new analogies. Plus Mayer's cognitive-load principles (Redundancy, Temporal Contiguity, Spatial Contiguity, Coherence, Modality) encoded into the visual+voice protocol.

### 1.3 Personalized
- Per-student knowledge graph: concept mastery map + learning pattern profile + session history (three layers, see §10).
- Adapts pace, depth, analogies, examples. Remembers what was hard last time.
- Sparse-data tolerant: most students rarely ask doubts; the graph stays sparse, and the system must teach beautifully WITH sparse data. Knowledge graph is **enhancement, not dependency**.
- Today: per-student persistence is designed but not implemented. v0 ships without it; magic moment is the precondition.

### 1.4 Teaching agent
- Voice + rich visual aids (diagrams, equations, animations, hand-drawn-feeling strokes, KaTeX overlays). No chat UI. The "board" is the first-class teaching tool — drawn on, modified, erased, referenced.
- Lesson modeled as a **tree/graph**: main branch is a linear sequence of concepts; doubt branches spawn and merge back. Nested doubts supported. Comprehension gates can spawn agent-initiated re-approach branches.
- Stack-based async navigation. Always knows where it is and where to return.

### 1.5 The market wedge

**Three irreducible wedges** the consumer thesis bets on (`docs/strategy/01-consumer-product-thesis.md`):

1. **Real-time voice+visual with branching** — ChatGPT can't do this (text-only or voice-only, no live visuals, no branching). Khanmigo can't (no real visual board). Tutors can but cost ₹8K/week and are unavailable at 8 PM Wednesday.
2. **IGCSE 0580 specificity** — syllabus, marking scheme, past papers. ChatGPT is general; we are specialized. This is moat depth.
3. **Continuity via per-student knowledge graph** — remembers prior struggles, adapts. ChatGPT context resets; we don't.

**What Feynman is NOT** (deliberate cuts):
- Not a chatbot (live-teaching, voice-first).
- Not a video lecture (interactive, branches on doubt).
- Not a marketplace (no human-tutor matchmaking).
- Not classroom-mode in v0 (multi-student, voice ID, teacher dashboard — all PARKED under consumer pivot; see §16.1).
- Not "ChatGPT with diagrams" — the moat is real-time branching + IGCSE specificity + continuity.

### 1.6 Persona — Aanya

- 13-year-old Year 9 IGCSE student in Indian metro.
- Family pays ₹6L/year for school + ₹8K/week for math tutor. Tutor isn't enough — there's a recurring 8 PM "I don't get this" gap.
- We fill that gap. ₹4000/mo single-subject; ₹6–8K all-subjects; 30% off annual.
- v0 subject: IGCSE Math 0580 (Year 9–10). v1: Physics 0625 → Chem 0620 → Bio 0610. v2: IB MYP/DP. v2+: UAE / Singapore / Malaysia.

### 1.7 What "magic" means

From `MEMORY.md`: every interaction must feel like **somebody really cared a lot**. Not "AI generated good output." Care. Three concrete tests:

- The **Aanya demo** (`docs/design/12-aanya-demo-v0.md`) — 7-minute right-triangle lesson must make 3+ internal viewers say "whoa" unprompted before we touch mom-validation.
- The **first 90 seconds** of any session decide bounce vs delight.
- **Quality bar**: parent should feel ₹4000/mo is underpriced.

---

## 2. The Aanya Story (Product Experience)

8:14 PM, Wednesday. Aanya stares at IGCSE 0580 Paper 4 Q7: a 4m ladder leaning against a wall, slipping. She doesn't know where to start.

She opens the app. One button: **start session**. She taps. 1.2s later, a warm voice: *"Hi Aanya. What are you stuck on tonight?"* The classroom screen shows a fresh notebook and an empty slide. She reads the problem aloud.

The slide animates a ladder against a wall — drawn left-to-right with a hand-drawn stroke-reveal, cached and rendering in 600ms (anticipation engine, see §7.5). The agent narrates: *"Okay — this is a right-triangle problem. Let me show you why."* As the word "right-triangle" hits the speakers, a `<highlight target="right_angle"/>` tag inline in the narration triggers a soft pulse at the corner of the wall and floor.

Aanya: *"But how do I know what the angle is?"* — mid-sentence, the agent's words abort cleanly (Silero VAD + interruption). The state machine **pushes a doubt branch**. The board pushes too — a new slate. The orchestrator (§5) snapshots the parent state: which beat we were on, which highlights were active, the return cue. Aanya is suddenly in a new conversation tree branch and Feynman knows it.

The agent fires `draw_design_diagram(prompt="...")` for one of four pre-generated doubt diagrams. Cache hit (anticipation engine warmed this concept's likely doubts). 700ms later: a similar-triangle invariance figure on the board. The agent teaches: *"Look — these two triangles share the same angle..."* Aanya gets it. She says *"oh, so I just measure the angle?"* — that's a checklist tick (the doubt's resolution checklist has an "Explains similar-triangle invariance" item which auto-completes via voice keyword match in `DoubtOrchestrator.on_voice_emitted`, see §5.3).

Watchdog (§5.4): if Aanya had wandered for 60 seconds, soft nudge. 120 seconds, force-resolve. She doesn't wander. After 35 seconds, the orchestrator's `is_resolution_allowed()` returns True. The agent calls `resolve_doubt()`. The board POPs. The orchestrator restores: active_highlights re-fire on the parent slide, the verbatim return cue plays — *"Okay, back to the ladder."*

Aanya solves it. She says the answer. The agent confirms — kid owns the win.

Session ends. Audit summary (§12): 1 concept taught, 1 doubt resolved, 3 vision verifications fired, 0 drift detected, total cost ~$0.08. **Aanya tells her mom Feynman is "actually good."** That's the magic moment hypothesis.

This narrative drives every architectural decision below.

---

## 3. High-Level Architecture (HLD)

### 3.1 Process topology — master diagram

```text
╔════════════════════════════════════════════════════════════════════════════════════════════╗
║                              STUDENT'S BROWSER (single device)                              ║
║  React 19 · TypeScript · Vite · Tailwind · GSAP · KaTeX · Rough.js · Chart.js               ║
║  ──────────────────────────────────────────────────────────────────────────────────────── ║
║  Frame budget (student-perceived):                                                          ║
║   • Inline pointing  (mid-sentence)      :  ≤300ms after tag emission                       ║
║   • Diagram swap     (sentence-boundary) :  ≤800ms after instruction                        ║
║   • Cache-miss draw  (with voice-bridge) :  5–10s acceptable IF agent vocally bridges       ║
║  ──────────────────────────────────────────────────────────────────────────────────────── ║
║  Modules:                                                                                   ║
║   /screens/ClassroomScreen.tsx              · main teaching UI                              ║
║   /engine: Canvas, InstructionSwitch, SyncManager  · visuals dispatch + render              ║
║   /engine/whiteboard/BoardCapture.tsx       · PNG capture for vision verify (~150ms)        ║
║   /engine/whiteboard/content/DesignDiagramContent.tsx · SVG + KaTeX renderer                ║
║   /livekit: RoomProvider, useVisualChannel, useAgentTranscription                           ║
╚══════════╤═══════════════════════════════════════════════════╤════════════════════════════╝
           │ WebRTC audio  (~50–80ms RTT India)                │ Data channel
           │ Silero VAD on-device (browser end)                │  topic="visuals"     JSON
           │ TTS audio frames in · mic audio out               │  topic="board_capture" PNG
           │                                                   │  topic="bounds"        bbox
           ▼                                                   │
┌─────────────────────────────────────┐                        │
│  LiveKit cloud / self-host           │                        │
│  Room mgmt · JWT · barge-in handler  │                        │
│  TTS-aligned transcripts             │                        │
│  RTC stack                           │                        │
└────────────────┬────────────────────┘                        │
                 │ audio bidirectional                          │
                 ▼                                              ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│         LIVEKIT AGENT WORKER  ── separate long-running Python process ──                  │
│         $ cd backend && uv run python -m feynman.livekit.worker dev                       │
│  Stack: Python 3.13 · uv · structlog (JSON in prod) · pydantic-settings                   │
│  ───────────────────────────────────────────────────────────────────────────────────────  │
│  worker.py:entrypoint(ctx)                                                                 │
│    • teaching_ctx = TeachingContext(session_id, state_machine)                             │
│    • board_verifier = BoardVerifier(publish_fn, audit)                                     │
│    • session = AgentSession(stt, llm, tts, vad, userdata=teaching_ctx,                     │
│                             use_tts_aligned_transcript=True, max_tool_steps=30)            │
│    • agent = FeynmanAgent(teaching_ctx, topic, subject, grade_level)                       │
│    • try: await session.start(agent, room)                                                 │
│      finally: drift_task.cancel()  ← Phase 5a-3 cleanup                                    │
│                                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────────────────────┐ │
│  │  FeynmanAgent : livekit.agents.Agent                                                 │ │
│  │  ───────────────────────────────────────────────────────────────────────────────── │ │
│  │  on_enter()              ─ curriculum load + warm + plan + drift loop spawn          │ │
│  │  llm_node(chat_ctx,...)  ─ drain PerceptionFeedback → chat_ctx (Phase 5a-1)          │ │
│  │  tts_node(text,...)      ─ strip <highlight target=.../> mid-stream → dispatch       │ │
│  │  _periodic_drift_check() ─ 30s asyncio loop, Haiku vision check (Phase 5a-3)         │ │
│  └────────┬───────────────────┬────────────────────┬─────────────────────┬──────────────┘ │
│           │                   │                    │                     │                │
│  ┌────────▼────────┐ ┌────────▼─────────┐ ┌────────▼──────────┐ ┌────────▼────────────┐  │
│  │ TeachingContext │ │ BoardManager     │ │ BoardVerifier     │ │ Tools (32+)         │  │
│  │ (in-mem hub)    │ │ active_board     │ │ ─4 vision modes─  │ │ @function_tool      │  │
│  │ ─────────────── │ │ board_stack[]    │ │ • layout verify   │ │ @state_constrained  │  │
│  │ session_id      │ │ design_specs{}   │ │ • annotation 5a-1 │ │ ───────────────────  │  │
│  │ state_machine   │ │ next_id()        │ │ • diag intent 5a-2│ │ draw_design_diagram │  │
│  │ lesson_plan     │ │ push/pop_board   │ │ • drift     5a-3  │ │ modify_design_...   │  │
│  │ current_idx     │ └──────────────────┘ │ ─────────────────│ │ write_equation      │  │
│  │ board_verifier  │                       │ Haiku ~$0.001/cal│ │ pin_label_near      │  │
│  │ anticipation    │                       │ Combined cost:   │ │ start_doubt_branch  │  │
│  │ doubt_orch.     │                       │ $0.30-0.34/hr typ│ │ resolve_doubt       │  │
│  │ audit           │                       └───────────────────┘ │ advance_concept     │  │
│  │ perception_que  │                                              │ ...                 │  │
│  │ original_diag_  │                                              └─────────────────────┘  │
│  │  claims (5a-3)  │                                                                       │
│  │ concept_plans   │                                                                       │
│  └─────────────────┘                                                                       │
└──┬────────────┬──────────────┬───────────────┬────────────────┬─────────────────┬─────────┘
   │ STT        │ LLM          │ TTS           │ VAD (local)    │ Vision (Haiku)  │ Cypher
   │ stream     │ teaching     │ stream        │                │                 │
   ▼            ▼              ▼               ▼                ▼                 ▼
┌─────────┐ ┌────────────┐ ┌─────────┐  ┌───────────┐  ┌─────────────┐  ┌──────────────────┐
│Deepgram │ │ Anthropic  │ │Cartesia │  │ Silero    │  │ Anthropic   │  │ Neo4j (async)    │
│ STT     │ │ Sonnet 4.6+│ │ TTS     │  │ VAD       │  │ Haiku 4.5   │  │ ──────────────── │
│ ─────── │ │ ────────── │ │ ─────── │  │ (in-proc) │  │ ─────────── │  │ bolt:// driver   │
│ stream  │ │ teaching   │ │ stream  │  │ ~10ms     │  │ vision      │  │ ~3-8ms / query   │
│ TTFB    │ │ brain      │ │ TTFA    │  │ always-on │  │ ~600-1500ms │  │ self-host or Aura│
│ ~200-   │ │ ~1-3s/turn │ │ ~150ms  │  │ CPU only  │  │ /verify call│  │ ────────────────  │
│  400ms  │ │ $3/$15 per │ │ $varies │  │           │  │ $1/$5 per M │  │ Schema:           │
│         │ │  1M tokens │ │ /1M chr │  │           │  │  tokens     │  │ • (:Concept)      │
│ en-IN   │ │ prompt-    │ │ voice + │  │           │  │ ~$0.001/cal │  │   uid, type,      │
│ model   │ │  cache ON  │ │  emotion│  │           │  │             │  │   summary,        │
│         │ │  (8M cap)  │ │  mod    │  │           │  │             │  │   visual_hint,    │
│         │ │ COST: $3-5 │ │         │  │           │  │             │  │   page_range      │
│         │ │ /hr live   │ │         │  │           │  │             │  │ • (:Chapter)      │
│         │ │ TEACHING   │ │         │  │           │  │             │  │ • PREREQUISITE,   │
│         │ │ (dominant) │ │         │  │           │  │             │  │   LEADS_TO,       │
│         │ │            │ │         │  │           │  │             │  │   EXAMPLE_OF      │
└─────────┘ └────────────┘ └─────────┘  └───────────┘  └─────────────┘  └──────────────────┘
                                                                                ▲
                                                                                │ seeded by
                                                                                │ (offline)
                                                                  ┌─────────────┴────────────┐
                                                                  │  data_pre_compute        │
                                                                  │  ──────────────────────  │
                                                                  │  13-phase ingestion       │
                                                                  │  pipeline (DESIGNED,      │
                                                                  │   NOT BUILT)              │
                                                                  │  ───────────────────────  │
                                                                  │  PDF → BookSkeleton →     │
                                                                  │  anchors → chapter        │
                                                                  │  extraction → validation  │
                                                                  │  → entity resolution →    │
                                                                  │  unification → Neo4j      │
                                                                  │  ingestion → salience →   │
                                                                  │  semantic validation →    │
                                                                  │  pipeline+CLI → visual    │
                                                                  │  pre-gen → cleanup        │
                                                                  │  ───────────────────────  │
                                                                  │  Anthropic Opus for       │
                                                                  │  extraction, Haiku for    │
                                                                  │  validation. Reference:   │
                                                                  │  patient-medical-graph    │
                                                                  └───────────────────────────┘

(parallel: design_agent runs IN-PROCESS via feynman.agent.design_bridge — not a separate process)

┌─────────────────────────────────────────────────────┐   ┌─────────────────────────────────────┐
│  design_agent  (in-process Python module)           │   │  FastAPI server (uvicorn)           │
│  imported by: feynman.agent.design_bridge           │   │  separate Python process            │
│  ─────────────────────────────────────────────────  │   │  ─────────────────────────────────  │
│  generate_design_diagram(prompt, mode):             │   │  POST /sessions  ─ create LiveKit   │
│   • mode="auto"  ─ dispatch regex routes to JSON    │   │       room + JWT, persist row       │
│     or python (5 keywords: perpendicular,           │   │  GET  /sessions/:id                 │
│     tangent, intersect, parametric, polar)          │   │  WS   /ws/:session_id  (fallback)   │
│   • mode="direct" ─ SYSTEM_PROMPT → Sonnet → JSON   │   │                                     │
│     Latency: 5–15s · Cost: ~$0.10–0.30 / diagram    │   │  Stack: FastAPI · asyncpg · uvicorn │
│   • mode="python" ─ SYSTEM_PROMPT_PYTHON → Sonnet   │   │  Mostly stateless                   │
│     writes Python → AST-whitelist sandbox executes  │   └────────┬────────────────────────────┘
│     → DiagramSpec · Latency: 3–8s · Same cost       │            │
│                                                     │            ▼
│  In-memory FIFO cache (≤64 entries, OrderedDict),   │   ┌──────────────────────────┐
│  key = prompt + mode + provider + model + mtimes    │   │  Postgres (asyncpg)      │
│   → identical prompts within session = 0ms          │   │  • SessionModel · ~5ms   │
│                                                     │   │    (id, room_name,       │
│  STEM composites (Phase 3-5):                       │   │     subject, status,     │
│   add_right_triangle · add_free_body_diagram        │   │     teaching_state,      │
│   add_lens · add_ray · add_lewis_structure          │   │     ended_at)            │
│   All auto-register dictionary roles                │   └──────────────────────────┘
└─────────────────────────────────────────────────────┘   ┌──────────────────────────┐
                                                          │  Redis (redis.asyncio)   │
                                                          │  ──────────────────────  │
                                                          │  • hot session snapshots │
                                                          │  • diagram spec cache    │
                                                          │  • ~1ms / op             │
                                                          └──────────────────────────┘
```

**Diagram legend**:
- Solid lines = synchronous in-process calls or single-network-hop.
- Process boundaries = double-line boxes (╔═╗) only at the topmost levels.
- Latencies and per-call costs annotated inline where they bind a design decision.
- `5a-1 / 5a-2 / 5a-3` refers to the perception loop phases shipped in commits `febe268` / `a9cf255` / `87e6957`.

### 3.2 The five subsystems (`memory/architecture-tech-stack.md`)

1. **EARS** — STT + VAD + speaker awareness + interrupt detection. Today: Deepgram + Silero. Speaker ID parked (consumer = single student, no need; school mode would need it).
2. **BRAIN** — teaching state machine, the core IP. Custom async Python in `backend/src/feynman/agent/`. Explicitly NOT LangGraph (stack-based branching is natural, zero overhead, ~13K LOC of IP).
3. **VOICE** — Cartesia TTS, real-time streaming, interrupt handling, TTS-aligned transcript. `livekit/pipeline.py:create_tts()`.
4. **VISUALS** — typed Pydantic instructions over LiveKit data channel; rendered on React + Canvas/WebGL. Split-board: Slide (~38%) + Notebook (~62%).
5. **MEMORY** — Postgres (durable), Redis (hot), Neo4j (curriculum graph). Per-student knowledge graph designed, not yet built.

### 3.3 Provider stack

| Layer | Provider | Why | Cost reference |
|---|---|---|---|
| STT | Deepgram | Streaming, IGCSE-level accuracy | bundled |
| LLM (teaching) | Anthropic Claude Sonnet | Best frontier for teaching | dominant cost driver |
| LLM (sub-tasks) | Anthropic Haiku | Cheap perception + planning | $0.10–0.34/hr |
| TTS | Cartesia | Natural, fast, emotion control | bundled |
| VAD | Silero | Open-source, fast | local |
| RTC | LiveKit Agents | Room model + SDK + barge-in | self-host or cloud |
| Curriculum store | Neo4j | Graph-native, async driver | self-host |
| Hot state | Redis | Async, fast | self-host |
| Durable state | Postgres | Async via asyncpg | self-host |

Baseline session cost: **~$5–8/hour** of live teaching at full Sonnet + Cartesia + Deepgram. Subscription at ₹4000/mo = ~$48/mo ≈ 6–10 hours of teaching budget. **Cost discipline matters**. Every subsystem has a per-hour cap (typically <$1/hr). See §15.5.

### 3.3a Latency budget — master sheet

```text
                    LATENCY BUDGET (live teaching, student-perceived)
┌──────────────────────────────────────────┬─────────────┬───────────────────────────────┐
│ Stage / Event                            │ Target      │ Source                        │
├──────────────────────────────────────────┼─────────────┼───────────────────────────────┤
│ Voice round-trip (turn-taking)           │  ≤ 2.0s     │ MEMORY.md hardest-problem #3  │
│   ├ Mic → VAD detect end of student turn │  ≤ 200ms    │ Silero VAD on-device          │
│   ├ Audio → Deepgram STT TTFB partials   │ 200–400ms   │ Deepgram streaming en-IN      │
│   ├ Student transcript → Sonnet turn end │ 1.0–3.0s    │ Anthropic Sonnet teaching     │
│   └ First TTS audio frame                │ ≤ 150ms     │ Cartesia TTFA                 │
│                                          │             │                               │
│ Inline pointing (mid-sentence)           │  ≤ 300ms    │ Phase 4 (action tags 4e1811c) │
│   ├ Token containing tag → tts_node      │   ~5-20ms   │ in-process                    │
│   ├ Tag parsed → asyncio.create_task     │   ~1ms      │ ActionTagParser               │
│   ├ Dispatch → publish over DC           │   ~5-20ms   │ LiveKit data channel          │
│   └ Browser → SyncManager → DOM render   │   ~50-200ms │ GSAP + CSS animations         │
│                                          │             │                               │
│ Diagram swap (sentence-boundary)         │  ≤ 800ms    │ Phase 2 (Tier A AFTER_NEXT…)  │
│   ├ Tool call → cache hit                │   <50ms     │ AnticipationEngine            │
│   ├ Publish → frontend                   │   ~50ms     │ Data channel                  │
│   └ Stroke-reveal animation              │   ~600ms    │ GSAP path-draw                │
│                                          │             │                               │
│ Diagram swap (cache MISS)                │  5–10s OK   │ ONLY with vocal bridge        │
│   ├ design_bridge → Anthropic Sonnet     │ 5–15s       │ JSON path                     │
│   │      OR Python sandbox path          │ 3–8s        │ Python DSL (Phase 3)          │
│   └ Same publish + stroke-reveal         │             │                               │
│                                          │             │                               │
│ Annotation re-point (perception recovery)│  next turn  │ Phase 5a-1 (febe268)          │
│   ├ Tool publishes annotation            │   ~50ms     │                               │
│   ├ Screenshot capture (async, parallel) │ 100–500ms   │ frontend BoardCapture.tsx     │
│   ├ Haiku vision call                    │ 600–1500ms  │ ~$0.001/call                  │
│   └ Feedback → drained on next LLM turn  │  3–30s late │ depends on student utterance  │
│                                          │             │                               │
│ Drift check (periodic 30s background)    │ background  │ Phase 5a-3 (87e6957)          │
│   ├ Pre-flight (hash dedup, branch)      │   <1ms      │ skip if no change             │
│   ├ Screenshot + Haiku                   │ ~1.5s wall  │ doesn't block hot path        │
│   └ Apply feedback                       │  next turn  │                               │
│                                          │             │                               │
│ VL-JEPA self-hosted (Phase 5b, FUTURE)   │  ≤ 142ms    │ sub-sentence correction       │
│                                          │             │ POST-TRACTION (GPU infra)     │
├──────────────────────────────────────────┼─────────────┼───────────────────────────────┤
│ Curriculum load (session boot)           │ 50–200ms    │ Neo4j Cypher single chapter   │
│ Concept plan (boot, warm task)           │ 2–4s        │ Sonnet plan_concept           │
│ Anticipation pre-gen (boot, async)       │ 5–15s/diag  │ overlapped with greeting +    │
│                                          │             │ first concept teaching        │
└──────────────────────────────────────────┴─────────────┴───────────────────────────────┘
```

### 3.3b Cost budget — master sheet

```text
                    COST BUDGET ($USD per hour of live teaching)
┌──────────────────────────────────────────┬─────────────┬───────────────────────────────┐
│ Subsystem                                │ Per-hour    │ Notes                         │
├──────────────────────────────────────────┼─────────────┼───────────────────────────────┤
│ Anthropic Sonnet (teaching LLM)          │ $3.00-5.00  │ DOMINANT cost. ~$3/M input,   │
│                                          │             │ $15/M output. Prompt-cache    │
│                                          │             │ ON; ~50-70% input cached.     │
│                                          │             │ At 1-3 turns/min × ~5K tok    │
│                                          │             │ context × 60 min/hr.          │
│                                          │             │                               │
│ Anthropic Haiku (perception loop)        │ $0.30-0.34  │ 5a-1 ann + 5a-2 diag + 5a-3   │
│   ├ 5a-1 annotation verify               │ $0.06-0.12  │   drift. Combined budget cap. │
│   ├ 5a-2 diagram intent + layout         │ $0.08-0.12  │   Worst-case $0.44-0.48/hr.   │
│   └ 5a-3 drift check                     │ $0.08-0.12  │                               │
│                                          │             │                               │
│ Anthropic Sonnet (design_agent)          │ $0.50-1.50  │ Per-diagram ~$0.10-0.30.      │
│                                          │             │ 3-7 cache misses per session  │
│                                          │             │ typical. Anticipation cuts.   │
│                                          │             │                               │
│ Anthropic Sonnet (concept_planner)       │ $0.20-0.50  │ ~$0.05 per concept × ~10      │
│                                          │             │ concepts/hr. Warm-task style. │
│                                          │             │                               │
│ Deepgram STT                             │ ~$0.50      │ Streaming en-IN, per-minute.  │
│ Cartesia TTS                             │ ~$0.30-0.60 │ Per character. ~5K chars/min  │
│                                          │             │ live teaching.                │
│ Silero VAD                               │ $0          │ Local, CPU.                   │
│ LiveKit (rooms + STT/TTS bridge)         │ ~$0.10-0.30 │ Cloud option. Self-host = $0  │
│ Postgres / Redis (asyncpg)               │ ~$0.01      │ Self-hosted.                  │
│ Neo4j                                    │ ~$0.05      │ Self-hosted curriculum.       │
│ Frontend hosting (Vite static)           │ ~$0.001     │ CDN, negligible.              │
├──────────────────────────────────────────┼─────────────┼───────────────────────────────┤
│ BASELINE TOTAL (typical session)         │ $5.00-8.00  │ vs ₹4000/mo subscription      │
│                                          │             │ = ~$48/mo ÷ session-hrs       │
│                                          │             │ → break-even at ~6-10 hr/mo   │
└──────────────────────────────────────────┴─────────────┴───────────────────────────────┘

   PER-SUBSYSTEM PER-HOUR CAP: $1.00 (informational ceiling, not a hard limit)
   Reject feature if its hourly cost-add > $0.50 unless it passes precision + latency.

   Future cost levers:
    • Phase 5b VL-JEPA self-hosted  → cuts perception cost to GPU electricity (~$0.20/hr)
    • Fine-tuned Feynman model      → cuts teaching LLM ~50% post-traction
    • Aggressive prompt-cache       → already on; can push further with cache discipline
    • Cheaper TTS provider          → Cartesia is premium; downgrade is option for free tier
```

### 3.4 Inter-process communication

- **Frontend ↔ FastAPI**: REST (`POST /sessions`, `GET /sessions/:id`) and WebSocket (`/ws/:session_id` streams visuals — fallback path; primary is LiveKit data channel).
- **Frontend ↔ LiveKit Worker**: WebRTC for audio; LiveKit data channel for visual instructions (topic `"visuals"`, `"board_capture"`, `"bounds"`).
- **Worker ↔ design_agent**: in-process (Python imports `feynman.agent.design_bridge` which reads the design_agent prompt files at runtime and calls Anthropic).
- **Worker ↔ Neo4j**: async via `neo4j` driver from `agent/curriculum_loader.py`.
- **Worker ↔ Postgres**: via SQLAlchemy + asyncpg (mostly used by FastAPI; worker is mostly stateless except `SessionAudit`).

### 3.5 Why these choices

- **LiveKit Agents** over custom WebRTC: room model, STT/LLM/TTS pipeline, barge-in handling, TTS-aligned transcripts. Saves us 6–12 months.
- **Custom async state machine** over LangGraph: doubt branching is a stack (push/pop), states are an enum, transitions are predictable. LangGraph adds nodes-and-edges overhead with no win. Stack-based async in ~500–1000 LOC is the IP.
- **Two LLM streams** (voice script + visual instructions) over one: separation lets us cache visuals (anticipation engine), parallelize generation, and apply different cost discipline to each.
- **Neo4j** over Postgres-for-curriculum: the curriculum IS a graph. We need prerequisite/leads_to edges, salience scoring, multi-hop queries.
- **Python+FastAPI** backend: best ML/AI ecosystem, async-native, matches LiveKit Agents (Python SDK is first-class).
- **React+Canvas/WebGL** frontend: SVG for crisp KaTeX overlays, Canvas/WebGL for animations.

---

## 4. The Teaching State Machine (Core IP)

This is the most important section. The state machine is **the IP**.

### 4.0 State machine + branch tree — visual model

```text
                            BRANCH STACK (TeachingStateMachine._stack)

   Stack top ──▶  ┌─────────────────────────────────────────────────────┐
                  │ BranchContext (doubt — "why is sin = opp/hyp?")     │
                  │ ─ id: UUID, state: HANDLING_DOUBT                   │
                  │ ─ concept: "Why sin = opp/hyp"                      │
                  │ ─ return_anchor: ↓ (snapshot of parent)              │
                  │ ─ checklist: [                                       │
                  │     ChecklistItem("Explain ratio invariance", done)  │
                  │     ChecklistItem("Give numerical example", pending) │
                  │     ChecklistItem("Test similar case", pending)      │
                  │   ]                                                  │
                  │ ─ watchdog: 60s soft / 120s hard                     │
                  └─────────────────────────────────────────────────────┘
                  ┌─────────────────────────────────────────────────────┐
                  │ BranchContext (main — "SOH-CAH-TOA")                │
                  │ ─ id: UUID, state: TEACHING                         │
                  │ ─ concept: ConceptNode(2)                           │
                  │ ─ checklist: none (main branch)                     │
                  └─────────────────────────────────────────────────────┘
   Stack bottom

                            BRANCH TREE (logical view)

      ┌─────────────────────────────────────────────────────────────┐
      │ Main branch (linear concept progression)                     │
      │                                                              │
      │  C0 ─▶ C1 ─▶ C2 ─▶ C3 ─▶ C4 ─▶ C5 ─▶ ... ─▶ Cn              │
      │   │     │     │                                              │
      │   │     │     └── D2.1 ─▶ (resolves, pops back to C2)        │
      │   │     │                                                    │
      │   │     └── D1.1 ─▶ D1.1.1 ─▶ (nested; both resolve)         │
      │   │            │                                             │
      │   │            └─ (resolves, pops back to C1)                │
      │   │                                                          │
      │   └── (Re)-approach branch agent-initiated when              │
      │       comprehension gate fails on C0 ─▶ (resolves)           │
      └─────────────────────────────────────────────────────────────┘

      C* = main-branch concept (TeachingState.TEACHING)
      D* = doubt branch       (TeachingState.HANDLING_DOUBT)

                          STATE TRANSITIONS (enum: TeachingState)

         ┌──────────┐
         │   IDLE   │
         └────┬─────┘
              │ on_enter() fires
              ▼
         ┌──────────┐        ┌────────────────────┐
         │ GREETING │ ──────▶│ WAITING_FOR_STUDENT │
         └──────────┘        └──────────┬─────────┘
                                        │ student speaks
                                        ▼
                              ┌────────────────────┐
                              │      TEACHING      │◀────────────┐
                              └─────┬──────────┬───┘             │
                                    │          │                 │
                  start_doubt_branch│          │advance_concept  │ resolve_doubt
                                    ▼          ▼                 │  (after restore)
                              ┌────────────────────┐             │
                              │  HANDLING_DOUBT    │─────────────┘
                              └────────────────────┘
                                    │
                                    │ (terminal)
                                    ▼
                              ┌────────────────────┐
                              │     COMPLETED      │
                              └────────────────────┘

       Constraints in HANDLING_DOUBT (enforced by @state_constrained decorator):
         ✗ advance_concept       (can't skip ahead from inside a doubt)
         ✗ set_lesson_topic      (can't pivot mid-doubt)
         ✗ switch_board          (can't navigate boards out from under)
         ✗ start_doubt_branch    (depth-limited; only nesting up to 2 currently)
         ✓ resolve_doubt         (gated by orchestrator.is_resolution_allowed)
         ✓ all draw/write tools  (free use)

       File refs:
         agent/state_machine.py    ─ TeachingStateMachine, BranchContext
         agent/states.py           ─ TeachingState enum
         agent/teaching_context.py ─ TeachingContext (the hub)
         agent/tools.py            ─ @function_tool + @state_constrained decorators
```

### 4.1 Model

A teaching session is a **tree/graph** (`memory/teaching-flow.md`). Like git:

```
Concept 0: Intro to Right Triangles
  └─ Concept 1: SOH-CAH-TOA
       ├─ Doubt: "what's sin again?"           ← branch
       │    └─ Doubt: "wait, what's a ratio?"  ← nested branch
       │         └─ (resolves, pops)
       │    (resolves, pops)
       └─ Concept 2: Solving for sides         ← back on main
            └─ Doubt: "why do we use sin here?"
                 └─ (resolves, pops)
```

- **Main branch**: linear sequence of concepts.
- **Doubt branches**: spawned from main when student asks a question. Carry their own checklist, own board, own return anchor.
- **Nested doubts**: branches from branches. Same push/pop mechanism.
- **Comprehension re-approach branches**: agent-initiated, spawned when a comprehension check fails. Not LLM-initiated like doubt branches; system can force them.

### 4.2 Implementation (LLD)

**File**: `backend/src/feynman/agent/state_machine.py`

```python
class TeachingState(Enum):
    IDLE
    GREETING
    TEACHING
    HANDLING_DOUBT
    WAITING_FOR_STUDENT
    PAUSED
    COMPLETED

class BranchContext:
    id: UUID
    state: TeachingState
    concept: ConceptNode | None
    return_anchor: ReturnAnchor | None  # for doubts
    checklist: list[ChecklistItem]
    started_at: datetime

class TeachingStateMachine:
    _stack: list[BranchContext]  # the branch stack
    @property
    def current(self) -> BranchContext: return self._stack[-1]
    @property
    def depth(self) -> int: return len(self._stack)
    async def push_branch(self, concept) -> BranchContext  # for doubt
    async def pop_branch(self) -> BranchContext            # for resolve
    async def transition(self, new_state)
```

**File**: `backend/src/feynman/agent/teaching_context.py` — the **hub** for all in-flight state. Held in `AgentSession.userdata`.

```python
@dataclass
class TeachingContext:
    session_id: UUID
    state_machine: TeachingStateMachine
    lesson_plan: LessonPlan | None
    current_concept_index: int
    completed_indices: list[int]
    board_manager: BoardManager
    board_verifier: BoardVerifier | None    # Phase 5a
    anticipation: AnticipationEngine        # warm cache
    doubt_orchestrator: DoubtOrchestrator
    audit: SessionAudit
    curriculum: CurriculumData | None       # Neo4j payload
    # Phase 5a-1 (annotations) + 5a-2 (diagrams) perception:
    perception_feedback_queue: list[PerceptionFeedback]
    perception_feedback_budget_used: dict[int, int]
    annotation_verified: set[tuple[str, str, int]]
    last_diagram_claims: dict[str, DiagramClaim]
    diagram_version: dict[str, int]
    diagram_intent_verified: set[tuple[str, int, int]]
    diagram_layout_verified: set[tuple[str, int, int]]
    # Phase 5a-3 (drift):
    original_diagram_claims: dict[str, str]    # FIRST claim, never overwritten
    last_drift_check_hash: str | None
    drift_feedback_budget_used: dict[int, int]
    # Planning:
    concept_plans: dict[int, ConceptTeachingPlan]
    doubt_plan: ConceptTeachingPlan | None
    # Live overlay tracking:
    current_diagram_dictionary: dict[str, Any]
    active_highlights: list[str]
    active_annotations: list[str]
    last_beat_index: int
```

This is the entire state surface of an in-flight session. Everything else is either Redis (hot snapshots) or Postgres (durable session record).

### 4.3 The dual-output model

The LLM emits **two streams**:

1. **Voice script** — natural narration. Goes to TTS.
2. **Tool calls** (visual instructions) — `draw_design_diagram(prompt=...)`, `write_equation(latex=...)`, etc. Each produces a typed `VisualInstruction` published over the data channel.

Plus a third channel woven into the voice script:
3. **Inline action tags** — `<highlight target="hypotenuse"/>` embedded in narration text. Phase 4 (`4e1811c`). The `tts_node` override strips them from TTS-bound text and dispatches as visual instructions mid-stream (see §6.5).

The agent doesn't think about WHICH channel to use — the prompt teaches it the protocol. The TWO streams are merged on the frontend by the rendering engine (`engine/SyncManager.ts`) using `SyncMode` enum: `IMMEDIATE`, `VISUAL_FIRST`, `AFTER_NEXT_SENTENCE`, `SPEECH_FIRST`, `SIMULTANEOUS`, `PAUSE`.

### 4.4 Concept planning (`agent/concept_planner.py`)

Before the agent teaches a concept, a **separate async planning agent** generates a `ConceptTeachingPlan`:

```python
@dataclass
class ConceptTeachingPlan:
    concept_index: int
    beats: list[TeachingBeat]
    checklist: list[ChecklistItem]   # comprehension gates

@dataclass
class TeachingBeat:
    speech_intent: str                # what the agent should say (intent, not verbatim)
    visual_type: str                  # "draw_design_diagram", "write_equation", etc.
    visual_payload: dict              # args to the tool
    timing: BeatTiming                # VISUAL_FIRST | SPEECH_FIRST | SIMULTANEOUS | PAUSE
    pause_seconds: float | None
    target_voice_script: str | None   # verbatim binding for demo beats (Aanya)
```

**Status of beat orchestration**: doc 05 (`docs/design/05-beat-orchestration-system.md`) specs a BEAT MODE (deterministic orchestrator plays pre-generated beats) vs CONVERSATIONAL MODE (live tool calls). Today, **planning happens** (`concept_plans` populated in `TeachingContext`) but **the deterministic orchestrator does NOT play them**. The plan is injected into the system prompt as guidance; the agent reacts to it via tool calls live. The "orchestrator with mode switching on interruption" is **designed but not built**. Aanya demo's `target_voice_script` binding lets specific beats be played verbatim — partial realization. This is a planned gap (§15.6).

### 4.5 Curriculum loading

**Files**: `agent/curriculum_loader.py` (Neo4j queries), `agent/lesson_plan.py` (LessonPlan + ConceptNode).

At session boot (`FeynmanAgent.on_enter`):
1. If `USE_NEO4J_CURRICULUM=true` and `topic` provided: `load_curriculum(topic, subject) → CurriculumData`.
2. `lesson_plan_from_curriculum(curriculum) → LessonPlan` ordered by `teaching_order` (chapter_order × 1000 + within_chapter_order).
3. Stored on `tc.lesson_plan`. Drives the system prompt context and the anticipation engine.
4. If curriculum absent: free-form mode (no plan, no pre-gens, no checklist). Topic still passed; agent improvises.

### 4.6 State-constrained tools

**File**: `agent/tools.py` — every tool decorated `@function_tool()`.

Some tools are **forbidden in certain states**:

```python
@function_tool()
@state_constrained(
    forbidden_states={TeachingState.HANDLING_DOUBT},
    error_template="Cannot advance the lesson while inside a doubt branch — call resolve_doubt first."
)
async def advance_concept(ctx) -> str: ...
```

This is one of the **five doubt guardrails** (§5.5). The decorator returns a `ToolConstraintError` to the LLM if the constraint is violated. The LLM sees the error in its next turn and adapts.

---

## 5. The Doubt System (Production-Grade Guardrails)

Doubt handling is the **irreducible moat**. From `docs/design/12-aanya-demo-v0.md`: "Beat 4 is real, not scripted." Students ask whatever they want; the agent must branch correctly and return cleanly **every time**.

LLMs without guardrails fail. They forget to resolve, resolve too early, advance while in doubt, nest doubts uncontrolled, lose their place. Production-grade requires five guardrails (`docs/design/15-doubt-orchestrator.md`).

### 5.0 Doubt branch flow — push to resolve

```text
                            DOUBT BRANCH LIFECYCLE (push → resolve)

  STUDENT: "Wait, why is sin = opposite/hypotenuse?"
                          │
                          │ Sonnet LLM emits tool call:
                          ▼
       ┌──────────────────────────────────────────────────────────────┐
       │  tools.py:start_doubt_branch(related_concept=...)             │
       │  ──────────────────────────────────────────────────────────  │
       │  parent_branch_id = tc.state_machine.current.id               │
       └────────────────────────┬─────────────────────────────────────┘
                                │
                ┌───────────────┴───────────────┐
                ▼                                ▼
   ┌────────────────────────┐       ┌────────────────────────────────┐
   │ state_machine          │       │ board_manager                   │
   │  .push_branch(concept) │       │  .push_board(parent_id=...)     │
   │ ─────────────────────  │       │ ──────────────────────────────  │
   │ BranchContext(         │       │ • Old board pushed to stack     │
   │   id=uuid4(),          │       │ • New empty board active        │
   │   state=HANDLING_DOUBT │       │ • Slide cleared, notebook new   │
   │   concept=related,     │       │ • Branch ID stored on board     │
   │   started_at=now()     │       └────────────────────────────────┘
   │ ) pushed onto stack    │
   └────────────────────────┘
                │
                ▼
   ┌────────────────────────────────────────────────────────────────┐
   │  doubt_orchestrator.on_push(branch, related_concept,            │
   │                              parent_branch_id,                  │
   │                              checklist=[<3 items>])             │
   │  ────────────────────────────────────────────────────────────  │
   │                                                                 │
   │  1. SNAPSHOT — capture return_anchor (no LLM call):             │
   │     return_anchor = ReturnAnchor(                               │
   │       parent_branch_id=parent_branch_id,                        │
   │       parent_concept_index=tc.current_concept_index,            │
   │       last_beat_index=tc.last_beat_index,                       │
   │       last_voice_anchor="...last phrase spoken...",             │
   │       active_highlights=list(tc.active_highlights),             │
   │       active_annotations=list(tc.active_annotations),           │
   │       notebook_cursor=board_mgr.notebook_position,              │
   │       timestamp=now()                                           │
   │     )                                                            │
   │                                                                 │
   │  2. WATCHDOG — spawn asyncio.Task:                              │
   │     • 60s  → mark soft_nudge_fired, next prompt rebuild adds    │
   │              "wrap up the doubt"                                │
   │     • 120s → _force_resolve_doubt(branch):                      │
   │                speak fallback "Let's circle back next time"     │
   │                pop board + branch                               │
   │                                                                 │
   │  3. CHECKLIST — store {                                         │
   │       ChecklistItem("Explain why sin = opp/hyp", status="pend") │
   │       ChecklistItem("Give numerical example",    status="pend") │
   │       ChecklistItem("Test similar case",         status="pend") │
   │     }                                                            │
   │                                                                 │
   │  4. ANTICIPATION — fire pre-gen for likely doubt diagrams       │
   │     (4-diagram library for Aanya demo cached at boot)           │
   └────────────────────────────────────────────────────────────────┘
                │
                ▼
   ┌────────────────────────────────────────────────────────────────┐
   │  await _update_agent_prompt(ctx)                                │
   │  ────────────────────────────────────────────────────────────  │
   │  Prompt now contains:                                           │
   │   • "## Active Doubt Branch"                                    │
   │   • Resolution checklist with current statuses                  │
   │   • Tool constraints (forbidden in HANDLING_DOUBT)              │
   │   • Soft-nudge banner (if fired)                                │
   └────────────────────────────────────────────────────────────────┘

                              │
        ═══════════════════════ NOW IN HANDLING_DOUBT ═══════════════════════
                              │
   ┌────────────────────────────────────────────────────────────────┐
   │  AGENT TEACHES THE DOUBT (multiple LLM turns):                  │
   │   • draw_design_diagram("similar triangle invariance")          │
   │   • write_equation("sin θ = opp/hyp")                           │
   │   • Speak narration with inline <highlight/> tags               │
   │                                                                 │
   │  AUTO-TICK happens here:                                        │
   │   ┌────────────────────────────────────────────────────────┐   │
   │   │ Each assistant message is forwarded to                  │   │
   │   │   doubt_orchestrator.on_voice_emitted(text, branch.id)  │   │
   │   │ (registered via session.on("conversation_item_added"))  │   │
   │   │                                                         │   │
   │   │ orchestrator substring-matches text against each        │   │
   │   │ checklist item's keywords:                              │   │
   │   │   "ratio" + "invariance" → ticks item 0                 │   │
   │   │   numeric value + degree → ticks item 1                 │   │
   │   │   "let's check"          → ticks item 2 (manual or kw)  │   │
   │   └────────────────────────────────────────────────────────┘   │
   │                                                                 │
   │  TOOL-BASED auto-tick:                                          │
   │     draw_design_diagram → ticks any "show diagram" item         │
   │                                                                 │
   │  MANUAL tick: mark_doubt_step_complete(step_index) tool         │
   └────────────────────────────────────────────────────────────────┘

                              │
                              │ AGENT: "OK, that should make sense now."
                              ▼
   ┌────────────────────────────────────────────────────────────────┐
   │  tools.py:resolve_doubt()                                       │
   │  @state_constrained: caller must be in HANDLING_DOUBT           │
   │  ────────────────────────────────────────────────────────────  │
   │                                                                 │
   │  GATE — orchestrator.is_resolution_allowed(branch.id):          │
   │   ┌─────────────────────────────────────────────────────────┐  │
   │   │ if any(item.status != "done"):                          │  │
   │   │   return ToolConstraintError("checklist not complete")  │  │
   │   │ else: return True                                       │  │
   │   └─────────────────────────────────────────────────────────┘  │
   │                                                                 │
   │  If error: LLM sees it next turn, adjusts (e.g., calls          │
   │            mark_doubt_step_complete manually or finishes        │
   │            unresolved items via more teaching).                 │
   │  If allowed: proceed.                                           │
   └────────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┴─────────────┐
                ▼                            ▼
   ┌────────────────────────┐       ┌────────────────────────────┐
   │ board_manager           │       │ state_machine               │
   │  .pop_board()           │       │  .pop_branch()              │
   │ ─────────────────────  │       │ ──────────────────────────  │
   │ • Doubt board removed   │       │ • Doubt branch popped       │
   │ • Parent slide returns  │       │ • Parent branch active      │
   │ • Notebook cursor       │       │ • state → TEACHING          │
   │   restored              │       │                             │
   └────────────────────────┘       └────────────────────────────┘
                │                              │
                └──────────────┬───────────────┘
                               ▼
   ┌────────────────────────────────────────────────────────────────┐
   │  doubt_orchestrator.on_pop(branch.id)                           │
   │  ────────────────────────────────────────────────────────────  │
   │                                                                 │
   │  1. WATCHDOG — cancel asyncio.Task                              │
   │                                                                 │
   │  2. ANTICIPATION — tc.anticipation.clear_doubt_cache()          │
   │                                                                 │
   │  3. AUTO-RESTORE (no LLM round-trip):                           │
   │     • Re-publish each active_highlight from return_anchor:      │
   │         await _publish_visual(ctx, HighlightPulseInstruction(   │
   │             target=h, duration_ms=1500))                        │
   │       Highlights re-glow on parent slide.                        │
   │                                                                 │
   │     • Speak verbatim return cue (no LLM call):                  │
   │         await ctx.session.say(                                   │
   │             text="Okay, back to the ladder problem.",           │
   │             allow_interruptions=False                            │
   │         )                                                        │
   │                                                                 │
   │  4. Notebook cursor restored to return_anchor.notebook_cursor   │
   └────────────────────────────────────────────────────────────────┘
                               │
                               ▼
              ┌──────────────────────────────────────┐
              │  await _update_agent_prompt(ctx)      │
              │  ─ tool constraints lifted            │
              │  ─ doubt checklist gone               │
              │  ─ back to main teaching context      │
              └──────────────────────────────────────┘
                               │
                               ▼
                  AGENT CONTINUES MAIN LESSON
                  (state = TEACHING, depth = 1)


   File refs:
     agent/doubt_orchestrator.py    ─ DoubtOrchestrator class (~481 LOC)
     agent/state_machine.py         ─ push_branch / pop_branch
     agent/board.py                 ─ BoardManager.push_board / pop_board
     agent/tools.py:start_doubt_branch
     agent/tools.py:resolve_doubt
     agent/tools.py:mark_doubt_step_complete
     livekit/worker.py              ─ conversation_item_added → on_voice_emitted
```

### 5.1 Auto-snapshot on push (`DoubtOrchestrator.on_push`)

When `start_doubt_branch(related_concept)` fires:

```python
return_anchor = ReturnAnchor(
    parent_branch_id=parent.id,
    parent_concept_index=tc.current_concept_index,
    last_beat_index=tc.last_beat_index,
    last_voice_anchor="...last spoken phrase...",
    active_highlights=list(tc.active_highlights),
    notebook_cursor=tc.board_manager.notebook_position,
    timestamp=now()
)
branch.return_anchor = return_anchor
```

No LLM call. Pure state capture.

### 5.2 Auto-restore on pop (`DoubtOrchestrator.on_pop`)

When `resolve_doubt()` fires:
1. Pop board → parent slate returns.
2. Re-publish stored `active_highlights` (pulse + glow re-fire).
3. Speak the verbatim return cue ("Okay, back to the ladder.") via `ctx.session.say()` — no LLM round-trip.

Cleaner than asking the LLM to remember "where were we." The orchestrator does it.

### 5.3 Resolution checklist

Each doubt has 3 checklist items (generated by `plan_doubt`):

```python
ChecklistItem(description="Explain why sin = opposite/hypotenuse", status="pending")
ChecklistItem(description="Give a concrete numerical example", status="pending")
ChecklistItem(description="Test understanding with a similar case", status="pending")
```

**Auto-tick**:
- **Tool-based**: `draw_design_diagram(...)` auto-ticks any item with keyword "show diagram." Decorator on each tool maps to checklist matchers.
- **Voice-based**: every committed assistant message inside a doubt branch is forwarded to `orchestrator.on_voice_emitted(text, branch.id)` which substring-matches against checklist `keywords`. Implemented at `worker.py` via the `conversation_item_added` event listener.
- **Manual**: `mark_doubt_step_complete(step_index)` tool — the LLM can declare it explicitly.

**Gating**: `resolve_doubt()` is rejected (via `@state_constrained`) unless all items are `done`. Returns checklist error to LLM as a tool result; agent reads + complies.

### 5.4 Watchdog (`asyncio.Task` on push)

Two timers:
- **60s soft nudge**: orchestrator records `soft_nudge_fired`, agent's next prompt rebuild includes "wrap up the doubt — we have 1 minute."
- **120s force-resolve**: orchestrator triggers `_force_resolve_doubt(branch)`. Speaks fallback verbatim — "Let's circle back to that next time" — then pops the board + branch. LLM never gets a chance to drift forever.

Polite escape hatch. The watchdog protects the lesson's main thread.

### 5.5 Tool constraints in `HANDLING_DOUBT`

Forbidden inside doubt branches (return `ToolConstraintError`):
- `start_doubt_branch` — no nested doubts above depth 2 (config gate, currently allows 1 nesting level).
- `advance_concept` — can't skip ahead from inside a doubt.
- `set_lesson_topic` — can't pivot mid-doubt.
- `switch_board` — can't navigate boards out from under the doubt.

Implementation: `@state_constrained(forbidden_states={TeachingState.HANDLING_DOUBT})` decorator on each tool. Pattern is reusable for any constraint.

### 5.6 Implementation status

- 2A (core: snapshot + restore + checklist happy path) — **shipped** (`docs/design/15-doubt-orchestrator.md` Phase 2A).
- 2B (safety: watchdog + tool constraints + voice-keyword auto-tick) — **shipped** (commit `c79fede`).
- The DoubtOrchestrator is the most production-hardened piece of the BRAIN. Five-guardrail design = real not theater.

---

## 6. The Voice Pipeline

### 6.1 Framework

LiveKit Agents (`livekit-agents` Python SDK). The entire voice pipeline is built around their `Agent` + `AgentSession` classes.

### 6.2 Boot

**File**: `livekit/worker.py` — the entrypoint (~600 LOC; the largest single file).

```python
@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()
    teaching_ctx = TeachingContext(...)
    teaching_ctx.board_verifier = BoardVerifier(...)
    agent = FeynmanAgent(teaching_ctx, topic, subject, grade_level)
    session = AgentSession(
        stt=create_stt(),       # Deepgram
        llm=create_llm(),       # Anthropic Sonnet
        tts=create_tts(),       # Cartesia
        vad=create_vad(),       # Silero
        userdata=teaching_ctx,
        use_tts_aligned_transcript=True,
        max_tool_steps=30,
    )
    try:
        await session.start(agent=agent, room=ctx.room)
    finally:
        # Phase 5a-3: cancel drift loop on shutdown.
        drift_task.cancel()
```

### 6.2a Voice pipeline detail diagram

```text
                              VOICE PIPELINE (one student turn end-to-end)

╔══════════════════════════════════════════════════════════════════════════════════════════════╗
║                                       STUDENT SPEAKS                                          ║
║                                  "Wait, what's a hypotenuse?"                                 ║
╚════════════════════════════════════════╤═════════════════════════════════════════════════════╝
                                         │ mic audio frames (WebRTC, ~50-80ms RTT India)
                                         ▼
              ┌─────────────────────────────────────────────────┐
              │  Silero VAD  (in-browser AND on-worker)         │
              │  ──────────────────────────────────────────────  │
              │  • Detects speech start → barge-in fires        │
              │    LiveKit cancels in-flight TTS audio          │
              │    LiveKit aborts in-flight LLM stream          │
              │  • Detects speech end → turn boundary           │
              │  Latency: ~10ms                                 │
              └────────────────────────┬────────────────────────┘
                                       │ audio chunks
                                       ▼
              ┌─────────────────────────────────────────────────┐
              │  Deepgram STT (streaming, en-IN model)          │
              │  ──────────────────────────────────────────────  │
              │  • TTFB ~200-400ms for partial transcripts      │
              │  • Final committed transcript on turn end       │
              │  • Cost ~$0.50/hr                               │
              │  • Streaming output goes directly to chat_ctx   │
              └────────────────────────┬────────────────────────┘
                                       │ final transcript committed
                                       ▼
              ┌─────────────────────────────────────────────────────────────────────────────┐
              │  FeynmanAgent.llm_node(chat_ctx, tools, model_settings)    [worker.py:llm_node]│
              │  ──────────────────────────────────────────────────────────────────────────  │
              │  PRE-LLM:                                                                     │
              │   • drain_perception_feedback(tc, chat_ctx)  [worker.py:142]                  │
              │     For each fb in tc.perception_feedback_queue:                              │
              │       chat_ctx.add_message(role="user", content=fb.as_chat_note())            │
              │     [Phase 5a-1/2/3 — see §8]                                                  │
              │     Inserts `[PERCEPTION_FEEDBACK] ...` notes BEFORE the student's message    │
              │     so the LLM sees them in the same turn.                                    │
              │                                                                                │
              │  CALL:                                                                         │
              │   • Agent.default.llm_node(self, chat_ctx, tools, model_settings)              │
              │     → Anthropic Sonnet streaming completion                                    │
              │     Inputs:  TEACHING_SYSTEM_PROMPT + lesson_plan + concept_plan + dictionary  │
              │              + recent transcripts + perception feedback                        │
              │     Outputs: text chunks + tool_call chunks (parallel-safe)                    │
              │     Latency: ~1-3s per turn end-to-end                                         │
              │     Cost:    $3 in/$15 out per 1M tokens; prompt-cache ON (8M token cap)       │
              └─────────────┬───────────────────────────────┬───────────────────────────────┘
                            │                               │
                            │ text chunks (narration)        │ tool_call chunks (visuals)
                            │                               │ → parallel dispatch
                            ▼                               ▼
              ┌─────────────────────────────────┐  ┌─────────────────────────────────┐
              │  FeynmanAgent.tts_node(text,...)│  │  Tool execution (see §7 diagrams)│
              │  ─────────────────────────────  │  │  ───────────────────────────── │
              │  strip_action_tags(text, on_tag)│  │  draw_design_diagram(prompt=...)│
              │  ─ ActionTagParser:             │  │  write_equation(latex=...)       │
              │    • buffer across chunks       │  │  pin_label_near(target=...)     │
              │    • parse <highlight target=…/>│  │  start_doubt_branch(...)        │
              │    • 256-char overflow cap      │  │  ...                            │
              │    • fail-silent on malformed   │  │  Each emits typed Pydantic      │
              │  ─ on each tag:                 │  │  instruction over data channel  │
              │    asyncio.create_task(         │  │  topic="visuals"                │
              │      dispatch_action_tag(...))  │  │                                 │
              │  ─ yield cleaned text → TTS     │  │  Verification scheduled         │
              │                                 │  │  (Phase 5a-1/2, fire-and-forget)│
              │  use_tts_aligned_transcript=    │  │                                 │
              │   True → student transcript     │  └─────────────────────────────────┘
              │   mirrors cleaned text          │
              └─────────────┬───────────────────┘
                            │ cleaned text chunks
                            ▼
              ┌─────────────────────────────────────────────────┐
              │  Cartesia TTS (streaming)                       │
              │  ──────────────────────────────────────────────  │
              │  • TTFA ~150ms                                  │
              │  • Audio chunks streamed back continuously       │
              │  • Voice selection + emotion modulation         │
              │  • Cost: ~$0.30-0.60/hr live teaching            │
              └────────────────────────┬────────────────────────┘
                                       │ audio frames
                                       ▼
╔══════════════════════════════════════════════════════════════════════════════════════════════╗
║                              AGENT SPEAKS BACK TO STUDENT                                     ║
║          "Great question! The hypotenuse is the longest side of a right triangle…"            ║
║                  (with inline <highlight target="hypotenuse"/> firing mid-sentence)           ║
╚══════════════════════════════════════════════════════════════════════════════════════════════╝

                                    TURN ROUND-TRIP TARGET: ≤ 2.0s

  Interruption path: student speaks during agent's TTS →
    Silero VAD detects → LiveKit aborts TTS audio + cancels LLM stream →
    in-flight tool calls dropped → student transcript begins streaming →
    next llm_node turn fires with new context (and any perception feedback drained).

  Mid-sentence pointing path: LLM emits "<highlight target='x'/>" in narration →
    tts_node parser extracts → asyncio task dispatches publish over visuals channel →
    frontend renders pulse within ~300ms of token emission →
    cleaned text continues to TTS (student hears narration uninterrupted).
```

### 6.3 The pipeline (Deepgram → Anthropic → Cartesia)

LiveKit Agents handles the orchestration:
1. Audio chunks from WebRTC → Silero VAD detects speech start/end.
2. Deepgram STT streams transcript chunks → committed to `chat_ctx.history` on turn end.
3. `Agent.llm_node(chat_ctx, tools, model_settings)` invoked → LLM streams response.
4. Each LLM chunk: tool calls dispatched immediately (parallel `function_tool` invocations); text chunks go through `Agent.tts_node` → Cartesia → audio frames.
5. Audio frames stream back to WebRTC.

### 6.4 `llm_node` override — perception feedback drain (Phase 5a-1)

```python
async def llm_node(self, chat_ctx, tools, model_settings):
    drain_perception_feedback(self._teaching_ctx, chat_ctx)
    async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
        yield chunk
```

`drain_perception_feedback` (worker.py:142) appends each `PerceptionFeedback` from the queue as a synthetic `role="user"` message with `[PERCEPTION_FEEDBACK]` prefix. The agent's prompt teaches it to recognize this prefix and react. See §8.

Why `role="user"` not `role="system"`: Anthropic Messages API serializes `system` at the top level (not in `messages[]`); a `user` message with a known prefix is more deterministic and gets the LLM's attention immediately.

### 6.5 `tts_node` override — action tag stripping (Phase 4)

```python
async def tts_node(self, text, model_settings):
    def schedule(tag: ActionTag) -> None:
        asyncio.create_task(dispatch_action_tag(session, tag))
    cleaned = strip_action_tags(text, schedule)
    async for frame in Agent.default.tts_node(self, cleaned, model_settings):
        yield frame
```

The LLM emits inline tags in its narration:

> *"Okay, look at the **\<highlight target="hypotenuse"/\>** longest side — that's our hypotenuse."*

`ActionTagParser` (`agent/action_tag_parser.py`) buffers across chunks, handles 256-char overflow, fails silent on malformed/unknown tags. Five verbs: `highlight`, `pulse`, `callout`, `bracket`, `pin`. Dispatched via `livekit/action_tag_dispatch.py` to the same publish path as tool annotations.

Because `use_tts_aligned_transcript=True`, the student-facing transcription mirrors the cleaned TTS text automatically — no separate transcription_node override needed.

### 6.6 Why inline tags AND annotation tools

- Tools (`pin_label_near`, `draw_callout`, `bracket`, `highlight_pulse`) — discrete actions the LLM thinks about.
- Inline tags — pointing flow during natural speech. Lightweight, mid-sentence.

Both go through the same `_publish_visual` path. Both verify through the same Phase 5a-1 annotation perception loop. The agent's prompt teaches when to use which: tags for pointing-while-speaking, tools for explicit annotation actions.

### 6.7 Interruption handling

Silero VAD detects student speech start. LiveKit Agents aborts the current TTS playback and signals the LLM stream to cancel. The agent's response (text + tool calls in-flight) is dropped. The student's transcript begins streaming. The agent then sees the new turn in `chat_ctx.history` and responds.

This is **first-class**. The product depends on it. Magic-moment Beat B (real doubt handling) IS this flow.

---

## 7. The Visual System (The Hardest Problem)

The fundamental tension across all visual design: **accuracy vs speed** (`docs/design/06-board-intelligence-and-latency.md`).

The old deterministic component library was fast but couldn't render IGCSE-grade diversity. Claude generating a `DiagramSpec` from scratch is accurate but takes 5–15s. **A teacher cannot pause mid-sentence for 10 seconds.** The visual system is a layered attempt to get both.

### 7.0a Visual pipeline — master diagram

```text
                       VISUAL PIPELINE (one draw_design_diagram call end-to-end)

  ┌─────────────────────────────────────────────────────────────────────────────────────────┐
  │ Sonnet LLM emits tool call:                                                              │
  │   draw_design_diagram(prompt="Draw a ladder leaning against a wall at 35°")              │
  └────────────────────────────────────────┬────────────────────────────────────────────────┘
                                           │
                                           ▼
                          ┌──────────────────────────────────────┐
                          │  tools.py:draw_design_diagram         │
                          │  ─────────────────────────────────── │
                          │  • eid = tc.board_manager.next_id()   │ → "design-1"
                          │  • Phase 5a-3 retention:              │
                          │     if eid not in original_claims:    │
                          │       original_claims[eid] = prompt   │
                          └────────────────┬─────────────────────┘
                                           │
                                           ▼
                          ┌──────────────────────────────────────┐                       ┌──────┐
                          │  AnticipationEngine.match(prompt,    │                       │CACHE │
                          │                           concept_idx)│ ──────HIT ─────────▶ │ HIT  │
                          │  ─────────────────────────────────── │                       │ <50ms│
                          │  • concept_index-based match (NOT    │                       └──┬───┘
                          │    Jaccard; old Jaccard failed prod) │                          │
                          │  • Hits include: warm-task pre-gens, │                          │
                          │    pre-generated visuals from        │                          │
                          │    curriculum graph (visual_hint)    │                          │
                          └────────────────┬─────────────────────┘                          │
                                           │ MISS                                            │
                                           ▼                                                 │
                          ┌──────────────────────────────────────┐                          │
                          │  design_bridge._dispatch_mode(prompt)│                          │
                          │  ─────────────────────────────────── │                          │
                          │  regex keywords trigger "python":    │                          │
                          │   perpendicular, tangent, intersect, │                          │
                          │   parametric, polar, perpendicular   │                          │
                          │   bisector, exact angle, etc.        │                          │
                          │  Else: "direct" (JSON path)          │                          │
                          └────────┬────────────────────┬────────┘                          │
                                   │                    │                                    │
                          MODE="direct" (JSON)  MODE="python" (sandbox)                      │
                                   │                    │                                    │
                                   ▼                    ▼                                    │
              ┌────────────────────────────┐  ┌────────────────────────────┐                │
              │  generate_design_diagram   │  │  generate_via_python        │                │
              │  ────────────────────────  │  │  ─────────────────────────  │                │
              │  • SYSTEM_PROMPT (JSON)    │  │  • SYSTEM_PROMPT_PYTHON     │                │
              │  • Anthropic Sonnet stream │  │  • Sonnet writes Python     │                │
              │  • LATENCY: 5–15s           │  │    against Canvas DSL +     │                │
              │  • COST: ~$0.10-0.30/diag  │  │    helpers + 5 STEM         │                │
              │  • Output: DiagramSpec     │  │    composites               │                │
              │    JSON (elements, dict,   │  │  • visuals/sandbox.py runs  │                │
              │    parameters, animations) │  │    AST-whitelist execution  │                │
              └────────────┬───────────────┘  │  • LATENCY: 3–8s            │                │
                           │                  │  • COST: same as direct     │                │
                           │                  │  • Outputs DiagramSpec      │                │
                           │                  └────────────┬────────────────┘                │
                           │                               │                                 │
                           ▼                               ▼                                 │
              ┌────────────────────────────────────────────────────────┐                    │
              │  design_bridge cache (in-mem FIFO, ≤64 entries)         │                    │
              │  ──────────────────────────────────────────────────────│                    │
              │  Key = prompt + mode + provider + model + prompt-file  │                    │
              │        mtimes + schema-file mtime                       │                    │
              │  Identical prompts within session → 0ms next time       │                    │
              └────────────────────────────────────┬───────────────────┘                    │
                                                   │                                         │
                                                   ▼                                         ▼
                          ┌──────────────────────────────────────────────────────────────────┐
                          │  DiagramSpec (JSON, Pydantic-typed)                              │
                          │  ───────────────────────────────────────────────────────────────│
                          │  {                                                                │
                          │    "title": "Ladder against wall (35°)",                          │
                          │    "description": "...",                                          │
                          │    "elements": [                                                  │
                          │      {"id": "wall", "type": "svg_line", ...},                     │
                          │      {"id": "ground", "type": "svg_line", ...},                   │
                          │      {"id": "ladder", "type": "svg_line", ...},                   │
                          │      {"id": "angle_arc", "type": "svg_arc", ...}                  │
                          │    ],                                                             │
                          │    "dictionary": {  ◀── Phase 14 diagram-awareness               │
                          │      "wall":         {role: "wall", semantic: "vertical wall"},   │
                          │      "ladder":       {role: "ladder", semantic: "leaning ladder"},│
                          │      "angle_arc":    {role: "angle_marker", semantic: "35° arc"}  │
                          │    },                                                             │
                          │    "parameters": [...],   "animations": [...]                     │
                          │  }                                                                │
                          └──────────────────────────────────┬───────────────────────────────┘
                                                             │
                                                             ▼
                          ┌──────────────────────────────────────────────────────┐
                          │  tc.board_manager.store_design_spec(eid, spec)        │
                          │  tc.board_manager.record(instruction)                 │
                          │  tc.current_diagram_dictionary = spec.dictionary      │
                          │   ◀── now annotation tools can target by role         │
                          │  await _update_agent_prompt(ctx)                      │
                          │   ◀── rebuilds system prompt with new dictionary so   │
                          │       next LLM turn sees available roles              │
                          └────────────────────────────────┬─────────────────────┘
                                                           │
                                                           ▼
                          ┌──────────────────────────────────────────────────────┐
                          │  _publish_visual(ctx, DrawDesignDiagramInstruction)   │
                          │  ─────────────────────────────────────────────────── │
                          │  • Serialize to JSON                                  │
                          │  • Publish over data channel topic="visuals"          │
                          │  • Latency: ~5-20ms in-process + LiveKit fan-out      │
                          └────────────────────────────────┬─────────────────────┘
                                                           │ data channel
                                                           ▼
            ┌─────────────────────────────────────────────────────────────────────┐
            │  BROWSER: useVisualChannel.ts                                        │
            │   → InstructionSwitch.tsx routes to DesignDiagramContent.tsx         │
            │   → SVG + KaTeX + GSAP stroke-reveal animation                       │
            │   → ~600ms render time, hand-drawn feel via Rough.js                 │
            │   → element bounds reported back via topic="bounds" (~150ms)         │
            └────────────────────────────────┬────────────────────────────────────┘
                                             │
                                             ▼
            ┌────────────────────────────────────────────────────────────────────┐
            │  Phase 5a-2 verification scheduling (parallel, fire-and-forget)     │
            │  ─────────────────────────────────────────────────────────────────│
            │  _schedule_diagram_verification(                                    │
            │      tool_name="draw_design_diagram", element_id=eid,                │
            │      claim_text=prompt,                                             │
            │      role_list=[m.role for m in spec.dictionary.values()])          │
            │  ── increments diagram_version[eid]                                 │
            │  ── records DiagramClaim(eid, prompt, "draw…", version)             │
            │  ── two asyncio.create_task()s (intent + layout)                    │
            │     against the same screenshot capture cycle                       │
            │  ── ~1.5s wall, $0.002 cost — see §8 perception loop                │
            └─────────────────────────────────────────────────────────────────────┘

  TOTAL LATENCY:
   • Cache HIT path:        50ms tool dispatch + 600ms render          ≈ 650ms ✓ (≤800ms)
   • Cache MISS direct:     5-15s gen + 50ms publish + 600ms render    ≈ 5-15s (needs voice bridge)
   • Cache MISS python:     3-8s gen + 50ms publish + 600ms render     ≈ 3-8s  (needs voice bridge)
```

### 7.0b Anticipation engine — warm flow

```text
                          ANTICIPATION ENGINE (boot warm + per-concept advance)

  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │ Boot trigger: FeynmanAgent.on_enter (worker.py)                                         │
  │                                                                                          │
  │ Per-concept-advance trigger: tools.py:advance_concept                                    │
  │   → asyncio.create_task(tc.anticipation.warm(plan, start=next_idx, count=3, curriculum)) │
  └─────────────────────────────────────────┬──────────────────────────────────────────────┘
                                            │
                                            ▼
                ┌──────────────────────────────────────────────────────┐
                │  AnticipationEngine.warm(plan, start, count,         │
                │                          curriculum)                  │
                │  ──────────────────────────────────────────────────  │
                │  For each concept in plan[start : start+count]:       │
                │    For each visual_hint in concept (Neo4j) OR        │
                │        visual_suggestion in concept (lesson_plan):    │
                │      generate_design_diagram(prompt) → DiagramSpec    │
                │      cache key: (concept_idx, sub_idx)                │
                │      cache value: DiagramSpec                         │
                │  Audit: "source_graph" or "source_plan"               │
                │  All gen tasks run in parallel.                       │
                │  Cost: 3 concepts × ~2 visuals × ~$0.20 ≈ ~$1.20/hr   │
                │  Latency: parallel; total ~10-15s but overlapped      │
                │     with greeting + first concept teaching.           │
                └──────────────────────────────────────────────────────┘

   CACHE-HIT MATCHING (when tool fires):
     • concept_index-based (not Jaccard — old Jaccard mismatched vocabulary)
     • If exact concept-idx hit, return cached spec.
     • If miss within current concept, try sub_index=0 as fallback.
     • Else → cache miss → design_bridge path.

   DOUBT CACHE (Aanya demo's 4 anticipated doubts):
     • Pre-generated offline + loaded at boot
     • Loaded into tc.anticipation under concept_idx="doubt"
     • Matched at start_doubt_branch by similar-doubt Jaccard
     • Cache-hit rate target: ≥3/4 on the Aanya demo

   FUTURE (Curriculum Phase 12 — NOT BUILT):
     • EVERY concept_node.visual_hint pre-generates DiagramSpec at ingest time
     • Stored in Neo4j as concept.pre_generated_visuals
     • At session boot: warm tasks pull from Neo4j directly, zero LLM gen cost
     • Estimated: eliminates 70% of teaching visual latency
```

### 7.0c Frontend rendering pipeline

```text
                           FRONTEND VISUAL RENDERING PIPELINE

                    (data channel topic="visuals" carries JSON instructions)
                                              │
                                              ▼
              ┌─────────────────────────────────────────────────────────────┐
              │  /livekit/useVisualChannel.ts                                │
              │  ─────────────────────────────────────────────────────────  │
              │  • Subscribes to LiveKit data channel                        │
              │  • Deserializes JSON per contracts/visuals.schema.json       │
              │  • Validates discriminator → instruction type                │
              │  • Pushes to Zustand store                                   │
              └───────────────────────────┬─────────────────────────────────┘
                                          │
                                          ▼
              ┌─────────────────────────────────────────────────────────────┐
              │  /engine/InstructionSwitch.tsx                               │
              │  ─────────────────────────────────────────────────────────  │
              │  switch (instruction.instruction_type) {                     │
              │    case "draw_design_diagram":                               │
              │       → DesignDiagramContent (SLIDE panel)                   │
              │    case "write_equation":                                    │
              │       → NotebookEquationEntry (NOTEBOOK panel)               │
              │    case "highlight_pulse":                                   │
              │       → SlideAnnotationLayer (overlay on SLIDE)              │
              │    ...40+ types                                              │
              │  }                                                            │
              └───────────────────────────┬─────────────────────────────────┘
                                          │
                                          ▼
              ┌─────────────────────────────────────────────────────────────┐
              │  /engine/SyncManager.ts                                      │
              │  ─────────────────────────────────────────────────────────  │
              │  • Inspects instruction.sync_mode:                           │
              │    ─ IMMEDIATE       → render now                            │
              │    ─ VISUAL_FIRST    → render now, TTS waits                 │
              │    ─ AFTER_NEXT_SENTENCE → queue until next TTS sentence-    │
              │      boundary signal (LiveKit transcription events)          │
              │    ─ SPEECH_FIRST    → TTS plays one beat, then render       │
              │    ─ SIMULTANEOUS    → align with current TTS chunk          │
              │    ─ PAUSE           → wait pause_seconds before render      │
              └───────────────────────────┬─────────────────────────────────┘
                                          │
                       ┌──────────────────┴────────────────────┐
                       ▼                                       ▼
              ┌──────────────────────┐               ┌──────────────────────┐
              │ Slide pane (~38%)    │               │ Notebook pane (~62%) │
              │ Canvas/SVG layer     │               │ Vertical stack       │
              │ One diagram          │               │ Entries: equation,   │
              │ Cross-fade swap      │               │ step, section, text, │
              │ Stroke-reveal anim   │               │ answer, page-turn    │
              │ GSAP-driven          │               │ align_groups for `=` │
              │ Rough.js hand-drawn  │               │ KaTeX + indent       │
              │                      │               │                      │
              │ SlideAnnotationLayer │               │ Strike-through swipe │
              │ overlays:            │               │ Answer-box SVG trace │
              │ highlight_pulse,     │               │                      │
              │ pin_label_near,      │               │ Carry-forward from   │
              │ draw_callout,        │               │ prev pages (muted)   │
              │ bracket              │               │                      │
              └──────────────────────┘               └──────────────────────┘
                       │                                       │
                       └──────────────────┬────────────────────┘
                                          │
                                          ▼
              ┌─────────────────────────────────────────────────────────────┐
              │  /engine/whiteboard/BoardCapture.tsx                         │
              │  ─────────────────────────────────────────────────────────  │
              │  • Subscribes to data channel topic="board_capture"          │
              │  • On request: html-to-image PNG capture of whiteboard       │
              │  • Resizes to 512×288 (cheap Haiku input)                    │
              │  • Encodes b64 → publishes back over board_capture           │
              │  • Round-trip latency: ~150ms typical                        │
              │  • Used by Phase 5a perception loop                          │
              └─────────────────────────────────────────────────────────────┘

   Also: every element reports its bounding box back via topic="bounds"
   after rendering, so backend BoardManager.update_bounds(report) knows
   where elements actually landed (used by annotation resolution).
```

### 7.1 Split-board layout (`docs/design/10-split-board.md` — shipped Apr 2026)

**Insight**: real teachers don't reason about 2D space. They use two panels with distinct rendering semantics.

```
┌────────────────────┬───────────────────────────────────────┐
│                    │                                       │
│   SLIDE (38%)      │   NOTEBOOK (62%)                      │
│                    │                                       │
│   One diagram at   │   Vertical stack of entries:          │
│   a time. Cross-   │   - equation (KaTeX, align at `=`)    │
│   fade + stroke-   │   - step (indent, ordered)            │
│   reveal swap.     │   - section_header (bold, larger)     │
│                    │   - text (paragraph)                  │
│   Pre-generated    │   - answer (boxed, highlighted)       │
│   via anticipation │   - strikethrough (mistake)           │
│   when possible.   │                                       │
│                    │   page-turn animation                 │
│                    │   align_groups for `=`                │
│                    │   carry-forward from prev pages       │
└────────────────────┴───────────────────────────────────────┘
```

Per-concept modes: `split` (80%+ of teaching), `slide_full` (apparatus intro), `notebook_full` (pure derivation).

**Phase 7 next**: delete ~2500 LOC of legacy 2D-layout machinery (spatial_solver, placement_executor, scenario_planner, board_flow, board_snapshot, board_verifier zone logic, size_estimator). Replaced by the simpler `panel` field on every instruction.

### 7.2 Typed visual instructions

**File**: `backend/src/feynman/visuals/schemas.py` (~23K LOC of Pydantic models). 40+ instruction types as a discriminated union.

Categories:
- **Slide-targeted**: `DrawDesignDiagramInstruction`, `ModifyDesignDiagramInstruction`, `DrawSceneInstruction`, `DrawDiagramInstruction`, `ShowGraphInstruction`, `ShowEquationInstruction`, `ShowTextInstruction`.
- **Notebook-targeted**: `WriteEquationInstruction`, `WriteStepInstruction`, `WriteTextInstruction`, `WriteSectionInstruction`, `WriteAnswerInstruction`, `StrikethroughInstruction`, `NewPageInstruction`.
- **Annotations** (overlay on slide): `HighlightInstruction`, `HighlightPulseInstruction`, `HighlightWalkInstruction`, `AnnotateInstruction`, `PinLabelInstruction`, `DrawCalloutInstruction`, `BracketInstruction`.
- **Board control**: `ClearInstruction`, `SwitchBoardInstruction`, `ScrollViewInstruction`.

Every instruction has:
- `instruction_type` (discriminator)
- `element_id` (server-generated)
- `panel` (SLIDE | NOTEBOOK)
- `sync_mode` (IMMEDIATE | VISUAL_FIRST | AFTER_NEXT_SENTENCE | SPEECH_FIRST | SIMULTANEOUS | PAUSE)
- `placement` (optional `PlacementIntent` near another element)

Serialized to JSON via the LiveKit data channel (topic `"visuals"`). Frontend deserializes per `contracts/visuals.schema.json` and routes via `engine/InstructionSwitch.tsx`.

### 7.3 Design agent (the LLM-as-author approach)

**Separate codebase**: `design_agent/backend/` (`agent.py`, `schema.py`, `prompts.py`, `prompts_python.py`).

When the teaching agent calls `draw_design_diagram(prompt="ladder against wall")`:

1. `tools.py:draw_design_diagram` checks `AnticipationEngine` cache.
2. On miss: `feynman.agent.design_bridge.generate_design_diagram(prompt)`.
3. design_bridge calls Anthropic with `prompts.SYSTEM_PROMPT` (direct JSON path) or `prompts_python.SYSTEM_PROMPT` (Python DSL path).
4. Returns a full `DiagramSpec`: SVG elements, KaTeX equations, interactive parameters, `dictionary` mapping semantic roles → element IDs.
5. design_bridge has an in-memory FIFO cache (≤64 entries, OrderedDict) keyed by prompt + mode + provider + model + prompt-file mtimes. Hot path on identical prompts within a session.

**The accuracy/speed tension lives here**: 5–15s on cache miss. We attack it on three fronts.

### 7.4 Python sandbox DSL (`docs/design/16` Phase 3 — shipped)

For diagrams needing parametric geometry (perpendiculars, tangents, intersections, specific angles), the agent passes `mode="python"`. The LLM writes Python code against a constrained `Canvas` API:

```python
from canvas_dsl import Canvas, polar, perpendicular_to

c = Canvas(width=900, height=650)
ramp = c.add_line(origin=(100, 500), polar(35, 600), color="#888")
block = c.add_rect(corner=polar(35, 350) - (40, 80), size=(80, 80))
normal = c.add_arrow(from_=block.center_bottom, perpendicular_to(ramp, length=120))
```

The code executes in a **whitelisted AST sandbox** (`visuals/sandbox.py`) — not `RestrictedPython`. Subprocess isolation deferred. ~50 primitives + helpers + 5 STEM composites (`add_right_triangle`, `add_free_body_diagram`, `add_lens`, `add_ray`, `add_lewis_structure`). All auto-register dictionary entries with stable roles.

**Why**: geometry is hallucinated when the LLM writes JSON directly. Python sandbox makes geometry exact and cacheable. Auto-mode dispatch (`_dispatch_mode` regex in design_bridge) routes parametric prompts to python automatically.

### 7.5 Anticipation engine (warm cache)

**File**: `agent/anticipation.py` (758 LOC).

At session boot (`on_enter`), fires `anticipation.warm(plan, start=0, count=3, curriculum)`. Pre-generates `DiagramSpec` for the first 3 concepts using:
- Concept node's `visual_hint` from the curriculum (Neo4j) if present.
- Falls back to `visual_suggestions` from the lesson plan.

When `draw_design_diagram(prompt=X)` fires, the cache is matched against `(concept_index, sub_index)` keys. Modern matching is **concept-index-based, NOT Jaccard** (the old Jaccard matcher failed in production — `docs/design/07`).

Pre-generated diagrams from the curriculum pipeline (§9) bypass live LLM-gen entirely. Cache-hit latency: ~600–800ms (frontend render time, not LLM). **The Aanya demo magic moment depends on this**: 3 main diagrams + 4 likely doubts all cache-hit.

### 7.6 Modify tool

`modify_design_diagram(target_id, modification)` — 1–3s vs 5–15s for regeneration. Pass existing spec to Claude with the modification request. Used heavily by the Phase 5a perception recovery loop (§8).

### 7.7 Annotations: 4 tools + dictionary resolution

**Files**: `agent/tools.py` (`pin_label_near`, `draw_callout`, `bracket`, `highlight_pulse`).

After `draw_design_diagram` lands, the `DiagramSpec.dictionary` is stored on `tc.current_diagram_dictionary`. The agent can target elements by **semantic role** (e.g., `"hypotenuse"`) instead of raw ID. `DictionaryResolver` (in tools.py) maps role → element_id at publish time. Frontend renders the annotation overlay (`SlideAnnotationLayer.tsx`).

This is `docs/design/14-agent-diagram-awareness.md`. Eliminates "agent guesses wrong element id" — semantic dictionary is cheaper, faster, and more reliable than a vision-LLM lookup.

### 7.8 Frontend rendering (overview)

- `engine/Canvas.tsx`, `engine/VisualScene.tsx` — the main render orchestrator.
- `engine/InstructionSwitch.tsx` — routes instruction type → renderer component.
- `engine/whiteboard/content/DesignDiagramContent.tsx` — renders DiagramSpec (SVG + KaTeX overlays + interactive sliders).
- `engine/SyncManager.ts` — deferred queue for `AFTER_NEXT_SENTENCE` instructions; releases at TTS sentence boundary.
- `engine/whiteboard/BoardCapture.tsx` — captures the rendered board to PNG on data-channel request (for vision verification).
- Rough.js gives hand-drawn aesthetic. GSAP for animations. KaTeX for equations. Chart.js for graphs.

### 7.9 The four-front attack on accuracy/speed

| Front | What it does | Status |
|---|---|---|
| **Anticipation engine** | Pre-gen 3 concepts + 4 doubts per concept ahead of time | Shipped |
| **Modify tool** | 1–3s incremental update vs 5–15s regen | Shipped |
| **Python sandbox DSL** | Parametric geometry computes exactly | Shipped (Phase 3) |
| **STEM composites** | One call → right_triangle / FBD / lens / Lewis | Shipped (Phase 3-5) |
| **Pre-generated DiagramSpecs from curriculum pipeline** | ~70% of teaching visuals cache-hit | DESIGNED (curriculum pipeline §9 Phase 12 not built) |
| **VL-JEPA self-hosted perception** | ~142ms sub-sentence correction | DESIGNED (Phase 5b, post-traction) |

---

## 8. The Perception Loop (Phase 5a — Just Shipped)

This section is what landed in `87e6957` and is **fresh state**.

### 8.1 Why

The agent can claim things that aren't true. "I drew a free body diagram of a block on a ramp" — but the design agent produced a block on flat ground. "I'm highlighting the hypotenuse" — but the annotation landed on the right-angle marker. Even worse: a diagram from Concept 3 sitting stale on the board during Concept 7. No human-in-the-loop can catch this in real time.

Phase 5a wires up a fire-and-forget vision loop: Haiku (cheap, fast) watches the rendered board and feeds findings back to the LLM via an `[PERCEPTION_FEEDBACK]` channel. The agent's prompt teaches it to acknowledge briefly + fix. The loop closes.

### 8.2 BoardVerifier — four modes

**File**: `agent/board_verifier.py` (1341 LOC).

All four modes share one screenshot-capture path (`_request_screenshot()` over the data channel topic `"board_capture"`):

| Mode | Method | Triggered by | Prompt | What it checks |
|---|---|---|---|---|
| Layout quality | `request_verification` | (legacy, mostly audit-only) | `_VERIFY_PROMPT` | overlap, spacing, cut-off, readability |
| **Annotation accuracy (5a-1)** | `request_annotation_verification` | every annotation tool + every inline action tag | `_VERIFY_ANNOTATION_PROMPT` | did the annotation land on the claimed element? |
| **Diagram intent (5a-2)** | `request_diagram_intent_verification` | every `draw_design_diagram` + `modify_design_diagram` | `_VERIFY_DIAGRAM_INTENT_PROMPT` | does the diagram match the agent's claim? |
| **Drift check (5a-3)** | `request_drift_check` | 30s periodic loop in worker.py | `_VERIFY_DRIFT_PROMPT` | (a) concept_fit: is the board still appropriate for the current concept? (b) cumulative_integrity: did each diagram drift from its ORIGINAL claim across modifications? |

Model: `claude-haiku-4-5-20251001`. Cost: ~$0.001–0.002 per call.

### 8.2a Perception loop — end-to-end flow

```text
                            PERCEPTION LOOP (Phase 5a — shipped)

  ╔══════════════════════════════════════════════════════════════════════════════════════════╗
  ║  TRIGGER PATHS (4 of them, all fire async via asyncio.create_task)                       ║
  ║                                                                                            ║
  ║  ─ Annotation tool fires (pin_label_near, draw_callout, bracket, highlight_pulse,         ║
  ║    annotate, highlight_diagram_part, highlight_walk):                                     ║
  ║      → _schedule_annotation_verification(...) → request_annotation_verification          ║
  ║         [5a-1, febe268]                                                                   ║
  ║                                                                                            ║
  ║  ─ Inline action tag dispatched (mid-stream <highlight target=.../>):                     ║
  ║      → action_tag_dispatch._schedule_verification_from_tag → same as above                ║
  ║         [5a-1]                                                                            ║
  ║                                                                                            ║
  ║  ─ draw_design_diagram or modify_design_diagram fires:                                    ║
  ║      → _schedule_diagram_verification(...) → 2 parallel tasks:                            ║
  ║         • request_diagram_intent_verification  (intent: claim vs render)                  ║
  ║         • request_verification (layout: overlap, cut-off, etc.)                           ║
  ║         [5a-2, a9cf255]                                                                   ║
  ║                                                                                            ║
  ║  ─ Every 30s periodic loop in worker.py:_periodic_drift_check:                            ║
  ║      → _should_run_drift_check (cheap pre-flight)                                         ║
  ║      → _run_drift_check → request_drift_check                                             ║
  ║         [5a-3, 87e6957]                                                                   ║
  ╚══════════════════════════════════════════════════════════════════════════════════════════╝
                                          │
                                          │  all paths converge into BoardVerifier
                                          ▼
       ┌───────────────────────────────────────────────────────────────────────────────────┐
       │  BoardVerifier method (one of four)                                                │
       │                          [agent/board_verifier.py, ~1341 LOC]                      │
       │  ──────────────────────────────────────────────────────────────────────────────  │
       │                                                                                    │
       │  STEP 1 — Pre-flight (drift only):                                                 │
       │    if empty board + empty concept desc: return None (no Haiku call)               │
       │                                                                                    │
       │  STEP 2 — Screenshot capture:                                                      │
       │    request_id = uuid4()                                                            │
       │    future = loop.create_future()                                                   │
       │    self._pending[request_id] = future                                              │
       │    await self._publish(JSON({                                                      │
       │      "type": "capture_board",                                                      │
       │      "request_id": request_id,                                                     │
       │      "max_width": 512, "max_height": 288                                           │
       │    }), topic="board_capture")                                                      │
       │    ── frontend BoardCapture.tsx receives request                                   │
       │    ── frontend rasterizes whiteboard to PNG (~50-100ms)                            │
       │    ── frontend publishes back over board_capture topic                             │
       │    ── data channel handler in worker.py calls resolve_capture(request_id, b64)     │
       │    ── future resolved → screenshot bytes available                                 │
       │    Latency: ~100-500ms round-trip                                                  │
       │    Timeout: 5s (returns None on timeout, audited)                                  │
       │                                                                                    │
       │  STEP 3 — Build prompt + call Haiku:                                               │
       │    prompt = _VERIFY_*_PROMPT.format(claim=truncated, role_list=..., ...)           │
       │    response = await anthropic.messages.create(                                     │
       │      model="claude-haiku-4-5-20251001",                                            │
       │      max_tokens=400-500,                                                           │
       │      messages=[{"role": "user", "content": [                                       │
       │        {"type": "image", "source": {"type": "base64", "data": screenshot}},        │
       │        {"type": "text", "text": prompt}                                            │
       │      ]}]                                                                            │
       │    )                                                                                │
       │    Latency: 600-1500ms typical                                                     │
       │    Cost: ~$0.001/call                                                              │
       │                                                                                    │
       │  STEP 4 — Parse JSON response with graceful fallback:                              │
       │    _parse_*_response(text, ...) → typed VerificationResult                         │
       │    On parse failure: conservative defaults (no false-positive feedback)            │
       │                                                                                    │
       │  STEP 5 — Decide whether to fire feedback:                                         │
       │    Annotation (5a-1): score ≤ 2 AND suggested_target exists                       │
       │    Diagram intent (5a-2): score ≤ 2 AND suggested_modification exists             │
       │    Layout (5a-2): score ≤ 2 AND actionable FixActions                             │
       │    Drift (5a-3): is_consistent == False                                           │
       │                                                                                    │
       │  STEP 6 — Audit + (if firing) invoke on_feedback callback:                        │
       │    self._audit.record("annotation_verification", "result", ...)                   │
       │    if on_feedback is not None and condition_met:                                  │
       │      feedback = PerceptionFeedback(...)  # right flavour                          │
       │      on_feedback(feedback, result)                                                │
       └───────────────────────┬───────────────────────────────────────────────────────────┘
                               │
                               ▼
       ┌───────────────────────────────────────────────────────────────────────────────────┐
       │  on_feedback closure (built by tool helper, captures `concept_index`)              │
       │  ──────────────────────────────────────────────────────────────────────────────  │
       │  def _on_feedback(fb, _result):                                                    │
       │      # STALE-GUARD: concept may have advanced while vision ran                     │
       │      if tc.current_concept_index != concept_index:                                 │
       │          tc.audit.record("*_check", "feedback_stale", "")                          │
       │          return                                                                     │
       │                                                                                     │
       │      # BUDGET CHECK:                                                                │
       │      #  • 5a-1 + 5a-2 share 2/concept budget (perception_feedback_budget_used)     │
       │      #  • 5a-3 has separate 1/concept budget (drift_feedback_budget_used)          │
       │      if budget_used >= cap:                                                         │
       │          tc.audit.record(..., "feedback_budget_full", "")                          │
       │          return                                                                     │
       │                                                                                     │
       │      tc.perception_feedback_queue.append(fb)                                       │
       │      tc.<budget>[concept_index] += 1                                               │
       └───────────────────────┬───────────────────────────────────────────────────────────┘
                               │
                               │ feedback now sits in tc.perception_feedback_queue
                               │ (waits for next LLM turn)
                               ▼
       ┌───────────────────────────────────────────────────────────────────────────────────┐
       │  NEXT LLM TURN — worker.py:llm_node                                                │
       │  ──────────────────────────────────────────────────────────────────────────────  │
       │  async def llm_node(self, chat_ctx, tools, model_settings):                       │
       │      drain_perception_feedback(self._teaching_ctx, chat_ctx)                      │
       │      # drain_perception_feedback:                                                  │
       │      #   for fb in queue:                                                          │
       │      #     chat_ctx.add_message(role="user", content=fb.as_chat_note())            │
       │      #   queue.clear()                                                              │
       │      #                                                                              │
       │      # PerceptionFeedback.as_chat_note() branches on tool_name:                    │
       │      #   "highlight_pulse" / annotation → "[PERCEPTION_FEEDBACK] ... Re-point now: │
       │      #                                     <highlight target='X'/>"                │
       │      #   "draw_design_diagram"/...     → "[PERCEPTION_FEEDBACK] ... Fix it now:    │
       │      #                                     modify_design_diagram(target_id=..., …)"│
       │      #   "periodic_drift_check"        → "[PERCEPTION_FEEDBACK] Drift detected     │
       │      #                                     during concept '...'. Kind: ...        │
       │      #                                     Suggested: ..."                          │
       │      async for chunk in Agent.default.llm_node(self, chat_ctx, tools, …):         │
       │          yield chunk                                                                │
       └───────────────────────┬───────────────────────────────────────────────────────────┘
                               │
                               ▼
       ┌───────────────────────────────────────────────────────────────────────────────────┐
       │  Sonnet LLM sees [PERCEPTION_FEEDBACK] notes in chat_ctx history.                  │
       │  Prompt teaches it to:                                                             │
       │   1. Acknowledge briefly ("let me adjust…")                                        │
       │   2. Fire the suggested correction (inline tag re-point OR modify call            │
       │      OR clear stale diagram)                                                       │
       │   3. Continue lesson — modification triggers re-verification automatically        │
       │                                                                                     │
       │  RECOVERY EXPECTED RATES:                                                          │
       │   • 5a-1 annotation: ~70-80% catch, ~85% recovery                                 │
       │   • 5a-2 diagram intent: ~75% catch, ~70% recovery                                │
       │   • 5a-3 concept_fit drift: ~80% catch, ~70% recovery                             │
       │   • 5a-3 cumulative_integrity: ~65% catch, ~55% recovery (LLM-translation flaky)  │
       └───────────────────────────────────────────────────────────────────────────────────┘

   TOTAL CYCLE TIME:
     • Verification fires (background) — student doesn't perceive any pause
     • Haiku result returns ~1-1.5s later
     • Feedback enqueues, awaits next LLM turn
     • Next student utterance triggers turn typically 3-30s later
     • Recovery applies as next turn's response → student sees it as natural conversation flow

   COST PER FEEDBACK CYCLE:
     • Screenshot capture:       ~$0 (free, already-rendered)
     • Haiku verification:       ~$0.001
     • Possible Sonnet re-call:  ~$0.05 (normal LLM turn)
     • TOTAL:                    ~$0.05 (dominated by the Sonnet turn that would have
                                          happened anyway)

   COMBINED PHASE 5A COST: $0.30-0.34/hr typical, $0.44-0.48/hr worst case.
     (within $0.50/hr subsystem cap)
```

### 8.3 The PerceptionFeedback queue + `llm_node` injection

When a verification mode finds a problem and a usable suggestion exists, it appends to `tc.perception_feedback_queue`:

```python
@dataclass(frozen=True)
class PerceptionFeedback:
    tool_name: str
    original_claim: str
    score: int
    issue: str
    # Annotation flavour (5a-1):
    suggested_target: str | None
    suggested_tag_syntax: str
    # Diagram flavour (5a-2):
    suggested_modification: str | None
    target_diagram_id: str | None
    # Drift flavour (5a-3):
    drift_kind: str | None         # "concept_fit" | "cumulative_integrity" | "both"
    suggested_action: str          # free-form remediation

    def as_chat_note(self) -> str:
        # Branches on tool_name → annotation / diagram / drift format
        ...
```

On next `llm_node` call, `drain_perception_feedback` appends each as a synthetic `user` message:

```
[PERCEPTION_FEEDBACK] Your previous highlight_pulse on 'hypotenuse' missed (score 2/5).
Issue: landed on right-angle marker. Suggested target: side_AB.
Re-point now: <highlight target="side_AB"/>
```

or

```
[PERCEPTION_FEEDBACK] Drift detected during concept 'Right-triangle trigonometry'.
Kind: cumulative_integrity. design-2 was originally "free body diagram of a block
on a 30° ramp" but the ramp has been edited away. Suggested:
modify_design_diagram(target_id="design-2", modification="Restore the ramp at 30°")
```

The agent's prompt (in `prompts.py`) teaches it to:
1. Acknowledge briefly ("let me adjust" or "actually, ...") so the student knows the correction is intentional, not glitchy.
2. Fire the suggested correction (re-point with the inline tag, or call `modify_design_diagram`, or clear the stale diagram).
3. Continue — modification triggers re-verification automatically.

### 8.4 Budgets + dedup (production hardening)

Per-concept budget caps prevent retry spirals:
- 5a-1/5a-2 share **2 per concept** (annotation + diagram intent + severe layout).
- 5a-3 drift has **1 per concept** (separate budget so drift doesn't crowd corrective feedback or vice versa).

Per-(element_id, version, concept) dedup prevents thrashing:
- 5a-2 increments `diagram_version` on every modify; verification keyed by version.
- 5a-3 state-hash dedup: `compute_drift_state_hash(concept, sorted_element_ids, versions)` — same hash → skip the Haiku call entirely. Catches ~60% of unchanged ticks in typical sessions.

Stale-guard: every `on_feedback` closure captures `concept_index` and re-checks `tc.current_concept_index == concept_index` at fire time. Mid-flight vision results from an advanced concept are dropped + audited.

### 8.5 Three-factor scorecard

| Mode | Precision | Latency | Cost |
|---|---|---|---|
| 5a-1 annotation | ~70–80% catch + ~85% recovery | zero hot-path | $0.06–0.12/hr |
| 5a-2 diagram intent | ~75% catch + ~70% recovery | zero hot-path (2 parallel Haiku calls per event) | $0.08–0.12/hr add |
| 5a-3 drift | ~80% concept_fit + ~65% cumulative_integrity catch | zero hot-path (30s cadence, hash-dedup) | ~$0.10/hr typical |
| **Combined 5a** | | | **$0.30–0.34/hr typical, $0.44–0.48/hr worst** |

Well within the $0.50/hr per-subsystem cap.

### 8.6 Phase 5b — the future end-state (vision)

VL-JEPA self-hosted (video joint embedding predictive architecture). ~142ms latency. Enables **sub-sentence correction** — the agent's word stream can be corrected mid-utterance, not just at the next turn. Combined with TTS aligned transcripts + barge-in, this would let the agent self-interrupt: *"...this is the hypoten— sorry, this side here is the hypotenuse."*

Requires GPU infra. Cost ~$0.20–0.50/hr at scale. Explicitly **post-traction**.

---

## 9. The Curriculum System (Designed, Partial)

`docs/design/08-curriculum-graph-pipeline.md` — 13 phases, design complete, implementation deferred until Aanya demo validates magic moment.

### 9.1 Why a curriculum graph

The lesson IS the curriculum. Not pre-baked scripts. The graph encodes:
- **Concepts** with prerequisite/leads_to/example_of relationships.
- **Salience** (static rule-based + structural PageRank + dynamic from teaching usage).
- **Visual hints** that drive pre-generation.
- **Anchors**: section numbers, figure references, example numbers from the source textbook.

### 9.2 v0 scope (rescoped under consumer pivot)

Single subject: **IGCSE 0580 Mathematics**. One textbook (the official Cambridge syllabus textbook). Past-paper archive. v1 expands to Physics 0625 → Chem 0620 → Bio 0610.

### 9.2a Curriculum pipeline — 13 phases data flow (offline)

```text
                  CURRICULUM INGESTION PIPELINE — OFFLINE (NOT YET BUILT)
                  Run once per textbook, output seeds Neo4j curriculum graph

  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │  INPUT: IGCSE Cambridge 0580 Mathematics PDF (~500 pages, ~200 figures)                 │
  │  Sister inputs: past papers (Paper 2 / Paper 4), syllabus document, marking schemes     │
  └────────────────────────────────────────────────┬───────────────────────────────────────┘
                                                   │
                                                   ▼
   PHASE 1: Foundation                  ┌────────────────────────────────────────────┐
   ──────────────────                   │  Pydantic models for ConceptNode,           │
   no LLM                                │  ChapterNode, ConceptEdge.                  │
   ~0.5d                                 │  Neo4j schema init (Cypher constraints,    │
                                         │  indexes on uid + topic_name).             │
                                         │  Stable ID generation (hash-based).        │
                                         └────────────────────────────────────────────┘
                                                   │
                                                   ▼
   PHASE 2: Book Skeleton                ┌────────────────────────────────────────────┐
   ────────────────                      │  Single LLM call (Anthropic Opus,           │
   Opus, $5-15                            │  ~200K input tokens) extracts                │
   ~0.5d                                 │  entire book's structure:                   │
                                         │   • Chapters (uid, title, page_range)       │
                                         │   • Sections (numbered: 1.1, 1.2, ...)      │
                                         │   • Figure references                        │
                                         │   • Example references                       │
                                         │  Output: BookSkeleton (no concept content)   │
                                         └────────────────────────────────────────────┘
                                                   │
                                                   ▼
   PHASE 3: Anchor Extraction            ┌────────────────────────────────────────────┐
   ─────────────                         │  Deterministic regex (pre-LLM):              │
   no LLM                                │   • Section numbers ("1.2.1", "§3.4")        │
   ~0.5d                                 │   • Figure refs ("Figure 1.3")               │
                                         │   • Example refs ("Example 2.5")             │
                                         │   • Equation labels                          │
                                         │  Output: anchors set per chapter             │
                                         │  Purpose: EXTRACTION FLOOR — every numbered  │
                                         │  section must have ≥1 ConceptNode at the    │
                                         │  end of pipeline.                            │
                                         └────────────────────────────────────────────┘
                                                   │
                                                   ▼
   PHASE 4: Chapter Extraction           ┌────────────────────────────────────────────┐
   ────────────                          │  Book-aware two-pass LLM extraction         │
   Opus, $1-3/ch                          │   per chapter (parallel):                    │
   ~3d                                   │     Pass 1 (structure): Opus extracts        │
                                         │       concept boundaries, types              │
                                         │       (DEFINITION, FORMULA, EXAMPLE,         │
                                         │       DERIVATION, ...).                       │
                                         │     Pass 2 (content): Opus fills in           │
                                         │       summary, prerequisites, leads_to.       │
                                         │  Each pass receives BookSkeleton + anchors   │
                                         │  for that chapter as context.                │
                                         │  Output: per-chapter ConceptNode list +     │
                                         │  ConceptEdge list                            │
                                         └────────────────────────────────────────────┘
                                                   │
                                                   ▼
   PHASE 5: Structural Validation        ┌────────────────────────────────────────────┐
   ─────────────                         │  Deterministic checks against anchors:       │
   no LLM (gap-fill                       │   • Every numbered section has ≥1 concept?  │
   uses Opus)                             │   • Every figure ref resolves to a concept? │
   ~1d                                   │   • Every example ref?                       │
                                         │  Gaps trigger gap-fill loop:                 │
                                         │   • Opus called with gap description +      │
                                         │     surrounding context → fills missing     │
                                         │   • Loop until all anchors satisfied OR     │
                                         │     5 iterations exhausted (flag for human) │
                                         └────────────────────────────────────────────┘
                                                   │
                                                   ▼
   PHASE 6: Entity Resolution            ┌────────────────────────────────────────────┐
   ──────────                            │  Within each chapter: hash-based chunk       │
   no LLM (Haiku                          │  merging.                                    │
   for ambiguous)                         │  Identifies concepts that appear in         │
   ~1d                                   │  multiple sections of same chapter,         │
                                         │  merges into one node with all references.  │
                                         │  Ambiguous merges → Haiku judge.            │
                                         └────────────────────────────────────────────┘
                                                   │
                                                   ▼
   PHASE 7: Book Unification             ┌────────────────────────────────────────────┐
   ─────────                             │  Cross-chapter resolve: same concept across  │
   Haiku for sim                          │  chapters merges via embedding similarity.   │
   ~1d                                   │  Hierarchy: parent-child links inferred from│
                                         │  section numbering.                          │
                                         │  Shared concept detection (across topics).   │
                                         └────────────────────────────────────────────┘
                                                   │
                                                   ▼
   PHASE 8: Neo4j Ingestion              ┌────────────────────────────────────────────┐
   ───────                               │  Deterministic Cypher MERGE statements:      │
   no LLM                                │   MERGE (:Concept {uid, topic_name,          │
   ~1d                                   │           summary, visual_hint, ...})        │
                                         │   MERGE (a)-[:PREREQUISITE]->(b)             │
                                         │   MERGE (a)-[:LEADS_TO]->(b)                 │
                                         │   MERGE (a)-[:EXAMPLE_OF]->(b)               │
                                         │  Embeddings generated for similarity search. │
                                         │  Reference: PMG json_to_cypher pattern.      │
                                         └────────────────────────────────────────────┘
                                                   │
                                                   ▼
   PHASE 9: Salience Scoring             ┌────────────────────────────────────────────┐
   ─────────────                         │  Three-component scoring:                    │
   no LLM                                │   • Static: rule-based (concept_type weight, │
   ~1d                                   │     summary length, mention frequency)       │
                                         │   • Structural: PageRank over the edge graph │
                                         │   • Dynamic: from teaching telemetry         │
                                         │     (post-launch — initially 0)              │
                                         │  Higher salience = taught more prominently. │
                                         └────────────────────────────────────────────┘
                                                   │
                                                   ▼
   PHASE 10: Semantic Validation         ┌────────────────────────────────────────────┐
   ─────────                             │  Sonnet spot-checks on random 5% sample:     │
   Sonnet, $5-10                          │   • Is summary accurate to source PDF?       │
   ~1d                                   │   • Are prerequisite edges sound?            │
                                         │   • Are visual_hints meaningful?             │
                                         │  Failure rate < 5% target.                  │
                                         └────────────────────────────────────────────┘
                                                   │
                                                   ▼
   PHASE 11: Pipeline + CLI              ┌────────────────────────────────────────────┐
   ──────                                │  Glue + DX:                                  │
   ~1d                                   │   $ lecture-pipeline ingest-book              │
                                         │       <pdf> --subject math --output neo4j   │
                                         │   Resumable. Idempotent. Logs every phase.  │
                                         └────────────────────────────────────────────┘
                                                   │
                                                   ▼
   PHASE 12: Visual Pre-Generation       ┌────────────────────────────────────────────┐
   ──────────                            │  THE HIGH-LEVERAGE PHASE.                   │
   Sonnet design_                         │  For every Concept with visual_hint:         │
   agent calls,                           │   • design_bridge.generate_design_diagram   │
   ~10-20s each                           │   • DiagramSpec stored on                   │
   $0.10-0.30/diag                        │     concept.pre_generated_visuals            │
   ~$50-200 total                         │  At session boot, anticipation warm-task    │
                                         │  pulls from here — ZERO live LLM gen for     │
                                         │  ~70% of teaching visuals.                  │
                                         │  Eliminates the largest source of latency.   │
                                         └────────────────────────────────────────────┘
                                                   │
                                                   ▼
   PHASE 13: Cleanup                     ┌────────────────────────────────────────────┐
   ───                                   │  Delete dead code, migrate Poetry → uv,     │
   ~0.5d                                 │  doc the pipeline, smoke-test full run.     │
                                         └────────────────────────────────────────────┘
                                                   │
                                                   ▼
   OUTPUT: Neo4j curriculum graph populated for one subject (e.g., IGCSE 0580 Math).
   Total LLM cost per subject: ~$100-300 (one-time).
   Total runtime per subject: ~12-24h on a single machine.

   REFERENCE CODEBASE: /Users/yashbansal/proj/patient-medical-graph (PMG)
     branches: feature/deployable-feature-branch, feature/cyper-standardization-updates-v2
     Key files:
       pmg/ingestion/models/extraction_result.py    ─ canonical intermediate format
       pmg/ingestion/extraction_validator.py        ─ structural validation pattern
       pmg/ingestion/extraction_merger.py           ─ entity merge pattern
       pmg/ingestion/json_to_cypher.py              ─ deterministic Cypher gen
       pmg/ingestion/prompts/schema_context.py      ─ schema injection into prompts
       pmg/ingestion/validation/post_processor.py   ─ deterministic post-processing
       pmg/db/schema.py                              ─ Neo4j schema init
       pmg/services/salience/                       ─ salience scoring composite

   ⚠ Pipeline is fully designed; ZERO PHASES BUILT YET. v0 Aanya demo bypasses it
     entirely with hand-authored in-memory LessonPlan.
```

### 9.3 The 13 phases

1. **Foundation** — Pydantic models, Neo4j schema, stable ID generation.
2. **Book Skeleton** — single LLM call extracts entire book's structure (chapters, sections, figures).
3. **Anchor Extraction** — deterministic regex: section numbers, figures, examples (pre-LLM).
4. **Chapter Extraction** — book-aware two-pass LLM extraction (structure → content).
5. **Structural Validation** — completeness checks against anchors + gap-filling loop.
6. **Entity Resolution** — hash-based chunk merging within chapters.
7. **Book Unification** — cross-chapter resolve, hierarchy, shared concept detection.
8. **Neo4j Ingestion** — Cypher generation + embeddings.
9. **Salience Scoring** — static (rule-based) + structural (PageRank) + dynamic (from teaching telemetry, post-launch).
10. **Semantic Validation** — LLM spot-checks on sample.
11. **Pipeline + CLI** — wire everything, `ingest-book` command.
12. **Visual Pre-Generation** — `DiagramSpec` for every concept with `visual_hint`. This eliminates the largest source of visual latency.
13. **Cleanup** — delete dead code, Poetry → uv.

### 9.4 Architecture

- **Three-graph model**:
  - **Curriculum graph** (Neo4j): shared spine across all students.
  - **Dashboard state**: ephemeral, in-session board state (lives in `TeachingContext` + frontend).
  - **Student knowledge graph**: per-student, persistent. See §10.

- **Reference codebase**: `/Users/yashbansal/proj/patient-medical-graph` (PMG) — production-grade patterns for graph ingestion, validation, entity resolution, salience scoring. Adapt patterns, don't copy blindly.

### 9.5 Runtime integration

When a session boots with `topic="Right-triangle trigonometry"`:
1. `curriculum_loader.load_curriculum(topic, subject)` → Cypher query → `CurriculumData(chapter_uid, concepts, relationships, pre_generated_visuals)`.
2. `lesson_plan_from_curriculum(curriculum)` → `LessonPlan(topic, concepts: list[ConceptNode], total_concepts)` ordered by `teaching_order`.
3. `tc.lesson_plan = plan`.
4. `tc.anticipation.warm(plan, start=0, count=3, curriculum)` — uses the rich concept summaries + visual_hints to pre-generate diagrams.
5. `plan_concept(0, curriculum, plan)` async — produces `ConceptTeachingPlan` with beats + checklist.

### 9.6 Status

- Curriculum loading from Neo4j: **implemented** (`agent/curriculum_loader.py`).
- LessonPlan derivation: **implemented**.
- The 13-phase pipeline itself: **NOT IMPLEMENTED**. The Neo4j store is seeded manually or via partial scripts. The whole `data_pre_compute/` package is a WIP.
- For the Aanya demo: hand-authored in-memory LessonPlan (`docs/design/13` Item 1) bypasses Neo4j entirely. The demo doesn't need the pipeline.

This is one of the **largest gaps between design and reality**.

---

## 10. The Knowledge Graph (Per-Student, Vision)

`memory/knowledge-graph.md`. **Designed, not yet implemented.** Critical to the personalization wedge.

### 10.0 Three-graph architecture

```text
                       THREE-GRAPH MODEL  (designed; partial; vision)

  ┌──────────────────────────────────────┐    ┌──────────────────────────────────────┐
  │   1.  CURRICULUM GRAPH               │    │   2.  DASHBOARD STATE (per-session)  │
  │       (shared across all students)   │    │       (ephemeral, in-memory)         │
  │   ────────────────────────────────   │    │   ────────────────────────────────   │
  │   Storage: Neo4j (bolt://)           │    │   Storage: TeachingContext (mem) +   │
  │   Schema:                            │    │            BoardManager + state_mach │
  │     (:Concept)                       │    │   Lifecycle: lives within one LiveKit│
  │       uid, type, summary,            │    │     session, dies on session end     │
  │       visual_hint, page_range,       │    │   ────────────────────────────────   │
  │       difficulty, salience           │    │   Shape:                             │
  │     (:Chapter) uid, title, subject   │    │     • lesson_plan (loaded from #1)   │
  │     -[:PREREQUISITE]->               │    │     • current_concept_index          │
  │     -[:LEADS_TO]->                   │    │     • board_manager (slide stack +   │
  │     -[:EXAMPLE_OF]->                 │    │       notebook entries)               │
  │     -[:PARENT_OF]->                  │    │     • state_machine (branch stack)   │
  │   ────────────────────────────────   │    │     • doubt_orchestrator (checklists)│
  │   Built by: 13-phase ingestion       │    │     • anticipation cache             │
  │     pipeline (§9) — NOT YET BUILT    │    │     • perception_feedback_queue      │
  │   Consumed by:                       │    │     • original_diagram_claims (5a-3) │
  │     • curriculum_loader at boot      │    │     • concept_plans                  │
  │     • anticipation engine warm tasks │    │     • current_diagram_dictionary     │
  │     • concept_planner context        │    │     • active_highlights /            │
  │   Status: schema implemented;        │    │           active_annotations         │
  │     content hand-seeded for v0;      │    │     • audit (SessionAudit)           │
  │     pipeline is highest-leverage     │    │   Status: FULLY IMPLEMENTED          │
  │     post-Aanya-demo work             │    │                                      │
  └──────────────────────────────────────┘    └──────────────────────────────────────┘

                                ┌──────────────────────────────────────┐
                                │   3.  STUDENT KNOWLEDGE GRAPH        │
                                │       (per-student, durable)         │
                                │   ────────────────────────────────   │
                                │   Storage: Neo4j or Postgres TBD     │
                                │     (likely Neo4j — graph-shaped)    │
                                │   Lifecycle: lives for the student's │
                                │     entire account history.          │
                                │   ────────────────────────────────   │
                                │   Schema:                            │
                                │     Layer 1 — Concept Mastery Map    │
                                │       (:Student)-[:HAS_MASTERY]->    │
                                │       (:Concept) with props:         │
                                │         state: not-introduced /      │
                                │                introduced /          │
                                │                partial / solid /     │
                                │                mastered              │
                                │         confidence: 0.0–1.0           │
                                │         last_seen: timestamp         │
                                │         decay_after_days: int        │
                                │                                       │
                                │     Layer 2 — Learning Pattern        │
                                │       (:Student) attrs:               │
                                │         preferred_analogy_type        │
                                │         engagement_signal_history     │
                                │         struggle_loci (concept IDs)   │
                                │         pace_preference                │
                                │                                       │
                                │     Layer 3 — Session History         │
                                │       (:Student)-[:HAD_SESSION]->     │
                                │       (:Session) -[:BRANCH_TREE]-> ...│
                                │         doubts asked + resolved       │
                                │         comprehension check results   │
                                │         re-approach outcomes          │
                                │   ────────────────────────────────   │
                                │   Built by: every session end          │
                                │     (post-session writer)             │
                                │   Consumed by:                        │
                                │     • prompt builder (next session    │
                                │       sees prior struggles)           │
                                │     • lesson_plan derivation          │
                                │       (skip mastered, focus weak)     │
                                │     • analogy selection                │
                                │   Status: SCHEMA DESIGNED, NOT BUILT  │
                                │     v0 stateless — first-session only │
                                └──────────────────────────────────────┘

                              HOW THE THREE GRAPHS COMBINE

           CURRICULUM (#1) is read-only at session time.
           Provides: structure, prerequisites, visual hints, pre-generated diagrams.

                    │
                    │  At boot: load chapter for the topic →
                    │           derive LessonPlan
                    ▼

           DASHBOARD STATE (#2) is in-flight session state.
           Holds: which concept we're on, what's on the board, branch tree, audits.
           Lives in TeachingContext + BoardManager + state_machine.

                    │
                    │  At session end: write outcomes →
                    │  (doubt patterns, comprehension results, time-on-concept)
                    ▼

           STUDENT KNOWLEDGE GRAPH (#3) is durable per-student memory.
           Updated by post-session writer. Read at next session's boot to
           personalize: skip mastered concepts, surface prior struggles,
           apply preferred analogy type.

   ═══════════════════════════════════════════════════════════════════════════════════
   CRITICAL DESIGN PROPERTY: SPARSE-DATA TOLERANCE
   Most students will never ask doubts. Most session outcomes will be uninformative.
   The student knowledge graph stays sparse for most users. The system MUST teach
   beautifully WITH sparse data. Layer 2 (learning patterns) emerges slowly; the
   system should not block on having rich Layer 2 — defaults work.
   ═══════════════════════════════════════════════════════════════════════════════════

   File refs (existing):
     agent/curriculum_loader.py     ─ reads #1 from Neo4j
     agent/lesson_plan.py           ─ derives LessonPlan from #1
     agent/teaching_context.py      ─ holds #2
     agent/board.py + board_state.py ─ holds the visual portion of #2

   File refs (planned):
     knowledge/                     ─ module exists; per-student writer not built
```

### 10.1 Three layers

1. **Concept Mastery Map** — per-subject nodes with states:
   - `not-introduced → introduced → partially-understood → solid → mastered`
   - Each state carries a confidence score (0.0–1.0).
   - Edges mirror the curriculum graph's prerequisite/leads_to.

2. **Learning Pattern Profile** — what works for THIS student:
   - Analogy preference (visual / verbal / numerical / kinesthetic).
   - Engagement patterns (energized after example vs after derivation).
   - Struggle zones (frequent doubt loci, time-to-resolve distributions).

3. **Session History** — full tree/audit trail:
   - Every session's branch tree.
   - Doubt patterns (what they asked, what resolved them).
   - Comprehension check results.
   - Re-approach branches and what worked.

### 10.2 Sparse-data tolerance (THE critical design property)

Most students NEVER ask doubts. Most sessions produce minimal graph updates. **The system must teach beautifully WITH sparse data.** The knowledge graph is **enhancement, not dependency**.

When a quiet student finally speaks up: the doubt-branch mechanism handles it well, and the rare data point is **valuable** — treat it accordingly (record verbatim, surface in next session).

### 10.3 Continuity vs uniqueness

- **Mastery doesn't transfer cross-subject** (knowing trig doesn't mean knowing chemistry).
- **Learning style DOES transfer** (if visual analogies work for math, try them for physics too).
- Hence: per-subject mastery maps, single learning style profile, unified session history.

### 10.4 Status

- Schema designed.
- Persistence not implemented.
- v0 Aanya demo: stateless. No cross-session memory.
- v1+: this is the personalization wedge. Without it, we're not differentiated from ChatGPT-with-diagrams.

---

## 11. Session Lifecycle — Complete Flow of Control

Walk through one teaching session from `entrypoint(ctx)` to clean shutdown. Cite file:line where relevant.

### 11.0 Session lifecycle — sequence diagram (boot → teach → doubt → advance → end)

```text
  FRONTEND     FastAPI       LiveKit         WORKER          Anthropic      Cartesia      Neo4j
  (browser)    (uvicorn)      cloud         (Python)         (Sonnet+Haiku)  (TTS)        (curric)
     │            │             │              │                  │            │             │
─────┴────────────┴─────────────┴──────────────┴──────────────────┴────────────┴─────────────┴────
STAGE 1: Session creation
     │  POST /sessions      │             │              │                  │            │
     │ ──────────────────▶ │             │              │                  │            │
     │                      │  create room+token         │                  │            │
     │                      │ ─────────────▶│              │                  │            │
     │                      │ ◀────token────│              │                  │            │
     │  ◀───{room,token}───│             │              │                  │            │
     │                                                                                       │
STAGE 2: Frontend joins room
     │                                  │              │                  │            │
     │ ─────WebRTC join───▶│              │                  │            │
     │                                  │ ─kick worker(rtc_session)─▶│            │
     │                                                                                       │
STAGE 3: Worker boots (entrypoint)
     │                                                 │                  │            │
     │                                                 │ ctx.connect()    │            │
     │                                                 │ parse metadata   │            │
     │                                                 │ build TeachingCtx│            │
     │                                                 │ build BoardVer.  │            │
     │                                                 │ build AgentSes.  │            │
     │                                                 │ build FeynmanAg. │            │
     │                                                 │ session.start()  │            │
     │                                                                                       │
STAGE 4: FeynmanAgent.on_enter — curriculum load + warm tasks
     │                                                 │                  │            │
     │                                                 │ load_curriculum(topic,subject)─────────▶│
     │                                                 │                  │            │   ~50-200ms
     │                                                 │ ◀─────────CurriculumData(concepts, edges, pre-gens)─┤
     │                                                 │                  │            │
     │                                                 │ lesson_plan_from_curriculum()          │
     │                                                 │ tc.lesson_plan = plan                   │
     │                                                 │ board.label = first_concept.title       │
     │                                                 │                                          │
     │                                                 │ ┌────────fire WARM TASKS (parallel)────┐│
     │                                                 │ │                                       ││
     │                                                 │ │ _warm_task = anticipation.warm        ││
     │                                                 │ │   ─ pre-gen 3 concepts × ~2 visuals   ││
     │                                                 │ │   ─ generate_design_diagram x N       ││
     │                                                 │ │ ──────────────────────────────────────────▶│
     │                                                 │ │ ◀──────────DiagramSpec(s)───────────────│  Sonnet
     │                                                 │ │   (parallel; 5-15s each, overlapped)  │  ~$0.10-0.30 ea
     │                                                 │ │                                       ││
     │                                                 │ │ _plan_task = plan_concept(0)          ││
     │                                                 │ │   ─ Anthropic Sonnet structured       ││
     │                                                 │ │     output → ConceptTeachingPlan      ││
     │                                                 │ │ ──────────────────────────────────────────▶│
     │                                                 │ │ ◀────────ConceptTeachingPlan─────────────│
     │                                                 │ │   ~2-4s, $0.05/concept                ││
     │                                                 │ │ also fires plan_concept(1) async      ││
     │                                                 │ │                                       ││
     │                                                 │ │ _prompt_rebuild_task                   ││
     │                                                 │ │   ─ awaits warm + plan                ││
     │                                                 │ │   ─ build_teaching_prompt()           ││
     │                                                 │ │   ─ update_instructions()              ││
     │                                                 │ │                                       ││
     │                                                 │ │ _drift_check_task (Phase 5a-3)        ││
     │                                                 │ │   ─ asyncio loop, 30s cadence          ││
     │                                                 │ └───────────────────────────────────────┘│
     │                                                 │                                          │
     │                                                 │ generate_reply(greeting_instructions)   │
     │                                                 │ ────────────────▶│                       │
     │                                                 │ ◀─text stream───│ ~1-3s, $0.05          │
     │                                                 │ tts_node(text)──────────▶│              │
     │                                                 │ ◀───audio frames──────────│ ~150ms TTFA│
     │ ◀────────────────────────────────────────audio─────────────────────────────────────────│
     │                                                                                          │
STAGE 5: Student speaks for the first time
     │ mic audio ─────────────▶│              │                  │            │
     │                          │              │ Silero VAD detects speech start              │
     │                          │              │ Deepgram STT streaming starts                │
     │                          │              │ ~200-400ms TTFB                              │
     │                          │              │ student transcript ↓                          │
     │                          │              │ committed to chat_ctx on turn end             │
     │                                                                                          │
STAGE 6: First LLM turn (FeynmanAgent.llm_node override)
     │                                                 │                                          │
     │                                                 │ drain_perception_feedback(chat_ctx)     │
     │                                                 │   (queue empty on first turn)           │
     │                                                 │ Agent.default.llm_node(...)             │
     │                                                 │ ──────────────────▶│                   │
     │                                                 │ ◀─text + tool_calls stream────────────│ ~1-3s
     │                                                                                          │
STAGE 7: Tool call — draw_design_diagram (cache HIT path)
     │                                                 │                                          │
     │                                                 │ tool: draw_design_diagram(prompt)        │
     │                                                 │   eid = "design-1"                      │
     │                                                 │   tc.original_diagram_claims["design-1"]│
     │                                                 │      = prompt   (5a-3 retention)        │
     │                                                 │                                          │
     │                                                 │ anticipation.match(prompt, concept_idx) │
     │                                                 │ ◀── HIT (warmed at boot)                │
     │                                                 │                                          │
     │                                                 │ board_mgr.store_design_spec(eid, spec)  │
     │                                                 │ tc.current_diagram_dictionary = ...     │
     │                                                 │ _update_agent_prompt(ctx) (rebuild)     │
     │                                                 │                                          │
     │                                                 │ _publish_visual(instr)                  │
     │ ◀──────────data ch "visuals" JSON──────────────│                                          │
     │ Renders DiagramSpec (~600ms stroke-reveal)                                                │
     │ Reports bounds back via "bounds" topic ─────────▶│                                        │
     │                                                                                          │
     │                                                 │ _schedule_diagram_verification(...)     │
     │                                                 │   ─ asyncio.create_task × 2 (intent +   │
     │                                                 │     layout) (Phase 5a-2)                │
     │                                                 │   ─ BoardVerifier captures screenshot   │
     │                                                 │     → topic "board_capture" round-trip  │
     │ ◀── capture request ──────────────────────────│                                          │
     │ ──── PNG b64 response ────────────────────────▶│                                          │
     │                                                 │ ─── Haiku call ────▶│                   │
     │                                                 │ ◀─── result ────────│ ~1-1.5s, $0.001  │
     │                                                 │ if score <= 2: enqueue PerceptionFeedback│
     │                                                                                          │
STAGE 8: TTS streaming with inline action tag
     │                                                 │                                          │
     │                                                 │ tts_node(text)                          │
     │                                                 │   text contains "<highlight target=     │
     │                                                 │     'hypotenuse'/>"                     │
     │                                                 │   ─ ActionTagParser strips tag          │
     │                                                 │   ─ asyncio.create_task(                │
     │                                                 │       dispatch_action_tag())            │
     │                                                 │     → publish HighlightPulseInstruction │
     │                                                 │   ─ cleaned text → Cartesia             │
     │                                                 │ ────────────────────────▶│              │
     │                                                 │ ◀─audio frames───────────│ ~150ms TTFA │
     │ ◀─────────────────audio + visual tag───────────────────────────────────────────────────│
     │ (browser pulses hypotenuse element within ~300ms of TTS token)                            │
     │                                                                                          │
     │                                                 │ verification scheduled for the tag      │
     │                                                 │ (annotation accuracy 5a-1)              │
     │                                                                                          │
STAGE 9: Student asks a doubt → push branch
     │ mic audio "Wait, what's sin again?" ──▶│      │                                          │
     │                          │              │ STT → chat_ctx                                 │
     │                          │              │                                                │
     │                                                 │ LLM turn fires                          │
     │                                                 │ tool: start_doubt_branch(related)       │
     │                                                 │ ┌──────────────────────────────────┐  │
     │                                                 │ │ state_machine.push_branch()       │  │
     │                                                 │ │ board_mgr.push_board()            │  │
     │                                                 │ │ doubt_orch.on_push():             │  │
     │                                                 │ │   snapshot return_anchor          │  │
     │                                                 │ │   spawn watchdog (60s/120s)       │  │
     │                                                 │ │   store checklist (3 items)       │  │
     │                                                 │ │ anticipation warm doubt diagrams  │  │
     │                                                 │ │ _update_agent_prompt() (doubt ctx)│  │
     │                                                 │ └──────────────────────────────────┘  │
     │ ◀──── board push instruction ─────────────────│                                          │
     │ (Slide cross-fades to fresh doubt board)                                                  │
     │                                                                                          │
STAGE 10: Doubt teaching — multiple turns
     │                                                 │ Agent teaches doubt (draws, writes,    │
     │                                                 │ explains). Each assistant message →    │
     │                                                 │   conversation_item_added event →      │
     │                                                 │   doubt_orch.on_voice_emitted(text)    │
     │                                                 │   → auto-tick checklist items          │
     │                                                                                          │
STAGE 11: Doubt resolve
     │                                                 │ tool: resolve_doubt()                   │
     │                                                 │   @state_constrained: ok in DOUBT       │
     │                                                 │   doubt_orch.is_resolution_allowed?     │
     │                                                 │     if checklist incomplete →            │
     │                                                 │       ToolConstraintError to LLM,       │
     │                                                 │       agent retries with more teaching  │
     │                                                 │     if complete →                        │
     │                                                 │       board_mgr.pop_board()             │
     │                                                 │       state_machine.pop_branch()        │
     │                                                 │       doubt_orch.on_pop():              │
     │                                                 │         cancel watchdog                  │
     │                                                 │         clear doubt anticipation        │
     │                                                 │         RESTORE: re-fire highlights     │
     │                                                 │ ────publish HighlightPulse(s)──▶│      │
     │                                                 │         ctx.session.say(return_cue)     │
     │                                                 │ ────TTS verbatim "back to ladder"▶│    │
     │                                                                                          │
STAGE 12: Periodic drift check (background — happens every 30s during teaching)
     │                                                 │ asyncio.sleep(30)                        │
     │                                                 │ _should_run_drift_check(tc):            │
     │                                                 │   if doubt branch: skip + audit         │
     │                                                 │   if no diagrams: skip + audit          │
     │                                                 │   if state hash == last_hash: skip      │
     │                                                 │   else: proceed                          │
     │                                                 │ _run_drift_check(tc):                   │
     │                                                 │   build state_hash + element_summary    │
     │                                                 │   ─ BoardVerifier.request_drift_check──▶│
     │                                                 │   ─ screenshot round-trip ──────────────┘
     │ ◀── capture request ──────────────────────────│
     │ ──── PNG b64 response ────────────────────────▶│
     │                                                 │   ─ Haiku call with concept context   ─▶│
     │                                                 │   ◀── DriftCheckResult ───────────────│ ~1.5s, $0.001
     │                                                 │   if is_consistent == False:            │
     │                                                 │     enqueue drift PerceptionFeedback    │
     │                                                                                          │
STAGE 13: Concept advance
     │                                                 │ tool: advance_concept()                 │
     │                                                 │   @state_constrained: blocked in DOUBT  │
     │                                                 │   tc.advance() → next concept           │
     │                                                 │   board_mgr.create_and_switch()         │
     │                                                 │   reset perception state:               │
     │                                                 │     queue.clear()                       │
     │                                                 │     intent/layout verified.clear()      │
     │                                                 │     last_drift_check_hash = None        │
     │                                                 │     active_highlights.clear()           │
     │                                                 │   fire anticipation for next concept    │
     │                                                 │   plan_concept(next+1) async            │
     │                                                 │   _update_agent_prompt(ctx)             │
     │ ◀── new board switch instruction ─────────────│                                          │
     │                                                                                          │
STAGE 14: Lesson end
     │                                                 │ tc.is_lesson_complete == True           │
     │                                                 │   OR student disconnects                │
     │                                                 │ session.start() returns                 │
     │                                                 │ finally:                                │
     │                                                 │   drift_task.cancel()                   │
     │                                                 │   await drift_task (CancelledError)     │
     │                                                 │ logger.info("session_started" emit'd)   │
     │                                                 │ audit.summary_text() logged              │
     │                                                                                          │
     │                          │              │ ◀── room disconnect ────│              │      │
     │                          │              │  cleanup tokens, free room                     │
     │                                                                                          │
     │ ─── (future) post-session writer updates per-student knowledge graph                    │
     │      Currently NOT BUILT.                                                                │
     │                                                                                          │
     ════════════════════════ END OF SESSION ════════════════════════════════════════════════════

   FILE REFS:
     livekit/worker.py:entrypoint          ─ Stage 3 + 14 (finally block)
     livekit/worker.py:FeynmanAgent.on_enter ─ Stage 4
     livekit/worker.py:FeynmanAgent.llm_node ─ Stage 6 (drain) + every subsequent turn
     livekit/worker.py:FeynmanAgent.tts_node ─ Stage 8 (action tag stripping)
     livekit/worker.py:_periodic_drift_check ─ Stage 12
     agent/tools.py:draw_design_diagram     ─ Stage 7
     agent/tools.py:start_doubt_branch       ─ Stage 9
     agent/tools.py:resolve_doubt            ─ Stage 11
     agent/tools.py:advance_concept          ─ Stage 13
     agent/doubt_orchestrator.py             ─ Stage 9 + 10 + 11 hooks
```

### Stage 1: Process boot
- `livekit/worker.py` runs as a separate process (`cd backend && uv run python -m feynman.livekit.worker dev`).
- `AgentServer` is constructed at module load. Connects to LiveKit cloud.
- `@server.rtc_session()` registers `entrypoint(ctx)` as the room handler.

### Stage 2: Student creates session
- Frontend POSTs `/sessions` to FastAPI (`api/sessions.py`).
- API generates a LiveKit room + JWT token, creates `SessionModel` in Postgres.
- Returns `{room_name, token}`. Frontend joins the room.

### Stage 3: Worker handler fires (`entrypoint(ctx)`, worker.py)
1. `await ctx.connect()` — joins the LiveKit room.
2. Parse room metadata for `topic`, `subject`, `grade_level`.
3. Construct `state_machine = TeachingStateMachine(session_id)`.
4. Construct `teaching_ctx = TeachingContext(session_id, state_machine)`.
5. Construct `BoardVerifier(publish_fn=_publish_capture, audit=teaching_ctx.audit)` — for Phase 5a.
6. Register data-channel handler (`@ctx.room.on("data_received")`) for `bounds` reports (frontend → backend, element positions) and `board_capture` responses (frontend → backend, screenshot bytes).
7. Construct `agent = FeynmanAgent(teaching_ctx, topic, subject, grade_level)`.
8. Construct `session = AgentSession(stt, llm, tts, vad, userdata=teaching_ctx, use_tts_aligned_transcript=True, max_tool_steps=30)`.
9. Register `conversation_item_added` event listener — forwards every committed assistant message inside a doubt branch to `doubt_orchestrator.on_voice_emitted(text, branch.id)` for keyword auto-tick.
10. `try: await session.start(agent=agent, room=ctx.room)` — blocking until the session ends.
11. `finally: drift_task.cancel()` — clean shutdown of the Phase 5a-3 periodic loop.

### Stage 4: `FeynmanAgent.on_enter` (worker.py:on_enter)
1. **Curriculum load** (if `USE_NEO4J_CURRICULUM=true`):
   - `curriculum = await load_curriculum(topic, subject)` → Cypher query on Neo4j.
   - `plan = lesson_plan_from_curriculum(curriculum)`.
   - `tc.lesson_plan = plan; tc.curriculum = curriculum`.
   - Set initial board label to `first_concept.title`.
2. **Warm tasks** (fire async):
   - `_warm_task = asyncio.create_task(anticipation.warm(plan, start=0, count=3, curriculum))` — pre-gen diagrams for first 3 concepts.
   - `_plan_task = asyncio.create_task(_plan_concepts())` — runs `plan_concept(0)` synchronously, fires `plan_concept(1)` async with continuity.
3. **Prompt rebuild** (after warm + plan tasks):
   - `_prompt_rebuild_task = asyncio.create_task(_update_after_warm())` — awaits both, then `await self.update_instructions(build_teaching_prompt(plan, tc))`.
4. **Drift check loop** (Phase 5a-3):
   - `_drift_check_task = asyncio.create_task(self._periodic_drift_check(), name="periodic_drift_check")`.
5. **Initial instructions** + **greeting**:
   - `prompt = build_teaching_prompt(plan, tc)`; `await self.update_instructions(prompt)`.
   - `session.generate_reply(instructions=greeting_instructions)` — agent says hello.

### Stage 5: Agent speaks → student listens → student speaks
- Greeting flows through `tts_node` → Cartesia → audio frames → WebRTC.
- Student speaks. Silero VAD detects. Deepgram STT streams transcript.
- Turn ends → student message committed to `chat_ctx.history`.

### Stage 6: LLM turn (`Agent.llm_node` → `FeynmanAgent.llm_node` override)
1. `drain_perception_feedback(tc, chat_ctx)` — appends any queued `PerceptionFeedback` as synthetic `role="user"` messages with `[PERCEPTION_FEEDBACK]` prefix.
2. `Agent.default.llm_node(self, chat_ctx, tools, model_settings)` — invokes Anthropic Sonnet.
3. LLM streams response chunks:
   - Tool calls → dispatched as parallel `function_tool` invocations (e.g., `draw_design_diagram(prompt=...)`).
   - Text chunks → go through `tts_node`.

### Stage 7: Tool call flow — `draw_design_diagram` (`tools.py:draw_design_diagram`)
1. `tc.anticipation.match(prompt, tc.current_concept_index)` — cache lookup.
2. On hit: `spec = cached`. On miss: `spec = await generate_design_diagram(prompt, mode="auto")` → design_bridge → Claude → DiagramSpec.
3. Element ID allocated: `eid = tc.board_manager.next_id("design")` → `"design-1"`.
4. **Phase 5a-3 retention**: `if eid not in tc.original_diagram_claims: tc.original_diagram_claims[eid] = prompt`.
5. `instruction = DrawDesignDiagramInstruction(element_id=eid, spec=spec, placement=..., panel=SLIDE)`.
6. `await _publish_visual(ctx, instruction)` — published over data channel topic `"visuals"`.
7. `tc.board_manager.store_design_spec(eid, spec)` and `tc.board_manager.record(instruction)`.
8. `tc.current_diagram_dictionary = dict(spec.dictionary)` — exposes semantic roles to subsequent annotation tools.
9. `await _update_agent_prompt(ctx)` — rebuilds system prompt so the LLM's NEXT turn sees the new dictionary.
10. **Phase 5a-2 verification scheduling**: `_schedule_diagram_verification(ctx, tool_name="draw_design_diagram", element_id=eid, claim_text=prompt, role_list=[...])`. Increments `tc.diagram_version[eid]`, records `DiagramClaim`, fires two `asyncio.create_task`s — one for intent verification (Haiku), one for layout verification (Haiku) — against the same screenshot capture cycle.

### Stage 8: TTS streaming + action tag dispatch (`FeynmanAgent.tts_node`)
- Text chunks pass through `strip_action_tags(text, schedule)`:
  - `ActionTagParser` buffers across chunks, parses `<highlight target="x"/>`-style tags.
  - Each parsed tag → `asyncio.create_task(dispatch_action_tag(session, tag))`.
- Cleaned text goes to Cartesia TTS → audio frames → WebRTC.
- `use_tts_aligned_transcript=True` mirrors cleaned text in user-facing transcription automatically.

### Stage 9: Annotation tool flow (e.g., `pin_label_near`)
1. Agent calls `pin_label_near(target="hypotenuse", label="hyp.")`.
2. `_build_annotation_target("hypotenuse", tc.current_diagram_dictionary)` resolves role → element_id.
3. `instruction = PinLabelInstruction(target=AnnotationTarget(role="hypotenuse"), label="hyp.", sync_mode=AFTER_NEXT_SENTENCE, panel=SLIDE)`.
4. `await _publish_visual(ctx, instruction)`.
5. `tc.active_annotations.append(instruction.element_id)`.
6. **Phase 5a-1 verification scheduling**: `_schedule_annotation_verification(...)` → fire-and-forget Haiku check.

### Stage 10: Periodic drift check (`FeynmanAgent._periodic_drift_check`)
Every 30 seconds:
1. `await asyncio.sleep(30)`.
2. `if not _should_run_drift_check(tc): continue` — pre-flight skips if no verifier, doubt branch, no concept, no diagrams, budget full, or unchanged state hash.
3. `await _run_drift_check(tc)`:
   - Compute `state_hash = compute_drift_state_hash(concept_index, design_ids, diagram_version)`.
   - Build `element_summary` from `tc.original_diagram_claims` + `tc.diagram_version`.
   - `result = await tc.board_verifier.request_drift_check(...)`.
   - On `is_consistent=False`: enqueue `PerceptionFeedback` (subject to 1/concept drift budget).
   - `tc.last_drift_check_hash = state_hash`.

### Stage 11: Doubt branch push (`start_doubt_branch`)
1. Agent calls `start_doubt_branch(related_concept="why is sin opposite/hypotenuse?")`.
2. `parent_branch_id = tc.state_machine.current.id`.
3. `branch = await tc.state_machine.push_branch(concept=related_concept)`.
4. `tc.board_manager.push_board(label=related_concept, branch_id=branch.id)` — new slate.
5. `await tc.doubt_orchestrator.on_push(branch, related_concept, parent_branch_id, checklist=[...])`:
   - Snapshot `return_anchor` (concept_index, beat_index, voice_anchor, active_highlights, notebook_cursor, timestamp).
   - Spawn watchdog task: 60s soft nudge, 120s force-resolve.
   - Anticipation cache pre-fires for likely doubt diagrams.
6. Prompt rebuild — agent now sees doubt-context-aware prompt with checklist + state constraints.

### Stage 12: Doubt resolve (`resolve_doubt`)
1. Decorator `@state_constrained(forbidden_states={IDLE, ...})` enforces it's only callable inside a doubt.
2. Checklist gating: `await tc.doubt_orchestrator.is_resolution_allowed(branch.id)` — returns False with unsatisfied items if any. Tool returns `ToolConstraintError` to LLM with details.
3. On allowed: `tc.board_manager.pop_board()` → parent board active again.
4. `await tc.state_machine.pop_branch()`.
5. `tc.anticipation.clear_doubt_cache()`.
6. `tc.current_diagram_dictionary = {}` (will rebuild on first annotation tool call on parent board).
7. **Orchestrator auto-restore**:
   - Re-fire `active_highlights` on parent slide via `_publish_visual`.
   - Speak verbatim return cue via `ctx.session.say()` — no LLM round-trip.
8. Watchdog cancelled.

### Stage 13: Concept advance (`advance_concept`)
1. Decorator blocks inside `HANDLING_DOUBT`.
2. `next_concept = tc.advance()` — marks current done, increments index.
3. Reset state:
   - `tc.perception_feedback_queue.clear()`.
   - `tc.diagram_intent_verified.clear()`, `tc.diagram_layout_verified.clear()` (Phase 5a-2).
   - `tc.last_drift_check_hash = None` (Phase 5a-3).
   - `tc.active_highlights.clear()`, `tc.active_annotations.clear()`.
4. `tc.board_manager.create_and_switch(label=next_concept.title, branch_id=branch.id)` — new board for new concept.
5. Detect scenario (`detect_scenario`) + `plan_scenario` (legacy 2D-layout machinery; will be removed post-split-board Phase 7).
6. Anticipation re-fires for the new concept's likely visuals.
7. Concept planner fires for `next_concept + 1` (continuity).
8. Prompt rebuild.

### Stage 14: Lesson end
1. All concepts complete OR student initiates end.
2. `await session.start(...)` returns.
3. `finally` block cancels `_drift_check_task`.
4. SessionAudit summary logged (§12).
5. SessionModel in Postgres updated with `ended_at` + final state.

---

## 12. Observability & Quality

### 12.1 SessionAudit (`agent/session_audit.py`)

Every system reports its decisions:

```python
audit.record("anticipation", "cache_hit", "concept=0, prompt='free body...'")
audit.record("drift_check", "completed", "concept=2, is_consistent=False, drift_kind=concept_fit")
audit.record("modify_diagram", "modified", "target=design-1", elapsed_ms=1234)
```

Systems tracked: curriculum, anticipation, routing, board_graph, concept_context, layout, modify_diagram, doubt, drift_check.

`audit.summary()` produces a structured dict; `audit.summary_text()` produces a human-readable report. Logged at session end. Silent failures become visible — particularly **graceful fallbacks that mask degradation**.

### 12.2 structlog

JSON in prod, pretty in dev. Module-level logger. Every key event logs with structured context: `concept_index`, `element_id`, `tool_name`, `score`, `elapsed_ms`. Greppable.

### 12.3 Three-factor scorecard (mandatory per feature)

Every plan + PR includes a scorecard. From `memory/feedback-three-factor-evaluation.md`:

| Factor | Bar |
|---|---|
| **Precision** | Deterministic where possible (Python sandbox geometry = pixel-correct). Perception-loop recovery where not (Haiku verification + LLM retry). |
| **Latency** | Voice round-trip <2s. Visual reactions <300ms mid-sentence / <800ms sentence boundary. Full round-trip counts. |
| **Cost** | Per-subsystem typically <$1/hr. Baseline ~$5–8/hr full Sonnet teaching. |

Reject proposals failing two axes even if acing the third.

### 12.4 What we don't measure yet

- Per-student outcomes (lesson completion, post-session quiz, retention).
- Long-tail latency (P95, P99 for visual rendering).
- Cost telemetry per session (current logs are dev-only).
- Engagement signals (drop-off mid-session).

These come post-Aanya-demo when we have real students.

---

## 13. Operating Principles

These aren't "engineering best practices." They're the rules Yash + Claude (this Claude) actually use. Documented because without them, work degrades.

### 13.1 Product, not demo (`feedback-product-not-demo.md`)

Optimize for general product. Don't anchor architectural plans on Aanya demo timeline. Test every proposal against: *"Would this make ANY STEM doubt magical-precision?"* — not *"What ships by demo day?"*

Tell-tale anti-patterns: pre-baked annotation libraries marked "Tier 1" for Aanya's 4 diagrams (theater), parking architectural ideas as "post-demo," compressing 6-week plans to 1 week.

### 13.2 Brutally honest co-founding (`MEMORY.md`)

In every conversation: if something is bad, say so. If something won't work, say so. No sugar-coating. Yash expects it. This doc embodies it (§15).

### 13.3 Three-factor mandate (`feedback-three-factor-evaluation.md`)

Mandatory scorecard per feature. See §12.3.

### 13.4 RLM protocol (`memory/rlm-protocol.md`)

For non-trivial work (4+ files, design decisions, multiple modules):
- Step 0: Assess. What does Yash want the user to FEEL? What files exist? What's the simplest core-value version?
- Step 1: Feature state file at `active-features/[feature].md`. External memory that doesn't degrade.
- Step 2: Decompose into 3–6 self-contained phases.
- Step 3: Execute. Re-read state file every phase. Decide self vs sub-agent based on coupling.
- Step 4: Verify with FRESH agent reading files + state file.
- Step 5: Close. Delete state file when done OR leave with updated Current State.

Without RLM, work degrades at step ~30 from context rot + contradictory decisions. With it, coherence holds at step 47 like step 1.

### 13.5 Probe-then-dive, sub-agents, cheaper models

- Never stuff full files into context. Tool-based interaction (read, grep, glob).
- Probe-then-dive: broad orientation first, then narrow.
- Sub-agents with fresh contexts for parallel work. Pass focused specs.
- Cheaper models for sub-tasks: Haiku for mechanical/perception, Sonnet for implementation, Opus for design/synthesis/decomposition.

### 13.6 Magic moments over feature counts

Three internal viewers saying "whoa" unprompted = the bar. Not "five features shipped this sprint." The Aanya demo's three magic beats (cache-hit diagrams, doubt-branch-and-return, kid-solves-it) ARE the v0 quality bar.

### 13.7 Care that you can feel

From `MEMORY.md` Product Philosophy: "every detail must feel like somebody really cared a lot." Hover states matter. Stroke-reveal animation timing matters. Return-cue verbatim phrasing matters. **No cutting corners.**

---

## 14. Build Status — Where We Actually Are

### 14.1 Shipped

**Voice + visual core infrastructure**:
- LiveKit Agent worker pipeline (`worker.py`).
- `FeynmanAgent` with `llm_node` + `tts_node` overrides.
- 40+ typed Pydantic visual instructions (`visuals/schemas.py`).
- React frontend with Canvas/WebGL rendering.
- Real-time content generation Phases 1–7 (typed instructions, animated equations, step-by-step, structured diagrams, graphs, topic decomp, state machine).

**Teaching state machine**:
- `TeachingStateMachine` with stack-based async branching (`agent/state_machine.py`).
- `TeachingContext` hub.
- `BoardManager` with multi-board stack.
- 32+ `@function_tool` decorated tools (`agent/tools.py`).

**Doubt orchestration** (`docs/design/15`):
- Phase 2A core (snapshot + restore + checklist) — shipped.
- Phase 2B safety (watchdog + tool constraints + voice-keyword auto-tick) — shipped (`c79fede`).

**Split-board** (`docs/design/10`):
- Phases 1–6 + styling-bridge — shipped (Apr 2026).
- Phase 7 (delete legacy 2D-layout machinery) — pending.

**Diagram awareness re-architecture** (`docs/design/16`, the 5-layer perception arch):
- Phase 0: prompt trim — `71c08ea`.
- Phase 1: frontend bounds + multi-kind targets — `c651f74`.
- Phase 2: voice-visual sync Tier A (`AFTER_NEXT_SENTENCE`) — `35efb21`.
- Phase 3: Python sandbox DSL — `3b7552c` → `008b698` (5 sub-phases: walking skeleton, full primitives, geometric helpers, auto-dict + dispatch, STEM composites).
- Phase 4: inline action tags (5 verbs) — `4e1811c`.
- Phase 5a-1: continuous annotation verification — `febe268`.
- Phase 5a-2: diagram-intent + layout-fix feedback — `a9cf255`.
- Phase 5a-3: periodic drift check + cumulative-claim verification — `87e6957` (just shipped today).
- **Phase 5a is COMPLETE**.

**Curriculum loading** (partial):
- `curriculum_loader.py` Neo4j queries — implemented.
- `lesson_plan.py` LessonPlan derivation — implemented.
- 13-phase pipeline itself — NOT implemented.

### 14.2 In progress

- **Aanya demo build** (`docs/design/13`):
  - In-memory LessonPlan loader.
  - Pre-cached DiagramSpec library (7 diagrams: 3 main + 4 doubt).
  - Verbatim script binding (`target_voice_script`).
  - Frontend `/dev/aanya-demo` route.
  - `listen_for_user_speech` primitive (spike first).
- Status: build sprint not yet started; spec + build list complete.

- **Live LiveKit smoke** of Phase 5a (12 scenarios across 5a-1/5a-2/5a-3) — pending.

### 14.3 Parked

- **Classroom perception (V-JEPA 2)** (`docs/design/archive/11-classroom-perception.md`) — multi-student vision, parked under consumer pivot.
- **School mode** — Mode 1/2, teacher dashboard, classroom voice ID. Topic files preserved (`memory/voice-identification.md`, `memory/teacher-dashboard.md`). Revive post-traction if schools become viable.
- **Living Whiteboard** (`memory/living-whiteboard-design.md`) — 12 phases done, parked. Superseded by Split-board.
- **Diagram Engine** (legacy component library) — 10 phases done, superseded by `design_agent/`.
- **Board Intelligence + Board Cortex** (`docs/design/06`, `09`) — superseded by Split-board. Anticipation engine still in use.
- **Fine-tuning research** (`memory/fine-tuning-research.md`) — deferred until product traction.

### 14.4 Designed but unbuilt

- **Curriculum graph pipeline** Phases 1–13 (`docs/design/08`).
- **Per-student knowledge graph** persistence (§10).
- **Beat Orchestrator deterministic playback** (`docs/design/05`) — planning happens, orchestrator doesn't yet play beats deterministically.
- **Phase 7 Split-board cleanup** — delete ~2500 LOC legacy.
- **Phase 5b VL-JEPA** — sub-sentence correction.
- **Listen-for-user-speech primitive** — Aanya Beat 8 (waits for student speech with timeout).

### 14.5 Path forward (recommended order)

1. **Live smoke Phase 5a (1–2 days)** — validate the 12 perception scenarios in a real LiveKit session before moving on.
2. **Aanya demo build (5–7 days)** — the magic-moment validator. This IS the v0 launch gate.
3. **Phase 7 Split-board cleanup (2 days)** — delete legacy 2D-layout. Cleaner foundation for next work.
4. **Phase 8 voice-visual sync** (`real-time-content-generation` Phase 8) — term-by-term sync. Some of this is already in Phase 5a Tier A.
5. **Per-student knowledge graph v0** — sparse-tolerant, lift Aanya demo to 2nd session.
6. **Curriculum pipeline Phase 1 → Phase 13** — 13 weeks of work. The largest single project on the roadmap. Must come before multi-subject expansion.

---

## 15. Open Problems (Brutally Honest)

### 15.1 Latency vs accuracy — the eternal tension

We have **anticipation engine, modify tool, Python sandbox, STEM composites, and pre-gen-from-curriculum** as the four-front attack on this. It is **not solved**. Specific risks:
- On cache miss with a novel prompt, latency is still 5–15s. The agent must voice-bridge ("let me sketch this for you..."). If the bridge fails or the agent can't fill the gap, the student bounces.
- The Python sandbox is fast for composites but slower than direct JSON for simple shapes. The auto-mode dispatch heuristic is ~5 keywords; it will mis-route in edge cases.
- Pre-gen from curriculum (Phase 12) eliminates ~70% of latency — but Phase 12 isn't built.
- **Honest take**: until Phase 12 lands, ~30% of teaching visuals will be cache miss; voice-bridging is the fragile load-bearing mechanism. Aanya demo dodges this by pre-baking all 7 diagrams (theater).

### 15.2 Drift recovery LLM-translation reliability

Phase 5a-3 detects drift correctly (~80% concept_fit, ~65% cumulative_integrity). But the LLM has to translate `suggested_action` into a clean `modify_design_diagram` call. Estimated first-turn recovery: ~70%/~55%.

That means **30–45% of detected drifts won't be cleanly fixed on first try**. The agent's prompt explicitly says "don't retry more than twice; acknowledge verbally if vision keeps flagging." That's a graceful degradation, not a fix. Real fix requires either:
- VL-JEPA (5b) — direct vision-to-action, no LLM-as-interpreter.
- A specialized "correction model" fine-tuned on diagram-fix patterns (post-traction).

### 15.3 Drift cadence is too sparse for fast-moving lessons

30s cadence catches concept drift but can miss in-concept drift if the agent is rapid-firing diagrams. State-hash dedup helps but doesn't fix this. Mitigations:
- Lower to 20s post-smoke if tests reveal lag (costs go up proportionally).
- Trigger drift check after every Nth tool call (more complex; not implemented).

### 15.4 Beat Orchestrator not built

The beat-deterministic-playback design (`docs/design/05`) is unbuilt. Today's system is more reactive than orchestrated — the agent emits tool calls live with plan-as-guidance, not deterministic beat playback. Trade-offs:
- **Pro**: more flexible, handles edge cases.
- **Con**: more LLM cost (every beat requires reasoning), more variance, no clean MODE switching on interruption.

Aanya demo dodges this with `target_voice_script` binding (temperature=0 plus verbatim instructions). Production needs the orchestrator. Estimated 1–2 weeks.

### 15.5 Cost discipline at scale

Baseline ~$5–8/hr full Sonnet teaching. At ₹4000/mo subscription (~$48/mo), each user gets 6–10 hours of teaching. If usage exceeds, we lose money per user.

Per-subsystem budgets (~<$1/hr) are honored. But the dominant cost is **Sonnet teaching token throughput**, not perception or planning. Mitigations:
- Phase 5b VL-JEPA reduces perception cost further.
- Fine-tuned Feynman-specific model (post-traction) replaces Sonnet for the bulk teaching. Could halve cost.
- Prompt caching (Anthropic's prompt-cache) — partially used; can be tuned harder.

Honest take: **we don't know retention curves yet**. If average usage is <2 hours/month, margin is fine. If it's >10 hours/month, we need to ship cost optimizations before scaling.

### 15.6 Curriculum pipeline is the biggest gap

13 phases of work, design complete, none built. Until Phase 12 (visual pre-generation) lands, anticipation is fed by hand-curated visual_hints + visual_suggestions. That works for v0 (IGCSE 0580, one textbook). It does NOT work for v1+ (multi-subject) at scale.

The pipeline is the highest-leverage thing on the roadmap after the Aanya demo. ~13 weeks of work.

### 15.7 CAC + retention (business)

`MEMORY.md` "Critical Risks": paid acquisition for parents is $30–80 CPI; need viral hook or warm-network seeding. Retention is THE metric. Single sessions are noise. We need 3–4×/week for 6 months to claim "real product."

Architectural implication: **per-student knowledge graph is the retention mechanic**. Without it, every session is the first session — no "the AI remembered I was stuck on this." We need it before paid acquisition.

### 15.8 Trust + COPPA + parental consent

Kids under 13 (Aanya is 13; many in our market are 12). COPPA still applies regardless of geography. We need:
- Parental consent UX (sign-up flow).
- Content guardrails (no off-topic chat, no inappropriate responses).
- Parent dashboard (limited — see usage, hours/week).
- Clear privacy policy.
- Optional: voice not stored (real-time only).

None of this is built. Pre-launch checklist.

### 15.9 First 90 seconds

We don't have telemetry to know bounce rate yet. Aanya demo is the test. If 3+ internal viewers say "whoa," we have signal. If not, we iterate before exposing to parents.

---

## 16. Future Vision

What we've discussed but not built. Ordered roughly by likelihood.

### 16.1 Multi-subject expansion

After Math 0580: Physics 0625 → Chemistry 0620 → Biology 0610. Same visual engine across subjects. Each subject adds:
- New curriculum graph (13-phase pipeline per textbook).
- New STEM composites where useful (e.g., circuit diagrams for Physics, organic skeletons for Chemistry, cell anatomy for Biology).
- New pedagogical patterns (Physics: derivations heavy; Chemistry: reactions + equations; Biology: structures + processes).

Estimated 4–8 weeks per subject post-pipeline-complete.

### 16.2 International expansion

IB MYP/DP (UK international schools) → UAE → Singapore → Malaysia. Same product, different curricula. Architecture supports it (Neo4j curriculum is per-subject, per-syllabus).

### 16.3 Classroom mode (parked)

If consumer fails or schools become viable post-traction:
- V-JEPA 2 multi-student perception (`docs/design/archive/11-classroom-perception.md`) — see which students look confused vs engaged.
- Voice ID per student (`memory/voice-identification.md`) — Picovoice Eagle on-device + pyannote/WeSpeaker fine-tuned.
- Teacher dashboard (`memory/teacher-dashboard.md`) — flag struggling students, annotate knowledge graphs, real-time analytics.
- Mode 1 (single agent, multiple students) vs Mode 2 (multi-agent, one per student).

Significant infrastructure investment. Parked.

### 16.4 AR/VR (Phase N)

`MEMORY.md` Modality section: "Future phases: AR, VR, and beyond — step by step." Holographic diagrams. Spatial walkthroughs. Manipulables. Vision Pro / Quest / future hardware. Not a v1 priority.

### 16.5 Fine-tuned Feynman-specific model (post-traction)

`memory/fine-tuning-research.md` + `engineering-guide.md`. After ~100 hours of real teaching telemetry, fine-tune Qwen 2.5 7B via QLoRA + Unsloth. Convert 3B1B + tutor transcripts to SFT + DPO examples. Sweet spot: ~4–5K training examples. Cost: ~$43 (Anthropic Batch + GPU). Replaces Sonnet for bulk teaching — halves cost, potentially matches or exceeds teaching quality (TeachLM paper validates the pattern).

### 16.6 VL-JEPA self-hosted (Phase 5b)

Sub-sentence correction at ~142ms. Direct vision → state diff → action. Removes the LLM-as-interpreter bottleneck in the perception recovery loop. GPU infra at ~$0.20–0.50/hr. Post-traction.

### 16.7 Spaced repetition + cross-session continuity

The per-student knowledge graph's natural extension. Flag concepts that have decayed (mastery score drops over time). Spawn micro-review sessions: "Hey Aanya, we covered SOH-CAH-TOA two weeks ago — let me re-check quickly before today's harder problem." Increases retention.

### 16.8 Parent/Teacher artifacts

Auto-generated lesson summaries, comprehension reports, weak-spot diagnoses. Parent dashboard. Future: teacher-co-pilot mode where a school deploys Feynman for homework support.

### 16.9 Voice variety + emotion modulation

Cartesia supports it. Today we use a fixed warm voice. Future: voice that matches student preference, modulates excitement/empathy contextually, slows down on hard concepts.

### 16.10 The really long horizon

A teaching agent that students grow up with — accompanies Aanya from Year 9 IGCSE Math to A-Level Physics to undergrad Engineering. Knows her completely. Co-evolves with her. **That's the real product.** Everything we're building is a step toward that.

---

## Appendix A: Module Reference

```
backend/src/feynman/
├── agent/                            # Teaching state machine — CORE IP (~13.3K LOC)
│   ├── action_tag_parser.py          # Mid-stream <highlight target="..."/> parser
│   ├── anticipation.py               # Pre-gen DiagramSpec cache + warm tasks (~758 LOC)
│   ├── board.py                      # BoardManager + Board (multi-board stack)
│   ├── board_state.py                # BoardState (elements, design_specs, scene_graphs)
│   ├── board_verifier.py             # 4-mode perception loop (~1341 LOC)
│   ├── concept_planner.py            # Per-concept ConceptTeachingPlan async generation
│   ├── curriculum_loader.py          # Neo4j queries → CurriculumData
│   ├── design_bridge.py              # Bridge to design_agent (Claude calls + cache)
│   ├── doubt_orchestrator.py         # 5 guardrails: snapshot/restore/checklist/watchdog/constraints
│   ├── drift_state.py                # NEW (5a-3): pure helpers (state_hash + element_summary)
│   ├── lesson_plan.py                # LessonPlan + ConceptNode
│   ├── prompts.py                    # TEACHING_SYSTEM_PROMPT + build_teaching_prompt
│   ├── session_audit.py              # SessionAudit + summary()
│   ├── state_machine.py              # TeachingStateMachine + BranchContext + TeachingState
│   ├── states.py                     # TeachingState enum
│   ├── teaching_context.py           # TeachingContext dataclass (THE HUB)
│   └── tools.py                      # All 32+ @function_tool functions (~2712 LOC)
├── livekit/                          # Voice pipeline (~25.6K LOC)
│   ├── action_tag_dispatch.py        # Inline tag → visual instruction publish
│   ├── pipeline.py                   # create_stt/llm/tts/vad factories
│   └── worker.py                     # Agent worker entrypoint (~600 LOC of FeynmanAgent + helpers)
├── session/                          # Postgres + Redis state
│   ├── manager.py                    # SessionManager (CRUD)
│   ├── models.py                     # SessionModel SQLAlchemy
│   ├── schemas.py                    # Pydantic API schemas
│   └── store.py                      # Redis + Postgres store
├── visuals/
│   ├── canvas_dsl.py                 # Python DSL for diagram building (~55K LOC, WIP)
│   ├── instructions.py               # VisualInstruction discriminated union
│   ├── protocol.py                   # VisualFrame (future batching)
│   ├── sandbox.py                    # AST-whitelist sandbox for canvas_dsl
│   └── schemas.py                    # 40+ Pydantic instruction types (~23K LOC)
├── api/                              # FastAPI routers
│   ├── health.py
│   ├── router.py
│   ├── sessions.py                   # POST /sessions, GET /sessions/:id
│   └── ws.py                         # WebSocket /ws/:session_id
├── db/                               # SQLAlchemy async setup
├── redis/                            # Async Redis client
├── common/
│   ├── logging.py                    # structlog setup
│   └── types.py                      # Subject enum, LLMProvider enum
└── config.py                         # Pydantic Settings (env vars)

design_agent/backend/                 # Separate codebase for diagram gen
├── agent.py                          # DiagramAgent (Claude calls)
├── prompts.py                        # SYSTEM_PROMPT (direct JSON path)
├── prompts_python.py                 # SYSTEM_PROMPT_PYTHON (sandbox path)
└── schema.py                         # DiagramSpec + ElementMeta

data_pre_compute/                     # Curriculum pipeline (WIP, mostly not built)
└── src/lecture_pipeline/curriculum/

contracts/                            # Shared schemas
└── visuals.schema.json               # ~96K, generated from Pydantic

frontend/src/
├── screens/                          # ClassroomScreen, SplitBoardPrototype, DevHarness
├── engine/                           # Canvas + InstructionSwitch + SyncManager
│   ├── whiteboard/
│   │   ├── BoardCapture.tsx          # Screenshot for vision verification
│   │   └── content/DesignDiagramContent.tsx  # Renders DiagramSpec
├── livekit/                          # WebRTC integration
├── hooks/                            # useSession, useSplitBoardState
└── types/                            # TypeScript mirror of contracts/visuals.schema.json
```

## Appendix B: Tool Registry (32+ `@function_tool` in `agent/tools.py`)

| Category | Tool | Produces |
|---|---|---|
| **Slide visuals** | `show_equation` | ShowEquationInstruction |
|  | `step_equation` | StepEquationInstruction |
|  | `show_graph` | ShowGraphInstruction |
|  | `draw_diagram` | DrawDiagramInstruction (fast, node/edge) |
|  | `draw_design_diagram` | DrawDesignDiagramInstruction (slow, via design_agent) |
|  | `modify_design_diagram` | ModifyDesignDiagramInstruction |
|  | `draw_scene` | DrawSceneInstruction |
| **Notebook visuals** | `write_equation` | WriteEquationInstruction |
|  | `write_step` | WriteStepInstruction |
|  | `write_section` | WriteSectionInstruction |
|  | `write_text` | WriteTextInstruction |
|  | `write_answer` | WriteAnswerInstruction |
|  | `new_page` | NewPageInstruction |
|  | `strikethrough` | StrikethroughInstruction |
| **Annotations** | `annotate` | AnnotateInstruction (circle/underline/arrow) |
|  | `pin_label_near` | PinLabelInstruction |
|  | `draw_callout` | DrawCalloutInstruction |
|  | `bracket` | BracketInstruction |
|  | `highlight_pulse` | HighlightPulseInstruction |
|  | `highlight_diagram_part` | HighlightInstruction |
|  | `highlight_walk` | HighlightWalkInstruction (step-by-step) |
| **Board control** | `clear_board` | ClearInstruction |
|  | `clear_cluster` | (cluster-aware clear) |
|  | `switch_board` | SwitchBoardInstruction |
|  | `scroll_board` | ScrollViewInstruction |
| **Teaching state** | `set_lesson_topic` | reload curriculum + lesson plan |
|  | `teach_pause` | SlidePendingInstruction |
| **Doubt management** | `start_doubt_branch` | push branch + board, orchestrator on_push |
|  | `resolve_doubt` | pop branch + board, orchestrator on_pop |
|  | `mark_doubt_step_complete` | manual checklist tick |
| **Lesson progression** | `advance_concept` | mark current concept done, advance to next |

State constraints applied:
- `advance_concept` — forbidden in HANDLING_DOUBT.
- `start_doubt_branch` — forbidden above doubt depth N (currently 2).
- `resolve_doubt` — checklist-gated; returns `ToolConstraintError` if items unsatisfied.

## Appendix C: Design Doc Index

| File | Topic | Status |
|---|---|---|
| `docs/design/01-architecture-analysis.md` | Precompute the plan, perform live | Foundational |
| `docs/design/02-voice-visual-sync.md` | Teaching beats unified streams | Partial (Phase 5a-2 Tier A) |
| `docs/design/04-board-model-annotations.md` | Semantic + spatial board layers | Partial |
| `docs/design/05-beat-orchestration-system.md` | BEAT MODE vs CONVERSATIONAL MODE | Planning shipped, playback NOT |
| `docs/design/06-board-intelligence-and-latency.md` | Anticipation + modify tool | Shipped (anticipation, modify) |
| `docs/design/07-visual-quality-and-next-steps.md` | Hard data + fixes | Applied |
| `docs/design/08-curriculum-graph-pipeline.md` | 13-phase pipeline | Design complete, NOT built |
| `docs/design/09-board-cortex.md` | (superseded by Split-board) | Parked |
| `docs/design/10-split-board.md` | Slide + Notebook panels | Phases 1–6 shipped |
| `docs/design/12-aanya-demo-v0.md` | 7-min magic demo | Spec complete |
| `docs/design/13-aanya-demo-build-list.md` | 5–7 day build sprint | Not started |
| `docs/design/14-agent-diagram-awareness.md` | Semantic dictionary | Shipped (Phase 1A/B) |
| `docs/design/15-doubt-orchestrator.md` | 5 guardrails | 2A + 2B shipped |
| `docs/design/16-diagram-awareness-rearchitecture.md` | 5-layer perception | **Phase 5a COMPLETE** |
| `docs/design/archive/11-classroom-perception.md` | V-JEPA 2 classroom | PARKED |
| `docs/strategy/01-consumer-product-thesis.md` | Consumer + India + IGCSE bet | LOCKED |

## Appendix D: Glossary

- **Aanya** — the 13-year-old Year 9 IGCSE persona; v0 user.
- **Anticipation engine** — pre-generates DiagramSpecs ahead of when they're needed. `agent/anticipation.py`.
- **BEAT MODE / CONVERSATIONAL MODE** — `docs/design/05`. Designed; orchestrator playback NOT built.
- **BranchContext** — one node in the state machine stack: state, concept, return_anchor, checklist.
- **DiagramClaim** — frozen dataclass of (element_id, claim_text, tool_name, version). Phase 5a-2.
- **DiagramSpec** — the JSON output of design_agent. Elements, parameters, animations, dictionary.
- **DictionaryResolver** — maps semantic role → element_id at annotation publish time.
- **Doubt branch** — a branch spawned when a student asks a question. Push-pop via state machine + orchestrator.
- **DoubtOrchestrator** — five guardrails enforcer. `agent/doubt_orchestrator.py`.
- **ElementMeta** — per-element metadata: role, semantic, position, bounds. Part of DiagramSpec.dictionary.
- **PerceptionFeedback** — structured note from vision-loop → LLM via `[PERCEPTION_FEEDBACK]` prefix.
- **Phase 5a** — the diagram-awareness re-architecture's perception loop. 5a-1/5a-2/5a-3 just complete.
- **Phase 5b** — VL-JEPA self-hosted. Sub-sentence correction. Post-traction.
- **return_anchor** — orchestrator snapshot of parent state for doubt-restore.
- **SessionAudit** — every system reports decisions; surfaces silent failures.
- **Split-board** — Slide (left, ~38%) + Notebook (right, ~62%) layout. `docs/design/10`.
- **STEM composites** — `add_right_triangle`, `add_free_body_diagram`, `add_lens`, `add_ray`, `add_lewis_structure`. Phase 3-5.
- **Stroke-reveal** — hand-drawn-feeling animation for diagrams appearing on the slide.
- **Sync mode** — when an instruction renders relative to TTS: IMMEDIATE, VISUAL_FIRST, AFTER_NEXT_SENTENCE, etc.
- **Teaching tree/graph** — the session's branch structure. Main + doubts + nested + comprehension re-approaches.
- **Three-factor scorecard** — precision × latency × cost. Mandatory per feature.
- **VL-JEPA** — Vision-Language Joint Embedding Predictive Architecture. Phase 5b target.

---

## Closing

This doc is the snapshot. It will go stale. Update it when the architecture shifts at the **layer** level — not for routine commits. Phase 6 (when it lands) gets a new section. Phase 12 (curriculum pipeline) replaces the §9 "designed, not built" with "shipped." 5b lands → §16.6 → §8.6 → kills the LLM-as-interpreter bottleneck.

The four words in §1 hold: **real-time, autonomous, personalized, teaching agent**. Everything we ship gets tested against them. If a feature makes one stronger without weakening another, ship. If it weakens one, push back.

This is what we are building. The bar is **magic that Aanya feels at 8 PM on a Wednesday**. Until that bar lands, everything else is preparation.
