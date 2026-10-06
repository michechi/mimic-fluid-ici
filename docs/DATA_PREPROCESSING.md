# Recreating the two samples

`data_preprocessing.py` reconstructs the **Imputed sample** and **Complete-case sample** from an authorized, complete copy of MIMIC-IV 3.1. The repository contains source code and reference mappings, not MIMIC records. Every generated patient table, intermediate file, and identifier file remains restricted MIMIC data and must stay outside the repository.

The Imputed sample is named for its subsequent analysis. Its exported table still contains missing values: mean/mode imputation, missingness indicators, and categorical encoding are fitted within the analysis training folds. Preparing a globally filled table here would change the analysis.

## Inputs and execution

Install the repository's pinned Python dependencies. Preprocessing uses DuckDB, pandas, NumPy, and PyArrow; it does not use R or download clinical mappings. The input directory must contain these tables as `.csv.gz` or `.csv` files. Compressed files take precedence when both are present.

| Module | Required tables |
|---|---|
| `hosp` | `patients`, `admissions`, `transfers`, `d_labitems`, `services`, `prescriptions`, `emar`, `emar_detail`, `microbiologyevents`, `labevents`, `diagnoses_icd` |
| `icu` | `icustays`, `d_items`, `inputevents`, `chartevents`, `outputevents`, `procedureevents` |

No MIMIC-IV-ED tables or external derived-concept database are required. The pipeline scans large source tables, so allow substantial disk space and time. Four DuckDB threads and a 16 GB memory limit are the defaults; staged data and temporary spill files are written under the work directory.

From the repository root:

```bash
python data_preprocessing.py \
  --mimic-dir /secure/mimiciv/3.1 \
  --work-dir /secure/analysis-work/extraction \
  --output-dir /secure/analysis-work/derived \
  --threads 4 --memory-limit 16GB
```

`--raw-data` is an alias for `--mimic-dir`. Add `--check-inputs` to validate required filenames and destination paths without reading records or creating files. Both destination directories must be new or empty, disjoint, and outside the raw input directory and repository. Existing extractions are never overwritten. A failed run retains its private audit files; start a new extraction in fresh directories after resolving the failure.

The clinical eligibility section of `config/cohort.json` describes the fixed published protocol. It is not a general configuration system for alternative clinical definitions. The entrypoint verifies the fixed thresholds, age cap, and missingness threshold rather than silently accepting unsupported changes. An intentionally different protocol requires a documented code change and a new analysis.

## Index decision and eligibility

The treatment decision is an explicitly recorded ICU crystalloid bolus. Lactated Ringer's is item `225828`; 0.9% saline is item `225158`. Qualifying input events have category `03-IV Fluid Bolus`, component `Main order parameter`, description `Bolus`, positive recorded volume converted from mL or L, nonnegative duration, and a start within the recorded ICU stay. Events marked `Rewritten` are excluded. There is no additional minimum 250 mL volume, infusion-rate threshold, or maximum-duration restriction.

Time zero, `t0`, is the recorded bolus start. Eligible decisions occur at least 6 and less than 48 hours after ICU entry in adults of approximate age at least 18. The current transfer unit at `t0` must be MICU, MICU/SICU, SICU, TSICU, CCU, CVICU, or Neuro SICU. Eligibility uses the current unit, not merely the stay's first unit.

Suspected infection requires both a systemic antimicrobial administration and a blood-culture collection during `[t0−24 hours, t0)`. Administration must also have been documented before `t0`. Systemic administration includes qualifying enteral/oral routes as well as parenteral routes. Cultures require a collection timestamp and must belong to the current hospitalization or its ED episode; culture growth is not used. These criteria do not implement retrospective Sepsis-3.

Hemodynamic instability requires at least one recorded MAP below 65 mmHg or systolic pressure below 90 mmHg during `[t0−2 hours, t0)`, or a positive-rate qualifying vasopressor infusion spanning `t0` and documented before `t0`. Pressure measurements must have both event and recording times before treatment. Plausibility bounds are applied first: MAP 20–200, systolic pressure 40–300, and diastolic pressure 10–180 mmHg. Repeated or persistent hypotension is not required. Earlier fluid and vasopressor treatment is allowed.

The first clinically eligible decision is selected per person. Records of both fluids at exactly the same selected start time make treatment ambiguous; that person is excluded without substituting a later bolus. A running continuous infusion of the other fluid, or an opposite-fluid bolus at a different timestamp, does not by itself exclude the person. The application concerns this ICU decision, not necessarily the patient's first fluid exposure in the hospital.

The original source flow is 5,195 first clinically eligible decisions, 3 excluded for simultaneous ambiguous fluid choice, and 5,192 decisions linked to the endpoint. Subsequent time-zero integrity checks exclude 21 people with an index at/after discharge, missing discharge time, or recorded death before the index. These are post-linkage integrity checks, reported separately from clinical eligibility. No later index is substituted. The cleaned source cohort contains 5,171 people.

## Treatment, outcome, and the 64 original covariates

`A=1` denotes lactated Ringer's and `A=0` denotes saline at the selected bolus. `Y=1` denotes a recorded death on inclusive calendar days 0 through 28 relative to `t0`. Patient date of death is used when available, otherwise the earliest recorded hospital death date for that person. Missing recorded death in this interval is coded zero. This is a recorded calendar-day mortality endpoint; it is neither an exact 28×24-hour endpoint nor restricted to in-hospital deaths.

