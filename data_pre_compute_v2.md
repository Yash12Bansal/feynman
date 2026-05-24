# Data Pre-Compute v2 — Setup & Test Guide

A standalone offline pipeline that turns a PDF textbook into a Neo4j curriculum graph with pre-rendered TTS audio + a React preview player that streams it back as a "classroom feel" lecture.

```
PDF
 → parse + OCR + section anchors
 → BookSkeleton (whole-book LLM call)
 → per-section Topics (one joint LLM call → our_understanding + examples)
 → enrichment (DiagramSpec generation + Question generation with judge)
 → within-book PREREQ linking
 → validation gate (structural + semantic + render-test)
 → per-chapter lecture script (with <<SHOW_DIAGRAM:id>> + <<PAUSE>> markers)
 → split + Kokoro TTS → manifest events on Chapter / Topic nodes
 → diagram fallback PNG render (cairosvg)
 → embeddings (sentence-transformers MiniLM, local MPS)
 → idempotent Neo4j MERGE + verify
```

The runtime preview walks the manifest, plays cached audio, and renders DiagramSpecs in the existing `SplitBoard` component — no live LLM, no live TTS.

---

## 1. Prerequisites

Install these once on your machine:

| Tool | Version | Install |
|---|---|---|
| **macOS** | Sequoia or later | Apple |
| **Homebrew** | latest | `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"` |
| **Python** | 3.11.x (3.12 also OK) | `brew install python@3.11` |
| **Poetry** | 2.x | `brew install poetry` |
| **Node** | 20.x or 25.x | `brew install node` |
| **pnpm** | 11.x | `npm install -g pnpm` |
| **Docker Desktop** | latest | Download from docker.com — must be **running** before pipeline starts |
| **ffmpeg** | latest | `brew install ffmpeg` — required for Kokoro MP3 output + audio stitching |
| **Ollama** | latest | Download Ollama desktop app from ollama.com |
| **Git LFS** *(optional)* | latest | `brew install git-lfs` — only needed if you commit audio fixtures |

Confirm each:

```bash
python3.11 --version
poetry --version
node --version && pnpm --version
docker --version
ffmpeg -version | head -1
ollama --version
```

---

## 2. Clone & branch

```bash
cd ~/Desktop/Projects   # or wherever you keep repos
git clone https://github.com/Yash12Bansal/feynman.git
cd feynman
git checkout feature/data_pre_compute_v2
```

---

## 3. External services

### Neo4j (curriculum graph — required)

A Docker service is pre-configured in the repo's `docker-compose.yml`. Bring it up:

```bash
docker compose up -d neo4j
```

This exposes:

| | |
|---|---|
| **Bolt URI** | `bolt://localhost:7687` |
| **Browser UI** | `http://localhost:7474` |
| **Username / password** | `neo4j` / `password` |
| **Database** | `neo4j` |
| **Plugins** | APOC enabled |

Verify it's healthy:
```bash
docker compose ps neo4j        # should show STATUS=healthy after ~15s
docker compose logs -f neo4j   # for live logs
```

The first ingest auto-initialises schema (constraints, indexes, vector indexes). To do it manually:
```bash
cd data_pre_compute_v2
poetry run lecture-pipeline-v2 init-schema
```

To wipe and start fresh:
```cypher
// in Neo4j browser
MATCH (n) DETACH DELETE n;
```

### Ollama (multi-model judge — required for question validation)

Start the Ollama desktop app (menu-bar icon). Then pull the judge model:

```bash
ollama pull qwen3:8b
ollama list                    # should show qwen3:8b
```

Resource note: qwen3:8b at 4-bit ≈ 5 GB RAM; fits comfortably on M4 Pro 24 GB.

If you don't have Ollama running, the pipeline still works — generated questions just get `solution_confidence = 0.0` and `needs_review = true`, so they're flagged but not lost.

---

## 4. API keys (env vars)

| Variable | Required for | How to get |
|---|---|---|
| `ANTHROPIC_API_KEY` | Skeleton, topic extraction, diagrams, questions, lecture script | console.anthropic.com → Settings → API Keys |
| `OPENAI_API_KEY` | Only if you switch embedding provider to `openai` in config (default uses local sentence-transformers, no key needed) | platform.openai.com → API keys |

```bash
# Add to ~/.zshrc or ~/.bashrc
export ANTHROPIC_API_KEY="sk-ant-..."
# Reload
source ~/.zshrc
```

---

