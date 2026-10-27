#!/usr/bin/env python3

import csv
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
ACCESS_DATE = date.today().isoformat()
PROMPT_NAME = "Exec Prompt 18"

REGISTRY_DIR = PROJECT_DIR / "data" / "registry"
INTERIM_DIR = PROJECT_DIR / "data" / "interim"
PROCESSED_DIR = PROJECT_DIR / "data" / "processed"
LOG_DIR = PROJECT_DIR / "logs"

MATRIX_PATH = REGISTRY_DIR / "firm_country_service_matrix.csv"
SERVICE_DICT_PATH = REGISTRY_DIR / "entity_dictionary_service.csv"
FILING_PANEL_PATH = INTERIM_DIR / "filing_metadata_panel.csv"
MUSIC_PANEL_PATH = INTERIM_DIR / "music_market_raw_panel.csv"
WEBTOON_PANEL_PATH = INTERIM_DIR / "webtoon_platform_raw_panel.csv"
INFRA_PANEL_PATH = INTERIM_DIR / "infra_service_raw_panel.csv"
VARIABLE_PLATFORM_QUARTER_PATH = PROCESSED_DIR / "variable_panel_platform_quarter.csv"

AUDIT_PATH = PROCESSED_DIR / "firm_service_coverage_audit.csv"
LOG_PATH = LOG_DIR / "firm_service_audit.md"
PROJECT_MANIFEST_PATH = REGISTRY_DIR / "project_manifest.csv"
WORKFLOW_LOG_PATH = LOG_DIR / "workflow_log.md"

PROJECT_MANIFEST_FIELDS = [
    "artifact_type",
    "path",
    "owner_step",
    "source_type",
    "source_url",
    "access_date",
    "status",
    "notes",
]

PANEL_CONFIG = {
    "music": {
        "path": MUSIC_PANEL_PATH,
        "primary_period_field": "year_month",
        "secondary_period_field": "",
        "panel_source": "music_market_raw_panel.csv",
        "minimum_required_periods": 3,
        "minimum_rule": "service-country cell needs at least 3 monthly observations",
    },
    "webtoon_story": {
        "path": WEBTOON_PANEL_PATH,
        "primary_period_field": "year_quarter",
        "secondary_period_field": "",
        "panel_source": "webtoon_platform_raw_panel.csv",
        "minimum_required_periods": 1,
        "minimum_rule": "service-country cell needs at least 1 quarterly observation",
    },
    "digital_infra": {
        "path": INFRA_PANEL_PATH,
        "primary_period_field": "year_month",
        "secondary_period_field": "year_quarter",
        "panel_source": "infra_service_raw_panel.csv",
        "minimum_required_periods": 1,
        "minimum_rule": "service-country cell needs at least 1 monthly or quarterly observation",
    },
}

MINIMUM_READY_TARGETS = {
    "music": 4,
    "webtoon_story": 4,
    "digital_infra": 8,
}


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def append_unique_rows(path, fieldnames, new_rows, unique_keys):
    existing_rows = []
    seen = set()
    if path.exists():
        existing_rows = read_csv(path)
        for row in existing_rows:
            seen.add(tuple(row[key] for key in unique_keys))
    for row in new_rows:
        normalized = {field: str(row.get(field, "")) for field in fieldnames}
        key = tuple(normalized[key_field] for key_field in unique_keys)
        if key not in seen:
            existing_rows.append(normalized)
            seen.add(key)
    write_csv(path, existing_rows, fieldnames)


def append_workflow_section(path, header, bullets):
    section_lines = ["", f"### {header}", ""]
    section_lines.extend(f"- {bullet}" for bullet in bullets)
    section = "\n".join(section_lines) + "\n"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
    else:
        existing = "# Workflow Log\n"
    if header in existing:
        return
    path.write_text(existing.rstrip() + section, encoding="utf-8")


def to_bool_flag(value):
    return "yes" if value else "no"


def sort_join(values):
    return "; ".join(sorted(value for value in values if value))


def get_period(row, primary_field, secondary_field):
    primary_value = (row.get(primary_field) or "").strip()
    if primary_value:
        return primary_value
    secondary_value = (row.get(secondary_field) or "").strip()
    return secondary_value


def first_last(sorted_values):
    if not sorted_values:
        return "", ""
    return sorted_values[0], sorted_values[-1]


