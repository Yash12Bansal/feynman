# 08 — Curriculum Graph Pipeline

> Redesign of `data_pre_compute/` — from static concept dump to production-grade curriculum knowledge graph.

**Status**: Design  
**Date**: 2026-04-05  
**Depends on**: None (foundational infrastructure)  
**Feeds into**: Teaching agent, dashboard state graph, student knowledge graph

---

## 1. Why This Matters

The curriculum graph is the **spine of the entire product**. Two other graphs — dashboard state (ephemeral, per-session) and student knowledge (persistent, per-student) — will reference it as their shared ontology. If the spine is weak, everything built on it is weak.

Today's `data_pre_compute` pipeline has critical problems:

| Problem | Impact |
|---|---|
| No source text preserved (`content=""` on every node) | Teaching agent teaches from LLM hearsay, not the textbook |
| Granularity too coarse (13 nodes for 15-page chapter) | Agent can't branch to fine-grained concepts when students are confused |
| Zero validation of LLM output | Hallucinated formulas and wrong relationships go to production |
| Broken chunked merging (mechanical ID append, no dedup) | Duplicate concepts, disconnected clusters in long chapters |
| No cross-chapter linking | Agent can't trace prerequisites across chapters |
| Untyped concept nodes | Agent doesn't know if something is a definition, formula, or example |
| Pre-baked lecture scripts (95KB monologues) | Opposite of adaptive teaching; expensive and unused |
| No node importance scoring | Agent treats "F=ma" and "Example 3.5" equally |
| JSON file output, no graph database | Can't support runtime evolution, cross-graph queries, or concurrent access |

---

## 2. Three-Graph Architecture (Context)

The curriculum graph exists within a larger system:

```
┌─────────────────────────────────────────────────────────────┐
│                         Neo4j                               │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  CURRICULUM GRAPH (persistent, shared, evolves)      │   │
│  │  Seeded by pre-compute pipeline                      │   │
│  │  Evolved by teaching runtime (Hebbian, salience)     │   │
│  │  Shared ontology for all other graphs                │   │
│  └──────────┬──────────────────────────┬────────────────┘   │
│             │ ILLUSTRATES              │ MASTERED            │
│             │ REPRESENTS               │ STRUGGLING          │
│             ▼                          ▼                     │
│  ┌─────────────────────┐   ┌────────────────────────────┐   │
│  │ DASHBOARD STATE     │   │ STUDENT KNOWLEDGE          │   │
│  │ (ephemeral/session) │   │ (persistent/per-student)   │   │
│  │ Board elements,     │   │ Mastery states,            │   │
│  │ spatial layout,     │   │ misconceptions,            │   │
│  │ visual↔concept refs │   │ learning patterns          │   │
│  └─────────────────────┘   └────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**This design doc covers the curriculum graph and its ingestion pipeline.** Dashboard and student graphs are future work but we define the integration contract here so they can plug in without refactoring.

---

## 3. Design Decisions

### 3.1 Neo4j as the Curriculum Store

**Decision**: Write directly to Neo4j, not JSON files.

**Why**: The curriculum graph is not static. It evolves through:
- Hebbian learning (concepts frequently co-activated during teaching get linked)
- Salience updates (real teaching data reveals which concepts matter most)
- Consolidation (cross-chapter insights synthesized after processing full textbooks)
- Dashboard and student graphs referencing curriculum concepts via stable IDs

A mutable graph database supports all of this. JSON files don't.

**Latency**: Neo4j single-node operations are 5-15ms. Not a bottleneck — Claude generating content takes 5-15 seconds. Graph ops are 1000x faster.

### 3.2 Drop Lecture Generation

**Decision**: Remove `lecture/script_generator.py` and `lecture/graph_generator.py`. No more pre-baked scripts.

**Why**: The teaching agent generates speech live from the concept graph. Pre-written 95KB monologues are the opposite of adaptive, branching teaching. They cost ~$0.30/chapter in API calls and produce output the agent won't use. The concept graph — with its rich summaries, source text, and relationships — IS the curriculum.

### 3.3 Stable Semantic IDs

**Decision**: Concept IDs are deterministic and human-readable:
```
curriculum:{subject}:{chapter_slug}:{concept_slug}
curriculum:{subject}:{chapter_slug}:{concept_slug}:{sub_concept_slug}
```

Examples:
```
curriculum:physics:simple_harmonic_motion
curriculum:physics:simple_harmonic_motion:energy_in_shm
curriculum:physics:simple_harmonic_motion:energy_in_shm:potential_energy_formula
```

**Why**: Other graphs (dashboard, student) will reference these IDs. They must be:
- **Deterministic** — same input produces same ID across re-runs
- **Meaningful** — debuggable by humans
- **Stable** — don't change when you re-process the same chapter

Generated from: `slugify(subject + chapter_title + topic_name + parent_path)`.

### 3.4 Typed Concept Nodes

**Decision**: Every concept node has an explicit `concept_type` from a constrained enum:

```
ConceptType:
  TOPIC          — A broad teaching topic (e.g., "Simple Harmonic Motion")
  DEFINITION     — A precise definition (e.g., "SHM is motion where a = -ω²x")
  FORMULA        — A mathematical relationship (e.g., "x = A sin(ωt + δ)")
  DERIVATION     — A step-by-step mathematical proof
  EXAMPLE        — A worked problem or concrete instance
  APPLICATION    — Real-world use case or connection
  MISCONCEPTION  — A common mistake students make
  ANALOGY        — An intuitive comparison to aid understanding
  EXPERIMENT     — A demonstration or lab procedure
  VISUALIZATION  — A diagram, graph, or animation description
```

**Why**: The teaching agent uses type to decide teaching strategy. A `FORMULA` gets written on the board with KaTeX. A `MISCONCEPTION` gets addressed proactively. A `DERIVATION` gets walked through step-by-step. An `EXAMPLE` gets solved interactively. Without types, the agent treats everything as undifferentiated text.

### 3.5 Multi-Resolution / Fractal Structure

**Decision**: The curriculum graph has explicit resolution levels:

```
ResolutionLevel:
  SYLLABUS   — Full subject overview     ("Physics Class 11")
  UNIT       — Chapter cluster           ("Oscillations & Waves")
  CHAPTER    — Single chapter            ("Simple Harmonic Motion")
  CONCEPT    — Teachable unit            ("Energy in SHM")
  DETAIL     — Atomic fact/formula       ("U = ½kx²", worked example)
```

Each node knows its resolution level. The teaching agent:
- **Zooms in** when a student is confused: expand CONCEPT → DETAIL nodes
- **Zooms out** for recaps: compress DETAIL → CONCEPT summaries
- **Auto-selects** resolution based on teaching context

A `SUMMARIZES` edge connects higher-resolution nodes to their children (same pattern as PMG's fractal memory).

### 3.6 Source Text Preservation

**Decision**: Every node stores BOTH the original source text AND the LLM summary, in separate fields:

```
source_text: str    — Verbatim text from the PDF for this concept's page range
summary: str        — LLM-generated teaching summary (exhaustive, with formulas)
page_start: int     — Exact start page for THIS concept (not the chapter)
page_end: int       — Exact end page for THIS concept
```

**Why**: When the LLM summary is wrong, the source text is the ground truth. The teaching agent can fall back to it. Validation can compare summary against source to catch hallucinations.

---

## 4. Schema

### 4.1 Node Labels

```
(:Subject)           — Physics, Chemistry, Mathematics, Biology
(:Unit)              — Chapter cluster within a subject
(:Chapter)           — Single chapter from a textbook
(:Concept)           — A teachable unit (the workhorse node)
(:Detail)            — Atomic fact, formula, or example
(:Visual)            — Pre-generated DiagramSpec for a concept (eliminates runtime latency)
(:OntologyConcept)   — Cross-subject shared concept (future: "Energy" across Physics + Chemistry)
```

### 4.2 Concept Node Properties

```cypher
(:Concept {
  // Identity
  uid: "curriculum:physics:shm:energy_in_shm",  // stable semantic ID
  
  // Content
  topic_name: "Energy in SHM",
  concept_type: "FORMULA",              // from ConceptType enum
  summary: "Energy analysis reveals...", // LLM-generated exhaustive summary
  source_text: "The potential energy...",// Verbatim from PDF
  
  // Resolution
  resolution_level: "concept",          // from ResolutionLevel enum
  
  // Location
  page_start: 245,                      // exact page for THIS concept
  page_end: 246,
  textbook_title: "HC Verma - Concepts of Physics",
  
  // Teaching order (preserves the book's intended sequence)
  chapter_order: 10,                    // which chapter in the book (1-based)
  within_chapter_order: 6,             // concept sequence within chapter
  global_teaching_order: 10006,        // chapter_order*1000 + within_chapter_order
  estimated_duration_minutes: 5,        // LLM-estimated time to teach this concept
  difficulty: "intermediate",           // beginner/intermediate/advanced
  
  // Board intelligence bridge
  visual_hint: "Spring-mass energy diagram with KE/PE curves overlaid",
                                        // what the board should show for this concept
                                        // NULL for concepts that don't need visuals
  
  // Salience (computed post-extraction)
  salience_static: 8.0,                 // inherent importance (rule or LLM scored)
  salience_structural: 0.0,             // PageRank — computed after graph is built
  salience_total: 0.0,                  // α·static + β·structural + γ·dynamic
  
  // Provenance
  extraction_model: "claude-sonnet-4",
  extraction_confidence: 0.92,
  extracted_at: datetime("2026-04-05T..."),
  
  // Embeddings (for semantic search)
  embedding: [0.023, -0.019, ...]       // vector embedding of summary
})
```

### 4.3 Relationship Types

```
// Structural (hierarchy)
CONTAINS           — Subject→Unit, Unit→Chapter, Chapter→Concept
SUMMARIZES         — Higher-resolution node summarizes children (fractal)

