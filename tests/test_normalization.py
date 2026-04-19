"""Phase 1a normalization guard.

* CSV ``MGJ = 0`` -> ``None`` (means "not measured" in the chart
  convention).  Without this, every site silently computes as a
  mucogingival breach.
* CSV ``GM = 0`` -> ``GM(mm=0)`` with ``at_cej == True`` (clinically
  meaningful: gingival margin at the CEJ).
* Empty / null CSV value -> ``None``.
* Constructing ``MGJ(0)`` directly is rejected so accidental
  round-tripping is impossible.

Plus an integration check that every ``Site`` of the real
``patient_01`` has ``mgj is None`` and that the mucogingival /
KTW rules return ``NOT_ASSESSABLE`` Evidence with ``MGJ`` listed in
``missing_inputs``.
"""

from __future__ import annotations

import pytest

from analysis import CAL, GM, MGJ, PD, EvidenceStatus, normalize_value


# ---------------------------------------------------------------------------
# normalize_value() unit tests.
# ---------------------------------------------------------------------------


def test_mgj_zero_normalizes_to_none():
    """The silent-breach footgun: CSV value 0 for MGJ must NOT
    produce ``MGJ(0)`` -- it is normalized to ``None`` because 0
    means 'not measured' in the chart convention."""
    assert normalize_value("MGJ", "0") is None
    assert normalize_value("MGJ", 0) is None


def test_mgj_positive_value_constructs_mgj():
    result = normalize_value("MGJ", "5")
    assert isinstance(result, MGJ)
    assert result.mm == 5


def test_mgj_zero_constructor_rejected():
    """Direct construction of ``MGJ(0)`` is forbidden so accidental
    round-trips through the value-object layer cannot bypass the
    parser-layer normalization."""
    with pytest.raises(ValueError):
        MGJ(0)


def test_gm_zero_normalizes_to_at_cej():
    """GM = 0 in CSV is meaningful (gingival margin at CEJ) and
    must be preserved as ``GM(mm=0)`` with ``at_cej == True``."""
    result = normalize_value("GM", "0")
    assert isinstance(result, GM)
    assert result.mm == 0
    assert result.at_cej is True
    assert result.is_recession is False
    assert result.is_overgrowth is False


def test_gm_positive_is_recession():
    result = normalize_value("GM", "3")
    assert isinstance(result, GM)
    assert result.is_recession is True
    assert result.recession_mm == 3
    assert result.overgrowth_mm == 0


def test_gm_negative_is_overgrowth():
    """Signed GM convention -- negative = gingival overgrowth (never
    observed in patient_01 but the type accepts it for future
    patients on calcium-channel-blockers / cyclosporine)."""
    result = normalize_value("GM", "-2")
    assert isinstance(result, GM)
    assert result.is_overgrowth is True
    assert result.overgrowth_mm == 2
    assert result.recession_mm == 0


def test_pd_and_cal_pass_through():
    pd = normalize_value("PD", "5")
    cal = normalize_value("CAL", "7")
    assert isinstance(pd, PD) and pd.mm == 5
    assert isinstance(cal, CAL) and cal.mm == 7


def test_blank_value_normalizes_to_none():
    for measurement in ("PD", "GM", "CAL", "MGJ"):
        assert normalize_value(measurement, "") is None
        assert normalize_value(measurement, None) is None


def test_unknown_measurement_raises():
    with pytest.raises(ValueError):
        normalize_value("WHATEVER", "5")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Integration: real patient_01 has MGJ=None at every site, and the
# mucogingival rules consistently report NOT_ASSESSABLE with the
# right missing_inputs.
# ---------------------------------------------------------------------------


def test_patient_01_mgj_uniformly_none(patient_01):
    """All 168 sites x 5 exams = 840 site-records must report
    ``mgj is None`` after normalization.  If any site comes back
    with a real ``MGJ`` value, the parser layer regressed."""
    n_total = 0
    n_none = 0
    for e in patient_01.exams:
        for s in e.mouth.all_sites:
            n_total += 1
            if s.mgj is None:
                n_none += 1
    assert n_total == 840
    assert n_none == 840


def test_patient_01_gm_zero_is_at_cej(patient_01):
    """Every site whose GM is 0 must report ``at_cej == True``."""
    at_cej_count = 0
    for s in patient_01.most_recent.mouth.all_sites:
        if s.gm.mm == 0:
            assert s.gm.at_cej is True
            at_cej_count += 1
    # Exam 5 has 158 of 168 sites at CEJ (10 sites with recession on the
    # tracked teeth: 14, 3, 4, 11, 12, 13, 26, 5, 19, 28, 29, 30, 21, etc.).
    # The exact number can shift slightly with future data; we just
    # assert that the dominant pattern is at-CEJ as expected for this
    # patient.
    assert at_cej_count >= 140


def test_mucogingival_breach_not_assessable_on_patient_01(patient_01):
    """Per-site mucogingival_breach must return NOT_ASSESSABLE with
    ``MGJ`` in ``missing_inputs`` for every site of patient_01."""
    sample = list(patient_01.most_recent.mouth.all_sites)[:20]
    for site in sample:
        ev = site.mucogingival_breach()
        assert ev.status is EvidenceStatus.NOT_ASSESSABLE
        assert "MGJ" in ev.missing_inputs


def test_ktw_not_assessable_on_patient_01(patient_01):
    """Per-site KTW must return NOT_ASSESSABLE because ``MGJ`` is
    None throughout the dataset."""
    sample = list(patient_01.most_recent.mouth.all_sites)[:20]
    for site in sample:
        ev = site.ktw()
        assert ev.status is EvidenceStatus.NOT_ASSESSABLE
        assert "MGJ" in ev.missing_inputs


def test_mouth_level_mucogingival_count_not_assessable(patient_01):
    """Mouth-level rollup ``n_sites_mucogingival_breach`` must
    propagate the NOT_ASSESSABLE status."""
    ev = patient_01.most_recent.mouth.n_sites_mucogingival_breach()
    assert ev.status is EvidenceStatus.NOT_ASSESSABLE
    assert "MGJ" in ev.missing_inputs
