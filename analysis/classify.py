"""Phase 3 classification engine.

Every public function here takes a :class:`analysis.mouth.Mouth` (or a
:class:`analysis.tooth.Tooth`) and returns one or more
:class:`analysis.evidence.Evidence` objects.  No bare strings or bare
classification labels are returned -- the Phase 5 narrative renderer
reads ``Evidence.value``, ``Evidence.status``, and
``Evidence.assumptions`` to phrase the result.

Cited rules:
* Stage I-IV: PERIODONTAL_INTERPRETATION.md sec 6; AAP/EFP 2018 [1][2].
* Localised vs generalised: sec 6 [1][8].
* CDC/AAP severity: sec 7 [12][13].
* PSR PD-floor per sextant: sec 8 [14][15].
* Per-tooth prognosis floor: sec 9 [16].
"""

from __future__ import annotations

from analysis import citations
from analysis.evidence import Evidence, EvidenceStatus
from analysis.mouth import Mouth
from analysis.sextants import SEXTANT_LABELS, SEXTANT_TEETH
from analysis.tooth import Tooth
from analysis.types import INTERDENTAL_SITES


# ---------------------------------------------------------------------------
# AAP/EFP 2018 Stage (sec 6).
# ---------------------------------------------------------------------------


def stage(mouth: Mouth) -> Evidence:
    """Return AAP/EFP Stage I-IV (provisional).

    Algorithm (sec 6 [1][2]):

    1. Severity floor by ``max_interdental_CAL``: <=2 -> I, 3-4 -> II,
       >=5 -> III.
    2. PD complexity bumps that ARE supported from this dataset:
       I+max_PD>=5 -> II; II+max_PD>=6 -> III.
    3. Stage IV upgrade requires teeth-lost-to-perio >= 5, mobility >= 2,
       or remaining-teeth < 20 -- none assessable here.  Status is
       always PROVISIONAL with the Stage IV inputs listed in
       ``missing_inputs``.
    """
    cal_ev = mouth.max_interdental_CAL()
    if cal_ev.is_not_assessable:
        return Evidence(
            rule_id="aap_efp_2018.stage",
            scope=mouth.scope,
            status=EvidenceStatus.NOT_ASSESSABLE,
            threshold_crossed="Stage I-IV by max_interdental_CAL",
            citation=citations.CLASSIFY_STAGE,
            missing_inputs=("CAL",),
        )
    max_int_cal = cal_ev.value
    max_pd = mouth.max_PD

    if max_int_cal <= 2:
        base = "I"
    elif max_int_cal <= 4:
        base = "II"
    else:
        base = "III"
    # PD complexity bumps (only ones our data supports).
    if base == "I" and max_pd >= 5:
        base = "II"
    if base == "II" and max_pd >= 6:
        base = "III"

    return Evidence(
        rule_id=f"aap_efp_2018.stage.{base.lower()}",
        scope=mouth.scope,
        status=EvidenceStatus.PROVISIONAL,
        threshold_crossed=(
            "max_interdental_CAL <=2 -> I; 3-4 -> II; >=5 -> III; "
            "PD complexity bumps: I+PD>=5 -> II, II+PD>=6 -> III"
        ),
        citation=citations.CLASSIFY_STAGE,
        value=base,
        trigger_measurements=(
            {"name": "max_interdental_CAL", "mm": max_int_cal},
            {"name": "max_PD_mouth", "mm": max_pd},
        ),
        missing_inputs=(
            "RBL_percent",
            "teeth_lost_to_periodontitis",
            "mobility_grade",
            "furcation_class",
            "remaining_teeth_count",
        ),
        assumptions=(
            "Stage IV upgrade inputs unknown; cannot raise above III from "
            "this dataset alone (Phase 0 history may upgrade later)",
        ),
    )


# ---------------------------------------------------------------------------
# Localised vs generalised extent (sec 6).
# ---------------------------------------------------------------------------


