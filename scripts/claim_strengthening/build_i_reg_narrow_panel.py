from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CORE_SAMPLE_PATH = (
    PROJECT_ROOT
    / "data/registry/claim_strengthening/reverse_discrimination_core_sample_v1.csv"
)
BURDEN_PANEL_PATH = (
    PROJECT_ROOT
    / "data/processed/claim_strengthening/direct_regulatory_burden_panel.csv"
)
OUTPUT_PATH = (
    PROJECT_ROOT / "data/processed/claim_strengthening/i_reg_narrow_panel.csv"
)
LOG_PATH = PROJECT_ROOT / "logs/claim_strengthening/i_reg_narrow_log.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def normalize_role(role: str) -> str:
    if role.startswith("korean_"):
        return "korean"
    if role.startswith("global_"):
        return "global"
    return "other"


def main() -> None:
    core_rows = [row for row in read_csv(CORE_SAMPLE_PATH) if row["include_flag"] == "yes"]
    burden_rows = read_csv(BURDEN_PANEL_PATH)

    burden_map = {
        (
            row["peer_group_id"],
            row["firm_std"],
            row["service_std"],
            row["country_std"],
        ): row
        for row in burden_rows
    }

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in core_rows:
        grouped[row["peer_group_id"]].append(row)

    output_rows: list[dict[str, str]] = []
    status_counter: Counter[str] = Counter()
    peer_ready_counter: Counter[str] = Counter()

    for peer_group_id, peer_rows in sorted(grouped.items()):
        observed_rows: list[dict[str, str]] = []
        peer_side_observed = {"korean": False, "global": False}

        for row in peer_rows:
            key = (
                row["peer_group_id"],
                row["firm_std"],
                row["service_std"],
                row["country_std"],
            )
            burden_row = burden_map.get(key)
            if burden_row is not None:
                observed_rows.append(burden_row)
                peer_side_observed[normalize_role(row["analysis_role"])] = True

        observed_intensities = [
            float(row["obligation_intensity_score"]) for row in observed_rows
        ]
        peer_observed_row_count = len(observed_rows)
        peer_full_coverage_flag = "yes" if peer_observed_row_count == len(peer_rows) else "no"
        peer_has_variation_flag = (
            "yes"
            if observed_intensities and max(observed_intensities) > min(observed_intensities)
            else "no"
        )
        peer_has_cross_side_observed_flag = (
            "yes" if peer_side_observed["korean"] and peer_side_observed["global"] else "no"
        )
        peer_min_intensity = min(observed_intensities) if observed_intensities else None
        peer_max_intensity = max(observed_intensities) if observed_intensities else None
        peer_ready_flag = (
            "yes"
            if (
                peer_has_cross_side_observed_flag == "yes"
                and peer_full_coverage_flag == "yes"
                and peer_has_variation_flag == "yes"
            )
            else "no"
        )
        peer_ready_counter[peer_ready_flag] += 1

        observed_rank_count = len(
            {
                burden_map[
                    (r["peer_group_id"], r["firm_std"], r["service_std"], r["country_std"])
                ]["burden_rank_within_peer"]
                for r in peer_rows
                if (
                    r["peer_group_id"],
                    r["firm_std"],
                    r["service_std"],
                    r["country_std"],
                )
                in burden_map
            }
        )

        for row in peer_rows:
            key = (
                row["peer_group_id"],
                row["firm_std"],
                row["service_std"],
                row["country_std"],
            )
            burden_row = burden_map.get(key)
            observed_flag = "yes" if burden_row is not None else "no"

            if observed_flag == "no":
                status = "direct_missing"
                note = "No service-country direct obligation row exists under the current direct source set."
            elif peer_ready_flag == "yes":
                status = "ready_direct_relative_score"
                note = "Peer has full direct coverage, cross-side observation, and non-zero variation."
            elif peer_has_cross_side_observed_flag == "yes" and peer_has_variation_flag == "no":
                status = "direct_observed_no_signal"
                note = "Direct rows exist on both sides, but all observed burden scores are tied at zero."
            else:
                status = "direct_observed_partial_peer"
                note = "Direct row exists, but the peer lacks full cross-side direct coverage for a narrow score."

            status_counter[status] += 1

            obligation_count = burden_row["obligation_count"] if burden_row else ""
            obligation_intensity_score = (
                burden_row["obligation_intensity_score"] if burden_row else ""
            )
            enforced_obligation_score = (
                burden_row["enforced_obligation_score"] if burden_row else ""
            )
            same_peer_relative_rank = (
                burden_row["burden_rank_within_peer"] if burden_row else ""
            )

            i_reg_narrow = ""
            absolute_gap_from_peer_max = ""
            absolute_gap_from_peer_min = ""
            relative_position_pct = ""

            if peer_ready_flag == "yes" and burden_row is not None:
                intensity_value = float(burden_row["obligation_intensity_score"])
                assert peer_min_intensity is not None
                assert peer_max_intensity is not None
                denom = peer_max_intensity - peer_min_intensity
                relative_pct_value = 100.0 * (intensity_value - peer_min_intensity) / denom
                i_reg_narrow = f"{relative_pct_value:.6f}"
                relative_position_pct = f"{relative_pct_value:.6f}"
                absolute_gap_from_peer_max = f"{peer_max_intensity - intensity_value:.6f}"
                absolute_gap_from_peer_min = f"{intensity_value - peer_min_intensity:.6f}"

            output_rows.append(
                {
                    "peer_group_id": row["peer_group_id"],
                    "firm_std": row["firm_std"],
                    "service_std": row["service_std"],
                    "country_std": row["country_std"],
                    "analysis_role": row["analysis_role"],
                    "direct_obligation_observed_flag": observed_flag,
                    "obligation_count": obligation_count,
                    "obligation_intensity_score": obligation_intensity_score,
                    "enforced_obligation_score": enforced_obligation_score,
                    "same_peer_relative_rank": same_peer_relative_rank,
                    "same_peer_relative_rank_count": str(observed_rank_count),
                    "same_peer_relative_position_pct": relative_position_pct,
                    "absolute_gap_from_peer_max": absolute_gap_from_peer_max,
                    "absolute_gap_from_peer_min": absolute_gap_from_peer_min,
                    "peer_observed_row_count": str(peer_observed_row_count),
                    "peer_total_core_row_count": str(len(peer_rows)),
                    "peer_full_direct_coverage_flag": peer_full_coverage_flag,
                    "peer_has_cross_side_observed_flag": peer_has_cross_side_observed_flag,
                    "peer_has_variation_flag": peer_has_variation_flag,
                    "peer_ready_flag": peer_ready_flag,
                    "i_reg_narrow": i_reg_narrow,
                    "i_reg_narrow_status": status,
                    "construction_note": note,
                }
            )

    fieldnames = [
        "peer_group_id",
        "firm_std",
        "service_std",
        "country_std",
        "analysis_role",
        "direct_obligation_observed_flag",
        "obligation_count",
        "obligation_intensity_score",
        "enforced_obligation_score",
        "same_peer_relative_rank",
        "same_peer_relative_rank_count",
        "same_peer_relative_position_pct",
        "absolute_gap_from_peer_max",
        "absolute_gap_from_peer_min",
        "peer_observed_row_count",
        "peer_total_core_row_count",
        "peer_full_direct_coverage_flag",
        "peer_has_cross_side_observed_flag",
        "peer_has_variation_flag",
        "peer_ready_flag",
        "i_reg_narrow",
        "i_reg_narrow_status",
        "construction_note",
    ]
    write_csv(OUTPUT_PATH, output_rows, fieldnames)

    ready_rows = [row for row in output_rows if row["peer_ready_flag"] == "yes"]
    ready_with_score_rows = [row for row in output_rows if row["i_reg_narrow"]]

    log_lines = [
        "# Strength Prompt 19. 역차별 주장용 I_reg 협의 버전 계산",
        "",
        "- `i_reg_narrow_panel.csv`는 core sample v1만 남긴 뒤 `direct_regulatory_burden_panel.csv`를 left join해 direct obligation 기준 협의 규제부담 지표를 계산한 결과다.",
        "- 협의 `I_reg_narrow`는 peer 내부 직접 burden 강도 합계(`obligation_intensity_score`)를 0~100으로 재척도화한 값이며, full direct coverage와 cross-side observation, 비영점 variation이 동시에 있을 때만 계산한다.",
        "- direct source 부재 또는 all-zero tie 상황에서는 점수를 억지로 채우지 않고 `i_reg_narrow_status`에 결측 사유를 남긴다.",
        "",
        f"- total core rows: `{len(output_rows)}`",
        f"- peer ready rows: `{len(ready_rows)}`",
        f"- rows with nonmissing `i_reg_narrow`: `{len(ready_with_score_rows)}`",
        f"- peer ready flag distribution: `yes {peer_ready_counter['yes']}`, `no {peer_ready_counter['no']}`",
        "",
        "## Status distribution",
        "",
    ]

    for status in sorted(status_counter):
        log_lines.append(f"- `{status}`: `{status_counter[status]}`")

    log_lines.extend(
        [
            "",
            "## Peer interpretation",
            "",
            "- 현재 core peer 중 full direct coverage와 cross-side variation을 동시에 만족하는 그룹은 없어 협의 `I_reg_narrow` 비결측 행이 `0`이다.",
            "- `infra_traffic_ott`는 한국 통신 3사의 direct burden row는 있으나 `Netflix`의 `kr` service-country direct obligation row가 없어 partial peer로 남는다.",
            "- `mus_streaming_paid_core`는 한국 `flo`, `melon`의 direct burden row는 있으나 `Spotify`의 `kr` service-country direct obligation row가 없어 partial peer로 남는다.",
            "- `mus_label_ip_export`는 direct row 일부가 존재하지만 관측 burden가 전부 `0`이거나 일부 country-service row가 비어 있어 direct no-signal 또는 direct missing으로 남는다.",
        ]
    )

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
