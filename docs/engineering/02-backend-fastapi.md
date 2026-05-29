# 02 — Backend FastAPI (`backend/src/feynman/`)

**Branch:** `feat/unify_boardstate` · **Last verified:** 2026-05-28

> Scope: the FastAPI HTTP layer, session lifecycle, database, Redis, knowledge module stub. The teaching state machine itself is `03-teaching-state-machine.md`. The LiveKit worker is `04-livekit-agent-worker.md`. The visuals protocol is `07-contracts-and-protocols.md`.

## TL;DR

The FastAPI server is **thin**. It is a session-bootstrapping HTTP API, not a teaching engine. Three reasons for that:

1. **Real-time audio doesn't go through it.** That path is owned by the separate `feynman.livekit.worker` process, which connects to LiveKit directly. The frontend's `RoomProvider` connects to LiveKit, not to FastAPI.
2. **Visual instructions don't go through it.** Those flow over a LiveKit data-channel topic, again worker → frontend, bypassing FastAPI entirely. The `api/ws.py` file is effectively a placeholder.
3. **Lecture playback (precomputed) doesn't go through it.** Manifests are served by a separate `preview_server.py` (port 8080) inside `data_pre_compute_v2/`.

So FastAPI's actual job is: hand out LiveKit tokens, persist session state, run migrations, and host the experimental diagram-strategy testbed.

```
Browser ──HTTP──▶ FastAPI (:8000)
                  ├─ POST /api/sessions    → create session, mint LK token
                  ├─ GET  /api/sessions/{} → status (hot Redis, cold Postgres)
                  ├─ POST /api/sessions/{}/end
                  ├─ GET  /api/health
                  └─ /api/diagtest/*       → diagram-lab experiments

Browser ──WSS──▶ LiveKit server (:7880)  (NOT FastAPI)
                  ▲
                  │
              LiveKit worker (separate process)
              ├─ subscribes to room audio  → STT → LLM → TTS
              └─ publishes data on topic "visuals" → frontend
```

---

## 1. App bootstrap — `main.py`

`backend/src/feynman/main.py` is 72 lines and does only what's strictly required.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):                       # main.py:24
    setup_logging(settings.log_level)
    engine = create_engine()
    db_factory = create_session_factory(engine)
    redis = create_redis_client()

    if settings.is_dev:                                 # main.py:35
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    app.state.engine = engine
    app.state.db_factory = db_factory
    app.state.redis = redis
    app.state.session_manager = SessionManager(db_factory, redis)
    yield
    await redis.aclose()
    await engine.dispose()

