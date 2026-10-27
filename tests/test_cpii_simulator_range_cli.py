from __future__ import annotations

import csv
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
COMPANY_CSV = ROOT / "data" / "processed" / "cpii_simulator" / "examples" / "fictional_companies.csv"
RANGE_CSV = ROOT / "data" / "processed" / "cpii_simulator" / "examples" / "fictional_feature_ranges.csv"
RANGE_FIELDS = [
    "observation_id",
    "variable_name",
    "low",
    "base",
    "high",
    "range_type",
    "source_id",
]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, strict=True))


def write_rows(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class FeatureRangeCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.companies = read_rows(COMPANY_CSV)
        cls.ranges = read_rows(RANGE_CSV)
        cls.company_fields = list(cls.companies[0])

    def run_compare(
        self,
        company_path: Path,
        output_dir: Path,
        range_path: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            PYTHON,
            str(ROOT / "scripts" / "cpii_simulator" / "compare.py"),
            str(company_path),
            "--output-dir",
            str(output_dir),
        ]
        if range_path is not None:
            command.extend(["--feature-ranges", str(range_path)])
        return subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_example_ranges_generate_pair_summary_and_variants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            result = self.run_compare(COMPANY_CSV, output, RANGE_CSV)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            summaries = read_rows(output / "sensitivity_summary.csv")
            variants = read_rows(output / "sensitivity_variants.csv")
            self.assertEqual(len(summaries), 6)
            self.assertEqual(len(variants), 36)
            self.assertTrue(all(row["input_range_assessed"] == "yes" for row in summaries))
            self.assertTrue(all(row["input_range_feature_count_a"] == "10" for row in summaries))
            self.assertTrue(all(row["input_range_feature_count_b"] == "10" for row in summaries))
            self.assertEqual(
                {row["category"] for row in variants},
                {"baseline", "method_specification", "input_range"},
            )

    def test_incomparable_pairs_are_skipped_and_empty_outputs_keep_headers(self) -> None:
        companies = [dict(row) for row in self.companies[:2]]
        companies[1]["service_scope"] = "different_scope"
        ranges = [
            dict(row)
            for row in self.ranges
            if row["observation_id"] in {companies[0]["observation_id"], companies[1]["observation_id"]}
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            company_path = root / "companies.csv"
            range_path = root / "ranges.csv"
            write_rows(company_path, companies, self.company_fields)
            write_rows(range_path, ranges, RANGE_FIELDS)
            result = self.run_compare(company_path, root / "out", range_path)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("1 incomparable pair(s) skipped", result.stdout)
            self.assertEqual(read_rows(root / "out" / "sensitivity_summary.csv"), [])
            self.assertEqual(read_rows(root / "out" / "sensitivity_variants.csv"), [])

    def test_invalid_range_rows_fail_cleanly(self) -> None:
        base = dict(self.ranges[0])
        cases: dict[str, list[dict[str, str]]] = {}
        unknown = dict(base)
        unknown["observation_id"] = "UNKNOWN-ID"
        cases["unknown"] = [unknown]
        cases["duplicate"] = [dict(base), dict(base)]
        nonfinite = dict(base)
        nonfinite["low"] = "nan"
        cases["nonfinite"] = [nonfinite]
        inverted = dict(base)
        inverted["low"], inverted["high"] = "99", "-99"
        cases["inverted"] = [inverted]
        bad_type = dict(base)
        bad_type["range_type"] = "confidence_interval"
        cases["range_type"] = [bad_type]
        no_source = dict(base)
        no_source["source_id"] = "   "
        cases["source"] = [no_source]
        wrong_base = dict(base)
        wrong_base["base"] = str(float(base["base"]) + 0.01)
        wrong_base["high"] = str(float(wrong_base["base"]) + 0.01)
        cases["base"] = [wrong_base]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, rows in cases.items():
                with self.subTest(name=name):
                    path = root / f"{name}.csv"
                    write_rows(path, rows, RANGE_FIELDS)
                    result = self.run_compare(COMPANY_CSV, root / f"out-{name}", path)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("FAIL comparison:", result.stderr)
                    self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_malformed_range_csv_fails_without_traceback(self) -> None:
        malformed = {
            "header.csv": "observation_id,variable_name,low,base,high,range_type\n",
            "extra.csv": (
                ",".join(RANGE_FIELDS)
                + "\nSYN-A,effective_tax_rate_gap,-.03,-.02,-.01,assumption,SRC,EXTRA\n"
            ),
            "quote.csv": ",".join(RANGE_FIELDS) + '\nSYN-A,"unterminated\n',
            "empty.csv": ",".join(RANGE_FIELDS) + "\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, text in malformed.items():
                with self.subTest(name=name):
                    path = root / name
                    path.write_text(text, encoding="utf-8")
                    result = self.run_compare(COMPANY_CSV, root / f"out-{name}", path)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("FAIL comparison:", result.stderr)
                    self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_text_cells_are_neutralized_against_csv_formula_injection(self) -> None:
        companies = [dict(row) for row in self.companies[:2]]
        companies[0]["company_name"] = "=2+3"
        companies[0]["source_note"] = " +SUM(1,2)"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            company_path = root / "companies.csv"
            write_rows(company_path, companies, self.company_fields)
            result = self.run_compare(company_path, root / "out")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            score = read_rows(root / "out" / "company_scores.csv")[0]
            pair = read_rows(root / "out" / "pair_gaps.csv")[0]
            self.assertEqual(score["company_name"], "'=2+3")
            self.assertEqual(score["source_note"], "' +SUM(1,2)")
            self.assertEqual(pair["company_name_a"], "'=2+3")


if __name__ == "__main__":
    unittest.main()