## 5. Install Python dependencies (Poetry)

```bash
cd ~/Desktop/Projects/feynman/data_pre_compute_v2
poetry install                              # core
poetry install --extras "tts render"        # add Kokoro TTS + cairosvg
poetry install --extras "preview"           # add FastAPI + uvicorn (for preview_server)
poetry install --extras "tts render preview"  # all of the above
poetry install --with dev                   # add pytest etc.
```

Poetry creates `.venv/` inside `data_pre_compute_v2/` (see `poetry.toml`). All future commands use `poetry run` to enter that venv.

First Kokoro run downloads `~/.cache/huggingface` model weights (~80 MB) — that's one-time.

---

## 6. Pipeline configuration

Edit `data_pre_compute_v2/config.yaml` if defaults don't suit you. Defaults:

```yaml
llm:
  provider: "anthropic"
  model: "claude-sonnet-4-6"
  temperature: 0.3
  max_tokens: 16384

tts:
  provider: "kokoro"
  voice: "af_heart"         # other voices: af_bella, am_michael, etc.
  output_format: "mp3"      # set to "wav" if you don't have ffmpeg

validation:
  judge_models:
    - provider: "ollama"
      model: "qwen3:8b"
  judge_agreement_threshold: 0.5

embedding:
  provider: "sentence_transformers"           # alt: "openai"
  model: "sentence-transformers/all-MiniLM-L6-v2"
  dimensions: 384

neo4j:
  uri: "bolt://localhost:7687"
  username: "neo4j"
  password: "password"
```

---

## 7. Fast path — skip ingestion entirely

The repo ships a canonical fixture: H.C. Verma chapter 5 fully precomputed (audio fragments, diagram PNGs/SVGs, and `out/extraction.json` containing the full Neo4j graph state). To go from `git clone` → playable lecture without running any LLM or TTS:

```bash
cd ~/Desktop/Projects/feynman
docker compose up -d neo4j         # start Neo4j

cd data_pre_compute_v2
poetry install --extras "preview"  # core + FastAPI for the preview server

# Hydrate Neo4j from the committed extraction JSON — zero LLM calls.
poetry run lecture-pipeline-v2 load-extraction ./out/extraction.json
# Should report: "Ingestion OK — 125/125 statements, 55 nodes, 70 rels"
# Takes ~1.5 seconds.

# Confirm
poetry run lecture-pipeline-v2 stats
# Expect: Chapter=1, Topic=7, Diagram=12, Question=35
```

That's it — Neo4j now has chapter 5's graph (manifests, diagrams, questions) and `artifacts/audio/chapter_physics_newtons_laws_of_motion/` already contains the 126 MP3 fragments referenced by the manifest. You can now skip to **§9 Preview servers** to play it back. ~12 MB of fixtures travel with the repo.

> **No need for ANTHROPIC_API_KEY, no need for Ollama, no need for Kokoro/PyTorch.** Those are only required if you want to ingest new chapters yourself. Everything below in §7-§8 covers that "full ingestion" path; skip if the fixture is enough for your immediate needs.

---

## 7b. Full ingestion (when you want to add new chapters)

### Quick test on H.C. Verma chapter 5 (Newton's Laws of Motion)

This is the canonical smoke-test chapter. Drop the PDF anywhere; we use `~/Downloads/H C Verma- Concepts of Physics 1.pdf`.

```bash
cd ~/Desktop/Projects/feynman/data_pre_compute_v2

# 1. Sanity-check chapter detection (no LLM calls, no Neo4j)
poetry run lecture-pipeline-v2 list-chapters \
    "/Users/gauravkasat/Downloads/H C Verma- Concepts of Physics 1.pdf"

# Output should show "5. Newton's Laws of Motion (pages 74-94, 21 pages)"

# 2. Full ingest of chapter 5 — first pass without TTS to iterate on quality
poetry run lecture-pipeline-v2 ingest-book \
    "/Users/gauravkasat/Downloads/H C Verma- Concepts of Physics 1.pdf" \
    --subject physics \
    --chapters 5 \
    --skip-tts \
    --output ./out \
    --verbose
```

Expect ~13 minutes wall time (sequential topic extraction is the bottleneck). Output:

```
Pipeline complete — .../book.pdf
  Subject: physics
  Counts: 1 chapters, 7 topics, 14 diagrams, 35 questions
  Skipped: lecture_script, tts
  Total time: 776.9s
  Extraction saved: out/extraction.json
```

