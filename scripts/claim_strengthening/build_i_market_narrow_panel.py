from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CORE_SAMPLE_PATH = (
    PROJECT_ROOT
    / "data/registry/claim_strengthening/reverse_discrimination_core_sample_v1.csv"
)
TRANSFER_PATH = (
    PROJECT_ROOT
    / "data/processed/claim_strengthening/cross_market_transfer_matched_panel.csv"
)
SWITCHING_PATH = (
    PROJECT_ROOT
    / "data/processed/claim_strengthening/switching_cost_narrow_panel.csv"
)
CONCENTRATION_PATH = (
    PROJECT_ROOT
    / "data/processed/claim_strengthening/concentration_decomposition_table.csv"
)
OUTPUT_PANEL_PATH = (
    PROJECT_ROOT
    / "data/processed/claim_strengthening/i_market_narrow_panel.csv"
)
OUTPUT_LOG_PATH = (
    PROJECT_ROOT / "logs/claim_strengthening/i_market_narrow_log.md"
)


def is_korean_role(role: str) -> bool:
    return role.startswith("korean")


def load_core_rows() -> list[dict[str, str]]:
    with CORE_SAMPLE_PATH.open(newline="", encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle) if row["include_flag"] == "yes"]


def load_transfer_rows():
    keyed: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    max_support_gap = 0.0
    with TRANSFER_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["comparability_flag"] != "yes":
                continue
            key = (
                row["peer_group_id"],
                row["firm_std"],
                row["service_std"],
                row["country_std"],
            )
            keyed[key].append(row)

            gap = float(row["korean_minus_global_gap"])
            if is_korean_role(row["analysis_role"]):
                support_gap = max(0.0, gap)
            else:
                support_gap = max(0.0, -gap)
            max_support_gap = max(max_support_gap, support_gap)
    return keyed, max_support_gap


def load_switching_rows():
    keyed: dict[tuple[str, str, str, str], dict[str, str]] = {}
    with SWITCHING_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = (
                row["peer_group_id"],
                row["firm_std"],
                row["service_std"],
                row["country_std"],
            )
            keyed[key] = row
    return keyed


