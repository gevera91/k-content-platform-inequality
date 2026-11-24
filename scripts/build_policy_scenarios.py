from __future__ import annotations

import csv
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_cpii_panels import (  # noqa: E402
    build_anchor_profiles,
    compute_cpii_fields,
    compute_subindex_dict,
    normalize_with_anchor,
    read_csv,
    safe_float,
)
from build_policy_calibration import (  # noqa: E402
    PARAM_BOUNDS,
    lookup_structural_metric,
    build_structural_metric_lookup,
)
from build_subindex_panels import subindex_components_active  # noqa: E402


BASELINE_INPUT_PATH = ROOT / "data/processed/policy_simulator_baseline_inputs.csv"
PARAM_INPUT_PATH = ROOT / "data/processed/policy_simulator_calibrated_parameters.csv"
VARIABLE_SECTOR_PATH = ROOT / "data/processed/variable_panel_sector_quarter.csv"
VARIABLE_PLATFORM_Q_PATH = ROOT / "data/processed/variable_panel_platform_quarter.csv"

SUMMARY_OUTPUT_PATH = ROOT / "outputs/tables/policy_scenario_summary.csv"
SENSITIVITY_OUTPUT_PATH = ROOT / "outputs/tables/policy_sensitivity_summary.csv"
FIGURE_OUTPUT_PATH = ROOT / "outputs/figures/policy_tornado_chart.png"
LOG_OUTPUT_PATH = ROOT / "logs/policy_scenario_log.md"

EPS = 1e-9
SENSITIVITY_SCALES = {
    "low": 0.8,
    "base": 1.0,
    "high": 1.2,
}
SCENARIO_ORDER = ["BND", "NET", "IPF", "CBA"]
SCENARIO_LABELS = {
    "BND": "Bundling Restriction",
    "NET": "Network Cost Recovery",
    "IPF": "IP Financialization",
    "CBA": "Collective Bargaining",
}


def fmt(value: float | None) -> str:
    if value is None:
        return ""
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def fmt_amount(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.2f}"


def quarter_index(value: str) -> int:
    year = int(value[:4])
    quarter = int(value[-1])
    return year * 4 + quarter - 1


def clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def scenario_parameter_map(rows: list[dict[str, str]]) -> dict[str, dict[str, dict[str, float]]]:
    out: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for row in rows:
        if row["calibration_status"] != "calibrated":
            continue
        value = safe_float(row["parameter_value"])
        if value is None:
            continue
        out[row["baseline_id"]][row["scenario_code"]][row["parameter_name"]] = value
    return out


