#!/usr/bin/env python3
"""For every site where the CAL identity (CAL = PD + GM) is violated, render
a high-resolution comparison image showing the PD, GM and CAL cells stacked,
each labelled with its current OCR'd value.  This lets a reviewer eyeball
which value is wrong and how to fix it.

Outputs go to ``outputs/mismatch_review/`` plus a ``manifest.csv`` listing
every mismatch with its strip / tooth / site coordinates, current OCR
values, and predicted CAL.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "outputs" / "periodontal_readings.csv"
ROWS_DIR = ROOT / "crops" / "rows"
OUT_DIR = ROOT / "outputs" / "mismatch_review"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from annotate_and_crop_periodontal_rows import (  # noqa: E402
    TOOTH_TRIPLETS,
    compute_tooth_boundaries,
)

TEETH_PER_ARCH = 14
SITES_PER_TOOTH = 3
MEASUREMENTS = ("PD", "GM", "CAL")

TOOTH_NUMBERS = {
    "maxillary":  [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    "mandibular": [31, 30, 29, 28, 27, 26, 25, 24, 23, 22, 21, 20, 19, 18],
}
SITE_LABELS_RIGHT = ("distal", "central", "mesial")
SITE_LABELS_LEFT = ("mesial", "central", "distal")


def font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size
        )
    except OSError:
        return ImageFont.load_default()


def site_label_for(tooth_idx: int, site_idx: int) -> str:
    return (SITE_LABELS_RIGHT if tooth_idx < 7 else SITE_LABELS_LEFT)[site_idx]


def parse_value(s: str) -> Optional[int]:
    return None if s == "" else int(s)


def load_csv() -> dict[tuple, dict[str, Optional[int]]]:
    by_site: dict[tuple, dict[str, Optional[int]]] = {}
    with CSV_PATH.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            key = (
                int(r["chart_id"]), r["arch"], r["surface"],
                int(r["tooth_number"]), r["site"],
            )
            by_site.setdefault(key, {})[r["measurement"]] = parse_value(r["value"])
    return by_site


def gather_mismatches() -> list[dict]:
    by_site = load_csv()
    out: list[dict] = []
    for key, m in by_site.items():
        pd = m.get("PD")
        cal = m.get("CAL")
        gm = m.get("GM")
        gm_v = gm if gm is not None else 0
        if pd is None or cal is None:
            continue
        if pd + gm_v == cal:
            continue
        chart_id, arch, surface, tooth, site = key
        out.append({
            "chart_id": chart_id,
            "arch": arch,
            "surface": surface,
            "tooth_number": tooth,
            "site": site,
            "PD": pd,
            "GM": gm,
            "CAL": cal,
            "predicted_CAL": pd + gm_v,
        })
    out.sort(key=lambda r: (
        r["chart_id"], r["arch"], r["surface"],
        TOOTH_NUMBERS[r["arch"]].index(r["tooth_number"]),
        ("distal", "central", "mesial").index(r["site"])
        if r["arch"] == "maxillary" and r["tooth_number"] <= 8
        else 0,
    ))
    return out


def crop_cell(
    strip_image: Image.Image,
    boundaries: list[int],
    triplets: list[list[int]],
    tooth_idx: int,
    site_idx: int,
    pad: int = 8,
) -> Image.Image:
    """Crop a single site cell, going from the inter-site boundary to the
    next one.  Uses the inter-site tick midpoints implied by triplets."""
    sites = triplets[tooth_idx]
    # x boundaries inside the tooth = midpoints between adjacent site centers
    left_outer = boundaries[tooth_idx]
    right_outer = boundaries[tooth_idx + 1]
    inter_a = (sites[0] + sites[1]) // 2
    inter_b = (sites[1] + sites[2]) // 2
    edges = [left_outer, inter_a, inter_b, right_outer]
    x0 = max(0, edges[site_idx] - pad)
    x1 = min(strip_image.width, edges[site_idx + 1] + pad)
    return strip_image.crop((x0, 0, x1, strip_image.height))


def render_mismatch_image(rec: dict, idx: int) -> Path:
    chart_id = rec["chart_id"]
    arch = rec["arch"]
    surface = rec["surface"]
    tooth_number = rec["tooth_number"]
    site = rec["site"]

    tooth_idx = TOOTH_NUMBERS[arch].index(tooth_number)
    if tooth_idx < 7:
        site_idx = SITE_LABELS_RIGHT.index(site)
    else:
        site_idx = SITE_LABELS_LEFT.index(site)

    triplets = TOOTH_TRIPLETS[(chart_id, arch)]
    boundaries = compute_tooth_boundaries(triplets)

    # Crop each measurement's cell, plus a wider context (1-tooth window).
    cells: dict[str, Image.Image] = {}
    contexts: dict[str, Image.Image] = {}
    SCALE = 5
    for meas in MEASUREMENTS:
        path = (
            ROWS_DIR
            / f"periodontal_charting_{chart_id:02d}_{arch}_{surface}_{meas}.jpg"
        )
        with Image.open(path) as src:
            strip = src.convert("RGB").copy()
        cell = crop_cell(strip, boundaries, triplets, tooth_idx, site_idx, pad=4)
        cell = cell.resize(
            (cell.width * SCALE, cell.height * SCALE), resample=Image.LANCZOS
        )
        cells[meas] = cell

        # 1-tooth context (this tooth + the two neighbors when they exist).
        ctx_left = max(0, boundaries[max(0, tooth_idx - 1)])
        ctx_right = min(strip.width, boundaries[min(TEETH_PER_ARCH, tooth_idx + 2)])
        ctx = strip.crop((ctx_left, 0, ctx_right, strip.height))
        ctx = ctx.resize(
            (ctx.width * 2, ctx.height * 3), resample=Image.LANCZOS
        )
        contexts[meas] = ctx

    cell_w = max(c.width for c in cells.values())
    cell_h = max(c.height for c in cells.values())
    ctx_w = max(c.width for c in contexts.values())
    ctx_h = max(c.height for c in contexts.values())

    label_w = 280
    spacer_h = 30
    title_h = 70
    section_h = max(cell_h, ctx_h)
    total_w = label_w + cell_w + 60 + ctx_w + 20
    total_h = title_h + len(MEASUREMENTS) * (section_h + spacer_h)

    img = Image.new("RGB", (total_w, total_h), "white")
    draw = ImageDraw.Draw(img)
    title_font = font(28)
    label_font = font(38)
    val_font = font(60)

    title = (
        f"#{idx:03d}  chart {chart_id} {arch}/{surface}  "
        f"tooth {tooth_number} {site}    "
        f"PD={rec['PD']}  GM={rec['GM']!r}  CAL={rec['CAL']}  "
        f"(predicted CAL = PD+GM = {rec['predicted_CAL']})"
    )
    draw.text((10, 20), title, fill="black", font=title_font)

    for i, meas in enumerate(MEASUREMENTS):
        y0 = title_h + i * (section_h + spacer_h)
        v = rec[meas]
        v_str = "blank" if v is None else str(v)
        draw.text((10, y0 + 10), f"{meas} = {v_str}", fill="black", font=label_font)
        # paste cell
        cx = label_w
        img.paste(cells[meas], (cx, y0))
        # paste context
        ctx_x = label_w + cell_w + 60
        img.paste(contexts[meas], (ctx_x, y0))
        # vertical line between cell and context
        draw.line(
            [(cx + cell_w + 20, y0), (cx + cell_w + 20, y0 + section_h)],
            fill=(180, 180, 180), width=1,
        )

    out_path = OUT_DIR / (
        f"{idx:03d}_chart{chart_id:02d}_{arch}_{surface}_t{tooth_number:02d}_{site}.png"
    )
    img.save(out_path)
    return out_path


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    mismatches = gather_mismatches()
    print(f"Found {len(mismatches)} mismatches.")

    manifest_path = OUT_DIR / "manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([
            "idx", "chart_id", "arch", "surface", "tooth_number", "site",
            "PD", "GM", "CAL", "predicted_CAL", "image_file",
        ])
        for i, rec in enumerate(mismatches, 1):
            path = render_mismatch_image(rec, i)
            w.writerow([
                i, rec["chart_id"], rec["arch"], rec["surface"],
                rec["tooth_number"], rec["site"],
                rec["PD"], "" if rec["GM"] is None else rec["GM"], rec["CAL"],
                rec["predicted_CAL"], path.relative_to(ROOT),
            ])
    print(f"Wrote {manifest_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
