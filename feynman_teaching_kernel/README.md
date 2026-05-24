# feynman-teaching-kernel

Shared teaching-planner kernel. The single source of truth for `ConceptTeachingPlan`, `TeachingBeat`, `VisualBeatAction`, `ChecklistItem`, the `PLANNING_SYSTEM_PROMPT`, and the `plan_concept` / `plan_doubt` / `format_plan_for_prompt` functions.

Both the **real-time agent** (`backend/src/feynman/agent/`) and the **precompute pipeline** (`data_pre_compute_v2/src/lecture_pipeline_v2/`) import this kernel so live teaching and recorded teaching can never drift in their planning logic. See `docs/design/17-precompute-lecture-pipeline-overhaul.md` §3.3 for the architectural rationale.

Installed as an editable path-dependency from each consumer's `pyproject.toml`:

- backend (`uv`): `[tool.uv.sources]` block with `feynman-teaching-kernel = { path = "../feynman_teaching_kernel", editable = true }`
- data_pre_compute_v2 (`poetry`): `[tool.poetry.dependencies]` with `feynman-teaching-kernel = { path = "../feynman_teaching_kernel", develop = true }`
