# Incremental fluid-choice interventions in MIMIC-IV

Reproduce the study of lactated Ringer's versus 0.9% saline at one qualifying ICU bolus, using MIMIC-IV **version 3.1**. This repository contains extraction code, the 64-covariate specification, model fitting, IPI curves, ICI mechanism-sensitivity regions, and plotting code.

The two analyses are named **Imputed sample** and **Complete-case sample** throughout. The original internal letter labels are not used. Both analyses use the same 64 clinical fields, before categorical encoding and additional missingness indicators.

**No MIMIC-IV records or patient-level derived data are included.** Authorized users supply their own local MIMIC-IV download. All extraction intermediates, selected datasets, prediction caches, and generated results are written to a separate working directory outside this repository. The `expected/` directory contains aggregate reference results only.

## What is reproduced

The eligible source cohort contains 5,171 adults, with one selected bolus per patient. Time zero is its recorded start, at least 6 and less than 48 hours after ICU admission. Eligibility requires a systemic antimicrobial administration and blood-culture collection in the preceding 24 hours, plus hypotension in the preceding two hours or a documented ongoing vasopressor infusion. Treatment is LR (`A=1`) versus saline (`A=0`). The outcome indicates recorded death on calendar days 0–28 relative to treatment.

| Analysis | Selection from the eligible cohort | Patients |
|---|---|---:|
| Imputed sample | All 17 prior-history fields observed; at most four missing values among the other 47 fields | 2,089 |
| Complete-case sample | All 64 fields observed | 529 |

The imputed sample remains unimputed on disk after cohort construction. Continuous means, discrete/nominal modes, missingness indicators, and categorical encoders are learned inside each model-training fold. This is simple single imputation, not chained equations or multiple imputation. All complete cases are included in the imputed sample.

## Requirements

- Authorized access to the complete MIMIC-IV 3.1 `hosp/` and `icu/` folders, containing the original `.csv.gz` files (uncompressed `.csv` files are also supported).
- Python 3.12.3 with the versions in `requirements.txt`.
- R 4.3.3 and ggplot2 3.4.4 for the figures. The data extraction and estimation do not require R.
- The validated VM has 8 CPU cores and 32 GB RAM. Extraction uses four threads and a 16 GB DuckDB memory limit; provide a separate working directory with adequate free disk space.

No database server, BigQuery account, private prediction files, or earlier analysis directories are required. The pinned public concept definitions needed by extraction are bundled with their upstream license.

## Run from raw data

Run these commands from the repository root. Replace `/path/to/mimiciv/3.1` and `/path/to/private-work` with your own locations. The private working directory must be outside both the repository and the raw MIMIC directory.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

.venv/bin/python data_preprocessing.py \
  --mimic-dir /path/to/mimiciv/3.1 \
  --work-dir /path/to/private-work/extraction \
  --output-dir /path/to/private-work/derived

.venv/bin/python run_analysis.py \
  --data-dir /path/to/private-work/derived \
  --output-dir /path/to/private-work/analysis \
  --workers 2

Rscript make_figures.R \
  --results-dir /path/to/private-work/analysis/results \
  --output-dir /path/to/private-work/analysis/figures

# Optional: editable, self-contained LaTeX versions of both figures.
.venv/bin/python export_latex_figures.py \
  --results-dir /path/to/private-work/analysis/results \
  --output-dir /path/to/private-work/analysis/latex
```

Install ggplot2 in your R environment before the last command if needed. The tested version is recorded above; versions that change plotting defaults can change appearance without changing the numerical analysis.

`data_preprocessing.py` is the complete raw-data-to-analysis-dataset entry point. It applies the recorded timing, eligibility, history, fluid-documentation, urine-quality, and missingness rules. It does not choose variables by LASSO or use treatment-effect estimates to select patients. See [data preprocessing](docs/DATA_PREPROCESSING.md) for the exact definitions and source tables.

The work and derived-data directories must be new or empty. Extraction leaves existing runs intact. The readable [covariate list](docs/COVARIATES.md) and `config/covariate_definitions.json` describe all 64 fields. The clinical protocol in `config/cohort.json` is a fixed study specification, not a menu of interchangeable clinical thresholds.

`run_analysis.py` estimates treatment propensity and separate mortality risks using ridge logistic regression and gradient boosting with at most seven or fifteen leaves. Model weights use three-fold inner validation. Five-fold outer cross-fitting is repeated for three fixed seeds. Patient-level held-out predictions are averaged before calculating the plug-in IPI and the paper's sharp ICI sensitivity regions. See [analysis details](docs/ANALYSIS.md).

## Read the results

- `analysis/results/curves.csv`: both analyses over the full delta and chi grids.
- `analysis/results/selected_results.csv`: selected intervention strengths and sensitivity values.
- `analysis/results/`: fitted-model diagnostics, cohort summaries, and validation outputs.
- `analysis/figures/`: LR-use and mortality-difference figures, comparing the two samples.
- `analysis/latex/`: optional editable PGFPlots figures and standalone previews; see [LaTeX export instructions](docs/EXPORTED_FIGURES.md).
- `analysis/cache/`: **restricted patient-level predictions**; keep private and do not publish.

The signed parameter `delta` multiplies conditional LR odds by `exp(delta)`. Zero represents the fitted baseline policy. Mortality contrasts are percentage-point differences from **each sample's own** fitted baseline. Gray regions represent mechanism sensitivity and are **not sampling confidence intervals**.

The samples differ in population and missing-data handling. Their comparison does not isolate an effect of imputation, establish clinical efficacy, or account for sampling and imputation uncertainty through the chi regions. The sample-selection analyses were developed after earlier analyses; they were not prospectively preregistered.

## Validate a reproduction

The aggregate reference curves and cohort counts are in `expected/`. They contain no patient identifiers, rows, timestamps, or prediction vectors. Use the analysis runner's aggregate verification option to compare a reproduction against the reference curves:

```sh
.venv/bin/python run_analysis.py \
  --data-dir /path/to/private-work/derived \
  --output-dir /path/to/private-work/analysis \
  --summarize-only \
  --verify-against expected/curves.csv

.venv/bin/python -m unittest discover -s tests -v
```

Exact binary Parquet hashes can depend on serialization and row ordering. Validate sorted records, missingness patterns, and numerical tolerances as well as cohort counts. Fixed model versions and seeds are needed for close numerical agreement. The supplied reference values are regression checks for this specific release and study specification, not constraints to force a different dataset to match.

See [verification record](docs/VERIFICATION.md) for the checks actually completed on the VM.

## Data and attribution

Access to MIMIC-IV remains governed by PhysioNet's credentialing and data-use requirements. This repository neither provides data access nor grants permission to redistribute MIMIC-derived patient records. Public concept SQL is credited separately in [third-party notices](THIRD_PARTY_NOTICES.md). Study-specific adaptations are documented in the preprocessing specification.
