"""Canonical marker keys for looking up loci across files, kits and frequency tables.

The marker name exported by a program stays unchanged in the data model. The key
derived here is only a lookup aid: it removes differences in letter case and spacing
(``vWA`` / ``VWA``, ``Penta D`` / ``PentaD``) and maps a small, explicit set of
well-known synonyms. Nothing is matched fuzzily.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from types import MappingProxyType

_SYNONYMS: Mapping[str, str] = MappingProxyType(
    {
        # Amelogenin is exported under several names depending on kit and software.
        "AM": "AMEL",
        "AMELOGENIN": "AMEL",
        # SE33 is also known by its historical locus name.
        "ACTBP2": "SE33",
    }
)


def marker_key(name: str) -> str:
    """Return the canonical lookup key of a marker name.

    The key is the Unicode-NFC-normalised name in upper case without any whitespace,
    replaced by its canonical form if it is one of the documented synonyms
    (:data:`MARKER_SYNONYMS`). An empty or blank name is rejected.
    """

    text = unicodedata.normalize("NFC", str(name))
    key = "".join(text.split()).upper()
    if not key:
        raise ValueError("Marker name must not be empty.")
    return _SYNONYMS.get(key, key)


MARKER_SYNONYMS: Mapping[str, str] = _SYNONYMS
"""Read-only table of documented marker synonyms (synonym key -> canonical key)."""


__all__ = ["MARKER_SYNONYMS", "marker_key"]