def build_panel_maps(service_lookup):
    combo_stats = {}
    service_countries = defaultdict(set)
    firm_periods = defaultdict(set)
    unexpected_observed = []
    aggregate_issue_counter = Counter()

    matrix_expected = {
        tuple(row[key] for key in ["sector_std", "firm_std", "service_std", "country_std"])
        for row in read_csv(MATRIX_PATH)
    }

    for sector_std, config in PANEL_CONFIG.items():
        rows = read_csv(config["path"])
        primary_field = config["primary_period_field"]
        secondary_field = config["secondary_period_field"]
        for row in rows:
            firm_std = (row.get("firm_std") or "").strip()
            service_std = (row.get("service_std") or "").strip()
            country_std = (row.get("country_std") or "").strip()
            metric_name = (row.get("metric_name") or "").strip()
            period = get_period(row, primary_field, secondary_field)
            if not firm_std or not service_std:
                aggregate_issue_counter[(sector_std, country_std, metric_name)] += 1
                continue

            combo_key = (sector_std, firm_std, service_std, country_std)
            stats = combo_stats.setdefault(
                combo_key,
                {
                    "panel_source": config["panel_source"],
                    "row_count": 0,
                    "metrics": set(),
                    "periods": set(),
                },
            )
            stats["row_count"] += 1
            stats["metrics"].add(metric_name)
            if period:
                stats["periods"].add(period)

            service_countries[(sector_std, firm_std, service_std)].add(country_std)
            if period:
                firm_periods[(sector_std, firm_std)].add(period)

            service_row = service_lookup.get(service_std)
            anomaly_reasons = []
            if service_row is None:
                anomaly_reasons.append("service_code_not_in_dictionary")
            else:
                if service_row["parent_firm_std"] != firm_std:
                    anomaly_reasons.append("service_parent_mismatch")
                if service_row["sector_std"] != sector_std:
                    anomaly_reasons.append("service_sector_mismatch")
            if combo_key not in matrix_expected:
                anomaly_reasons.append("observed_cell_outside_matrix_universe")
            if anomaly_reasons:
                unexpected_observed.append(
                    {
                        "sector_std": sector_std,
                        "firm_std": firm_std,
                        "service_std": service_std,
                        "country_std": country_std,
                        "panel_source": config["panel_source"],
                        "panel_row_count": stats["row_count"],
                        "panel_metric_names": sort_join(stats["metrics"]),
                        "panel_period_count": len(stats["periods"]),
                        "panel_first_period": min(stats["periods"]) if stats["periods"] else "",
                        "panel_last_period": max(stats["periods"]) if stats["periods"] else "",
                        "anomaly_reason": "; ".join(sorted(set(anomaly_reasons))),
                    }
                )

    deduped_unexpected = {}
    for row in unexpected_observed:
        key = (
            row["sector_std"],
            row["firm_std"],
            row["service_std"],
            row["country_std"],
        )
        deduped_unexpected[key] = row

    return combo_stats, service_countries, firm_periods, list(deduped_unexpected.values()), aggregate_issue_counter


def build_filing_maps():
    filing_rows = read_csv(FILING_PANEL_PATH)
    filing_periods = defaultdict(set)
    filing_countries = defaultdict(set)
    firm_filing_periods = defaultdict(set)

    for row in filing_rows:
        key = (row["sector_std"], row["firm_std"], row["service_std"])
        filing_period = (row.get("fiscal_period") or "").strip()
        if filing_period:
            filing_periods[key].add(filing_period)
            firm_filing_periods[(row["sector_std"], row["firm_std"])].add(filing_period)
        filing_country = (row.get("country_std") or "").strip()
        if filing_country:
            filing_countries[key].add(filing_country)

    return filing_periods, filing_countries, firm_filing_periods