def create_app() -> FastAPI:                            # main.py:51
    app = FastAPI(title="Feynman", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api")
    return app

app = create_app()
```

`uvicorn feynman.main:app --reload` is the dev entrypoint, started by `make dev-backend`.

### Dev-mode auto-create

In `is_dev`, tables are created via `Base.metadata.create_all` so a fresh database "just works." In prod you use Alembic migrations (`make migrate`).

### What lives on `app.state`

- `engine` — SQLAlchemy async engine.
- `db_factory` — `async_sessionmaker(engine, expire_on_commit=False)`.
- `redis` — async `Redis` client.
- `session_manager` — `SessionManager(db_factory, redis)`. Every request handler that needs sessions pulls this directly via `request.app.state.session_manager`.

There is **no FastAPI `Depends` factory for these** — the codebase favors direct app-state access. The only `Depends` is `get_settings()` in `dependencies.py:6-7`.

---

## 2. Config — `config.py`

`Settings` is a `BaseSettings` (Pydantic) that reads from `.env` at the repo root and from env vars.

| Field | Default | Purpose |
|---|---|---|
| `environment` | `development` | Toggles auto-create-tables in `lifespan`. |
| `log_level` | `DEBUG` | structlog level. |
| `backend_port` | `8000` | (Reference; uvicorn is invoked with explicit port.) |
| `frontend_url` | `http://localhost:5173` | CORS allowed origin. |
| `anthropic_api_key` | `""` | Claude. Required for live agent. |
| `openai_api_key` | `""` | GPT. Fallback / sub-task. |
| `ollama_base_url` | `http://localhost:11434` | Local LLM endpoint (used by `design_bridge` + judge). |
| `design_agent_provider` | `anthropic` | `anthropic` or `ollama` — picks the LLM for `design_bridge.generate_design_diagram()`. |
| `design_agent_model` | `""` | Model name when using Ollama. |
| `bypass_pregen_visuals` | `False` | If true, force live regeneration of diagrams (skip Neo4j pre-gens). Debug flag. |
| `livekit_url` | `ws://localhost:7880` | LiveKit signaling URL — handed to the frontend in the create-session response. |
| `livekit_api_key` | `devkey` | LiveKit JWT key. |
| `livekit_api_secret` | `devsecret` | LiveKit JWT secret. |
| `deepgram_api_key` | `""` | STT. |
| `cartesia_api_key` | `""` | TTS. |
| `database_url` | `postgresql+asyncpg://feynman:feynman@localhost:5433/feynman` | Postgres. |
| `redis_url` | `redis://localhost:6379/0` | Redis. |
| `neo4j_uri` | `bolt://localhost:7687` | Curriculum graph. |
| `neo4j_user/password/database` | `neo4j / password / neo4j` | Auth. |
| `use_neo4j_curriculum` | `True` | If false, agent runs without curriculum context. |

`settings.is_dev` is a property returning `environment == "development"`. The module-level `settings` singleton (line 77) is what gets imported everywhere.

---

## 3. API routers — `api/`

`api/router.py` aggregates four sub-routers:

```python
api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(sessions_router, prefix="/sessions", tags=["sessions"])
api_router.include_router(students_router, prefix="/students", tags=["students"])
api_router.include_router(diagtest_router, prefix="/diagtest", tags=["diagtest"])
```

### Health — `api/health.py`

```python
@router.get("/health")
async def health():
    return {"status": "ok"}
```

Zero deps. Used by Docker healthchecks and local sanity.

### Sessions — `api/sessions.py`

Three endpoints. The interesting one is `POST /sessions` — it creates the Postgres row, seeds Redis, **pre-creates the LiveKit room with metadata**, and mints a JWT.

```python
async def _create_livekit_token(room_name: str) -> str:                       # sessions.py:28
    token = api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
    token = token.with_identity(f"student-{uuid4().hex[:8]}").with_name("Student")
    token = token.with_grants(api.VideoGrants(
        room_join=True, room=room_name,
        can_publish=True, can_subscribe=True, can_publish_data=True,
    ))
    return token.to_jwt()

async def _create_livekit_room(                                               # sessions.py:46
    room_name: str, *, topic: str, subject: str | None,
    grade_level: str | None, lecture_chapter_id: str | None,
) -> None:
    lkapi = api.LiveKitAPI(settings.livekit_url, settings.livekit_api_key,
                           settings.livekit_api_secret)
    try:
        meta = json.dumps({
            "topic": topic,
            "subject": subject,
            "grade_level": grade_level,
            "lecture_chapter_id": lecture_chapter_id,
        })
        await lkapi.room.create_room(api.CreateRoomRequest(name=room_name, metadata=meta))
    finally:
        await lkapi.aclose()
```

`POST /sessions` end-to-end (`sessions.py:79-105`):

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
        lecture_chapter_id=create.lecture_chapter_id,
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

The room metadata is **how the LiveKit worker learns what to teach**. When the worker enters the room, it parses `ctx.room.metadata` (JSON) and routes either to interactive-teaching mode (if `topic` is set) or to lecture-playback mode (if `lecture_chapter_id` is set). See `04-livekit-agent-worker.md` §1.

The other two endpoints:

```python
@router.get("/{session_id}", response_model=SessionInfo)
async def get_session(request, session_id: UUID):                              # sessions.py:108
    info = await _get_manager(request).get_session(session_id)
    if info is None: raise HTTPException(404)
    return info

@router.post("/{session_id}/end", response_model=SessionInfo)
async def end_session(request, session_id: UUID):                              # sessions.py:117
    info = await _get_manager(request).end_session(session_id)
    if info is None: raise HTTPException(404)
    return info
```

### Students — `api/students.py`

Placeholder. No routes yet. Reserved for per-student knowledge graph endpoints once the `knowledge/` module is wired.

### WebSocket — `api/ws.py`

Two-line file:

```python
"""Visual streaming WebSocket. Currently unused — visuals go over LiveKit data channel."""
```

This was the original plan. The current architecture uses LiveKit data channels (topic `"visuals"`) instead. If you need to send something to the frontend that isn't audio or visuals, you'd add it here. Nothing does today.

### Diagram-lab — `experiments/diagram_lab/router.py`

In-memory testbed for diagram-generation strategies. Single-user, no auth. Used to A/B different prompts and Claude models against the IGCSE Maths prompt library.

| Endpoint | Method | Purpose |
|---|---|---|
| `/diagtest/strategies` | GET | List registered strategy plugins + their JSON schema for options. |
| `/diagtest/maths-library` | GET | Curated IGCSE/class 9-12 maths prompts. |
| `/diagtest/run` | POST | Run a strategy with `(strategy_id, model, prompt, options)`. Returns generated `DiagramSpec`. |
| `/diagtest/history` | GET | Last 50 runs in an `OrderedDict`. |
| `/diagtest/history/{run_id}` | GET | Detail for one run. |
| `/diagtest/annotate` | POST | Inject annotations into a previously-generated diagram. |

Strategies are loaded from `experiments/diagram_lab/strategies/registry.py`. Each strategy has `.descriptor()`, `.availability()`, `.parse_options()`, `.generate(...)`. The frontend's `DiagramGenerationTestScreen` consumes these endpoints.

---

## 4. Session lifecycle — `session/`

Sessions live in **two stores simultaneously**:

- **Redis** (hot) — `HSET session:<id> status / teaching_state / branch_depth / room_name / subject / created_at / updated_at`. TTL 24h.
- **Postgres** (cold) — `sessions` table with the full SQLAlchemy `SessionModel`.

The hot path during teaching is Redis-only. Postgres is only touched at session creation, on `activate_session` (transition idle → greeting), and on `end_session`.

### Models — `session/models.py`

```python
class SessionModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "sessions"
    room_name:      Mapped[str]  = mapped_column(String(255), unique=True, index=True)
    subject:        Mapped[str | None] = mapped_column(String(50), nullable=True)
    status:         Mapped[str]  = mapped_column(String(20), default=SessionStatus.PENDING)
    teaching_state: Mapped[str]  = mapped_column(String(30), default=TeachingState.IDLE)
    ended_at:       Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

Inherited from `UUIDPrimaryKeyMixin`: `id: UUID = uuid4`. From `TimestampMixin`: `created_at`, `updated_at` with `server_default=now()` and `onupdate=now()`.

### Schemas — `session/schemas.py`

```python
class SessionStatus(StrEnum):
    PENDING = "pending"
    ACTIVE  = "active"
    ENDED   = "ended"

class SessionCreate(BaseModel):
    topic:              str | None = None
    subject:            str | None = None
    grade_level:        str | None = None
    lecture_chapter_id: str | None = None

class SessionInfo(BaseModel):
    id:             UUID
    room_name:      str
    subject:        str | None
    status:         SessionStatus
    teaching_state: TeachingState        # from feynman.agent.states
    branch_depth:   int                  # stack depth in the state machine
    created_at:     datetime
    updated_at:     datetime
    ended_at:       datetime | None = None

class CreateSessionResponse(BaseModel):
    session_id:         UUID
    token:              str              # LiveKit JWT
    livekit_url:        str
    room_name:          str
    lecture_chapter_id: str | None = None
```

Note: `teaching_state` and `branch_depth` are in `SessionInfo` so the HTTP API can expose them. They are pulled from Redis (the worker process updates Redis every state transition).

### Manager — `session/manager.py`

`SessionManager` is the orchestrator across both stores.

```python
class SessionManager:
    def __init__(self, db_factory, redis):                              # manager.py:32
        self._db_factory = db_factory
        self._redis_store = SessionRedisStore(redis)

    async def create_session(self, create: SessionCreate) -> SessionInfo:   # manager.py:36
        session_id = uuid4()
        room_name = f"feynman-{session_id.hex[:12]}"
        async with self._db_factory() as db:
            model = SessionModel(
                id=session_id, room_name=room_name,
                subject=create.subject,
                status=SessionStatus.PENDING,
                teaching_state=TeachingState.IDLE,
            )
            await SessionRepository(db).create(model)
        await self._redis_store.seed(session_id, ...)
        return self._model_to_info(model, branch_depth=1)

    async def get_session(self, session_id) -> SessionInfo | None:      # manager.py:65
        data = await self._redis_store.get(session_id)
        if data:
            return self._redis_to_info(session_id, data)
        async with self._db_factory() as db:
            model = await SessionRepository(db).get_by_id(session_id)
        return self._model_to_info(model, branch_depth=1) if model else None

    async def update_teaching_state(self, session_id, state, branch_depth) -> None:  # manager.py:107
        # Hot path — Redis only. Called frequently by the worker.
        await self._redis_store.update_teaching_state(session_id, state, branch_depth)

    async def end_session(self, session_id) -> SessionInfo | None:      # manager.py:121
        data = await self._redis_store.get(session_id)
        async with self._db_factory() as db:
            repo = SessionRepository(db)
            model = await repo.get_by_id(session_id)
            if model is None: return None
            model.status = SessionStatus.ENDED
            model.ended_at = datetime.now(UTC)
            if data:
                model.teaching_state = data.get("teaching_state", TeachingState.ENDING)
            await repo.update(model)
        await self._redis_store.delete(session_id)
        return self._model_to_info(model, branch_depth=1)
```

### Store — `session/store.py`

Two thin wrappers.

**`SessionRedisStore`** — async wrapper over `redis.asyncio`:

```python
class SessionRedisStore:
    KEY_PREFIX = "session:"
    TTL_SECONDS = 86400    # 24h

    async def seed(self, session_id, *, status, teaching_state, room_name, subject, created_at):
        await self._redis.hset(self._key(session_id), mapping={...})
        await self._redis.expire(self._key(session_id), self.TTL_SECONDS)

    async def get(self, session_id) -> dict | None:
        data = await self._redis.hgetall(self._key(session_id))
        return data or None

    async def update_teaching_state(self, session_id, teaching_state, branch_depth):
        await self._redis.hset(self._key(session_id), mapping={
            "teaching_state": teaching_state,
            "branch_depth": str(branch_depth),
            "updated_at": datetime.now(UTC).isoformat(),
        })

    async def delete(self, session_id):
        await self._redis.delete(self._key(session_id))
```

**`SessionRepository`** — async SQLAlchemy CRUD:

```python
class SessionRepository:
    def __init__(self, db: AsyncSession): self._db = db
    async def create(self, model): self._db.add(model); await self._db.commit(); await self._db.refresh(model)
    async def get_by_id(self, sid): return await self._db.get(SessionModel, sid)
    async def get_by_room_name(self, rn): return await self._db.scalar(select(SessionModel).where(SessionModel.room_name == rn))
    async def update(self, model): await self._db.commit(); await self._db.refresh(model)
```

---

## 5. Knowledge module — stubs

`backend/src/feynman/knowledge/` exists with `models.py`, `schemas.py`, `repository.py`, `service.py`, and a `CLAUDE.md`. **All four code files are stubs today.**

Design intent (from `knowledge/CLAUDE.md`):

- Per-subject knowledge graphs with a shared student profile.
- Three layers per subject: concept mastery, learning patterns, session history.
- Backed by Postgres (single-store, abstract repository pattern, so a future Neo4j swap is doable).
- **Enhancement, not dependency** — the teaching agent must work great without it. Most students rarely ask doubts, so the graph stays naturally sparse for most students.

Nothing imports from `knowledge/` at runtime yet. The teaching agent's `TeachingContext.curriculum` field holds the *curriculum* graph (loaded from Neo4j by `agent/curriculum_loader.py`), which is unrelated.

---

## 6. DB layer — `db/`

### Engine — `db/engine.py`

```python
def create_engine() -> AsyncEngine:                                     # db/engine.py:8
    return create_async_engine(
        settings.database_url,
        echo=settings.is_dev,           # logs SQL in dev
        pool_pre_ping=True,             # verify conn before reuse
    )

def create_session_factory(engine) -> async_sessionmaker:               # db/engine.py:16
    return async_sessionmaker(engine, expire_on_commit=False)
```

### Base + mixins — `db/base.py`

```python
class Base(DeclarativeBase): pass

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

class UUIDPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
```

### Alembic — `backend/alembic/`

`alembic/env.py` imports `Base.metadata` and overrides `sqlalchemy.url` from settings. Online runs go through `async_engine_from_config → connect → run_sync → dispose`. Migrations are applied with `make migrate` (alias for `uv run alembic upgrade head`).

Current migrations:

| Revision | File | Effect |
|---|---|---|
| `d36697d13f1b` | `versions/d36697d13f1b_create_sessions_table.py` | Creates `sessions` table with `id (UUID PK), room_name (unique), subject, status, teaching_state, ended_at, created_at, updated_at`. Adds unique index on `room_name`. |

That's the only table. Knowledge graph migrations will appear when the knowledge module ships.

---

## 7. Redis — `redis/client.py`

```python
def create_redis_client() -> Redis:                                     # redis/client.py:8
    return Redis.from_url(settings.redis_url, decode_responses=True)
```

`decode_responses=True` returns strings, not bytes — important since the session store stores ISO timestamps and enum string values.

The only consumer right now is the session store. No pub/sub, no streams.

---

## 8. Common — `common/`

| File | Contents |
|---|---|
| `exceptions.py` | `FeynmanError`, `SessionNotFoundError`, `SessionAlreadyActiveError`, `StudentNotFoundError`, `ToolConstraintError`. The last one is surfaced back to the LLM as a tool error so the agent can correct course. |
| `types.py` | Type aliases (`SessionId = UUID`), `Subject` enum (`MATH/PHYSICS/CHEMISTRY/BIOLOGY`), `LLMProvider` enum. |
| `logging.py` | `setup_logging(level)` configures structlog with `merge_contextvars + add_log_level + add_logger_name + TimeStamper(ISO) + StackInfoRenderer + ExceptionPrettyPrinter`. Also includes `_IPCSafeFormatter` (lines 35-61) — a workaround for LiveKit's subprocess logging pickling `LogRecord`s across processes, which stringifies structlog's msg dict; the formatter strips sentinel attrs so records are treated as foreign. |

---

## 9. Dependencies — `backend/pyproject.toml`

The relevant deps:

| Dep | Why |
|---|---|
| `fastapi >= 0.115`, `uvicorn[standard]` | HTTP server. |
| `livekit-agents >= 1.0` | Agent worker SDK. |
| `livekit-plugins-{deepgram,cartesia,silero,turn-detector,anthropic,openai}` | STT, TTS, VAD, turn detection, LLM bindings. |
| `sqlalchemy[asyncio]`, `asyncpg`, `alembic` | DB + migrations. |
| `redis[hiredis]` | Session hot store. |
| `neo4j >= 5.20` | Curriculum graph driver (used by `agent/curriculum_loader.py`). |
| `pydantic >= 2.10`, `pydantic-settings` | Models + env config. |
| `structlog`, `websockets` | Logging, WS support. |
| `feynman-teaching-kernel` | Shared planning kernel (editable path dep to `../feynman_teaching_kernel`). |

Dev: `ruff`, `pytest + pytest-asyncio + pytest-cov`, `fakeredis`, `httpx`, `pre-commit`.

Lint config: ruff line length 100, rule set `E W F I N UP B SIM ASYNC RUF`, target py3.13. Tests: `asyncio_mode = "auto"`.

---

## 10. Why so thin?

Compare to the LiveKit worker (`04-livekit-agent-worker.md`) — that file is ~950 lines and does the real teaching work. The FastAPI server is ~70 lines because:

- **Audio is WebRTC** — frontend talks to LiveKit directly, worker subscribes server-side. No FastAPI in the path.
- **Visuals are LiveKit data channels** — same thing.
- **The teaching state machine** lives in `agent/state_machine.py` and is owned by the worker per session, not by FastAPI.
- **Curriculum data** lives in Neo4j; the worker queries Neo4j directly via `agent/curriculum_loader.py`.

The FastAPI server only owns the *Session resource* in the REST sense (create, read, end) plus token minting and migration ops. Everything else is bypassed for latency.

---

## Reading order for a new engineer

1. `main.py` — 72 lines, the whole bootstrap.
2. `config.py` — every env var.
3. `api/sessions.py` — the one router that actually does work.
4. `session/manager.py:32-142` — the lifecycle.
5. `session/store.py` — Redis vs Postgres split.
6. Then jump to `04-livekit-agent-worker.md` to follow what happens *after* the JWT is handed out.
