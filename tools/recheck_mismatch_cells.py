#!/usr/bin/env python3
"""For every site that fails the CAL identity (CAL = PD + GM), re-OCR the
PD, GM and CAL cells INDIVIDUALLY at high resolution.  Single-cell crops
are unambiguous to the vision model, so this catches the systematic
misreads from the strip-level OCR pass.

For each cell we ask the model the same question N times (default 3) and
take the majority vote.  Updates land directly in the per-strip cache
files under ``outputs/json/`` (the canonical pass-1 file), so the next
``read_periodontal_rows.py`` invocation will pick them up.

Run with no arguments after every change to the CSV.
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "outputs" / "periodontal_readings.csv"
JSON_DIR = ROOT / "outputs" / "json"
ROWS_DIR = ROOT / "crops" / "rows"
CELL_DEBUG_DIR = ROOT / "outputs" / "cell_recheck"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from annotate_and_crop_periodontal_rows import (  # noqa: E402
    TOOTH_TRIPLETS,
    compute_tooth_boundaries,
)

TEETH_PER_ARCH = 14
SITES_PER_TOOTH = 3
MEASUREMENTS = ("PD", "GM", "CAL")
MODEL = "gpt-4.1"
DEFAULT_PASSES = 3
SCALE = 6  # px multiplier per axis for the cell crop sent to the model

TOOTH_NUMBERS = {
    "maxillary":  [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    "mandibular": [31, 30, 29, 28, 27, 26, 25, 24, 23, 22, 21, 20, 19, 18],
}
SITE_LABELS_RIGHT = ("distal", "central", "mesial")
SITE_LABELS_LEFT = ("mesial", "central", "distal")


SYSTEM_PROMPT = """\
You are a dental data-entry assistant.  The image you receive is a
single periodontal-chart cell, magnified.  It contains either:

* a single printed digit (0-9), or
* a two-digit integer (typically 10-15) where the digits are stacked
  vertically inside the cell, or
* nothing (a blank cell - no printed digit at all; faint dotted-line
  residue, the inter-site tick marks at the top/bottom edges and the
  vertical column boundary lines on the left/right edges are NOT
  digits).

