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
- **Visuals are typed instructions** — backend generates commands like `draw_diagram`, `show_equation`, frontend renders them. Clean separation.
- **Knowledge graph is an enhancement, not a dependency** — system works great without it, works better with it.
- **PostgreSQL for everything** (no Neo4j yet) — abstract repository allows future swap.
