#!/usr/bin/env python3

import csv
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "manifests" / "periodontal_crop_manifest.csv"


def crop_from_manifest() -> None:
    with MANIFEST.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        raise ValueError(f"No crop rows found in {MANIFEST}")

    for row in rows:
        source_path = ROOT / row["source_file"]
        output_path = ROOT / row["output_file"]
        rotation_deg_clockwise = int(row["rotation_deg_clockwise"])
        crop_x = int(row["crop_x"])
        crop_y = int(row["crop_y"])
        crop_width = int(row["crop_width"])
        crop_height = int(row["crop_height"])

        with Image.open(source_path) as image:
            upright = image.rotate(-rotation_deg_clockwise, expand=True)
            crop_box = (
                crop_x,
                crop_y,
                crop_x + crop_width,
                crop_y + crop_height,
            )

            if crop_box[2] > upright.width or crop_box[3] > upright.height:
                raise ValueError(
                    f"Crop box {crop_box} exceeds rotated image bounds "
                    f"{upright.size} for {source_path}"
                )

            output_path.parent.mkdir(parents=True, exist_ok=True)
            cropped = upright.crop(crop_box)
            cropped.save(output_path, quality=95)
            print(f"saved {output_path.relative_to(ROOT)}")


if __name__ == "__main__":
    crop_from_manifest()
