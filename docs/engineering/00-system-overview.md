# 00 — System Overview

**Branch:** `feat/unify_boardstate` · **Last verified:** 2026-05-28

This is the map. Every other doc in this set zooms into one quadrant; this one shows how the quadrants fit.

## What Feynman is, in one paragraph

Feynman is an AI teaching agent. It teaches IGCSE Year 9-10 Mathematics on a big screen using real-time voice + a rich visual board. Students interact verbally. The agent adapts in real-time using the Feynman Technique: explain simply, find gaps, revisit fundamentals, simplify with new analogies. The product has two playback modes that share infrastructure: **live agent** (Claude → STT/TTS, full state machine, every visual generated live) and **lecture playback** (precomputed lessons that play back deterministically, with a live "Ask Feynman" doubt-resolution layer on top).

---

## Six modules at a glance

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                                                                                    │
│    contracts/             (the wire format — JSON Schema source of truth)         │
│      ▲                                                                            │
│      │                                                                            │
│  ┌───┴──────┐    ┌──────────────────┐    ┌────────────────────────────────┐     │
│  │  backend/ │◀──▶│ feynman_teaching │◀───▶│  data_pre_compute_v2/          │     │
│  │ FastAPI   │    │ _kernel/         │     │  offline pipeline               │     │
│  │ + Agent   │    │ (plan_concept,    │     │  PDF → Neo4j + TTS + diagrams   │     │
│  │ State Mach│    │  plan_doubt,      │     │  manifest playback contract     │     │
│  │ + LiveKit │    │  Pydantic models, │     │  shares planning kernel above   │     │
│  │   worker  │    │  prompts,         │     │                                 │     │
│  │           │    │  style guide)     │     │                                 │     │
│  └─────┬─────┘    └──────────────────┘     └─────────┬───────────────────────┘     │
│        │                  ▲                          │                              │
│        │                  │                          │                              │
│        │     ┌────────────┴────────────────┐         │                              │
│        │     │   design_agent/             │         │                              │
│        │     │   (standalone playground,   │         │                              │
│        │     │    main backend imports its │         │                              │
│        │     │    prompts directly)        │         │                              │
│        │     └─────────────────────────────┘         │                              │
│        │                                              │                              │
│        ▼                                              ▼                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │  frontend/   (React 19 + Vite, split-board + lecture viewer)                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                    │
└──────────────────────────────────────────────────────────────────────────────────┘
```


| Module                           | Role                                                                                | Deep-dive                                                        |
| -------------------------------- | ----------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `data_pre_compute_v2/`           | Offline: PDF → Neo4j graph + audio + diagram artifacts                              | [01-precompute-pipeline.md](./01-precompute-pipeline.md)         |
| `backend/` (FastAPI)             | Session HTTP API + token minting                                                    | [02-backend-fastapi.md](./02-backend-fastapi.md)                 |
| `backend/` (agent state machine) | Teaching IP — stack-based branching, ~40 LLM tools, unified board state             | [03-teaching-state-machine.md](./03-teaching-state-machine.md)   |
| `backend/` (LiveKit worker)      | Real-time path — STT→LLM→TTS pipeline + lecture-mode doubt delivery                 | [04-livekit-agent-worker.md](./04-livekit-agent-worker.md)       |
| `feynman_teaching_kernel/`       | Shared planning kernel (live + precompute)                                          | [05-feynman-teaching-kernel.md](./05-feynman-teaching-kernel.md) |
| `design_agent/`                  | Diagram authoring playground + spec schema (used by main backend via direct import) | [06-design-agent.md](./06-design-agent.md)                       |
| `contracts/`                     | Wire-protocol source of truth                                                       | [07-contracts-and-protocols.md](./07-contracts-and-protocols.md) |
| `frontend/`                      | React 19 + Vite classroom display                                                   | [08-frontend-architecture.md](./08-frontend-architecture.md)     |
| (cross-cutting)                  | Data stores (Postgres / Redis / Neo4j / filesystem)                                 | [10-data-stores.md](./10-data-stores.md)                         |
| (cross-cutting)                  | A concrete end-to-end trace of one lesson                                           | [09-end-to-end-trace.md](./09-end-to-end-trace.md)               |


---

## Process topology

Feynman is a **multi-process system**. There are four production processes and one developer-only process.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                                                                                    │
│  Browser (frontend, port 5173 in dev)                                              │
│   ├── HTTP/JSON to FastAPI            (POST /api/sessions, etc.)                  │
│   ├── HTTP/JSON to preview_server.py  (GET /lecture-api/chapters/{id})            │
│   ├── WebRTC to LiveKit server         (audio + video — though only audio is used) │
│   └── LiveKit data channels:                                                       │
│       - "visuals"        (worker → browser, instructions)                          │
│       - "bounds"          (browser → worker, element rects)                        │
│       - "board_capture"   (bidirectional, screenshot request/response)             │
│       - "doubt_signal"    (bidirectional, lecture-mode doubt lifecycle)            │
│                                                                                    │
└──────────────────────────────────────────────────────────────────────────────────┘
        │                  │                       │
        │ HTTP             │ HTTP                  │ WebRTC + data channels
        ▼                  ▼                       ▼
┌──────────────┐   ┌────────────────┐   ┌──────────────────────┐
│  FastAPI      │   │ preview_server  │   │  LiveKit server      │
│  (:8000)      │   │ (:8080, dev    │   │  (:7880 ws, :7881    │
│  ─────────    │   │  & QA)          │   │   tcp, :7882 udp)    │
│  /api/health  │   │ ──────────────  │   │  ──────────────────  │
│  /api/        │   │ /lecture-api/  │   │  Hosts ephemeral     │
│   sessions    │   │ chapters       │   │  rooms, signals      │
│  /api/        │   │ /chapter/{id}  │   │  WebRTC, routes      │
│   diagtest    │   │ /lecture-      │   │  data channels       │
│               │   │  artifacts/*   │   │                      │
└──────┬────────┘   └─────┬──────────┘   └──────┬───────────────┘
       │                  │                     │
       │ session writes   │ Neo4j reads          │ Agent dispatch
       ▼                  ▼                     ▼
┌──────────────┐   ┌────────────┐   ┌──────────────────────────┐
│  Postgres    │   │  Neo4j     │   │  LiveKit Worker          │
│  (:5433)     │   │  (:7687)   │   │  (separate process)      │
│  ──────      │   │  ──────    │   │  ──────────────────────  │
│  sessions    │   │ Chapter/   │   │  @server.rtc_session()   │
│  table only  │   │ Topic/     │   │  → entrypoint()          │
│              │   │ Diagram/   │   │     ├── interactive mode │
│  ┌────────┐  │   │ Question   │   │     │   STT→LLM→TTS      │
│  │ Redis  │  │   │ + edges    │   │     │   ~40 tools        │
│  │ (:6379)│  │   │            │   │     │   state machine    │
│  │ hot    │  │   │ Read by:   │   │     │   board manager    │
│  │ session│  │   │ - backend  │   │     │                    │
│  │ state  │  │   │   curr...  │   │     └── lecture mode     │
│  │        │  │   │ - worker   │   │         silent + doubt   │
│  └────────┘  │   │ - preview  │   │         delivery         │
│              │   │   server   │   │                          │
└──────────────┘   └──────┬─────┘   └──────────────────────────┘
                          │
                          │ Writes:
                          │
                   ┌──────┴──────────────┐
                   │  data_pre_compute_  │
                   │  v2/ pipeline (CLI) │
                   │  ─────────────────  │
                   │  poetry run         │
                   │  lecture-pipeline-v2│
                   │  ingest-book ...    │
                   │                     │
                   │  Writes to Neo4j +  │
                   │  filesystem         │
                   │  artifacts/         │
                   └─────────────────────┘
```

