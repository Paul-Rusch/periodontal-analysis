# gummies_iii — periodontal-chart OCR + analytical layer

> **Informational use only — not a medical device.** This software
> extracts probing-chart data and renders structured summaries that
> mirror the AAP/EFP 2018 clinical framework.  It is **not intended
> to diagnose disease, replace a periodontist's clinical judgement,
> or drive surgical or treatment decisions on its own.**  Every
> classification it produces carries an explicit
> `provisional` / `not_assessable` status and a list of inputs the
> probing chart cannot speak to (radiographic bone loss, mobility,
> furcation, MGJ / KTW, intra-oral exam findings).  Always work with
> a licensed periodontist using the full clinical examination, not
> with the output of this report alone.  See
> [`LICENSE`](LICENSE) for the licence terms (MIT) and the
> warranty / liability disclaimer.

End-to-end periodontal-data project for one patient (`patient_01`):

1. **OCR pipeline** (`tools/`) extracts 3,360 individual probing
   measurements from five scanned paper periodontal-charting forms
   into a single tidy CSV — locked at `840 / 840 = 100.0 %` on the
   `CAL = PD + GM` identity.
2. **Analytical layer** (`analysis/`) reads that CSV plus three
   Phase 0 manifest files and exposes typed access at every
   aggregation level — `Site -> Tooth -> ArchSurface -> Mouth ->
   Exam -> Patient` — plus AAP/EFP staging and grading, CDC/AAP
   severity, PSR PD-floor codes, per-tooth prognosis floor,
   longitudinal trend / treatment-response analyses, recession
   trajectory, and soft-tissue-intervention assessment.  Every
   classification, threshold, and recommendation is the output of a
   structured `Evidence` object cited back to
   `PERIODONTAL_INTERPRETATION.md`.
3. **Recommendation engine** (`analysis/recommend.py`) renders the
   `Evidence` produced upstream into a markdown report (and a
   matching JSON audit trail) at
   `outputs/recommendation_patient_01.{md,json}`.

> The OCR side is **locked**: scripts in `tools/`, files in
> `pdf_scans/` / `crops/` / `outputs/json/`, and the schema of
> `outputs/periodontal_readings.csv` must not change.  The validator
> [`tools/validate_periodontal_readings.py`](tools/validate_periodontal_readings.py)
> must continue to report `840 / 840 = 100.0 %` after any future
> change.  The active development surface is everything under
> `analysis/`, `manifests/`, and `scripts/`.

## At a glance

```
                            (LOCKED)                                                     (ACTIVE)

  pdf_scans/*.jpg                                                  manifests/patient_metadata.csv
        |                                                          manifests/chart_metadata.csv
        | tools/ OCR pipeline (5 stages, see below)                manifests/patient_history_events.csv
        v                                                                       |
  outputs/periodontal_readings.csv  --[CSV schema is the contract]-->  analysis/ package
  outputs/json/<strip>.json (cache)                                             |
  outputs/cell_recheck_log.json                                                 v
                                                              outputs/recommendation_patient_01.md
                                                              outputs/recommendation_patient_01.json
```

The CSV schema is the contract between the two halves.  Adding a new
exam or enriching an existing one is described in the **Workflows for
future agents** section below.

## Quick start

```bash
. .venv/bin/activate                                # create with `python -m venv .venv` if needed
pip install -r requirements.txt

# render the full markdown recommendation report for patient_01
python scripts/render_recommendation.py
# wrote outputs/recommendation_patient_01.md
# wrote outputs/recommendation_patient_01.json

# console-style end-to-end demo (per-tooth flowsheet, classifications, deltas, grade)
python scripts/demo_patient_01.py

# always-pass invariant
python tools/validate_periodontal_readings.py | head -3
```

## Repository layout

