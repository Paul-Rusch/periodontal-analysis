"""Shared pytest fixtures.

Adds the repo root to ``sys.path`` so tests can ``from analysis import ...``
without requiring an editable install, and provides a session-scoped
``patient_01`` fixture so the load-from-CSV cost is paid once per
``pytest`` invocation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analysis import Patient, load_patient  # noqa: E402


@pytest.fixture(scope="session")
def patient_01() -> Patient:
    """Real ``patient_01`` loaded from
    ``outputs/periodontal_readings.csv`` plus the three Phase 0
    manifests.  Session-scoped to amortise the load cost.

    Skipped if the readings CSV isn't present locally -- the public
    repo gitignores all personal data per ``.gitignore``, so a fresh
    clone of the repo without the data files will simply skip these
    tests.
    """
    csv_path = ROOT / "outputs" / "periodontal_readings.csv"
    if not csv_path.exists():
        pytest.skip(
            "outputs/periodontal_readings.csv not present "
            "(personal data file is gitignored from the public repo)"
        )
    return load_patient("patient_01")
