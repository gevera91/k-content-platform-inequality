from __future__ import annotations

import csv
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CPII_SQ_PATH = ROOT / "data/processed/cpii_panel_sector_quarter.csv"
VARIABLE_SECTOR_PATH = ROOT / "data/processed/variable_panel_sector_quarter.csv"
VARIABLE_PLATFORM_Q_PATH = ROOT / "data/processed/variable_panel_platform_quarter.csv"
STANDARDIZED_NUMERIC_PATH = ROOT / "data/interim/standardized_numeric_panel.csv"
INFRA_RAW_PATH = ROOT / "data/interim/infra_service_raw_panel.csv"

REGRESSION_PATHS = [
    ROOT / "outputs/tables/regression_results_music.csv",
    ROOT / "outputs/tables/regression_results_webtoon.csv",
    ROOT / "outputs/tables/regression_results_infra.csv",
    ROOT / "outputs/tables/regression_results_cross_country.csv",
]

BASELINE_OUTPUT_PATH = ROOT / "data/processed/policy_simulator_baseline_inputs.csv"
PARAM_OUTPUT_PATH = ROOT / "data/processed/policy_simulator_calibrated_parameters.csv"
LOG_OUTPUT_PATH = ROOT / "logs/policy_calibration_log.md"

PARAM_BOUNDS: dict[str, tuple[float, float]] = {
    "rho_bundle": (0.0, 1.0),
    "eta_transfer": (0.0, 1.5),
    "eta_share": (0.0, 1.0),
    "phi_recover": (0.0, 1.0),
    "psi_capex": (0.0, 1.0),
    "kappa_replace": (0.0, 1.0),
    "alpha_ip": (0.0, 1.0),
    "lambda_advance": (0.0, 1.0),
    "eta_funding": (0.0, 2.0),
    "eta_recovery": (0.0, 2.0),
    "theta_bargain": (0.0, 1.0),
    "eta_cash": (0.0, 1.0),
}

PARAMETER_SCENARIO = {
    "rho_bundle": "BND",
    "eta_transfer": "BND",
    "eta_share": "BND",
    "phi_recover": "NET",
    "psi_capex": "NET",
    "kappa_replace": "NET",
    "alpha_ip": "IPF",
    "lambda_advance": "IPF",
    "eta_funding": "IPF",
    "eta_recovery": "IPF",
    "theta_bargain": "CBA",
    "eta_cash": "CBA",
}

SECTOR_SCENARIO_COVERAGE = {
    "music": {"BND", "NET", "IPF", "CBA", "MON"},
    "webtoon_story": {"BND", "NET", "IPF", "CBA", "MON"},
    "digital_infra": {"NET", "MON"},
}

STRUCTURAL_METRICS = [
    "bundle_leverage_index",
    "cross_market_transfer_index",
    "foreign_dependency_ratio",
    "outflow_to_capex_ratio",
    "network_cost_ratio",
    "investment_recovery_ratio",
    "cashflow_recovery_ratio",
    "ip_assetization_gap",
    "creator_share_ratio",
    "effective_tax_rate_gap",
    "infra_dependency_ratio",
    "funding_cost_spread",
]

