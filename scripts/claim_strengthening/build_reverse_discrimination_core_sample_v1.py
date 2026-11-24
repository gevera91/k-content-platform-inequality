#!/usr/bin/env python3
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

MATCHED_PEER_PATH = ROOT / "data/processed/claim_strengthening/matched_peer_registry.csv"
FILTER_PATH = ROOT / "data/processed/claim_strengthening/comparable_country_cell_filter.csv"
PERIOD_AUDIT_PATH = ROOT / "data/processed/claim_strengthening/common_period_audit_matched.csv"
OUTPUT_PATH = ROOT / "data/registry/claim_strengthening/reverse_discrimination_core_sample_v1.csv"
LOG_PATH = ROOT / "logs/claim_strengthening/core_sample_v1_log.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def analysis_role_for(group: str, side: str) -> str:
    role_map = {
        "mus_streaming_paid_core": ("korean_anchor", "global_same_service_peer"),
        "mus_streaming_bundle_alt": ("korean_anchor", "global_bundle_peer"),
        "mus_label_ip_export": ("korean_ip_anchor", "global_ip_peer"),
        "webtoon_serial_platform": ("korean_platform_anchor", "global_webtoon_peer"),
        "webtoon_internal_geo_split": ("domestic_anchor", "overseas_same_group_reference"),
        "story_ebook_adjacent": ("korean_story_anchor", "global_adjacent_reference"),
        "infra_traffic_ott": ("korean_network_anchor", "global_traffic_peer"),
        "infra_traffic_video": ("korean_network_anchor", "global_attention_peer"),
        "infra_delivery_cdn": ("korean_network_anchor", "global_delivery_peer"),
        "infra_cloud_reference": ("korean_network_anchor", "global_infra_reference"),
    }
    return role_map[group][0 if side == "korean" else 1]


def include_decision(group: str, common_row: dict[str, str]) -> tuple[str, str]:
    if common_row["usable_for_level_compare"] != "yes":
        return "no", "common_period_too_short_for_level_compare"
    if group == "mus_streaming_paid_core":
        return "yes", "direct_same_service_and_usable_level_overlap"
    if group == "mus_label_ip_export":
        return "yes", "content_ip_peer_with_usable_level_overlap"
    if group == "infra_traffic_ott":
        return "yes", "traffic_burden_peer_with_usable_level_overlap"
    if group == "mus_streaming_bundle_alt":
        return "no", "close_substitute_bundle_peer_reserved_for_sensitivity"
    if group == "infra_traffic_video":
        return "no", "thin_overlap_attention_peer_reserved_for_followup"
    if group == "infra_delivery_cdn":
        return "no", "delivery_stack_peer_reserved_for_followup"
    if group == "infra_cloud_reference":
        return "no", "exploratory_cloud_reference_reserved_for_sensitivity"
    if group == "webtoon_serial_platform":
        return "no", "no_webtoon_same_country_overlap_after_matching"
    if group == "webtoon_internal_geo_split":
        return "no", "geography_split_reference_not_core_v1"
    if group == "story_ebook_adjacent":
        return "no", "adjacent_story_distribution_not_core_v1"
    return "no", "not_selected_for_core_v1"


def build_rows() -> list[dict[str, str]]:
    matched = read_csv(MATCHED_PEER_PATH)
    comparable_filter = {
        (row["peer_group_id"], row["country_std"]): row
        for row in read_csv(FILTER_PATH)
        if row["cell_comparable_flag"] == "yes"
    }
    period_audit = {
        (row["peer_group_id"], row["country_std"]): row for row in read_csv(PERIOD_AUDIT_PATH)
    }

    dedup: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for row in matched:
        for country in sorted({c for (g, c) in comparable_filter if g == row["peer_group_id"]}):
            common_key = (row["peer_group_id"], country)
            common_row = period_audit[common_key]
            include_flag, include_reason = include_decision(row["peer_group_id"], common_row)

            korean_key = (row["peer_group_id"], row["korean_firm_std"], row["korean_service_std"], country)
            if korean_key not in dedup:
                dedup[korean_key] = {
                    "peer_group_id": row["peer_group_id"],
                    "firm_std": row["korean_firm_std"],
                    "service_std": row["korean_service_std"],
                    "country_std": country,
                    "include_flag": include_flag,
                    "include_reason": include_reason,
                    "analysis_role": analysis_role_for(row["peer_group_id"], "korean"),
                }

            global_key = (row["peer_group_id"], row["global_peer_std"], row["global_service_std"], country)
            if global_key not in dedup:
                dedup[global_key] = {
                    "peer_group_id": row["peer_group_id"],
                    "firm_std": row["global_peer_std"],
                    "service_std": row["global_service_std"],
                    "country_std": country,
                    "include_flag": include_flag,
                    "include_reason": include_reason,
                    "analysis_role": analysis_role_for(row["peer_group_id"], "global"),
                }

    return sorted(
        dedup.values(),
        key=lambda r: (
            r["peer_group_id"],
            r["country_std"],
            {"yes": 0, "no": 1}[r["include_flag"]],
            r["analysis_role"],
            r["firm_std"],
            r["service_std"],
        ),
    )


def write_outputs(rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "peer_group_id",
        "firm_std",
        "service_std",
        "country_std",
        "include_flag",
        "include_reason",
        "analysis_role",
    ]
    with OUTPUT_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    include_yes = [row for row in rows if row["include_flag"] == "yes"]
    include_no = [row for row in rows if row["include_flag"] == "no"]
    by_group_yes = defaultdict(int)
    for row in include_yes:
        by_group_yes[row["peer_group_id"]] += 1

    with LOG_PATH.open("w") as f:
        f.write("# Strength Prompt 09. 강한 비교표본 v1 고정\n\n")
        f.write("- `reverse_discrimination_core_sample_v1.csv`는 matched peer, comparable country cell, common period audit를 차례로 통과한 뒤 실제 강화 분석에 우선 사용할 row-level core sample이다.\n")
        f.write("- 이번 v1은 보수적으로 설계했다. `direct same-service`, `content IP peer`, `traffic burden peer` 가운데 level compare가 가능한 셀만 포함했다.\n")
        f.write("- 따라서 `mus_streaming_bundle_alt`, `webtoon_internal_geo_split`, `infra_cloud_reference` 같은 sensitivity 또는 exploratory 그룹은 이번 v1에서 의도적으로 제외했다.\n")
        f.write("- 웹툰 same-country direct pair는 공통기간이 실질적으로 남지 않아 core sample v1에 편입되지 못했다. 이는 현재 claim strengthening의 가장 큰 잔여 약점 중 하나다.\n\n")
        f.write(f"- included rows: `{len(include_yes)}`\n")
        f.write(f"- excluded rows: `{len(include_no)}`\n\n")
        f.write("## Included Groups\n\n")
        for group in sorted(by_group_yes):
            f.write(f"- `{group}`: `{by_group_yes[group]}` rows\n")


def main() -> None:
    rows = build_rows()
    write_outputs(rows)


if __name__ == "__main__":
    main()
