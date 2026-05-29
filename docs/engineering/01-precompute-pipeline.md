# 01 — Precompute Pipeline (`data_pre_compute_v2/`)

**Branch:** `feat/unify_boardstate` · **Last verified:** 2026-05-28

## TL;DR

The precompute pipeline is a **fully offline** Poetry-managed Python program. You feed it a textbook PDF and a subject; it produces, for every chapter you ingest:

- A **Neo4j graph** of `Chapter`, `Topic`, `Diagram`, `Question` nodes with `CONTAINS / NEXT / PREREQ / HAS_DIAGRAM / HAS_QUESTION` edges.
- **Pre-rendered audio** (Kokoro TTS) chunked into manifest events keyed to visual markers.
- **Pre-rendered diagrams** (design-agent-style SVG + PNG fallback).
- A **manifest** (ordered event sequence) per topic *and* per chapter that the frontend `LectureViewer` later plays back deterministically.

At runtime the agent loads this content from Neo4j and plays back the manifest. **No live TTS, no live LLM in the main flow.** The teaching agent only re-engages live when a student taps "Ask Feynman" to ask a doubt.

The 12-phase pipeline shares the planning kernel (`feynman_teaching_kernel`) with the live agent — same `ConceptTeachingPlan` schema, same `plan_concept()` function, same Feynman-arc validator — so live and recorded teaching cannot drift.

---

## Process topology

```
┌──────────────────────────────────────────────────────────────────────────┐
│  CLI: poetry run lecture-pipeline-v2 ingest-book <pdf> -s <subject> ...  │
│  (entry: lecture_pipeline_v2/cli.py:app → ingest_book command lines 44)  │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  CurriculumPipelineV2.run()  —  pipeline.py:140                          │
│                                                                          │
│   Phase 1  PDF + TOC          parser.py + toc.py                        │
│   Phase 2  Anchors            anchor_extractor.py (deterministic regex) │
│   Phase 3  BookSkeleton       skeleton_extractor.py    [1 LLM call]     │
│   Phase 4  Topics             topic_extractor.py       [N LLM calls]    │
│   Phase 5  Enrichment         orchestrator.py          [N LLM + judge]  │
│              ├─ diagrams.py    (one SVG spec per topic, design prompt)  │
│              └─ questions.py   (MCQ + solved example, multi-model judge)│
│   Phase 6  PREREQ links       prereqs.py               [1 LLM call]     │
│   Phase 7a Validation gate    validation/gate.py                        │
│   Phase 7b Chapter arc        chapter_planner.py       [1 LLM/chapter]  │
│   Phase 7H Lesson pipeline    lesson_quality_gate.py   [doc-19 stack]   │
│              (replaces 7c-g when use_lesson_pipeline=True, the default) │
│   Phase 7c Per-beat diagrams  diagram_spec_generator.py + DiagramQA     │
│   Phase 7d Beat narration     beat_narration/writer.py [N LLM calls]    │
│   Phase 7e Length enforce     length_enforcer/enforcer.py               │
│   Phase 7f Script assemble    script_assembler.py                       │
│   Phase 8+ TTS + manifests    audio_pipeline.py + chunker.py + kokoro   │
│   Phase 10 Diagram fallback   diagram_renderer (SVG → PNG)              │
│   Phase 11 Embeddings         embedding_generator.py                    │
│   Phase 12 Neo4j ingest       cypher_generator.py → neo4j_writer.py     │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Artifacts persisted:                                                    │
│   • Neo4j graph (chapter, topic, diagram, question nodes + edges)        │
│   • artifacts/audio/<chapter_id>/*.mp3  (per-fragment, deduped by hash)  │
│   • artifacts/diagrams/<diagram_id>.svg + .png                           │
│   • out/extraction.json  (full CurriculumExtractionResult, debug + reuse)│
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Preview server (data_pre_compute_v2/tools/preview_server.py, port 8080) │
│   • GET /lecture-api/chapters           → list available chapters       │
│   • GET /lecture-api/chapter/{id}       → manifest + URLs (rewritten)   │
│   • GET /lecture-artifacts/...          → static audio + image files     │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                       Frontend LectureViewer plays it
```

---

## 1. CLI surface — `src/lecture_pipeline_v2/cli.py`

The `lecture-pipeline-v2` entry point is registered in `pyproject.toml` and bound to the Typer `app` in `cli.py`.

| Command | Lines | Purpose |
|---|---|---|
| `ingest-book <pdf>` | 44–154 | The main path. Runs all 12 phases for the chapters you select. |
| `list-chapters <pdf>` | 156–195 | Sanity check chapter detection on a PDF (uses TOC extractor only). |
| `init-schema` | 303–337 | Create Neo4j constraints + indexes (idempotent). |
| `stats` | 197–260 | Count nodes/relationships in the graph. |
| `query <cypher>` | 263–300 | Ad-hoc Cypher with limit. |
| `load-extraction <json>` | 340–414 | Zero-LLM re-hydration: read a previously saved `extraction.json` and ingest into Neo4j. |
| `regen-audio <json>` | 417–547 | Re-run TTS only for a saved extraction, optionally swap voices/chapters. |

