#!/usr/bin/env python3
"""Deskew, annotate with tooth-column structure, then slice each periodontal
table crop into per-measurement row strips.

For every table this tool:
  1. Deskews the source crop with the per-table angle baked into
     ``manifests/periodontal_row_crop_manifest.csv``.
  2. Auto-derives tooth-boundary x-positions from a small per-table
     calibration of digit-triplet centers (``TOOTH_TRIPLETS`` below).
  3. Draws onto the deskewed image:
       - 15 strong gray vertical tooth-boundary lines spanning the chart
         data area (top of first row strip to bottom of last).
       - 4 faint short tick marks per tooth inter-site boundary, placed at
         the top and bottom edges of every row strip.  This gives every
         row strip an unmistakable "tick-tick-tick" pattern within each
         tooth so a vision model can count blank sites.
  4. Renders a tooth-number header strip ("00 teeth") with the universal
     tooth numbers (2-15 for maxillary, 31-18 for mandibular) centered
     between consecutive tooth-boundary lines.
  5. Crops every measurement row from the manifest and writes one strip
     per (chart, arch, surface, measurement), plus the header strip, into
     ``crops/rows/``.

All angles, separators and tooth-column triplets are hardcoded - no
runtime detection.  The annotation overlay is purely additive: it never
touches the source crops in ``crops/`` and the underlying digit pixels
are never overdrawn (lines fall in inter-cell whitespace).
"""

import csv
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "manifests" / "periodontal_row_crop_manifest.csv"
OUTPUT_DIR = ROOT / "crops" / "rows"


# Per-table 9 row-separator y-positions (in deskewed coordinates).
# Identical to the values stored in the row-crop manifest; cached here so we
# know the full chart data extent (sep[0] to sep[8]) for drawing vertical
# boundary lines and the y-position of the tooth-number header strip.
SEPARATORS: Dict[Tuple[int, str], List[int]] = {
    (1, "maxillary"):  [65, 121, 177, 233, 302, 362, 418, 473, 529],
    (1, "mandibular"): [23, 80, 136, 193, 250, 322, 378, 435, 492],
    (2, "maxillary"):  [74, 130, 186, 243, 311, 371, 426, 482, 538],
    (2, "mandibular"): [12, 69, 125, 182, 238, 311, 363, 424, 481],
    (3, "maxillary"):  [81, 138, 195, 250, 319, 379, 434, 490, 546],
    (3, "mandibular"): [20, 76, 132, 189, 246, 319, 371, 432, 488],
    (4, "maxillary"):  [62, 119, 175, 231, 303, 359, 415, 471, 527],
    (4, "mandibular"): [20, 77, 133, 190, 247, 315, 372, 432, 489],
    (5, "maxillary"):  [85, 141, 198, 254, 326, 382, 437, 494, 550],
    (5, "mandibular"): [24, 79, 136, 193, 250, 322, 375, 436, 492],
}


