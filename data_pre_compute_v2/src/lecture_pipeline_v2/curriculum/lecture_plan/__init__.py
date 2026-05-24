"""Chapter + concept lecture planning for the precompute pipeline.

Two planners:
- ChapterLecturePlanner — produces a chapter-level arc (concept_sequence,
  coverage, length budget). Sync; uses v2's own AnthropicProvider.
- ConceptPlanner — for each topic in the chapter plan, calls
  feynman_teaching_kernel.plan_concept to produce a per-concept teaching
  plan. Async; uses the kernel's AsyncAnthropic client.

The CurriculumAdapter bridges v2's Chapter+Topic[] data model into the
duck-typed surface the kernel expects.
"""