### Process responsibilities


| #   | Process                                           | When it runs | Purpose                                                                                                             |
| --- | ------------------------------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------- |
| 1   | **LiveKit server** (Docker)                       | Always       | WebRTC signaling + data channel routing. Stateless across restarts (rooms are ephemeral).                           |
| 2   | **Postgres** (Docker)                             | Always       | Session persistence (one table today).                                                                              |
| 3   | **Redis** (Docker)                                | Always       | Session hot state.                                                                                                  |
| 4   | **Neo4j** (Docker)                                | Always       | Curriculum graph.                                                                                                   |
| 5   | **FastAPI** (`make dev-backend`)                  | Always       | HTTP API. Hands out LiveKit JWTs. Manages session resource.                                                         |
| 6   | **LiveKit worker** (`make dev-worker`)            | Always       | Real-time path. One Python process serving multiple rooms via `@server.rtc_session()` dispatch.                     |
| 7   | **Frontend** (`make dev-frontend`)                | Dev only     | Vite dev server with proxy. In prod, statically built and served.                                                   |
| 8   | **preview_server.py** (`make dev-preview-server`) | Dev + QA     | Serves chapter manifests + static artifact files. In prod, replaced by CDN + a small Neo4j-backed manifest service. |
| 9   | **design_agent** (manual)                         | Dev only     | Diagram-authoring playground. Never touched in production.                                                          |


