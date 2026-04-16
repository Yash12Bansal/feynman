"""Book-level unification for curriculum extraction."""

from .book_unifier import BookUnifier, UnificationReport
from .hierarchy_builder import HierarchyBuilder, HierarchyResult
from .reference_resolver import ReferenceResolver, ResolutionResult
from .shared_concept_detector import SharedConceptDetector, SharedConceptResult

__all__ = [
    "BookUnifier",
    "HierarchyBuilder",
    "HierarchyResult",
    "ReferenceResolver",
    "ResolutionResult",
    "SharedConceptDetector",
    "SharedConceptResult",
    "UnificationReport",
]
