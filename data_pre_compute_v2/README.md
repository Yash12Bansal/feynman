# Curriculum Pipeline v2

Standalone precompute pipeline that turns a PDF textbook into a Neo4j knowledge graph with pre-rendered TTS audio. Runtime agent plays the cached audio and renders diagrams at marker points — zero live TTS, zero live LLM in the main flow.

Sibling to `data_pre_compute/` (v1); v2 carries forward v1's PDF/anchors/skeleton/LLM patterns and replaces the schema with a flat Topic/Diagram/Question model.

## Pipeline (12 phases)

```
PDF
 → parse + OCR
 → TOC + section anchors
 → BookSkeleton (1 LLM call)
 → Topics (one per anchored section)
 → enrichment (joint our_understanding+examples, diagrams, questions+judge)
 → within-book PREREQ linking
 → validation gate (structural + semantic + render-test)
 → lecture script (per-chapter narration with <<SHOW_DIAGRAM:id>> markers)
 → script split + Kokoro TTS → manifest events
 → diagram fallback render (SVG → PNG)
 → embeddings (sentence-transformers default, OpenAI optional)
 → Neo4j ingest + verify
```

## Setup

Managed by Poetry, virtualenv lives in `./.venv/` inside this directory.

```bash
cd data_pre_compute_v2

# One-time: install dependencies. Poetry creates .venv/ in-project (see poetry.toml).
poetry install                            # core + sentence-transformers
poetry install --with dev                 # + tests
poetry install --extras "tts render"      # + Kokoro TTS, cairosvg
poetry install --extras "tts render" --with dev   # everything

# Activate
source .venv/bin/activate
# or just prefix with: poetry run lecture-pipeline-v2 ...
```

## External services

### Neo4j (graph store)

Already configured in the project's root `docker-compose.yml`:

| Setting    | Value                   |
| ---------- | ----------------------- |
| Bolt URI   | `bolt://localhost:7687` |
| Browser UI | `http://localhost:7474` |
| Username   | `neo4j`                 |
| Password   | `password`              |
| Database   | `neo4j`                 |
| Plugins    | APOC enabled            |

Start it:

```bash
cd ..                              # back to project root
docker compose up -d neo4j         # waits ~10s, exposes Bolt + Browser
docker compose logs -f neo4j       # to watch startup
```

Schema is created automatically on the first `ingest-book` run, or manually:

```bash
poetry run lecture-pipeline-v2 init-schema
```

### Ollama (judge model)

```bash
# Install Ollama once: https://ollama.com
ollama pull qwen3:8b               # ~5GB at 4-bit, fits 24GB
ollama serve                       # if not auto-running
```

Note: there is no `qwen3.5:9b` — `qwen3:8b` is the closest available size.

### Switching the ingestion model (single place)

The whole authoring path runs through one provider abstraction. Set
`llm.provider` + `llm.model` in `config.yaml` and every stage (skeleton,
topics, prereqs, questions, lesson planner, diagram generator, book-example
weaver, highlight aligner, semantic validation, vision DiagramQA) uses it:

```yaml
llm:
  provider: "gemini" # "anthropic" | "openai" | "gemini" | "ollama"
  model: "gemini-2.5-pro" # any model id valid for that provider
```

The API key is read from the matching env var automatically. Optional per-role
overrides (`enrichment.diagram_qa.*` for vision QA, `enrichment.lesson_pipeline.
judge_*` for the LLM-as-judge) let you pin a different model for those roles —
unset, they follow the main switch. See `config.yaml` for examples.

Notes:

- DiagramQA needs a **vision-capable** model; if the chosen model can't see
  images it degrades gracefully (skips QA, never blocks).
- A judge model that differs from the author reduces correlated error.

### API keys (env vars)

| Var                                    | Required for                                            |
| -------------------------------------- | ------------------------------------------------------- |
| `ANTHROPIC_API_KEY`                    | `llm.provider: anthropic` (Claude)                      |
| `OPENAI_API_KEY`                       | `llm.provider: openai`, or `embedding.provider: openai` |
| `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) | `llm.provider: gemini`                                  |

(`ollama` is local + keyless.)

## Commands

```bash
# Sanity-check chapter detection
poetry run lecture-pipeline-v2 list-chapters /path/to/book.pdf

# Initialize Neo4j schema
poetry run lecture-pipeline-v2 init-schema

# Ingest by chapter name (substring match, case-insensitive)
poetry run lecture-pipeline-v2 ingest-book /path/to/book.pdf \
    -s physics --chapter "Simple Harmonic Motion" --output ./out

# Ingest by index
poetry run lecture-pipeline-v2 ingest-book /path/to/book.pdf -s physics --chapters 12,13,14

# Full book — idempotent, skips what's already in graph
poetry run lecture-pipeline-v2 ingest-book /path/to/book.pdf -s physics

# Force a full recompute
poetry run lecture-pipeline-v2 ingest-book /path/to/book.pdf -s physics --force

# Skip expensive phases while iterating on prompts
poetry run lecture-pipeline-v2 ingest-book /path/to/book.pdf -s physics \
    --skip-tts --skip-questions --skip-embeddings --skip-neo4j --output ./out

# Inspect the graph
poetry run lecture-pipeline-v2 stats
poetry run lecture-pipeline-v2 query "MATCH (t:Topic) RETURN t.topic_name LIMIT 20"
```

## Schema

| Label      | Purpose                                             |
| ---------- | --------------------------------------------------- |
| `Chapter`  | book chapter; holds chapter-level lecture manifest  |
| `Topic`    | one per anchored section; holds standalone manifest |
| `Diagram`  | renderer-specific (svg or manim) + fallback PNG     |
| `Question` | with pre-rendered audio for question + answer       |

| Edge           | Used for                                    |
| -------------- | ------------------------------------------- |
| `CONTAINS`     | Chapter → Topic                             |
| `NEXT`         | Topic → Topic (lecture flow only)           |
| `PREREQ`       | Topic → Topic (reference only, within-book) |
| `HAS_DIAGRAM`  | Topic → Diagram                             |
| `HAS_QUESTION` | Topic → Question                            |

## Idempotency

By default, the pipeline reads existing graph state once and skips work for
content that already exists (topics, diagrams, questions, audio manifests,
embeddings). Pass `--force` to recompute everything regardless.