def enrich_baseline_raw_variables(
    baseline_row: dict[str, str],
    structural_lookup: dict[str, dict[str, list[tuple[str, float, str]]]],
) -> tuple[dict[str, float | None], list[str]]:
    sector = baseline_row["sector_std"]
    yq = baseline_row["year_quarter"]

    def lookup(metric: str) -> tuple[float | None, str]:
        value, source_yq, status = lookup_structural_metric(structural_lookup, metric, sector, yq)
        note = f"{metric}:{status}"
        if source_yq:
            note += f"@{source_yq}"
        return value, note

    notes: list[str] = []
    effective_tax_rate_gap, note = lookup("effective_tax_rate_gap")
    notes.append(note)
    infra_dependency_ratio, note = lookup("infra_dependency_ratio")
    notes.append(note)
    bundle_leverage_index, note = lookup("bundle_leverage_index")
    notes.append(note)
    cross_market_transfer_index, note = lookup("cross_market_transfer_index")
    notes.append(note)
    foreign_dependency_ratio, note = lookup("foreign_dependency_ratio")
    notes.append(note)
    outflow_to_capex_ratio, note = lookup("outflow_to_capex_ratio")
    notes.append(note)
    network_cost_ratio, note = lookup("network_cost_ratio")
    notes.append(note)
    investment_recovery_ratio, note = lookup("investment_recovery_ratio")
    notes.append(note)
    cashflow_recovery_ratio, note = lookup("cashflow_recovery_ratio")
    notes.append(note)
    ip_assetization_gap, note = lookup("ip_assetization_gap")
    notes.append(note)
    creator_share_ratio, note = lookup("creator_share_ratio")
    notes.append(note)
    funding_cost_spread, note = lookup("funding_cost_spread")
    notes.append(note)

    # Prefer values already fixed in the calibrated baseline file when present.
    def baseline_float(name: str) -> float | None:
        return safe_float(baseline_row.get(name, ""))

    return (
        {
            "effective_tax_rate_gap": effective_tax_rate_gap,
            "network_cost_ratio": baseline_float("network_cost_ratio_base")
            if baseline_float("network_cost_ratio_base") is not None
            else network_cost_ratio,
            "infra_dependency_ratio": infra_dependency_ratio,
            "funding_cost_spread": baseline_float("funding_cost_spread_base")
            if baseline_float("funding_cost_spread_base") is not None
            else funding_cost_spread,
            "ip_assetization_gap": baseline_float("ip_assetization_gap_base")
            if baseline_float("ip_assetization_gap_base") is not None
            else ip_assetization_gap,
            "investment_recovery_ratio": baseline_float("investment_recovery_ratio_base")
            if baseline_float("investment_recovery_ratio_base") is not None
            else investment_recovery_ratio,
            "cashflow_recovery_ratio": baseline_float("cashflow_recovery_ratio_base")
            if baseline_float("cashflow_recovery_ratio_base") is not None
            else cashflow_recovery_ratio,
            "creator_share_ratio": baseline_float("creator_share_ratio_base")
            if baseline_float("creator_share_ratio_base") is not None
            else creator_share_ratio,
            "bundle_leverage_index": baseline_float("bundle_leverage_index_base")
            if baseline_float("bundle_leverage_index_base") is not None
            else bundle_leverage_index,
            "cross_market_transfer_index": baseline_float("cross_market_transfer_index_base")
            if baseline_float("cross_market_transfer_index_base") is not None
            else cross_market_transfer_index,
            "foreign_dependency_ratio": baseline_float("foreign_dependency_ratio_base")
            if baseline_float("foreign_dependency_ratio_base") is not None
            else foreign_dependency_ratio,
            "outflow_to_capex_ratio": baseline_float("outflow_to_capex_ratio_base")
            if baseline_float("outflow_to_capex_ratio_base") is not None
            else outflow_to_capex_ratio,
        },
        notes,
    )


def scaled_parameters(params: dict[str, float], scale: float) -> dict[str, float]:
    out: dict[str, float] = {}
    for name, value in params.items():
        lower, upper = PARAM_BOUNDS[name]
        out[name] = clip(value * scale, lower, upper)
    return out


def compute_priority_score(
    cpii_base: float,
    delta_cpii: float,
    recovered_revenue: float,
    market_revenue: float,
    domestic_capex_gain: float,
    revenue: float,
    npv_gain: float,
    content_investment: float,
    creator_income_gain: float,
    eligible_revenue: float,
) -> float:
    delta_cpii_share = max(delta_cpii, 0.0) / max(cpii_base, 1.0)
    revenue_gain_share = max(recovered_revenue, 0.0) / max(market_revenue, 1.0)
    capex_gain_share = max(domestic_capex_gain, 0.0) / max(revenue, 1.0)
    npv_gain_share = max(npv_gain, 0.0) / max(content_investment, 1.0)
    creator_gain_share = max(creator_income_gain, 0.0) / max(eligible_revenue, 1.0)
    return (
        0.55 * delta_cpii_share
        + 0.15 * revenue_gain_share
        + 0.10 * capex_gain_share
        + 0.10 * npv_gain_share
        + 0.10 * creator_gain_share
    )


