from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean


BASE_DIR = Path(__file__).resolve().parents[2]
CORE_SAMPLE_PATH = (
    BASE_DIR
    / "data/registry/claim_strengthening/reverse_discrimination_core_sample_v1.csv"
)
FUNDING_PATH = (
    BASE_DIR / "data/processed/claim_strengthening/funding_cost_matched_panel.csv"
)
IP_PATH = (
    BASE_DIR
    / "data/processed/claim_strengthening/ip_assetization_comparison_table.csv"
)
RECOVERY_PATH = (
    BASE_DIR
    / "data/processed/claim_strengthening/investment_recovery_horizon_panel.csv"
)
CASHFLOW_PATH = (
    BASE_DIR
    / "data/processed/claim_strengthening/cashflow_recovery_pressure_panel.csv"
)
OUTPUT_PATH = (
    BASE_DIR / "data/processed/claim_strengthening/i_risk_narrow_panel.csv"
)
LOG_PATH = BASE_DIR / "logs/claim_strengthening/i_risk_narrow_log.md"


COMPONENT_SPECS = {
    "funding": {
        "path": FUNDING_PATH,
        "value_field": "borrowing_rate_proxy",
        "gap_field": "funding_cost_spread_signed",
        "comparability_field": "comparability_flag",
        "risk_value_sign": 1.0,
        "risk_gap_sign": 1.0,
        "metric_label": "borrowing_rate_proxy",
    },
    "ip_assetization": {
        "path": IP_PATH,
        "value_field": "ip_assetization_proxy",
        "gap_field": "ip_assetization_gap_signed",
        "comparability_field": "comparability_flag",
        "risk_value_sign": -1.0,
        "risk_gap_sign": -1.0,
        "metric_label": "ip_assetization_proxy",
    },
    "recovery_horizon": {
        "path": RECOVERY_PATH,
        "value_field": "investment_recovery_horizon_months",
        "gap_field": "horizon_gap_months_signed",
        "comparability_field": "comparability_flag",
        "risk_value_sign": 1.0,
        "risk_gap_sign": 1.0,
        "metric_label": "investment_recovery_horizon_months",
    },
    "cashflow_pressure": {
        "path": CASHFLOW_PATH,
        "value_field": "cashflow_pressure_ratio",
        "gap_field": "pressure_gap_signed",
        "comparability_field": "comparability_flag",
        "risk_value_sign": 1.0,
        "risk_gap_sign": 1.0,
        "metric_label": "cashflow_pressure_ratio",
    },
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_float(value: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def fmt_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}"


def core_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        row["peer_group_id"],
        row["firm_std"],
        row["service_std"],
        row["country_std"],
    )


def minmax_pct(value: float, values: list[float]) -> float | None:
    low = min(values)
    high = max(values)
    if high - low <= 1e-12:
        return None
    return 100.0 * (value - low) / (high - low)


def build_component_observations(
    spec: dict[str, object]
) -> tuple[dict[tuple[str, str, str, str], list[dict[str, object]]], dict[str, int]]:
    rows = read_csv(spec["path"])
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row.get(spec["comparability_field"], "") != "yes":
            continue
        grouped[(row["peer_group_id"], row["fiscal_period"])].append(row)

    observations_by_core: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    period_counter: dict[str, set[tuple[str, str]]] = defaultdict(set)

    for (peer_group_id, fiscal_period), period_rows in grouped.items():
        value_candidates = []
        gap_candidates = []
        enriched_rows = []
        for row in period_rows:
            raw_value = parse_float(row.get(spec["value_field"], ""))
            raw_gap = parse_float(row.get(spec["gap_field"], ""))
            if raw_value is None or raw_gap is None:
                continue
            risk_value = raw_value * float(spec["risk_value_sign"])
            risk_gap = raw_gap * float(spec["risk_gap_sign"])
            value_candidates.append(risk_value)
            gap_candidates.append(risk_gap)
            enriched_rows.append((row, raw_value, risk_value, raw_gap, risk_gap))

        if not enriched_rows:
            continue

        for row, raw_value, risk_value, raw_gap, risk_gap in enriched_rows:
            relative_pct = minmax_pct(risk_value, value_candidates)
            gap_pct = minmax_pct(risk_gap, gap_candidates)
            score_parts = [part for part in [relative_pct, gap_pct] if part is not None]
            component_score = mean(score_parts) if score_parts else None
            key = core_key(row)
            observations_by_core[key].append(
                {
                    "fiscal_period": fiscal_period,
                    "raw_metric": raw_value,
                    "risk_gap": risk_gap,
                    "relative_pct": relative_pct,
                    "gap_pct": gap_pct,
                    "component_score": component_score,
                }
            )
            period_counter[peer_group_id].add((peer_group_id, fiscal_period))

    support_counts = {
        peer_group_id: len(periods) for peer_group_id, periods in period_counter.items()
    }
    return observations_by_core, support_counts