Key flags on `ingest-book`:

| Flag | Effect |
|---|---|
| `--chapter "Newton's Laws"` | Substring match (case-insensitive) on chapter title. |
| `--chapters 12,13,14` | 1-based chapter indices. |
| `--single-chapter` | Treat the PDF as a single chapter (skip TOC). |
| `--force` | Disable idempotency snapshot — recompute everything. |
| `--skip-{neo4j,embeddings,tts,visuals,questions,prereqs,beat-narration,diagram-qa}` | Skip expensive phases while iterating prompts. |
| `--output ./out` | Dump `extraction.json` to disk. |

The CLI loads `.env` from the project root (`cli.py:19`) so `ANTHROPIC_API_KEY` etc. are available to all sub-clients.

---

## 2. Pipeline orchestrator — `pipeline.py`

The `CurriculumPipelineV2` class (`pipeline.py:112`) orchestrates everything. Construction is cheap; everything heavy lives in lazy-initialized members (`llm`, `tts`, `artifact_store`) created on first use.

`CurriculumPipelineV2.run()` (`pipeline.py:140`) is the single entry-point. It returns a `CurriculumExtractionResult` (`models.py:810`) carrying the full graph in memory, which is then optionally dumped to `extraction.json` and/or ingested into Neo4j.

### Idempotency snapshot

Before any LLM work, `pipeline.py:200-206` calls `_take_snapshot_safely()` which reads existing Neo4j state into an `IdempotencySnapshot` carrying:

- `existing_chapter_ids`, `existing_topic_ids`, `existing_diagram_ids`, `existing_question_ids`
- Which chapters/topics already have audio manifests
- Which nodes already have embeddings

Each downstream phase consults this snapshot before doing work. For example, `TopicExtractor.extract_chapter_topics(...)` (`pipeline.py:243`) is passed `existing_topic_ids=snapshot.existing_topic_ids` and silently skips sections already in the graph. If Neo4j is unreachable, `IdempotencySnapshot.empty()` is returned (`pipeline.py:737`) and everything runs from scratch.

`--force` bypasses the snapshot entirely.

### Phase-by-phase

| # | Phase | Implementation | Reads | Writes |
|---|---|---|---|---|
| 1 | PDF + TOC | `PDFParser.parse()` (`pdf/parser.py:102`) + `normalize_chapter_titles()` (`pdf/toc.py:135`) | PDF file | `PDFContent` + ordered `Chapter` objects |
| 2 | Anchors | `DeterministicAnchorExtractor.extract_for_chapter()` (`curriculum/anchors/anchor_extractor.py:86`) | Chapter text | `ExtractionAnchors` (sections, figures, equations, examples, defined terms) — in-memory only |
| 3 | BookSkeleton | `SkeletonExtractor.extract()` (`curriculum/skeleton_extractor.py:35`) | TOC + chapter previews | One `BookSkeleton` (subject overview + per-chapter summary + cross-chapter prereqs/leads-to) — **1 LLM call total** |
| 4 | Topics | `TopicExtractor.extract_chapter_topics()` (per chapter loop, `pipeline.py:230`) | Chapter text + anchors + skeleton | List of `Topic` nodes — **1 LLM call per anchored leaf section** |
| 5 | Enrichment | `EnrichmentOrchestrator.enrich()` (`curriculum/enrichment/orchestrator.py`) | Topics | New `Diagram` + `Question` nodes — parallel LLM calls per topic, judge-gated |
| 6 | PREREQ | `PrereqLinker.link()` (`curriculum/enrichment/prereqs.py`) | All topics | `topic.prereq_topic_ids` filled — **1 LLM call** |
| 7a | Validation | `ValidationGate.run()` (`curriculum/validation/gate.py`) | Extraction + anchors | `report.validation` (structural completeness, semantic spot-checks) |
| 7b | Chapter arc | `ChapterLecturePlanner.plan_for_all()` (`curriculum/lecture_plan/chapter_planner.py`) | Chapters + their topics | `chapter.lecture_plan` (`ChapterLecturePlan`: pedagogical arc + topic ordering) — **1 LLM call per chapter** |
| 7H | Lesson pipeline (doc-19, default) | `LessonQualityGate.gate_one_topic()` per topic (`pipeline.py:335-378`) | Chapter arcs + topics | `chapter.lesson_plans` + `chapter.lesson_narrations` + new beat-linked diagrams |
| 7c | Per-beat diagrams (legacy) | `DiagramSpecGenerator.generate_for_chapter()` (`pipeline.py:421-449`) | Concept plans | New diagrams with `linked_beat_id` set |
| 7d | Beat narration (legacy) | `BeatNarrationWriter.write_for_chapter()` (`pipeline.py:459-541`) | Concept plans + beat diagrams | `chapter.beat_narrations` |
| 7e | Length enforce (legacy) | `LengthEnforcer.trim()` | Narration | Trimmed narration |
| 7f | Script assemble (legacy) | `ScriptAssembler.assemble_chapter()` | Beat narrations | `chapter.assembled_chapter_script` dict |
| 8 | Chapter scripts → TTS + manifests | `AudioPipeline.build_for_book()` (`tts/audio_pipeline.py`) | Chapter scripts + diagrams | Audio files + `chapter.chapter_manifest` + `topic.standalone_manifest` |
| 10 | Diagram fallback render | `DiagramFallbackRenderer.render_all()` | SVG specs | PNG files (`artifacts/diagrams/diagram_*.png`) |
| 11 | Embeddings | `EmbeddingGenerator.embed_extraction()` | Topic + chapter content | `embedding: list[float]` on each node (sentence-transformers default, OpenAI optional) |
| 12 | Neo4j ingest | `CypherGenerator.generate()` → `Neo4jWriter.ingest()` → `verify_ingestion()` | Full extraction | MERGE statements run in batches; verification pass checks node/rel counts |

