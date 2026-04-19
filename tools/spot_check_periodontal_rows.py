#!/usr/bin/env python3
"""Render side-by-side images for visually verifying the OCR output.

For each selected strip we render a vertical stack:
  [strip image]
  [overlay row showing the OCR'd value beneath the digit position]

The overlay uses the per-tooth boundaries and inter-site x-centers from
``annotate_and_crop_periodontal_rows.TOOTH_TRIPLETS`` so every value lands
under the correct cell.

Usage:
    python tools/spot_check_periodontal_rows.py
        - default: a curated 8-strip sample covering all 4 measurements
          and both arches.

    python tools/spot_check_periodontal_rows.py all
        - render every strip in the manifest.

    python tools/spot_check_periodontal_rows.py mismatches
        - render only strips whose CAL = PD + GM identity is violated for
          at least one site.

Outputs are written to ``outputs/spot_checks/``.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "manifests" / "periodontal_row_crop_manifest.csv"
JSON_DIR = ROOT / "outputs" / "json"
OUTPUT_DIR = ROOT / "outputs" / "spot_checks"
CSV_PATH = ROOT / "outputs" / "periodontal_readings.csv"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from annotate_and_crop_periodontal_rows import (  # noqa: E402
    TOOTH_TRIPLETS,
    compute_tooth_boundaries,
)

TEETH_PER_ARCH = 14
SITES_PER_TOOTH = 3

OVERLAY_HEIGHT = 90  # px
FONT_SIZE = 36
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

DEFAULT_SAMPLE = [
    # one strip per (measurement, surface, arch) combination, covering charts
    # 1-5 to spot-check variety
    "periodontal_charting_01_maxillary_facial_PD.jpg",
    "periodontal_charting_02_maxillary_lingual_GM.jpg",
    "periodontal_charting_03_mandibular_facial_CAL.jpg",
    "periodontal_charting_04_mandibular_lingual_MGJ.jpg",
    "periodontal_charting_05_maxillary_facial_GM.jpg",
    "periodontal_charting_05_mandibular_facial_PD.jpg",
    "periodontal_charting_03_maxillary_lingual_CAL.jpg",
    "periodontal_charting_02_mandibular_facial_MGJ.jpg",
]


def load_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except OSError:
        return ImageFont.load_default()


def load_manifest() -> list[dict]:
    with MANIFEST.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def values_for(chart_id: int, arch: str, surface: str, measurement: str) -> list[Optional[int]]:
    p = JSON_DIR / f"chart_{chart_id:02d}_{arch}_{surface}_{measurement}.json"
    if not p.exists():
        raise FileNotFoundError(f"Missing OCR JSON: {p}")
    with p.open(encoding="utf-8") as fh:
        return json.load(fh)["values"]


def render_overlay(
    width: int,
    triplets: list[list[int]],
    boundaries: list[int],
    values: list[Optional[int]],
    expected: Optional[list[Optional[int]]] = None,
) -> Image.Image:
    """Render the OCR values beneath each site x-center.  When ``expected``
    is provided, mismatched cells are flagged in red."""
    overlay = Image.new("RGB", (width, OVERLAY_HEIGHT), "white")
    draw = ImageDraw.Draw(overlay)
    font = load_font(FONT_SIZE)
    small = load_font(18)

    for x in boundaries:
        draw.line([(x, 0), (x, OVERLAY_HEIGHT)], fill=(60, 60, 60), width=2)

    for tooth_idx, sites in enumerate(triplets):
        for site_idx, x in enumerate(sites):
            i = tooth_idx * SITES_PER_TOOTH + site_idx
            v = values[i]
            text = "_" if v is None else str(v)
            color = (0, 0, 0)
            if expected is not None:
                exp = expected[i]
                if exp is not None and v != exp and not (v is None and exp == 0):
                    color = (200, 0, 0)
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            cx = x
            cy = OVERLAY_HEIGHT // 2
            draw.text(
                (cx - tw // 2 - bbox[0], cy - th // 2 - bbox[1]),
                text,
                fill=color,
                font=font,
            )
            # tiny tick under the cell to anchor the digit visually
            draw.line(
                [(x, OVERLAY_HEIGHT - 6), (x, OVERLAY_HEIGHT - 1)],
                fill=(120, 120, 120),
                width=1,
            )

    # Tag overlay row with a label.
    draw.text((6, 4), "OCR", fill=(80, 80, 80), font=small)
    return overlay


def render_strip(
    chart_id: int,
    arch: str,
    surface: str,
    measurement: str,
    image_path: Path,
    expected_overlay: Optional[list[Optional[int]]] = None,
) -> Image.Image:
    """Stack the strip on top of an OCR-overlay row of the same width."""
    triplets = TOOTH_TRIPLETS[(chart_id, arch)]
    boundaries = compute_tooth_boundaries(triplets)
    values = values_for(chart_id, arch, surface, measurement)

    with Image.open(image_path) as src:
        strip = src.convert("RGB").copy()
    overlay = render_overlay(
        strip.width, triplets, boundaries, values, expected_overlay
    )

    out = Image.new("RGB", (strip.width, strip.height + overlay.height), "white")
    out.paste(strip, (0, 0))
    out.paste(overlay, (0, strip.height))
    return out


def collect_mismatch_strips() -> set[str]:
    """Return the set of strip filenames whose CAL identity has at least one
    violated site (CAL != PD + GM)."""
    if not CSV_PATH.exists():
        return set()
    rows = list(csv.DictReader(CSV_PATH.open()))
    by_site: dict[tuple, dict[str, str]] = {}
    for r in rows:
        key = (r["chart_id"], r["arch"], r["surface"],
               r["tooth_number"], r["site"])
        by_site.setdefault(key, {})[r["measurement"]] = r["value"]
    bad_keys: set[tuple] = set()
    for key, m in by_site.items():
        try:
            pd = int(m["PD"]) if m["PD"] != "" else None
            cal = int(m["CAL"]) if m["CAL"] != "" else None
            gm = int(m["GM"]) if m["GM"] != "" else 0
        except (KeyError, ValueError):
            continue
        if pd is None or cal is None:
            continue
        if pd + gm != cal:
            bad_keys.add((key[0], key[1], key[2]))
    out: set[str] = set()
    for chart_id, arch, surface in bad_keys:
        for meas in ("PD", "GM", "CAL"):
            out.add(
                f"periodontal_charting_{int(chart_id):02d}_{arch}_{surface}_{meas}.jpg"
            )
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "mode",
        nargs="?",
        default="sample",
        choices=("sample", "all", "mismatches"),
        help="Which strips to render.",
    )
    args = p.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    by_name = {Path(r["output_file"]).name: r for r in manifest}

    if args.mode == "sample":
        names = DEFAULT_SAMPLE
    elif args.mode == "all":
        names = [Path(r["output_file"]).name for r in manifest]
    else:
        names = sorted(collect_mismatch_strips())
        if not names:
            print("No mismatched strips found.")
            return 0

    print(f"Rendering {len(names)} strips to {OUTPUT_DIR.relative_to(ROOT)} ...")
    for name in names:
        if name not in by_name:
            print(f"  skip {name}: not in manifest")
            continue
        row = by_name[name]
        chart_id = int(row["chart_id"])
        arch = row["arch"]
        surface = row["surface"]
        measurement = row["measurement"]
        image_path = ROOT / row["output_file"]
        rendered = render_strip(
            chart_id, arch, surface, measurement, image_path
        )
        out_path = OUTPUT_DIR / f"spot_check_{name}"
        rendered.save(out_path, quality=92)
        print(f"  wrote {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
