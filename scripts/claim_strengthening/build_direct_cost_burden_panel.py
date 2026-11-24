from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE_SAMPLE_PATH = ROOT / "data/registry/claim_strengthening/reverse_discrimination_core_sample_v1.csv"
TAX_PATH = ROOT / "data/processed/claim_strengthening/matched_effective_tax_rate_panel.csv"
PARAFISCAL_PATH = ROOT / "data/processed/claim_strengthening/parafiscal_burden_table.csv"
NETWORK_PATH = ROOT / "data/processed/claim_strengthening/network_cost_incidence_table.csv"
PRESSURE_PATH = ROOT / "data/processed/claim_strengthening/traffic_cost_pressure_matched_panel.csv"
OUTPUT_PATH = ROOT / "data/processed/claim_strengthening/direct_cost_burden_panel.csv"
LOG_PATH = ROOT / "logs/claim_strengthening/direct_cost_burden_log.md"


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


def parse_fiscal_period(period: str) -> tuple[int, int]:
    if not period:
        return (0, 0)
    if period.startswith("FY"):
        return (int(period[2:]), 12)
    if "Q" in period:
        year, quarter = period.split("Q", 1)
        return (int(year), int(quarter) * 3)
    if "H" in period:
        year, half = period.split("H", 1)
        return (int(year), int(half) * 6)
    return (0, 0)


def fmt_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}"


def normalize_scores(rows: list[dict[str, object]], raw_field: str, score_field: str, status_field: str) -> None:
    by_peer: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for idx, row in enumerate(rows):
        raw_value = row.get(raw_field)
        if raw_value is None:
            continue
        by_peer[str(row["peer_group_id"])].append((idx, float(raw_value)))

    for peer_group_id, items in by_peer.items():
        values = [value for _, value in items]
        min_value = min(values)
        max_value = max(values)
        if max_value > min_value:
            for idx, value in items:
                rows[idx][score_field] = round(100.0 * (value - min_value) / (max_value - min_value), 6)
                rows[idx][status_field] = "peer_minmax_0_100"
        else:
            for idx, _ in items:
                rows[idx][score_field] = 0.0
                rows[idx][status_field] = "peer_no_variation_zero_score"