def aggregate_component(
    obs: list[dict[str, object]],
) -> dict[str, str | int]:
    if not obs:
        return {
            "period_count": 0,
            "periods_observed": "",
            "metric_mean": "",
            "relative_pct_mean": "",
            "gap_mean": "",
            "gap_pct_mean": "",
            "component_score": "",
        }

    periods = sorted({str(item["fiscal_period"]) for item in obs})
    metric_values = [float(item["raw_metric"]) for item in obs if item["raw_metric"] is not None]
    relative_values = [float(item["relative_pct"]) for item in obs if item["relative_pct"] is not None]
    gap_values = [float(item["risk_gap"]) for item in obs if item["risk_gap"] is not None]
    gap_pct_values = [float(item["gap_pct"]) for item in obs if item["gap_pct"] is not None]
    score_values = [float(item["component_score"]) for item in obs if item["component_score"] is not None]

    return {
        "period_count": len(obs),
        "periods_observed": "|".join(periods),
        "metric_mean": fmt_float(mean(metric_values) if metric_values else None),
        "relative_pct_mean": fmt_float(mean(relative_values) if relative_values else None),
        "gap_mean": fmt_float(mean(gap_values) if gap_values else None),
        "gap_pct_mean": fmt_float(mean(gap_pct_values) if gap_pct_values else None),
        "component_score": fmt_float(mean(score_values) if score_values else None),
    }