def recompute_indices(
    raw_values: dict[str, float | None],
    anchor_profiles: dict[str, dict[str, object]],
    active_components: dict[str, list[str]],
    inactive_variables: dict[str, dict[str, str]],
) -> tuple[float | None, float | None, float | None, float | None]:
    normalized_values: dict[str, float] = {}
    for variable_name, raw_value in raw_values.items():
        if raw_value is None or variable_name not in anchor_profiles:
            continue
        normalized_values[variable_name] = normalize_with_anchor(raw_value, anchor_profiles[variable_name])

    subindex_fields = compute_subindex_dict(normalized_values, active_components, inactive_variables)
    i_reg = safe_float(subindex_fields.get("I_reg", ""))
    i_risk = safe_float(subindex_fields.get("I_risk", ""))
    i_market = safe_float(subindex_fields.get("I_market", ""))
    cpii_fields = compute_cpii_fields(i_reg, i_risk, i_market)
    cpii = safe_float(cpii_fields.get("CPII", ""))
    return i_reg, i_risk, i_market, cpii


def evaluate_scenario(
    baseline_row: dict[str, str],
    raw_values: dict[str, float | None],
    scenario_code: str,
    params: dict[str, float],
    anchor_profiles: dict[str, dict[str, object]],
    active_components: dict[str, list[str]],
    inactive_variables: dict[str, dict[str, str]],
) -> dict[str, float | str]:
    cpii_base = float(baseline_row["CPII_base"])
    market_revenue = float(baseline_row["market_revenue_krw_nominal"])
    revenue = float(baseline_row["revenue_krw_nominal"])
    pretax_income = float(baseline_row["pretax_income_krw_nominal"])
    content_investment = float(baseline_row["content_investment_krw_nominal"])
    eligible_revenue = float(baseline_row["eligible_revenue_krw_nominal"])
    local_share = float(baseline_row["local_platform_share_base"])
    traffic_cost_pressure = float(baseline_row["traffic_cost_pressure_base"])
    network_cost_ratio = raw_values["network_cost_ratio"] or 0.0
    foreign_dependency_ratio = raw_values["foreign_dependency_ratio"] or 0.0
    outflow_to_capex_ratio = raw_values["outflow_to_capex_ratio"] or 0.0
    ip_gap = raw_values["ip_assetization_gap"] or 0.0
    funding_spread = raw_values["funding_cost_spread"] or 0.0
    investment_recovery = raw_values["investment_recovery_ratio"] or 0.0
    creator_share = raw_values["creator_share_ratio"] or 0.0
    cashflow_recovery = raw_values["cashflow_recovery_ratio"] or 0.0
    bundle_value = raw_values["bundle_leverage_index"] or 0.0
    transfer_value = raw_values["cross_market_transfer_index"] or 0.0
    securitization_delta = float(baseline_row["securitization_npv_delta_krw_nominal"])
    collective_premium = float(baseline_row["collective_bargaining_premium_base"])

    updated = dict(raw_values)
    recovered_revenue = 0.0
    recovered_cost = 0.0
    domestic_capex_gain = 0.0
    npv_gain = 0.0
    finance_capacity = 0.0
    creator_income_gain = 0.0
    local_share_scenario = local_share

    if scenario_code == "BND":
        rho = params["rho_bundle"]
        eta_transfer = params["eta_transfer"]
        eta_share = params["eta_share"]
        updated["bundle_leverage_index"] = (1.0 - rho) * bundle_value
        updated["cross_market_transfer_index"] = max(0.0, (1.0 - eta_transfer * rho) * transfer_value)
        local_share_scenario = min(
            1.0,
            local_share + eta_share * rho * (bundle_value + transfer_value) / 2.0,
        )
        recovered_revenue = max(0.0, (local_share_scenario - local_share) * market_revenue)
    elif scenario_code == "NET":
        phi = params["phi_recover"]
        psi = params["psi_capex"]
        kappa = params["kappa_replace"]
        recovered_cost = phi * traffic_cost_pressure * revenue
        domestic_capex_gain = psi * recovered_cost
        updated["network_cost_ratio"] = max(0.0, network_cost_ratio - recovered_cost / (revenue + EPS))
        updated["foreign_dependency_ratio"] = max(0.0, (1.0 - kappa) * foreign_dependency_ratio)
        updated["outflow_to_capex_ratio"] = max(
            0.0,
            outflow_to_capex_ratio - domestic_capex_gain / (revenue + EPS),
        )
    elif scenario_code == "IPF":
        alpha = params["alpha_ip"]
        lambd = params["lambda_advance"]
        eta_funding = params["eta_funding"]
        eta_recovery = params["eta_recovery"]
        npv_gain = alpha * securitization_delta
        finance_capacity = lambd * npv_gain
        updated["ip_assetization_gap"] = (1.0 - alpha) * ip_gap
        updated["funding_cost_spread"] = max(
            0.0,
            funding_spread - eta_funding * finance_capacity / (content_investment + EPS),
        )
        updated["investment_recovery_ratio"] = (
            investment_recovery + eta_recovery * finance_capacity / (content_investment + EPS)
        )
    elif scenario_code == "CBA":
        theta = params["theta_bargain"]
        eta_cash = params["eta_cash"]
        delta_creator_share = theta * collective_premium
        updated["creator_share_ratio"] = min(1.0, creator_share + delta_creator_share)
        creator_income_gain = eligible_revenue * delta_creator_share
        updated["cashflow_recovery_ratio"] = cashflow_recovery + eta_cash * delta_creator_share
    else:
        raise KeyError(scenario_code)

    i_reg_new, i_risk_new, i_market_new, cpii_new = recompute_indices(
        updated,
        anchor_profiles,
        active_components,
        inactive_variables,
    )
    delta_cpii = (cpii_base - cpii_new) if cpii_new is not None else None
    priority_score = compute_priority_score(
        cpii_base=cpii_base,
        delta_cpii=delta_cpii or 0.0,
        recovered_revenue=recovered_revenue,
        market_revenue=market_revenue,
        domestic_capex_gain=domestic_capex_gain,
        revenue=revenue,
        npv_gain=npv_gain,
        content_investment=content_investment,
        creator_income_gain=creator_income_gain,
        eligible_revenue=max(eligible_revenue, market_revenue if scenario_code == "BND" else 1.0),
    )

    return {
        "scenario_code": scenario_code,
        "scenario_name": SCENARIO_LABELS[scenario_code],
        "CPII_scenario": cpii_new,
        "Delta_CPII": delta_cpii,
        "I_reg_scenario": i_reg_new,
        "I_risk_scenario": i_risk_new,
        "I_market_scenario": i_market_new,
        "Delta_I_reg": (float(baseline_row["I_reg_base"]) - i_reg_new) if i_reg_new is not None else None,
        "Delta_I_risk": (float(baseline_row["I_risk_base"]) - i_risk_new) if i_risk_new is not None else None,
        "Delta_I_market": (float(baseline_row["I_market_base"]) - i_market_new)
        if i_market_new is not None and baseline_row["I_market_base"] != ""
        else None,
        "RecoveredRevenue": recovered_revenue,
        "RecoveredCost": recovered_cost,
        "DomesticCapexGain": domestic_capex_gain,
        "NPVGain": npv_gain,
        "FinanceCapacity": finance_capacity,
        "CreatorIncomeGain": creator_income_gain,
        "local_platform_share_scenario": local_share_scenario,
        "policy_priority_score": priority_score,
        "updated_values": updated,
    }


