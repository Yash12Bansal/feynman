# Test Script Documentation

`test.py` is the main script for testing the lecture pipeline. It accepts a PDF, chapter name, mode, and various options.

## Usage

```bash
python test.py <pdf_path> <chapter_name> <mode> [options]
```

## Parameters

### Required

| Parameter | Description |
|-----------|-------------|
| `pdf_path` | Path to the PDF file |
| `chapter_name` | Name of the chapter to process. Matched via case-insensitive substring against the TOC. e.g. `"Thermodynamics"` will match `"Chapter 5: Thermodynamics"` |
| `mode` | `graph` — extract concept graph. `direct_lecture` — generate lecture script directly from text |

### Optional

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--start-page` | None | Start page of the chapter (1-indexed). Use when the PDF has no TOC or TOC detection is wrong |
| `--end-page` | None | End page of the chapter (1-indexed). Must be used together with `--start-page` |
| `--topic` | None | A specific topic within the chapter for a deep-dive lecture. The full chapter text is used as context, but the LLM focuses on this specific topic |
| `--quality` | `advanced` | Lecture depth level. `beginner` — simple language, analogies, small steps. `advanced` — full derivations, edge cases, exam tips, deep reasoning |
| `--generate-lec-from-graph` | `False` | When mode is `graph`, also generate a lecture script from the concept graph. Without this flag, graph mode only outputs the graph JSON |
| `--output-dir` | `./output` | Directory where output files are saved |

## How Chapter Matching Works

1. If `--start-page` and `--end-page` are provided, they are used directly (TOC is skipped)
2. Otherwise, the pipeline tries to detect chapters from the PDF's TOC metadata
3. If no TOC metadata exists, it falls back to heuristic detection (patterns like "Chapter 1", "Unit 2")
4. The `chapter_name` is matched as a case-insensitive substring against detected chapter titles
5. If no match is found, all available chapters are printed so you can pick the right one

## Quality Levels

### `--quality advanced` (default)
- Full mathematical derivations with step-by-step reasoning
- Edge cases and common misconceptions highlighted
- "Exam tip" and "Key insight" callouts
- Cross-topic connections and "What if..." scenarios
- Deep explanations of WHY things work, not just WHAT

### `--quality beginner`
- Everyday language, all jargon defined before use
- Simple analogies from daily life (cooking, sports, etc.)
- Concepts broken into smallest possible steps
- Reassuring tone when topics get complex
- "Think of it this way..." moments

## Test Commands

### 1. Graph Mode — Extract concept graph only

```bash
python test.py "/path/to/book.pdf" "Chapter Name" graph \
  --start-page 10 --end-page 25 \
  --output-dir ./output
```

**Output**: `Chapter Name_graph.json`, `Chapter Name_graph_outline.md`, `Chapter Name_images/`

### 2. Graph Mode — With lecture generation from graph

```bash
python test.py "/path/to/book.pdf" "Chapter Name" graph \
  --start-page 10 --end-page 25 \
  --generate-lec-from-graph \
  --output-dir ./output
```

**Output**: `Chapter Name_graph.json`, `Chapter Name_graph_outline.md`, `Chapter Name_lecture.md`, `Chapter Name_images/`

### 3. Direct Lecture Mode — Full chapter lecture

```bash
python test.py "/path/to/book.pdf" "Chapter Name" direct_lecture \
  --start-page 10 --end-page 25 \
  --output-dir ./output
```

**Output**: `Chapter Name_lecture.md`, `Chapter Name_images/`

### 4. Direct Lecture Mode — Beginner quality

```bash
python test.py "/path/to/book.pdf" "Chapter Name" direct_lecture \
  --start-page 10 --end-page 25 \
  --quality beginner \
  --output-dir ./output
```

**Output**: `Chapter Name_lecture.md`, `Chapter Name_images/`

### 5. Topic Deep-Dive — Focus on a specific topic

```bash
python test.py "/path/to/book.pdf" "Chapter Name" direct_lecture \
  --start-page 10 --end-page 25 \
  --topic "Energy Conservation" \
  --output-dir ./output
```

**Output**: `Energy Conservation_deep_dive.md`, `Chapter Name_images/`

### 6. Topic Deep-Dive — Beginner quality

```bash
python test.py "/path/to/book.pdf" "Chapter Name" direct_lecture \
  --start-page 10 --end-page 25 \
  --topic "Energy Conservation" \
  --quality beginner \
  --output-dir ./output
```

**Output**: `Energy Conservation_deep_dive.md`, `Chapter Name_images/`

### 7. Book with TOC — Auto-detect chapter (no page range needed)

```bash
python test.py "/path/to/book.pdf" "Managerial Accounting" graph \
  --output-dir ./output
```

The chapter is matched from the PDF's table of contents. No `--start-page`/`--end-page` needed.

### 8. List all chapters (use a non-matching name)

```bash
python test.py "/path/to/book.pdf" "zzz_no_match" graph
```

This will fail to match and print all detected chapters with their page ranges, so you can find the right name and pages.

## Visualization

After generating a graph, visualize it:

```bash
python visualize.py output/Chapter_Name_graph.json
open output/Chapter_Name_viz.html
```

Accepts `.json` (graph file) or `.md` (outline file, auto-finds matching JSON).

```bash
# Custom output path
python visualize.py output/Chapter_Name_graph.json --output my_viz.html
```

## Output Files Reference

| File | Description |
|------|-------------|
| `*_graph.json` | Concept graph with nodes (topics, summaries) and edges (relationships). Serializable, editable |
| `*_graph_outline.md` | Markdown outline of the graph — quick readable view of the hierarchy and relationships |
| `*_lecture.md` | Full lecture script in markdown. Ready for a teacher to deliver |
| `*_deep_dive.md` | In-depth lecture on a specific topic within a chapter |
| `*_viz.html` | Interactive D3.js graph visualization. Open in browser |
| `*_images/` | Directory with page renders (PNG) and any embedded raster images |
