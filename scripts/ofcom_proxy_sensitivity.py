#!/usr/bin/env python3
"""Sensitivity audit for the unresolved UK Ofcom 0.94 proxy.

This script does not overwrite the production processed data. It blanks the
UK `foreign_dependency_ratio == 0.94` values in working copies, rebuilds the
subindex/CPII panels in memory, and writes comparison artifacts under logs/.
"""

from __future__ import annotations

import csv
import datetime as dt
import sys
from copy import deepcopy
from pathlib import Path
from statistics import mean
from typing import Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from build_subindex_panels import (  # noqa: E402
    SUBINDEX_COMPONENTS,
    calculate_country_panel,
    calculate_sector_quarter_panel,
    fmt,
    read_csv,
    safe_float,
    variable_pipeline,
    write_csv,
)
from build_cpii_panels import (  # noqa: E402
    FIRM_COUNTRY_SPEC_CODE,
    SECTOR_COUNTRY_SPEC_CODE,
    SECTOR_SPEC_CODE,
    add_cpii_to_subindex_rows,
    build_anchor_profiles,
    build_firm_country_panel,
    subindex_components_active,
)


VARIABLE_COLUMNS = sorted({variable for values in SUBINDEX_COMPONENTS.values() for variable in values})

SECTOR_VARIABLE_PATH = ROOT / "data/processed/variable_panel_sector_quarter.csv"
PLATFORM_VARIABLE_PATH = ROOT / "data/processed/variable_panel_platform_quarter.csv"
BASELINE_SECTOR_PATH = ROOT / "data/processed/cpii_panel_sector_quarter.csv"
BASELINE_SECTOR_COUNTRY_PATH = ROOT / "data/processed/cpii_panel_sector_country_quarter.csv"
BASELINE_FIRM_COUNTRY_PATH = ROOT / "data/processed/cpii_panel_firm_country_quarter.csv"

OUT_SECTOR_SUMMARY = ROOT / "logs/ofcom_proxy_sensitivity_sector_summary.csv"
OUT_UK_SECTOR_COUNTRY = ROOT / "logs/ofcom_proxy_sensitivity_sector_country_uk.csv"
OUT_UK_FIRM_COUNTRY = ROOT / "logs/ofcom_proxy_sensitivity_firm_country_uk.csv"
OUT_SUMMARY_TXT = ROOT / "logs/ofcom_proxy_sensitivity_summary.txt"


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def copy_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    return [dict(row) for row in deepcopy(rows)]


def is_target_ofcom_proxy(row: Dict[str, str]) -> bool:
    value = safe_float(row.get("foreign_dependency_ratio", ""))
    return row.get("country_std") == "uk" and value is not None and abs(value - 0.94) < 1e-12


def refresh_available_variables(row: Dict[str, str]) -> None:
    available = [name for name in VARIABLE_COLUMNS if safe_float(row.get(name, "")) is not None]
    row["available_variable_count"] = str(len(available))
    row["available_variable_names"] = "|".join(available)


def blank_uk_ofcom_proxy(rows: List[Dict[str, str]]) -> int:
    changed = 0
    for row in rows:
        if is_target_ofcom_proxy(row):
            row["foreign_dependency_ratio"] = ""
            refresh_available_variables(row)
            changed += 1
    return changed


