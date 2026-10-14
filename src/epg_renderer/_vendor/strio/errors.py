"""Exception hierarchy for STRio.

Every error raised for unreadable or invalid input derives from :class:`ParseError`,
which itself derives from :class:`ValueError`. Callers can therefore catch one class
for "this file cannot be used" and still distinguish the cause when they need to.
"""

from __future__ import annotations


class StrioError(ValueError):
    """Base class of every error raised by STRio."""


class ParseError(StrioError):
    """Raised when an input file is unreadable, malformed or unsupported."""


class MissingColumnError(ParseError):
    """Raised when a required source column is absent."""


class DuplicateColumnError(ParseError):
    """Raised when two columns have the same or a semantically identical name."""


class DuplicateLocusError(ParseError):
    """Raised when one sample contains the same marker row twice."""


class NumericValueError(ParseError):
    """Raised when an exported numeric value is malformed or out of range."""


class InconsistentExtraError(StrioError):
    """Raised when a sample-level value is requested but the rows disagree."""


__all__ = [
    "DuplicateColumnError",
    "DuplicateLocusError",
    "InconsistentExtraError",
    "MissingColumnError",
    "NumericValueError",
    "ParseError",
    "StrioError",
]
