#!/usr/bin/env python3
"""Slice each periodontal table crop into per-measurement row strips.

Reads ``manifests/periodontal_row_crop_manifest.csv`` and, for every row
in that file, deskews the source table crop by the specified per-table
rotation angle and then cuts a horizontal y-band that contains a single
measurement row (PD / GM / CAL / MGJ for either the FACIAL or LINGUAL
surface).  All deskew angles and y-ranges are hardcoded in the manifest
- there is no runtime detection.
"""

import csv
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "manifests" / "periodontal_row_crop_manifest.csv"


def crop_rows_from_manifest() -> None:
    with MANIFEST.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        raise ValueError(f"No row-crop entries found in {MANIFEST}")

    cache: dict[tuple[Path, float], Image.Image] = {}

    for row in rows:
        source_path = ROOT / row["source_file"]
        output_path = ROOT / row["output_file"]
        rotation_deg_clockwise = float(row["rotation_deg_clockwise"])
        crop_y_top = int(row["crop_y_top"])
        crop_y_bottom = int(row["crop_y_bottom"])

        cache_key = (source_path, rotation_deg_clockwise)
        deskewed = cache.get(cache_key)
        if deskewed is None:
            with Image.open(source_path) as image:
                deskewed = image.rotate(
                    -rotation_deg_clockwise,
                    resample=Image.BILINEAR,
                    fillcolor="white",
                )
            cache[cache_key] = deskewed

        if crop_y_bottom > deskewed.height or crop_y_top < 0:
            raise ValueError(
                f"y range [{crop_y_top}, {crop_y_bottom}] out of bounds for "
                f"deskewed image of size {deskewed.size} ({source_path})"
            )

        crop_box = (0, crop_y_top, deskewed.width, crop_y_bottom)
        cropped = deskewed.crop(crop_box)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(output_path, quality=95)
        print(f"saved {output_path.relative_to(ROOT)}")


if __name__ == "__main__":
    crop_rows_from_manifest()