def rebuild_sensitivity_panels(
    sector_variable_rows: List[Dict[str, str]],
    platform_variable_rows: List[Dict[str, str]],
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], List[Dict[str, str]]]:
    normalized_by_row, variable_stats, inactive_variables = variable_pipeline(sector_variable_rows)
    sector_country_subindex_rows, _, _ = calculate_country_panel(
        sector_variable_rows,
        normalized_by_row,
        variable_stats,
        inactive_variables,
    )
    sector_subindex_rows, _ = calculate_sector_quarter_panel(sector_country_subindex_rows)

    sector_country_rows = add_cpii_to_subindex_rows(
        sector_country_subindex_rows,
        SECTOR_COUNTRY_SPEC_CODE,
        "sector_country_quarter_expanded",
    )
    for row in sector_country_rows:
        row["firm_std"] = ""

    sector_rows = add_cpii_to_subindex_rows(
        sector_subindex_rows,
        SECTOR_SPEC_CODE,
        "sector_quarter_base",
    )
    for row in sector_rows:
        row["country_std"] = ""
        row["firm_std"] = ""

    anchor_profiles, cpii_inactive_variables = build_anchor_profiles(sector_variable_rows)
    active_components = subindex_components_active(
        {variable: {"status": "active"} for variable in anchor_profiles}
    )
    firm_country_rows = build_firm_country_panel(
        platform_variable_rows,
        anchor_profiles,
        active_components,
        cpii_inactive_variables,
    )
    return sector_rows, sector_country_rows, firm_country_rows


def rows_by_key(rows: Iterable[Dict[str, str]], key_fields: Iterable[str]) -> Dict[Tuple[str, ...], Dict[str, str]]:
    fields = list(key_fields)
    return {tuple(row.get(field, "") for field in fields): row for row in rows}


def metric_mean(rows: Iterable[Dict[str, str]], field: str) -> Optional[float]:
    values = [safe_float(row.get(field, "")) for row in rows]
    clean = [value for value in values if value is not None]
    return mean(clean) if clean else None


def metric_count(rows: Iterable[Dict[str, str]], field: str) -> int:
    return sum(1 for row in rows if safe_float(row.get(field, "")) is not None)


def fmt_delta(value: Optional[float]) -> str:
    return fmt(value)


def delta(after: Optional[float], before: Optional[float]) -> Optional[float]:
    if after is None or before is None:
        return None
    return after - before


