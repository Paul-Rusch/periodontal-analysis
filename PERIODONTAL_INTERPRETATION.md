# Periodontal data interpretation guide

This document is the clinical backbone for any analytical tool, visualisation,
or recommendation engine built on top of `outputs/periodontal_readings.csv`.
It defines:

1. What each measurement in the CSV means clinically.
2. How site-level values aggregate to per-tooth, per-arch, and whole-mouth
   indicators.
3. Which periodontal classifications, severity scores, and prognosis frameworks
   are supported by what we have — and which require data we do not have.
4. Concrete pseudocode + threshold tables for every metric a dashboard,
   prognosis tool, or recommendation engine might compute.
5. Visualisation conventions (color bins, glyphs, layout) that match what
   clinicians expect from commercial periodontal charting software.

All clinical thresholds and definitions are anchored in the **AAP/EFP 2018
World Workshop classification of periodontal diseases and conditions** and
related primary periodontology guidance (sources cited at the end). The
interpretive framing is what a periodontist would apply when reading these
charts.

---

## 1. The data we have

`outputs/periodontal_readings.csv` is a tidy long-format table with 3,360 rows
covering 5 patient charts × 2 arches × 2 surfaces × 4 measurements ×
14 teeth × 3 sites (wisdom teeth excluded, blank GM/MGJ recorded as 0).

| column | clinical meaning |
| --- | --- |
| `patient_id` | patient identifier; currently a single patient (`patient_01`) |
| `chart_id` | source-chart identifier (1–5); tied to filenames and the JSON cache. **`chart_id` is anti-chronological** (chart 5 is the baseline, chart 1 is the most recent), so always use `exam_index` or `exam_date` for time-series logic, not `chart_id` |
| `exam_date` | date the exam was performed, ISO `YYYY-MM-DD`, joined from `manifests/chart_metadata.csv` |
| `exam_index` | per-patient chronological exam number (1 = baseline, ascending); derived from `exam_date` |
| `arch` | `maxillary` (upper) or `mandibular` (lower) |
| `surface` | `facial` (cheek/lip side) or `lingual` (tongue/palate side) |
| `measurement` | `PD`, `GM`, `CAL`, or `MGJ` (defined below) |
| `tooth_number` | universal numbering (2–15 maxillary, 18–31 mandibular) |
| `site` | `distal`, `central`, or `mesial` per tooth |
| `value` | integer mm |

The five `exam_date` values are five sequential periodontal-maintenance
exams of **one patient** (`patient_01`) over a ~20-month window:

| `exam_index` | `chart_id` | `exam_date` | gap from previous exam |
| --- | --- | --- | --- |
| 1 (baseline) | 5 | 2024-06-17 | — |
| 2 | 4 | 2024-12-04 | ~5.6 months |
| 3 | 3 | 2025-03-24 | ~3.6 months |
| 4 | 2 | 2025-11-06 | ~7.4 months |
| 5 | 1 | 2026-02-09 | ~3.1 months |

Per-site, per-tooth, and whole-mouth trend analyses are therefore unlocked
— see §15.

**Three sites per tooth on each surface, two surfaces per tooth, gives six
sites per tooth — the standard "six-point periodontal exam" used for
classification staging and most published case definitions.**[1][2]

### What we deliberately do *not* have

These are part of a complete periodontal exam but were not on the source
charts and so cannot be inferred without further data:

- **Bleeding on probing (BOP)** — site-level binary; required for the
  AAP/EFP definitions of health vs gingivitis, and for the EFP S3 treatment
  endpoint "no PD ≥ 5 mm with BOP".[1][3]