def load_latest_concentration_rows():
    keyed: dict[tuple[str, str], dict[str, str]] = {}
    with CONCENTRATION_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["latest_period_flag"] != "yes":
                continue
            if row["decomposition_status"] != "direct_chart_proxy_market":
                continue
            keyed[(row["peer_group_id"], row["country_std"])] = row
    return keyed


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def build_rows() -> list[dict[str, str]]:
    core_rows = load_core_rows()
    transfer_rows, max_support_gap = load_transfer_rows()
    switching_rows = load_switching_rows()
    concentration_rows = load_latest_concentration_rows()

    output_rows: list[dict[str, str]] = []

    for core in core_rows:
        key = (
            core["peer_group_id"],
            core["firm_std"],
            core["service_std"],
            core["country_std"],
        )
        role = core["analysis_role"]
        korean_role = is_korean_role(role)

        transfer_obs = transfer_rows.get(key, [])
        transfer_periods = sorted(row["panel_time_key"] for row in transfer_obs)
        transfer_gap_values = [float(row["korean_minus_global_gap"]) for row in transfer_obs]
        transfer_index_values = [
            float(row["cross_market_transfer_index"]) for row in transfer_obs
        ]
        transfer_position_values = [
            float(row["relative_position_pct"]) for row in transfer_obs
        ]
        transfer_support_gaps = []
        for gap in transfer_gap_values:
            if korean_role:
                transfer_support_gaps.append(max(0.0, gap))
            else:
                transfer_support_gaps.append(max(0.0, -gap))
        if transfer_support_gaps and max_support_gap > 0:
            transfer_component_score = (
                mean(transfer_support_gaps) / max_support_gap * 100.0
            )
        else:
            transfer_component_score = None

        switching = switching_rows.get(key)
        switching_component_score = None
        switching_signal_count = ""
        switching_status = ""
        switching_erosion_flag = ""
        if switching:
            switching_status = switching["switching_cost_narrow_status"]
            switching_signal_count = switching["switching_cost_signal_count"]
            switching_erosion_flag = switching["local_share_erosion_flag"]
            if switching_status != "not_applicable_content_ip_peer":
                signal_count = float(switching["switching_cost_signal_count"] or 0.0)
                switching_component_score = min(
                    100.0,
                    signal_count / 4.0 * 100.0
                    + (25.0 if switching["local_share_erosion_flag"] == "yes" else 0.0),
                )

        concentration = concentration_rows.get((core["peer_group_id"], core["country_std"]))
        concentration_component_score = None
        concentration_period_key = ""
        concentration_proxy_scope = ""
        concentration_local_hhi_component = ""
        concentration_global_hhi_component = ""
        concentration_market_gap = ""
        if concentration:
            local_hhi = float(concentration["local_hhi_component"])
            global_hhi = float(concentration["global_hhi_component"])
            total_hhi = local_hhi + global_hhi
            concentration_period_key = concentration["period_key"]
            concentration_proxy_scope = concentration["proxy_scope"]
            concentration_local_hhi_component = concentration["local_hhi_component"]
            concentration_global_hhi_component = concentration["global_hhi_component"]
            concentration_market_gap = concentration["local_minus_global_hhi_gap"]
            if total_hhi > 0:
                if korean_role:
                    burden_share = max(0.0, global_hhi - local_hhi) / total_hhi
                else:
                    burden_share = max(0.0, local_hhi - global_hhi) / total_hhi
                concentration_component_score = burden_share * 25.0

        observed_scores = [
            score
            for score in [
                transfer_component_score,
                switching_component_score,
                concentration_component_score,
            ]
            if score is not None
        ]

        observed_component_count = len(observed_scores)
        if observed_component_count:
            i_market_narrow = mean(observed_scores)
        else:
            i_market_narrow = None

        if observed_component_count >= 3:
            status = "stronger_direct_market_coverage"
        elif observed_component_count == 2:
            status = "partial_direct_market_coverage"
        elif observed_component_count == 1:
            status = "thin_direct_market_coverage"
        else:
            status = "no_direct_market_coverage"

        notes = []
        if transfer_component_score is not None:
            if korean_role and mean(transfer_support_gaps) == 0.0:
                notes.append("transfer gap does not favor Korean-burden interpretation")
            elif (not korean_role) and mean(transfer_support_gaps) > 0.0:
                notes.append("transfer gap favors global-row burden instead of Korean-row burden")
        if switching_component_score is not None:
            if switching_erosion_flag == "yes":
                notes.append("observed local share erosion supports switching pressure")
            elif switching_status == "partial_country_multihoming_only":
                notes.append("country multihoming only")
        if concentration_component_score is not None and concentration_component_score == 0.0:
            notes.append("local concentration dominates observed proxy market")
        if observed_component_count == 0:
            notes.append("no usable narrow market component under current direct source set")

        output_rows.append(
            {
                "peer_group_id": core["peer_group_id"],
                "firm_std": core["firm_std"],
                "service_std": core["service_std"],
                "country_std": core["country_std"],
                "analysis_role": role,
                "observed_component_count": str(observed_component_count),
                "transfer_period_count": str(len(transfer_obs)),
                "transfer_periods_observed": "|".join(transfer_periods),
                "transfer_index_mean": (
                    f"{mean(transfer_index_values):.9f}" if transfer_obs else ""
                ),
                "transfer_relative_position_pct_mean": (
                    f"{mean(transfer_position_values):.6f}" if transfer_obs else ""
                ),
                "transfer_role_support_gap_mean": (
                    f"{mean(transfer_support_gaps):.9f}" if transfer_obs else ""
                ),
                "transfer_component_score": (
                    f"{transfer_component_score:.6f}"
                    if transfer_component_score is not None
                    else ""
                ),
                "switching_signal_count": switching_signal_count,
                "switching_status": switching_status,
                "switching_erosion_flag": switching_erosion_flag,
                "switching_component_score": (
                    f"{switching_component_score:.6f}"
                    if switching_component_score is not None
                    else ""
                ),
                "concentration_period_key": concentration_period_key,
                "concentration_proxy_scope": concentration_proxy_scope,
                "concentration_local_hhi_component": concentration_local_hhi_component,
                "concentration_global_hhi_component": concentration_global_hhi_component,
                "concentration_market_gap": concentration_market_gap,
                "concentration_component_score": (
                    f"{concentration_component_score:.6f}"
                    if concentration_component_score is not None
                    else ""
                ),
                "i_market_narrow": (
                    f"{i_market_narrow:.6f}" if i_market_narrow is not None else ""
                ),
                "i_market_narrow_status": status,
                "construction_note": "; ".join(notes),
            }
        )

    return output_rows


