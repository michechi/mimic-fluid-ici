"""Command-line orchestration; raw inputs and the source checkout remain read-only."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

REPOSITORY = Path(__file__).resolve().parents[3]
REQUIRED_TABLES = [
    "hosp/patients", "hosp/admissions", "hosp/transfers", "hosp/d_labitems",
    "hosp/services", "hosp/prescriptions", "hosp/emar", "hosp/emar_detail",
    "hosp/microbiologyevents", "hosp/labevents", "hosp/diagnoses_icd",
    "icu/icustays", "icu/d_items", "icu/inputevents", "icu/chartevents",
    "icu/outputevents", "icu/procedureevents",
]
STAGES = ["stage_core", "stage_medications", "stage_clinical", "build_eligibility",
          "build_baseline", "validate_baseline", "finalize"]


def overlaps(left, right):
    """True for equal directories or either ancestor relationship, following links."""
    left, right = Path(left).resolve(), Path(right).resolve()
    return left == right or left in right.parents or right in left.parents


def validate_paths(raw_data, work_dir, output_dir, repository=REPOSITORY):
    raw_data, work_dir, output_dir, repository = map(Path, [raw_data, work_dir, output_dir, repository])
    raw_data, work_dir, output_dir, repository = [p.resolve() for p in [raw_data, work_dir, output_dir, repository]]
    if not raw_data.is_dir():
        raise ValueError("--raw-data must be an existing directory containing hosp/ and icu/")
    for name, path in [("work", work_dir), ("output", output_dir)]:
        if overlaps(path, raw_data) or overlaps(path, repository):
            raise ValueError(f"The {name} directory must be outside, and not contain, the raw data and repository")
        if path.exists() and (not path.is_dir() or any(path.iterdir())):
            raise ValueError(f"The {name} directory must be new or empty; existing extractions are never overwritten")
    if overlaps(work_dir, output_dir):
        raise ValueError("--work-dir and --output-dir must be disjoint directories")
    files = []
    for table in REQUIRED_TABLES:
        matches = [raw_data / (table + suffix) for suffix in [".csv.gz", ".csv"]]
        available = [p for p in matches if p.is_file()]
        if not available:
            raise ValueError(f"Missing required source table: {table}.csv.gz (or .csv)")
        files.append(available[0])
    return raw_data, work_dir, output_dir, files


def main(argv=None):
    parser = argparse.ArgumentParser(description="Recreate the Imputed sample and Complete-case sample from licensed raw MIMIC-IV 3.1 CSV files.")
    parser.add_argument("--raw-data", "--mimic-dir", dest="raw_data", type=Path, required=True, help="Directory containing raw hosp/ and icu/ subdirectories")
    parser.add_argument("--work-dir", type=Path, required=True, help="New private directory for staged restricted data")
    parser.add_argument("--output-dir", type=Path, required=True, help="New private directory for sample tables and audit files")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--memory-limit", default="16GB")
    parser.add_argument("--check-inputs", action="store_true", help="Check paths and required files without reading records or creating outputs")
    args = parser.parse_args(argv)
    if args.threads < 1 or not re.fullmatch(r"[1-9][0-9]*(?:MB|GB)", args.memory_limit):
        parser.error("--threads must be positive; --memory-limit must look like 16GB or 512MB")
    try:
        raw_data, work_dir, output_dir, files = validate_paths(args.raw_data, args.work_dir, args.output_dir)
    except ValueError as exc:
        parser.error(str(exc))
    config_path = REPOSITORY / "config" / "cohort.json"
    config = json.loads(config_path.read_text())
    fixed = {"minimum_age": 18, "icu_hours_lower_inclusive": 6,
             "icu_hours_upper_exclusive": 48, "infection_hours": 24,
             "hypotension_hours": 2, "MAP_below": 65, "SBP_below": 90}
    if any(config["clinical_eligibility"].get(k) != v for k, v in fixed.items()):
        raise ValueError("Clinical eligibility is the fixed published protocol, not a runtime configuration")
    if config["mimic_version"] != "3.1" or config["age_cap"] != 90 or config["max_missing_nonhistory"] != 4:
        raise ValueError("This reproducibility entrypoint supports only the fixed published cohort protocol")
    if args.check_inputs:
        print(f"Input validation passed: {len(files)} required tables; no data read and no outputs created.")
        return
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "source_file_manifest.json").write_text(json.dumps({
        "files": [{"file": str(p.relative_to(raw_data)), "bytes": p.stat().st_size} for p in files]
    }, indent=2) + "\n")
    environment = os.environ.copy()
    environment.update({
        "FLUID_ICI_RAW_DATA": str(raw_data), "FLUID_ICI_WORK_DIR": str(work_dir),
        "FLUID_ICI_OUTPUT_DIR": str(output_dir), "FLUID_ICI_CONFIG": str(config_path),
        "FLUID_ICI_THREADS": str(args.threads), "FLUID_ICI_MEMORY_LIMIT": args.memory_limit,
        "PYTHONPATH": str(REPOSITORY / "src") + os.pathsep + environment.get("PYTHONPATH", ""),
    })
    for stage in STAGES:
        print(f"\nRunning {stage} ...", flush=True)
        subprocess.run([sys.executable, "-u", "-m", f"fluid_ici.preprocessing.stages.{stage}"],
                       env=environment, check=True)
    print("Both samples are ready. Their tables and all intermediate files remain restricted MIMIC data.")


if __name__ == "__main__":
    main()
