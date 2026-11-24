#!/usr/bin/env python3
"""Reproducible end-to-end v1.0.1 recalculation pipeline from published inputs.

Executes all stages downstream of `data/interim/financial_extraction_panel.csv`
in dependency order while respecting published-archive boundaries:
- Offline frozen World Bank 2024 macro references (no live network API drift).
- Outflow magnitude normalization for `capex` and `content_investment` at
  standardization/calculation boundaries (preserving raw stated signs and
  signed `pretax_income`).
- Archived event-study sample membership preservation with linked numeric refresh
  by stable `panel_row_id`.
- Frozen archived direct OCF reuse in `cashflow_recovery_pressure_panel.csv` when
  raw OpenDART/SEC filing HTML files are absent from the public repository.
- Deterministic propagation of recomputed `i_risk_narrow_panel.csv` into
  `signed_rebuild/` tables without altering unrelated case codings.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]

PIPELINE_STEPS: list[tuple[str, list[str]]] = [
    ("standardize_numeric_panel", ["scripts/build_standardized_numeric_panel.py"]),
    ("deduplicate_panel", ["scripts/build_deduplicated_panel.py"]),
    ("variable_panels", ["scripts/build_variable_panels.py"]),
    ("variable_qc_report", ["scripts/build_variable_qc_report.py"]),
    ("event_panel_refresh", ["scripts/build_event_registry.py", "--refresh-archived-linked-numeric"]),
    ("subindex_panels", ["scripts/build_subindex_panels.py"]),
    ("cpii_panels", ["scripts/build_cpii_panels.py"]),
    ("alt_spec_cpii_panels", ["scripts/build_alt_spec_cpii_panels.py"]),
    ("spec_robustness", ["scripts/build_spec_robustness.py"]),
    ("country_comparison_tables", ["scripts/build_country_comparison_tables.py"]),
    ("firm_comparison_tables", ["scripts/build_firm_comparison_tables.py"]),
    ("timeseries_analysis", ["scripts/build_timeseries_analysis.py"]),
    ("sector_regressions", ["scripts/run_sector_regressions.py"]),
    ("ofcom_proxy_sensitivity", ["scripts/ofcom_proxy_sensitivity.py"]),
    ("claim_pretrend_check", ["scripts/claim_strengthening/build_claim_pretrend_check.py"]),
    ("claim_placebo_event", ["scripts/claim_strengthening/build_claim_placebo_event_results.py"]),
    ("claim_placebo_outcome", ["scripts/claim_strengthening/build_claim_placebo_outcome_results.py"]),
    ("policy_calibration", ["scripts/build_policy_calibration.py"]),
    ("policy_scenarios", ["scripts/build_policy_scenarios.py"]),
    ("report_ready_assets", ["scripts/build_report_ready_assets.py"]),
    ("row_level_lineage", ["scripts/build_row_level_lineage_table.py"]),
    ("narrow_ip_assetization", ["scripts/claim_strengthening/build_ip_assetization_comparison_table.py"]),
    ("narrow_recovery_horizon", ["scripts/claim_strengthening/build_investment_recovery_horizon_panel.py"]),
    ("narrow_cashflow_pressure", ["scripts/claim_strengthening/build_cashflow_recovery_pressure_panel.py"]),
    ("narrow_i_risk", ["scripts/claim_strengthening/build_i_risk_narrow_panel.py"]),
    ("narrow_composite", ["scripts/claim_strengthening/build_reverse_discrimination_composite_narrow.py"]),
    ("narrow_peer_rank", ["scripts/claim_strengthening/build_claim_peer_rank_table.py"]),
    ("narrow_kr_vs_global_gap", ["scripts/claim_strengthening/build_claim_korea_vs_global_gap_outputs.py"]),
    ("narrow_channel_decomp", ["scripts/claim_strengthening/build_claim_channel_decomposition_outputs.py"]),
    ("narrow_balanced_panel", ["scripts/claim_strengthening/build_reverse_discrimination_balanced_panel.py"]),
    ("narrow_loco", ["scripts/claim_strengthening/build_claim_leave_one_country_out.py"]),
    ("narrow_lopo", ["scripts/claim_strengthening/build_claim_leave_one_peer_out.py"]),
    ("narrow_alt_hypothesis", ["scripts/claim_strengthening/build_claim_alt_hypothesis_reduction.py"]),
    ("signed_case_propagation", ["scripts/claim_strengthening/rebuild_signed_case_tables.py"]),
    ("review_strengthening_checks", ["scripts/review_strengthening_20260915.py"]),
]


def ensure_log_dirs(root: Path) -> None:
    (root / "logs" / "claim_strengthening").mkdir(parents=True, exist_ok=True)


def run_pipeline(root: Path, skip_steps: set[str] | None = None) -> None:
    skip = skip_steps or set()
    ensure_log_dirs(root)
    started = time.time()
    for idx, (label, cmd) in enumerate(PIPELINE_STEPS, start=1):
        if label in skip:
            print(f"[{idx:02d}/{len(PIPELINE_STEPS)}] SKIP {label}")
            continue
        t0 = time.time()
        print(f"[{idx:02d}/{len(PIPELINE_STEPS)}] RUN  {label}: {' '.join(cmd)}", flush=True)
        subprocess.run([sys.executable, *cmd], cwd=root, check=True)
        print(f"       OK   {label} ({time.time() - t0:.2f}s)", flush=True)
    print(f"Completed v1.0.1 recalculation pipeline in {time.time() - started:.2f}s.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument(
        "--skip",
        nargs="*",
        default=[],
        help="Optional step labels to skip.",
    )
    args = parser.parse_args()
    run_pipeline(args.project_root.resolve(), skip_steps=set(args.skip))


if __name__ == "__main__":
    main()