def write_panel(rows: list[dict[str, str]]) -> None:
    OUTPUT_PANEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "peer_group_id",
        "firm_std",
        "service_std",
        "country_std",
        "analysis_role",
        "observed_component_count",
        "transfer_period_count",
        "transfer_periods_observed",
        "transfer_index_mean",
        "transfer_relative_position_pct_mean",
        "transfer_role_support_gap_mean",
        "transfer_component_score",
        "switching_signal_count",
        "switching_status",
        "switching_erosion_flag",
        "switching_component_score",
        "concentration_period_key",
        "concentration_proxy_scope",
        "concentration_local_hhi_component",
        "concentration_global_hhi_component",
        "concentration_market_gap",
        "concentration_component_score",
        "i_market_narrow",
        "i_market_narrow_status",
        "construction_note",
    ]
    with OUTPUT_PANEL_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_log(rows: list[dict[str, str]]) -> None:
    status_counts = Counter(row["i_market_narrow_status"] for row in rows)
    nonmissing_rows = [row for row in rows if row["i_market_narrow"]]
    korean_rows = [
        row for row in nonmissing_rows if is_korean_role(row["analysis_role"])
    ]
    global_rows = [
        row for row in nonmissing_rows if not is_korean_role(row["analysis_role"])
    ]

    def top_lines(selected_rows: list[dict[str, str]], label: str) -> list[str]:
        if not selected_rows:
            return [f"- {label}: none"]
        ordered = sorted(
            selected_rows, key=lambda row: float(row["i_market_narrow"]), reverse=True
        )
        lines = [f"- {label}:"]
        for row in ordered[:3]:
            lines.append(
                f"  - {row['firm_std']} | {row['peer_group_id']} | {row['i_market_narrow']}"
            )
        return lines

    log_lines = [
        "# Strength Prompt 36. 협의 I_market_narrow 계산",
        "",
        "## Summary",
        "",
        f"- total core rows: {len(rows)}",
        f"- nonmissing i_market_narrow rows: {len(nonmissing_rows)}",
        f"- status counts: {dict(status_counts)}",
        "",
        "## Interpretation",
        "",
        "- This narrow market index uses only three direct market-side inputs: role-sensitive transfer support gaps, switching-cost evidence, and role-sensitive concentration burden.",
        "- The transfer component contributes only when the signed Korean-minus-global gap points to burden on the row's own side, so most Korean rows receive little or no transfer support under the current matched evidence.",
        "- The concentration component is intentionally conservative: when the Korean proxy market is locally concentrated, Korean rows receive zero concentration burden while global rows can receive a positive burden score.",
        "- As a result, this market axis remains the weakest strengthening axis in the current chain and should be read as a disciplined constraint rather than a forced supportive result.",
        "",
        "## Highest Rows",
        "",
        *top_lines(korean_rows, "Top Korean rows"),
        *top_lines(global_rows, "Top Global rows"),
        "",
    ]
    OUTPUT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")


def main() -> None:
    rows = build_rows()
    write_panel(rows)
    write_log(rows)


if __name__ == "__main__":
    main()
