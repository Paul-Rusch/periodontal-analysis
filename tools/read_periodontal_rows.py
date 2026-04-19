#!/usr/bin/env python3
"""OCR each annotated periodontal row strip and emit a tidy long-format CSV.

Driven by ``manifests/periodontal_row_crop_manifest.csv`` (80 strips).
For every strip we ask a vision model to read exactly 42 values
(14 teeth x 3 sites, left-to-right) and return them as a structured list.
Per-strip raw JSON is cached under ``outputs/json/`` so the tidy CSV can be
rebuilt without re-OCR'ing.

Site labelling
--------------
Each strip is 14 teeth wide.  In the universal numbering system the chart
is mirrored at the midline:

    maxillary  : 2  3  4  5  6  7  8 | 9 10 11 12 13 14 15
    mandibular : 31 30 29 28 27 26 25 | 24 23 22 21 20 19 18

For the patient's right side (positions 1-7, the left half of the strip)
sites read distal-central-mesial; for the patient's left side (positions
8-14) they read mesial-central-distal.  The CSV records the dental site
label, not just the positional index.
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import sys
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field

# Tooth-column geometry comes from the annotation tool, which is the source
# of truth for where each tooth sits in the deskewed coordinate system.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from annotate_and_crop_periodontal_rows import (  # noqa: E402
    TOOTH_TRIPLETS,
    compute_tooth_boundaries,
)


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "manifests" / "periodontal_row_crop_manifest.csv"
CHART_METADATA_PATH = ROOT / "manifests" / "chart_metadata.csv"
JSON_DIR = ROOT / "outputs" / "json"
CSV_PATH = ROOT / "outputs" / "periodontal_readings.csv"
DEBUG_TILES_DIR = ROOT / "outputs" / "ocr_tiles"

TEETH_PER_ARCH = 14
SITES_PER_TOOTH = 3
VALUES_PER_ROW = TEETH_PER_ARCH * SITES_PER_TOOTH  # 42

TOOTH_NUMBERS: dict[str, list[int]] = {
    "maxillary":  [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    "mandibular": [31, 30, 29, 28, 27, 26, 25, 24, 23, 22, 21, 20, 19, 18],
}

# Site labels per half-arch (0-indexed positions 0..6 = right half, 7..13 = left half)
SITE_LABELS_RIGHT = ("distal", "central", "mesial")
SITE_LABELS_LEFT = ("mesial", "central", "distal")

DEFAULT_MODEL = "gpt-4.1"

# Stack each strip's 14 single-tooth crops vertically.  Visual upscaling makes
# digits big enough to OCR reliably; padding rows separate them.
TOOTH_TILE_VSCALE = 4
TOOTH_TILE_HSCALE = 2
TOOTH_TILE_PAD = 12   # px of vertical white padding between teeth (after scale)
TOOTH_TILE_LABEL_W = 90  # px of left-side label column (tooth index 1..14)

SYSTEM_PROMPT = f"""\
You are a dental data-entry assistant transcribing periodontal probing
measurements from a single chart row.

The image you receive is a vertical stack of exactly {TEETH_PER_ARCH}
crops, one per tooth.  Each crop is labelled on its left with its
1-indexed tooth row number ("01" through "14").  The teeth are stacked
top to bottom in left-to-right order as they appear on the chart.

Within each tooth crop you will see {SITES_PER_TOOTH} measurement sites
side by side, separated by short vertical tick marks at the top and
bottom edges.  Read the {SITES_PER_TOOTH} sites of each tooth strictly
left to right.

For every tooth (rows 01-{TEETH_PER_ARCH:02d}) return a list of exactly
{SITES_PER_TOOTH} entries.  Each entry is the integer printed in that
cell, or null if the cell is blank.

Rules:
* Most printed values are a single digit (0-9).  A few cells contain a
  two-digit number (e.g. 10, 12, 14) where the digits are stacked
  vertically; treat any vertically stacked digit pair within one site as
  a single number (so "1" stacked over "0" means 10, not two values).
