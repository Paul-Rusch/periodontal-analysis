"""Provisional-propagation guard.

Two rules must always come back as ``EvidenceStatus.PROVISIONAL``
with the expected explanatory fields populated:

* ``Mouth.stage()`` -- AAP/EFP Stage III (for patient_01) carries
  Stage IV upgrade inputs in ``missing_inputs`` and an explicit
  assumption explaining the cap.
* ``Patient.grade()`` -- AAP/EFP Grade A/B/C from longitudinal CAL
  always carries the ``"projected from {N}-year window"``
  assumption because the published thresholds are 5-year and the
  observation window here is shorter.

If either of these flips to ``SUPPORTED`` accidentally, the report's
clinical disclaimer signal weakens silently.
"""

from __future__ import annotations

from analysis import EvidenceStatus


def test_stage_provisional_with_stage_iv_inputs_listed(patient_01):
    ev = patient_01.most_recent.mouth.stage()
    assert ev.value == "III"
    assert ev.status is EvidenceStatus.PROVISIONAL
    expected_missing = {
        "RBL_percent",
        "teeth_lost_to_periodontitis",
        "mobility_grade",
        "furcation_class",
        "remaining_teeth_count",
    }
    assert expected_missing.issubset(set(ev.missing_inputs)), (
        f"Stage Evidence missing expected Stage IV upgrade inputs; "
        f"got {ev.missing_inputs}"
    )
    # An explicit assumption explaining the Stage IV cap must be
    # present (the Phase 5 renderer surfaces these in the caveats
    # section).
    assert any("Stage IV" in a for a in ev.assumptions), (
        f"Stage Evidence missing 'Stage IV upgrade ...' assumption; "
        f"got {ev.assumptions}"
    )


def test_grade_provisional_with_projection_window_assumption(patient_01):
    """Grade is computed from longitudinal CAL across the available
    window; status must be PROVISIONAL and the
    ``"projected from {N}-year window"`` assumption must be present."""
    ev = patient_01.grade()
    assert ev.status is EvidenceStatus.PROVISIONAL
    assert ev.value in ("A", "B", "C"), f"unexpected Grade value {ev.value!r}"
    assert any(
        "projected from" in a and "year window" in a for a in ev.assumptions
    ), (
        f"Grade Evidence missing the mandatory projection-window "
        f"assumption; got {ev.assumptions}"
    )


def test_grade_assumption_carries_real_window_years(patient_01):
    """The projection-window string must reference a window value
    that matches ``patient.window_years`` (so a renderer can show
    the actual window without re-deriving it)."""
    ev = patient_01.grade()
    # The assumption text contains "{N.NN}-year window"; pull the
    # numeric value back out and compare.
    assumption = next(a for a in ev.assumptions if "year window" in a)
    expected = f"{patient_01.window_years:.2f}"
    assert expected in assumption, (
        f"projection-window text {assumption!r} does not contain the "
        f"actual window {expected}"
    )


def test_grade_status_constant_across_all_callers(patient_01):
    """Whether grade is computed across the full window or a sub-
    window, status remains PROVISIONAL.  (The clinical floor is the
    5-year extrapolation; that floor doesn't disappear on a smaller
    window.)"""
    full = patient_01.grade(label="full_window")
    post_srp = patient_01.grade(start_exam_index=2, end_exam_index=5, label="post_srp")
    assert full.status is EvidenceStatus.PROVISIONAL
    assert post_srp.status is EvidenceStatus.PROVISIONAL


def test_evidence_post_init_blocks_uncited_provisional():
    """Direct check on the contract: a PROVISIONAL Evidence with
    no assumption AND no missing_input must raise.  This contract
    is what guarantees Stage / Grade caveats can never be silently
    dropped."""
    from analysis import Evidence

    import pytest

    with pytest.raises(ValueError):
        Evidence(
            rule_id="test.uncited",
            scope=(),
            status=EvidenceStatus.PROVISIONAL,
            threshold_crossed="",
            citation="",
        )
