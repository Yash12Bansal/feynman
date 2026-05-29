# 05 — Feynman Teaching Kernel (`feynman_teaching_kernel/`)

**Branch:** `feat/unify_boardstate` · **Last verified:** 2026-05-28

## TL;DR

The teaching kernel is a tiny, hand-curated Python package (~800 LoC across 6 files) that holds the **canonical planning contract** shared between the live agent and the precompute pipeline. Both consumers install it as an **editable path dependency** to the same source tree, so any change ships to both at once.

Public surface:

```python
from feynman_teaching_kernel import (
    # Data models (Pydantic)
    ConceptTeachingPlan,
    TeachingBeat,
    VisualBeatAction,
    ChecklistItem,
    # Planning functions
    plan_concept,
    plan_doubt,
    DEFAULT_PLANNING_MODEL,
    # Prompt + style
    PLANNING_SYSTEM_PROMPT,
    BANNED_OPENERS,
    # Formatter
    format_plan_for_prompt,
)
```

These ten symbols are everything. Live teaching and precomputed teaching pass through them, and the **Feynman arc validator** (`hook → big_picture → first_principles` mandate enforced on the model itself) guarantees both paths produce structurally identical plans.

---

## Why a shared kernel?

Without this kernel, drift is inevitable. The precompute pipeline would slowly diverge from the live agent in subtle ways — different beat structures, different visual selection logic, different prompt phrasing — and a student bouncing between a recorded lesson and a live doubt would feel the seam.

By **importing the same `plan_concept()` from a single source**, both consumers ask the LLM in the same way, validate against the same schema, and apply the same Feynman-arc constraint. The cost is one extra path dependency; the value is structural unity across modes.

Design context: `docs/design/17-precompute-lecture-pipeline-overhaul.md` §3.3 spells out the rationale.

---

## Repository layout

```
feynman_teaching_kernel/
├── src/feynman_teaching_kernel/
│   ├── __init__.py            (public API — 10 exports)
│   ├── models.py              (VisualBeatAction, TeachingBeat, ChecklistItem, ConceptTeachingPlan)
│   ├── planner.py             (plan_concept, plan_doubt, _build_planning_context; async Claude calls)
│   ├── prompts.py             (PLANNING_SYSTEM_PROMPT — ~240 lines)
│   ├── format.py              (format_plan_for_prompt — markdown serialization)
│   ├── style_guide.py         (PRONUNCIATION_RULES + BANNED_OPENERS)
│   └── py.typed               (PEP 561 marker; enables type hints in consumers)
├── tests/
│   ├── __init__.py
│   └── test_models.py         (9 smoke tests — round-trip, defaults, arc, allowed_visual_tools)
├── pyproject.toml             (3 runtime deps: anthropic, pydantic, structlog)
└── README.md
```

Python 3.11+. Build backend: hatchling. Installed editable into both consumers.

---

## 1. Data models — `models.py`

All models are Pydantic v2. Every `Field(description=...)` string is the LLM tool schema contract — these descriptions are what Claude sees when filling the structured output.

### `VisualBeatAction`

A single visual tool call planned for a teaching beat.

```python
class VisualBeatAction(BaseModel):
    tool: str = Field(description=(
        "Which visual tool to use. Split-board model:\n"
        "NOTEBOOK panel (right, sequential writing column): write_section, "
        "write_equation, write_step, write_text, write_answer, strikethrough, "
        "new_page, show_equation, step_equation, show_graph, show_text.\n"
        "SLIDE panel (left, one diagram at a time): draw_scene, "
        "draw_design_diagram, modify_design_diagram, draw_diagram.\n"
        "REFERENCE (targets an existing element): highlight_diagram_part, "
        "highlight_walk, annotate, clear_cluster, scroll_board."
    ))
    description: str = Field(description="What this visual shows — used as the tool's main content parameter")
    zone:        str = Field(default="", description="Board zone for SLIDE-panel placement only ...")
    timing:      str = Field(default="visual_first", description='"visual_first", "after_speech", or "term_sync"')
    builds_on:   str = Field(default="", description="If this visual extends/modifies a previous one, describe which and how")
```

