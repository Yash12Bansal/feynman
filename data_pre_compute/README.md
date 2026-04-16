# Curriculum Graph Pipeline

Build a production-grade knowledge graph from PDF textbooks. Extracts concepts, relationships, and visual hints into Neo4j for real-time teaching.

## Pipeline Stages

```
PDF textbook
  -> Skeleton extraction (whole-book structure in one LLM call)
  -> Anchor extraction (deterministic: section numbers, figures, examples)
  -> Chapter extraction (book-aware two-pass LLM extraction per chapter)
  -> Structural validation + gap-filling loop
  -> Entity resolution (hash-based chunk merging within chapters)
  -> Book unification (cross-chapter resolve, hierarchy, shared concepts)
  -> Visual pre-generation (DiagramSpec for concepts with visual_hint)
  -> Neo4j ingestion (Cypher MERGE + embeddings)
  -> Salience scoring (static rules + structural PageRank)
  -> Semantic validation (LLM spot-checks on sample)
```

## Project Structure

```
src/lecture_pipeline/
├── cli.py                         # CLI entry point (5 commands)
├── config.py                      # YAML + env-based configuration
├── pipeline.py                    # Main orchestrator
├── pdf/
│   ├── parser.py                  # PyMuPDF text + image + OCR extraction
│   └── toc.py                     # TOC detection + chapter tree building
├── llm/
│   ├── base.py                    # Abstract LLMProvider interface
│   ├── openai_provider.py         # OpenAI / Ollama / vLLM compatible
│   ├── anthropic_provider.py      # Claude
│   └── factory.py                 # Provider factory
└── curriculum/
    ├── models.py                  # Pydantic models (nodes, edges, extraction results)
    ├── schema.py                  # Neo4j schema (constraints, indexes)
    ├── prompts.py                 # LLM prompt templates
    ├── skeleton_extractor.py      # Book skeleton extraction
    ├── anchors/                   # Section anchor extraction
    ├── chapter_extractor.py       # Chapter-level concept extraction
    ├── validation/                # Structural + semantic validation
    ├── merge/                     # Entity resolution within chapters
    ├── unification/               # Cross-chapter unification
    ├── salience/                  # PageRank + static scoring
    ├── ingestion/                 # Neo4j writer, Cypher gen, embeddings
    └── visuals/                   # Visual pre-generation (DiagramSpec)
```

## Setup

```bash
cd data_pre_compute
python -m venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Configuration

Edit `config.yaml`:

```yaml
llm:
  provider: "anthropic"
  model: "claude-sonnet-4-20250514"
  temperature: 0.3
  max_tokens: 16384

neo4j:
  uri: "bolt://localhost:7687"
  username: "neo4j"
  password: "password"
  database: "neo4j"
```

Set `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`) as an environment variable.

## CLI Commands

```bash
# Full pipeline: PDF -> Neo4j knowledge graph
lecture-pipeline ingest-book book.pdf --subject physics

# With options
lecture-pipeline ingest-book book.pdf -s physics --chapters 1,2,3 --output ./out --verbose
lecture-pipeline ingest-book book.pdf -s physics --skip-neo4j       # extraction only
lecture-pipeline ingest-book book.pdf -s physics --skip-visuals     # skip visual generation
lecture-pipeline ingest-book book.pdf -s physics --skip-embeddings  # skip embeddings
lecture-pipeline ingest-book book.pdf -s physics --skip-salience    # skip salience scoring

# List detected chapters
lecture-pipeline list-chapters book.pdf

# Neo4j graph statistics
lecture-pipeline stats

# Ad-hoc Cypher query
lecture-pipeline query "MATCH (n:Concept) RETURN n.topic_name LIMIT 10"

# Validate a saved extraction JSON
lecture-pipeline validate extraction.json --semantic
```

## Tests

```bash
pytest tests/ -v
```
