# Agent guidance for `gummies_iii`

Read these in order:

1. [`README.md`](README.md) -- project overview, repository layout,
   workflows for adding new exams / patients / history events /
   metrics.
2. [`PERIODONTAL_INTERPRETATION.md`](PERIODONTAL_INTERPRETATION.md)
   -- the clinical spec.  Every threshold the analytical layer
   enforces is cited here.  Treat as authoritative.
3. [`analysis/README.md`](analysis/README.md) -- module-by-module
   guide for the analytical layer + the hard rules the package
   contracts on.

## What this project is

Two halves separated by one validator-locked CSV:

| half | directories | status |
| --- | --- | --- |
| OCR pipeline | `pdf_scans/`, `crops/`, `tools/`, `outputs/json/`, `outputs/cell_recheck_log.json`, `manifests/periodontal_*_manifest.csv`, `outputs/periodontal_readings.csv` | **LOCKED.** Do not modify scripts in `tools/`, files in `pdf_scans/` / `crops/` / `outputs/json/`, or the CSV schema.  The validator [`tools/validate_periodontal_readings.py`](tools/validate_periodontal_readings.py) must continue to report `840 / 840 = 100.0 %`. |
| Analytical layer + recommendation engine | `analysis/`, `scripts/`, `manifests/{patient_metadata,chart_metadata,patient_history_events}.csv`, `outputs/recommendation_patient_*.{md,json}` | **Active.** New metrics, new patients, new clinical questions land here. |

## Hard invariants (do not break)

- `tools/validate_periodontal_readings.py` reports `840 / 840 = 100 %`.
- The CSV schema (`outputs/periodontal_readings.csv` columns) is the
  contract between the two halves.  Add columns in
  `manifests/chart_metadata.csv` (point-in-time per-exam) or
  `manifests/patient_history_events.csv` (dated events) instead.
- `analysis/normalize.py` is the only module that consumes the raw
  CSV.
- `MGJ = 0` in the CSV is "not recorded" and is normalized to
  `None`; mucogingival metrics return
  `Evidence(status=not_assessable, missing_inputs=['MGJ'])`.
- `GM = 0` in the CSV is meaningful (gingival margin at CEJ) and is
  preserved as `GM(mm=0)`.
- Sort by `ExamKey` (or `exam_index` / `exam_date`), never by
  `chart_id` (chart_id is anti-chronological: chart 5 = baseline,
  chart 1 = most recent).
- Per-site delta joins use the full key
  `(patient_id, arch, surface, tooth_number, site)`; the `SiteKey`
  dataclass is the single source of truth.
- `Stage` uses `max_interdental_CAL` (distal / mesial sites only),
  not `max(CAL)` over all sites.
- `Grade` is always reported as `EvidenceStatus.PROVISIONAL` with the
  explicit `"projected from {window:.2f}-year window"` assumption.
- Every classifier / flag-style metric / recommendation returns an
  `Evidence` object.  `PROVISIONAL` Evidence must list at least one
  `assumption` or `missing_input`; `NOT_ASSESSABLE` must list at
  least one `missing_input` (enforced in `Evidence.__post_init__`).
- `analysis/recommend.py` cannot embed clinical thresholds.  Numbers
  come from `Evidence.value` and `Evidence.trigger_measurements`;
  threshold rule text from `Evidence.threshold_crossed`; status
  badges from `Evidence.status`.

## Common workflows

See README.md "Workflows for future agents" section for the full
recipes.  In short:

| task | edit | run |
| --- | --- | --- |
| Add a new exam (chart 6) for an existing patient | `manifests/periodontal_*_manifest.csv` (geometry), `manifests/chart_metadata.csv` (one row), drop new scan into `pdf_scans/` | OCR pipeline (steps 1-5 of `tools/`), then `python scripts/render_recommendation.py` |
| Enrich existing data (e.g. fill in MGJ readings) | `outputs/json/*_MGJ.json` directly, or re-OCR with updated prompt | `python tools/read_periodontal_rows.py --passes 1` -> validator -> renderer |
| Add a new patient | `manifests/patient_metadata.csv`, `manifests/chart_metadata.csv`, `manifests/patient_history_events.csv` (all + one row each minimum) | OCR pipeline for the new charts; then `load_patient("patient_<NN>")` |
| Add a new history event (procedure, condition, medication) | append rows to `manifests/patient_history_events.csv` (one row per affected tooth for multi-tooth procedures) | `python scripts/render_recommendation.py` |
| Add a new metric / classifier | new function in `analysis/{site,tooth,mouth,classify,longitudinal}.py` returning Evidence; cite via `analysis/citations.py`; export in `analysis/__init__.py.__all__` | `python scripts/demo_patient_01.py` to spot-check |
| Address a new patient-specific clinical question | pass a `ToothFocus(tooth_number=N, question="...")` into `analysis.report(...)` from `scripts/render_recommendation.py` | `python scripts/render_recommendation.py` |

## Public API

`from analysis import ...` -- everything in
[`analysis/__init__.py`](analysis/__init__.py) `__all__`.  See
README.md "Public API" for the catalog.

## Outputs you should regenerate after any change

```bash
python tools/validate_periodontal_readings.py | head -3
python scripts/render_recommendation.py
```