- **Plaque score / plaque index** (e.g. O'Leary, Silness–Löe) — required for
  any oral-hygiene metric.[3]
- **Tooth mobility** (Miller class 0–3) — feeds prognosis and Stage IV
  complexity.[1]
- **Furcation involvement** (class I–III) — feeds prognosis and Stage III/IV
  complexity.[1]
- **Radiographic bone loss (RBL)** — primary alternative to CAL for Stage
  assignment.[1]
- **Patient age, smoking status, HbA1c** — required for the AAP/EFP Grade
  (A/B/C) modifiers.[1] Direct longitudinal evidence (CAL change over the
  exam window) **is** available — see §15.3 — so Grade can be assigned from
  longitudinal CAL alone; the demographic modifiers would only let us
  *confirm* or *upgrade* the Grade.

Any tool we build should record which of these are missing and either
degrade gracefully or label results as "provisional" when that is the case.

---

## 2. Glossary of measurements

Every distance below is in millimetres (mm) and is recorded by walking a
calibrated periodontal probe (UNC-15 or equivalent) along the sulcus at each
site at a controlled light force of approximately **0.15–0.25 N** (15–25 g).
Force above ~0.25 N over-penetrates inflamed tissue and biases readings.[4]

### 2.1 PD — Probing Depth

Distance from the **gingival margin** (top of the gum) down to the **base of
the sulcus or pocket**. PD is the most commonly cited periodontal number —
"a 5-mm pocket" means PD = 5 at that site. PD increases with both
inflammation (oedema pushes the margin coronally) and attachment loss
(deeper sulcus).[3]

| PD value | clinical interpretation |
| --- | --- |
| 1–3 mm | normal sulcus, compatible with health |
| 4 mm | borderline; "too deep to be controlled by tooth brushing and interdental cleaning alone" — flag for active therapy decision[5] |
| 5 mm | moderate pocket; non-surgical therapy indicated |
| 6 mm | deep pocket; treatment endpoint of EFP S3 is to eliminate ≥ 6 mm pockets[3] |
| ≥ 7 mm | severe pocket; high tooth-loss risk, often surgical |

### 2.2 GM — Gingival Margin position relative to the CEJ

A **signed** linear distance from the cemento-enamel junction (CEJ — the line
where enamel meets root) to the gingival margin.[3]

| GM convention | meaning |
| --- | --- |
| GM = 0 | gingival margin sits exactly at the CEJ — the textbook "ideal" |
| GM > 0 | **recession** — gingiva apical to CEJ, root surface exposed |
| GM < 0 | **gingival overgrowth / hyperplasia** — gingiva coronal to CEJ |

**On the source charts in this project, GM is recorded only as positive
integers (recession). A blank cell means "GM at CEJ" — i.e. value 0 — which
is by far the most common case. We never observe the < 0 (overgrowth) case
in the source data.** The pipeline therefore stores blank GM as the integer
0 in the CSV, faithful to the chart's convention.[3]

### 2.3 CAL — Clinical Attachment Level (a.k.a. clinical attachment loss)

Distance from the **CEJ** down to the **base of the pocket**. CAL is the
gold-standard measure of accumulated periodontal destruction because it is
anchored to a fixed tooth landmark (the CEJ) and is therefore unaffected by
gingival swelling. **CAL — not PD — drives Stage assignment in the AAP/EFP
2018 classification.**[1][2]

The site-level identity is:

> **CAL = PD + GM** (with the signed GM convention above)

Worked examples:[3]

| PD | GM | CAL | reading |
| --- | --- | --- | --- |
| 4 | 0 | 4 | sulcus 4 mm, margin at CEJ → 4 mm of attachment loss |
| 3 | +2 | 5 | 3 mm sulcus + 2 mm recession → 5 mm of attachment loss |
| 3 | -2 (overgrowth) | 1 | 3 mm sulcus minus 2 mm of pseudo-pocket → 1 mm of true loss |

**This identity holds at 100% of all 840 sites in our dataset and is what we
used in `tools/validate_periodontal_readings.py` to drive the manual fix-up
loop.** It must hold for any analytics built on the data.

### 2.4 MGJ — Mucogingival Junction position

Distance from the gingival margin **down to the mucogingival junction** —
the visible line where firmly bound keratinised gingiva meets the loose
alveolar mucosa. MGJ is recorded only at sites where the clinician is
specifically interested in the mucogingival relationship (root coverage
planning, areas of progressive recession, etc.); blank means "not measured /
not relevant", which is by far the most common case in our data.[3][6]

The clinically interesting derived quantity is the **width of attached
keratinised gingiva (KTW)** at a site:

> **KTW ≈ MGJ − PD**

KTW thresholds commonly used to flag mucogingival deficiency:[6][7]

| KTW | interpretation |
| --- | --- |
| ≥ 2 mm | adequate band of attached gingiva |
| 1–2 mm | borderline; monitor |
| < 1 mm | mucogingival deficiency; consider grafting if recession is also progressive |

A second mucogingival flag any tool can compute is: **does the pocket
extend to or beyond the MGJ?** That is, **`PD ≥ MGJ`** (when MGJ is
recorded). When true, the pocket has crossed onto unattached mucosa, which
is itself a surgical indication.[6]

---

## 3. Site-level interpretation

Every site has its own (PD, GM, CAL, MGJ) tuple. The simplest tool any
dashboard needs is a per-site classifier:

```text
site_status(PD, GM, CAL, MGJ):
    PD_class ∈ {healthy: PD<=3, borderline: PD=4, moderate: PD=5,
                deep: PD=6, severe: PD>=7}
    recession  = max(GM, 0)        # positive recession only
    overgrowth = max(-GM, 0)       # negative GM = overgrowth
    cal_class ∈ {<=2: mild, 3-4: moderate, >=5: severe}
    mucogingival_breach = (MGJ != null and PD >= MGJ)
    KTW = (MGJ is not null) ? max(MGJ - PD, 0) : null
    KTW_class ∈ {>=2: adequate, 1-2: borderline, <1: deficient}
```

### Recommended color bins for site-level pocket-depth heatmaps

These match the conventions used by Florida Probe, Dentrix, and
Eaglesoft.[10][11]

| PD (mm) | colour | label |
| --- | --- | --- |
| 0–3 | green | healthy |
| 4 | yellow / orange | watch |
| 5 | red | moderate |
| 6 | dark red | deep |
| ≥ 7 | maroon / purple | severe |

For CAL heatmaps, use the same green-to-purple ramp but binned at
0–2 / 3–4 / ≥ 5 to mirror the AAP/EFP Stage I / II / III thresholds.[1]

For GM, render recession as a **negative bar above the gum line** (typical
chart convention) so the gum appears "below the CEJ" by `GM` mm; this
intuitively mirrors the patient-facing chart.

---

## 4. Tooth-level aggregation

The standard per-tooth aggregates needed for prognosis, treatment planning,
and the per-tooth row of any chart UI:

| metric | definition (over the 6 sites of one tooth) |
| --- | --- |
| `max_PD_tooth` | `max(PD)` across the 6 sites |
| `mean_PD_tooth` | `mean(PD)` |
| `max_CAL_tooth` | `max(CAL)` |
| `mean_CAL_tooth` | `mean(CAL)` |
| `max_recession_tooth` | `max(GM)` (positive values only) |
| `n_sites_PD_ge_4_tooth` | count of sites with PD ≥ 4 |
| `n_sites_PD_ge_6_tooth` | count of sites with PD ≥ 6 |
| `n_sites_CAL_ge_3_tooth` | count of sites with CAL ≥ 3 |
| `mucogingival_breach_tooth` | any site with `PD ≥ MGJ` |
| `min_KTW_tooth` | `min(MGJ − PD)` over sites where MGJ is recorded |

Use **`max_PD_tooth`** and **`max_CAL_tooth`** rather than means whenever
applying classification rules: a single deep site is the clinically
relevant signal, not the average across an otherwise healthy tooth.

### Tooth = "affected" rules (used downstream for extent)

A tooth is conventionally counted as "periodontally affected" (i.e.
contributes to the localised vs generalised denominator) when **any** of:

- `max_CAL_tooth ≥ 3` mm (this is the cutoff used by CDC/AAP surveillance
  case definitions and matches the Stage II floor of the AAP/EFP framework)
  [1][12]
- `max_PD_tooth ≥ 4` mm

A "deep" tooth (Stage III complexity contributor) requires
`max_PD_tooth ≥ 6` mm or `max_CAL_tooth ≥ 5` mm.[1]

---

## 5. Whole-mouth indicators

These are the headline numbers a clinician scans first, and the tiles a
dashboard should put across the top of the screen.

| metric | definition (over all sites in one chart × arch × surface, or all 168 sites in one chart) |
| --- | --- |
| `mean_PD` | arithmetic mean of all PD values |
| `mean_CAL` | arithmetic mean of all CAL values |
| `pct_sites_PD_ge_4` | `100 × count(PD ≥ 4) / count(sites)` |
| `pct_sites_PD_ge_5` | `100 × count(PD ≥ 5) / count(sites)` |
| `pct_sites_PD_ge_6` | `100 × count(PD ≥ 6) / count(sites)` |
| `pct_sites_CAL_ge_3` | `100 × count(CAL ≥ 3) / count(sites)` |
| `pct_sites_CAL_ge_5` | `100 × count(CAL ≥ 5) / count(sites)` |
| `n_teeth_with_PD_ge_6` | count of distinct teeth with `max_PD_tooth ≥ 6` |
| `n_teeth_with_CAL_ge_5` | count of distinct teeth with `max_CAL_tooth ≥ 5` |
| `pct_teeth_affected` | `100 × n_teeth_with_max_CAL_ge_3 / n_teeth_present` (drives extent) |
| `max_PD_mouth` | `max(PD)` over all sites |
| `max_CAL_mouth` | `max(CAL)` over all sites — drives Stage |
| `mean_recession` | `mean(max(GM, 0))` |
| `n_sites_mucogingival_breach` | count of sites where `PD ≥ MGJ` (only on sites with MGJ recorded) |

**Two surface stratifications that matter clinically:**
report each metric separately for `facial` vs `lingual`. Plaque tends to
accumulate differently on the two surfaces and treatment access differs
(facial is generally more accessible than lingual), so unequal disease
burden across surfaces is itself a finding worth surfacing.

---

## 6. AAP/EFP 2018 staging (Stage I–IV)

This is the primary classification we can populate from our dataset
(provisionally, since we lack radiographic bone loss and tooth-loss
attribution data).[1][2]

### Algorithm

```text
def stage(chart):
    # Inputs from our data
    max_interdental_CAL = max( CAL[s] for s in sites
                               if s.site in {distal, mesial} )
    max_PD              = max( PD[s] for s in all sites )

    # Inputs we DO NOT have — flag as missing
    max_RBL_percent     = MISSING   # radiographic bone loss
    teeth_lost_to_perio = MISSING   # we have no edentulous flag
    furcation_class     = MISSING
    mobility_grade      = MISSING

    # Severity floor by max_interdental_CAL
    if max_interdental_CAL <= 2:   base = "I"
    elif max_interdental_CAL <= 4: base = "II"
    elif max_interdental_CAL >= 5: base = "III"   # IV requires extra inputs

    # PD complexity bumps that ARE supported by our data
    if base == "I"  and max_PD >= 5: base = "II"
    if base == "II" and max_PD >= 6: base = "III"

    # Stage IV requires teeth-lost ≥ 5, mobility ≥ 2, or remaining_teeth < 20.
    # We cannot assess these → never assign IV from our data alone; surface
    # "Stage III (Stage IV not assessable from this dataset)".

    return base, "provisional"
```

### Severity thresholds (from the 2018 World Workshop)[1][2]

| Stage | Greatest interdental CAL | Max PD (complexity) | Notes |
| --- | --- | --- | --- |
| I | 1–2 mm | ≤ 4 mm | mild |
| II | 3–4 mm | ≤ 5 mm | moderate |
| III | ≥ 5 mm | ≤ 6 mm typically | severe; ≤ 4 teeth lost to perio |
| IV | ≥ 5 mm | ≥ 6 mm with complexity | severe + ≥ 5 teeth lost to perio, mobility ≥ 2, or remaining teeth < 20 |

### Extent[1][8]

```text
def extent(chart):
    n_present  = count(distinct tooth_number)
    n_affected = count(distinct tooth_number where max_CAL_tooth >= 3)
    pct        = 100.0 * n_affected / n_present
    return "localised" if pct < 30 else "generalised"
```

The "molar–incisor pattern" descriptor (typical of aggressive periodontitis
in young patients) is a *qualitative* call when bone loss is concentrated on
first molars and incisors.[8]

### Grading (A / B / C) — **provisional, via §15.3**

This subsection was originally written before `exam_date` and `patient_id`
were joined onto every CSV row, when the dataset looked like five
unrelated charts.  With those columns now present and confirmed to be
five sequential exams of one patient over a ~20-month window (see §15),
the **direct longitudinal-CAL evidence path** for grading IS available
and is the authoritative method for this dataset.  See **§15.3** for the
algorithm.

The result must always be reported as `Evidence(status="provisional")`
because the published Grade thresholds are expressed per 5 years and
this dataset's window is shorter; §15.3 scales linearly to a 5-year
equivalent and the resulting Grade therefore carries the explicit
assumption `"projected from {window_years:.2f}-year window"`.  Demographic
modifiers (age, smoking, HbA1c) — gathered into `manifests/patient_metadata.csv`
and `manifests/patient_history_events.csv` in Phase 0 — can subsequently
*confirm* or *upgrade* the Grade returned by §15.3, but they are no longer
required to compute it.

The earlier guidance to "default to Grade B (assumed)" is superseded:
return the Grade computed in §15.3, with `status="provisional"` and the
projection-window assumption attached, rather than a bare default.

---

## 7. CDC / AAP surveillance case definitions

These are the population-epidemiology rules used by NHANES and most
periodontal surveillance papers; they are interproximal-CAL-and-PD based and
fully computable from our data.[12][13]

```text
def cdc_aap_severity(chart):
    interp = sites where site in {distal, mesial}

    n_cal6_diff_teeth = count_distinct_teeth(interp, CAL >= 6)
    n_pd5_interprox   = count(interp where PD >= 5)
    n_cal4_diff_teeth = count_distinct_teeth(interp, CAL >= 4)
    n_pd5_diff_teeth  = count_distinct_teeth(interp, PD >= 5)
    n_cal3_diff_teeth = count_distinct_teeth(interp, CAL >= 3)
    n_pd4_diff_teeth  = count_distinct_teeth(interp, PD >= 4)

    if n_cal6_diff_teeth >= 2 and n_pd5_interprox >= 1:
        return "severe"
    if n_cal4_diff_teeth >= 2 or n_pd5_diff_teeth >= 2:
        return "moderate"
    if n_cal3_diff_teeth >= 2 and n_pd4_diff_teeth >= 2:
        return "mild"
    return "no/minimal"
```

The "different teeth" requirement (`distinct tooth_number`) prevents a
single bad tooth from dominating the patient classification.[12]

---

## 8. Periodontal Screening and Recording (PSR)

PSR collapses the mouth into 6 sextants (UR / U-anterior / UL / LL /
L-anterior / LR) and assigns a single 0–4 code per sextant based on the
worst finding in that sextant.[14][15]

**Caveat for our dataset:** PSR codes 1 vs 2 distinguish "BOP without
calculus" vs "BOP/calculus", neither of which we have. From PD alone we can
only assign a *PD-floor PSR* — that is, the minimum code consistent with
our pocket depths. Any production tool should expose this clearly.

```text
def psr_pd_floor(sextant_sites):
    if all sextant teeth missing: return 'X'
    max_pd = max(PD over sextant_sites)
    if max_pd <= 3:   return 0   # could actually be 1 or 2 with BOP/calculus
    elif max_pd <= 5: return 3
    else:             return 4
```

Standard sextant boundaries (universal numbering):

| sextant | maxillary teeth | mandibular teeth |
| --- | --- | --- |
| right | 2, 3, 4, 5 | 28, 29, 30, 31 |
| anterior | 6, 7, 8, 9, 10, 11 | 22, 23, 24, 25, 26, 27 |
| left | 12, 13, 14, 15 | 18, 19, 20, 21 |

A sextant marked with "\" in clinical PSR notation indicates furcation
involvement, mobility, mucogingival problems, or recession to the band — we
can flag the mucogingival-problem variant from our MGJ data when
`PD ≥ MGJ` at any sextant site.[14]

---

## 9. Per-tooth prognosis frameworks

Three published systems are widely cited; pick the one that matches your
audience.

### 9.1 McGuire & Nunn (qualitative, hierarchical)[16]

| prognosis | key thresholds (from PD / CAL / mobility / furcation) |
| --- | --- |
| Good | bone loss < 25%, PD ≤ 4, CAL ≤ 2, no mobility, no furcation |
| Fair | bone loss 25–50%, PD ≈ 5, CAL 3–4, mobility ≤ I, furcation I |
| Poor | bone loss ~50%, PD 6–7, CAL 5–6, mobility ≤ II, furcation II |
| Questionable | bone loss > 50%, PD ≥ 8, CAL ≥ 7, mobility ≥ II, furcation II/III |
| Hopeless | bone loss > 50% with vertical defect, PD > 10, mobility ≥ III, furcation III |

From our data alone we cannot fully apply this (we lack mobility,
furcation, and bone loss) but **`max_PD_tooth` and `max_CAL_tooth` give a
PD/CAL-only floor**: a tooth with `max_PD_tooth ≥ 8` or `max_CAL_tooth ≥ 7`
cannot be better than Questionable, regardless of the other inputs.

### 9.2 Kwok & Caton (focus on stability / controllability)[17]

Four categories — Favorable / Questionable / Unfavorable / Hopeless — applied
post-therapy and based on the **most limiting factor**, with the same
PD/CAL/mobility/furcation thresholds. It is built around "can periodontal
stability be maintained?" rather than "will the tooth survive 10 years?".

### 9.3 Miller–McEntire Periodontal Prognostic Index (MMPPI, molars only)[18][19]

Additive score:

| parameter | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- |
| Probing depth (mm) | < 5 | 5–7 | 8–10 | > 10 |
| Mobility | none | I | II | III |
| Furcation | none | I | II | III |
| Age | < 40 | ≥ 40 | — | — |
| Smoking | non-smoker | smoker | — | — |
| Diabetes | non-diabetic | diabetic | — | — |

Total → prognosis & 10-yr survival probability:

| total | category | ~10-yr survival |
| --- | --- | --- |
| 0–3 | Good | ~99% |
| 4–6 | Fair | ~96% |
| 7–8 | Poor | ~75% |
| 9–10 | Hopeless | ~12% |

For our dataset we can populate the PD axis (and contribute that to a UI
that lets the clinician fill in the rest), but we cannot compute MMPPI
end-to-end without mobility, furcation, age, smoking, and diabetes.

---

## 10. Mucogingival assessment

Even though MGJ is sparsely recorded in our charts, where it is recorded we
can flag two clinically significant conditions:

1. **Mucogingival defect** (pocket has crossed onto loose mucosa):
   `PD >= MGJ` at the site.[6]
2. **Inadequate keratinised tissue width**:
   `KTW = MGJ - PD < 2` mm — borderline if 1–2, deficient if < 1.[7]

Combined with `GM` (recession) at the same site, these flag candidates for
mucogingival surgery (free gingival graft, connective tissue graft, or
coronally advanced flap), per AAP guidance.[6][7]

---

## 11. Suggested dashboard layout

Mirror the layout periodontists are used to from Florida Probe, Dentrix,
and Eaglesoft.[10][11][20]

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Patient: chart 3   |  Stage III (provisional)   |  Extent: generalised   │
│ Mean PD 3.4 mm     |  Mean CAL 3.9 mm  |  Max PD 7  |  Max CAL 8         │
│ Sites PD ≥ 4: 28%  |  PD ≥ 5: 11%  |  PD ≥ 6: 4%                         │
│ Teeth with PD ≥ 6: 5  |  Teeth with CAL ≥ 5: 9                           │
└──────────────────────────────────────────────────────────────────────────┘

Maxillary heatmap (facial above, lingual below):
  ┌─2──3──4──5──6──7──8──9──10─11─12─13─14─15─┐
F │  3  3  4  4  3  3  4  4  4  3  4  4  6  5│
  │  4  4  3  3  4  3  4  4  3  4  3  3  3  4│   ← three sites per tooth
  │  4  3  4  4  3  3  4  3  4  3  4  4  5  4│
L │ ...                                      │   coloured per §3
  └──────────────────────────────────────────┘

Per-tooth detail row on hover/click:
  Tooth 14  | PD 5/6/4 (max 6)  | GM 0/1/0  | CAL 5/7/4  | KTW —
            | Status: deep pocket distal-buccal; recession central
            | PD-floor prognosis: Poor (max_PD ≥ 6)
```

### Glyphs and overlays

- **Recession** (`GM > 0`): draw a small gum-line offset above the tooth
  glyph, scaled by mm.
- **Deep pocket** (PD ≥ 6): triangle marker beneath the affected site.
- **Mucogingival breach** (`PD ≥ MGJ`): orange asterisk on the site.
- **Per-arch / per-surface stratification**: split the heatmap into 4
  panels (max-facial, max-lingual, mand-facial, mand-lingual).

---

## 12. Recipes for the analyses we can do *now*

These are directly executable on `outputs/periodontal_readings.csv` without
any additional data.

| analysis | what to compute |
| --- | --- |
| Site-level pocket-depth heatmap (per chart) | colour-code each (tooth, site, surface) by PD bin; arrange as in §11 |
| Per-tooth max-PD / max-CAL bar chart | for each tooth, plot max(PD) and max(CAL) side-by-side |
| Whole-mouth tile dashboard | the metrics in §5, repeated per chart |
| AAP/EFP Stage (provisional) | algorithm in §6 |
| Localised vs generalised extent | §6 algorithm |
| CDC/AAP severity (mild/moderate/severe) | §7 algorithm |
| PSR PD-floor codes per sextant | §8 algorithm |
| Per-tooth PD-floor prognosis | from §9.1 thresholds, on `max_PD_tooth` alone |
| Mucogingival breach map | §10 — sites where `PD ≥ MGJ` |
| Recession map | per site `max(GM, 0)` heatmap |
| Cross-exam comparison | sort exams chronologically by `exam_date` or `exam_index` (ISO format makes lexicographic sort safe; never sort by `chart_id`, which is anti-chronological) |
| Per-site / per-tooth deltas across exams | join two exams on `(patient_id, arch, surface, measurement, tooth_number, site)` and subtract — see §15.1 |
| AAP/EFP Grade A/B/C via longitudinal CAL | direct evidence path, see §15.3 |
| EFP S3 treatment-endpoint (PD-only variant) | per exam: `n_teeth_with_PD_ge_6 == 0`; full endpoint requires BOP |
| Tooth-loss tracking across exams | `n_distinct(tooth_number) per exam_index` — see §15.5 |

## 13. Recipes for analyses that require *extra* inputs

These should be designed as forms or upload steps in any production tool:

| analysis | extra inputs needed |
| --- | --- |
| Periodontal health vs gingivitis classification | BOP per site |
| EFP S3 treatment endpoint check ("no PD ≥ 5 with BOP, no PD ≥ 6") | BOP per site |
| AAP/EFP Grade A/B/C (full, with demographic modifiers) | age + smoking + HbA1c. The direct longitudinal-CAL path is **already computable** from this dataset — see §15.3 |
| EFP S3 treatment endpoint (full, with BOP)      | site-level BOP per exam |
| Per-site bleeding / inflammation analysis       | site-level BOP per exam |
| Stage IV upgrade | tooth-loss-due-to-periodontitis count, remaining-teeth count, mobility, occlusal/functional flags |
| McGuire & Nunn / Kwok & Caton / MMPPI prognosis (full) | mobility grade, furcation class, % radiographic bone loss; for MMPPI also age/smoking/diabetes |
| Risk-stratified maintenance interval recommendation | any of the above |

---

## 14. Conventions and edge cases for tool builders

1. **Always treat blank GM and blank MGJ as 0 / "not measured".** The CSV
   already encodes blank GM as 0 (which mathematically agrees with the
   "GM at CEJ" clinical convention). Blank MGJ should be treated as
   `null` / unknown (not 0), because 0 here would mean "the gingival margin
   is at the MGJ", which is biologically nonsensical.
2. **Always use site-level data as the source of truth.** Aggregate up;
   never start from a per-tooth max and try to re-derive site behaviour.
3. **Never silently impute PD or CAL.** A blank PD or CAL is a missing
   measurement, not a 0. Our pipeline already enforces this (the validator
   prints any blank PD/CAL); analytics should too.
4. **Use `max(interdental CAL)` for staging**, not `max(CAL)` over all
   sites. "Interdental" means the distal and mesial sites (i.e. the two
   sides between adjacent teeth) — the CAL identity is recorded between
   teeth, not directly on the buccal/lingual aspect of a single tooth.[1]
5. **Stratify by surface when reporting BOP-equivalent data**
   (`mucogingival_breach`, recession, etc.); facial and lingual disease
   patterns differ and lumping them hides useful clinical signal.
6. **Label every classification "provisional" until the missing inputs
   listed in §1 are available.** A periodontist will trust the dashboard
   more if the limits are explicit.
7. **Per-tooth prognosis is most defensible when expressed as a floor**:
   "this tooth cannot be better than 'fair' based on PD/CAL alone" is
   honest; "this tooth is poor" without mobility / furcation / radiographs
   overstates what we know.

---

## 15. Longitudinal analyses

The CSV carries `patient_id`, `exam_date`, and `exam_index` on every row,
joined from `manifests/chart_metadata.csv`. The five exams in the data are
all from one patient (`patient_01`):

| `exam_index` | `chart_id` | `exam_date` | gap from previous |
| --- | --- | --- | --- |
| 1 (BASELINE) | 5 | 2024-06-17 | — |
| 2 | 4 | 2024-12-04 | ~5.6 months |
| 3 | 3 | 2025-03-24 | ~3.6 months |
| 4 | 2 | 2025-11-06 | ~7.4 months |
| 5 | 1 | 2026-02-09 | ~3.1 months |

The cadence matches a 3-to-6-month periodontal-maintenance recall schedule.
Always sort by `exam_date` (or the equivalent `exam_index`) when doing
trend work — never by `chart_id`, which is anti-chronological.

### 15.1 Per-site delta computations

For any pair of exams (`baseline_exam_index`, `current_exam_index`), join
on `(patient_id, arch, surface, measurement, tooth_number, site)` and
compute:

```text
delta_PD  (per site) = current_PD  - baseline_PD
delta_CAL (per site) = current_CAL - baseline_CAL
delta_GM  (per site) = current_GM  - baseline_GM   (positive = more recession)
```

Use these to populate the standard treatment-response widgets:

| metric | definition |
| --- | --- |
| `pct_sites_PD_improved_ge_2mm` | % of sites where `delta_PD <= -2` |
| `pct_sites_PD_worsened_ge_2mm` | % of sites where `delta_PD >= +2` |
| `pct_sites_CAL_lost_ge_2mm` | % of sites where `delta_CAL >= +2` (progression marker) |
| `n_sites_recession_progression` | count of sites where `delta_GM >= +1` |
| `mean_PD_change` | mean of `delta_PD` |
| `mean_CAL_change` | mean of `delta_CAL` |

Conventions used by Florida Probe and PracticeWorks treat `delta` of
≥ 1 mm as "minor change" and ≥ 2 mm as "clinically meaningful" — render
≥ 2 mm changes with prominent colour (green for improvement, red for
progression).[10][20]

### 15.2 Trend charts

Whole-mouth aggregates from §5 plotted as time series across exams give
the standard maintenance-response chart:

- `mean_PD` over time (line)
- `mean_CAL` over time (line)
- `pct_sites_PD_ge_4` over time (line)
- `pct_sites_PD_ge_6` over time (line)
- `n_teeth_with_PD_ge_6` over time (bar)
- per-tooth `max_PD_tooth` heat-strip across exams (rows = teeth, columns
  = exam dates, colour by PD bin) — the periodontal equivalent of a
  vital-signs flowsheet

### 15.3 AAP/EFP Grade (A / B / C)

With longitudinal CAL across ~20 months we can take the **direct
evidence path** for grading. The published thresholds are expressed per
5 years; for shorter windows, scale linearly and **state the
extrapolation explicitly** when reporting:

```text
window_years        = (max(exam_date) - min(exam_date)) / 365.25
max_cal_change_obs  = max(CAL_per_site @ exam_index=N) - max(CAL_per_site @ exam_index=1)
cal_change_5yr_equiv = max_cal_change_obs * (5 / window_years)

Grade A if cal_change_5yr_equiv == 0      (no progression)
Grade B if cal_change_5yr_equiv  < 2 mm
Grade C if cal_change_5yr_equiv >= 2 mm   (rapid progression)
```

A 20-month observation projected to 5 years has more uncertainty than a
true 5-year direct measurement; tools should label the result
"projected from {window_years:.1f}-year window".[1][9]

### 15.4 EFP S3 treatment-endpoint check

The EFP S3 treatment endpoint (post-active-therapy success criterion) is
"no PD ≥ 5 mm with BOP, no PD ≥ 6 mm".[20] We don't have BOP, but the PD
half is fully computable per exam:

```text
endpoint_pd_only(exam) = (pct_sites_PD_ge_6(exam) == 0)
                        and (pct_sites_PD_ge_5(exam) == 0  # strict variant
                             or n_teeth_with_PD_ge_5 == 0)
```

Track this boolean across exams to surface "treatment-endpoint achieved
at exam N" / "endpoint lost at exam N" events.

### 15.5 Tooth-loss tracking

Comparing `n_distinct(tooth_number)` per exam reveals teeth that
disappear from one exam to the next (extracted between visits). This
feeds the AAP/EFP Stage IV "teeth-lost-due-to-periodontitis ≥ 5"
criterion.

In the current data, each chart contains all 28 non-wisdom teeth, so no
teeth have been lost across the 20-month window — but the analysis
should be wired up so it surfaces a finding the moment a future exam
contains fewer teeth.

---

## References

[1] Caton J. et al. *A new classification scheme for periodontal and
peri-implant diseases and conditions — Introduction and key changes from the
1999 classification.* J Periodontol 2018; J Clin Periodontol 2018.
<https://caseyhein.com/wp-content/uploads/Caton_et_al-2018-Journal_of_Periodontology.pdf>

[2] American Academy of Periodontology. *Staging and Grading Periodontitis*
(2019). <https://perio.org/wp-content/uploads/2019/08/Staging-and-Grading-Periodontitis.pdf>

[3] Scottish Dental Clinical Effectiveness Programme. *Periodontal
parameters — what should be recorded.*
<https://periodontalcare.sdcep.org.uk/guidance/assessment/special-tests/full-periodontal-examination/what-should-be-recorded/periodontal-parameters/>

[4] Floridaprobe overview — controlled probing force literature.
<https://floridaprobe.com/downloads/FP_Overview.pdf>

[5] British Society of Periodontology. *Good Practitioner's Guide* (2016).
<https://bsperio.org.uk/assets/downloads/good_practitioners_guide_2016.pdf>

[6] Mucogingival junction (Wikipedia clinical summary, with primary refs).
<https://en.wikipedia.org/wiki/Mucogingival_junction>

[7] Keratinised tissue width thresholds and grafting indications.
<https://decisionsindentistry.com/article/decision-making-modern-mucogingival-therapy/>

[8] Papapanou P. N. et al. *Periodontitis: Consensus report of workgroup 2
of the 2017 World Workshop.* J Clin Periodontol 2018.
<https://efp.org/fileadmin/uploads/efp/Documents/Campaigns/New_Classification/Reports/Consensus_report__Workgroup_2__Papapanou_et_al-2018-Journal_of_Clinical_Periodontology.pdf>

[9] EFP Guidance Notes — staging and grading.
<https://efp.org/fileadmin/uploads/efp/Documents/Campaigns/New_Classification/Guidance_Notes/report-02b.pdf>

[10] Florida Probe sample chart (color thresholds and per-tooth layout).
<https://floridaprobe.com/pdf/FP_PerioChart_sample.pdf>

[11] Dentrix Perio Chart documentation (six-site ordering, color
conventions). <https://hsps.pro/Dentrix/Help/mergedProjects/Perio%20Chart/Data%20Chart/The_Data_Chart_overview.htm>

[12] CDC/AAP surveillance case definitions.
<https://stacks.cdc.gov/view/cdc/6953/cdc_6953_DS5.pdf>

[13] CDC–AAP definitions analytical paper.
<https://pmc.ncbi.nlm.nih.gov/articles/PMC6005373/>

[14] Periodontal Screening and Recording (PSR) — CE course summary.
<https://assets.ctfassets.net/u2qv1tdtdbbu/263D0rgANUt1xNLpWYLIYU/46d6347af1145bbb42b883367d2194ca/ce617.pdf>

[15] Augusta University PSR chart reference.
<https://augusta.edu/dentaltable/pdfs/patientexam/PSR-chart.pdf>

[16] McGuire & Nunn — periodontal prognosis (Okanagan Periodontics summary
of the 1991/1996 system).
<https://www.okanaganperiodontics.com/wp-content/uploads/2017/10/Periodontal-PrognosisPV.pdf>

[17] Kwok V, Caton JG. *Commentary: prognosis revisited — a system for
assigning periodontal prognosis.* J Periodontol 2007 (USUHS digital
collection copy).
<https://digitalcollections.lrc.usuhs.edu/digital/api/collection/p16005coll10/id/197782/download>

[18] Miller PD, McEntire ML. *Miller–McEntire Periodontal Prognostic Index*
(2011 scoring sheet).
<https://www.periomem.com/wp-content/uploads/2018/11/Miller-McEntire-Prognosis-Scoring-System-Jan-23-2011.pdf>

[19] Validation of the MMPPI in molar survival.
<https://pmc.ncbi.nlm.nih.gov/articles/PMC8936013/>

[20] EFP S3 Level Treatment Guideline (Periodontitis treatment endpoints).
<https://efp.org/fileadmin/uploads/efp/Documents/Perio_Insight/Perioinsight13.pdf>