> **Two stacks, one config flag.** `use_lesson_pipeline: bool = True` in `EnrichmentConfig` chooses between the **doc-19 lesson stack** (the default — `LessonPlanner` → `LessonDiagramGenerator` → `LessonNarrator` → `LessonProsody` → `LessonQualityGate`) and the **legacy 7c-7g stack**. The doc-19 stack is what runs today and what the frontend `LectureViewer` plays back.

---

## 3. PDF and anchors — `pdf/` and `curriculum/anchors/`

### PDF parsing — `pdf/parser.py`

`PDFParser.parse(pdf_path, page_range=None)` (`pdf/parser.py:102`) uses PyMuPDF (`fitz`) to:

1. Open the document and call `doc.get_toc()` for raw `(level, title, page_no)` bookmarks.
2. For each page, extract text via `page.get_text("text")` and capture image refs (`page._image_refs`).
3. Return a `PDFContent` carrying pages, raw TOC, total page count, metadata, and the source path.

Helpers on `PDFContent`:

- `get_text_for_range(start, end)` — join text from a page slice (used to build chapter text).
- `extract_images_for_page(idx)` — pull embedded images by xref.
- `extract_images_to_dir(out_dir, dpi)` — dump page images at a target DPI (used by the layout-measurement loop).

### TOC normalization — `pdf/toc.py`

Most textbook PDFs have clean bookmarks. Some (the HC Verma scans we care about) have file-name bookmarks like `COP1_05_1_Pg_064-071`, which is useless. `normalize_chapter_titles()` (`pdf/toc.py:135`) handles this:

1. Detect filename-style bookmarks via `_FILENAME_LIKE_BOOKMARK` regex (`toc.py:61`).
2. Extract the chapter number from the middle of the filename via `_CHAPTER_NUMBER_FROM_BOOKMARK` (`toc.py:65`).
3. Group consecutive bookmarks that share a chapter number into one `Chapter`.
4. Search the first ~3KB of the chapter's text for a real heading (`_CHAPTER_HEADING_IN_TEXT`, `toc.py:75`) or a bare number heading.
5. Title-case the extracted heading via `_normalise_caps_title()`.

### Deterministic anchors — `curriculum/anchors/anchor_extractor.py`

Anchors are *not* persisted to Neo4j. They are computed fresh per chapter and used in two ways:

- As a **completeness floor** for topic extraction (every leaf section must produce at least one topic).
- As a **checklist** for the validation gate (figure/equation references should be reachable).

`DeterministicAnchorExtractor.extract_for_chapter(pdf_content, chapter)` (`anchor_extractor.py:86`) runs five regex sweeps on chapter text:

| Field | Pattern source |
|---|---|
| `section_numbers` | `_SECTION_3_LEVEL`, `_SECTION_2_LEVEL`, `_SECTION_LETTER_SUB` (e.g. `12.1.1 Title`, `12.1 Title`, `12.1a Title`) |
| `equations` | `_EQUATION_REF` (`Eq. (12.5)`) |
| `figure_refs` | `_FIGURE_REF` (`Fig. 12.1a`) |
| `example_refs` | `_EXAMPLE_REF` (`Example 12.3`) |
| `defined_terms` | Four `_DEFINED_TERM_PATTERNS` (italic, bold, "is defined as", "called the") |

Returns an `ExtractionAnchors` (`curriculum/anchors/models.py:1-90`):

```python
class ExtractionAnchors(BaseModel):
    section_numbers: list[SectionAnchor]    # SectionAnchor(section_number, title, depth)
    equations: list[str]
    figure_refs: list[str]
    example_refs: list[str]
    defined_terms: list[str]
    page_count: int

    @property
    def leaf_sections(self) -> list[SectionAnchor]: ...    # max-depth sections only
    @property
    def smallest_section_depth(self) -> int: ...
```

`leaf_sections` is the workhorse — it's what topic extraction iterates over.

---

## 4. Curriculum extraction — `curriculum/`

### BookSkeleton (Phase 3)

`SkeletonExtractor.extract(pdf_content, chapters, subject_hint=None)` (`curriculum/skeleton_extractor.py:35`) makes **one LLM call for the entire book**:

```python
system_prompt = get_skeleton_system_prompt()
user_prompt   = build_skeleton_user_prompt(toc_text, previews, subject_hint)
raw_json      = self._call_llm(system_prompt, user_prompt)
skeleton      = self._parse_response(raw_json, pdf_content.total_pages)
```

