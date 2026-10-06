"""Synthetic regression checks: run without access to any MIMIC records."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from .cohorts import clean_urine, mortality_outcome, sample_masks, select_samples
from .pipeline import REPOSITORY, REQUIRED_TABLES, validate_paths


class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((REPOSITORY / "config" / "cohort.json").read_text())

    def test_clinical_types_partition_the_fixed_64_fields(self):
        groups = [self.config[key] for key in ["continuous_covariates", "discrete_covariates", "categorical_covariates"]]
        self.assertEqual([len(x) for x in groups], [35, 24, 5])
        flat = sum(groups, [])
        self.assertEqual(len(set(flat)), 64)
        self.assertEqual(set(flat), set(self.config["covariates"]))

    def test_calendar_endpoint_and_no_replacement(self):
        t0 = pd.Timestamp("2020-01-01 12:00:00")
        data = pd.DataFrame({
            "t0": [t0] * 7,
            "death_date": pd.to_datetime(["2020-01-01", "2020-01-29", "2020-01-30", None,
                                           "2019-12-31", "2020-01-01", None]),
            "hospital_death_time": pd.to_datetime([None, None, None, None, None, "2020-01-01 11:59", None]),
            "dischtime": pd.to_datetime(["2020-02-01 00:00"] * 6 + ["2020-01-01 12:00"]),
            "hospital_expire_flag": [0] * 7,
        })
        retained, audit = mortality_outcome(data)
        self.assertEqual(retained.index.tolist(), [0, 1, 2, 3])
        self.assertEqual(retained.Y.tolist(), [1, 1, 0, 0])
        self.assertEqual(audit["union_excluded_n"], 3)
        self.assertFalse(audit["later_index_substitution"])

    def test_urine_bounds_are_missing_not_zero(self):
        values = pd.Series([-1.0, 0.0, 6000.0, 6000.1, np.nan])
        result, bad = clean_urine(values)
        self.assertEqual(bad.tolist(), [True, False, False, True, False])
        self.assertEqual(result.iloc[1:3].tolist(), [0, 6000])
        self.assertTrue(result.iloc[[0, 3, 4]].isna().all())

    def test_selection_uses_original_fields_not_encoding(self):
        covariates, history = self.config["covariates"], self.config["history_covariates"]
        other = [x for x in covariates if x not in history and x != "x_age"]
        data = pd.DataFrame(1.0, index=range(4), columns=covariates)
        data[["A", "Y"]] = 0
        data["decision_id"] = [40, 30, 20, 10]
        data["subject_id"] = [4, 3, 2, 1]
        data["hadm_id"] = [104, 103, 102, 101]
        data["stay_id"] = [204, 203, 202, 201]
        data["t0"] = pd.Timestamp("2020-01-01")
        data["x_age"] = 95.0
        data.loc[1, other[:4]] = np.nan
        data.loc[2, other[:5]] = np.nan
        data.loc[3, history] = np.nan
        samples, membership = select_samples(data, self.config)
        complete, _ = samples["complete_case"]
        imputed, identifiers = samples["imputed"]
        self.assertEqual(complete.decision_id.tolist(), [40])
        self.assertEqual(imputed.decision_id.tolist(), [30, 40])
        self.assertEqual(identifiers.subject_id.tolist(), [3, 4])
        self.assertEqual(imputed[covariates].isna().sum().sum(), 4)
        self.assertEqual(imputed.x_age.tolist(), [90, 90])
        self.assertEqual(data.x_age.tolist(), [95] * 4)
        self.assertEqual(membership.subject_id.tolist(), [1, 2, 3, 4])
        self.assertEqual(len(imputed.columns), 67)
        data.loc[0, history[0]] = np.nan
        with self.assertRaisesRegex(ValueError, "partially observed"):
            sample_masks(data, covariates, history)

    def test_destination_guards_and_source_preflight(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            raw, repo = base / "raw", base / "repository"
            raw.mkdir()
            repo.mkdir()
            for table in REQUIRED_TABLES:
                file = raw / (table + ".csv.gz")
                file.parent.mkdir(exist_ok=True)
                file.touch()
            work, output = base / "work", base / "output"
            result = validate_paths(raw, work, output, repo)
            self.assertEqual(len(result[-1]), 17)
            self.assertFalse(work.exists())
            for bad_work in [raw / "derived", repo / "derived", base]:
                with self.assertRaises(ValueError):
                    validate_paths(raw, bad_work, output, repo)
            with self.assertRaises(ValueError):
                validate_paths(raw, work, work / "output", repo)
            alias = base / "alias"
            alias.symlink_to(raw, target_is_directory=True)
            with self.assertRaises(ValueError):
                validate_paths(raw, alias / "derived", output, repo)
            output.mkdir()
            (output / "existing.txt").write_text("synthetic")
            with self.assertRaisesRegex(ValueError, "never overwritten"):
                validate_paths(raw, work, output, repo)


if __name__ == "__main__":
    unittest.main()
