"""Headless-browser measurement service for notebook blocks (Phase 3).

The pre-compute pipeline cannot trust LLM judgment to decide when a notebook
panel will overflow — it needs measured dimensions for every block at the
exact CSS the frontend renders. This module wraps Playwright to provide that
measurement, with an on-disk cache keyed by content + CSS hash so re-runs
don't re-launch a browser for the same content.

The cache key includes a SHA256 of `SplitBoard.css` content — any CSS edit
auto-invalidates measurements, avoiding silent visual drift.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Literal

from lecture_pipeline_v2.config import LayoutConfig

logger = logging.getLogger(__name__)


BlockType = Literal["SECTION", "EQUATION", "STEP", "KEY", "TEXT", "ANSWER"]
_ALLOWED_BLOCK_TYPES: frozenset[str] = frozenset(
    {"SECTION", "EQUATION", "STEP", "KEY", "TEXT", "ANSWER"}
)


class MeasurementService:
    """Owns one Chromium browser + a content-hashed cache.

    Lifecycle: construct → optionally `await start()` to launch the browser →
    call `await measure(...)` per block → `await stop()` when done. May also
    be used as an async context manager (`async with svc:`). Cache hits do
    not require the browser to be running, so cache-only mode works even
    without `start()`.
    """

    def __init__(self, layout_config: LayoutConfig, cache_dir: Path | str) -> None:
        self._config = layout_config
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        # Compute css_hash eagerly so cache lookups work without start().
        # Hash combines SplitBoard.css AND measurement_page.html — any edit
        # to either invalidates cache (catches drift between them too).
        css_path = Path(self._config.measurement.css_hash_path).resolve()
        if not css_path.exists():
            raise FileNotFoundError(
                f"MeasurementService: CSS file not found at "
                f"{css_path} (configure layout.measurement.css_hash_path)"
            )
        hasher = hashlib.sha256()
        hasher.update(css_path.read_bytes())
        page_path = Path(self._config.measurement.page_path).resolve()
        if page_path.exists():
            hasher.update(b"\x00")  # separator
            hasher.update(page_path.read_bytes())
        self._css_hash = hasher.hexdigest()
        self._css_path = css_path

        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._page: Any | None = None
        self._started = False
        self._cache_hits = 0
        self._cache_misses = 0
        self._eval_failures = 0

    @property
    def css_hash(self) -> str:
        return self._css_hash

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    @property
    def started(self) -> bool:
        return self._started

    @property
    def report(self) -> dict[str, int]:
        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "eval_failures": self._eval_failures,
        }

    async def start(self) -> None:
        if self._started:
            return
        page_path = Path(self._config.measurement.page_path).resolve()
        if not page_path.exists():
            raise FileNotFoundError(
                f"MeasurementService: measurement page not found at "
                f"{page_path} (configure layout.measurement.page_path)"
            )

        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise RuntimeError(
                "MeasurementService requires playwright. Install with "
                "`poetry install --with dev` and `poetry run playwright install chromium`."
            ) from e

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        viewport = {
            "width": self._config.viewport.width,
            "height": self._config.viewport.height,
        }
        context = await self._browser.new_context(viewport=viewport)
        self._page = await context.new_page()
        await self._page.goto(f"file://{page_path}")
        # The page exposes `window.measureBlock` synchronously AND KaTeX
        # via external script. Wait for both before declaring ready.
        await self._page.wait_for_function(
            "typeof window.measureBlock === 'function' && typeof window.katex !== 'undefined'",
            timeout=15_000,
        )
        self._started = True
        logger.info(
            "MeasurementService started",
            extra={"css_hash_short": self._css_hash[:8], "page": str(page_path)},
        )

    async def stop(self) -> None:
        if not self._started:
            return
        try:
            if self._browser is not None:
                await self._browser.close()
            if self._playwright is not None:
                await self._playwright.stop()
        finally:
            self._started = False
            self._browser = None
            self._page = None
            self._playwright = None
            logger.info(
                "MeasurementService stopped",
                extra={
                    "cache_hits": self._cache_hits,
                    "cache_misses": self._cache_misses,
                    "eval_failures": self._eval_failures,
                },
            )

    async def __aenter__(self) -> MeasurementService:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()

    def _cache_key(
        self, block_type: str, content: str, attrs: dict[str, Any], width_px: float
    ) -> str:
        payload = "|".join(
            [
                block_type,
                content,
                json.dumps(attrs, sort_keys=True, ensure_ascii=False),
                str(int(width_px)),
                self._css_hash,
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def measure(
        self,
        block_type: BlockType,
        content: str,
        attrs: dict[str, Any] | None = None,
        width_px: float | None = None,
    ) -> dict[str, float]:
        """Return measured `{width, height}` in pixels.

        Cache-first: a hit avoids launching the browser. On miss, requires
        `start()` to have been called. `attrs` is the per-block-type attribute
        bundle (e.g., `{indent: 1}` for STEP). `width_px` defaults to the
        configured block_default_widths.
        """
        if block_type not in _ALLOWED_BLOCK_TYPES:
            raise ValueError(
                f"Unknown block_type: {block_type!r}. "
                f"Expected one of {sorted(_ALLOWED_BLOCK_TYPES)}."
            )
        attrs = attrs or {}
        if width_px is None:
            width_px = float(self._config.block_default_widths.get(block_type, 540))

        key = self._cache_key(block_type, content, attrs, width_px)
        cache_file = self._cache_dir / f"{key}.json"

        if cache_file.exists():
            self._cache_hits += 1
            with cache_file.open(encoding="utf-8") as f:
                data = json.load(f)
            return {"width": float(data["width"]), "height": float(data["height"])}

        if not self._started:
            raise RuntimeError(
                f"MeasurementService.measure(): cache miss for {block_type!r} "
                "but browser is not started. Call start() first."
            )

        result = await self._measure_via_browser(block_type, content, attrs, width_px)
        self._cache_misses += 1

        # Persist atomically (write to tmp then rename) to avoid partial files
        # if the process is killed mid-measurement.
        tmp = cache_file.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(result, f)
        tmp.replace(cache_file)
        return result

    async def _measure_via_browser(
        self,
        block_type: str,
        content: str,
        attrs: dict[str, Any],
        width_px: float,
    ) -> dict[str, float]:
        """Internal: dispatch to window.measureBlock. Tests monkeypatch this."""
        assert self._page is not None
        try:
            result = await self._page.evaluate(
                "args => window.measureBlock(args)",
                {
                    "type": block_type,
                    "content": content,
                    "attrs": attrs,
                    "width": float(width_px),
                },
            )
        except Exception as e:
            self._eval_failures += 1
            logger.warning(
                "MeasurementService.evaluate failed",
                extra={"block_type": block_type, "error": str(e)},
            )
            raise
        return {"width": float(result["width"]), "height": float(result["height"])}
