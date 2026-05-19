"""Deterministic anchor data models.

Anchors are structural markers (section numbers, figures, examples, equations,
defined terms) found via regex in PDF text — extracted BEFORE any LLM call.

In v2 anchors play two roles:
1. Section numbers are the **topic boundaries** — every numbered section
   becomes one Topic node.
2. Figures/examples/equations form the completeness checklist for the
   per-topic enrichment validator.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class SectionAnchor(BaseModel):
    section_number: str = Field(..., description="e.g. '12.1.1'")
    title: str = Field(..., description="e.g. 'Potential Energy in SHM'")
    depth: int = Field(
        ...,
        description="Dot-separated part count: '12' -> 1, '12.1' -> 2, '12.1.1' -> 3",
    )


class ExtractionAnchors(BaseModel):
    section_numbers: list[SectionAnchor] = Field(default_factory=list)
    equations: list[str] = Field(default_factory=list)
    figure_refs: list[str] = Field(default_factory=list)
    example_refs: list[str] = Field(default_factory=list)
    defined_terms: list[str] = Field(default_factory=list)
    page_count: int = Field(default=0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def smallest_section_depth(self) -> int:
        if not self.section_numbers:
            return 0
        return max(s.depth for s in self.section_numbers)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def leaf_sections(self) -> list[SectionAnchor]:
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
        return (
            len(self.section_numbers)
            + len(self.equations)
            + len(self.figure_refs)
            + len(self.example_refs)
            + len(self.defined_terms)
        )

    @property
    def is_empty(self) -> bool:
        return self.total_anchor_count == 0

    def summary(self) -> str:
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