### Add TTS in a second pass

```bash
poetry run lecture-pipeline-v2 ingest-book \
    "/Users/gauravkasat/Downloads/H C Verma- Concepts of Physics 1.pdf" \
    --subject physics \
    --chapters 5 \
    --force \
    --skip-questions \
    --output ./out \
    --verbose
```

`--skip-questions` saves ~5 min of Ollama judging on this pass. Expect ~5–7 min total (TTS is ~3 min of that — Kokoro runs at ~11× realtime on CPU; MPS is actually slower for this model so we leave it on CPU).

After completion you'll have:

```
artifacts/audio/chapter_physics_newtons_laws_of_motion/
    topic_..._5_1_chapter_000.mp3        # chapter-narration fragments
    topic_..._5_1_standalone_000.mp3     # standalone-narration fragments
    ...
artifacts/diagrams/
    diagram_..._5_1_inertial_vs_non_inertial.png
    diagram_..._5_1_inertial_vs_non_inertial.svg
    ...
out/extraction.json                       # the full extraction in JSON
```

### CLI cheatsheet

```bash
# Always run from data_pre_compute_v2/
poetry run lecture-pipeline-v2 --help

# Discovery
poetry run lecture-pipeline-v2 list-chapters book.pdf

# Schema
poetry run lecture-pipeline-v2 init-schema

# Ingest variants
poetry run lecture-pipeline-v2 ingest-book book.pdf --subject physics --chapters 5
poetry run lecture-pipeline-v2 ingest-book book.pdf --subject physics --chapter "Newton"  # by name substring
poetry run lecture-pipeline-v2 ingest-book book.pdf --subject physics --chapters 5,6,7   # multiple
poetry run lecture-pipeline-v2 ingest-book book.pdf --subject physics                    # whole book

# Skip flags (combine as needed)
--skip-tts          # skip lecture script + TTS phases
--skip-questions    # skip question generation + Ollama judging
--skip-visuals      # skip diagram generation
--skip-embeddings   # skip sentence-transformers
--skip-neo4j        # extract only, dump to ./out/extraction.json
--skip-prereqs      # skip within-book prereq linking
--force             # ignore idempotency snapshot; recompute everything

# Inspection
poetry run lecture-pipeline-v2 stats
poetry run lecture-pipeline-v2 query "MATCH (t:Topic) RETURN t.section_number, t.topic_name LIMIT 20"
poetry run lecture-pipeline-v2 verify-graph ./out/extraction.json   # check what landed
poetry run lecture-pipeline-v2 validate ./out/extraction.json --semantic

# Replay a saved extraction into Neo4j (no LLM/TTS — for sharing snapshots)
poetry run lecture-pipeline-v2 load-extraction ./out/extraction.json
```

---

## 8. Inspecting results

### Neo4j browser

Open `http://localhost:7474`, login `neo4j` / `password`, then:

```cypher
// 1. All chapters that have manifests (TTS-complete)
MATCH (c:Chapter)
RETURN
  c.chapter_id AS id,
  c.chapter_index AS idx,
  c.title AS title,
  c.chapter_manifest IS NOT NULL AS has_audio
ORDER BY idx;

// 2. Topics in lecture order for a chapter
MATCH (c:Chapter)-[:CONTAINS]->(t:Topic)
WHERE c.chapter_index = 5
RETURN
  t.within_chapter_order AS ord,
  t.section_number,
  t.topic_name,
  t.needs_review,
  size(t.our_understanding) AS understanding_len,
  size(t.examples) AS num_examples
ORDER BY ord;

// 3. Questions per topic with confidence
MATCH (t:Topic)-[:HAS_QUESTION]->(q:Question)
RETURN
  t.within_chapter_order AS ord,
  t.section_number,
  count(q) AS q_count,
  sum(CASE WHEN q.needs_review THEN 1 ELSE 0 END) AS flagged,
  avg(q.solution_confidence) AS avg_conf
ORDER BY ord;

// 4. Diagrams per topic
MATCH (t:Topic)-[:HAS_DIAGRAM]->(d:Diagram)
RETURN
  t.within_chapter_order AS ord,
  t.section_number,
  count(d) AS diagram_count,
  collect(d.description) AS descriptions
ORDER BY ord;

// 5. NEXT chain walking
MATCH path = (start:Topic {section_number: '5.1'})-[:NEXT*]->(:Topic)
RETURN [n IN nodes(path) | n.section_number] AS chain;

// 6. PREREQ edges (cross-section dependencies)
MATCH (a:Topic)-[:PREREQ]->(b:Topic)
RETURN
  a.section_number AS from_section, a.topic_name AS from_name,
  b.section_number AS to_section,  b.topic_name AS to_name;
```