In `make dev`, all five dev processes start in a single command — but they are five separate OS processes.

---

## Two playback modes

### Mode A — live agent

```
Student opens / → LectureHomeScreen (if they want to pick a recorded chapter)
                  OR
                  goes to #/dev/live-teacher → WaitingScreen (live-mode entry)

Student enters topic + subject → useSession().startSession({ topic, subject })
                              → POST /api/sessions
                              → backend creates Postgres row, seeds Redis,
                                creates LiveKit room with metadata,
                                mints JWT, returns token

Frontend RoomProvider connects to LiveKit room

LiveKit dispatches a new job → worker's entrypoint() fires
  → reads metadata: lecture_chapter_id is None → interactive mode
  → builds TeachingStateMachine + TeachingContext
  → loads curriculum from Neo4j
  → starts async planning of concept 0 + 1 via kernel's plan_concept
  → fires anticipation warm-up for first 3 concepts (cache design_agent specs)
  → AgentSession starts: STT (Deepgram) → LLM (Claude Sonnet 4) → TTS (Cartesia)
                          + ~40 LLM tools
                          + ActionTagParser middleware on TTS stream

Student says "I want to learn the Pythagorean theorem"
  → STT transcript appended to chat_ctx
  → LLM produces response chunks + tool calls
  → Tools execute: draw_design_diagram, show_equation, write_step, highlight, ...
    Each tool _publish_visual() over LiveKit topic="visuals" (reliable JSON)
  → Response text → TTS → audio frames → LiveKit room audio track
  → Inline tags <highlight target="hypotenuse"/> stripped from speech,
    dispatched as visuals with sync_mode=AFTER_NEXT_SENTENCE

Frontend useVisualChannel onMessage:
  → JSON.parse, defer if after_next_sentence
  → addInstruction to useBoardStore
  → SplitBoard/Whiteboard re-renders
  → DOM update → BoundsReporter sends topic="bounds" back
  → Worker updates BoardState.scene_graph + spatial_solver

Student asks a doubt → state machine push_branch → board_manager push_board
                    → doubt_orchestrator.on_push (snapshot parent state, start watchdog)
                    → plan_doubt() generates 2-3 beat plan + checklist
                    → Agent teaches the doubt on a fresh board
                    → resolve_doubt when checklist done → pop, restore parent state
```

### Mode B — lecture playback