AMOUNT_METRICS = [
    "revenue",
    "pretax_income",
    "content_investment",
    "intangible_assets",
    "capex",
    "network_cloud_cost",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def to_float(value: str | float | int | None) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def safe_div(numerator: float | None, denominator: float | None, default: float = 0.0) -> float:
    if numerator is None or denominator in (None, 0.0):
        return default
    return float(numerator) / float(denominator)


def quarter_index(value: str) -> int:
    year = int(value[:4])
    quarter = int(value[-1])
    return year * 4 + quarter - 1


def fmt_ratio(value: float | None) -> str:
    if value is None or math.isnan(value):
        return ""
    return f"{value:.10f}"


def fmt_amount(value: float | None) -> str:
    if value is None or math.isnan(value):
        return ""
    return f"{value:.2f}"


def build_regression_lookup() -> dict[str, dict[str, float | str]]:
    rows: list[dict[str, str]] = []
    for path in REGRESSION_PATHS:
        rows.extend(read_csv(path))

    def find_row(sector: str, model_id: str, explanatory: str) -> dict[str, str]:
        for row in rows:
            if (
                row["sector_std"] == sector
                and row["model_id"] == model_id
                and row["explanatory_variable"] == explanatory
            ):
                return row
        raise KeyError(f"Missing regression row for {sector} | {model_id} | {explanatory}")

    evidence = {
        "cross_reg_market": find_row(
            "cross_country",
            "cross_country_sector_country_panel",
            "I_reg",
        ),
        "cross_risk_market": find_row(
            "cross_country",
            "cross_country_sector_country_panel",
            "I_risk",
        ),
        "music_foreign_recovery": find_row(
            "music",
            "music_service_month_fe_main",
            "foreign_dependency_ratio",
        ),
        "webtoon_foreign_recovery": find_row(
            "webtoon_story",
            "webtoon_service_quarter_fe_main",
            "foreign_dependency_ratio",
        ),
        "infra_foreign_outflow": find_row(
            "digital_infra",
            "infra_service_quarter_fe_main",
            "foreign_dependency_ratio",
        ),
        "infra_network_outflow": find_row(
            "digital_infra",
            "infra_service_quarter_fe_main",
            "network_cost_ratio",
        ),
    }

    for key, row in evidence.items():
        coef = abs(float(row["coefficient"]))
        std = abs(float(row["standard_error"]))
        p_value = clip(float(row["p_value"]), 0.0, 1.0)
        magnitude = coef / (coef + std + 1e-9)
        reliability = 1.0 - p_value
        row["magnitude_score"] = magnitude
        row["reliability_score"] = reliability
        row["effective_strength"] = magnitude * reliability

    return evidence


def build_structural_metric_lookup(
    sector_rows: list[dict[str, str]],
    platform_rows: list[dict[str, str]],
) -> dict[str, dict[str, list[tuple[str, float, str]]]]:
    by_metric_sector: dict[str, dict[str, list[tuple[str, float, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )

    platform_bucket: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for row in platform_rows:
        sector = row["sector_std"]
        yq = row["year_quarter"]
        for metric in STRUCTURAL_METRICS:
            value = to_float(row.get(metric, ""))
            if value is not None:
                platform_bucket[(metric, sector, yq)].append(value)

    for (metric, sector, yq), values in platform_bucket.items():
        by_metric_sector[metric][sector].append(
            (yq, statistics.median(values), "platform_quarter_median")
        )

    sector_best: dict[tuple[str, str, str], float] = {}
    for row in sector_rows:
        sector = row["sector_std"]
        yq = row["year_quarter"]
        for metric in STRUCTURAL_METRICS:
            key = (metric, sector, yq)
            value = to_float(row.get(metric, ""))
            if value is None or key in sector_best:
                continue
            sector_best[key] = value

    for (metric, sector, yq), value in sector_best.items():
        existing_quarters = {quarter for quarter, _, _ in by_metric_sector[metric][sector]}
        if yq not in existing_quarters:
            by_metric_sector[metric][sector].append((yq, value, "sector_quarter_fallback"))

    for metric in by_metric_sector:
        for sector in by_metric_sector[metric]:
            by_metric_sector[metric][sector].sort(key=lambda item: quarter_index(item[0]))

    return by_metric_sector


def lookup_structural_metric(
    lookup: dict[str, dict[str, list[tuple[str, float, str]]]],
    metric: str,
    sector: str,
    target_yq: str,
) -> tuple[float | None, str, str]:
    series = lookup.get(metric, {}).get(sector, [])
    if not series:
        return None, "", "missing"

    target_idx = quarter_index(target_yq)
    prior = [item for item in series if quarter_index(item[0]) <= target_idx]
    if prior:
        yq, value, source = prior[-1]
        return value, yq, source

    yq, value, source = series[-1]
    return value, yq, f"{source}_backfilled_from_latest_available"


def build_amount_lookup(
    standardized_rows: list[dict[str, str]],
) -> tuple[
    dict[str, dict[str, list[tuple[str, float]]]],
    dict[str, dict[str, list[tuple[str, float]]]],
]:
    exact: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    positive: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))

    for row in standardized_rows:
        if row["source_panel"] != "financial_extraction_panel":
            continue
        metric = row["metric_name"]
        if metric not in AMOUNT_METRICS:
            continue
        sector = row["sector_std"]
        yq = row["year_quarter"]
        value = to_float(row["metric_value_krw_nominal"])
        if value is None:
            continue
        exact[metric][sector][yq] = exact[metric][sector].get(yq, 0.0) + value
        positive[metric][sector][yq] = positive[metric][sector].get(yq, 0.0) + max(value, 0.0)

    exact_sorted: dict[str, dict[str, list[tuple[str, float]]]] = defaultdict(lambda: defaultdict(list))
    positive_sorted: dict[str, dict[str, list[tuple[str, float]]]] = defaultdict(lambda: defaultdict(list))

    for metric, sector_map in exact.items():
        for sector, yq_map in sector_map.items():
            exact_sorted[metric][sector] = sorted(yq_map.items(), key=lambda item: quarter_index(item[0]))
    for metric, sector_map in positive.items():
        for sector, yq_map in sector_map.items():
            positive_sorted[metric][sector] = sorted(
                yq_map.items(), key=lambda item: quarter_index(item[0])
            )

    return exact_sorted, positive_sorted


def lookup_amount(
    lookup: dict[str, dict[str, list[tuple[str, float]]]],
    metric: str,
    sector: str,
    target_yq: str,
) -> tuple[float | None, str, str]:
    series = lookup.get(metric, {}).get(sector, [])
    if not series:
        return None, "", "missing"

    target_idx = quarter_index(target_yq)
    prior = [item for item in series if quarter_index(item[0]) <= target_idx]
    if not prior:
        return None, "", "missing_before_target"
    yq, value = prior[-1]
    status = "exact" if yq == target_yq else "carry_forward_from_latest_prior"
    return value, yq, status


def build_infra_quarter_lookup(
    infra_rows: list[dict[str, str]],
) -> dict[str, list[tuple[str, float]]]:
    bucket: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in infra_rows:
        metric = row["metric_name"]
        if metric not in {"traffic_cost_pressure", "domestic_infra_capex_ratio"}:
            continue
        value = to_float(row["metric_value"])
        if value is None:
            continue
        bucket[metric][row["year_quarter"]].append(value)

    out: dict[str, list[tuple[str, float]]] = {}
    for metric, yq_map in bucket.items():
        out[metric] = sorted(
            [(yq, statistics.mean(values)) for yq, values in yq_map.items()],
            key=lambda item: quarter_index(item[0]),
        )
    return out


def lookup_infra_quarter_metric(
    lookup: dict[str, list[tuple[str, float]]],
    metric: str,
    target_yq: str,
) -> tuple[float | None, str, str]:
    series = lookup.get(metric, [])
    if not series:
        return None, "", "missing"
    target_idx = quarter_index(target_yq)
    prior = [item for item in series if quarter_index(item[0]) <= target_idx]
    if prior:
        yq, value = prior[-1]
        status = "exact" if yq == target_yq else "carry_forward_from_latest_prior"
        return value, yq, status
    return None, "", "missing_before_target"


def build_baseline_rows() -> tuple[list[dict[str, str]], dict[str, dict[str, float | str]], dict[str, dict[str, float | str]]]:
    regression = build_regression_lookup()
    cpii_rows = [row for row in read_csv(CPII_SQ_PATH) if row["cpii_status"] == "computed"]
    sector_rows = read_csv(VARIABLE_SECTOR_PATH)
    platform_rows = read_csv(VARIABLE_PLATFORM_Q_PATH)
    standardized_rows = read_csv(STANDARDIZED_NUMERIC_PATH)
    infra_rows = read_csv(INFRA_RAW_PATH)

    structural_lookup = build_structural_metric_lookup(sector_rows, platform_rows)
    amount_lookup, positive_amount_lookup = build_amount_lookup(standardized_rows)
    infra_lookup = build_infra_quarter_lookup(infra_rows)

    regression_strengths = {
        "reg_market": float(regression["cross_reg_market"]["effective_strength"]),
        "risk_market": float(regression["cross_risk_market"]["effective_strength"]),
        "music_recovery": float(regression["music_foreign_recovery"]["effective_strength"]),
        "webtoon_recovery": float(regression["webtoon_foreign_recovery"]["effective_strength"]),
        "infra_foreign": float(regression["infra_foreign_outflow"]["effective_strength"]),
        "infra_network": float(regression["infra_network_outflow"]["effective_strength"]),
    }

    baseline_rows: list[dict[str, str]] = []
    baseline_numeric: dict[str, dict[str, float | str]] = {}

    for idx, row in enumerate(cpii_rows, start=1):
        sector = row["sector_std"]
        yq = row["year_quarter"]
        baseline_id = f"baseline_{idx:03d}"

        cpii = to_float(row["CPII"]) or 0.0
        i_reg = to_float(row["I_reg"]) or 0.0
        i_risk = to_float(row["I_risk"]) or 0.0
        i_market = to_float(row["I_market"]) or 0.0
        reg_pressure = clip(i_reg / 100.0, 0.0, 1.0)
        risk_pressure = clip(i_risk / 100.0, 0.0, 1.0)
        market_pressure = clip(i_market / 100.0, 0.0, 1.0)

        revenue, revenue_yq, revenue_status = lookup_amount(amount_lookup, "revenue", sector, yq)
        pretax_income, pretax_yq, pretax_status = lookup_amount(
            amount_lookup, "pretax_income", sector, yq
        )
        content_investment_pos, content_yq, content_status = lookup_amount(
            positive_amount_lookup, "content_investment", sector, yq
        )
        content_investment_raw, _, _ = lookup_amount(amount_lookup, "content_investment", sector, yq)
        intangible_assets, intangible_yq, intangible_status = lookup_amount(
            amount_lookup, "intangible_assets", sector, yq
        )
        capex, capex_yq, capex_status = lookup_amount(amount_lookup, "capex", sector, yq)
        network_cloud_cost, _, _ = lookup_amount(amount_lookup, "network_cloud_cost", sector, yq)

        if revenue is None:
            raise RuntimeError(f"Missing revenue baseline for {sector} {yq}")

        # Keep content investment positive for denominator use. When extracted values are structurally
        # negative or unavailable, fall back to a conservative share of revenue and intangible assets.
        if content_investment_pos is None or content_investment_pos <= 0:
            fallback_revenue_component = 0.03 * revenue
            fallback_ip_component = 0.10 * (intangible_assets or 0.0)
            content_investment = max(fallback_revenue_component, fallback_ip_component, 1.0)
            content_status = "derived_from_revenue_or_intangibles"
            content_yq = intangible_yq or revenue_yq
        else:
            content_investment = content_investment_pos

        bundle_value, bundle_yq, bundle_status = lookup_structural_metric(
            structural_lookup, "bundle_leverage_index", sector, yq
        )
        cross_value, cross_yq, cross_status = lookup_structural_metric(
            structural_lookup, "cross_market_transfer_index", sector, yq
        )
        foreign_value, foreign_yq, foreign_status = lookup_structural_metric(
            structural_lookup, "foreign_dependency_ratio", sector, yq
        )
        outflow_value, outflow_yq, outflow_status = lookup_structural_metric(
            structural_lookup, "outflow_to_capex_ratio", sector, yq
        )
        network_value, network_yq, network_status = lookup_structural_metric(
            structural_lookup, "network_cost_ratio", sector, yq
        )
        investment_recovery, invrec_yq, invrec_status = lookup_structural_metric(
            structural_lookup, "investment_recovery_ratio", sector, yq
        )
        cashflow_recovery, cash_yq, cash_status = lookup_structural_metric(
            structural_lookup, "cashflow_recovery_ratio", sector, yq
        )
        ip_gap, ip_yq, ip_status = lookup_structural_metric(
            structural_lookup, "ip_assetization_gap", sector, yq
        )
        creator_share, creator_yq, creator_status = lookup_structural_metric(
            structural_lookup, "creator_share_ratio", sector, yq
        )
        funding_spread, funding_yq, funding_status = lookup_structural_metric(
            structural_lookup, "funding_cost_spread", sector, yq
        )

        if foreign_value is None:
            foreign_value = market_pressure
            foreign_status = "derived_from_i_market"
        foreign_value = clip(foreign_value, 0.0, 1.0)

        if bundle_value is None:
            bundle_value = clip(0.5 * market_pressure + 0.25 * reg_pressure, 0.0, 1.0)
            bundle_status = "derived_from_subindices"
        else:
            bundle_value = clip(bundle_value, 0.0, 1.0)

        if cross_value is None:
            cross_value = clip(0.75 * market_pressure + 0.25 * bundle_value, 0.0, 1.0)
            cross_status = "derived_from_i_market_and_bundle"
        else:
            cross_value = clip(cross_value, 0.0, 1.0)

        if network_value is None:
            network_value = safe_div(network_cloud_cost, revenue, 0.0)
            network_status = "derived_from_network_cloud_cost_over_revenue"
        network_value = max(network_value, 0.0)

        if outflow_value is None:
            outflow_value = safe_div(network_cloud_cost, capex, 0.0)
            outflow_status = "derived_from_network_cloud_cost_over_capex"
        outflow_value = max(outflow_value, 0.0)

        if investment_recovery is None:
            investment_recovery = safe_div(pretax_income, content_investment, 0.0) * 100.0
            invrec_status = "derived_from_pretax_income_over_content_investment"

        if cashflow_recovery is None:
            cashflow_recovery = safe_div(pretax_income, content_investment, 0.0) * 100.0
            cash_status = "derived_from_pretax_income_over_content_investment"

        if ip_gap is None:
            ip_gap = max(0.0, 1.0 - safe_div(intangible_assets, content_investment, 0.0))
            ip_status = "derived_from_intangibles_gap_proxy"

        if funding_spread is None:
            funding_spread = 0.0
            funding_status = "imputed_zero_due_missing_direct_spread"

        if creator_share is None:
            creator_share = clip(
                0.50 + 0.25 * math.tanh((cashflow_recovery or 0.0) / 25.0) - 0.15 * risk_pressure,
                0.15,
                0.85,
            )
            creator_status = "derived_from_cashflow_and_i_risk_proxy"
        else:
            creator_share = clip(creator_share, 0.0, 1.0)

        local_platform_share = clip(1.0 - foreign_value, 0.05, 0.95)

        direct_domestic_capex, domcap_yq, domcap_status = lookup_infra_quarter_metric(
            infra_lookup, "domestic_infra_capex_ratio", yq
        )
        if sector == "digital_infra" and direct_domestic_capex is not None:
            domestic_capex_ratio = clip(direct_domestic_capex, 0.0, 1.0)
        else:
            domestic_capex_ratio = clip(safe_div(capex, revenue, 0.0), 0.0, 1.0)
            domcap_status = "derived_from_capex_over_revenue"
            domcap_yq = capex_yq

        direct_traffic, traffic_yq, traffic_status = lookup_infra_quarter_metric(
            infra_lookup, "traffic_cost_pressure", yq
        )
        if sector == "digital_infra" and direct_traffic is not None:
            traffic_cost_pressure = clip(direct_traffic, 0.0, 1.0)
        else:
            traffic_cost_pressure = clip(foreign_value * max(network_value, 0.0), 0.0, 1.0)
            traffic_status = "derived_from_foreign_dependency_x_network_cost"
            traffic_yq = network_yq or foreign_yq

        ip_gap_need = clip(max(ip_gap, 0.0), 0.0, 1.0)
        funding_need = clip(max(funding_spread, 0.0) / (0.05 + max(funding_spread, 0.0)), 0.0, 1.0)
        recovery_shortfall = clip((50.0 - investment_recovery) / 100.0, 0.0, 1.0)
        creator_gap = clip(1.0 - creator_share, 0.0, 1.0)
        cashflow_gap = clip((25.0 - cashflow_recovery) / 50.0, 0.0, 1.0)

        securitization_multiplier = clip(
            0.05
            + 0.50 * ip_gap_need
            + 0.25 * funding_need
            + 0.20 * recovery_shortfall
            + 0.15 * regression_strengths["risk_market"],
            0.05,
            0.80,
        )
        securitization_npv_delta = content_investment * securitization_multiplier

        if sector in {"music", "webtoon_story"}:
            collective_bargaining_premium = clip(
                0.02 + 0.25 * creator_gap + 0.10 * cashflow_gap + 0.05 * risk_pressure,
                0.02,
                0.30,
            )
            eligible_revenue = revenue * local_platform_share
            collective_status = "calibrated_from_creator_gap_and_cashflow_gap"
        else:
            collective_bargaining_premium = 0.0
            eligible_revenue = 0.0
            collective_status = "not_applicable_non_creator_sector"

        scenario_coverage = "|".join(sorted(SECTOR_SCENARIO_COVERAGE[sector]))
        note_parts = [
            f"revenue:{revenue_status}",
            f"pretax:{pretax_status}",
            f"content:{content_status}",
            f"intangible:{intangible_status}",
            f"capex:{capex_status}",
            f"bundle:{bundle_status}",
            f"transfer:{cross_status}",
            f"foreign:{foreign_status}",
            f"network:{network_status}",
            f"traffic:{traffic_status}",
            f"creator:{creator_status}",
            f"collective:{collective_status}",
        ]

        baseline_rows.append(
            {
                "baseline_id": baseline_id,
                "sector_std": sector,
                "year_quarter": yq,
                "scenario_coverage": scenario_coverage,
                "baseline_status": "ready",
                "CPII_base": fmt_ratio(cpii),
                "I_reg_base": fmt_ratio(i_reg),
                "I_risk_base": fmt_ratio(i_risk),
                "I_market_base": fmt_ratio(i_market),
                "local_platform_share_base": fmt_ratio(local_platform_share),
                "market_revenue_krw_nominal": fmt_amount(revenue),
                "revenue_krw_nominal": fmt_amount(revenue),
                "pretax_income_krw_nominal": fmt_amount(pretax_income),
                "content_investment_krw_nominal": fmt_amount(content_investment),
                "intangible_assets_krw_nominal": fmt_amount(intangible_assets),
                "capex_krw_nominal": fmt_amount(capex),
                "domestic_capex_ratio_base": fmt_ratio(domestic_capex_ratio),
                "bundle_leverage_index_base": fmt_ratio(bundle_value),
                "cross_market_transfer_index_base": fmt_ratio(cross_value),
                "traffic_cost_pressure_base": fmt_ratio(traffic_cost_pressure),
                "network_cost_ratio_base": fmt_ratio(network_value),
                "foreign_dependency_ratio_base": fmt_ratio(foreign_value),
                "outflow_to_capex_ratio_base": fmt_ratio(outflow_value),
                "ip_assetization_gap_base": fmt_ratio(ip_gap),
                "funding_cost_spread_base": fmt_ratio(funding_spread),
                "investment_recovery_ratio_base": fmt_ratio(investment_recovery),
                "creator_share_ratio_base": fmt_ratio(creator_share),
                "cashflow_recovery_ratio_base": fmt_ratio(cashflow_recovery),
                "securitization_npv_delta_krw_nominal": fmt_amount(securitization_npv_delta),
                "collective_bargaining_premium_base": fmt_ratio(collective_bargaining_premium),
                "eligible_revenue_krw_nominal": fmt_amount(eligible_revenue),
                "revenue_source_year_quarter": revenue_yq,
                "pretax_source_year_quarter": pretax_yq,
                "content_investment_source_year_quarter": content_yq,
                "intangible_assets_source_year_quarter": intangible_yq,
                "capex_source_year_quarter": capex_yq,
                "baseline_notes": "; ".join(note_parts),
            }
        )

        baseline_numeric[baseline_id] = {
            "sector_std": sector,
            "year_quarter": yq,
            "CPII_base": cpii,
            "I_reg_base": i_reg,
            "I_risk_base": i_risk,
            "I_market_base": i_market,
            "reg_pressure": reg_pressure,
            "risk_pressure": risk_pressure,
            "market_pressure": market_pressure,
            "local_platform_share_base": local_platform_share,
            "market_revenue_krw_nominal": revenue,
            "revenue_krw_nominal": revenue,
            "pretax_income_krw_nominal": pretax_income or 0.0,
            "content_investment_krw_nominal": content_investment,
            "intangible_assets_krw_nominal": intangible_assets or 0.0,
            "capex_krw_nominal": capex or 0.0,
            "domestic_capex_ratio_base": domestic_capex_ratio,
            "bundle_leverage_index_base": bundle_value,
            "cross_market_transfer_index_base": cross_value,
            "traffic_cost_pressure_base": traffic_cost_pressure,
            "network_cost_ratio_base": network_value,
            "foreign_dependency_ratio_base": foreign_value,
            "outflow_to_capex_ratio_base": outflow_value,
            "ip_assetization_gap_base": ip_gap,
            "funding_cost_spread_base": funding_spread,
            "investment_recovery_ratio_base": investment_recovery,
            "creator_share_ratio_base": creator_share,
            "cashflow_recovery_ratio_base": cashflow_recovery,
            "securitization_npv_delta_krw_nominal": securitization_npv_delta,
            "collective_bargaining_premium_base": collective_bargaining_premium,
            "eligible_revenue_krw_nominal": eligible_revenue,
            "scenario_coverage": scenario_coverage,
        }

    return baseline_rows, baseline_numeric, regression


def calibrate_parameter(
    parameter_name: str,
    baseline: dict[str, float | str],
    regression: dict[str, dict[str, float | str]],
) -> tuple[float, str, str]:
    lower, upper = PARAM_BOUNDS[parameter_name]

    sector = str(baseline["sector_std"])
    local_share = float(baseline["local_platform_share_base"])
    market_pressure = float(baseline["market_pressure"])
    risk_pressure = float(baseline["risk_pressure"])
    bundle_value = float(baseline["bundle_leverage_index_base"])
    cross_value = float(baseline["cross_market_transfer_index_base"])
    traffic_pressure = float(baseline["traffic_cost_pressure_base"])
    domestic_capex_ratio = float(baseline["domestic_capex_ratio_base"])
    foreign_value = float(baseline["foreign_dependency_ratio_base"])
    outflow_value = float(baseline["outflow_to_capex_ratio_base"])
    ip_gap = float(baseline["ip_assetization_gap_base"])
    funding_spread = float(baseline["funding_cost_spread_base"])
    investment_recovery = float(baseline["investment_recovery_ratio_base"])
    creator_share = float(baseline["creator_share_ratio_base"])
    cashflow_recovery = float(baseline["cashflow_recovery_ratio_base"])
    content_investment = float(baseline["content_investment_krw_nominal"])
    intangible_assets = float(baseline["intangible_assets_krw_nominal"])

    reg_market_strength = float(regression["cross_reg_market"]["effective_strength"])
    risk_market_strength = float(regression["cross_risk_market"]["effective_strength"])
    music_recovery_strength = float(regression["music_foreign_recovery"]["effective_strength"])
    webtoon_recovery_strength = float(regression["webtoon_foreign_recovery"]["effective_strength"])
    infra_foreign_strength = float(regression["infra_foreign_outflow"]["effective_strength"])
    infra_network_strength = float(regression["infra_network_outflow"]["effective_strength"])

    if sector == "music":
        sector_recovery_strength = music_recovery_strength
    elif sector == "webtoon_story":
        sector_recovery_strength = webtoon_recovery_strength
    else:
        sector_recovery_strength = max(infra_foreign_strength, infra_network_strength)

    outflow_norm = clip(outflow_value / (1.0 + outflow_value), 0.0, 1.0)
    ip_gap_need = clip(max(ip_gap, 0.0), 0.0, 1.0)
    funding_need = clip(max(funding_spread, 0.0) / (0.05 + max(funding_spread, 0.0)), 0.0, 1.0)
    recovery_shortfall = clip((50.0 - investment_recovery) / 100.0, 0.0, 1.0)
    collateral_norm = clip(
        safe_div(intangible_assets, intangible_assets + content_investment, 0.0), 0.0, 1.0
    )
    creator_gap = clip(1.0 - creator_share, 0.0, 1.0)
    cashflow_gap = clip((25.0 - cashflow_recovery) / 50.0, 0.0, 1.0)

    formula = ""
    regression_source = ""

    if parameter_name == "rho_bundle":
        value = 0.10 + 0.45 * bundle_value + 0.25 * cross_value + 0.20 * reg_market_strength
        formula = "0.10 + 0.45*bundle + 0.25*transfer + 0.20*reg_market_strength"
        regression_source = "cross_country_sector_country_panel:I_reg"
    elif parameter_name == "eta_transfer":
        value = 0.20 + 0.60 * cross_value + 0.70 * reg_market_strength
        formula = "0.20 + 0.60*transfer + 0.70*reg_market_strength"
        regression_source = "cross_country_sector_country_panel:I_reg"
    elif parameter_name == "eta_share":
        value = (
            0.10
            + 0.50 * (1.0 - local_share)
            + 0.35 * sector_recovery_strength
            + 0.10 * market_pressure
        )
        formula = "0.10 + 0.50*(1-local_share) + 0.35*sector_recovery_strength + 0.10*market_pressure"
        regression_source = (
            "music_service_month_fe_main:foreign_dependency_ratio"
            if sector == "music"
            else "webtoon_service_quarter_fe_main:foreign_dependency_ratio"
            if sector == "webtoon_story"
            else "cross_country_sector_country_panel:I_reg"
        )
    elif parameter_name == "phi_recover":
        value = 0.10 + 0.65 * traffic_pressure + 0.20 * infra_network_strength
        formula = "0.10 + 0.65*traffic_pressure + 0.20*infra_network_strength"
        regression_source = "infra_service_quarter_fe_main:network_cost_ratio"
    elif parameter_name == "psi_capex":
        value = 0.10 + 0.55 * domestic_capex_ratio + 0.20 * outflow_norm + 0.10 * clip(
            0.10 + 0.65 * traffic_pressure + 0.20 * infra_network_strength, 0.0, 1.0
        )
        formula = "0.10 + 0.55*domestic_capex_ratio + 0.20*outflow_norm + 0.10*phi_recover"
        regression_source = "infra_service_quarter_fe_main:network_cost_ratio"
    elif parameter_name == "kappa_replace":
        value = (
            0.05
            + 0.45 * domestic_capex_ratio
            + 0.25 * (1.0 - foreign_value)
            + 0.25 * clip(0.10 + 0.65 * traffic_pressure + 0.20 * infra_network_strength, 0.0, 1.0)
        )
        formula = "0.05 + 0.45*domestic_capex_ratio + 0.25*(1-foreign_dep) + 0.25*phi_recover"
        regression_source = "infra_service_quarter_fe_main:foreign_dependency_ratio"
    elif parameter_name == "alpha_ip":
        value = 0.10 + 0.55 * ip_gap_need + 0.20 * risk_pressure + 0.15 * sector_recovery_strength
        formula = "0.10 + 0.55*ip_gap_need + 0.20*risk_pressure + 0.15*sector_recovery_strength"
        regression_source = "cross_country_sector_country_panel:I_risk"
    elif parameter_name == "lambda_advance":
        alpha_proxy = clip(
            0.10 + 0.55 * ip_gap_need + 0.20 * risk_pressure + 0.15 * sector_recovery_strength,
            0.0,
            1.0,
        )
        value = 0.15 + 0.55 * collateral_norm + 0.15 * alpha_proxy
        formula = "0.15 + 0.55*collateral_norm + 0.15*alpha_ip"
        regression_source = "cross_country_sector_country_panel:I_risk"
    elif parameter_name == "eta_funding":
        alpha_proxy = clip(
            0.10 + 0.55 * ip_gap_need + 0.20 * risk_pressure + 0.15 * sector_recovery_strength,
            0.0,
            1.0,
        )
        value = 0.25 + 1.00 * risk_market_strength + 0.50 * funding_need + 0.20 * alpha_proxy
        formula = "0.25 + 1.00*risk_market_strength + 0.50*funding_need + 0.20*alpha_ip"
        regression_source = "cross_country_sector_country_panel:I_risk"
    elif parameter_name == "eta_recovery":
        value = 0.20 + 1.10 * sector_recovery_strength + 0.60 * recovery_shortfall + 0.20 * risk_market_strength
        formula = "0.20 + 1.10*sector_recovery_strength + 0.60*recovery_shortfall + 0.20*risk_market_strength"
        regression_source = (
            "music_service_month_fe_main:foreign_dependency_ratio"
            if sector == "music"
            else "webtoon_service_quarter_fe_main:foreign_dependency_ratio"
            if sector == "webtoon_story"
            else "cross_country_sector_country_panel:I_risk"
        )
    elif parameter_name == "theta_bargain":
        value = 0.15 + 0.60 * creator_gap + 0.15 * risk_pressure + 0.10 * cashflow_gap
        formula = "0.15 + 0.60*creator_gap + 0.15*risk_pressure + 0.10*cashflow_gap"
        regression_source = "cross_country_sector_country_panel:I_risk"
    elif parameter_name == "eta_cash":
        theta_proxy = clip(
            0.15 + 0.60 * creator_gap + 0.15 * risk_pressure + 0.10 * cashflow_gap,
            0.0,
            1.0,
        )
        value = 0.10 + 0.55 * cashflow_gap + 0.20 * theta_proxy + 0.15 * risk_market_strength
        formula = "0.10 + 0.55*cashflow_gap + 0.20*theta_bargain + 0.15*risk_market_strength"
        regression_source = "cross_country_sector_country_panel:I_risk"
    else:
        raise KeyError(parameter_name)

    return clip(value, lower, upper), formula, regression_source


def build_parameter_rows(
    baseline_numeric: dict[str, dict[str, float | str]],
    regression: dict[str, dict[str, float | str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    regression_row_map = {
        "cross_country_sector_country_panel:I_reg": regression["cross_reg_market"],
        "cross_country_sector_country_panel:I_risk": regression["cross_risk_market"],
        "music_service_month_fe_main:foreign_dependency_ratio": regression["music_foreign_recovery"],
        "webtoon_service_quarter_fe_main:foreign_dependency_ratio": regression["webtoon_foreign_recovery"],
        "infra_service_quarter_fe_main:foreign_dependency_ratio": regression["infra_foreign_outflow"],
        "infra_service_quarter_fe_main:network_cost_ratio": regression["infra_network_outflow"],
    }

    for baseline_id, baseline in baseline_numeric.items():
        sector = str(baseline["sector_std"])
        yq = str(baseline["year_quarter"])
        coverage = set(str(baseline["scenario_coverage"]).split("|"))

        for param_idx, parameter_name in enumerate(PARAMETER_SCENARIO, start=1):
            scenario_code = PARAMETER_SCENARIO[parameter_name]
            lower, upper = PARAM_BOUNDS[parameter_name]
            calibration_id = f"{baseline_id}_{param_idx:02d}"

            if scenario_code not in coverage:
                rows.append(
                    {
                        "calibration_id": calibration_id,
                        "baseline_id": baseline_id,
                        "sector_std": sector,
                        "year_quarter": yq,
                        "scenario_code": scenario_code,
                        "parameter_name": parameter_name,
                        "parameter_value": "",
                        "lower_bound": fmt_ratio(lower),
                        "upper_bound": fmt_ratio(upper),
                        "baseline_input_names": "",
                        "regression_source": "",
                        "regression_coefficient": "",
                        "regression_p_value": "",
                        "effective_strength": "",
                        "calibration_formula": "",
                        "calibration_status": "not_applicable_sector_scope",
                        "notes": f"{sector} baseline is outside the configured scenario coverage for {scenario_code}.",
                    }
                )
                continue

            value, formula, regression_source = calibrate_parameter(parameter_name, baseline, regression)
            reg_row = regression_row_map[regression_source]

            baseline_input_names = {
                "BND": "bundle_leverage_index_base|cross_market_transfer_index_base|local_platform_share_base|I_market_base",
                "NET": "traffic_cost_pressure_base|domestic_capex_ratio_base|foreign_dependency_ratio_base|outflow_to_capex_ratio_base",
                "IPF": "ip_assetization_gap_base|funding_cost_spread_base|investment_recovery_ratio_base|content_investment_krw_nominal|intangible_assets_krw_nominal",
                "CBA": "creator_share_ratio_base|cashflow_recovery_ratio_base|collective_bargaining_premium_base|eligible_revenue_krw_nominal|I_risk_base",
            }[scenario_code]

            rows.append(
                {
                    "calibration_id": calibration_id,
                    "baseline_id": baseline_id,
                    "sector_std": sector,
                    "year_quarter": yq,
                    "scenario_code": scenario_code,
                    "parameter_name": parameter_name,
                    "parameter_value": fmt_ratio(value),
                    "lower_bound": fmt_ratio(lower),
                    "upper_bound": fmt_ratio(upper),
                    "baseline_input_names": baseline_input_names,
                    "regression_source": regression_source,
                    "regression_coefficient": fmt_ratio(to_float(reg_row["coefficient"])),
                    "regression_p_value": fmt_ratio(to_float(reg_row["p_value"])),
                    "effective_strength": fmt_ratio(to_float(reg_row["effective_strength"])),
                    "calibration_formula": formula,
                    "calibration_status": "calibrated",
                    "notes": "Bounded to the simulator range after combining observed baseline pressure and regression evidence.",
                }
            )

    return rows


def build_log(
    baseline_rows: list[dict[str, str]],
    parameter_rows: list[dict[str, str]],
    regression: dict[str, dict[str, float | str]],
) -> str:
    baseline_count = len(baseline_rows)
    calibrated_rows = [row for row in parameter_rows if row["calibration_status"] == "calibrated"]
    parameter_status_counter = Counter(row["calibration_status"] for row in parameter_rows)

    param_range_lines = []
    for parameter_name in PARAMETER_SCENARIO:
        values = [
            float(row["parameter_value"])
            for row in calibrated_rows
            if row["parameter_name"] == parameter_name and row["parameter_value"] not in ("", None)
        ]
        if values:
            param_range_lines.append(
                f"- `{parameter_name}`: count `{len(values)}`, min `{min(values):.4f}`, max `{max(values):.4f}`, mean `{statistics.mean(values):.4f}`"
            )

    regression_lines = []
    regression_labels = {
        "cross_reg_market": "Cross-country `I_reg -> I_market`",
        "cross_risk_market": "Cross-country `I_risk -> I_market`",
        "music_foreign_recovery": "Music FE `foreign_dependency_ratio -> investment_recovery_ratio`",
        "webtoon_foreign_recovery": "Webtoon FE `foreign_dependency_ratio -> investment_recovery_ratio`",
        "infra_foreign_outflow": "Infra FE `foreign_dependency_ratio -> outflow_to_capex_ratio`",
        "infra_network_outflow": "Infra FE `network_cost_ratio -> outflow_to_capex_ratio`",
    }
    for key, label in regression_labels.items():
        row = regression[key]
        regression_lines.append(
            f"- {label}: coef `{float(row['coefficient']):.6f}`, p-value `{float(row['p_value']):.6f}`, strength `{float(row['effective_strength']):.6f}`"
        )

    carry_forward_rows = [
        row
        for row in baseline_rows
        if "carry_forward" in row["baseline_notes"] or "backfilled" in row["baseline_notes"]
    ]

    return "\n".join(
        [
            "# Policy Calibration Log",
            "",
            "## Overview",
            f"- Baseline rows built: `{baseline_count}`",
            f"- Calibrated parameter rows: `{len(calibrated_rows)}`",
            f"- Parameter row status split: `{dict(parameter_status_counter)}`",
            "",
            "## Baseline Construction Rules",
            "- `sector-quarter` baseline rows use only `cpii_status=computed` observations from `cpii_panel_sector_quarter.csv`.",
            "- Monetary inputs are aggregated from `standardized_numeric_panel.csv` in `KRW nominal` and carried forward only from the latest prior observed quarter when the exact quarter is missing.",
            "- Structural ratios prefer `platform-quarter` medians. If a direct service value is unavailable, the script falls back to the `sector-quarter` variable table. If there is still no prior observation, the latest available structural value is backfilled and marked in `baseline_notes`.",
            "- `traffic_cost_pressure_base` uses the direct Korean telecom proxy when available for digital infrastructure and otherwise falls back to `foreign_dependency_ratio * network_cost_ratio`.",
            "- `content_investment_krw_nominal` is forced non-negative for simulator denominators. When the observed content-investment aggregate is non-positive, the fallback is `max(3% of revenue, 10% of intangible assets)`.",
            "- `creator_share_ratio_base` is direct when observed. For sectors without a direct creator-share series, the fallback proxy is a bounded function of `cashflow_recovery_ratio` and `I_risk`.",
            "",
            "## Regression Evidence Used",
            *regression_lines,
            "",
            "## Parameter Summary",
            *param_range_lines,
            "",
            "## Carry-Forward and Fallback Notes",
            f"- Rows with carry-forward or structural backfill notes: `{len(carry_forward_rows)}`",
            "- Music `2025Q1` and all `2026Q1` monetary inputs necessarily rely on the latest prior quarter because the standardized financial panel does not yet contain later direct fiscal statements.",
            "- Webtoon/story `content_investment_krw_nominal` uses the denominator fallback because the extracted aggregate content-investment lines are non-positive in the current public filing sample.",
            "- `collective_bargaining_premium_base` and `eligible_revenue_krw_nominal` are set to zero for `digital_infra` because the simulator coverage for that sector is `NET|MON` only.",
            "",
            "## Output Use",
            "- `policy_simulator_baseline_inputs.csv` includes `scenario_coverage`, so the next scenario-calculation step can filter which baseline rows feed `BND`, `NET`, `IPF`, `CBA`, and `MON`.",
            "- `policy_simulator_calibrated_parameters.csv` keeps one row per `sector-quarter-parameter` with explicit scenario code, bounds, formula, and regression source.",
        ]
    )


def main() -> None:
    baseline_rows, baseline_numeric, regression = build_baseline_rows()
    parameter_rows = build_parameter_rows(baseline_numeric, regression)

    baseline_fieldnames = [
        "baseline_id",
        "sector_std",
        "year_quarter",
        "scenario_coverage",
        "baseline_status",
        "CPII_base",
        "I_reg_base",
        "I_risk_base",
        "I_market_base",
        "local_platform_share_base",
        "market_revenue_krw_nominal",
        "revenue_krw_nominal",
        "pretax_income_krw_nominal",
        "content_investment_krw_nominal",
        "intangible_assets_krw_nominal",
        "capex_krw_nominal",
        "domestic_capex_ratio_base",
        "bundle_leverage_index_base",
        "cross_market_transfer_index_base",
        "traffic_cost_pressure_base",
        "network_cost_ratio_base",
        "foreign_dependency_ratio_base",
        "outflow_to_capex_ratio_base",
        "ip_assetization_gap_base",
        "funding_cost_spread_base",
        "investment_recovery_ratio_base",
        "creator_share_ratio_base",
        "cashflow_recovery_ratio_base",
        "securitization_npv_delta_krw_nominal",
        "collective_bargaining_premium_base",
        "eligible_revenue_krw_nominal",
        "revenue_source_year_quarter",
        "pretax_source_year_quarter",
        "content_investment_source_year_quarter",
        "intangible_assets_source_year_quarter",
        "capex_source_year_quarter",
        "baseline_notes",
    ]
    parameter_fieldnames = [
        "calibration_id",
        "baseline_id",
        "sector_std",
        "year_quarter",
        "scenario_code",
        "parameter_name",
        "parameter_value",
        "lower_bound",
        "upper_bound",
        "baseline_input_names",
        "regression_source",
        "regression_coefficient",
        "regression_p_value",
        "effective_strength",
        "calibration_formula",
        "calibration_status",
        "notes",
    ]

    write_csv(BASELINE_OUTPUT_PATH, baseline_rows, baseline_fieldnames)
    write_csv(PARAM_OUTPUT_PATH, parameter_rows, parameter_fieldnames)
    LOG_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_OUTPUT_PATH.write_text(
        build_log(baseline_rows, parameter_rows, regression) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