Return the integer printed in the cell, or null if the cell is blank.
"""


class CellReading(BaseModel):
    value: Optional[int] = Field(
        ...,
        description="Integer printed in the cell, or null if blank.",
    )


def site_label_for(tooth_idx: int, site_idx: int) -> str:
    return (SITE_LABELS_RIGHT if tooth_idx < 7 else SITE_LABELS_LEFT)[site_idx]


def site_index_in_strip(arch: str, tooth_number: int, site: str) -> int:
    tooth_idx = TOOTH_NUMBERS[arch].index(tooth_number)
    if tooth_idx < 7:
        site_idx = SITE_LABELS_RIGHT.index(site)
    else:
        site_idx = SITE_LABELS_LEFT.index(site)
    return tooth_idx * SITES_PER_TOOTH + site_idx


def crop_cell(
    strip_image: Image.Image,
    boundaries: list[int],
    triplets: list[list[int]],
    tooth_idx: int,
    site_idx: int,
    pad: int = 4,
) -> Image.Image:
    sites = triplets[tooth_idx]
    inter_a = (sites[0] + sites[1]) // 2
    inter_b = (sites[1] + sites[2]) // 2
    edges = [boundaries[tooth_idx], inter_a, inter_b, boundaries[tooth_idx + 1]]
    x0 = max(0, edges[site_idx] - pad)
    x1 = min(strip_image.width, edges[site_idx + 1] + pad)
    return strip_image.crop((x0, 0, x1, strip_image.height))


def image_to_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


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
        pd = m.get("PD"); cal = m.get("CAL"); gm = m.get("GM")
        gm_v = gm if gm is not None else 0
        if pd is None or cal is None:
            continue
        if pd + gm_v == cal:
            continue
        chart_id, arch, surface, tooth, site = key
        out.append({
            "chart_id": chart_id, "arch": arch, "surface": surface,
            "tooth_number": tooth, "site": site,
            "PD": pd, "GM": gm, "CAL": cal,
        })
    return out


def _call_with_backoff(client: OpenAI, **kwargs):
    import openai
    delay = 2.0
    for attempt in range(8):
        try:
            return client.responses.parse(**kwargs)
        except openai.RateLimitError as exc:
            wait = delay
            # Honor the API hint when present.
            msg = str(exc)
            if "try again in" in msg:
                try:
                    hint = msg.split("try again in")[1].split("s")[0].strip()
                    wait = max(delay, float(hint) + 0.5)
                except Exception:  # noqa: BLE001
                    pass
            print(f"  rate-limited; sleeping {wait:.1f}s (attempt {attempt + 1})",
                  flush=True)
            time.sleep(wait)
            delay = min(delay * 2, 30)
    raise RuntimeError("rate-limit retries exhausted")


def ocr_cell(
    client: OpenAI,
    cell_img: Image.Image,
    measurement: str,
    passes: int,
) -> tuple[Optional[int], list[Optional[int]]]:
    b64 = image_to_b64(cell_img)
    user_text = (
        f"Magnified single periodontal-chart cell from a {measurement} row. "
        "Return the integer printed in the cell, or null if blank."
    )
    votes: list[Optional[int]] = []
    for _ in range(passes):
        response = _call_with_backoff(
            client,
            model=MODEL,
            instructions=SYSTEM_PROMPT,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": user_text},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{b64}",
                            "detail": "high",
                        },
                    ],
                },
            ],
            text_format=CellReading,
        )
        parsed = response.output_parsed
        if parsed is None:
            votes.append(None)
        else:
            votes.append(parsed.value)
    counts = Counter(votes)
    winner, _ = counts.most_common(1)[0]
    return winner, votes


def update_strip_json(
    chart_id: int, arch: str, surface: str, measurement: str,
    site_index: int, new_value: Optional[int],
) -> tuple[Optional[int], Optional[int]]:
    """Return (old_value, new_value).  Patches every pass-N JSON for the
    strip so the cross-pass reconciliation in ``read_periodontal_rows`` does
    not override the manual fix."""
    base = f"chart_{chart_id:02d}_{arch}_{surface}_{measurement}"
    # Pass 1 (canonical) plus any later passes.
    pass_paths = [JSON_DIR / f"{base}.json"]
    pass_paths += sorted(JSON_DIR.glob(f"{base}_pass*.json"))

    old = None
    for i, path in enumerate(pass_paths):
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if i == 0:
            old = data["values"][site_index]
        data["values"][site_index] = new_value
        data.setdefault("manual_overrides", []).append(
            {"site_index": site_index, "from": data["values"][site_index]
             if False else old, "to": new_value}
        )
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    return old, new_value


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--passes", type=int, default=DEFAULT_PASSES)
    p.add_argument("--save-cells", action="store_true",
                   help="Save each cell crop sent to the model under "
                        f"{CELL_DEBUG_DIR.relative_to(ROOT)}.")
    p.add_argument("--limit", type=int, default=None,
                   help="Optional max number of mismatches to recheck.")
    args = p.parse_args()

    load_dotenv(ROOT / ".env")
    client = OpenAI()
    if args.save_cells:
        CELL_DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    mismatches = gather_mismatches()
    if args.limit is not None:
        mismatches = mismatches[:args.limit]
    print(f"Re-checking {len(mismatches)} mismatched sites "
          f"({args.passes} passes per cell)")

    n_changed = 0
    n_resolved = 0
    n_unresolved = 0
    log_rows: list[dict] = []

    for i, rec in enumerate(mismatches, 1):
        chart_id = rec["chart_id"]; arch = rec["arch"]
        surface = rec["surface"]; tooth = rec["tooth_number"]
        site = rec["site"]

        tooth_idx = TOOTH_NUMBERS[arch].index(tooth)
        if tooth_idx < 7:
            site_idx_in_tooth = SITE_LABELS_RIGHT.index(site)
        else:
            site_idx_in_tooth = SITE_LABELS_LEFT.index(site)
        site_index = tooth_idx * SITES_PER_TOOTH + site_idx_in_tooth

        triplets = TOOTH_TRIPLETS[(chart_id, arch)]
        boundaries = compute_tooth_boundaries(triplets)

        new_vals: dict[str, Optional[int]] = {}
        votes_per_meas: dict[str, list[Optional[int]]] = {}
        t0 = time.time()
        for meas in MEASUREMENTS:
            strip_path = (
                ROWS_DIR
                / f"periodontal_charting_{chart_id:02d}_{arch}_{surface}_{meas}.jpg"
            )
            with Image.open(strip_path) as src:
                strip = src.convert("RGB").copy()
            cell = crop_cell(strip, boundaries, triplets, tooth_idx, site_idx_in_tooth)
            cell = cell.resize(
                (cell.width * SCALE, cell.height * SCALE), resample=Image.LANCZOS
            )
            if args.save_cells:
                cell.save(
                    CELL_DEBUG_DIR
                    / f"chart{chart_id:02d}_{arch}_{surface}_t{tooth:02d}_{site}_{meas}.png"
                )
            value, votes = ocr_cell(client, cell, meas, args.passes)
            new_vals[meas] = value
            votes_per_meas[meas] = votes

        old_pd, old_gm, old_cal = rec["PD"], rec["GM"], rec["CAL"]
        new_pd, new_gm, new_cal = new_vals["PD"], new_vals["GM"], new_vals["CAL"]
        new_gm_v = new_gm if new_gm is not None else 0
        identity_ok = (
            new_pd is not None and new_cal is not None
            and new_pd + new_gm_v == new_cal
        )

        change_summary = []
        for meas, old, new in [
            ("PD", old_pd, new_pd), ("GM", old_gm, new_gm), ("CAL", old_cal, new_cal),
        ]:
            if old != new:
                update_strip_json(
                    chart_id, arch, surface, meas, site_index, new,
                )
                change_summary.append(f"{meas}:{old}->{new}")
                n_changed += 1

        dt = time.time() - t0
        status = "OK" if identity_ok else "STILL OFF"
        if identity_ok:
            n_resolved += 1
        else:
            n_unresolved += 1
        print(
            f"[{i:3d}/{len(mismatches)}] chart{chart_id} {arch}/{surface} "
            f"tooth {tooth} {site}: {','.join(change_summary) or 'no change'}  "
            f"now PD={new_pd} GM={new_gm} CAL={new_cal}  -> {status}  "
            f"({dt:.1f}s)"
        )
        log_rows.append({
            "chart_id": chart_id, "arch": arch, "surface": surface,
            "tooth_number": tooth, "site": site,
            "old_PD": old_pd, "new_PD": new_pd,
            "old_GM": old_gm, "new_GM": new_gm,
            "old_CAL": old_cal, "new_CAL": new_cal,
            "votes_PD": votes_per_meas["PD"],
            "votes_GM": votes_per_meas["GM"],
            "votes_CAL": votes_per_meas["CAL"],
            "identity_ok": identity_ok,
        })

    print(
        f"\nDone.  {n_changed} cells updated.  "
        f"Identity now satisfied: {n_resolved} sites; "
        f"still off: {n_unresolved} sites."
    )

    log_path = ROOT / "outputs" / "cell_recheck_log.json"
    with log_path.open("w", encoding="utf-8") as fh:
        json.dump(log_rows, fh, indent=2, default=str)
    print(f"Log: {log_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
