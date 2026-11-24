from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
import re


BASE_DIR = Path(__file__).resolve().parents[2]
CORE_SAMPLE_PATH = (
    BASE_DIR
    / "data/registry/claim_strengthening/reverse_discrimination_core_sample_v1.csv"
)
FINANCIAL_PANEL_PATH = BASE_DIR / "data/interim/financial_extraction_panel.csv"
OUTPUT_PATH = (
    BASE_DIR
    / "data/processed/claim_strengthening/investment_recovery_horizon_panel.csv"
)
LOG_PATH = (
    BASE_DIR
    / "logs/claim_strengthening/investment_recovery_horizon_log.md"
)

TARGET_METRICS = {"revenue", "content_investment"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_float(value: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def fmt_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}"


def period_sort_key(period: str) -> tuple[int, float, str]:
    if not period:
        return (9999, 99.0, period)
    year_match = re.search(r"(20\d{2})", period)
    year = int(year_match.group(1)) if year_match else 9999
    if period.startswith("FY"):
        slot = 4.9
    elif "Q1" in period:
        slot = 1.0
    elif "Q2" in period:
        slot = 2.0
    elif "H1" in period:
        slot = 2.5
    elif "Q3" in period:
        slot = 3.0
    elif "Q4" in period:
        slot = 4.0
    else:
        slot = 9.0
    return (year, slot, period)


def period_granularity(period: str) -> str:
    if period.startswith("FY"):
        return "annual"
    if "H1" in period or "H2" in period:
        return "semiannual"
    if "Q" in period:
        return "quarterly"
    return ""


def period_length_months(period: str) -> float | None:
    granularity = period_granularity(period)
    if granularity == "annual":
        return 12.0
    if granularity == "semiannual":
        return 6.0
    if granularity == "quarterly":
        return 3.0
    return None


def analysis_side(analysis_role: str) -> str:
    return "korean" if "korean" in analysis_role else "global"


def build_metric_lookup(
    panel_rows: list[dict[str, str]],
) -> dict[tuple[str, str], dict[str, dict[str, str]]]:
    lookup: dict[tuple[str, str], dict[str, dict[str, str]]] = {}
    for row in panel_rows:
        if row["metric_name"] not in TARGET_METRICS:
            continue
        key = (row["firm_std"], row["fiscal_period"])
        lookup.setdefault(key, {})[row["metric_name"]] = row
    return lookup


def main() -> None:
    core_rows = [r for r in read_csv(CORE_SAMPLE_PATH) if r["include_flag"] == "yes"]
    financial_rows = read_csv(FINANCIAL_PANEL_PATH)
    metric_lookup = build_metric_lookup(financial_rows)

    periods_by_firm: dict[str, set[str]] = defaultdict(set)
    for firm_std, fiscal_period in metric_lookup:
        periods_by_firm[firm_std].add(fiscal_period)

    output_rows: list[dict[str, str]] = []

    for core_row in core_rows:
        firm_std = core_row["firm_std"]
        periods = sorted(periods_by_firm.get(firm_std, set()), key=period_sort_key)
        if not periods:
            output_rows.append(
                {
                    "peer_group_id": core_row["peer_group_id"],
                    "firm_std": firm_std,
                    "service_std": core_row["service_std"],
                    "country_std": core_row["country_std"],
                    "analysis_role": core_row["analysis_role"],
                    "fiscal_period": "",
                    "period_granularity": "",
                    "revenue": "",
                    "content_investment": "",
                    "content_investment_for_horizon": "",
                    "content_sign_flag": "",
                    "investment_recovery_ratio_proxy": "",
                    "investment_recovery_horizon_periods": "",
                    "investment_recovery_horizon_months": "",
                    "opposite_side_reference_horizon_months": "",
                    "horizon_gap_months_signed": "",
                    "korean_minus_global_gap_months": "",
                    "comparability_flag": "no",
                    "exclude_reason": "no_financial_metric_rows",
                    "matched_korean_firm_count": "0",
                    "matched_global_firm_count": "0",
                    "matched_peer_firm_count": "0",
                    "revenue_source_note": "",
                    "content_source_note": "",
                    "revenue_extraction_method": "",
                    "content_extraction_method": "",
                    "evidence_note": "No direct filing revenue/content-investment pair exists for this core-sample firm.",
                }
            )
            continue

        for fiscal_period in periods:
            metric_rows = metric_lookup.get((firm_std, fiscal_period), {})
            revenue_row = metric_rows.get("revenue")
            content_row = metric_rows.get("content_investment")
            revenue_value = parse_float(revenue_row["metric_value_raw"] if revenue_row else "")
            content_value = parse_float(content_row["metric_value_raw"] if content_row else "")
            months = period_length_months(fiscal_period)

            content_for_horizon: float | None = None
            content_sign_flag = ""
            if content_value is not None:
                if content_value < 0:
                    content_for_horizon = abs(content_value)
                    content_sign_flag = "negative_raw_abs_used"
                elif content_value > 0:
                    content_for_horizon = content_value
                    content_sign_flag = "positive_raw"
                else:
                    content_for_horizon = 0.0
                    content_sign_flag = "zero_raw"

            ratio_proxy: float | None = None
            horizon_periods: float | None = None
            horizon_months: float | None = None
            if (
                revenue_value is not None
                and revenue_value > 0
                and content_for_horizon is not None
                and months is not None
                and content_for_horizon > 0
            ):
                ratio_proxy = revenue_value / content_for_horizon
                horizon_periods = content_for_horizon / revenue_value
                horizon_months = horizon_periods * months

            if revenue_value is None:
                exclude_reason = "missing_revenue"
            elif revenue_value <= 0:
                exclude_reason = "nonpositive_revenue_not_interpretable"
            elif content_value is None:
                exclude_reason = "missing_content_investment"
            elif content_for_horizon == 0:
                exclude_reason = "nonpositive_content_investment_not_interpretable"
            else:
                exclude_reason = ""

            output_rows.append(
                {
                    "peer_group_id": core_row["peer_group_id"],
                    "firm_std": firm_std,
                    "service_std": core_row["service_std"],
                    "country_std": core_row["country_std"],
                    "analysis_role": core_row["analysis_role"],
                    "fiscal_period": fiscal_period,
                    "period_granularity": period_granularity(fiscal_period),
                    "revenue": fmt_float(revenue_value),
                    "content_investment": fmt_float(content_value),
                    "content_investment_for_horizon": fmt_float(content_for_horizon),
                    "content_sign_flag": content_sign_flag,
                    "investment_recovery_ratio_proxy": fmt_float(ratio_proxy),
                    "investment_recovery_horizon_periods": fmt_float(horizon_periods),
                    "investment_recovery_horizon_months": fmt_float(horizon_months),
                    "opposite_side_reference_horizon_months": "",
                    "horizon_gap_months_signed": "",
                    "korean_minus_global_gap_months": "",
                    "comparability_flag": "no",
                    "exclude_reason": exclude_reason,
                    "matched_korean_firm_count": "0",
                    "matched_global_firm_count": "0",
                    "matched_peer_firm_count": "0",
                    "revenue_source_note": (
                        revenue_row["source_page_or_note"] if revenue_row else ""
                    ),
                    "content_source_note": (
                        content_row["source_page_or_note"] if content_row else ""
                    ),
                    "revenue_extraction_method": (
                        revenue_row["extraction_method"] if revenue_row else ""
                    ),
                    "content_extraction_method": (
                        content_row["extraction_method"] if content_row else ""
                    ),
                    "evidence_note": "",
                }
            )

    grouped_rows: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in output_rows:
        grouped_rows[(row["peer_group_id"], row["fiscal_period"])].append(row)

    comparable_periods: list[tuple[str, str]] = []
    sign_normalized_count = 0
    for row in output_rows:
        if row["content_sign_flag"] == "negative_raw_abs_used":
            sign_normalized_count += 1

    for (peer_group_id, fiscal_period), rows in grouped_rows.items():
        if not fiscal_period:
            continue

        unique_side_horizon: dict[str, dict[str, float]] = {"korean": {}, "global": {}}
        for row in rows:
            horizon = parse_float(row["investment_recovery_horizon_months"])
            if horizon is None:
                continue
            side = analysis_side(row["analysis_role"])
            unique_side_horizon[side][row["firm_std"]] = horizon

        korean_values = list(unique_side_horizon["korean"].values())
        global_values = list(unique_side_horizon["global"].values())
        korean_mean = mean(korean_values) if korean_values else None
        global_median = median(global_values) if global_values else None
        comparable = korean_mean is not None and global_median is not None
        if comparable:
            comparable_periods.append((peer_group_id, fiscal_period))

        for row in rows:
            horizon = parse_float(row["investment_recovery_horizon_months"])
            row["matched_korean_firm_count"] = str(len(unique_side_horizon["korean"]))
            row["matched_global_firm_count"] = str(len(unique_side_horizon["global"]))
            row["matched_peer_firm_count"] = str(
                len(unique_side_horizon["korean"]) + len(unique_side_horizon["global"])
            )

            if horizon is not None and comparable:
                opposite_reference = (
                    global_median if analysis_side(row["analysis_role"]) == "korean" else korean_mean
                )
                row["comparability_flag"] = "yes"
                row["opposite_side_reference_horizon_months"] = fmt_float(opposite_reference)
                row["horizon_gap_months_signed"] = fmt_float(horizon - opposite_reference)
                row["korean_minus_global_gap_months"] = fmt_float(korean_mean - global_median)
            elif horizon is not None and not comparable:
                row["comparability_flag"] = "no"
                if len(unique_side_horizon["korean"]) == 0:
                    row["exclude_reason"] = "no_korean_anchor_same_fiscal_period"
                elif len(unique_side_horizon["global"]) == 0:
                    row["exclude_reason"] = "no_global_peer_same_fiscal_period"

            evidence_parts: list[str] = []
            if row["exclude_reason"] == "no_financial_metric_rows":
                evidence_parts.append("No direct filing revenue/content-investment pair exists.")
            else:
                if parse_float(row["revenue"]) is not None:
                    evidence_parts.append("Revenue row observed.")
                else:
                    evidence_parts.append("Revenue row missing.")

                if parse_float(row["content_investment"]) is not None:
                    if row["content_sign_flag"] == "negative_raw_abs_used":
                        evidence_parts.append(
                            "Content investment is signed as outflow in the filing, so abs() is used for the horizon."
                        )
                    elif row["content_sign_flag"] == "positive_raw":
                        evidence_parts.append("Content investment is observed with a positive raw amount.")
                    elif row["content_sign_flag"] == "zero_raw":
                        evidence_parts.append("Content investment is zero, so the horizon is left blank.")
                else:
                    evidence_parts.append("Content-investment row missing.")

                if parse_float(row["investment_recovery_horizon_months"]) is not None:
                    if row["comparability_flag"] == "yes":
                        evidence_parts.append("Same-peer same-period horizon comparison is available.")
                    else:
                        evidence_parts.append("Horizon is observed, but no opposite-side same-period peer exists.")
                else:
                    evidence_parts.append("Horizon is left blank under the conservative construction rule.")
            row["evidence_note"] = " ".join(evidence_parts)

    output_rows.sort(
        key=lambda row: (
            row["peer_group_id"],
            period_sort_key(row["fiscal_period"]),
            row["analysis_role"],
            row["firm_std"],
            row["country_std"],
        )
    )

    fieldnames = [
        "peer_group_id",
        "firm_std",
        "service_std",
        "country_std",
        "analysis_role",
        "fiscal_period",
        "period_granularity",
        "revenue",
        "content_investment",
        "content_investment_for_horizon",
        "content_sign_flag",
        "investment_recovery_ratio_proxy",
        "investment_recovery_horizon_periods",
        "investment_recovery_horizon_months",
        "opposite_side_reference_horizon_months",
        "horizon_gap_months_signed",
        "korean_minus_global_gap_months",
        "comparability_flag",
        "exclude_reason",
        "matched_korean_firm_count",
        "matched_global_firm_count",
        "matched_peer_firm_count",
        "revenue_source_note",
        "content_source_note",
        "revenue_extraction_method",
        "content_extraction_method",
        "evidence_note",
    ]
    write_csv(OUTPUT_PATH, output_rows, fieldnames)

    comparable_yes = sum(row["comparability_flag"] == "yes" for row in output_rows)
    comparable_no = len(output_rows) - comparable_yes
    unique_periods = sorted(
        set(comparable_periods), key=lambda item: (item[0], period_sort_key(item[1]))
    )
    periods_text = "\n".join(
        f"- `{peer_group_id} | {fiscal_period}`"
        for peer_group_id, fiscal_period in unique_periods
    )
    if not periods_text:
        periods_text = "- none"

    log_text = "\n".join(
        [
            "# Strength Prompt 28. Investment recovery horizon panel",
            "",
            "## Summary",
            "",
            f"- total rows: `{len(output_rows)}`",
            f"- `comparability_flag = yes`: `{comparable_yes}`",
            f"- `comparability_flag = no`: `{comparable_no}`",
            f"- `content_sign_flag = negative_raw_abs_used`: `{sign_normalized_count}`",
            "",
            "## Comparable peer-periods",
            "",
            periods_text,
            "",
            "## Key interpretation",
            "",
            "- `infra_traffic_ott` remains the thickest exact-period recovery-horizon comparison because `Netflix` overlaps with all three Korean telecom anchors in `FY2024`, `2025Q3`, and `FY2025` on both revenue and content/platform-investment rows.",
            "- `mus_label_ip_export` only matches at `FY2025`; `Warner Music` has no same-period direct row for `2025H1` or `2025Q3` Korean anchor filings.",
            "- `mus_streaming_paid_core` is partially salvageable because `Dreamus` and `Spotify` overlap at `2025Q3` and `FY2025`, but `Kakao Entertainment` still has no direct filing row.",
            "- The horizon is intentionally conservative: it uses `abs(content_investment) / revenue` and then converts the ratio into months using the filing-period length only when both rows exist and revenue is positive.",
        ]
    )
    LOG_PATH.write_text(log_text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