# Per-table digit-triplet centers, 14 teeth × 3 sites each, in the deskewed
# coordinate system.  Detected automatically from PD rows then hardcoded
# here so cropping is fully deterministic.  The three values per tooth are
# the x-centers of the printed digits for that tooth's three measurement
# sites, read left-to-right.
TOOTH_TRIPLETS: Dict[Tuple[int, str], List[List[int]]] = {
    (1, "maxillary"): [
        [636, 726, 816], [961, 1052, 1142], [1287, 1378, 1469], [1615, 1704, 1795],
        [1943, 2035, 2125], [2269, 2359, 2451], [2598, 2689, 2778], [2925, 3014, 3107],
        [3252, 3344, 3433], [3578, 3668, 3757], [3901, 3993, 4082], [4228, 4319, 4409],
        [4552, 4645, 4734], [4878, 4968, 5056],
    ],
    (1, "mandibular"): [
        [647, 737, 827], [972, 1063, 1151], [1297, 1388, 1478], [1624, 1714, 1803],
        [1950, 2042, 2132], [2276, 2368, 2459], [2605, 2696, 2786], [2932, 3022, 3112],
        [3258, 3350, 3439], [3584, 3674, 3765], [3909, 3999, 4091], [4237, 4326, 4417],
        [4562, 4653, 4742], [4888, 4977, 5065],
    ],
    (2, "maxillary"): [
        [633, 723, 814], [960, 1049, 1139], [1285, 1375, 1466], [1612, 1702, 1792],
        [1940, 2032, 2122], [2267, 2358, 2450], [2597, 2687, 2777], [2922, 3012, 3103],
        [3249, 3341, 3430], [3576, 3666, 3756], [3900, 3992, 4081], [4226, 4317, 4407],
        [4550, 4643, 4731], [4877, 4966, 5054],
    ],
    (2, "mandibular"): [
        [641, 732, 820], [967, 1058, 1147], [1293, 1383, 1473], [1619, 1709, 1799],
        [1946, 2039, 2129], [2273, 2366, 2456], [2603, 2694, 2783], [2930, 3019, 3110],
        [3257, 3347, 3438], [3584, 3672, 3763], [3908, 3999, 4088], [4235, 4325, 4416],
        [4560, 4651, 4740], [4885, 4974, 5064],
    ],
    (3, "maxillary"): [
        [640, 730, 819], [965, 1056, 1146], [1291, 1382, 1473], [1619, 1710, 1799],
        [1947, 2040, 2131], [2276, 2367, 2458], [2604, 2694, 2786], [2932, 3023, 3114],
        [3259, 3350, 3440], [3584, 3673, 3765], [3910, 4000, 4089], [4236, 4327, 4416],
        [4560, 4653, 4743], [4888, 4976, 5065],
    ],
    (3, "mandibular"): [
        [640, 731, 820], [966, 1057, 1147], [1294, 1384, 1473], [1619, 1710, 1799],
        [1947, 2040, 2130], [2276, 2367, 2457], [2604, 2695, 2785], [2932, 3023, 3114],
        [3260, 3350, 3441], [3586, 3674, 3765], [3910, 4001, 4090], [4237, 4328, 4418],
        [4563, 4654, 4743], [4889, 4977, 5066],
    ],
    (4, "maxillary"): [
        [646, 737, 827], [973, 1063, 1153], [1300, 1389, 1480], [1626, 1715, 1807],
        [1956, 2048, 2138], [2284, 2373, 2463], [2610, 2702, 2792], [2938, 3028, 3120],
        [3264, 3355, 3445], [3590, 3683, 3772], [3916, 4007, 4095], [4239, 4331, 4421],
        [4565, 4658, 4746], [4891, 4981, 5069],
    ],
    (4, "mandibular"): [
        [660, 750, 839], [985, 1076, 1165], [1311, 1401, 1491], [1636, 1727, 1817],
        [1965, 2057, 2146], [2292, 2383, 2473], [2619, 2711, 2801], [2948, 3038, 3128],
        [3274, 3364, 3455], [3601, 3690, 3780], [3926, 4016, 4105], [4250, 4342, 4433],
        [4577, 4668, 4757], [4902, 4990, 5080],
    ],
    (5, "maxillary"): [
        [637, 728, 818], [967, 1058, 1144], [1293, 1383, 1471], [1619, 1711, 1801],
        [1948, 2041, 2130], [2277, 2367, 2459], [2607, 2700, 2790], [2936, 3027, 3116],
        [3263, 3354, 3445], [3591, 3683, 3773], [3918, 4008, 4097], [4241, 4335, 4425],
        [4570, 4662, 4751], [4896, 4986, 5071],
    ],
    (5, "mandibular"): [
        [633, 725, 815], [963, 1055, 1145], [1290, 1380, 1469], [1615, 1708, 1798],
        [1945, 2038, 2127], [2274, 2364, 2455], [2605, 2697, 2786], [2933, 3024, 3115],
        [3260, 3352, 3443], [3589, 3680, 3769], [3916, 4006, 4095], [4241, 4332, 4422],
        [4568, 4659, 4749], [4892, 4984, 5069],
    ],
}