def dense_rank_desc(values: list[tuple[str, float]]) -> dict[str, int]:
    ordered = sorted(values, key=lambda item: (-item[1], item[0]))
    out: dict[str, int] = {}
    rank = 0
    prev_value: float | None = None
    for key, value in ordered:
        if prev_value is None or value != prev_value:
            rank += 1
            prev_value = value
        out[key] = rank
    return out


def draw_tornado_chart(rows: list[dict[str, str]]) -> None:
    width, height = 1400, 900
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.load_default()
    text_font = ImageFont.load_default()

    draw.text((40, 25), "Policy Scenario Sensitivity Tornado", fill="black", font=title_font)
    draw.text(
        (40, 50),
        "Range uses latest sector-quarter baselines only; horizontal span = mean Delta_CPII from low to high sensitivity.",
        fill="black",
        font=text_font,
    )

    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row["scenario_selection_scope"] != "latest_sector_only":
            continue
        delta = safe_float(row["Delta_CPII"])
        if delta is None:
            continue
        grouped[row["scenario_code"]][row["sensitivity_case"]].append(delta)

    aggregated: list[dict[str, float | str]] = []
    for scenario_code in SCENARIO_ORDER:
        bucket = grouped.get(scenario_code, {})
        if not bucket:
            continue
        low = statistics.mean(bucket.get("low", [0.0]))
        base = statistics.mean(bucket.get("base", [0.0]))
        high = statistics.mean(bucket.get("high", [0.0]))
        aggregated.append(
            {
                "scenario_code": scenario_code,
                "scenario_name": SCENARIO_LABELS[scenario_code],
                "low": low,
                "base": base,
                "high": high,
                "range": high - low,
            }
        )

    aggregated.sort(key=lambda item: float(item["range"]), reverse=True)
    if not aggregated:
        FIGURE_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        image.save(FIGURE_OUTPUT_PATH)
        return

    min_x = min(float(item["low"]) for item in aggregated)
    max_x = max(float(item["high"]) for item in aggregated)
    x0 = 280
    x1 = width - 80
    usable = x1 - x0

    def x_pos(value: float) -> int:
        if max_x == min_x:
            return x0
        ratio = (value - min_x) / (max_x - min_x)
        return int(x0 + ratio * usable)

    axis_y = 120
    draw.line((x0, axis_y, x1, axis_y), fill="black", width=2)
    for tick in range(6):
        value = min_x + (max_x - min_x) * tick / 5.0
        xpos = x_pos(value)
        draw.line((xpos, axis_y - 6, xpos, axis_y + 6), fill="black", width=1)
        draw.text((xpos - 12, axis_y - 26), f"{value:.1f}", fill="black", font=text_font)

    colors = {
        "BND": "#3b82f6",
        "NET": "#10b981",
        "IPF": "#f59e0b",
        "CBA": "#ef4444",
    }

    start_y = 210
    step_y = 150
    for idx, item in enumerate(aggregated):
        y = start_y + idx * step_y
        low = float(item["low"])
        base = float(item["base"])
        high = float(item["high"])
        code = str(item["scenario_code"])

        draw.text((40, y - 18), f"{code} | {item['scenario_name']}", fill="black", font=title_font)
        draw.text((40, y + 6), f"low {low:.2f} | base {base:.2f} | high {high:.2f}", fill="black", font=text_font)

        xl = x_pos(low)
        xb = x_pos(base)
        xh = x_pos(high)
        color = colors.get(code, "#6b7280")
        draw.rounded_rectangle((xl, y, xh, y + 42), radius=10, fill=color, outline="black", width=1)
        draw.ellipse((xb - 7, y + 14, xb + 7, y + 28), fill="white", outline="black", width=2)

    FIGURE_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(FIGURE_OUTPUT_PATH)


