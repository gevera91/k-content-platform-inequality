from pathlib import Path
import unittest

from scripts.cpii_simulator.validate_input import observation_id_error, valid_source_date


class ComparatorV2Test(unittest.TestCase):
    def test_real_dates_and_exact_text_format(self):
        for value in ("2024-02-29", "2025-12-31", "2000-02-29", "2100-12-31"):
            self.assertTrue(valid_source_date(value), value)
        for value in ("2025-02-29", "2100-02-29", "2025-02-30", "20251231", "2025-W01-1", "2025-1-01", "not-a-date", "1999-12-31"):
            self.assertFalse(valid_source_date(value), value)

    def test_excel_safe_id_alphabet(self):
        for value in ("SYN-A", "FIRM_01.2025Q4", "123", "A" * 64):
            self.assertIsNone(observation_id_error(value))
        for value in ("COMPANY-É", "COMPANY-é", "A:B", "A B", "A\nB", "A" * 65):
            self.assertIsNotNone(observation_id_error(value))

    def test_dependency_formula_resolves_names_not_assumed_order(self):
        source = (Path(__file__).resolve().parents[1] / "scripts/cpii_simulator/build_workbook.mjs").read_text()
        self.assertIn('featureCell("infra_dependency_ratio")', source)
        self.assertIn('featureCell("network_cost_ratio")', source)
        self.assertIn('featureCell("foreign_dependency_ratio")', source)


if __name__ == "__main__":
    unittest.main()
