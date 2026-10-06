# Verification record

The complete raw-data-to-figures pipeline was run on the study VM on 6 October 2026, using a fresh Python environment and new private working directories. Existing study datasets and patient predictions were not used as inputs to extraction or model fitting. Frozen datasets and aggregate curves were used afterward to check the results.

## Dataset reconstruction

The pipeline read the 17 required raw MIMIC-IV 3.1 tables and reconstructed:

| Dataset | Patients | Comparison result |
|---|---:|---|
| Eligible source cohort | 5,171 | 70 checked fields, including patient/admission/stay keys, time zero, treatment, outcome, and all 64 covariates |
| Imputed sample | 2,089 | All 67 dataset columns agree, including membership, treatment, outcome, and all 64 covariates |
| Complete-case sample | 529 | All 67 dataset columns agree, including membership, treatment, outcome, and all 64 covariates |

There were no value or missingness discrepancies at absolute tolerance `1e-8` and relative tolerance `1e-12`, after sorting by the appropriate keys. Counts alone were not used to establish agreement. The aggregate, identifier-free comparison record is in [cohort_reconstruction.json](../verification/cohort_reconstruction.json).

## Refitting and intervention curves

All six outer cross-fitting partitions (three per sample) were fitted from the reconstructed datasets. The complete 81-by-101 intervention/sensitivity grid was recomputed separately for each sample: **16,362 aggregate rows** in total.

Every numeric output field agrees with the frozen reference at absolute tolerance `1e-8`. The largest discrepancy in mortality contrasts or sensitivity endpoints is approximately `1.12e-14` percentage points; risk and treatment-probability discrepancies are on the order of `1e-16`. These are numerical-rounding differences. The full aggregate verification is in [curve_reproduction.json](../verification/curve_reproduction.json).

## Additional checks

- Six synthetic tests passed in the fresh environment, covering endpoint timing, urine cleaning, cohort selection, feature types, path protections, and the sensitivity solver.
- Sixty independently formulated finite-support linear-program comparisons checked the sharp sensitivity solver; the maximum discrepancy was `2.73e-10`. Nesting, zero/one limits, treatment relabeling, deterministic strata, and primal-dual certificates passed.
- Dependency validation reported no broken requirements.
- Both ggplot2 comparison figures were rendered from the fresh results. Reference-data PNGs were visually inspected for axes, labels, shading, and legend placement.
- Both self-contained LaTeX preview documents generated from the aggregate reference compiled successfully in the native editor. The same exporter also generated LaTeX figures from the fresh VM results.
- A source-only review found no raw records, patient-level derived datasets, individual prediction archives, credentials, or private machine paths in the tracked repository. Generated data and caches are excluded and stored externally.

## Environment and scope

Tested versions: Python 3.12.3, DuckDB 1.5.5, NumPy 2.5.3, pandas 3.0.5, PyArrow 25.0.1, SciPy 1.18.1, scikit-learn 1.9.1; R 4.3.3 with ggplot2 3.4.4. See [environment.json](../verification/environment.json) and the pinned requirements.

These checks establish computational agreement for the stated MIMIC-IV release, definitions, and fitted models. They do not establish causal identification, correct unrecorded clinical information, or quantify sampling uncertainty. Raw-data scans, serialized file bytes, and numerical libraries can behave differently in another environment; use value-level checks and the supplied aggregate comparisons rather than requiring identical Parquet bytes.