def build_outputs() -> tuple[list[dict[str, str]], list[dict[str, str]], str]:
    baseline_rows = read_csv(BASELINE_INPUT_PATH)
    parameter_rows = read_csv(PARAM_INPUT_PATH)
    sector_rows = read_csv(VARIABLE_SECTOR_PATH)
    platform_rows = read_csv(VARIABLE_PLATFORM_Q_PATH)

    anchor_profiles, inactive_variables = build_anchor_profiles(sector_rows)
    active_components = subindex_components_active(anchor_profiles)
    parameter_lookup = scenario_parameter_map(parameter_rows)
    structural_lookup = build_structural_metric_lookup(sector_rows, platform_rows)

    latest_by_sector: dict[str, str] = {}
    for row in baseline_rows:
        sector = row["sector_std"]
        yq = row["year_quarter"]
        if sector not in latest_by_sector or quarter_index(yq) > quarter_index(latest_by_sector[sector]):
            latest_by_sector[sector] = yq

    scenario_summary_rows_numeric: list[dict[str, float | str]] = []
    sensitivity_rows_numeric: list[dict[str, float | str]] = []

    for baseline_row in baseline_rows:
        baseline_id = baseline_row["baseline_id"]
        coverage = set(baseline_row["scenario_coverage"].split("|"))
        raw_values, lookup_notes = enrich_baseline_raw_variables(baseline_row, structural_lookup)

        for scenario_code in SCENARIO_ORDER:
            if scenario_code not in coverage:
                continue

            base_params = parameter_lookup[baseline_id][scenario_code]
            if not base_params:
                continue

            sensitivity_cache: dict[str, dict[str, float | str]] = {}
            for sensitivity_case, scale in SENSITIVITY_SCALES.items():
                params = scaled_parameters(base_params, scale)
                result = evaluate_scenario(
                    baseline_row=baseline_row,
                    raw_values=raw_values,
                    scenario_code=scenario_code,
                    params=params,
                    anchor_profiles=anchor_profiles,
                    active_components=active_components,
                    inactive_variables=inactive_variables,
                )
                result.update(
                    {
                        "baseline_id": baseline_id,
                        "sector_std": baseline_row["sector_std"],
                        "year_quarter": baseline_row["year_quarter"],
                        "scenario_code": scenario_code,
                        "sensitivity_case": sensitivity_case,
                        "scale_factor": scale,
                        "scenario_selection_scope": "latest_sector_only"
                        if latest_by_sector[baseline_row["sector_std"]] == baseline_row["year_quarter"]
                        else "all_computed_baselines",
                        "lookup_note_summary": "|".join(lookup_notes),
                    }
                )
                sensitivity_cache[sensitivity_case] = result
                sensitivity_rows_numeric.append(result)

            scenario_summary_rows_numeric.append(sensitivity_cache["base"])

    # Rank within each sector-quarter.
    grouped_for_rank: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
    for row in scenario_summary_rows_numeric:
        key = (str(row["sector_std"]), str(row["year_quarter"]))
        grouped_for_rank[key].append((str(row["scenario_code"]), float(row["policy_priority_score"])))

    rank_lookup: dict[tuple[str, str, str], int] = {}
    for key, values in grouped_for_rank.items():
        ranking = dense_rank_desc(values)
        for scenario_code, rank in ranking.items():
            rank_lookup[(key[0], key[1], scenario_code)] = rank

    # Overall priority among latest sector baselines.
    latest_grouped: dict[str, list[float]] = defaultdict(list)
    for row in scenario_summary_rows_numeric:
        if row["year_quarter"] == latest_by_sector[str(row["sector_std"])]:
            latest_grouped[str(row["scenario_code"])].append(float(row["policy_priority_score"]))
    overall_scores = {
        scenario_code: statistics.mean(values)
        for scenario_code, values in latest_grouped.items()
        if values
    }
    overall_ranks = dense_rank_desc(list(overall_scores.items()))

    summary_rows: list[dict[str, str]] = []
    for idx, row in enumerate(scenario_summary_rows_numeric, start=1):
        sector = str(row["sector_std"])
        yq = str(row["year_quarter"])
        scenario_code = str(row["scenario_code"])
        baseline_id = str(row["baseline_id"])
        base_row = next(item for item in baseline_rows if item["baseline_id"] == baseline_id)
        summary_rows.append(
            {
                "scenario_result_id": f"scenario_{idx:03d}",
                "baseline_id": baseline_id,
                "sector_std": sector,
                "year_quarter": yq,
                "scenario_code": scenario_code,
                "scenario_name": SCENARIO_LABELS[scenario_code],
                "policy_priority_rank_within_sector_quarter": str(
                    rank_lookup[(sector, yq, scenario_code)]
                ),
                "policy_priority_score": fmt(float(row["policy_priority_score"])),
                "overall_policy_priority_latest_rank": str(overall_ranks.get(scenario_code, "")),
                "overall_policy_priority_latest_score": fmt(overall_scores.get(scenario_code)),
                "CPII_base": base_row["CPII_base"],
                "CPII_scenario": fmt(safe_float(str(row["CPII_scenario"]))),
                "Delta_CPII": fmt(safe_float(str(row["Delta_CPII"]))),
                "I_reg_scenario": fmt(safe_float(str(row["I_reg_scenario"]))),
                "I_risk_scenario": fmt(safe_float(str(row["I_risk_scenario"]))),
                "I_market_scenario": fmt(safe_float(str(row["I_market_scenario"]))),
                "Delta_I_reg": fmt(safe_float(str(row["Delta_I_reg"]))),
                "Delta_I_risk": fmt(safe_float(str(row["Delta_I_risk"]))),
                "Delta_I_market": fmt(safe_float(str(row["Delta_I_market"]))),
                "RecoveredRevenue": fmt_amount(float(row["RecoveredRevenue"])),
                "RecoveredCost": fmt_amount(float(row["RecoveredCost"])),
                "DomesticCapexGain": fmt_amount(float(row["DomesticCapexGain"])),
                "NPVGain": fmt_amount(float(row["NPVGain"])),
                "FinanceCapacity": fmt_amount(float(row["FinanceCapacity"])),
                "CreatorIncomeGain": fmt_amount(float(row["CreatorIncomeGain"])),
                "local_platform_share_base": base_row["local_platform_share_base"],
                "local_platform_share_scenario": fmt(float(row["local_platform_share_scenario"])),
                "parameter_names": "|".join(sorted(parameter_lookup[baseline_id][scenario_code].keys())),
                "parameter_values_base": "|".join(
                    f"{name}:{fmt(value)}"
                    for name, value in sorted(parameter_lookup[baseline_id][scenario_code].items())
                ),
                "lookup_note_summary": str(row["lookup_note_summary"]),
            }
        )

    sensitivity_rows: list[dict[str, str]] = []
    for idx, row in enumerate(sensitivity_rows_numeric, start=1):
        baseline_id = str(row["baseline_id"])
        scenario_code = str(row["scenario_code"])
        base_row = next(item for item in baseline_rows if item["baseline_id"] == baseline_id)
        sensitivity_rows.append(
            {
                "sensitivity_id": f"sensitivity_{idx:03d}",
                "baseline_id": baseline_id,
                "sector_std": str(row["sector_std"]),
                "year_quarter": str(row["year_quarter"]),
                "scenario_code": scenario_code,
                "scenario_name": SCENARIO_LABELS[scenario_code],
                "sensitivity_case": str(row["sensitivity_case"]),
                "scale_factor": fmt(float(row["scale_factor"])),
                "scenario_selection_scope": str(row["scenario_selection_scope"]),
                "Delta_CPII": fmt(safe_float(str(row["Delta_CPII"]))),
                "RecoveredRevenue": fmt_amount(float(row["RecoveredRevenue"])),
                "DomesticCapexGain": fmt_amount(float(row["DomesticCapexGain"])),
                "NPVGain": fmt_amount(float(row["NPVGain"])),
                "CreatorIncomeGain": fmt_amount(float(row["CreatorIncomeGain"])),
                "policy_priority_score": fmt(float(row["policy_priority_score"])),
                "CPII_base": base_row["CPII_base"],
                "CPII_scenario": fmt(safe_float(str(row["CPII_scenario"]))),
                "parameter_values_scaled": "|".join(
                    f"{name}:{fmt(value)}"
                    for name, value in sorted(
                        scaled_parameters(
                            parameter_lookup[baseline_id][scenario_code],
                            float(row["scale_factor"]),
                        ).items()
                    )
                ),
                "lookup_note_summary": str(row["lookup_note_summary"]),
            }
        )

    # Logging summary.
    status_counter = Counter(row["scenario_code"] for row in summary_rows)
    latest_priority_lines = []
    for scenario_code, score in sorted(overall_scores.items(), key=lambda item: (-item[1], item[0])):
        latest_priority_lines.append(
            f"- `{scenario_code}`: latest-baseline mean priority score `{score:.6f}`, rank `{overall_ranks[scenario_code]}`"
        )

    delta_by_scenario = defaultdict(list)
    for row in summary_rows:
        delta = safe_float(row["Delta_CPII"])
        if delta is not None:
            delta_by_scenario[row["scenario_code"]].append(delta)

    delta_lines = []
    for scenario_code in SCENARIO_ORDER:
        values = delta_by_scenario.get(scenario_code, [])
        if not values:
            continue
        delta_lines.append(
            f"- `{scenario_code}`: count `{len(values)}`, mean `{statistics.mean(values):.4f}`, max `{max(values):.4f}`"
        )

    log_text = "\n".join(
        [
            "# Policy Scenario Log",
            "",
            "## Overview",
            f"- Base scenario rows: `{len(summary_rows)}`",
            f"- Sensitivity rows: `{len(sensitivity_rows)}`",
            f"- Scenario coverage split: `{dict(status_counter)}`",
            "",
            "## Calculation Rules",
            "- Uses the calibrated baseline inputs from Prompt 33 and re-applies the simulator formulas in the report for `BND`, `NET`, `IPF`, and `CBA`.",
            "- For each scenario, only the variables directly named in the report equation are changed; all other raw variables remain fixed at baseline values.",
            "- Updated raw variables are passed through the original CPII anchor profiles from `variable_panel_sector_quarter.csv`, then `I_reg`, `I_risk`, `I_market`, and `CPII` are recomputed with the same equal-weight and missing-value rules used in Prompts 25 and 26.",
            "- Sensitivity uses bounded common scaling: `low=0.8`, `base=1.0`, `high=1.2` applied to every parameter in the scenario-specific calibrated set.",
            "",
            "## Delta_CPII Summary",
            *delta_lines,
            "",
            "## Latest-Baseline Policy Priority",
            *latest_priority_lines,
            "",
            "## Notes",
            "- `digital_infra` only participates in `NET` because Prompt 33 fixed its scenario coverage to `NET|MON`.",
            "- `RecoveredRevenue`, `DomesticCapexGain`, `NPVGain`, and `CreatorIncomeGain` are reported together in the summary table; metrics not directly generated by a scenario are kept at `0` rather than left missing so policy comparisons remain rectangular.",
            "- `BND` can improve `I_market` only through variables that remain active in the CPII anchor profile. In the current build, `bundle_leverage_index` stays structurally weak in the anchor set, so most of the CPII movement comes from `cross_market_transfer_index` and not from the bundle term itself.",
        ]
    )

    return summary_rows, sensitivity_rows, log_text


