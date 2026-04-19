"""``Tooth`` -- the six sites of one tooth at one exam.

Three facial + three lingual, per PERIODONTAL_INTERPRETATION.md sec 1
(six-point periodontal exam) and sec 4 (tooth-level aggregation).

First metrics implemented in Phase 1:

* ``max_PD``, ``mean_PD``, ``max_CAL``, ``max_recession`` -- bare
  numbers per the plan ("flag-style outputs return Evidence; numeric
  aggregates may return bare values").
* ``n_sites_PD_ge`` / ``n_sites_CAL_ge`` -- bare counts.
* ``is_affected`` and ``is_deep`` -- flag-style, return Evidence.

The full §4 metric catalog (``mean_CAL``, all ``n_sites_X_ge_Y`` for
the standard thresholds) lands in Phase 2 and lives on this same
class.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from analysis import citations
from analysis.evidence import Evidence, EvidenceStatus
from analysis.site import Site
from analysis.types import INTERDENTAL_SITES, Arch, Surface


@dataclass(frozen=True)
class Tooth:
    """All six sites of one tooth at one exam, plus optional caveats
    that come from Phase 0 history (e.g. crown on tooth 8).

    Caveats are pre-baked Evidence objects attached at load time;
    Phase 5 narrative renders them whenever it surfaces a finding on
    this tooth.
    """

    arch: Arch
    tooth_number: int
    sites: tuple[Site, ...]
    caveats: tuple[Evidence, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        # Spec: 6 sites per tooth (3 facial + 3 lingual); allow shorter
        # tuples only if a future patient has a recorded missing site.
        if len(self.sites) > 6:
            raise ValueError(
                f"Tooth {self.tooth_number}: more than 6 sites ({len(self.sites)})"
            )
        for s in self.sites:
            if s.site_key.tooth_number != self.tooth_number:
                raise ValueError(
                    f"Tooth {self.tooth_number}: site belongs to tooth "
                    f"{s.site_key.tooth_number}"
                )
            if s.site_key.arch != self.arch:
                raise ValueError(
                    f"Tooth {self.tooth_number}: site belongs to arch "
                    f"{s.site_key.arch} (expected {self.arch})"
                )

    # ---- composition --------------------------------------------------------

    def site(self, surface: Surface, site_position: str) -> Site:
        for s in self.sites:
            if s.site_key.surface == surface and s.site_key.site == site_position:
                return s
        raise KeyError(
            f"Tooth {self.tooth_number}: no site at "
            f"surface={surface!r}, site={site_position!r}"
        )

    def sites_on(self, surface: Surface) -> tuple[Site, ...]:
        return tuple(s for s in self.sites if s.site_key.surface == surface)

    @property
    def scope(self) -> tuple[object, ...]:
        # Patient + exam_index + arch + tooth -- no surface/site.
        ek = self.sites[0].exam_key
        return (ek.patient_id, ek.exam_index, self.arch, self.tooth_number)

    # ---- bare-number aggregates (sec 4) ------------------------------------

    def _pds(self) -> tuple[int, ...]:
        return tuple(s.pd.mm for s in self.sites if s.pd is not None)

    def _cals(self) -> tuple[int, ...]:
        return tuple(s.cal.mm for s in self.sites if s.cal is not None)

    @property
    def max_PD(self) -> int:
        return max(self._pds())

    @property
    def mean_PD(self) -> float:
        pds = self._pds()
        return sum(pds) / len(pds)

    @property
    def max_CAL(self) -> int:
        return max(self._cals())

    @property
    def mean_CAL(self) -> float:
        cals = self._cals()
        return sum(cals) / len(cals)

    @property
    def max_recession(self) -> int:
        return max(s.recession_mm for s in self.sites)

    @property
    def mean_recession(self) -> float:
        recs = [s.recession_mm for s in self.sites]
        return sum(recs) / len(recs)

    def n_sites_PD_ge(self, threshold: int) -> int:
        return sum(1 for v in self._pds() if v >= threshold)

    def n_sites_CAL_ge(self, threshold: int) -> int:
        return sum(1 for v in self._cals() if v >= threshold)

    # ---- interdental-only views (sec 14 rule 4 -- staging input) ----------

    def _interdental_sites(self) -> tuple[Site, ...]:
        return tuple(s for s in self.sites if s.site_key.site in INTERDENTAL_SITES)

    @property
    def max_interdental_CAL(self) -> int:
        cals = [s.cal.mm for s in self._interdental_sites() if s.cal is not None]
        return max(cals) if cals else 0

    @property
    def max_interdental_PD(self) -> int:
        pds = [s.pd.mm for s in self._interdental_sites() if s.pd is not None]
        return max(pds) if pds else 0

    # ---- mucogingival rollups (sec 4 + sec 10) -- always not_assessable
    # for patient_01 because Site.mgj is None throughout ---------------------

    def mucogingival_breach_tooth(self) -> Evidence:
        """Any site on this tooth where ``PD >= MGJ``.
        PERIODONTAL_INTERPRETATION.md sec 4 + sec 10."""
        ev_per_site = [s.mucogingival_breach() for s in self.sites]
        return _aggregate_any_breach(self.scope, ev_per_site)

    def min_KTW_tooth(self) -> Evidence:
        """``min(MGJ - PD)`` over sites where MGJ is recorded; surfaces
        the worst attached-gingiva-width site on the tooth.
        PERIODONTAL_INTERPRETATION.md sec 4."""
        ev_per_site = [s.ktw() for s in self.sites]
        return _aggregate_min_ktw(self.scope, ev_per_site)

    # ---- flag-style metrics returning Evidence -----------------------------

    def is_affected(self) -> Evidence:
        """Tooth is "periodontally affected" (CDC/AAP-style) when
        ``max_CAL >= 3`` mm or ``max_PD >= 4`` mm.
        PERIODONTAL_INTERPRETATION.md sec 4 [1][12]."""
        max_cal = self.max_CAL
        max_pd = self.max_PD
        cal_hit = max_cal >= 3
        pd_hit = max_pd >= 4
        affected = cal_hit or pd_hit
        triggers: list[dict] = []
        if cal_hit:
            triggers.append({"name": "max_CAL_tooth", "mm": max_cal})
        if pd_hit:
            triggers.append({"name": "max_PD_tooth", "mm": max_pd})
        return Evidence(
            rule_id="tooth.affected" if affected else "tooth.unaffected",
            scope=self.scope,
            status=EvidenceStatus.SUPPORTED,
            threshold_crossed="max_CAL_tooth >= 3 OR max_PD_tooth >= 4",
            citation=citations.TOOTH_AFFECTED,
            value=affected,
            trigger_measurements=tuple(triggers) or (
                {"name": "max_CAL_tooth", "mm": max_cal},
                {"name": "max_PD_tooth", "mm": max_pd},
            ),
        )

    def prognosis_floor(self) -> Evidence:
        """Per-tooth McGuire-Nunn-style PD/CAL-only prognosis floor;
        delegates to :func:`analysis.classify.prognosis_floor`."""
        from analysis.classify import prognosis_floor as _pf
        return _pf(self)

    def is_deep(self) -> Evidence:
        """Tooth is "deep" (Stage III complexity contributor) when
        ``max_PD >= 6`` mm or ``max_CAL >= 5`` mm.
        PERIODONTAL_INTERPRETATION.md sec 4 [1]."""
        max_cal = self.max_CAL
        max_pd = self.max_PD
        cal_hit = max_cal >= 5
        pd_hit = max_pd >= 6
        deep = cal_hit or pd_hit
        triggers: list[dict] = []
        if cal_hit:
            triggers.append({"name": "max_CAL_tooth", "mm": max_cal})
        if pd_hit:
            triggers.append({"name": "max_PD_tooth", "mm": max_pd})
        return Evidence(
            rule_id="tooth.deep" if deep else "tooth.not_deep",
            scope=self.scope,
            status=EvidenceStatus.SUPPORTED,
            threshold_crossed="max_PD_tooth >= 6 OR max_CAL_tooth >= 5",
            citation=citations.TOOTH_DEEP,
            value=deep,
            trigger_measurements=tuple(triggers) or (
                {"name": "max_CAL_tooth", "mm": max_cal},
                {"name": "max_PD_tooth", "mm": max_pd},
            ),
        )


# ---- helpers for mucogingival rollups -------------------------------------


def _aggregate_any_breach(
    scope: tuple[object, ...], ev_per_site: list[Evidence]
) -> Evidence:
    """OR-collapse a list of per-site mucogingival_breach Evidence."""
    if all(e.is_not_assessable for e in ev_per_site):
        return Evidence(
            rule_id="tooth.mucogingival_breach",
            scope=scope,
            status=EvidenceStatus.NOT_ASSESSABLE,
            threshold_crossed="any site PD >= MGJ",
            citation=citations.MGN_NOT_ASSESSABLE_ON_PATIENT_01,
            missing_inputs=("MGJ",),
        )
    breach_sites = [e for e in ev_per_site if e.is_supported and e.value is True]
    return Evidence(
        rule_id="tooth.mucogingival_breach",
        scope=scope,
        status=EvidenceStatus.SUPPORTED,
        threshold_crossed="any site PD >= MGJ",
        citation=citations.SITE_MUCOGINGIVAL_BREACH,
        value=bool(breach_sites),
        trigger_measurements=tuple({"site_scope": e.scope} for e in breach_sites),
    )


def _aggregate_min_ktw(
    scope: tuple[object, ...], ev_per_site: list[Evidence]
) -> Evidence:
    """Return the worst (minimum) per-site KTW, or NOT_ASSESSABLE."""
    valid = [e for e in ev_per_site if e.is_supported and isinstance(e.value, int)]
    if not valid:
        return Evidence(
            rule_id="tooth.min_ktw",
            scope=scope,
            status=EvidenceStatus.NOT_ASSESSABLE,
            threshold_crossed="min(MGJ - PD) over sites with MGJ recorded",
            citation=citations.MGN_NOT_ASSESSABLE_ON_PATIENT_01,
            missing_inputs=("MGJ",),
        )
    worst = min(valid, key=lambda e: e.value)
    return Evidence(
        rule_id="tooth.min_ktw",
        scope=scope,
        status=EvidenceStatus.SUPPORTED,
        threshold_crossed="min(MGJ - PD) across sites with MGJ recorded",
        citation=citations.SITE_KTW,
        value=worst.value,
        trigger_measurements=({"site_scope": worst.scope, "ktw_mm": worst.value},),
    )
