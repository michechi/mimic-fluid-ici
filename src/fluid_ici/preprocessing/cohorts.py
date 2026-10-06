"""Value-preserving quality rules and sample selection; no statistical imputation."""
from __future__ import annotations

import numpy as np
import pandas as pd


def clean_urine(values):
    """Quarantine negative or >6000-mL six-hour net recordings, retaining missingness."""
    invalid = values.lt(0) | values.gt(6000)
    return values.mask(invalid), invalid


def mortality_outcome(data):
    """Inclusive recorded calendar-day 0–28 outcome and the original timing checks."""
    before = (data.death_date.notna() & (data.death_date < data.t0.dt.normalize()))
    before |= data.hospital_death_time.notna() & (data.hospital_death_time < data.t0)
    discharged = data.dischtime.isna() | (data.dischtime <= data.t0)
    invalid = before | discharged
    retained = data.loc[~invalid].copy()
    if ((retained.hospital_expire_flag == 1) & retained.death_date.isna()).any():
        raise ValueError("A recorded inpatient death lacks a usable date")
    days = (retained.death_date - retained.t0.dt.normalize()).dt.days
    retained["Y"] = days.between(0, 28).fillna(False).astype("int8")
    audit = {
        "clinical_index_n": len(data),
        "after_recorded_death_n": int(before.sum()),
        "at_or_after_discharge_or_missing_discharge_n": int(discharged.sum()),
        "union_excluded_n": int(invalid.sum()),
        "retained_n": len(retained),
        "later_index_substitution": False,
    }
    return retained, audit


def sample_masks(data, covariates, history, max_missing=4):
    """Determine membership using the fixed fields after clinical quality cleaning."""
    if len(covariates) != 64 or len(set(covariates)) != 64 or len(history) != 17:
        raise ValueError("Expected exactly 64 unique clinical fields and 17 history fields")
    other = [c for c in covariates if c not in history]
    if len(other) != 47 or not set(history).issubset(covariates):
        raise ValueError("History and other covariate lists are inconsistent")
    if data[["A", "Y"]].isna().any().any():
        raise ValueError("Treatment and outcome must be observed")
    if not data["A"].isin([0, 1]).all() or not data["Y"].isin([0, 1]).all():
        raise ValueError("Treatment and outcome must be binary")
    available_history = data[history].notna().all(axis=1)
    absent_history = data[history].isna().all(axis=1)
    if not (available_history | absent_history).all():
        raise ValueError("Unexpected partially observed history block")
    missing_other = data[other].isna().sum(axis=1)
    complete = data[covariates].notna().all(axis=1)
    imputed = available_history & missing_other.le(max_missing)
    if (complete & ~imputed).any():
        raise ValueError("Complete cases must be contained in the imputed sample")
    return {"complete_case": complete, "imputed": imputed}, available_history, missing_other


def select_samples(data, config):
    """Return deterministically ordered raw covariates plus separate keyed metadata."""
    covariates = config["covariates"]
    data = data.sort_values(["subject_id", "decision_id"]).reset_index(drop=True)
    if not data.subject_id.is_unique or not data.decision_id.is_unique:
        raise ValueError("Source must have exactly one selected decision per person")
    masks, available_history, missing_other = sample_masks(
        data, covariates, config["history_covariates"], config["max_missing_nonhistory"]
    )
    samples = {}
    for key, mask in masks.items():
        analysis = data.loc[mask, ["decision_id", "A", "Y", *covariates]].copy().reset_index(drop=True)
        analysis["x_age"] = analysis.x_age.clip(upper=config["age_cap"])
        analysis[["A", "Y"]] = analysis[["A", "Y"]].astype("int8")
        metadata = data.loc[mask, ["decision_id", "subject_id", "hadm_id", "stay_id", "t0"]].copy().reset_index(drop=True)
        numeric = analysis.select_dtypes(include="number")
        if not np.isfinite(numeric.astype(float).fillna(0)).all().all():
            raise ValueError("Nonfinite numerical values in selected inputs")
        if not analysis.decision_id.equals(metadata.decision_id):
            raise ValueError("Analysis and metadata are misaligned")
        samples[key] = (analysis, metadata)
    membership = data[["decision_id", "subject_id"]].copy()
    membership["history_available"] = available_history.to_numpy()
    membership["missing_other47"] = missing_other.to_numpy()
    for key, mask in masks.items():
        membership[key] = mask.to_numpy()
    return samples, membership
