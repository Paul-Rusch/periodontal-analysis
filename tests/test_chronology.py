"""Chronology guard.

The dataset's ``chart_id`` is anti-chronological (chart 5 = baseline,
chart 1 = most recent).  Anything that sorts by ``chart_id`` instead
of ``ExamKey`` (which sorts by ``exam_index`` / ``exam_date``)
silently inverts the timeline -- the original handoff prompt called
this out as "this has already burned us once".

These tests pin both the correct behavior (sort by ``ExamKey``) and
the anti-pattern (sort by ``chart_id``) so a future regression is
loud.
"""

from __future__ import annotations


def test_exam_keys_sort_baseline_first(patient_01):
    """``patient.exams`` must be in chronological order (baseline first)."""
    exam_indices = [e.exam_index for e in patient_01.exams]
    assert exam_indices == [1, 2, 3, 4, 5]


def test_baseline_is_chart_5_not_chart_1(patient_01):
    """Pin the dataset-specific anti-chronological ``chart_id``
    mapping.  Baseline is the *earliest* exam (June 2024) and was
    scanned last -- ``chart_id == 5``."""
    assert patient_01.baseline.chart_id == 5
    assert patient_01.most_recent.chart_id == 1


def test_chart_id_sort_is_wrong(patient_01):
    """Anti-pattern guard: sorting exams by ``chart_id`` produces the
    *reverse* of chronological order.  If a future agent sorts by
    ``chart_id``, baseline becomes the last entry instead of the first."""
    by_chart_id = sorted(patient_01.exams, key=lambda e: e.chart_id)
    assert by_chart_id[0].chart_id == 1
    assert by_chart_id[0].exam_index == 5  # most-recent exam appears first
    assert by_chart_id[-1].chart_id == 5
    assert by_chart_id[-1].exam_index == 1  # baseline appears last
    # And, critically, this is the OPPOSITE of the correct
    # chronological order produced by ExamKey.
    by_exam_key = sorted(e.exam_key for e in patient_01.exams)
    assert [ek.exam_index for ek in by_exam_key] == [1, 2, 3, 4, 5]
    assert [ek.chart_id for ek in by_exam_key] == [5, 4, 3, 2, 1]


def test_exam_dates_strictly_increase_with_exam_index(patient_01):
    for prev, curr in zip(patient_01.exams, patient_01.exams[1:]):
        assert prev.exam_date < curr.exam_date
        assert prev.exam_index + 1 == curr.exam_index
