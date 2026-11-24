from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.cpii_simulator.compare import pair_records  # noqa: E402
from scripts.cpii_simulator.decompose import decompose_pair  # noqa: E402
from scripts.cpii_simulator.engine import read_company_csv, score_rows  # noqa: E402
from scripts.cpii_simulator.narrative import build_pair_narrative, explain_point_gap  # noqa: E402
from scripts.cpii_simulator.sensitivity import analyze_pair_sensitivity, dependency_warnings  # noqa: E402


class SensitivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = read_company_csv(
            ROOT / "data" / "processed" / "cpii_simulator" / "examples" / "fictional_companies.csv"
        )
        cls.scores = score_rows(cls.rows, strict=True)

    def test_point_one_explanation_has_exact_weighted_position_meaning(self) -> None:
        text = explain_point_gap(0.1)
        self.assertIn("+0.0010", text)
        self.assertIn("0.9%p", text)
        self.assertIn("1.2%p", text)
        self.assertIn("비용·매출의 0.10%나", text)

    def test_tiny_nonzero_gap_is_not_displayed_as_zero(self) -> None:
        text = explain_point_gap(0.004)
        self.assertIn("+0.004점", text)
        self.assertIn("+0.00004", text)
        self.assertNotIn("ΔCPII +0.00점", text)

    def test_low_support_and_overlap_reduced_specs_are_present(self) -> None:
        result = analyze_pair_sensitivity(self.rows[0], self.rows[1])
        names = {row["specification"] for row in result["variants"]}
        self.assertIn("exclude_low_support_features", names)
        self.assertIn("overlap_reduced", names)
        self.assertAlmostEqual(result["low_support_effective_weight"], 2 / 9, places=12)

    def test_no_probability_or_empirical_percentile_claim(self) -> None:
        result = analyze_pair_sensitivity(self.rows[0], self.rows[1])
        self.assertEqual(result["probability_interpretation_allowed"], "no")
        self.assertIsNone(result["empirical_pair_gap_percentile"])
        self.assertIn("insufficient_joint", result["empirical_pair_gap_percentile_status"])
        self.assertIn("not_confidence_interval", result["range_type"])

    def test_dependency_consistency_warning(self) -> None:
        bad = dict(self.rows[0])
        bad["infra_dependency_ratio"] = "0.9"
        self.assertIn(
            "infra_dependency_ratio_inconsistent_with_network_cost_ratio_times_foreign_dependency_ratio",
            dependency_warnings(bad),
        )

    def test_range_crossing_zero_is_difference_unclear(self) -> None:
        left = dict(self.rows[0])
        right = dict(self.rows[0])
        left["observation_id"], right["observation_id"] = "RANGE-A", "RANGE-B"
        ranges = {
            "RANGE-A": {"network_cost_ratio": (0.10, 0.18, 0.30)},
            "RANGE-B": {"network_cost_ratio": (0.10, 0.18, 0.30)},
        }
        result = analyze_pair_sensitivity(left, right, ranges=ranges)
        self.assertEqual(result["interpretation_status"], "difference_unclear")
        self.assertLess(result["sensitivity_min_points"], 0)
        self.assertGreater(result["sensitivity_max_points"], 0)

    def test_narrative_keeps_score_money_and_causality_separate(self) -> None:
        pair = pair_records(self.scores[:2])[0]
        decomposition = decompose_pair(self.scores[0], self.scores[1])
        sensitivity = analyze_pair_sensitivity(self.rows[0], self.rows[1])
        narrative = build_pair_narrative(pair, decomposition, sensitivity)
        self.assertIn("기업 백분위", narrative["disclaimer_ko"])
        self.assertIn("인과효과", narrative["disclaimer_ko"])
        self.assertIn("금액 해석은 비활성화", narrative["economic_interpretation_ko"])

    def test_identical_features_do_not_create_arbitrary_top_drivers(self) -> None:
        pair = {
            "delta_cpii_points_a_minus_b": 0.0,
        }
        decomposition = {
            "features": [
                {
                    "variable_name": "network_cost_ratio",
                    "display_name_ko": "네트워크 비용률",
                    "cpii_point_contribution": 0.0,
                }
            ]
        }
        sensitivity = {
            "interpretation_status": "difference_unclear",
            "sensitivity_min_points": 0.0,
            "sensitivity_max_points": 0.0,
        }
        narrative = build_pair_narrative(pair, decomposition, sensitivity)
        self.assertIn("상위 driver를 선정하지 않습니다", narrative["drivers_ko"])
        self.assertNotIn("+0.00점", narrative["drivers_ko"])


if __name__ == "__main__":
    unittest.main()
