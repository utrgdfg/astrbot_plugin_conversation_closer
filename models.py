"""Core data models for Conversation Closer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class Decision(StrEnum):
    """The only decisions accepted from the judge model."""

    END = "END"
    CONTINUE = "CONTINUE"
    UNCERTAIN = "UNCERTAIN"


@dataclass(frozen=True, slots=True)
class HistoryMessage:
    """One bounded, text-only entry in a session history."""

    role: Literal["user", "assistant"]
    content: str
    timestamp: float


@dataclass(frozen=True, slots=True)
class JudgeResult:
    """Strictly validated output from the independent judge model."""

    decision: Decision
    confidence: float
    reason: str
    elapsed_seconds: float = 0.0
    error_code: str | None = None

    @classmethod
    def fail_open(
        cls,
        reason: str,
        *,
        error_code: str,
        elapsed_seconds: float = 0.0,
    ) -> JudgeResult:
        """Return a non-blocking result for every failure path."""

        return cls(
            decision=Decision.UNCERTAIN,
            confidence=0.0,
            reason=reason,
            elapsed_seconds=elapsed_seconds,
            error_code=error_code,
        )
