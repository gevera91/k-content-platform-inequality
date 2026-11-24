#!/usr/bin/env python3
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

MATCHED_PEER_PATH = ROOT / "data/processed/claim_strengthening/matched_peer_registry.csv"
FILTER_PATH = ROOT / "data/processed/claim_strengthening/comparable_country_cell_filter.csv"
PLATFORM_MONTH_PATH = ROOT / "data/processed/variable_panel_platform_month.csv"
PLATFORM_QUARTER_PATH = ROOT / "data/processed/variable_panel_platform_quarter.csv"
TITLE_QUARTER_PATH = ROOT / "data/processed/variable_panel_title_quarter.csv"
FIRM_CPII_PATH = ROOT / "data/processed/cpii_panel_firm_country_quarter.csv"
OUTPUT_PATH = ROOT / "data/processed/claim_strengthening/common_period_audit_matched.csv"
LOG_PATH = ROOT / "logs/claim_strengthening/common_period_audit_log.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def sorted_unique(values: list[str]) -> list[str]:
    return sorted(set(v for v in values if v))


def usable_for_level_compare(period_type: str, count: int) -> str:
    threshold = 2
    return "yes" if count >= threshold else "no"


def usable_for_event_study(period_type: str, count: int) -> str:
    threshold = 6 if period_type == "month" else 4
    return "yes" if count >= threshold else "no"


def best_overlap(pair_periods: list[list[str]]) -> list[str]:
    if not pair_periods:
        return []
    pair_periods = [sorted_unique(periods) for periods in pair_periods if periods]
    if not pair_periods:
        return []
    best = max(pair_periods, key=lambda vals: (len(vals), vals[0], vals[-1]))
    return best


def service_period_map_month(rows: list[dict[str, str]]) -> dict[tuple[str, str], list[str]]:
    period_map: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        if row.get("observed_any_flag") == "yes":
            period_map[(row["service_std"], row["country_std"])].append(row["year_month"])
    return {k: sorted_unique(v) for k, v in period_map.items()}


def service_period_map_quarter(rows: list[dict[str, str]]) -> dict[tuple[str, str], list[str]]:
    period_map: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        if row.get("construction_status") == "ready_for_qc":
            period_map[(row["service_std"], row["country_std"])].append(row["year_quarter"])
    return {k: sorted_unique(v) for k, v in period_map.items()}


def title_period_map(rows: list[dict[str, str]]) -> dict[tuple[str, str], list[str]]:
    period_map: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        if row.get("construction_status") == "ready_for_qc":
            period_map[(row["service_std"], row["country_std"])].append(row["year_quarter"])
    return {k: sorted_unique(v) for k, v in period_map.items()}


def firm_cpii_period_map(rows: list[dict[str, str]]) -> dict[tuple[str, str], list[str]]:
    period_map: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        if row.get("CPII"):
            period_map[(row["firm_std"], row["country_std"])].append(row["year_quarter"])
    return {k: sorted_unique(v) for k, v in period_map.items()}


def intersect_periods(*period_lists: list[str]) -> list[str]:
    if not period_lists:
        return []
    common = set(period_lists[0])
    for periods in period_lists[1:]:
        common &= set(periods)
    return sorted(common)


