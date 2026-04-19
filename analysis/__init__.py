"""Periodontal analytical layer over the locked OCR'd CSV.

Read the package-level architecture in ``analysis/README.md`` and the
project overview in the top-level ``README.md``.  Every clinical
threshold and metric implemented here is cited back into
``PERIODONTAL_INTERPRETATION.md``.

Modules, in dependency order (bottom-up):

* :mod:`analysis.types`       -- string enums + tooth/sextant constants.
* :mod:`analysis.citations`   -- central registry of citation strings.
* :mod:`analysis.evidence`    -- ``Evidence`` dataclass.  Phase 1b spec.
* :mod:`analysis.normalize`   -- typed value objects (PD/GM/CAL/MGJ) +
  the canonical CSV parser.  The **only** module allowed to consume the
  raw CSV.  Phase 1a spec.
* :mod:`analysis.site`,       -- typed access layer:
  :mod:`analysis.tooth`,         Site -> Tooth -> ArchSurface -> Mouth ->
  :mod:`analysis.mouth`,         Exam -> Patient.  Phase 1.
  :mod:`analysis.exam`,
  :mod:`analysis.patient`
* :mod:`analysis.sextants`    -- PSR sextant geometry.
* :mod:`analysis.classify`    -- AAP/EFP Stage, extent, CDC/AAP
  severity, PSR PD-floor, per-tooth prognosis floor.  Phase 3.
* :mod:`analysis.longitudinal` -- per-site deltas, treatment-response,
  trend series, Grade, EFP S3 PD-only endpoint, tooth-loss tracking,
  recession trajectory, soft-tissue intervention assessment, PST/graft
  effectiveness.  Phase 4.
* :mod:`analysis.loader`      -- ``load_patient(patient_id)``: wires all
  three Phase 0 manifests into a fully-populated ``Patient``.
* :mod:`analysis.recommend`   -- pure markdown renderer over the
  Evidence produced by all of the above.  No clinical thresholds may
  appear in this module's source.  Phase 5.

Every public name from every module is re-exported here and listed
in ``__all__``.  Higher-layer modules consume :mod:`analysis.normalize`,
**never** the raw CSV.
"""

from __future__ import annotations

from analysis.classify import (
    cdc_aap_severity,
    extent,
    prognosis_floor,
    psr_pd_floor,
    stage,
)
from analysis.evidence import Evidence, EvidenceStatus
from analysis.exam import ChartContext, Exam
from analysis.loader import load_patient
from analysis.longitudinal import (
    SiteDelta,
    grade,
    per_site_deltas,
    pst_or_graft_treatment_response,
    recession_trajectory,
    s3_pd_only_endpoint,
    soft_tissue_intervention_assessment,
    tooth_loss_events,
    treatment_response,
    trend_series,
)
from analysis.mouth import ArchSurface, Mouth
from analysis.normalize import (
    CAL,
    GM,
    MGJ,
    PD,
    ExamKey,
    NormalizedSite,
    SiteKey,
    iter_normalized_sites,
    normalize_value,
)
from analysis.patient import HistoryEvent, HistoryEvents, Patient, PatientMetadata
from analysis.recommend import RecommendationReport, ToothFocus, report
from analysis.site import Site
from analysis.tooth import Tooth
from analysis.types import (
    ARCHES,
    INTERDENTAL_SITES,
    MEASUREMENTS,
    SITE_POSITIONS,
    SURFACES,
    TOOTH_NUMBERS_BY_ARCH,
    Arch,
    Measurement,
    SitePosition,
    Surface,
)

__all__ = [
    "ARCHES",
    "Arch",
    "ArchSurface",
    "CAL",
    "ChartContext",
    "Evidence",
    "EvidenceStatus",
    "Exam",
    "ExamKey",
    "GM",
    "HistoryEvent",
    "HistoryEvents",
    "INTERDENTAL_SITES",
    "MEASUREMENTS",
    "MGJ",
    "Measurement",
    "Mouth",
    "NormalizedSite",
    "PD",
    "Patient",
    "PatientMetadata",
    "RecommendationReport",
    "SITE_POSITIONS",
    "SURFACES",
    "Site",
    "SiteDelta",
    "SiteKey",
    "SitePosition",
    "Surface",
    "TOOTH_NUMBERS_BY_ARCH",
    "Tooth",
    "ToothFocus",
    "cdc_aap_severity",
    "extent",
    "grade",
    "iter_normalized_sites",
    "load_patient",
    "normalize_value",
    "per_site_deltas",
    "prognosis_floor",
    "psr_pd_floor",
    "pst_or_graft_treatment_response",
    "recession_trajectory",
    "report",
    "s3_pd_only_endpoint",
    "soft_tissue_intervention_assessment",
    "stage",
    "tooth_loss_events",
    "treatment_response",
    "trend_series",
]
