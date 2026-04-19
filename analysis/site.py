"""``Site`` -- one observation at one (chart, arch, surface, tooth, site).

Wraps a :class:`analysis.normalize.NormalizedSite` and exposes the
site-level interpretation rules from PERIODONTAL_INTERPRETATION.md
sec 3 and the mucogingival rules from sec 10.

For ``patient_01`` every site has ``mgj is None`` (Phase 1a normalizes
all 840 CSV-zero MGJ values away), so ``mucogingival_breach`` and
``ktw`` always return ``Evidence(status=NOT_ASSESSABLE,
missing_inputs=["MGJ"])`` here.  That is by design -- the rule is a
capability hook for any future patient whose chart actually records
MGJ; it must not silently fire on a chart where MGJ wasn't taken.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from analysis import citations
from analysis.evidence import Evidence, EvidenceStatus
from analysis.normalize import CAL, GM, MGJ, PD, ExamKey, NormalizedSite, SiteKey


# Pocket-depth bins from PERIODONTAL_INTERPRETATION.md sec 3 / sec 2.1.
# Open-on-the-right intervals: ``healthy`` is PD <= 3, ``borderline`` is
# PD == 4, ``moderate`` PD == 5, ``deep`` PD == 6, ``severe`` PD >= 7.
PD_CLASS_RULES: tuple[tuple[str, int, int | None], ...] = (
    ("healthy",     0, 3),
    ("borderline",  4, 4),
    ("moderate",    5, 5),
    ("deep",        6, 6),
    ("severe",      7, None),
)


# CAL bins from PERIODONTAL_INTERPRETATION.md sec 3 (the green-to-purple
# ramp at 0-2 / 3-4 / >= 5 mirrors the AAP/EFP Stage I / II / III floors).
CAL_CLASS_RULES: tuple[tuple[str, int, int | None], ...] = (
    ("mild",      0, 2),
    ("moderate",  3, 4),
    ("severe",    5, None),
)


@dataclass(frozen=True)
class Site:
    """Typed wrapper around one ``NormalizedSite``.  Site-level rules
    from PERIODONTAL_INTERPRETATION.md sec 3 + sec 10.

    ``caveats`` is a tuple of pre-baked Evidence objects attached at
    load time -- e.g. the ``site.mouth_breathing_anterior_facial_bias``
    flag for any anterior-facial site of a patient with chronic
    mouth-breathing on file.  Phase 5 narrative renders relevant
    caveats whenever it surfaces a finding from the carrying site.
    """

    normalized: NormalizedSite
    caveats: tuple[Evidence, ...] = field(default_factory=tuple)

    # ---- raw-typed accessors ------------------------------------------------

    @property
    def exam_key(self) -> ExamKey:
        return self.normalized.exam_key

    @property
    def site_key(self) -> SiteKey:
        return self.normalized.site_key

    @property
    def pd(self) -> PD | None:
        return self.normalized.pd

    @property
    def gm(self) -> GM:
        return self.normalized.gm

    @property
    def cal(self) -> CAL | None:
        return self.normalized.cal

    @property
    def mgj(self) -> MGJ | None:
        return self.normalized.mgj

    @property
    def scope(self) -> tuple[object, ...]:
        """Six-tuple scope used in Evidence(scope=...) for site-level rules."""
        ek = self.exam_key
        sk = self.site_key
        return (
            sk.patient_id,
            ek.exam_index,
            sk.arch,
            sk.surface,
            sk.tooth_number,
            sk.site,
        )

    # ---- bare-number derived values (sec 3) --------------------------------

    @property
    def recession_mm(self) -> int:
        """``max(GM, 0)``.  PERIODONTAL_INTERPRETATION.md sec 2.2 + sec 3."""
        return self.gm.recession_mm

    # ---- flag-style metrics returning Evidence (sec 3 + sec 10) -----------

    def cal_class(self) -> Evidence:
        """Return one of {mild, moderate, severe} per
        PERIODONTAL_INTERPRETATION.md sec 3 CAL bins (the AAP/EFP
        Stage I / II / III floors expressed at site level)."""
        cal = self.cal
        if cal is None:
            return Evidence(
                rule_id="site.cal_class",
                scope=self.scope,
                status=EvidenceStatus.NOT_ASSESSABLE,
                threshold_crossed="CAL bin",
                citation=citations.SITE_PD_CLASS,
                missing_inputs=("CAL",),
            )
        label, lo, hi = _bin_lookup(cal.mm, CAL_CLASS_RULES)
        return Evidence(
            rule_id=f"site.cal_class.{label}",
            scope=self.scope,
            status=EvidenceStatus.SUPPORTED,
            threshold_crossed=_bin_text("CAL", lo, hi),
            citation=citations.SITE_PD_CLASS,
            value=label,
            trigger_measurements=({"measurement": "CAL", "mm": cal.mm},),
        )

    def pd_class(self) -> Evidence:
        """Return one of {healthy, borderline, moderate, deep, severe}
        per PERIODONTAL_INTERPRETATION.md sec 3 PD bins.  ``Evidence.value``
        carries the bin label; ``trigger_measurements`` carries the PD
        value."""
        pd = self.pd
        if pd is None:
            return Evidence(
                rule_id="site.pd_class",
                scope=self.scope,
                status=EvidenceStatus.NOT_ASSESSABLE,
                threshold_crossed="PD bin",
                citation=citations.SITE_PD_CLASS,
                missing_inputs=("PD",),
            )
        label, lo, hi = _bin_lookup(pd.mm, PD_CLASS_RULES)
        return Evidence(
            rule_id=f"site.pd_class.{label}",
            scope=self.scope,
            status=EvidenceStatus.SUPPORTED,
            threshold_crossed=_bin_text("PD", lo, hi),
            citation=citations.SITE_PD_CLASS,
            value=label,
            trigger_measurements=({"measurement": "PD", "mm": pd.mm},),
        )

    def mucogingival_breach(self) -> Evidence:
        """``PD >= MGJ`` flag.  PERIODONTAL_INTERPRETATION.md sec 10 [6].

        For ``patient_01`` always ``NOT_ASSESSABLE`` because MGJ was not
        recorded.  The rule remains in the API so future patients with
        recorded MGJ will get a real flag."""
        if self.mgj is None:
            return Evidence(
                rule_id="mgn.mucogingival_breach",
                scope=self.scope,
                status=EvidenceStatus.NOT_ASSESSABLE,
                threshold_crossed="PD >= MGJ",
                citation=citations.MGN_NOT_ASSESSABLE_ON_PATIENT_01,
                missing_inputs=("MGJ",),
            )
        if self.pd is None:
            return Evidence(
                rule_id="mgn.mucogingival_breach",
                scope=self.scope,
                status=EvidenceStatus.NOT_ASSESSABLE,
                threshold_crossed="PD >= MGJ",
                citation=citations.SITE_MUCOGINGIVAL_BREACH,
                missing_inputs=("PD",),
            )
        breach = self.pd.mm >= self.mgj.mm
        return Evidence(
            rule_id="mgn.mucogingival_breach",
            scope=self.scope,
            status=EvidenceStatus.SUPPORTED,
            threshold_crossed="PD >= MGJ",
            citation=citations.SITE_MUCOGINGIVAL_BREACH,
            value=breach,
            trigger_measurements=(
                {"measurement": "PD", "mm": self.pd.mm},
                {"measurement": "MGJ", "mm": self.mgj.mm},
            ),
        )

    def ktw(self) -> Evidence:
        """Width of attached keratinised gingiva: ``max(MGJ - PD, 0)``.
        PERIODONTAL_INTERPRETATION.md sec 2.4 + sec 10 [7].  ``Evidence.value``
        carries the mm value and a class label in ``trigger_measurements``
        when both inputs are present.

        Always ``NOT_ASSESSABLE`` for ``patient_01``."""
        if self.mgj is None:
            return Evidence(
                rule_id="mgn.ktw",
                scope=self.scope,
                status=EvidenceStatus.NOT_ASSESSABLE,
                threshold_crossed="KTW = MGJ - PD",
                citation=citations.MGN_NOT_ASSESSABLE_ON_PATIENT_01,
                missing_inputs=("MGJ",),
            )
        if self.pd is None:
            return Evidence(
                rule_id="mgn.ktw",
                scope=self.scope,
                status=EvidenceStatus.NOT_ASSESSABLE,
                threshold_crossed="KTW = MGJ - PD",
                citation=citations.SITE_KTW,
                missing_inputs=("PD",),
            )
        ktw_mm = max(self.mgj.mm - self.pd.mm, 0)
        # sec 10: >=2 adequate, 1-2 borderline, <1 deficient.
        if ktw_mm >= 2:
            ktw_class = "adequate"
        elif ktw_mm >= 1:
            ktw_class = "borderline"
        else:
            ktw_class = "deficient"
        return Evidence(
            rule_id=f"mgn.ktw.{ktw_class}",
            scope=self.scope,
            status=EvidenceStatus.SUPPORTED,
            threshold_crossed="KTW = MGJ - PD; >=2 adequate, 1-2 borderline, <1 deficient",
            citation=citations.SITE_KTW,
            value=ktw_mm,
            trigger_measurements=(
                {"measurement": "PD", "mm": self.pd.mm},
                {"measurement": "MGJ", "mm": self.mgj.mm},
                {"name": "ktw_class", "value": ktw_class},
            ),
        )


def _bin_lookup(
    mm: int, rules: tuple[tuple[str, int, int | None], ...]
) -> tuple[str, int, int | None]:
    for label, lo, hi in rules:
        if hi is None:
            if mm >= lo:
                return label, lo, hi
        elif lo <= mm <= hi:
            return label, lo, hi
    raise ValueError(f"value {mm} out of bin range: {rules}")


def _bin_text(name: str, lo: int, hi: int | None) -> str:
    if hi is None:
        return f"{name} >= {lo}"
    if lo == hi:
        return f"{name} == {lo}"
    return f"{lo} <= {name} <= {hi}"
