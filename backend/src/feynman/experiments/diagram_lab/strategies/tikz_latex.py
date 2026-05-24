# ruff: noqa: RUF001
"""TikZ-via-pdflatex strategy.

Claude writes a TikZ picture; we render through pdflatex → PDF → pdf2svg
and embed the resulting SVG into the spec under the testbed-only
`_tikz_svg` field. The testbed renderer mounts it directly.

Availability check runs at every `/strategies` fetch via `shutil.which`:
missing tools degrade to `available=False` instead of crashing. Install on
macOS via `brew install --cask mactex-no-gui` then `brew install pdf2svg`.

Why pdf2svg instead of dvisvgm: dvisvgm needs Ghostscript<10.01 or
mutool to convert from PDF, and current macOS Ghostscript is 10.07. PDF
mode via pdf2svg is a tiny brew formula (~150KB) with no transitive
dependency drama.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import ClassVar

from pydantic import Field

from feynman.agent.design_bridge import _MODELS, _get_client
from feynman.experiments.diagram_lab.strategies.base import (
    GenerationStrategy,
    StrategyAvailability,
    StrategyOptions,
    StrategyResult,
    TimingBreakdown,
)

_TIKZ_SYSTEM_PROMPT = r"""You are a TikZ expert teaching mathematics. Given a prompt, \
write a single TikZ picture that renders as a precise, beautiful diagram. The picture \
will be compiled with pdflatex and converted to SVG, then rendered on a dark classroom \
board.

## Output format

Return **only** the body of one `\begin{tikzpicture}...\end{tikzpicture}` block. \
No preamble, no `\documentclass`, no `\begin{document}`. No markdown fences, no prose. \
The runtime wraps your output in a standard preamble that already loads:
  - `tikz`, `pgfplots` (with `compat=1.18`)
  - libraries: `arrows.meta`, `calc`, `intersections`, `decorations.markings`, \
    `angles`, `quotes`, `patterns`, `positioning`
  - `amsmath`, `amssymb`

## Style

- Background is dark — use **light strokes**. Set default with the picture's first \
  line: `[every node/.style={text=white}, line cap=round]`.
- Default stroke color is `white!90!cyan` for primary geometry. Use these accents \
  consistently:
  - `cyan` — primary forces / velocities / highlighted shapes
  - `green!70` — correct values, key answers
  - `magenta!80` — callouts, important warnings
  - `yellow!70` — angles, measurements, dimensions
- Line widths: `thick` for the main subject, `thin` for axes/scaffolding.
- Label every meaningful point (`A`, `B`, `C`, `O`, `P`). Use `node[above]`, \
  `node[below right]`, etc.; place angle labels with `pic [angle radius=...]`.
- For graphs use `\begin{axis}[...]` from pgfplots.

## Coordinate budget

Aim for a final figure under roughly 12cm × 9cm — TikZ default units. Bigger figures \
get cropped; smaller ones look lost. If you set explicit ranges (e.g. on `axis`), \
prefer `width=10cm, height=7cm`.

## Examples of strong output (just the inner body)

Right triangle with marked angle:
```
[every node/.style={text=white}, line cap=round, thick]
\coordinate[label=above left:$A$] (A) at (0,4);
\coordinate[label=below left:$B$] (B) at (0,0);
\coordinate[label=below right:$C$] (C) at (5,0);
\draw[cyan] (A) -- (B) -- (C) -- cycle;
\draw[thin, white!50] (B) ++(0,0.4) -- ++(0.4,0) -- ++(0,-0.4);
\pic [draw=yellow!70, angle radius=0.8cm, "$\theta$" {yellow!70}] {angle=B--C--A};
```

Parabola y = x² with tangent at x=1 (note `axis` must be inside `tikzpicture`):
```
[every node/.style={text=white}]
\begin{axis}[
  width=10cm, height=7cm,
  axis lines=middle,
  axis line style={white!70},
  every axis label/.style={text=white},
  every tick label/.style={text=white!70},
  domain=-3:3, samples=80, samples y=1,
  ymin=-1, ymax=8,
]
  \addplot [cyan, thick] {x^2};
  \addplot [yellow!70, thick] {2*x - 1};
  \node[cyan] at (axis cs:2,5) {$y = x^2$};
  \node[yellow!70] at (axis cs:-1,5) {$y = 2x - 1$};
\end{axis}
```

**Important**: when using pgfplots' `\begin{axis}...\end{axis}`, it MUST appear inside a `\begin{tikzpicture}...\end{tikzpicture}` block. The runtime extractor wraps your output only if you forget to. Always include the wrapping `tikzpicture` yourself for safety.

