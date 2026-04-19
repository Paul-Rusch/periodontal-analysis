"""Phase 4 longitudinal layer.

Joins use the full key ``(patient_id, arch, surface, measurement,
tooth_number, site)`` per PERIODONTAL_INTERPRETATION.md sec 15.1, and
chronological ordering is *always* by ``ExamKey`` (i.e. by
``exam_index`` / ``exam_date``), never by ``chart_id``.

What lives here:

* :func:`per_site_deltas` -- all PD / CAL / GM site-level changes
  between any two exams.
* :func:`treatment_response` -- the §15.1 widget bundle returned as
  one Evidence per metric.
* :func:`trend_series` -- the §15.2 mouth-level trend lines.
* :func:`grade` -- AAP/EFP A/B/C from longitudinal CAL per §15.3.
  Always provisional, always carries the explicit
  ``"projected from {window:.2f}-year window"`` assumption.
  Optional ``start_exam_index`` / ``end_exam_index`` parameters let
  the caller compute Grade across an arbitrary sub-window -- patient
  ``patient_01`` gets two: one across the full window (which crosses
  the SRP boundary and is therefore confounded by treatment) and one
  across the post-SRP maintenance phase only.
* :func:`s3_pd_only_endpoint` -- §15.4 PD-only treatment endpoint
  flag per exam (full endpoint requires BOP, which we do not have).
* :func:`tooth_loss_events` -- §15.5 tooth-loss tracker; per
  consecutive exam pair, surface any tooth_number that disappears.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from analysis import citations
from analysis.evidence import Evidence, EvidenceStatus
from analysis.normalize import SiteKey

if TYPE_CHECKING:  # avoid import cycle at module load
    from analysis.exam import Exam
    from analysis.patient import Patient


# ---------------------------------------------------------------------------
# Per-site deltas (sec 15.1).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SiteDelta:
    """One per-site change record between two exams.  Fields are
    ``None`` whenever the underlying value was ``None`` at either end
    of the window."""

    site_key: SiteKey
    delta_PD: int | None
    delta_CAL: int | None
    delta_GM: int | None


def per_site_deltas(from_exam: Exam, to_exam: Exam) -> tuple[SiteDelta, ...]:
    """Compute per-site deltas joining on the full
    ``(patient_id, arch, surface, tooth_number, site)`` key.

    ``measurement`` is not part of the key here because each
    ``Site`` already carries all four measurements -- the join is on
    the *site*, and per-measurement deltas come out of that.
    """
    by_key: dict[SiteKey, dict[str, int | None]] = {}
    for s in from_exam.mouth.all_sites:
        by_key.setdefault(s.site_key, {})["from_PD"] = (
            s.pd.mm if s.pd is not None else None
        )
        by_key[s.site_key]["from_CAL"] = s.cal.mm if s.cal is not None else None
        by_key[s.site_key]["from_GM"] = s.gm.mm
    for s in to_exam.mouth.all_sites:
        by_key.setdefault(s.site_key, {})["to_PD"] = (
            s.pd.mm if s.pd is not None else None
        )
        by_key[s.site_key]["to_CAL"] = s.cal.mm if s.cal is not None else None
        by_key[s.site_key]["to_GM"] = s.gm.mm

    out: list[SiteDelta] = []
    for sk, cells in by_key.items():
        out.append(
            SiteDelta(
                site_key=sk,
                delta_PD=_safe_sub(cells.get("to_PD"), cells.get("from_PD")),
                delta_CAL=_safe_sub(cells.get("to_CAL"), cells.get("from_CAL")),
                delta_GM=_safe_sub(cells.get("to_GM"), cells.get("from_GM")),
            )
        )
    return tuple(out)


def _safe_sub(a: int | None, b: int | None) -> int | None:
    if a is None or b is None:
        return None
    return a - b


# ---------------------------------------------------------------------------
# Treatment-response widget bundle (sec 15.1).
# ---------------------------------------------------------------------------


def treatment_response(from_exam: Exam, to_exam: Exam) -> tuple[Evidence, ...]:
    """Widget set per PERIODONTAL_INTERPRETATION.md sec 15.1: the
    "what changed between these two exams" tile group.  >=2 mm at a
    site is the standard "clinically meaningful" cutoff (Florida
    Probe / PracticeWorks convention) [10][20]."""
    deltas = per_site_deltas(from_exam, to_exam)
    n_pd = sum(1 for d in deltas if d.delta_PD is not None)
    n_cal = sum(1 for d in deltas if d.delta_CAL is not None)
    n_gm = sum(1 for d in deltas if d.delta_GM is not None)

    pd_changes = [d.delta_PD for d in deltas if d.delta_PD is not None]
    cal_changes = [d.delta_CAL for d in deltas if d.delta_CAL is not None]
    gm_changes = [d.delta_GM for d in deltas if d.delta_GM is not None]

    pct_pd_improved = (
        100.0 * sum(1 for x in pd_changes if x <= -2) / n_pd if n_pd else 0.0
    )
    pct_pd_worsened = (
        100.0 * sum(1 for x in pd_changes if x >= +2) / n_pd if n_pd else 0.0
    )
    pct_cal_lost = (
        100.0 * sum(1 for x in cal_changes if x >= +2) / n_cal if n_cal else 0.0
    )
    pct_cal_gained = (
        100.0 * sum(1 for x in cal_changes if x <= -2) / n_cal if n_cal else 0.0
    )
    n_recession_progressed = sum(1 for x in gm_changes if x >= +1) if n_gm else 0
    mean_pd_change = sum(pd_changes) / n_pd if n_pd else 0.0
    mean_cal_change = sum(cal_changes) / n_cal if n_cal else 0.0

    base_scope = (
        from_exam.patient_id,
        from_exam.exam_index,
        to_exam.exam_index,
    )

    def _ev(rule_id: str, value: float, threshold: str) -> Evidence:
        return Evidence(
            rule_id=rule_id,
            scope=base_scope,
            status=EvidenceStatus.SUPPORTED,
            threshold_crossed=threshold,
            citation=citations.LONGITUDINAL_TREATMENT_RESPONSE,
            value=round(value, 2),
            trigger_measurements=(
                {"name": "from_exam_index", "value": from_exam.exam_index},
                {"name": "to_exam_index", "value": to_exam.exam_index},
                {"name": "from_date", "value": from_exam.exam_date.isoformat()},
                {"name": "to_date", "value": to_exam.exam_date.isoformat()},
            ),
        )

    return (
        _ev("longitudinal.pct_sites_PD_improved_ge_2mm", pct_pd_improved,
            "% sites with delta_PD <= -2"),
        _ev("longitudinal.pct_sites_PD_worsened_ge_2mm", pct_pd_worsened,
            "% sites with delta_PD >= +2"),
        _ev("longitudinal.pct_sites_CAL_lost_ge_2mm", pct_cal_lost,
            "% sites with delta_CAL >= +2 (progression)"),
        _ev("longitudinal.pct_sites_CAL_gained_ge_2mm", pct_cal_gained,
            "% sites with delta_CAL <= -2 (improvement)"),
        _ev("longitudinal.n_sites_recession_progression",
            float(n_recession_progressed),
            "count(sites with delta_GM >= +1)"),
        _ev("longitudinal.mean_PD_change", mean_pd_change, "mean(delta_PD)"),
        _ev("longitudinal.mean_CAL_change", mean_cal_change, "mean(delta_CAL)"),
    )


# ---------------------------------------------------------------------------
# Trend series (sec 15.2).
# ---------------------------------------------------------------------------


def trend_series(patient: Patient, metric_name: str) -> Evidence:
    """Return one Evidence carrying a per-exam value series for one
    mouth-level metric.  Phase 5 renders these as line/bar charts.

    Supported ``metric_name`` values (sec 15.2):
    * ``mean_PD``, ``mean_CAL``
    * ``pct_sites_PD_ge_4``, ``pct_sites_PD_ge_5``, ``pct_sites_PD_ge_6``
    * ``n_teeth_with_PD_ge_6``, ``n_teeth_with_CAL_ge_5``
    * ``max_interdental_CAL``
    """
    series: list[dict] = []
    for e in patient.exams:
        if metric_name == "mean_PD":
            v = round(e.mouth.mean_PD, 3)
        elif metric_name == "mean_CAL":
            v = round(e.mouth.mean_CAL, 3)
        elif metric_name.startswith("pct_sites_PD_ge_"):
            thr = int(metric_name.rsplit("_", 1)[-1])
            v = round(e.mouth.pct_sites_PD_ge(thr), 2)
        elif metric_name.startswith("pct_sites_CAL_ge_"):
            thr = int(metric_name.rsplit("_", 1)[-1])
            v = round(e.mouth.pct_sites_CAL_ge(thr), 2)
        elif metric_name == "n_teeth_with_PD_ge_6":
            v = e.mouth.n_teeth_with_PD_ge(6)
        elif metric_name == "n_teeth_with_CAL_ge_5":
            v = e.mouth.n_teeth_with_CAL_ge(5)
        elif metric_name == "max_interdental_CAL":
            v = e.mouth.max_interdental_CAL().value
        else:
            raise ValueError(f"unknown trend metric: {metric_name!r}")
        series.append(
            {
                "exam_index": e.exam_index,
                "exam_date": e.exam_date.isoformat(),
                "value": v,
            }
        )
    return Evidence(
        rule_id=f"longitudinal.trend.{metric_name}",
        scope=(patient.patient_id,),
        status=EvidenceStatus.SUPPORTED,
        threshold_crossed=f"per-exam time series of {metric_name}",
        citation=citations.LONGITUDINAL_TREND,
        value=tuple(series),
    )


# ---------------------------------------------------------------------------
# AAP/EFP Grade A/B/C from longitudinal CAL (sec 15.3) -- always provisional.
# ---------------------------------------------------------------------------


def grade(
    patient: Patient,
    *,
    start_exam_index: int | None = None,
    end_exam_index: int | None = None,
    label: str | None = None,
) -> Evidence:
    """Return AAP/EFP Grade A/B/C via the §15.3 direct-evidence path.

    ``Evidence.status`` is *always* ``PROVISIONAL`` -- the published
    Grade thresholds are 5-year, this dataset's window is shorter,
    and the resulting 5-year-equivalent CAL change carries the
    mandatory ``"projected from {window:.2f}-year window"`` assumption.

    Optional ``start_exam_index`` / ``end_exam_index`` window the
    computation to a sub-range (e.g. post-SRP maintenance phase only).
    ``label`` annotates the rule_id so multiple Grade Evidence
    objects from the same patient remain distinguishable.

    The progression metric is ``max(delta_CAL)`` over per-site joins,
    consistent with sec 15.1's full-key join rule and AAP's
    "worst-site progression drives Grade" reading of the spec.
    """
    exams = patient.exams
    if not exams:
        return Evidence(
            rule_id="aap_efp_2018.grade",
            scope=(patient.patient_id,),
            status=EvidenceStatus.NOT_ASSESSABLE,
            threshold_crossed="Grade A/B/C from per-site max(delta_CAL)",
            citation=citations.LONGITUDINAL_GRADE,
            missing_inputs=("at_least_two_exams",),
        )
    start = start_exam_index or exams[0].exam_index
    end = end_exam_index or exams[-1].exam_index
    if start == end:
        return Evidence(
            rule_id="aap_efp_2018.grade",
            scope=(patient.patient_id, start, end),
            status=EvidenceStatus.NOT_ASSESSABLE,
            threshold_crossed="Grade requires distinct start and end exams",
            citation=citations.LONGITUDINAL_GRADE,
            missing_inputs=("distinct_exam_pair",),
        )
    e_start = patient.exam(start)
    e_end = patient.exam(end)
    deltas = per_site_deltas(e_start, e_end)
    cal_changes = [d.delta_CAL for d in deltas if d.delta_CAL is not None]
    if not cal_changes:
        return Evidence(
            rule_id="aap_efp_2018.grade",
            scope=(patient.patient_id, start, end),
            status=EvidenceStatus.NOT_ASSESSABLE,
            threshold_crossed="Grade A/B/C from per-site max(delta_CAL)",
            citation=citations.LONGITUDINAL_GRADE,
            missing_inputs=("CAL",),
        )

    max_cal_change_obs = max(cal_changes)  # most-progressed site
    window_years = (e_end.exam_date - e_start.exam_date).days / 365.25
    if window_years <= 0:
        return Evidence(
            rule_id="aap_efp_2018.grade",
            scope=(patient.patient_id, start, end),
            status=EvidenceStatus.NOT_ASSESSABLE,
            threshold_crossed="Grade A/B/C from per-site max(delta_CAL)",
            citation=citations.LONGITUDINAL_GRADE,
            missing_inputs=("positive_window",),
        )
    cal_change_5yr_equiv = max_cal_change_obs * (5.0 / window_years)

    if max_cal_change_obs <= 0:
        bin_label = "A"
    elif cal_change_5yr_equiv < 2.0:
        bin_label = "B"
    else:
        bin_label = "C"

    suffix = f".{label}" if label else ""
    return Evidence(
        rule_id=f"aap_efp_2018.grade.{bin_label.lower()}{suffix}",
        scope=(patient.patient_id, start, end),
        status=EvidenceStatus.PROVISIONAL,
        threshold_crossed=(
            "A: max(delta_CAL) <= 0; B: 5-yr-equiv < 2 mm; C: 5-yr-equiv >= 2 mm"
        ),
        citation=citations.LONGITUDINAL_GRADE,
        value=bin_label,
        trigger_measurements=(
            {"name": "start_exam_index", "value": start},
            {"name": "end_exam_index", "value": end},
            {"name": "start_date", "value": e_start.exam_date.isoformat()},
            {"name": "end_date", "value": e_end.exam_date.isoformat()},
            {"name": "window_years", "value": round(window_years, 3)},
            {"name": "max_cal_change_observed_mm", "value": max_cal_change_obs},
            {"name": "cal_change_5yr_equiv_mm", "value": round(cal_change_5yr_equiv, 3)},
        ),
        assumptions=(
            f"projected from {window_years:.2f}-year window (published "
            "thresholds are 5-year; result scaled linearly)",
        ),
        missing_inputs=("age", "smoking_status", "hba1c"),
    )


# ---------------------------------------------------------------------------
# EFP S3 PD-only treatment endpoint (sec 15.4).
# ---------------------------------------------------------------------------


def s3_pd_only_endpoint(exam: Exam) -> Evidence:
    """Per-exam PD-only EFP S3 treatment-endpoint flag.  True when no
    site has PD >= 6.  Always carries a ``missing_inputs=["BOP"]``
    flag because the full endpoint additionally requires "no PD >= 5
    with BOP".  PERIODONTAL_INTERPRETATION.md sec 15.4 [20]."""
    n_teeth_pd_ge_6 = exam.mouth.n_teeth_with_PD_ge(6)
    achieved = n_teeth_pd_ge_6 == 0
    return Evidence(
        rule_id=(
            "efp_s3.endpoint.pd_only.achieved"
            if achieved
            else "efp_s3.endpoint.pd_only.not_achieved"
        ),
        scope=(exam.patient_id, exam.exam_index),
        status=EvidenceStatus.PROVISIONAL,
        threshold_crossed="no tooth with max_PD >= 6",
        citation=citations.LONGITUDINAL_S3_PD_ONLY,
        value=achieved,
        trigger_measurements=(
            {"name": "n_teeth_with_PD_ge_6", "value": n_teeth_pd_ge_6},
            {"name": "max_PD_mouth", "mm": exam.mouth.max_PD},
        ),
        missing_inputs=("BOP",),
        assumptions=(
            "PD-only floor variant of the EFP S3 endpoint; full endpoint "
            "additionally requires 'no PD >= 5 with BOP'",
        ),
    )


