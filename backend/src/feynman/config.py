"""Application configuration via environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env at the project root (two levels up from this file: src/feynman/config.py → project root)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    environment: str = "development"
    log_level: str = "DEBUG"
    backend_port: int = 8000
    frontend_url: str = "http://localhost:5173"

    # LLM Providers
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Ollama / Local Models
    ollama_base_url: str = "http://localhost:11434"
    design_agent_provider: str = "anthropic"  # "anthropic" or "ollama"
    design_agent_model: str = ""  # model name for ollama (e.g. "qwen2.5-vl:7b")

    # When True, the anticipation engine ignores `curriculum.pre_generated_visuals`
    # from Neo4j and regenerates every diagram fresh via `generate_design_diagram`.
    # Use this while iterating on the design_agent prompt — Neo4j pre-gens are
    # baked under whatever prompt was active at Phase 12 ingestion time, so they
    # don't reflect prompt edits until the curriculum pipeline re-runs.
    bypass_pregen_visuals: bool = False

    # LiveKit
    livekit_url: str = "ws://localhost:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "devsecret"

    # Speech Providers
    deepgram_api_key: str = ""
    cartesia_api_key: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://feynman:feynman@localhost:5433/feynman"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Neo4j (curriculum graph)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: str = "neo4j"

    # Personalised memory layer. The student knowledge graph is an INDEPENDENT
    # Neo4j subgraph (own labels) — it links to the curriculum graph by id
    # strings only, never by shared nodes.
    memory_lookback_sessions: int = 2  # how many past study-days a chapter card spans
    memory_global_limit: int = 8  # max items per kind on the user-level global card
    interaction_question_mode: str = "mcq"  # "mcq" | "mcq_subjective"
    # NOTE: the student graph is RETAINED in full — never pruned. `lookback`
    # controls only what the memory card SHOWS; the underlying history (for
    # mastery-over-time + analytics) is the product's moat and is kept forever.

    # When True (default), the agent loads curriculum from Neo4j at session
    # start (and on `set_lesson_topic`) — every topic must exist in the graph
    # or `CurriculumNotFoundError` aborts the session. When False, Neo4j is
    # skipped entirely: the agent runs in free-form mode, has no lesson plan,
    # no pre-generated visuals, and no doubt-resolution checklist (the doubt
    # orchestrator still snapshots/restores correctly; the checklist is just
    # empty). Use False for local exercise of the doubt orchestrator without
    # seeding Neo4j, and for any deployment where you don't have curriculum
    # ingested yet.
    use_neo4j_curriculum: bool = True

    # Doubt capture: seconds of continuous silence after the student stops
    # speaking before we finalize the transcript and start reasoning. The STT's
    # own VAD already endpoints the utterance at ~350ms, so this is only a
    # "don't cut a mid-thought pause" buffer. A doubt is question-shaped and
    # often has a thinking pause mid-sentence ("which state has the… [pause]
    # …weakest forces?"). 1.2s cut those off, truncating the doubt and making
    # Feynman answer the wrong thing. 3s balances pause-room against the dead
    # air after the student finishes (a fixed timer can't tell "thinking" from
    # "done" — see the semantic-endpointing item in todo.md for the real fix).
    # Tune via env.
    doubt_silence_timeout_s: float = 3.0

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"


settings = Settings()
