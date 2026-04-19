"""Top-level loader -- wires the locked CSV and the three Phase 0
manifests into a fully-populated :class:`analysis.patient.Patient`.

This is the only module in the package allowed to read the manifest
CSVs; once a ``Patient`` has been built, downstream code reads only
the typed objects.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

from analysis import citations
from analysis.evidence import Evidence, EvidenceStatus
from analysis.exam import ChartContext, Exam
from analysis.mouth import Mouth
from analysis.normalize import ExamKey, NormalizedSite, SiteKey, iter_normalized_sites
from analysis.patient import HistoryEvent, HistoryEvents, Patient, PatientMetadata
from analysis.site import Site
from analysis.tooth import Tooth
from analysis.types import Arch


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_READINGS_CSV = ROOT / "outputs" / "periodontal_readings.csv"
DEFAULT_PATIENT_METADATA = ROOT / "manifests" / "patient_metadata.csv"
DEFAULT_CHART_METADATA = ROOT / "manifests" / "chart_metadata.csv"
DEFAULT_HISTORY_EVENTS = ROOT / "manifests" / "patient_history_events.csv"


def load_patient(
    patient_id: str,
    *,
    readings_csv: Path | str = DEFAULT_READINGS_CSV,
    patient_metadata_csv: Path | str = DEFAULT_PATIENT_METADATA,
    chart_metadata_csv: Path | str = DEFAULT_CHART_METADATA,
    history_events_csv: Path | str = DEFAULT_HISTORY_EVENTS,
) -> Patient:
    """Build one fully-populated ``Patient`` for ``patient_id``."""
    metadata = _load_patient_metadata(Path(patient_metadata_csv), patient_id)
    history = _load_history_events(Path(history_events_csv), patient_id)
    chart_context_by_id = _load_chart_metadata(Path(chart_metadata_csv), patient_id)

    sites_by_exam: dict[ExamKey, list[NormalizedSite]] = defaultdict(list)
    for ns in iter_normalized_sites(readings_csv):
        if ns.exam_key.patient_id != patient_id:
            continue
        sites_by_exam[ns.exam_key].append(ns)

    exams: list[Exam] = []
    for exam_key in sorted(sites_by_exam):  # ExamKey sorts chronologically
        normalized_sites = sites_by_exam[exam_key]
        mouth = _build_mouth(normalized_sites, history=history)
        ctx = chart_context_by_id.get(exam_key.chart_id, ChartContext())
        exams.append(Exam(exam_key=exam_key, mouth=mouth, context=ctx))

    return Patient(metadata=metadata, history=history, exams=tuple(exams))


# ---------------------------------------------------------------------------
# Per-manifest loaders.
# ---------------------------------------------------------------------------


def _load_patient_metadata(path: Path, patient_id: str) -> PatientMetadata:
    if not path.exists():
        # No metadata file yet -- return a stub.  Phase 0 should have
        # created the file, so emit an explicit warning-shaped error
        # if it ever goes missing.
        raise FileNotFoundError(
            f"patient_metadata.csv not found at {path}; Phase 0 should "
            "have created this file"
        )
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["patient_id"] != patient_id:
                continue
            return PatientMetadata(
                patient_id=row["patient_id"],
                dob=_parse_date(row.get("dob") or ""),
                sex=row.get("sex", ""),
                family_history_perio=_parse_bool(row.get("family_history_perio")),
                family_history_details=row.get("family_history_details", ""),
                allergies=row.get("allergies", ""),
                notes=row.get("notes", ""),
            )
    raise KeyError(f"patient_id={patient_id!r} not in {path}")


def _load_chart_metadata(path: Path, patient_id: str) -> dict[int, ChartContext]:
    out: dict[int, ChartContext] = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("patient_id") != patient_id:
                continue
            chart_id = int(row["chart_id"])
            out[chart_id] = ChartContext(
                hba1c_at_exam=_parse_optional_float(row.get("hba1c_at_exam")),
                pregnant_at_exam=_parse_bool(row.get("pregnant_at_exam")),
                systemic_antibiotic_within_4w=_parse_bool(
                    row.get("systemic_antibiotic_within_4w")
                ),
                notes=row.get("notes", ""),
            )
    return out


def _load_history_events(path: Path, patient_id: str) -> HistoryEvents:
    if not path.exists():
        return HistoryEvents()
    events: list[HistoryEvent] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("patient_id") != patient_id:
                continue
            details_raw = row.get("details_json") or "{}"
            try:
                details = json.loads(details_raw)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"patient_history_events.csv row for {patient_id} "
                    f"has invalid details_json: {e}"
                ) from e
            events.append(
                HistoryEvent(
                    patient_id=row["patient_id"],
                    event_type=row["event_type"],
                    event_subtype=row.get("event_subtype", ""),
                    start_date=_parse_date(row.get("start_date") or ""),
                    end_date=_parse_date(row.get("end_date") or ""),
                    start_date_uncertain=_parse_bool(row.get("start_date_uncertain")),
                    end_date_uncertain=_parse_bool(row.get("end_date_uncertain")),
                    tooth_number=_parse_optional_int(row.get("tooth_number")),
                    details=details,
                )
            )
    return HistoryEvents(events=tuple(events))


# ---------------------------------------------------------------------------
# Mouth / Tooth / Site assembly.
# ---------------------------------------------------------------------------


# Anterior-facial site geometry for the chronic-mouth-breathing site
# caveat per patient_history_events.csv -- maxillary 6-11 facial and
# mandibular 22-27 facial are the regions whose gingival inflammation
# is biased upward by chronic mouth breathing.
_MOUTH_BREATHING_TEETH: dict[Arch, tuple[int, ...]] = {
    "maxillary": (6, 7, 8, 9, 10, 11),
    "mandibular": (22, 23, 24, 25, 26, 27),
}


def _build_mouth(
    normalized_sites: list[NormalizedSite],
    *,
    history: HistoryEvents,
) -> Mouth:
    """Group ``NormalizedSite``s by tooth, build ``Tooth``s with any
    Phase-0-derived caveats attached, return a ``Mouth``."""
    mouth_breathing_event = next(
        (
            e
            for e in history.of_subtype("chronic_mouth_breathing")
        ),
        None,
    )

    by_tooth: dict[tuple[Arch, int], list[Site]] = defaultdict(list)
    for ns in normalized_sites:
        site_caveats = _caveats_for_site(ns, mouth_breathing_event)
        site = Site(normalized=ns, caveats=site_caveats)
        by_tooth[(ns.site_key.arch, ns.site_key.tooth_number)].append(site)

    teeth: dict[int, Tooth] = {}
    for (arch, tooth_number), sites in by_tooth.items():
        caveats = _caveats_for_tooth(arch, tooth_number, history)
        teeth[tooth_number] = Tooth(
            arch=arch,
            tooth_number=tooth_number,
            sites=tuple(sites),
            caveats=caveats,
        )

    return Mouth(teeth=teeth)


def _caveats_for_site(
    ns: NormalizedSite,
    mouth_breathing_event: HistoryEvent | None,
) -> tuple[Evidence, ...]:
    """Pre-bake site-level caveats from Phase 0 history.

    Currently emitted: anterior-facial inflammation bias for any
    patient with ``chronic_mouth_breathing`` on file (sites: maxillary
    6-11 facial + mandibular 22-27 facial)."""
    out: list[Evidence] = []
    if mouth_breathing_event is not None:
        eligible_teeth = _MOUTH_BREATHING_TEETH.get(ns.site_key.arch, ())
        if (
            ns.site_key.surface == "facial"
            and ns.site_key.tooth_number in eligible_teeth
        ):
            out.append(
                Evidence(
                    rule_id="caveat.mouth_breathing_anterior_facial_bias",
                    scope=(
                        ns.site_key.patient_id,
                        ns.exam_key.exam_index,
                        ns.site_key.arch,
                        ns.site_key.surface,
                        ns.site_key.tooth_number,
                        ns.site_key.site,
                    ),
                    status=EvidenceStatus.PROVISIONAL,
                    threshold_crossed=(
                        "anterior-facial site of patient with chronic "
                        "mouth-breathing on file -- gingival inflammation "
                        "and PD readings biased upward"
                    ),
                    citation=citations.SITE_MOUTH_BREATHING_CAVEAT,
                    value="anterior_facial_inflammation_bias",
                    assumptions=(
                        "chronic mouth-breathing inflates anterior-facial "
                        "PD/gingival inflammation independently of true "
                        "attachment loss",
                    ),
                    notes=mouth_breathing_event.details.get("bias", ""),
                )
            )
    return tuple(out)


def _caveats_for_tooth(
    arch: Arch,
    tooth_number: int,
    history: HistoryEvents,
) -> tuple[Evidence, ...]:
    """Pre-bake caveat Evidence for this tooth from Phase 0 history.

    Currently emitted:
    * crown caveat -- for any ``restoration`` event with matching
      ``tooth_number`` (e.g. tooth 8 = maxillary right central
      incisor on patient_01).  Phase 5 narrative renders it whenever
      it surfaces a finding on this tooth.
    """
    out: list[Evidence] = []
    for event in history.for_tooth(tooth_number):
        if event.event_type == "restoration" and event.event_subtype == "crown":
            out.append(
                Evidence(
                    rule_id="caveat.crown_margin_probing_bias",
                    scope=("tooth", tooth_number),
                    status=EvidenceStatus.PROVISIONAL,
                    threshold_crossed=(
                        "crowned tooth: probing-depth measurements biased "
                        "upward at margin; recession measurement also suspect"
                    ),
                    citation=citations.TOOTH_CROWN_CAVEAT,
                    value="crown",
                    assumptions=(
                        f"tooth {tooth_number} is crowned -- restoration margin "
                        "may bias PD/GM/CAL upward",
                    ),
                    notes=event.details.get("note", ""),
                )
            )
    return tuple(out)


# ---------------------------------------------------------------------------
# Tiny CSV value-parsers.
# ---------------------------------------------------------------------------


def _parse_date(s: str) -> date | None:
    s = s.strip()
    if not s:
        return None
    return date.fromisoformat(s)


def _parse_bool(s: Any) -> bool:
    if s is None:
        return False
    s = str(s).strip().lower()
    if s in ("true", "1", "yes", "y", "t"):
        return True
    return False


def _parse_optional_int(s: Any) -> int | None:
    if s is None or s == "":
        return None
    return int(s)


def _parse_optional_float(s: Any) -> float | None:
    if s is None or s == "":
        return None
    return float(s)