# ---------------------------------------------------------------------------
# Tooth-loss tracking (sec 15.5).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Recession trajectory + soft-tissue surgery assessment (sec 2.2, sec 10,
# sec 15.1).  These look across the whole exam window for one tooth.
# ---------------------------------------------------------------------------


def recession_trajectory(patient: Patient, tooth_number: int) -> Evidence:
    """Per-site recession trajectory for one tooth across all exams.

    ``Evidence.value`` is one of:

    * ``"improving"`` -- at least one site has GM that decreased by >= 1 mm
      from baseline to most-recent (typical of a successful PST/graft).
    * ``"progressing"`` -- at least one site has GM that increased by >= 1 mm
      (recession is worsening at one or more sites).
    * ``"stable"`` -- no per-site GM change of >= 1 mm in either direction.

    PERIODONTAL_INTERPRETATION.md sec 2.2 + sec 15.1.  Status is
    SUPPORTED -- this is just a per-site delta read off the chart data.
    """
    if tooth_number not in patient.baseline.mouth.teeth:
        return Evidence(
            rule_id="longitudinal.recession_trajectory",
            scope=(patient.patient_id, tooth_number),
            status=EvidenceStatus.NOT_ASSESSABLE,
            threshold_crossed="per-site delta_GM across exam window",
            citation=citations.RECESSION_TRAJECTORY,
            missing_inputs=("tooth_present_at_baseline",),
        )
    site_keys = sorted(
        {s.site_key for s in patient.baseline.tooth(tooth_number).sites},
        key=lambda sk: (sk.surface, sk.site),
    )
    trajectories: list[dict] = []
    has_progression = False
    has_improvement = False
    for sk in site_keys:
        gms: list[tuple[int, int]] = []  # (exam_index, gm_mm)
        for e in patient.exams:
            if tooth_number not in e.mouth.teeth:
                continue
            t = e.tooth(tooth_number)
            try:
                site = t.site(sk.surface, sk.site)
            except KeyError:
                continue
            gms.append((e.exam_index, site.gm.mm))
        if len(gms) < 2:
            continue
        baseline_gm = gms[0][1]
        recent_gm = gms[-1][1]
        delta = recent_gm - baseline_gm
        if delta >= 1:
            has_progression = True
        if delta <= -1:
            has_improvement = True
        trajectories.append(
            {
                "surface": sk.surface,
                "site": sk.site,
                "gm_per_exam": tuple({"exam_index": ei, "gm_mm": v} for ei, v in gms),
                "delta_gm_baseline_to_recent": delta,
            }
        )
    if has_progression and not has_improvement:
        label = "progressing"
    elif has_improvement and not has_progression:
        label = "improving"
    elif has_improvement and has_progression:
        label = "mixed"
    else:
        label = "stable"
    return Evidence(
        rule_id=f"longitudinal.recession_trajectory.{label}",
        scope=(patient.patient_id, tooth_number),
        status=EvidenceStatus.SUPPORTED,
        threshold_crossed=(
            "per-site delta_GM (baseline -> most recent): "
            ">=+1 mm at any site -> progressing; <=-1 mm at any site -> improving; "
            "both -> mixed; otherwise stable"
        ),
        citation=citations.RECESSION_TRAJECTORY,
        value=label,
        trigger_measurements=tuple(trajectories),
    )


