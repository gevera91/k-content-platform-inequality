#!/usr/bin/env python3

from __future__ import annotations

import csv
import statistics
from calendar import monthrange
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


BASE_DIR = Path(__file__).resolve().parents[1]

DEDUP_PATH = BASE_DIR / "data/interim/deduplicated_panel.csv"
PLATFORM_MONTH_SKELETON_PATH = BASE_DIR / "data/interim/panel_skeleton_platform_month.csv"
PLATFORM_QUARTER_SKELETON_PATH = BASE_DIR / "data/interim/panel_skeleton_platform_quarter.csv"
TITLE_QUARTER_SKELETON_PATH = BASE_DIR / "data/interim/panel_skeleton_title_quarter.csv"
SECTOR_QUARTER_SKELETON_PATH = BASE_DIR / "data/interim/panel_skeleton_sector_quarter.csv"
FIRM_DICT_PATH = BASE_DIR / "data/registry/entity_dictionary_firm.csv"

OUT_PLATFORM_MONTH_PATH = BASE_DIR / "data/processed/variable_panel_platform_month.csv"
OUT_PLATFORM_QUARTER_PATH = BASE_DIR / "data/processed/variable_panel_platform_quarter.csv"
OUT_TITLE_QUARTER_PATH = BASE_DIR / "data/processed/variable_panel_title_quarter.csv"
OUT_SECTOR_QUARTER_PATH = BASE_DIR / "data/processed/variable_panel_sector_quarter.csv"
LOG_PATH = BASE_DIR / "logs/variable_construction_log.md"
MANIFEST_PATH = BASE_DIR / "data/registry/project_manifest.csv"
WORKFLOW_LOG_PATH = BASE_DIR / "logs/workflow_log.md"

ACCESS_DATE = "2026-03-29"
PROMPT_NAME = "Exec Prompt 23"

VARIABLES = [
    "effective_tax_rate_gap",
    "network_cost_ratio",
    "infra_dependency_ratio",
    "funding_cost_spread",
    "ip_assetization_gap",
    "investment_recovery_ratio",
    "cashflow_recovery_ratio",
    "creator_share_ratio",
    "bundle_leverage_index",
    "cross_market_transfer_index",
    "foreign_dependency_ratio",
    "outflow_to_capex_ratio",
]

PRICE_VARIANT_PRIORITY = {
    "youtube_music": ["music_premium_individual", "premium_bundle_individual", "premium_lite_individual"],
    "spotify": ["individual", "basic", "student", "duo"],
    "melon": ["streaming_plus", "streaming_club"],
}


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def safe_float(value: str) -> Optional[float]:
    if value is None:
        return None
    stripped = str(value).strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def fmt(value: Optional[float]) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        text = f"{value:.10f}".rstrip("0").rstrip(".")
        if text == "-0":
            return "0"
        return text
    return str(value)


def quarter_sort_key(value: str) -> Tuple[int, int]:
    return int(value[:4]), int(value[-1])


def month_sort_key(value: str) -> Tuple[int, int]:
    return int(value[:4]), int(value[5:7])


def quarter_distance(source_quarter: str, target_quarter: str) -> int:
    sy, sq = quarter_sort_key(source_quarter)
    ty, tq = quarter_sort_key(target_quarter)
    return (ty - sy) * 4 + (tq - sq)


def latest_quarter_at_or_before(quarters: Iterable[str], target_quarter: str) -> Optional[str]:
    candidates = [quarter for quarter in quarters if quarter_distance(quarter, target_quarter) >= 0]
    if not candidates:
        return None
    return sorted(candidates, key=quarter_sort_key)[-1]


def mean_or_none(values: Iterable[Optional[float]]) -> Optional[float]:
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return None
    return statistics.mean(cleaned)


def median_or_none(values: Iterable[Optional[float]]) -> Optional[float]:
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return None
    return statistics.median(cleaned)


def join_nonempty(values: Iterable[str]) -> str:
    cleaned = sorted({value for value in values if value})
    return "|".join(cleaned)


def available_variable_summary(row: Dict[str, str]) -> Tuple[str, str]:
    names = [variable for variable in VARIABLES if row.get(variable, "").strip()]
    return str(len(names)), "|".join(names)


def representative_price_choice(rows: List[Dict[str, str]], service_std: str) -> Tuple[Optional[float], str]:
    if not rows:
        return None, "no_price"
    priced = []
    for row in rows:
        value = safe_float(row.get("metric_value_standardized", ""))
        if value is not None:
            priced.append((row["metric_variant"], value))
    if not priced:
        return None, "no_numeric_price"

    preferred_variants = PRICE_VARIANT_PRIORITY.get(service_std, [])
    for variant in preferred_variants:
        for observed_variant, value in priced:
            if observed_variant == variant:
                return value, variant

    priced_sorted = sorted(priced, key=lambda item: item[1])
    return priced_sorted[0][1], f"fallback_min_{priced_sorted[0][0]}"


