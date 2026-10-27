import csv
import itertools
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from review_strengthening_20260915 import weighted_minimum


class ReportReviewChecks(unittest.TestCase):
    def rows(self, name):
        with (ROOT / "outputs/tables/review_20260915" / name).open(newline="") as f:
            return list(csv.DictReader(f))

    def test_weight_box_matches_dense_grid_lower_bound(self):
        values = [0.75, -0.294013, 0.75]
        minimum = weighted_minimum(values)
        for weights in itertools.product((0.5, 0.75, 1, 1.5, 2), repeat=3):
            score = sum(w * v for w, v in zip(weights, values)) / sum(weights)
            self.assertGreaterEqual(score + 1e-12, minimum)
        self.assertAlmostEqual(minimum, 0.0539913333333333)

    def test_constant_scores_do_not_depend_on_weights(self):
        self.assertEqual(weighted_minimum([0.25, 0.25, 0.25]), 0.25)

    def test_policy_decomposition_identity(self):
        rows = self.rows("policy_baseline_decomposition.csv")
        self.assertEqual(len(rows), 44)
        for row in rows:
            self.assertAlmostEqual(float(row["reported_delta"]),
                                   float(row["rebase_offset"]) + float(row["same_input_difference"]), places=8)

    def test_matched_contrasts_cancel_offsets(self):
        rows = self.rows("policy_baseline_decomposition.csv")
        lookup = {(r["sector"], r["quarter"], r["scenario"]): r for r in rows}
        for row in self.rows("policy_matched_contrasts.csv"):
            net = lookup[(row["sector"], row["quarter"], "NET")]
            other = lookup[(row["sector"], row["quarter"], row["other"])]
            self.assertAlmostEqual(float(row["net_advantage"]),
                                   float(net["reported_delta"]) - float(other["reported_delta"]), places=8)

    def test_reported_robustness_counts(self):
        signed = self.rows("signed_axis_robustness.csv")
        self.assertEqual(len(signed), 11)
        self.assertTrue(all(float(r["extended_loo_min"]) > 0 for r in signed))
        self.assertTrue(all(float(r["extended_box_weight_min"]) > 0 for r in signed))
        adverse = self.rows("policy_adverse_sensitivity_contrasts.csv")
        self.assertEqual(len(adverse), 30)
        self.assertTrue(all(float(r["adverse_net_advantage"]) > 0 for r in adverse))


if __name__ == "__main__":
    unittest.main()