Output `BookSkeleton` (`models.py:518`) has:
- `textbook_title`, `subject`, `subject_overview`
- `total_chapters`, `total_pages`
- `chapters: list[ChapterSummary]` — each carries `chapter_index, title, page_start, page_end, summary, key_concepts, prerequisites_from, leads_to`

This is the single source of cross-chapter context that gets injected into every subsequent per-chapter prompt.

### Topics (Phase 4)

For each chapter and each `leaf_section` in its anchors, `TopicExtractor.extract_chapter_topics(...)` slices the chapter text to just that section and makes **one LLM call** producing:

- `Topic.our_understanding` — the teacher-voice explanation (this is what becomes the lecture script's spine).
- `Topic.book_examples: list[BookExample]` — worked problems verbatim, each tagged with `verbatim_text, page_number, kind (worked_out|inline), lesson_focus, setup_facts, has_derivation`.

Topic IDs are **deterministic**: `topic_{slug(subject)}_{slug(chapter_title)}_{slug(section_number)}` (`curriculum/id_generator.py`), so re-runs are safe.

Full `Topic` model (`models.py:666`):

```python
class Topic(BaseModel):
    # Identity
    topic_id: str                       # "topic_physics_newtons_laws_12.1"
    chapter_id: str
    section_number: str                 # from anchor
    within_chapter_order: int
    topic_name: str                     # LLM-titled
    # Content
    orig_book_content: str              # verbatim PDF slice
    our_understanding: str              # LLM-rewritten in teacher voice
    book_examples: list[BookExample]
    # Graph navigation
    next_topic_id: str | None
    prereq_topic_ids: list[str]
    has_diagram_ids: list[str]
    has_question_ids: list[str]
    # Playback (filled by phases 8+)
    standalone_manifest: Manifest
    standalone_narration_text: str
    # Retrieval
    embedding: list[float]
    needs_review: bool
    language: str = "en"
    version: int = 1
```

### Enrichment (Phase 5)

`EnrichmentOrchestrator.enrich(topics, existing_diagram_ids, existing_question_ids, ...)` runs in parallel:

- `DiagramGenerator.generate_for_topics()` — one SVG-spec LLM call per topic that doesn't already have a diagram. **The system prompt used is a verbatim copy of the design-agent's prompt** at `curriculum/enrichment/diagrams.py` (see §11 below).
- `QuestionGenerator.generate_for_topics()` — one MCQ + one solved example per topic. A multi-model judge scores them; only those with `solution_confidence > threshold` are kept.

### PREREQ linking (Phase 6)

`PrereqLinker.link()` makes **one LLM call** over the entire `all_topics` list. For each topic, the LLM picks which earlier topics it depends on. Writes back to `topic.prereq_topic_ids`. PREREQ edges in Neo4j are reference-only — they don't drive lecture flow.

### Validation gate (Phase 7a)

`ValidationGate.run(extraction, anchors_by_chapter)` (`curriculum/validation/gate.py`) is **non-fatal** — it produces a `GateReport` with:

- Structural checks: every topic ID referenced in `Chapter.topic_ids` exists, every leaf section has at least one topic.
- Semantic spot-checks: multi-model judge on a random sample.
- Render tests: actually exercise the SVG renderer to catch spec errors early.

Findings are attached to `extraction.warnings`. Pipeline continues regardless.

### Chapter arc (Phase 7b)

`ChapterLecturePlanner.plan_for_all(chapter_nodes, topics_by_chapter)` makes **one LLM call per chapter** that reasons about the chapter's pedagogical arc:

- What's the hook?
- What's the spine?
- In what order should topics be taught?

Output `ChapterLecturePlan` is attached to each `Chapter.lecture_plan`.

### Lesson pipeline (Phase 7H, doc-19, the active path)

When `use_lesson_pipeline=True` (default), `LessonQualityGate.gate_one_topic()` runs per topic and orchestrates the full doc-19 chain:

1. **`LessonPlanner`** — takes the chapter arc + the topic and produces a `LessonPlan` (a 5-stage scope → pedagogy → visual plan → choreography → math structure described in doc 19).
2. **`LessonDiagramGenerator`** — for each beat with a `DiagramRequirement`, generate a `DiagramSpec` (per-beat, `linked_beat_id` set). Element IDs in the spec are validated against the requirement.
3. **`LessonNarrator`** — walks `LessonPlan.choreography` and produces a `TopicNarration` with chunker-grammar text (`<<FOCUS:id:element>>`, `<<SHOW_DIAGRAM:id>>`, etc.).
4. **`LessonProsody`** — applies prosody rules (elongate questions, bold crucial facts).
5. **`LessonQualityGate`** — runs LLM-as-judge on the produced plan + diagrams; retries up to N times if scores fall below threshold.

Output is attached to each `Chapter.lesson_plans` and `Chapter.lesson_narrations`. The script assembler (Phase 7f-equivalent) stitches the lesson narrations into the chapter script.

> The kernel function `plan_concept()` (from `feynman_teaching_kernel`) is called by **both** the legacy ConceptPlanner *and* (with different framing) inside the lesson stack. This is the single point where the live agent and the precompute pipeline share planning logic. See `docs/engineering/05-feynman-teaching-kernel.md`.

### Beat narration (legacy, Phase 7d)

Used only when `use_lesson_pipeline=False`. `BeatNarrationWriter.write_for_chapter()` makes one LLM call per concept beat and emits a `BeatNarration` carrying the actual TTS text with embedded markers. Style rules (`PRONUNCIATION_RULES`, `BANNED_OPENERS`) come from the kernel's `style_guide`.

### Script assembly

Whichever path produced narrations, `ScriptAssembler.assemble_chapter()` stitches them into `chapter.assembled_chapter_script` — a dict of:

```python
{
  "chapter_id": "chapter_physics_newtons_laws",
  "segments": [
    {"topic_id": "topic_...12.1", "narration_chapter": "...", "narration_standalone": "..."},
    ...
  ]
}
```

`narration_chapter` is the version that flows inside a full chapter playback (no chapter-context preamble). `narration_standalone` is the version used when the topic is taught in isolation — it starts with a brief "Here's where this fits" preamble pulled from the chapter arc.

---

## 5. LLM layer — `src/lecture_pipeline_v2/llm/`

The LLM abstraction is provider-agnostic.

```python
# llm/base.py
@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict | None = None    # {input_tokens, output_tokens}

class LLMProvider(ABC):
    def generate(system: str, user: str) -> LLMResponse: ...
    def generate_json(system: str, user: str) -> LLMResponse: ...   # appends "respond JSON only", strips fences
```

Concrete providers in `llm/`:

| File | Provider | Notes |
|---|---|---|
| `anthropic_provider.py` | Claude (default) | Uses the `anthropic` SDK, captures usage in response. |
| `openai_provider.py` | GPT | Alternative for cost experiments. |
| `ollama_provider.py` | Local | For judge models (qwen3:8b). |

`llm/factory.py:create_llm_provider(config)` dispatches by `config.provider`.

The judge model is configured separately. Multi-model judges (e.g., in questions enrichment) instantiate two providers and require agreement.

---

## 6. TTS and manifests — `src/lecture_pipeline_v2/tts/`

### Kokoro TTS

`KokoroTTSProvider.synthesize(text, output_path)` (`tts/kokoro_provider.py`) calls the local Kokoro pipeline, concatenates the streaming audio chunks, and writes the result:

```python
pipeline = KPipeline(lang_code=self.config.voice[0].lower())   # "a" for "af_heart"
chunks: list = []
for _gs, _ps, audio in pipeline(text, voice=self.config.voice):
    chunks.append(audio)
combined = np.concatenate(chunks)
soundfile.write(wav_path, combined, sample_rate=24000)
# Convert to mp3 if needed via ffmpeg, return TTSResult(audio_path, duration_ms, ...)
```

Silence frames go through a separate path (`synthesize_silence(duration_ms, output_path)`).

### Chunker — `tts/chunker.py`

Narration text contains inline markers that mean "fire a visual event when this point in the audio plays." The chunker splits a narration string into `Fragment` objects:

```
"Here is the equation <<WRITE_EQUATION:eq1:F=ma>> and we see <<FOCUS:diag1:arrow>> the force."
                          │                                  │
                          ▼                                  ▼
[TextFragment "Here is the equation"]
[WriteEquationFragment id=eq1 latex=F=ma]
[TextFragment "and we see"]
[FocusFragment diag1.arrow]
[TextFragment "the force."]
```

Recognized markers include `<<SHOW_DIAGRAM:id>>`, `<<FOCUS:diag:element>>`, `<<UNFOCUS:diag>>`, `<<PAUSE:ms>>`, `<<WRITE_SECTION:id:title>>`, `<<WRITE_EQUATION:id:latex>>`, `<<WRITE_STEP:text>>`, `<<TRACE:diag:elem>>`, `<<MARK_POINT:diag:x:y>>`, `<<POINT_AT:diag:elem:side>>`, `<<WRITE_MARGIN:text>>`, `<<NEW_PAGE>>`, plus legacy `<<PIN>>`/`<<CALLOUT>>`/`<<BRACKET>>`/`<<HIGHLIGHT>>`/`<<PULSE>>`.

### Audio pipeline — `tts/audio_pipeline.py`

`AudioPipeline.build_for_book(chapter_nodes, topics, chapter_scripts, diagrams)` is the orchestrator:

```python
for chapter in chapter_nodes:
    script = chapter_scripts.get(chapter.chapter_id)
    for segment in script.segments:
        topic = lookup(segment["topic_id"])

        # Topic standalone manifest
        fragments = split_script(segment["narration_standalone"])
        fragments = await ManifestComposer(diagrams_by_id).compose(fragments)  # layout pass

        events = []
        for fragment in fragments:
            if isinstance(fragment, TextFragment):
                tts_result = await tts.synthesize(fragment.text, output_path)
                events.append(AudioEvent(url=tts_result.audio_path, duration_ms=tts_result.duration_ms))
            elif isinstance(fragment, ShowDiagramFragment):
                events.append(ShowDiagramEvent(diagram_id=fragment.diagram_id, placement=fragment.placement))
            # ... one branch per fragment type ...

        topic.standalone_manifest = Manifest(events=events)
        topic.standalone_narration_text = segment["narration_standalone"]

    # Chapter manifest: same idea but prepends TopicStartEvent before each segment's events
```

`ManifestComposer` is where Phase-3 layout planning happens: Playwright measures notebook block sizes, the layout planner decides page breaks, and `Placement` objects (x, y, w, h in viewport pixels) get attached to `ShowDiagramEvent`/`WriteEquationEvent`/etc.

### What is a manifest event?

The full union is in `curriculum/models.py:365-395`. Twenty-seven event types organized as a Pydantic `Annotated[Union[...], Field(discriminator="type")]`. The headline ones:

| Type | Fields | Renders as |
|---|---|---|
| `audio` | `url, duration_ms` | Plays MP3 file. |
| `pause` | `duration_ms` | Sleeps. |
| `topic_start` | `topic_id` | Marks new topic (frontend may show progress). |
| `show_diagram` | `diagram_id, placement?, presentation_mode?` | Mounts the diagram on the slide. |
| `focus` | `diagram_id, target_element_id\|target_role, text` | Spotlights a sub-element. |
| `unfocus` | `diagram_id` | Removes spotlight. |
| `trace` | `diagram_id, element_id, duration_ms` | Animates a stroke along the element's path. |
| `mark_point` | `diagram_id, x, y, kind, label` | Drops a marker in viewBox space. |
| `point_at` | `diagram_id, element_id, from_side` | Finger/arrow pointing at the element. |
| `write_margin` | `text` | Margin note in the notebook. |
| `write_section` | `id, title, placement?` | Header in the notebook. |
| `write_equation` | `id, latex, align_group?, boxed, placement?` | Equation line. |
| `write_step` | `id, text, indent (0-3), placement?` | Numbered/unnumbered working step. |
| `write_text`, `write_key_point`, `write_answer` | similar | Notebook prose lines. |
| `strikethrough` | `target_id` | Cross out a previous notebook entry. |
| `new_page` | `carry_forward_ids` | Turn page, optionally copy specified entries. |
| `page_break` | (none) | Forced layout break. |
| `clear_annotations` | `diagram_id` | Wipe focus/trace/markers. |

Legacy back-compat events (`pin`, `callout`, `bracket`, `highlight`, `pulse`) still exist but new content uses the focus/trace/point_at/mark_point/write_margin set.

The `Manifest` model itself (`models.py:488`) is just `events: list[ManifestEvent]` with a `total_audio_ms` property summing `AudioEvent + PauseEvent` durations.

---

## 7. Config — `src/lecture_pipeline_v2/config.py` and `config.yaml`

`PipelineConfig` is the root Pydantic model (`config.py`), loaded from `config.yaml` plus env vars:

```python
class PipelineConfig(BaseModel):
    llm:        LLMConfig            # provider, model, temperature, max_tokens
    pdf:        PDFConfig            # ocr_threshold, image_dpi, ocr_language
    tts:        TTSConfig            # kokoro voice, pause_short_ms, pause_long_ms
    layout:     LayoutConfig         # viewport (1600x900), slide region, notebook region
    enrichment: EnrichmentConfig     # per_beat_diagrams, diagram_qa, beat_narration, use_lesson_pipeline=True
    validation: ValidationConfig
    neo4j:      Neo4jConfig          # bolt://localhost:7687, neo4j/password
    embedding:  EmbeddingConfig      # sentence_transformers or openai
    artifacts:  ArtifactsConfig      # base_dir="./artifacts", url_prefix="file://./artifacts"
```

Default `layout` block (from `config.yaml`):

```yaml
layout:
  viewport: {width: 1600, height: 900}
  slide:    {x: 30,  y: 50, width: 900, height: 800, padding: 20}
  notebook: {x: 970, y: 50, width: 600, height: 800, padding: 30}
```

These are the exact pixels the precompute pipeline writes into manifest `Placement` fields, and the same numbers the frontend's `LectureViewer` uses for its preview-mode viewport. This is the contract that keeps "what we measured" === "what the user sees."

---

## 8. Tools — `data_pre_compute_v2/tools/`

| Tool | Purpose |
|---|---|
| `preview_server.py` | FastAPI server on `:8080`. Endpoints `/lecture-api/chapters` and `/lecture-api/chapter/{id}` query Neo4j and return manifests with URLs rewritten from `file://./artifacts/...` to `/lecture-artifacts/...` (served as static). The frontend `LectureHomeScreen` and `LectureViewer` consume these. Started by `make dev-preview-server`. |
| `measurement_page.html` | Headless-browser-driven DOM measurement for Phase 3 layout planning (Playwright loads it, renders notebook blocks at the configured viewport, queries `getBoundingClientRect`, writes cached heights into `artifacts/measurement_cache/`). |
| `snap_lecture.py` / `snap_lecture_sequence.py` | Take screenshots of single or sequential lecture frames for offline review. |
| `stitch_chapter_audio.py` | Concatenate per-fragment MP3s into a single chapter MP3 (for review only — runtime plays per-fragment). |
| `dump_chapter_extraction.py` | Print the extracted data for a chapter from Neo4j as `extraction.json` for inspection. |
| `diagnose_script_writer.py` | Analyze narration + marker structure to find broken markers. |
| `preview_static/` | HTML/JS player UI used by `preview_server` for in-browser playback. |

---

## 9. Artifacts on disk

```
data_pre_compute_v2/
├── artifacts/
│   ├── audio/
│   │   └── chapter_<chapter_id>/
│   │       └── <topic_id>_<role>_<index>.mp3      # role = "chapter" | "standalone"
│   ├── diagrams/
│   │   ├── diagram_<id>.svg                       # SVG render of render_data
│   │   └── diagram_<id>.png                       # Phase-10 raster fallback
│   ├── animations/                                # Reserved
│   ├── runs/                                      # Intermediate/debug
│   └── measurement_cache/
│       └── *.json                                 # Notebook block height cache (Phase 3)
└── out/
    └── extraction.json                            # Full CurriculumExtractionResult dump
```

URLs in manifests are stored as `file://./artifacts/...`; the preview server rewrites them to `/lecture-artifacts/...` on the fly when serving to the browser.

---

## 10. Pydantic models — `curriculum/models.py`

The complete graph schema is in one file. Key models (already referenced above):

| Model | Lines | Notes |
|---|---|---|
| `BookExample` | ~615 | Worked problem; `kind` is `worked_out` or `inline`. |
| `BookSkeleton` | 518–538 | One per book; subject overview + per-chapter summaries with cross-chapter prereqs. |
| `Chapter` | 743–795 | `topic_ids` ordered by lecture flow; `chapter_manifest` is the playback event stream; `lecture_plan`, `lesson_plans`, `lesson_narrations`, `assembled_chapter_script` are intermediate authoring artifacts. |
| `Topic` | 666–736 | One per anchored section; carries `standalone_manifest` so the frontend can play a single topic standalone. |
| `Diagram` | 550–579 | `renderer="svg"\|"manim"`, `render_data` is the renderer-specific spec, `linked_beat_id` ties beat-scoped diagrams to their authoring beat, `presentation_mode` is `build_up` or `overview`. |
| `Question` | 596–613 | `type="mcq"\|"solved_example"`, multi-judge `solution_confidence` 0–1. |
| `Manifest` + 27 event types | 58–500 | See §6 above. |
| `BoardElement` | 425–442 | **feat/unify_boardstate** addition: one element on the board at a snapshot moment. `kind` is `diagram\|diagram_element\|notebook_block`. |
| `BoardSnapshot` | 445–448 | A `page_index`, `topic_id`, and `elements: list[BoardElement]`. One snapshot per chapter page. |
| `ConceptVisualIndex` | (lookup helper) | Diagram element → role lookup. |
| `CurriculumExtractionResult` | 810–871 | The top-level dump. Has `.save(path)` and `.load(path)` classmethods. |

### Board snapshots — the v2 unification

The `feat/unify_boardstate` branch attaches a `board_snapshots: list[BoardSnapshot]` to each `Chapter`. One snapshot per logical page. Each snapshot is the authoritative answer to "what is on the board at this point of the lecture" — across both slide (diagrams + their elements) and notebook (blocks).

This is what the frontend `LectureViewer` ships back to the worker inside the `doubt_intent` payload (`board_snapshot: BoardSnapshot | null`) when a student asks Feynman — so the doubt resolver doesn't have to introspect the DOM. See `07-contracts-and-protocols.md` for the wire shape and `09-end-to-end-trace.md` for the doubt-resolution walkthrough.

---

## 11. Neo4j ingest — `curriculum/ingestion/`

### Schema — `curriculum/schema.py`

Constraints (run on first ingest or via `init-schema`):

```python
CONSTRAINT_QUERIES = [
    "CREATE CONSTRAINT chapter_uid  IF NOT EXISTS FOR (n:Chapter)  REQUIRE n.chapter_id  IS UNIQUE",
    "CREATE CONSTRAINT topic_uid    IF NOT EXISTS FOR (n:Topic)    REQUIRE n.topic_id    IS UNIQUE",
    "CREATE CONSTRAINT diagram_uid  IF NOT EXISTS FOR (n:Diagram)  REQUIRE n.diagram_id  IS UNIQUE",
    "CREATE CONSTRAINT question_uid IF NOT EXISTS FOR (n:Question) REQUIRE n.question_id IS UNIQUE",
]
```

Indexes:
- Range: `chapter_index`, `topic.section_number`, `topic.chapter_id`, `topic.within_chapter_order`, `diagram.renderer`, `question.type`.
- Composite: `(topic.chapter_id, topic.within_chapter_order)` — "all topics in chapter, ordered."
- Fulltext: `topic_search` over `(topic_name, our_understanding, orig_book_content)`; `question_search` over `(q_text, answer)`.
- Vector: `topic_embedding` (cosine), dimensions from `EmbeddingConfig.dimensions`.

### Cypher generation — `curriculum/ingestion/cypher_generator.py`

`CypherGenerator.generate(extraction)` yields `CypherStatement(query, params, category, uid)` objects in dependency order: chapters → topics → diagrams → questions → edges. Every statement is `MERGE`-based, so re-runs are idempotent. JSON-valued properties (e.g., `chapter_manifest`) are stored as serialized strings via `chapter.chapter_manifest.model_dump_json()`. Scalars go through parameters — never string interpolation.

### Ingestion — `curriculum/ingestion/neo4j_writer.py`

`Neo4jWriter.ingest(statements, batch_size=50, initialize=True)`:
1. If `initialize`, runs the schema constraints/indexes idempotently.
2. Executes statements in batches; one failed MERGE is logged but doesn't fail the batch.
3. Returns `IngestionReport(statements_succeeded, nodes_created, rels_created, errors)`.
4. The optional `verify_ingestion()` pass checks expected node IDs and relationships actually exist.

---

## 12. Kernel coupling — `feynman_teaching_kernel` usage

The precompute pipeline imports the kernel in eight places:

| File | Lines | What it imports / does |
|---|---|---|
| `curriculum/prompts.py` | 15 | `PRONUNCIATION_RULES` — injected into beat narration prompts so TTS reads "kilometers per hour" not "km/h". |
| `curriculum/models.py` | 19, 858 | `ConceptTeachingPlan` — type hint + forward-ref on `Chapter.concept_plans` and lesson plan models. |
| `curriculum/lecture_plan/concept_planner.py` | 18 | `ConceptTeachingPlan, plan_concept` — the legacy path; calls kernel once per topic with `allowed_visual_tools` restricting `visual.tool` to renderable types. |
| `curriculum/lecture_plan/example_allocator.py` | 24 | `ConceptTeachingPlan, TeachingBeat` — allocates `Topic.book_examples` to beats, sets `beat.example_source = "book"` and `beat.book_example_ref = i`. |
| `curriculum/length_enforcer/enforcer.py` | 23 | `ConceptTeachingPlan, TeachingBeat` — trims beats to fit duration budgets. |
| `curriculum/beat_narration/writer.py` | 27 | `ConceptTeachingPlan, TeachingBeat` — writes narration per beat, branches on `example_source` (book vs. extended). |
| `curriculum/beat_narration/prompts.py` | 13–14 | `ConceptTeachingPlan, TeachingBeat, PRONUNCIATION_RULES` — prompt template inputs. |
| `curriculum/enrichment/diagram_spec_generator.py` | 26 | `ConceptTeachingPlan, TeachingBeat` — generates per-beat design diagrams from beat metadata. |

The doc-19 lesson stack also uses `plan_concept` indirectly through its own planner abstractions but ultimately routes through the kernel for the actual LLM call.

### Diagram prompt sync

`curriculum/enrichment/diagrams.py` carries a **verbatim copy** of `design_agent/backend/prompts.py:SYSTEM_PROMPT`. The file is annotated:

> "DO NOT EDIT — synced VERBATIM from design_agent/backend/prompts.py. If the canonical design_agent prompt changes, copy the new version here."

This ensures that diagrams precomputed offline use the same authoring rules as diagrams generated by the live agent's `draw_design_diagram` tool (which in turn imports the same prompt via `backend/src/feynman/agent/design_bridge.py`). See `06-design-agent.md`.

---

## 13. Dependencies — `pyproject.toml`

Highlights of `data_pre_compute_v2/pyproject.toml`:

```toml
[tool.poetry.dependencies]
python = "^3.11"
pymupdf        = "*"               # PDF parsing
neo4j          = "*"               # graph driver
anthropic      = "*"               # Claude
openai         = "*"               # GPT (judge)
sentence-transformers = "*"        # default embeddings
typer          = "*"               # CLI
pyyaml         = "*"               # config
playwright     = "*"               # layout measurement
feynman-teaching-kernel = { path = "../feynman_teaching_kernel", develop = true }

[tool.poetry.extras]
tts    = ["kokoro>=0.7.0", "soundfile>=0.12.0"]
render = ["cairosvg"]

[tool.poetry.scripts]
lecture-pipeline-v2 = "lecture_pipeline_v2.cli:app"
```

The `feynman-teaching-kernel` is installed as an editable path dep — same source the backend imports.

---

## Reading order for a new engineer

1. `README.md` — five-minute overview.
2. `src/lecture_pipeline_v2/cli.py` — see every command's signature.
3. `src/lecture_pipeline_v2/pipeline.py:140` — the `run()` method walks the whole 12-phase flow.
4. `curriculum/models.py` — read the Pydantic models in this order: `BookSkeleton → Chapter → Topic → BookExample → Diagram → Question → ManifestEvent union → Manifest → BoardSnapshot → CurriculumExtractionResult`.
5. `tts/audio_pipeline.py` + `tts/chunker.py` — how narration becomes a manifest.
6. `tools/preview_server.py` — how the frontend reads the output.
7. Cross-link to `05-feynman-teaching-kernel.md` to understand what the planning calls actually do.
