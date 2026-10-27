from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

EVENT_REGISTRY_PATH = (
    PROJECT_ROOT / "data/registry/claim_strengthening/event_registry_narrow.csv"
)
EVENT_STUDY_PANEL_PATH = PROJECT_ROOT / "data/processed/event_study_panel.csv"
MUSIC_REGRESSION_PATH = PROJECT_ROOT / "outputs/tables/regression_results_music.csv"
WEBTOON_REGRESSION_PATH = PROJECT_ROOT / "outputs/tables/regression_results_webtoon.csv"
INFRA_REGRESSION_PATH = PROJECT_ROOT / "outputs/tables/regression_results_infra.csv"

OUTPUT_TABLE_PATH = (
    PROJECT_ROOT / "outputs/tables/claim_strengthening/T_claim_pretrend_check.csv"
)
OUTPUT_LOG_PATH = (
    PROJECT_ROOT / "logs/claim_strengthening/pretrend_recheck_log.md"
)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_event_registry() -> list[dict[str, str]]:
    return read_csv_rows(EVENT_REGISTRY_PATH)


def load_sector_model_map() -> dict[str, dict[str, str] | None]:
    mapping: dict[str, dict[str, str] | None] = {
        "music": None,
        "webtoon_story": None,
        "digital_infra": None,
    }
    source_map = {
        "music": MUSIC_REGRESSION_PATH,
        "webtoon_story": WEBTOON_REGRESSION_PATH,
        "digital_infra": INFRA_REGRESSION_PATH,
    }
    for sector_std, path in source_map.items():
        for row in read_csv_rows(path):
            if row.get("model_type") == "event_study":
                mapping[sector_std] = row
                break
    return mapping


def load_panel_stats(event_ids: set[str]) -> dict[str, dict[str, object]]:
    counts: dict[str, dict[str, object]] = {
        event_id: {
            "panel_types": set(),
            "shared_pre_periods": [],
            "treated_pre_rows": 0,
            "control_pre_rows": 0,
        }
        for event_id in event_ids
    }
    pre_rel_counts: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"treated": 0, "control": 0})
    )

    for row in read_csv_rows(EVENT_STUDY_PANEL_PATH):
        event_id = row["event_id"]
        if event_id not in event_ids:
            continue
        counts[event_id]["panel_types"].add(row["panel_type"])
        if row["pre_flag"] != "1":
            continue
        relative_period = row["relative_period"]
        if row["treated_flag"] == "1":
            pre_rel_counts[event_id][relative_period]["treated"] += 1
            counts[event_id]["treated_pre_rows"] += 1
        if row["control_flag"] == "1":
            pre_rel_counts[event_id][relative_period]["control"] += 1
            counts[event_id]["control_pre_rows"] += 1

    for event_id, rel_map in pre_rel_counts.items():
        shared = [
            rel
            for rel, rel_counts in rel_map.items()
            if rel_counts["treated"] > 0 and rel_counts["control"] > 0
        ]
        counts[event_id]["shared_pre_periods"] = sorted(shared, key=lambda value: int(value))
    return counts


def supporting_pretrend_reason(
    sector_std: str,
    sector_model_map: dict[str, dict[str, str] | None],
) -> tuple[str, str, str]:
    model_row = sector_model_map.get(sector_std)
    if not model_row:
        return "", "", "No sector-level narrow event-study model available"
    return (
        model_row["model_id"],
        model_row["pretrend_test_result"],
        model_row["pretrend_detail"],
    )