```
pdf_scans/                          raw chart scans (5 jpgs)            -- LOCKED
crops/                              full-table crops (10 jpgs)          -- LOCKED
crops/rows/                         row strips + tooth-number headers   -- LOCKED
manifests/
  periodontal_crop_manifest.csv     drives table-level cropping         -- LOCKED (touch only when adding a new chart's geometry)
  periodontal_row_crop_manifest.csv drives row-strip slicing + OCR      -- LOCKED (touch only when adding a new chart's geometry)
  chart_metadata.csv                chart_id -> {patient_id, exam_date, point-in-time context}
  patient_metadata.csv              one row per patient: stable lifetime fields (DOB, sex, family hx, allergies)
  patient_history_events.csv        one row per dated event (medication, condition, smoking-period, dental-therapy, extraction, restoration)
tools/
  crop_periodontal_tables.py
  crop_periodontal_rows.py
  annotate_and_crop_periodontal_rows.py
  read_periodontal_rows.py          strip-level OCR + tidy CSV writer
  validate_periodontal_readings.py  the five sanity checks
  recheck_mismatch_cells.py         per-cell re-OCR for mismatched sites
  render_mismatch_cells.py          high-res visual renderer for any site
  render_ascii_chart.py             monospaced ASCII reproduction of every chart
  spot_check_periodontal_rows.py    strip + values-overlay visual checker
analysis/                           typed analytical layer + classification + longitudinal + recommendation
  README.md                         module-by-module guide
  __init__.py                       public re-exports (every public name listed in __all__)
  types.py
  citations.py
  evidence.py                       Evidence + EvidenceStatus
  normalize.py                      PD/GM/CAL/MGJ + iter_normalized_sites (the only CSV consumer)
  site.py / tooth.py / mouth.py     typed access layer
  exam.py / patient.py              ChartContext, Patient, HistoryEvents
  loader.py                         load_patient(patient_id)
  sextants.py                       PSR sextant geometry
  classify.py                       Stage, extent, CDC-AAP severity, PSR PD-floor, prognosis floor
  longitudinal.py                   deltas, treatment-response, trends, Grade, S3 endpoint, tooth-loss,
                                      recession_trajectory, pst_or_graft_treatment_response,
                                      soft_tissue_intervention_assessment
  recommend.py                      pure markdown renderer
scripts/
  demo_patient_01.py                console-style end-to-end demo
  render_recommendation.py          writes outputs/recommendation_patient_01.{md,json}
outputs/
  periodontal_readings.csv          THE OCR deliverable (3,360 rows; LOCKED schema)
  periodontal_readings_ascii.txt    chronological ASCII reproduction (oracle for sanity checks)
  json/                             cached per-strip OCR (80 files; LOCKED)
  spot_checks/                      strip + overlay images for visual review
  cell_recheck_log.json             audit trail of every cell-level fix
  recommendation_patient_01.md      renderer output (regeneratable)
  recommendation_patient_01.json    structured Evidence audit trail (regeneratable)
PERIODONTAL_INTERPRETATION.md       clinical spec.  Every threshold the analytical layer enforces is cited here.
.env                                OPENAI_API_KEY (gitignored; only needed to re-OCR, not to render)
requirements.txt                    openai, python-dotenv, Pillow, pydantic
```

## OCR-pipeline final output (locked)

`outputs/periodontal_readings.csv` — 3,360 rows, one per
`(chart, arch, surface, measurement, tooth, site)`.

Columns:

| column | type | values |
| --- | --- | --- |
| `patient_id` | str | patient identifier (currently a single patient: `patient_01`); joined from `manifests/chart_metadata.csv` |
| `chart_id` | int | source-chart identifier (1..5); tied to filenames and the JSON cache. Note: chart_id is *anti-chronological* — chart 5 is the baseline, chart 1 is the most recent — use `exam_index` for time-series logic, not `chart_id` |
| `exam_date` | date (ISO `YYYY-MM-DD`) | exam date for this chart |
| `exam_index` | int | per-patient chronological exam number (1 = baseline, ascending); derived from `exam_date` |
| `arch` | str | `maxillary` / `mandibular` |
| `surface` | str | `facial` / `lingual` |
| `measurement` | str | `PD` / `GM` / `CAL` / `MGJ` |
| `tooth_number` | int | universal-numbering tooth (2..15 maxillary, 18..31 mandibular; wisdom teeth excluded) |
| `site` | str | `distal` / `central` / `mesial` (per-tooth labels rotate at the midline — see "Site labels" below) |
| `value` | int | measurement in mm; `0` for blank GM / MGJ |

