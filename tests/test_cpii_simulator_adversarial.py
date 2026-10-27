from __future__ import annotations

import csv
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.cpii_simulator.compare import (  # noqa: E402
    _pair_comparability,
    cohort_id,
    compare_companies,
    pair_records,
    pairwise_matrix,
    rank_companies,
)
from scripts.cpii_simulator.decompose import decompose_pair  # noqa: E402
from scripts.cpii_simulator.economic_bridge import monetize_pair, read_exposures  # noqa: E402
from scripts.cpii_simulator.engine import load_anchor, read_company_csv, score_row, score_rows  # noqa: E402
from scripts.cpii_simulator.sensitivity import analyze_pair_sensitivity  # noqa: E402
from scripts.cpii_simulator.validate_input import (  # noqa: E402
    validate_company_rows,
    validate_exposure_rows,
)


COMPANY_CSV = ROOT / "data" / "processed" / "cpii_simulator" / "examples" / "fictional_companies.csv"


def exposure(row_id: str) -> dict[str, object]:
    row: dict[str, object] = {
        "observation_id": row_id,
        "currency": "KRW",
        "price_year": "2025",
        "exposure_period": "2025Q4",
        "period_year_fraction": "1",
        "exposure_source_id": "SYNTHETIC",
        "exposure_quality": "SYNTHETIC",
    }
    bases = {
        "revenue": 1.0e12,
        "positive_pretax_income": 1.0e11,
        "average_interest_bearing_debt": 2.0e11,
        "content_investment": 3.0e11,
        "eligible_market_revenue": 2.5e11,
        "scenario_conversion_rate": 0.05,
    }
    for name, value in bases.items():
        for case, factor in (("low", 0.9), ("base", 1.0), ("high", 1.1)):
            row[f"{name}_{case}"] = value * factor
    return row


