from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

REG_PATH = (
    PROJECT_ROOT / "data/processed/claim_strengthening/i_reg_narrow_panel.csv"
)
RISK_PATH = (
    PROJECT_ROOT / "data/processed/claim_strengthening/i_risk_narrow_panel.csv"
)
MARKET_PATH = (
    PROJECT_ROOT / "data/processed/claim_strengthening/i_market_narrow_panel.csv"
)
OUTPUT_PATH = (
    PROJECT_ROOT
    / "data/processed/claim_strengthening/reverse_discrimination_composite_narrow.csv"
)
LOG_PATH = (
    PROJECT_ROOT
    / "logs/claim_strengthening/reverse_discrimination_composite_log.md"
)

KEY_FIELDS = ["peer_group_id", "firm_std", "service_std", "country_std"]


def load_panel(path: Path, value_field: str, status_field: str):
    data: dict[tuple[str, str, str, str], dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = tuple(row[field] for field in KEY_FIELDS)
            data[key] = {
                "value": row[value_field],
                "status": row[status_field],
                "analysis_role": row["analysis_role"],
                "service_std": row["service_std"],
                "country_std": row["country_std"],
            }
    return data


def safe_float(value: str) -> float | None:
    if value == "":
        return None
    return float(value)


def build_rows() -> list[dict[str, str]]:
    reg = load_panel(REG_PATH, "i_reg_narrow", "i_reg_narrow_status")
    risk = load_panel(RISK_PATH, "i_risk_narrow", "i_risk_narrow_status")
    market = load_panel(MARKET_PATH, "i_market_narrow", "i_market_narrow_status")

    all_keys = sorted(set(reg) | set(risk) | set(market))
    rows: list[dict[str, str]] = []

    for key in all_keys:
        reg_value = safe_float(reg[key]["value"])
        risk_value = safe_float(risk[key]["value"])
        market_value = safe_float(market[key]["value"])
        observed = [
            ("reg", reg_value),
            ("risk", risk_value),
            ("market", market_value),
        ]
        observed = [(name, value) for name, value in observed if value is not None]
        observed_count = len(observed)

        if observed_count == 0:
            weight_reg = weight_risk = weight_market = 0.0
            composite = None
            status = "no_direct_composite_coverage"
            rank_eligible_flag = "no"
        else:
            weight_reg = 1.0 / observed_count if reg_value is not None else 0.0
            weight_risk = 1.0 / observed_count if risk_value is not None else 0.0
            weight_market = 1.0 / observed_count if market_value is not None else 0.0
            composite = (
                (reg_value or 0.0) * weight_reg
                + (risk_value or 0.0) * weight_risk
                + (market_value or 0.0) * weight_market
            )
            if observed_count == 3:
                status = "stronger_direct_composite_coverage"
            elif observed_count == 2:
                status = "partial_direct_composite_coverage"
            else:
                status = "thin_direct_composite_coverage"
            rank_eligible_flag = "yes" if observed_count >= 2 else "no"

        observed_names = "|".join(name for name, _ in observed)
        notes = []
        if reg_value is None:
            notes.append("reg_narrow missing")
        if risk_value is None:
            notes.append("risk_narrow missing")
        if market_value is None:
            notes.append("market_narrow missing")
        if observed_count == 1:
            notes.append("composite equals single observed narrow axis")
        if observed_count == 2:
            notes.append("composite reweights two observed narrow axes equally")
        if observed_count == 3:
            notes.append("composite uses equal weights across reg, risk, market")

        analysis_role = risk[key]["analysis_role"]

        rows.append(
            {
                "peer_group_id": key[0],
                "firm_std": key[1],
                "service_std": key[2],
                "country_std": key[3],
                "analysis_role": analysis_role,
                "i_reg_narrow": f"{reg_value:.6f}" if reg_value is not None else "",
                "i_reg_narrow_status": reg[key]["status"],
                "i_risk_narrow": f"{risk_value:.6f}" if risk_value is not None else "",
                "i_risk_narrow_status": risk[key]["status"],
                "i_market_narrow": (
                    f"{market_value:.6f}" if market_value is not None else ""
                ),
                "i_market_narrow_status": market[key]["status"],
                "observed_narrow_subindex_count": str(observed_count),
                "observed_narrow_subindices": observed_names,
                "weight_reg": f"{weight_reg:.6f}",
                "weight_risk": f"{weight_risk:.6f}",
                "weight_market": f"{weight_market:.6f}",
                "composite_narrow": f"{composite:.6f}" if composite is not None else "",
                "reverse_discrimination_composite_narrow": (
                    f"{composite:.6f}" if composite is not None else ""
                ),
                "composite_narrow_status": status,
                "composite_rank_eligible_flag": rank_eligible_flag,
                "construction_note": "; ".join(notes),
            }
        )

    return rows


def write_rows(rows: list[dict[str, str]]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "peer_group_id",
        "firm_std",
        "service_std",
        "country_std",
        "analysis_role",
        "i_reg_narrow",
        "i_reg_narrow_status",
        "i_risk_narrow",
        "i_risk_narrow_status",
        "i_market_narrow",
        "i_market_narrow_status",
        "observed_narrow_subindex_count",
        "observed_narrow_subindices",
        "weight_reg",
        "weight_risk",
        "weight_market",
        "composite_narrow",
        "reverse_discrimination_composite_narrow",
        "composite_narrow_status",
        "composite_rank_eligible_flag",
        "construction_note",
    ]
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_log(rows: list[dict[str, str]]) -> None:
    status_counts = Counter(row["composite_narrow_status"] for row in rows)
    nonmissing = [row for row in rows if row["composite_narrow"]]
    eligible = [row for row in nonmissing if row["composite_rank_eligible_flag"] == "yes"]
    korean_eligible = [
        row for row in eligible if row["analysis_role"].startswith("korean")
    ]
    global_eligible = [
        row for row in eligible if not row["analysis_role"].startswith("korean")
    ]

    def top_block(title: str, selected: list[dict[str, str]]) -> list[str]:
        lines = [f"### {title}", ""]
        if not selected:
            lines.append("- none")
            lines.append("")
            return lines
        ordered = sorted(
            selected, key=lambda row: float(row["composite_narrow"]), reverse=True
        )
        for row in ordered[:3]:
            lines.append(
                f"- {row['firm_std']} | {row['peer_group_id']} | {row['composite_narrow']} | observed={row['observed_narrow_subindices']}"
            )
        lines.append("")
        return lines

    lines = [
        "# Strength Prompt 37. 협의 Reverse Discrimination Composite 계산",
        "",
        "## Summary",
        "",
        f"- total core rows: {len(rows)}",
        f"- nonmissing composite rows: {len(nonmissing)}",
        f"- rank-eligible rows (2+ observed narrow axes): {len(eligible)}",
        f"- status counts: {dict(status_counts)}",
        "",
        "## Interpretation",
        "",
        "- This composite is stored in parallel with the original CPII and does not replace it.",
        "- Composite weights are re-normalized only over observed narrow axes, so rows with one observed axis are retained but explicitly marked as thin coverage.",
        "- Under the current strengthening chain, no row has a usable reg_narrow value, so there are no stronger three-axis rows; practical rank-eligible rows are two-axis risk-market composites.",
        "- Because market_narrow is the weakest axis and reg_narrow is fully missing, this composite mostly reflects direct risk evidence plus limited market evidence.",
        "",
        *top_block("Top Rank-Eligible Korean Rows", korean_eligible),
        *top_block("Top Rank-Eligible Global Rows", global_eligible),
    ]

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    rows = build_rows()
    write_rows(rows)
    write_log(rows)


if __name__ == "__main__":
    main()
