"""Unit tests for semantic validation (mock LLM, no external deps)."""

from __future__ import annotations

import json

import pytest

from lecture_pipeline.config import LLMConfig
from lecture_pipeline.llm.base import LLMProvider, LLMResponse
from lecture_pipeline.curriculum.models import (
    ConceptType,
    CurriculumExtractionResult,
    CurriculumRelationType,
    ExtractionNode,
    ExtractionRelationship,
    ExtractionSource,
    ResolutionLevel,
)
from lecture_pipeline.curriculum.validation.semantic import (
    SemanticIssue,
    SemanticValidationReport,
    SemanticValidator,
)


# ---------------------------------------------------------------------------
# Mock LLM
# ---------------------------------------------------------------------------

_NO_ISSUES = json.dumps({
    "factual_issues": [],
    "relationship_issues": [],
    "missing_concepts": [],
})


class MockLLM(LLMProvider):
    """LLM that returns pre-configured responses in order."""

    def __init__(self, responses: list[str] | None = None):
        config = LLMConfig(provider="anthropic", model="test", api_key="test")
        super().__init__(config)
        self._responses = responses or []
        self._call_idx = 0
        self.calls: list[tuple[str, str]] = []

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        return self.generate_json(system_prompt, user_prompt)

    def generate_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        self.calls.append((system_prompt, user_prompt))
        content = (
            self._responses[self._call_idx]
            if self._call_idx < len(self._responses)
            else _NO_ISSUES
        )
        self._call_idx += 1
        return LLMResponse(content=content, model="test")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _source() -> ExtractionSource:
    return ExtractionSource(
        textbook_title="Test", chapter_title="Ch1",
        page_range="1-10", extractor_model="test",
    )


def _node(
    uid: str,
    concept_type: ConceptType = ConceptType.DEFINITION,
    **kwargs,
) -> ExtractionNode:
    defaults = dict(
        uid=uid, topic_name=uid, concept_type=concept_type,
        resolution_level=ResolutionLevel.CONCEPT,
        summary="Test node.", page_start=1, page_end=5,
        chapter_order=1, within_chapter_order=1,
    )
    defaults.update(kwargs)
    return ExtractionNode(**defaults)


def _rel(
    from_uid: str,
    to_uid: str,
    rel_type: CurriculumRelationType = CurriculumRelationType.PREREQUISITE,
) -> ExtractionRelationship:
    return ExtractionRelationship(
        relationship_key=f"rel:{rel_type.value}:{from_uid}:{to_uid}",
        type=rel_type, from_uid=from_uid, to_uid=to_uid,
    )