def build_derived_platform_maps():
    rows = read_csv(VARIABLE_PLATFORM_QUARTER_PATH)
    derived_combo_stats = {}
    for row in rows:
        sector_std = (row.get("sector_std") or "").strip()
        firm_std = (row.get("firm_std") or "").strip()
        service_std = (row.get("service_std") or "").strip()
        country_std = (row.get("country_std") or "").strip()
        year_quarter = (row.get("year_quarter") or "").strip()
        available_variable_count = int((row.get("available_variable_count") or "0").strip() or "0")
        if not sector_std or not firm_std or not service_std or not country_std or not year_quarter:
            continue
        if available_variable_count <= 0:
            continue
        combo_key = (sector_std, firm_std, service_std, country_std)
        stats = derived_combo_stats.setdefault(
            combo_key,
            {
                "periods": set(),
                "modes": set(),
            },
        )
        stats["periods"].add(year_quarter)
        if row.get("foreign_dependency_mode"):
            stats["modes"].add(row["foreign_dependency_mode"])
        if row.get("financial_bridge_mode"):
            stats["modes"].add(row["financial_bridge_mode"])
    return derived_combo_stats


def build_audit_rows():
    matrix_rows = read_csv(MATRIX_PATH)
    service_lookup = {row["service_std"]: row for row in read_csv(SERVICE_DICT_PATH)}
    expected_service_countries = defaultdict(set)
    for row in matrix_rows:
        expected_service_countries[(row["sector_std"], row["firm_std"], row["service_std"])].add(row["country_std"])

    combo_stats, observed_service_countries, firm_panel_periods, unexpected_observed, aggregate_issues = build_panel_maps(
        service_lookup
    )
    filing_periods, filing_countries, firm_filing_periods = build_filing_maps()
    derived_combo_stats = build_derived_platform_maps()

    audit_rows = []
    sector_summary = defaultdict(lambda: Counter())
    firm_summary = defaultdict(lambda: {"panel_periods": set(), "filing_periods": set()})

    for row in matrix_rows:
        sector_std = row["sector_std"]
        firm_std = row["firm_std"]
        service_std = row["service_std"]
        country_std = row["country_std"]
        combo_key = (sector_std, firm_std, service_std, country_std)
        service_key = (sector_std, firm_std, service_std)
        firm_key = (sector_std, firm_std)
        config = PANEL_CONFIG[sector_std]

        expected_countries = expected_service_countries[service_key]
        observed_countries = observed_service_countries.get(service_key, set())
        matched_countries = expected_countries.intersection(observed_countries)
        combo = combo_stats.get(combo_key, {})
        panel_periods = sorted(combo.get("periods", set()))
        panel_first_period, panel_last_period = first_last(panel_periods)
        panel_metrics = combo.get("metrics", set())
        derived_combo = derived_combo_stats.get(combo_key, {})
        derived_periods = sorted(derived_combo.get("periods", set()))
        derived_first_period, derived_last_period = first_last(derived_periods)
        derived_modes = derived_combo.get("modes", set())
        filing_period_list = sorted(filing_periods.get(service_key, set()))
        filing_first_period, filing_last_period = first_last(filing_period_list)
        firm_panel_period_list = sorted(firm_panel_periods.get(firm_key, set()))
        firm_panel_first, firm_panel_last = first_last(firm_panel_period_list)
        firm_filing_period_list = sorted(firm_filing_periods.get(firm_key, set()))
        firm_filing_first, firm_filing_last = first_last(firm_filing_period_list)

        service_dict_row = service_lookup.get(service_std)
        service_in_dictionary = service_dict_row is not None
        parent_match = service_in_dictionary and service_dict_row["parent_firm_std"] == firm_std
        sector_match = service_in_dictionary and service_dict_row["sector_std"] == sector_std
        service_code_consistent = service_in_dictionary and parent_match and sector_match

        observed_expected_country = combo_key in combo_stats
        panel_period_count = len(panel_periods)
        derived_period_count = len(derived_periods)
        minimum_required = config["minimum_required_periods"]
        service_analysis_ready = observed_expected_country and service_code_consistent and panel_period_count >= minimum_required
        derived_analysis_ready = service_code_consistent and derived_period_count >= minimum_required
        effective_analysis_ready = service_analysis_ready or derived_analysis_ready
        filing_linkage = service_key in filing_periods
        filing_linked_ready = service_analysis_ready and filing_linkage
        effective_filing_linked_ready = effective_analysis_ready and filing_linkage

        blocking_issue = []
        linkage_issue = []
        if not service_in_dictionary:
            blocking_issue.append("service_code_not_in_dictionary")
        if service_in_dictionary and not parent_match:
            blocking_issue.append("service_parent_mismatch")
        if service_in_dictionary and not sector_match:
            blocking_issue.append("service_sector_mismatch")
        if not observed_expected_country and not derived_analysis_ready:
            if observed_countries:
                blocking_issue.append("observed_elsewhere_only")
            else:
                blocking_issue.append("no_panel_observation")
        if observed_expected_country and panel_period_count < minimum_required:
            if effective_analysis_ready:
                linkage_issue.append("thin_direct_panel_covered_by_proxy")
            else:
                blocking_issue.append("insufficient_period_coverage")
        if not observed_expected_country and derived_analysis_ready:
            linkage_issue.append("derived_via_country_proxy_or_firm_bridge")
        if not filing_linkage:
            linkage_issue.append("no_filing_linkage")

        cell_status = "not_ready"
        if filing_linked_ready:
            cell_status = "ready_with_filing"
        elif service_analysis_ready:
            cell_status = "ready_service_only"
        elif effective_filing_linked_ready:
            cell_status = "ready_with_filing_via_country_proxy"
        elif effective_analysis_ready:
            cell_status = "ready_service_only_via_country_proxy"

        audit_row = {
            "audit_scope": "expected_matrix_cell",
            "sector_std": sector_std,
            "firm_std": firm_std,
            "service_std": service_std,
            "country_std": country_std,
            "tier": row["tier"],
            "coverage_expectation": row["coverage_expectation"],
            "target_data_types": row["target_data_types"],
            "matrix_notes": row["notes"],
            "service_in_dictionary_flag": to_bool_flag(service_in_dictionary),
            "service_parent_match_flag": to_bool_flag(parent_match),
            "service_sector_match_flag": to_bool_flag(sector_match),
            "service_code_consistency_flag": to_bool_flag(service_code_consistent),
            "expected_country_count_for_service": str(len(expected_countries)),
            "observed_country_count_for_service": str(len(observed_countries)),
            "matched_country_count_for_service": str(len(matched_countries)),
            "observed_expected_country_flag": to_bool_flag(observed_expected_country),
            "panel_source": config["panel_source"],
            "panel_row_count": str(combo.get("row_count", 0)),
            "panel_metric_count": str(len(panel_metrics)),
            "panel_metric_names": sort_join(panel_metrics),
            "panel_period_count": str(panel_period_count),
            "panel_first_period": panel_first_period,
            "panel_last_period": panel_last_period,
            "derived_panel_period_count": str(derived_period_count),
            "derived_panel_first_period": derived_first_period,
            "derived_panel_last_period": derived_last_period,
            "derived_mode_summary": sort_join(derived_modes),
            "firm_panel_period_count": str(len(firm_panel_period_list)),
            "firm_panel_first_period": firm_panel_first,
            "firm_panel_last_period": firm_panel_last,
            "filing_linkage_flag": to_bool_flag(filing_linkage),
            "filing_period_count": str(len(filing_period_list)),
            "filing_first_period": filing_first_period,
            "filing_last_period": filing_last_period,
            "firm_filing_period_count": str(len(firm_filing_period_list)),
            "firm_filing_first_period": firm_filing_first,
            "firm_filing_last_period": firm_filing_last,
            "minimum_required_periods": str(minimum_required),
            "minimum_rule": config["minimum_rule"],
            "service_analysis_ready_flag": to_bool_flag(service_analysis_ready),
            "derived_analysis_ready_flag": to_bool_flag(derived_analysis_ready),
            "effective_analysis_ready_flag": to_bool_flag(effective_analysis_ready),
            "filing_linked_ready_flag": to_bool_flag(filing_linked_ready),
            "effective_filing_linked_ready_flag": to_bool_flag(effective_filing_linked_ready),
            "cell_status": cell_status,
            "blocking_issue": "; ".join(blocking_issue),
            "linkage_issue": "; ".join(linkage_issue),
        }
        audit_rows.append(audit_row)

        sector_summary[sector_std]["expected_cells"] += 1
        if observed_expected_country:
            sector_summary[sector_std]["observed_cells"] += 1
        if effective_analysis_ready:
            sector_summary[sector_std]["service_ready_cells"] += 1
        if effective_filing_linked_ready:
            sector_summary[sector_std]["filing_linked_ready_cells"] += 1
        if service_code_consistent:
            sector_summary[sector_std]["consistent_code_cells"] += 1
        firm_summary[firm_key]["panel_periods"].update(firm_panel_period_list)
        firm_summary[firm_key]["filing_periods"].update(firm_filing_period_list)

    for anomaly in unexpected_observed:
        sector_std = anomaly["sector_std"]
        firm_std = anomaly["firm_std"]
        service_std = anomaly["service_std"]
        country_std = anomaly["country_std"]
        service_row = service_lookup.get(service_std)
        service_in_dictionary = service_row is not None
        parent_match = service_in_dictionary and service_row["parent_firm_std"] == firm_std
        sector_match = service_in_dictionary and service_row["sector_std"] == sector_std
        audit_rows.append(
            {
                "audit_scope": "observed_anomaly",
                "sector_std": sector_std,
                "firm_std": firm_std,
                "service_std": service_std,
                "country_std": country_std,
                "tier": "",
                "coverage_expectation": "",
                "target_data_types": "",
                "matrix_notes": "",
                "service_in_dictionary_flag": to_bool_flag(service_in_dictionary),
                "service_parent_match_flag": to_bool_flag(parent_match),
                "service_sector_match_flag": to_bool_flag(sector_match),
                "service_code_consistency_flag": to_bool_flag(service_in_dictionary and parent_match and sector_match),
                "expected_country_count_for_service": "0",
                "observed_country_count_for_service": "1",
                "matched_country_count_for_service": "0",
                "observed_expected_country_flag": "no",
                "panel_source": anomaly["panel_source"],
                "panel_row_count": str(anomaly["panel_row_count"]),
                "panel_metric_count": str(len(anomaly["panel_metric_names"].split("; ")) if anomaly["panel_metric_names"] else 0),
                "panel_metric_names": anomaly["panel_metric_names"],
                "panel_period_count": str(anomaly["panel_period_count"]),
                "panel_first_period": anomaly["panel_first_period"],
                "panel_last_period": anomaly["panel_last_period"],
                "derived_panel_period_count": "0",
                "derived_panel_first_period": "",
                "derived_panel_last_period": "",
                "derived_mode_summary": "",
                "firm_panel_period_count": "",
                "firm_panel_first_period": "",
                "firm_panel_last_period": "",
                "filing_linkage_flag": "no",
                "filing_period_count": "0",
                "filing_first_period": "",
                "filing_last_period": "",
                "firm_filing_period_count": "0",
                "firm_filing_first_period": "",
                "firm_filing_last_period": "",
                "minimum_required_periods": "",
                "minimum_rule": "",
                "service_analysis_ready_flag": "no",
                "derived_analysis_ready_flag": "no",
                "effective_analysis_ready_flag": "no",
                "filing_linked_ready_flag": "no",
                "effective_filing_linked_ready_flag": "no",
                "cell_status": "observed_outside_matrix",
                "blocking_issue": anomaly["anomaly_reason"],
                "linkage_issue": "not_in_expected_matrix_cell",
            }
        )

    fieldnames = [
        "audit_scope",
        "sector_std",
        "firm_std",
        "service_std",
        "country_std",
        "tier",
        "coverage_expectation",
        "target_data_types",
        "matrix_notes",
        "service_in_dictionary_flag",
        "service_parent_match_flag",
        "service_sector_match_flag",
        "service_code_consistency_flag",
        "expected_country_count_for_service",
        "observed_country_count_for_service",
        "matched_country_count_for_service",
        "observed_expected_country_flag",
        "panel_source",
        "panel_row_count",
        "panel_metric_count",
        "panel_metric_names",
        "panel_period_count",
        "panel_first_period",
        "panel_last_period",
        "derived_panel_period_count",
        "derived_panel_first_period",
        "derived_panel_last_period",
        "derived_mode_summary",
        "firm_panel_period_count",
        "firm_panel_first_period",
        "firm_panel_last_period",
        "filing_linkage_flag",
        "filing_period_count",
        "filing_first_period",
        "filing_last_period",
        "firm_filing_period_count",
        "firm_filing_first_period",
        "firm_filing_last_period",
        "minimum_required_periods",
        "minimum_rule",
        "service_analysis_ready_flag",
        "derived_analysis_ready_flag",
        "effective_analysis_ready_flag",
        "filing_linked_ready_flag",
        "effective_filing_linked_ready_flag",
        "cell_status",
        "blocking_issue",
        "linkage_issue",
    ]
    write_csv(AUDIT_PATH, audit_rows, fieldnames)

    return audit_rows, sector_summary, firm_summary, unexpected_observed, aggregate_issues


