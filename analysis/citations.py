"""Central registry of citation strings.

Every metric / classifier / flag in the analytical layer puts one of
these into its ``Evidence(citation=...)`` so the Phase 5 narrative
layer can render uniform pointers back into the clinical spec without
embedding clinical text of its own.

Pattern: ``"PERIODONTAL_INTERPRETATION.md sec N (one-line topic);
upstream guidance [refs]"``.
"""

from __future__ import annotations

# Site-level (sec 2 measurement definitions, sec 3 site-level interpretation).
SITE_PD_CLASS = "PERIODONTAL_INTERPRETATION.md sec 3 (site PD bins); sec 2.1 [3]"
SITE_RECESSION = "PERIODONTAL_INTERPRETATION.md sec 2.2 (signed GM convention); sec 3"
SITE_MUCOGINGIVAL_BREACH = (
    "PERIODONTAL_INTERPRETATION.md sec 10 (PD >= MGJ flags pocket onto mucosa); "
    "sec 2.4 [6]"
)
SITE_KTW = (
    "PERIODONTAL_INTERPRETATION.md sec 2.4 (KTW = MGJ - PD); sec 10 thresholds [7]"
)

# Tooth-level (sec 4).
TOOTH_AGGREGATE = "PERIODONTAL_INTERPRETATION.md sec 4 (tooth-level aggregation)"
TOOTH_AFFECTED = (
    "PERIODONTAL_INTERPRETATION.md sec 4 (tooth = 'affected' when "
    "max_CAL_tooth >= 3 mm or max_PD_tooth >= 4 mm) [1][12]"
)
TOOTH_DEEP = (
    "PERIODONTAL_INTERPRETATION.md sec 4 (tooth 'deep' when "
    "max_PD_tooth >= 6 mm or max_CAL_tooth >= 5 mm) [1]"
)

# Mouth-level (sec 5).
MOUTH_AGGREGATE = "PERIODONTAL_INTERPRETATION.md sec 5 (whole-mouth indicators)"
MOUTH_INTERDENTAL_CAL = (
    "PERIODONTAL_INTERPRETATION.md sec 6 + sec 14 rule 4 "
    "(stage uses max interdental CAL = max over distal/mesial sites only) [1]"
)
MOUTH_EXTENT = (
    "PERIODONTAL_INTERPRETATION.md sec 6 (extent: localised < 30 percent of "
    "teeth affected, generalised >= 30 percent) [1][8]"
)

# Mucogingival (sec 10).
MGN_NOT_ASSESSABLE_ON_PATIENT_01 = (
    "PERIODONTAL_INTERPRETATION.md sec 10 + sec 14 rule 1 (MGJ = 0 in CSV "
    "means 'not measured'; mucogingival metrics not assessable when MGJ "
    "is None for the entire dataset)"
)

# Per-tooth caveats from Phase 0 history.
TOOTH_CROWN_CAVEAT = (
    "PERIODONTAL_INTERPRETATION.md sec 14 rule 1 spirit (record provenance "
    "of every reading); patient_history_events.csv restoration row"
)
SITE_MOUTH_BREATHING_CAVEAT = (
    "patient_history_events.csv condition 'chronic_mouth_breathing' "
    "(anterior-facial inflammation bias)"
)

# Patient / longitudinal (sec 15).
PATIENT_DEMOGRAPHICS = (
    "manifests/patient_metadata.csv (Phase 0 intake); "
    "PERIODONTAL_INTERPRETATION.md sec 1"
)
LONGITUDINAL_DELTA = (
    "PERIODONTAL_INTERPRETATION.md sec 15.1 (per-site delta on full "
    "(patient_id, arch, surface, measurement, tooth_number, site) join key)"
)
LONGITUDINAL_TREATMENT_RESPONSE = (
    "PERIODONTAL_INTERPRETATION.md sec 15.1 (treatment-response widgets; "
    ">=2 mm delta = clinically meaningful) [10][20]"
)
LONGITUDINAL_TREND = "PERIODONTAL_INTERPRETATION.md sec 15.2 (trend charts)"
LONGITUDINAL_GRADE = (
    "PERIODONTAL_INTERPRETATION.md sec 15.3 (Grade A/B/C from longitudinal "
    "CAL, projected to 5-year equivalent); sec 6 (Grade Provisional via "
    "sec 15.3); AAP/EFP 2018 [1][9]"
)
LONGITUDINAL_S3_PD_ONLY = (
    "PERIODONTAL_INTERPRETATION.md sec 15.4 (EFP S3 treatment endpoint, "
    "PD-only variant: full endpoint requires BOP) [20]"
)
LONGITUDINAL_TOOTH_LOSS = (
    "PERIODONTAL_INTERPRETATION.md sec 15.5 (tooth-loss tracking)"
)

# Classification (sec 6, 7, 8, 9).
CLASSIFY_STAGE = (
    "PERIODONTAL_INTERPRETATION.md sec 6 (AAP/EFP 2018 Stage I-IV); [1][2]"
)
CLASSIFY_STAGE_IV_NOT_ASSESSABLE = (
    "PERIODONTAL_INTERPRETATION.md sec 6 (Stage IV upgrade requires "
    "teeth-lost-to-perio, mobility, remaining-teeth count -- inputs not "
    "available from this dataset)"
)
CLASSIFY_EXTENT = MOUTH_EXTENT
CLASSIFY_CDC_AAP = (
    "PERIODONTAL_INTERPRETATION.md sec 7 (CDC/AAP surveillance "
    "case definitions) [12][13]"
)
CLASSIFY_PSR = (
    "PERIODONTAL_INTERPRETATION.md sec 8 (PSR PD-floor codes per "
    "sextant; full PSR requires BOP/calculus) [14][15]"
)
CLASSIFY_PROGNOSIS_FLOOR = (
    "PERIODONTAL_INTERPRETATION.md sec 9 (per-tooth prognosis frameworks; "
    "PD/CAL-only floor applied without mobility/furcation/RBL inputs) [16]"
)

# Mucogingival / soft-tissue surgery assessment (sec 2.2 + sec 10).
RECESSION_TRAJECTORY = (
    "PERIODONTAL_INTERPRETATION.md sec 2.2 (signed GM convention; "
    "recession_mm = max(GM, 0)); sec 15.1 (per-site delta on full join key)"
)
SOFT_TISSUE_INTERVENTION = (
    "PERIODONTAL_INTERPRETATION.md sec 10 (mucogingival assessment + "
    "candidates for grafting / coronally-advanced-flap surgery); sec 14 "
    "rule 1 (KTW from MGJ - PD not assessable when MGJ is None) [6][7]"
)
SOFT_TISSUE_TREATMENT_RESPONSE = (
    "PERIODONTAL_INTERPRETATION.md sec 15.1 (per-site delta_GM as "
    "treatment-response signal for mucogingival procedures); sec 2.2"
)