def build_financial_data(dedup_rows: List[Dict[str, str]], firm_home_country: Dict[str, str]) -> Tuple[
    Dict[Tuple[str, str], Dict[str, float]],
    Dict[str, Dict[str, Dict[str, float]]],
    Dict[str, Dict[str, str]],
]:
    financial_metrics: Dict[Tuple[str, str], Dict[str, float]] = defaultdict(dict)
    for row in dedup_rows:
        if row["source_panel"] != "financial_extraction_panel":
            continue
        metric_value = safe_float(row.get("metric_value_standardized", ""))
        if metric_value is None:
            continue
        financial_metrics[(row["firm_std"], row["year_quarter"])][row["metric_name"]] = metric_value

    financial_derived: Dict[Tuple[str, str], Dict[str, float]] = {}
    for (firm_std, year_quarter), metrics in financial_metrics.items():
        revenue = metrics.get("revenue")
        pretax = metrics.get("pretax_income")
        tax_expense = metrics.get("tax_expense")
        interest_expense = metrics.get("interest_expense")
        debt = metrics.get("debt")
        intangible_assets = metrics.get("intangible_assets")
        content_investment = metrics.get("content_investment")
        network_cost = metrics.get("network_cloud_cost")
        capex = metrics.get("capex")

        derived = {}
        if revenue and revenue != 0:
            if network_cost is not None:
                derived["network_cost_ratio"] = network_cost / revenue
            if intangible_assets is not None:
                derived["ip_asset_ratio_proxy"] = intangible_assets / revenue
            if content_investment not in (None, 0):
                derived["investment_recovery_ratio"] = revenue / content_investment
        if pretax and pretax > 0 and tax_expense is not None:
            derived["effective_tax_rate"] = tax_expense / pretax
        if debt not in (None, 0) and interest_expense is not None:
            derived["funding_cost_rate"] = interest_expense / debt
        if content_investment not in (None, 0) and pretax is not None:
            derived["cashflow_recovery_ratio_proxy"] = pretax / content_investment
        if capex not in (None, 0) and network_cost is not None:
            derived["outflow_to_capex_ratio"] = network_cost / capex
        financial_derived[(firm_std, year_quarter)] = derived

    benchmark_series: Dict[str, Dict[str, Dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    fallback_note: Dict[str, Dict[str, str]] = defaultdict(dict)
    global_pool: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    for (firm_std, year_quarter), derived in financial_derived.items():
        home_country = firm_home_country.get(firm_std, "")
        if home_country == "kr":
            continue
        sector_std = next(
            (row["sector_std"] for row in dedup_rows if row["firm_std"] == firm_std and row["year_quarter"] == year_quarter and row["source_panel"] == "financial_extraction_panel"),
            "",
        )
        for variable_name, helper_key in [
            ("effective_tax_rate_gap", "effective_tax_rate"),
            ("funding_cost_spread", "funding_cost_rate"),
            ("ip_assetization_gap", "ip_asset_ratio_proxy"),
        ]:
            value = derived.get(helper_key)
            if value is not None:
                benchmark_series[variable_name][sector_std][year_quarter] = benchmark_series[variable_name][sector_std].get(year_quarter, [])
                existing = benchmark_series[variable_name][sector_std][year_quarter]
                if isinstance(existing, list):
                    existing.append(value)
                else:
                    benchmark_series[variable_name][sector_std][year_quarter] = [value]
                global_pool[variable_name][sector_std].append(value)

    normalized_benchmark_series: Dict[str, Dict[str, Dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for variable_name, sector_dict in benchmark_series.items():
        for sector_std, quarter_values in sector_dict.items():
            for year_quarter, values in quarter_values.items():
                normalized_benchmark_series[variable_name][sector_std][year_quarter] = statistics.median(values)
            sector_values = global_pool[variable_name][sector_std]
            sector_fallback = statistics.median(sector_values) if sector_values else None
            for year_quarter in quarter_values:
                if sector_fallback is not None:
                    fallback_note[variable_name][sector_std] = fmt(sector_fallback)

    return financial_derived, normalized_benchmark_series, fallback_note


def get_sector_benchmark(
    variable_name: str,
    sector_std: str,
    target_quarter: str,
    benchmark_series: Dict[str, Dict[str, Dict[str, float]]],
) -> Tuple[Optional[float], str]:
    sector_series = benchmark_series.get(variable_name, {}).get(sector_std, {})
    if not sector_series:
        return None, "benchmark_unavailable"
    if target_quarter in sector_series:
        return sector_series[target_quarter], f"benchmark_exact_{target_quarter}"
    latest_available = latest_quarter_at_or_before(sector_series.keys(), target_quarter)
    if latest_available:
        lag = quarter_distance(latest_available, target_quarter)
        return sector_series[latest_available], f"benchmark_carry_forward_{lag}q_from_{latest_available}"
    fallback_value = statistics.median(sector_series.values())
    return fallback_value, "benchmark_sector_fallback_median"


def get_financial_bridge(
    firm_std: str,
    sector_std: str,
    target_quarter: str,
    financial_derived: Dict[Tuple[str, str], Dict[str, float]],
    benchmark_series: Dict[str, Dict[str, Dict[str, float]]],
) -> Tuple[Dict[str, Optional[float]], str]:
    available_quarters = sorted(
        {quarter for firm, quarter in financial_derived if firm == firm_std},
        key=quarter_sort_key,
    )
    source_quarter = latest_quarter_at_or_before(available_quarters, target_quarter)
    if not source_quarter:
        return {variable: None for variable in VARIABLES}, "none"

    source_values = financial_derived.get((firm_std, source_quarter), {})
    bridge_mode = "exact" if source_quarter == target_quarter else f"carry_forward_{quarter_distance(source_quarter, target_quarter)}q_from_{source_quarter}"

    etr_benchmark, _ = get_sector_benchmark("effective_tax_rate_gap", sector_std, source_quarter, benchmark_series)
    funding_benchmark, _ = get_sector_benchmark("funding_cost_spread", sector_std, source_quarter, benchmark_series)
    ip_benchmark, _ = get_sector_benchmark("ip_assetization_gap", sector_std, source_quarter, benchmark_series)

    result = {variable: None for variable in VARIABLES}
    result["network_cost_ratio"] = source_values.get("network_cost_ratio")
    result["investment_recovery_ratio"] = source_values.get("investment_recovery_ratio")
    result["cashflow_recovery_ratio"] = source_values.get("cashflow_recovery_ratio_proxy")
    result["outflow_to_capex_ratio"] = source_values.get("outflow_to_capex_ratio")

    if source_values.get("effective_tax_rate") is not None and etr_benchmark is not None:
        result["effective_tax_rate_gap"] = source_values["effective_tax_rate"] - etr_benchmark
    if source_values.get("funding_cost_rate") is not None and funding_benchmark is not None:
        result["funding_cost_spread"] = source_values["funding_cost_rate"] - funding_benchmark
    if source_values.get("ip_asset_ratio_proxy") is not None and ip_benchmark is not None:
        result["ip_assetization_gap"] = ip_benchmark - source_values["ip_asset_ratio_proxy"]

    return result, bridge_mode


def build_country_dependency_series(dedup_rows: List[Dict[str, str]]) -> Tuple[
    Dict[Tuple[str, str], float],
    Dict[Tuple[str, str, str], float],
]:
    country_quarter_values: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    service_country_quarter_values: Dict[Tuple[str, str, str], List[float]] = defaultdict(list)
    for row in dedup_rows:
        if row["metric_name"] != "foreign_dependency_ratio":
            continue
        value = safe_float(row.get("metric_value_standardized", ""))
        if value is None:
            continue
        country_quarter_values[(row["country_std"], row["year_quarter"])].append(value)
        service_country_quarter_values[(row["service_std"], row["country_std"], row["year_quarter"])].append(value)

    country_series = {key: statistics.mean(values) for key, values in country_quarter_values.items()}
    service_series = {key: statistics.mean(values) for key, values in service_country_quarter_values.items()}
    return country_series, service_series


def get_country_dependency(
    country_std: str,
    target_quarter: str,
    country_series: Dict[Tuple[str, str], float],
) -> Tuple[Optional[float], str]:
    quarter_map = {quarter: value for (country, quarter), value in country_series.items() if country == country_std}
    if not quarter_map:
        return None, "none"
    if target_quarter in quarter_map:
        return quarter_map[target_quarter], "exact_country_quarter"
    latest_available = latest_quarter_at_or_before(quarter_map.keys(), target_quarter)
    if not latest_available:
        return None, "none"
    lag = quarter_distance(latest_available, target_quarter)
    return quarter_map[latest_available], f"carry_forward_{lag}q_from_{latest_available}"


def get_service_or_country_dependency(
    service_std: str,
    country_std: str,
    target_quarter: str,
    service_series: Dict[Tuple[str, str, str], float],
    country_series: Dict[Tuple[str, str], float],
) -> Tuple[Optional[float], str]:
    service_map = {
        quarter: value
        for (service, country, quarter), value in service_series.items()
        if service == service_std and country == country_std
    }
    if target_quarter in service_map:
        return service_map[target_quarter], "exact_service_quarter"
    latest_service = latest_quarter_at_or_before(service_map.keys(), target_quarter)
    if latest_service:
        lag = quarter_distance(latest_service, target_quarter)
        return service_map[latest_service], f"carry_forward_service_{lag}q_from_{latest_service}"
    return get_country_dependency(country_std, target_quarter, country_series)


def build_music_indexes(dedup_rows: List[Dict[str, str]]) -> Tuple[
    Dict[Tuple[str, str, str, str], float],
    Dict[Tuple[str, str, str], float],
    Dict[Tuple[str, str], Dict[str, Tuple[float, str]]],
    Dict[Tuple[str, str, str], float],
]:
    chart_share_month_values: Dict[Tuple[str, str, str, str], List[float]] = defaultdict(list)
    service_price_rows: Dict[Tuple[str, str, str], List[Dict[str, str]]] = defaultdict(list)
    relative_price_gap_month: Dict[Tuple[str, str, str], float] = {}

    for row in dedup_rows:
        if row["metric_name"] == "chart_share":
            value = safe_float(row.get("metric_value_standardized", ""))
            if value is not None:
                chart_share_month_values[(row["firm_std"], row["service_std"], row["country_std"], row["year_month"])].append(value)
        elif row["metric_name"] == "service_monthly_price_krw":
            service_price_rows[(row["service_std"], row["country_std"], row["year_month"])].append(row)
        elif row["metric_name"] == "relative_price_gap":
            value = safe_float(row.get("metric_value_standardized", ""))
            if value is not None:
                relative_price_gap_month[(row["country_std"], row["year_month"], row["year_quarter"])] = value

    chart_share_month = {
        key: statistics.mean(values) for key, values in chart_share_month_values.items()
    }
    chart_share_quarter_values: Dict[Tuple[str, str, str], List[float]] = defaultdict(list)
    for (firm_std, service_std, country_std, year_month), value in chart_share_month.items():
        year_quarter = f"{year_month[:4]}Q{((int(year_month[5:7]) - 1) // 3) + 1}"
        chart_share_quarter_values[(firm_std, service_std, country_std, year_quarter)].append(value)
    chart_share_quarter = {
        key: statistics.mean(values) for key, values in chart_share_quarter_values.items()
    }

    representative_price_series: Dict[Tuple[str, str], Dict[str, Tuple[float, str]]] = defaultdict(dict)
    for (service_std, country_std, year_month), rows in service_price_rows.items():
        price_value, mode = representative_price_choice(rows, service_std)
        if price_value is not None:
            representative_price_series[(service_std, country_std)][year_month] = (price_value, mode)

    bundle_leverage_month: Dict[Tuple[str, str, str], float] = {}
    youtube_bundle_reference: Dict[Tuple[str, str], float] = {}
    youtube_music_standalone: Dict[Tuple[str, str], float] = {}
    for (service_std, country_std), month_map in representative_price_series.items():
        if service_std == "youtube_music":
            for year_month, (price_value, mode) in month_map.items():
                if "music_premium_individual" in mode or mode == "music_premium_individual":
                    youtube_music_standalone[(country_std, year_month)] = price_value
            rows = service_price_rows.get((service_std, country_std, next(iter(month_map.keys()))), [])
        for year_month, rows in {
            key[2]: value
            for key, value in service_price_rows.items()
            if key[0] == "youtube_music" and key[1] == country_std
        }.items():
            bundle_rows = [row for row in rows if row["metric_variant"] == "premium_bundle_individual"]
            if bundle_rows:
                bundle_value = safe_float(bundle_rows[0]["metric_value_standardized"])
                if bundle_value is not None:
                    youtube_bundle_reference[(country_std, year_month)] = bundle_value

    for (service_std, country_std), month_map in representative_price_series.items():
        for year_month, (service_price, _) in month_map.items():
            bundle_price = youtube_bundle_reference.get((country_std, year_month))
            standalone_price = youtube_music_standalone.get((country_std, year_month))
            if bundle_price and standalone_price:
                bundle_leverage_month[(service_std, country_std, year_month)] = standalone_price / bundle_price

    bundle_leverage_quarter_values: Dict[Tuple[str, str, str], List[float]] = defaultdict(list)
    for (service_std, country_std, year_month), value in bundle_leverage_month.items():
        year_quarter = f"{year_month[:4]}Q{((int(year_month[5:7]) - 1) // 3) + 1}"
        bundle_leverage_quarter_values[(service_std, country_std, year_quarter)].append(value)
    bundle_leverage_quarter = {
        key: statistics.mean(values) for key, values in bundle_leverage_quarter_values.items()
    }

    return chart_share_month, chart_share_quarter, representative_price_series, bundle_leverage_quarter


def build_webtoon_title_indexes(dedup_rows: List[Dict[str, str]]) -> Tuple[
    Dict[Tuple[str, str, str, str], Dict[str, Optional[float]]],
    Dict[Tuple[str, str, str], Dict[str, Optional[float]]],
]:
    title_metrics: Dict[Tuple[str, str, str, str], Dict[str, Optional[float]]] = defaultdict(dict)
    for row in dedup_rows:
        if row["source_panel"] != "webtoon_title_raw_panel":
            continue
        key = (row["title_std"], row["service_std"], row["country_std"], row["year_quarter"])
        title_metrics[key][row["metric_name"]] = safe_float(row.get("metric_value_standardized", ""))

    title_proxy_metrics: Dict[Tuple[str, str, str, str], Dict[str, Optional[float]]] = {}
    service_proxy_values: Dict[Tuple[str, str, str], Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))

    for (title_std, service_std, country_std, year_quarter), metrics in title_metrics.items():
        position = metrics.get("title_position")
        local_ip = metrics.get("local_ip_proxy")
        translated = metrics.get("translated_proxy")
        inv_rank = None if position in (None, 0) else 1.0 / position
        creator_share = local_ip
        investment_recovery = inv_rank
        cashflow_recovery = None if inv_rank is None or local_ip is None else inv_rank * local_ip
        cross_market_transfer = None if inv_rank is None or translated is None else inv_rank * translated
        title_proxy_metrics[(title_std, service_std, country_std, year_quarter)] = {
            "creator_share_ratio": creator_share,
            "investment_recovery_ratio": investment_recovery,
            "cashflow_recovery_ratio": cashflow_recovery,
            "cross_market_transfer_index": cross_market_transfer,
        }

        if creator_share is not None:
            service_proxy_values[(service_std, country_std, year_quarter)]["creator_share_ratio"].append(creator_share)
        if investment_recovery is not None:
            service_proxy_values[(service_std, country_std, year_quarter)]["investment_recovery_ratio"].append(investment_recovery)
        if cashflow_recovery is not None:
            service_proxy_values[(service_std, country_std, year_quarter)]["cashflow_recovery_ratio"].append(cashflow_recovery)
        if cross_market_transfer is not None:
            service_proxy_values[(service_std, country_std, year_quarter)]["cross_market_transfer_index"].append(cross_market_transfer)

    service_proxy_metrics: Dict[Tuple[str, str, str], Dict[str, Optional[float]]] = {}
    for key, metric_lists in service_proxy_values.items():
        service_proxy_metrics[key] = {
            metric_name: mean_or_none(values) for metric_name, values in metric_lists.items()
        }

    return title_proxy_metrics, service_proxy_metrics


def row_with_variables(base_row: Dict[str, str], variables: Dict[str, Optional[float]], extra_fields: Dict[str, str]) -> Dict[str, str]:
    row = dict(base_row)
    for variable in VARIABLES:
        row[variable] = fmt(variables.get(variable))
    row.update(extra_fields)
    available_count, available_names = available_variable_summary(row)
    row["available_variable_count"] = available_count
    row["available_variable_names"] = available_names
    row["construction_status"] = "ready_for_qc" if int(available_count) > 0 else "no_constructed_variables"
    return row


def aggregate_variable_rows(
    rows: List[Dict[str, str]],
    group_fields: List[str],
    id_field: str,
    id_prefix: str,
) -> List[Dict[str, str]]:
    grouped: Dict[Tuple[str, ...], List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row[field] for field in group_fields)].append(row)

    output_rows: List[Dict[str, str]] = []
    for index, (group_key, members) in enumerate(sorted(grouped.items()), start=1):
        row = {field: value for field, value in zip(group_fields, group_key)}
        row[id_field] = f"{id_prefix}_{index:05d}"
        row["platform_support_count"] = str(len(members))
        for variable in VARIABLES:
            row[variable] = fmt(mean_or_none(safe_float(member.get(variable, "")) for member in members))
        available_count, available_names = available_variable_summary(row)
        row["available_variable_count"] = available_count
        row["available_variable_names"] = available_names
        row["construction_status"] = "ready_for_qc" if int(available_count) > 0 else "no_constructed_variables"
        output_rows.append(row)
    return output_rows


def main() -> None:
    dedup_rows = read_csv(DEDUP_PATH)
    platform_month_skeleton = read_csv(PLATFORM_MONTH_SKELETON_PATH)
    platform_quarter_skeleton = read_csv(PLATFORM_QUARTER_SKELETON_PATH)
    title_quarter_skeleton = read_csv(TITLE_QUARTER_SKELETON_PATH)
    sector_quarter_skeleton = read_csv(SECTOR_QUARTER_SKELETON_PATH)
    firm_dict = {row["firm_std"]: row for row in read_csv(FIRM_DICT_PATH)}
    firm_home_country = {firm_std: row["home_country"] for firm_std, row in firm_dict.items()}

    financial_derived, benchmark_series, _ = build_financial_data(dedup_rows, firm_home_country)
    country_dependency_series, service_dependency_series = build_country_dependency_series(dedup_rows)
    chart_share_month, chart_share_quarter, representative_price_series, bundle_leverage_quarter = build_music_indexes(dedup_rows)
    title_proxy_metrics, service_title_proxy_metrics = build_webtoon_title_indexes(dedup_rows)

    direct_service_quarter_metric: Dict[Tuple[str, str, str, str], Dict[str, float]] = defaultdict(dict)
    for row in dedup_rows:
        if row["year_quarter"] and row["service_std"] and row["country_std"]:
            metric_value = safe_float(row.get("metric_value_standardized", ""))
            if metric_value is None:
                continue
            key = (row["firm_std"], row["service_std"], row["country_std"], row["year_quarter"])
            if row["metric_name"] in {"network_cost_ratio", "outflow_to_capex_ratio", "domestic_infra_capex_ratio", "foreign_dependency_ratio"}:
                direct_service_quarter_metric[key][row["metric_name"]] = metric_value

    platform_month_rows: List[Dict[str, str]] = []
    platform_quarter_rows: List[Dict[str, str]] = []
    title_quarter_rows: List[Dict[str, str]] = []

    platform_month_bridge_counter = Counter()
    platform_quarter_bridge_counter = Counter()
    title_quarter_bridge_counter = Counter()
    dependency_counter = Counter()

    for base_row in platform_month_skeleton:
        financial_values, bridge_mode = get_financial_bridge(
            base_row["firm_std"],
            base_row["sector_std"],
            base_row["year_quarter"],
            financial_derived,
            benchmark_series,
        )
        platform_month_bridge_counter[bridge_mode] += 1
        dependency_value, dependency_mode = get_country_dependency(
            base_row["country_std"],
            base_row["year_quarter"],
            country_dependency_series,
        )
        dependency_counter[dependency_mode] += 1

        chart_value = chart_share_month.get(
            (base_row["firm_std"], base_row["service_std"], base_row["country_std"], base_row["year_month"])
        )
        bundle_value = None
        price_mode = "none"
        service_price = representative_price_series.get((base_row["service_std"], base_row["country_std"]), {}).get(base_row["year_month"])
        youtube_price = representative_price_series.get(("youtube_music", base_row["country_std"]), {}).get(base_row["year_month"])
        youtube_bundle_rows = [
            row for row in dedup_rows
            if row["metric_name"] == "service_monthly_price_krw"
            and row["service_std"] == "youtube_music"
            and row["country_std"] == base_row["country_std"]
            and row["year_month"] == base_row["year_month"]
            and row["metric_variant"] == "premium_bundle_individual"
        ]
        youtube_bundle_price = None
        if youtube_bundle_rows:
            youtube_bundle_price = safe_float(youtube_bundle_rows[0]["metric_value_standardized"])
        youtube_standalone_price = None if not youtube_price else youtube_price[0]
        if youtube_standalone_price is not None and youtube_bundle_price not in (None, 0):
            bundle_value = youtube_standalone_price / youtube_bundle_price
            price_mode = "youtube_music_standalone_over_bundle"

        variables = {variable: None for variable in VARIABLES}
        for variable_name in [
            "effective_tax_rate_gap",
            "network_cost_ratio",
            "funding_cost_spread",
            "ip_assetization_gap",
            "investment_recovery_ratio",
            "cashflow_recovery_ratio",
            "outflow_to_capex_ratio",
        ]:
            variables[variable_name] = financial_values.get(variable_name)
        variables["foreign_dependency_ratio"] = dependency_value
        variables["bundle_leverage_index"] = bundle_value
        if variables["network_cost_ratio"] is not None and dependency_value is not None:
            variables["infra_dependency_ratio"] = variables["network_cost_ratio"] * dependency_value
        if bundle_value is not None and dependency_value is not None:
            chart_gap = 1.0 - chart_value if chart_value is not None else 1.0
            variables["cross_market_transfer_index"] = bundle_value * dependency_value * chart_gap

        platform_month_rows.append(
            row_with_variables(
                base_row,
                variables,
                {
                    "financial_bridge_mode": bridge_mode,
                    "foreign_dependency_mode": dependency_mode,
                    "price_reference_mode": price_mode,
                    "chart_share_proxy": fmt(chart_value),
                },
            )
        )

    for base_row in platform_quarter_skeleton:
        financial_values, bridge_mode = get_financial_bridge(
            base_row["firm_std"],
            base_row["sector_std"],
            base_row["year_quarter"],
            financial_derived,
            benchmark_series,
        )
        platform_quarter_bridge_counter[bridge_mode] += 1
        dependency_value, dependency_mode = get_service_or_country_dependency(
            base_row["service_std"],
            base_row["country_std"],
            base_row["year_quarter"],
            service_dependency_series,
            country_dependency_series,
        )
        dependency_counter[dependency_mode] += 1

        service_direct_values = direct_service_quarter_metric.get(
            (base_row["firm_std"], base_row["service_std"], base_row["country_std"], base_row["year_quarter"]),
            {},
        )
        webtoon_service_proxy = service_title_proxy_metrics.get(
            (base_row["service_std"], base_row["country_std"], base_row["year_quarter"]),
            {},
        )

        variables = {variable: None for variable in VARIABLES}
        variables["effective_tax_rate_gap"] = financial_values.get("effective_tax_rate_gap")
        variables["funding_cost_spread"] = financial_values.get("funding_cost_spread")
        variables["ip_assetization_gap"] = financial_values.get("ip_assetization_gap")
        variables["investment_recovery_ratio"] = financial_values.get("investment_recovery_ratio") or webtoon_service_proxy.get("investment_recovery_ratio")
        variables["cashflow_recovery_ratio"] = financial_values.get("cashflow_recovery_ratio") or webtoon_service_proxy.get("cashflow_recovery_ratio")
        variables["creator_share_ratio"] = webtoon_service_proxy.get("creator_share_ratio")
        variables["network_cost_ratio"] = service_direct_values.get("network_cost_ratio") or financial_values.get("network_cost_ratio")
        variables["outflow_to_capex_ratio"] = service_direct_values.get("outflow_to_capex_ratio") or financial_values.get("outflow_to_capex_ratio")
        variables["foreign_dependency_ratio"] = service_direct_values.get("foreign_dependency_ratio") or dependency_value

        if variables["network_cost_ratio"] is not None and variables["foreign_dependency_ratio"] is not None:
            variables["infra_dependency_ratio"] = variables["network_cost_ratio"] * variables["foreign_dependency_ratio"]

        bundle_value = bundle_leverage_quarter.get((base_row["service_std"], base_row["country_std"], base_row["year_quarter"]))
        chart_value = chart_share_quarter.get((base_row["firm_std"], base_row["service_std"], base_row["country_std"], base_row["year_quarter"]))
        variables["bundle_leverage_index"] = bundle_value
        if base_row["sector_std"] == "music":
            if bundle_value is not None and variables["foreign_dependency_ratio"] is not None:
                chart_gap = 1.0 - chart_value if chart_value is not None else 1.0
                variables["cross_market_transfer_index"] = bundle_value * variables["foreign_dependency_ratio"] * chart_gap
            elif chart_value is not None and variables["foreign_dependency_ratio"] is not None:
                variables["cross_market_transfer_index"] = variables["foreign_dependency_ratio"] * (1.0 - chart_value)
        elif base_row["sector_std"] == "webtoon_story":
            variables["cross_market_transfer_index"] = webtoon_service_proxy.get("cross_market_transfer_index")

        platform_quarter_rows.append(
            row_with_variables(
                base_row,
                variables,
                {
                    "financial_bridge_mode": bridge_mode,
                    "foreign_dependency_mode": dependency_mode,
                    "service_direct_mode": "direct_service_metric" if service_direct_values else "none",
                    "title_proxy_mode": "service_title_proxy" if webtoon_service_proxy else "none",
                    "chart_share_proxy": fmt(chart_value),
                },
            )
        )

    for base_row in title_quarter_skeleton:
        financial_values, bridge_mode = get_financial_bridge(
            base_row["firm_std"],
            base_row["sector_std"],
            base_row["year_quarter"],
            financial_derived,
            benchmark_series,
        )
        title_quarter_bridge_counter[bridge_mode] += 1
        dependency_value, dependency_mode = get_country_dependency(
            base_row["country_std"],
            base_row["year_quarter"],
            country_dependency_series,
        )
        dependency_counter[dependency_mode] += 1
        title_proxy = title_proxy_metrics.get(
            (base_row["title_std"], base_row["service_std"], base_row["country_std"], base_row["year_quarter"]),
            {},
        )
        variables = {variable: None for variable in VARIABLES}
        variables["effective_tax_rate_gap"] = financial_values.get("effective_tax_rate_gap")
        variables["funding_cost_spread"] = financial_values.get("funding_cost_spread")
        variables["ip_assetization_gap"] = financial_values.get("ip_assetization_gap")
        variables["network_cost_ratio"] = financial_values.get("network_cost_ratio")
        variables["outflow_to_capex_ratio"] = financial_values.get("outflow_to_capex_ratio")
        variables["investment_recovery_ratio"] = title_proxy.get("investment_recovery_ratio")
        variables["cashflow_recovery_ratio"] = title_proxy.get("cashflow_recovery_ratio")
        variables["creator_share_ratio"] = title_proxy.get("creator_share_ratio")
        variables["cross_market_transfer_index"] = title_proxy.get("cross_market_transfer_index")
        variables["foreign_dependency_ratio"] = dependency_value
        if variables["network_cost_ratio"] is not None and dependency_value is not None:
            variables["infra_dependency_ratio"] = variables["network_cost_ratio"] * dependency_value
        title_quarter_rows.append(
            row_with_variables(
                base_row,
                variables,
                {
                    "financial_bridge_mode": bridge_mode,
                    "foreign_dependency_mode": dependency_mode,
                    "title_proxy_mode": "title_proxy_direct" if title_proxy else "none",
                },
            )
        )

    sector_quarter_rows = []
    platform_rows_by_sector = defaultdict(list)
    for row in platform_quarter_rows:
        platform_rows_by_sector[(row["sector_std"], row["country_std"], row["year_quarter"])].append(row)

    sector_bridge_counter = Counter()
    for base_row in sector_quarter_skeleton:
        members = platform_rows_by_sector.get((base_row["sector_std"], base_row["country_std"], base_row["year_quarter"]), [])
        variables = {
            variable: mean_or_none(safe_float(member.get(variable, "")) for member in members)
            for variable in VARIABLES
        }
        available_platform_count = sum(1 for member in members if member.get("available_variable_count", "0") != "0")
        sector_bridge_counter["with_platform_support" if available_platform_count else "without_platform_support"] += 1
        sector_quarter_rows.append(
            row_with_variables(
                base_row,
                variables,
                {
                    "platform_support_count": str(len(members)),
                    "platform_ready_count": str(available_platform_count),
                },
            )
        )

    platform_month_fields = list(platform_month_rows[0].keys()) if platform_month_rows else []
    platform_quarter_fields = list(platform_quarter_rows[0].keys()) if platform_quarter_rows else []
    title_quarter_fields = list(title_quarter_rows[0].keys()) if title_quarter_rows else []
    sector_quarter_fields = list(sector_quarter_rows[0].keys()) if sector_quarter_rows else []

    write_csv(OUT_PLATFORM_MONTH_PATH, platform_month_rows, platform_month_fields)
    write_csv(OUT_PLATFORM_QUARTER_PATH, platform_quarter_rows, platform_quarter_fields)
    write_csv(OUT_TITLE_QUARTER_PATH, title_quarter_rows, title_quarter_fields)
    write_csv(OUT_SECTOR_QUARTER_PATH, sector_quarter_rows, sector_quarter_fields)

    panel_counts = {
        "platform_month": Counter(),
        "platform_quarter": Counter(),
        "title_quarter": Counter(),
        "sector_quarter": Counter(),
    }
    for row in platform_month_rows:
        for variable in VARIABLES:
            if row.get(variable, ""):
                panel_counts["platform_month"][variable] += 1
    for row in platform_quarter_rows:
        for variable in VARIABLES:
            if row.get(variable, ""):
                panel_counts["platform_quarter"][variable] += 1
    for row in title_quarter_rows:
        for variable in VARIABLES:
            if row.get(variable, ""):
                panel_counts["title_quarter"][variable] += 1
    for row in sector_quarter_rows:
        for variable in VARIABLES:
            if row.get(variable, ""):
                panel_counts["sector_quarter"][variable] += 1

    log_lines = [
        "# Variable Construction Log",
        "",
        f"- Access date: `{ACCESS_DATE}`",
        f"- Prompt: `{PROMPT_NAME}`",
        "",
        "## Construction Principles",
        "- 현재 단계는 CPII 최종 정규화 이전의 1차 변수 마스터 테이블 단계이며, 공시 직접값과 storefront/public proxy를 결합했다.",
        "- 공시가 없는 구간은 `financial_bridge_mode`에 따라 직전 분기 공시를 carry-forward 할 수 있도록 했다.",
        "- `foreign_dependency_ratio`는 서비스 직접 관측이 있으면 그것을 우선하고, 없으면 국가-분기 공통 proxy를 carry-forward 했다.",
        "",
        "## Variable Formulas",
        "- `effective_tax_rate_gap = (tax_expense / pretax_income) - foreign_sector_median(ETR)`",
        "- `network_cost_ratio = direct service network_cost_ratio`가 있으면 우선 사용하고, 없으면 `network_cloud_cost / revenue`를 사용",
        "- `infra_dependency_ratio = network_cost_ratio * foreign_dependency_ratio`",
        "- `funding_cost_spread = (interest_expense / debt) - foreign_sector_median(funding_cost_rate)`",
        "- `ip_assetization_gap = foreign_sector_median(intangible_assets / revenue) - (intangible_assets / revenue)`",
        "- `investment_recovery_ratio = revenue / content_investment`; 웹툰 title panel에서는 `1 / title_position` proxy를 사용",
        "- `cashflow_recovery_ratio = pretax_income / content_investment`; 웹툰 title panel에서는 `local_ip_proxy / title_position` proxy를 사용",
        "- `creator_share_ratio = webtoon title/service panel의 local_ip_proxy 평균`을 1차 proxy로 사용",
        "- `bundle_leverage_index = youtube_music_standalone_price / youtube_bundle_price`",
        "- `cross_market_transfer_index`: 음악은 `bundle_leverage_index * foreign_dependency_ratio * (1 - chart_share_proxy)`, 웹툰은 `translated_proxy / title_position` 또는 그 서비스 평균",
        "- `foreign_dependency_ratio = direct service foreign dependency` 또는 `country-quarter carry-forward proxy`",
        "- `outflow_to_capex_ratio = direct service outflow_to_capex_ratio`가 있으면 우선 사용하고, 없으면 `network_cloud_cost / capex`를 사용",
        "",
        "## Panel Coverage",
        f"- `variable_panel_platform_month.csv`: `{len(platform_month_rows)}` rows",
        f"- `variable_panel_platform_quarter.csv`: `{len(platform_quarter_rows)}` rows",
        f"- `variable_panel_title_quarter.csv`: `{len(title_quarter_rows)}` rows",
        f"- `variable_panel_sector_quarter.csv`: `{len(sector_quarter_rows)}` rows",
        "",
        "## Nonmissing Counts By Variable And Panel",
    ]
    for variable in VARIABLES:
        log_lines.append(
            f"- `{variable}`: month `{panel_counts['platform_month'][variable]}`, quarter `{panel_counts['platform_quarter'][variable]}`, title `{panel_counts['title_quarter'][variable]}`, sector `{panel_counts['sector_quarter'][variable]}`"
        )
    log_lines.extend(
        [
            "",
            "## Bridge Usage",
            f"- platform month financial bridge: `{dict(platform_month_bridge_counter)}`",
            f"- platform quarter financial bridge: `{dict(platform_quarter_bridge_counter)}`",
            f"- title quarter financial bridge: `{dict(title_quarter_bridge_counter)}`",
            f"- foreign dependency bridge: `{dict(dependency_counter)}`",
            "",
            "## Notes",
            "- `creator_share_ratio`, `cashflow_recovery_ratio`, `cross_market_transfer_index`는 현재 공개 raw의 제약 때문에 웹툰/storefront proxy를 사용한 임시 계량식이다.",
            "- `bundle_leverage_index`는 2026년 3월 한국 공식 가격표가 확보된 구간에만 계산된다.",
            "- 이후 `Exec Prompt 24`에서 허용 범위, 극단값, 통화 변환 누락, 표본 손실을 별도로 검증해야 한다.",
        ]
    )
    LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    manifest_rows = read_csv(MANIFEST_PATH)
    additions = [
        {
            "artifact_type": "script",
            "path": "scripts/build_variable_panels.py",
            "owner_step": PROMPT_NAME,
            "source_type": "local_code",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Constructs first-stage variable master tables for month, quarter, title-quarter, and sector-quarter units.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/processed/variable_panel_platform_month.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_variable_panel",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Platform-month variable master table with financial bridges, dependency proxies, and music bundle metrics.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/processed/variable_panel_platform_quarter.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_variable_panel",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Platform-quarter variable master table with direct service metrics, financial bridges, and title aggregate proxies.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/processed/variable_panel_title_quarter.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_variable_panel",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Title-quarter variable master table built from webtoon title rank and script proxies plus country dependency bridges.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/processed/variable_panel_sector_quarter.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_variable_panel",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Sector-quarter variable master table aggregated from platform-quarter rows.",
        },
        {
            "artifact_type": "log",
            "path": "logs/variable_construction_log.md",
            "owner_step": PROMPT_NAME,
            "source_type": "local_log",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Formula log and coverage summary for actual variable construction.",
        },
    ]
    existing_keys = {(row["owner_step"], row["path"]) for row in manifest_rows}
    for addition in additions:
        key = (addition["owner_step"], addition["path"])
        if key not in existing_keys:
            manifest_rows.append(addition)
            existing_keys.add(key)
    write_csv(MANIFEST_PATH, manifest_rows, list(manifest_rows[0].keys()))

    workflow_header = f"### {PROMPT_NAME}. 실제 변수 계산 테이블 작성"
    workflow_text = WORKFLOW_LOG_PATH.read_text(encoding="utf-8") if WORKFLOW_LOG_PATH.exists() else ""
    if workflow_header not in workflow_text:
        addition = "\n".join(
            [
                workflow_header,
                "",
                f"- `data/processed/variable_panel_platform_month.csv`, `variable_panel_platform_quarter.csv`, `variable_panel_title_quarter.csv`, `variable_panel_sector_quarter.csv` 생성",
                "- 공시 직접값, 서비스 직접 metric, 국가 foreign dependency proxy, 웹툰 storefront proxy를 결합해 12개 필수 변수의 1차 master table을 구성",
                "- `logs/variable_construction_log.md`에 변수별 실제 입력 열과 산식, panel별 nonmissing count를 기록",
            ]
        )
        if workflow_text and not workflow_text.endswith("\n"):
            workflow_text += "\n"
        WORKFLOW_LOG_PATH.write_text(workflow_text + addition + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
