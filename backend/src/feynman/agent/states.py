"""Teaching state definitions for the state machine."""

from enum import StrEnum


class TeachingState(StrEnum):
    """States in the teaching state machine."""

    IDLE = "idle"
    GREETING = "greeting"
    TEACHING = "teaching"
    ASKING_QUESTION = "asking_question"
    WAITING_FOR_RESPONSE = "waiting_for_response"
    HANDLING_DOUBT = "handling_doubt"
    SOLVING_PROBLEM = "solving_problem"
    SUMMARIZING = "summarizing"
    ENDING = "ending"