def main() -> None:
    core_rows = [row for row in read_csv(CORE_SAMPLE_PATH) if row["include_flag"] == "yes"]

    component_obs: dict[str, dict[tuple[str, str, str, str], list[dict[str, object]]]] = {}
    peer_support_counts: dict[str, int] = defaultdict(int)
    for component_name, spec in COMPONENT_SPECS.items():
        obs_map, support_counts = build_component_observations(spec)
        component_obs[component_name] = obs_map
        for peer_group_id, count in support_counts.items():
            peer_support_counts[(peer_group_id, component_name)] = count

    output_rows: list[dict[str, str]] = []
    status_counter: dict[str, int] = defaultdict(int)

    for row in core_rows:
        key = core_key(row)
        aggregated = {}
        observed_component_names = []
        mean_relative_parts = []
        mean_gap_parts = []
        final_score_parts = []
        peer_group_id = row["peer_group_id"]

        for component_name in COMPONENT_SPECS:
            component_data = aggregate_component(component_obs[component_name].get(key, []))
            aggregated[component_name] = component_data
            if component_data["component_score"] != "":
                observed_component_names.append(component_name)
                if component_data["relative_pct_mean"] != "":
                    mean_relative_parts.append(float(component_data["relative_pct_mean"]))
                if component_data["gap_pct_mean"] != "":
                    mean_gap_parts.append(float(component_data["gap_pct_mean"]))
                final_score_parts.append(float(component_data["component_score"]))

        observed_component_count = len(observed_component_names)
        peer_supported_components = sum(
            1 for component_name in COMPONENT_SPECS if peer_support_counts.get((peer_group_id, component_name), 0) > 0
        )

        if observed_component_count >= 3:
            status = "stronger_direct_risk_coverage"
        elif observed_component_count == 2:
            status = "partial_direct_risk_coverage"
        elif observed_component_count == 1:
            status = "thin_direct_risk_coverage"
        else:
            status = "no_direct_risk_coverage"
        status_counter[status] += 1

        if observed_component_count >= 2:
            i_risk_narrow = fmt_float(mean(final_score_parts))
        else:
            i_risk_narrow = ""

        if observed_component_count == 0 and peer_supported_components > 0:
            note = "Peer-level direct risk evidence exists, but this specific row has no usable matched financing/recovery observation."
        elif observed_component_count == 0:
            note = "No usable direct matched financing/recovery component is available for this row."
        else:
            note = (
                "Observed direct components: "
                + ", ".join(observed_component_names)
                + ". "
                + ("Index computed from component means." if observed_component_count >= 2 else "Single-component evidence retained without a composite index.")
            )

        result = {
            "peer_group_id": row["peer_group_id"],
            "firm_std": row["firm_std"],
            "service_std": row["service_std"],
            "country_std": row["country_std"],
            "analysis_role": row["analysis_role"],
            "peer_supported_component_count": str(peer_supported_components),
            "observed_component_count": str(observed_component_count),
            "mean_relative_position_pct": fmt_float(mean(mean_relative_parts) if mean_relative_parts else None),
            "mean_absolute_gap_score_pct": fmt_float(mean(mean_gap_parts) if mean_gap_parts else None),
            "i_risk_narrow": i_risk_narrow,
            "i_risk_narrow_status": status,
            "construction_note": note,
        }

        for component_name, spec in COMPONENT_SPECS.items():
            prefix = component_name
            result[f"{prefix}_period_count"] = str(aggregated[component_name]["period_count"])
            result[f"{prefix}_periods_observed"] = str(aggregated[component_name]["periods_observed"])
            result[f"{prefix}_{spec['metric_label']}_mean"] = str(aggregated[component_name]["metric_mean"])
            result[f"{prefix}_relative_position_pct_mean"] = str(aggregated[component_name]["relative_pct_mean"])
            result[f"{prefix}_risk_gap_mean"] = str(aggregated[component_name]["gap_mean"])
            result[f"{prefix}_gap_score_pct_mean"] = str(aggregated[component_name]["gap_pct_mean"])
            result[f"{prefix}_component_score"] = str(aggregated[component_name]["component_score"])

        output_rows.append(result)

    fieldnames = [
        "peer_group_id",
        "firm_std",
        "service_std",
        "country_std",
        "analysis_role",
        "peer_supported_component_count",
        "observed_component_count",
        "funding_period_count",
        "funding_periods_observed",
        "funding_borrowing_rate_proxy_mean",
        "funding_relative_position_pct_mean",
        "funding_risk_gap_mean",
        "funding_gap_score_pct_mean",
        "funding_component_score",
        "ip_assetization_period_count",
        "ip_assetization_periods_observed",
        "ip_assetization_ip_assetization_proxy_mean",
        "ip_assetization_relative_position_pct_mean",
        "ip_assetization_risk_gap_mean",
        "ip_assetization_gap_score_pct_mean",
        "ip_assetization_component_score",
        "recovery_horizon_period_count",
        "recovery_horizon_periods_observed",
        "recovery_horizon_investment_recovery_horizon_months_mean",
        "recovery_horizon_relative_position_pct_mean",
        "recovery_horizon_risk_gap_mean",
        "recovery_horizon_gap_score_pct_mean",
        "recovery_horizon_component_score",
        "cashflow_pressure_period_count",
        "cashflow_pressure_periods_observed",
        "cashflow_pressure_cashflow_pressure_ratio_mean",
        "cashflow_pressure_relative_position_pct_mean",
        "cashflow_pressure_risk_gap_mean",
        "cashflow_pressure_gap_score_pct_mean",
        "cashflow_pressure_component_score",
        "mean_relative_position_pct",
        "mean_absolute_gap_score_pct",
        "i_risk_narrow",
        "i_risk_narrow_status",
        "construction_note",
    ]
    write_csv(OUTPUT_PATH, output_rows, fieldnames)

    component_observed_counts = {}
    for component_name in COMPONENT_SPECS:
        count = sum(
            1
            for row in output_rows
            if row[f"{component_name}_component_score"] != ""
        )
        component_observed_counts[component_name] = count

    top_rows = sorted(
        [row for row in output_rows if row["i_risk_narrow"] != ""],
        key=lambda row: float(row["i_risk_narrow"]),
        reverse=True,
    )[:5]
    top_lines = "\n".join(
        f"- `{row['peer_group_id']} | {row['firm_std']} | {row['country_std']} | {row['i_risk_narrow']}`"
        for row in top_rows
    )
    if not top_lines:
        top_lines = "- none"

    log_text = "\n".join(
        [
            "# Strength Prompt 30. I_risk_narrow panel",
            "",
            "## Summary",
            "",
            f"- total rows: `{len(output_rows)}`",
            f"- status distribution: `{dict(sorted(status_counter.items()))}`",
            f"- component coverage: `{component_observed_counts}`",
            "",
            "## Construction rule",
            "",
            "- This narrow risk index uses only direct matched financing/recovery panels: funding cost, IP assetization, investment recovery horizon, and cashflow recovery pressure.",
            "- For each comparable peer-period, every component keeps both a peer-internal relative-position score and an opposite-side risk-gap score.",
            "- Component scores are the mean of those two scores, and the final `i_risk_narrow` is computed only when at least two direct components are observed for the row.",
            "",
            "## Top observed rows",
            "",
            top_lines,
            "",
            "## Key interpretation",
            "",
            "- `infra_traffic_ott` and `mus_label_ip_export` are the only peer groups with four usable direct risk components.",
            "- `mus_streaming_paid_core` remains partial because funding-cost matching fails on missing Spotify debt and cashflow-pressure matching fails on negative Dreamus operating cash flow plus Kakao Entertainment's missing filing row.",
            "- The index is therefore strongest for infrastructure and music IP cells, while streaming rows should still be treated as partial evidence.",
        ]
    )
    LOG_PATH.write_text(log_text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