The five charts are five sequential periodontal-maintenance exams of one
patient; chart 5 (2024-06-17) is the baseline and chart 1 (2026-02-09) is
the most recent.  Time-series queries should sort by `exam_date` (or the
equivalent `exam_index`).

**Quality (after the full pipeline):**

```
[1] Cardinality:  3,360 rows
[2] CAL = PD + GM:  840 / 840 = 100.0% match
[3] Range sanity:  0 out-of-range, 0 unexpected blanks
[4] GM blank-rate: 35–41 of 42 sites blank/0 across all 20 GM rows
[5] Tooth-number ordering: OK across all 10 (chart, arch) pairs
```

## Pipeline overview

```
pdf_scans/*.jpg                   five raw scans
        |
        |  (1) crop full periodontal table out of each scan
        v
crops/periodontal_charting_NN_{maxillary,mandibular}.jpg
        |
        |  (2) deskew, draw tooth-boundary + inter-site annotations,
        |      slice into one strip per measurement row
        v
crops/rows/periodontal_charting_NN_{arch}_{surface}_{PD,GM,CAL,MGJ}.jpg
crops/rows/periodontal_charting_NN_{arch}_TEETH.jpg                  (reference only)
        |
        |  (3) per-strip OCR via gpt-4.1 (tile composite + structured output)
        v
outputs/json/chart_NN_{arch}_{surface}_{measurement}.json
        |
        |  (4) tidy long-format CSV
        v
outputs/periodontal_readings.csv  (initial)
        |
        |  (5) validator: per-strip cardinality, CAL = PD + GM identity,
        |      range sanity, GM blank-rate, tooth-number ordering
        v
~90 sites where CAL ≠ PD + GM
        |
        |  (6) per-mismatched-site cell-level re-OCR
        |      (single isolated cells at 6× upscale; near-perfect)
        |      + 2 hand-fixes for residual stubborn cells
        v
outputs/periodontal_readings.csv  (final, 100% identity match)
```

## Step-by-step

### 1. Table-level crops

`tools/crop_periodontal_tables.py` reads
`manifests/periodontal_crop_manifest.csv` and crops a fixed rectangular
region out of each raw scan to isolate the periodontal table.  Outputs
land in `crops/`, one maxillary and one mandibular crop per chart
(10 files total).

### 2. Row strips with deterministic column annotations

`tools/annotate_and_crop_periodontal_rows.py` is the calibration step.
For each table crop it:

1. Deskews the crop using a per-table angle stored in the manifest.
2. Uses hardcoded, per-table digit-triplet x-centers (`TOOTH_TRIPLETS`)
   to compute the 15 tooth-boundary x-positions and the 28 inter-site
   tick positions.
3. Draws those boundaries and ticks onto the deskewed image as
   2-px-wide dark vertical lines (between teeth, full chart height) and
   16-px medium-gray ticks (within each tooth, top + bottom edges).
4. Slices the annotated image into 8 horizontal strips per table — one
   for each measurement (PD, GM, CAL, MGJ) on each surface (facial,
   lingual).  Plus a tooth-number reference header strip.

Output: `crops/rows/`, 5 charts × 2 arches × (8 measurement strips +
1 header strip) = 90 JPG files.  Each measurement strip is
`5710 × ~56 px` and contains exactly 14 teeth × 3 sites = 42 site
positions.

This step is the key insight that made the rest of the project work.
The original attempt OCR'd full tables in one shot and failed because
the model couldn't reliably count which cells were blank vs. populated
on the GM and MGJ rows.  Annotating with explicit column structure
turns the OCR question into "what value is in cell N?" rather than
"how many cells in this row?".

The slicing tools and their manifest are the source of truth for
column structure and are not modified by anything downstream.

### 3. Strip-level OCR

`tools/read_periodontal_rows.py` drives the OCR.  For every entry in
`manifests/periodontal_row_crop_manifest.csv` (80 measurement strips):

1. Loads the strip and uses `TOOTH_TRIPLETS`-derived boundaries to slice
   it into 14 single-tooth crops.
2. Upscales each tooth crop (2× horizontal, 4× vertical) and stacks
   them vertically into a single composite image (~750 × 3,300 px) with
   a "01"–"14" tooth-row label on the left.  Stacking turns the strip's
   extreme aspect ratio (5710 × 56) into something the vision model can
   reliably reason about.