// Pedagogical
PREREQUISITE       — A must be understood before B
LEADS_TO           — A naturally flows into B (teaching sequence)
EXAMPLE_OF         — B is a worked example of concept A
DERIVED_FROM       — B is mathematically derived from A
MISCONCEPTION_OF   — B is a common mistake about A
ANALOGY_FOR        — B is an intuitive analogy for A
APPLICATION_OF     — B is a real-world application of A

// Cross-chapter
CROSS_REFERENCES   — Concept in chapter X relates to concept in chapter Y
SHARED_FOUNDATION  — Both concepts build on the same underlying idea

// Visual
HAS_VISUAL         — Concept has a pre-generated DiagramSpec (Concept→Visual)

// Runtime evolution (populated by teaching agent, not pre-compute)
CO_ACTIVATED_WITH  — Hebbian: these concepts are frequently retrieved together
COMMONLY_CONFUSED  — Teaching data: students confuse these two concepts
```

### 4.4 Cross-Graph Edge Types (Integration Contract)

These edges are NOT created by the pre-compute pipeline. They are defined here so dashboard and student graph implementations know the contract:

```
// Dashboard State → Curriculum
ILLUSTRATES        — Board diagram illustrates a curriculum concept
REPRESENTS         — Board equation represents a curriculum formula

// Student Knowledge → Curriculum  
MASTERED           — Student has mastered this concept (with confidence score)
STRUGGLING         — Student is struggling with this concept
NOT_SEEN           — Student hasn't encountered this concept yet
HAS_MISCONCEPTION  — Student holds a specific misconception about this concept
```

---

## 5. Pipeline Architecture

### 5.1 Core Principle: Whole-Book Input, Book-Aware Extraction

The pipeline takes an **entire textbook** as input and produces **one unified curriculum graph**. It does NOT process chapters in isolation — that creates a disconnect where Chapter 10's extractor doesn't know what Chapter 5 covered, producing weak cross-chapter links patched as an afterthought.

Instead, the pipeline uses a **three-pass approach**:

1. **Book Skeleton Pass** — Understand the whole book's structure, chapter sequence, and cross-chapter dependencies FIRST.
2. **Chapter Detail Pass** — Extract fine-grained concepts per chapter, but WITH the book skeleton as context so every extraction is book-aware.
3. **Unification Pass** — Merge all chapter extractions into one graph, resolve cross-chapter references against real node UIDs, build summary hierarchy.

This ensures cross-chapter relationships are **first-class outputs of extraction**, not post-hoc discoveries.

### 5.2 Overview

```
Entire PDF Textbook
    │
    ▼
┌────────────────────────────────────────────────────────────────┐
│  STAGE 1: PDF Parsing (keep existing — it works)              │
│  PyMuPDF → text per page, TOC metadata, image refs            │
│  Output: PDFContent (all pages, all text, all metadata)       │
└───────────────────────┬────────────────────────────────────────┘
                        ▼
┌────────────────────────────────────────────────────────────────┐
│  STAGE 2: Chapter Detection (keep existing — it works)        │
│  TOC metadata → list[Chapter] with page ranges                │
│  Output: ordered list of ALL chapters in the book             │
└───────────────────────┬────────────────────────────────────────┘
                        ▼
