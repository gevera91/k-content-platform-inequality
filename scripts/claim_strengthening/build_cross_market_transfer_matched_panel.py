from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parents[2]

CORE_SAMPLE_PATH = (
    ROOT
    / "data/registry/claim_strengthening/reverse_discrimination_core_sample_v1.csv"
)
MONTH_PANEL_PATH = ROOT / "data/processed/variable_panel_platform_month.csv"
QUARTER_PANEL_PATH = ROOT / "data/processed/variable_panel_platform_quarter.csv"
EVENT_REGISTRY_NARROW_PATH = (
    ROOT / "data/registry/claim_strengthening/event_registry_narrow.csv"
)

OUTPUT_PANEL_PATH = (
    ROOT / "data/processed/claim_strengthening/cross_market_transfer_matched_panel.csv"
)
OUTPUT_SUMMARY_PATH = (
    ROOT / "outputs/tables/claim_strengthening/T_claim_transfer_summary.csv"
)
LOG_PATH = ROOT / "logs/claim_strengthening/cross_market_transfer_matched_log.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def safe_float(value: str) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def fmt(value: float | int | None) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    return f"{value:.9f}".rstrip("0").rstrip(".")


def classify_formula_case(sector_std: str, bundle: float | None, dep: float | None, chart: float | None) -> str:
    if sector_std == "music":
        if bundle is not None and dep is not None and chart is not None:
            return "music_bundle_dependency_chart_gap"
        if bundle is not None and dep is not None and chart is None:
            return "music_bundle_dependency_missing_chart"
        if bundle is None and dep is not None and chart is not None:
            return "music_dependency_chart_gap"
        return "music_partial_other"
    if sector_std == "webtoon_story":
        return "webtoon_storefront_proxy"
    return "other_sector_transfer_proxy"


def classify_directness_status(formula_case: str) -> str:
    if formula_case == "music_bundle_dependency_chart_gap":
        return "stronger_direct_transfer_coverage"
    if formula_case in {"music_bundle_dependency_missing_chart", "music_dependency_chart_gap"}:
        return "partial_direct_transfer_coverage"
    if formula_case == "webtoon_storefront_proxy":
        return "proxy_transfer_coverage"
    return "thin_direct_transfer_coverage"


def relative_position_pct(values: list[float], value: float) -> float:
    if len(values) == 1:
        return 100.0
    lower = sum(1 for item in values if item < value)
    equal = sum(1 for item in values if item == value)
    return 100.0 * (lower + 0.5 * (equal - 1)) / (len(values) - 1)