```
Student opens / → LectureHomeScreen
  → fetch /lecture-api/chapters from preview_server → ChapterListEntry[]
  → renders chapter grid

Student picks chapter "Newton's Laws Ch 5"
  → window.location.search = "?lecture=chapter_physics_newtons_laws_..."
  → App.tsx MainEntry sees ?lecture, auto-starts session with that chapter

useSession.startSession({ lecture_chapter_id: "chapter_..." })
  → POST /api/sessions with lecture_chapter_id
  → backend creates session + LiveKit room with that metadata
  → mints JWT, returns token

Frontend connects to LiveKit room
LiveKit dispatches job → worker's entrypoint() reads metadata
  → lecture_chapter_id is set → _run_lecture_mode()
  → loads ChapterContext from Neo4j (LectureDoubtSession)
  → DoubtDelivery publishes outbound audio track (silent until needed)
  → Listens on topic="doubt_signal"

Frontend ClassroomScreen sees lectureChapterId → renders LectureViewer
LectureViewer:
  → fetch /lecture-api/chapter/{id} from preview_server → ChapterPayload
  → useExtractionPlayback({ chapter, autoStart: true })
  → Walks chapter.events[] sequentially:
    - AudioEvent → HTMLAudioElement plays the MP3
    - ShowDiagramEvent → mount the diagram on slide
    - FocusEvent → spotlight an element
    - TraceEvent → animate stroke
    - WriteEquationEvent → notebook page append
    - NewPageEvent → turn notebook page
    - ... 27 event types total

Student watches lecture, audio + visuals stream from frontend's player.
Worker stays silent in the room.

Student taps "Ask Feynman":
  → LectureViewer pauses playback, rewinds cursor by 1 event
  → publishes doubt_intent over topic="doubt_signal" with currentSnapshot
    (BoardSnapshot from precompute — the unified board state)
  → Worker _handle_doubt_intent:
    - STT capture student utterance (12s budget)
    - DoubtClassifier → ResolutionPlanner → DiagramFitMatcher → ResolutionPlan
    - DoubtDelivery.deliver_resolution: for each beat:
      - publish doubt_beat_start with target_diagram_id + annotation_actions
      - sleep 150ms (frontend swaps visuals)
      - TTS narration of beat_text
    - publish satisfaction_prompt with options
  → Frontend renders annotations + speaks via worker's audio track
  → Student picks "crystal_clear" → satisfaction_choice → lecture_resume
  → useExtractionPlayback play() resumes from rewound cursor
```

---

## Three critical paths

Three places where engineering decisions matter most.

### Critical path #1 — live visual latency

When the agent decides to draw a diagram, **the visual must appear within 200-800ms** of the spoken cue. The pipeline:

```
LLM emits tool call (e.g., draw_design_diagram)
  └── design_bridge.generate_design_diagram(prompt):
      Cache hit?   → ~10ms                                  ◀── ideal path
      Cache miss?  → 5-15s (full Claude call)               ◀── kills the magic
```

The mitigation is the **anticipation engine** (`agent/anticipation.py`):

- On session start: warm the first 3 concepts.
- On `advance_concept`: warm the next concept N+1.
- Warm = pre-fire `design_bridge.generate_design_diagram(...)` so the spec is in the FIFO cache (64 entries).

This converts most draws to cache hits. The remaining cold draws are the LLM's "I want something I didn't anticipate" moments — these still cost 5-15s and feel slow.

Action tags (`<highlight target="..."/>`) bypass this entirely — they're CSS-only effects on already-rendered elements, dispatched in parallel with TTS via the `after_next_sentence` queue.

See `03-teaching-state-machine.md` §8 (anticipation) and `06-design-agent.md` (the bridge + cache).

### Critical path #2 — board awareness

The agent must know what's on the board so it can refer back, point at things, and not blindly draw over existing content.

The architecture (the branch name): `feat/unify_boardstate`. One `BoardState` per board, three sub-views in sync:

- `_elements: dict[id, BoardElement]` — flat ID lookup.
- `scene_graph: SceneGraph` — pixel bounds from frontend bounds reports.
- `board_graph: BoardGraph` — semantic relationship edges declared by the LLM (`relates_to`, `relation`).
- `spatial_solver: SpatialSolver` — MaxRects free-space tracker for placement.

Plus the prompt assembly: every LLM turn, `build_teaching_prompt()` injects:

- An ASCII board snapshot (72×18 cell grid showing occupied regions).
- A clustered semantic summary (from `board_graph.get_clusters`).
- A scenario plan slot status.
- A reconstructed notebook state (from `notebook.reconstruct(audit)`).
- The current `ConceptTeachingPlan` rendered as markdown.

This is also what makes the precompute pipeline coherent: it produces `BoardSnapshot[]` (one per page) attached to `Chapter.board_snapshots`. When a student in lecture mode taps "Ask Feynman," the snapshot at the current playback cursor is shipped in `doubt_intent.board_snapshot` so the doubt resolver knows exactly what's on screen.

See `03-teaching-state-machine.md` §6 + §7 and `07-contracts-and-protocols.md` §6.

### Critical path #3 — drift prevention

Live teaching and precomputed teaching could easily diverge. The kernel `feynman_teaching_kernel/` prevents this:

- One `ConceptTeachingPlan` Pydantic model.
- One Feynman-arc validator (`hook → big_picture → first_principles` mandate).
- One `plan_concept(...)` function called by both consumers.
- One `PLANNING_SYSTEM_PROMPT`.
- One `PRONUNCIATION_RULES` + `BANNED_OPENERS` style guide.

