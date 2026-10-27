#!/usr/bin/env python3

from __future__ import annotations

import csv
from calendar import monthrange
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


BASE_DIR = Path(__file__).resolve().parents[1]

DEDUP_PATH = BASE_DIR / "data/interim/deduplicated_panel.csv"
MATRIX_PATH = BASE_DIR / "data/registry/firm_country_service_matrix.csv"
FIRM_DICT_PATH = BASE_DIR / "data/registry/entity_dictionary_firm.csv"
SERVICE_DICT_PATH = BASE_DIR / "data/registry/entity_dictionary_service.csv"
COUNTRY_UNIVERSE_PATH = BASE_DIR / "data/registry/country_universe.csv"

KEY_AUDIT_PATH = BASE_DIR / "data/interim/panel_key_audit.csv"
PLATFORM_MONTH_PATH = BASE_DIR / "data/interim/panel_skeleton_platform_month.csv"
PLATFORM_QUARTER_PATH = BASE_DIR / "data/interim/panel_skeleton_platform_quarter.csv"
TITLE_QUARTER_PATH = BASE_DIR / "data/interim/panel_skeleton_title_quarter.csv"
SECTOR_QUARTER_PATH = BASE_DIR / "data/interim/panel_skeleton_sector_quarter.csv"
LOG_PATH = BASE_DIR / "logs/panel_key_log.md"
MANIFEST_PATH = BASE_DIR / "data/registry/project_manifest.csv"
WORKFLOW_LOG_PATH = BASE_DIR / "logs/workflow_log.md"

ACCESS_DATE = "2026-03-29"
PROMPT_NAME = "Exec Prompt 22"

