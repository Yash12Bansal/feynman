"""Application-level exceptions."""


class FeynmanError(Exception):
    """Base exception for all Feynman errors."""


class SessionNotFoundError(FeynmanError):
    """Raised when a teaching session is not found."""


class SessionAlreadyActiveError(FeynmanError):
    """Raised when trying to start a session that's already running."""


class StudentNotFoundError(FeynmanError):
    """Raised when a student is not found."""
