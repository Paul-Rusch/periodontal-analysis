"""PSR sextant geometry, per PERIODONTAL_INTERPRETATION.md sec 8.

Six sextants partition the dentition into right / anterior / left
across each arch.  Used by :func:`analysis.classify.psr_pd_floor`.
"""

from __future__ import annotations

from analysis.types import Arch


# (sextant_label, arch, ordered tuple of universal tooth_numbers)
SEXTANT_LABELS = (
    "upper_right",
    "upper_anterior",
    "upper_left",
    "lower_left",
    "lower_anterior",
    "lower_right",
)


SEXTANT_TEETH: dict[str, tuple[Arch, tuple[int, ...]]] = {
    "upper_right":    ("maxillary",  (2, 3, 4, 5)),
    "upper_anterior": ("maxillary",  (6, 7, 8, 9, 10, 11)),
    "upper_left":     ("maxillary",  (12, 13, 14, 15)),
    "lower_left":     ("mandibular", (18, 19, 20, 21)),
    "lower_anterior": ("mandibular", (22, 23, 24, 25, 26, 27)),
    "lower_right":    ("mandibular", (28, 29, 30, 31)),
}