def pst_or_graft_treatment_response(
    patient: Patient,
    tooth_number: int,
) -> Evidence | None:
    """If a PST / graft event exists in this patient's history for this
    tooth, return an Evidence summarising its effectiveness as the
    delta_GM across the exam pair that brackets the procedure date.

    Returns ``None`` if no soft-tissue surgical event is recorded for
    this tooth -- callers should treat ``None`` as "not applicable".

    PERIODONTAL_INTERPRETATION.md sec 15.1 + sec 2.2.
    """
    relevant_subtypes = {
        "pinhole_soft_tissue_technique",
        "free_gingival_graft",
        "connective_tissue_graft",
        "coronally_advanced_flap",
    }
    events = [
        ev
        for ev in patient.history.for_tooth(tooth_number)
        if ev.event_type == "dental-therapy" and ev.event_subtype in relevant_subtypes
    ]
    if not events:
        return None
    event = events[0]  # single procedure assumed; multi-event extension later
    # Bracketing exams: last exam strictly before procedure window, first
    # exam strictly after.
    pre_exam: Exam | None = None
    post_exam: Exam | None = None
    if event.start_date is not None:
        candidates_before = [
            e for e in patient.exams if e.exam_date <= event.start_date
        ]
        if candidates_before:
            pre_exam = candidates_before[-1]
    if event.end_date is not None:
        candidates_after = [
            e for e in patient.exams if e.exam_date >= event.end_date
        ]
        if candidates_after:
            post_exam = candidates_after[0]
    if pre_exam is None or post_exam is None or pre_exam.exam_index == post_exam.exam_index:
        return Evidence(
            rule_id="longitudinal.pst_or_graft_response",
            scope=(patient.patient_id, tooth_number, event.event_subtype),
            status=EvidenceStatus.NOT_ASSESSABLE,
            threshold_crossed="bracketing pre-/post-procedure exams required",
            citation=citations.SOFT_TISSUE_TREATMENT_RESPONSE,
            missing_inputs=("pre_procedure_exam", "post_procedure_exam"),
        )
    pre_tooth = pre_exam.tooth(tooth_number)
    post_tooth = post_exam.tooth(tooth_number)
    per_site: list[dict] = []
    max_gm_reduction = 0
    for s_pre in pre_tooth.sites:
        try:
            s_post = post_tooth.site(s_pre.site_key.surface, s_pre.site_key.site)
        except KeyError:
            continue
        delta_gm = s_post.gm.mm - s_pre.gm.mm
        max_gm_reduction = max(max_gm_reduction, -delta_gm)
        if s_pre.gm.mm > 0 or delta_gm != 0:
            per_site.append(
                {
                    "surface": s_pre.site_key.surface,
                    "site": s_pre.site_key.site,
                    "pre_gm_mm": s_pre.gm.mm,
                    "post_gm_mm": s_post.gm.mm,
                    "delta_gm_mm": delta_gm,
                }
            )
    return Evidence(
        rule_id=f"longitudinal.pst_or_graft_response.{event.event_subtype}",
        scope=(patient.patient_id, tooth_number, event.event_subtype),
        status=EvidenceStatus.SUPPORTED,
        threshold_crossed="post-procedure GM compared to last pre-procedure exam",
        citation=citations.SOFT_TISSUE_TREATMENT_RESPONSE,
        value=max_gm_reduction,  # mm of recession reduction at the most-improved site
        trigger_measurements=(
            {"name": "tooth_number", "value": tooth_number},
            {"name": "procedure", "value": event.event_subtype},
            {"name": "pre_exam_index", "value": pre_exam.exam_index},
            {"name": "post_exam_index", "value": post_exam.exam_index},
            {"name": "pre_exam_date", "value": pre_exam.exam_date.isoformat()},
            {"name": "post_exam_date", "value": post_exam.exam_date.isoformat()},
            {"name": "per_site_changes", "value": tuple(per_site)},
        ),
    )


