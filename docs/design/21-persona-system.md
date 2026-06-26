# Design 21 — Persona System & Layered Ingestion

**Doc ID:** `21` · **Status:** PR-1, PR-2, PR-4 & PR-6 done · PR-3/5 planned  
**Related:** [24-quality-evaluation-engine.md](./24-quality-evaluation-engine.md)

Single source of truth for teacher personas, spine/variant ingest, and topic → chapter → book layering.

---

## 1. What we're building

Multiple **teacher personas** (default, Feynman, finance_teacher, …) over the **same curriculum spine**:

- Same facts: `book_examples`, formulas, prereqs, shared diagrams
- Different voice, extended examples, choreography, audio
- Student picks persona at playback; Ask Feynman uses the same persona

```
BEFORE                              AFTER
──────                              ─────
Full ingest × each persona          Spine once (phases 1–7)
Duplicate PDF + diagrams            Variant per persona (phases 7a–12)
?lecture=physics_feynman:*          ?lecture=physics:*&persona=feynman
```

**Cost target:** 2nd persona ≈ **22%** of full ingest (not 100%).

---

## 2. Three tiers

| Tier | Phases | Mutable by persona? |
|------|--------|---------------------|
| **Spine** | 1–7 → `SpineCheckpoint` | No |
| **Variant** | 7a–12 → lesson, narration, audio, manifest | Yes |
| **Runtime** | preview API, frontend, LiveKit | Read-only |

### Shared vs per-persona

| Shared (spine) | Per persona (variant) |
|----------------|----------------------|
| `book_examples`, `setup_facts` | `style_block`, `example_policy` |
| Diagram `render_data` (default) | Lesson choreography, extended examples |
| Questions, prereqs | `narration_text`, audio, TTS voice |
| Embeddings, diagram PNGs | `persona_overlay` diagrams (~10%) |

**Rules:** Persona changes *how* things are taught, never textbook facts. `setup_facts` on book examples are immutable.

---

## 3. Layered ingest (topic → chapter → book)

**Topic is the atomic unit.** Chapter = ordered topic list. Book = ordered chapter list.

| You want… | Scope | Pay for |
|-----------|-------|---------|
| One section | **1 topic** | 1 topic spine + variant |
| One chapter PDF | **1 chapter** (N topics) | N topics + chapter arc |
| Full textbook | **1 book** | all chapters |

```bash
# Book
lecture-pipeline-v2 ingest-spine book.pdf --subject physics
lecture-pipeline-v2 generate-variant --checkpoint ... --persona feynman

# Chapter (today)
lecture-pipeline-v2 ingest-spine book.pdf --subject physics --chapter "Fluid Mechanics"

# Single-topic PDF
lecture-pipeline-v2 ingest-spine section.pdf --subject finance \
  --single-chapter "Simple Interest"

# Topic scope (planned — PR-23)
lecture-pipeline-v2 ingest-spine ... --topics topic:physics:relativity:15_3
lecture-pipeline-v2 generate-variant --checkpoint ... --persona feynman --topics ...
```

**Merge rule:** partial ingests patch by `topic_id`; siblings untouched.

---

## 4. `TeacherPersona` (YAML)

Location: `data_pre_compute_v2/personas/` · Loader: `feynman_teaching_kernel`

```yaml
persona_id: finance_teacher
extends: default
persona_version: 1
style_block: |          # voice + pedagogical moves
  ...
pedagogical_moves:      # optional bullet list → planner prompt
  - "Timeline before symbols"
example_policy:
  domains: [savings_account, loan]
  fun_fact_rate: low
voice_profile:
  tts_voice: null
diagram_policy: shared | overlay_allowed
figure_preferences: reproduce_named_figures   # optional overlay diagrams
```

**Domain overlay:** `personas/domains/{subject}.yaml` merges onto persona when `--subject` matches (e.g. finance).

---

## 5. Rendering

Frontend is **persona-agnostic**. It replays a **`ChapterPayload`** for the chosen variant:

```
variant ingest → events[] + diagrams{} + board_snapshots[]
       → preview_server (?persona=)
       → useExtractionPlayback → SplitBoard
```

| Layer | In payload |
|-------|------------|
| Timeline | `events[]` (show_diagram, focus, audio) |
| Assets | `diagrams[id].spec` (spine + overlays) |
| Layout | `placement`, `board_snapshots[]` |

---

## 6. Data stores

```
Neo4j
  CurriculumChapter → Topic, Diagram (shared), LectureVariant (persona_id, manifest)

Artifacts
  artifacts/spine/extraction_{subject}.json
  artifacts/audio/variant_{chapter}__persona_{id}/
  out/{run}/extraction.json + quality_report.json
```

`variant_id` = `{chapter_id}::persona:{persona_id}`

---

## 7. Runtime flow

1. `LectureHomeScreen` → chapter + persona chip  
2. `GET /lecture-api/chapter/{id}?persona=feynman`  
3. `LectureViewer` → `useExtractionPlayback` → `SplitBoard`  
4. Ask Feynman → `persona_id` in session → doubt planner gets `style_block`

---

## 8. Implementation status

| PR | Deliverable | Status |
|----|-------------|--------|
| **1** | `TeacherPersona`, `personas/*.yaml`, `--persona` | **Done** |
| **2** | `ingest-spine`, `generate-variant`, spine checkpoint | **Done** |
| **3** | Phase cache + idempotency | Planned |
| **4** | Neo4j `LectureVariant` + `?persona=` API | **Done** |
| **5** | Parallel topic gate, batch CLI | Partial (`generate-variants`) |
| **6** | Frontend picker + doubt `persona_id` | **Done** |
| **1b** | Book weaver voice + overlay diagrams | Planned |
| **7** | `render_profile` theme (optional) | Planned |
| **23** | `--topics` scope, `TopicSpine` checkpoints | Planned |

### Smoke test

```bash
cd data_pre_compute_v2
python -m lecture_pipeline_v2.cli ingest-spine fixtures/finance/simple_interest.pdf \
  --subject finance --single-chapter "Simple Interest" \
  -o artifacts/spine/extraction_finance.json

python -m lecture_pipeline_v2.cli generate-variant \
  --checkpoint artifacts/spine/extraction_finance.json \
  --persona finance_teacher --skip-tts --skip-neo4j --skip-embeddings \
  -o out/finance-teacher/extraction.json

# All personas in one command
python -m lecture_pipeline_v2.cli generate-variants \
  --checkpoint artifacts/spine/extraction_finance.json \
  --personas default,feynman,finance_teacher \
  --skip-tts --skip-neo4j --skip-embeddings \
  -o out/
```

Quality: auto `quality_report.json` · compare personas via `compare-quality` ([doc 24](./24-quality-evaluation-engine.md)).

---

## 9. Acceptance (full system)

- [x] P1: `--persona` loads YAML into planner
- [x] P2: `generate-variant` — no PDF parse in logs
- [ ] P3: identical re-run — zero LLM calls
- [x] P4: one Topic set, two `LectureVariant` nodes in Neo4j
- [ ] P5: parallel faster than sequential (5+ topics)
- [x] P6: E2E persona pick → play → Ask Feynman same voice

---

## 10. Out of scope (later)

Per-student adaptation, mid-lecture persona switch, substituting book examples, persona marketplace, S3 artifacts.

---

## 11. References

- `data_pre_compute_v2/personas/` — persona YAML files  
- `data_pre_compute_v2/fixtures/finance/simple_interest.txt` — demo topic source  
- Docs 17, 19 — lesson quality bar  
- [24-quality-evaluation-engine.md](./24-quality-evaluation-engine.md) — QEE / persona A/B