┌────────────────────────────────────────────────────────────────┐
│  STAGE 3: Book Skeleton Extraction (NEW)                      │
│                                                               │
│  Input: Full TOC + first 2-3 paragraphs of every chapter      │
│         (fits in a single LLM call — ~5-10K tokens)           │
│                                                               │
│  LLM extracts:                                                │
│   - Chapter teaching order (the book's intended sequence)     │
│   - Chapter-level summaries (what each chapter covers)        │
│   - Cross-chapter prerequisites                               │
│     ("Ch10 SHM assumes Ch5 Energy + Ch7 Circular Motion")    │
│   - Unit groupings (which chapters form natural clusters)     │
│   - Subject-level theme map                                   │
│                                                               │
│  Output: BookSkeleton — the global context for all            │
│          subsequent extraction                                │
└───────────────────────┬────────────────────────────────────────┘
                        ▼
┌────────────────────────────────────────────────────────────────┐
│  STAGE 4: Book-Aware Chapter Extraction (NEW)                 │
│  Runs per-chapter, but each call receives:                    │
│   - The BookSkeleton (global context)                         │
│   - This chapter's full text                                  │
│   - Previous chapter's concept list (local continuity)        │
│   - Next chapter's summary (forward awareness)                │
│                                                               │
│  Two sub-passes per chapter:                                  │
│   Pass A — Structure: concept hierarchy, types, relationships │
│            including cross-chapter PREREQUISITE/LEADS_TO edges │
│            that reference other chapters BY NAME               │
│   Pass B — Content: exhaustive summaries + source text        │
│            for each concept, batched by page range            │
│                                                               │
│  Output: CurriculumExtractionResult per chapter               │
│          (already cross-chapter aware from BookSkeleton)       │
│                                                               │
│  NOTE: Large chapters (>50K chars) are chunked within this    │
│  stage. Chunks share the same BookSkeleton context.           │
│  Entity resolution merges chunks before moving to Stage 5.    │
└───────────────────────┬────────────────────────────────────────┘
                        ▼
┌────────────────────────────────────────────────────────────────┐
│  STAGE 5: Validation (NEW)                                    │
│  Runs per-chapter extraction result BEFORE merging            │
│                                                               │
│  Layer 1 — Structural (deterministic, no LLM):                │
│    referential integrity, required properties,                │
│    duplicate detection, page coverage check,                  │
│    teaching order continuity                                  │
│                                                               │
│  Layer 2 — Semantic (LLM, on sample):                         │
│    factual consistency vs source text,                        │
│    relationship correctness spot-check,                       │
│    missing concept detection                                  │
└───────────────────────┬────────────────────────────────────────┘
                        ▼
┌────────────────────────────────────────────────────────────────┐
│  STAGE 6: Unification & Entity Resolution (NEW)               │
│  Merges ALL chapter extractions into ONE unified result        │
│                                                               │
│  6a. Resolve cross-chapter references:                        │
│      Stage 4 created edges like:                              │
│        PREREQUISITE → "Chapter 5: Energy Conservation"        │
│      Now resolve to actual UIDs:                              │
│        PREREQUISITE → curriculum:physics:energy:conservation   │
│                                                               │
│  6b. Deduplicate shared concepts across chapters:             │
│      "Force" in Ch3 and "Restoring Force" in Ch10 — detect    │
│      via normalized name hash + embedding similarity           │
│      Create SHARED_FOUNDATION / CROSS_REFERENCES edges        │
│                                                               │
│  6c. Build hierarchy:                                         │
│      - Create Unit nodes from BookSkeleton unit groupings     │
│      - Create Subject node as root                            │
│      - Wire CONTAINS edges: Subject→Unit→Chapter→Concept      │
│      - Wire SUMMARIZES edges at each resolution level         │
│                                                               │
│  6d. Assign global teaching order:                            │
│      chapter_order (from book sequence) ×1000                 │
│      + within_chapter_order                                   │
│      = global_teaching_order (stable, gapless)                │
│                                                               │
│  Output: One unified CurriculumExtractionResult               │
│          for the ENTIRE book                                  │
└───────────────────────┬────────────────────────────────────────┘
                        ▼
┌────────────────────────────────────────────────────────────────┐
│  STAGE 7: Salience Scoring (NEW)                              │
│  Static salience: rule-based (concept type, formula presence) │
│  Structural salience: PageRank on the full unified graph      │
│  Total: α·static + β·structural (dynamic added at runtime)   │
└───────────────────────┬────────────────────────────────────────┘
                        ▼
┌────────────────────────────────────────────────────────────────┐
│  STAGE 8: Neo4j Ingestion (NEW — replaces JSON save)          │
│  MERGE nodes and relationships into Neo4j                     │
│  Create constraints, indexes, vector indexes                  │
│  Generate embeddings for all concept summaries                │
│  Verify: re-runnable (MERGE = upsert, no duplicates)         │
└────────────────────────────────────────────────────────────────┘
```

### 5.3 The BookSkeleton (Stage 3 Output)

The BookSkeleton is the global context that makes every chapter extraction book-aware. It's extracted once and passed to every subsequent stage.

```python
class ChapterSummary(BaseModel):
    """A chapter's role within the book."""
    chapter_index: int                    # 1-based position in book
    title: str
    page_start: int
    page_end: int
    summary: str                          # 2-3 sentence overview
    key_concepts: list[str]               # major topics covered
    prerequisites_from: list[str]         # chapter titles this depends on
    leads_to: list[str]                   # chapter titles that depend on this

class UnitGrouping(BaseModel):
    """A cluster of related chapters."""
    unit_name: str                        # e.g., "Oscillations & Waves"
    chapter_indices: list[int]            # which chapters belong
    theme: str                            # unifying theme description

class BookSkeleton(BaseModel):
    """Global structure of the entire textbook."""
    textbook_title: str
    subject: str
    total_chapters: int
    total_pages: int
    chapters: list[ChapterSummary]        # ordered by book sequence
    units: list[UnitGrouping]             # chapter clusters
    cross_chapter_prerequisites: list[dict]  # [{from_chapter, to_chapter, reason}]
    subject_overview: str                 # what this book covers overall
```

**LLM prompt for skeleton extraction** (single call):

```
System: You are analyzing a textbook's structure. Given the table of contents 
and opening paragraphs of each chapter, extract the book's teaching architecture.

Input:
- Full table of contents with page numbers
- First 2-3 paragraphs of each chapter

Extract:
1. Chapter summaries (what each chapter covers, in 2-3 sentences)
2. Cross-chapter prerequisites (which chapters MUST be understood before which)
3. Unit groupings (which chapters form natural clusters)
4. The book's overall teaching philosophy and subject scope

Return JSON matching the BookSkeleton schema.

CRITICAL: The chapter order in the book is an intentional pedagogical design.
Preserve and respect this order — it represents the author's teaching sequence.
```

This costs ~1 LLM call for the entire book. The skeleton is small (~2-5K tokens) and gets passed as context to every chapter extraction.

### 5.2 Canonical Intermediate Format

The key architectural insight from PMG: **decouple extraction from storage**. Every extraction — whether from a single chapter, a chunk of a large chapter, or a cross-chapter synthesis — produces a `CurriculumExtractionResult`:

```python
class ConceptType(str, Enum):
    TOPIC = "topic"
    DEFINITION = "definition"
    FORMULA = "formula"
    DERIVATION = "derivation"
    EXAMPLE = "example"
    APPLICATION = "application"
    MISCONCEPTION = "misconception"
    ANALOGY = "analogy"
    EXPERIMENT = "experiment"
    VISUALIZATION = "visualization"

class ResolutionLevel(str, Enum):
    SYLLABUS = "syllabus"
    UNIT = "unit"
    CHAPTER = "chapter"
    CONCEPT = "concept"
    DETAIL = "detail"

class CurriculumRelationType(str, Enum):
    CONTAINS = "contains"
    SUMMARIZES = "summarizes"
    PREREQUISITE = "prerequisite"
    LEADS_TO = "leads_to"
    EXAMPLE_OF = "example_of"
    DERIVED_FROM = "derived_from"
    MISCONCEPTION_OF = "misconception_of"
    ANALOGY_FOR = "analogy_for"
    APPLICATION_OF = "application_of"
    CROSS_REFERENCES = "cross_references"
    SHARED_FOUNDATION = "shared_foundation"

class ExtractionNode(BaseModel):
    """A concept extracted from curriculum content."""
    uid: str                           # stable semantic ID
    topic_name: str
    concept_type: ConceptType
    resolution_level: ResolutionLevel
    section_number: str | None = None  # textbook section ref: "12.1.3", "5.2", etc.
                                       # the extraction floor — every numbered section
                                       # in the textbook MUST have at least one node
    summary: str                       # LLM-generated exhaustive summary
    source_text: str                   # verbatim from PDF
    page_start: int
    page_end: int
    chapter_order: int                 # which chapter in the book (1-based)
    within_chapter_order: int          # concept sequence within the chapter
    global_teaching_order: int = 0     # computed: chapter_order*1000 + within_chapter_order
    difficulty: str = "intermediate"
    estimated_duration_minutes: float = 3.0  # LLM-estimated teaching time
    visual_hint: str | None = None     # what to draw on the board for this concept
                                       # e.g., "Spring-mass energy diagram with KE/PE curves"
                                       # Bridges curriculum graph → board intelligence
    parent_uid: str | None = None
    children_uids: list[str] = []
    metadata: dict = {}

class ExtractionRelationship(BaseModel):
    """A relationship between two concepts."""
    relationship_key: str              # unique key for dedup
    type: CurriculumRelationType
    from_uid: str
    to_uid: str
    label: str = ""                    # human-readable explanation
    properties: dict = {}

class ExtractionSource(BaseModel):
    """Provenance metadata."""
    textbook_title: str
    chapter_title: str
    page_range: str
    extractor_model: str
    extraction_timestamp: str
    confidence: float = 0.0

class CurriculumExtractionResult(BaseModel):
    """Canonical intermediate format — the bridge between extraction and Neo4j.
    
    At chapter level: contains one chapter's concepts.
    At book level (after unification): contains ALL chapters' concepts merged.
    """
    version: str = "1.0"
    subject: str
    textbook_title: str
    scope: str = "chapter"             # "chapter" or "book" (after unification)
    chapter_title: str | None = None   # None when scope="book"
    source: ExtractionSource
    book_skeleton: BookSkeleton | None = None  # attached after Stage 3
    nodes: list[ExtractionNode]
    relationships: list[ExtractionRelationship]
    warnings: list[str] = []
```

This format is:
- **Inspectable** — serialize to JSON, review before committing to Neo4j
- **Mergeable** — two extractions can be merged with entity resolution
- **Validatable** — structural and semantic checks run on this before ingestion

### 5.4 Schema Context Injection

Every LLM extraction call receives the curriculum graph schema as context. This forces the LLM to produce output that conforms to our structure instead of inventing its own. Adapted from PMG's `schema_context.py` pattern.

```
CURRICULUM_SCHEMA_CONTEXT = """
## Curriculum Graph Schema

### Hierarchy (NOT flat — concepts are nested):
  Subject → Unit → Chapter → Concept → Detail
  Each level connected by CONTAINS edges.

### Concept Types (every node MUST have exactly one):
  TOPIC          — broad teaching topic
  DEFINITION     — precise definition of a key term
  FORMULA        — mathematical relationship (MUST include the equation)
  DERIVATION     — step-by-step mathematical proof
  EXAMPLE        — worked problem or concrete instance
  APPLICATION    — real-world use case
  MISCONCEPTION  — common student mistake (MUST describe the wrong belief)
  ANALOGY        — intuitive comparison
  EXPERIMENT     — demonstration or lab procedure
  VISUALIZATION  — diagram, graph, or animation description

### Relationship Types (only these are valid):
  PREREQUISITE     — A must be understood before B
  LEADS_TO         — A naturally flows into B (teaching sequence)
  EXAMPLE_OF       — B is a worked example of concept A
  DERIVED_FROM     — B is mathematically derived from A
  MISCONCEPTION_OF — B is a common mistake about A
  ANALOGY_FOR      — B is an intuitive analogy for A
  APPLICATION_OF   — B is a real-world application of A
  CROSS_REFERENCES — concept in chapter X relates to concept in chapter Y

### Mandatory Extraction Rules (do NOT merge or skip these):
  - Every named equation → SEPARATE FORMULA node (F=ma is one, v=u+at is another, NEVER combine)
  - Every bolded/key term with a definition → SEPARATE DEFINITION node
  - Every worked example or solved problem → SEPARATE EXAMPLE node
  - Every figure, diagram, or graph referenced in the text → SEPARATE VISUALIZATION node
  - Every step-by-step proof or derivation → DERIVATION node
  - Every "common mistake", "caution", or "note" callout → MISCONCEPTION node
  - Every real-world application mentioned → APPLICATION node
  - If a single page has 3 equations, that's 3 FORMULA nodes. Do NOT combine them.
  - Every FORMULA node MUST contain the actual equation in its topic_name or summary
  - Every MISCONCEPTION node MUST describe what students wrongly believe

### Visual Hint Rules (when to generate visual_hint):
  - FORMULA      → ALWAYS. Show equation with labeled diagram of variables.
  - DERIVATION   → ALWAYS. Step-by-step visual with equations appearing sequentially.
  - EXAMPLE      → ALWAYS. Problem setup diagram (free body diagram, circuit, geometry, etc.)
  - EXPERIMENT   → ALWAYS. Apparatus/setup diagram.
  - VISUALIZATION→ ALWAYS. This IS the visual — describe the diagram the textbook shows.
  - DEFINITION   → IF it has physical/geometric meaning (e.g., "amplitude" → sine wave with A marked).
  - MISCONCEPTION→ IF visual helps (side-by-side "wrong vs right" diagram).
  - APPLICATION  → IF it describes a physical scenario (e.g., "car suspension" → spring-damper diagram).
  - ANALOGY      → IF the analogy is visual (e.g., "energy like water in connected vessels").
  - TOPIC        → Usually null (too broad for a single visual).

### Other Rules:
  - Cross-chapter references use format "ChapterTitle::ConceptName"
  - No circular prerequisites (A→B→C→A is forbidden)
  - Teaching order within a chapter follows the book's sequence
"""
```

This schema context is prepended to EVERY extraction prompt (Pass A and Pass B). It ensures the LLM never invents unlisted concept types or relationship types.

### 5.5 Book-Aware Chapter Extraction (Stage 4 Detail)

Each chapter is extracted with full awareness of the book's structure. The LLM receives:

1. **Curriculum Schema Context** — the graph structure rules (~1K tokens)
2. **BookSkeleton** — the global context (~2-5K tokens)
3. **This chapter's full text** — the content to extract from
4. **Previous chapter's concept list** — for continuity ("the student just learned these concepts")
5. **Next chapter's summary** — for forward-linking ("this feeds into these topics next")

**Two sub-passes per chapter:**

**Pass A — Structure** (1 LLM call per chapter):

Extract the concept hierarchy with types and relationships. No long summaries yet — just structure. This is cheap and fast.

```
System: You are extracting a curriculum concept graph from a textbook chapter.

{CURRICULUM_SCHEMA_CONTEXT}

BOOK CONTEXT (do NOT extract concepts from this — it's for awareness only):
{book_skeleton_json}

PREVIOUS CHAPTER covered these concepts:
{previous_chapter_concept_names}

THIS CHAPTER's text follows. Extract ONLY from this chapter.

For each concept, return a JSON object with:
- topic_name
- concept_type (MUST be from the schema above)
- resolution_level (concept or detail)
- section_number (the textbook section this belongs to: "12.1", "12.1.3", etc. 
  If the concept is a sub-part of a numbered section, use the parent section's number)
- parent concept within this chapter (if any)
- relationships (MUST use relationship types from the schema above)
- relationships to concepts in OTHER chapters (format: "ChapterTitle::ConceptName")
- approximate page range
- visual_hint (one-line description of what to draw on the board for this concept, 
  or null if no visual needed)
- estimated_duration_minutes (how long a teacher should spend on this)

Return JSON with nodes[] and relationships[].

CRITICAL — Mandatory extraction (follow the schema rules above strictly):
- EVERY named equation → separate FORMULA node (if a page has 3 equations, that's 3 nodes)
- EVERY bolded/key term with a definition → separate DEFINITION node
- EVERY worked example or "Example X.Y" → separate EXAMPLE node
- EVERY figure/diagram referenced ("Fig. 12.3", "see diagram") → separate VISUALIZATION node
- EVERY step-by-step proof → DERIVATION node
- EVERY "common mistake"/"caution"/"note" callout → MISCONCEPTION node
- EVERY real-world application → APPLICATION node
- Do NOT merge small concepts into bigger ones. If it's separately teachable, it's a separate node.
- Cross-chapter PREREQUISITE edges where this chapter builds on earlier chapters
- Cross-chapter LEADS_TO edges where this chapter feeds into later chapters
- Preserve the book's teaching order within the chapter

Visual hints — follow the visual hint rules from the schema:
- FORMULA/DERIVATION/EXAMPLE/EXPERIMENT/VISUALIZATION → ALWAYS provide visual_hint
- DEFINITION → provide visual_hint IF the concept has physical/geometric meaning
- MISCONCEPTION → provide visual_hint IF a "wrong vs right" diagram would help
- APPLICATION → provide visual_hint IF it describes a physical scenario

Expected output: a 15-page physics chapter typically yields 50-100 nodes. 
If you're producing fewer than 40, you're likely merging concepts that should be separate.
```

**Pass B — Content** (batched LLM calls):

For each node from Pass A, extract its exhaustive summary and identify its exact source text. Batched in groups of 5-10 nodes by page range.

```
System: You are writing exhaustive teaching summaries for curriculum concepts.

{CURRICULUM_SCHEMA_CONTEXT}

Each summary must contain ALL information a teacher needs to deliver a 
complete explanation — every formula, derivation step, example, and insight.

For each concept below, provide:
1. summary: exhaustive teaching content (include all formulas with variable meanings)
2. source_text_pages: the exact page numbers where this content appears
3. difficulty: beginner/intermediate/advanced

Chapter text (pages {start}-{end}):
{chapter_text_for_pages}

Concepts to summarize:
{list_of_concept_names_and_types}
```

**Why two sub-passes:**
- Pass A is cheap (~1 LLM call per chapter, structured JSON output)
- Pass B is targeted — the LLM only summarizes specific page ranges, not the whole chapter
- If Pass A has quality issues (structural validation catches them), fix before spending on Pass B
- For large chapters (>50K chars), Pass A is chunked. Each chunk gets the same BookSkeleton context. Entity resolution merges chunks BEFORE Pass B runs on the merged structure.

**Chunking strategy for large chapters:**
1. Split chapter text at ~25K char boundaries (at paragraph breaks)
2. Each chunk gets: BookSkeleton + chunk text + overlap with adjacent chunks (2K chars)
3. Run Pass A on each chunk → per-chunk extraction results
4. Entity resolution merges chunk results (see Stage 6)
5. Run Pass B on the merged structure (no duplication of LLM summarization work)

### 5.5a Deterministic Anchor Extraction (Pre-LLM)

Before the LLM ever runs, we extract **verifiable anchors** from the raw PDF text using pure regex/heuristics. These anchors become the completeness checklist that the LLM's output is validated against. This is our equivalent of PMG's deterministic JSON extractors — the part that CAN'T miss anything because it doesn't rely on LLM judgment.

```python
class DeterministicAnchorExtractor:
    """Extract verifiable anchors from PDF text BEFORE LLM extraction.
    These become the completeness checklist the LLM output is validated against.
    
    PMG gets completeness for free because ~70% of its data is structured JSON.
    We're 100% PDF — so we extract what structure we CAN deterministically,
    then use it to verify the LLM didn't miss anything.
    """
    
    def extract_anchors(self, chapter_text: str, pages: list) -> ExtractionAnchors:
        return ExtractionAnchors(
            # Section numbering — THE most reliable anchor
            section_numbers=self._find_section_numbers(chapter_text),
            
            # Other deterministic anchors
            equations=self._find_equations(chapter_text),
            figure_refs=self._find_figure_references(chapter_text),
            example_refs=self._find_example_references(chapter_text),
            defined_terms=self._find_defined_terms(chapter_text),
            page_count=len(pages),
        )
    
    def _find_section_numbers(self, text: str) -> list[SectionAnchor]:
        """Find ALL numbered sections/subsections in the text.
        
        Textbooks use numbered sections: 12.1, 12.2, 12.2.1, 12.2.2, etc.
        The format varies by textbook but is always present:
          - Two-level: 12.1, 12.2, 12.3
          - Three-level: 12.1.1, 12.1.2, 12.2.1
          - Mixed: 1.2, 1.2.a, 1.3
        
        The SMALLEST numbered unit is the extraction floor — the LLM 
        MUST produce at least one concept node for every numbered section.
        It may break them down further, but it cannot skip any.
        """
        patterns = [
            # Three-level: 12.1.1, 1.2.3, etc. (most granular — check first)
            r'(?m)^\s*(\d{1,3}\.\d{1,3}\.\d{1,3})\s+([A-Z][^\n]{3,80})',
            # Two-level: 12.1, 1.2, etc.
            r'(?m)^\s*(\d{1,3}\.\d{1,3})\s+([A-Z][^\n]{3,80})',
            # Letter sub-sections: 12.1a, 12.1(a), etc.
            r'(?m)^\s*(\d{1,3}\.\d{1,3}\s*[a-z\(\)])\s+([A-Z][^\n]{3,80})',
        ]
        
        anchors = []
        seen_numbers = set()
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                number = match.group(1).strip()
                title = match.group(2).strip()
                if number not in seen_numbers:
                    seen_numbers.add(number)
                    anchors.append(SectionAnchor(
                        section_number=number,
                        title=title,
                        depth=number.count('.'),  # 12.1 = depth 1, 12.1.1 = depth 2
                    ))
        
        return sorted(anchors, key=lambda a: a.section_number)

@dataclass
class SectionAnchor:
    section_number: str   # "12.1.1"
    title: str            # "Potential Energy in SHM"
    depth: int            # number of dots (1 = major, 2 = sub, 3 = sub-sub)

@dataclass  
class ExtractionAnchors:
    section_numbers: list[SectionAnchor]  # THE primary completeness anchor
    equations: list[str]                   # equation strings found
    figure_refs: list[str]                 # "Fig. 12.3", "Figure 5"
    example_refs: list[str]               # "Example 12.1", "Problem 5"
    defined_terms: list[str]              # bold/italic terms
    page_count: int
    
    @property
    def smallest_section_depth(self) -> int:
        """The finest granularity of section numbering in this chapter."""
        return max((a.depth for a in self.section_numbers), default=1)
    
    @property
    def leaf_sections(self) -> list[SectionAnchor]:
        """Sections at the finest granularity — the extraction floor."""
        max_depth = self.smallest_section_depth
        return [a for a in self.section_numbers if a.depth == max_depth]
```

**How this feeds into the LLM extraction:**

The anchors are passed to Pass A as an explicit checklist:

```
{CURRICULUM_SCHEMA_CONTEXT}

...existing prompt...

SECTION NUMBERING FOUND IN THIS CHAPTER (extraction floor — do NOT skip any):
{for anchor in anchors.section_numbers}
  {anchor.section_number} — {anchor.title}
{endfor}

EVERY numbered section above MUST have AT LEAST ONE concept node.
You may break sections into finer-grained concepts (formulas, examples, etc.)
but you MUST NOT skip any numbered section entirely.

FIGURES FOUND: {anchors.figure_refs}
EXAMPLES FOUND: {anchors.example_refs}
Each figure and example above MUST also have its own node.
```

This makes the LLM's job explicit: "here are the sections, figures, and examples. Extract all of them. You can go deeper, but this is the floor."

### 5.5b Validation (Stage 5)

**Layer 1 — Structural (deterministic, no LLM)**:

```python
class StructuralValidator:
    def validate(self, extraction: CurriculumExtractionResult) -> ValidationReport:
        self._check_duplicate_uids(extraction, report)
        self._check_referential_integrity(extraction, report)     # all relationships reference existing nodes
        self._check_required_properties(extraction, report)       # summary non-empty, page range valid
        self._check_type_consistency(extraction, report)          # FORMULA nodes should contain equations
        self._check_hierarchy_integrity(extraction, report)       # parent-child references are consistent
        self._check_page_coverage(extraction, report)             # every page in chapter range has ≥1 concept
        self._check_teaching_order_continuity(extraction, report) # no gaps in teaching order
        self._check_circular_dependencies(extraction, report)     # no A→B→C→A prerequisite cycles
        return report
```

**Circular dependency detection** (`_check_circular_dependencies`): Builds a directed graph from all PREREQUISITE edges and runs DFS-based cycle detection. A cycle like "Energy in SHM → Mathematical Description → Energy in SHM" would cause the teaching agent to loop forever when traversing prerequisites. Any cycle is a hard error — the extraction must be fixed before proceeding.

**Extraction completeness verification** (`_check_extraction_completeness`): Compares the extraction against deterministic anchors in the source text to catch under-extraction. This is critical — LLMs systematically under-extract, merging small concepts and skipping "obvious" items.

```python
def _check_extraction_completeness(self, extraction, anchors: ExtractionAnchors, report):
    """Compare extraction against deterministic anchors from source text.
    
    The anchors were extracted BEFORE the LLM ran. They represent
    what we KNOW exists in the source text. If the LLM missed any,
    that's a hard error.
    """
    
    # 0. MOST CRITICAL: Section number coverage
    #    Every numbered section in the textbook MUST have at least one concept node.
    #    This is the extraction floor — the LLM can go deeper but cannot skip sections.
    extracted_topics = {n.topic_name.lower() for n in extraction.nodes}
    extracted_summaries = " ".join(n.summary.lower() for n in extraction.nodes)
    
    missing_sections = []
    for section in anchors.section_numbers:
        # Check if any extracted node matches this section (by number or title)
        section_covered = (
            section.section_number in extracted_summaries or
            section.title.lower() in extracted_topics or
            any(section.title.lower() in n.topic_name.lower() or
                section.section_number in (n.metadata.get("section_number", "") or "")
                for n in extraction.nodes)
        )
        if not section_covered:
            missing_sections.append(section)
    
    if missing_sections:
        report.add_error("MISSING_SECTIONS",
            f"{len(missing_sections)}/{len(anchors.section_numbers)} textbook sections "
            f"have NO corresponding concept node. Missing: "
            f"{[f'{s.section_number} {s.title}' for s in missing_sections[:10]]}")
    
    # 1. Equation coverage
    equation_count = len(anchors.equations)
    formula_nodes = [n for n in extraction.nodes if n.concept_type == ConceptType.FORMULA]
    if formula_nodes and equation_count and len(formula_nodes) < equation_count * 0.7:
        report.add_error("MISSING_FORMULAS",
            f"Source has ~{equation_count} equations but only "
            f"{len(formula_nodes)} FORMULA nodes extracted (need ≥70%)")
    
    # 2. Figure coverage
    figure_count = len(anchors.figure_refs)
    viz_nodes = [n for n in extraction.nodes if n.concept_type == ConceptType.VISUALIZATION]
    if figure_count and len(viz_nodes) < figure_count:
        report.add_error("MISSING_FIGURES",
            f"Source references {figure_count} figures but only "
            f"{len(viz_nodes)} VISUALIZATION nodes extracted. "
            f"Missing: {[f for f in anchors.figure_refs if not any(f.lower() in n.topic_name.lower() for n in viz_nodes)][:5]}")
    
    # 3. Example coverage
    example_count = len(anchors.example_refs)
    example_nodes = [n for n in extraction.nodes if n.concept_type == ConceptType.EXAMPLE]
    if example_count and len(example_nodes) < example_count * 0.8:
        report.add_error("MISSING_EXAMPLES",
            f"Source has ~{example_count} examples but only "
            f"{len(example_nodes)} EXAMPLE nodes extracted (need ≥80%)")
    
    # 4. Visual hint coverage on visual-mandatory types
    visual_mandatory_types = {
        ConceptType.FORMULA, ConceptType.DERIVATION, ConceptType.EXAMPLE,
        ConceptType.EXPERIMENT, ConceptType.VISUALIZATION
    }
    concepts_needing_visuals = [
        n for n in extraction.nodes if n.concept_type in visual_mandatory_types
    ]
    missing_hints = [n for n in concepts_needing_visuals if not n.visual_hint]
    if missing_hints:
        report.add_error("MISSING_VISUAL_HINTS",
            f"{len(missing_hints)}/{len(concepts_needing_visuals)} visual-mandatory "
            f"concepts have no visual_hint: "
            f"{[n.topic_name for n in missing_hints[:5]]}")
    
    # 5. Overall density check
    if anchors.page_count > 0:
        density = len(extraction.nodes) / anchors.page_count
        if density < 3.0:
            report.add_warning("LOW_EXTRACTION_DENSITY",
                f"Only {density:.1f} concepts/page extracted. "
                f"Expected ≥3.0 for thorough extraction. "
                f"LLM may be merging concepts that should be separate.")
```

**Self-correcting extraction loop:**

When completeness checks fail, the pipeline re-runs Pass A with a **targeted gap-filling prompt**. This is modeled after PMG's entity creation sub-agent — a separate LLM call focused ONLY on finding what was missed.

```
System: You are a gap-filling agent. A previous extraction MISSED some content.
Your job is to extract ONLY the missing items listed below.

{CURRICULUM_SCHEMA_CONTEXT}

Chapter text:
{chapter_text}

ALREADY EXTRACTED (do NOT re-extract these):
{list_of_already_extracted_concept_names}

MISSING ITEMS THAT MUST BE EXTRACTED:

Textbook sections with no concept node:
{for section in missing_sections}
  {section.section_number} — {section.title}
    → Extract at least one concept node for this section
{endfor}

Figures with no VISUALIZATION node:
{for fig in unmatched_figures}
  {fig} → Extract a VISUALIZATION node with visual_hint
{endfor}

Examples with no EXAMPLE node:
{for ex in unmatched_examples}
  {ex} → Extract an EXAMPLE node
{endfor}

Equations with no FORMULA node:
{for eq in unmatched_equations}
  {eq} → Extract a FORMULA node
{endfor}

For each missing item, return a JSON node with all standard fields
(topic_name, concept_type, visual_hint, estimated_duration_minutes, etc.)
and relationships to existing concepts where applicable.
```

This creates a **self-correcting extraction loop**:

```
Extract (Pass A) → Validate against anchors → gaps found?
    │                                            │
    │  NO gaps                              YES: gaps exist
    │                                            │
    ▼                                            ▼
  Proceed to Pass B                    Run gap-filling sub-agent
                                             │
                                             ▼
                                       Merge gap-fill results
                                       into extraction
                                             │
                                             ▼
                                       Re-validate (max 2 retries)
```

Maximum 2 retries to avoid infinite loops. If gaps persist after 2 retries, log as warnings and proceed — the teaching agent can still function with partial coverage, but the quality report flags it for human review.

**Layer 2 — Semantic (LLM, runs on structural-validated output)**:

Feed the extraction result + source text to a cheaper model (Haiku/Sonnet) with:
```
Here is the source text for pages 245-246:
{source_text}

Here is the extracted concept:
  topic: "Energy in SHM"
  type: FORMULA
  summary: "Energy analysis reveals..."
  relationships: [PREREQUISITE from "Mathematical Description"]

Check:
1. Is the summary factually consistent with the source text?
2. Are any formulas in the summary incorrect?
3. Is the PREREQUISITE relationship correct — does "Mathematical Description" 
   actually need to be understood before "Energy in SHM"?
4. Are there concepts on these pages that were NOT extracted?

Return JSON: {factual_issues: [...], missing_concepts: [...], relationship_issues: [...]}
```

This catches the exact problems current pipeline can't: hallucinated formulas, wrong relationships, missed concepts. Runs on ~10% of nodes (random sample + all FORMULA/DERIVATION nodes) to balance cost vs quality.

### 5.6 Unification & Entity Resolution (Stage 6 Detail)

This is where all chapter extractions become ONE unified book graph. Three sub-steps:

**6a. Within-chapter chunk merging** (only for large chapters that were chunked):

1. **Normalize topic names**: lowercase, strip whitespace, remove "of", "the", "in"
2. **Hash**: `SHA-256(normalized_name + concept_type + parent_slug)` → 16-char identity key
3. **Match**: Concepts with same identity key across chunks are the same concept
4. **Merge strategy**: 
   - `summary` → concatenate with LLM reconciliation ("merge these two summaries of the same concept into one exhaustive summary")
   - `source_text` → concatenate (preserve all source material)
   - `page_start` → min of both, `page_end` → max of both
   - `relationships` → union (dedup by relationship_key)

**6b. Cross-chapter reference resolution**:

Stage 4 created edges like:
```
PREREQUISITE from "Energy in SHM" → "Chapter 5::Energy Conservation"
```

Now resolve the `"Chapter 5::ConceptName"` references to actual UIDs:
1. Fuzzy-match chapter title → find the chapter extraction
2. Fuzzy-match concept name within that chapter → find the target node UID
3. Replace placeholder with real UID: `→ curriculum:physics:work_energy:conservation_of_energy`
4. Log unresolved references as warnings (may indicate extraction gaps)

**6c. Cross-chapter shared concept detection**:

Beyond the explicit cross-chapter edges from extraction, detect implicit connections:
- "Force" in Chapter 3 and "Restoring Force" in Chapter 10 share a foundation
- "Energy Conservation" in Chapter 5 and "Energy in SHM" in Chapter 10 cross-reference
- Detection via: embedding similarity of concept summaries (threshold: cosine > 0.85) + LLM confirmation for high-similarity pairs
- Create `SHARED_FOUNDATION` and `CROSS_REFERENCES` edges

**6d. Build resolution hierarchy**:

- Create `(:Subject)` node from BookSkeleton's subject + overview
- Create `(:Unit)` nodes from BookSkeleton's unit groupings
- Wire `CONTAINS` edges: Subject→Unit→Chapter→Concept→Detail
- Wire `SUMMARIZES` edges: each parent summarizes its children

**6e. Assign global teaching order**:

```python
global_teaching_order = (chapter_order * 1000) + within_chapter_order
```

This preserves the book's intended teaching sequence across ALL chapters while allowing fine-grained ordering within each chapter. The `* 1000` gap leaves room for future insertions without renumbering.

**Output**: One unified `CurriculumExtractionResult` for the entire book — all chapters, all cross-chapter edges, full hierarchy from Subject down to Detail.

### 5.6 Salience Scoring (Stage 6)

**Static salience (rule-based)**:

```python
SALIENCE_RULES = {
    ConceptType.DEFINITION: 8.0,      # Definitions are foundational
    ConceptType.FORMULA: 9.0,         # Formulas are high-value
    ConceptType.DERIVATION: 7.0,      # Important for deep understanding
    ConceptType.EXAMPLE: 5.0,         # Useful but not foundational
    ConceptType.APPLICATION: 6.0,     # Bridges theory to practice
    ConceptType.MISCONCEPTION: 8.5,   # Critical to address proactively
    ConceptType.ANALOGY: 4.0,         # Helpful but supplementary
    ConceptType.EXPERIMENT: 5.0,
    ConceptType.VISUALIZATION: 4.0,
    ConceptType.TOPIC: 7.0,           # Structural importance
}

# Boost for nodes with many prerequisites pointing TO them (highly depended upon)
# Boost for nodes at CHAPTER or CONCEPT resolution (more important than DETAIL)
```

**Structural salience (PageRank)**:

After the full graph is in Neo4j, run PageRank on the PREREQUISITE and LEADS_TO subgraph. Concepts that many others depend on get higher structural salience.

**Total**: `S = α·S_static + β·S_structural` (α=0.6, β=0.4 initially; dynamic salience added at runtime by teaching agent).

### 5.7 Neo4j Ingestion (Stage 7)

Convert `CurriculumExtractionResult` to Cypher deterministically (no LLM):

```python
class CurriculumCypherGenerator:
    def generate(self, extraction: CurriculumExtractionResult) -> list[str]:
        statements = []
        for node in extraction.nodes:
            statements.append(self._node_to_merge(node))
        for rel in extraction.relationships:
            statements.append(self._rel_to_merge(rel))
        return statements
    
    def _node_to_merge(self, node: ExtractionNode) -> str:
        # MERGE by uid (stable, deterministic)
        # SET all properties
        # Handles re-runs gracefully (MERGE = upsert)
        ...
```

**Also**: Generate embeddings for all concept summaries (via embedding model) and store as vector properties for semantic search.

### 5.8 Visual Pre-Generation (Stage 9)

This stage directly attacks the #1 product experience killer: **10-15 second diagram generation latency**. Currently, the design_agent generates every DiagramSpec from scratch during a live lesson. By shifting generation to pre-compute time — where latency doesn't matter — we eliminate wait time for the majority of teaching visuals.

**How it works:**

For every concept node with a non-null `visual_hint`, generate a `DiagramSpec` JSON offline:

```
Input (per concept):
  - visual_hint: "Spring-mass energy diagram with KE/PE curves overlaid"
  - summary: "Energy analysis reveals... U = ½kx², K = ½mv²..."
  - concept_type: FORMULA
  - related concepts (from graph edges): parent topic, prerequisites

Output:
  - Full DiagramSpec JSON (same format design_agent produces)
  - Stored as (:Visual) node in Neo4j, linked via HAS_VISUAL edge
```

**The generation prompt** reuses the existing design_agent's system prompt (from `design_agent/backend/prompts.py`) — same SVG element types, same coordinate system, same KaTeX rules. The only difference is it runs offline with no latency pressure.

```
For each concept with visual_hint:

  1. Build prompt:
     "Generate a DiagramSpec for a teaching visual.
      Topic: {concept.topic_name}
      Visual description: {concept.visual_hint}
      Key content: {concept.summary (first 500 chars)}
      Concept type: {concept.concept_type}
      
      The diagram should be clear, educational, and suitable for 
      display on a classroom screen. Include interactive parameters 
      (sliders) where the concept benefits from exploration."

  2. Call Claude → get DiagramSpec JSON
  3. Validate spec against DiagramSpec Pydantic schema
  4. Store as (:Visual) node with HAS_VISUAL edge to concept
```

**Neo4j schema for Visual nodes:**

```cypher
(:Visual {
  uid: "visual:physics:shm:energy_in_shm",   // mirrors concept UID
  diagram_spec: "{...}",                       // full DiagramSpec JSON string
  spec_version: "1.0",                         // for cache invalidation
  generation_model: "claude-sonnet-4",
  generated_at: datetime("2026-04-05T..."),
  element_count: 12,                           // number of SVG elements
  has_interactive_params: true,                // has sliders
  width: 900,
  height: 650
})

// Edge
(concept)-[:HAS_VISUAL]->(visual)
```

**At teaching time — the latency payoff:**

```
BEFORE (current design_agent flow):
  Agent needs visual → sends prompt to Claude → 10-15 sec → DiagramSpec → render
  
AFTER (with pre-generated visuals):
  Agent reaches concept → queries Neo4j for HAS_VISUAL → 5-15ms → DiagramSpec → render
  
  If agent needs to MODIFY the visual (highlight, animate, change parameter):
    → Uses Modify Tool on the pre-generated spec (incremental, fast)
    → NOT regenerating from scratch
```

**Tiered visual strategy (complete picture):**

| Tier | When Generated | Latency at Teaching Time | Coverage |
|---|---|---|---|
| **Tier 1: Pre-generated** | Pipeline time (this stage) | **5-15ms** (Neo4j lookup) | ~70% of visuals |
| **Tier 2: Lesson-load** | When teacher selects chapter | **0ms** (ready before lesson) | ~15% of visuals |
| **Tier 3: Anticipated** | Background, during teaching (concept N+1 while teaching N) | **0ms** if pre-gen completes in time | ~10% of visuals |
| **Tier 4: Real-time** | On-demand via design_agent | **5-15s** (fallback for ad-hoc) | ~5% of visuals |

Tier 1 is handled by the curriculum pipeline. Tiers 2-3 are the Anticipation Engine (board intelligence). Tier 4 is the existing design_agent as fallback. **Combined, ~95% of visuals have zero perceived latency.**

**Cost estimate:**

For a 30-chapter textbook with ~40 concepts per chapter = ~1200 concepts. Assume ~60% have visual_hints = ~720 visual generations. At ~$0.03 per Claude Sonnet call = **~$22 per textbook**. This is a one-time cost that eliminates latency for every future lesson taught from this book.

**Parallelization:** Visual generation is embarrassingly parallel — each concept is independent. Batch with rate-limit-aware concurrency (e.g., 10 concurrent calls). Full textbook visuals generated in ~10-15 minutes.

---

## 6. Implementation Phases

### Phase 1: Foundation — Schema, Models, Neo4j Setup
**Scope**: Define the Pydantic models (including `BookSkeleton`), Neo4j schema, and stable ID generation.  
**Files**:
- `src/lecture_pipeline/curriculum/models.py` — `BookSkeleton`, `CurriculumExtractionResult`, all enums, node/edge models
- `src/lecture_pipeline/curriculum/schema.py` — Neo4j constraints, indexes, vector indexes
- `src/lecture_pipeline/curriculum/id_generator.py` — deterministic semantic ID generation
- `config.yaml` — add Neo4j connection settings

**Deliverable**: Can create Neo4j schema, generate stable IDs, serialize/deserialize extraction results and book skeletons.  
**Test**: Round-trip serialization, ID stability across runs, schema initialization.

### Phase 2: Book Skeleton Extraction (Stage 3)
**Scope**: Build the BookSkeleton extractor — the single LLM call that captures the entire book's structure.  
**Files**:
- `src/lecture_pipeline/curriculum/skeleton_extractor.py` — `BookSkeletonExtractor`
- `src/lecture_pipeline/curriculum/prompts.py` — skeleton extraction prompt

**Deliverable**: Feed a full textbook PDF → get a `BookSkeleton` with chapter summaries, cross-chapter prerequisites, unit groupings, and teaching order.  
**Test**: Process HC Verma. Verify: all chapters detected, cross-chapter prerequisites make physical sense (e.g., "Work & Energy" before "SHM"), unit groupings are coherent.

### Phase 3: Deterministic Anchor Extraction
**Scope**: Build the regex-based anchor extractor that runs BEFORE the LLM. Extracts section numbers, equation patterns, figure references, example references from raw PDF text. No LLM involved — pure Python.  
**Files**:
- `src/lecture_pipeline/curriculum/anchors/anchor_extractor.py` — `DeterministicAnchorExtractor`
- `src/lecture_pipeline/curriculum/anchors/models.py` — `ExtractionAnchors`, `SectionAnchor`

**Deliverable**: Feed raw chapter text → get anchors: all section numbers (12.1, 12.1.3), all figure refs, all example refs, all equation patterns.  
**Test**: Process SHM chapter text. Verify: all section headings found, all "Figure X.Y" refs found, all "Example X.Y" refs found. Compare against manual count.

### Phase 4: Book-Aware Chapter Extraction (Stage 4)
**Scope**: Replace `GraphBuilder` with book-aware two-pass extraction. Uses BookSkeleton (Phase 2) + anchors (Phase 3) as inputs.  
**Files**:
- `src/lecture_pipeline/curriculum/chapter_extractor.py` — `ChapterExtractor` (Pass A: structure, Pass B: content)
- `src/lecture_pipeline/curriculum/prompts.py` — chapter extraction prompts (both passes, includes anchors as checklist)

**Deliverable**: Extract 50-100 typed, fine-grained concepts from a 15-page chapter. Section number anchors passed to LLM as extraction floor. Source text preserved. Cross-chapter edges present.  
**Test**: Process SHM chapter WITH book skeleton + anchors. Verify: every section anchor has ≥1 node, all ConceptTypes present, source_text non-empty, cross-chapter PREREQUISITE edges exist.

### Phase 5: Structural Validation + Completeness Checks (Stage 5)
**Scope**: Deterministic validation including completeness verification against anchors and self-correcting gap-fill loop.  
**Files**:
- `src/lecture_pipeline/curriculum/validation/structural.py` — `StructuralValidator` (all checks including circular deps + completeness)
- `src/lecture_pipeline/curriculum/validation/gap_filler.py` — gap-filling sub-agent (targeted LLM call for missing items)

**Deliverable**: Catches all structural issues. Completeness verification compares extraction against anchors. Gap-filler re-extracts missing sections/figures/examples. Self-correcting loop (max 2 retries).  
**Test**: 
- Feed deliberately malformed extractions → verify all issues caught.
- Feed extraction with 2 sections deliberately removed → verify gap-filler recovers them.

### Phase 6: Entity Resolution (Chunk Merging)
**Scope**: Within-chapter chunk merging for large chapters. Deterministic hash-based deduplication.  
**Files**:
- `src/lecture_pipeline/curriculum/merge/entity_resolver.py` — hash-based concept identity
- `src/lecture_pipeline/curriculum/merge/extraction_merger.py` — merge chunk results within a chapter

**Deliverable**: Process a 40-page chapter in chunks, merge without duplicates or disconnected clusters.  
**Test**: Process same chapter as 1 chunk and as 3 chunks. Verify merged graph has <5% node difference.

### Phase 7: Book Unification (Stage 6)
**Scope**: Merge all chapter extractions into one unified book graph. Resolve cross-chapter references to real UIDs. Build Subject→Unit→Chapter hierarchy. Assign global teaching order.  
**Files**:
- `src/lecture_pipeline/curriculum/unification/book_unifier.py` — merge all chapters into one result
- `src/lecture_pipeline/curriculum/unification/reference_resolver.py` — resolve `"Chapter 5::ConceptName"` → real UIDs
- `src/lecture_pipeline/curriculum/unification/hierarchy_builder.py` — create Subject→Unit→Chapter→Concept→Detail tree
- `src/lecture_pipeline/curriculum/unification/shared_concept_detector.py` — embedding similarity for cross-chapter shared concepts

**Deliverable**: One unified `CurriculumExtractionResult` with scope="book". All cross-chapter edges resolved to real UIDs. Subject/Unit hierarchy built. global_teaching_order assigned.  
**Test**: Process 3 chapters. Verify cross-chapter edges resolved to real UIDs. Verify Subject and Unit nodes exist. Verify global_teaching_order is monotonically increasing across chapters.

### Phase 8: Neo4j Ingestion (Stage 8)
**Scope**: Write the unified book extraction result to Neo4j.  
**Files**:
- `src/lecture_pipeline/curriculum/ingestion/cypher_generator.py` — deterministic Cypher from extraction result
- `src/lecture_pipeline/curriculum/ingestion/neo4j_writer.py` — execute Cypher, handle MERGE idempotency
- `src/lecture_pipeline/curriculum/ingestion/embedding_generator.py` — generate and store vector embeddings

**Deliverable**: Full book graph in Neo4j with constraints, indexes, and vector embeddings. Re-runnable (MERGE = upsert).  
**Test**: Ingest full book. Query concepts via Cypher and vector search. Traverse cross-chapter edges. Re-ingest — verify no duplicates.

### Phase 9: Salience Scoring (Stage 7)
**Scope**: Compute static and structural salience for all concept nodes in the unified graph.  
**Files**:
- `src/lecture_pipeline/curriculum/salience/static_scorer.py` — rule-based scoring by concept type
- `src/lecture_pipeline/curriculum/salience/pagerank_scorer.py` — structural scoring via PageRank on full book graph
- `src/lecture_pipeline/curriculum/salience/salience_service.py` — orchestrator (α·static + β·structural)

**Deliverable**: Every concept node has `salience_static`, `salience_structural`, and `salience_total`. PageRank runs on the FULL book graph (not per-chapter), so cross-chapter dependencies influence structural scores.  
**Test**: FORMULA/DEFINITION nodes score higher than EXAMPLE/ANALOGY. Foundational concepts referenced by many chapters (e.g., "Newton's Laws") have highest structural salience.

### Phase 10: Semantic Validation (Stage 5, Layer 2)
**Scope**: LLM-based validation of extraction quality on a sample of nodes.  
**Files**:
- `src/lecture_pipeline/curriculum/validation/semantic.py` — `SemanticValidator`

**Deliverable**: Spot-check ~10% of nodes (all FORMULA + random sample). Flag factual issues, wrong relationships, missing concepts.  
**Test**: Inject a deliberately wrong formula into an extraction result. Verify semantic validator catches it.

### Phase 11: Pipeline Orchestrator & CLI
**Scope**: Wire everything together. One command: `ingest-book textbook.pdf --subject physics`.  
**Files**:
- `src/lecture_pipeline/pipeline.py` — rewritten orchestrator: PDF → skeleton → anchors → chapters → validate → gap-fill → merge → unify → salience → ingest
- `src/lecture_pipeline/cli.py` — new commands: `ingest-book`, `validate`, `query`, `stats`

**Deliverable**: End-to-end: feed PDF, get full curriculum graph in Neo4j.  
**Test**: `ingest-book hcverma.pdf --subject physics` produces a complete, queryable, cross-linked curriculum graph.

### Phase 12: Visual Pre-Generation (Stage 9)
**Scope**: For every concept with a `visual_hint`, generate a DiagramSpec offline and store in Neo4j.  
**Files**:
- `src/lecture_pipeline/curriculum/visuals/visual_generator.py` — orchestrator: concept → DiagramSpec via Claude
- `src/lecture_pipeline/curriculum/visuals/spec_validator.py` — validate generated DiagramSpec against schema
- `src/lecture_pipeline/curriculum/visuals/neo4j_visual_writer.py` — store (:Visual) nodes with HAS_VISUAL edges
- Reuse `design_agent/backend/prompts.py` system prompt for DiagramSpec generation (same format, same rules)

**Deliverable**: Every concept with a visual_hint has a pre-generated DiagramSpec stored in Neo4j. Teaching agent retrieves visuals in 5-15ms instead of 10-15 seconds.  
**Test**: 
- Generate visual for "Energy in SHM" concept. Verify valid DiagramSpec with SVG elements and KaTeX.
- Load visual from Neo4j via concept UID. Verify renders correctly in design_agent frontend.
- Benchmark: Neo4j retrieval < 20ms. Compare against design_agent live generation (10-15s).
- Re-generate same concept — verify MERGE idempotency (no duplicate Visual nodes).

### Phase 13: Cleanup & Migration
**Scope**: Remove dead code, migrate from Poetry to uv.  
**Files**:
- Delete `src/lecture_pipeline/lecture/` (script_generator.py, graph_generator.py)
- Delete `src/lecture_pipeline/graph/` (old builder.py, models.py, serializer.py)
- Migrate `pyproject.toml` from Poetry to uv
- Add `neo4j` driver dependency

**Deliverable**: Clean, single-tool codebase with no dead code.

---

## 7. Runtime Graph Evolution (Not Built Here — Defined for Context)

These services operate on the curriculum graph at teaching runtime. They are NOT part of the pre-compute pipeline but share the same Neo4j schema:

### 7.1 Hebbian Learning
- Track which concepts are co-activated during teaching sessions
- When co-activation count exceeds threshold, create `CO_ACTIVATED_WITH` edge
- Edges strengthen with use, decay over time
- **Trigger**: Teaching agent retrieves multiple concepts to answer a student question

### 7.2 Dynamic Salience
- Track retrieval frequency and recency per concept
- Update `salience_dynamic` based on access patterns
- Recompute `salience_total` = α·static + β·structural + γ·dynamic
- **Trigger**: Every concept retrieval by the teaching agent

### 7.3 Consolidation
- Periodically cluster recent teaching interactions
- Generate cross-session insights ("Students in Class 10B consistently struggle with Phase Constant")
- Archive low-salience stale data
- **Trigger**: Scheduled background job (e.g., nightly)

### 7.4 Dashboard State (Ephemeral)
- Per-session graph of board elements with spatial positions
- Edges to curriculum concepts: `ILLUSTRATES`, `REPRESENTS`
- In-memory hot cache for zero-latency agent reads, async sync to Neo4j
- Archived (compressed log) after session; hot state destroyed
- **Trigger**: Every visual change on the board

### 7.5 Student Knowledge Graph
- Per-student persistent graph
- Edges to curriculum concepts: `MASTERED`, `STRUGGLING`, `NOT_SEEN`, `HAS_MISCONCEPTION`
- Learning pattern profile (visual learner, needs analogies, etc.)
- **Trigger**: Every student interaction during teaching

---

## 8. Migration Path from Current Pipeline

The existing `data_pre_compute` has working PDF parsing and LLM integration. We keep those and replace the graph layer:

| Current Module | Action |
|---|---|
| `pdf/parser.py` | **Keep** — PyMuPDF extraction works fine |
| `pdf/toc.py` | **Keep** — Chapter detection works fine |
| `llm/base.py`, `anthropic_provider.py`, `openai_provider.py`, `factory.py` | **Keep** — LLM abstraction is clean |
| `config.py` | **Extend** — add Neo4j settings, salience weights |
| `graph/builder.py` | **Replace** → `curriculum/extractor.py` (two-pass, fine-grained) |
| `graph/models.py` | **Replace** → `curriculum/models.py` (typed, multi-resolution) |
| `graph/serializer.py` | **Replace** → `curriculum/ingestion/` (Neo4j, not JSON) |
| `lecture/script_generator.py` | **Delete** |
| `lecture/graph_generator.py` | **Delete** |
| `pipeline.py` | **Rewrite** — new stages, new flow |
| `cli.py` | **Rewrite** — new commands |
| `test.py` | **Rewrite** — test against Neo4j |
| `visualize.py` | **Keep/adapt** — point at Neo4j instead of JSON files |

### New Module Structure

```
src/lecture_pipeline/
├── cli.py                          # Updated CLI
├── config.py                       # Extended config
├── pipeline.py                     # New orchestrator
├── pdf/                            # KEPT AS-IS
│   ├── parser.py
│   └── toc.py
├── llm/                            # KEPT AS-IS
│   ├── base.py
│   ├── anthropic_provider.py
│   ├── openai_provider.py
│   └── factory.py
└── curriculum/                     # NEW — everything below
    ├── models.py                   # CurriculumExtractionResult, BookSkeleton, enums
    ├── id_generator.py             # Stable semantic ID generation
    ├── schema.py                   # Neo4j schema initialization
    ├── skeleton_extractor.py       # BookSkeleton extraction (Phase 2)
    ├── chapter_extractor.py        # Two-pass concept extraction (Phase 4)
    ├── prompts.py                  # All LLM prompts
    ├── anchors/                    # Deterministic pre-LLM extraction (Phase 3)
    │   ├── anchor_extractor.py     # Regex-based section/figure/example finder
    │   └── models.py               # ExtractionAnchors, SectionAnchor
    ├── validation/
    │   ├── structural.py           # Deterministic validation + completeness (Phase 5)
    │   ├── gap_filler.py           # Targeted gap-filling sub-agent (Phase 5)
    │   └── semantic.py             # LLM-based spot-check validation (Phase 10)
    ├── merge/
    │   ├── entity_resolver.py      # Hash-based concept identity (Phase 6)
    │   └── extraction_merger.py    # Cross-chunk merge (Phase 6)
    ├── unification/                # Book-level merge (Phase 7)
    │   ├── book_unifier.py         # Merge all chapters into one result
    │   ├── reference_resolver.py   # "Chapter 5::ConceptName" → real UIDs
    │   ├── hierarchy_builder.py    # Subject→Unit→Chapter→Concept→Detail
    │   └── shared_concept_detector.py  # Embedding similarity cross-chapter
    ├── ingestion/                  # Neo4j write (Phase 8)
    │   ├── cypher_generator.py     # ExtractionResult → Cypher
    │   ├── neo4j_writer.py         # Execute Cypher statements
    │   └── embedding_generator.py  # Vector embeddings
    ├── salience/                   # Importance scoring (Phase 9)
    │   ├── static_scorer.py        # Rule-based scoring
    │   ├── pagerank_scorer.py      # Structural scoring
    │   └── salience_service.py     # Orchestrator
    └── visuals/                    # Diagram pre-generation (Phase 12)
        ├── visual_generator.py     # Concept → DiagramSpec via Claude
        ├── spec_validator.py       # Validate DiagramSpec schema
        └── neo4j_visual_writer.py  # Store (:Visual) nodes
```

---

## 9. Success Criteria

After full implementation:

1. **Whole-book input**: Pipeline takes one PDF → produces one unified curriculum graph. Not chapter-by-chapter with post-hoc linking.
2. **Book-aware extraction**: Every chapter extraction receives the BookSkeleton as context. Cross-chapter edges are first-class extraction outputs, not afterthoughts.
3. **Teaching order preserved**: `global_teaching_order` field on every node reflects the book author's intended sequence. The agent can traverse the entire textbook in order.
4. **Granularity**: 50-100 concept nodes per 15-page chapter (vs 13 today), ≥3 nodes/page. Every named equation has a FORMULA node. Every figure reference has a VISUALIZATION node. Every worked example has an EXAMPLE node. Full book produces 1000-3000 nodes depending on length.
5. **Source text**: Every node has non-empty `source_text` with exact page range (per-concept, not per-chapter).
6. **Typed concepts**: Every node has a `concept_type` from the enum. Teaching agent knows if it's a FORMULA, DEFINITION, EXAMPLE, etc.
7. **Validation**: Structural validation catches 100% of referential integrity issues. Semantic validation flags >80% of factual errors on sampled nodes.
8. **Chunk merging**: Processing a chapter as 1 chunk vs 3 chunks produces graphs with <5% node difference.
9. **Cross-chapter**: Full book graph has cross-chapter PREREQUISITE, LEADS_TO, CROSS_REFERENCES, and SHARED_FOUNDATION edges. No chapter is an island.
10. **Full hierarchy**: Subject→Unit→Chapter→Concept→Detail with CONTAINS and SUMMARIZES edges at every level. Fractal resolution navigation works.
11. **Salience**: FORMULA/DEFINITION nodes consistently score higher than EXAMPLE/ANALOGY. Foundational cross-chapter concepts (e.g., "Newton's Laws") have highest structural salience via PageRank on full book graph.
12. **Neo4j**: Full graph queryable via Cypher and vector search. Re-ingestion produces no duplicates (MERGE idempotency).
13. **Stable IDs**: Re-processing same book produces same UIDs. Dashboard and student graphs can safely reference them.
14. **No pre-baked lectures**: Pipeline produces no markdown lecture files. The graph IS the curriculum.
15. **Integration-ready**: Cross-graph edge types (ILLUSTRATES, MASTERED, etc.) defined in schema. Dashboard and student graphs can plug in without curriculum graph changes.
16. **Visual hint coverage**: ≥80% of concept nodes have visual_hint. 100% of FORMULA, DERIVATION, EXAMPLE, EXPERIMENT, and VISUALIZATION nodes have visual_hint (mandatory).
17. **Visual pre-generation**: Every node with visual_hint has a pre-generated DiagramSpec in Neo4j. Retrieval latency < 20ms vs 10-15 seconds for live generation. Combined with anticipation (Tiers 2-3), ~95% of teaching visuals have zero perceived latency.
18. **Extraction completeness**: 100% of numbered textbook sections have at least one concept node (the extraction floor). ≥70% of equations have FORMULA nodes. 100% of figure references have VISUALIZATION nodes. ≥80% of worked examples have EXAMPLE nodes. Verified by deterministic anchor extraction before the LLM runs.
19. **Section number traceability**: Every concept node carries a `section_number` linking it back to the textbook's numbering system. Enables teachers and QA to verify "is section 12.1.3 covered?" with a simple query.
