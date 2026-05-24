"""Validation result types — small dataclasses, not serialised externally."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationIssue:
    level: str
    code: str
    message: str
    entity_id: str | None = None
    details: dict[str, Any] | None = None


@dataclass
class ValidationReport:
    valid: bool = True
    issues: list[ValidationIssue] = field(default_factory=list)
    topics_checked: int = 0
    diagrams_checked: int = 0
    questions_checked: int = 0
    error_count: int = 0
    warning_count: int = 0

    def add_error(self, code: str, message: str, **kwargs) -> None:
        self.issues.append(
            ValidationIssue(level="error", code=code, message=message, **kwargs)
        )
        self.error_count += 1
        self.valid = False

    def add_warning(self, code: str, message: str, **kwargs) -> None:
        self.issues.append(
            ValidationIssue(level="warning", code=code, message=message, **kwargs)
        )
        self.warning_count += 1

    def summary(self) -> str:
        status = "PASS" if self.valid else "FAIL"
        return (
            f"Validation: {status} | "
            f"{self.topics_checked} topics, {self.diagrams_checked} diagrams, "
            f"{self.questions_checked} questions | "
            f"{self.error_count} errors, {self.warning_count} warnings"
        )
