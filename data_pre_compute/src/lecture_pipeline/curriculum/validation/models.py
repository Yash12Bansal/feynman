"""Validation result types for curriculum extraction.

Lightweight dataclasses — internal pipeline artifacts, not serialized externally.
Pattern adapted from PMG's ExtractionValidator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Issue codes that represent completeness gaps (fillable by GapFiller)
COMPLETENESS_ISSUE_CODES = frozenset({
    "MISSING_SECTIONS",
    "MISSING_FORMULAS",
    "MISSING_FIGURES",
    "MISSING_EXAMPLES",
})


@dataclass
class ValidationIssue:
    """A single validation issue found during structural checks."""

    level: str  # "error" or "warning"
    code: str  # machine-readable, e.g. "DUPLICATE_UID", "MISSING_SECTIONS"
    message: str  # human-readable description
    entity_key: str | None = None  # node UID if issue is about a specific node
    relationship_key: str | None = None  # rel key if about a specific relationship
    details: dict[str, Any] | None = None  # structured data for gap-filler


@dataclass
class ValidationReport:
    """Complete validation report for a CurriculumExtractionResult."""

    valid: bool = True
    issues: list[ValidationIssue] = field(default_factory=list)
    node_count: int = 0
    relationship_count: int = 0
    error_count: int = 0
    warning_count: int = 0

    def add_error(self, code: str, message: str, **kwargs: Any) -> None:
        """Add an error-level issue. Sets valid=False."""
        self.issues.append(
            ValidationIssue(level="error", code=code, message=message, **kwargs)
        )
        self.error_count += 1
        self.valid = False

    def add_warning(self, code: str, message: str, **kwargs: Any) -> None:
        """Add a warning-level issue. Does not affect valid flag."""
        self.issues.append(
            ValidationIssue(level="warning", code=code, message=message, **kwargs)
        )
        self.warning_count += 1

    def errors_by_code(self, code: str) -> list[ValidationIssue]:
        """Filter error-level issues by code."""
        return [
            i for i in self.issues if i.level == "error" and i.code == code
        ]

    def has_completeness_errors(self) -> bool:
        """True if any completeness-gap errors exist (fillable by GapFiller)."""
        return any(
            i.level == "error" and i.code in COMPLETENESS_ISSUE_CODES
            for i in self.issues
        )

    def downgrade_completeness_errors(self) -> None:
        """Convert remaining completeness errors to warnings.

        Called after max gap-fill retries — accept what we have,
        flag for human review.
        """
        for issue in self.issues:
            if issue.level == "error" and issue.code in COMPLETENESS_ISSUE_CODES:
                issue.level = "warning"
                self.error_count -= 1
                self.warning_count += 1
        # Recompute valid: only True if no errors remain
        self.valid = self.error_count == 0

    def summary(self) -> str:
        """Human-readable one-line summary for logging."""
        status = "PASS" if self.valid else "FAIL"
        return (
            f"Validation: {status} | "
            f"{self.node_count} nodes, {self.relationship_count} rels | "
            f"{self.error_count} errors, {self.warning_count} warnings"
        )
