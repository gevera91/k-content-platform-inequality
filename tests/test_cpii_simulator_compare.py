from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.cpii_simulator.compare import compare_companies, pair_records, pairwise_matrix  # noqa: E402
from scripts.cpii_simulator.engine import read_company_csv, score_rows  # noqa: E402


class CompareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = read_company_csv(
            ROOT / "data" / "processed" / "cpii_simulator" / "examples" / "fictional_companies.csv"
        )

    def test_two_company_view_equals_n_equals_two(self) -> None:
        result = compare_companies(self.rows[:2])
        direct = score_rows(self.rows[:2], strict=True)
        self.assertEqual([row["CPII"] for row in result["scored"]], [row["CPII"] for row in direct])
        self.assertEqual(len(result["pairs"]), 1)

    def test_n_company_pair_count(self) -> None:
        result = compare_companies(self.rows)
        self.assertEqual(len(result["pairs"]), len(self.rows) * (len(self.rows) - 1) // 2)

    def test_pair_matrix_is_antisymmetric_with_zero_diagonal(self) -> None:
        scored = score_rows(self.rows, strict=True)
        header, matrix_rows = pairwise_matrix(scored)
        ids = header[1:]
        matrix = {row[0]: dict(zip(ids, row[1:])) for row in matrix_rows}
        for a in ids:
            self.assertEqual(matrix[a][a], 0.0)
            for b in ids:
                self.assertAlmostEqual(matrix[a][b], -matrix[b][a], places=12)

    def test_ranking_and_scores_do_not_depend_on_input_order(self) -> None:
        forward = compare_companies(self.rows)
        reverse = compare_companies(list(reversed(self.rows)))
        forward_scores = {row["observation_id"]: row["CPII"] for row in forward["ranking"]}
        reverse_scores = {row["observation_id"]: row["CPII"] for row in reverse["ranking"]}
        self.assertEqual(forward_scores, reverse_scores)

    def test_reverse_discrimination_label_is_strictly_gated(self) -> None:
        scored = score_rows(self.rows, strict=True)
        domestic_foreign = pair_records(scored[:2])[0]
        self.assertEqual(domestic_foreign["pair_type"], "reverse_discrimination_hypothesis_related_structural_burden_gap")
        foreign_foreign = pair_records(scored[1:3])[0]
        self.assertEqual(foreign_foreign["pair_type"], "structural_burden_gap")
        changed = [dict(scored[0]), dict(scored[1])]
        changed[1]["reporting_period"] = "2024Q4"
        incompatible = pair_records(changed)[0]
        self.assertEqual(incompatible["pair_type"], "structural_burden_gap")
        self.assertEqual(incompatible["comparable"], "no")
        self.assertIsNone(incompatible["delta_cpii_points_a_minus_b"])

    def test_incomparable_third_company_does_not_change_valid_pair(self) -> None:
        base = compare_companies(self.rows[:2])
        third = dict(self.rows[2])
        third["reporting_period"] = "2024Q4"
        expanded = compare_companies(self.rows[:2] + [third])
        self.assertEqual(base["pairs"][0]["delta_cpii_points_a_minus_b"], expanded["pairs"][0]["delta_cpii_points_a_minus_b"])
        _, matrix_rows = expanded["matrix"]
        self.assertTrue(any(isinstance(cell, str) and cell.startswith("N/A:") for row in matrix_rows for cell in row[1:]))

    def test_c_grade_blocks_reverse_discrimination_label(self) -> None:
        scored = score_rows(self.rows[:2], strict=True)
        scored[1]["input_quality"] = "C"
        record = pair_records(scored)[0]
        self.assertEqual(record["pair_type"], "structural_burden_gap")
        self.assertEqual(record["reverse_discrimination_label_eligible"], "no")


if __name__ == "__main__":
    unittest.main()
