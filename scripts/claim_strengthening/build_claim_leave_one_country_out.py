from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT / "data/processed/claim_strengthening/reverse_discrimination_balanced_panel.csv"
)
OUTPUT_TABLE_PATH = (
    PROJECT_ROOT / "outputs/tables/claim_strengthening/T_claim_leave_one_country_out.csv"
)
OUTPUT_LOG_PATH = (
    PROJECT_ROOT / "logs/claim_strengthening/leave_one_country_out_log.md"
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def is_korean_role(role: str) -> bool:
    return role.startswith("korean")


def gap_sign(value: float) -> str:
    if value > 0:
        return "korean_higher"
    if value < 0:
        return "global_higher"
    return "tie"


def collapse_firm_level(rows: list[dict[str, str]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["peer_group_id"], row["firm_std"])].append(row)

    peer_rows: dict[str, list[dict[str, object]]] = defaultdict(list)
    for (peer_group_id, firm_std), items in grouped.items():
        eligible = [
            row
            for row in items
            if row["composite_rank_eligible_flag"] == "yes" and row["composite_narrow"] != ""
        ]
        chosen = eligible if eligible else [row for row in items if row["composite_narrow"] != ""]
        if not chosen:
            continue

        peer_rows[peer_group_id].append(
            {
                "firm_std": firm_std,
                "korean_firm_flag": "yes"
                if any(is_korean_role(row["analysis_role"]) for row in items)
                else "no",
                "composite_narrow": mean([float(row["composite_narrow"]) for row in chosen]),
                "ranking_basis": "eligible_mean" if eligible else "all_row_mean_fallback",
                "country_cells_used": "|".join(sorted({row["country_std"] for row in chosen})),
                "country_cells_used_count": len({row["country_std"] for row in chosen}),
            }
        )

    for peer_group_id, items in peer_rows.items():
        items.sort(key=lambda row: (-float(row["composite_narrow"]), str(row["firm_std"])))
    return peer_rows


def build_peer_summary(rows: list[dict[str, str]]) -> dict[str, dict[str, object]]:
    firm_level = collapse_firm_level(rows)
    summaries: dict[str, dict[str, object]] = {}
    for peer_group_id, peer_rows in firm_level.items():
        korean_rows = [row for row in peer_rows if row["korean_firm_flag"] == "yes"]
        global_rows = [row for row in peer_rows if row["korean_firm_flag"] == "no"]
        row_count = sum(1 for row in rows if row["peer_group_id"] == peer_group_id)
        country_count = len(
            {(row["peer_group_id"], row["country_std"]) for row in rows if row["peer_group_id"] == peer_group_id}
        )
        eligible_count = sum(
            1
            for row in rows
            if row["peer_group_id"] == peer_group_id and row["composite_rank_eligible_flag"] == "yes"
        )

        if not korean_rows or not global_rows:
            summaries[peer_group_id] = {
                "analysis_status": "not_estimable_after_country_drop",
                "remaining_row_count": row_count,
                "remaining_country_cell_count": country_count,
                "remaining_rank_eligible_row_count": eligible_count,
                "remaining_korean_firm_count": len(korean_rows),
                "remaining_global_firm_count": len(global_rows),
                "korean_mean_composite": "",
                "global_mean_composite": "",
                "korea_minus_global_gap": "",
                "gap_sign": "",
                "peer_top_firm_std": "",
                "peer_top_composite": "",
                "best_korean_firm_std": "",
                "best_korean_composite": "",
                "best_global_firm_std": "",
                "best_global_composite": "",
                "korean_fallback_firm_count": "",
                "global_fallback_firm_count": "",
                "peer_top_ranking_basis": "",
                "best_korean_ranking_basis": "",
                "best_global_ranking_basis": "",
                "interpretation_note": "No Korean or no global firm remains after omitting this country.",
            }
            continue

        korean_mean = mean([float(row["composite_narrow"]) for row in korean_rows])
        global_mean = mean([float(row["composite_narrow"]) for row in global_rows])
        gap = korean_mean - global_mean
        peer_top = peer_rows[0]
        best_korean = korean_rows[0]
        best_global = global_rows[0]

        summaries[peer_group_id] = {
            "analysis_status": "estimable",
            "remaining_row_count": row_count,
            "remaining_country_cell_count": country_count,
            "remaining_rank_eligible_row_count": eligible_count,
            "remaining_korean_firm_count": len(korean_rows),
            "remaining_global_firm_count": len(global_rows),
            "korean_mean_composite": f"{korean_mean:.6f}",
            "global_mean_composite": f"{global_mean:.6f}",
            "korea_minus_global_gap": f"{gap:.6f}",
            "gap_sign": gap_sign(gap),
            "peer_top_firm_std": str(peer_top["firm_std"]),
            "peer_top_composite": f"{float(peer_top['composite_narrow']):.6f}",
            "best_korean_firm_std": str(best_korean["firm_std"]),
            "best_korean_composite": f"{float(best_korean['composite_narrow']):.6f}",
            "best_global_firm_std": str(best_global["firm_std"]),
            "best_global_composite": f"{float(best_global['composite_narrow']):.6f}",
            "korean_fallback_firm_count": str(
                sum(1 for row in korean_rows if row["ranking_basis"] == "all_row_mean_fallback")
            ),
            "global_fallback_firm_count": str(
                sum(1 for row in global_rows if row["ranking_basis"] == "all_row_mean_fallback")
            ),
            "peer_top_ranking_basis": str(peer_top["ranking_basis"]),
            "best_korean_ranking_basis": str(best_korean["ranking_basis"]),
            "best_global_ranking_basis": str(best_global["ranking_basis"]),
            "interpretation_note": "Peer remains estimable after country omission.",
        }
    return summaries


def build_table_rows() -> list[dict[str, str]]:
    base_rows = read_csv(INPUT_PATH)
    baseline = build_peer_summary(base_rows)
    countries = sorted({row["country_std"] for row in base_rows})
    peer_group_ids = sorted({row["peer_group_id"] for row in base_rows})

    rows: list[dict[str, str]] = []
    for omitted_country in countries:
        kept_rows = [row for row in base_rows if row["country_std"] != omitted_country]
        scenario = build_peer_summary(kept_rows)

        estimable_peer_count = 0
        sign_preserved_count = 0
        peer_top_preserved_count = 0
        best_korean_preserved_count = 0

        for peer_group_id in peer_group_ids:
            base = baseline[peer_group_id]
            current = scenario.get(
                peer_group_id,
                {
                    "analysis_status": "not_estimable_after_country_drop",
                    "remaining_row_count": 0,
                    "remaining_country_cell_count": 0,
                    "remaining_rank_eligible_row_count": 0,
                    "remaining_korean_firm_count": 0,
                    "remaining_global_firm_count": 0,
                    "korean_mean_composite": "",
                    "global_mean_composite": "",
                    "korea_minus_global_gap": "",
                    "gap_sign": "",
                    "peer_top_firm_std": "",
                    "peer_top_composite": "",
                    "best_korean_firm_std": "",
                    "best_korean_composite": "",
                    "best_global_firm_std": "",
                    "best_global_composite": "",
                    "korean_fallback_firm_count": "",
                    "global_fallback_firm_count": "",
                    "peer_top_ranking_basis": "",
                    "best_korean_ranking_basis": "",
                    "best_global_ranking_basis": "",
                    "interpretation_note": "Peer disappears after country omission.",
                },
            )

            sign_preserved = ""
            peer_top_preserved = ""
            best_korean_preserved = ""
            if current["analysis_status"] == "estimable":
                estimable_peer_count += 1
                sign_preserved = "yes" if current["gap_sign"] == base["gap_sign"] else "no"
                peer_top_preserved = (
                    "yes" if current["peer_top_firm_std"] == base["peer_top_firm_std"] else "no"
                )
                best_korean_preserved = (
                    "yes"
                    if current["best_korean_firm_std"] == base["best_korean_firm_std"]
                    else "no"
                )
                sign_preserved_count += 1 if sign_preserved == "yes" else 0
                peer_top_preserved_count += 1 if peer_top_preserved == "yes" else 0
                best_korean_preserved_count += 1 if best_korean_preserved == "yes" else 0

            gap_change = ""
            if current["analysis_status"] == "estimable":
                gap_change = (
                    f"{float(current['korea_minus_global_gap']) - float(base['korea_minus_global_gap']):.6f}"
                )

            interpretation_note = current["interpretation_note"]
            if current["analysis_status"] == "estimable" and peer_top_preserved == "no":
                interpretation_note = "Gap sign survives but peer-top firm changes after country omission."
            elif current["analysis_status"] == "estimable" and sign_preserved == "yes":
                interpretation_note = "Gap sign and ranking remain aligned with the balanced baseline."

            rows.append(
                {
                    "row_type": "peer_summary",
                    "omitted_country_std": omitted_country,
                    "peer_group_id": peer_group_id,
                    "analysis_status": str(current["analysis_status"]),
                    "remaining_row_count": str(current["remaining_row_count"]),
                    "remaining_country_cell_count": str(current["remaining_country_cell_count"]),
                    "remaining_rank_eligible_row_count": str(current["remaining_rank_eligible_row_count"]),
                    "remaining_korean_firm_count": str(current["remaining_korean_firm_count"]),
                    "remaining_global_firm_count": str(current["remaining_global_firm_count"]),
                    "baseline_gap": str(base["korea_minus_global_gap"]),
                    "recomputed_gap": str(current["korea_minus_global_gap"]),
                    "gap_change_vs_baseline": gap_change,
                    "baseline_gap_sign": str(base["gap_sign"]),
                    "recomputed_gap_sign": str(current["gap_sign"]),
                    "gap_sign_preserved_flag": sign_preserved,
                    "baseline_peer_top_firm_std": str(base["peer_top_firm_std"]),
                    "recomputed_peer_top_firm_std": str(current["peer_top_firm_std"]),
                    "peer_top_rank_preserved_flag": peer_top_preserved,
                    "baseline_best_korean_firm_std": str(base["best_korean_firm_std"]),
                    "recomputed_best_korean_firm_std": str(current["best_korean_firm_std"]),
                    "best_korean_rank_preserved_flag": best_korean_preserved,
                    "baseline_best_global_firm_std": str(base["best_global_firm_std"]),
                    "recomputed_best_global_firm_std": str(current["best_global_firm_std"]),
                    "baseline_korean_mean_composite": str(base["korean_mean_composite"]),
                    "recomputed_korean_mean_composite": str(current["korean_mean_composite"]),
                    "baseline_global_mean_composite": str(base["global_mean_composite"]),
                    "recomputed_global_mean_composite": str(current["global_mean_composite"]),
                    "recomputed_korean_fallback_firm_count": str(current["korean_fallback_firm_count"]),
                    "recomputed_global_fallback_firm_count": str(current["global_fallback_firm_count"]),
                    "recomputed_peer_top_ranking_basis": str(current["peer_top_ranking_basis"]),
                    "recomputed_best_korean_ranking_basis": str(current["best_korean_ranking_basis"]),
                    "recomputed_best_global_ranking_basis": str(current["best_global_ranking_basis"]),
                    "interpretation_note": interpretation_note,
                }
            )

        rows.append(
            {
                "row_type": "overall",
                "omitted_country_std": omitted_country,
                "peer_group_id": "",
                "analysis_status": "overall_summary",
                "remaining_row_count": str(len(kept_rows)),
                "remaining_country_cell_count": str(len({row["country_std"] for row in kept_rows})),
                "remaining_rank_eligible_row_count": str(
                    sum(1 for row in kept_rows if row["composite_rank_eligible_flag"] == "yes")
                ),
                "remaining_korean_firm_count": str(
                    len({row["firm_std"] for row in kept_rows if is_korean_role(row["analysis_role"])})
                ),
                "remaining_global_firm_count": str(
                    len({row["firm_std"] for row in kept_rows if not is_korean_role(row["analysis_role"])})
                ),
                "baseline_gap": "",
                "recomputed_gap": "",
                "gap_change_vs_baseline": "",
                "baseline_gap_sign": "",
                "recomputed_gap_sign": "",
                "gap_sign_preserved_flag": f"{sign_preserved_count}/{estimable_peer_count}",
                "baseline_peer_top_firm_std": "",
                "recomputed_peer_top_firm_std": "",
                "peer_top_rank_preserved_flag": f"{peer_top_preserved_count}/{estimable_peer_count}",
                "baseline_best_korean_firm_std": "",
                "recomputed_best_korean_firm_std": "",
                "best_korean_rank_preserved_flag": f"{best_korean_preserved_count}/{estimable_peer_count}",
                "baseline_best_global_firm_std": "",
                "recomputed_best_global_firm_std": "",
                "baseline_korean_mean_composite": "",
                "recomputed_korean_mean_composite": "",
                "baseline_global_mean_composite": "",
                "recomputed_global_mean_composite": "",
                "recomputed_korean_fallback_firm_count": "",
                "recomputed_global_fallback_firm_count": "",
                "recomputed_peer_top_ranking_basis": "",
                "recomputed_best_korean_ranking_basis": "",
                "recomputed_best_global_ranking_basis": "",
                "interpretation_note": (
                    f"{estimable_peer_count} estimable peers remain; "
                    f"gap sign preserved in {sign_preserved_count}; "
                    f"peer-top rank preserved in {peer_top_preserved_count}; "
                    f"best-Korean rank preserved in {best_korean_preserved_count}."
                ),
            }
        )

    rows.sort(
        key=lambda row: (
            row["omitted_country_std"],
            0 if row["row_type"] == "overall" else 1,
            row["peer_group_id"],
        )
    )
    return rows


def write_table(rows: list[dict[str, str]]) -> None:
    OUTPUT_TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "row_type",
        "omitted_country_std",
        "peer_group_id",
        "analysis_status",
        "remaining_row_count",
        "remaining_country_cell_count",
        "remaining_rank_eligible_row_count",
        "remaining_korean_firm_count",
        "remaining_global_firm_count",
        "baseline_gap",
        "recomputed_gap",
        "gap_change_vs_baseline",
        "baseline_gap_sign",
        "recomputed_gap_sign",
        "gap_sign_preserved_flag",
        "baseline_peer_top_firm_std",
        "recomputed_peer_top_firm_std",
        "peer_top_rank_preserved_flag",
        "baseline_best_korean_firm_std",
        "recomputed_best_korean_firm_std",
        "best_korean_rank_preserved_flag",
        "baseline_best_global_firm_std",
        "recomputed_best_global_firm_std",
        "baseline_korean_mean_composite",
        "recomputed_korean_mean_composite",
        "baseline_global_mean_composite",
        "recomputed_global_mean_composite",
        "recomputed_korean_fallback_firm_count",
        "recomputed_global_fallback_firm_count",
        "recomputed_peer_top_ranking_basis",
        "recomputed_best_korean_ranking_basis",
        "recomputed_best_global_ranking_basis",
        "interpretation_note",
    ]
    with OUTPUT_TABLE_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_log(rows: list[dict[str, str]]) -> None:
    peer_rows = [row for row in rows if row["row_type"] == "peer_summary"]
    overall_rows = [row for row in rows if row["row_type"] == "overall"]

    total_estimable = sum(
        1 for row in peer_rows if row["analysis_status"] == "estimable"
    )
    sign_preserved = sum(
        1 for row in peer_rows if row["gap_sign_preserved_flag"] == "yes"
    )
    peer_top_preserved = sum(
        1 for row in peer_rows if row["peer_top_rank_preserved_flag"] == "yes"
    )
    best_korean_preserved = sum(
        1 for row in peer_rows if row["best_korean_rank_preserved_flag"] == "yes"
    )

    lines = [
        "# Strength Prompt 46. Leave-One-Country-Out Analysis",
        "",
        "## Summary",
        f"- Omitted countries analyzed: {', '.join(row['omitted_country_std'] for row in overall_rows)}",
        f"- Estimable peer checks: {total_estimable}",
        f"- Gap sign preserved: {sign_preserved}/{total_estimable}",
        f"- Peer-top rank preserved: {peer_top_preserved}/{total_estimable}",
        f"- Best-Korean rank preserved: {best_korean_preserved}/{total_estimable}",
        "",
        "## Country-Level Notes",
    ]

    for overall in overall_rows:
        omitted_country = overall["omitted_country_std"]
        subset = [row for row in peer_rows if row["omitted_country_std"] == omitted_country]
        estimable_subset = [row for row in subset if row["analysis_status"] == "estimable"]
        not_estimable_subset = [
            row for row in subset if row["analysis_status"] != "estimable"
        ]
        lines.append(f"- `{omitted_country}` omission:")
        lines.append(f"  estimable peers `{len(estimable_subset)}/{len(subset)}`")
        lines.append(
            f"  sign preserved `{sum(1 for row in estimable_subset if row['gap_sign_preserved_flag'] == 'yes')}/{len(estimable_subset)}`"
        )
        lines.append(
            f"  peer-top preserved `{sum(1 for row in estimable_subset if row['peer_top_rank_preserved_flag'] == 'yes')}/{len(estimable_subset)}`"
        )
        if not_estimable_subset:
            lines.append(
                "  non-estimable peers: "
                + ", ".join(row["peer_group_id"] for row in not_estimable_subset)
            )
        changed_top = [
            row["peer_group_id"] for row in estimable_subset if row["peer_top_rank_preserved_flag"] == "no"
        ]
        if changed_top:
            lines.append("  changed peer-top rank: " + ", ".join(changed_top))

    lines.extend(
        [
            "",
            "## Interpretation",
            "- `jp` and `us` omissions leave all three peer groups estimable and preserve both gap sign and peer-top ordering.",
            "- Omitting `kr` removes all estimable rows from `infra_traffic_ott` and `mus_streaming_paid_core` because those balanced peers are Korea-only cells.",
            "- Under `kr` omission, `mus_label_ip_export` remains estimable and keeps a negative Korea-minus-global gap, but peer-top changes from `warner_music` to `jyp_ent` because only the thinner `jp/us` risk-only rows remain.",
            "- Therefore the current claim-strengthening conclusion is not fully country-robust at the peer-top ranking level even though the surviving estimable gaps do not flip sign.",
            "",
        ]
    )

    OUTPUT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_LOG_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    rows = build_table_rows()
    write_table(rows)
    write_log(rows)


if __name__ == "__main__":
    main()