The tool names listed in the description are the **exact** tool names the backend agent module exposes via `@function_tool`. The LLM uses them as guidance when picking `tool` for a beat.

### `TeachingBeat`

One coordinated moment of teaching — the atomic unit of a lesson plan.

```python
class TeachingBeat(BaseModel):
    beat_type:               str = Field(description=(
        "Type of teaching moment. One of: hook, big_picture, first_principles, "
        "bridge, visual_build, explain, derive, ask, misconception, example, "
        "summarize, transition. The first three beats of every concept plan must "
        "be hook → big_picture → first_principles (mandatory Feynman arc — see system prompt)."
    ))
    speech_guidance:         str = Field(description=(
        "What to say during this beat. NOT a verbatim script — guidance for the "
        "teaching agent on content, tone, and approach. 2-4 sentences."
    ))
    visual:                  VisualBeatAction | None = Field(default=None, description="Visual to show during this beat. None for speech-only beats.")
    target_duration_seconds: int = Field(default=30, description="Approximate duration for this beat in seconds")
    student_cue:             str = Field(default="", description="What to watch for from students (confusion signals, questions)")

    # Book-coverage USP (2026-05-27). Set ONLY when beat_type == "example".
    example_source:          Literal["book", "extended"] | None = Field(default=None, description=(
        "`book` = faithful render of a textbook example (numbers + relationships "
        "preserved). `extended` = LLM-invented real-world example to strengthen "
        "coverage. None = not an example beat."
    ))
    book_example_ref:        int | None = Field(default=None, description=(
        "Index into Topic.book_examples — populated when example_source='book' "
        "so the writer can look up the verbatim text + setup_facts. None for non-book beats."
    ))
```

**The two example fields** (`example_source`, `book_example_ref`) are the "book-coverage USP" hook. When the planner picks an `example` beat with `example_source="book"`, the precompute's `BeatNarrationWriter` knows to render the example **faithfully** (preserving numbers and relationships) rather than invent its own. This is what makes the precomputed lecture grounded in the textbook rather than drifting into "AI-invented" examples.

### `ChecklistItem`

One requirement the agent must satisfy before `resolve_doubt` is allowed.

```python
class ChecklistItem(BaseModel):
    """
    Items auto-tick when a tool listed in `auto_satisfied_by` is invoked, when
    a keyword in `keywords` appears in the agent's emitted voice, or via the
    explicit `mark_doubt_step_complete(step_index)` tool when the agent knows
    it has addressed the requirement but no auto-trigger fired.
    """
    description:        str = Field(..., min_length=1, max_length=240)
    status:             Literal["pending", "done"] = "pending"
    auto_satisfied_by:  list[str] = Field(default_factory=list)
    keywords:           list[str] = Field(default_factory=list)
```

The `DoubtOrchestrator` (`backend/src/feynman/agent/doubt_orchestrator.py`) is what enforces this — it ticks items on each `on_tool_invoked()` and `on_voice_emitted()` event, and gates `resolve_doubt` on every item being `done`.

### `ConceptTeachingPlan`

The whole plan for one concept.

