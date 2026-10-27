from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Iterable
import importlib.util
import sys


ROOT = Path(__file__).resolve().parents[1]

T09_PATH = ROOT / "outputs/tables/T09_cpii_sector_mean_comparison.csv"
T10_PATH = ROOT / "outputs/tables/T10_cpii_extreme_observations.csv"
REG_MUSIC_PATH = ROOT / "outputs/tables/regression_results_music.csv"
REG_WEBTOON_PATH = ROOT / "outputs/tables/regression_results_webtoon.csv"
REG_INFRA_PATH = ROOT / "outputs/tables/regression_results_infra.csv"
REG_CROSS_PATH = ROOT / "outputs/tables/regression_results_cross_country.csv"
POLICY_SUMMARY_PATH = ROOT / "outputs/tables/policy_scenario_summary.csv"
POLICY_SENSITIVITY_PATH = ROOT / "outputs/tables/policy_sensitivity_summary.csv"
BASELINE_INPUT_PATH = ROOT / "data/processed/policy_simulator_baseline_inputs.csv"
CALIBRATION_PATH = ROOT / "data/processed/policy_simulator_calibrated_parameters.csv"
CPII_SECTOR_QUARTER_PATH = ROOT / "data/processed/cpii_panel_sector_quarter.csv"
CPII_SECTOR_COUNTRY_PATH = ROOT / "data/processed/cpii_panel_sector_country_quarter.csv"

OUT_LINEAGE = ROOT / "data/processed/row_level_lineage_table.csv"
OUT_SUMMARY = ROOT / "data/processed/row_level_lineage_summary.csv"
OUT_LOG = ROOT / "logs/row_level_lineage_log.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def to_float(value: str | None) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def fmt_number(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.10f}"


def fmt_int(value: int) -> str:
    return str(value)