Both backend and precompute install the kernel as an **editable path dependency** to the same source tree. There's no way for them to drift on planning logic.

The design_agent prompt is a similar contract:

- `design_agent/backend/prompts.py:SYSTEM_PROMPT` is the source of truth.
- `backend/src/feynman/agent/design_bridge.py` reads it from disk at runtime.
- `data_pre_compute_v2/.../diagrams.py` carries a **verbatim copy** annotated "DO NOT EDIT — synced VERBATIM."

The verbatim-copy annotation is the discipline. Sync is enforced by code review, not by codegen.

See `05-feynman-teaching-kernel.md` for the planning kernel, `06-design-agent.md` for the diagram prompt sync.

---

## Tech stack at a glance


| Layer              | Choice                                             | Why                                                                                     |
| ------------------ | -------------------------------------------------- | --------------------------------------------------------------------------------------- |
| Frontend framework | React 19 + TypeScript + Vite                       | Modern, fast HMR, full type safety.                                                     |
| Backend framework  | FastAPI (Python 3.13)                              | Async-native, Pydantic-native, plays well with LiveKit Agents SDK.                      |
| Real-time voice    | LiveKit (WebRTC + Agents SDK)                      | Production-grade WebRTC. Agent SDK handles STT/LLM/TTS plumbing.                        |
| STT                | Deepgram nova-3                                    | Lowest latency, best transcription. Fallback to OpenAI gpt-4o-mini-transcribe.          |
| LLM (live)         | Claude Sonnet 4                                    | Best teaching reasoning.                                                                |
| LLM (planning)     | Claude Sonnet 4 (also Sonnet for design diagrams)  | Same model, but called separately via the kernel + design_bridge.                       |
| LLM (judge)        | qwen3:8b (local via Ollama)                        | Cheap multi-model agreement check in precompute.                                        |
| TTS                | Cartesia sonic-3                                   | Natural voice, low latency. Fallback to OpenAI.                                         |
| TTS (precompute)   | Kokoro (local)                                     | Free, runs offline, voice "af_heart".                                                   |
| VAD                | Silero (local)                                     | Offline, robust.                                                                        |
| Database           | PostgreSQL 17                                      | Sessions.                                                                               |
| Cache              | Redis 7                                            | Session hot state.                                                                      |
| Curriculum store   | Neo4j 5 (community + APOC)                         | Native graph for curriculum + manifest storage.                                         |
| Embeddings         | sentence-transformers (default) or OpenAI          | Local, free option; OpenAI for quality if needed.                                       |
| Build              | uv (backend), Poetry (precompute), pnpm (frontend) | Each was chosen for its module's needs. Backend was migrated from Poetry → uv recently. |


The mixing of `uv` and `poetry` is one piece of friction. The `feynman_teaching_kernel/` is installed as an editable path-dep in both: `uv` consumes via `[tool.uv.sources]`, `poetry` via `[tool.poetry.dependencies]` with `develop = true`. Both point to the same `feynman_teaching_kernel/` directory.

---

## All entry points

### Commands

```bash
# Local development
make setup            # uv sync, pnpm install, docker compose up, migrations
make dev              # starts worker + backend + frontend + preview_server
make dev-backend      # FastAPI :8000
make dev-frontend     # Vite :5173
make dev-worker       # LiveKit worker
make dev-preview-server  # preview_server.py :8080

# Tests
make test
make test-backend
make test-frontend

# Lint + format
make lint
make format

# Database
make db-up
make db-down
make db-reset
make migrate

# Precompute
cd data_pre_compute_v2
poetry run lecture-pipeline-v2 init-schema
poetry run lecture-pipeline-v2 ingest-book <pdf> -s <subject>
poetry run lecture-pipeline-v2 stats
poetry run lecture-pipeline-v2 query "MATCH (n) RETURN count(n)"

# Design agent (dev only)
cd design_agent/backend && python -m backend.main     # :8000
cd design_agent/frontend && npm start                 # :3001
# (DON'T run main backend and design_agent backend at the same time — both want :8000)
```

### Files


