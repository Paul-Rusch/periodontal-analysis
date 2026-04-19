#!/usr/bin/env python3
"""Render the periodontal recommendation report for ``patient_01``.

Writes:
* ``outputs/recommendation_patient_01.md``  -- human-readable report
* ``outputs/recommendation_patient_01.json`` -- structured Evidence
  list (audit trail / future web view input)

Usage::

    python scripts/render_recommendation.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analysis import (  # noqa: E402
    ToothFocus,
    load_patient,
    report,
)


ROOT = Path(__file__).resolve().parent.parent
MD_OUT = ROOT / "outputs" / "recommendation_patient_01.md"
JSON_OUT = ROOT / "outputs" / "recommendation_patient_01.json"


def main() -> None:
    patient = load_patient("patient_01")
    rep = report(
        patient,
        focus_teeth=(
            ToothFocus(
                tooth_number=11,
                question=(
                    "maxillary left canine -- pinhole surgical technique "
                    "(PST) was recommended at the most recent visit to "
                    "address \"progressing\" recession.  Is the chart "
                    "data consistent with active progression at this "
                    "time, and how does this tooth's recession compare "
                    "to teeth 21 and 22 prior to their successful PST?"
                ),
            ),
        ),
    )
    rep.write(MD_OUT, json_path=JSON_OUT)
    print(f"wrote {MD_OUT}")
    print(f"wrote {JSON_OUT}")


if __name__ == "__main__":
    main()