def load_regression_module():
    module_path = ROOT / "scripts/run_sector_regressions.py"
    spec = importlib.util.spec_from_file_location("run_sector_regressions", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load run_sector_regressions.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def append_lineage(
    rows: list[dict[str, str]],
    *,
    reported_artifact_id: str,
    reported_result_id: str,
    reported_result_label: str,
    reported_metric_name: str,
    reported_metric_value: str,
    reported_source_file: str,
    reported_row_key: str,
    lineage_stage: str,
    upstream_file: str,
    upstream_row_id: str,
    upstream_metric_name: str,
    upstream_value: str,
    aggregation_or_filter_rule: str,
    contributor_rank: int,
    contributor_count: int,
    notes: str,
) -> None:
    rows.append(
        {
            "lineage_id": f"lineage_{len(rows) + 1:05d}",
            "reported_artifact_id": reported_artifact_id,
            "reported_result_id": reported_result_id,
            "reported_result_label": reported_result_label,
            "reported_metric_name": reported_metric_name,
            "reported_metric_value": reported_metric_value,
            "reported_source_file": reported_source_file,
            "reported_row_key": reported_row_key,
            "lineage_stage": lineage_stage,
            "upstream_file": upstream_file,
            "upstream_row_id": upstream_row_id,
            "upstream_metric_name": upstream_metric_name,
            "upstream_value": upstream_value,
            "aggregation_or_filter_rule": aggregation_or_filter_rule,
            "contributor_rank": fmt_int(contributor_rank),
            "contributor_count": fmt_int(contributor_count),
            "notes": notes,
        }
    )


def build_t09_lineage(
    lineage_rows: list[dict[str, str]],
    t09_rows: list[dict[str, str]],
    cpii_rows: list[dict[str, str]],
) -> None:
    metric_pairs = [
        ("observation_count", "CPII"),
        ("mean_CPII", "CPII"),
        ("mean_I_reg", "I_reg"),
        ("mean_I_risk", "I_risk"),
        ("mean_I_market", "I_market"),
    ]
    for row in t09_rows:
        sector = row["sector_std"]
        contributors = [
            item
            for item in cpii_rows
            if item["sector_std"] == sector and item.get("CPII")
        ]
        contributors.sort(key=lambda item: item["year_quarter"])
        for reported_metric, upstream_metric in metric_pairs:
            contributor_count = len(contributors)
            for idx, src in enumerate(contributors, start=1):
                upstream_value = "1" if reported_metric == "observation_count" else src.get(upstream_metric, "")
                append_lineage(
                    lineage_rows,
                    reported_artifact_id="T09",
                    reported_result_id=f"T09::{sector}::{reported_metric}",
                    reported_result_label=f"T09 {sector} {reported_metric}",
                    reported_metric_name=reported_metric,
                    reported_metric_value=row.get(reported_metric, ""),
                    reported_source_file="outputs/tables/T09_cpii_sector_mean_comparison.csv",
                    reported_row_key=sector,
                    lineage_stage="aggregation_input",
                    upstream_file="data/processed/cpii_panel_sector_quarter.csv",
                    upstream_row_id=f"{src['sector_std']}|{src['year_quarter']}",
                    upstream_metric_name=upstream_metric if reported_metric != "observation_count" else "CPII_nonmissing_indicator",
                    upstream_value=upstream_value,
                    aggregation_or_filter_rule=(
                        f"{reported_metric}=aggregate over sector_std={sector} and nonmissing CPII"
                    ),
                    contributor_rank=idx,
                    contributor_count=contributor_count,
                    notes="T09 sector mean comparison table derives from the sector-quarter CPII panel.",
                )


def build_t10_lineage(
    lineage_rows: list[dict[str, str]],
    t10_rows: list[dict[str, str]],
    cpii_rows: list[dict[str, str]],
) -> None:
    cpii_index = {
        (row["sector_std"], row["year_quarter"]): row
        for row in cpii_rows
        if row.get("CPII")
    }
    for row in t10_rows:
        key = (row["sector_std"], row["year_quarter"])
        src = cpii_index.get(key)
        if src is None:
            continue
        for metric in ["CPII", "I_reg", "I_risk", "I_market"]:
            append_lineage(
                lineage_rows,
                reported_artifact_id="T10",
                reported_result_id=f"T10::{row['rank_group']}::{row['rank_order']}",
                reported_result_label=f"T10 {row['rank_group']} {row['rank_order']}",
                reported_metric_name=metric,
                reported_metric_value=row.get(metric, ""),
                reported_source_file="outputs/tables/T10_cpii_extreme_observations.csv",
                reported_row_key=f"{row['rank_group']}|{row['rank_order']}",
                lineage_stage="direct_match",
                upstream_file="data/processed/cpii_panel_sector_quarter.csv",
                upstream_row_id=f"{src['sector_std']}|{src['year_quarter']}",
                upstream_metric_name=metric,
                upstream_value=src.get(metric, ""),
                aggregation_or_filter_rule="Exact match on sector_std + year_quarter.",
                contributor_rank=1,
                contributor_count=1,
                notes="T10 ranks exact sector-quarter rows from the final sector-quarter CPII panel.",
            )


def build_regression_sample_cache(module) -> dict[str, dict[str, object]]:
    month_rows = module.read_csv(module.PLATFORM_MONTH_PATH)
    quarter_rows = module.read_csv(module.PLATFORM_QUARTER_PATH)
    event_rows = module.read_csv(module.EVENT_PANEL_PATH)
    cross_rows = module.read_csv(module.SECTOR_COUNTRY_CPII_PATH)

    music_panel = module.prepare_numeric_rows(
        [row for row in month_rows if row["sector_std"] == "music"],
        dependent_var="investment_recovery_ratio",
        explanatory_vars=["foreign_dependency_ratio"],
    )
    music_event_sample, music_event_vars, music_baseline, _music_note = module.make_event_sample(
        event_rows,
        sector_std="music",
        dependent_var="investment_recovery_ratio",
        include_medium=False,
        baseline_rel=-1,
    )
    webtoon_panel = module.prepare_numeric_rows(
        [row for row in quarter_rows if row["sector_std"] == "webtoon_story"],
        dependent_var="investment_recovery_ratio",
        explanatory_vars=["foreign_dependency_ratio"],
    )
    webtoon_event_sample, webtoon_event_vars, webtoon_baseline, _webtoon_note = module.make_event_sample(
        event_rows,
        sector_std="webtoon_story",
        dependent_var="investment_recovery_ratio",
        include_medium=False,
        baseline_rel=0,
    )
    infra_panel = module.prepare_numeric_rows(
        [row for row in quarter_rows if row["sector_std"] == "digital_infra"],
        dependent_var="outflow_to_capex_ratio",
        explanatory_vars=["foreign_dependency_ratio", "network_cost_ratio"],
    )
    cross_sample = module.prepare_numeric_rows(
        cross_rows,
        dependent_var="I_market",
        explanatory_vars=["I_reg", "I_risk"],
    )

    return {
        "music_service_month_fe_main": {
            "sample_rows": music_panel,
            "upstream_file": "data/processed/variable_panel_platform_month.csv",
            "upstream_row_id_field": "panel_platform_month_id",
            "dependent_var": "investment_recovery_ratio",
            "filter_rule": "prepare_numeric_rows on music service-month rows with nonmissing investment_recovery_ratio and foreign_dependency_ratio.",
        },
        "music_event_study_spotify_lossless": {
            "sample_rows": music_event_sample,
            "upstream_file": "data/processed/event_study_panel.csv",
            "upstream_row_id_field": "event_panel_row_id",
            "dependent_var": "investment_recovery_ratio",
            "filter_rule": f"make_event_sample strong-only, baseline {music_baseline}, then retain nonmissing investment_recovery_ratio.",
        },
        "webtoon_service_quarter_fe_main": {
            "sample_rows": webtoon_panel,
            "upstream_file": "data/processed/variable_panel_platform_quarter.csv",
            "upstream_row_id_field": "panel_platform_quarter_id",
            "dependent_var": "investment_recovery_ratio",
            "filter_rule": "prepare_numeric_rows on webtoon_story service-quarter rows with nonmissing investment_recovery_ratio and foreign_dependency_ratio.",
        },
        "webtoon_event_study_service_launches": {
            "sample_rows": webtoon_event_sample,
            "upstream_file": "data/processed/event_study_panel.csv",
            "upstream_row_id_field": "event_panel_row_id",
            "dependent_var": "investment_recovery_ratio",
            "filter_rule": f"make_event_sample strong-only, baseline {webtoon_baseline}, then retain nonmissing investment_recovery_ratio.",
        },
        "infra_service_quarter_fe_main": {
            "sample_rows": infra_panel,
            "upstream_file": "data/processed/variable_panel_platform_quarter.csv",
            "upstream_row_id_field": "panel_platform_quarter_id",
            "dependent_var": "outflow_to_capex_ratio",
            "filter_rule": "prepare_numeric_rows on digital_infra service-quarter rows with nonmissing outflow_to_capex_ratio, foreign_dependency_ratio, network_cost_ratio.",
        },
        "cross_country_sector_country_panel": {
            "sample_rows": cross_sample,
            "upstream_file": "data/processed/cpii_panel_sector_country_quarter.csv",
            "upstream_row_id_field": "panel_sector_quarter_id",
            "dependent_var": "I_market",
            "filter_rule": "prepare_numeric_rows on sector-country-quarter rows with nonmissing I_market, I_reg, and I_risk.",
        },
    }


def build_regression_lineage(
    lineage_rows: list[dict[str, str]],
    regression_rows: list[dict[str, str]],
    reported_artifact_id: str,
    reported_source_file: str,
    sample_cache: dict[str, dict[str, object]],
) -> None:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in regression_rows:
        grouped[row["model_id"]].append(row)

    for model_id, model_rows in grouped.items():
        cache = sample_cache[model_id]
        sample_rows: list[dict[str, str]] = cache["sample_rows"]  # type: ignore[assignment]
        upstream_file = str(cache["upstream_file"])
        upstream_row_id_field = str(cache["upstream_row_id_field"])
        dependent_var = str(cache["dependent_var"])
        filter_rule = str(cache["filter_rule"])

        model_rows.sort(key=lambda item: item["explanatory_variable"])
        contributor_count = len(sample_rows)
        for row in model_rows:
            result_key = f"{row['model_id']}|{row['explanatory_variable']}"
            bundle_value = (
                f"coefficient={row['coefficient']}|standard_error={row['standard_error']}|"
                f"p_value={row['p_value']}|sample_n={row['sample_n']}"
            )
            append_lineage(
                lineage_rows,
                reported_artifact_id=reported_artifact_id,
                reported_result_id=f"{reported_artifact_id}::{result_key}",
                reported_result_label=f"{reported_artifact_id} {row['model_id']} {row['explanatory_variable']}",
                reported_metric_name="regression_row",
                reported_metric_value=bundle_value,
                reported_source_file=reported_source_file,
                reported_row_key=result_key,
                lineage_stage="model_output_row",
                upstream_file=reported_source_file,
                upstream_row_id=result_key,
                upstream_metric_name="regression_output_bundle",
                upstream_value=bundle_value,
                aggregation_or_filter_rule="Direct regression output row stored in the report-ready regression CSV.",
                contributor_rank=1,
                contributor_count=1,
                notes="This row preserves the exact regression result row that is rendered in T11.",
            )
            append_lineage(
                lineage_rows,
                reported_artifact_id=reported_artifact_id,
                reported_result_id=f"{reported_artifact_id}::{result_key}",
                reported_result_label=f"{reported_artifact_id} {row['model_id']} {row['explanatory_variable']}",
                reported_metric_name="pretrend_test_result",
                reported_metric_value=row.get("pretrend_test_result", ""),
                reported_source_file=reported_source_file,
                reported_row_key=result_key,
                lineage_stage="model_output_row",
                upstream_file=reported_source_file,
                upstream_row_id=result_key,
                upstream_metric_name="pretrend_test_result",
                upstream_value=row.get("pretrend_test_result", ""),
                aggregation_or_filter_rule="Direct regression output row stored in the report-ready regression CSV.",
                contributor_rank=1,
                contributor_count=1,
                notes="This row keeps the pretrend decision shown in the T11 tables and the report text.",
            )
            if contributor_count != int(row["sample_n"]):
                raise RuntimeError(
                    f"Sample size mismatch for {model_id}: lineage cache {contributor_count} vs reported {row['sample_n']}"
                )
            for idx, sample_row in enumerate(sample_rows, start=1):
                upstream_value = (
                    f"y={sample_row.get(dependent_var, '')}|"
                    f"x={sample_row.get(row['explanatory_variable'], '')}"
                )
                append_lineage(
                    lineage_rows,
                    reported_artifact_id=reported_artifact_id,
                    reported_result_id=f"{reported_artifact_id}::{result_key}",
                    reported_result_label=f"{reported_artifact_id} {row['model_id']} {row['explanatory_variable']}",
                    reported_metric_name="coefficient",
                    reported_metric_value=row.get("coefficient", ""),
                    reported_source_file=reported_source_file,
                    reported_row_key=result_key,
                    lineage_stage="model_input_row",
                    upstream_file=upstream_file,
                    upstream_row_id=sample_row.get(upstream_row_id_field, ""),
                    upstream_metric_name=f"{dependent_var}|{row['explanatory_variable']}",
                    upstream_value=upstream_value,
                    aggregation_or_filter_rule=filter_rule,
                    contributor_rank=idx,
                    contributor_count=contributor_count,
                    notes="Each contributing observation is one row in the executable regression sample used to estimate the reported coefficient.",
                )


def build_policy_lineage(
    lineage_rows: list[dict[str, str]],
    policy_rows: list[dict[str, str]],
    baseline_rows: list[dict[str, str]],
    calibration_rows: list[dict[str, str]],
    sensitivity_rows: list[dict[str, str]],
) -> None:
    baseline_index = {row["baseline_id"]: row for row in baseline_rows}
    calibration_index: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in calibration_rows:
        if row.get("calibration_status") == "calibrated":
            calibration_index[(row["baseline_id"], row["scenario_code"])].append(row)

    for row in policy_rows:
        result_id = row["scenario_result_id"]
        row_key = result_id
        for metric in ["Delta_CPII", "policy_priority_score", "overall_policy_priority_latest_rank", "overall_policy_priority_latest_score"]:
            append_lineage(
                lineage_rows,
                reported_artifact_id="T12",
                reported_result_id=f"T12::{result_id}::{metric}",
                reported_result_label=f"T12 {result_id} {metric}",
                reported_metric_name=metric,
                reported_metric_value=row.get(metric, ""),
                reported_source_file="outputs/tables/policy_scenario_summary.csv",
                reported_row_key=row_key,
                lineage_stage="scenario_output_row",
                upstream_file="outputs/tables/policy_scenario_summary.csv",
                upstream_row_id=result_id,
                upstream_metric_name=metric,
                upstream_value=row.get(metric, ""),
                aggregation_or_filter_rule="Direct policy scenario output row rendered in T12.",
                contributor_rank=1,
                contributor_count=1,
                notes="Direct policy scenario row used in the report-ready T12 table.",
            )

        baseline = baseline_index.get(row["baseline_id"])
        if baseline is not None:
            append_lineage(
                lineage_rows,
                reported_artifact_id="T12",
                reported_result_id=f"T12::{result_id}::baseline",
                reported_result_label=f"T12 {result_id} baseline",
                reported_metric_name="CPII_base",
                reported_metric_value=row.get("CPII_base", ""),
                reported_source_file="outputs/tables/policy_scenario_summary.csv",
                reported_row_key=row_key,
                lineage_stage="scenario_baseline_row",
                upstream_file="data/processed/policy_simulator_baseline_inputs.csv",
                upstream_row_id=baseline["baseline_id"],
                upstream_metric_name="CPII_base|I_reg_base|I_risk_base|I_market_base",
                upstream_value=(
                    f"CPII_base={baseline.get('CPII_base', '')}|"
                    f"I_reg_base={baseline.get('I_reg_base', '')}|"
                    f"I_risk_base={baseline.get('I_risk_base', '')}|"
                    f"I_market_base={baseline.get('I_market_base', '')}"
                ),
                aggregation_or_filter_rule="Join on baseline_id from the simulator baseline input table.",
                contributor_rank=1,
                contributor_count=1,
                notes="Policy scenario outputs inherit their baseline values from the simulator baseline input table.",
            )

        params = calibration_index.get((row["baseline_id"], row["scenario_code"]), [])
        for idx, param in enumerate(sorted(params, key=lambda item: item["parameter_name"]), start=1):
            append_lineage(
                lineage_rows,
                reported_artifact_id="T12",
                reported_result_id=f"T12::{result_id}::parameters",
                reported_result_label=f"T12 {result_id} calibrated parameters",
                reported_metric_name="calibrated_parameter",
                reported_metric_value=param.get("parameter_value", ""),
                reported_source_file="outputs/tables/policy_scenario_summary.csv",
                reported_row_key=row_key,
                lineage_stage="scenario_parameter_row",
                upstream_file="data/processed/policy_simulator_calibrated_parameters.csv",
                upstream_row_id=param["calibration_id"],
                upstream_metric_name=param["parameter_name"],
                upstream_value=param.get("parameter_value", ""),
                aggregation_or_filter_rule="Join on baseline_id + scenario_code for calibrated parameters only.",
                contributor_rank=idx,
                contributor_count=len(params),
                notes="These calibrated parameters feed the scenario equation that produced the T12 row.",
            )

    mean_delta_rows = defaultdict(list)
    latest_priority_rows = defaultdict(list)
    for row in policy_rows:
        mean_delta_rows[row["scenario_code"]].append(row)
        if row.get("overall_policy_priority_latest_rank"):
            latest_priority_rows[row["scenario_code"]].append(row)

    for scenario_code, rows in sorted(mean_delta_rows.items()):
        deltas = [to_float(row["Delta_CPII"]) for row in rows if to_float(row["Delta_CPII"]) is not None]
        if not deltas:
            continue
        mean_delta = sum(deltas) / len(deltas)
        rows_sorted = sorted(rows, key=lambda item: (item["year_quarter"], item["scenario_result_id"]))
        for idx, row in enumerate(rows_sorted, start=1):
            append_lineage(
                lineage_rows,
                reported_artifact_id="TEXT",
                reported_result_id=f"TEXT::policy_mean_delta::{scenario_code}",
                reported_result_label=f"Report text mean Delta_CPII {scenario_code}",
                reported_metric_name="mean_Delta_CPII",
                reported_metric_value=fmt_number(mean_delta),
                reported_source_file="outputs/tables/policy_scenario_summary.csv",
                reported_row_key=f"scenario_code={scenario_code}",
                lineage_stage="aggregation_input",
                upstream_file="outputs/tables/policy_scenario_summary.csv",
                upstream_row_id=row["scenario_result_id"],
                upstream_metric_name="Delta_CPII",
                upstream_value=row.get("Delta_CPII", ""),
                aggregation_or_filter_rule=f"Average Delta_CPII over all T12 rows where scenario_code={scenario_code}.",
                contributor_rank=idx,
                contributor_count=len(rows_sorted),
                notes="These mean Delta_CPII values are cited in the policy chapter and conclusion text.",
            )

    for scenario_code, rows in sorted(latest_priority_rows.items()):
        ref = rows[0]
        for metric in ["overall_policy_priority_latest_rank", "overall_policy_priority_latest_score"]:
            append_lineage(
                lineage_rows,
                reported_artifact_id="TEXT",
                reported_result_id=f"TEXT::policy_latest_priority::{scenario_code}::{metric}",
                reported_result_label=f"Report text latest policy priority {scenario_code} {metric}",
                reported_metric_name=metric,
                reported_metric_value=ref.get(metric, ""),
                reported_source_file="outputs/tables/policy_scenario_summary.csv",
                reported_row_key=f"scenario_code={scenario_code}",
                lineage_stage="direct_match",
                upstream_file="outputs/tables/policy_scenario_summary.csv",
                upstream_row_id=ref["scenario_result_id"],
                upstream_metric_name=metric,
                upstream_value=ref.get(metric, ""),
                aggregation_or_filter_rule="Scenario-level latest priority metrics are repeated across rows and taken directly from the policy summary table.",
                contributor_rank=1,
                contributor_count=1,
                notes="These metrics are cited in the policy recommendation and roadmap text.",
            )

    for row in sensitivity_rows:
        append_lineage(
            lineage_rows,
            reported_artifact_id="T12",
            reported_result_id=f"T12::SENS::{row['sensitivity_id']}",
            reported_result_label=f"T12 sensitivity {row['sensitivity_id']}",
            reported_metric_name="Delta_CPII",
            reported_metric_value=row.get("Delta_CPII", ""),
            reported_source_file="outputs/tables/policy_sensitivity_summary.csv",
            reported_row_key=row["sensitivity_id"],
            lineage_stage="sensitivity_output_row",
            upstream_file="outputs/tables/policy_sensitivity_summary.csv",
            upstream_row_id=row["sensitivity_id"],
            upstream_metric_name="Delta_CPII|policy_priority_score",
            upstream_value=(
                f"Delta_CPII={row.get('Delta_CPII', '')}|"
                f"policy_priority_score={row.get('policy_priority_score', '')}"
            ),
            aggregation_or_filter_rule="Direct sensitivity row used as the support file for T12.",
            contributor_rank=1,
            contributor_count=1,
            notes="Sensitivity rows are not always cited verbatim in the text, but they are the direct support file for T12.",
        )


def build_text_cpii_lineage(
    lineage_rows: list[dict[str, str]],
    t09_rows: list[dict[str, str]],
    cpii_rows: list[dict[str, str]],
) -> None:
    t09_index = {row["sector_std"]: row for row in t09_rows}
    grouped = defaultdict(list)
    for row in cpii_rows:
        if row.get("CPII"):
            grouped[row["sector_std"]].append(row)

    for sector, contributors in sorted(grouped.items()):
        reported_row = t09_index[sector]
        contributors.sort(key=lambda item: item["year_quarter"])
        for idx, src in enumerate(contributors, start=1):
            append_lineage(
                lineage_rows,
                reported_artifact_id="TEXT",
                reported_result_id=f"TEXT::sector_mean_CPII::{sector}",
                reported_result_label=f"Report text sector mean CPII {sector}",
                reported_metric_name="mean_CPII",
                reported_metric_value=reported_row.get("mean_CPII", ""),
                reported_source_file="outputs/tables/T09_cpii_sector_mean_comparison.csv",
                reported_row_key=sector,
                lineage_stage="aggregation_input",
                upstream_file="data/processed/cpii_panel_sector_quarter.csv",
                upstream_row_id=f"{src['sector_std']}|{src['year_quarter']}",
                upstream_metric_name="CPII",
                upstream_value=src.get("CPII", ""),
                aggregation_or_filter_rule=f"Average CPII over sector_std={sector} in the sector-quarter CPII panel.",
                contributor_rank=idx,
                contributor_count=len(contributors),
                notes="These values are cited directly in the executive summary, conclusion, and quality-check sections.",
            )


def build_text_cross_country_lineage(
    lineage_rows: list[dict[str, str]],
    cross_rows: list[dict[str, str]],
    regression_rows: list[dict[str, str]],
) -> None:
    target = None
    for row in regression_rows:
        if row["model_id"] == "cross_country_sector_country_panel" and row["explanatory_variable"] == "I_reg":
            target = row
            break
    if target is None:
        return
    sample_rows = [
        row
        for row in cross_rows
        if to_float(row.get("I_market")) is not None
        and to_float(row.get("I_reg")) is not None
        and to_float(row.get("I_risk")) is not None
    ]
    for idx, src in enumerate(sample_rows, start=1):
        append_lineage(
            lineage_rows,
            reported_artifact_id="TEXT",
            reported_result_id="TEXT::cross_country_I_reg_to_I_market",
            reported_result_label="Report text cross-country I_reg to I_market coefficient",
            reported_metric_name="coefficient",
            reported_metric_value=target.get("coefficient", ""),
            reported_source_file="outputs/tables/regression_results_cross_country.csv",
            reported_row_key="cross_country_sector_country_panel|I_reg",
            lineage_stage="model_input_row",
            upstream_file="data/processed/cpii_panel_sector_country_quarter.csv",
            upstream_row_id=src.get("panel_sector_quarter_id", ""),
            upstream_metric_name="I_market|I_reg|I_risk",
            upstream_value=(
                f"I_market={src.get('I_market', '')}|"
                f"I_reg={src.get('I_reg', '')}|"
                f"I_risk={src.get('I_risk', '')}"
            ),
            aggregation_or_filter_rule="prepare_numeric_rows on sector-country-quarter rows with nonmissing I_market, I_reg, and I_risk.",
            contributor_rank=idx,
            contributor_count=len(sample_rows),
            notes="This coefficient is cited in the digital infra results section and the conclusion.",
        )
    append_lineage(
        lineage_rows,
        reported_artifact_id="TEXT",
        reported_result_id="TEXT::cross_country_I_reg_to_I_market",
        reported_result_label="Report text cross-country I_reg to I_market coefficient",
        reported_metric_name="regression_row",
        reported_metric_value=(
            f"coefficient={target.get('coefficient', '')}|"
            f"standard_error={target.get('standard_error', '')}|"
            f"p_value={target.get('p_value', '')}|sample_n={target.get('sample_n', '')}"
        ),
        reported_source_file="outputs/tables/regression_results_cross_country.csv",
        reported_row_key="cross_country_sector_country_panel|I_reg",
        lineage_stage="model_output_row",
        upstream_file="outputs/tables/regression_results_cross_country.csv",
        upstream_row_id="cross_country_sector_country_panel|I_reg",
        upstream_metric_name="regression_output_bundle",
        upstream_value=(
            f"coefficient={target.get('coefficient', '')}|"
            f"standard_error={target.get('standard_error', '')}|"
            f"p_value={target.get('p_value', '')}|sample_n={target.get('sample_n', '')}"
        ),
        aggregation_or_filter_rule="Direct regression output row stored in the cross-country regression CSV.",
        contributor_rank=1,
        contributor_count=1,
        notes="This direct row preserves the exact coefficient cited in the report text.",
    )


def build_summary(lineage_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in lineage_rows:
        grouped[row["reported_artifact_id"]].append(row)

    summary_rows: list[dict[str, str]] = []
    for artifact_id, rows in sorted(grouped.items()):
        result_ids = sorted({row["reported_result_id"] for row in rows})
        upstream_files = sorted({row["upstream_file"] for row in rows})
        stages = sorted({row["lineage_stage"] for row in rows})
        summary_rows.append(
            {
                "reported_artifact_id": artifact_id,
                "reported_result_count": fmt_int(len(result_ids)),
                "lineage_row_count": fmt_int(len(rows)),
                "upstream_file_count": fmt_int(len(upstream_files)),
                "lineage_stages": "|".join(stages),
                "upstream_files": "|".join(upstream_files),
                "notes": "Artifact-level lineage coverage summary.",
            }
        )
    return summary_rows


def write_log(lineage_rows: list[dict[str, str]], summary_rows: list[dict[str, str]]) -> None:
    def count_rows(predicate) -> int:
        return sum(1 for row in lineage_rows if predicate(row))

    content = f"""# Row-Level Lineage Log

기준 시점: `2026-03-29`

## 생성 산출물

- `data/processed/row_level_lineage_table.csv`
- `data/processed/row_level_lineage_summary.csv`

## 총계

- lineage row 수: `{len(lineage_rows)}`
- artifact 요약 행 수: `{len(summary_rows)}`
- TEXT claim lineage row 수: `{count_rows(lambda row: row['reported_artifact_id'] == 'TEXT')}`
- T11 계수 입력 sample lineage row 수: `{count_rows(lambda row: row['reported_artifact_id'].startswith('T11') and row['lineage_stage'] == 'model_input_row')}`
- T12 baseline / parameter lineage row 수: `{count_rows(lambda row: row['reported_artifact_id'] == 'T12' and row['lineage_stage'] in {'scenario_baseline_row', 'scenario_parameter_row'})}`

## 커버 범위

- `T09` 분야 평균 비교표: sector mean 집계 입력 row 추적
- `T10` 극단 관측치 표: sector-quarter exact row direct match
- `T11-Music`, `T11-Webtoon`, `T11-Infra`: 결과 row + 회귀 sample row 추적
- `T12`: scenario output row + baseline row + calibrated parameter row + sensitivity support row 추적
- 본문 핵심 문장: 분야 평균 CPII, `I_reg -> I_market` 계수, 정책별 평균 `Delta_CPII`, 최신 정책 우선순위 추적

## 해석 메모

- 이 lineage table은 최종 통계량을 report-ready table row와 executable analysis sample row에 직접 연결한다.
- regression sample lineage는 `run_sector_regressions.py`의 실제 필터 규칙을 불러와 같은 표본을 재구성한 뒤 저장했다.
- policy lineage는 `baseline_id`와 `scenario_code`를 기준으로 baseline input 및 calibrated parameter row를 직접 연결했다.
"""
    OUT_LOG.write_text(content, encoding="utf-8")


def fieldnames(rows: Iterable[dict[str, str]]) -> list[str]:
    preferred = [
        "lineage_id",
        "reported_artifact_id",
        "reported_result_id",
        "reported_result_label",
        "reported_metric_name",
        "reported_metric_value",
        "reported_source_file",
        "reported_row_key",
        "lineage_stage",
        "upstream_file",
        "upstream_row_id",
        "upstream_metric_name",
        "upstream_value",
        "aggregation_or_filter_rule",
        "contributor_rank",
        "contributor_count",
        "notes",
    ]
    all_keys = set().union(*(row.keys() for row in rows))
    extras = sorted(key for key in all_keys if key not in preferred)
    return preferred + extras


def summary_fieldnames() -> list[str]:
    return [
        "reported_artifact_id",
        "reported_result_count",
        "lineage_row_count",
        "upstream_file_count",
        "lineage_stages",
        "upstream_files",
        "notes",
    ]


def main() -> None:
    module = load_regression_module()

    t09_rows = read_csv(T09_PATH)
    t10_rows = read_csv(T10_PATH)
    reg_music_rows = read_csv(REG_MUSIC_PATH)
    reg_webtoon_rows = read_csv(REG_WEBTOON_PATH)
    reg_infra_rows = read_csv(REG_INFRA_PATH)
    reg_cross_rows = read_csv(REG_CROSS_PATH)
    policy_rows = read_csv(POLICY_SUMMARY_PATH)
    sensitivity_rows = read_csv(POLICY_SENSITIVITY_PATH)
    baseline_rows = read_csv(BASELINE_INPUT_PATH)
    calibration_rows = read_csv(CALIBRATION_PATH)
    cpii_sector_rows = read_csv(CPII_SECTOR_QUARTER_PATH)
    cpii_sector_country_rows = read_csv(CPII_SECTOR_COUNTRY_PATH)

    lineage_rows: list[dict[str, str]] = []
    build_t09_lineage(lineage_rows, t09_rows, cpii_sector_rows)
    build_t10_lineage(lineage_rows, t10_rows, cpii_sector_rows)

    sample_cache = build_regression_sample_cache(module)
    build_regression_lineage(
        lineage_rows,
        reg_music_rows,
        reported_artifact_id="T11-Music",
        reported_source_file="outputs/tables/regression_results_music.csv",
        sample_cache=sample_cache,
    )
    build_regression_lineage(
        lineage_rows,
        reg_webtoon_rows,
        reported_artifact_id="T11-Webtoon",
        reported_source_file="outputs/tables/regression_results_webtoon.csv",
        sample_cache=sample_cache,
    )
    build_regression_lineage(
        lineage_rows,
        reg_infra_rows,
        reported_artifact_id="T11-Infra",
        reported_source_file="outputs/tables/regression_results_infra.csv",
        sample_cache=sample_cache,
    )
    build_regression_lineage(
        lineage_rows,
        reg_cross_rows,
        reported_artifact_id="T11-Infra",
        reported_source_file="outputs/tables/regression_results_cross_country.csv",
        sample_cache=sample_cache,
    )

    build_policy_lineage(
        lineage_rows,
        policy_rows,
        baseline_rows,
        calibration_rows,
        sensitivity_rows,
    )
    build_text_cpii_lineage(lineage_rows, t09_rows, cpii_sector_rows)
    build_text_cross_country_lineage(lineage_rows, cpii_sector_country_rows, reg_cross_rows)

    summary_rows = build_summary(lineage_rows)
    write_csv(OUT_LINEAGE, lineage_rows, fieldnames(lineage_rows))
    write_csv(OUT_SUMMARY, summary_rows, summary_fieldnames())
    write_log(lineage_rows, summary_rows)


if __name__ == "__main__":
    main()