def sector_summary(
    baseline_rows: List[Dict[str, str]],
    sensitivity_rows: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    sectors = sorted({row["sector_std"] for row in baseline_rows + sensitivity_rows if row.get("sector_std")})
    out: List[Dict[str, str]] = []
    for sector in sectors:
        base_sector = [row for row in baseline_rows if row.get("sector_std") == sector]
        sens_sector = [row for row in sensitivity_rows if row.get("sector_std") == sector]
        base_cpii = metric_mean(base_sector, "CPII")
        sens_cpii = metric_mean(sens_sector, "CPII")
        base_market = metric_mean(base_sector, "I_market")
        sens_market = metric_mean(sens_sector, "I_market")
        out.append(
            {
                "sector_std": sector,
                "baseline_obs_CPII": str(metric_count(base_sector, "CPII")),
                "sensitivity_obs_CPII": str(metric_count(sens_sector, "CPII")),
                "baseline_mean_CPII": fmt(base_cpii),
                "sensitivity_mean_CPII": fmt(sens_cpii),
                "delta_mean_CPII": fmt_delta(delta(sens_cpii, base_cpii)),
                "baseline_obs_I_market": str(metric_count(base_sector, "I_market")),
                "sensitivity_obs_I_market": str(metric_count(sens_sector, "I_market")),
                "baseline_mean_I_market": fmt(base_market),
                "sensitivity_mean_I_market": fmt(sens_market),
                "delta_mean_I_market": fmt_delta(delta(sens_market, base_market)),
            }
        )
    return out


def comparison_rows(
    baseline_rows: List[Dict[str, str]],
    sensitivity_rows: List[Dict[str, str]],
    key_fields: List[str],
    filter_country: str,
    keep_fields: List[str],
) -> List[Dict[str, str]]:
    baseline_by_key = rows_by_key(
        [row for row in baseline_rows if row.get("country_std") == filter_country],
        key_fields,
    )
    sensitivity_by_key = rows_by_key(
        [row for row in sensitivity_rows if row.get("country_std") == filter_country],
        key_fields,
    )
    keys = sorted(set(baseline_by_key) | set(sensitivity_by_key))
    out: List[Dict[str, str]] = []
    for key in keys:
        base = baseline_by_key.get(key, {})
        sens = sensitivity_by_key.get(key, {})
        row: Dict[str, str] = {field: (base or sens).get(field, "") for field in keep_fields}
        for field in ["foreign_dependency_ratio", "I_market", "i_market_status", "CPII", "cpii_status"]:
            base_value = base.get(field, "")
            sens_value = sens.get(field, "")
            row[f"baseline_{field}"] = base_value
            row[f"sensitivity_{field}"] = sens_value
            if field in {"I_market", "CPII"}:
                row[f"delta_{field}"] = fmt_delta(delta(safe_float(sens_value), safe_float(base_value)))
        out.append(row)
    return out


def attach_variable_values(
    comparison: List[Dict[str, str]],
    baseline_variable_rows: List[Dict[str, str]],
    sensitivity_variable_rows: List[Dict[str, str]],
    key_fields: List[str],
    field: str,
) -> None:
    baseline_by_key = rows_by_key(baseline_variable_rows, key_fields)
    sensitivity_by_key = rows_by_key(sensitivity_variable_rows, key_fields)
    for row in comparison:
        key = tuple(row.get(field_name, "") for field_name in key_fields)
        row[f"baseline_{field}"] = baseline_by_key.get(key, {}).get(field, "")
        row[f"sensitivity_{field}"] = sensitivity_by_key.get(key, {}).get(field, "")


def transition_count(
    baseline_rows: List[Dict[str, str]],
    sensitivity_rows: List[Dict[str, str]],
    key_fields: List[str],
    country: str,
    status_field: str,
) -> int:
    baseline_by_key = rows_by_key(
        [row for row in baseline_rows if row.get("country_std") == country],
        key_fields,
    )
    sensitivity_by_key = rows_by_key(
        [row for row in sensitivity_rows if row.get("country_std") == country],
        key_fields,
    )
    count = 0
    for key, base in baseline_by_key.items():
        sens = sensitivity_by_key.get(key, {})
        if base.get(status_field) == "computed" and sens.get(status_field) != "computed":
            count += 1
    return count


def max_abs_delta(rows: Iterable[Dict[str, str]], field: str) -> Optional[float]:
    deltas = [safe_float(row.get(field, "")) for row in rows]
    clean = [abs(value) for value in deltas if value is not None]
    return max(clean) if clean else None


def main() -> None:
    sector_variable_rows = read_csv(SECTOR_VARIABLE_PATH)
    platform_variable_rows = read_csv(PLATFORM_VARIABLE_PATH)
    sensitivity_sector_variable_rows = copy_rows(sector_variable_rows)
    sensitivity_platform_variable_rows = copy_rows(platform_variable_rows)

    blanked_sector_rows = blank_uk_ofcom_proxy(sensitivity_sector_variable_rows)
    blanked_platform_rows = blank_uk_ofcom_proxy(sensitivity_platform_variable_rows)

    sensitivity_sector_rows, sensitivity_sector_country_rows, sensitivity_firm_country_rows = rebuild_sensitivity_panels(
        sensitivity_sector_variable_rows,
        sensitivity_platform_variable_rows,
    )

    baseline_sector_rows = read_csv(BASELINE_SECTOR_PATH)
    baseline_sector_country_rows = read_csv(BASELINE_SECTOR_COUNTRY_PATH)
    baseline_firm_country_rows = read_csv(BASELINE_FIRM_COUNTRY_PATH)

    summary_rows = sector_summary(baseline_sector_rows, sensitivity_sector_rows)
    uk_sector_country_rows = comparison_rows(
        baseline_sector_country_rows,
        sensitivity_sector_country_rows,
        ["sector_std", "country_std", "year_quarter"],
        "uk",
        ["sector_std", "country_std", "country_priority_tier", "year_quarter"],
    )
    attach_variable_values(
        uk_sector_country_rows,
        sector_variable_rows,
        sensitivity_sector_variable_rows,
        ["sector_std", "country_std", "year_quarter"],
        "foreign_dependency_ratio",
    )
    uk_firm_country_rows = comparison_rows(
        baseline_firm_country_rows,
        sensitivity_firm_country_rows,
        ["firm_std", "country_std", "sector_std", "year_quarter"],
        "uk",
        ["firm_std", "country_std", "sector_std", "country_priority_tier", "year_quarter", "service_list"],
    )

    write_csv(OUT_SECTOR_SUMMARY, summary_rows, list(summary_rows[0].keys()))
    write_csv(OUT_UK_SECTOR_COUNTRY, uk_sector_country_rows, list(uk_sector_country_rows[0].keys()))
    write_csv(OUT_UK_FIRM_COUNTRY, uk_firm_country_rows, list(uk_firm_country_rows[0].keys()))

    uk_sc_i_market_lost = transition_count(
        baseline_sector_country_rows,
        sensitivity_sector_country_rows,
        ["sector_std", "country_std", "year_quarter"],
        "uk",
        "i_market_status",
    )
    uk_sc_cpii_lost = transition_count(
        baseline_sector_country_rows,
        sensitivity_sector_country_rows,
        ["sector_std", "country_std", "year_quarter"],
        "uk",
        "cpii_status",
    )
    uk_fc_i_market_lost = transition_count(
        baseline_firm_country_rows,
        sensitivity_firm_country_rows,
        ["firm_std", "country_std", "sector_std", "year_quarter"],
        "uk",
        "i_market_status",
    )
    uk_fc_cpii_lost = transition_count(
        baseline_firm_country_rows,
        sensitivity_firm_country_rows,
        ["firm_std", "country_std", "sector_std", "year_quarter"],
        "uk",
        "cpii_status",
    )

    max_sector_cpii_delta = max_abs_delta(summary_rows, "delta_mean_CPII")
    max_sector_market_delta = max_abs_delta(summary_rows, "delta_mean_I_market")
    max_uk_sc_cpii_delta = max_abs_delta(uk_sector_country_rows, "delta_CPII")
    max_uk_fc_cpii_delta = max_abs_delta(uk_firm_country_rows, "delta_CPII")

    timestamp = dt.datetime.now().isoformat(timespec="seconds")
    lines = [
        "Ofcom Proxy Sensitivity Summary",
        f"Timestamp: {timestamp}",
        "",
        "Scenario: blank UK `foreign_dependency_ratio == 0.94` in working copies, rebuild subindex/CPII panels in memory, and compare against baseline processed artifacts.",
        f"Blanked sector-quarter variable rows: {blanked_sector_rows}",
        f"Blanked platform-quarter variable rows: {blanked_platform_rows}",
        "",
        "Headline movement:",
        f"- Maximum absolute sector mean CPII delta: {fmt(max_sector_cpii_delta)}",
        f"- Maximum absolute sector mean I_market delta: {fmt(max_sector_market_delta)}",
        f"- Maximum absolute UK sector-country CPII row delta: {fmt(max_uk_sc_cpii_delta)}",
        f"- Maximum absolute UK firm-country CPII row delta: {fmt(max_uk_fc_cpii_delta)}",
        "",
        "Coverage loss:",
        f"- UK sector-country rows losing computed I_market: {uk_sc_i_market_lost}",
        f"- UK sector-country rows losing computed CPII: {uk_sc_cpii_lost}",
        f"- UK firm-country rows losing computed I_market: {uk_fc_i_market_lost}",
        f"- UK firm-country rows losing computed CPII: {uk_fc_cpii_lost}",
        "",
        "Artifacts:",
        f"- {rel(OUT_SECTOR_SUMMARY)}",
        f"- {rel(OUT_UK_SECTOR_COUNTRY)}",
        f"- {rel(OUT_UK_FIRM_COUNTRY)}",
    ]
    OUT_SUMMARY_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
