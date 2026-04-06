"""Tests for book skeleton extraction — mocked LLM, no API calls."""

from __future__ import annotations

import json

import pytest

from lecture_pipeline.curriculum.models import BookSkeleton
from lecture_pipeline.curriculum.prompts import (
    build_skeleton_user_prompt,
    get_skeleton_system_prompt,
)
from lecture_pipeline.curriculum.skeleton_extractor import (
    SkeletonExtractionError,
    SkeletonExtractor,
)
from lecture_pipeline.llm.base import LLMProvider, LLMResponse
from lecture_pipeline.pdf.parser import PageContent, PDFContent
from lecture_pipeline.pdf.toc import Chapter


# ---------------------------------------------------------------------------
# Mock LLM provider
# ---------------------------------------------------------------------------


class MockLLMProvider(LLMProvider):
    """LLM provider that returns preconfigured responses."""

    def __init__(self, responses: list[str] | None = None):
        # Skip super().__init__ — no config needed for mock
        self.responses = list(responses or [])
        self.calls: list[dict[str, str]] = []
        self._call_index = 0

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        return self.generate_json(system_prompt, user_prompt)

    def generate_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        self.calls.append({"system": system_prompt, "user": user_prompt})
        if self._call_index < len(self.responses):
            content = self.responses[self._call_index]
            self._call_index += 1
        else:
            content = "{}"
        return LLMResponse(content=content, model="mock", usage=None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_SKELETON_JSON = json.dumps({
    "textbook_title": "HC Verma - Concepts of Physics",
    "subject": "physics",
    "total_chapters": 3,
    "total_pages": 400,
    "chapters": [
        {
            "chapter_index": 1,
            "title": "Work, Energy and Power",
            "page_start": 80,
            "page_end": 100,
            "summary": "Covers work-energy theorem and conservation of energy.",
            "key_concepts": ["work", "kinetic energy", "potential energy"],
            "prerequisites_from": [],
            "leads_to": ["Simple Harmonic Motion"],
        },
        {
            "chapter_index": 2,
            "title": "Circular Motion",
            "page_start": 120,
            "page_end": 145,
            "summary": "Covers uniform and non-uniform circular motion.",
            "key_concepts": ["centripetal force", "angular velocity"],
            "prerequisites_from": [],
            "leads_to": ["Simple Harmonic Motion"],
        },
        {
            "chapter_index": 3,
            "title": "Simple Harmonic Motion",
            "page_start": 239,
            "page_end": 260,
            "summary": "Covers SHM, energy analysis, damped and forced oscillations.",
            "key_concepts": ["SHM", "energy in SHM", "damped oscillations"],
            "prerequisites_from": ["Work, Energy and Power", "Circular Motion"],
            "leads_to": [],
        },
    ],
    "units": [
        {
            "unit_name": "Mechanics",
            "chapter_indices": [1, 2],
            "theme": "Forces, motion, energy, and work.",
        },
        {
            "unit_name": "Oscillations",
            "chapter_indices": [3],
            "theme": "Periodic motion and harmonic oscillations.",
        },
    ],
    "cross_chapter_prerequisites": [
        {
            "from_chapter": "Work, Energy and Power",
            "to_chapter": "Simple Harmonic Motion",
            "reason": "Energy conservation is used to derive SHM energy formulas.",
        },
    ],
    "subject_overview": "Classical mechanics from kinematics through oscillations.",
})


def _make_pdf_content(num_chapters: int = 3) -> PDFContent:
    """Create a minimal PDFContent with fake page text."""
    pages = []
    for i in range(1, 401):
        pages.append(PageContent(
            page_number=i,
            text=f"This is page {i} with substantial content about physics concepts. "
                 f"The chapter continues with detailed explanations and formulas. "
                 f"Multiple paragraphs of educational content follow here. " * 3,
        ))
    return PDFContent(
        pages=pages,
        toc_raw=[],
        total_pages=400,
        metadata={},
    )


def _make_chapters() -> list[Chapter]:
    """Create test chapters matching the valid skeleton fixture."""
    return [
        Chapter(title="Work, Energy and Power", level=1, start_page=80, end_page=119),
        Chapter(title="Circular Motion", level=1, start_page=120, end_page=238),
        Chapter(title="Simple Harmonic Motion", level=1, start_page=239, end_page=260),
    ]


# ---------------------------------------------------------------------------
# Tests: prompts
# ---------------------------------------------------------------------------


class TestPrompts:
    def test_system_prompt_contains_schema(self):
        prompt = get_skeleton_system_prompt()
        assert "textbook_title" in prompt
        assert "chapter_index" in prompt
        assert "BookSkeleton" in prompt or "chapters" in prompt

    def test_user_prompt_basic(self):
        prompt = build_skeleton_user_prompt(
            toc_text="1. Chapter One (pages 1-50)",
            chapter_previews=[{
                "chapter_index": 1,
                "title": "Chapter One",
                "page_start": 1,
                "page_end": 50,
                "preview_text": "This chapter covers basics.",
            }],
        )
        assert "Chapter One" in prompt
        assert "pages 1-50" in prompt
        assert "This chapter covers basics." in prompt

    def test_user_prompt_with_subject_hint(self):
        prompt = build_skeleton_user_prompt(
            toc_text="1. Intro",
            chapter_previews=[],
            subject_hint="physics",
        )
        assert "physics" in prompt
        assert "Subject" in prompt

    def test_user_prompt_without_subject_hint(self):
        prompt = build_skeleton_user_prompt(
            toc_text="1. Intro",
            chapter_previews=[],
            subject_hint=None,
        )
        assert "The subject of this textbook is" not in prompt


# ---------------------------------------------------------------------------
# Tests: _build_toc_text
# ---------------------------------------------------------------------------


class TestBuildTocText:
    def test_basic_formatting(self):
        chapters = _make_chapters()
        extractor = SkeletonExtractor(MockLLMProvider())
        toc = extractor._build_toc_text(chapters)
        assert "1. Work, Energy and Power (pages 80-119)" in toc
        assert "2. Circular Motion (pages 120-238)" in toc
        assert "3. Simple Harmonic Motion (pages 239-260)" in toc

    def test_empty_chapters(self):
        extractor = SkeletonExtractor(MockLLMProvider())
        assert extractor._build_toc_text([]) == ""

    def test_nested_children(self):
        parent = Chapter(title="Mechanics", level=1, start_page=1, end_page=100)
        parent.children = [
            Chapter(title="Kinematics", level=2, start_page=1, end_page=50),
        ]
        extractor = SkeletonExtractor(MockLLMProvider())
        toc = extractor._build_toc_text([parent])
        assert "1. Mechanics" in toc
        assert "   - Kinematics" in toc


# ---------------------------------------------------------------------------
# Tests: _extract_chapter_previews
# ---------------------------------------------------------------------------


class TestExtractChapterPreviews:
    def test_normal_chapter(self):
        pdf = _make_pdf_content()
        chapters = _make_chapters()
        extractor = SkeletonExtractor(MockLLMProvider())
        previews = extractor._extract_chapter_previews(pdf, chapters)
        assert len(previews) == 3
        assert previews[0]["title"] == "Work, Energy and Power"
        assert previews[0]["chapter_index"] == 1
        assert len(previews[0]["preview_text"]) > 0

    def test_preview_capped_at_max_chars(self):
        pdf = _make_pdf_content()
        chapters = _make_chapters()
        extractor = SkeletonExtractor(MockLLMProvider())
        previews = extractor._extract_chapter_previews(pdf, chapters)
        for p in previews:
            assert len(p["preview_text"]) <= SkeletonExtractor.MAX_PREVIEW_CHARS

    def test_short_first_page_extends(self):
        """If first page has < MIN_PREVIEW_CHARS, extractor pulls more pages."""
        pages = [
            PageContent(page_number=1, text="Short."),
            PageContent(page_number=2, text="More content here with details. " * 20),
        ]
        pdf = PDFContent(pages=pages, toc_raw=[], total_pages=2, metadata={})
        chapter = Chapter(title="Test", level=1, start_page=1, end_page=2)
        extractor = SkeletonExtractor(MockLLMProvider())
        preview = extractor._extract_preview_for_chapter(pdf, chapter)
        # Should contain text from page 2 since page 1 was short
        assert "More content" in preview

    def test_empty_chapter_text(self):
        pages = [PageContent(page_number=1, text="")]
        pdf = PDFContent(pages=pages, toc_raw=[], total_pages=1, metadata={})
        chapter = Chapter(title="Empty", level=1, start_page=1, end_page=1)
        extractor = SkeletonExtractor(MockLLMProvider())
        preview = extractor._extract_preview_for_chapter(pdf, chapter)
        assert preview == ""


# ---------------------------------------------------------------------------
# Tests: _parse_response
# ---------------------------------------------------------------------------


class TestParseResponse:
    def test_valid_json_parses(self):
        extractor = SkeletonExtractor(MockLLMProvider())
        skeleton = extractor._parse_response(VALID_SKELETON_JSON, 400)
        assert skeleton.textbook_title == "HC Verma - Concepts of Physics"
        assert skeleton.subject == "physics"
        assert len(skeleton.chapters) == 3
        assert len(skeleton.units) == 2
        assert len(skeleton.cross_chapter_prerequisites) == 1

    def test_total_chapters_mismatch_fixed(self):
        data = json.loads(VALID_SKELETON_JSON)
        data["total_chapters"] = 999  # wrong
        extractor = SkeletonExtractor(MockLLMProvider())
        skeleton = extractor._parse_response(json.dumps(data), 400)
        assert skeleton.total_chapters == 3  # fixed to match actual count

    def test_total_pages_injected_if_missing(self):
        data = json.loads(VALID_SKELETON_JSON)
        data["total_pages"] = 0  # falsy
        extractor = SkeletonExtractor(MockLLMProvider())
        skeleton = extractor._parse_response(json.dumps(data), 400)
        assert skeleton.total_pages == 400

    def test_missing_optional_fields_default(self):
        data = json.loads(VALID_SKELETON_JSON)
        del data["units"]
        del data["cross_chapter_prerequisites"]
        for ch in data["chapters"]:
            del ch["key_concepts"]
            del ch["prerequisites_from"]
            del ch["leads_to"]
        extractor = SkeletonExtractor(MockLLMProvider())
        skeleton = extractor._parse_response(json.dumps(data), 400)
        assert skeleton.units == []
        assert skeleton.cross_chapter_prerequisites == []
        assert skeleton.chapters[0].key_concepts == []

    def test_invalid_json_raises(self):
        extractor = SkeletonExtractor(MockLLMProvider())
        with pytest.raises(SkeletonExtractionError):
            extractor._parse_response("not json at all", 400)

    def test_missing_required_fields_raises(self):
        extractor = SkeletonExtractor(MockLLMProvider())
        with pytest.raises(SkeletonExtractionError):
            extractor._parse_response('{"textbook_title": "Test"}', 400)


# ---------------------------------------------------------------------------
# Tests: _validate_skeleton
# ---------------------------------------------------------------------------


class TestValidateSkeleton:
    def test_valid_skeleton_no_warnings(self):
        extractor = SkeletonExtractor(MockLLMProvider())
        skeleton = BookSkeleton.model_validate(json.loads(VALID_SKELETON_JSON))
        chapters = _make_chapters()
        warnings = extractor._validate_skeleton(skeleton, chapters)
        assert len(warnings) == 0

    def test_missing_chapter_warning(self):
        extractor = SkeletonExtractor(MockLLMProvider())
        skeleton = BookSkeleton.model_validate(json.loads(VALID_SKELETON_JSON))
        # Add an extra chapter to TOC that skeleton doesn't have
        chapters = _make_chapters() + [
            Chapter(title="Thermodynamics", level=1, start_page=261, end_page=300)
        ]
        warnings = extractor._validate_skeleton(skeleton, chapters)
        assert any("missing" in w.lower() for w in warnings)

    def test_self_prerequisite_warning(self):
        data = json.loads(VALID_SKELETON_JSON)
        data["chapters"][0]["prerequisites_from"] = ["Work, Energy and Power"]
        extractor = SkeletonExtractor(MockLLMProvider())
        skeleton = BookSkeleton.model_validate(data)
        warnings = extractor._validate_skeleton(skeleton, _make_chapters())
        assert any("itself" in w for w in warnings)

    def test_unknown_prerequisite_warning(self):
        data = json.loads(VALID_SKELETON_JSON)
        data["chapters"][2]["prerequisites_from"].append("Nonexistent Chapter")
        extractor = SkeletonExtractor(MockLLMProvider())
        skeleton = BookSkeleton.model_validate(data)
        warnings = extractor._validate_skeleton(skeleton, _make_chapters())
        assert any("unknown prerequisite" in w.lower() for w in warnings)

    def test_invalid_page_range_warning(self):
        data = json.loads(VALID_SKELETON_JSON)
        data["chapters"][0]["page_start"] = 200
        data["chapters"][0]["page_end"] = 100
        extractor = SkeletonExtractor(MockLLMProvider())
        skeleton = BookSkeleton.model_validate(data)
        warnings = extractor._validate_skeleton(skeleton, _make_chapters())
        assert any("invalid page range" in w.lower() for w in warnings)

    def test_empty_subject_warning(self):
        data = json.loads(VALID_SKELETON_JSON)
        data["subject"] = "  "
        extractor = SkeletonExtractor(MockLLMProvider())
        skeleton = BookSkeleton.model_validate(data)
        warnings = extractor._validate_skeleton(skeleton, _make_chapters())
        assert any("subject" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# Tests: full extract() integration
# ---------------------------------------------------------------------------


class TestExtractIntegration:
    def test_extract_success(self):
        mock = MockLLMProvider(responses=[VALID_SKELETON_JSON])
        extractor = SkeletonExtractor(mock)
        skeleton = extractor.extract(_make_pdf_content(), _make_chapters())
        assert skeleton.subject == "physics"
        assert len(skeleton.chapters) == 3
        assert len(mock.calls) == 1

    def test_extract_with_subject_hint(self):
        mock = MockLLMProvider(responses=[VALID_SKELETON_JSON])
        extractor = SkeletonExtractor(mock)
        extractor.extract(_make_pdf_content(), _make_chapters(), subject_hint="physics")
        assert "physics" in mock.calls[0]["user"]

    def test_extract_retry_on_malformed_json(self):
        mock = MockLLMProvider(responses=["not json", VALID_SKELETON_JSON])
        extractor = SkeletonExtractor(mock)
        skeleton = extractor.extract(_make_pdf_content(), _make_chapters())
        assert skeleton.subject == "physics"
        assert len(mock.calls) == 2  # first failed, second succeeded

    def test_extract_raises_after_max_retries(self):
        mock = MockLLMProvider(responses=["bad json", "still bad"])
        extractor = SkeletonExtractor(mock)
        with pytest.raises(SkeletonExtractionError, match="invalid JSON"):
            extractor.extract(_make_pdf_content(), _make_chapters())

    def test_extract_no_chapters_raises(self):
        mock = MockLLMProvider()
        extractor = SkeletonExtractor(mock)
        with pytest.raises(SkeletonExtractionError, match="No chapters"):
            extractor.extract(_make_pdf_content(), [])

    def test_extract_round_trip(self):
        """Extracted skeleton serializes and deserializes correctly."""
        mock = MockLLMProvider(responses=[VALID_SKELETON_JSON])
        extractor = SkeletonExtractor(mock)
        skeleton = extractor.extract(_make_pdf_content(), _make_chapters())
        json_str = skeleton.model_dump_json()
        restored = BookSkeleton.model_validate_json(json_str)
        assert restored.textbook_title == skeleton.textbook_title
        assert len(restored.chapters) == len(skeleton.chapters)
