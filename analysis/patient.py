"""``Patient`` -- the ordered list of ``Exam``s for one patient, plus
the lifetime metadata and dated history events gathered in Phase 0.

Three Phase 0 manifests feed in here:

* ``manifests/patient_metadata.csv`` -> :class:`PatientMetadata`
  (DOB, sex, family history, allergies).
* ``manifests/chart_metadata.csv`` -> per-exam :class:`ChartContext`
  attached on the ``Exam`` (see :mod:`analysis.exam`).
* ``manifests/patient_history_events.csv`` -> :class:`HistoryEvents`,
  a date-ranged log queried by event_type / subtype / window.

The Patient API exposes both the chronological exam list (``baseline``,
``most_recent``, ``exam(N)``) and the helpers Phase 4 / Phase 5 need
(``age_at(date)``, ``smoking_status_at(date)``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from analysis.exam import Exam


@dataclass(frozen=True)
class PatientMetadata:
    """One row from ``manifests/patient_metadata.csv``."""

    patient_id: str
    dob: date | None
    sex: str
    family_history_perio: bool
    family_history_details: str = ""
    allergies: str = ""
    notes: str = ""


@dataclass(frozen=True)
class HistoryEvent:
    """One row from ``manifests/patient_history_events.csv``.

    Date fields are ``None`` when blank in the CSV; ``*_uncertain``
    flags carry forward so downstream narrative can render
    "approximately ..." appropriately.
    """

    patient_id: str
    event_type: str
    event_subtype: str
    start_date: date | None
    end_date: date | None
    start_date_uncertain: bool
    end_date_uncertain: bool
    tooth_number: int | None
    details: dict[str, Any]

    def is_active_at(self, when: date) -> bool:
        """Is this event 'in effect' on the given date?  Open-ended
        events (``end_date is None``) are treated as ongoing."""
        if self.start_date is not None and when < self.start_date:
            return False
        if self.end_date is not None and when > self.end_date:
            return False
        return True


@dataclass(frozen=True)
class HistoryEvents:
    """Read-only collection of HistoryEvents with convenience filters."""

    events: tuple[HistoryEvent, ...] = ()

    def of_type(self, event_type: str) -> tuple[HistoryEvent, ...]:
        return tuple(e for e in self.events if e.event_type == event_type)

    def of_subtype(self, subtype: str) -> tuple[HistoryEvent, ...]:
        return tuple(e for e in self.events if e.event_subtype == subtype)

    def for_tooth(self, tooth_number: int) -> tuple[HistoryEvent, ...]:
        return tuple(e for e in self.events if e.tooth_number == tooth_number)

    def active_at(self, when: date) -> tuple[HistoryEvent, ...]:
        return tuple(e for e in self.events if e.is_active_at(when))


@dataclass(frozen=True)
class Patient:
    """One patient: lifetime metadata + history + chronologically
    ordered exam list.

    ``exams`` is sorted ascending by ``exam_index`` (= baseline first)
    by construction in :func:`analysis.loader.load_patient`; never
    re-sort by chart_id.
    """

    metadata: PatientMetadata
    history: HistoryEvents
    exams: tuple[Exam, ...]

    @property
    def patient_id(self) -> str:
        return self.metadata.patient_id

    # ---- exam access --------------------------------------------------------

    def exam(self, exam_index: int) -> Exam:
        for e in self.exams:
            if e.exam_index == exam_index:
                return e
        raise KeyError(
            f"patient {self.patient_id}: no exam with exam_index={exam_index}"
        )

    @property
    def baseline(self) -> Exam:
        """First exam in chronological order (exam_index == 1)."""
        return self.exams[0]

    @property
    def most_recent(self) -> Exam:
        return self.exams[-1]

    @property
    def window_years(self) -> float:
        """Time span of the available exam window, in years.  Drives
        the §15.3 5-year-equivalent extrapolation for AAP/EFP Grade
        in Phase 4."""
        if len(self.exams) < 2:
            return 0.0
        delta = self.most_recent.exam_date - self.baseline.exam_date
        return delta.days / 365.25

    # ---- demographic / behavioral helpers ----------------------------------

    def age_at(self, when: date) -> float | None:
        """Age in years on ``when``, or ``None`` if DOB is unknown."""
        if self.metadata.dob is None:
            return None
        delta = when - self.metadata.dob
        return delta.days / 365.25

    # ---- Phase 4 longitudinal shims (delegate to analysis.longitudinal) ---

    def grade(
        self,
        *,
        start_exam_index: int | None = None,
        end_exam_index: int | None = None,
        label: str | None = None,
    ):
        from analysis.longitudinal import grade as _grade
        return _grade(
            self,
            start_exam_index=start_exam_index,
            end_exam_index=end_exam_index,
            label=label,
        )

    def trend(self, metric_name: str):
        from analysis.longitudinal import trend_series as _trend
        return _trend(self, metric_name)

    def deltas(self, *, from_exam: int, to_exam: int):
        from analysis.longitudinal import per_site_deltas as _deltas
        return _deltas(self.exam(from_exam), self.exam(to_exam))

    def treatment_response(self, *, from_exam: int, to_exam: int):
        from analysis.longitudinal import treatment_response as _tr
        return _tr(self.exam(from_exam), self.exam(to_exam))

    def tooth_loss_events(self):
        from analysis.longitudinal import tooth_loss_events as _tl
        return _tl(self)