def _extraction(
    nodes: list[ExtractionNode],
    rels: list[ExtractionRelationship] | None = None,
) -> CurriculumExtractionResult:
    return CurriculumExtractionResult(
        subject="physics", textbook_title="Test", scope="book",
        source=_source(), nodes=nodes, relationships=rels or [],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSampling:
    def test_formula_always_included(self):
        """All FORMULA nodes checked even at 0% sample rate."""
        llm = MockLLM()
        validator = SemanticValidator(llm, sample_rate=0.0, seed=42)

        nodes = [
            _node("f1", ConceptType.FORMULA),
            _node("f2", ConceptType.FORMULA, within_chapter_order=2),
            _node("d1", ConceptType.DEFINITION, within_chapter_order=3),
        ]
        report = validator.validate(_extraction(nodes), "source text")

        # Only 2 FORMULA nodes checked (0% of rest = no random sampling)
        assert report.nodes_checked == 2

    def test_derivation_always_included(self):
        """All DERIVATION nodes always in the sample."""
        llm = MockLLM()
        validator = SemanticValidator(llm, sample_rate=0.0, seed=42)

        nodes = [
            _node("der1", ConceptType.DERIVATION),
            _node("d1", ConceptType.DEFINITION, within_chapter_order=2),
        ]
        report = validator.validate(_extraction(nodes), "source text")

        assert report.nodes_checked == 1  # 1 DERIVATION only

    def test_sample_rate_full(self):
        """With sample_rate=1.0, all nodes are checked."""
        llm = MockLLM()
        validator = SemanticValidator(llm, sample_rate=1.0, seed=42)

        nodes = [_node(f"n{i}", within_chapter_order=i) for i in range(10)]
        report = validator.validate(_extraction(nodes), "source text")

        assert report.nodes_checked == 10

    def test_sample_rate_partial(self):
        """10% of 20 non-formula nodes = 2, plus at least min 1."""
        llm = MockLLM()
        validator = SemanticValidator(llm, sample_rate=0.10, seed=42)

        nodes = [_node(f"n{i}", within_chapter_order=i) for i in range(20)]
        report = validator.validate(_extraction(nodes), "source text")

        assert report.nodes_checked == 2  # max(1, int(20 * 0.1)) = 2

    def test_min_one_sampled_when_rate_positive(self):
        """Even at low rates, at least 1 non-formula node is sampled."""
        llm = MockLLM()
        validator = SemanticValidator(llm, sample_rate=0.01, seed=42)

        nodes = [_node(f"n{i}", within_chapter_order=i) for i in range(5)]
        report = validator.validate(_extraction(nodes), "source text")

        # max(1, int(5 * 0.01)) = max(1, 0) = 1
        assert report.nodes_checked == 1

    def test_empty_extraction(self):
        llm = MockLLM()
        validator = SemanticValidator(llm)
        report = validator.validate(_extraction([]), "source text")

        assert report.nodes_checked == 0
        assert len(llm.calls) == 0

    def test_deterministic_with_seed(self):
        """Same seed = same sample = same prompts."""
        nodes = [_node(f"n{i}", within_chapter_order=i) for i in range(20)]
        ext = _extraction(nodes)

        llm1 = MockLLM()
        SemanticValidator(llm1, sample_rate=0.2, seed=42).validate(ext, "text")

        llm2 = MockLLM()
        SemanticValidator(llm2, sample_rate=0.2, seed=42).validate(ext, "text")

        assert len(llm1.calls) == len(llm2.calls)
        for (_, u1), (_, u2) in zip(llm1.calls, llm2.calls):
            assert u1 == u2


class TestResponseParsing:
    def test_parses_factual_issues(self):
        response = json.dumps({
            "factual_issues": [
                {"severity": "error", "description": "Formula F=ma\u00b2 is wrong"}
            ],
            "relationship_issues": [],
            "missing_concepts": [],
        })
        llm = MockLLM([response])
        validator = SemanticValidator(llm, sample_rate=1.0, seed=42)

        report = validator.validate(_extraction([_node("f1", ConceptType.FORMULA)]), "src")

        assert report.factual_issues == 1
        assert report.issues[0].issue_type == "factual"
        assert report.issues[0].severity == "error"
        assert "F=ma" in report.issues[0].description

    def test_parses_relationship_issues(self):
        response = json.dumps({
            "factual_issues": [],
            "relationship_issues": [
                {"severity": "warning", "description": "Prereq backwards", "relationship": "PREREQUISITE"}
            ],
            "missing_concepts": [],
        })
        llm = MockLLM([response])
        validator = SemanticValidator(llm, sample_rate=1.0, seed=42)

        report = validator.validate(_extraction([_node("n1")]), "src")

        assert report.relationship_issues == 1
        assert report.issues[0].issue_type == "relationship"
        assert report.issues[0].relationship_key == "PREREQUISITE"

    def test_parses_missing_concepts(self):
        response = json.dumps({
            "factual_issues": [],
            "relationship_issues": [],
            "missing_concepts": [
                {"description": "Kinetic energy formula not extracted"}
            ],
        })
        llm = MockLLM([response])
        validator = SemanticValidator(llm, sample_rate=1.0, seed=42)

        report = validator.validate(_extraction([_node("n1")]), "src")

        assert report.missing_concept_flags == 1
        assert report.issues[0].issue_type == "missing"
        assert report.issues[0].severity == "warning"

    def test_handles_invalid_json(self):
        """Invalid JSON degrades gracefully — no crash, no issues."""
        llm = MockLLM(["not json at all {{{"])
        validator = SemanticValidator(llm, sample_rate=1.0, seed=42)

        report = validator.validate(_extraction([_node("n1")]), "src")

        assert report.nodes_checked == 1
        assert len(report.issues) == 0

    def test_handles_non_dict_json(self):
        """Valid JSON but not a dict — graceful degradation."""
        llm = MockLLM(["[1, 2, 3]"])
        validator = SemanticValidator(llm, sample_rate=1.0, seed=42)

        report = validator.validate(_extraction([_node("n1")]), "src")

        assert report.nodes_checked == 1
        assert len(report.issues) == 0

    def test_handles_malformed_items(self):
        """Non-dict items in issue arrays are skipped."""
        response = json.dumps({
            "factual_issues": ["just a string", {"severity": "error", "description": "Real issue"}],
            "relationship_issues": [42],
            "missing_concepts": [],
        })
        llm = MockLLM([response])
        validator = SemanticValidator(llm, sample_rate=1.0, seed=42)

        report = validator.validate(_extraction([_node("f1", ConceptType.FORMULA)]), "src")

        assert len(report.issues) == 1
        assert report.issues[0].description == "Real issue"

    def test_no_issues_clean_response(self):
        llm = MockLLM([_NO_ISSUES])
        validator = SemanticValidator(llm, sample_rate=1.0, seed=42)

        report = validator.validate(_extraction([_node("n1")]), "src")

        assert report.nodes_checked == 1
        assert report.nodes_with_issues == 0
        assert len(report.issues) == 0


class TestWrongFormulaDetection:
    """Design doc test criterion: inject a wrong formula, verify it's caught."""

    def test_wrong_formula_flagged(self):
        """Node with F=ma\u00b2 instead of F=ma gets flagged as factual error."""
        response = json.dumps({
            "factual_issues": [{
                "severity": "error",
                "description": (
                    "Formula states F=ma\u00b2 but the source text shows "
                    "Newton's second law as F=ma (force equals mass times "
                    "acceleration, not acceleration squared)."
                ),
            }],
            "relationship_issues": [],
            "missing_concepts": [],
        })
        llm = MockLLM([response])
        validator = SemanticValidator(llm, sample_rate=1.0, seed=42)

        wrong = _node(
            "formula:newton2",
            ConceptType.FORMULA,
            topic_name="Newton's Second Law",
            summary="F = ma\u00b2 \u2014 force equals mass times acceleration squared.",
            source_text=(
                "Newton's second law: F = ma. The net force on an object "
                "equals its mass times its acceleration."
            ),
        )
        report = validator.validate(_extraction([wrong]), "chapter text")

        assert report.factual_issues >= 1
        assert report.nodes_with_issues >= 1
        assert any(
            i.issue_type == "factual" and i.severity == "error"
            for i in report.issues
        )

    def test_correct_formula_no_issues(self):
        """A correct formula should produce no issues."""
        llm = MockLLM([_NO_ISSUES])
        validator = SemanticValidator(llm, sample_rate=1.0, seed=42)

        correct = _node(
            "formula:newton2",
            ConceptType.FORMULA,
            topic_name="Newton's Second Law",
            summary="F = ma \u2014 force equals mass times acceleration.",
            source_text="Newton's second law: F = ma.",
        )
        report = validator.validate(_extraction([correct]), "chapter text")

        assert report.factual_issues == 0
        assert report.nodes_with_issues == 0


class TestPromptConstruction:
    def test_prompt_includes_node_details(self):
        llm = MockLLM()
        validator = SemanticValidator(llm, sample_rate=1.0, seed=42)

        node = _node(
            "energy", ConceptType.FORMULA,
            topic_name="Kinetic Energy", summary="KE = \u00bdmv\u00b2",
        )
        validator.validate(_extraction([node]), "Chapter text about energy")

        assert len(llm.calls) == 1
        _, user_prompt = llm.calls[0]
        assert "Kinetic Energy" in user_prompt
        assert "KE = \u00bdmv\u00b2" in user_prompt
        assert "FORMULA" in user_prompt

    def test_prompt_includes_relationships(self):
        llm = MockLLM()
        validator = SemanticValidator(llm, sample_rate=1.0, seed=42)

        nodes = [
            _node("a", ConceptType.FORMULA, topic_name="Force"),
            _node("b", topic_name="Mass", within_chapter_order=2),
        ]
        rels = [_rel("b", "a", CurriculumRelationType.PREREQUISITE)]
        validator.validate(_extraction(nodes, rels), "text")

        # Force node (FORMULA, always checked) prompt should mention Mass prereq
        force_call = next(
            (s, u) for s, u in llm.calls if "Force" in u
        )
        assert "PREREQUISITE" in force_call[1]
        assert "Mass" in force_call[1]

    def test_uses_node_source_text_when_available(self):
        llm = MockLLM()
        validator = SemanticValidator(llm, sample_rate=1.0, seed=42)

        node = _node(
            "n1", ConceptType.FORMULA,
            source_text="The force F equals mass m times acceleration a.",
        )
        validator.validate(_extraction([node]), "Full chapter text here")

        _, user_prompt = llm.calls[0]
        assert "force F equals mass m" in user_prompt
        assert "Full chapter text here" not in user_prompt

    def test_falls_back_to_chapter_text(self):
        """When node has no source_text, uses chapter_text instead."""
        llm = MockLLM()
        validator = SemanticValidator(llm, sample_rate=1.0, seed=42)

        node = _node("n1", ConceptType.FORMULA, source_text="")
        validator.validate(_extraction([node]), "Chapter fallback text")

        _, user_prompt = llm.calls[0]
        assert "Chapter fallback text" in user_prompt

    def test_contains_relationships_excluded(self):
        """CONTAINS rels should NOT appear in the validation prompt."""
        llm = MockLLM()
        validator = SemanticValidator(llm, sample_rate=1.0, seed=42)

        nodes = [
            _node("ch", ConceptType.TOPIC, topic_name="Chapter",
                  resolution_level=ResolutionLevel.CHAPTER),
            _node("f1", ConceptType.FORMULA, topic_name="Formula",
                  within_chapter_order=2),
        ]
        rels = [_rel("ch", "f1", CurriculumRelationType.CONTAINS)]
        validator.validate(_extraction(nodes, rels), "text")

        formula_call = next(
            (s, u) for s, u in llm.calls if "Formula" in u
        )
        assert "CONTAINS" not in formula_call[1]


class TestReportBuilding:
    def test_summary_format(self):
        report = SemanticValidationReport(
            nodes_checked=15,
            nodes_with_issues=3,
            factual_issues=2,
            relationship_issues=1,
            missing_concept_flags=0,
            elapsed_seconds=1.5,
        )
        summary = report.summary()
        assert "15 nodes checked" in summary
        assert "3 issues" in summary
        assert "2 factual" in summary
        assert "1.5s" in summary

    def test_empty_report(self):
        report = SemanticValidationReport()
        summary = report.summary()
        assert "0 nodes checked" in summary
        assert "0 issues" in summary


class TestMultipleNodes:
    def test_issues_aggregated_across_nodes(self):
        responses = [
            json.dumps({
                "factual_issues": [{"severity": "error", "description": "Wrong formula"}],
                "relationship_issues": [],
                "missing_concepts": [{"description": "Missing KE"}],
            }),
            json.dumps({
                "factual_issues": [],
                "relationship_issues": [{"severity": "warning", "description": "Bad prereq"}],
                "missing_concepts": [],
            }),
        ]
        llm = MockLLM(responses)
        validator = SemanticValidator(llm, sample_rate=1.0, seed=42)

        nodes = [
            _node("f1", ConceptType.FORMULA),
            _node("f2", ConceptType.FORMULA, within_chapter_order=2),
        ]
        report = validator.validate(_extraction(nodes), "text")

        assert report.nodes_checked == 2
        assert report.nodes_with_issues == 2
        assert report.factual_issues == 1
        assert report.relationship_issues == 1
        assert report.missing_concept_flags == 1
        assert len(report.issues) == 3

    def test_clean_node_not_counted_as_issue(self):
        responses = [
            json.dumps({
                "factual_issues": [{"severity": "error", "description": "Bad"}],
                "relationship_issues": [],
                "missing_concepts": [],
            }),
            _NO_ISSUES,
        ]
        llm = MockLLM(responses)
        validator = SemanticValidator(llm, sample_rate=1.0, seed=42)

        nodes = [
            _node("f1", ConceptType.FORMULA),
            _node("f2", ConceptType.FORMULA, within_chapter_order=2),
        ]
        report = validator.validate(_extraction(nodes), "text")

        assert report.nodes_checked == 2
        assert report.nodes_with_issues == 1

    def test_llm_exception_graceful(self):
        """If LLM throws, that node is skipped — no crash."""

        class FailingLLM(MockLLM):
            def generate_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
                self.calls.append((system_prompt, user_prompt))
                if self._call_idx == 0:
                    self._call_idx += 1
                    raise RuntimeError("API timeout")
                return super().generate_json(system_prompt, user_prompt)

        llm = FailingLLM()
        validator = SemanticValidator(llm, sample_rate=1.0, seed=42)

        nodes = [
            _node("f1", ConceptType.FORMULA),
            _node("f2", ConceptType.FORMULA, within_chapter_order=2),
        ]
        report = validator.validate(_extraction(nodes), "text")

        assert report.nodes_checked == 2
        assert len(report.issues) == 0  # First failed, second clean


class TestRealisticExtraction:
    """Realistic-ish extraction to test sampling + aggregation together."""

    def _build(self) -> CurriculumExtractionResult:
        nodes = []
        # 3 formulas (always checked)
        for i in range(3):
            nodes.append(_node(f"f{i}", ConceptType.FORMULA, within_chapter_order=i))
        # 1 derivation (always checked)
        nodes.append(_node("der0", ConceptType.DERIVATION, within_chapter_order=3))
        # 10 definitions
        for i in range(10):
            nodes.append(_node(f"d{i}", ConceptType.DEFINITION, within_chapter_order=i + 4))
        # 5 examples
        for i in range(5):
            nodes.append(_node(f"e{i}", ConceptType.EXAMPLE, within_chapter_order=i + 14))
        # 2 analogies
        for i in range(2):
            nodes.append(_node(f"a{i}", ConceptType.ANALOGY, within_chapter_order=i + 19))

        rels = [_rel(f"d{i}", f"f{i % 3}") for i in range(10)]
        return _extraction(nodes, rels)

    def test_always_check_types_counted(self):
        """3 formulas + 1 derivation = 4 always-checked nodes."""
        llm = MockLLM()
        validator = SemanticValidator(llm, sample_rate=0.0, seed=42)
        report = validator.validate(self._build(), "text")
        assert report.nodes_checked == 4

    def test_default_rate_samples_rest(self):
        """Default 10%: 4 always + max(1, int(17 * 0.1)) = 4 + 1 = 5."""
        llm = MockLLM()
        validator = SemanticValidator(llm, sample_rate=0.10, seed=42)
        report = validator.validate(self._build(), "text")
        assert report.nodes_checked == 5

    def test_all_nodes_checkable(self):
        llm = MockLLM()
        validator = SemanticValidator(llm, sample_rate=1.0, seed=42)
        report = validator.validate(self._build(), "text")
        assert report.nodes_checked == 21
