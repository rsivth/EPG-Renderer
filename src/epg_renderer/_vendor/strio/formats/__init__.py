"""Readers for file formats of forensic genetics software.

Each format lives in its own module and returns a :class:`strio.Dataset`.

* :mod:`strio.formats.genemapper` -- GeneMapper genotype-table exports (CSV/TSV).
"""

from .genemapper import parse_genemapper, read_genemapper

__all__ = ["parse_genemapper", "read_genemapper"]
