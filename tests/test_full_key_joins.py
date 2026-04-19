"""Full-key delta-join guard.

PERIODONTAL_INTERPRETATION.md sec 15.1 requires per-site delta
computations to join on the full key
``(patient_id, arch, surface, tooth_number, site)``.  Joining on a
partial key (e.g. just ``tooth_number``) silently merges sites that
should be distinct -- the standard 28-tooth dentition does not
overlap tooth_numbers across arches, but a partial-arch chart or a
patient with renumbered teeth (or two patients in the same call)
would silently fail.

The unit tests pin the ``SiteKey`` equality contract directly; the
integration test asserts that a real per-site delta on
``patient_01`` produces exactly 168 distinct delta records (no
collisions).
"""

from __future__ import annotations

from analysis import SiteKey, per_site_deltas


# ---------------------------------------------------------------------------
# Unit tests on SiteKey equality / hash.
# ---------------------------------------------------------------------------


def _sk(**overrides) -> SiteKey:
    """Construct a SiteKey with sensible defaults; override per test."""
    base = dict(
        patient_id="p",
        arch="maxillary",
        surface="facial",
        tooth_number=14,
        site="distal",
    )
    base.update(overrides)
    return SiteKey(**base)


def test_site_key_equal_when_all_fields_match():
    a = _sk()
    b = _sk()
    assert a == b
    assert hash(a) == hash(b)


def test_site_key_distinguishes_arch():
    """Same tooth_number in different arches must NOT collide."""
    assert _sk(arch="maxillary") != _sk(arch="mandibular")


def test_site_key_distinguishes_surface():
    """facial vs lingual at the same site must NOT collide."""
    assert _sk(surface="facial") != _sk(surface="lingual")


def test_site_key_distinguishes_site_position():
    """distal vs mesial vs central at the same tooth must NOT collide."""
    assert _sk(site="distal") != _sk(site="mesial")
    assert _sk(site="distal") != _sk(site="central")
    assert _sk(site="mesial") != _sk(site="central")


def test_site_key_distinguishes_tooth_number():
    assert _sk(tooth_number=14) != _sk(tooth_number=15)


def test_site_key_distinguishes_patient_id():
    assert _sk(patient_id="patient_01") != _sk(patient_id="patient_02")


# ---------------------------------------------------------------------------
# Integration test: real per_site_deltas on patient_01 must produce
# 168 distinct delta records (one per site), confirming the join is
# not collapsing distinct sites.
# ---------------------------------------------------------------------------


def test_per_site_deltas_no_collisions(patient_01):
    deltas = per_site_deltas(patient_01.exam(1), patient_01.exam(5))
    # 28 teeth x 2 surfaces x 3 sites = 168 sites.
    assert len(deltas) == 168
    site_keys = {d.site_key for d in deltas}
    assert len(site_keys) == 168, (
        "duplicate SiteKey found in per_site_deltas output -- the join "
        "collapsed distinct sites; check SiteKey equality and "
        "per_site_deltas grouping"
    )
