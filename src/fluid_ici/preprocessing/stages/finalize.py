"""Link the prespecified endpoint, apply quality rules, and export both samples."""
import hashlib
import json
import platform
from datetime import datetime, timezone
from importlib.metadata import version

import pandas as pd

from .settings import *
from ..cohorts import clean_urine, mortality_outcome, select_samples


def main():
    destination = Path(os.environ["FLUID_ICI_OUTPUT_DIR"])
    config_path = Path(os.environ["FLUID_ICI_CONFIG"])
    config = json.loads(config_path.read_text())
    con = connect()
    quality = json.loads((OUT / "baseline_quality.json").read_text())
    if quality["n"] <= 0 or any(quality["pretreatment_timing_violations"].values()):
        raise ValueError("Baseline temporal validation failed")

    # The endpoint uses all recorded admissions for eligible people, exactly as
    # in the original linkage. Patient death date takes precedence if available.
    save(con, "outcome_admissions", f'''SELECT subject_id::BIGINT subject_id,
    hadm_id::BIGINT hadm_id,dischtime::TIMESTAMP dischtime,
    deathtime::TIMESTAMP deathtime,hospital_expire_flag::INTEGER hospital_expire_flag
    FROM {raw('hosp/admissions')} WHERE subject_id::BIGINT IN
    (SELECT subject_id FROM {pq('primary_index')})''')
    save(con, "outcome_patient_dates", f'''SELECT subject_id::BIGINT subject_id,
    dod::DATE dod FROM {raw('hosp/patients')} WHERE subject_id::BIGINT IN
    (SELECT subject_id FROM {pq('primary_index')})''')
    save(con, "mortality_linked", f'''WITH hd AS
    (SELECT subject_id,min(deathtime) hospital_death_time
     FROM {pq('outcome_admissions')} GROUP BY subject_id)
    SELECT b.*,a.dischtime,a.hospital_expire_flag,
    a.deathtime index_admission_death_time,p.dod,h.hospital_death_time,
    coalesce(p.dod,h.hospital_death_time::DATE) death_date
    FROM {pq('analysis_baseline')} b
    JOIN {pq('outcome_admissions')} a USING(subject_id,hadm_id)
    JOIN {pq('outcome_patient_dates')} p USING(subject_id)
    LEFT JOIN hd h USING(subject_id)''')
    data = con.execute(f"SELECT * FROM {pq('mortality_linked')} ORDER BY subject_id").fetchdf()
    if len(data) != quality["n"] or not data.subject_id.is_unique:
        raise ValueError("Mortality linkage changed index membership")
    data, timing = mortality_outcome(data)
    # A private intermediate is useful for value-level reproducibility audits;
    # it never belongs in the public repository.
    data.to_parquet(WORK / "endpoint_linked_source.parquet", index=False, compression="zstd")
    con.execute(f"CREATE VIEW ds AS SELECT * FROM {pq('endpoint_linked_source')}")
    con.execute(f'''CREATE TEMP TABLE ongoing AS
    SELECT d.decision_id,d.A,d.t0,f.* EXCLUDE(subject_id,hadm_id,stay_id)
    FROM ds d JOIN {pq('fluid_inputs')} f
    ON f.stay_id=d.stay_id AND f.starttime<d.t0 AND f.endtime>d.t0
    WHERE f.itemid IN (225158,225828) AND f.ml>0
    AND f.ordercomponenttypedescription='Main order parameter'
    AND f.ordercategoryname='02-Fluids (Crystalloids)'
    AND f.ordercategorydescription='Continuous IV'
    AND f.statusdescription IS DISTINCT FROM 'Rewritten' ''')
    supplement = con.execute('''SELECT d.decision_id,
    CASE WHEN count(f.itemid) FILTER(WHERE f.itemid=225158 AND f.storetime<d.t0)=0
    THEN 0 ELSE max(f.rate) FILTER(WHERE f.itemid=225158 AND f.storetime<d.t0
    AND f.rateuom='mL/hour' AND f.rate>0) END x_ongoing_ns_max_rate_ml_h,
    CASE WHEN count(f.itemid) FILTER(WHERE f.itemid=225828 AND f.storetime<d.t0)=0
    THEN 0 ELSE max(f.rate) FILTER(WHERE f.itemid=225828 AND f.storetime<d.t0
    AND f.rateuom='mL/hour' AND f.rate>0) END x_ongoing_lr_max_rate_ml_h,
    max(f.storetime) FILTER(WHERE f.storetime<d.t0) continuous_fluids_latest_available
    FROM ds d LEFT JOIN ongoing f ON f.decision_id=d.decision_id
    GROUP BY d.decision_id,d.t0 ORDER BY d.decision_id''').fetchdf()
    data = data.merge(supplement, on="decision_id", how="left", validate="one_to_one")
    if (data.continuous_fluids_latest_available >= data.t0).any():
        raise ValueError("Ongoing-fluid covariates contain concurrent/future documentation")
    original_urine = data.x_recorded_urine_ml_6h.copy()
    data["x_recorded_urine_ml_6h"], invalid_urine = clean_urine(original_urine)
    data = data.sort_values(["subject_id", "decision_id"]).reset_index(drop=True)
    # Keep original approximate age here; cap it only in the two analysis files.
    data.to_parquet(WORK / "cleaned_source.parquet", index=False, compression="zstd")
    samples, membership = select_samples(data, config)
    membership.to_parquet(destination / "sample_membership.parquet", index=False, compression="zstd")
    audit = {
        "time_zero_integrity": timing,
        "cleaned_source_n": len(data),
        "source_lr_n": int(data.A.sum()),
        "source_mortality_n": int(data.Y.sum()),
        "urine_quarantined_n": int(invalid_urine.sum()),
        "urine_negative_n": int(original_urine.lt(0).sum()),
        "urine_above_6000_n": int(original_urine.gt(6000).sum()),
        "history_available_n": int(membership.history_available.sum()),
        "history_unavailable_n": int((~membership.history_available).sum()),
        "samples": {},
    }
    metadata = {
        "schema_version": 1,
        "mimic_version": config["mimic_version"],
        "covariates": config["covariates"],
        "covariates64": config["covariates"],
        "categorical_covariates": config["categorical_covariates"],
        "continuous_covariates": config["continuous_covariates"],
        "discrete_covariates": config["discrete_covariates"],
        "history_covariates": config["history_covariates"],
        "age_cap": config["age_cap"],
        "max_missing_nonhistory": config["max_missing_nonhistory"],
        "imputation_already_applied": False,
        "row_order": "ascending subject_id; one index decision per person",
        "A": "1: lactated Ringer's; 0: 0.9% saline at the selected ICU bolus",
        "Y": "Recorded death on inclusive calendar days 0 through 28 after t0",
        "samples": {},
    }
    missingness_rows = []
    for key, (analysis, identifiers) in samples.items():
        filename = f"{key}_sample.parquet"
        identifier_file = f"{key}_sample_metadata.parquet"
        analysis.to_parquet(destination / filename, index=False, compression="zstd")
        identifiers.to_parquet(destination / identifier_file, index=False, compression="zstd")
        counts = {
            "n": len(analysis), "lr_n": int(analysis.A.sum()),
            "saline_n": int(analysis.A.eq(0).sum()), "mortality_n": int(analysis.Y.sum()),
            "missing_covariate_cells": int(analysis[config["covariates"]].isna().sum().sum()),
            "age_above_90_capped_n": int(data.loc[data.decision_id.isin(analysis.decision_id), "x_age"].gt(90).sum()),
            "missing_fields_per_person": {
                str(k): int(v) for k, v in analysis[config["covariates"]].isna().sum(axis=1).value_counts().sort_index().items()
            },
        }
        audit["samples"][key] = counts
        metadata["samples"][key] = {
            "label": config["sample_labels"][key], "data_file": filename,
            "metadata_file": identifier_file, "n": len(analysis),
        }
        for column in config["covariates"]:
            count = int(analysis[column].isna().sum())
            missingness_rows.append({"sample": config["sample_labels"][key], "column": column,
                                     "n_missing": count, "fraction_missing": count / len(analysis)})
    pd.DataFrame(missingness_rows).to_csv(destination / "input_missingness.csv", index=False)
    expected = config["expected_counts"]
    audit["published_count_checks"] = {
        "cleaned_source": len(data) == expected["cleaned_source"],
        **{key: len(value[0]) == expected[key] for key, value in samples.items()},
    }
    metadata["created_utc"] = datetime.now(timezone.utc).isoformat()
    metadata["packages"] = {name: version(name) for name in ["duckdb", "numpy", "pandas", "pyarrow"]}
    metadata["python"] = platform.python_version()
    metadata["mimic_code_commit"] = (REF / "mimic_code_commit.txt").read_text().strip()
    metadata["config_sha256"] = hashlib.sha256(config_path.read_bytes()).hexdigest()
    for filename, value in [("cohort_metadata.json", metadata), ("cohort_audit.json", audit)]:
        (destination / filename).write_text(json.dumps(value, indent=2) + "\n")
    if not all(audit["published_count_checks"].values()):
        raise ValueError("Counts differ from the published MIMIC-IV 3.1 extraction; inspect private audit outputs")
    print(json.dumps({"cleaned_source_n": len(data), "samples": audit["samples"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
