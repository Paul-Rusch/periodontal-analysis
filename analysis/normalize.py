"""Canonical normalization layer -- the *only* module in this package
that consumes the raw OCR'd CSV.  Phase 1a spec.

Why a separate normalization layer?
-----------------------------------

The CSV stores blank GM and blank MGJ both as the integer ``0`` for
tabular convenience, but the two have different clinical semantics
(PERIODONTAL_INTERPRETATION.md sec 2 and sec 14):

* ``GM = 0`` is meaningful -- "gingival margin sits at the CEJ", the
  textbook ideal.  Preserved as ``GM(mm=0)`` with ``at_cej=True``.

* ``MGJ = 0`` is *not* meaningful -- "the gingival margin is at the
  mucogingival junction" is biologically nonsensical, and in the
  current dataset all 840 MGJ values are ``0`` meaning MGJ was not
  recorded.  Normalized to ``None`` here so downstream mucogingival
  metrics correctly return ``Evidence(status=NOT_ASSESSABLE,
  missing_inputs=["MGJ"])`` instead of computing every site as a
  silent mucogingival breach.

Higher layers (``site``, ``tooth``, ``mouth``, classification,
longitudinal, recommendation) consume :func:`iter_normalized_sites` --
never the raw CSV.  Touching the raw CSV outside this module is a
code-review reject.

CSV schema (locked):

    patient_id, chart_id, exam_date, exam_index, arch, surface,
    measurement, tooth_number, site, value
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Iterator

from analysis.types import (
    MEASUREMENTS,
    Arch,
    Measurement,
    SitePosition,
    Surface,
)


# ---------------------------------------------------------------------------
# Typed measurement value objects.
#
# Each is a frozen dataclass so it is hashable, cheap, and safe to embed
# inside Evidence objects without anyone mutating it after the fact.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PD:
    """Probing depth in millimetres.  Always non-negative.

    PERIODONTAL_INTERPRETATION.md sec 2.1; bin thresholds in sec 3.
    """

    mm: int

    def __post_init__(self) -> None:
        if self.mm < 0:
            raise ValueError(f"PD.mm must be >= 0, got {self.mm}")


@dataclass(frozen=True)
class GM:
    """Gingival-margin position relative to the CEJ, in millimetres,
    *signed* per PERIODONTAL_INTERPRETATION.md sec 2.2:

    * ``mm > 0`` -- recession (gingiva apical to CEJ; root exposed).
    * ``mm == 0`` -- gingival margin sits exactly at the CEJ; the
      textbook "ideal".
    * ``mm < 0`` -- gingival overgrowth / hyperplasia (gingiva coronal
      to CEJ).  Never observed in this dataset; the type accepts it
      for future patients.
    """

    mm: int

    @property
    def at_cej(self) -> bool:
        return self.mm == 0

    @property
    def is_recession(self) -> bool:
        return self.mm > 0

    @property
    def is_overgrowth(self) -> bool:
        return self.mm < 0

    @property
    def recession_mm(self) -> int:
        """``max(GM, 0)``, used for recession heatmaps and aggregates
        per PERIODONTAL_INTERPRETATION.md sec 3 and sec 5."""
        return max(self.mm, 0)

    @property
    def overgrowth_mm(self) -> int:
        """``max(-GM, 0)``, used for pseudo-pocket flagging when
        gingival overgrowth meds (CCB / phenytoin / cyclosporine) are
        on the patient's history."""
        return max(-self.mm, 0)


@dataclass(frozen=True)
class CAL:
    """Clinical attachment level in millimetres.  PERIODONTAL_INTERPRETATION.md
    sec 2.3.  Site-level identity ``CAL = PD + GM`` (with signed GM)
    holds at 100 percent of the 840 sites in the locked CSV; the
    validator enforces it.  ``CAL`` is the AAP/EFP Stage driver, not PD.
    """

    mm: int

    def __post_init__(self) -> None:
        if self.mm < 0:
            raise ValueError(f"CAL.mm must be >= 0, got {self.mm}")


@dataclass(frozen=True)
class MGJ:
    """Distance from gingival margin to the mucogingival junction,
    in millimetres.  PERIODONTAL_INTERPRETATION.md sec 2.4.

    ``MGJ`` is constructed only for *recorded* values.  A CSV value of
    ``0`` is the "not measured" convention and is normalized to
    ``None`` by :func:`normalize_value`; constructing ``MGJ(mm=0)``
    raises ``ValueError`` to make accidental round-trips impossible.
    """

    mm: int

    def __post_init__(self) -> None:
        if self.mm <= 0:
            raise ValueError(
                f"MGJ.mm must be > 0; got {self.mm}.  CSV value 0 means "
                "'not measured' and must be normalized to None."
            )


# ---------------------------------------------------------------------------
# Identity / addressing keys.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, order=True)
class ExamKey:
    """Identifies one chart in chronological / patient context.

    Always sort by ``(patient_id, exam_index)`` -- never by
    ``chart_id``.  ``chart_id`` is anti-chronological in this dataset
    (chart 5 is the baseline, chart 1 is the most recent), and the
    handoff prompt names this as a known footgun.  ``order=True`` plus
    field declaration order makes ``sorted([...ExamKey...])`` correct
    by construction.
    """

    patient_id: str
    exam_index: int  # 1 = baseline, ascending; primary sort key
    exam_date: date
    chart_id: int  # source-chart label; never a sort key