```python
class ConceptTeachingPlan(BaseModel):
    concept_title:           str
    concept_index:           int                  # -1 signals a doubt plan (bypasses arc validator)

    # Pedagogical strategy
    opening_hook:            str = Field(description="Specific attention-grabbing opening — an analogy, question, or demonstration")
    core_analogy:            str = Field(description="The primary analogy or mental model to use throughout this concept")
    prerequisite_bridge:     str = Field(description="How to connect this concept to what was just taught — 1-2 sentences")

    # Ordered beats
    beats: list[TeachingBeat] = Field(description="Ordered sequence of teaching moments. As many as needed — but every beat must earn its place.")

    # Board layout
    board_pattern:           str = Field(description=(
        'Which teaching scenario to use. One of: "concept_intro", "derivation", '
        '"comparison", "problem_solving", "single_focus", "free_form". These map '
        "to reserved slot layouts on the slide + an expected notebook flow."
    ))
    visual_narrative:        str = Field(description="2-3 sentence description of the visual arc — how slide and notebook build on each other across beats")

    # Misconception defense
    likely_misconceptions:   list[str] = Field(default_factory=list, description="Common student misconceptions to watch for and pre-empt (1-3 items)")
    misconception_responses: list[str] = Field(default_factory=list, description="How to address each misconception if it surfaces (parallel to likely_misconceptions)")

    # Understanding checkpoints
    check_questions:         list[str] = Field(default_factory=list, description="Questions to ask students to verify understanding (1-3 items)")
    expected_answers:        list[str] = Field(default_factory=list, description="Expected correct answers (parallel to check_questions)")

    # Transition
    transition_to_next:      str = Field(default="", description="How to naturally bridge to the next concept — 1-2 sentences")

    # Doubt-branch only
    resolution_checklist:    list[ChecklistItem] = Field(default_factory=list, description=(
        "Doubt-branch only. 2-4 items the agent must touch before resolve_doubt is allowed. "
        "Each item has a description and a list of `auto_satisfied_by` tool names that auto-tick "
        "the item when invoked. Leave empty for non-doubt plans."
    ))

    @model_validator(mode="after")
    def _enforce_arc(self) -> "ConceptTeachingPlan":
        # Doubt plans (concept_index = -1) bypass — they have a 2-3 beat
        # explain/ask/transition structure, not the Feynman arc.
        if self.concept_index < 0:
            return self
        if len(self.beats) < 3:
            raise ValueError(f"ConceptTeachingPlan requires at least 3 beats; got {len(self.beats)}.")
        expected = ("hook", "big_picture", "first_principles")
        actual = tuple(b.beat_type for b in self.beats[:3])
        if actual != expected:
            raise ValueError(f"First three beats must be {expected} in order, got {actual}.")
        return self
```

### The Feynman arc validator (the most important 10 lines)

`_enforce_arc()` is the model's structural backbone. It runs on every plan after Pydantic deserialization. The rule:

- Concept plans (any non-negative `concept_index`) **must** have at least 3 beats whose `beat_type` is exactly `hook → big_picture → first_principles` in that order.
- Doubt plans (signaled by `concept_index = -1`, set inside `plan_doubt()`) bypass the validator entirely — they have a free 2-3 beat structure suited to addressing confusion quickly.

This is the **only structural guarantee** the kernel makes, and it's enough. Once the first three beats are nailed down — start with a hook, give the big picture, ground in first principles — the rest of the plan composes around them. The LLM is constrained to produce this structure or its output is rejected at the kernel boundary.

---

## 2. Planning functions — `planner.py`

Both functions are async, accept a bare `api_key` (no global config), and use **forced Anthropic tool calls** to enforce schema compliance.

### `plan_concept`

```python
DEFAULT_PLANNING_MODEL = "claude-sonnet-4-20250514"

async def plan_concept(
    concept_index:  int,
    curriculum:     Any,                      # CurriculumData
    plan:           Any,                      # LessonPlan
    board_summary:  str = "",
    audit:          Any | None = None,        # SessionAudit (optional)
    prev_plan:      ConceptTeachingPlan | None = None,
    allowed_visual_tools: list[str] | None = None,
    *,
    api_key:        str,
    model:          str = DEFAULT_PLANNING_MODEL,
) -> ConceptTeachingPlan | None:
    """
    Generate a ConceptTeachingPlan for the given concept index.

    `allowed_visual_tools`: when non-None, the LLM is told to restrict
    `visual.tool` for every beat to one of these names. When None (live
    agent default), no constraint is injected — behavior unchanged from
    pre-doc-18. The precompute pipeline passes a restricted list so
    concept-style beats produce diagrams the renderer can actually draw.

    Makes one Anthropic structured output call. Returns None on failure
    (the teaching agent falls back to the current unplanned behavior).
    """
```