| Process               | Entry file                                                                                       |
| --------------------- | ------------------------------------------------------------------------------------------------ |
| FastAPI               | `backend/src/feynman/main.py` (uvicorn target: `feynman.main:app`)                               |
| Worker                | `backend/src/feynman/livekit/worker.py:__main__` (via `python -m feynman.livekit.worker dev`)    |
| Frontend              | `frontend/src/main.tsx` (Vite entry)                                                             |
| Precompute CLI        | `data_pre_compute_v2/src/lecture_pipeline_v2/cli.py:app` (Typer; bound to `lecture-pipeline-v2`) |
| Preview server        | `data_pre_compute_v2/tools/preview_server.py`                                                    |
| Design agent backend  | `design_agent/backend/main.py`                                                                   |
| Design agent frontend | `design_agent/frontend/src/index.js`                                                             |


### URLs (dev)


| URL                     | Process           |
| ----------------------- | ----------------- |
| `http://localhost:5173` | Frontend (Vite)   |
| `http://localhost:8000` | FastAPI           |
| `http://localhost:8080` | preview_server.py |
| `ws://localhost:7880`   | LiveKit signaling |
| `http://localhost:7474` | Neo4j browser UI  |
| `localhost:5433`        | Postgres          |
| `localhost:6379`        | Redis             |
| `bolt://localhost:7687` | Neo4j Bolt        |


---

## Cross-cutting concerns

### Async everywhere

All IO is async on the backend. `asyncpg` for Postgres, `redis.asyncio` for Redis, `neo4j` async API, `httpx` for outbound HTTP, `anthropic.AsyncAnthropic` for Claude. The LiveKit worker is an async event loop. The teaching state machine uses `asyncio.Lock` for stack-safe push/pop.

### Structured logging

`structlog` with JSON output in prod, pretty in dev. Set up in `common/logging.py`. Module-level pattern:

```python
import structlog
logger = structlog.get_logger()
m
logger.info("event.name", session_id=..., key1=value1)
```

There's a small fix in `_IPCSafeFormatter` for LiveKit's subprocess logging that stringifies structlog's dict on cross-process pickle.

### Pydantic for all data

Everything that crosses a boundary (HTTP request, LLM tool call, LiveKit data channel, Neo4j property) is a Pydantic model. This is the discipline that lets us have a three-way wire-format mirror (`contracts/visuals.schema.json` ↔ Pydantic ↔ TypeScript).

### Audit trail

`SessionAudit` records every "the system actually did this" event — tool calls, fallbacks, skips, drift detections — for the active session. Used to:

- Inject `[PERCEPTION_FEEDBACK]` into the LLM's next turn.
- Reconstruct the notebook (`notebook.reconstruct(audit)`).
- Power post-session debugging.

Audit is in-memory only.

---

## Production-vs-dev gap

What changes when this leaves localhost:

- API keys come from a secret manager, not `.env`.
- TLS everywhere (LiveKit, FastAPI, Postgres, Redis).
- Postgres + Neo4j managed services with daily backups.
- Artifact serving moves to S3 + CDN; the URL rewriter in `preview_server.py` becomes a config-driven URL prefix.
- LiveKit cluster instead of `livekit-server --dev`.
- Worker autoscaled per concurrent room.
- Sentry or similar for error reporting.

No architectural shifts. The architecture is shaped for production; only the hosting + secrets layer changes.

---

## Where to go from here

By complexity:

1. **Quickest tour** — read [09-end-to-end-trace.md](./09-end-to-end-trace.md). It follows one student session through every module.
2. **Want to ingest a textbook** — [01-precompute-pipeline.md](./01-precompute-pipeline.md).
3. **Want to change a tool or add an instruction type** — [03-teaching-state-machine.md](./03-teaching-state-machine.md) + [07-contracts-and-protocols.md](./07-contracts-and-protocols.md).
4. **Want to tune diagram aesthetics** — [06-design-agent.md](./06-design-agent.md).
5. **Want to add a frontend screen** — [08-frontend-architecture.md](./08-frontend-architecture.md).
6. **Want to understand the planning kernel** — [05-feynman-teaching-kernel.md](./05-feynman-teaching-kernel.md).
7. **Want to deploy** — [10-data-stores.md](./10-data-stores.md) §11 covers the gap to production.

Or just read the docs in order — they're written to compose.