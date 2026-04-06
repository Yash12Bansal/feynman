"""Semantic validation of curriculum extraction quality via LLM spot-checks.

After structural validation (Phase 5) ensures completeness and integrity,
semantic validation spot-checks a sample of nodes against the source text
to catch factual issues, wrong relationships, and missing concepts.

Usage:
    validator = SemanticValidator(llm)
    report = validator.validate(extraction, chapter_text)
"""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..models import (
    ConceptType,
    CurriculumExtractionResult,
    CurriculumRelationType,
    ExtractionNode,
)

if TYPE_CHECKING:
    from ...llm.base import LLMProvider

logger = logging.getLogger(__name__)


# Types always included in the spot-check sample (high-stakes for accuracy)
_ALWAYS_CHECK_TYPES = frozenset({ConceptType.FORMULA, ConceptType.DERIVATION})

# Relationship types whose correctness gets checked
_PEDAGOGICAL_REL_TYPES = frozenset({
    CurriculumRelationType.PREREQUISITE,
    CurriculumRelationType.LEADS_TO,
    CurriculumRelationType.DERIVED_FROM,
    CurriculumRelationType.EXAMPLE_OF,
})


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class SemanticIssue:
    """A single issue found during semantic spot-checking."""

    issue_type: str  # "factual", "relationship", "missing"
    severity: str  # "error" or "warning"
    description: str
    node_uid: str
    relationship_key: str | None = None


@dataclass
class SemanticValidationReport:
    """Results of a semantic validation run."""

    nodes_checked: int = 0
    nodes_with_issues: int = 0
    factual_issues: int = 0
    relationship_issues: int = 0
    missing_concept_flags: int = 0
    elapsed_seconds: float = 0.0
    issues: list[SemanticIssue] = field(default_factory=list)

    def summary(self) -> str:
        total = self.factual_issues + self.relationship_issues + self.missing_concept_flags
        return (
            f"Semantic validation — {self.nodes_checked} nodes checked, "
            f"{total} issues ({self.factual_issues} factual, "
            f"{self.relationship_issues} relationship, "
            f"{self.missing_concept_flags} missing), "
            f"{self.elapsed_seconds:.1f}s"
        )


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a factual validator for a curriculum knowledge graph extracted from a textbook.

Given source text from a textbook and an extracted concept, verify:
1. Is the summary factually consistent with the source text?
2. Are any formulas or equations in the summary incorrect or distorted?
3. Are the listed relationships correct (e.g., does Concept A truly need to be \
understood before Concept B)?
4. Are there important concepts on these pages that seem to be missing from the extraction?

Return a JSON object with exactly three keys:
- "factual_issues": list of objects with {"severity": "error"|"warning", "description": "..."}
- "relationship_issues": list of objects with \
{"severity": "error"|"warning", "description": "...", "relationship": "..."}
- "missing_concepts": list of objects with {"description": "..."}

If no issues are found for a category, return an empty list.
Return ONLY the JSON object. No markdown fences, no explanatory text."""

_USER_PROMPT_TEMPLATE = """\
## Source Text (pages {page_start}\u2013{page_end})

{source_text}

## Extracted Concept

- **Topic**: {topic_name}
- **Type**: {concept_type}
- **Resolution Level**: {resolution_level}
- **Summary**: {summary}

## Relationships

{relationships}

## Task