def build_rows() -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    matched_rows = read_csv(MATCHED_PEER_PATH)
    filter_rows = read_csv(FILTER_PATH)
    month_map = service_period_map_month(read_csv(PLATFORM_MONTH_PATH))
    quarter_service_map = service_period_map_quarter(read_csv(PLATFORM_QUARTER_PATH))
    title_map = title_period_map(read_csv(TITLE_QUARTER_PATH))
    firm_map = firm_cpii_period_map(read_csv(FIRM_CPII_PATH))

    pairs_by_group = defaultdict(list)
    for row in matched_rows:
        pairs_by_group[row["peer_group_id"]].append(row)

    period_type_by_group = {
        "mus_streaming_paid_core": "month",
        "mus_streaming_bundle_alt": "month",
        "mus_label_ip_export": "quarter",
        "webtoon_serial_platform": "quarter",
        "webtoon_internal_geo_split": "quarter",
        "story_ebook_adjacent": "quarter",
        "infra_traffic_ott": "quarter",
        "infra_traffic_video": "quarter",
        "infra_delivery_cdn": "quarter",
        "infra_cloud_reference": "quarter",
    }

    rows_out: list[dict[str, str]] = []
    summary = defaultdict(lambda: {"yes": 0, "event_yes": 0})

    for frow in filter_rows:
        group = frow["peer_group_id"]
        country = frow["country_std"]
        comparable = frow["cell_comparable_flag"]
        period_type = period_type_by_group[group]

        common_periods: list[str] = []
        if comparable == "yes":
            pair_overlaps: list[list[str]] = []
            for pair in pairs_by_group[group]:
                korean_service = pair["korean_service_std"]
                global_service = pair["global_service_std"]
                korean_firm = pair["korean_firm_std"]
                global_firm = pair["global_peer_std"]

                if group in {"mus_streaming_paid_core", "mus_streaming_bundle_alt"}:
                    k_periods = month_map.get((korean_service, country), [])
                    g_periods = month_map.get((global_service, country), [])
                    overlap = intersect_periods(k_periods, g_periods)
                elif group == "mus_label_ip_export":
                    k_periods = quarter_service_map.get((korean_service, country), [])
                    g_periods = quarter_service_map.get((global_service, country), [])
                    overlap = intersect_periods(k_periods, g_periods)
                elif group == "webtoon_serial_platform":
                    k_periods = title_map.get((korean_service, country), [])
                    g_periods = title_map.get((global_service, country), [])
                    overlap = intersect_periods(k_periods, g_periods)
                elif group == "webtoon_internal_geo_split":
                    k_periods = title_map.get((korean_service, "kr"), [])
                    g_periods = title_map.get((global_service, country), [])
                    overlap = intersect_periods(k_periods, g_periods)
                elif group in {"infra_traffic_ott", "infra_traffic_video", "infra_delivery_cdn", "infra_cloud_reference"}:
                    k_periods = firm_map.get((korean_firm, country), [])
                    g_periods = firm_map.get((global_firm, country), [])
                    overlap = intersect_periods(k_periods, g_periods)
                else:
                    overlap = []

                if overlap:
                    pair_overlaps.append(overlap)

            common_periods = best_overlap(pair_overlaps)

        count = len(common_periods)
        common_start = common_periods[0] if common_periods else ""
        common_end = common_periods[-1] if common_periods else ""
        level_flag = usable_for_level_compare(period_type, count) if comparable == "yes" else "no"
        event_flag = usable_for_event_study(period_type, count) if comparable == "yes" else "no"

        if comparable == "yes":
            summary[group]["yes"] += 1
            if event_flag == "yes":
                summary[group]["event_yes"] += 1

        rows_out.append(
            {
                "peer_group_id": group,
                "country_std": country,
                "period_type": period_type,
                "common_start": common_start,
                "common_end": common_end,
                "common_period_count": str(count),
                "usable_for_level_compare": level_flag,
                "usable_for_event_study": event_flag,
            }
        )

    return rows_out, summary


def write_outputs(rows: list[dict[str, str]], summary: dict[str, dict[str, str]]) -> None:
    fieldnames = [
        "peer_group_id",
        "country_std",
        "period_type",
        "common_start",
        "common_end",
        "common_period_count",
        "usable_for_level_compare",
        "usable_for_event_study",
    ]
    with OUTPUT_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    usable_level = sum(1 for row in rows if row["usable_for_level_compare"] == "yes")
    usable_event = sum(1 for row in rows if row["usable_for_event_study"] == "yes")
    with LOG_PATH.open("w") as f:
        f.write("# Strength Prompt 08. 공통기간 감사표 재작성\n\n")
        f.write("- `common_period_audit_matched.csv`는 matched peer와 comparable country cell을 기준으로 다시 계산한 공통기간 감사표다.\n")
        f.write("- 음악 스트리밍 direct pair는 `month`, 음악 IP·웹툰·디지털 인프라는 `quarter` 기준으로 계산했다.\n")
        f.write("- `webtoon_internal_geo_split`은 same-country comparison이 아니라 국내 `kr` baseline과 해외 전개 셀의 공통분기를 비교했다.\n")
        f.write("- 공통기간은 peer group-country 단위에서 유효한 pair들 가운데 가장 긴 pairwise overlap을 기준으로 기록했다. 이 값은 다음 단계 row-level core sample 고정의 상한선으로 해석해야 한다.\n")
        f.write("- 사용 판정 규칙은 다음과 같이 고정했다.\n")
        f.write("  - `usable_for_level_compare`: month와 quarter 모두 공통기간 `2` 이상\n")
        f.write("  - `usable_for_event_study`: month `6` 이상, quarter `4` 이상\n\n")
        f.write(f"- level compare usable cell: `{usable_level}`\n")
        f.write(f"- event study usable cell: `{usable_event}`\n\n")
        f.write("## Group Summary\n\n")
        for group in sorted(summary):
            f.write(
                f"- `{group}`: comparable cell `{summary[group]['yes']}`, event-study-usable cell `{summary[group]['event_yes']}`\n"
            )


def main() -> None:
    rows, summary = build_rows()
    write_outputs(rows, summary)


if __name__ == "__main__":
    main()