### Stitch chapter into one MP3 (offline listening)

```bash
poetry run python tools/stitch_chapter_audio.py \
    --chapter-id "chapter:physics:newtons_laws_of_motion" \
    --output /tmp/chapter5_full.mp3

afplay /tmp/chapter5_full.mp3
```

The script reads the chapter manifest, concatenates audio fragments with silent pauses inserted for `pause` events, and ignores `show_diagram` / `topic_start` events (those are UI-only).

---

## 9. Preview servers (classroom-feel playback)

There are **two** preview surfaces — pick whichever you prefer.

### A) Plain HTML player (`preview_server.py` only, no React build)

Fast to spin up. Renders diagrams as raw PNGs.

```bash
poetry run python tools/preview_server.py
# Open http://localhost:8080
```

### B) Full SplitBoard React integration (recommended for the real classroom feel)

Uses the same React `SplitBoard` component that drives the live LiveKit classroom — cross-fade, stroke-reveal SVG animation, DraftingLoader between topics, sharp KaTeX rendering.

**Terminal 1 — backend (preview_server on :8080)**:
```bash
cd ~/Desktop/Projects/feynman/data_pre_compute_v2
poetry run python tools/preview_server.py
```

**Terminal 2 — frontend (Vite dev on :5173)**:
```bash
cd ~/Desktop/Projects/feynman/frontend
pnpm install            # one-time
pnpm dev                # starts dev server on :5173
```

Then open:
```
http://localhost:5173/#/lecture-preview
```

The chapter-list view shows a `SplitBoard · localhost:5173` blue pill (so you can tell it apart from the plain HTML player). Click `Newton's Laws of Motion` → click `▶ Play`.

What happens visually:
- **Topic boundary** → DraftingLoader animation (grid + neon lines + compass arc) appears on the slide panel
- **`show_diagram`** event → diagram cross-fades in over the loader, with SVG paths stroke-revealing
- **`audio`** event → MP3 plays via HTML5 `<audio>` element
- **`pause`** event → silent gap (250 ms / 750 ms)
- **`topic_start`** event → updates the chapter banner

The Vite dev server proxies `/lecture-api/*` and `/lecture-artifacts/*` to `localhost:8080` so the React app can fetch manifests and audio without CORS issues. The existing `/api/*` proxy to the live LiveKit backend on `:8000` is undisturbed.

---

## 10. Common gotchas

### "Chapter not found" when stitching or previewing

The Chapter node's `chapter_index` is stored from the **filtered list** position, not the original book position, in pre-Nov-2026 ingests. If you ran `--chapters 5` only, the chapter ended up with `chapter_index = 1` in Neo4j. Fix per chapter:

```cypher
MATCH (c:Chapter {chapter_id: 'chapter:physics:newtons_laws_of_motion'})
SET c.chapter_index = 5
RETURN c.chapter_id, c.chapter_index;
```

Fresh ingests on `feature/data_pre_compute_v2` and later use the original index — no manual fix needed.

### `pnpm` not found

```bash
npm install -g pnpm
```

### Vite says "port 5173 in use"

A stale `node` process is hanging on. Kill it:
```bash
lsof -ti:5173 | xargs -r kill -9
```

### Preview server: `address already in use`

Same for port 8080:
```bash
lsof -ti:8080 | xargs -r kill -9
```

### Neo4j: connection refused

Docker daemon isn't running or Neo4j container is stopped:
```bash
docker info >/dev/null && echo OK || echo "start Docker Desktop manually"
cd ~/Desktop/Projects/feynman && docker compose up -d neo4j
```

### Ollama: connection refused

Open the Ollama app from `/Applications/`. Verify:
```bash
curl -s http://localhost:11434/api/tags | python -m json.tool
```

### "ANTHROPIC_API_KEY not set"

```bash
echo $ANTHROPIC_API_KEY   # should not be empty
```
If empty, set it in your shell rc (`~/.zshrc`) and reload (`source ~/.zshrc`).

### Kokoro / ffmpeg "command not found"

ffmpeg only needed if `tts.output_format: "mp3"` in config. Either install ffmpeg (`brew install ffmpeg`) or change config to `output_format: "wav"`.

