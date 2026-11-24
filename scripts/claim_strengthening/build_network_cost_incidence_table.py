from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CORE_SAMPLE_PATH = (
    PROJECT_ROOT
    / "data/registry/claim_strengthening/reverse_discrimination_core_sample_v1.csv"
)
INFRA_PANEL_PATH = PROJECT_ROOT / "data/interim/infra_service_raw_panel.csv"
OUTPUT_PATH = (
    PROJECT_ROOT / "data/processed/claim_strengthening/network_cost_incidence_table.csv"
)
LOG_PATH = (
    PROJECT_ROOT / "logs/claim_strengthening/network_cost_incidence_log.md"
)

METRIC_PRIORITY = {
    "network_cost_ratio",
    "domestic_infra_capex_ratio",
    "outflow_to_capex_ratio",
    "traffic_cost_pressure",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def quarter_sort_key(value: str) -> tuple[int, int]:
    year = int(value[:4])
    quarter = int(value[-1])
    return (year, quarter)


def direct_or_proxy(status: str) -> str:
    return "direct" if status == "collected" else "proxy"


def allocation_basis(metric_name: str, status: str) -> str:
    is_direct = direct_or_proxy(status) == "direct"
    if metric_name == "network_cost_ratio":
        return (
            "service_level_sec_cost_to_revenue"
            if is_direct
            else "company_opex_to_revenue_proxy_assigned_to_network_service"
        )
    if metric_name == "domestic_infra_capex_ratio":
        return (
            "service_level_sec_capex_to_revenue"
            if is_direct
            else "company_capex_proxy_to_revenue_assigned_to_network_service"
        )
    if metric_name == "outflow_to_capex_ratio":
        return (
            "service_level_sec_outflow_to_capex"
            if is_direct
            else "company_opex_to_capex_proxy_assigned_to_network_service"
        )
    if metric_name == "traffic_cost_pressure":
        return "country_ott_usage_proxy_x_network_cost_ratio"
    return "other"


def main() -> None:
    core_rows = [row for row in read_csv(CORE_SAMPLE_PATH) if row["include_flag"] == "yes"]
    infra_rows = read_csv(INFRA_PANEL_PATH)

    core_infra = [
        row for row in core_rows if row["peer_group_id"].startswith("infra_")
    ]
    core_key_map = {
        (row["peer_group_id"], row["firm_std"], row["service_std"]): row
        for row in core_infra
    }

    selected_candidates: dict[tuple[str, str, str, str], dict[str, str]] = {}

    for row in infra_rows:
        metric_name = row["metric_name"]
        if metric_name not in METRIC_PRIORITY:
            continue

        matching_keys = [
            key
            for key in core_key_map
            if key[1] == row["firm_std"] and key[2] == row["service_std"]
        ]
        for key in matching_keys:
            selection_key = (key[0], key[1], key[2], metric_name)
            existing = selected_candidates.get(selection_key)
            if existing is None or quarter_sort_key(row["year_quarter"]) > quarter_sort_key(
                existing["year_quarter"]
            ):
                selected_candidates[selection_key] = row

    output_rows: list[dict[str, str]] = []

    for selection_key, row in sorted(selected_candidates.items()):
        peer_group_id, firm_std, service_std, metric_name = selection_key
        core_row = core_key_map[(peer_group_id, firm_std, service_std)]
        status = row["collection_status"]
        output_rows.append(
            {
                "peer_group_id": peer_group_id,
                "firm_std": firm_std,
                "cost_metric": metric_name,
                "value": row["metric_value"],
                "allocation_basis": allocation_basis(metric_name, status),
                "direct_or_proxy": direct_or_proxy(status),
                "service_std": service_std,
                "comparison_country_std": core_row["country_std"],
                "metric_country_std": row["country_std"],
                "year_quarter": row["year_quarter"],
                "metric_unit": row["metric_unit"],
                "source_id": row["source_id"],
                "raw_source_file": row["raw_source_file"],
                "collection_status": status,
                "notes": row["notes"],
            }
        )

    fieldnames = [
        "peer_group_id",
        "firm_std",
        "cost_metric",
        "value",
        "allocation_basis",
        "direct_or_proxy",
        "service_std",
        "comparison_country_std",
        "metric_country_std",
        "year_quarter",
        "metric_unit",
        "source_id",
        "raw_source_file",
        "collection_status",
        "notes",
    ]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    metric_counter = Counter(row["cost_metric"] for row in output_rows)
    direct_counter = Counter(row["direct_or_proxy"] for row in output_rows)
    peer_counter = Counter(row["peer_group_id"] for row in output_rows)

    log_lines = [
        "# Strength Prompt 22. 망 비용 귀속 테이블 작성",
        "",
        "- `network_cost_incidence_table.csv`는 core sample 중 infra peer만 남긴 뒤 `infra_service_raw_panel.csv`에서 비용 관련 metric의 최신 관측 1개씩을 뽑아 만든 peer-level 비용 귀속표다.",
        "- 현재 core sample에서 비용 귀속을 직접 비교할 수 있는 그룹은 `infra_traffic_ott`뿐이라 결과도 해당 peer에 집중된다.",
        "- 한국 통신 3사는 `OpenDART` 기반 company-level proxy, `Netflix`는 `SEC` 기반 service-level direct metric이 최신 관측으로 선택됐다.",
        "- `foreign_dependency_ratio`는 노출 측 지표라 이번 표에서는 제외했고, 다음 `traffic_cost_pressure` 재계산 단계에서 따로 다룬다.",
        "",
        f"- total rows: `{len(output_rows)}`",
        "",
        "## Direct vs Proxy",
        "",
    ]

    for key in sorted(direct_counter):
        log_lines.append(f"- `{key}`: `{direct_counter[key]}`")

    log_lines.extend(["", "## Metric coverage", ""])
    for key in sorted(metric_counter):
        log_lines.append(f"- `{key}`: `{metric_counter[key]}`")

    log_lines.extend(["", "## Peer coverage", ""])
    for key in sorted(peer_counter):
        log_lines.append(f"- `{key}`: `{peer_counter[key]}`")

    log_lines.extend(
        [
            "",
            "## Key interpretation",
            "",
            "- 한국 통신 3사는 모두 `2025Q4` 기준 `network_cost_ratio`, `domestic_infra_capex_ratio`, `outflow_to_capex_ratio`, `traffic_cost_pressure`가 남는다.",
            "- `Netflix`는 `2025Q4` 기준 `network_cost_ratio`, `domestic_infra_capex_ratio`, `outflow_to_capex_ratio` direct row가 남지만 `traffic_cost_pressure`는 직접 관측이 없어 제외된다.",
            "- 따라서 현재 비용 귀속 비교는 '한국 통신 3사는 네트워크 부담을 직접 떠안는 구조가 보이고, 글로벌 OTT peer는 회사 재무 차원의 비용 부담은 보이지만 한국 네트워크 부담의 직접 귀속 row는 아직 없다'는 수준으로 읽는 것이 안전하다.",
        ]
    )

    LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