DIRECT_SERVICE_PANELS = {
    "music_market_raw_panel",
    "webtoon_platform_raw_panel",
    "infra_service_raw_panel",
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


def quarter_sort_key(value: str) -> Tuple[int, int]:
    return int(value[:4]), int(value[-1])


def month_sort_key(value: str) -> Tuple[int, int]:
    return int(value[:4]), int(value[5:7])


def year_month_end_date(value: str) -> str:
    year, month = value.split("-")
    y = int(year)
    m = int(month)
    last_day = monthrange(y, m)[1]
    return f"{y:04d}-{m:02d}-{last_day:02d}"


def quarter_start_end_dates(value: str) -> Tuple[str, str]:
    year = int(value[:4])
    quarter = int(value[-1])
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    start_date = date(year, start_month, 1).isoformat()
    end_day = monthrange(year, end_month)[1]
    end_date = date(year, end_month, end_day).isoformat()
    return start_date, end_date


def join_sorted(values: Iterable[str]) -> str:
    cleaned = sorted({value for value in values if value})
    return "|".join(cleaned)


def merge_type_from_count(count: int) -> str:
    if count == 0:
        return "zero_to_many_missing"
    if count == 1:
        return "one_to_one"
    return "one_to_many_requires_aggregation"


def unique_test(rows: List[Dict[str, str]], fields: List[str]) -> Tuple[int, int, int, int]:
    counter = Counter(tuple(row[field] for field in fields) for row in rows if all(row.get(field, "") for field in fields))
    distinct_keys = len(counter)
    duplicate_keys = sum(1 for value in counter.values() if value > 1)
    max_rows_per_key = max(counter.values()) if counter else 0
    evaluated_rows = sum(counter.values())
    return distinct_keys, duplicate_keys, max_rows_per_key, evaluated_rows


def build_key_audit_summary(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    specs = [
        {
            "analysis_unit": "platform_month_raw",
            "test_name": "service_std + year_month uniqueness",
            "tested_key_fields": "service_std|year_month",
            "tested_fields": ["service_std", "year_month"],
            "recommended_key_fields": "service_std|country_std|year_month",
            "merge_type": "one_to_many_requires_aggregation",
            "notes": "동일 서비스가 여러 국가에 존재하고, 같은 서비스-월에 여러 metric row가 존재하므로 naive join은 불가하다.",
        },
        {
            "analysis_unit": "platform_quarter_raw",
            "test_name": "service_std + year_quarter uniqueness",
            "tested_key_fields": "service_std|year_quarter",
            "tested_fields": ["service_std", "year_quarter"],
            "recommended_key_fields": "service_std|country_std|year_quarter",
            "merge_type": "one_to_many_requires_aggregation",
            "notes": "서비스-분기 단위는 direct service row, title row, filing row가 함께 존재하므로 집계 전 병합키로 사용할 수 없다.",
        },
        {
            "analysis_unit": "title_quarter_raw",
            "test_name": "title_std + service_std + year_quarter uniqueness",
            "tested_key_fields": "title_std|service_std|year_quarter",
            "tested_fields": ["title_std", "service_std", "year_quarter"],
            "recommended_key_fields": "title_std|service_std|country_std|year_quarter",
            "merge_type": "one_to_many_requires_metric_pivot",
            "notes": "작품 단위는 `title_position`, `local_ip_proxy`, `translated_proxy`가 개별 row로 존재하므로 metric pivot이 필요하다.",
        },
        {
            "analysis_unit": "sector_quarter_raw",
            "test_name": "sector_std + year_quarter uniqueness",
            "tested_key_fields": "sector_std|year_quarter",
            "tested_fields": ["sector_std", "year_quarter"],
            "recommended_key_fields": "sector_std|country_std|year_quarter",
            "merge_type": "one_to_many_requires_aggregation",
            "notes": "섹터-분기 단위는 국가, 서비스, 작품, 기업 row가 혼재하므로 국가 축과 집계 규칙을 먼저 고정해야 한다.",
        },
    ]

    summary_rows = []
    for index, spec in enumerate(specs, start=1):
        distinct_keys, duplicate_keys, max_rows_per_key, evaluated_rows = unique_test(rows, spec["tested_fields"])
        summary_rows.append(
            {
                "audit_id": f"audit_summary_{index:03d}",
                "row_type": "uniqueness_test",
                "analysis_unit": spec["analysis_unit"],
                "test_name": spec["test_name"],
                "tested_key_fields": spec["tested_key_fields"],
                "recommended_key_fields": spec["recommended_key_fields"],
                "rows_evaluated": str(evaluated_rows),
                "distinct_key_count": str(distinct_keys),
                "duplicate_key_count": str(duplicate_keys),
                "max_rows_per_key": str(max_rows_per_key),
                "key_unique_flag": "yes" if duplicate_keys == 0 else "no",
                "merge_type": spec["merge_type"],
                "expected_cell_count": "",
                "covered_cell_count": "",
                "failure_count": "",
                "firm_std": "",
                "service_std": "",
                "country_std": "",
                "title_std": "",
                "sector_std": "",
                "year_month": "",
                "year_quarter": "",
                "failure_reason": "",
                "notes": spec["notes"],
            }
        )
    return summary_rows


def main() -> None:
    dedup_rows = read_csv(DEDUP_PATH)
    matrix_rows = read_csv(MATRIX_PATH)
    firm_dict = {row["firm_std"]: row for row in read_csv(FIRM_DICT_PATH)}
    service_dict = {row["service_std"]: row for row in read_csv(SERVICE_DICT_PATH)}
    country_dict = {row["country_std"]: row for row in read_csv(COUNTRY_UNIVERSE_PATH)}

    month_periods_by_sector: Dict[str, List[str]] = defaultdict(list)
    quarter_periods_by_sector: Dict[str, List[str]] = defaultdict(list)

    direct_month_index: Dict[Tuple[str, str, str], List[Dict[str, str]]] = defaultdict(list)
    direct_quarter_index: Dict[Tuple[str, str, str], List[Dict[str, str]]] = defaultdict(list)
    title_quarter_index: Dict[Tuple[str, str, str, str], List[Dict[str, str]]] = defaultdict(list)
    title_service_quarter_index: Dict[Tuple[str, str, str], List[Dict[str, str]]] = defaultdict(list)
    financial_quarter_index: Dict[Tuple[str, str], List[Dict[str, str]]] = defaultdict(list)
    financial_month_index: Dict[Tuple[str, str], List[Dict[str, str]]] = defaultdict(list)
    sector_country_quarter_index: Dict[Tuple[str, str, str], List[Dict[str, str]]] = defaultdict(list)

    for row in dedup_rows:
        sector = row.get("sector_std", "")
        if row.get("period_type") == "month" and sector and row.get("year_month"):
            month_periods_by_sector[sector].append(row["year_month"])
        if sector and row.get("year_quarter"):
            quarter_periods_by_sector[sector].append(row["year_quarter"])

        service_std = row.get("service_std", "")
        country_std = row.get("country_std", "")
        firm_std = row.get("firm_std", "")
        year_month = row.get("year_month", "")
        year_quarter = row.get("year_quarter", "")
        title_std = row.get("title_std", "")

        if service_std and country_std and year_month and row.get("period_type") == "month":
            direct_month_index[(service_std, country_std, year_month)].append(row)

        if service_std and country_std and year_quarter and row.get("source_panel") in DIRECT_SERVICE_PANELS:
            direct_quarter_index[(service_std, country_std, year_quarter)].append(row)

        if title_std and service_std and country_std and year_quarter:
            title_quarter_index[(title_std, service_std, country_std, year_quarter)].append(row)
            title_service_quarter_index[(service_std, country_std, year_quarter)].append(row)

        if row.get("source_panel") == "financial_extraction_panel" and firm_std and year_quarter:
            financial_quarter_index[(firm_std, year_quarter)].append(row)
        if row.get("source_panel") == "financial_extraction_panel" and firm_std and year_month:
            financial_month_index[(firm_std, year_month)].append(row)

        if sector and country_std and year_quarter:
            sector_country_quarter_index[(sector, country_std, year_quarter)].append(row)

    month_periods_by_sector = {
        sector: sorted(set(periods), key=month_sort_key) for sector, periods in month_periods_by_sector.items()
    }
    quarter_periods_by_sector = {
        sector: sorted(set(periods), key=quarter_sort_key) for sector, periods in quarter_periods_by_sector.items()
    }

    key_audit_rows = build_key_audit_summary(dedup_rows)
    platform_month_rows: List[Dict[str, str]] = []
    platform_quarter_rows: List[Dict[str, str]] = []
    title_quarter_rows: List[Dict[str, str]] = []
    sector_quarter_rows: List[Dict[str, str]] = []
    failure_rows: List[Dict[str, str]] = []

    platform_month_id = 1
    platform_quarter_id = 1
    title_quarter_id = 1
    sector_quarter_id = 1
    failure_id = 1

    monthly_matrix_rows = [row for row in matrix_rows if row["sector_std"] == "music"]

    for matrix_row in monthly_matrix_rows:
        firm_row = firm_dict[matrix_row["firm_std"]]
        country_meta = country_dict.get(matrix_row["country_std"], {})
        for year_month in month_periods_by_sector.get("music", []):
            direct_rows = direct_month_index.get((matrix_row["service_std"], matrix_row["country_std"], year_month), [])
            fiscal_rows = financial_month_index.get((matrix_row["firm_std"], year_month), [])
            direct_metric_names = join_sorted(row["metric_name"] for row in direct_rows)
            fiscal_metric_names = join_sorted(row["metric_name"] for row in fiscal_rows)
            direct_sources = join_sorted(row["source_panel"] for row in direct_rows)
            fiscal_sources = join_sorted(row["source_panel"] for row in fiscal_rows)
            total_support_rows = len(direct_rows) + len(fiscal_rows)
            observed_any_flag = "yes" if total_support_rows > 0 else "no"

            if len(direct_rows) > 0 and len(fiscal_rows) > 0:
                merge_readiness = "ready_direct_and_firm_bridge"
            elif len(direct_rows) > 0:
                merge_readiness = "ready_direct_only"
            elif len(fiscal_rows) > 0:
                merge_readiness = "ready_firm_bridge_only"
            else:
                merge_readiness = "not_ready"

            row = {
                "panel_platform_month_id": f"platform_month_{platform_month_id:05d}",
                "firm_std": matrix_row["firm_std"],
                "service_std": matrix_row["service_std"],
                "country_std": matrix_row["country_std"],
                "home_country": firm_row["home_country"],
                "sector_std": matrix_row["sector_std"],
                "tier": matrix_row["tier"],
                "coverage_expectation": matrix_row["coverage_expectation"],
                "target_data_types": matrix_row["target_data_types"],
                "country_priority_tier": country_meta.get("priority_tier", ""),
                "year_month": year_month,
                "year": year_month[:4],
                "year_quarter": f"{year_month[:4]}Q{((int(year_month[5:7]) - 1) // 3) + 1}",
                "month_end_date": year_month_end_date(year_month),
                "merge_key_service_year_month": f"{matrix_row['service_std']}|{year_month}",
                "merge_key_service_country_year_month": f"{matrix_row['service_std']}|{matrix_row['country_std']}|{year_month}",
                "direct_service_row_count": str(len(direct_rows)),
                "fiscal_same_month_row_count": str(len(fiscal_rows)),
                "direct_metric_count": str(len({row['metric_name'] for row in direct_rows})),
                "fiscal_metric_count": str(len({row['metric_name'] for row in fiscal_rows})),
                "direct_metric_names": direct_metric_names,
                "fiscal_metric_names": fiscal_metric_names,
                "direct_source_panels": direct_sources,
                "fiscal_source_panels": fiscal_sources,
                "observed_any_flag": observed_any_flag,
                "merge_type_observed": merge_type_from_count(total_support_rows),
                "merge_readiness": merge_readiness,
                "failure_flag": "yes" if merge_readiness == "not_ready" else "no",
                "failure_reason": "no_month_source_or_fiscal_bridge" if merge_readiness == "not_ready" else "",
            }
            platform_month_rows.append(row)

            if row["failure_flag"] == "yes":
                failure_rows.append(
                    {
                        "audit_id": f"audit_failure_{failure_id:05d}",
                        "row_type": "merge_failure_cell",
                        "analysis_unit": "platform_month",
                        "test_name": "expected service-country-month cell coverage",
                        "tested_key_fields": "service_std|country_std|year_month",
                        "recommended_key_fields": "service_std|country_std|year_month",
                        "rows_evaluated": "",
                        "distinct_key_count": "",
                        "duplicate_key_count": "",
                        "max_rows_per_key": "",
                        "key_unique_flag": "",
                        "merge_type": "zero_to_many_missing",
                        "expected_cell_count": "",
                        "covered_cell_count": "",
                        "failure_count": "",
                        "firm_std": matrix_row["firm_std"],
                        "service_std": matrix_row["service_std"],
                        "country_std": matrix_row["country_std"],
                        "title_std": "",
                        "sector_std": matrix_row["sector_std"],
                        "year_month": year_month,
                        "year_quarter": row["year_quarter"],
                        "failure_reason": row["failure_reason"],
                        "notes": "firm_country_service_matrix 기반 기대 셀이지만 direct month row와 fiscal bridge가 모두 부재함.",
                    }
                )
                failure_id += 1

            platform_month_id += 1

    for matrix_row in matrix_rows:
        firm_row = firm_dict[matrix_row["firm_std"]]
        country_meta = country_dict.get(matrix_row["country_std"], {})
        for year_quarter in quarter_periods_by_sector.get(matrix_row["sector_std"], []):
            direct_rows = direct_quarter_index.get((matrix_row["service_std"], matrix_row["country_std"], year_quarter), [])
            title_rows = title_service_quarter_index.get((matrix_row["service_std"], matrix_row["country_std"], year_quarter), [])
            fiscal_rows = financial_quarter_index.get((matrix_row["firm_std"], year_quarter), [])
            total_support_rows = len(direct_rows) + len(title_rows) + len(fiscal_rows)

            if direct_rows and fiscal_rows:
                merge_readiness = "ready_service_and_firm"
            elif direct_rows:
                merge_readiness = "ready_service_only"
            elif title_rows and fiscal_rows:
                merge_readiness = "ready_title_aggregate_and_firm"
            elif title_rows:
                merge_readiness = "ready_title_aggregate_only"
            elif fiscal_rows:
                merge_readiness = "ready_firm_only"
            else:
                merge_readiness = "not_ready"

            start_date, end_date = quarter_start_end_dates(year_quarter)
            row = {
                "panel_platform_quarter_id": f"platform_quarter_{platform_quarter_id:05d}",
                "firm_std": matrix_row["firm_std"],
                "service_std": matrix_row["service_std"],
                "country_std": matrix_row["country_std"],
                "home_country": firm_row["home_country"],
                "sector_std": matrix_row["sector_std"],
                "tier": matrix_row["tier"],
                "coverage_expectation": matrix_row["coverage_expectation"],
                "target_data_types": matrix_row["target_data_types"],
                "country_priority_tier": country_meta.get("priority_tier", ""),
                "year_quarter": year_quarter,
                "quarter_start_date": start_date,
                "quarter_end_date": end_date,
                "merge_key_service_year_quarter": f"{matrix_row['service_std']}|{year_quarter}",
                "merge_key_service_country_year_quarter": f"{matrix_row['service_std']}|{matrix_row['country_std']}|{year_quarter}",
                "direct_service_row_count": str(len(direct_rows)),
                "title_aggregate_row_count": str(len(title_rows)),
                "fiscal_same_quarter_row_count": str(len(fiscal_rows)),
                "direct_metric_names": join_sorted(row["metric_name"] for row in direct_rows),
                "title_metric_names": join_sorted(row["metric_name"] for row in title_rows),
                "fiscal_metric_names": join_sorted(row["metric_name"] for row in fiscal_rows),
                "direct_source_panels": join_sorted(row["source_panel"] for row in direct_rows),
                "title_source_panels": join_sorted(row["source_panel"] for row in title_rows),
                "fiscal_source_panels": join_sorted(row["source_panel"] for row in fiscal_rows),
                "observed_any_flag": "yes" if total_support_rows > 0 else "no",
                "merge_type_observed": merge_type_from_count(total_support_rows),
                "merge_readiness": merge_readiness,
                "failure_flag": "yes" if merge_readiness == "not_ready" else "no",
                "failure_reason": "no_service_title_or_fiscal_bridge" if merge_readiness == "not_ready" else "",
            }
            platform_quarter_rows.append(row)

            if row["failure_flag"] == "yes":
                failure_rows.append(
                    {
                        "audit_id": f"audit_failure_{failure_id:05d}",
                        "row_type": "merge_failure_cell",
                        "analysis_unit": "platform_quarter",
                        "test_name": "expected service-country-quarter cell coverage",
                        "tested_key_fields": "service_std|country_std|year_quarter",
                        "recommended_key_fields": "service_std|country_std|year_quarter",
                        "rows_evaluated": "",
                        "distinct_key_count": "",
                        "duplicate_key_count": "",
                        "max_rows_per_key": "",
                        "key_unique_flag": "",
                        "merge_type": "zero_to_many_missing",
                        "expected_cell_count": "",
                        "covered_cell_count": "",
                        "failure_count": "",
                        "firm_std": matrix_row["firm_std"],
                        "service_std": matrix_row["service_std"],
                        "country_std": matrix_row["country_std"],
                        "title_std": "",
                        "sector_std": matrix_row["sector_std"],
                        "year_month": "",
                        "year_quarter": year_quarter,
                        "failure_reason": row["failure_reason"],
                        "notes": "service-country-quarter 기대 셀에 direct service row, title aggregate row, firm fiscal bridge가 모두 부재함.",
                    }
                )
                failure_id += 1

            platform_quarter_id += 1

    for key in sorted(title_quarter_index.keys(), key=lambda value: (quarter_sort_key(value[3]), value[1], value[2], value[0])):
        title_std, service_std, country_std, year_quarter = key
        rows_for_key = title_quarter_index[key]
        service_meta = service_dict[service_std]
        firm_std = service_meta["parent_firm_std"]
        firm_row = firm_dict[firm_std]
        country_meta = country_dict.get(country_std, {})
        start_date, end_date = quarter_start_end_dates(year_quarter)
        title_quarter_rows.append(
            {
                "panel_title_quarter_id": f"title_quarter_{title_quarter_id:05d}",
                "title_std": title_std,
                "service_std": service_std,
                "firm_std": firm_std,
                "country_std": country_std,
                "home_country": firm_row["home_country"],
                "sector_std": service_meta["sector_std"],
                "country_priority_tier": country_meta.get("priority_tier", ""),
                "year_quarter": year_quarter,
                "quarter_start_date": start_date,
                "quarter_end_date": end_date,
                "merge_key_title_service_year_quarter": f"{title_std}|{service_std}|{year_quarter}",
                "merge_key_title_service_country_year_quarter": f"{title_std}|{service_std}|{country_std}|{year_quarter}",
                "title_row_count": str(len(rows_for_key)),
                "metric_count": str(len({row['metric_name'] for row in rows_for_key})),
                "metric_names": join_sorted(row["metric_name"] for row in rows_for_key),
                "source_panels": join_sorted(row["source_panel"] for row in rows_for_key),
                "observed_any_flag": "yes",
                "merge_type_observed": merge_type_from_count(len(rows_for_key)),
                "merge_readiness": "ready_title_direct",
                "failure_flag": "no",
                "failure_reason": "",
            }
        )
        title_quarter_id += 1

    sectors = sorted({row["sector_std"] for row in matrix_rows})
    countries_by_sector = {
        sector: sorted({row["country_std"] for row in matrix_rows if row["sector_std"] == sector})
        for sector in sectors
    }
    firms_by_sector_country = defaultdict(set)
    services_by_sector_country = defaultdict(set)
    for row in matrix_rows:
        firms_by_sector_country[(row["sector_std"], row["country_std"])].add(row["firm_std"])
        services_by_sector_country[(row["sector_std"], row["country_std"])].add(row["service_std"])

    for sector in sectors:
        for country_std in countries_by_sector[sector]:
            country_meta = country_dict.get(country_std, {})
            for year_quarter in quarter_periods_by_sector.get(sector, []):
                rows_for_key = sector_country_quarter_index.get((sector, country_std, year_quarter), [])
                active_firms = sorted(firms_by_sector_country[(sector, country_std)])
                fiscal_firm_count = sum(
                    1 for firm_std in active_firms if financial_quarter_index.get((firm_std, year_quarter))
                )
                service_cell_count_observed = len(
                    {
                        (row["service_std"], row["country_std"], row["year_quarter"])
                        for row in rows_for_key
                        if row["service_std"]
                    }
                )
                title_cell_count_observed = len(
                    {
                        (row["title_std"], row["service_std"], row["country_std"], row["year_quarter"])
                        for row in rows_for_key
                        if row["title_std"]
                    }
                )
                start_date, end_date = quarter_start_end_dates(year_quarter)
                merge_readiness = "ready_sector_aggregate" if rows_for_key or fiscal_firm_count else "not_ready"
                sector_quarter_rows.append(
                    {
                        "panel_sector_quarter_id": f"sector_quarter_{sector_quarter_id:05d}",
                        "sector_std": sector,
                        "country_std": country_std,
                        "country_priority_tier": country_meta.get("priority_tier", ""),
                        "year_quarter": year_quarter,
                        "quarter_start_date": start_date,
                        "quarter_end_date": end_date,
                        "service_cell_count_expected": str(len(services_by_sector_country[(sector, country_std)])),
                        "service_cell_count_observed": str(service_cell_count_observed),
                        "title_cell_count_observed": str(title_cell_count_observed),
                        "fiscal_firm_count_observed": str(fiscal_firm_count),
                        "row_count_observed": str(len(rows_for_key)),
                        "metric_names": join_sorted(row["metric_name"] for row in rows_for_key),
                        "source_panels": join_sorted(row["source_panel"] for row in rows_for_key),
                        "observed_any_flag": "yes" if rows_for_key or fiscal_firm_count else "no",
                        "merge_type_observed": merge_type_from_count(len(rows_for_key) + fiscal_firm_count),
                        "merge_readiness": merge_readiness,
                        "failure_flag": "yes" if merge_readiness == "not_ready" else "no",
                        "failure_reason": "no_sector_country_quarter_source" if merge_readiness == "not_ready" else "",
                    }
                )

                if merge_readiness == "not_ready":
                    failure_rows.append(
                        {
                            "audit_id": f"audit_failure_{failure_id:05d}",
                            "row_type": "merge_failure_cell",
                            "analysis_unit": "sector_quarter",
                            "test_name": "expected sector-country-quarter cell coverage",
                            "tested_key_fields": "sector_std|country_std|year_quarter",
                            "recommended_key_fields": "sector_std|country_std|year_quarter",
                            "rows_evaluated": "",
                            "distinct_key_count": "",
                            "duplicate_key_count": "",
                            "max_rows_per_key": "",
                            "key_unique_flag": "",
                            "merge_type": "zero_to_many_missing",
                            "expected_cell_count": "",
                            "covered_cell_count": "",
                            "failure_count": "",
                            "firm_std": "",
                            "service_std": "",
                            "country_std": country_std,
                            "title_std": "",
                            "sector_std": sector,
                            "year_month": "",
                            "year_quarter": year_quarter,
                            "failure_reason": "no_sector_country_quarter_source",
                            "notes": "sector-country-quarter 기대 셀에 direct/title/fiscal source가 모두 부재함.",
                        }
                    )
                    failure_id += 1

                sector_quarter_id += 1

    expected_platform_month = len(platform_month_rows)
    covered_platform_month = sum(1 for row in platform_month_rows if row["observed_any_flag"] == "yes")
    expected_platform_quarter = len(platform_quarter_rows)
    covered_platform_quarter = sum(1 for row in platform_quarter_rows if row["observed_any_flag"] == "yes")
    expected_title_quarter = len(title_quarter_rows)
    covered_title_quarter = expected_title_quarter
    expected_sector_quarter = len(sector_quarter_rows)
    covered_sector_quarter = sum(1 for row in sector_quarter_rows if row["observed_any_flag"] == "yes")

    failure_counter = Counter(row["analysis_unit"] for row in failure_rows)
    for row in key_audit_rows:
        if row["analysis_unit"] == "platform_month_raw":
            row["expected_cell_count"] = str(expected_platform_month)
            row["covered_cell_count"] = str(covered_platform_month)
            row["failure_count"] = str(failure_counter["platform_month"])
        elif row["analysis_unit"] == "platform_quarter_raw":
            row["expected_cell_count"] = str(expected_platform_quarter)
            row["covered_cell_count"] = str(covered_platform_quarter)
            row["failure_count"] = str(failure_counter["platform_quarter"])
        elif row["analysis_unit"] == "title_quarter_raw":
            row["expected_cell_count"] = str(expected_title_quarter)
            row["covered_cell_count"] = str(covered_title_quarter)
            row["failure_count"] = "0"
        elif row["analysis_unit"] == "sector_quarter_raw":
            row["expected_cell_count"] = str(expected_sector_quarter)
            row["covered_cell_count"] = str(covered_sector_quarter)
            row["failure_count"] = str(failure_counter["sector_quarter"])

    key_audit_rows.extend(failure_rows)

    key_audit_fields = [
        "audit_id",
        "row_type",
        "analysis_unit",
        "test_name",
        "tested_key_fields",
        "recommended_key_fields",
        "rows_evaluated",
        "distinct_key_count",
        "duplicate_key_count",
        "max_rows_per_key",
        "key_unique_flag",
        "merge_type",
        "expected_cell_count",
        "covered_cell_count",
        "failure_count",
        "firm_std",
        "service_std",
        "country_std",
        "title_std",
        "sector_std",
        "year_month",
        "year_quarter",
        "failure_reason",
        "notes",
    ]

    platform_month_fields = list(platform_month_rows[0].keys()) if platform_month_rows else []
    platform_quarter_fields = list(platform_quarter_rows[0].keys()) if platform_quarter_rows else []
    title_quarter_fields = list(title_quarter_rows[0].keys()) if title_quarter_rows else []
    sector_quarter_fields = list(sector_quarter_rows[0].keys()) if sector_quarter_rows else []

    write_csv(KEY_AUDIT_PATH, key_audit_rows, key_audit_fields)
    write_csv(PLATFORM_MONTH_PATH, platform_month_rows, platform_month_fields)
    write_csv(PLATFORM_QUARTER_PATH, platform_quarter_rows, platform_quarter_fields)
    write_csv(TITLE_QUARTER_PATH, title_quarter_rows, title_quarter_fields)
    write_csv(SECTOR_QUARTER_PATH, sector_quarter_rows, sector_quarter_fields)

    log_lines = [
        "# Panel Key Log",
        "",
        f"- Access date: `{ACCESS_DATE}`",
        f"- Prompt: `{PROMPT_NAME}`",
        "",
        "## Key Uniqueness Summary",
        "- `service_std + year_month`: non-unique, recommended analysis key is `service_std + country_std + year_month` after aggregation.",
        "- `service_std + year_quarter`: non-unique, recommended analysis key is `service_std + country_std + year_quarter` after aggregation.",
        "- `title_std + service_std + year_quarter`: non-unique in raw rows, recommended analysis key is `title_std + service_std + country_std + year_quarter` after metric pivot.",
        "- `sector_std + year_quarter`: non-unique, recommended analysis key is `sector_std + country_std + year_quarter` after aggregation.",
        "",
        "## Skeleton Counts",
        f"- `panel_skeleton_platform_month.csv`: expected `{expected_platform_month}`, covered `{covered_platform_month}`, failures `{failure_counter['platform_month']}`",
        f"- `panel_skeleton_platform_quarter.csv`: expected `{expected_platform_quarter}`, covered `{covered_platform_quarter}`, failures `{failure_counter['platform_quarter']}`",
        f"- `panel_skeleton_title_quarter.csv`: observed `{expected_title_quarter}`, failures `0`",
        f"- `panel_skeleton_sector_quarter.csv`: expected `{expected_sector_quarter}`, covered `{covered_sector_quarter}`, failures `{failure_counter['sector_quarter']}`",
        "",
        "## Notes",
        "- 월 골격은 실제 월 자료가 존재하는 `music` sector만 대상으로 생성했다.",
        "- 분기 골격은 sector별 관측 가능한 분기 집합을 기준으로 생성했고, 서비스국가와 법인 본국을 분리해 `home_country`를 함께 보존했다.",
        "- `panel_key_audit.csv`에는 required uniqueness test 4건과 skeleton 기준 merge failure cell 목록을 함께 기록했다.",
    ]
    LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    manifest_rows = read_csv(MANIFEST_PATH)
    manifest_additions = [
        {
            "artifact_type": "script",
            "path": "scripts/build_panel_skeletons.py",
            "owner_step": PROMPT_NAME,
            "source_type": "local_code",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Builds panel key audit tables and four analysis skeleton panels from deduplicated numeric data.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/interim/panel_key_audit.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_key_audit",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Key uniqueness tests plus merge failure cell records for expected analysis units.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/interim/panel_skeleton_platform_month.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_panel_skeleton",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Expected service-country-month analysis skeleton for music sector with source coverage flags.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/interim/panel_skeleton_platform_quarter.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_panel_skeleton",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Expected service-country-quarter analysis skeleton with direct, title, and filing bridge coverage flags.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/interim/panel_skeleton_title_quarter.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_panel_skeleton",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Observed title-service-country-quarter skeleton built from retained webtoon title rows.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/interim/panel_skeleton_sector_quarter.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_panel_skeleton",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Expected sector-country-quarter skeleton with observed source coverage counts.",
        },
        {
            "artifact_type": "log",
            "path": "logs/panel_key_log.md",
            "owner_step": PROMPT_NAME,
            "source_type": "local_log",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Summary log for key uniqueness tests, merge types, skeleton counts, and failure cells.",
        },
    ]
    existing_manifest_keys = {(row["owner_step"], row["path"]) for row in manifest_rows}
    for addition in manifest_additions:
        key = (addition["owner_step"], addition["path"])
        if key not in existing_manifest_keys:
            manifest_rows.append(addition)
            existing_manifest_keys.add(key)
    write_csv(MANIFEST_PATH, manifest_rows, list(manifest_rows[0].keys()))

    workflow_header = f"### {PROMPT_NAME}. 병합 키 검증 및 패널 골격 생성"
    workflow_text = WORKFLOW_LOG_PATH.read_text(encoding="utf-8") if WORKFLOW_LOG_PATH.exists() else ""
    if workflow_header not in workflow_text:
        addition = "\n".join(
            [
                workflow_header,
                "",
                f"- `data/interim/panel_key_audit.csv`에 required key test 4건과 merge failure cell `{len(failure_rows)}`건을 기록",
                f"- `data/interim/panel_skeleton_platform_month.csv` `{expected_platform_month}`행, `panel_skeleton_platform_quarter.csv` `{expected_platform_quarter}`행 생성",
                f"- `data/interim/panel_skeleton_title_quarter.csv` `{expected_title_quarter}`행, `panel_skeleton_sector_quarter.csv` `{expected_sector_quarter}`행 생성",
                "- 서비스국가와 법인 본국을 분리해 `home_country`를 함께 보존하고, direct/title/fiscal bridge coverage flag를 추가",
            ]
        )
        if workflow_text and not workflow_text.endswith("\n"):
            workflow_text += "\n"
        WORKFLOW_LOG_PATH.write_text(workflow_text + addition + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