def soft_tissue_intervention_assessment(
    patient: Patient,
    tooth_number: int,
) -> Evidence:
    """Surface what the chart data says about whether this tooth is a
    candidate for soft-tissue intervention (PST, free gingival graft,
    coronally advanced flap, etc.).

    ``Evidence.value`` is one of:
    * ``"already_treated"`` -- a soft-tissue procedure is on file for
      this tooth; pst_or_graft_treatment_response reports outcome.
    * ``"recommended_for_evaluation"`` -- max_recession >= 2 mm AND
      recession trajectory is progressing.
    * ``"monitor"`` -- max_recession >= 2 mm but stable across the
      available exam window.
    * ``"no_significant_recession"`` -- max_recession < 2 mm.

    Status is **always PROVISIONAL** because the actual surgical
    decision additionally requires (a) MGJ / KTW assessment (we have
    none -- "not assessable" is in missing_inputs), (b) intra-oral
    clinician examination (aesthetic concern, root sensitivity,
    bone contour), and (c) patient factors (smoking, OH compliance).

    PERIODONTAL_INTERPRETATION.md sec 10 + sec 14 rule 1 [6][7].
    """
    if tooth_number not in patient.most_recent.mouth.teeth:
        return Evidence(
            rule_id="longitudinal.soft_tissue_intervention",
            scope=(patient.patient_id, tooth_number),
            status=EvidenceStatus.NOT_ASSESSABLE,
            threshold_crossed="recession + trajectory + KTW",
            citation=citations.SOFT_TISSUE_INTERVENTION,
            missing_inputs=("tooth_present_at_most_recent_exam",),
        )

    prior = pst_or_graft_treatment_response(patient, tooth_number)
    if prior is not None and prior.is_supported:
        return Evidence(
            rule_id="longitudinal.soft_tissue_intervention.already_treated",
            scope=(patient.patient_id, tooth_number),
            status=EvidenceStatus.PROVISIONAL,
            threshold_crossed=(
                "soft-tissue procedure already on file for this tooth; "
                "see longitudinal.pst_or_graft_response for outcome"
            ),
            citation=citations.SOFT_TISSUE_INTERVENTION,
            value="already_treated",
            trigger_measurements=(
                {
                    "name": "prior_procedure",
                    "value": prior.scope[-1] if len(prior.scope) >= 3 else None,
                },
                {"name": "max_gm_reduction_mm", "value": prior.value},
            ),
            missing_inputs=("MGJ", "KTW"),
            assumptions=(
                "outcome of prior procedure assessable via PD/GM only; "
                "long-term stability requires re-assessment of attached "
                "tissue band (MGJ not recorded)",
            ),
        )

    recent_tooth = patient.most_recent.tooth(tooth_number)
    max_recession = recent_tooth.max_recession
    trajectory = recession_trajectory(patient, tooth_number)
    trajectory_label = trajectory.value

    threshold_text = (
        "max_recession >= 2 mm AND trajectory progressing -> recommend "
        "evaluation; >= 2 mm AND stable -> monitor; < 2 mm -> no "
        "significant recession"
    )

    if max_recession < 2:
        label = "no_significant_recession"
    elif trajectory_label == "progressing":
        label = "recommended_for_evaluation"
    else:
        label = "monitor"

    return Evidence(
        rule_id=f"longitudinal.soft_tissue_intervention.{label}",
        scope=(patient.patient_id, tooth_number),
        status=EvidenceStatus.PROVISIONAL,
        threshold_crossed=threshold_text,
        citation=citations.SOFT_TISSUE_INTERVENTION,
        value=label,
        trigger_measurements=(
            {"name": "max_recession_mm_most_recent", "value": max_recession},
            {"name": "trajectory", "value": trajectory_label},
            {"name": "exams_observed", "value": len(patient.exams)},
            {"name": "window_years", "value": round(patient.window_years, 2)},
        ),
        missing_inputs=("MGJ", "KTW", "clinician_intra_oral_exam"),
        assumptions=(
            "decision requires KTW assessment (MGJ not recorded in this "
            "dataset) plus intra-oral clinician judgment (aesthetic "
            "concern, root sensitivity, bone contour) and patient factors "
            "(OH compliance, smoking) beyond the probing chart",
        ),
    )