def extent(mouth: Mouth) -> Evidence:
    """``localised`` if < 30 percent of present teeth are affected,
    ``generalised`` otherwise.  PERIODONTAL_INTERPRETATION.md sec 6
    [1][8]."""
    pct = mouth.pct_teeth_affected
    label = "localised" if pct < 30.0 else "generalised"
    return Evidence(
        rule_id=f"aap_efp_2018.extent.{label}",
        scope=mouth.scope,
        status=EvidenceStatus.SUPPORTED,
        threshold_crossed="localised < 30 percent of teeth affected; >=30 generalised",
        citation=citations.CLASSIFY_EXTENT,
        value=label,
        trigger_measurements=(
            {"name": "pct_teeth_affected", "value": round(pct, 2)},
            {"name": "n_teeth_affected", "value": mouth.n_teeth_affected},
            {"name": "n_teeth_present", "value": mouth.n_teeth_present},
        ),
    )


# ---------------------------------------------------------------------------
# CDC/AAP severity (sec 7).
# ---------------------------------------------------------------------------


def cdc_aap_severity(mouth: Mouth) -> Evidence:
    """CDC/AAP surveillance case definition: no/minimal, mild,
    moderate, severe.  PERIODONTAL_INTERPRETATION.md sec 7 [12][13]."""
    interp_sites = [
        s for s in mouth.all_sites if s.site_key.site in INTERDENTAL_SITES
    ]

    def teeth_with(predicate) -> set[int]:
        return {s.site_key.tooth_number for s in interp_sites if predicate(s)}

    n_cal6_diff_teeth = len(
        teeth_with(lambda s: s.cal is not None and s.cal.mm >= 6)
    )
    n_pd5_interprox = sum(
        1 for s in interp_sites if s.pd is not None and s.pd.mm >= 5
    )
    n_cal4_diff_teeth = len(
        teeth_with(lambda s: s.cal is not None and s.cal.mm >= 4)
    )
    n_pd5_diff_teeth = len(
        teeth_with(lambda s: s.pd is not None and s.pd.mm >= 5)
    )
    n_cal3_diff_teeth = len(
        teeth_with(lambda s: s.cal is not None and s.cal.mm >= 3)
    )
    n_pd4_diff_teeth = len(
        teeth_with(lambda s: s.pd is not None and s.pd.mm >= 4)
    )

    triggers = (
        {"name": "n_cal6_diff_teeth", "value": n_cal6_diff_teeth},
        {"name": "n_pd5_interprox", "value": n_pd5_interprox},
        {"name": "n_cal4_diff_teeth", "value": n_cal4_diff_teeth},
        {"name": "n_pd5_diff_teeth", "value": n_pd5_diff_teeth},
        {"name": "n_cal3_diff_teeth", "value": n_cal3_diff_teeth},
        {"name": "n_pd4_diff_teeth", "value": n_pd4_diff_teeth},
    )

    if n_cal6_diff_teeth >= 2 and n_pd5_interprox >= 1:
        label = "severe"
    elif n_cal4_diff_teeth >= 2 or n_pd5_diff_teeth >= 2:
        label = "moderate"
    elif n_cal3_diff_teeth >= 2 and n_pd4_diff_teeth >= 2:
        label = "mild"
    else:
        label = "no_or_minimal"

    return Evidence(
        rule_id=f"cdc_aap.severity.{label}",
        scope=mouth.scope,
        status=EvidenceStatus.SUPPORTED,
        threshold_crossed=(
            "severe: n_CAL>=6_diff_teeth >= 2 AND n_PD>=5_interprox >= 1; "
            "moderate: n_CAL>=4_diff_teeth >= 2 OR n_PD>=5_diff_teeth >= 2; "
            "mild: n_CAL>=3_diff_teeth >= 2 AND n_PD>=4_diff_teeth >= 2"
        ),
        citation=citations.CLASSIFY_CDC_AAP,
        value=label,
        trigger_measurements=triggers,
    )


# ---------------------------------------------------------------------------
# PSR PD-floor per sextant (sec 8).
# ---------------------------------------------------------------------------


