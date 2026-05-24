"""Application-level exceptions."""


class FeynmanError(Exception):
    """Base exception for all Feynman errors."""


class SessionNotFoundError(FeynmanError):
    """Raised when a teaching session is not found."""


class SessionAlreadyActiveError(FeynmanError):
    """Raised when trying to start a session that's already running."""


class StudentNotFoundError(FeynmanError):
    """Raised when a student is not found."""


class ToolConstraintError(FeynmanError):
    """Raised when an LLM tool call is rejected by orchestrator policy.

    The agent surfaces the message back to the LLM as a normal tool error so
    it can correct course (e.g. tick remaining checklist items, exit a doubt
    branch before advancing the lesson).
    """
