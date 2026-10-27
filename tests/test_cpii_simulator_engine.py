from __future__ import annotations

import csv
import importlib
import json
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from scripts.cpii_simulator.engine import (  # noqa: E402
    DEFAULT_ANCHOR_PATH,
    ScoringError,
    load_anchor,
    normalize_value,
    read_company_csv,
    score_row,
    score_rows,
)


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.anchor = load_anchor()
        cls.examples = read_company_csv(
            ROOT / "data" / "processed" / "cpii_simulator" / "examples" / "fictional_companies.csv"
        )

    def test_anchor_and_method_versions_are_frozen(self) -> None:
        self.assertEqual(self.anchor["anchor_version"], "POOL_SCQ_P01_P99_EMP_RANK_V1")
        self.assertEqual(self.anchor["product_spec_version"], "CPII_FIRM_INPUT_EQW_V1")

    def test_all_examples_score_on_zero_to_one_hundred_scale(self) -> None:
        scored = score_rows(self.examples, self.anchor, strict=True)
        self.assertEqual(len(scored), 4)
        for row in scored:
            self.assertGreaterEqual(row["CPII"], 0.0)
            self.assertLessEqual(row["CPII"], 100.0)
            self.assertEqual(row["observed_feature_count"], 10)
            self.assertIn("research_beta", row["release_status"])

    def test_selected_company_set_does_not_change_scores(self) -> None:
        one = score_row(self.examples[0], self.anchor, strict=True)
        many = score_rows(self.examples, self.anchor, strict=True)[0]
        self.assertEqual(one["CPII"], many["CPII"])
        self.assertEqual(one["normalized_features"], many["normalized_features"])

    def test_strict_mode_rejects_missing_feature(self) -> None:
        incomplete = dict(self.examples[0])
        incomplete["network_cost_ratio"] = ""
        with self.assertRaisesRegex(ScoringError, "missing: network_cost_ratio"):
            score_row(incomplete, self.anchor, strict=True)

    def test_transform_direction_and_clipping(self) -> None:
        profile = self.anchor["profiles"]["investment_recovery_ratio"]
        lower_recovery = normalize_value(1.0, profile)["normalized"]
        higher_recovery = normalize_value(5.0, profile)["normalized"]
        self.assertGreater(lower_recovery, higher_recovery)
        extreme = normalize_value(1e100, profile)
        self.assertTrue(extreme["clipped_low"])

    def test_low_support_mass_point_epsilon_is_warned(self) -> None:
        profile = self.anchor["profiles"]["cross_market_transfer_index"]
        at_zero = normalize_value(0.0, profile)
        epsilon = normalize_value(1e-12, profile)
        self.assertTrue(at_zero["rank_discontinuity_warning"])
        self.assertTrue(epsilon["rank_discontinuity_warning"])
        self.assertGreater(float(epsilon["normalized"]), float(at_zero["normalized"]))
        row = dict(self.examples[0])
        row["cross_market_transfer_index"] = "0.000000000001"
        self.assertIn("rank_discontinuity_warning", score_row(row, self.anchor)["diagnostic_flags"])

    def test_company_percentile_claim_is_disabled(self) -> None:
        score = score_row(self.examples[0], self.anchor)
        self.assertIsNone(score["company_empirical_percentile"])
        self.assertEqual(score["company_empirical_percentile_status"], "insufficient_joint_reference_support")

    def test_exact_parity_with_legacy_normalizer(self) -> None:
        legacy = importlib.import_module("build_cpii_panels")
        with (ROOT / "data" / "processed" / "variable_panel_sector_quarter.csv").open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            source_rows = list(csv.DictReader(handle))
        profiles, inactive = legacy.build_anchor_profiles(source_rows)
        self.assertEqual(set(inactive), {"bundle_leverage_index", "creator_share_ratio"})
        for name, profile in profiles.items():
            frozen_profile = self.anchor["profiles"][name]
            observed = [float(row[name]) for row in source_rows if row.get(name, "").strip()]
            probes = [min(observed), max(observed), sum(observed) / len(observed)]
            for raw in probes:
                expected = legacy.normalize_with_anchor(raw, profile)
                actual = float(normalize_value(raw, frozen_profile)["normalized"])
                self.assertTrue(math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-15), (name, raw))


if __name__ == "__main__":
    unittest.main()