def psr_pd_floor(mouth: Mouth) -> tuple[Evidence, ...]:
    """One Evidence per sextant, with the PD-floor PSR code (0/3/4)
    or 'X' for any sextant with no teeth present.  Always carries the
    sec 8 caveat in ``assumptions`` that codes 1 and 2 collapse into
    code 0 because BOP / calculus aren't recorded.
    PERIODONTAL_INTERPRETATION.md sec 8 [14][15]."""
    out: list[Evidence] = []
    for sextant in SEXTANT_LABELS:
        arch, tooth_numbers = SEXTANT_TEETH[sextant]
        teeth_present = [
            mouth.teeth[n] for n in tooth_numbers if n in mouth.teeth
        ]
        if not teeth_present:
            out.append(
                Evidence(
                    rule_id="psr.sextant.X",
                    scope=mouth.scope + (sextant,),
                    status=EvidenceStatus.SUPPORTED,
                    threshold_crossed="all teeth missing -> X",
                    citation=citations.CLASSIFY_PSR,
                    value="X",
                )
            )
            continue
        max_pd = max(t.max_PD for t in teeth_present)
        if max_pd <= 3:
            code = 0
        elif max_pd <= 5:
            code = 3
        else:
            code = 4
        out.append(
            Evidence(
                rule_id=f"psr.sextant.{code}",
                scope=mouth.scope + (sextant,),
                status=EvidenceStatus.PROVISIONAL,
                threshold_crossed=(
                    "PD <=3 -> 0; 4-5 -> 3; >=6 -> 4 (PD-only floor; "
                    "codes 1 and 2 require BOP/calculus)"
                ),
                citation=citations.CLASSIFY_PSR,
                value=code,
                trigger_measurements=(
                    {"name": "max_PD_sextant", "mm": max_pd},
                    {"name": "sextant", "value": sextant},
                    {"name": "arch", "value": arch},
                ),
                missing_inputs=("BOP", "calculus"),
                assumptions=(
                    "PSR codes 1 and 2 distinguish BOP-without-calculus from "
                    "BOP/calculus; without BOP/calculus inputs, code 0 in "
                    "this output may actually be 1 or 2",
                ),
            )
        )
    return tuple(out)


# ---------------------------------------------------------------------------
# Per-tooth prognosis floor (sec 9).
# ---------------------------------------------------------------------------


def prognosis_floor(tooth: Tooth) -> Evidence:
    """McGuire-Nunn-style prognosis floor from PD/CAL only
    (PERIODONTAL_INTERPRETATION.md sec 9.1 [16]):

    * ``hopeless`` floor: ``max_PD > 10``.
    * ``questionable`` floor: ``max_PD >= 8`` or ``max_CAL >= 7``.
    * ``poor`` floor: ``max_PD >= 6`` (6-7) or ``max_CAL >= 5`` (5-6).
    * ``fair`` floor: ``max_PD == 5`` or ``max_CAL`` 3-4.
    * ``good`` floor: ``max_PD <= 4`` and ``max_CAL <= 2``.

    Always returns ``Evidence(status=PROVISIONAL)`` -- the floor is
    the *best* prognosis a tooth could achieve given its PD/CAL alone;
    mobility, furcation, RBL inputs (Phase 0 future work) can only
    make the prognosis worse, never better.
    """
    max_pd = tooth.max_PD
    max_cal = tooth.max_CAL
    if max_pd > 10:
        label = "hopeless"
    elif max_pd >= 8 or max_cal >= 7:
        label = "questionable"
    elif max_pd >= 6 or max_cal >= 5:
        label = "poor"
    elif max_pd == 5 or max_cal in (3, 4):
        label = "fair"
    else:
        label = "good"
    return Evidence(
        rule_id=f"prognosis.floor.{label}",
        scope=tooth.scope,
        status=EvidenceStatus.PROVISIONAL,
        threshold_crossed=(
            "PD/CAL-only floor: hopeless PD>10; questionable PD>=8 or "
            "CAL>=7; poor PD>=6 or CAL>=5; fair PD==5 or CAL 3-4; good else"
        ),
        citation=citations.CLASSIFY_PROGNOSIS_FLOOR,
        value=label,
        trigger_measurements=(
            {"name": "max_PD_tooth", "mm": max_pd},
            {"name": "max_CAL_tooth", "mm": max_cal},
        ),
        missing_inputs=("mobility", "furcation", "RBL_percent"),
        assumptions=(
            "best-case floor from PD/CAL alone; mobility/furcation/RBL "
            "inputs would only make this worse, never better",
        ),
    )
