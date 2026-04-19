"""``Exam`` -- one ``Mouth`` plus its ``ExamKey`` and chart-level
metadata pulled from ``manifests/chart_metadata.csv`` (extended in
Phase 0).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from analysis.mouth import Mouth
from analysis.normalize import ExamKey
from analysis.tooth import Tooth


@dataclass(frozen=True)
class ChartContext:
    """Per-exam point-in-time context, joined from
    ``manifests/chart_metadata.csv``.  Plain strings/None for the
    optional fields -- typed numerics are deferred until a real value
    appears in the manifest.

    Sources:
    * ``hba1c_at_exam`` -- AAP/EFP Grade modifier (Grade C when >= 7.0).
    * ``pregnant_at_exam`` -- inflammation confounder.
    * ``systemic_antibiotic_within_4w`` -- BOP / inflammation confounder
      for any future BOP-bearing dataset.
    * ``notes`` -- free text per exam (e.g. "first post-SRP re-eval").
    """

    hba1c_at_exam: float | None = None
    pregnant_at_exam: bool = False
    systemic_antibiotic_within_4w: bool = False
    notes: str = ""


@dataclass(frozen=True)
class Exam:
    """One exam: ``Mouth`` + ``ExamKey`` + ``ChartContext``.

    Convenience pass-through accessors keep
    ``patient.exam(1).tooth(14).max_PD`` reading naturally without
    having to chain through ``.mouth.tooth(...)`` every time.
    """

    exam_key: ExamKey
    mouth: Mouth
    context: ChartContext = ChartContext()

    @property
    def exam_index(self) -> int:
        return self.exam_key.exam_index

    @property
    def exam_date(self) -> date:
        return self.exam_key.exam_date

    @property
    def chart_id(self) -> int:
        return self.exam_key.chart_id

    @property
    def patient_id(self) -> str:
        return self.exam_key.patient_id

    def tooth(self, tooth_number: int) -> Tooth:
        return self.mouth.tooth(tooth_number)

    # ---- Phase 4 shim ------------------------------------------------------

    def s3_pd_only_endpoint(self):
        """EFP S3 PD-only treatment-endpoint flag for this exam."""
        from analysis.longitudinal import s3_pd_only_endpoint as _s3
        return _s3(self)
