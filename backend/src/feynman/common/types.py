"""Shared type aliases and enums."""

from enum import StrEnum
from uuid import UUID

SessionId = UUID
StudentId = UUID


class Subject(StrEnum):
    MATH = "math"
    PHYSICS = "physics"
    CHEMISTRY = "chemistry"
    BIOLOGY = "biology"


class LLMProvider(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