### macOS Sequoia: editable installs invisible

If you use `pip install -e .` instead of Poetry, macOS Sequoia sets `UF_HIDDEN` on files inside `.venv/` and Python silently skips `.pth` files marked hidden. **Solution: use Poetry** (non-editable, drops a real package into site-packages — works fine). This guide already assumes Poetry.

---

## 11. Quick verification checklist

### Fastest: use committed fixtures (~3 minutes)

```bash
cd ~/Desktop/Projects/feynman
docker compose up -d neo4j
cd data_pre_compute_v2
poetry install --extras "preview"
poetry run lecture-pipeline-v2 load-extraction ./out/extraction.json
poetry run python tools/preview_server.py &
cd ../frontend && pnpm install && pnpm dev
# Open http://localhost:5173/#/lecture-preview → click chapter → ▶ Play
```

### Full: ingest a chapter from scratch (~25 minutes)

This validates the entire pipeline including LLM and TTS:

```bash
# 1. Services
docker compose up -d neo4j         # from project root
ollama list | grep qwen3:8b         # confirm model

# 2. Schema
cd data_pre_compute_v2
poetry run lecture-pipeline-v2 init-schema

# 3. Ingest chapter 5 fast (no TTS, no questions)
poetry run lecture-pipeline-v2 ingest-book \
    "/path/to/H C Verma- Concepts of Physics 1.pdf" \
    --subject physics --chapters 5 \
    --skip-tts --skip-questions --output ./out --verbose

# 4. Confirm in Neo4j
poetry run lecture-pipeline-v2 stats

# 5. Add TTS
poetry run lecture-pipeline-v2 ingest-book \
    "/path/to/H C Verma- Concepts of Physics 1.pdf" \
    --subject physics --chapters 5 \
    --force --skip-questions --output ./out --verbose

# 6. Listen
poetry run python tools/stitch_chapter_audio.py \
    --chapter-id "chapter:physics:newtons_laws_of_motion" \
    --output /tmp/chapter5_full.mp3
afplay /tmp/chapter5_full.mp3

# 7. Visual playback (in browser)
poetry run python tools/preview_server.py &   # terminal A
cd ../frontend && pnpm dev                    # terminal B
# Open http://localhost:5173/#/lecture-preview
```

---

## 12. What's not yet built (so you know)

These are intentional gaps after Path B (SplitBoard slide-only integration). Slated for future passes:

- **Notebook panel** is currently empty. Path C extends the lecture-script writer to emit `<<WRITE_EQUATION>>` / `<<WRITE_STEP>>` markers so equations and steps appear in the right panel as the voice mentions them — same way a teacher writes a derivation on the board.
- **Doubt / interrupt handling**: no mic input, no STT, no LLM in the playback path. The architecture is ready for it but unimplemented.
- **Whisper-based TTS quality QA**: design lives in `validation/`, no provider hooked up yet.
- **Manim renderer**: Diagram nodes accept `renderer: "manim"` but no MP4 generation is wired. SVG covers all current diagrams.
- **Parallel topic extraction**: today sequential (≈100 s for a 7-section chapter). Patch to use `asyncio.Semaphore` would 3× this phase.
- **Lecture-script text persistence**: today the script writer's output goes straight to TTS and is discarded. Persisting it as `Chapter.narration_text` would make debugging and editing much easier.

---

## 13. Repo layout reference

```
feynman/
├── docker-compose.yml             # Neo4j + Postgres + LiveKit services
├── data_pre_compute/              # v1 (untouched, kept for reference)
├── data_pre_compute_v2/           # this project
│   ├── pyproject.toml             # Poetry-managed
│   ├── poetry.toml                # in-project .venv
│   ├── config.yaml
│   ├── src/lecture_pipeline_v2/   # the pipeline
│   ├── tools/
│   │   ├── preview_server.py      # FastAPI player
│   │   ├── preview_static/        # plain HTML player
│   │   └── stitch_chapter_audio.py
│   └── tests/
├── frontend/                      # React + Vite (existing)
│   └── src/screens/
│       └── LecturePreviewScreen.tsx   # SplitBoard wiring for v2 manifests
└── docs/design/                   # design docs (board-intelligence etc.)
```

---

## 14. Where to ask questions / leave feedback

- Open an issue on the GitHub repo
- Drop notes in the `#feynman-v2` Slack channel (if one exists)
- Or ping Gaurav directly

Good luck — and please report any setup snag so we can fix this guide.
