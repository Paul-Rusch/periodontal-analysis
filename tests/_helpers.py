"""Builders for synthetic ``Patient`` / ``Mouth`` / ``Site`` objects
used by tests that need to exercise edge cases the real ``patient_01``
data does not produce (e.g. only-central-CAL high, full-key-join
collisions across arches).

Kept minimal -- if a test can run against ``patient_01`` it should;
this module is for the cases where that's not enough.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Iterable

from analysis import (
    CAL,
    GM,
    MGJ,
    PD,
    Arch,
    ArchSurface,
    ChartContext,
    Exam,
    ExamKey,
    Mouth,
    NormalizedSite,
    Site,
    SiteKey,
    SitePosition,
    Surface,
    Tooth,
)


def make_normalized_site(
    *,
    patient_id: str = "p_test",
    chart_id: int = 1,
    exam_index: int = 1,
    exam_date: date = date(2024, 1, 1),
    arch: Arch = "maxillary",
    surface: Surface = "facial",
    tooth_number: int = 14,
    site: SitePosition = "distal",
    pd: int = 3,
    gm: int = 0,
    cal: int | None = None,
    mgj: int | None = None,
) -> NormalizedSite:
    """Build a single ``NormalizedSite`` with sensible defaults.
    ``cal`` defaults to ``pd + gm`` so the ``CAL = PD + GM`` identity
    holds without callers having to compute it."""
    if cal is None:
        cal = pd + gm
    return NormalizedSite(
        exam_key=ExamKey(
            patient_id=patient_id,
            exam_index=exam_index,
            exam_date=exam_date,
            chart_id=chart_id,
        ),
        site_key=SiteKey(
            patient_id=patient_id,
            arch=arch,
            surface=surface,
            tooth_number=tooth_number,
            site=site,
        ),
        pd=PD(pd),
        gm=GM(gm),
        cal=CAL(cal),
        mgj=MGJ(mgj) if mgj else None,
    )


def make_site(**kwargs) -> Site:
    """Wrap ``make_normalized_site`` in a ``Site`` (no caveats)."""
    return Site(normalized=make_normalized_site(**kwargs))


def make_mouth(sites: Iterable[Site]) -> Mouth:
    """Group ``sites`` by tooth_number into a ``Mouth``.  All sites
    contributing to one tooth must share the same ``arch``."""
    by_tooth: dict[int, list[Site]] = defaultdict(list)
    arches: dict[int, Arch] = {}
    for s in sites:
        by_tooth[s.site_key.tooth_number].append(s)
        arches[s.site_key.tooth_number] = s.site_key.arch
    teeth = {
        tn: Tooth(arch=arches[tn], tooth_number=tn, sites=tuple(site_list))
        for tn, site_list in by_tooth.items()
    }
    return Mouth(teeth=teeth)


def make_exam(sites: Iterable[Site]) -> Exam:
    """Wrap ``make_mouth`` in an ``Exam``.  ``ExamKey`` is taken from
    the first site (all sites should share the same key)."""
    sites = list(sites)
    ek = sites[0].exam_key
    return Exam(exam_key=ek, mouth=make_mouth(sites), context=ChartContext())
