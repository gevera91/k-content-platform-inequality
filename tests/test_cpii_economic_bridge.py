from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.cpii_simulator.economic_bridge import monetize_pair  # noqa: E402
from scripts.cpii_simulator.engine import read_company_csv, score_rows  # noqa: E402


def exposure(row_id: str, *, revenue: float = 1e12, debt: float = 1e11, investment: float = 2e11) -> dict[str, str]:
    row = {
        "observation_id": row_id,
        "currency": "KRW",
        "price_year": "2025",
        "exposure_period": "2025Q4",
        "period_year_fraction": "1",
        "exposure_source_id": "SYNTHETIC",
        "exposure_quality": "SYNTHETIC",
    }
    bases = {
        "revenue": revenue,
        "positive_pretax_income": revenue * 0.1,
        "average_interest_bearing_debt": debt,
        "content_investment": investment,
        "eligible_market_revenue": revenue * 0.25,
        "scenario_conversion_rate": 0.05,
    }
    for name, value in bases.items():
        for case, factor in (("low", 0.9), ("base", 1.0), ("high", 1.1)):
            adjusted = value * factor if name != "scenario_conversion_rate" else min(1.0, value * factor)
            row[f"{name}_{case}"] = str(adjusted)
    return row


class EconomicBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.company_rows = read_company_csv(
            ROOT / "data" / "processed" / "cpii_simulator" / "examples" / "fictional_companies.csv"
        )
        cls.scores = score_rows(cls.company_rows, strict=True)
        cls.exposures = {row["observation_id"]: exposure(row["observation_id"]) for row in cls.company_rows}

    def test_no_universal_total_is_returned(self) -> None:
        result = monetize_pair(self.scores[0], self.scores[1], self.exposures)
        self.assertIsNone(result["total_amount"])
        self.assertIn("overlap", result["total_status"])
        self.assertTrue(all(row["aggregation_rule"] == "never_auto_sum" for row in result["rows"]))

    def test_network_common_size_formula(self) -> None:
        result = monetize_pair(self.scores[0], self.scores[1], self.exposures)
        row = next(item for item in result["rows"] if item["variable_name"] == "network_cost_ratio")
        expected = (0.180 - 0.105) * 1e12
        self.assertAlmostEqual(row["common_size_amount_base"], expected, places=5)
        self.assertEqual(row["interpretation_class"], "conditional_accounting_equivalent")

    def test_nonmonetizable_variable_stays_nonmonetizable(self) -> None:
        result = monetize_pair(self.scores[0], self.scores[1], self.exposures)
        row = next(item for item in result["rows"] if item["variable_name"] == "foreign_dependency_ratio")
        self.assertEqual(row["availability"], "not_monetizable")
        self.assertIsNone(row["common_size_amount_base"])

    def test_missing_exposure_disables_money_not_score(self) -> None:
        result = monetize_pair(self.scores[0], self.scores[1], {})
        enabled = [row for row in result["rows"] if row["bridge_status"] == "enabled"]
        self.assertTrue(all(row["availability"] == "not_available" for row in enabled))
        self.assertIsNotNone(self.scores[0]["CPII"])

    def test_same_score_gap_can_imply_very_different_amounts(self) -> None:
        base_a = dict(self.company_rows[0])
        base_b = dict(self.company_rows[0])
        base_a["observation_id"], base_b["observation_id"] = "GOLD-A", "GOLD-B"
        base_a["company_group"], base_b["company_group"] = "domestic", "foreign"

        network_a, network_b = dict(base_a), dict(base_b)
        network_a["network_cost_ratio"] = "0.446823515"
        network_b["network_cost_ratio"] = "0.3470713765"
        network_scores = score_rows([network_a, network_b], strict=True)
        network_money = monetize_pair(
            network_scores[0], network_scores[1],
            {"GOLD-A": exposure("GOLD-A", revenue=1e12), "GOLD-B": exposure("GOLD-B", revenue=1e12)},
        )
        network_row = next(row for row in network_money["rows"] if row["variable_name"] == "network_cost_ratio")

        funding_a, funding_b = dict(base_a), dict(base_b)
        funding_a["funding_cost_spread"] = "0"
        funding_b["funding_cost_spread"] = "-0.001999222"
        funding_scores = score_rows([funding_a, funding_b], strict=True)
        funding_money = monetize_pair(
            funding_scores[0], funding_scores[1],
            {"GOLD-A": exposure("GOLD-A", debt=1e11), "GOLD-B": exposure("GOLD-B", debt=1e11)},
        )
        funding_row = next(row for row in funding_money["rows"] if row["variable_name"] == "funding_cost_spread")

        network_gap = network_scores[0]["CPII"] - network_scores[1]["CPII"]
        funding_gap = funding_scores[0]["CPII"] - funding_scores[1]["CPII"]
        self.assertAlmostEqual(network_gap, funding_gap, places=9)
        self.assertAlmostEqual(network_gap, 1.388888888888889, places=9)
        self.assertGreater(network_row["common_size_amount_base"] / funding_row["common_size_amount_base"], 400)


if __name__ == "__main__":
    unittest.main()
