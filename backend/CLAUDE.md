# Backend — Feynman

Python 3.13 + FastAPI. Managed with `uv`.

## Module Map

| Module       | Purpose                                                                                      |
| ------------ | -------------------------------------------------------------------------------------------- |
| `agent/`     | Teaching state machine — stack-based branching, state definitions, LLM prompts and tools     |
| `livekit/`   | LiveKit integration — agent worker (separate process), room management, STT/LLM/TTS pipeline |
| `knowledge/` | Per-student knowledge graph — models, repository pattern, business logic                     |
| `visuals/`   | Visual instructions — typed commands sent to frontend for rendering                          |
| `session/`   | Session lifecycle — Redis for hot state, Postgres for persistence                            |
| `api/`       | FastAPI routers — REST endpoints + WebSocket for visual streaming                            |
| `db/`        | SQLAlchemy async engine, declarative base, mixins                                            |
| `redis/`     | Async Redis client factory                                                                   |
| `common/`    | Exceptions, structlog setup, shared types/enums                                              |

## Commands

```bash
uv run uvicorn feynman.main:app --reload    # Dev server
uv run pytest -x -v                          # Tests
uv run ruff check src/ tests/                # Lint
uv run ruff format src/ tests/               # Format
```

## Conventions

- **Async everywhere** — no sync IO. Use `asyncpg`, `redis.asyncio`, etc.
- **Pydantic for all data** — schemas, settings, visual instructions
- **structlog for logging** — `logger = structlog.get_logger()` at module level
- **Import style**: `from feynman.agent.states import TeachingState`
- **Tests live in `tests/`** with `unit/` and `integration/` subdirectories
