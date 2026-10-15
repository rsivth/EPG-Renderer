"""Interpretation of exported allele labels.

An exported allele label stays the authoritative source text. :class:`AlleleValue` is a
derived, conservative reading of that text for consumers that need to compare or sort
alleles, for example statistics modules. Anything that is not unambiguously a repeat
number, ``X``, ``Y`` or an off-ladder call is classified as :attr:`AlleleKind.OTHER`
instead of being guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

_NUMERIC_RE = re.compile(r"(?P<full>[0-9]+)(?:\.(?P<partial>[0-9]))?")


class AlleleKind(str, Enum):
    """Category of an exported allele label."""

    NUMERIC = "numeric"
    """A repeat designation such as ``15`` or the microvariant ``9.3``."""

    X = "x"
    """The X allele of a sex marker such as Amelogenin."""

    Y = "y"
    """The Y allele of a sex marker such as Amelogenin."""

    OFF_LADDER = "off_ladder"
    """A peak outside every allelic-ladder bin, exported as ``OL``."""

    OTHER = "other"
    """Any other label, for example ``?``, ``Q`` or ``9,3``; it is never guessed."""


@dataclass(frozen=True, slots=True)
class AlleleValue:
    """Conservative reading of one allele label.

    For :attr:`AlleleKind.NUMERIC`, ``number`` holds the designation as a decimal,
    for example ``Decimal("9.3")``. It orders correctly (``9 < 9.3 < 10``) but is a
    nomenclature, not a quantity: ``9.3`` means nine complete repeats plus three bases,
    which :attr:`full_repeats` and :attr:`partial_bases` expose separately.
    """

    kind: AlleleKind
    number: Decimal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, AlleleKind):
            raise TypeError("kind must be an AlleleKind value.")
        if self.kind is AlleleKind.NUMERIC:
            if not isinstance(self.number, Decimal) or not self.number.is_finite():
                raise ValueError("A numeric allele value needs a finite Decimal number.")
            if self.number < 0:
                raise ValueError("A numeric allele value must not be negative.")
        elif self.number is not None:
            raise ValueError("Only numeric allele values carry a number.")

    @property
    def is_numeric(self) -> bool:
        """Return whether the label is a repeat designation."""

        return self.kind is AlleleKind.NUMERIC

    @property
    def full_repeats(self) -> int | None:
        """Return the number of complete repeats, or ``None`` for non-numeric labels."""

        if self.number is None:
            return None
        return int(self.number)

    @property
    def partial_bases(self) -> int | None:
        """Return the bases of an incomplete repeat (``3`` for ``9.3``), else ``0``."""

        if self.number is None:
            return None
        sign, digits, exponent = self.number.as_tuple()
        del sign
        if not isinstance(exponent, int) or exponent >= 0:
            return 0
        return int("".join(str(digit) for digit in digits[exponent:]) or "0")


def parse_allele_label(label: str) -> AlleleValue:
    """Return the conservative interpretation of one exported allele label.

    Rules, applied to the label after surrounding whitespace is removed:

    * ASCII digits, optionally followed by a point and exactly one digit -> ``NUMERIC``;
    * ``X`` / ``Y`` (any case) -> ``X`` / ``Y``;
    * ``OL`` (any case) -> ``OFF_LADDER``;
    * everything else, including a decimal comma such as ``9,3`` and digits of other
      scripts such as ``٩.٣`` -> ``OTHER``.
    """

    if not isinstance(label, str):
        raise TypeError(f"Allele label must be a str, not {type(label).__name__}.")
    text = label.strip()
    match = _NUMERIC_RE.fullmatch(text)
    if match is not None:
        return AlleleValue(AlleleKind.NUMERIC, Decimal(text))
    folded = text.casefold()
    if folded == "x":
        return AlleleValue(AlleleKind.X)
    if folded == "y":
        return AlleleValue(AlleleKind.Y)
    if folded == "ol":
        return AlleleValue(AlleleKind.OFF_LADDER)
    return AlleleValue(AlleleKind.OTHER)


__all__ = ["AlleleKind", "AlleleValue", "parse_allele_label"]
