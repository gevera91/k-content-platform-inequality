from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.cpii_simulator.decompose import decompose_pair  # noqa: E402
from scripts.cpii_simulator.engine import read_company_csv, score_rows  # noqa: E402


class DecompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        rows = read_company_csv(
            ROOT / "data" / "processed" / "cpii_simulator" / "examples" / "fictional_companies.csv"
        )
        cls.scored = score_rows(rows, strict=True)

    def test_feature_contributions_sum_to_pair_gap(self) -> None:
        result = decompose_pair(self.scored[0], self.scored[1])
        self.assertAlmostEqual(result["feature_contribution_sum"], result["delta_cpii_points_a_minus_b"], places=12)
        self.assertAlmostEqual(result["decomposition_residual"], 0.0, places=12)

    def test_subindex_contributions_sum_to_pair_gap(self) -> None:
        result = decompose_pair(self.scored[0], self.scored[1])
        self.assertAlmostEqual(
            sum(row["cpii_point_contribution"] for row in result["subindices"]),
            result["delta_cpii_points_a_minus_b"],
            places=12,
        )
        for row in result["subindices"]:
            self.assertAlmostEqual(row["cpii_point_contribution"], row["expected_weighted_subindex_difference"], places=12)

    def test_reverse_direction_recovery_feature(self) -> None:
        result = decompose_pair(self.scored[0], self.scored[1])
        investment = next(row for row in result["features"] if row["variable_name"] == "investment_recovery_ratio")
        self.assertLess(investment["raw_difference_a_minus_b"], 0)
        self.assertGreaterEqual(investment["normalized_difference"], 0)
        self.assertEqual(investment["direction_code"], -1)

    def test_absolute_shares_sum_to_one(self) -> None:
        result = decompose_pair(self.scored[0], self.scored[2])
        self.assertAlmostEqual(sum(row["absolute_contribution_share"] for row in result["features"]), 1.0, places=12)
        ranks = sorted(row["absolute_driver_rank"] for row in result["features"])
        self.assertEqual(ranks, list(range(1, 11)))

    def test_pair_reversal_flips_every_contribution(self) -> None:
        forward = decompose_pair(self.scored[0], self.scored[1])
        backward = decompose_pair(self.scored[1], self.scored[0])
        f = {row["variable_name"]: row["cpii_point_contribution"] for row in forward["features"]}
        b = {row["variable_name"]: row["cpii_point_contribution"] for row in backward["features"]}
        for name in f:
            self.assertAlmostEqual(f[name], -b[name], places=12)


if __name__ == "__main__":
    unittest.main()
