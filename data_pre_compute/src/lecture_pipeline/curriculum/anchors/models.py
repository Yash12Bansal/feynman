"""Data models for deterministic anchor extraction.

Anchors are structural markers found in PDF text via regex — before any LLM call.
They form the completeness checklist that validates LLM extraction output.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class SectionAnchor(BaseModel):
    """A numbered section heading found in the text."""

    section_number: str = Field(..., description="e.g. '12.1.1'")
    title: str = Field(..., description="e.g. 'Potential Energy in SHM'")
    depth: int = Field(
        ...,
        description="Dot-separated part count: '12' -> 1, '12.1' -> 2, '12.1.1' -> 3",
    )


class ExtractionAnchors(BaseModel):
    """All deterministic anchors extracted from a chapter's text.

    Used downstream as:
    1. Injection into LLM prompts ("extraction floor — do NOT skip any")
    2. Validation checklist (StructuralValidator checks coverage percentages)
    """

    section_numbers: list[SectionAnchor] = Field(default_factory=list)
    equations: list[str] = Field(
        default_factory=list, description="Equation references like 'Eq. (3.5)'"
    )
    figure_refs: list[str] = Field(
        default_factory=list, description="Figure references like 'Figure 12.3'"
    )
    example_refs: list[str] = Field(
        default_factory=list, description="Example references like 'Example 12.1'"
    )
    defined_terms: list[str] = Field(
        default_factory=list, description="Terms found via definition patterns"
    )
    page_count: int = Field(default=0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def smallest_section_depth(self) -> int:
        """Deepest section level found (3 = sub-sub-section), 0 if empty."""
        if not self.section_numbers:
            return 0
        return max(s.depth for s in self.section_numbers)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def leaf_sections(self) -> list[SectionAnchor]:
        """Sections with no children — the extraction floor.

        A section is a leaf if no other section number starts with it + '.'.
        E.g. 12.1 is NOT a leaf if 12.1.1 exists, but 12.2 IS a leaf if no 12.2.X exists.
        """
        if not self.section_numbers:
            return []
        all_numbers = {s.section_number for s in self.section_numbers}
        return [
            s
            for s in self.section_numbers
            if not any(
                other.startswith(s.section_number + ".")
                for other in all_numbers
                if other != s.section_number
            )
        ]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_anchor_count(self) -> int:
        """Total number of anchors across all categories."""
        return (
            len(self.section_numbers)
            + len(self.equations)
            + len(self.figure_refs)
            + len(self.example_refs)
            + len(self.defined_terms)
        )

    @property
    def is_empty(self) -> bool:
        """True if no anchors were found at all."""
        return self.total_anchor_count == 0

    def summary(self) -> str:
        """Human-readable summary for logging."""
        parts = []
        if self.section_numbers:
            parts.append(
                f"{len(self.section_numbers)} sections (depth {self.smallest_section_depth})"
            )
        if self.equations:
            parts.append(f"{len(self.equations)} equations")
        if self.figure_refs:
            parts.append(f"{len(self.figure_refs)} figures")
        if self.example_refs:
            parts.append(f"{len(self.example_refs)} examples")
        if self.defined_terms:
            parts.append(f"{len(self.defined_terms)} definitions")
        if not parts:
            return "No anchors found"
        return f"Anchors: {', '.join(parts)} ({self.page_count} pages)"