# Universal tooth numbers in left-to-right order for our 14-tooth crops.
# Wisdom teeth (1, 16, 17, 32) are excluded by the upstream table-crop step.
TOOTH_NUMBERS: Dict[str, List[int]] = {
    "maxillary":  [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    "mandibular": [31, 30, 29, 28, 27, 26, 25, 24, 23, 22, 21, 20, 19, 18],
}


HEADER_STRIP_HEIGHT = 70  # px, for the tooth-number header strip
TOOTH_BOUNDARY_COLOR = (60, 60, 60)
TOOTH_BOUNDARY_WIDTH = 2
INTER_SITE_TICK_COLOR = (90, 90, 90)
INTER_SITE_TICK_HEIGHT = 16
INTER_SITE_TICK_WIDTH = 1
HEADER_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
HEADER_FONT_SIZE = 38


def compute_tooth_boundaries(triplets: List[List[int]]) -> List[int]:
    """Return 15 x-positions: left outer, 13 inter-tooth midpoints, right outer."""
    boundaries: List[int] = []
    # 13 inter-tooth midpoints: between rightmost site of T_i and leftmost of T_{i+1}
    inter = [
        (triplets[i][2] + triplets[i + 1][0]) // 2
        for i in range(len(triplets) - 1)
    ]
    # Outer boundaries: extrapolate using the local half-gap
    left_half_gap = (triplets[1][0] - triplets[0][2]) // 2
    right_half_gap = (triplets[-1][0] - triplets[-2][2]) // 2
    left_outer = triplets[0][0] - left_half_gap
    right_outer = triplets[-1][2] + right_half_gap
    boundaries.append(left_outer)
    boundaries.extend(inter)
    boundaries.append(right_outer)
    return boundaries


def compute_inter_site_ticks(triplets: List[List[int]]) -> List[int]:
    """Return 28 x-positions: 2 inter-site midpoints per tooth (between site
    1-2 and site 2-3)."""
    ticks: List[int] = []
    for sites in triplets:
        ticks.append((sites[0] + sites[1]) // 2)
        ticks.append((sites[1] + sites[2]) // 2)
    return ticks


def annotate_table(
    deskewed: Image.Image,
    seps: List[int],
    boundaries: List[int],
    inter_ticks: List[int],
) -> Image.Image:
    """Draw tooth-boundary lines (full chart height) and inter-site ticks
    (at top + bottom of each row strip) onto a copy of the deskewed image."""
    annotated = deskewed.copy().convert("RGB")
    draw = ImageDraw.Draw(annotated)

    chart_top = seps[0]
    chart_bot = seps[-1]

    for x in boundaries:
        draw.line(
            [(x, chart_top), (x, chart_bot)],
            fill=TOOTH_BOUNDARY_COLOR,
            width=TOOTH_BOUNDARY_WIDTH,
        )

    for i in range(len(seps) - 1):
        y_top = seps[i]
        y_bot = seps[i + 1]
        for x in inter_ticks:
            draw.line(
                [(x, y_top), (x, y_top + INTER_SITE_TICK_HEIGHT)],
                fill=INTER_SITE_TICK_COLOR,
                width=INTER_SITE_TICK_WIDTH,
            )
            draw.line(
                [(x, y_bot - INTER_SITE_TICK_HEIGHT), (x, y_bot)],
                fill=INTER_SITE_TICK_COLOR,
                width=INTER_SITE_TICK_WIDTH,
            )

    return annotated


def render_header_strip(
    width: int,
    boundaries: List[int],
    tooth_numbers: List[int],
) -> Image.Image:
    """Build the tooth-number header strip: tooth numbers centered between
    consecutive tooth-boundary lines, with the boundary lines drawn through."""
    header = Image.new("RGB", (width, HEADER_STRIP_HEIGHT), "white")
    draw = ImageDraw.Draw(header)

    try:
        font = ImageFont.truetype(HEADER_FONT_PATH, HEADER_FONT_SIZE)
    except OSError:
        font = ImageFont.load_default()

    for x in boundaries:
        draw.line(
            [(x, 0), (x, HEADER_STRIP_HEIGHT)],
            fill=TOOTH_BOUNDARY_COLOR,
            width=TOOTH_BOUNDARY_WIDTH,
        )

    for tooth_num, x_left, x_right in zip(
        tooth_numbers, boundaries[:-1], boundaries[1:]
    ):
        text = str(tooth_num)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        cx = (x_left + x_right) // 2
        cy = HEADER_STRIP_HEIGHT // 2
        draw.text(
            (cx - tw // 2 - bbox[0], cy - th // 2 - bbox[1]),
            text,
            fill="black",
            font=font,
        )

    return header


def load_manifest() -> List[dict]:
    with MANIFEST.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def annotate_and_crop() -> None:
    rows = load_manifest()
    if not rows:
        raise ValueError(f"No row entries found in {MANIFEST}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    by_table: Dict[Tuple[int, str], List[dict]] = {}
    for row in rows:
        key = (int(row["chart_id"]), row["arch"])
        by_table.setdefault(key, []).append(row)

    for (chart_id, arch), table_rows in sorted(by_table.items()):
        seps = SEPARATORS[(chart_id, arch)]
        triplets = TOOTH_TRIPLETS[(chart_id, arch)]
        tooth_numbers = TOOTH_NUMBERS[arch]
        boundaries = compute_tooth_boundaries(triplets)
        inter_ticks = compute_inter_site_ticks(triplets)

        first = table_rows[0]
        source_path = ROOT / first["source_file"]
        rotation_deg_clockwise = float(first["rotation_deg_clockwise"])

        with Image.open(source_path) as src:
            deskewed = src.rotate(
                -rotation_deg_clockwise,
                resample=Image.BILINEAR,
                fillcolor="white",
            )

        annotated = annotate_table(deskewed, seps, boundaries, inter_ticks)

        header = render_header_strip(annotated.width, boundaries, tooth_numbers)
        header_path = (
            OUTPUT_DIR / f"periodontal_charting_{chart_id:02d}_{arch}_TEETH.jpg"
        )
        header.save(header_path, quality=95)
        print(f"saved {header_path.relative_to(ROOT)}")

        for row in table_rows:
            y0 = int(row["crop_y_top"])
            y1 = int(row["crop_y_bottom"])
            output_path = ROOT / row["output_file"]
            cropped = annotated.crop((0, y0, annotated.width, y1))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            cropped.save(output_path, quality=95)
            print(f"saved {output_path.relative_to(ROOT)}")


if __name__ == "__main__":
    annotate_and_crop()
