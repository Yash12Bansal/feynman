# Feynman — AI Teaching Agent

## What This Is

Feynman is an AI teacher for school classrooms. It teaches from a big screen at the front of the room using real-time voice + rich visual aids (diagrams, equations, animations). Students interact verbally. The AI adapts in real-time using the Feynman Technique: explain simply, find gaps, revisit fundamentals, simplify with new analogies.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Classroom Screen (React + Canvas/WebGL)                    │
│  - Renders visual instructions from backend                 │
│  - LiveKit client for audio                                 │
└──────────────┬──────────────────────────────┬───────────────┘
               │ WebSocket (visuals)          │ WebRTC (audio)
               ▼                              ▼
┌──────────────────────────┐    ┌─────────────────────────────┐
│  FastAPI (backend/src/)  │    │  LiveKit Agent Worker        │
│  - REST API              │◄──►│  - STT → LLM → TTS pipeline │
│  - Session management    │    │  - Teaching state machine    │
│  - Knowledge graph       │    │  - Visual instruction gen    │
└──────────┬───────────────┘    └─────────────────────────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
┌─────────┐ ┌─────────┐
│PostgreSQL│ │  Redis  │
│(data)    │ │(state)  │
└─────────┘ └─────────┘
```

## Module Map

| Module        | Path                             | Purpose                                                                               |
| ------------- | -------------------------------- | ------------------------------------------------------------------------------------- |
| **agent**     | `backend/src/feynman/agent/`     | Teaching state machine — the core IP. Async state machine with stack-based branching. |
| **livekit**   | `backend/src/feynman/livekit/`   | LiveKit integration. Agent worker runs as separate process.                           |
| **knowledge** | `backend/src/feynman/knowledge/` | Per-student knowledge graph. SQLAlchemy models + abstract repository.                 |
| **visuals**   | `backend/src/feynman/visuals/`   | Visual instruction engine. Typed commands sent to frontend for rendering.             |
| **session**   | `backend/src/feynman/session/`   | Teaching session lifecycle. Redis for hot state, Postgres for persistence.            |
| **api**       | `backend/src/feynman/api/`       | FastAPI routers. REST + WebSocket endpoints.                                          |
| **db**        | `backend/src/feynman/db/`        | SQLAlchemy async engine, declarative base.                                            |
| **redis**     | `backend/src/feynman/redis/`     | Async Redis client factory.                                                           |
| **common**    | `backend/src/feynman/common/`    | Shared exceptions, logging (structlog), type aliases.                                 |
| **frontend**  | `frontend/src/`                  | React + Canvas/WebGL classroom screen.                                                |
| **contracts** | `contracts/`                     | Shared backend↔frontend schemas (JSON Schema).                                        |

## Conventions

### Python (backend)

- **Async everywhere** — all IO is async. No sync database calls, no sync Redis, no blocking.
- **Ruff** for linting and formatting (configured in pyproject.toml)
- **pytest + pytest-asyncio** for testing
- **Pydantic** for all data validation and settings
- **structlog** for logging — structured JSON in production, pretty in dev
- Import style: `from feynman.agent.states import TeachingState`

### TypeScript (frontend)

- **React 19** with functional components and hooks only
- **ESLint** flat config + Prettier
- **Vitest** for testing
- No class components. No default exports (except pages).

### General

- No LangGraph. Custom async state machine for teaching logic.
- Both Anthropic Claude and OpenAI GPT configured — frontier for teaching, cheaper for sub-tasks.
- LiveKit agent worker is a **separate process** from the FastAPI server.

## Common Commands

```bash
make setup          # Install all deps + start docker services
make dev            # Start backend (:8000) + frontend (:5173)
make dev-backend    # Backend only
make dev-frontend   # Frontend only
make test           # Run all tests
make lint           # Lint everything
make format         # Auto-format everything
make db-up          # Start docker services
make db-down        # Stop docker services
make db-reset       # Wipe volumes and restart
```

## When Adding a Feature

1. Start with the **backend module** — define types, schemas, business logic
2. Add **tests** alongside the code (not after)
3. If it touches the visual contract, update `contracts/visuals.schema.json` and both sides
4. Wire up the **API route** in `backend/src/feynman/api/`
5. Build the **frontend component** to consume it
6. Update the relevant `CLAUDE.md` in the module you touched

## Environment Variables

All env vars are defined in `backend/src/feynman/config.py` (Pydantic Settings). See `.env.example` for the full list.

## Key Design Decisions

- **Teaching sessions are tree/graph structures** — main branch for lesson flow, doubt branches spawn and merge back. Stack-based navigation.
- **Knowledge graph is an enhancement, not a dependency** — system works great without it, works better with it.
- **PostgreSQL for everything** (no Neo4j yet) — abstract repository allows future swap.

## Visual System: Current State & Critical Problems

### Current Approach: Design Agent (`design_agent/`)

The visual system uses an **LLM-as-author** approach. When the teaching agent needs a diagram:

1. Teaching agent sends a natural language requirement (e.g., "Draw a convex lens ray diagram")
2. `design_agent` backend sends this to Claude with a constrained system prompt
3. Claude generates a structured `DiagramSpec` JSON (SVG elements, KaTeX equations, interactive parameters)
4. Frontend renders SVG + KaTeX overlays with interactive sliders
5. Progressive rendering extracts elements from partial streaming JSON

**Why this approach**: The previous deterministic diagram engine (component library + layout strategies) could not accurately render the diversity of diagrams real teaching requires. Having Claude write the spec directly produces much better, more accurate visuals.

### CRITICAL PROBLEM 1: Latency Kills Real-Time Teaching

Claude generating a full diagram spec from scratch takes 5-15+ seconds. Even with progressive rendering, the first meaningful element takes several seconds. **A teacher cannot pause mid-sentence for 10 seconds waiting for a diagram.** The board must feel like an extension of the teacher's voice — visuals appearing as concepts are spoken.

The core tension: **accuracy (Claude writes it) vs speed (pre-built components)**. The old engine was fast but inaccurate. The current approach is accurate but too slow. We need both.

Solving this is the #1 priority for making the product feel magical.

### CRITICAL PROBLEM 2: The Board Has No Intelligence

The LLM generates diagrams in isolation. It has no awareness of:
- **What's on the board** — can't reference, modify, or build on existing visuals
- **Spatial layout** — doesn't know where things are or what space is available
- **Narrative flow** — can't use the board as a thinking tool (draw next to X, erase Y, highlight Z, connect A to B)
- **Board history** — doesn't know what was shown before or the visual narrative arc

Currently, basic element IDs prevent overlap, but that's not intelligence. A real teacher uses the board as a **reasoning and narrative tool** — pointing back to earlier diagrams, drawing connections, building layered explanations, erasing and redrawing.

The board needs a **semantic state model** the LLM can reason about — what's there, what it means, how it relates, and what operations are available.

**These two problems are connected**: good board context enables incremental updates (modify/extend existing visuals) instead of regenerating from scratch, which directly reduces latency.

### Design Principles for Solutions

- **The board is a first-class teaching tool**, not just a display surface. The LLM must be able to think about and manipulate the board like a teacher thinks about their whiteboard.
- **Latency budget**: visuals must appear within 1-2 seconds of the teacher referencing them, ideally faster.
- **Incremental over regenerative**: modify what's there rather than rebuilding from scratch.
- **The old diagram engine's component library may still be useful** as a fast fallback or building block, even if it can't be the whole solution.
- **Anticipation > reaction**: the teaching agent knows what's coming in the lesson plan; pre-generate where possible.

## Active Multi-Phase Implementation: Curriculum Graph Pipeline

**Status**: Design complete, Phase 1 next. 13 phases total.
**Design doc**: `docs/design/08-curriculum-graph-pipeline.md` — the SINGLE SOURCE OF TRUTH for this work.
**Memory**: `~/.claude/projects/-Users-yashbansal-proj-feynman/memory/curriculum-graph-pipeline.md`
**Codebase**: `data_pre_compute/` — the pipeline being rebuilt.

### Reference Codebase (IMPORTANT)
**Repo**: `/Users/yashbansal/proj/patient-medical-graph`
**Branches**: `feature/deployable-feature-branch` and `feature/cyper-standardization-updates-v2`
**Why**: Production-grade patterns for graph ingestion, validation, entity resolution, Neo4j schema, salience scoring. Reference these for implementation quality — don't copy blindly, adapt the patterns to our educational domain.
**Key files to reference**:
- `pmg/src/pmg/ingestion/models/extraction_result.py` — canonical intermediate format
- `pmg/src/pmg/ingestion/extraction_validator.py` — structural validation pattern
- `pmg/src/pmg/ingestion/extraction_merger.py` — entity merge pattern
- `pmg/src/pmg/ingestion/json_to_cypher.py` — deterministic Cypher generation
- `pmg/src/pmg/ingestion/prompts/schema_context.py` — schema injection into LLM prompts
- `pmg/src/pmg/ingestion/validation/post_processor.py` — deterministic post-processing
- `pmg/src/pmg/db/schema.py` — Neo4j schema initialization
- `pmg/src/pmg/services/salience/` — salience scoring (static + structural + dynamic)

### Phase Summary (13 phases)
1. **Foundation** — Pydantic models, Neo4j schema, stable ID generation
2. **Book Skeleton** — Single LLM call extracts entire book's structure
3. **Anchor Extraction** — Deterministic regex: section numbers, figures, examples (pre-LLM)
4. **Chapter Extraction** — Book-aware two-pass LLM extraction (structure → content)
5. **Structural Validation** — Completeness checks against anchors + gap-filling loop
6. **Entity Resolution** — Hash-based chunk merging within chapters
7. **Book Unification** — Cross-chapter resolve, hierarchy, shared concept detection
8. **Neo4j Ingestion** — Cypher generation + embeddings
9. **Salience Scoring** — Static (rule-based) + structural (PageRank)
10. **Semantic Validation** — LLM spot-checks on sample
11. **Pipeline + CLI** — Wire everything, `ingest-book` command
12. **Visual Pre-Generation** — DiagramSpec for every concept with visual_hint
13. **Cleanup** — Delete dead code, Poetry → uv

### When user says "continue" or "start phase X":
1. Read the design doc (`docs/design/08-curriculum-graph-pipeline.md`) for that phase's section
2. Read the memory file for reference codebase paths and key decisions
3. Check out the PMG reference branch if needed: `git checkout remotes/origin/feature/deployable-feature-branch`
4. Implement the phase in `data_pre_compute/src/lecture_pipeline/curriculum/`
5. Tests alongside code — every phase has test criteria in the design doc
6. After phase: tell user **"Phase X done. `/compact` then `continue`"**

### Key architectural decisions (don't re-debate these):
- **Neo4j** as curriculum store (graph evolves at runtime)
- **Whole-book-first** approach (BookSkeleton → book-aware chapter extraction)
- **Section numbers as extraction floor** (every numbered section must have ≥1 node)
- **Typed concept nodes** (FORMULA, DEFINITION, DERIVATION, EXAMPLE, etc.)
- **Visual hints** bridge curriculum graph → design_agent / board intelligence
- **Pre-generated DiagramSpecs** eliminate 10-15s latency for ~70% of teaching visuals
- **No pre-baked lecture scripts** — the graph IS the curriculum
- **Three-graph architecture**: curriculum (shared spine) + dashboard state (ephemeral) + student knowledge (per-student)

### Context management:
- Implement directly for quality — sub-agents only for exploration
- Each phase boundary = `/compact` or `/clear`
- Design doc + memory file are durable state — survive compact/clear
- Always reference PMG codebase for implementation patterns

### To remove these instructions:
Delete the "Active Multi-Phase Implementation" section and update memory files.