Flow:

1. Fetch the concept from `curriculum` at `concept_index`.
2. `_build_planning_context(...)` constructs a rich user message:
   - Concept (name, type, difficulty, summary, source text, visual hint)
   - Prerequisites (what students already know)
   - Next concept (for continuity)
   - Previous plan's context (analogy + transition + last beat) **if `prev_plan` given**
   - Related concepts from the knowledge graph
   - Board state summary (what's drawn)
   - Pre-generated visual indicators
   - If `allowed_visual_tools` is set, inject a constraint clause
3. One Anthropic call:
   ```python
   message = await client.messages.create(
       model=model,
       system=PLANNING_SYSTEM_PROMPT,
       messages=[{"role": "user", "content": user_message}],
       tools=[{
           "name": "create_teaching_plan",
           "input_schema": ConceptTeachingPlan.model_json_schema(),
       }],
       tool_choice={"type": "tool", "name": "create_teaching_plan"},   # forced
       max_tokens=8192,
       temperature=0.7,
   )
   ```
4. Extract the tool call payload, **set `concept_index` and `concept_title` manually** (the LLM doesn't need to fill them), then `ConceptTeachingPlan.model_validate(payload)`. If the arc validator throws, log + return `None`.
5. Return the validated plan.

### `plan_doubt`

```python
async def plan_doubt(
    doubt_description: str,
    parent_concept:    str = "",
    board_summary:     str = "",
    curriculum:        Any | None = None,
    audit:             Any | None = None,
    *,
    api_key:           str,
    model:             str = DEFAULT_PLANNING_MODEL,
) -> ConceptTeachingPlan | None:
    """
    Lighter than concept planning — produces 3-5 focused beats to address
    the confusion and bridge back to the main lesson.
    """
```

The differences from `plan_concept`:

1. The user message focuses on the doubt + parent concept context.
2. Embeds detailed **resolution checklist** instructions explaining what makes a checklist item concrete vs. vague, the controlled vocabulary of `auto_satisfied_by` tool names, how `keywords` enable voice-based auto-tick, and example items.
3. After the LLM returns the plan, **manually set `concept_index = -1`** to signal "doubt plan" so the arc validator bypasses.
4. Validate and return.

Both functions log every call to structlog at `info` level (model, latency, token counts) and optionally record an audit event if `audit` is passed.

---

## 3. System prompt — `prompts.py`

`PLANNING_SYSTEM_PROMPT` is ~240 lines. It teaches the LLM to be an expert **lesson planner**, not a teacher.

### Outline (sections in order)

1. **Role**: expert lesson planner.
2. **Style**: concise, interactive, engaging.
3. **Planning Principles** (8 points): hook first; visual narrative; one idea per beat; ask before telling; misconception pre-emption; incremental visuals (prefer instant `draw_scene` over slow `draw_design_diagram`); concrete before abstract; concept-style beats must have diagrams (except mechanic beats).
4. **MANDATORY FEYNMAN ARC** (strict, non-negotiable):
   - **Beat 1: hook** (10-15s) — question, surprise, concrete moment.
   - **Beat 2: big_picture** (20-30s) — where does this fit in the chapter?
   - **Beat 3: first_principles** (30-60s) — foundational "why."
   - Subsequent beats: any of `bridge / explain / derive / ask / misconception / example / summarize / transition`.
5. **Example**: a worked Pythagorean-theorem arc (6 beats).
6. **Available visual tools**:
   - Notebook (right column): `write_section, write_equation, write_step, write_text, write_answer, strikethrough, new_page, show_equation, step_equation, show_graph, show_text`.
   - Slide (left, one diagram): `draw_scene, draw_design_diagram, modify_design_diagram, draw_diagram`.
   - Reference: `highlight_diagram_part, highlight_walk, annotate, clear_cluster, scroll_board`.
7. **Board layout patterns** (6): `concept_intro, derivation, comparison, problem_solving, single_focus, free_form`.

### The doc-18 constraint, enforced at the prompt level

> For concept-style beats (`hook, big_picture, first_principles, bridge, visual_build, misconception, explain`), `visual.tool` MUST be `draw_design_diagram` or `modify_design_diagram`. Mechanic-style beats (`derive, example, ask, summarize, transition`) may use notebook-only tools without a slide diagram.

This is currently enforced by the prompt only, not by a Pydantic validator on the model. The doc-19 refinement *softened* the kernel-side rewrite of unsupported tools — instead, the planner has freedom to pick text-only when appropriate, guided by `allowed_visual_tools` if the consumer passes one.

---

## 4. Plan formatter — `format.py`

```python
def format_plan_for_prompt(teaching_plan: ConceptTeachingPlan) -> str:
    """
    Format a ConceptTeachingPlan into a prompt section for the teaching agent.
    Replaces the raw key_points + visual_suggestions in build_teaching_prompt().
    """
```

Used by the **live teaching agent** to inject the plan back into the runtime system prompt. The output is markdown like:

```markdown
### Teaching Plan for: Pythagorean Theorem

**Board pattern**: derivation
**Core analogy**: A ladder against a wall
**Bridge from previous**: We just measured triangles; now we'll prove a deep relationship.

**Visual narrative**: Start with the right-triangle scene on the slide ...

**Teaching Beats** — follow this sequence, adapt to student responses:

**Beat 1 — HOOK** (~15s)
  Speech guidance: ...
  Visual: `draw_scene` — A right triangle with sides a, b, c labeled, in zone center-center, timing visual_first
  (Builds on: nothing yet)
  Watch for: ...

...

**Misconceptions to watch for:**
- If student thinks: "Only works for integer sides"
  → Response: ...

**Understanding checks:**
- Ask: "What's the hypotenuse?"
  Expected: "The side opposite the right angle"

**Transition to next**: Now that we have c² = a² + b², let's see why...

**IMPORTANT**: This plan is guidance, not a rigid script. Adapt to student responses.
```

This markdown is concatenated into `TEACHING_SYSTEM_PROMPT` by the live agent's `build_teaching_prompt()` (`backend/src/feynman/agent/tools.py`). Whenever a tool is invoked, the LLM sees this plan in its system prompt and knows what the next beat should be.

---

## 5. Style guide — `style_guide.py`

Two string/list constants, both used by **narration**-side code (precompute beat writer + backend doubt resolution prompts).

### `PRONUNCIATION_RULES`

```
- NUMBERS: "four thousand nineteen", not "4019"
- UNITS:   "kilometers per hour", not "km/h"
- SYMBOLS: "delta v", not "Δv"
- EQUATIONS: "v equals m times a", not "v = ma"
- ABBREVIATIONS: "for example", not "e.g."

Single-letter variables (F, m, a, v, x) are acceptable as-is.
```

Injected into prompts that produce text destined for TTS so the speaker doesn't say "delta v" as "dee-l-t-a v."

### `BANNED_OPENERS`

```python
[
    "Let's", "Let me", "Now,", "So,", "Alright", "Okay", "Great",
    "So basically", "First of all", "In this section", "We're going to",
    "We will", "Today we", "Today, we", "I want to", "I would like to",
    "It's important to note", "Keep in mind", "Remember that",
]
```

Eighteen discouraged sentence starters. Used by:
- The precompute `BeatNarrationWriter` validator (`data_pre_compute_v2/curriculum/beat_narration/writer.py`) — rejects narration whose first sentence matches.
- `ResolutionBeat`'s Pydantic validator (`backend/src/feynman/agent/doubt_resolution/models.py`) — rejects beats whose `narration_text` opens with a banned phrase.

The goal: keep narration conversational, not lecture-y.

---

## 6. Public API — `__init__.py`

```python
from feynman_teaching_kernel.format     import format_plan_for_prompt
from feynman_teaching_kernel.models     import (
    ChecklistItem,
    ConceptTeachingPlan,
    TeachingBeat,
    VisualBeatAction,
)
from feynman_teaching_kernel.planner    import DEFAULT_PLANNING_MODEL, plan_concept, plan_doubt
from feynman_teaching_kernel.prompts    import PLANNING_SYSTEM_PROMPT
from feynman_teaching_kernel.style_guide import BANNED_OPENERS

__all__ = [
    "BANNED_OPENERS",
    "DEFAULT_PLANNING_MODEL",
    "PLANNING_SYSTEM_PROMPT",
    "ChecklistItem",
    "ConceptTeachingPlan",
    "TeachingBeat",
    "VisualBeatAction",
    "format_plan_for_prompt",
    "plan_concept",
    "plan_doubt",
]
```

`PRONUNCIATION_RULES` is *not* re-exported — consumers import it directly via `from feynman_teaching_kernel.style_guide import PRONUNCIATION_RULES`. This is a minor oversight; conceptually it belongs with the public API.

---

## 7. Tests — `tests/test_models.py`

Nine tests, all pass:

1. `test_concept_teaching_plan_round_trips` — JSON serialize/deserialize round-trip.
2. `test_visual_beat_action_defaults_blank` — zone/timing/builds_on defaults.
3. `test_checklist_item_pending_default` — status defaults to `pending`.
4. `test_teaching_beat_visual_optional` — visual can be `None`; target_duration defaults to 30.
5. `test_arc_valid_plan_validates` — `hook → big_picture → first_principles` passes.
6. `test_arc_missing_raises` — fewer than 3 beats → ValidationError.
7. `test_arc_wrong_order_raises` — out-of-order arc → ValidationError.
8. `test_arc_doubt_plan_exempt` — `concept_index = -1` bypasses validator.
9. `test_plan_concept_injects_allowed_visual_tools` — async; verifies the `allowed_visual_tools` constraint appears in the prompt when passed and is absent when `None`.

These are smoke tests for the public contract. Detailed planning tests live in the consumer codebases.

---

## 8. Dependencies — `pyproject.toml`

```toml
[project]
name = "feynman-teaching-kernel"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "anthropic>=0.40.0",     # AsyncAnthropic for LLM calls
    "pydantic>=2.5.0",       # Structured models + validators
    "structlog>=24.0.0",     # Logging
]

[project.optional-dependencies]
dev = ["pytest>=8.0.0", "pytest-asyncio>=0.23.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/feynman_teaching_kernel"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

Three runtime deps. Lower bounds only, no upper pins — keeps it neighborly when consumers update.

---

## 9. Consumers — call sites

### Backend (`backend/src/feynman/`)

| File | Line | Imports | Use |
|---|---|---|---|
| `agent/prompts.py` | 11 | `format_plan_for_prompt` | Serializes the active concept plan into the system prompt at runtime. |
| `agent/tools.py` | 2184 | `plan_concept` | Called from `advance_concept()` to async-plan the next concept in the background. |
| `agent/tools.py` | 2308 | `plan_doubt` | Called from `handle_student_doubt()` to generate a focused 2-3 beat plan with `resolution_checklist`. |
| `agent/state_machine.py` | 25 | `ChecklistItem` | Type hint on `BranchContext.checklist`. |
| `agent/doubt_orchestrator.py` | 35 | `ChecklistItem` | Tracks completion and gates `resolve_doubt`. |
| `agent/teaching_context.py` | 9 | `ConceptTeachingPlan` | Stored on `concept_plans: dict[int, ConceptTeachingPlan]`. |
| `agent/doubt_resolution/models.py` | 18 | `BANNED_OPENERS` | Validator on `ResolutionBeat.narration_text`. |
| `agent/doubt_resolution/prompts.py` | 14 | `BANNED_OPENERS`, `PRONUNCIATION_RULES` | Injected into the resolution beat narration prompt. |
| `livekit/worker.py` | 17 | `plan_concept` | Async planning fired from `on_enter`. |

### Precompute pipeline (`data_pre_compute_v2/src/lecture_pipeline_v2/`)

| File | Line | Imports | Use |
|---|---|---|---|
| `curriculum/prompts.py` | 15 | `PRONUNCIATION_RULES` | Beat narration prompts. |
| `curriculum/models.py` | 19, 858 | `ConceptTeachingPlan` (forward ref) | Type hint on `Chapter.concept_plans`. |
| `curriculum/lecture_plan/concept_planner.py` | 18 | `ConceptTeachingPlan, plan_concept` | The single call site that drives precompute planning. Passes `allowed_visual_tools` whitelist. |
| `curriculum/lecture_plan/example_allocator.py` | 24 | `ConceptTeachingPlan, TeachingBeat` | Allocates `Topic.book_examples` to beats, mutates `beat.example_source = "book"` and `beat.book_example_ref = i`. |
| `curriculum/length_enforcer/enforcer.py` | 23 | `ConceptTeachingPlan, TeachingBeat` | Trims beats to fit duration budgets. |
| `curriculum/beat_narration/writer.py` | 27 | `ConceptTeachingPlan, TeachingBeat` | Writes detailed narration per beat; branches on `example_source` for book-faithful vs. extended. |
| `curriculum/beat_narration/prompts.py` | 13-14 | `ConceptTeachingPlan, TeachingBeat, PRONUNCIATION_RULES` | Prompt template inputs. |
| `curriculum/enrichment/diagram_spec_generator.py` | 26 | `ConceptTeachingPlan, TeachingBeat` | Generates per-beat design diagrams. |

The doc-19 lesson stack also uses `plan_concept` indirectly through its own planner abstractions but ultimately routes through the kernel for the actual LLM call.

---

## 10. Two consumers, one truth

Concrete scenario: a student is mid-way through a precomputed lecture on Newton's laws and taps "Ask Feynman" with a doubt about inertia.

1. **Precompute path (already done, offline):** The chapter's concepts were planned with `plan_concept(concept_index=i, curriculum=...)`. Each plan obeyed the Feynman arc. Beat narrations were written by `BeatNarrationWriter` using `PRONUNCIATION_RULES` and respecting `BANNED_OPENERS`. The manifest now plays.

2. **Live doubt path (firing now):** The worker's lecture-mode `_handle_doubt_intent()` routes to `ResolutionPlanner.plan_resolution(...)`, which is *not* the kernel's `plan_doubt` directly but the same shape. The resulting `ResolutionPlan.beats` use `ChecklistItem`-aware logic if it needs to resolve a deeper sub-question.

3. **If the student then asks the agent for a fully-live deep-dive,** the agent's `start_doubt_branch` calls `plan_doubt(...)` (from the kernel) which produces a `ConceptTeachingPlan` with `concept_index=-1` and a `resolution_checklist` of 2-4 items. The `DoubtOrchestrator` enforces those items before `resolve_doubt` is allowed.

Through all three steps the **same Pydantic models, same Feynman arc validator, same prompt phrasing, same style rules** apply. That's the kernel's contribution: structural unity across modes.

---

## Reading order for a new engineer

1. `README.md` — three minutes.
2. `models.py` — every model, every field. Read the descriptions out loud; they're the LLM's spec.
3. `prompts.py` — skim the section structure, read the Feynman-arc section.
4. `planner.py` — both functions are ~60 lines each.
5. `format.py` — short.
6. `style_guide.py` — short.
7. `tests/test_models.py` — see the contract concretely.
8. Cross-reference `01-precompute-pipeline.md` §12 and `03-teaching-state-machine.md` §10 to see how the kernel is consumed.
