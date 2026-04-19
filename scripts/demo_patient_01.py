#!/usr/bin/env python3
"""End-to-end demonstration of the analytical layer against
``patient_01``.  Runnable manual-regression check; doubles as the seed
of the Phase 5 demo.

Usage::

    python scripts/demo_patient_01.py

Prints a snapshot covering:

* Patient demographics and Phase 0 history events.
* Per-exam classification (Stage / extent / CDC-AAP severity).
* PSR PD-floor codes per sextant at baseline.
* Per-tooth PD / CAL summary across all 5 exams (the maintenance
  flowsheet view).
* SRP treatment response (exam 1 -> exam 2 deltas).
* Maintenance-phase response (exam 2 -> exam 5 deltas).
* AAP/EFP Grade -- both full-window and post-SRP variants, both
  carrying the projection-window assumption.
* EFP S3 PD-only endpoint per exam.
* Tooth-loss events.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analysis import load_patient  # noqa: E402


def main() -> None:
    p = load_patient("patient_01")

    _section("Patient demographics + Phase 0 history")
    _print_patient(p)

    _section("Classification across all 5 exams")
    _print_classifications(p)

    _section("PSR PD-floor codes per sextant @ baseline (exam 1)")
    _print_psr(p)

    _section("Per-tooth flowsheet -- max_PD across all 5 exams")
    _print_tooth_flowsheet(p, "max_PD")

    _section("Per-tooth flowsheet -- max_CAL across all 5 exams")
    _print_tooth_flowsheet(p, "max_CAL")

    _section("Per-tooth prognosis floor @ most-recent exam")
    _print_prognosis(p)

    _section("SRP treatment response (exam 1 -> exam 2)")
    _print_treatment_response(p, from_exam=1, to_exam=2)

    _section("Maintenance-phase response (exam 2 -> exam 5)")
    _print_treatment_response(p, from_exam=2, to_exam=5)

    _section("AAP/EFP Grade -- both windows, always provisional")
    _print_grade(p)

    _section("EFP S3 PD-only treatment endpoint per exam")
    _print_s3(p)

    _section("Tooth-loss tracking")
    _print_tooth_loss(p)

    _section("Sample caveats from Phase 0 history")
    _print_caveats(p)

    _section("Mouth-level trend series")
    _print_trends(p)


# ---------------------------------------------------------------------------
# Renderers (plain print -- Phase 5 markdown renderer comes later).
# ---------------------------------------------------------------------------


def _section(title: str) -> None:
    print()
    print(f"=== {title} ===")


def _print_patient(p) -> None:
    md = p.metadata
    age_baseline = p.age_at(p.baseline.exam_date)
    age_recent = p.age_at(p.most_recent.exam_date)
    print(f"  patient: {p.patient_id}")
    print(f"  dob: {md.dob}  sex: {md.sex}")
    print(f"  family_history_perio: {md.family_history_perio}")
    print(f"    -> {md.family_history_details}")
    print(f"  allergies: {md.allergies}")
    print(
        f"  exam window: {p.window_years:.2f} years "
        f"(baseline {p.baseline.exam_date}; most recent {p.most_recent.exam_date})"
    )
    if age_baseline is not None and age_recent is not None:
        print(f"  age: {age_baseline:.1f} (baseline) -> {age_recent:.1f} (most recent)")
    print(f"  history events ({len(p.history.events)}):")
    for ev in p.history.events:
        scope = (
            f"tooth {ev.tooth_number}"
            if ev.tooth_number is not None
            else f"{ev.start_date} -> {ev.end_date or 'ongoing'}"
        )
        print(
            f"    {ev.event_type:>14s} | {ev.event_subtype:<28s} | {scope}"
        )


def _print_classifications(p) -> None:
    print(
        f"  {'exam':>4s}  {'date':>10s}  {'Stage':>9s}  {'extent':>11s}  "
        f"{'CDC/AAP':>14s}  {'max_interdental_CAL':>21s}  {'mean_PD':>8s}  "
        f"{'n_teeth_PD>=6':>14s}"
    )
    for e in p.exams:
        s = e.mouth.stage()
        x = e.mouth.extent()
        sev = e.mouth.cdc_aap_severity()
        ic = e.mouth.max_interdental_CAL()
        print(
            f"  {e.exam_index:>4d}  {str(e.exam_date):>10s}  "
            f"{s.value:>4s} ({s.status.value[:4]})  {x.value:>11s}  "
            f"{sev.value:>14s}  {ic.value:>21d}  {e.mouth.mean_PD:>8.2f}  "
            f"{e.mouth.n_teeth_with_PD_ge(6):>14d}"
        )


def _print_psr(p) -> None:
    for ev in p.baseline.mouth.psr_pd_floor():
        sextant = ev.scope[-1]
        max_pd = next(
            (t["mm"] for t in ev.trigger_measurements if t["name"] == "max_PD_sextant"),
            None,
        )
        print(
            f"  {sextant:>16s}: code {ev.value}  ({ev.status.value:>11s})  "
            f"max_PD={max_pd}"
        )


def _print_tooth_flowsheet(p, metric: str) -> None:
    headers = "  tooth | " + " | ".join(f"e{e.exam_index}" for e in p.exams)
    print(headers)
    print("  " + "-" * (len(headers) - 2))
    tooth_numbers = sorted(p.baseline.mouth.teeth)
    for tn in tooth_numbers:
        cells = []
        for e in p.exams:
            if tn not in e.mouth.teeth:
                cells.append(" - ")
            else:
                v = getattr(e.mouth.tooth(tn), metric)
                cells.append(f"{v:>2d} ")
        print(f"  {tn:>5d} | " + " | ".join(cells))


def _print_prognosis(p) -> None:
    print(f"  most-recent exam: {p.most_recent.exam_index} ({p.most_recent.exam_date})")
    print(
        f"  {'tooth':>5s}  {'max_PD':>6s}  {'max_CAL':>7s}  "
        f"{'prognosis_floor':>16s}"
    )
    for tn in sorted(p.most_recent.mouth.teeth):
        t = p.most_recent.mouth.tooth(tn)
        pf = t.prognosis_floor()
        print(
            f"  {tn:>5d}  {t.max_PD:>6d}  {t.max_CAL:>7d}  {pf.value:>16s}"
        )


def _print_treatment_response(p, *, from_exam: int, to_exam: int) -> None:
    fe = p.exam(from_exam)
    te = p.exam(to_exam)
    print(
        f"  window: exam {from_exam} ({fe.exam_date}) -> "
        f"exam {to_exam} ({te.exam_date})"
    )
    for ev in p.treatment_response(from_exam=from_exam, to_exam=to_exam):
        print(f"    {ev.rule_id:>52s}: {ev.value}")


def _print_grade(p) -> None:
    g_full = p.grade(label="full_window")
    g_post = p.grade(start_exam_index=2, end_exam_index=5, label="post_srp_maintenance")
    for label, g in (("full window (1->5, crosses SRP boundary)", g_full),
                     ("post-SRP maintenance only (2->5)", g_post)):
        print(f"  {label}:")
        print(f"    Grade {g.value}  ({g.status.value})")
        for t in g.trigger_measurements:
            if t["name"] in (
                "window_years",
                "max_cal_change_observed_mm",
                "cal_change_5yr_equiv_mm",
            ):
                print(f"      {t['name']}: {t['value']}")
        for a in g.assumptions:
            print(f"      assumption: {a}")
        for m in g.missing_inputs:
            print(f"      missing input (could refine): {m}")


def _print_s3(p) -> None:
    for e in p.exams:
        ev = e.s3_pd_only_endpoint()
        n = next(
            (t["value"] for t in ev.trigger_measurements
             if t["name"] == "n_teeth_with_PD_ge_6"),
            None,
        )
        print(
            f"  exam {e.exam_index} ({e.exam_date}): "
            f"achieved={ev.value}  (n_teeth_with_PD>=6={n})"
        )


def _print_tooth_loss(p) -> None:
    events = p.tooth_loss_events()
    if not events:
        print("  no tooth-loss events across the available exam window")
        return
    for ev in events:
        print(f"  {ev.scope}: tooth {ev.value} lost between exams")


def _print_caveats(p) -> None:
    crowned = p.most_recent.tooth(8)
    print(f"  tooth 8 (most-recent exam) caveats: {len(crowned.caveats)}")
    for c in crowned.caveats:
        print(f"    {c.rule_id} ({c.status.value})")
        for a in c.assumptions:
            print(f"      assumption: {a}")
    site = p.most_recent.tooth(8).site("facial", "central")
    print(f"  site (tooth 8 facial central) caveats: {len(site.caveats)}")
    for c in site.caveats:
        print(f"    {c.rule_id} ({c.status.value})")


def _print_trends(p) -> None:
    for metric in (
        "mean_PD",
        "mean_CAL",
        "pct_sites_PD_ge_4",
        "pct_sites_PD_ge_6",
        "n_teeth_with_PD_ge_6",
        "n_teeth_with_CAL_ge_5",
        "max_interdental_CAL",
    ):
        series = p.trend(metric).value
        cells = " | ".join(f"e{pt['exam_index']}={pt['value']}" for pt in series)
        print(f"  {metric:>22s}: {cells}")


if __name__ == "__main__":
    main()
