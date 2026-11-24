from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

COMPOSITE_PATH = (
    PROJECT_ROOT
    / "data/processed/claim_strengthening/reverse_discrimination_composite_narrow.csv"
)
OUTPUT_PATH = (
    PROJECT_ROOT / "outputs/tables/claim_strengthening/T_claim_peer_rank.csv"
)


def is_korean_role(role: str) -> bool:
    return role.startswith("korean")


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def load_rows() -> dict[tuple[str, str], list[dict[str, str]]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    with COMPOSITE_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            grouped[(row["peer_group_id"], row["firm_std"])].append(row)
    return grouped


def choose_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], str]:
    eligible = [
        row for row in rows if row["composite_rank_eligible_flag"] == "yes" and row["composite_narrow"]
    ]
    if eligible:
        return eligible, "eligible_mean"
    observed = [row for row in rows if row["composite_narrow"]]
    return observed, "all_row_mean_fallback"


def build_table() -> list[dict[str, str]]:
    grouped = load_rows()
    peer_rows: dict[str, list[dict[str, str]]] = defaultdict(list)

    for (peer_group_id, firm_std), rows in grouped.items():
        selected_rows, ranking_basis = choose_rows(rows)
        composite_value = mean(
            [float(row["composite_narrow"]) for row in selected_rows if row["composite_narrow"]]
        )
        analysis_roles = {row["analysis_role"] for row in rows}
        korean_flag = "yes" if any(is_korean_role(role) for role in analysis_roles) else "no"

        peer_rows[peer_group_id].append(
            {
                "peer_group_id": peer_group_id,
                "firm_std": firm_std,
                "composite_narrow": f"{composite_value:.6f}",
                "ranking_basis": ranking_basis,
                "country_cells_used_count": str(len(selected_rows)),
                "country_cells_used": "|".join(row["country_std"] for row in selected_rows),
                "rank_eligible_cell_count": str(
                    sum(1 for row in rows if row["composite_rank_eligible_flag"] == "yes")
                ),
                "all_observed_cell_count": str(sum(1 for row in rows if row["composite_narrow"])),
                "korean_firm_flag": korean_flag,
            }
        )

    final_rows: list[dict[str, str]] = []
    for peer_group_id, rows in peer_rows.items():
        rows.sort(key=lambda row: (-float(row["composite_narrow"]), row["firm_std"]))
        best_value = float(rows[0]["composite_narrow"])
        global_rows = [row for row in rows if row["korean_firm_flag"] == "no"]
        global_mean = mean([float(row["composite_narrow"]) for row in global_rows])

        current_rank = 0
        prev_value = None
        for idx, row in enumerate(rows, start=1):
            value = float(row["composite_narrow"])
            if prev_value is None or value < prev_value:
                current_rank = idx
            prev_value = value
            enriched = dict(row)
            enriched["rank_within_peer"] = str(current_rank)
            enriched["distance_from_best"] = f"{(best_value - value):.6f}"
            enriched["distance_from_global_peer_mean"] = f"{(value - global_mean):.6f}"
            enriched["global_peer_mean_composite"] = f"{global_mean:.6f}"
            final_rows.append(enriched)

    final_rows.sort(key=lambda row: (row["peer_group_id"], int(row["rank_within_peer"]), row["firm_std"]))
    return final_rows


def write_table(rows: list[dict[str, str]]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "peer_group_id",
        "firm_std",
        "composite_narrow",
        "rank_within_peer",
        "distance_from_best",
        "distance_from_global_peer_mean",
        "global_peer_mean_composite",
        "ranking_basis",
        "country_cells_used_count",
        "country_cells_used",
        "rank_eligible_cell_count",
        "all_observed_cell_count",
        "korean_firm_flag",
    ]
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rows = build_table()
    write_table(rows)


if __name__ == "__main__":
    main()