3. Sends the composite to `gpt-4.1` via the OpenAI Responses API with
   a strict pydantic schema: `list[ToothReading]` of length exactly 14,
   each with `list[Optional[int]]` of length exactly 3.  `null` means
   blank.
4. Caches the parsed result to `outputs/json/<strip>.json`.
5. Expands the cached values into long-format rows and writes
   `outputs/periodontal_readings.csv`.

Site labels are assigned per the universal-numbering convention:

* For teeth on the patient's right side (the left half of each strip,
  positions 1–7) sites read **distal, central, mesial** left-to-right.
* For teeth on the patient's left side (the right half, positions 8–14)
  sites read **mesial, central, distal** left-to-right.

This matches the source chart's `D C M | M C D` site headers.

GM and MGJ blanks are recorded as `0` in the CSV (blank means "gingival
margin at the CEJ" / "MGJ not measured" — i.e. literal zero).  PD and
CAL blanks would be unusual; the validator flags any.

### 4. Validation

`tools/validate_periodontal_readings.py` runs five checks against the
CSV.  The most discriminating is the **CAL identity**:

> `CAL = PD + GM` (with `GM = 0` when blank)

`GM` on these charts is signed-recession (positive = gingival margin
apical to the CEJ, i.e. recession), so the standard relationship is
`CAL = PD + GM`, **not** `CAL = PD - GM`.  This was confirmed
empirically on the first pass (the `-` variant matched 53% vs the `+`
variant at 89%).

A passing CAL identity requires PD, GM, and CAL at every site to all
be read correctly — three independent OCR reads must all be right.

### 5. Per-cell re-OCR for mismatches

The first strip-level pass scored 89% on the CAL identity.  The
remaining ~10% of mismatches were almost all single-digit OCR errors
caused by genuine ambiguity in this dot-matrix font (e.g. an open-top
"4" reading as a "7", or a "5" reading as a "3").  Re-running the
strip OCR (`--passes 3` ensemble) didn't help: errors were systematic,
not stochastic.

**The fix** (`tools/recheck_mismatch_cells.py`) is to OCR each
problematic cell *in isolation*:

1. Validator → find every site where `CAL ≠ PD + GM` (the validator
   prints them; the cell-recheck tool re-derives the same list from the
   CSV).
2. For each mismatched site, crop the PD, GM, and CAL cells from their
   respective row strips using the tooth and inter-site boundary
   geometry (so each crop is exactly one cell), upscale 6×, and send
   each cell individually to `gpt-4.1` 3 times with majority vote.
3. For every cell whose new vote differs from the cached value, patch
   `outputs/json/<strip>.json` in place (with a `manual_overrides`
   audit entry recording the before/after) and append to
   `outputs/cell_recheck_log.json`.

Single-cell OCR is essentially perfect because the source of error
(the 5710-px-wide aspect ratio of a row strip) is gone.  This pass
resolved 88 of 90 mismatches automatically.

### 6. Manual fix for the residual stubborn cells

Two sites still failed after cell-recheck — the cell OCR was reading
an obvious "4" digit as "14" and "7" respectively (the dot-matrix
glyph really is ambiguous in isolation for those two cells).
`tools/render_mismatch_cells.py` produces side-by-side high-resolution
renderings of the PD / GM / CAL crops at any failing site.  Looking at
the rendered images for those two sites makes the truth obvious; both
were patched directly in `outputs/json/chart_01_mandibular_lingual_CAL.json`
(visible in the file's `manual_overrides` array).

After this, the validator reports `840 / 840 = 100.0%` on the CAL
identity.

## Reproducing the OCR pipeline from scratch

The artefacts are all checked in, so a clean rebuild only needs an API
key and the scans:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
echo 'OPENAI_API_KEY=sk-...' > .env

# (1) table crops -> crops/*.jpg
python tools/crop_periodontal_tables.py

# (2) row strips with annotations -> crops/rows/*.jpg
python tools/annotate_and_crop_periodontal_rows.py

# (3) + (4) per-strip OCR + tidy CSV
rm -rf outputs/json outputs/periodontal_readings.csv
python tools/read_periodontal_rows.py

# (5) validate
python tools/validate_periodontal_readings.py

# (6) cell-level re-OCR until validator reports 100% identity match
#     (loop: re-validate after each pass)
while true; do
  N=$(python tools/validate_periodontal_readings.py 2>&1 | grep "CAL = PD + GM" | grep -oE '[0-9]+ / [0-9]+' | head -1)
  echo "current: $N"
  python tools/recheck_mismatch_cells.py
  python tools/read_periodontal_rows.py --passes 1   # rebuild CSV from cache
  python tools/validate_periodontal_readings.py | head -3
done
# stop the loop once "CAL = PD + GM: 840/840" or progress stalls;
# any residual stubborn cells get hand-patched in outputs/json/
```

Cost note: the strip-level OCR is 80 API calls.  Each cell-recheck
mismatch is 9 calls (3 measurements × 3 votes).  With ~90 mismatches
that is ~810 cell calls — still well under a dollar at gpt-4.1 image
pricing.

## Useful audit/inspection commands

```bash
# Overlay the OCR'd values under their cells for visual inspection:
python tools/spot_check_periodontal_rows.py            # default 8-strip sample
python tools/spot_check_periodontal_rows.py mismatches # one per failing strip
python tools/spot_check_periodontal_rows.py all        # all 80 strips

# High-resolution PD/GM/CAL comparison for every site failing the
# CAL identity (writes outputs/mismatch_review/):
python tools/render_mismatch_cells.py

# Monospaced ASCII reproduction of every chart, with surface stacking and
# per-tooth site order matching the source.  Open the resulting .txt file
# in any monospaced editor side-by-side with the corresponding
# crops/rows/*.jpg strips for cell-by-cell review:
python tools/render_ascii_chart.py                  # all 5 charts
python tools/render_ascii_chart.py --chart 3        # just chart 3
```

---

# Analytical layer (`analysis/`)

> The OCR pipeline above is locked.  Everything from here on is the
> active development surface.  See [`analysis/README.md`](analysis/README.md)
> for a module-by-module guide; see
> [`PERIODONTAL_INTERPRETATION.md`](PERIODONTAL_INTERPRETATION.md) for
> the clinical spec that every metric, threshold, and classification
> in this layer cites.

## Architecture

```
                 manifests/{patient_metadata,chart_metadata,patient_history_events}.csv
                              |
                              v
  outputs/periodontal_readings.csv  --(analysis/normalize.py: the *only* CSV consumer)-->
                              |
                              v
            NormalizedSite (PD, GM, CAL, MGJ all typed; MGJ=0 -> None; GM=0 -> at-CEJ)
                              |
                              v
   Site -> Tooth -> ArchSurface -> Mouth -> Exam -> Patient        (analysis/site,tooth,mouth,exam,patient.py)
                              |
                              v
             Phase 2 metrics (sec 3, 4, 5, 10) returning Evidence
                              |
                              v
      Phase 3 classifiers     +     Phase 4 longitudinal layer
        (Stage, extent,            (deltas, treatment-response,
         CDC/AAP, PSR,              Grade, S3 endpoint, tooth-loss,
         prognosis floor)           recession trajectory,
                                    PST/graft response,
                                    soft-tissue intervention)
                              |
                              v
      analysis/recommend.py: pure markdown renderer over the Evidence stream
                              |
                              v
        outputs/recommendation_patient_<id>.{md,json}
```

Every classifier, flag-style metric, and recommendation returns an
[`Evidence`](analysis/evidence.py) object carrying `rule_id`, `scope`,
`status` (∈ {`supported`, `provisional`, `not_assessable`}),
`threshold_crossed`, `trigger_measurements`, `missing_inputs`,
`assumptions`, `citation`, and `value`.  The renderer is a pure
function of these objects -- no clinical thresholds appear in
`recommend.py` source.

## Public API

The package exposes the following from `from analysis import ...`
(every public name is in `analysis.__all__`):

- **Loader / orchestration:** `load_patient`, `iter_normalized_sites`,
  `normalize_value`.
- **Core types:** `Patient`, `PatientMetadata`, `HistoryEvent`,
  `HistoryEvents`, `Exam`, `ChartContext`, `Mouth`, `ArchSurface`,
  `Tooth`, `Site`, `ExamKey`, `SiteKey`, `NormalizedSite`,
  `SiteDelta`.
- **Measurement value objects:** `PD`, `GM`, `CAL`, `MGJ`.
- **Evidence:** `Evidence`, `EvidenceStatus`.
- **Constants:** `ARCHES`, `SURFACES`, `SITE_POSITIONS`,
  `MEASUREMENTS`, `INTERDENTAL_SITES`, `TOOTH_NUMBERS_BY_ARCH`.
- **Type aliases:** `Arch`, `Surface`, `SitePosition`, `Measurement`.
- **Classifiers (Phase 3):** `stage`, `extent`, `cdc_aap_severity`,
  `psr_pd_floor`, `prognosis_floor`.
- **Longitudinal (Phase 4):** `per_site_deltas`,
  `treatment_response`, `trend_series`, `grade`,
  `s3_pd_only_endpoint`, `tooth_loss_events`,
  `recession_trajectory`, `pst_or_graft_treatment_response`,
  `soft_tissue_intervention_assessment`.
- **Recommendation (Phase 5):** `report`, `RecommendationReport`,
  `ToothFocus`.

Idiomatic usage:

```python
from analysis import load_patient, ToothFocus, report

p = load_patient("patient_01")

# Isolated views
p.exam(1).tooth(14).max_PD                     # 7
p.exam(1).tooth(14).is_deep().value            # True (Evidence)
p.most_recent.tooth(8).caveats                 # auto-attached crown caveat

# Integrative views
p.most_recent.mouth.stage().value              # 'III'
p.most_recent.mouth.cdc_aap_severity().value   # 'moderate'
p.grade(label="full_window").value             # 'C' (always provisional)
p.treatment_response(from_exam=1, to_exam=2)   # SRP response widgets

# Render the markdown report
rep = report(
    p,
    focus_teeth=(ToothFocus(tooth_number=11, question="..."),),
)
rep.write(Path("outputs/recommendation_patient_01.md"))
```

## The recommendation engine (`analysis/recommend.py`)

The renderer composes `Evidence` from the `analysis/` package into a
markdown report with sections:

1. Patient demographics + Phase 0 history
2. Headline classification (Stage, extent, CDC/AAP severity, Grade --
   full window and post-SRP-only)
3. Clinical questions addressed (driven by `ToothFocus` parameters)
4. Treatment history outcomes (SRP response + per-tooth PST / graft
   effectiveness)
5. Mouth-level trajectory + EFP S3 PD-only endpoint per exam
6. Where to focus next visit (per-tooth prognosis floor sorted
   worst-first)
7. Soft-tissue intervention -- candidates ranked by `max_recession`
8. Caveats, missing inputs, and what would tighten this report
9. Audit trail of every `Evidence` rendered

Outputs land at:
- [`outputs/recommendation_patient_01.md`](outputs/recommendation_patient_01.md)
  -- human-readable report (~190 lines, ~96 Evidence rendered).
- [`outputs/recommendation_patient_01.json`](outputs/recommendation_patient_01.json)
  -- structured Evidence audit trail for any future tooling
  (web view, dashboard, follow-up agent).

Hard renderer rule: **no clinical thresholds appear as literal
numbers in `recommend.py`.**  Numbers come from `Evidence.value` and
`Evidence.trigger_measurements`; status badges from `Evidence.status`;
threshold rule text from `Evidence.threshold_crossed`.  If a future
agent finds itself about to write `if max_PD >= ...` in
`recommend.py`, that's a code-review reject -- the threshold belongs
in `analysis/classify.py` or `analysis/longitudinal.py`.

# Phase 0 manifests

The paper charts capture probing measurements but not the systemic /
behavioural inputs a periodontist uses to interpret them.  Three
manifest files persist that context, joined into the analytical
layer at load time.

| file | one row per | what it holds | when to extend |
| --- | --- | --- | --- |
| [`manifests/patient_metadata.csv`](manifests/patient_metadata.csv) | patient | DOB, sex, family history, allergies, lifetime notes | new patient, or stable demographic correction |
| [`manifests/chart_metadata.csv`](manifests/chart_metadata.csv) | chart (= one exam) | `chart_id`, `exam_date`, `patient_id`, `hba1c_at_exam`, `pregnant_at_exam`, `systemic_antibiotic_within_4w`, `notes` | new exam, or new point-in-time observation for an existing exam |
| [`manifests/patient_history_events.csv`](manifests/patient_history_events.csv) | dated event | `patient_id`, `event_type` (`condition` / `medication` / `smoking-period` / `dental-therapy` / `extraction` / `restoration`), `event_subtype`, `start_date`, `end_date`, `*_uncertain` flags, `tooth_number`, `details_json` | any dated transition (new procedure, smoking change, condition diagnosis, restoration on a tooth) |

`details_json` is parsed as structured JSON by
[`analysis/loader.py`](analysis/loader.py); embed any extra
event-type-specific fields there.  `tooth_number` is normalised to a
top-level column for easy per-tooth join (`Patient.history.for_tooth(N)`).

The OCR pipeline also depends on `manifests/periodontal_crop_manifest.csv`
and `manifests/periodontal_row_crop_manifest.csv`; those are part of
the LOCKED OCR side and are touched only when adding a new chart's
geometry (see workflow below).

# Workflows for future agents

After any of these workflows: re-run the validator (must remain
`840 / 840 = 100.0 %` plus whatever new sites a new chart adds), then
re-run [`scripts/render_recommendation.py`](scripts/render_recommendation.py)
to regenerate the markdown report.

## 1. Add a new periodontal exam (chart 6) for an existing patient

1. Drop the new scan into [`pdf_scans/`](pdf_scans/) following the
   existing naming convention (`Periodontal charting 6 of 6.jpg` etc.).
2. Add a new row to
   [`manifests/periodontal_crop_manifest.csv`](manifests/periodontal_crop_manifest.csv)
   and a corresponding pair of new rows (one per arch) to
   [`manifests/periodontal_row_crop_manifest.csv`](manifests/periodontal_row_crop_manifest.csv).
   Tune the per-table angle / TOOTH_TRIPLETS using the same
   calibration approach used for charts 1-5 (see step 2 of the OCR
   pipeline above).
3. Append one row to
   [`manifests/chart_metadata.csv`](manifests/chart_metadata.csv) with
   the new `chart_id`, `exam_date`, and `patient_id`.  Leave the
   point-in-time columns blank if not known; fill them in if you have
   an `hba1c_at_exam` reading or pregnancy / antibiotic flag for the
   new exam.
4. Run the OCR pipeline for the new chart:
   ```bash
   python tools/crop_periodontal_tables.py
   python tools/annotate_and_crop_periodontal_rows.py
   python tools/read_periodontal_rows.py
   python tools/validate_periodontal_readings.py        # must still report 100% identity
   python tools/recheck_mismatch_cells.py               # if any mismatches, loop until clean
   ```
5. Re-render: `python scripts/render_recommendation.py`.
   `analysis.normalize.iter_normalized_sites` will pick up the new
   chart automatically; `ExamKey`-sorted access guarantees correct
   chronological ordering.

## 2. Enrich existing data (e.g. fill in MGJ readings)

Currently every MGJ value in the CSV is `0`, normalized to `None` by
[`analysis/normalize.py`](analysis/normalize.py); every mucogingival
metric returns `Evidence(status=not_assessable, missing_inputs=['MGJ'])`.
To unlock those rules:

1. Add real MGJ readings to the source charts (or at sites of
   clinical interest).
2. Either re-OCR with the MGJ row prompt updated, or hand-patch the
   relevant cells in [`outputs/json/`](outputs/json/) `*_MGJ.json`.
3. Run [`tools/read_periodontal_rows.py --passes 1`](tools/read_periodontal_rows.py)
   to rebuild the CSV from cache, then the validator (still 100%),
   then the recommendation renderer.  The mucogingival rules
   (`Site.mucogingival_breach`, `Site.ktw`,
   `Tooth.min_KTW_tooth`, `Mouth.n_sites_mucogingival_breach`) flip
   from `not_assessable` to `supported` for every site whose MGJ now
   has a real value.

The same pattern applies to filling in any future `hba1c_at_exam` or
other `chart_metadata.csv` extension column -- no code change needed,
just data.

## 3. Add a new patient

The package is multi-patient by construction (everything filters on
`patient_id`).

1. Append a row to
   [`manifests/patient_metadata.csv`](manifests/patient_metadata.csv).
2. Add this patient's chart rows to
   [`manifests/chart_metadata.csv`](manifests/chart_metadata.csv)
   alongside `patient_01`'s, with their own `patient_id`.
3. Add any history events to
   [`manifests/patient_history_events.csv`](manifests/patient_history_events.csv).
4. Run the OCR pipeline for the new patient's charts.  The CSV
   already carries `patient_id` so multi-patient rows coexist
   peacefully.
5. `load_patient("patient_<NN>")` works.

## 4. Add a new history event

Append one row per event to
[`manifests/patient_history_events.csv`](manifests/patient_history_events.csv);
re-render.  For multi-tooth procedures (e.g. PST on two adjacent
teeth), use one row per tooth so the per-tooth join
(`Patient.history.for_tooth(N)`) finds the event from either side --
the existing PST-on-21-and-22 event is the worked example.

## 5. Add a new metric, classifier, or recommendation rule

1. Decide which level it lives at: site / tooth / mouth /
   patient-longitudinal.
2. Add a function in the appropriate module
   ([`site.py`](analysis/site.py), [`tooth.py`](analysis/tooth.py),
   [`mouth.py`](analysis/mouth.py),
   [`classify.py`](analysis/classify.py),
   [`longitudinal.py`](analysis/longitudinal.py)).  Return an
   `Evidence` object for any flag-style or classification output;
   bare numbers are fine for pure aggregates.
3. Add a citation string to
   [`analysis/citations.py`](analysis/citations.py) and reference it
   from the new function.
4. Add the import to [`analysis/__init__.py`](analysis/__init__.py)
   `__all__` so it appears in the public API.
5. If the metric should appear in the markdown report, add a render
   call inside the appropriate section of
   [`analysis/recommend.py`](analysis/recommend.py) -- composition
   only, no clinical thresholds.

## 6. Address a new patient-specific clinical question in the report

Pass a `ToothFocus(tooth_number=N, question="...")` into
`analysis.report(...)` from
[`scripts/render_recommendation.py`](scripts/render_recommendation.py).
The renderer will surface a dedicated subsection at the top of the
report containing current state, recession trajectory, comparative
context (other teeth on this patient that received soft-tissue
procedures), and the soft-tissue intervention assessment.

# Known limitations and missing inputs

Documented in detail in
[`PERIODONTAL_INTERPRETATION.md`](PERIODONTAL_INTERPRETATION.md) sec 1
("What we deliberately do *not* have"), sec 6 ("Stage IV upgrade
inputs"), and sec 13 ("Recipes for analyses that require *extra*
inputs").  Summary of what would unlock additional rules if added:

| input | adding this would unlock |
| --- | --- |
| **MGJ** at any site | every mucogingival rule for that site (`KTW`, `mucogingival_breach`); intervention assessment moves from `monitor` to a tightened recommendation |
| **BOP** per site | true periodontal-health-vs-gingivitis classification; full EFP S3 endpoint (we run PD-only); PSR codes 1 / 2 differentiation |
| **plaque score** | oral-hygiene metric; combined-risk inputs |
| **mobility** (Miller class) | Stage IV upgrade input; full McGuire-Nunn / Kwok-Caton / MMPPI prognosis |
| **furcation** class | Stage III/IV complexity; full prognosis frameworks |
| **radiographic bone loss** | direct Stage I-IV input (today driven by CAL alone); full prognosis frameworks |
| **HbA1c** at exam | AAP/EFP Grade C modifier (currently in `chart_metadata.csv` schema but blank for `patient_01`) |
| **smoking pack-years (current)** | AAP/EFP Grade C modifier (currently always 0 -- patient is former smoker quit > 10 y) |

The analytical layer is wired so that adding any of these inputs
later -- to manifests, or to a new column on the CSV, or to a new
event type -- propagates through to the report without code changes
beyond the affected metric / classifier function.