def main() -> None:
    summary_rows, sensitivity_rows, log_text = build_outputs()

    summary_fieldnames = [
        "scenario_result_id",
        "baseline_id",
        "sector_std",
        "year_quarter",
        "scenario_code",
        "scenario_name",
        "policy_priority_rank_within_sector_quarter",
        "policy_priority_score",
        "overall_policy_priority_latest_rank",
        "overall_policy_priority_latest_score",
        "CPII_base",
        "CPII_scenario",
        "Delta_CPII",
        "I_reg_scenario",
        "I_risk_scenario",
        "I_market_scenario",
        "Delta_I_reg",
        "Delta_I_risk",
        "Delta_I_market",
        "RecoveredRevenue",
        "RecoveredCost",
        "DomesticCapexGain",
        "NPVGain",
        "FinanceCapacity",
        "CreatorIncomeGain",
        "local_platform_share_base",
        "local_platform_share_scenario",
        "parameter_names",
        "parameter_values_base",
        "lookup_note_summary",
    ]
    sensitivity_fieldnames = [
        "sensitivity_id",
        "baseline_id",
        "sector_std",
        "year_quarter",
        "scenario_code",
        "scenario_name",
        "sensitivity_case",
        "scale_factor",
        "scenario_selection_scope",
        "Delta_CPII",
        "RecoveredRevenue",
        "DomesticCapexGain",
        "NPVGain",
        "CreatorIncomeGain",
        "policy_priority_score",
        "CPII_base",
        "CPII_scenario",
        "parameter_values_scaled",
        "lookup_note_summary",
    ]

    SUMMARY_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SENSITIVITY_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with SUMMARY_OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)
    with SENSITIVITY_OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=sensitivity_fieldnames)
        writer.writeheader()
        writer.writerows(sensitivity_rows)

    draw_tornado_chart(sensitivity_rows)
    LOG_OUTPUT_PATH.write_text(log_text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
