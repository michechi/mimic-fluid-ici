# Analysis and estimand

The analysis fits two samples from the same 64 clinical input fields. The
**imputed sample** requires all 17 prior-history fields to be recorded and permits
at most four missing values among the other 47 fields. The **complete-case
sample** requires all 64 fields to be observed. The preprocessing metadata records
the sample sizes and ordered field list. Identifiers and metadata never enter the
models. Age is capped at 90 years in both samples.

These are selected-population sensitivity analyses. The complete-case sample is
nested in the imputed sample, but their comparison changes both the population
and the fitted models. It does not isolate the causal effect of missingness or
establish that either selection rule controls confounding better. The missingness
threshold was chosen during an exploratory analysis and is not a clinically
validated cutoff.

## Nuisance models

For each patient, the models estimate the treatment propensity `p`, mortality
risk under saline `mu0`, and mortality risk under lactated Ringer's `mu1`.
Separate mortality models are fitted within the corresponding observed treatment
group. All three targets use the same learner library:

* Ridge logistic regression: `C=0.1`, `lbfgs`, at most 2,000 iterations,
  convergence tolerance `1e-5`.
* Histogram gradient boosting with at most seven leaves per tree.
* Histogram gradient boosting with at most fifteen leaves per tree.

Both boosting learners use 250 iterations, learning rate 0.05, at least 40
observations per leaf, L2 penalty 5, and no early stopping. Convex ensemble
weights are selected by minimizing held-out log loss with three inner folds;
weights are nonnegative and sum to one. The optimizer is SLSQP with tolerance
`1e-10` and at most 300 iterations.

There are five outer folds, repeated for seeds `20260907`, `20260908`, and
`20260909`. Outer folds are stratified by observed treatment and outcome. Patients
are sorted by `subject_id` before constructing folds. Each patient receives
predictions only from models fitted without that patient. Inner splits are
stratified by their target, and preprocessing is fitted independently within
every inner and outer training subset. All three held-out prediction vectors
are averaged across the three outer partitions **before** evaluating the
nonlinear intervention functional.

The two samples deliberately preserve their respective fitted preprocessing
pipelines:

* **Imputed sample:** 35 continuous fields receive training-set means; 24
  numeric discrete fields and five nominal fields receive training-set modes.
  Missingness indicators are added only for fields missing in the corresponding
  training subset. A new missing value in an evaluation subset does not create
  a new indicator column. A training subset with an entirely missing field
  causes an explicit error. This is single imputation, not multiple imputation.
* **Complete-case sample:** numeric fields retain their original field order;
  the archived numeric-median and categorical-missing-level transformations are
  retained for exact reproducibility. Since the input fields are complete,
  neither fills a missing value and no numeric missingness indicators are
  added. This preprocessing is kept distinct from the imputed pipeline because
  changing feature order can change fitted tree tie-breaking.

Nominal variables use training-fitted one-hot encoding, pooling levels occurring
fewer than ten times. For ridge only, numeric fields with more than twenty
distinct training values are clipped to the 0.5th and 99.5th training quantiles
and standardized. Imputed-sample missingness indicators are also standardized
for ridge. Feature counts shown in figures refer to the 64 clinical input
fields, before encoding and additional missingness indicators.

## IPI curve

The signed parameter `delta` multiplies the conditional odds of receiving
lactated Ringer's by `exp(delta)`. The tilted probability is

\[
q_\delta(p)=\frac{e^\delta p}{1-p+e^\delta p}.
\]

`delta = 0` represents current practice, not saline. For each sample the
empirical plug-in value is

\[
\widehat\psi_W(\delta)=\frac1n\sum_i
\{\widehat\mu_{0i}+(\widehat\mu_{1i}-\widehat\mu_{0i})
q_\delta(\widehat p_i)\}.
\]

The plotted mortality difference is
`100 * (psi(delta) - psi(0))`, in percentage points. Each sample uses its own
plug-in baseline. This baseline need not equal the observed mortality proportion.
The plotted LR use is `100 * mean(q_delta(p))`. This estimator is a plug-in
estimator; it is not a one-step estimator or a directly fitted regression on
`delta`.

## Mechanism sensitivity

The fitted-law ICI bounds allow a latent treatment mechanism `G` satisfying

\[
E(G\mid W)=p(W),\qquad
E\{\operatorname{var}(G\mid W)\}
\leq\chi E\{p(W)(1-p(W))\}.
\]

The variance budget is global and is an upper bound, not an equality or a
separate budget in every stratum. Each sample recomputes its own empirical
`mean(p * (1 - p))`. The solver uses the exact conditional two-atom moment
solution and scalar Lagrange-multiplier bisection to allocate the global budget.
It returns attainable primal endpoints and dual-gap/budget certificates.
No discretization of latent probabilities is used in the analysis solver.

The grid contains 81 equally spaced signed `delta` values between `-log(4)`
and `log(4)` and 101 `chi` values from zero to one. At `chi=0`, both endpoints
equal the IPI; every mortality contrast is zero at `delta=0`. Bounds are nested
in `chi`. At `chi=1`, the interval includes the current-practice value by
construction. Endpoints are sharp pointwise for the fitted law; a single
mechanism need not attain an entire plotted boundary at all `delta` values.

The regions describe treatment-mechanism heterogeneity, not a general model of
unmeasured confounding. They do not quantify sampling, nuisance-estimation,
selection, or imputation uncertainty. They are **not confidence intervals**.

## Running and resuming

From the repository root:

```sh
python run_analysis.py --data-dir /external/derived --output-dir /external/run --workers 2 --threads 2
Rscript make_figures.R --results-dir /external/run/results --output-dir /external/run/figures
```

Input and output directories must be outside the repository. The Python runner
reads `cohort_metadata.json`, both sample Parquet tables, and their metadata
tables. All individual-level fold caches and out-of-fold predictions remain
under the external run's `cache/`. Only aggregate files are written to
`results/`; plotting reads aggregate `curves.csv` only.

`--prepare-only` validates input alignment and writes a frozen analysis plan
without fitting. `--summarize-only` recomputes curves from this run's own validated
caches. Re-running normally resumes completed folds. Input files, analysis code,
package versions, and thread settings are fingerprinted; a mismatch requires a
new output directory. No previous private prediction archive is needed.

Use `--verify-against expected/curves.csv` to compare all aggregate grid rows and
numeric columns against a supplied aggregate reference with the same current
sample names. Verification writes maximum absolute discrepancies and fails above
the default `1e-8` absolute tolerance. Matching historical estimates most closely
requires the pinned package versions and original data release. Small differences
can arise across numerical libraries or CPU implementations.

## Validation

Run the independent sensitivity tests with:

```sh
python -m unittest discover -s tests -p 'test_sensitivity.py' -v
```

The test checks sixty independently formulated finite-support linear programs,
including exact optimizer witness atoms, against the analytic solver. It also
checks nesting, zero/one limits, treatment relabeling symmetry, deterministic
propensity strata, and primal-dual certificates. Runtime validation checks
patient alignment, fold separation, probability ranges, complete held-out
predictions, endpoint nesting, budget feasibility, zero contrasts at the
reference intervention, and the global-budget limiting cases.

The mortality figure displays the IPI in blue and selected mechanism-sensitivity
regions in gray, with matching boundary colors and a legend above the axes.
The horizontal axis is linear in signed `delta`. The separate LR-use figure
shows the implied treatment-allocation changes for each sample.
