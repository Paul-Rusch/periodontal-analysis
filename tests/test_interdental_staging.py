"""Stage uses ``max_interdental_CAL`` -- distal/mesial sites only.

PERIODONTAL_INTERPRETATION.md sec 6 + sec 14 rule 4: AAP/EFP Stage
is computed from the maximum CAL across the *interdental* sites
(distal + mesial), not the maximum across all sites.  Using
``max(CAL)`` over all sites instead would cause central (buccal /
lingual) recession sites with high CAL to silently inflate the
stage.

These tests build synthetic mouths exercising both directions of the
rule.
"""

from __future__ import annotations

from analysis import EvidenceStatus, stage

from tests._helpers import make_exam, make_site


def _three_site_set(arch, surface, tooth_number, *, central_cal, interdental_cal, pd=3):
    """Three sites for one (arch, surface, tooth) -- distal + central +
    mesial -- with separate CAL values for the central vs interdental
    sites.  GM is fixed at 0 so CAL = PD; PD is fixed at 3 unless
    overridden so the PD-complexity bumps don't fire."""
    return [
        make_site(
            arch=arch, surface=surface, tooth_number=tooth_number, site=site,
            pd=pd, gm=interdental_cal - pd,
        )
        if site in ("distal", "mesial")
        else make_site(
            arch=arch, surface=surface, tooth_number=tooth_number, site=site,
            pd=pd, gm=central_cal - pd,
        )
        for site in ("distal", "central", "mesial")
    ]


def _build_synthetic(*, central_cal: int, interdental_cal: int, pd: int = 3):
    """Synthetic single-exam mouth: 4 teeth (2 maxillary + 2 mandibular)
    with the requested CAL distribution at every site."""
    sites: list = []
    for arch, tooth_numbers in (("maxillary", (8, 14)), ("mandibular", (24, 30))):
        for tn in tooth_numbers:
            for surface in ("facial", "lingual"):
                sites.extend(_three_site_set(
                    arch, surface, tn,
                    central_cal=central_cal,
                    interdental_cal=interdental_cal,
                    pd=pd,
                ))
    return make_exam(sites)


def test_high_central_cal_alone_does_not_trigger_stage_iii():
    """Every CENTRAL site at CAL=7, every INTERDENTAL site at CAL=2.
    Stage must be I (max_interdental_CAL = 2; PD = 3 so no
    complexity bump)."""
    exam = _build_synthetic(central_cal=7, interdental_cal=2, pd=3)
    ev = stage(exam.mouth)
    assert ev.value == "I", (
        f"Stage was {ev.value}; only the interdental (distal/mesial) "
        "sites should drive Stage.  If Stage came back III, the "
        "implementation is using max(CAL) over all sites instead of "
        "max_interdental_CAL."
    )
    assert ev.status is EvidenceStatus.PROVISIONAL


def test_high_interdental_cal_does_trigger_stage_iii():
    """Mirror case: interdental sites at CAL=7, central sites at CAL=2.
    Stage must be III."""
    exam = _build_synthetic(central_cal=2, interdental_cal=7, pd=3)
    ev = stage(exam.mouth)
    assert ev.value == "III"
    assert ev.status is EvidenceStatus.PROVISIONAL


def test_borderline_interdental_cal_3_4_is_stage_ii():
    """Interdental CAL=4 sits in the Stage II band (3-4)."""
    exam = _build_synthetic(central_cal=2, interdental_cal=4, pd=3)
    ev = stage(exam.mouth)
    assert ev.value == "II"


def test_max_interdental_cal_evidence_excludes_central():
    """Direct check: the ``max_interdental_CAL`` Evidence at the
    Mouth level must report the interdental value (2 mm here),
    not the central value (7 mm)."""
    exam = _build_synthetic(central_cal=7, interdental_cal=2, pd=3)
    ev = exam.mouth.max_interdental_CAL()
    assert ev.value == 2
    assert ev.status is EvidenceStatus.SUPPORTED
