"""String enums and constants for the periodontal analytical layer.

These mirror the column-value vocabulary of the locked CSV exactly --
they are the single source of truth for "what arches exist", "what
surfaces exist", "what counts as an interdental site", and so on.
Higher layers import from here rather than hard-coding strings.

Cited rules:
* Arches / surfaces / site positions: PERIODONTAL_INTERPRETATION.md sec 1.
* Interdental = distal + mesial: PERIODONTAL_INTERPRETATION.md sec 14
  rule 4 ("use ``max(interdental CAL)`` for staging, not ``max(CAL)``
  over all sites").
"""

from __future__ import annotations

from typing import Literal

Arch = Literal["maxillary", "mandibular"]
Surface = Literal["facial", "lingual"]
SitePosition = Literal["distal", "central", "mesial"]
Measurement = Literal["PD", "GM", "CAL", "MGJ"]

ARCHES: tuple[Arch, ...] = ("maxillary", "mandibular")
SURFACES: tuple[Surface, ...] = ("facial", "lingual")
SITE_POSITIONS: tuple[SitePosition, ...] = ("distal", "central", "mesial")
MEASUREMENTS: tuple[Measurement, ...] = ("PD", "GM", "CAL", "MGJ")

# sec 14 rule 4: only distal/mesial sites are interdental and so eligible
# for the AAP/EFP "max interdental CAL" used in Stage assignment.
INTERDENTAL_SITES: tuple[SitePosition, ...] = ("distal", "mesial")

TEETH_PER_ARCH: int = 14
SITES_PER_TOOTH_PER_SURFACE: int = 3
SURFACES_PER_TOOTH: int = 2
SITES_PER_TOOTH: int = SITES_PER_TOOTH_PER_SURFACE * SURFACES_PER_TOOTH  # = 6

TOOTH_NUMBERS_BY_ARCH: dict[Arch, tuple[int, ...]] = {
    "maxillary": (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
    "mandibular": (18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31),
}
