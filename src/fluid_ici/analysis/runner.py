"""Portable nested cross-fitting; all individual-level outputs stay external."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import scipy
import sklearn
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold

from . import complete_case_models, imputed_models
from .curves import make_curve
from .sensitivity import tilt

SAMPLES = ("imputed_sample", "complete_case_sample")
SEEDS = (20260907, 20260908, 20260909)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n")


def load_sample(data_dir, sample):
    data_dir = Path(data_dir)
    metadata = json.loads((data_dir / "cohort_metadata.json").read_text())
    columns = metadata["covariates64"]
    if len(columns) != 64 or len(set(columns)) != 64:
        raise ValueError("Exactly 64 ordered, unique clinical fields are required.")
    data = pd.read_parquet(data_dir / f"{sample}.parquet")
    identifiers = pd.read_parquet(data_dir / f"{sample}_metadata.parquet")
    if not data.decision_id.is_unique or not identifiers.decision_id.is_unique:
        raise ValueError("Decision identifiers must be unique.")
    if set(data.decision_id) != set(identifiers.decision_id):
        raise ValueError("Clinical and metadata rows do not match.")
    data = data.merge(identifiers[["decision_id", "subject_id"]], on="decision_id",
                      how="left", validate="one_to_one")
    data = data.sort_values("subject_id").reset_index(drop=True)
    if not data.subject_id.is_unique or data[["A", "Y"]].isna().any().any():
        raise ValueError("Require one decision per patient and observed A and Y.")
    if any(not set(data[c].unique()).issubset({0, 1}) for c in ["A", "Y"]):
        raise ValueError("A and Y must be binary.")
    x = data[columns].copy()
    x["x_age"] = x["x_age"].clip(upper=90)
    if sample == "complete_case_sample":
        if x.isna().any().any():
            raise ValueError("The complete-case table contains missing clinical inputs.")
        # Preserve the frozen complete-case preprocessing, including its numeric
        # ordering. Boolean columns follow its original categorical conversion.
        for column in columns:
            if pd.api.types.is_numeric_dtype(x[column]) and not pd.api.types.is_bool_dtype(x[column]):
                x[column] = pd.to_numeric(x[column]).astype(float)
            else:
                x[column] = x[column].map(str).astype(object)
    else:
        for column in columns:
            if column in imputed_models.NOMINAL:
                x[column] = x[column].map(lambda v: np.nan if pd.isna(v) else str(v)).astype(object)
            else:
                x[column] = pd.to_numeric(x[column], errors="raise").astype(float)
        imputed_models.variable_groups(x)
        history = [c for c in columns if c.startswith("x_history_")]
        if len(history) != 17 or x[history].isna().any().any():
            raise ValueError("Imputed sample requires all 17 history fields observed.")
        if x.drop(columns=history).isna().sum(axis=1).max() > 4:
            raise ValueError("Imputed sample permits at most four missing nonhistory fields.")
    for column in x.select_dtypes(include=np.number):
        if not np.isfinite(x[column].dropna()).all():
            raise ValueError(f"Nonfinite values in {column}.")
    return data, x, columns


def prepare(data_dir, output_dir, threads):
    data_dir, output_dir = Path(data_dir), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for child in ["cache", "results"]:
        (output_dir / child).mkdir(exist_ok=True)
    code_dir = Path(__file__).resolve().parent
    inputs = [data_dir / "cohort_metadata.json"]
    sample_info = {}
    missingness = []
    for sample in SAMPLES:
        data, x, columns = load_sample(data_dir, sample)
        inputs.extend([data_dir / f"{sample}.parquet", data_dir / f"{sample}_metadata.parquet"])
        sample_info[sample] = dict(n=len(data), clinical_input_count=len(columns), columns=columns,
                                  LR=int(data.A.sum()), saline=int((1-data.A).sum()), deaths=int(data.Y.sum()),
                                  missing_cells=int(x.isna().sum().sum()),
                                  patients_with_missing_values=int(x.isna().any(axis=1).sum()))
        missingness.extend(dict(analysis=sample, variable=c, missing_n=int(x[c].isna().sum()),
                               missing_percent=float(100*x[c].isna().mean())) for c in columns)
    complete, _, _ = load_sample(data_dir, "complete_case_sample")
    imputed, _, _ = load_sample(data_dir, "imputed_sample")
    if not set(complete.subject_id).issubset(set(imputed.subject_id)):
        raise ValueError("Complete cases must be nested in the imputed sample.")
    plan = dict(samples=sample_info, seeds=list(SEEDS), outer_folds=5, inner_folds=3,
                threads_per_worker=threads, outer_stratification="A x Y", age_cap=90,
                prediction_order=["propensity", "mu0", "mu1"],
                learner_library=["ridge C=0.1", "histogram boosting: 7 leaves", "histogram boosting: 15 leaves"],
                estimator="Average patient-specific held-out predictions across three partitions before computing empirical plug-in functionals.",
                delta_grid="81 equally spaced signed log-odds shifts from -log(4) to log(4)",
                chi_grid="101 values from 0 to 1; global variance budget; no sampling confidence intervals",
                input_sha256={p.name: sha(p) for p in inputs},
                code_sha256={p.name: sha(p) for p in sorted(code_dir.glob("*.py"))},
                environment=dict(python=sys.version, numpy=np.__version__, pandas=pd.__version__,
                                 scipy=scipy.__version__, sklearn=sklearn.__version__))
    plan_path = output_dir / "analysis_plan.json"
    if plan_path.exists() and json.loads(plan_path.read_text()) != plan:
        raise ValueError("Inputs, code, or environment differ from the saved run. Use a new output directory.")
    write_json(plan_path, plan)
    write_json(output_dir / "results" / "cohort_audit.json", sample_info)
    pd.DataFrame(missingness).to_csv(output_dir / "results" / "input_missingness.csv", index=False)
    return plan


def fit_partition(data_dir, output_dir, sample, seed, threads):
    output_dir = Path(output_dir)
    data, x, _ = load_sample(data_dir, sample)
    library = imputed_models if sample == "imputed_sample" else complete_case_models
    library.THREADS = threads
    a, y = data.A.to_numpy(int), data.Y.to_numpy(int)
    fingerprint = sha(output_dir / "analysis_plan.json")
    output = output_dir / "cache" / f"oof_{sample}_{seed}.npz"
    if output.exists():
        with np.load(output, allow_pickle=False) as f:
            if str(f["fingerprint"]) != fingerprint:
                raise ValueError("Cached prediction fingerprint mismatch.")
            np.testing.assert_array_equal(f["subject_id"], data.subject_id)
            np.testing.assert_array_equal(f["decision_id"], data.decision_id)
        return dict(analysis=sample, seed=seed, status="cached")
    pred = np.full((len(data), 3), np.nan)
    base = np.full((len(data), 3, 3), np.nan)
    folds = np.full(len(data), -1)
    weights = []
    strata = data.A.astype(str) + " / " + data.Y.astype(str)
    splits = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed).split(x, strata)
    for fold, (train_all, test) in enumerate(splits):
        folds[test] = fold
        for j, target in enumerate(["propensity", "mu0", "mu1"]):
            train = train_all if j == 0 else train_all[a[train_all] == j - 1]
            truth = a[train] if j == 0 else y[train]
            if np.intersect1d(train, test).size or np.bincount(truth, minlength=2).min() < 3:
                raise ValueError("Invalid training/test split or insufficient inner-fold classes.")
            cache = output_dir / "cache" / f"{sample}_{seed}_fold{fold}_{target}.npz"
            if cache.exists():
                with np.load(cache, allow_pickle=False) as f:
                    if str(f["fingerprint"]) != fingerprint:
                        raise ValueError("Fold-cache fingerprint mismatch.")
                    np.testing.assert_array_equal(f["test_index"], test)
                    pp, bb, ww, losses = [f[k] for k in ["pred", "base", "weights", "inner_log_loss"]]
            else:
                pp, bb, ww, losses = library.fit_stack(x.iloc[train], truth, x.iloc[test], seed + fold*1000 + j*10000)
                np.savez_compressed(cache, pred=pp, base=bb, weights=ww, inner_log_loss=losses,
                                    test_index=test, fingerprint=fingerprint)
            pred[test, j], base[test, j] = pp, bb
            weights.extend(dict(analysis=sample, seed=seed, fold=fold, target=target, learner=name,
                                weight=float(ww[k]), inner_log_loss=float(losses[k]), training_n=len(train))
                           for k, name in enumerate(library.NAMES))
        print(f"FIT {sample}: seed={seed}, fold={fold+1}/5", flush=True)
    if not np.isfinite(pred).all() or not np.isfinite(base).all() or np.any(folds < 0):
        raise ValueError("Incomplete held-out predictions.")
    if np.any((pred < 0) | (pred > 1)):
        raise ValueError("Invalid predicted probabilities.")
    np.savez_compressed(output, pred=pred, base=base, subject_id=data.subject_id.to_numpy(),
                        decision_id=data.decision_id.to_numpy(), fold=folds, fingerprint=fingerprint)
    write_json(output_dir / "cache" / f"weights_{sample}_{seed}.json", weights)
    return dict(analysis=sample, seed=seed, status="fitted")


def summarize(data_dir, output_dir):
    output_dir = Path(output_dir)
    delta = np.linspace(-np.log(4), np.log(4), 81)
    delta[np.abs(delta) < 1e-12] = 0.
    curves, reports, diagnostics, weights, seed_curves = [], [], [], [], []
    fingerprint = sha(output_dir / "analysis_plan.json")
    for sample in SAMPLES:
        data, _, columns = load_sample(data_dir, sample)
        each = []
        for seed in SEEDS:
            with np.load(output_dir / "cache" / f"oof_{sample}_{seed}.npz", allow_pickle=False) as f:
                if str(f["fingerprint"]) != fingerprint:
                    raise ValueError("Cached prediction fingerprint mismatch.")
                np.testing.assert_array_equal(f["subject_id"], data.subject_id)
                np.testing.assert_array_equal(f["decision_id"], data.decision_id)
                pp = f["pred"].copy()
                each.append(pp)
                arrays = [("ensemble", pp)] + [(name, f["base"][:, :, k].copy()) for k, name in enumerate(imputed_models.NAMES)]
            weights.extend(json.loads((output_dir / "cache" / f"weights_{sample}_{seed}.json").read_text()))
            for learner, pr in arrays:
                baseline = float(np.mean(pr[:, 1] + (pr[:, 2]-pr[:, 1])*pr[:, 0]))
                for d in delta:
                    risk = float(np.mean(pr[:, 1] + (pr[:, 2]-pr[:, 1])*tilt(pr[:, 0], d)))
                    seed_curves.append(dict(analysis=sample, seed=seed, learner=learner, delta=d,
                                            ipi_risk=risk, ipi_difference_pp=100*(risk-baseline)))
        averaged = np.mean(each, axis=0)
        frame, report = make_curve(sample, averaged, len(columns), delta)
        curves.append(frame)
        reports.append(report)
        for target, truth, estimate in [
            ("propensity", data.A.to_numpy(), averaged[:, 0]),
            ("mortality_observed", data.Y.to_numpy(), np.where(data.A.to_numpy(), averaged[:, 2], averaged[:, 1]))]:
            diagnostics.append(dict(analysis=sample, target=target, n=len(data), observed_mean=float(np.mean(truth)),
                                    predicted_mean=float(np.mean(estimate)), log_loss=float(log_loss(truth, estimate)),
                                    brier_score=float(brier_score_loss(truth, estimate)), auc=float(roc_auc_score(truth, estimate))))
        print("BOUNDS " + json.dumps(report), flush=True)
    result = pd.concat(curves, ignore_index=True)
    results = output_dir / "results"
    result.to_csv(results / "curves.csv", index=False)
    result[result.chi == 0].to_csv(results / "ipi_curves.csv", index=False)
    keep_delta = result.delta.map(lambda d: any(np.isclose(d, k) for k in [-np.log(4), -np.log(2), 0, np.log(2), np.log(4)]))
    result[keep_delta & result.chi.isin([0, .02, .1, .25, 1])].to_csv(results / "selected_results.csv", index=False)
    pd.DataFrame(diagnostics).to_csv(results / "model_diagnostics.csv", index=False)
    pd.DataFrame(weights).to_csv(results / "learner_weights.csv", index=False)
    pd.DataFrame(seed_curves).to_csv(results / "seed_and_learner_curves.csv", index=False)
    write_json(results / "validation.json", dict(analyses=reports, patient_ID_alignment_verified=True,
               nested_bounds_verified=True, chi_zero_collapses_to_IPI=True, delta_zero_contrasts_zero=True,
               predictions_averaged_before_functionals=True, no_sampling_or_imputation_confidence_bands=True,
               plan_sha256=fingerprint))
    return result


def verify_aggregates(actual, expected_path, output_dir, tolerance=1e-8):
    expected = pd.read_csv(expected_path)
    keys = ["analysis", "delta", "chi"]
    actual = actual.sort_values(keys).reset_index(drop=True)
    expected = expected.sort_values(keys).reset_index(drop=True)
    if len(actual) != len(expected) or list(actual.analysis) != list(expected.analysis):
        raise ValueError("Expected aggregate rows/sample names differ.")
    fields = [c for c in actual if c != "analysis"]
    differences = {}
    for field in fields:
        np.testing.assert_allclose(actual[field], expected[field], rtol=0, atol=tolerance, err_msg=field)
        differences[field] = float(np.max(np.abs(actual[field]-expected[field])))
    report = dict(passed=True, expected_sha256=sha(expected_path), absolute_tolerance=tolerance,
                  max_absolute_difference_by_column=differences)
    write_json(Path(output_dir) / "results" / "aggregate_reproduction.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--summarize-only", action="store_true")
    parser.add_argument("--verify-against", type=Path, help="Optional published aggregate curves.csv with current sample names.")
    args = parser.parse_args()
    if args.workers < 1 or args.threads < 1:
        parser.error("workers and threads must be positive")
    repository = Path(__file__).resolve().parents[3]
    data_dir, output_dir = args.data_dir.resolve(), args.output_dir.resolve()
    if data_dir == repository or repository in data_dir.parents:
        parser.error("Use a data directory outside the repository for protected cohort tables.")
    if output_dir == repository or repository in output_dir.parents:
        parser.error("Use an output directory outside the repository for protected patient predictions.")
    if output_dir == data_dir or output_dir in data_dir.parents:
        parser.error("The analysis output directory must not contain or replace its input directory.")
    prepare(data_dir, output_dir, args.threads)
    if args.prepare_only:
        print("Inputs and analysis plan validated; no models fitted.")
        return
    if not args.summarize_only:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            jobs = [pool.submit(fit_partition, str(data_dir), str(output_dir), sample, seed, args.threads)
                    for sample in SAMPLES for seed in SEEDS]
            for job in as_completed(jobs):
                print("PARTITION " + json.dumps(job.result()), flush=True)
    actual = summarize(data_dir, output_dir)
    if args.verify_against:
        print("REPRODUCTION " + json.dumps(verify_aggregates(actual, args.verify_against, output_dir)), flush=True)
