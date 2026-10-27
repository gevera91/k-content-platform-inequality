from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DECISIONS = PROJECT_ROOT / "docs" / "cpii_simulator_design_decisions.md"


def _text() -> str:
    return DECISIONS.read_text(encoding="utf-8")


class SimulatorContractTest(unittest.TestCase):
    def test_design_decision_document_covers_product_contract(self) -> None:
        text = _text()
        required_sections = [
            "## 1. Product purpose",
            "## 2. Primary score object",
            "## 3. Difference and sign convention",
            "## 4. When the term reverse-discrimination gap is permitted",
            "## 5. Input and comparability contract",
            "## 6. Two-company and n-company modes",
            "## 7. Economic-interpretation contract",
            "## 8. Sensitivity contract",
            "## 9. Delivery scope",
            "## 10. Versioning, packaging, and change control",
            "## 11. Reconciled implementation items",
            "## 12. Acceptance invariants",
        ]
        for section in required_sections:
            self.assertIn(section, text)

    def test_score_objects_and_ranges_are_unambiguous(self) -> None:
        text = _text()
        self.assertIn("CPII_FIRM_INPUT_EQW_V1", text)
        self.assertIn("POOL_SCQ_P01_P99_EMP_RANK_V1", text)
        self.assertIn("delta_cpii_points(A,B) = CPII(A) - CPII(B)", text)
        self.assertIn("delta_cpii_points` ranges from -100 to 100", text)
        self.assertIn("pairwise_burden_gap` ranges from -1 to 1", text)
        self.assertIn("signed evidence score", text)
        self.assertIn("must never share a label, axis, legend, or interpretation rule", text)

    def test_reverse_discrimination_label_is_conditioned_on_valid_domain(self) -> None:
        text = _text()
        self.assertIn("A is explicitly tagged `domestic` and B `foreign`", text)
        self.assertIn("share sector, comparable service scope, focal market, reporting period", text)
        self.assertIn("strict common-support rule", text)
        self.assertIn("Domestic-domestic and foreign-foreign comparisons are never automatically labeled", text)

    def test_two_and_n_modes_share_one_invariant_engine(self) -> None:
        text = _text()
        self.assertIn("same n-company engine with n=2", text)
        self.assertIn("antisymmetric pairwise difference matrix", text)
        self.assertIn("must not change an existing observation's score", text)
        self.assertIn("Strict ranking never mixes different effective feature sets", text)

    def test_delivery_and_deferred_scope_are_explicit(self) -> None:
        text = _text()
        self.assertIn("macro-free, external-link-free `.xlsx` comparator", text)
        self.assertIn("Python reference engine and versioned frozen anchor", text)
        self.assertIn("report with an economic-interpretation appendix", text)
        self.assertIn("hosted web application", text)
        self.assertIn("deferred from v1", text)

    def test_universal_score_to_money_claim_is_forbidden(self) -> None:
        text = _text()
        self.assertIn("There is no universal `one CPII point = currency amount` coefficient", text)
        self.assertIn("not automatically summed", text)
        self.assertIn(
            "never presented as a percentage cost, legal finding, causal effect, or unqualified total loss",
            text,
        )


if __name__ == "__main__":
    unittest.main()
