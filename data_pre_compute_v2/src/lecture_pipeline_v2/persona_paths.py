"""Persona path helpers for the v2 pipeline."""

from __future__ import annotations

from pathlib import Path


def default_personas_dir() -> Path:
    """Return data_pre_compute_v2/personas (sibling of src/)."""
    return Path(__file__).resolve().parents[2] / "personas"
