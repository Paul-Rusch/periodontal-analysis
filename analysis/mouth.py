"""``ArchSurface`` and ``Mouth`` -- whole-mouth aggregation level.

PERIODONTAL_INTERPRETATION.md sec 5: the headline numbers a clinician
scans first.

In Phase 1 we land:

* ``ArchSurface`` (one of {(maxillary,facial), (maxillary,lingual),
  (mandibular,facial), (mandibular,lingual)} = 42 sites): ``max_PD``,
  ``mean_PD``.
* ``Mouth`` (168 sites): ``mean_PD``, ``n_teeth_with_PD_ge``,
  ``max_interdental_CAL`` (the §6 staging input that Phase 3 will
  consume).

Phase 2 fleshes out the rest of the §5 catalog (``mean_CAL``,
``pct_sites_PD_ge_X``, ``pct_teeth_affected``, recession aggregates,
mucogingival counts, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass

from analysis import citations
from analysis.evidence import Evidence, EvidenceStatus
from analysis.site import Site
from analysis.tooth import Tooth
from analysis.types import (
    ARCHES,
    INTERDENTAL_SITES,
    SURFACES,
    TOOTH_NUMBERS_BY_ARCH,
    Arch,
    Surface,
)


def _site_aggregate_max_pd(sites: tuple[Site, ...]) -> int:
    return max(s.pd.mm for s in sites if s.pd is not None)


def _site_aggregate_mean_pd(sites: tuple[Site, ...]) -> float:
    pds = [s.pd.mm for s in sites if s.pd is not None]
    return sum(pds) / len(pds)


def _site_aggregate_max_cal(sites: tuple[Site, ...]) -> int:
    return max(s.cal.mm for s in sites if s.cal is not None)


def _site_aggregate_mean_cal(sites: tuple[Site, ...]) -> float:
    cals = [s.cal.mm for s in sites if s.cal is not None]
    return sum(cals) / len(cals)


def _site_aggregate_mean_recession(sites: tuple[Site, ...]) -> float:
    recs = [s.recession_mm for s in sites]
    return sum(recs) / len(recs)


def _site_aggregate_pct_pd_ge(sites: tuple[Site, ...], threshold: int) -> float:
    n = sum(1 for s in sites if s.pd is not None and s.pd.mm >= threshold)
    total = sum(1 for s in sites if s.pd is not None)
    return 100.0 * n / total if total else 0.0


def _site_aggregate_pct_cal_ge(sites: tuple[Site, ...], threshold: int) -> float:
    n = sum(1 for s in sites if s.cal is not None and s.cal.mm >= threshold)
    total = sum(1 for s in sites if s.cal is not None)
    return 100.0 * n / total if total else 0.0


@dataclass(frozen=True)
class ArchSurface:
    """One surface of one arch at one exam: 14 teeth x 3 sites = 42
    sites.  Used for surface-stratified §5 aggregates -- facial vs
    lingual disease patterns differ (sec 5 + sec 14 rule 5)."""

    arch: Arch
    surface: Surface
    sites: tuple[Site, ...]

    @property
    def scope(self) -> tuple[object, ...]:
        ek = self.sites[0].exam_key
        return (ek.patient_id, ek.exam_index, self.arch, self.surface)

    # Bare-number §5 aggregates over the 42 sites in this (arch, surface).
    @property
    def max_PD(self) -> int:
        return _site_aggregate_max_pd(self.sites)

    @property
    def mean_PD(self) -> float:
        return _site_aggregate_mean_pd(self.sites)

    @property
    def max_CAL(self) -> int:
        return _site_aggregate_max_cal(self.sites)

    @property
    def mean_CAL(self) -> float:
        return _site_aggregate_mean_cal(self.sites)

    @property
    def mean_recession(self) -> float:
        return _site_aggregate_mean_recession(self.sites)

    def pct_sites_PD_ge(self, threshold: int) -> float:
        return _site_aggregate_pct_pd_ge(self.sites, threshold)

    def pct_sites_CAL_ge(self, threshold: int) -> float:
        return _site_aggregate_pct_cal_ge(self.sites, threshold)


@dataclass(frozen=True)
class Mouth:
    """All 168 sites at one exam, organized by tooth.

    ``Mouth`` is the level at which AAP/EFP Stage and CDC/AAP severity
    will be computed in Phase 3.  Phase 1 implements only the §6
    staging input (``max_interdental_CAL``) and a handful of §5 tile
    metrics so the downstream layers have something to consume.
    """

    teeth: dict[int, Tooth]

    def __post_init__(self) -> None:
        # Validate composition: every tooth_number from both arches
        # should be present (28 teeth for the current dataset).  Future
        # patients with extractions will have fewer; tooth-loss tracking
        # is a Phase 4 concern, not a Phase 1 invariant.
        all_expected = set(TOOTH_NUMBERS_BY_ARCH["maxillary"]) | set(
            TOOTH_NUMBERS_BY_ARCH["mandibular"]
        )
        missing = all_expected - set(self.teeth)
        if missing and len(self.teeth) != len(all_expected):
            # Allow either "all 28 present" or "some legitimately missing"
            # (we just record it; Phase 4 surfaces it as tooth-loss).
            pass

    # ---- composition --------------------------------------------------------

    def tooth(self, tooth_number: int) -> Tooth:
        return self.teeth[tooth_number]

    def teeth_in_arch(self, arch: Arch) -> tuple[Tooth, ...]:
        nums = TOOTH_NUMBERS_BY_ARCH[arch]
        return tuple(self.teeth[n] for n in nums if n in self.teeth)

    def arch_surface(self, arch: Arch, surface: Surface) -> ArchSurface:
        sites: list[Site] = []
        for t in self.teeth_in_arch(arch):
            sites.extend(s for s in t.sites if s.site_key.surface == surface)
        return ArchSurface(arch=arch, surface=surface, sites=tuple(sites))

    @property
    def all_sites(self) -> tuple[Site, ...]:
        out: list[Site] = []
        for t in self.teeth.values():
            out.extend(t.sites)
        return tuple(out)

    @property
    def scope(self) -> tuple[object, ...]:
        ek = next(iter(self.teeth.values())).sites[0].exam_key
        return (ek.patient_id, ek.exam_index)

    # ---- §5 tile metrics (bare numbers) -------------------------------------

    @property
    def max_PD(self) -> int:
        return _site_aggregate_max_pd(self.all_sites)

    @property
    def mean_PD(self) -> float:
        return _site_aggregate_mean_pd(self.all_sites)

    @property
    def max_CAL(self) -> int:
        return _site_aggregate_max_cal(self.all_sites)

    @property
    def mean_CAL(self) -> float:
        return _site_aggregate_mean_cal(self.all_sites)

    @property
    def mean_recession(self) -> float:
        return _site_aggregate_mean_recession(self.all_sites)

    def pct_sites_PD_ge(self, threshold: int) -> float:
        return _site_aggregate_pct_pd_ge(self.all_sites, threshold)

    def pct_sites_CAL_ge(self, threshold: int) -> float:
        return _site_aggregate_pct_cal_ge(self.all_sites, threshold)

    def n_teeth_with_PD_ge(self, threshold: int) -> int:
        return sum(1 for t in self.teeth.values() if t.max_PD >= threshold)

    def n_teeth_with_CAL_ge(self, threshold: int) -> int:
        return sum(1 for t in self.teeth.values() if t.max_CAL >= threshold)

    @property
    def n_teeth_present(self) -> int:
        return len(self.teeth)

    @property
    def n_teeth_affected(self) -> int:
        """Distinct teeth where ``max_CAL_tooth >= 3`` mm (CDC/AAP cutoff,
        Stage II floor).  PERIODONTAL_INTERPRETATION.md sec 4 + sec 5."""
        return sum(1 for t in self.teeth.values() if t.max_CAL >= 3)

    @property
    def pct_teeth_affected(self) -> float:
        if not self.teeth:
            return 0.0
        return 100.0 * self.n_teeth_affected / self.n_teeth_present

    # ---- Phase 3 classification shims (delegate to analysis.classify) ----

    def stage(self) -> Evidence:
        from analysis.classify import stage as _stage  # local import; cycle
        return _stage(self)

    def extent(self) -> Evidence:
        from analysis.classify import extent as _extent
        return _extent(self)

    def cdc_aap_severity(self) -> Evidence:
        from analysis.classify import cdc_aap_severity as _sev
        return _sev(self)

    def psr_pd_floor(self) -> tuple[Evidence, ...]:
        from analysis.classify import psr_pd_floor as _psr
        return _psr(self)

    def n_sites_mucogingival_breach(self) -> Evidence:
        """Count of sites where ``PD >= MGJ``.  Always NOT_ASSESSABLE
        on patient_01 (MGJ is None throughout)."""
        per_site = [s.mucogingival_breach() for s in self.all_sites]
        if all(e.is_not_assessable for e in per_site):
            return Evidence(
                rule_id="mouth.n_sites_mucogingival_breach",
                scope=self.scope,
                status=EvidenceStatus.NOT_ASSESSABLE,
                threshold_crossed="count(sites where PD >= MGJ)",
                citation=citations.MGN_NOT_ASSESSABLE_ON_PATIENT_01,
                missing_inputs=("MGJ",),
            )
        n = sum(1 for e in per_site if e.is_supported and e.value is True)
        return Evidence(
            rule_id="mouth.n_sites_mucogingival_breach",
            scope=self.scope,
            status=EvidenceStatus.SUPPORTED,
            threshold_crossed="count(sites where PD >= MGJ)",
            citation=citations.SITE_MUCOGINGIVAL_BREACH,
            value=n,
        )

    # ---- §6 staging input ---------------------------------------------------

    def max_interdental_CAL(self) -> Evidence:
        """``max(CAL)`` over interdental (distal/mesial) sites only.
        PERIODONTAL_INTERPRETATION.md sec 6 + sec 14 rule 4 [1].

        This is the AAP/EFP Stage driver -- Phase 3 will read
        ``Evidence.value`` and threshold it (1-2 -> Stage I, 3-4 -> II,
        >=5 -> III).  Implemented at Phase 1 because the rest of the
        §5 catalog and the staging algorithm both consume it.
        """
        interdental_sites = [
            s
            for s in self.all_sites
            if s.site_key.site in INTERDENTAL_SITES and s.cal is not None
        ]
        if not interdental_sites:
            return Evidence(
                rule_id="mouth.max_interdental_CAL",
                scope=self.scope,
                status=EvidenceStatus.NOT_ASSESSABLE,
                threshold_crossed="max(CAL) over distal/mesial sites",
                citation=citations.MOUTH_INTERDENTAL_CAL,
                missing_inputs=("CAL",),
            )
        worst = max(interdental_sites, key=lambda s: s.cal.mm)
        return Evidence(
            rule_id="mouth.max_interdental_CAL",
            scope=self.scope,
            status=EvidenceStatus.SUPPORTED,
            threshold_crossed="max(CAL) over distal/mesial sites",
            citation=citations.MOUTH_INTERDENTAL_CAL,
            value=worst.cal.mm,
            trigger_measurements=(
                {
                    "site_key": tuple(worst.scope),
                    "measurement": "CAL",
                    "mm": worst.cal.mm,
                },
            ),
        )
