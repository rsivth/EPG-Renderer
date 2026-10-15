"""Structured, non-fatal findings reported while reading a file."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DiagnosticCode(str, Enum):
    """Stable machine-readable identifiers of non-fatal reader findings."""

    TRAILING_EMPTY_COLUMNS = "trailing-empty-columns"
    """Empty, unnamed columns at the end of the header were ignored."""

    ALLELE_DISPLAY_OVERFLOW = "allele-display-overflow"
    """GeneMapper flagged that more alleles existed than columns were exported."""

    HIGHEST_ALLELE_COLUMN_USED = "highest-allele-column-used"
    """The last exported allele column is filled; the export may be truncated."""


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One non-fatal finding with a stable code, a readable message and source lines.

    ``str(diagnostic)`` returns the message, so diagnostics can be shown wherever plain
    text warnings were shown before.
    """

    code: DiagnosticCode
    message: str
    lines: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.code, DiagnosticCode):
            raise TypeError("code must be a DiagnosticCode value.")
        if not isinstance(self.message, str):
            raise TypeError(f"message must be a str, not {type(self.message).__name__}.")
        message = self.message.strip()
        if not message:
            raise ValueError("message must not be empty.")
        lines = tuple(self.lines)
        if any(isinstance(line, bool) or not isinstance(line, int) or line < 1 for line in lines):
            raise ValueError("lines must be positive integers.")
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "lines", lines)

    def __str__(self) -> str:
        return self.message


__all__ = ["Diagnostic", "DiagnosticCode"]
