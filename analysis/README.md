# `analysis/` -- module-by-module guide

Read [`../README.md`](../README.md) first for the project overview
and the OCR / analysis split.  Read
[`../PERIODONTAL_INTERPRETATION.md`](../PERIODONTAL_INTERPRETATION.md)
for the clinical spec that every threshold and rule in this package
cites.

## Layered architecture

Modules are listed in dependency order (bottom-up).  Higher layers
consume only the public API of lower layers; in particular, the raw
CSV is consumed **only** by `normalize.py`.  All public names are
re-exported from [`__init__.py`](__init__.py) and listed in
`__all__`.

| module | role | key exports |
| --- | --- | --- |
| `types.py` | string enums + tooth/sextant constants | `Arch`, `Surface`, `SitePosition`, `Measurement`, `ARCHES`, `SURFACES`, `SITE_POSITIONS`, `MEASUREMENTS`, `INTERDENTAL_SITES`, `TOOTH_NUMBERS_BY_ARCH` |
| `citations.py` | central registry of citation strings used by every Evidence | `SITE_PD_CLASS`, `TOOTH_AFFECTED`, `MOUTH_INTERDENTAL_CAL`, `LONGITUDINAL_GRADE`, `SOFT_TISSUE_INTERVENTION`, ... |
| `evidence.py` | `Evidence` dataclass + `EvidenceStatus` enum.  Every classifier / flag / recommendation in this package returns one of these. | `Evidence`, `EvidenceStatus` |
| `normalize.py` | typed measurement value objects (`PD`, `GM`, `CAL`, `MGJ`); the canonical CSV parser; `NormalizedSite` records keyed by `(ExamKey, SiteKey)`.  **The only module that reads the raw CSV.** | `PD`, `GM`, `CAL`, `MGJ`, `ExamKey`, `SiteKey`, `NormalizedSite`, `iter_normalized_sites`, `normalize_value` |
| `site.py` | `Site` -- one observation at one site.  PD bins, CAL bins, mucogingival rules.  Carries `caveats` populated by the loader (e.g. anterior-facial mouth-breathing bias). | `Site` |
| `tooth.py` | `Tooth` -- six sites of one tooth at one exam.  Per-tooth aggregates from sec 4 of the clinical spec; affected / deep flags; per-tooth prognosis floor. | `Tooth` |
| `mouth.py` | `ArchSurface` (42 sites, surface-stratified §5 metrics) and `Mouth` (168 sites; whole-mouth tile metrics; classification shims). | `ArchSurface`, `Mouth` |
| `exam.py` | `Exam` = `Mouth` + `ExamKey` + `ChartContext` (point-in-time chart-metadata).  Convenience pass-through accessors. | `Exam`, `ChartContext` |
| `patient.py` | `Patient` = ordered tuple of `Exam`s + `PatientMetadata` + `HistoryEvents`.  Demographic / longitudinal helpers. | `Patient`, `PatientMetadata`, `HistoryEvent`, `HistoryEvents` |
| `loader.py` | `load_patient(patient_id)` -- wires the CSV and all three Phase 0 manifests into a `Patient`.  Pre-bakes per-tooth and per-site caveats from the history events. | `load_patient` |
| `sextants.py` | PSR sextant geometry (`upper_right`, `upper_anterior`, ...). | `SEXTANT_LABELS`, `SEXTANT_TEETH` |
| `classify.py` | Phase 3 classifiers: AAP/EFP Stage, extent, CDC/AAP severity, PSR PD-floor, per-tooth prognosis floor.  All return `Evidence`. | `stage`, `extent`, `cdc_aap_severity`, `psr_pd_floor`, `prognosis_floor` |
| `longitudinal.py` | Phase 4 longitudinal layer: per-site deltas, treatment-response widget set, mouth-level trend series, AAP/EFP Grade A-C (always provisional), EFP S3 PD-only endpoint, tooth-loss tracking, recession trajectory, PST/graft treatment-response, soft-tissue intervention assessment. | `per_site_deltas`, `treatment_response`, `trend_series`, `grade`, `s3_pd_only_endpoint`, `tooth_loss_events`, `recession_trajectory`, `pst_or_graft_treatment_response`, `soft_tissue_intervention_assessment`, `SiteDelta` |
| `recommend.py` | Phase 5 pure markdown renderer over the `Evidence` produced by everything above.  No clinical thresholds in the source. | `report`, `RecommendationReport`, `ToothFocus` |

## Hard rules (don't break these)

1. **`normalize.py` is the only module that reads
   `outputs/periodontal_readings.csv`.**  Higher layers consume the
   typed `NormalizedSite` records.
2. **The CSV schema is locked.**  Extend in code or in
   `manifests/`; never add a column to the CSV itself.
3. **Sort by `ExamKey` (or `exam_index` / `exam_date`), never by
   `chart_id`.**  `chart_id` is anti-chronological in this dataset
   (chart 5 = baseline, chart 1 = most recent).  `ExamKey.__lt__`
   is correct by construction; rely on it.
4. **Per-site delta joins use the full key**
   `(patient_id, arch, surface, tooth_number, site)` -- the
   `SiteKey` dataclass is the single source of truth.  `measurement`
   is not part of the key because each `NormalizedSite` already
   bundles all four measurements.
5. **MGJ = 0 in the CSV is "not recorded", not "0 mm".**
   `normalize.py` translates it to `None`; never read raw MGJ.
6. **`GM = 0` in the CSV is meaningful** (gingival margin at the
   CEJ) and is preserved as `GM(mm=0)`.
7. **Stage uses `max_interdental_CAL`** (distal/mesial sites only --
   `INTERDENTAL_SITES` constant), not `max(CAL)` over all sites.
8. **AAP/EFP Grade A/B/C is always reported as `provisional`** with
   the explicit `"projected from {window:.2f}-year window"`
   assumption (the published thresholds are 5-year and the dataset
   window is shorter -- result scaled linearly).
9. **`PROVISIONAL` Evidence must list at least one `assumption` or
   `missing_input`; `NOT_ASSESSABLE` must list at least one
   `missing_input`.**  These contracts are enforced in
   `Evidence.__post_init__`.
10. **`recommend.py` cannot embed clinical thresholds.**  Numbers
    come from `Evidence.value` and `Evidence.trigger_measurements`;
    threshold rule text from `Evidence.threshold_crossed`; status
    badges from `Evidence.status`.

## Testing the package interactively

Both scripts live at the project root, not inside this package:

- [`scripts/demo_patient_01.py`](../scripts/demo_patient_01.py) --
  console-style end-to-end snapshot (per-tooth flowsheets,
  classifications across exams, treatment response, Grade, S3
  endpoint, trends, tooth-loss).
- [`scripts/render_recommendation.py`](../scripts/render_recommendation.py)
  -- writes the markdown + JSON recommendation report.

For one-off queries against a loaded `Patient`, see the worked
examples in the project README "Public API" section.
