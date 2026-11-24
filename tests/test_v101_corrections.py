from __future__ import annotations

import csv
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _load_module(name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SPOTIFY_FY2025_20F_HTML = b"""
<html><body>
<p>(in &euro; millions)</p>
<table>
  <tr><th>Note</th><th>2025</th><th>2024</th><th>2023</th></tr>
  <tr><td>Revenue</td><td>4</td><td>17,186</td><td>15,673</td><td>13,247</td></tr>
  <tr><td>Cost of revenue</td><td>11,690</td><td>10,795</td><td>9,850</td></tr>
  <tr><td>Finance costs</td><td>8</td><td>(266)</td><td>(210)</td><td>(190)</td></tr>
  <tr><td>Income/(loss) before tax</td><td>2,224</td><td>1,200</td><td>(500)</td></tr>
  <tr><td>Income tax expense</td><td>9</td><td>12</td><td>50</td><td>20</td></tr>
</table>
<table>
  <tr><th>Assets</th><th>2025</th><th>2024</th></tr>
  <tr><td>Non-current assets</td><td></td><td></td></tr>
  <tr><td>Intangible assets</td><td>12</td><td>41</td><td>33</td></tr>
</table>
<!-- Distinct Cash Flow Statement table (PP&E purchases EUR 61m must NOT be selected as Note 11 additions) -->
<table>
  <tr><th>Cash flows from investing activities</th><th>2025</th><th>2024</th></tr>
  <tr><td>Operating activities summary</td><td>2,933</td><td>2,100</td></tr>
  <tr><td>Purchases of property and equipment (Additions proxy decoy)</td><td>61</td><td>11</td></tr>
</table>
<!-- Note 11: Property and equipment cost rollforward (FY2024 stacked above FY2025, empty leading header cell as in SEC 20-F) -->
<table>
  <tr><th></th><th>Property and equipment</th><th>Leasehold improvements</th><th>Total</th></tr>
  <tr><td>Cost</td><td></td><td></td><td></td></tr>
  <tr><td>At January 1, 2024</td><td>100</td><td>400</td><td>500</td></tr>
  <tr><td>Additions</td><td>4</td><td>8</td><td>12</td></tr>
  <tr><td>At December 31, 2024</td><td>104</td><td>408</td><td>512</td></tr>
  <tr><td>Additions</td><td>12</td><td>50</td><td>62</td></tr>
  <tr><td>At December 31, 2025</td><td>116</td><td>458</td><td>574</td></tr>
  <tr><td>Accumulated depreciation</td><td></td><td></td><td></td></tr>
  <tr><td>At January 1, 2024</td><td>(50)</td><td>(200)</td><td>(250)</td></tr>
  <tr><td>Additions</td><td>(1)</td><td>(1)</td><td>(2)</td></tr>
</table>
<!-- Note 12: Intangible assets cost rollforward (FY2024 stacked above FY2025) -->
<table>
  <tr><th></th><th>Internal development costs</th><th>Acquired intangible assets</th><th>Total</th></tr>
  <tr><td>Cost</td><td></td><td></td><td></td></tr>
  <tr><td>At January 1, 2024</td><td>60</td><td>80</td><td>140</td></tr>
  <tr><td>Additions</td><td>3</td><td>0</td><td>3</td></tr>
  <tr><td>Acquisitions</td><td>0</td><td>5</td><td>5</td></tr>
  <tr><td>At December 31, 2024</td><td>63</td><td>85</td><td>148</td></tr>
  <tr><td>At January 1, 2025</td><td>63</td><td>85</td><td>148</td></tr>
  <tr><td>Additions</td><td>12</td><td>0</td><td>12</td></tr>
  <tr><td>Acquisitions</td><td>0</td><td>5</td><td>5</td></tr>
  <tr><td>At December 31, 2025</td><td>75</td><td>90</td><td>165</td></tr>
  <tr><td>Accumulated amortization</td><td></td><td></td><td></td></tr>
  <tr><td>At January 1, 2025</td><td>(40)</td><td>(60)</td><td>(100)</td></tr>
</table>
</body></html>
"""

SPOTIFY_2025Q3_6K_HTML = b"""
<html><body>
<p>(in &euro; millions)</p>
<table>
  <tr><th>Three months ended September 30,</th><th>Nine months ended September 30,</th></tr>
  <tr><th>Note</th><th>2025</th><th>2024</th><th>2025</th><th>2024</th></tr>
  <tr><td>Revenue</td><td>4</td><td>4,200</td><td>3,900</td><td>12,655</td><td>11,500</td></tr>
  <tr><td>Cost of revenue</td><td>2,900</td><td>2,700</td><td>8,658</td><td>8,000</td></tr>
  <tr><td>Finance costs</td><td>8</td><td>(200)</td><td>(150)</td><td>(716)</td><td>(400)</td></tr>
  <tr><td>Income before tax</td><td>400</td><td>300</td><td>1,203</td><td>800</td></tr>
  <tr><td>Income tax expense</td><td>9</td><td>5</td><td>4</td><td>15</td><td>10</td></tr>
</table>
<table>
  <tr><th>Assets</th><th>September 30, 2025</th><th>December 31, 2024</th></tr>
  <tr><td>Non-current assets</td><td></td><td></td></tr>
  <tr><td>Intangible assets</td><td>12</td><td>33</td><td>36</td></tr>
</table>
<table>
  <tr><th>Property and equipment</th><th>Leasehold improvements</th><th>Other</th><th>Total</th></tr>
  <tr><td>At January 1, 2025</td><td>408</td><td>104</td><td>512</td></tr>
  <tr><td>Additions</td><td>30</td><td>9</td><td>39</td></tr>
  <tr><td>At September 30, 2025</td><td>438</td><td>113</td><td>551</td></tr>
</table>
<table>
  <tr><th>Intangible assets</th><th>Internal development costs</th><th>Acquired intangible assets</th><th>Total</th></tr>
  <tr><td>At January 1, 2025</td><td>63</td><td>85</td><td>148</td></tr>
  <tr><td>Additions</td><td>4</td><td>0</td><td>4</td></tr>
  <tr><td>At September 30, 2025</td><td>67</td><td>85</td><td>152</td></tr>
</table>
</body></html>
"""


HAS_LXML = importlib.util.find_spec("lxml") is not None


class V101CorrectionRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bfe = _load_module("bfe_v101", "scripts/build_financial_extraction_panel.py") if HAS_LXML else None
        cls.std = _load_module("std_v101", "scripts/build_standardized_numeric_panel.py")

    def _spotify_meta(self, filing_group: str, fiscal_period: str, fiscal_period_end: str) -> dict:
        return {
            "filing_id": f"lu_spotify_{filing_group}_{fiscal_period}",
            "firm_std": "spotify",
            "firm_name_std": "Spotify Technology S.A.",
            "country_std": "lu",
            "filing_system_country_std": "us",
            "sector_std": "music",
            "service_std": "spotify",
            "filing_group": filing_group,
            "filing_form": "20-F" if filing_group == "annual" else "6-K",
            "fiscal_period": fiscal_period,
            "fiscal_period_end": fiscal_period_end,
            "period_granularity": filing_group,
            "currency": "EUR",
            "source_file": "synthetic_test.htm",
            "source_url": "https://example.invalid/spotify",
        }

    @unittest.skipUnless(HAS_LXML, "requires optional source-parsing dependency lxml (requirements-sources.txt)")
    def test_spotify_fy2025_extracts_2025_rollforward_not_2024_or_cashflow(self) -> None:
        meta_2025 = self._spotify_meta("annual", "FY2025", "2025-12-31")
        rows, issues = self.bfe.extract_spotify_metrics(meta_2025, SPOTIFY_FY2025_20F_HTML)
        self.assertEqual(issues, [])
        by_metric = {row["metric_name"]: row for row in rows}
        self.assertEqual(by_metric["capex"]["metric_value_raw"], "62000000")
        self.assertEqual(by_metric["capex"]["metric_value_display"], "62")
        self.assertNotEqual(by_metric["capex"]["metric_value_raw"], "12000000")
        self.assertNotEqual(by_metric["capex"]["metric_value_raw"], "61000000")
        self.assertEqual(by_metric["content_investment"]["metric_value_raw"], "17000000")
        self.assertEqual(by_metric["content_investment"]["metric_value_display"], "12 + 5")

    @unittest.skipUnless(HAS_LXML, "requires optional source-parsing dependency lxml (requirements-sources.txt)")
    def test_spotify_fy2024_still_extracts_2024_rollforward_cleanly(self) -> None:
        meta_2024 = self._spotify_meta("annual", "FY2024", "2024-12-31")
        rows, issues = self.bfe.extract_spotify_metrics(meta_2024, SPOTIFY_FY2025_20F_HTML)
        self.assertEqual(issues, [])
        by_metric = {row["metric_name"]: row for row in rows}
        self.assertEqual(by_metric["capex"]["metric_value_raw"], "12000000")
        self.assertEqual(by_metric["content_investment"]["metric_value_raw"], "8000000")
        self.assertEqual(by_metric["content_investment"]["metric_value_display"], "3 + 5")

    @unittest.skipUnless(HAS_LXML, "requires optional source-parsing dependency lxml (requirements-sources.txt)")
    def test_spotify_2025q3_interim_preserves_39m_and_4m(self) -> None:
        meta_q3 = self._spotify_meta("interim", "2025Q3", "2025-09-30")
        rows, issues = self.bfe.extract_spotify_metrics(meta_q3, SPOTIFY_2025Q3_6K_HTML)
        self.assertEqual(issues, [])
        by_metric = {row["metric_name"]: row for row in rows}
        self.assertEqual(by_metric["capex"]["metric_value_raw"], "39000000")
        self.assertEqual(by_metric["content_investment"]["metric_value_raw"], "4000000")

    @unittest.skipUnless(HAS_LXML, "requires optional source-parsing dependency lxml (requirements-sources.txt)")
    def test_spotify_missing_target_year_does_not_fallback_to_prior_year(self) -> None:
        meta_2026 = self._spotify_meta("annual", "FY2026", "2026-12-31")
        rows, issues = self.bfe.extract_spotify_metrics(meta_2026, SPOTIFY_FY2025_20F_HTML)
        by_metric = {row["metric_name"]: row for row in rows}
        self.assertNotIn("capex", by_metric)
        self.assertNotIn("content_investment", by_metric)
        issue_reasons = {item["reason"] for item in issues}
        self.assertIn("capex_missing", issue_reasons)
        self.assertIn("content_investment_missing", issue_reasons)

    def test_outflow_sign_normalization_preserves_raw_and_signed_pretax(self) -> None:
        macro_lookup = self.std.load_macro_lookup()
        common = {
            "standardized_row_id": "test_00001",
            "source_panel": "financial_extraction_panel",
            "source_row_key": "test_key",
            "panel_unit_type": "firm_fiscal_period",
            "country_std": "kr",
            "firm_std": "naver",
            "service_std": "naver_webtoon",
            "title_std": "",
            "filing_id": "kr_naver_test",
            "sector_std": "webtoon_story",
            "metric_variant": "",
            "period_type": "annual",
            "raw_period_label": "FY2025",
            "date_standardized": "2025-12-31",
            "period_end_date": "2025-12-31",
            "year": "2025",
            "year_month": "2025-12",
            "year_quarter": "2025Q4",
            "fiscal_period": "FY2025",
            "metric_unit_raw": "currency_amount",
            "collection_status": "collected",
            "source_ref": "test",
            "notes": "orig",
        }
        for outflow_metric in ("content_investment", "capex"):
            base = {**common, "metric_name": outflow_metric, "metric_value_raw": "-500000000"}
            row = self.std.create_row(base, -500000000.0, "KRW", macro_lookup)
            self.assertEqual(row["metric_value_raw"], "-500000000")
            self.assertEqual(row["metric_value_numeric_raw"], "-500000000")
            self.assertEqual(row["metric_value_krw_nominal"], "500000000")
            self.assertEqual(row["metric_value_standardized"], "500000000")
            self.assertIn("v1.0.1_outflow_magnitude_normalized_from_negative_raw", row["notes"])

        # Pretax income MUST stay signed (negative pretax losses are real losses, not sign convention).
        pretax_base = {**common, "metric_name": "pretax_income", "metric_value_raw": "-250000000"}
        pretax_row = self.std.create_row(pretax_base, -250000000.0, "KRW", macro_lookup)
        self.assertEqual(pretax_row["metric_value_raw"], "-250000000")
        self.assertEqual(pretax_row["metric_value_numeric_raw"], "-250000000")
        self.assertEqual(pretax_row["metric_value_krw_nominal"], "-250000000")
        self.assertEqual(pretax_row["metric_value_standardized"], "-250000000")

    def test_frozen_financial_panel_spotify_and_23_negative_outflows(self) -> None:
        with (ROOT / "data/interim/financial_extraction_panel.csv").open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.DictReader(handle))

        fy25_spot = {
            r["metric_name"]: r
            for r in rows
            if r["filing_id"] == "lu_spotify_annual_0001628280-26-006874"
        }
        self.assertEqual(fy25_spot["capex"]["metric_value_raw"], "62000000")
        self.assertEqual(fy25_spot["capex"]["metric_value_display"], "62")
        self.assertEqual(fy25_spot["content_investment"]["metric_value_raw"], "17000000")
        self.assertEqual(fy25_spot["content_investment"]["metric_value_display"], "12 + 5")

        neg_capex = [r for r in rows if r["metric_name"] == "capex" and float(r["metric_value_raw"]) < 0]
        neg_ci = [
            r for r in rows if r["metric_name"] == "content_investment" and float(r["metric_value_raw"]) < 0
        ]
        self.assertEqual(len(neg_capex), 23)
        self.assertEqual(len(neg_ci), 23)

    def test_v101_recomputed_signed_cases_and_archived_event_coverage(self) -> None:
        with (ROOT / "data/processed/claim_strengthening/signed_rebuild/s_risk_recovery_panel.csv").open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            risk_rows = list(csv.DictReader(handle))
        flo_row = next(r for r in risk_rows if r["firm_std"] == "dreamus_flo" and r["foreign_peer_std"] == "spotify")
        self.assertAlmostEqual(float(flo_row["s_risk_recovery"]), 0.0, places=6)

        with (ROOT / "outputs/tables/claim_strengthening/signed_rebuild/T_signed_korea_market_case_studies.csv").open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            case_rows = list(csv.DictReader(handle))
        flo_case = next(r for r in case_rows if r["firm_std"] == "dreamus_flo" and r["foreign_peer_std"] == "spotify")
        self.assertAlmostEqual(float(flo_case["core_signed_score"]), 0.250000, places=6)
        self.assertAlmostEqual(float(flo_case["extended_signed_score"]), 0.380000, places=6)

        with (ROOT / "outputs/tables/regression_results_webtoon.csv").open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            wt_rows = list(csv.DictReader(handle))
        lead_row = next(
            r
            for r in wt_rows
            if r["model_id"] == "webtoon_event_study_service_launches"
            and r["explanatory_variable"] == "treated_rel_m1"
        )
        self.assertEqual(int(lead_row["sample_n"]), 170)
        self.assertAlmostEqual(float(lead_row["coefficient"]), 68.7629307491, places=5)

    def test_v101_anchor_and_archived_v1_anchor_backward_compatibility(self) -> None:
        from scripts.cpii_simulator.engine import load_anchor, read_company_csv, score_rows

        examples = read_company_csv(
            ROOT / "data/processed/cpii_simulator/examples/fictional_companies.csv"
        )
        anchor_v101 = load_anchor()
        self.assertEqual(anchor_v101["anchor_version"], "POOL_SCQ_P01_P99_EMP_RANK_V1_0_1")
        scores_v101 = {row["observation_id"]: row["CPII"] for row in score_rows(examples, anchor_v101)}
        self.assertAlmostEqual(scores_v101["SYN-A"], 40.41028798429696, places=10)
        self.assertAlmostEqual(scores_v101["SYN-B"], 32.73212620758967, places=10)
        self.assertAlmostEqual(scores_v101["SYN-A"] - scores_v101["SYN-B"], 7.6781617767072845, places=10)

        archived_v1_path = ROOT / "data/processed/cpii_simulator/anchor/POOL_SCQ_P01_P99_EMP_RANK_V1.json"
        self.assertTrue(archived_v1_path.is_file(), "archived v1.0.0 anchor should remain preserved")
        anchor_v1 = load_anchor(archived_v1_path)
        self.assertEqual(anchor_v1["anchor_version"], "POOL_SCQ_P01_P99_EMP_RANK_V1")
        scores_v1 = {row["observation_id"]: row["CPII"] for row in score_rows(examples, anchor_v1)}
        self.assertAlmostEqual(scores_v1["SYN-A"], 39.89561107334345, places=10)
        self.assertAlmostEqual(scores_v1["SYN-B"], 32.21744929663617, places=10)
        self.assertAlmostEqual(scores_v1["SYN-A"] - scores_v1["SYN-B"], 7.6781617767072845, places=10)


if __name__ == "__main__":
    unittest.main()