Stop. Return the picture body only."""


_BASE_PREAMBLE = r"""\documentclass[border=4pt]{standalone}
\usepackage{tikz}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\usetikzlibrary{
  arrows.meta,
  calc,
  intersections,
  decorations.markings,
  angles,
  quotes,
  patterns,
  positioning,
}
\usepackage{amsmath}
\usepackage{amssymb}
\definecolor{boardbg}{HTML}{0A0A12}
\pagecolor{boardbg}
\begin{document}
"""

_BASE_POSTAMBLE = r"""\end{document}"""

_VIEWBOX_RE = re.compile(r'viewBox=["\']([\d\.\-\s]+)["\']', re.IGNORECASE)
_WIDTH_RE = re.compile(r'\swidth=["\']([\d\.]+)pt["\']', re.IGNORECASE)
_HEIGHT_RE = re.compile(r'\sheight=["\']([\d\.]+)pt["\']', re.IGNORECASE)
_FENCE_RE = re.compile(r"```(?:latex|tex|tikz)?\s*\n?(.*?)\n?```", re.DOTALL)


def _extract_tikz(text: str) -> str:
    """Strip optional code fences; ensure the result is wrapped in tikzpicture.

    pgfplots' `axis` env must live inside `tikzpicture`. The prompt's bad
    early example let Claude emit bare `\\begin{axis}` blocks, so we wrap
    them defensively here instead of relying on prompt discipline alone.
    """
    match = _FENCE_RE.search(text)
    if match:
        text = match.group(1).strip()
    body_match = re.search(
        r"\\begin\{tikzpicture\}(.*?)\\end\{tikzpicture\}",
        text,
        re.DOTALL,
    )
    if body_match:
        return f"\\begin{{tikzpicture}}{body_match.group(1)}\\end{{tikzpicture}}"
    bare = text.strip()
    if not bare:
        return ""
    return f"\\begin{{tikzpicture}}\n{bare}\n\\end{{tikzpicture}}"


def _check_tools() -> StrategyAvailability:
    pdflatex = shutil.which("pdflatex")
    pdf2svg = shutil.which("pdf2svg")
    if not pdflatex:
        return StrategyAvailability(
            available=False,
            reason="pdflatex not on PATH. Install MacTeX or TeXLive.",
        )
    if not pdf2svg:
        return StrategyAvailability(
            available=False,
            reason="pdf2svg not on PATH. macOS: `brew install pdf2svg`.",
        )
    return StrategyAvailability(available=True)


async def _run(
    cmd: list[str],
    cwd: Path,
    timeout: float,  # noqa: ASYNC109 — explicit deadline as helper API
) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        raise
    return (
        proc.returncode if proc.returncode is not None else -1,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


async def _render_tikz_to_svg(
    tikz_body: str,
    *,
    pdflatex_timeout: float,
    converter_timeout: float,
) -> tuple[str, str]:
    """Returns (svg_markup, latex_log_tail). Raises ValueError on compile failure.

    Pipeline: pdflatex → PDF → pdf2svg → SVG. We use the PDF path instead of
    DVI→dvisvgm because dvisvgm on macOS needs Ghostscript<10.01 or mutool —
    both awkward dependencies. pdf2svg via brew is 150KB and just works.
    """
    with tempfile.TemporaryDirectory(prefix="tikz_lab_") as tmpdir:
        tmppath = Path(tmpdir)
        tex_file = tmppath / "diagram.tex"
        tex_file.write_text(_BASE_PREAMBLE + tikz_body + "\n" + _BASE_POSTAMBLE)

        rc, out, err = await _run(
            [
                "pdflatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "diagram.tex",
            ],
            cwd=tmppath,
            timeout=pdflatex_timeout,
        )
        if rc != 0:
            tail = (out + err).splitlines()[-25:]
            raise ValueError("pdflatex failed:\n" + "\n".join(tail))

        pdf_file = tmppath / "diagram.pdf"
        if not pdf_file.exists():
            raise ValueError("pdflatex produced no PDF output (unexpected).")

        rc, out, err = await _run(
            ["pdf2svg", "diagram.pdf", "diagram.svg"],
            cwd=tmppath,
            timeout=converter_timeout,
        )
        if rc != 0:
            raise ValueError("pdf2svg failed:\n" + (out + err)[-1200:])

        svg_file = tmppath / "diagram.svg"
        if not svg_file.exists():
            raise ValueError("pdf2svg produced no SVG output (unexpected).")
        svg_markup = svg_file.read_text(encoding="utf-8")

        log_path = tmppath / "diagram.log"
        log_tail = ""
        if log_path.exists():
            log_tail = "\n".join(log_path.read_text(errors="replace").splitlines()[-20:])
        return svg_markup, log_tail


def _strip_xml_decl(svg: str) -> str:
    return re.sub(r"<\?xml[^>]*\?>\s*", "", svg, count=1).strip()


def _svg_dimensions(svg: str) -> tuple[float, float]:
    vb = _VIEWBOX_RE.search(svg)
    if vb:
        parts = vb.group(1).split()
        if len(parts) == 4:
            return float(parts[2]), float(parts[3])
    w = _WIDTH_RE.search(svg)
    h = _HEIGHT_RE.search(svg)
    if w and h:
        return float(w.group(1)), float(h.group(1))
    return 900.0, 650.0


class TikzLatexOptions(StrategyOptions):
    max_tokens: int = Field(default=4000, ge=500, le=16000)
    temperature: float = Field(default=1.0, ge=0.0, le=1.0)
    pdflatex_timeout_s: float = Field(default=15.0, ge=2.0, le=60.0)
    converter_timeout_s: float = Field(default=10.0, ge=2.0, le=30.0)


class TikzLatexStrategy(GenerationStrategy):
    id = "tikz_latex"
    display_name = "TikZ → pdflatex → SVG"
    description = (
        "Claude writes TikZ; pdflatex compiles it; dvisvgm rasterizes to SVG. "
        "Highest-fidelity math output (pgfplots, axes, intersections, calc) but "
        "slow (extra render pass) and depends on a TeX install."
    )
    category = "latex"
    supports_models: ClassVar[list[str]] = ["opus", "sonnet", "haiku"]
    default_model = "sonnet"
    options_model = TikzLatexOptions

    def availability(self) -> StrategyAvailability:
        return _check_tools()

    async def generate(
        self,
        prompt: str,
        model: str,
        options: StrategyOptions,
    ) -> StrategyResult:
        assert isinstance(options, TikzLatexOptions)
        avail = self.availability()
        if not avail.available:
            raise ValueError(f"tikz_latex unavailable: {avail.reason}")

        model_id = _MODELS.get(model, model)
        client = _get_client()

        t_start = time.perf_counter()
        first_token_at: float | None = None
        accumulated = ""

        async with client.messages.stream(
            model=model_id,
            max_tokens=options.max_tokens,
            temperature=options.temperature,
            system=_TIKZ_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                accumulated += text
            final = await stream.get_final_message()

        t_llm_done = time.perf_counter()
        tikz_body = _extract_tikz(accumulated)
        if not tikz_body:
            raise ValueError("tikz_latex: model returned no TikZ source.")

        svg_markup, log_tail = await _render_tikz_to_svg(
            tikz_body,
            pdflatex_timeout=options.pdflatex_timeout_s,
            converter_timeout=options.converter_timeout_s,
        )
        t_render_done = time.perf_counter()

        svg_clean = _strip_xml_decl(svg_markup)
        width, height = _svg_dimensions(svg_clean)

        spec = {
            "title": (prompt[:60] + ("…" if len(prompt) > 60 else "")),
            "description": "Rendered via TikZ → pdflatex → dvisvgm.",
            "width": round(width),
            "height": round(height),
            "backgroundColor": "transparent",
            "elements": [],
            "parameters": [],
            "animations": [],
            "dictionary": {},
            "_tikz_svg": svg_clean,
            "_tikz_source": tikz_body,
        }

        warnings: list[str] = []
        if final.stop_reason == "max_tokens":
            warnings.append(f"TikZ response truncated at max_tokens={options.max_tokens}.")

        usage = final.usage
        metadata = {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "tikz_chars": len(tikz_body),
            "svg_chars": len(svg_clean),
            "svg_width": width,
            "svg_height": height,
            "pdflatex_log_tail": log_tail,
        }

        return StrategyResult(
            spec=spec,
            raw_output=tikz_body,
            prompt_used=_TIKZ_SYSTEM_PROMPT,
            model_used=model_id,
            timing=TimingBreakdown(
                total_ms=(t_render_done - t_start) * 1000,
                first_token_ms=((first_token_at - t_start) * 1000) if first_token_at else None,
                llm_ms=(t_llm_done - t_start) * 1000,
                render_ms=(t_render_done - t_llm_done) * 1000,
            ),
            metadata=metadata,
            warnings=warnings,
        )


__all__ = ["TikzLatexStrategy"]
