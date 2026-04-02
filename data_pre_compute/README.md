# Lecture Pipeline

PDF to lecture script and concept graph generator. Takes any PDF textbook, detects chapters, and generates either a direct lecture script or a structured concept graph (with optional lecture generation from the graph).

## Features

- **Two modes**: Direct lecture script generation, or concept graph extraction
- **LLM agnostic**: Works with OpenAI, Anthropic (Claude), Ollama, vLLM, or any OpenAI-compatible API
- **PDF parsing**: Text extraction, image extraction, OCR fallback for scanned PDFs
- **Chapter detection**: Automatic TOC detection or manual page range input
- **Concept graph**: Directed graph with parent-child hierarchy + cross-relationships (prerequisite, related, leads_to, example_of)
- **Topic deep-dive**: Focus on a specific topic within a chapter for in-depth lecture generation
- **Quality levels**: Beginner (simple, analogies-heavy) or Advanced (derivations, edge cases, exam tips)
- **Graph visualization**: Interactive D3.js-based HTML visualization
- **CLI + Python API**: Use from terminal or import in your code

## Project Structure

```
src/lecture_pipeline/
├── config.py                      # YAML + env-based configuration
├── cli.py                         # CLI entry point (3 commands)
├── pipeline.py                    # Main orchestrator
├── pdf/
│   ├── parser.py                  # PyMuPDF text + image + OCR extraction
│   └── toc.py                     # TOC detection + chapter tree building
├── llm/
│   ├── base.py                    # Abstract LLMProvider interface
│   ├── openai_provider.py         # OpenAI / Ollama / vLLM compatible
│   ├── anthropic_provider.py      # Claude
│   └── factory.py                 # Provider factory
├── graph/
│   ├── models.py                  # ConceptNode, ConceptEdge, ConceptGraph
│   ├── builder.py                 # LLM-powered graph construction
│   └── serializer.py              # JSON / YAML / Markdown export
└── lecture/
    ├── script_generator.py        # Mode 1: text -> lecture
    └── graph_generator.py         # Mode 2: graph -> lecture
```

## Setup

```bash
cd data_pre_compute
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Configuration

Edit `config.yaml` in the project root:

```yaml
llm:
  provider: "anthropic"          # "openai" or "anthropic"
  model: "claude-sonnet-4-20250514"
  api_key: ""                    # or set OPENAI_API_KEY / ANTHROPIC_API_KEY env var
  # base_url: "http://localhost:11434/v1"  # for Ollama / vLLM
  temperature: 0.3
  max_tokens: 16384
```

For Ollama:
```yaml
llm:
  provider: "openai"
  model: "llama3"
  base_url: "http://localhost:11434/v1"
```

## Quick Start

```bash
# List chapters in a PDF
lecture-pipeline list-chapters book.pdf

# Generate concept graph
lecture-pipeline run book.pdf --mode graph -o ./output

# Generate lecture script
lecture-pipeline run book.pdf --mode lecture_script -o ./output

# Generate lecture from an existing graph
lecture-pipeline from-graph output/chapter_graph.json -o ./output
```

## Python API

```python
from lecture_pipeline.pipeline import Pipeline
from lecture_pipeline.config import PipelineConfig

config = PipelineConfig.load("config.yaml")
pipeline = Pipeline(config)

# Graph only
result = pipeline.run("book.pdf", mode="graph")

# Graph + lecture from graph
result = pipeline.run("book.pdf", mode="graph", generate_lec_from_graph=True)

# Direct lecture
result = pipeline.run("book.pdf", mode="lecture_script")

# Save outputs
result.save("./output")
```

## Output

Depending on mode, the pipeline generates:

| Mode | Output Files |
|------|-------------|
| `graph` | `_graph.json`, `_graph_outline.md` |
| `graph` + `generate_lec_from_graph` | `_graph.json`, `_graph_outline.md`, `_lecture.md` |
| `lecture_script` | `_lecture.md` |
| `--topic` deep-dive | `_deep_dive.md` |

Images are extracted to a `_images/` directory (page renders + embedded raster images).

## Visualization

```bash
python visualize.py output/chapter_graph.json
# Opens an interactive D3.js graph in your browser
```

## Test Script

See [README_TEST.md](README_TEST.md) for all test commands and parameter documentation.