* PD and CAL rows are normally filled at every site.  A blank cell is
  unusual but does occur (e.g. for a missing tooth) - return null for
  those, do not guess.
* GM and MGJ rows are mostly blank: return null for any blank cell, and
  return a number only when a digit is clearly printed.  Faint dotted-
  line residue, the tooth-boundary lines and the site tick marks are
  NOT digits.
* You must return exactly {TEETH_PER_ARCH} tooth entries in row order
  (top to bottom of the stacked image), each containing exactly
  {SITES_PER_TOOTH} site entries.
"""


class ToothReading(BaseModel):
    sites: list[Optional[int]] = Field(
        ...,
        description=(
            f"Exactly {SITES_PER_TOOTH} entries, the three sites of this "
            "tooth read left to right.  Use null for a blank cell."
        ),
        min_length=SITES_PER_TOOTH,
        max_length=SITES_PER_TOOTH,
    )


class StripReading(BaseModel):
    teeth: list[ToothReading] = Field(
        ...,
        description=(
            f"Exactly {TEETH_PER_ARCH} entries, one per tooth, in the "
            "top-to-bottom order they appear in the stacked image."
        ),
        min_length=TEETH_PER_ARCH,
        max_length=TEETH_PER_ARCH,
    )

    def flat(self) -> list[Optional[int]]:
        out: list[Optional[int]] = []
        for tooth in self.teeth:
            out.extend(tooth.sites)
        return out


def encode_image_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def _label_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size
        )
    except OSError:
        return ImageFont.load_default()


def build_tooth_stack(
    strip_image: Image.Image,
    chart_id: int,
    arch: str,
) -> Image.Image:
    """Slice ``strip_image`` into 14 per-tooth crops using the deskewed-
    coordinate tooth boundaries, scale each crop, and stack them vertically
    with a left label column showing the tooth row index (1-14)."""
    triplets = TOOTH_TRIPLETS[(chart_id, arch)]
    boundaries = compute_tooth_boundaries(triplets)
    if len(boundaries) != TEETH_PER_ARCH + 1:
        raise ValueError(
            f"chart {chart_id} {arch}: expected {TEETH_PER_ARCH + 1} "
            f"boundaries, got {len(boundaries)}"
        )

    # Per-tooth horizontal extent (clamped to strip width).
    sw = strip_image.width
    crops: list[Image.Image] = []
    for i in range(TEETH_PER_ARCH):
        x0 = max(0, boundaries[i])
        x1 = min(sw, boundaries[i + 1])
        crop = strip_image.crop((x0, 0, x1, strip_image.height))
        crop = crop.resize(
            (crop.width * TOOTH_TILE_HSCALE, crop.height * TOOTH_TILE_VSCALE),
            resample=Image.LANCZOS,
        )
        crops.append(crop)

    tile_w = max(c.width for c in crops)
    tile_h = max(c.height for c in crops)
    pad = TOOTH_TILE_PAD
    label_w = TOOTH_TILE_LABEL_W
    total_h = TEETH_PER_ARCH * tile_h + (TEETH_PER_ARCH - 1) * pad
    total_w = label_w + tile_w

    composite = Image.new("RGB", (total_w, total_h), "white")
    draw = ImageDraw.Draw(composite)
    font = _label_font(48)

    for i, crop in enumerate(crops):
        y = i * (tile_h + pad)
        composite.paste(crop, (label_w, y))
        # Tooth row index label (01..14)
        text = f"{i + 1:02d}"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        cx = label_w // 2
        cy = y + tile_h // 2
        draw.text(
            (cx - tw // 2 - bbox[0], cy - th // 2 - bbox[1]),
            text,
            fill="black",
            font=font,
        )
        # Faint horizontal separator below each tile (except the last).
        if i < TEETH_PER_ARCH - 1:
            sep_y = y + tile_h + pad // 2
            draw.line([(0, sep_y), (total_w, sep_y)], fill=(180, 180, 180), width=1)

    return composite


def image_to_b64_jpeg(img: Image.Image, quality: int = 92) -> str:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode()


def read_strip(
    client: OpenAI,
    image_path: Path,
    chart_id: int,
    arch: str,
    surface: str,
    measurement: str,
    model: str,
    save_tile_to: Optional[Path] = None,
    max_attempts: int = 3,
) -> list[Optional[int]]:
    teeth_left_to_right = ", ".join(str(n) for n in TOOTH_NUMBERS[arch])

    with Image.open(image_path) as src:
        strip = src.convert("RGB").copy()
    composite = build_tooth_stack(strip, chart_id, arch)
    if save_tile_to is not None:
        save_tile_to.parent.mkdir(parents=True, exist_ok=True)
        composite.save(save_tile_to, quality=92)
    b64 = image_to_b64_jpeg(composite)

    base_user_text = (
        f"Strip metadata: chart {chart_id}, {arch} arch, {surface} surface, "
        f"{measurement} measurement.\n"
        f"The image is a vertical stack of {TEETH_PER_ARCH} per-tooth crops "
        f"(rows 01-{TEETH_PER_ARCH:02d}, top to bottom).\n"
        f"For reference, those tooth rows correspond to universal tooth "
        f"numbers (top to bottom): {teeth_left_to_right}.\n"
        "Return one entry per tooth row, each with the 3 site values read "
        "left to right inside that tooth (use null for blank cells)."
    )

    last_err: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        user_text = base_user_text
        if attempt > 1:
            user_text += (
                f"\n\nIMPORTANT: the previous response did not have the "
                f"required shape ({TEETH_PER_ARCH} teeth x "
                f"{SITES_PER_TOOTH} sites). Return one entry per row of "
                f"the stacked image, top to bottom, with exactly "
                f"{SITES_PER_TOOTH} site entries each. Use null for blank."
            )

        try:
            response = client.responses.parse(
                model=model,
                instructions=SYSTEM_PROMPT,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": user_text},
                            {
                                "type": "input_image",
                                "image_url": f"data:image/jpeg;base64,{b64}",
                                "detail": "high",
                            },
                        ],
                    },
                ],
                text_format=StripReading,
            )
        except Exception as exc:  # noqa: BLE001 - openai/pydantic length errors
            last_err = exc
            continue

        parsed = response.output_parsed
        if parsed is None:
            last_err = RuntimeError(f"{image_path.name}: no parsed output")
            continue
        flat = parsed.flat()
        if len(flat) != VALUES_PER_ROW:
            last_err = ValueError(
                f"{image_path.name}: expected {VALUES_PER_ROW} values, "
                f"got {len(flat)}"
            )
            continue
        return flat

    raise RuntimeError(
        f"{image_path.name}: failed to obtain {VALUES_PER_ROW} values after "
        f"{max_attempts} attempts ({last_err})"
    )


def site_label_for(tooth_position_idx: int, site_within_tooth: int) -> str:
    """tooth_position_idx: 0..13; site_within_tooth: 0..2."""
    if tooth_position_idx < 7:
        return SITE_LABELS_RIGHT[site_within_tooth]
    return SITE_LABELS_LEFT[site_within_tooth]


def expand_to_tidy_rows(
    chart_id: int,
    chart_meta: dict,
    arch: str,
    surface: str,
    measurement: str,
    values: list[Optional[int]],
) -> list[dict]:
    out: list[dict] = []
    teeth = TOOTH_NUMBERS[arch]
    for i, raw in enumerate(values):
        tooth_idx = i // SITES_PER_TOOTH      # 0..13
        site_idx = i % SITES_PER_TOOTH        # 0..2
        tooth_number = teeth[tooth_idx]
        site = site_label_for(tooth_idx, site_idx)

        is_blank = raw is None
        if is_blank and measurement in ("GM", "MGJ"):
            value: object = 0
        elif is_blank:
            # PD / CAL blank: leave empty + flag
            value = ""
        else:
            value = int(raw)

        out.append(
            {
                "patient_id": chart_meta["patient_id"],
                "chart_id": chart_id,
                "exam_date": chart_meta["exam_date"],
                "exam_index": chart_meta["exam_index"],
                "arch": arch,
                "surface": surface,
                "measurement": measurement,
                "tooth_number": tooth_number,
                "site": site,
                "value": value,
            }
        )
    return out


def load_manifest() -> list[dict]:
    with MANIFEST.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_chart_metadata() -> dict[int, dict]:
    """Map ``chart_id -> {patient_id, exam_date, exam_index}``.

    ``exam_index`` is computed at load time: 1 = the patient's earliest
    (baseline) exam, ascending in chronological order.  Indices are
    per-patient, so two patients each get an index 1.
    """
    if not CHART_METADATA_PATH.exists():
        raise FileNotFoundError(
            f"Expected chart metadata manifest at {CHART_METADATA_PATH}"
        )
    raw: list[dict] = []
    with CHART_METADATA_PATH.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            raw.append({
                "chart_id": int(row["chart_id"]),
                "exam_date": row["exam_date"].strip(),
                "patient_id": row["patient_id"].strip(),
            })
    by_patient: dict[str, list[dict]] = {}
    for r in raw:
        by_patient.setdefault(r["patient_id"], []).append(r)
    out: dict[int, dict] = {}
    for patient, rows in by_patient.items():
        for idx, r in enumerate(sorted(rows, key=lambda x: x["exam_date"]), 1):
            out[r["chart_id"]] = {
                "patient_id": r["patient_id"],
                "exam_date": r["exam_date"],
                "exam_index": idx,
            }
    return out


def json_path_for_pass(
    chart_id: int, arch: str, surface: str, measurement: str, pass_idx: int
) -> Path:
    """pass_idx == 1 uses the canonical filename; later passes get a suffix."""
    base = f"chart_{chart_id:02d}_{arch}_{surface}_{measurement}"
    if pass_idx == 1:
        return JSON_DIR / f"{base}.json"
    return JSON_DIR / f"{base}_pass{pass_idx}.json"


def reconcile_passes(
    passes: list[list[Optional[int]]],
    measurement: str,
    pd_values: Optional[list[Optional[int]]],
    gm_values: Optional[list[Optional[int]]],
    cal_values: Optional[list[Optional[int]]],
) -> tuple[list[Optional[int]], int, int]:
    """Combine N independent OCR passes of the same strip.

    Per cell: if all passes agree, return that value.  Otherwise prefer the
    most common value; ties are broken by whichever value makes the CAL
    identity (CAL = PD + GM with GM = 0 if blank) hold, then by pass-1 order.

    Returns (values, n_disagreements, n_unresolved_after_voting).
    """
    if not passes:
        raise ValueError("reconcile_passes called with no passes")
    n = len(passes[0])
    out: list[Optional[int]] = []
    disagreements = 0
    unresolved = 0
    for i in range(n):
        cell_votes = [p[i] for p in passes]
        if all(v == cell_votes[0] for v in cell_votes):
            out.append(cell_votes[0])
            continue
        disagreements += 1

        # Frequency vote.
        counts: dict[Optional[int], int] = {}
        for v in cell_votes:
            counts[v] = counts.get(v, 0) + 1
        max_freq = max(counts.values())
        top = [v for v, c in counts.items() if c == max_freq]

        if len(top) == 1:
            out.append(top[0])
            continue

        # Identity-based tiebreak (only for PD/GM/CAL strips).
        chosen: Optional[Optional[int]] = None
        if (
            measurement in ("PD", "GM", "CAL")
            and pd_values is not None
            and gm_values is not None
            and cal_values is not None
        ):
            for cand in top:
                pd = pd_values[i] if measurement != "PD" else cand
                gm_raw = gm_values[i] if measurement != "GM" else cand
                gm = gm_raw if gm_raw is not None else 0
                cal = cal_values[i] if measurement != "CAL" else cand
                if pd is None or cal is None:
                    continue
                if pd + gm == cal:
                    chosen = cand
                    break
        if chosen is None:
            unresolved += 1
            chosen = cell_votes[0]
        out.append(chosen)
    return out, disagreements, unresolved


def _ocr_strip_with_cache(
    *,
    client: OpenAI,
    image_path: Path,
    chart_id: int,
    arch: str,
    surface: str,
    measurement: str,
    model: str,
    pass_idx: int,
    use_cache: bool,
    save_tiles: bool,
    label: str,
) -> list[Optional[int]]:
    cache_path = json_path_for_pass(chart_id, arch, surface, measurement, pass_idx)
    if use_cache and cache_path.exists():
        with cache_path.open(encoding="utf-8") as fh:
            print(f"{label} -- cached", flush=True)
            return json.load(fh)["values"]
    t0 = time.time()
    print(f"{label} -- OCR'ing ...", end=" ", flush=True)
    tile_path = (
        DEBUG_TILES_DIR / f"chart_{chart_id:02d}_{arch}_{surface}_{measurement}.jpg"
        if save_tiles else None
    )
    values = read_strip(
        client=client,
        image_path=image_path,
        chart_id=chart_id,
        arch=arch,
        surface=surface,
        measurement=measurement,
        model=model,
        save_tile_to=tile_path,
    )
    with cache_path.open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "chart_id": chart_id,
                "arch": arch,
                "surface": surface,
                "measurement": measurement,
                "model": model,
                "pass": pass_idx,
                "values": values,
            },
            fh,
            indent=2,
        )
    dt = time.time() - t0
    n_blank = sum(1 for v in values if v is None)
    print(f"OK  ({n_blank}/{VALUES_PER_ROW} blank, {dt:.1f}s)", flush=True)
    return values


def process(
    *,
    model: str,
    use_cache: bool,
    only: Optional[set[str]] = None,
    save_tiles: bool = False,
    passes: int = 1,
) -> None:
    load_dotenv(ROOT / ".env")
    client = OpenAI()

    JSON_DIR.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest()
    if only is not None:
        manifest = [r for r in manifest if Path(r["output_file"]).name in only]
        if not manifest:
            print("No strips match --only filter.")
            return

    # Run all passes for every strip first, then reconcile per (chart, arch,
    # surface) so the CAL identity tiebreaker has access to PD/GM/CAL values
    # from the same pass set.
    raw: dict[tuple, list[list[Optional[int]]]] = {}

    for pass_idx in range(1, passes + 1):
        if passes > 1:
            print(f"\n=== PASS {pass_idx}/{passes} ===")
        for i, row in enumerate(manifest, 1):
            chart_id = int(row["chart_id"])
            arch = row["arch"]
            surface = row["surface"]
            measurement = row["measurement"]
            image_path = ROOT / row["output_file"]
            label = f"[{i}/{len(manifest)}] pass{pass_idx} {image_path.name}"

            values = _ocr_strip_with_cache(
                client=client,
                image_path=image_path,
                chart_id=chart_id,
                arch=arch,
                surface=surface,
                measurement=measurement,
                model=model,
                pass_idx=pass_idx,
                use_cache=use_cache,
                save_tiles=save_tiles,
                label=label,
            )
            key = (chart_id, arch, surface, measurement)
            raw.setdefault(key, []).append(values)

    # Reconcile.
    chart_meta = load_chart_metadata()
    all_tidy: list[dict] = []
    pd_cal_blanks: list[str] = []
    total_disagreements = 0
    total_unresolved = 0

    by_strip: dict[tuple, dict[str, list[list[Optional[int]]]]] = {}
    for (chart_id, arch, surface, measurement), passes_list in raw.items():
        by_strip.setdefault((chart_id, arch, surface), {})[measurement] = passes_list

    missing_meta = sorted({k[0] for k in raw} - set(chart_meta))
    if missing_meta:
        raise RuntimeError(
            "manifests/chart_metadata.csv is missing entries for "
            f"chart_ids: {missing_meta}"
        )

    for (chart_id, arch, surface), strip_map in sorted(by_strip.items()):
        # First-pass values for the identity tiebreaker (per measurement).
        pd_p1 = strip_map["PD"][0]
        gm_p1 = strip_map["GM"][0]
        cal_p1 = strip_map["CAL"][0]
        for measurement in ("PD", "GM", "CAL", "MGJ"):
            passes_list = strip_map[measurement]
            if len(passes_list) == 1:
                final_values = passes_list[0]
                disagreements = 0
                unresolved = 0
            else:
                final_values, disagreements, unresolved = reconcile_passes(
                    passes_list,
                    measurement,
                    pd_values=pd_p1 if measurement != "PD" else None,
                    gm_values=gm_p1 if measurement != "GM" else None,
                    cal_values=cal_p1 if measurement != "CAL" else None,
                )
            total_disagreements += disagreements
            total_unresolved += unresolved

            if measurement in ("PD", "CAL"):
                for j, v in enumerate(final_values):
                    if v is None:
                        teeth = TOOTH_NUMBERS[arch]
                        tooth_idx = j // SITES_PER_TOOTH
                        site_idx = j % SITES_PER_TOOTH
                        pd_cal_blanks.append(
                            f"  blank {measurement} chart={chart_id} {arch}/{surface} "
                            f"tooth={teeth[tooth_idx]} site={site_label_for(tooth_idx, site_idx)}"
                        )

            all_tidy.extend(
                expand_to_tidy_rows(
                    chart_id, chart_meta[chart_id], arch, surface,
                    measurement, final_values,
                )
            )

    if passes > 1:
        print(
            f"\nReconciliation: {total_disagreements} cell disagreements across "
            f"passes ({total_unresolved} unresolved by majority + CAL identity)"
        )
    if pd_cal_blanks:
        print(f"\nFlagged {len(pd_cal_blanks)} blank PD/CAL cells (left empty in CSV):")
        for line in pd_cal_blanks[:25]:
            print(line)
        if len(pd_cal_blanks) > 25:
            print(f"  ... and {len(pd_cal_blanks) - 25} more")

    write_csv(all_tidy)
    print(
        f"\nWrote {len(all_tidy)} rows to {CSV_PATH.relative_to(ROOT)}"
        f" (expected 3360)"
    )


def write_csv(rows: list[dict]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "patient_id", "chart_id", "exam_date", "exam_index",
        "arch", "surface", "measurement",
        "tooth_number", "site", "value",
    ]
    with CSV_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI model id")
    p.add_argument(
        "--no-cache",
        action="store_true",
        help="Re-OCR every strip even if a cached JSON exists.",
    )
    p.add_argument(
        "--only",
        nargs="+",
        default=None,
        help="Optional list of strip filenames (basename) to limit work to.",
    )
    p.add_argument(
        "--save-tiles",
        action="store_true",
        help=f"Save the per-strip composite (sent to model) to {DEBUG_TILES_DIR}",
    )
    p.add_argument(
        "--passes",
        type=int,
        default=1,
        help=(
            "Number of independent OCR passes per strip.  When >1, results "
            "are reconciled per cell via majority vote with the CAL identity "
            "(CAL = PD + GM) as a tiebreaker."
        ),
    )
    args = p.parse_args(argv)

    process(
        model=args.model,
        use_cache=not args.no_cache,
        only=set(args.only) if args.only else None,
        save_tiles=args.save_tiles,
        passes=args.passes,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