def write_company_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class AdversarialComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = read_company_csv(COMPANY_CSV)
        cls.scores = score_rows(cls.rows, strict=True)

    def test_headline_outputs_reject_blank_and_duplicate_ids(self) -> None:
        functions = (rank_companies, pair_records, pairwise_matrix)
        for function in functions:
            with self.subTest(function=function.__name__, defect="blank"):
                bad = [dict(self.scores[0]), dict(self.scores[1])]
                bad[1]["observation_id"] = "  "
                with self.assertRaisesRegex(ValueError, "nonblank observation_id"):
                    function(bad)
            with self.subTest(function=function.__name__, defect="duplicate"):
                bad = [dict(self.scores[0]), dict(self.scores[1])]
                bad[1]["observation_id"] = bad[0]["observation_id"]
                with self.assertRaisesRegex(ValueError, "unique observation_id"):
                    function(bad)

    def test_headline_outputs_reject_partial_or_nonfinite_scores(self) -> None:
        partial = score_rows(self.rows[:2], strict=False)
        for function in (rank_companies, pair_records, pairwise_matrix):
            with self.subTest(function=function.__name__, defect="partial"):
                with self.assertRaisesRegex(ValueError, "strict all-active"):
                    function(partial)
            with self.subTest(function=function.__name__, defect="nonfinite"):
                bad = [dict(self.scores[0]), dict(self.scores[1])]
                bad[1]["CPII"] = math.nan
                with self.assertRaisesRegex(ValueError, "finite CPII"):
                    function(bad)

    def test_mixed_versions_are_rejected_by_all_headline_paths(self) -> None:
        bad = [dict(self.scores[0]), dict(self.scores[1])]
        bad[1]["anchor_version"] = "OTHER-ANCHOR"
        for function in (rank_companies, pair_records, pairwise_matrix):
            with self.subTest(function=function.__name__):
                with self.assertRaisesRegex(ValueError, "cannot mix"):
                    function(bad)
        with self.assertRaisesRegex(ValueError, "anchor_version"):
            decompose_pair(bad[0], bad[1])

    def test_cohort_serialization_has_no_delimiter_collision(self) -> None:
        left = {
            "sector": "alpha::beta",
            "service_scope": "gamma",
            "focal_market": "Korea",
            "reporting_period": "2025Q4",
            "benchmark_id": "BM",
        }
        right = {
            "sector": "alpha",
            "service_scope": "beta::gamma",
            "focal_market": "Korea",
            "reporting_period": "2025Q4",
            "benchmark_id": "BM",
        }
        self.assertNotEqual(cohort_id(left), cohort_id(right))

    def test_blank_cohort_fields_are_incomparable_even_when_both_blank(self) -> None:
        left, right = dict(self.rows[0]), dict(self.rows[1])
        left["service_scope"] = right["service_scope"] = ""
        comparable, mismatches = _pair_comparability(left, right)
        self.assertFalse(comparable)
        self.assertIn("service_scope", mismatches)

    def test_unknown_or_blank_construction_mode_never_gets_special_label(self) -> None:
        for bad_mode in ("", "garbage"):
            scored = [dict(self.scores[0]), dict(self.scores[1])]
            scored[0]["construction_mode"] = bad_mode
            record = pair_records(scored)[0]
            self.assertEqual(record["pair_type"], "structural_burden_gap")
            self.assertEqual(record["reverse_discrimination_label_eligible"], "no")

    def test_unsafe_ids_are_rejected_before_pair_ids_are_built(self) -> None:
        for unsafe_id in ("lowercase", "A__vs__B", "A*", "A?", "A~", " A", "A" * 65):
            with self.subTest(unsafe_id=unsafe_id):
                bad = [dict(self.scores[0]), dict(self.scores[1])]
                bad[1]["observation_id"] = unsafe_id
                with self.assertRaisesRegex(ValueError, "invalid observation_id"):
                    pair_records(bad)

    def test_programmatic_comparison_requires_adjustment_and_valid_factor(self) -> None:
        unadjusted = [dict(row) for row in self.rows[:2]]
        unadjusted[0]["market_common_exposure_adjusted"] = "no"
        with self.assertRaisesRegex(ValueError, "market_common_exposure_adjusted=yes"):
            compare_companies(unadjusted)
        bad_factor = [dict(row) for row in self.rows[:2]]
        bad_factor[0]["company_exposure_factor"] = "nan"
        with self.assertRaisesRegex(ValueError, "company_exposure_factor"):
            compare_companies(bad_factor)

    def test_comparability_whitespace_is_not_silently_normalized(self) -> None:
        left, right = dict(self.rows[0]), dict(self.rows[1])
        left["service_scope"] = right["service_scope"] = " integrated_content "
        comparable, mismatches = _pair_comparability(left, right)
        self.assertFalse(comparable)
        self.assertIn("service_scope", mismatches)

    def test_score_output_retains_adjustment_audit_fields(self) -> None:
        score = self.scores[0]
        self.assertEqual(score["market_common_exposure_adjusted"], "yes")
        self.assertEqual(score["company_exposure_factor"], self.rows[0]["company_exposure_factor"])
        self.assertEqual(score["source_note"], self.rows[0]["source_note"])

    def test_decomposition_rejects_duplicate_ids_and_overflowed_raw_gap(self) -> None:
        duplicate = [dict(self.scores[0]), dict(self.scores[1])]
        duplicate[1]["observation_id"] = duplicate[0]["observation_id"]
        with self.assertRaisesRegex(ValueError, "unique observation_id"):
            decompose_pair(duplicate[0], duplicate[1])

        overflow = [dict(self.scores[0]), dict(self.scores[1])]
        overflow[0]["raw_effective_tax_rate_gap"] = 1e308
        overflow[1]["raw_effective_tax_rate_gap"] = -1e308
        with self.assertRaisesRegex(ValueError, "finite values and differences"):
            decompose_pair(overflow[0], overflow[1])


class AdversarialCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = read_company_csv(COMPANY_CSV)

    def run_script(self, script: str, *args: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "cpii_simulator" / script), *(str(arg) for arg in args)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_compare_cli_allows_multiple_cohorts(self) -> None:
        rows = [dict(row) for row in self.rows[:3]]
        rows[2]["service_scope"] = "standalone_content"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "companies.csv"
            write_company_csv(input_path, rows)
            result = self.run_script("compare.py", input_path, "--output-dir", root / "out")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((root / "out" / "pair_gap_matrix.csv").exists())
            self.assertIn("WARNING [comparison set] service_scope", result.stdout)

    def test_compare_cli_still_blocks_unadjusted_market_exposure(self) -> None:
        rows = [dict(row) for row in self.rows[:2]]
        rows[1]["market_common_exposure_adjusted"] = "no"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "companies.csv"
            write_company_csv(input_path, rows)
            result = self.run_script("compare.py", input_path, "--output-dir", root / "out")
            self.assertEqual(result.returncode, 1)
            self.assertIn("market_common_exposure_adjusted", result.stderr)

    def test_partial_cli_permits_missing_feature_values(self) -> None:
        rows = [dict(row) for row in self.rows[:2]]
        rows[0]["network_cost_ratio"] = ""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "companies.csv"
            output_path = root / "scores.csv"
            write_company_csv(input_path, rows)
            result = self.run_script("cli.py", input_path, "--output", output_path, "--partial")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with output_path.open("r", encoding="utf-8", newline="") as handle:
                output_rows = list(csv.DictReader(handle))
            self.assertEqual(output_rows[0]["score_mode"], "partial_diagnostic")
            self.assertIn("network_cost_ratio", output_rows[0]["missing_features"])

    def test_scoring_cli_neutralizes_formula_leading_text(self) -> None:
        rows = [dict(row) for row in self.rows[:2]]
        rows[0]["company_name"] = "=2+3"
        rows[0]["source_note"] = " +SUM(1,2)"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "companies.csv"
            output_path = root / "scores.csv"
            write_company_csv(input_path, rows)
            result = self.run_script("cli.py", input_path, "--output", output_path)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with output_path.open("r", encoding="utf-8", newline="") as handle:
                output = list(csv.DictReader(handle))
            self.assertEqual(output[0]["company_name"], "'=2+3")
            self.assertEqual(output[0]["source_note"], "' +SUM(1,2)")

    def test_malformed_or_truncated_csv_fails_without_traceback(self) -> None:
        cases = {
            "truncated.csv": "observation_id,company_name,company_group\nA,Only two fields\n",
            "extra.csv": "observation_id,company_name\nA,Name,EXTRA\n",
            "quote.csv": 'observation_id,company_name\nA,"unterminated\n',
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename, content in cases.items():
                with self.subTest(filename=filename):
                    input_path = root / filename
                    input_path.write_text(content, encoding="utf-8")
                    result = self.run_script("cli.py", input_path, "--output", root / f"{filename}.out.csv")
                    self.assertEqual(result.returncode, 1)
                    self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_csv_validation_rejects_unsafe_id_and_comparability_whitespace(self) -> None:
        rows = [dict(row) for row in self.rows[:2]]
        rows[0]["observation_id"] = "bad-id"
        rows[1]["service_scope"] = " integrated_content "
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "companies.csv"
            write_company_csv(path, rows)
            _, issues = validate_company_rows(path)
        messages = "\n".join(issue.render() for issue in issues)
        self.assertIn("ASCII lowercase", messages)
        self.assertIn("leading or trailing whitespace", messages)


class AdversarialSensitivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = read_company_csv(COMPANY_CSV)

    def test_self_and_incomparable_pairs_are_blocked(self) -> None:
        same = dict(self.rows[0])
        with self.assertRaisesRegex(ValueError, "distinct observation_id"):
            analyze_pair_sensitivity(same, dict(same))
        changed = dict(self.rows[1])
        changed["focal_market"] = "Japan"
        with self.assertRaisesRegex(ValueError, "incomparable pair"):
            analyze_pair_sensitivity(self.rows[0], changed)

    def test_range_triplets_are_validated(self) -> None:
        row_a, row_b = self.rows[:2]
        defects = (
            ("inverted", {row_a["observation_id"]: {"network_cost_ratio": (0.3, 0.2, 0.1)}}),
            ("short", {row_a["observation_id"]: {"network_cost_ratio": (0.1, 0.2)}}),
            ("nonfinite", {row_a["observation_id"]: {"network_cost_ratio": (0.1, math.nan, 0.3)}}),
            ("unknown", {row_a["observation_id"]: {"not_a_feature": (0.1, 0.2, 0.3)}}),
            ("base_mismatch", {row_a["observation_id"]: {"network_cost_ratio": (0.1, 0.19, 0.3)}}),
        )
        for label, ranges in defects:
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    analyze_pair_sensitivity(row_a, row_b, ranges=ranges)

    def test_anchor_is_loaded_once_per_sensitivity_analysis(self) -> None:
        with mock.patch(
            "scripts.cpii_simulator.sensitivity.load_anchor",
            wraps=load_anchor,
        ) as mocked:
            analyze_pair_sensitivity(self.rows[0], self.rows[1])
        self.assertEqual(mocked.call_count, 1)


class AdversarialEconomicBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = read_company_csv(COMPANY_CSV)
        cls.scores = score_rows(cls.rows[:2], strict=True)

    def exposure_map(self) -> dict[str, dict[str, object]]:
        return {
            str(score["observation_id"]): exposure(str(score["observation_id"]))
            for score in self.scores
        }

    @staticmethod
    def variable(result: dict[str, object], name: str) -> dict[str, object]:
        return next(row for row in result["rows"] if row["variable_name"] == name)  # type: ignore[index]

    def test_nonfinite_incomplete_and_inverted_triplets_are_unavailable(self) -> None:
        defects = (
            ("nonfinite", "revenue_base", math.nan),
            ("inverted", "revenue_low", 2.0e12),
            ("incomplete", "revenue_high", None),
        )
        for label, field, value in defects:
            with self.subTest(label=label):
                exposures = self.exposure_map()
                if value is None:
                    exposures[str(self.scores[0]["observation_id"])].pop(field)
                else:
                    exposures[str(self.scores[0]["observation_id"])][field] = value
                record = self.variable(monetize_pair(self.scores[0], self.scores[1], exposures), "network_cost_ratio")
                self.assertEqual(record["availability"], "not_available")
                self.assertIn("missing_or_invalid_exposure", str(record["unavailability_reason"]))

    def test_period_fraction_must_be_common_and_in_unit_interval(self) -> None:
        for left, right in ((0, 0), (1.01, 1.01), (0.5, 1.0)):
            with self.subTest(left=left, right=right):
                exposures = self.exposure_map()
                exposures[str(self.scores[0]["observation_id"])]["period_year_fraction"] = left
                exposures[str(self.scores[1]["observation_id"])]["period_year_fraction"] = right
                record = self.variable(monetize_pair(self.scores[0], self.scores[1], exposures), "funding_cost_spread")
                self.assertEqual(record["availability"], "not_available")

    def test_conversion_rate_cannot_exceed_one(self) -> None:
        exposures = self.exposure_map()
        exposures[str(self.scores[0]["observation_id"])]["scenario_conversion_rate_high"] = 1.1
        result = monetize_pair(self.scores[0], self.scores[1], exposures)
        transfer = self.variable(result, "cross_market_transfer_index")
        network = self.variable(result, "network_cost_ratio")
        self.assertEqual(transfer["availability"], "not_available")
        self.assertEqual(network["availability"], "available")

    def test_exposure_id_and_period_mismatch_are_unavailable(self) -> None:
        exposures = self.exposure_map()
        exposures[str(self.scores[0]["observation_id"])]["observation_id"] = "WRONG"
        result = monetize_pair(self.scores[0], self.scores[1], exposures)
        self.assertEqual(
            self.variable(result, "network_cost_ratio")["unavailability_reason"],
            "exposure_observation_id_mismatch",
        )

        exposures = self.exposure_map()
        exposures[str(self.scores[0]["observation_id"])]["exposure_period"] = "2025Q4"
        exposures[str(self.scores[1]["observation_id"])]["exposure_period"] = "2025"
        result = monetize_pair(self.scores[0], self.scores[1], exposures)
        self.assertEqual(
            self.variable(result, "network_cost_ratio")["unavailability_reason"],
            "exposure_period_mismatch",
        )

    def test_missing_source_or_invalid_quality_is_unavailable(self) -> None:
        for field, value, reason in (
            ("exposure_source_id", "", "missing_exposure_source_id"),
            ("exposure_quality", "UNKNOWN", "invalid_exposure_quality"),
        ):
            with self.subTest(field=field):
                exposures = self.exposure_map()
                exposures[str(self.scores[0]["observation_id"])][field] = value
                result = monetize_pair(self.scores[0], self.scores[1], exposures)
                record = self.variable(result, "network_cost_ratio")
                self.assertEqual(record["availability"], "not_available")
                self.assertEqual(record["unavailability_reason"], reason)

    def test_exposure_validator_predicts_cross_company_time_basis_failure(self) -> None:
        rows = [exposure(str(score["observation_id"])) for score in self.scores]
        rows[0]["exposure_period"] = "2025Q4"
        rows[1]["exposure_period"] = "2025"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "exposures.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            issues = validate_exposure_rows(path, self.rows[:2])
        self.assertTrue(
            any(
                issue.severity == "ERROR" and issue.field == "exposure_period"
                for issue in issues
            )
        )

    def test_string_and_integer_price_years_compare_equal_and_audit_fields_survive(self) -> None:
        exposures = self.exposure_map()
        exposures[str(self.scores[0]["observation_id"])]["price_year"] = 2025
        result = monetize_pair(self.scores[0], self.scores[1], exposures)
        record = self.variable(result, "cross_market_transfer_index")
        self.assertEqual(record["availability"], "available")
        self.assertEqual(record["price_year"], "2025")
        self.assertEqual(record["exposure_period"], "2025Q4")
        self.assertEqual(record["exposure_source_id_a"], "SYNTHETIC")
        self.assertEqual(record["exposure_quality_b"], "SYNTHETIC")
        self.assertAlmostEqual(float(record["conversion_rate_a_base"]), 0.05)

    def test_bad_score_version_or_raw_value_is_rejected(self) -> None:
        changed = dict(self.scores[1])
        changed["method_version"] = "OTHER"
        with self.assertRaisesRegex(ValueError, "cannot mix"):
            monetize_pair(self.scores[0], changed, self.exposure_map())
        changed = dict(self.scores[1])
        changed["raw_network_cost_ratio"] = math.inf
        with self.assertRaisesRegex(ValueError, "finite raw score feature"):
            monetize_pair(self.scores[0], changed, self.exposure_map())

    def test_exposure_reader_rejects_duplicate_ids(self) -> None:
        rows = [exposure("A"), exposure("A")]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "exposures.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(ValueError, "duplicate exposure"):
                read_exposures(path)


class PartialEligibilityTests(unittest.TestCase):
    def test_uncomputed_partial_score_is_ineligible(self) -> None:
        row = read_company_csv(COMPANY_CSV)[0]
        for name in load_anchor()["profiles"]:
            if name in row:
                row[name] = ""
        score = score_row(row, strict=False)
        self.assertIsNone(score["CPII"])
        self.assertEqual(score["score_eligible"], "no")

    def test_computed_partial_score_is_still_not_headline_eligible(self) -> None:
        row = read_company_csv(COMPANY_CSV)[0]
        row["network_cost_ratio"] = ""
        score = score_row(row, strict=False)
        self.assertIsNotNone(score["CPII"])
        self.assertEqual(score["score_eligible"], "no")


if __name__ == "__main__":
    unittest.main()