def event_lookup(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    lookup: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        lookup[row["linked_peer_group_id"]].append(row)
    return lookup


def build_panel_rows() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    core_rows = [row for row in read_csv(CORE_SAMPLE_PATH) if row["include_flag"] == "yes"]
    event_rows = read_csv(EVENT_REGISTRY_NARROW_PATH)
    events_by_peer = event_lookup(event_rows)

    core_meta = {
        (row["firm_std"], row["service_std"], row["country_std"]): row for row in core_rows
    }

    raw_panel_rows: list[dict[str, object]] = []
    for panel_path, frequency, time_col in [
        (MONTH_PANEL_PATH, "month", "year_month"),
        (QUARTER_PANEL_PATH, "quarter", "year_quarter"),
    ]:
        for row in read_csv(panel_path):
            key = (row["firm_std"], row["service_std"], row["country_std"])
            if key not in core_meta:
                continue
            transfer_value = safe_float(row.get("cross_market_transfer_index", ""))
            if transfer_value is None:
                continue
            bundle_value = safe_float(row.get("bundle_leverage_index", ""))
            dependency_value = safe_float(row.get("foreign_dependency_ratio", ""))
            chart_share = safe_float(row.get("chart_share_proxy", ""))
            meta = core_meta[key]
            raw_panel_rows.append(
                {
                    "peer_group_id": meta["peer_group_id"],
                    "firm_std": row["firm_std"],
                    "service_std": row["service_std"],
                    "country_std": row["country_std"],
                    "analysis_role": meta["analysis_role"],
                    "panel_frequency": frequency,
                    "panel_time_key": row[time_col],
                    "cross_market_transfer_index": transfer_value,
                    "bundle_leverage_index": bundle_value,
                    "foreign_dependency_ratio": dependency_value,
                    "chart_share_proxy": chart_share,
                    "sector_std": row["sector_std"],
                }
            )

    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in raw_panel_rows:
        grouped[
            (
                str(row["peer_group_id"]),
                str(row["country_std"]),
                str(row["panel_frequency"]),
                str(row["panel_time_key"]),
            )
        ].append(row)

    output_rows: list[dict[str, str]] = []
    summary_seed: list[dict[str, str]] = []

    for group_key, rows in sorted(grouped.items()):
        peer_group_id, country_std, panel_frequency, panel_time_key = group_key
        roles = [str(row["analysis_role"]) for row in rows]
        has_global = any("global" in role for role in roles)
        has_korean = any("korean" in role for role in roles)

        if has_global and has_korean:
            comparability_flag = "yes"
            exclude_reason = ""
            korean_values = [
                float(row["cross_market_transfer_index"])
                for row in rows
                if "korean" in str(row["analysis_role"])
            ]
            global_values = [
                float(row["cross_market_transfer_index"])
                for row in rows
                if "global" in str(row["analysis_role"])
            ]
            korean_mean = mean(korean_values)
            global_mean = mean(global_values)
            gap = korean_mean - global_mean
        else:
            comparability_flag = "no"
            if not has_global:
                exclude_reason = "no_global_peer_same_period"
            elif not has_korean:
                exclude_reason = "no_korean_anchor_same_period"
            else:
                exclude_reason = "unknown_match_failure"
            korean_mean = None
            global_mean = None
            gap = None

        values = [float(row["cross_market_transfer_index"]) for row in rows]
        sorted_values = sorted(values, reverse=True)
        event_rows_for_group = events_by_peer.get(peer_group_id, [])
        linked_event_ids = "|".join(sorted(row["event_id"] for row in event_rows_for_group))
        linked_event_types = "|".join(
            sorted({row["narrow_event_type"] for row in event_rows_for_group})
        )
        linked_event_count = len(event_rows_for_group)

        for row in rows:
            rank = 1 + sum(
                1
                for candidate in sorted_values
                if candidate > float(row["cross_market_transfer_index"])
            )
            formula_case = classify_formula_case(
                str(row["sector_std"]),
                row["bundle_leverage_index"],
                row["foreign_dependency_ratio"],
                row["chart_share_proxy"],
            )
            output_rows.append(
                {
                    "peer_group_id": peer_group_id,
                    "firm_std": str(row["firm_std"]),
                    "service_std": str(row["service_std"]),
                    "country_std": country_std,
                    "analysis_role": str(row["analysis_role"]),
                    "panel_frequency": panel_frequency,
                    "panel_time_key": panel_time_key,
                    "cross_market_transfer_index": fmt(float(row["cross_market_transfer_index"])),
                    "bundle_leverage_index": fmt(row["bundle_leverage_index"]),
                    "foreign_dependency_ratio": fmt(row["foreign_dependency_ratio"]),
                    "chart_share_proxy": fmt(row["chart_share_proxy"]),
                    "formula_case": formula_case,
                    "directness_status": classify_directness_status(formula_case),
                    "comparability_flag": comparability_flag,
                    "exclude_reason": exclude_reason,
                    "matched_peer_count": str(len(rows)),
                    "korean_anchor_count": str(sum(1 for role in roles if "korean" in role)),
                    "global_peer_count": str(sum(1 for role in roles if "global" in role)),
                    "korean_anchor_mean_transfer": fmt(korean_mean),
                    "global_peer_mean_transfer": fmt(global_mean),
                    "korean_minus_global_gap": fmt(gap),
                    "rank_within_peer_period": str(rank),
                    "relative_position_pct": fmt(
                        relative_position_pct(values, float(row["cross_market_transfer_index"]))
                    ),
                    "linked_narrow_event_count": str(linked_event_count),
                    "linked_narrow_event_ids": linked_event_ids,
                    "linked_narrow_event_types": linked_event_types,
                }
            )

        if comparability_flag == "yes":
            summary_seed.append(
                {
                    "peer_group_id": peer_group_id,
                    "country_std": country_std,
                    "panel_frequency": panel_frequency,
                    "panel_time_key": panel_time_key,
                    "korean_anchor_mean_transfer": fmt(korean_mean),
                    "global_peer_mean_transfer": fmt(global_mean),
                    "korean_minus_global_gap": fmt(gap),
                    "linked_narrow_event_count": str(linked_event_count),
                    "linked_narrow_event_ids": linked_event_ids,
                }
            )

    return output_rows, summary_seed


def build_summary_table(
    matched_rows: list[dict[str, str]], panel_rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in matched_rows:
        grouped[(row["peer_group_id"], row["country_std"], row["panel_frequency"])].append(row)

    directness_by_group: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
    for row in panel_rows:
        if row["comparability_flag"] != "yes":
            continue
        directness_by_group[
            (row["peer_group_id"], row["country_std"], row["panel_frequency"])
        ][row["directness_status"]] += 1

    summary_rows: list[dict[str, str]] = []
    for key, rows in sorted(grouped.items()):
        peer_group_id, country_std, panel_frequency = key
        gaps = [float(row["korean_minus_global_gap"]) for row in rows if row["korean_minus_global_gap"]]
        latest_row = max(rows, key=lambda row: row["panel_time_key"])
        nonzero_gaps = [gap for gap in gaps if abs(gap) > 1e-12]
        if nonzero_gaps and all(gap > 0 for gap in nonzero_gaps):
            gap_direction = "korean_higher_all_nonzero_periods"
        elif nonzero_gaps and all(gap < 0 for gap in nonzero_gaps):
            gap_direction = "global_higher_all_nonzero_periods"
        elif any(abs(gap) <= 1e-12 for gap in gaps) and not nonzero_gaps:
            gap_direction = "all_zero_gap_periods"
        else:
            gap_direction = "mixed_gap_direction"

        summary_rows.append(
            {
                "peer_group_id": peer_group_id,
                "country_std": country_std,
                "panel_frequency": panel_frequency,
                "matched_period_count": str(len(rows)),
                "mean_korean_anchor_transfer": fmt(
                    mean(float(row["korean_anchor_mean_transfer"]) for row in rows)
                ),
                "mean_global_peer_transfer": fmt(
                    mean(float(row["global_peer_mean_transfer"]) for row in rows)
                ),
                "mean_korean_minus_global_gap": fmt(mean(gaps)),
                "latest_panel_time_key": latest_row["panel_time_key"],
                "latest_korean_minus_global_gap": latest_row["korean_minus_global_gap"],
                "gap_direction": gap_direction,
                "dominant_directness_status": directness_by_group[key].most_common(1)[0][0],
                "linked_narrow_event_count": latest_row["linked_narrow_event_count"],
                "linked_narrow_event_ids": latest_row["linked_narrow_event_ids"],
                "interpretation": (
                    "글로벌 peer 확장 사건과 연결된 direct transfer row가 있으나 한국 평균이 더 높지 않음"
                    if latest_row["linked_narrow_event_count"] != "0"
                    else "이 그룹은 direct transfer matched row는 있으나 Prompt 31 협의 사건 registry와 직접 연결된 글로벌 확장 사건이 없음"
                ),
            }
        )

    return summary_rows


def main() -> None:
    panel_rows, matched_seed = build_panel_rows()
    summary_rows = build_summary_table(matched_seed, panel_rows)

    panel_fieldnames = [
        "peer_group_id",
        "firm_std",
        "service_std",
        "country_std",
        "analysis_role",
        "panel_frequency",
        "panel_time_key",
        "cross_market_transfer_index",
        "bundle_leverage_index",
        "foreign_dependency_ratio",
        "chart_share_proxy",
        "formula_case",
        "directness_status",
        "comparability_flag",
        "exclude_reason",
        "matched_peer_count",
        "korean_anchor_count",
        "global_peer_count",
        "korean_anchor_mean_transfer",
        "global_peer_mean_transfer",
        "korean_minus_global_gap",
        "rank_within_peer_period",
        "relative_position_pct",
        "linked_narrow_event_count",
        "linked_narrow_event_ids",
        "linked_narrow_event_types",
    ]
    summary_fieldnames = [
        "peer_group_id",
        "country_std",
        "panel_frequency",
        "matched_period_count",
        "mean_korean_anchor_transfer",
        "mean_global_peer_transfer",
        "mean_korean_minus_global_gap",
        "latest_panel_time_key",
        "latest_korean_minus_global_gap",
        "gap_direction",
        "dominant_directness_status",
        "linked_narrow_event_count",
        "linked_narrow_event_ids",
        "interpretation",
    ]

    write_csv(OUTPUT_PANEL_PATH, panel_rows, panel_fieldnames)
    write_csv(OUTPUT_SUMMARY_PATH, summary_rows, summary_fieldnames)

    panel_count = len(panel_rows)
    matched_count = sum(1 for row in panel_rows if row["comparability_flag"] == "yes")
    comparable_groups = Counter(
        row["peer_group_id"] for row in panel_rows if row["comparability_flag"] == "yes"
    )
    lines = [
        "# Cross Market Transfer Matched Log",
        "",
        "## Summary",
        "",
        f"- panel rows: `{panel_count}`",
        f"- matched rows: `{matched_count}`",
        f"- unmatched rows: `{panel_count - matched_count}`",
        f"- matched peer groups: `{dict(sorted(comparable_groups.items()))}`",
        "",
        "## Interpretation",
        "",
        "- core sample에서 direct transfer row가 실제로 남는 그룹은 음악 `mus_streaming_paid_core`, `mus_label_ip_export`뿐이다.",
        "- `mus_streaming_paid_core`는 `2026-03`와 `2026Q1`만 글로벌 peer와 같은 시점 overlap이 있고 `2025Q4`는 한국 row만 남아 unmatched 처리된다.",
        "- `mus_label_ip_export`는 `kr` 셀에서 `2025Q4`, `2026Q1`, `2026-03` matched row가 남지만 평균 gap은 0 또는 음(-)이라 한국 anchor transfer가 글로벌 peer보다 높게 나타나지 않는다.",
        "- Prompt 31 협의 사건 registry와 직접 연결되는 그룹은 `mus_streaming_paid_core`뿐이며, 이 경우에도 matched transfer gap은 latest quarter 기준 음(-)이라 사건축만으로 역차별 결론을 강화하지는 못한다.",
    ]
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