def build_markdown(audit_rows, sector_summary, firm_summary, unexpected_observed, aggregate_issues):
    expected_rows = [row for row in audit_rows if row["audit_scope"] == "expected_matrix_cell"]
    anomaly_rows = [row for row in audit_rows if row["audit_scope"] == "observed_anomaly"]

    lines = [
        "# Firm-Service Coverage Audit",
        "",
        f"- access_date: `{ACCESS_DATE}`",
        f"- prompt: `{PROMPT_NAME}`",
        f"- expected_matrix_cells: `{len(expected_rows)}`",
        f"- observed_anomaly_cells: `{len(anomaly_rows)}`",
        "",
        "## Sector Summary",
        "",
        "| sector_std | expected_cells | observed_cells | service_ready_cells | filing_linked_ready_cells | minimum_ready_target | target_met |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]

    for sector_std in ["music", "webtoon_story", "digital_infra"]:
        summary = sector_summary[sector_std]
        service_ready = summary["service_ready_cells"]
        target = MINIMUM_READY_TARGETS[sector_std]
        target_met = "yes" if service_ready >= target else "no"
        lines.append(
            f"| {sector_std} | {summary['expected_cells']} | {summary['observed_cells']} | {service_ready} | {summary['filing_linked_ready_cells']} | {target} | {target_met} |"
        )

    lines.extend(
        [
            "",
            "## Firm Period Coverage",
            "",
            "| sector_std | firm_std | panel_period_count | panel_first_period | panel_last_period | filing_period_count | filing_first_period | filing_last_period |",
            "| --- | --- | ---: | --- | --- | ---: | --- | --- |",
        ]
    )

    for (sector_std, firm_std) in sorted(firm_summary):
        panel_periods = sorted(firm_summary[(sector_std, firm_std)]["panel_periods"])
        filing_periods = sorted(firm_summary[(sector_std, firm_std)]["filing_periods"])
        panel_first, panel_last = first_last(panel_periods)
        filing_first, filing_last = first_last(filing_periods)
        lines.append(
            f"| {sector_std} | {firm_std} | {len(panel_periods)} | {panel_first} | {panel_last} | {len(filing_periods)} | {filing_first} | {filing_last} |"
        )

    lines.extend(
        [
            "",
            "## Service-Code Consistency Findings",
            "",
            f"- dictionary service count: `{len(read_csv(SERVICE_DICT_PATH))}`",
        ]
    )

    if unexpected_observed:
        lines.extend(
            [
                "- observed anomalies requiring follow-up:",
                "",
                "| sector_std | firm_std | service_std | country_std | anomaly_reason | panel_period_count |",
                "| --- | --- | --- | --- | --- | ---: |",
            ]
        )
        for row in sorted(
            unexpected_observed,
            key=lambda item: (item["sector_std"], item["firm_std"], item["service_std"], item["country_std"]),
        ):
            lines.append(
                f"| {row['sector_std']} | {row['firm_std']} | {row['service_std']} | {row['country_std']} | {row['anomaly_reason']} | {row['panel_period_count']} |"
            )
    else:
        lines.append("- unexpected observed service codes or out-of-matrix cells: none")

    lines.extend(["", "## Aggregate Rows Excluded From Firm-Service Counts", ""])
    if aggregate_issues:
        lines.extend(
            [
                "| sector_std | country_std | metric_name | excluded_row_count | note |",
                "| --- | --- | --- | ---: | --- |",
            ]
        )
        for key in sorted(aggregate_issues):
            sector_std, country_std, metric_name = key
            lines.append(
                f"| {sector_std} | {country_std} | {metric_name} | {aggregate_issues[key]} | aggregate metric without stable firm/service code |"
            )
    else:
        lines.append("- none")

    no_filing_rows = [row for row in expected_rows if row["filing_linkage_flag"] == "no"]
    not_ready_rows = [row for row in expected_rows if row["service_analysis_ready_flag"] == "no"]
    ready_with_filing_rows = [row for row in expected_rows if row["filing_linked_ready_flag"] == "yes"]

    lines.extend(
        [
            "",
            "## Audit Verdict",
            "",
            f"- service-analysis ready cells: `{sum(1 for row in expected_rows if row['service_analysis_ready_flag'] == 'yes')}`",
            f"- filing-linked ready cells: `{len(ready_with_filing_rows)}`",
            f"- expected cells with no filing linkage: `{len(no_filing_rows)}`",
            f"- expected cells not ready for next analysis: `{len(not_ready_rows)}`",
        ]
    )

    sector_not_ready = defaultdict(int)
    for row in not_ready_rows:
        sector_not_ready[row["sector_std"]] += 1
    lines.append(
        "- sector-level not-ready counts: "
        + ", ".join(f"`{sector}` {count}" for sector, count in sorted(sector_not_ready.items()))
    )

    lines.extend(
        [
            "",
            "### Main Follow-Ups",
            "",
            "- `music`: 글로벌 국가 확장 전에는 한국 월별 서비스 셀 위주로만 안정적 분석이 가능하다. `youtube_music`와 `warner_music` 한국 셀은 표준 사전과 운영 매트릭스에 정렬되었고, 이제 `jyp_music_ip`, `qq_music`의 직접 관측 보강이 다음 과제다.",
            "- `webtoon_story`: 현재는 `kakao_page`, `piccoma`, `naver_webtoon`, `webtoon` 4개 셀만 즉시 사용 가능하다. `bookwalker`, `lezhin_comics`, `ridi`는 storefront 구조 복원이 더 필요하다.",
            "- `digital_infra`: `kt_network`, `lguplus_network`, `skt_network`, `netflix`, `youtube`, `cloudflare_cdn`은 바로 비교 가능하지만 `aws`, `akamai_cdn`은 서비스-country raw가 비어 있다.",
            "- 공시 연결은 서비스-level 분석의 필수조건은 아니지만, 재무-서비스 결합 분석에서는 `kakao_ent`, `kakao_piccoma`, `ridi` 같은 비공시 기업이 별도 제한으로 남는다.",
            "",
        ]
    )

    LOG_PATH.write_text("\n".join(lines), encoding="utf-8")


def update_project_manifest():
    new_rows = [
        {
            "artifact_type": "script",
            "path": "scripts/build_firm_service_coverage_audit.py",
            "owner_step": PROMPT_NAME,
            "source_type": "local_code",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Builds firm-service coverage audit from matrix, service dictionary, filings, and service panels.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/processed/firm_service_coverage_audit.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_audit",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Expected-cell coverage audit with panel periods, service-code checks, and filing linkage flags.",
        },
        {
            "artifact_type": "log",
            "path": "logs/firm_service_audit.md",
            "owner_step": PROMPT_NAME,
            "source_type": "local_log",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Coverage-audit summary for firm-service cells, anomalies, and minimum-ready verdicts.",
        },
    ]
    append_unique_rows(PROJECT_MANIFEST_PATH, PROJECT_MANIFEST_FIELDS, new_rows, ["path"])


def update_workflow_log(audit_rows, unexpected_observed, aggregate_issues):
    expected_rows = [row for row in audit_rows if row["audit_scope"] == "expected_matrix_cell"]
    service_ready = sum(1 for row in expected_rows if row["service_analysis_ready_flag"] == "yes")
    filing_ready = sum(1 for row in expected_rows if row["filing_linked_ready_flag"] == "yes")
    bullets = [
        f"`data/processed/firm_service_coverage_audit.csv` 생성, 기대 셀 `{len(expected_rows)}`건과 anomaly 셀 `{len(unexpected_observed)}`건 감사 완료",
        f"서비스 분석 ready 셀 `{service_ready}`건, filing-linked ready 셀 `{filing_ready}`건으로 판정",
        f"서비스 코드 anomaly `{len(unexpected_observed)}`건과 aggregate 제외 row `{sum(aggregate_issues.values())}`건을 별도 기록",
        "`logs/firm_service_audit.md`에 섹터별 최소 셀 수 충족 여부와 후속 보강 필요 항목 정리",
    ]
    append_workflow_section(WORKFLOW_LOG_PATH, "Exec Prompt 18. 기업·서비스 수준 수집 검증", bullets)


def main():
    audit_rows, sector_summary, firm_summary, unexpected_observed, aggregate_issues = build_audit_rows()
    build_markdown(audit_rows, sector_summary, firm_summary, unexpected_observed, aggregate_issues)
    update_project_manifest()
    update_workflow_log(audit_rows, unexpected_observed, aggregate_issues)


if __name__ == "__main__":
    main()