def tooth_loss_events(patient: Patient) -> tuple[Evidence, ...]:
    """Surface every tooth_number that disappears from one exam to
    the next, in chronological order.  Each event is one Evidence.
    For the current dataset all 28 non-wisdom teeth are present at
    every exam, so this returns an empty tuple -- the rule is wired
    in for any future patient who loses a tooth between visits.
    PERIODONTAL_INTERPRETATION.md sec 15.5."""
    events: list[Evidence] = []
    prev_teeth: set[int] | None = None
    prev_exam: Exam | None = None
    for e in patient.exams:
        teeth_now = set(e.mouth.teeth.keys())
        if prev_teeth is not None and prev_exam is not None:
            lost = sorted(prev_teeth - teeth_now)
            for tooth_number in lost:
                events.append(
                    Evidence(
                        rule_id="longitudinal.tooth_loss",
                        scope=(
                            patient.patient_id,
                            prev_exam.exam_index,
                            e.exam_index,
                            tooth_number,
                        ),
                        status=EvidenceStatus.SUPPORTED,
                        threshold_crossed=(
                            "tooth_number absent from exam_index N "
                            "but present at exam_index N-1"
                        ),
                        citation=citations.LONGITUDINAL_TOOTH_LOSS,
                        value=tooth_number,
                        trigger_measurements=(
                            {
                                "name": "between_exams",
                                "value": (prev_exam.exam_index, e.exam_index),
                            },
                            {
                                "name": "between_dates",
                                "value": (
                                    prev_exam.exam_date.isoformat(),
                                    e.exam_date.isoformat(),
                                ),
                            },
                        ),
                        notes=(
                            "extraction reason (perio vs non-perio) lives in "
                            "manifests/patient_history_events.csv; consult "
                            "Patient.history.for_tooth(...)"
                        ),
                    )
                )
        prev_teeth = teeth_now
        prev_exam = e
    return tuple(events)
