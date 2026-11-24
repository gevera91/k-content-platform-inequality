from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CORE_SAMPLE_PATH = (
    PROJECT_ROOT / "data/registry/claim_strengthening/reverse_discrimination_core_sample_v1.csv"
)
COMMON_PERIOD_PATH = (
    PROJECT_ROOT / "data/processed/claim_strengthening/common_period_audit_matched.csv"
)
COMPOSITE_PATH = (
    PROJECT_ROOT / "data/processed/claim_strengthening/reverse_discrimination_composite_narrow.csv"
)
PREVIOUS_GAP_PATH = (
    PROJECT_ROOT / "outputs/tables/claim_strengthening/T_claim_korea_vs_global_gap.csv"
)

OUTPUT_BALANCED_PATH = (
    PROJECT_ROOT / "data/processed/claim_strengthening/reverse_discrimination_balanced_panel.csv"
)
OUTPUT_SUMMARY_PATH = (
    PROJECT_ROOT / "outputs/tables/claim_strengthening/T_claim_balanced_panel_summary.csv"
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def load_core_include_set() -> set[tuple[str, str, str, str]]:
    included: set[tuple[str, str, str, str]] = set()
    for row in read_csv(CORE_SAMPLE_PATH):
        if row["include_flag"] != "yes":
            continue
        included.add(
            (
                row["peer_group_id"],
                row["firm_std"],
                row["service_std"],
                row["country_std"],
            )
        )
    return included


def load_common_period_map() -> dict[tuple[str, str], dict[str, str]]:
    keep: dict[tuple[str, str], dict[str, str]] = {}
    for row in read_csv(COMMON_PERIOD_PATH):
        if row["usable_for_level_compare"] != "yes":
            continue
        keep[(row["peer_group_id"], row["country_std"])] = row
    return keep


def build_balanced_rows() -> list[dict[str, str]]:
    include_set = load_core_include_set()
    common_map = load_common_period_map()
    balanced_rows: list[dict[str, str]] = []
    for row in read_csv(COMPOSITE_PATH):
        key = (
            row["peer_group_id"],
            row["firm_std"],
            row["service_std"],
            row["country_std"],
        )
        common_key = (row["peer_group_id"], row["country_std"])
        if key not in include_set:
            continue
        if common_key not in common_map:
            continue
        common_row = common_map[common_key]
        clone = dict(row)
        clone["balanced_cell_flag"] = "yes"
        clone["balanced_period_type"] = common_row["period_type"]
        clone["balanced_common_start"] = common_row["common_start"]
        clone["balanced_common_end"] = common_row["common_end"]
        clone["balanced_common_period_count"] = common_row["common_period_count"]
        clone["balanced_inclusion_rule"] = (
            "core_sample_include_yes_and_common_period_usable_for_level_compare"
        )
        balanced_rows.append(clone)
    balanced_rows.sort(
        key=lambda item: (
            item["peer_group_id"],
            item["country_std"],
            item["firm_std"],
            item["service_std"],
        )
    )
    return balanced_rows


def write_balanced_panel(rows: list[dict[str, str]]) -> None:
    OUTPUT_BALANCED_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with OUTPUT_BALANCED_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_firm_level_rows(rows: list[dict[str, str]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["peer_group_id"], row["firm_std"])].append(row)

    out: dict[str, list[dict[str, object]]] = defaultdict(list)
    for (peer_group_id, firm_std), items in grouped.items():
        eligible = [
            row
            for row in items
            if row["composite_rank_eligible_flag"] == "yes" and row["composite_narrow"] != ""
        ]
        chosen = eligible if eligible else [row for row in items if row["composite_narrow"] != ""]
        composite_values = [float(row["composite_narrow"]) for row in chosen]
        country_cells = sorted({row["country_std"] for row in chosen})
        out[peer_group_id].append(
            {
                "firm_std": firm_std,
                "korean_firm_flag": "yes"
                if any(row["analysis_role"].startswith("korean") for row in items)
                else "no",
                "composite_narrow": mean(composite_values),
                "ranking_basis": "eligible_mean" if eligible else "all_row_mean_fallback",
                "country_cells_used_count": len(country_cells),
                "country_cells_used": "|".join(country_cells),
            }
        )
    return out


def load_previous_gap_map() -> dict[str, dict[str, str]]:
    return {row["peer_group_id"]: row for row in read_csv(PREVIOUS_GAP_PATH)}


def build_summary_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    previous_gap_map = load_previous_gap_map()
    firm_level = build_firm_level_rows(rows)
    summary_rows: list[dict[str, str]] = []

    unique_cells = sorted({(row["peer_group_id"], row["country_std"]) for row in rows})
    eligible_rows = [row for row in rows if row["composite_rank_eligible_flag"] == "yes"]
    summary_rows.append(
        {
            "row_type": "overall",
            "peer_group_id": "",
            "balanced_row_count": str(len(rows)),
            "balanced_peer_group_count": str(len(firm_level)),
            "balanced_country_cell_count": str(len(unique_cells)),
            "balanced_rank_eligible_row_count": str(len(eligible_rows)),
            "balanced_korean_firm_count": str(
                len({row["firm_std"] for row in rows if row["analysis_role"].startswith("korean")})
            ),
            "balanced_global_firm_count": str(
                len({row["firm_std"] for row in rows if not row["analysis_role"].startswith("korean")})
            ),
            "balanced_korean_mean_composite": "",
            "balanced_global_mean_composite": "",
            "balanced_korea_minus_global_gap": "",
            "previous_unbalanced_gap": "",
            "gap_change_vs_unbalanced": "",
            "best_korean_firm_std": "",
            "best_global_firm_std": "",
            "korean_fallback_firm_count": "",
            "gap_changed_flag": "",
            "interpretation_note": (
                "Balanced panel keeps only core rows on common-period cells that pass usable_for_level_compare."
            ),
        }
    )

    for peer_group_id in sorted(firm_level):
        peer_rows = firm_level[peer_group_id]
        korean_rows = [row for row in peer_rows if row["korean_firm_flag"] == "yes"]
        global_rows = [row for row in peer_rows if row["korean_firm_flag"] == "no"]
        korean_mean = mean([row["composite_narrow"] for row in korean_rows])
        global_mean = mean([row["composite_narrow"] for row in global_rows])
        gap = korean_mean - global_mean
        previous_gap = float(previous_gap_map[peer_group_id]["korea_minus_global_gap"])
        delta = gap - previous_gap
        delta_text = f"{delta:.6f}"
        delta_effective = float(delta_text)
        best_korean = max(korean_rows, key=lambda item: item["composite_narrow"])
        best_global = max(global_rows, key=lambda item: item["composite_narrow"])
        fallback_count = sum(
            1 for row in korean_rows if row["ranking_basis"] == "all_row_mean_fallback"
        )
        summary_rows.append(
            {
                "row_type": "peer_summary",
                "peer_group_id": peer_group_id,
                "balanced_row_count": str(
                    sum(1 for row in rows if row["peer_group_id"] == peer_group_id)
                ),
                "balanced_peer_group_count": "1",
                "balanced_country_cell_count": str(
                    len({row["country_std"] for row in rows if row["peer_group_id"] == peer_group_id})
                ),
                "balanced_rank_eligible_row_count": str(
                    sum(
                        1
                        for row in rows
                        if row["peer_group_id"] == peer_group_id
                        and row["composite_rank_eligible_flag"] == "yes"
                    )
                ),
                "balanced_korean_firm_count": str(len(korean_rows)),
                "balanced_global_firm_count": str(len(global_rows)),
                "balanced_korean_mean_composite": f"{korean_mean:.6f}",
                "balanced_global_mean_composite": f"{global_mean:.6f}",
                "balanced_korea_minus_global_gap": f"{gap:.6f}",
                "previous_unbalanced_gap": f"{previous_gap:.6f}",
                "gap_change_vs_unbalanced": delta_text,
                "best_korean_firm_std": best_korean["firm_std"],
                "best_global_firm_std": best_global["firm_std"],
                "korean_fallback_firm_count": str(fallback_count),
                "gap_changed_flag": "yes" if abs(delta_effective) > 0 else "no",
                "interpretation_note": (
                    "Balanced summary unchanged from prior estimate"
                    if abs(delta_effective) == 0
                    else "Balanced filter changes the prior peer gap"
                ),
            }
        )
    return summary_rows


def write_summary(rows: list[dict[str, str]]) -> None:
    OUTPUT_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "row_type",
        "peer_group_id",
        "balanced_row_count",
        "balanced_peer_group_count",
        "balanced_country_cell_count",
        "balanced_rank_eligible_row_count",
        "balanced_korean_firm_count",
        "balanced_global_firm_count",
        "balanced_korean_mean_composite",
        "balanced_global_mean_composite",
        "balanced_korea_minus_global_gap",
        "previous_unbalanced_gap",
        "gap_change_vs_unbalanced",
        "best_korean_firm_std",
        "best_global_firm_std",
        "korean_fallback_firm_count",
        "gap_changed_flag",
        "interpretation_note",
    ]
    with OUTPUT_SUMMARY_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    balanced_rows = build_balanced_rows()
    write_balanced_panel(balanced_rows)
    write_summary(build_summary_rows(balanced_rows))


if __name__ == "__main__":
    main()
