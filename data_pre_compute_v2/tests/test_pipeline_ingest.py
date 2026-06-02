"""Regression guard for the Phase 12 Neo4j ingest wiring.

`CurriculumPipelineV2._ingest` was once commented out while its call site in
`run()` stayed live, so every `ingest-book` without `--skip-neo4j` crashed with
`AttributeError: ... has no attribute '_ingest'` AND discarded the run's output
(the CLI writes the extraction JSON only after `run()` returns). The fix was
also lost once to branch divergence. This test locks the method's existence so
a future refactor/merge can't silently reintroduce the crash.
"""

from __future__ import annotations

import inspect

from lecture_pipeline_v2.config import PipelineConfig
from lecture_pipeline_v2.pipeline import CurriculumPipelineV2


def test_ingest_method_exists_and_is_coroutine() -> None:
    assert hasattr(CurriculumPipelineV2, "_ingest"), (
        "_ingest must be a live method — run() calls it in Phase 12"
    )
    assert inspect.iscoroutinefunction(CurriculumPipelineV2._ingest)


def test_pipeline_constructs_without_network() -> None:
    # llm / tts / artifact_store are lazy properties, so constructing the
    # pipeline must not touch the network — and _ingest is resolvable on it.
    pipeline = CurriculumPipelineV2(PipelineConfig())
    assert hasattr(pipeline, "_ingest")