@dataclass(frozen=True, order=True)
class SiteKey:
    """Full join-key for any per-site delta computation.

    PERIODONTAL_INTERPRETATION.md sec 15.1: deltas across exams must
    join on the *full* key ``(patient_id, arch, surface, measurement,
    tooth_number, site)`` so a tooth_number that exists in both arches
    cannot be silently merged.  ``measurement`` is not part of the key
    here because :class:`NormalizedSite` already carries all four
    measurements per site -- the join key for the *site* is everything
    except measurement, and per-measurement deltas read off the
    bundled values.
    """

    patient_id: str
    arch: Arch
    surface: Surface
    tooth_number: int
    site: SitePosition


# ---------------------------------------------------------------------------
# Normalized record produced by the parser.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalizedSite:
    """One site at one exam, with all four measurements normalized.

    Created by :func:`iter_normalized_sites`.  Higher layers wrap this
    in their typed access layer (``Site`` / ``Tooth`` / ``Mouth`` /
    ``Exam`` -- Phase 1).
    """

    exam_key: ExamKey
    site_key: SiteKey
    pd: PD | None
    gm: GM
    cal: CAL | None
    mgj: MGJ | None


# ---------------------------------------------------------------------------
# Per-cell normalization rules (PERIODONTAL_INTERPRETATION.md sec 14).
# ---------------------------------------------------------------------------


def normalize_value(
    measurement: Measurement, raw: str | int | None
) -> PD | GM | CAL | MGJ | None:
    """Translate one CSV cell into its typed clinical value.

    Rules, all from PERIODONTAL_INTERPRETATION.md sec 2 and sec 14:

    * Empty string / ``None`` -> ``None`` (missing measurement).
    * ``MGJ = 0`` -> ``None`` (chart convention: "not recorded").
      All 840 MGJ values in the current dataset are ``0`` and so all
      become ``None`` here.  Without this, every site looks like a
      mucogingival breach (``PD >= MGJ`` always true) and KTW comes
      out uniformly negative -- the silent failure mode the handoff
      prompt warned about.
    * ``GM = 0`` -> ``GM(mm=0)`` (gingival margin at CEJ; meaningful).
    * ``PD``, ``CAL`` -> integer mm wrappers.  Validator enforces
      these are never blank in the locked CSV.
    """
    if raw is None or raw == "":
        return None
    mm = int(raw)
    if measurement == "PD":
        return PD(mm)
    if measurement == "CAL":
        return CAL(mm)
    if measurement == "GM":
        return GM(mm)
    if measurement == "MGJ":
        if mm == 0:
            return None
        return MGJ(mm)
    raise ValueError(f"unknown measurement {measurement!r}")


# ---------------------------------------------------------------------------
# CSV loader.
# ---------------------------------------------------------------------------


def iter_normalized_sites(
    csv_path: str | Path,
) -> Iterator[NormalizedSite]:
    """Stream ``NormalizedSite`` records from the locked CSV.

    The CSV is one row per (chart, arch, surface, measurement, tooth,
    site) -- 4 measurements x 840 sites = 3 360 rows.  This loader
    re-pivots on ``measurement`` so each yielded record carries the
    bundled (PD, GM, CAL, MGJ) tuple for its site.

    Raises ``ValueError`` if any site is missing one of the four
    measurement rows -- that would be a CSV corruption the OCR
    validator should already have caught at ``840/840 = 100 percent``.
    """
    csv_path = Path(csv_path)
    rows = list(_read_raw_csv(csv_path))

    grouped: dict[tuple[ExamKey, SiteKey], dict[Measurement, Any]] = {}
    for row in rows:
        ek = ExamKey(
            patient_id=row["patient_id"],
            exam_index=int(row["exam_index"]),
            exam_date=date.fromisoformat(row["exam_date"]),
            chart_id=int(row["chart_id"]),
        )
        sk = SiteKey(
            patient_id=row["patient_id"],
            arch=row["arch"],
            surface=row["surface"],
            tooth_number=int(row["tooth_number"]),
            site=row["site"],
        )
        bucket = grouped.setdefault((ek, sk), {})
        m: Measurement = row["measurement"]
        normalized = normalize_value(m, row["value"])
        if m in bucket:
            raise ValueError(
                f"duplicate ({m}) row for {ek}/{sk}; CSV invariant broken"
            )
        bucket[m] = normalized

    for (ek, sk), measurements in grouped.items():
        missing = [m for m in MEASUREMENTS if m not in measurements]
        if missing:
            raise ValueError(
                f"site {ek}/{sk} is missing measurement rows: {missing}"
            )
        gm = measurements["GM"]
        if gm is None:
            # GM is the one measurement whose CSV ``0`` is a real
            # value; if a row's ``value`` was literally blank then GM
            # comes back as ``None`` and we cannot construct CAL = PD
            # + GM relationships downstream.  In the locked CSV this
            # never fires (validator confirms 100 percent identity);
            # leaving the assertion in to fail loudly if it ever does.
            raise ValueError(
                f"site {ek}/{sk} has blank GM after normalization; "
                "expected GM=0 (at CEJ) when chart cell was blank"
            )
        yield NormalizedSite(
            exam_key=ek,
            site_key=sk,
            pd=measurements["PD"],
            gm=gm,
            cal=measurements["CAL"],
            mgj=measurements["MGJ"],
        )


def _read_raw_csv(csv_path: Path) -> Iterable[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        yield from csv.DictReader(fh)
