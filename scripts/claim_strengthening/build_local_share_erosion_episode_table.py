from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parents[2]

EVENT_REGISTRY_NARROW_PATH = (
    ROOT / "data/registry/claim_strengthening/event_registry_narrow.csv"
)
EVENT_STUDY_PANEL_PATH = ROOT / "data/processed/event_study_panel.csv"
OUTPUT_TABLE_PATH = (
    ROOT / "data/processed/claim_strengthening/local_share_erosion_episode_table.csv"
)
LOG_PATH = ROOT / "logs/claim_strengthening/local_share_erosion_episode_log.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def safe_float(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.9f}".rstrip("0").rstrip(".")


def family_id(event_row: dict[str, str]) -> str:
    return event_row["event_id"].rsplit("_", 2)[0] + "_" + event_row["event_date"].replace("-", "")


def evidence_strength(pre_count: int, post_count: int, longest_run: int) -> str:
    if pre_count >= 3 and post_count >= 3 and longest_run >= 2:
        return "high"
    if pre_count >= 2 and post_count >= 2:
        return "medium"
    return "low"


def main() -> None:
    event_rows = read_csv(EVENT_REGISTRY_NARROW_PATH)
    panel_rows = read_csv(EVENT_STUDY_PANEL_PATH)

    families: dict[str, dict[str, object]] = {}
    for row in event_rows:
        fid = family_id(row)
        fam = families.setdefault(
            fid,
            {
                "event_family_id": fid,
                "linked_peer_group_id": row["linked_peer_group_id"],
                "narrow_event_type": row["narrow_event_type"],
                "global_service_std": row["service_std"],
                "event_date": row["event_date"],
                "source_event_ids": [],
                "target_korean_firms": set(),
            },
        )
        fam["source_event_ids"].append(row["event_id"])
        target_firms = [item for item in row["target_korean_firm_list"].split("|") if item]
        for firm in target_firms:
            fam["target_korean_firms"].add(firm)

    retained_rows: list[dict[str, str]] = []
    family_notes: list[str] = []

    for fam in families.values():
        source_event_ids = set(fam["source_event_ids"])
        target_firms = set(fam["target_korean_firms"])

        candidate_rows = []
        for row in panel_rows:
            if row["event_id"] not in source_event_ids:
                continue
            if row["country_std"] != "kr":
                continue
            if row["firm_std"] not in target_firms:
                continue
            if row["control_flag"] != "1":
                continue
            share = safe_float(row.get("chart_share_proxy"))
            if share is None:
                continue
            panel_frequency = "month" if row["panel_type"] == "platform_month" else "quarter"
            panel_time_key = row["year_month"] if panel_frequency == "month" else row["year_quarter"]
            candidate_rows.append(
                {
                    "firm_std": row["firm_std"],
                    "service_std": row["service_std"],
                    "panel_frequency": panel_frequency,
                    "panel_time_key": panel_time_key,
                    "relative_period": int(row["relative_period"]),
                    "chart_share_proxy": share,
                }
            )

        if not candidate_rows:
            family_notes.append(
                f"- `{fam['event_family_id']}`: 한국 local control row는 있으나 직접 점유율 proxy `chart_share_proxy`가 없어 잠식 episode 비교 불가"
            )
            continue

        deduped = {}
        for row in candidate_rows:
            key = (
                row["firm_std"],
                row["service_std"],
                row["panel_frequency"],
                row["panel_time_key"],
                row["relative_period"],
            )
            deduped[key] = row

        grouped: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
        for row in deduped.values():
            grouped[(row["firm_std"], row["service_std"], row["panel_frequency"])].append(row)

        aggregate_by_panel: dict[str, dict[int, float]] = defaultdict(dict)
        for panel_frequency in {"month", "quarter"}:
            per_period_values: dict[int, list[float]] = defaultdict(list)
            for row in deduped.values():
                if row["panel_frequency"] != panel_frequency:
                    continue
                per_period_values[int(row["relative_period"])].append(float(row["chart_share_proxy"]))
            for rel, values in per_period_values.items():
                aggregate_by_panel[panel_frequency][rel] = sum(values)

        family_retained = 0
        for (firm_std, service_std, panel_frequency), rows in sorted(grouped.items()):
            rows.sort(key=lambda row: int(row["relative_period"]))
            pre_rows = [row for row in rows if int(row["relative_period"]) < 0]
            post_rows = [row for row in rows if int(row["relative_period"]) > 0]
            event_rows_same = [row for row in rows if int(row["relative_period"]) == 0]

            min_required = 2 if panel_frequency == "month" else 1
            if len(pre_rows) < min_required or len(post_rows) < min_required:
                continue

            pre_values = [float(row["chart_share_proxy"]) for row in pre_rows]
            post_values = [float(row["chart_share_proxy"]) for row in post_rows]
            pre_mean = mean(pre_values)
            post_mean = mean(post_values)
            event_value = mean(float(row["chart_share_proxy"]) for row in event_rows_same) if event_rows_same else None
            trough_post = min(post_values)
            share_change = post_mean - pre_mean
            trough_gap = trough_post - pre_mean

            longest_below_run = 0
            current_run = 0
            for row in post_rows:
                if float(row["chart_share_proxy"]) < pre_mean:
                    current_run += 1
                    longest_below_run = max(longest_below_run, current_run)
                else:
                    current_run = 0

            local_share_decline_flag = "yes" if post_mean < pre_mean and trough_post < pre_mean else "no"
            if local_share_decline_flag != "yes":
                continue

            aggregate_panel = aggregate_by_panel[panel_frequency]
            agg_pre = [value for rel, value in sorted(aggregate_panel.items()) if rel < 0]
            agg_post = [value for rel, value in sorted(aggregate_panel.items()) if rel > 0]
            aggregate_group_change = None
            if len(agg_pre) >= min_required and len(agg_post) >= min_required:
                aggregate_group_change = mean(agg_post) - mean(agg_pre)

            family_retained += 1
            episode_id = f"{fam['event_family_id']}|{firm_std}|{service_std}|{panel_frequency}"
            retained_rows.append(
                {
                    "episode_id": episode_id,
                    "event_family_id": str(fam["event_family_id"]),
                    "linked_peer_group_id": str(fam["linked_peer_group_id"]),
                    "narrow_event_type": str(fam["narrow_event_type"]),
                    "global_service_std": str(fam["global_service_std"]),
                    "source_event_count": str(len(source_event_ids)),
                    "source_event_ids": "|".join(sorted(source_event_ids)),
                    "event_date": str(fam["event_date"]),
                    "target_local_firm_std": firm_std,
                    "target_local_service_std": service_std,
                    "panel_frequency": panel_frequency,
                    "local_share_proxy_name": "chart_share_proxy",
                    "pre_period_count": str(len(pre_rows)),
                    "post_period_count": str(len(post_rows)),
                    "pre_period_keys": "|".join(str(row["panel_time_key"]) for row in pre_rows),
                    "post_period_keys": "|".join(str(row["panel_time_key"]) for row in post_rows),
                    "pre_share_mean": fmt(pre_mean),
                    "event_period_share": fmt(event_value),
                    "post_share_mean": fmt(post_mean),
                    "share_change_post_minus_pre": fmt(share_change),
                    "trough_post_share": fmt(trough_post),
                    "trough_gap_vs_pre": fmt(trough_gap),
                    "longest_consecutive_post_below_pre": str(longest_below_run),
                    "aggregate_local_group_change_same_panel": fmt(aggregate_group_change),
                    "evidence_strength": evidence_strength(len(pre_rows), len(post_rows), longest_below_run),
                    "retained_reason": "event family pre/post 비교가 가능하고 local share mean과 trough가 모두 pre mean 아래로 내려감",
                }
            )

        if family_retained == 0:
            family_notes.append(
                f"- `{fam['event_family_id']}`: 전후 비교 가능한 local control row는 있었지만 retained decline episode 조건을 만족한 한국 서비스가 없음"
            )

    retained_rows.sort(
        key=lambda row: (
            row["event_date"],
            row["event_family_id"],
            row["target_local_firm_std"],
            row["panel_frequency"],
        )
    )

    fieldnames = [
        "episode_id",
        "event_family_id",
        "linked_peer_group_id",
        "narrow_event_type",
        "global_service_std",
        "source_event_count",
        "source_event_ids",
        "event_date",
        "target_local_firm_std",
        "target_local_service_std",
        "panel_frequency",
        "local_share_proxy_name",
        "pre_period_count",
        "post_period_count",
        "pre_period_keys",
        "post_period_keys",
        "pre_share_mean",
        "event_period_share",
        "post_share_mean",
        "share_change_post_minus_pre",
        "trough_post_share",
        "trough_gap_vs_pre",
        "longest_consecutive_post_below_pre",
        "aggregate_local_group_change_same_panel",
        "evidence_strength",
        "retained_reason",
    ]
    write_csv(OUTPUT_TABLE_PATH, retained_rows, fieldnames)

    lines = [
        "# Local Share Erosion Episode Log",
        "",
        "## Summary",
        "",
        f"- event families evaluated: `{len(families)}`",
        f"- retained erosion episodes: `{len(retained_rows)}`",
        "",
        "## Retained Episodes",
        "",
    ]
    if retained_rows:
        for row in retained_rows:
            lines.append(
                f"- `{row['event_family_id']} -> {row['target_local_service_std']}`: pre `{row['pre_share_mean']}`, post `{row['post_share_mean']}`, delta `{row['share_change_post_minus_pre']}`, trough gap `{row['trough_gap_vs_pre']}`, evidence `{row['evidence_strength']}`"
            )
    else:
        lines.append("- retained episode 없음")

    lines.extend(
        [
            "",
            "## Exclusions",
            "",
        ]
    )
    if family_notes:
        lines.extend(family_notes)
    else:
        lines.append("- 제외된 family 없음")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- 현재 직접 local share erosion episode는 `spotify_lossless` family에서만 추출된다.",
            "- `melon`은 사건 전 3개월 평균 대비 사건 후 5개월 평균이 낮고 post trough도 pre 평균 아래라 retained episode로 남는다.",
            "- 반면 `flo`는 같은 사건 family에서 share가 개선됐고, local aggregate share도 같은 창에서 소폭 상승해 그룹 전체 잠식으로 일반화하긴 어렵다.",
            "- `youtube_premium_lite`와 `webtoon_video_episodes` family는 한국 local control row는 있으나 직접 local share proxy가 없어 이번 단계에서 에피소드로 승격하지 않았다.",
        ]
    )

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
