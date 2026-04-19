"""Citation-output guard.

Every ``Evidence`` rendered by the Phase 5 narrative engine must
carry a non-empty ``rule_id`` and a ``citation`` that points back
into ``PERIODONTAL_INTERPRETATION.md``.  This is the invariant that
keeps the renderer auditable -- a future agent reading any line of
the markdown report can trace it back to its clinical source.

If a future Evidence is added with an empty citation or a citation
that doesn't reference the spec, this test fails.
"""

from __future__ import annotations

import re

from analysis import ToothFocus, report


SPEC_FILENAME = "PERIODONTAL_INTERPRETATION.md"
# rule_id convention: lowercase namespace prefix, then dotted identifier
# segments.  Segments may contain uppercase clinical abbreviations
# (PD, CAL, GM, MGJ, KTW, BOP, RBL) and numeric thresholds (4, 6, 2mm),
# so we allow [A-Za-z0-9_] within segments after the lowercase first
# character.  No spaces, no punctuation other than dots and underscores.
RULE_ID_PATTERN = re.compile(r"^[a-z][a-zA-Z0-9_]*(\.[a-zA-Z0-9_]+)+$")


def test_every_rendered_evidence_has_rule_id_and_citation(patient_01):
    rep = report(patient_01)
    assert rep.evidence, "report rendered no Evidence at all"
    for ev in rep.evidence:
        assert ev.rule_id, f"Evidence {ev!r} has empty rule_id"
        assert ev.citation, (
            f"Evidence rule_id={ev.rule_id!r} has empty citation"
        )


def test_every_rendered_evidence_cites_clinical_spec(patient_01):
    rep = report(patient_01)
    offenders: list[str] = []
    for ev in rep.evidence:
        if SPEC_FILENAME not in ev.citation:
            offenders.append(f"{ev.rule_id}: {ev.citation!r}")
    assert not offenders, (
        f"{len(offenders)} Evidence object(s) do not cite "
        f"{SPEC_FILENAME}:\n  " + "\n  ".join(offenders)
    )


def test_rule_id_naming_convention(patient_01):
    """``rule_id`` should be lowercase dotted words.  Catches
    accidental rule_ids like 'foo bar' or 'Stage III' that would
    break narrative anchors / grouping in any downstream tooling."""
    rep = report(patient_01)
    offenders = [
        ev.rule_id for ev in rep.evidence
        if not RULE_ID_PATTERN.match(ev.rule_id)
    ]
    assert not offenders, (
        f"rule_ids violate lowercase-dotted-words convention: {offenders}"
    )


def test_focus_tooth_question_is_addressed_in_audit(patient_01):
    """When a ``ToothFocus`` is passed in, the Evidence stream must
    include the per-tooth Evidence rules (recession trajectory,
    intervention assessment, prognosis floor) for the requested
    tooth -- so the renderer's clinical-questions section is
    actually backed by structured Evidence rather than free text."""
    rep = report(
        patient_01,
        focus_teeth=(
            ToothFocus(tooth_number=11, question="dummy"),
        ),
    )
    rule_ids = {ev.rule_id for ev in rep.evidence}
    assert any(
        rid.startswith("longitudinal.recession_trajectory") for rid in rule_ids
    )
    assert any(
        rid.startswith("longitudinal.soft_tissue_intervention") for rid in rule_ids
    )
    assert any(rid.startswith("prognosis.floor") for rid in rule_ids)


def test_audit_trail_is_self_consistent(patient_01):
    """Every Evidence rule_id rendered should appear in the markdown
    audit-trail table at the bottom of the report.  This is the
    invariant that lets a reader cross-reference any clinical claim
    with its rule_id."""
    rep = report(patient_01)
    rendered_ids = {ev.rule_id for ev in rep.evidence}
    for rid in rendered_ids:
        assert f"`{rid}`" in rep.markdown, (
            f"rule_id {rid!r} is in the audit list but does not appear "
            "in the rendered markdown -- audit trail and report drifted"
        )
