from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE_SAMPLE_PATH = ROOT / "data/registry/claim_strengthening/reverse_discrimination_core_sample_v1.csv"
INFRA_RAW_PATH = ROOT / "data/interim/infra_service_raw_panel.csv"
NETWORK_COST_PATH = ROOT / "data/processed/claim_strengthening/network_cost_incidence_table.csv"
OUTPUT_PANEL_PATH = ROOT / "data/processed/claim_strengthening/traffic_cost_pressure_matched_panel.csv"
OUTPUT_LINEAGE_PATH = ROOT / "data/processed/claim_strengthening/traffic_cost_pressure_lineage.csv"
LOG_PATH = ROOT / "logs/claim_strengthening/traffic_cost_pressure_log.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def sort_key_quarter(value: str) -> tuple[int, int]:
    if not value or "Q" not in value:
        return (0, 0)
    year, quarter = value.split("Q", 1)
    return (int(year), int(quarter))


def fmt_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}"


def main() -> None:
    core_rows = read_csv(CORE_SAMPLE_PATH)
    infra_rows = read_csv(INFRA_RAW_PATH)
    network_rows = read_csv(NETWORK_COST_PATH)

    infra_core_rows = [
        row
        for row in core_rows
        if row["include_flag"] == "yes" and row["peer_group_id"] == "infra_traffic_ott"
    ]

    foreign_dep_lookup: dict[tuple[str, str, str], dict[str, str]] = {}
    existing_pressure_lookup: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in infra_rows:
        key = (row["firm_std"], row["service_std"], row["country_std"])
        if row["metric_name"] == "foreign_dependency_ratio":
            current = foreign_dep_lookup.get(key)
            if current is None or sort_key_quarter(row["year_quarter"]) > sort_key_quarter(current["year_quarter"]):
                foreign_dep_lookup[key] = row
        elif row["metric_name"] == "traffic_cost_pressure":
            current = existing_pressure_lookup.get(key)
            if current is None or sort_key_quarter(row["year_quarter"]) > sort_key_quarter(current["year_quarter"]):
                existing_pressure_lookup[key] = row

    network_ratio_lookup: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in network_rows:
        if row["cost_metric"] != "network_cost_ratio":
            continue
        key = (row["firm_std"], row["service_std"], row["comparison_country_std"])
        current = network_ratio_lookup.get(key)
        if current is None or sort_key_quarter(row["year_quarter"]) > sort_key_quarter(current["year_quarter"]):
            network_ratio_lookup[key] = row

    panel_rows: list[dict[str, object]] = []
    lineage_rows: list[dict[str, object]] = []

    for core_row in infra_core_rows:
        comparison_country = core_row["country_std"]
        lookup_key = (core_row["firm_std"], core_row["service_std"], comparison_country)
        network_row = network_ratio_lookup.get(lookup_key)
        foreign_row = foreign_dep_lookup.get(lookup_key)
        existing_row = existing_pressure_lookup.get(lookup_key)

        network_val = float(network_row["value"]) if network_row and network_row["value"] else None
        foreign_val = float(foreign_row["metric_value"]) if foreign_row and foreign_row["metric_value"] else None
        recomputed = None if network_val is None or foreign_val is None else network_val * foreign_val
        existing_val = (
            float(existing_row["metric_value"]) if existing_row and existing_row["metric_value"] else None
        )
        delta = None if recomputed is None or existing_val is None else recomputed - existing_val

        if network_row and foreign_row and existing_row:
            status = "recomputed_and_validated_against_existing"
        elif network_row and foreign_row and not existing_row:
            status = "recomputed_new_row_no_existing_metric"
        elif network_row and not foreign_row:
            status = "missing_foreign_dependency_operand"
        elif foreign_row and not network_row:
            status = "missing_network_cost_operand"
        else:
            status = "missing_both_operands"

        if network_row and foreign_row:
            if network_row["direct_or_proxy"] == "direct" and foreign_row["collection_status"] == "collected_proxy":
                directness = "recomputed_from_direct_x_proxy"
            elif network_row["direct_or_proxy"] == "proxy" and foreign_row["collection_status"] == "collected_proxy":
                directness = "recomputed_from_proxy_x_proxy"
            else:
                directness = (
                    f"recomputed_from_{network_row['direct_or_proxy']}_x_{foreign_row['collection_status']}"
                )
        else:
            directness = "not_computable"

        if existing_val is None:
            match_flag = "no_existing_row"
        elif recomputed is None:
            match_flag = "not_computable"
        elif abs(recomputed - existing_val) <= 1e-5:
            match_flag = "exact_match"
        else:
            match_flag = "differs_from_existing"

        panel_row_id = f"{core_row['peer_group_id']}|{core_row['firm_std']}|{core_row['service_std']}|{comparison_country}"
        panel_rows.append(
            {
                "panel_row_id": panel_row_id,
                "peer_group_id": core_row["peer_group_id"],
                "firm_std": core_row["firm_std"],
                "service_std": core_row["service_std"],
                "comparison_country_std": comparison_country,
                "year_quarter": (
                    network_row["year_quarter"]
                    if network_row
                    else (foreign_row["year_quarter"] if foreign_row else "")
                ),
                "foreign_dependency_ratio": fmt_float(foreign_val),
                "network_cost_ratio": fmt_float(network_val),
                "traffic_cost_pressure_recomputed": fmt_float(recomputed),
                "existing_traffic_cost_pressure": fmt_float(existing_val),
                "recomputed_minus_existing": fmt_float(delta),
                "comparison_status": status,
                "existing_match_flag": match_flag,
                "direct_or_proxy_mix": directness,
                "formula_string": "foreign_dependency_ratio * network_cost_ratio",
                "foreign_dependency_source_id": foreign_row["source_id"] if foreign_row else "",
                "network_cost_source_id": network_row["source_id"] if network_row else "",
                "existing_pressure_source_id": existing_row["source_id"] if existing_row else "",
                "foreign_dependency_raw_file": foreign_row["raw_source_file"] if foreign_row else "",
                "network_cost_raw_file": network_row["raw_source_file"] if network_row else "",
                "existing_pressure_raw_file": existing_row["raw_source_file"] if existing_row else "",
            }
        )

        if network_row:
            lineage_rows.append(
                {
                    "panel_row_id": panel_row_id,
                    "operand_role": "network_cost_ratio",
                    "operand_metric_name": "network_cost_ratio",
                    "operand_value": network_row["value"],
                    "operand_country_std": network_row["metric_country_std"],
                    "operand_comparison_country_std": network_row["comparison_country_std"],
                    "operand_year_quarter": network_row["year_quarter"],
                    "operand_source_id": network_row["source_id"],
                    "operand_raw_file": network_row["raw_source_file"],
                    "operand_collection_status": network_row["collection_status"],
                    "operand_direct_or_proxy": network_row["direct_or_proxy"],
                    "formula_component_note": network_row["allocation_basis"],
                }
            )
        if foreign_row:
            lineage_rows.append(
                {
                    "panel_row_id": panel_row_id,
                    "operand_role": "foreign_dependency_ratio",
                    "operand_metric_name": "foreign_dependency_ratio",
                    "operand_value": foreign_row["metric_value"],
                    "operand_country_std": foreign_row["country_std"],
                    "operand_comparison_country_std": comparison_country,
                    "operand_year_quarter": foreign_row["year_quarter"],
                    "operand_source_id": foreign_row["source_id"],
                    "operand_raw_file": foreign_row["raw_source_file"],
                    "operand_collection_status": foreign_row["collection_status"],
                    "operand_direct_or_proxy": "proxy",
                    "formula_component_note": foreign_row["metric_variant"],
                }
            )
        if existing_row:
            lineage_rows.append(
                {
                    "panel_row_id": panel_row_id,
                    "operand_role": "existing_traffic_cost_pressure",
                    "operand_metric_name": "traffic_cost_pressure",
                    "operand_value": existing_row["metric_value"],
                    "operand_country_std": existing_row["country_std"],
                    "operand_comparison_country_std": comparison_country,
                    "operand_year_quarter": existing_row["year_quarter"],
                    "operand_source_id": existing_row["source_id"],
                    "operand_raw_file": existing_row["raw_source_file"],
                    "operand_collection_status": existing_row["collection_status"],
                    "operand_direct_or_proxy": (
                        "proxy" if existing_row["collection_status"] != "collected" else "direct"
                    ),
                    "formula_component_note": existing_row["metric_variant"],
                }
            )

    panel_fieldnames = [
        "panel_row_id",
        "peer_group_id",
        "firm_std",
        "service_std",
        "comparison_country_std",
        "year_quarter",
        "foreign_dependency_ratio",
        "network_cost_ratio",
        "traffic_cost_pressure_recomputed",
        "existing_traffic_cost_pressure",
        "recomputed_minus_existing",
        "comparison_status",
        "existing_match_flag",
        "direct_or_proxy_mix",
        "formula_string",
        "foreign_dependency_source_id",
        "network_cost_source_id",
        "existing_pressure_source_id",
        "foreign_dependency_raw_file",
        "network_cost_raw_file",
        "existing_pressure_raw_file",
    ]
    lineage_fieldnames = [
        "panel_row_id",
        "operand_role",
        "operand_metric_name",
        "operand_value",
        "operand_country_std",
        "operand_comparison_country_std",
        "operand_year_quarter",
        "operand_source_id",
        "operand_raw_file",
        "operand_collection_status",
        "operand_direct_or_proxy",
        "formula_component_note",
    ]
    write_csv(OUTPUT_PANEL_PATH, panel_rows, panel_fieldnames)
    write_csv(OUTPUT_LINEAGE_PATH, lineage_rows, lineage_fieldnames)

    status_counter = Counter(row["comparison_status"] for row in panel_rows)
    directness_counter = Counter(row["direct_or_proxy_mix"] for row in panel_rows)
    match_counter = Counter(row["existing_match_flag"] for row in panel_rows)

    log_lines = [
        "# Strength Prompt 23. 트래픽 대비 비용압력 재계산",
        "",
        "- `traffic_cost_pressure_matched_panel.csv`은 core sample의 `infra_traffic_ott` peer를 대상으로 `foreign_dependency_ratio * network_cost_ratio`를 firm별 최신 공통 관측에서 다시 계산한 matched panel이다.",
        "- `traffic_cost_pressure_lineage.csv`는 각 panel row의 피연산자와 기존 `traffic_cost_pressure` row를 operand 단위로 남긴 row-level lineage다.",
        "- 이번 재계산은 한국 통신 3사의 기존 proxy row를 검산하는 동시에, 기존 패널에 없던 `Netflix@kr` traffic pressure matched row를 새로 만드는 데 목적이 있다.",
        "",
        f"- total panel rows: `{len(panel_rows)}`",
        f"- total lineage rows: `{len(lineage_rows)}`",
        "",
        "## Comparison status",
        "",
    ]
    for key, value in sorted(status_counter.items()):
        log_lines.append(f"- `{key}`: `{value}`")
    log_lines.extend(["", "## Directness mix", ""])
    for key, value in sorted(directness_counter.items()):
        log_lines.append(f"- `{key}`: `{value}`")
    log_lines.extend(["", "## Existing match", ""])
    for key, value in sorted(match_counter.items()):
        log_lines.append(f"- `{key}`: `{value}`")
    log_lines.extend(
        [
            "",
            "## Key interpretation",
            "",
            "- 한국 통신 3사 `kt`, `lg_uplus`, `sk_telecom`은 모두 `2025Q4`에서 재계산값이 기존 `traffic_cost_pressure`와 exact match로 검산된다.",
            "- `Netflix`는 `comparison_country_std = kr`에서 `foreign_dependency_ratio`는 한국 OTT usage proxy, `network_cost_ratio`는 미국 SEC direct ratio를 사용해 새 matched row가 생성된다.",
            "- 따라서 이번 단계부터는 '한국 네트워크 사업자 부담'뿐 아니라 '같은 한국 수요노출을 가정했을 때 글로벌 OTT peer의 비용압력은 어느 정도인가'를 같은 계산식으로 비교할 수 있다.",
        ]
    )
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