The ordered 64-field list in `config/cohort.json` is authoritative. It comprises 17 prior-disease-history fields and 47 other fields, before categorical encoding or missingness indicators. Computationally, the analysis uses 35 continuous, 24 discrete, and 5 nominal fields. The 47 other fields do not become 64 through encoding. See the covariate dictionary supplied with the repository for individual definitions.

Vital signs and GCS generally use the last available measurement in the preceding 6 hours, with weight using 24 hours. Laboratory values use 24 hours within the current hospitalization/ED episode. Event and recording times must precede `t0`. Blood pH is the selected blood-gas item and is not restricted to arterial specimens. Earlier diagnoses come only from hospitalizations completed before the current hospital admission; current-admission discharge diagnoses are not used. When no prior hospitalization is observed, all 17 disease-history fields remain missing rather than being set to zero.

Recorded prior NS/LR volumes sum qualifying completed, documented events earlier in the current ICU stay, not only the preceding 6 hours. The two ongoing-fluid variables summarize qualifying continuous infusions spanning `t0` that were already documented: they take the maximum positive mL/hour rate separately for NS and LR. They are not sums of overlapping rates. No qualifying pre-documented infusion gives zero; a qualifying record without a usable positive mL/hour rate would remain missing.

The 6-hour recorded net urine total includes the source irrigant correction. Negative totals and totals above 6,000 mL are quarantined as missing, not changed to zero. The original extraction has seven such cells: six negative and one above 6,000 mL. This correction precedes sample selection. Approximate age is capped at 90 in both analysis samples; the private cleaned-source intermediate retains the original approximate age for auditing.

## Sample selection and output files

The Complete-case sample contains 529 people with all 64 covariates observed after clinical cleaning. The Imputed sample contains 2,089 people with all 17 history fields observed and at most 4 missing fields among the remaining 47. These rules use covariate missingness only; curves and mortality results are not used to choose a threshold. Complete cases are contained in the Imputed sample.

Among the 5,171 source patients, 2,769 have the observed history block; the remaining missingness restriction excludes 680 of these. The Imputed sample has 529, 635, 346, 255, and 324 people with respectively 0, 1, 2, 3, and 4 missing fields. A low number of missing fields per person does not guarantee low missingness in every covariate: albumin is missing for 698/2,089 people (33.4%). Selection can change the population and introduce selection bias; neither this rule nor single imputation guarantees recovery of unmeasured confounding.

The output directory contains:

| File | Contents |
|---|---|
| `imputed_sample.parquet` | `decision_id`, `A`, `Y`, and the ordered 64 raw covariates, with missing values retained |
| `complete_case_sample.parquet` | The same 67-column schema, with all covariates observed |
| `imputed_sample_metadata.parquet` | Aligned `decision_id`, `subject_id`, `hadm_id`, `stay_id`, `t0` |
| `complete_case_sample_metadata.parquet` | The same identifier/timing schema for complete cases |
| `sample_membership.parquet` | Private source membership and missingness-rule audit |
| `cohort_metadata.json` | Exact feature order/types, sample filenames, definitions, package versions, and mapping revision |
| `cohort_audit.json` | Aggregate timing exclusions, cleaning counts, sample sizes, treatment/outcome counts, and missingness checks |
| `input_missingness.csv` | Aggregate per-field missingness in each sample |

Rows in both analysis tables and their metadata are sorted by `subject_id`, with one selected decision per person. Join metadata by `decision_id`; do not rely on a row order after filtering or merging. The outcome and identifiers are not covariates. All these outputs are kept outside the source repository; patient-level files must not be shared as part of the reproducibility code.

The private work directory contains staged Parquet files and aggregate audits. `staged/cleaned_source.parquet` permits a value-level check against a prior frozen extraction before sample selection and age capping. `staged/endpoint_linked_source.parquet` additionally retains the original urine total. Neither is a public release artifact.

## Provenance and verification

The extraction retains the frozen clinical SQL and its original event-selection/tie rules. File-location handling, orchestration, endpoint/sample export, and audit output are adapted for portability. Antibiotic and Charlson-category mappings are vendored under `src/fluid_ici/preprocessing/references/`, with their license, source revision `303d26c623dcc9c49cc0f204468d4acc2f063797`, and source-code provenance. No network connection is used during extraction. Charlson mappings supply the individual historical disease indicators; an aggregate Charlson score is not among the 64 inputs.

Built-in checks verify temporal eligibility, one decision per person, binary treatment/outcome, historical admissions, absence of concurrent/future baseline information, and expected MIMIC-IV 3.1 counts. A full reproducibility check should compare identifiers, `t0`, treatment, outcome, each of the 64 values, and missingness after sorting by person. Matching row counts alone is insufficient. Parallel Parquet writes need not have identical byte hashes, and tied source records should be checked at the value level rather than handled by a silently changed tie rule.

Synthetic tests require no MIMIC records:

```bash
PYTHONPATH=src python -m fluid_ici.preprocessing.test_protocol
```

These test calendar-day endpoint boundaries, discharge/death timing exclusions, urine quality bounds, history/missingness selection, age capping, ordered sample alignment, the fixed feature partition, and safeguards against writes into source data or the repository. They complement, rather than replace, a fresh raw-data reconstruction.
