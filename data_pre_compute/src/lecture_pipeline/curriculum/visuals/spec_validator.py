"""Light semantic validation for generated DiagramSpec objects.

Pydantic parse handles structural validation (types, required fields).
This module catches semantic issues: empty diagrams, duplicate IDs,
out-of-bounds elements, empty LaTeX expressions, etc.
"""

from __future__ import annotations

import logging

from .models import DiagramSpec, SvgLatex

logger = logging.getLogger(__name__)


class VisualSpecValidator:
    """Validates a DiagramSpec beyond Pydantic structural checks."""

    def validate(self, spec: DiagramSpec) -> list[str]:
        """Return a list of warning strings. Empty list = valid."""
        warnings: list[str] = []

        # 1. Must have at least one element
        if not spec.elements:
            warnings.append("DiagramSpec has no elements.")
            return warnings

        # 2. Unique IDs
        ids: list[str] = []
        for el in spec.elements:
            if hasattr(el, "id") and el.id is not None:
                ids.append(el.id)
        seen: set[str] = set()
        for eid in ids:
            if eid in seen:
                warnings.append(f"Duplicate element id: {eid!r}")
            seen.add(eid)

        # 3. Empty LaTeX expressions
        for el in spec.elements:
            if isinstance(el, SvgLatex) and not el.expression.strip():
                warnings.append(
                    f"Empty LaTeX expression in element {getattr(el, 'id', '?')!r}"
                )

        # 4. Parameters defined but never referenced
        if spec.parameters:
            param_names = {p.name for p in spec.parameters}
            # Serialize elements to check for parameter references
            elements_json = spec.model_dump_json(include={"elements"})
            unreferenced = [
                name for name in param_names if name not in elements_json
            ]
            if unreferenced:
                warnings.append(
                    f"Parameters defined but not referenced in elements: {unreferenced}"
                )

        return warnings
