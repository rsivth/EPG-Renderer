"""Shared validity limits for relative fluorescence unit peak heights.

Thermo Fisher documents 32,000 RFU as the maximum raw-data signal threshold for
the Applied Biosystems 3500/3500xL; higher signals are off-scale. Promega's
VersaPlex matrix-standard protocol documents 32,767 RFU as the maximum raw
spectral-calibration signal for the Spectrum Compact CE System. The package-wide
32,767-RFU ceiling is therefore a structural limit for the supported instrument
domain, not a substitute for instrument-specific analytical quality control.

Manufacturer references:
https://www.thermofisher.com/order/catalog/product/4337454/faqs
https://worldwide.promega.com/-/media/files/resources/protocols/technical-manuals/tmd/versaplex-matrix-standards-for-spectrum-compact-ce-system-protocol-tmd072.pdf
"""

from __future__ import annotations

MAX_RFU = 32_767


def validate_rfu(value: object, *, allow_zero: bool) -> int:
    """Return an RFU height after enforcing the supported whole-number range."""

    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= MAX_RFU:
        raise ValueError(f"RFU height must be a whole number from {minimum:,} to {MAX_RFU:,}.")
    return value


__all__ = ["MAX_RFU", "validate_rfu"]