def build_rows() -> list[dict[str, str]]:
    registry_rows = load_event_registry()
    sector_model_map = load_sector_model_map()
    panel_stats = load_panel_stats({row["event_id"] for row in registry_rows})

    out_rows: list[dict[str, str]] = []
    for row in registry_rows:
        event_id = row["event_id"]
        stats = panel_stats[event_id]
        shared_pre_periods = list(stats["shared_pre_periods"])
        shared_pre_count = len(shared_pre_periods)
        supporting_model_id, supporting_pretrend_result, supporting_pretrend_detail = (
            supporting_pretrend_reason(row["sector_std"], sector_model_map)
        )

        reasons: list[str] = []
        if row["core_sample_link_flag"] != "yes":
            reasons.append("Not linked to claim core sample v1")
        if row["country_comparable_flag"] != "yes":
            reasons.append("No same-country comparable cell")
        if shared_pre_count < 2:
            reasons.append(
                f"Insufficient shared pre-periods (count={shared_pre_count}, observed="
                f"{'|'.join(shared_pre_periods) if shared_pre_periods else 'none'})"
            )
        if supporting_model_id == "":
            reasons.append("No sector-level narrow event-study model available")
        elif supporting_pretrend_result == "fail":
            reasons.append(
                f"Inherited sector-level pretrend fail from {supporting_model_id} "
                f"({supporting_pretrend_detail})"
            )
        elif supporting_pretrend_result not in {"pass", "not_applicable", ""}:
            reasons.append(
                f"Sector-level pretrend status unresolved ({supporting_pretrend_result})"
            )

        pretrend_pass_flag = "yes" if not reasons else "no"
        out_rows.append(
            {
                "event_id": event_id,
                "peer_group_id": row["linked_peer_group_id"],
                "sector_std": row["sector_std"],
                "country_std": row["country_std"],
                "core_sample_link_flag": row["core_sample_link_flag"],
                "country_comparable_flag": row["country_comparable_flag"],
                "panel_type": "|".join(sorted(stats["panel_types"])),
                "shared_pre_period_count": str(shared_pre_count),
                "shared_pre_periods": "|".join(shared_pre_periods),
                "treated_pre_row_count": str(stats["treated_pre_rows"]),
                "control_pre_row_count": str(stats["control_pre_rows"]),
                "supporting_model_id": supporting_model_id,
                "supporting_model_pretrend_result": supporting_pretrend_result,
                "pretrend_pass_flag": pretrend_pass_flag,
                "reason_if_fail": "; ".join(reasons),
            }
        )
    return out_rows


def write_table(rows: list[dict[str, str]]) -> None:
    OUTPUT_TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "event_id",
        "peer_group_id",
        "sector_std",
        "country_std",
        "core_sample_link_flag",
        "country_comparable_flag",
        "panel_type",
        "shared_pre_period_count",
        "shared_pre_periods",
        "treated_pre_row_count",
        "control_pre_row_count",
        "supporting_model_id",
        "supporting_model_pretrend_result",
        "pretrend_pass_flag",
        "reason_if_fail",
    ]
    with OUTPUT_TABLE_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_log(rows: list[dict[str, str]]) -> None:
    pass_count = sum(1 for row in rows if row["pretrend_pass_flag"] == "yes")
    fail_count = len(rows) - pass_count

    peer_counter = Counter(row["peer_group_id"] for row in rows)
    reason_counter: Counter[str] = Counter()
    for row in rows:
        if row["reason_if_fail"]:
            for reason in row["reason_if_fail"].split("; "):
                reason_counter[reason] += 1

    OUTPUT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_LOG_PATH.open("w", encoding="utf-8") as handle:
        handle.write("# Strength Prompt 41. Narrow Event Pretrend Recheck\n\n")
        handle.write("## Summary\n\n")
        handle.write(f"- events reviewed: `{len(rows)}`\n")
        handle.write(f"- pretrend pass: `{pass_count}`\n")
        handle.write(f"- pretrend fail: `{fail_count}`\n\n")

        handle.write("## Peer-Group Coverage\n\n")
        for peer_group_id in sorted(peer_counter):
            handle.write(f"- `{peer_group_id}`: `{peer_counter[peer_group_id]}` events\n")
        handle.write("\n")

        handle.write("## Failure Reason Counts\n\n")
        for reason, count in sorted(reason_counter.items(), key=lambda item: (-item[1], item[0])):
            handle.write(f"- `{reason}`: `{count}`\n")
        handle.write("\n")

        handle.write("## Event Notes\n\n")
        for row in rows:
            if row["pretrend_pass_flag"] == "yes":
                note = "pass"
            else:
                note = row["reason_if_fail"]
            handle.write(
                f"- `{row['event_id']}` | peer=`{row['peer_group_id']}` | "
                f"pre=`{row['shared_pre_periods'] or 'none'}` | result=`{row['pretrend_pass_flag']}` | "
                f"{note}\n"
            )


def main() -> None:
    rows = build_rows()
    write_table(rows)
    write_log(rows)


if __name__ == "__main__":
    main()
