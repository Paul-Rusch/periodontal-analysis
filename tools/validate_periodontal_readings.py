#!/usr/bin/env python3
"""Sanity-check the tidy periodontal CSV produced by ``read_periodontal_rows``.

Checks performed:

1. Per-strip cardinality       - 80 strips x 42 sites = 3360 rows.
2. CAL = PD - GM identity      - per (chart, arch, surface, tooth, site).
3. Range sanity                - PD/GM/CAL/MGJ value ranges, flagging outliers.
4. GM blank-rate sanity        - per-row blank counts on GM strips.
5. Header tooth-number agreement - first row per (chart, arch) shows tooth
   numbers that match the universal numbering reference.

Run with no arguments; prints a report and exits non-zero if a hard check fails
(currently only the cardinality check is fatal).
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "outputs" / "periodontal_readings.csv"

EXPECTED_TOTAL_ROWS = 3360

TOOTH_NUMBERS: dict[str, list[int]] = {
    "maxillary":  [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    "mandibular": [31, 30, 29, 28, 27, 26, 25, 24, 23, 22, 21, 20, 19, 18],
}

RANGE_RULES = {
    # measurement: (min_typical, max_typical, must_be_present)
    "PD":  (1, 15, True),
    "GM":  (0, 9,  False),
    "CAL": (1, 15, True),
    "MGJ": (0, 12, False),
}


def parse_value(raw: str) -> Optional[int]:
    if raw == "" or raw is None:
        return None
    return int(raw)


def load_rows() -> list[dict]:
    if not CSV_PATH.exists():
        print(f"ERROR: {CSV_PATH} does not exist", file=sys.stderr)
        sys.exit(2)
    with CSV_PATH.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def check_cardinality(rows: list[dict]) -> int:
    n = len(rows)
    ok = n == EXPECTED_TOTAL_ROWS
    print(
        f"[1] Cardinality:  {n} rows  -> "
        f"{'OK' if ok else f'FAIL (expected {EXPECTED_TOTAL_ROWS})'}"
    )

    by_strip: dict[tuple, int] = defaultdict(int)
    for r in rows:
        key = (r["chart_id"], r["arch"], r["surface"], r["measurement"])
        by_strip[key] += 1
    bad = [(k, v) for k, v in by_strip.items() if v != 42]
    if bad:
        print(f"    FAIL: {len(bad)} strips do not have 42 entries:")
        for k, v in bad:
            print(f"      {k} -> {v}")
        return 2
    return 0 if ok else 2


def check_cal_identity(rows: list[dict]) -> None:
    """In this chart's convention, GM is the recession value (distance from
    the gingival margin DOWN to the CEJ).  CAL = PD + GM, NOT PD - GM."""
    by_site: dict[tuple, dict[str, Optional[int]]] = defaultdict(dict)
    for r in rows:
        key = (
            r["chart_id"], r["arch"], r["surface"],
            r["tooth_number"], r["site"],
        )
        by_site[key][r["measurement"]] = parse_value(r["value"])

    total = 0
    matches = 0
    mismatches: list[tuple] = []
    pd_or_cal_blank = 0

    for key, meas in by_site.items():
        pd = meas.get("PD")
        gm = meas.get("GM")
        cal = meas.get("CAL")
        if pd is None or cal is None:
            pd_or_cal_blank += 1
            continue
        gm_v = gm if gm is not None else 0
        predicted = pd + gm_v
        total += 1
        if predicted == cal:
            matches += 1
        else:
            mismatches.append((key, pd, gm_v, predicted, cal))

    pct = 100.0 * matches / total if total else 0.0
    print(
        f"[2] CAL = PD + GM:  {matches}/{total} = {pct:.1f}% match  "
        f"(skipped {pd_or_cal_blank} sites with blank PD or CAL)"
    )
    if mismatches:
        sample = mismatches[:25]
        print(f"    Sample mismatches ({len(mismatches)} total):")
        for (key, pd, gm_v, pred, cal) in sample:
            chart_id, arch, surface, tooth, site = key
            print(
                f"      chart {chart_id} {arch}/{surface} tooth {tooth} "
                f"{site}: PD={pd} GM={gm_v} -> predicted CAL={pred} but "
                f"recorded CAL={cal}"
            )


def check_ranges(rows: list[dict]) -> None:
    print("[3] Range sanity:")
    by_meas: dict[str, list[tuple]] = defaultdict(list)
    for r in rows:
        v = parse_value(r["value"])
        by_meas[r["measurement"]].append((r, v))

    for meas, (lo, hi, must_present) in RANGE_RULES.items():
        recs = by_meas[meas]
        outliers = []
        blanks = 0
        for r, v in recs:
            if v is None:
                blanks += 1
                if must_present:
                    outliers.append((r, "blank"))
                continue
            if v < lo or v > hi:
                outliers.append((r, f"value={v}"))
            elif must_present and v == 0:
                outliers.append((r, "value=0"))
        print(
            f"    {meas}: {len(recs)} sites, {blanks} blank, "
            f"{len(outliers)} flagged"
        )
        for r, why in outliers[:15]:
            print(
                f"      chart {r['chart_id']} {r['arch']}/{r['surface']} "
                f"tooth {r['tooth_number']} {r['site']}: {why}"
            )
        if len(outliers) > 15:
            print(f"      ... and {len(outliers) - 15} more")


def check_gm_blank_rate(rows: list[dict]) -> None:
    print("[4] GM blank-rate (most sites should be blank/0):")
    by_strip: dict[tuple, list[Optional[int]]] = defaultdict(list)
    for r in rows:
        if r["measurement"] != "GM":
            continue
        key = (r["chart_id"], r["arch"], r["surface"])
        by_strip[key].append(parse_value(r["value"]))
    for key in sorted(by_strip):
        vals = by_strip[key]
        zero = sum(1 for v in vals if v == 0 or v is None)
        nonzero = sum(1 for v in vals if v not in (None, 0))
        print(
            f"    chart {key[0]} {key[1]}/{key[2]}: "
            f"{zero} blank/0, {nonzero} non-zero  "
            f"{'(suspicious)' if nonzero > 20 else ''}"
        )


def check_header_alignment(rows: list[dict]) -> None:
    print("[5] Tooth-number ordering (deduplicated per chart/arch):")
    seen: dict[tuple, list[int]] = {}
    for r in rows:
        if r["measurement"] != "PD" or r["surface"] != "facial":
            continue
        key = (r["chart_id"], r["arch"])
        seen.setdefault(key, []).append(int(r["tooth_number"]))
    for key in sorted(seen):
        all_teeth: list[int] = []
        seen_set: set[int] = set()
        for t in seen[key]:
            if t not in seen_set:
                all_teeth.append(t)
                seen_set.add(t)
        match = all_teeth == TOOTH_NUMBERS[key[1]]
        print(
            f"    chart {key[0]} {key[1]}: {all_teeth} -> "
            f"{'OK' if match else 'MISMATCH'}"
        )


def main() -> int:
    rows = load_rows()
    fail = check_cardinality(rows)
    check_cal_identity(rows)
    check_ranges(rows)
    check_gm_blank_rate(rows)
    check_header_alignment(rows)
    return fail


if __name__ == "__main__":
    sys.exit(main())
