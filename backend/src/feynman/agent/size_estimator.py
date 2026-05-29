# TODO(DEADCODE): file unused in active pipelines (precompute-gen / lecture-playback / ask-feynman) — interactive live-teaching subsystem (parked). See docs/engineering/13-redundant-code-audit.md Group 2. Safe to delete.
# """Pre-render size estimates for visual elements.

# Estimates how big an equation, text block, diagram, etc. will be
# when rendered on the 1920x1080 board. Not pixel-perfect — within
# ~20% is sufficient for the spatial solver to make placement decisions.
# The frontend reports actual bounds after render.
# """

# from __future__ import annotations

# from dataclasses import dataclass


# @dataclass(frozen=True)
# class SizeEstimate:
#     """Estimated rendered dimensions in board space (1920x1080)."""

#     width: float
#     height: float
#     confidence: float  # 0-1, how reliable this estimate is

#     @property
#     def area(self) -> float:
#         return self.width * self.height


# # ── KaTeX size estimation ────────────────────────────────────────
# # Based on empirical measurements of KaTeX rendered output at
# # the font sizes and board dimensions we use.

# _KATEX_CHAR_WIDTH = 14.0  # avg width per character (board px)
# _KATEX_LINE_HEIGHT = 50.0  # single-line equation height
# _KATEX_FRAC_BONUS = 30.0  # extra height per fraction level
# _KATEX_SQRT_BONUS = 15.0  # extra height for sqrt
# _KATEX_MIN_WIDTH = 100.0
# _KATEX_MAX_WIDTH = 800.0
# _KATEX_PADDING = 40.0  # visual padding around equation


# def estimate_equation_size(latex: str) -> SizeEstimate:
#     """Estimate rendered size of a KaTeX equation.

#     Not pixel-perfect — within ~20% is sufficient for placement
#     decisions. The frontend will report actual bounds after render.
#     """
#     # Strip LaTeX commands for character counting
#     stripped = latex
#     for cmd in (
#         "\\frac",
#         "\\sqrt",
#         "\\sum",
#         "\\int",
#         "\\prod",
#         "\\left",
#         "\\right",
#         "\\htmlId",
#         "\\text",
#     ):
#         stripped = stripped.replace(cmd, "")
#     # Remove braces
#     stripped = stripped.replace("{", "").replace("}", "")

#     char_count = len(stripped)
#     width = min(
#         max(char_count * _KATEX_CHAR_WIDTH + _KATEX_PADDING, _KATEX_MIN_WIDTH),
#         _KATEX_MAX_WIDTH,
#     )

#     # Height: base + fraction nesting + sqrt
#     height = _KATEX_LINE_HEIGHT
#     frac_depth = latex.count("\\frac")
#     if frac_depth > 0:
#         height += frac_depth * _KATEX_FRAC_BONUS
#     if "\\sqrt" in latex:
#         height += _KATEX_SQRT_BONUS
#     # Multi-line (aligned environments)
#     newlines = latex.count("\\\\")
#     if newlines > 0:
#         height += newlines * _KATEX_LINE_HEIGHT * 0.8

#     height += _KATEX_PADDING

#     return SizeEstimate(width=width, height=height, confidence=0.7)


# # ── Text size estimation ─────────────────────────────────────────

# _TEXT_CHAR_WIDTH = 10.0
# _TEXT_LINE_HEIGHT = 28.0
# _TEXT_TITLE_HEIGHT = 36.0
# _TEXT_MAX_WIDTH = 500.0
# _TEXT_PADDING = 32.0


# def estimate_text_size(text: str, title: str = "") -> SizeEstimate:
#     """Estimate rendered size of a text block."""
#     max_line_width = _TEXT_MAX_WIDTH
#     words = text.split()
#     lines = 1
#     current_width = 0.0
#     for word in words:
#         word_width = len(word) * _TEXT_CHAR_WIDTH
#         if current_width + word_width > max_line_width and current_width > 0:
#             lines += 1
#             current_width = word_width
#         else:
#             current_width += word_width + _TEXT_CHAR_WIDTH  # space

#     height = lines * _TEXT_LINE_HEIGHT + _TEXT_PADDING
#     if title:
#         height += _TEXT_TITLE_HEIGHT
#     width = min(max(len(text) * _TEXT_CHAR_WIDTH, 200), max_line_width) + _TEXT_PADDING

#     return SizeEstimate(width=width, height=height, confidence=0.75)


# # ── Diagram size estimation ──────────────────────────────────────

# _DIAGRAM_SIZES: dict[str, tuple[float, float]] = {
#     "small": (300, 250),
#     "medium": (500, 400),
#     "large": (700, 550),
#     "full": (900, 650),
# }


# def estimate_diagram_size(complexity: str = "medium") -> SizeEstimate:
#     """Estimate diagram size from complexity hint.

#     complexity: "small", "medium", "large", "full"
#     """
#     w, h = _DIAGRAM_SIZES.get(complexity, _DIAGRAM_SIZES["medium"])
#     return SizeEstimate(width=w, height=h, confidence=0.5)


# def estimate_design_diagram_size(prompt: str) -> SizeEstimate:
#     """Estimate design agent diagram size from prompt complexity."""
#     word_count = len(prompt.split())
#     if word_count > 40:
#         return estimate_diagram_size("large")
#     elif word_count > 20:
#         return estimate_diagram_size("medium")
#     return estimate_diagram_size("small")


# def estimate_graph_size(series_count: int = 1) -> SizeEstimate:
#     """Estimate chart/graph rendered size."""
#     base_w, base_h = 500, 350
#     if series_count > 2:
#         base_w += 100
#     return SizeEstimate(width=base_w, height=base_h, confidence=0.7)


# def estimate_scene_size(element_count: int = 3) -> SizeEstimate:
#     """Estimate draw_scene component diagram size."""
#     if element_count > 6:
#         return estimate_diagram_size("large")
#     elif element_count > 3:
#         return estimate_diagram_size("medium")
#     return estimate_diagram_size("small")


# def estimate_step_equation_size(step_count: int = 3) -> SizeEstimate:
#     """Estimate step-by-step equation derivation size."""
#     width = 450.0
#     height = step_count * 65.0 + 60.0  # per step + header
#     return SizeEstimate(width=width, height=height, confidence=0.65)