Check the extracted concept against the source text. Report any factual errors, \
formula mistakes, incorrect relationships, or important concepts from these pages \
that seem to be missing."""


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class SemanticValidator:
    """LLM-based semantic validation \u2014 spot-checks extraction quality.

    Samples all FORMULA/DERIVATION nodes + ~sample_rate fraction of the rest.
    Each sampled node gets one LLM call against its source text.
    """

    def __init__(
        self,
        llm: LLMProvider,
        *,
        sample_rate: float = 0.10,
        seed: int | None = None,
    ) -> None:
        self.llm = llm
        self.sample_rate = sample_rate
        self._rng = random.Random(seed)

    def validate(
        self,
        extraction: CurriculumExtractionResult,
        chapter_text: str,
    ) -> SemanticValidationReport:
        """Spot-check a sample of nodes against source text.

        Args:
            extraction: The extraction result to validate.
            chapter_text: Full chapter text for fallback source context.

        Returns:
            SemanticValidationReport with any issues found.
        """
        start = time.monotonic()

        sample = self._select_sample(extraction)
        if not sample:
            return SemanticValidationReport(elapsed_seconds=time.monotonic() - start)

        rel_context = self._build_relationship_context(extraction)

        all_issues: list[SemanticIssue] = []
        uids_with_issues: set[str] = set()

        for node in sample:
            node_rels = rel_context.get(node.uid, [])
            source = node.source_text if node.source_text else chapter_text
            issues = self._validate_node(node, node_rels, source)
            all_issues.extend(issues)
            if issues:
                uids_with_issues.add(node.uid)

        elapsed = time.monotonic() - start
        return self._build_report(all_issues, len(sample), len(uids_with_issues), elapsed)

    # ------------------------------------------------------------------
    # Sampling
    # ------------------------------------------------------------------

    def _select_sample(
        self, extraction: CurriculumExtractionResult
    ) -> list[ExtractionNode]:
        """Select nodes for spot-checking.

        Always: all FORMULA and DERIVATION nodes.
        Additionally: random sample_rate fraction of remaining nodes (min 1
        when sample_rate > 0).
        """
        always: list[ExtractionNode] = []
        rest: list[ExtractionNode] = []

        for node in extraction.nodes:
            if node.concept_type in _ALWAYS_CHECK_TYPES:
                always.append(node)
            else:
                rest.append(node)

        if rest and self.sample_rate > 0:
            k = max(1, int(len(rest) * self.sample_rate))
            k = min(k, len(rest))
            sampled = self._rng.sample(rest, k)
        else:
            sampled = []

        return always + sampled

    # ------------------------------------------------------------------
    # Relationship context
    # ------------------------------------------------------------------

    def _build_relationship_context(
        self, extraction: CurriculumExtractionResult
    ) -> dict[str, list[str]]:
        """Build human-readable relationship descriptions per node.

        Returns: {uid: ["PREREQUISITE from 'Concept A'", ...]}
        """
        uid_to_name = {n.uid: n.topic_name for n in extraction.nodes}
        context: dict[str, list[str]] = {}

        for rel in extraction.relationships:
            if rel.type not in _PEDAGOGICAL_REL_TYPES:
                continue

            from_name = uid_to_name.get(rel.from_uid, rel.from_uid)
            to_name = uid_to_name.get(rel.to_uid, rel.to_uid)

            # Incoming edge for the "to" node
            context.setdefault(rel.to_uid, []).append(
                f'{rel.type.value.upper()} from "{from_name}"'
            )
            # Outgoing edge for the "from" node
            context.setdefault(rel.from_uid, []).append(
                f'{rel.type.value.upper()} to "{to_name}"'
            )

        return context

    # ------------------------------------------------------------------
    # Per-node validation
    # ------------------------------------------------------------------

    def _validate_node(
        self,
        node: ExtractionNode,
        relationships: list[str],
        source_text: str,
    ) -> list[SemanticIssue]:
        """Validate a single node via one LLM call."""
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            page_start=node.page_start,
            page_end=node.page_end,
            source_text=source_text or "(source text not available)",
            topic_name=node.topic_name,
            concept_type=node.concept_type.value.upper(),
            resolution_level=node.resolution_level.value,
            summary=node.summary,
            relationships=(
                "\n".join(f"- {r}" for r in relationships)
                if relationships
                else "(no relationships)"
            ),
        )

        try:
            response = self.llm.generate_json(_SYSTEM_PROMPT, user_prompt)
        except Exception:
            logger.exception("Semantic validation LLM call failed for %s", node.uid)
            return []

        if response.usage:
            logger.debug(
                "Semantic check %s: %s in, %s out tokens",
                node.uid,
                response.usage.get("input_tokens", "?"),
                response.usage.get("output_tokens", "?"),
            )

        return self._parse_response(response.content, node.uid)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(self, raw: str, node_uid: str) -> list[SemanticIssue]:
        """Parse LLM JSON response into SemanticIssue list."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning(
                "Semantic validation returned invalid JSON for %s: %s", node_uid, exc
            )
            return []

        if not isinstance(data, dict):
            logger.warning("Semantic validation returned non-dict for %s", node_uid)
            return []

        issues: list[SemanticIssue] = []

        for item in data.get("factual_issues", []):
            if not isinstance(item, dict):
                continue
            issues.append(
                SemanticIssue(
                    issue_type="factual",
                    severity=item.get("severity", "warning"),
                    description=item.get("description", "Unknown factual issue"),
                    node_uid=node_uid,
                )
            )

        for item in data.get("relationship_issues", []):
            if not isinstance(item, dict):
                continue
            issues.append(
                SemanticIssue(
                    issue_type="relationship",
                    severity=item.get("severity", "warning"),
                    description=item.get("description", "Unknown relationship issue"),
                    node_uid=node_uid,
                    relationship_key=item.get("relationship"),
                )
            )

        for item in data.get("missing_concepts", []):
            if not isinstance(item, dict):
                continue
            issues.append(
                SemanticIssue(
                    issue_type="missing",
                    severity="warning",
                    description=item.get("description", "Missing concept"),
                    node_uid=node_uid,
                )
            )

        return issues

    # ------------------------------------------------------------------
    # Report building
    # ------------------------------------------------------------------

    def _build_report(
        self,
        issues: list[SemanticIssue],
        nodes_checked: int,
        nodes_with_issues: int,
        elapsed: float,
    ) -> SemanticValidationReport:
        """Aggregate issues into a report."""
        report = SemanticValidationReport(
            nodes_checked=nodes_checked,
            nodes_with_issues=nodes_with_issues,
            factual_issues=sum(1 for i in issues if i.issue_type == "factual"),
            relationship_issues=sum(1 for i in issues if i.issue_type == "relationship"),
            missing_concept_flags=sum(1 for i in issues if i.issue_type == "missing"),
            elapsed_seconds=elapsed,
            issues=issues,
        )
        logger.info(report.summary())
        return report