def main() -> None:
    core_rows = [row for row in read_csv(CORE_SAMPLE_PATH) if row["include_flag"] == "yes"]
    tax_rows = read_csv(TAX_PATH)
    para_rows = read_csv(PARAFISCAL_PATH)
    network_rows = read_csv(NETWORK_PATH)
    pressure_rows = read_csv(PRESSURE_PATH)

    tax_lookup: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in tax_rows:
        if row["comparability_flag"] != "yes":
            continue
        key = (row["peer_group_id"], row["firm_std"], row["country_std"])
        current = tax_lookup.get(key)
        if current is None or parse_fiscal_period(row["fiscal_period"]) > parse_fiscal_period(current["fiscal_period"]):
            tax_lookup[key] = row

    para_lookup: dict[tuple[str, str, str], dict[str, object]] = {}
    grouped_para: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in para_rows:
        grouped_para[(row["peer_group_id"], row["firm_std"], row["comparison_country_std"])].append(row)
    for key, rows_for_key in grouped_para.items():
        numeric_scores = [float(r["burden_score"]) for r in rows_for_key if r["burden_score"] != ""]
        para_lookup[key] = {
            "raw_value": sum(numeric_scores) if numeric_scores else None,
            "row_count": len(rows_for_key),
            "numeric_count": len(numeric_scores),
            "mandatory_yes_count": sum(1 for r in rows_for_key if r["mandatory_flag"] == "yes"),
            "note": "numeric_burden_score_sum" if numeric_scores else "no_numeric_burden_score",
        }

    network_metric_lookup: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in network_rows:
        if row["cost_metric"] != "domestic_infra_capex_ratio":
            continue
        network_metric_lookup[(row["peer_group_id"], row["firm_std"], row["comparison_country_std"])] = row

    pressure_lookup: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in pressure_rows:
        pressure_lookup[(row["peer_group_id"], row["firm_std"], row["comparison_country_std"])] = row

    output_rows: list[dict[str, object]] = []
    for core_row in core_rows:
        key = (core_row["peer_group_id"], core_row["firm_std"], core_row["country_std"])
        tax_row = tax_lookup.get(key)
        para_info = para_lookup.get(key)
        pressure_row = pressure_lookup.get(key)
        infra_row = network_metric_lookup.get(key)

        tax_raw = float(tax_row["effective_tax_rate"]) if tax_row else None
        para_raw = para_info["raw_value"] if para_info and para_info["raw_value"] is not None else None
        network_raw = float(pressure_row["traffic_cost_pressure_recomputed"]) if pressure_row else None
        infra_raw = float(infra_row["value"]) if infra_row else None

        row: dict[str, object] = {
            "peer_group_id": core_row["peer_group_id"],
            "firm_std": core_row["firm_std"],
            "country_std": core_row["country_std"],
            "service_std": core_row["service_std"],
            "analysis_role": core_row["analysis_role"],
            "tax_burden_score": None,
            "parafiscal_burden_score": None,
            "network_cost_score": None,
            "infra_cost_score": None,
            "total_direct_burden_score": None,
            "tax_raw_value": tax_raw,
            "tax_basis_period": tax_row["fiscal_period"] if tax_row else "",
            "tax_score_status": "matched_latest_comparable_period" if tax_row else "no_comparable_tax_row",
            "parafiscal_raw_value": para_raw,
            "parafiscal_score_status": (
                "numeric_parafiscal_signal_present"
                if para_raw is not None
                else (
                    "direct_rows_exist_but_no_numeric_signal"
                    if para_info and para_info["row_count"] > 0
                    else "no_direct_parafiscal_rows"
                )
            ),
            "parafiscal_row_count": para_info["row_count"] if para_info else 0,
            "parafiscal_numeric_count": para_info["numeric_count"] if para_info else 0,
            "network_raw_value": network_raw,
            "network_score_status": "matched_pressure_recomputed" if pressure_row else "no_matched_network_pressure_row",
            "network_basis_period": pressure_row["year_quarter"] if pressure_row else "",
            "infra_raw_value": infra_raw,
            "infra_score_status": "latest_domestic_infra_capex_ratio" if infra_row else "no_infra_capex_row",
            "infra_basis_period": infra_row["year_quarter"] if infra_row else "",
        }
        output_rows.append(row)

    normalize_scores(output_rows, "tax_raw_value", "tax_burden_score", "tax_score_status")
    normalize_scores(
        output_rows, "parafiscal_raw_value", "parafiscal_burden_score", "parafiscal_score_status"
    )
    normalize_scores(output_rows, "network_raw_value", "network_cost_score", "network_score_status")
    normalize_scores(output_rows, "infra_raw_value", "infra_cost_score", "infra_score_status")

    rank_groups: dict[str, list[tuple[int, float]]] = defaultdict(list)
    coverage_counter = Counter()
    for idx, row in enumerate(output_rows):
        observed_scores = []
        for field in [
            "tax_burden_score",
            "parafiscal_burden_score",
            "network_cost_score",
            "infra_cost_score",
        ]:
            if row[field] is not None:
                observed_scores.append(float(row[field]))

        observed_count = len(observed_scores)
        row["observed_component_count"] = observed_count
        if observed_count >= 2:
            row["total_direct_burden_score"] = round(sum(observed_scores) / observed_count, 6)
            row["total_score_status"] = "mean_of_observed_component_scores"
            rank_groups[str(row["peer_group_id"])].append((idx, float(row["total_direct_burden_score"])))
        elif observed_count == 1:
            row["total_score_status"] = "suppressed_single_component_only"
        else:
            row["total_score_status"] = "suppressed_no_observed_component"

        if observed_count >= 3:
            coverage_label = "stronger_direct_cost_coverage"
        elif observed_count == 2:
            coverage_label = "partial_direct_cost_coverage"
        elif observed_count == 1:
            coverage_label = "thin_direct_cost_coverage"
        else:
            coverage_label = "no_direct_cost_coverage"
        row["coverage_status"] = coverage_label
        coverage_counter[coverage_label] += 1

    for peer_group_id, items in rank_groups.items():
        sorted_items = sorted(items, key=lambda x: x[1], reverse=True)
        rank = 0
        last_value = None
        for position, (idx, value) in enumerate(sorted_items, start=1):
            if last_value is None or value != last_value:
                rank = position
                last_value = value
            output_rows[idx]["total_rank_within_peer"] = rank

    fieldnames = [
        "peer_group_id",
        "firm_std",
        "country_std",
        "tax_burden_score",
        "parafiscal_burden_score",
        "network_cost_score",
        "infra_cost_score",
        "total_direct_burden_score",
        "service_std",
        "analysis_role",
        "tax_raw_value",
        "tax_basis_period",
        "tax_score_status",
        "parafiscal_raw_value",
        "parafiscal_score_status",
        "parafiscal_row_count",
        "parafiscal_numeric_count",
        "network_raw_value",
        "network_basis_period",
        "network_score_status",
        "infra_raw_value",
        "infra_basis_period",
        "infra_score_status",
        "observed_component_count",
        "coverage_status",
        "total_score_status",
        "total_rank_within_peer",
    ]
    write_csv(OUTPUT_PATH, output_rows, fieldnames)

    total_rows = len(output_rows)
    total_scored = sum(1 for row in output_rows if row["total_direct_burden_score"] is not None)
    peer_counter = Counter(row["peer_group_id"] for row in output_rows)
    log_lines = [
        "# Strength Prompt 24. 비용부담 종합패널 작성",
        "",
        "- `direct_cost_burden_panel.csv`은 core sample include row를 기준으로 유효세율 matched row, 준조세 burden table, 재계산 `traffic_cost_pressure`, `domestic_infra_capex_ratio`를 하나의 direct cost burden panel로 합친 결과다.",
        "- 각 component score는 `peer_group_id` 내부 observed raw value를 기준으로 `0~100` min-max 점수화했고, 총점은 observed component가 `2개 이상`일 때만 평균으로 계산했다.",
        "- 따라서 이 패널은 component coverage가 얇은 row를 억지로 총점화하지 않고, `coverage_status`와 `total_score_status`로 해석 가능 범위를 함께 남긴 보수적 설계다.",
        "",
        f"- total rows: `{total_rows}`",
        f"- rows with total_direct_burden_score: `{total_scored}`",
        "",
        "## Peer coverage",
        "",
    ]
    for key, value in sorted(peer_counter.items()):
        log_lines.append(f"- `{key}`: `{value}`")
    log_lines.extend(["", "## Coverage status", ""])
    for key, value in sorted(coverage_counter.items()):
        log_lines.append(f"- `{key}`: `{value}`")

    top_rows = sorted(
        [row for row in output_rows if row["total_direct_burden_score"] is not None],
        key=lambda r: float(r["total_direct_burden_score"]),
        reverse=True,
    )[:5]
    log_lines.extend(["", "## Top observed total scores", ""])
    for row in top_rows:
        log_lines.append(
            f"- `{row['peer_group_id']} | {row['firm_std']} | {row['country_std']}`: `{fmt_float(float(row['total_direct_burden_score']))}`"
        )

    log_lines.extend(
        [
            "",
            "## Key interpretation",
            "",
            "- `infra_traffic_ott`는 세금·준조세·망비용·인프라비용의 네 축이 가장 두껍게 관측되는 peer라 총점 비교가 가장 직접적이다.",
            "- `mus_streaming_paid_core`와 `mus_label_ip_export`는 주로 세금축에 의존하고, 일부 row는 준조세 numeric signal이 없어 총점이 의도적으로 비워진다.",
            "- 따라서 이번 panel의 핵심 가치는 모든 row를 같은 강도로 해석하는 것이 아니라, 어디서 direct cost burden 비교가 실제로 두껍고 어디서 아직 얇은지를 한눈에 드러내는 데 있다.",
        ]
    )
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
