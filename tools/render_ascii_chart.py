#!/usr/bin/env python3
"""Render the OCR'd readings in ``outputs/periodontal_readings.csv`` as
monospaced ASCII charts that mirror the visual layout of the source paper
charts, so a reviewer can compare each rendered table against the
corresponding strip image in ``crops/rows/`` cell-by-cell.

Layout (per chart):
  - One block per arch (maxillary first, then mandibular).
  - 14 tooth columns, each subdivided into 3 site sub-columns, in the same
    left-to-right order as the source chart:
      * patient's right half (positions 1-7): sites read distal, central, mesial
      * patient's left  half (positions 8-14): sites read mesial, central, distal
  - A vertical midline separator (║) sits between positions 7 and 8.
  - 8 measurement rows per arch in the same order as the source chart:
      * maxillary: facial PD/GM/CAL/MGJ on top, then lingual PD/GM/CAL/MGJ
      * mandibular: lingual PD/GM/CAL/MGJ on top, then facial PD/GM/CAL/MGJ
  - GM / MGJ blanks (recorded as 0 in the CSV) render as middle-dot "·" so
    the visual sparseness matches the original chart.  Real printed digits
    (including non-zero GM, and any PD / CAL value) render as their integer.

Output: ``outputs/periodontal_readings_ascii.txt`` (one combined file).
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "outputs" / "periodontal_readings.csv"
CHART_METADATA_PATH = ROOT / "manifests" / "chart_metadata.csv"
OUT_PATH = ROOT / "outputs" / "periodontal_readings_ascii.txt"

TEETH_PER_ARCH = 14
SITES_PER_TOOTH = 3

TOOTH_NUMBERS: dict[str, list[int]] = {
    "maxillary":  [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    "mandibular": [31, 30, 29, 28, 27, 26, 25, 24, 23, 22, 21, 20, 19, 18],
}

# Site order, left-to-right on the chart, by tooth-position index (0..13).
def chart_site_order(tooth_position_idx: int) -> tuple[str, str, str]:
    if tooth_position_idx < 7:
        return ("distal", "central", "mesial")     # patient's right
    return ("mesial", "central", "distal")         # patient's left


# Per-arch surface stacking order (top-to-bottom on the source chart).
SURFACE_ORDER: dict[str, tuple[str, str]] = {
    "maxillary":  ("facial",  "lingual"),
    "mandibular": ("lingual", "facial"),
}

MEASUREMENTS = ("PD", "GM", "CAL", "MGJ")
BLANK_GLYPH = "·"

# Cell formatting
CELL_W = 2          # 2-char field per site (handles 2-digit values e.g. "10")
INTRA_TOOTH_SEP = " "    # between sites within a tooth
INTER_TOOTH_SEP = "  "   # between adjacent teeth (within a half-arch)
MIDLINE_SEP = "  ║  "    # between the two half-arches (positions 7 and 8)
LABEL_W = 14             # left label column ("FACIAL  PD")


def parse_value(s: str) -> Optional[int]:
    return None if s == "" else int(s)


def load_readings() -> dict[tuple, dict[tuple, Optional[int]]]:
    """Returns nested map:
      readings[(chart_id, arch, surface, measurement)][(tooth_number, site)] = value
    """
    out: dict[tuple, dict[tuple, Optional[int]]] = defaultdict(dict)
    with CSV_PATH.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            key = (
                int(r["chart_id"]), r["arch"], r["surface"], r["measurement"],
            )
            sub = (int(r["tooth_number"]), r["site"])
            out[key][sub] = parse_value(r["value"])
    return out


def load_chart_metadata() -> dict[int, dict]:
    """Map chart_id -> {patient_id, exam_date, exam_index}.  ``exam_index`` is
    1 for the patient's earliest (baseline) exam, ascending in chronological
    order; computed at load time."""
    out: dict[int, dict] = {}
    if not CHART_METADATA_PATH.exists():
        return out
    raw: list[dict] = []
    with CHART_METADATA_PATH.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            raw.append({
                "chart_id": int(r["chart_id"]),
                "exam_date": r["exam_date"].strip(),
                "patient_id": r["patient_id"].strip(),
            })
    by_patient: dict[str, list[dict]] = {}
    for r in raw:
        by_patient.setdefault(r["patient_id"], []).append(r)
    for rows in by_patient.values():
        for idx, r in enumerate(sorted(rows, key=lambda x: x["exam_date"]), 1):
            out[r["chart_id"]] = {
                "patient_id": r["patient_id"],
                "exam_date": r["exam_date"],
                "exam_index": idx,
                "n_exams_for_patient": len(rows),
            }
    return out


def values_in_chart_order(
    readings: dict[tuple, dict[tuple, Optional[int]]],
    chart_id: int, arch: str, surface: str, measurement: str,
) -> list[Optional[int]]:
    """Return the 42 values for one strip in the SAME left-to-right order as
    the source chart (so position 0 = leftmost cell on the strip)."""
    teeth = TOOTH_NUMBERS[arch]
    strip_map = readings[(chart_id, arch, surface, measurement)]
    values: list[Optional[int]] = []
    for tooth_idx, tooth_number in enumerate(teeth):
        for site in chart_site_order(tooth_idx):
            values.append(strip_map[(tooth_number, site)])
    return values


def fmt_cell(value: Optional[int], measurement: str) -> str:
    """Render one site value into a CELL_W-wide string."""
    is_blank = value is None or (measurement in ("GM", "MGJ") and value == 0)
    if is_blank:
        return BLANK_GLYPH.rjust(CELL_W)
    return str(value).rjust(CELL_W)


def fmt_value_row(values: list[Optional[int]], measurement: str) -> str:
    """Render the 42 values of one strip into a single line, using the
    intra/inter-tooth and midline spacers."""
    teeth_chunks: list[str] = []
    for tooth_idx in range(TEETH_PER_ARCH):
        tooth_cells = [
            fmt_cell(values[tooth_idx * SITES_PER_TOOTH + s], measurement)
            for s in range(SITES_PER_TOOTH)
        ]
        teeth_chunks.append(INTRA_TOOTH_SEP.join(tooth_cells))
    # Stitch with inter-tooth and midline separators.
    right_half = INTER_TOOTH_SEP.join(teeth_chunks[:7])
    left_half  = INTER_TOOTH_SEP.join(teeth_chunks[7:])
    return right_half + MIDLINE_SEP + left_half


def fmt_tooth_number_row(arch: str) -> str:
    """Render the tooth-number header (e.g. ' 2,  3, ...') aligned over each
    tooth column.  Each tooth occupies (3 * CELL_W + 2 * len(INTRA_TOOTH_SEP))
    characters."""
    teeth = TOOTH_NUMBERS[arch]
    tooth_block_w = SITES_PER_TOOTH * CELL_W + (SITES_PER_TOOTH - 1) * len(INTRA_TOOTH_SEP)
    chunks = [str(t).center(tooth_block_w) for t in teeth]
    right_half = INTER_TOOTH_SEP.join(chunks[:7])
    left_half  = INTER_TOOTH_SEP.join(chunks[7:])
    return right_half + MIDLINE_SEP + left_half


def fmt_site_label_row(arch: str) -> str:
    teeth = TOOTH_NUMBERS[arch]
    chunks = []
    for tooth_idx in range(len(teeth)):
        order = chart_site_order(tooth_idx)
        site_chars = [s[0].upper() for s in order]   # D / C / M
        chunks.append(INTRA_TOOTH_SEP.join(c.rjust(CELL_W) for c in site_chars))
    right_half = INTER_TOOTH_SEP.join(chunks[:7])
    left_half  = INTER_TOOTH_SEP.join(chunks[7:])
    return right_half + MIDLINE_SEP + left_half


def render_arch(
    readings: dict[tuple, dict[tuple, Optional[int]]],
    chart_id: int, arch: str,
) -> list[str]:
    lines: list[str] = []
    label_pad = " " * LABEL_W

    teeth = TOOTH_NUMBERS[arch]
    body_w = len(fmt_tooth_number_row(arch))
    full_w = LABEL_W + body_w

    # Arch title + half-arch annotations
    lines.append("─" * full_w)
    title = (
        f" CHART {chart_id:02d} — {arch.upper()}  "
        f"(left half = patient's RIGHT, teeth {teeth[0]}–{teeth[6]};  "
        f"right half = patient's LEFT, teeth {teeth[7]}–{teeth[-1]})"
    )
    lines.append(title)
    lines.append("─" * full_w)

    # Tooth numbers + site labels
    lines.append(label_pad + fmt_tooth_number_row(arch))
    lines.append(label_pad + fmt_site_label_row(arch))
    lines.append("─" * full_w)

    for surface in SURFACE_ORDER[arch]:
        for j, meas in enumerate(MEASUREMENTS):
            values = values_in_chart_order(
                readings, chart_id, arch, surface, meas
            )
            label = (
                f"{surface.upper():<8}{meas:<{LABEL_W - 8}}"
                if j == 0
                else f"{'':<8}{meas:<{LABEL_W - 8}}"
            )
            lines.append(label + fmt_value_row(values, meas))
        # Blank line between the two surfaces inside one arch
        if surface != SURFACE_ORDER[arch][-1]:
            lines.append("")
    return lines


def render_chart(
    readings: dict[tuple, dict[tuple, Optional[int]]],
    chart_id: int,
    chart_meta: dict[int, dict],
) -> list[str]:
    lines: list[str] = []
    full_w = LABEL_W + len(fmt_tooth_number_row("maxillary"))
    meta = chart_meta.get(chart_id)
    if meta:
        n = meta["n_exams_for_patient"]
        idx = meta["exam_index"]
        baseline_tag = "  (BASELINE)" if idx == 1 else ""
        title = (
            f"chart_id {chart_id:02d}   —   patient {meta['patient_id']}   "
            f"—   exam {idx} of {n}{baseline_tag}   —   {meta['exam_date']}"
        )
    else:
        title = f"chart_id {chart_id:02d}   —   (no metadata)"
    lines.append("=" * full_w)
    lines.append(title.center(full_w))
    lines.append("=" * full_w)
    for arch in ("maxillary", "mandibular"):
        lines.extend(render_arch(readings, chart_id, arch))
        lines.append("")
    return lines


def render_legend(full_w: int) -> list[str]:
    return [
        "=" * full_w,
        "LEGEND",
        "=" * full_w,
        "  Cell values are integers in millimetres (mm).",
        f"  '{BLANK_GLYPH}' = blank cell on the source chart.  For PD / CAL this is",
        "        anomalous (real probing depths / attachment levels are always",
        "        recorded); for GM / MGJ it is the common case meaning",
        "        'gingival margin at CEJ' / 'mucogingival junction not measured'.",
        "        The validator confirms 0 such cases in the current data.",
        "",
        "  Surface stacking matches the source chart:",
        "    maxillary  -> facial above lingual",
        "    mandibular -> lingual above facial",
        "",
        "  Site ordering within a tooth matches the source chart's D-C-M | M-C-D",
        "  layout (the chart mirrors at the midline because 'distal' always",
        "  points away from the midline).  Reading left-to-right:",
        "    teeth 2-8  / 31-25 (patient's right)  -> Distal, Central, Mesial",
        "    teeth 9-15 / 24-18 (patient's left)   -> Mesial, Central, Distal",
        "",
        "  The midline ║ separates the two half-arches.",
        "",
        "  Side-by-side check: the n-th cell (from the left) in any value row",
        "  corresponds 1:1 to the n-th cell (from the left) in the matching",
        "  strip image:  crops/rows/periodontal_charting_NN_{arch}_{surface}_{meas}.jpg",
        "=" * full_w,
        "",
    ]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--out", default=str(OUT_PATH),
        help="Output text file (default: outputs/periodontal_readings_ascii.txt)",
    )
    p.add_argument(
        "--chart", type=int, default=None,
        help="Render only this chart_id (1-5).  Defaults to all 5.",
    )
    args = p.parse_args()

    readings = load_readings()
    chart_meta = load_chart_metadata()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    available_chart_ids = sorted({k[0] for k in readings})
    if args.chart:
        chart_ids = [args.chart]
    else:
        # Render in chronological order (baseline first), so the file reads
        # like a clinical timeline.  Charts with no metadata fall to the end.
        def sort_key(cid: int) -> tuple:
            m = chart_meta.get(cid)
            return (0, m["exam_date"]) if m else (1, str(cid))
        chart_ids = sorted(available_chart_ids, key=sort_key)

    full_w = LABEL_W + len(fmt_tooth_number_row("maxillary"))
    all_lines: list[str] = []
    all_lines.extend(render_legend(full_w))
    if chart_meta:
        all_lines.append("EXAM TIMELINE  (one row per chart, oldest first)")
        all_lines.append("-" * full_w)
        ordered = sorted(chart_meta.items(),
                         key=lambda kv: kv[1]["exam_date"])
        for cid, m in ordered:
            tag = "  (BASELINE)" if m["exam_index"] == 1 else ""
            all_lines.append(
                f"  exam {m['exam_index']}/{m['n_exams_for_patient']}  "
                f"chart_id {cid:02d}  patient {m['patient_id']}  "
                f"{m['exam_date']}{tag}"
            )
        all_lines.append("")
    for cid in chart_ids:
        all_lines.extend(render_chart(readings, cid, chart_meta))

    out_path.write_text("\n".join(all_lines) + "\n", encoding="utf-8")
    print(f"Wrote {out_path.relative_to(ROOT)} ({len(all_lines)} lines, "
          f"{out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
