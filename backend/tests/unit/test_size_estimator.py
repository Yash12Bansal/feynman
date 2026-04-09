"""Tests for the pre-render size estimator."""

import pytest

from feynman.agent.size_estimator import (
    SizeEstimate,
    estimate_design_diagram_size,
    estimate_diagram_size,
    estimate_equation_size,
    estimate_graph_size,
    estimate_scene_size,
    estimate_step_equation_size,
    estimate_text_size,
)

# Board bounds — estimates should never exceed these
_MAX_W = 1920
_MAX_H = 1080


class TestEquationSize:
    def test_simple_equation(self):
        size = estimate_equation_size("E = mc^2")
        assert 100 <= size.width <= 400
        assert 50 <= size.height <= 200
        assert 0 < size.confidence <= 1

    def test_fraction_increases_height(self):
        simple = estimate_equation_size("x + y")
        frac = estimate_equation_size("\\frac{a}{b}")
        assert frac.height > simple.height

    def test_nested_fractions(self):
        single = estimate_equation_size("\\frac{a}{b}")
        nested = estimate_equation_size("\\frac{\\frac{a}{b}}{c}")
        assert nested.height > single.height

    def test_sqrt_increases_height(self):
        simple = estimate_equation_size("x + y")
        sqrt = estimate_equation_size("\\sqrt{x^2 + y^2}")
        assert sqrt.height > simple.height

    def test_multiline_equation(self):
        single = estimate_equation_size("x = 1")
        multi = estimate_equation_size("x = 1 \\\\ y = 2 \\\\ z = 3")
        assert multi.height > single.height

    def test_width_capped(self):
        long_eq = "a + b + c + d + e + f + g + h + i + j + k + l + m + n + o + p + q + r + s + t + u + v + w + x + y + z"
        size = estimate_equation_size(long_eq)
        assert size.width <= 800

    def test_minimum_width(self):
        size = estimate_equation_size("x")
        assert size.width >= 100

    def test_area_positive(self):
        size = estimate_equation_size("E = mc^2")
        assert size.area > 0


class TestTextSize:
    def test_short_text(self):
        size = estimate_text_size("Hello world")
        assert 100 <= size.width <= 600
        assert 30 <= size.height <= 200

    def test_title_increases_height(self):
        no_title = estimate_text_size("Some body text")
        with_title = estimate_text_size("Some body text", title="Key Concept")
        assert with_title.height > no_title.height

    def test_long_text_wraps(self):
        short = estimate_text_size("Short text.")
        long_text = "This is a much longer text that should wrap across multiple lines and therefore be taller than a short text block."
        long = estimate_text_size(long_text)
        assert long.height > short.height

    def test_reasonable_bounds(self):
        size = estimate_text_size("A paragraph of content for the board.")
        assert size.width <= _MAX_W
        assert size.height <= _MAX_H

    def test_confidence(self):
        size = estimate_text_size("Test")
        assert 0 < size.confidence <= 1


class TestDiagramSize:
    @pytest.mark.parametrize("complexity", ["small", "medium", "large", "full"])
    def test_valid_complexities(self, complexity: str):
        size = estimate_diagram_size(complexity)
        assert size.width > 0
        assert size.height > 0
        assert size.width <= _MAX_W
        assert size.height <= _MAX_H

    def test_larger_complexity_bigger(self):
        small = estimate_diagram_size("small")
        large = estimate_diagram_size("large")
        assert large.area > small.area

    def test_unknown_complexity_defaults(self):
        size = estimate_diagram_size("unknown")
        medium = estimate_diagram_size("medium")
        assert size.width == medium.width
        assert size.height == medium.height


class TestDesignDiagramSize:
    def test_short_prompt_small(self):
        size = estimate_design_diagram_size("Draw a simple arrow")
        small = estimate_diagram_size("small")
        assert size.width == small.width

    def test_long_prompt_large(self):
        long_prompt = " ".join(["word"] * 50)
        size = estimate_design_diagram_size(long_prompt)
        large = estimate_diagram_size("large")
        assert size.width == large.width

    def test_medium_prompt(self):
        mid_prompt = " ".join(["word"] * 30)
        size = estimate_design_diagram_size(mid_prompt)
        medium = estimate_diagram_size("medium")
        assert size.width == medium.width


class TestGraphSize:
    def test_single_series(self):
        size = estimate_graph_size(1)
        assert 300 <= size.width <= 700
        assert 200 <= size.height <= 500

    def test_many_series_wider(self):
        one = estimate_graph_size(1)
        many = estimate_graph_size(5)
        assert many.width > one.width


class TestSceneSize:
    def test_few_elements_small(self):
        size = estimate_scene_size(2)
        small = estimate_diagram_size("small")
        assert size.width == small.width

    def test_many_elements_large(self):
        size = estimate_scene_size(10)
        large = estimate_diagram_size("large")
        assert size.width == large.width


class TestStepEquationSize:
    def test_height_scales_with_steps(self):
        few = estimate_step_equation_size(2)
        many = estimate_step_equation_size(8)
        assert many.height > few.height

    def test_reasonable_bounds(self):
        size = estimate_step_equation_size(5)
        assert size.width > 0
        assert size.height > 0
        assert size.width <= _MAX_W

    def test_confidence(self):
        size = estimate_step_equation_size(3)
        assert 0 < size.confidence <= 1
