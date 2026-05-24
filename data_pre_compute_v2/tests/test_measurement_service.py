"""Tests for MeasurementService (Phase 3) — no real Playwright launch.

Strategy: monkeypatch `_measure_via_browser` to return deterministic dims.
The browser layer is tested by hand in Step 4's eyeball check. These tests
verify cache behavior, key stability, and error paths.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lecture_pipeline_v2.config import LayoutConfig, MeasurementConfig
from lecture_pipeline_v2.curriculum.manifest_composer.measurement import (
    MeasurementService,
)


def _make_layout(
    tmp_path: Path, css_content: bytes = b"body { color: red; }"
) -> LayoutConfig:
    """Build a LayoutConfig pointing at tmp_path fixtures."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    css_file = tmp_path / "fake.css"
    css_file.write_bytes(css_content)
    page_file = tmp_path / "fake.html"
    page_file.write_text(
        "<html><body><script>window.measureBlock=()=>({width:0,height:0});</script></body></html>"
    )
    cache_dir = tmp_path / "cache"
    return LayoutConfig(
        measurement=MeasurementConfig(
            css_hash_path=str(css_file),
            page_path=str(page_file),
            cache_dir=str(cache_dir),
        ),
    )


def test_init_computes_css_hash(tmp_path: Path):
    """Hash combines SplitBoard.css + measurement_page.html so drift in
    either file invalidates the cache."""
    import hashlib

    cfg = _make_layout(tmp_path, css_content=b"hello")
    svc = MeasurementService(cfg, tmp_path / "cache")
    # Recompute expected: sha256(css_bytes + sep + page_bytes)
    css_bytes = b"hello"
    page_bytes = (tmp_path / "fake.html").read_bytes()
    expected = hashlib.sha256()
    expected.update(css_bytes)
    expected.update(b"\x00")
    expected.update(page_bytes)
    assert svc.css_hash == expected.hexdigest()
    # And it's stable: a fresh instance over the same files matches.
    svc2 = MeasurementService(cfg, tmp_path / "cache")
    assert svc2.css_hash == svc.css_hash


def test_init_missing_css_file_raises(tmp_path: Path):
    cfg = LayoutConfig(
        measurement=MeasurementConfig(
            css_hash_path=str(tmp_path / "does_not_exist.css"),
        ),
    )
    with pytest.raises(FileNotFoundError, match="CSS file not found"):
        MeasurementService(cfg, tmp_path / "cache")


def test_cache_key_stable(tmp_path: Path):
    cfg = _make_layout(tmp_path)
    svc = MeasurementService(cfg, tmp_path / "cache")
    k1 = svc._cache_key("EQUATION", "E=mc^2", {"boxed": True}, 540)
    k2 = svc._cache_key("EQUATION", "E=mc^2", {"boxed": True}, 540)
    assert k1 == k2
    # Different attrs → different key
    k3 = svc._cache_key("EQUATION", "E=mc^2", {"boxed": False}, 540)
    assert k1 != k3
    # Different content → different key
    k4 = svc._cache_key("EQUATION", "F=ma", {"boxed": True}, 540)
    assert k1 != k4
    # Different width → different key
    k5 = svc._cache_key("EQUATION", "E=mc^2", {"boxed": True}, 600)
    assert k1 != k5


def test_attrs_order_does_not_affect_key(tmp_path: Path):
    """Attr dict ordering must not influence the cache key (json sorted)."""
    cfg = _make_layout(tmp_path)
    svc = MeasurementService(cfg, tmp_path / "cache")
    k1 = svc._cache_key("STEP", "x", {"a": 1, "b": 2}, 520)
    k2 = svc._cache_key("STEP", "x", {"b": 2, "a": 1}, 520)
    assert k1 == k2


def test_css_change_invalidates_key(tmp_path: Path):
    cfg_a = _make_layout(tmp_path / "a", css_content=b"old")
    cfg_b = _make_layout(tmp_path / "b", css_content=b"new")
    svc_a = MeasurementService(cfg_a, tmp_path / "a" / "cache")
    svc_b = MeasurementService(cfg_b, tmp_path / "b" / "cache")
    assert svc_a.css_hash != svc_b.css_hash
    k_a = svc_a._cache_key("TEXT", "hi", {}, 540)
    k_b = svc_b._cache_key("TEXT", "hi", {}, 540)
    assert k_a != k_b


@pytest.mark.asyncio
async def test_cache_hit_skips_browser(tmp_path: Path):
    """A pre-existing cache file should be returned without starting browser."""
    cfg = _make_layout(tmp_path)
    svc = MeasurementService(cfg, tmp_path / "cache")
    # Seed cache
    key = svc._cache_key("EQUATION", "E=mc^2", {}, 540)
    cache_file = svc.cache_dir / f"{key}.json"
    cache_file.write_text(json.dumps({"width": 200.0, "height": 60.0}))

    # Measure without starting browser — should still succeed via cache
    result = await svc.measure("EQUATION", "E=mc^2", {}, 540)
    assert result == {"width": 200.0, "height": 60.0}
    assert svc.report["cache_hits"] == 1
    assert svc.report["cache_misses"] == 0


@pytest.mark.asyncio
async def test_cache_miss_without_start_raises(tmp_path: Path):
    cfg = _make_layout(tmp_path)
    svc = MeasurementService(cfg, tmp_path / "cache")
    with pytest.raises(RuntimeError, match="not started"):
        await svc.measure("EQUATION", "E=mc^2", {}, 540)


@pytest.mark.asyncio
async def test_cache_miss_writes_file(tmp_path: Path, monkeypatch):
    cfg = _make_layout(tmp_path)
    svc = MeasurementService(cfg, tmp_path / "cache")

    async def fake_eval(block_type, content, attrs, width_px):
        return {"width": 540.0, "height": 88.5}

    monkeypatch.setattr(svc, "_measure_via_browser", fake_eval)
    svc._started = True  # bypass start() so cache miss runs the fake

    result = await svc.measure("STEP", "Compute opposite", {"indent": 1}, 520)
    assert result == {"width": 540.0, "height": 88.5}
    # Verify file was written
    key = svc._cache_key("STEP", "Compute opposite", {"indent": 1}, 520)
    assert (svc.cache_dir / f"{key}.json").exists()
    assert svc.report["cache_misses"] == 1

    # Second call should hit cache, not browser
    monkeypatch.setattr(
        svc,
        "_measure_via_browser",
        lambda *a, **kw: pytest.fail("should not call browser on hit"),
    )
    result2 = await svc.measure("STEP", "Compute opposite", {"indent": 1}, 520)
    assert result2 == {"width": 540.0, "height": 88.5}
    assert svc.report["cache_hits"] == 1


@pytest.mark.asyncio
async def test_unknown_block_type_raises(tmp_path: Path):
    cfg = _make_layout(tmp_path)
    svc = MeasurementService(cfg, tmp_path / "cache")
    with pytest.raises(ValueError, match="Unknown block_type"):
        await svc.measure("UNKNOWN", "x", {}, 540)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_default_width_from_config(tmp_path: Path, monkeypatch):
    """If width_px omitted, falls back to LayoutConfig.block_default_widths."""
    cfg = _make_layout(tmp_path)
    svc = MeasurementService(cfg, tmp_path / "cache")
    captured: dict = {}

    async def fake_eval(block_type, content, attrs, width_px):
        captured["width"] = width_px
        return {"width": width_px, "height": 30.0}

    monkeypatch.setattr(svc, "_measure_via_browser", fake_eval)
    svc._started = True

    await svc.measure("STEP", "x", {})
    # STEP's default width is 520
    assert captured["width"] == 520.0
