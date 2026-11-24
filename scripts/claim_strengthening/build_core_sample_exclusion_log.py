#!/usr/bin/env python3
from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

CORE_SAMPLE_PATH = ROOT / "data/registry/claim_strengthening/reverse_discrimination_core_sample_v1.csv"
SERVICE_DICT_PATH = ROOT / "data/registry/entity_dictionary_service.csv"
OUTPUT_PATH = ROOT / "data/processed/claim_strengthening/core_sample_exclusion_log.csv"
LOG_PATH = ROOT / "logs/claim_strengthening/core_sample_exclusion_log.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def followup_mapping(peer_group_id: str, excluded_reason: str) -> tuple[str, str]:
    if excluded_reason == "common_period_too_short_for_level_compare":
        if peer_group_id == "webtoon_serial_platform":
            return "yes", "high"
        if peer_group_id == "infra_traffic_video":
            return "yes", "high"
        if peer_group_id == "infra_delivery_cdn":
            return "yes", "medium"
        if peer_group_id == "webtoon_internal_geo_split":
            return "yes", "medium"
        return "yes", "medium"
    if excluded_reason == "close_substitute_bundle_peer_reserved_for_sensitivity":
        return "no", "medium"
    if excluded_reason == "exploratory_cloud_reference_reserved_for_sensitivity":
        return "no", "low"
    return "no", "low"


def build_rows() -> list[dict[str, str]]:
    core_rows = read_csv(CORE_SAMPLE_PATH)
    service_rows = read_csv(SERVICE_DICT_PATH)
    sector_by_service = {row["service_std"]: row["sector_std"] for row in service_rows}

    excluded = [row for row in core_rows if row["include_flag"] == "no"]
    output_rows: list[dict[str, str]] = []
    for row in excluded:
        can_fix, priority = followup_mapping(row["peer_group_id"], row["include_reason"])
        output_rows.append(
            {
                "sector_std": sector_by_service.get(row["service_std"], ""),
                "firm_std": row["firm_std"],
                "service_std": row["service_std"],
                "country_std": row["country_std"],
                "excluded_reason": row["include_reason"],
                "can_be_fixed_by_more_collection": can_fix,
                "priority_for_followup": priority,
            }
        )

    output_rows.sort(
        key=lambda r: (
            {"high": 0, "medium": 1, "low": 2}[r["priority_for_followup"]],
            r["sector_std"],
            r["country_std"],
            r["firm_std"],
            r["service_std"],
        )
    )
    return output_rows


def write_outputs(rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "sector_std",
        "firm_std",
        "service_std",
        "country_std",
        "excluded_reason",
        "can_be_fixed_by_more_collection",
        "priority_for_followup",
    ]
    with OUTPUT_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    fixable = sum(row["can_be_fixed_by_more_collection"] == "yes" for row in rows)
    high = sum(row["priority_for_followup"] == "high" for row in rows)
    medium = sum(row["priority_for_followup"] == "medium" for row in rows)
    low = sum(row["priority_for_followup"] == "low" for row in rows)

    with LOG_PATH.open("w") as f:
        f.write("# Strength Prompt 10. 제외 표본 로그 작성\n\n")
        f.write("- `core_sample_exclusion_log.csv`는 core sample v1에서 제외된 기업-서비스-국가 셀을 전부 기록한 follow-up registry다.\n")
        f.write("- 이 표는 단순 제외 목록이 아니라, 추가 수집으로 되살릴 수 있는 셀과 설계상 core 밖에 두는 셀을 분리하는 데 목적이 있다.\n")
        f.write("- 현재 기준에서 가장 먼저 보강해야 할 영역은 `webtoon_serial_platform`과 `infra_traffic_video`다. 둘 다 결론 강화에 중요한데 공통기간이 짧아서 core v1에서 밀려났다.\n")
        f.write("- `mus_streaming_bundle_alt`와 `infra_cloud_reference`는 지금 당장 더 모은다고 core v1이 되는 성격이 아니라 sensitivity 또는 exploratory 그룹으로 유지했다.\n\n")
        f.write(f"- total excluded rows: `{total}`\n")
        f.write(f"- fixable by more collection: `{fixable}`\n")
        f.write(f"- priority high: `{high}`\n")
        f.write(f"- priority medium: `{medium}`\n")
        f.write(f"- priority low: `{low}`\n")


def main() -> None:
    rows = build_rows()
    write_outputs(rows)


if __name__ == "__main__":
    main()
