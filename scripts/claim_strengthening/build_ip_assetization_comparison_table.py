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
    / "data/processed/claim_strengthening/ip_assetization_comparison_table.csv"
)
LOG_PATH = (
    BASE_DIR / "logs/claim_strengthening/ip_assetization_comparison_log.md"
)

TARGET_METRICS = {"intangible_assets", "content_investment"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def fmt_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}"


def parse_float(value: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


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
        metric_bucket = lookup.setdefault(key, {})
        metric_bucket[row["metric_name"]] = row
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
                    "intangible_assets": "",
                    "content_investment": "",
                    "content_investment_for_proxy": "",
                    "content_sign_flag": "",
                    "ip_assetization_proxy": "",
                    "opposite_side_reference_proxy": "",
                    "ip_assetization_gap_signed": "",
                    "korean_minus_global_gap": "",
                    "comparability_flag": "no",
                    "exclude_reason": "no_financial_metric_rows",
                    "matched_korean_firm_count": "0",
                    "matched_global_firm_count": "0",
                    "matched_peer_firm_count": "0",
                    "intangible_source_note": "",
                    "content_source_note": "",
                    "intangible_extraction_method": "",
                    "content_extraction_method": "",
                    "evidence_note": "No intangible-assets or content-investment metric row exists for this core-sample firm.",
                }
            )
            continue

        for fiscal_period in periods:
            metric_rows = metric_lookup.get((firm_std, fiscal_period), {})
            intangible_row = metric_rows.get("intangible_assets")
            content_row = metric_rows.get("content_investment")

            intangible_value = parse_float(
                intangible_row["metric_value_raw"] if intangible_row else ""
            )
            content_value = parse_float(
                content_row["metric_value_raw"] if content_row else ""
            )
            content_for_proxy: float | None = None
            content_sign_flag = ""
            if content_value is not None:
                if content_value < 0:
                    content_for_proxy = abs(content_value)
                    content_sign_flag = "negative_raw_abs_used"
                elif content_value > 0:
                    content_for_proxy = content_value
                    content_sign_flag = "positive_raw"
                else:
                    content_for_proxy = 0.0
                    content_sign_flag = "zero_raw"

            proxy: float | None = None
            if (
                intangible_value is not None
                and content_for_proxy is not None
                and content_for_proxy > 0
            ):
                proxy = intangible_value / content_for_proxy

            if intangible_value is None:
                exclude_reason = "missing_intangible_assets"
            elif content_value is None:
                exclude_reason = "missing_content_investment"
            elif content_for_proxy == 0:
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
                    "intangible_assets": fmt_float(intangible_value),
                    "content_investment": fmt_float(content_value),
                    "content_investment_for_proxy": fmt_float(content_for_proxy),
                    "content_sign_flag": content_sign_flag,
                    "ip_assetization_proxy": fmt_float(proxy),
                    "opposite_side_reference_proxy": "",
                    "ip_assetization_gap_signed": "",
                    "korean_minus_global_gap": "",
                    "comparability_flag": "no",
                    "exclude_reason": exclude_reason,
                    "matched_korean_firm_count": "0",
                    "matched_global_firm_count": "0",
                    "matched_peer_firm_count": "0",
                    "intangible_source_note": (
                        intangible_row["source_page_or_note"] if intangible_row else ""
                    ),
                    "content_source_note": (
                        content_row["source_page_or_note"] if content_row else ""
                    ),
                    "intangible_extraction_method": (
                        intangible_row["extraction_method"] if intangible_row else ""
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

        unique_side_proxy: dict[str, dict[str, float]] = {"korean": {}, "global": {}}
        for row in rows:
            proxy = parse_float(row["ip_assetization_proxy"])
            if proxy is None:
                continue
            side = analysis_side(row["analysis_role"])
            unique_side_proxy[side][row["firm_std"]] = proxy

        korean_values = list(unique_side_proxy["korean"].values())
        global_values = list(unique_side_proxy["global"].values())
        korean_mean = mean(korean_values) if korean_values else None
        global_median = median(global_values) if global_values else None

        comparable = korean_mean is not None and global_median is not None
        if comparable:
            comparable_periods.append((peer_group_id, fiscal_period))

        for row in rows:
            side = analysis_side(row["analysis_role"])
            proxy = parse_float(row["ip_assetization_proxy"])
            row["matched_korean_firm_count"] = str(len(unique_side_proxy["korean"]))
            row["matched_global_firm_count"] = str(len(unique_side_proxy["global"]))
            row["matched_peer_firm_count"] = str(
                len(unique_side_proxy["korean"]) + len(unique_side_proxy["global"])
            )

            if proxy is not None and comparable:
                opposite_reference = global_median if side == "korean" else korean_mean
                row["comparability_flag"] = "yes"
                row["opposite_side_reference_proxy"] = fmt_float(opposite_reference)
                row["ip_assetization_gap_signed"] = fmt_float(proxy - opposite_reference)
                row["korean_minus_global_gap"] = fmt_float(korean_mean - global_median)
            elif proxy is not None and not comparable:
                row["comparability_flag"] = "no"
                if len(unique_side_proxy["korean"]) == 0:
                    row["exclude_reason"] = "no_korean_anchor_same_fiscal_period"
                elif len(unique_side_proxy["global"]) == 0:
                    row["exclude_reason"] = "no_global_peer_same_fiscal_period"

            evidence_parts: list[str] = []
            if row["exclude_reason"] == "no_financial_metric_rows":
                evidence_parts.append("No direct filing metrics are available.")
            else:
                if parse_float(row["intangible_assets"]) is not None:
                    evidence_parts.append("Intangible-assets row observed.")
                else:
                    evidence_parts.append("Intangible-assets row missing.")

                if parse_float(row["content_investment"]) is not None:
                    if row["content_sign_flag"] == "negative_raw_abs_used":
                        evidence_parts.append(
                            "Content investment is signed as outflow in the filing, so abs() is used for the proxy."
                        )
                    elif row["content_sign_flag"] == "positive_raw":
                        evidence_parts.append(
                            "Content investment is observed with a positive raw amount."
                        )
                    elif row["content_sign_flag"] == "zero_raw":
                        evidence_parts.append(
                            "Content investment is zero, so the proxy is left blank."
                        )
                else:
                    evidence_parts.append("Content-investment row missing.")

                if parse_float(row["ip_assetization_proxy"]) is not None:
                    if row["comparability_flag"] == "yes":
                        evidence_parts.append(
                            "Same-peer same-period matched comparison is available."
                        )
                    else:
                        evidence_parts.append(
                            "Proxy is observed, but no opposite-side same-period peer exists."
                        )
                else:
                    evidence_parts.append("Proxy is left blank under the conservative construction rule.")

            row["evidence_note"] = " ".join(evidence_parts)

    fieldnames = [
        "peer_group_id",
        "firm_std",
        "service_std",
        "country_std",
        "analysis_role",
        "fiscal_period",
        "period_granularity",
        "intangible_assets",
        "content_investment",
        "content_investment_for_proxy",
        "content_sign_flag",
        "ip_assetization_proxy",
        "opposite_side_reference_proxy",
        "ip_assetization_gap_signed",
        "korean_minus_global_gap",
        "comparability_flag",
        "exclude_reason",
        "matched_korean_firm_count",
        "matched_global_firm_count",
        "matched_peer_firm_count",
        "intangible_source_note",
        "content_source_note",
        "intangible_extraction_method",
        "content_extraction_method",
        "evidence_note",
    ]
    output_rows.sort(
        key=lambda row: (
            row["peer_group_id"],
            period_sort_key(row["fiscal_period"]),
            row["analysis_role"],
            row["firm_std"],
            row["country_std"],
        )
    )
    write_csv(OUTPUT_PATH, output_rows, fieldnames)

    comparable_yes = sum(row["comparability_flag"] == "yes" for row in output_rows)
    comparable_no = len(output_rows) - comparable_yes
    unique_comparable_periods = sorted(
        set(comparable_periods), key=lambda item: (item[0], period_sort_key(item[1]))
    )
    periods_text = "\n".join(
        f"- `{peer_group_id} | {fiscal_period}`"
        for peer_group_id, fiscal_period in unique_comparable_periods
    )
    if not periods_text:
        periods_text = "- none"

    periods_by_group: dict[str, list[str]] = defaultdict(list)
    for peer_group_id, fiscal_period in unique_comparable_periods:
        periods_by_group[peer_group_id].append(fiscal_period)

    def pretty_periods(peer_group_id: str) -> str:
        periods = periods_by_group.get(peer_group_id, [])
        if not periods:
            return "none"
        return ", ".join(periods)

    log_text = "\n".join(
        [
            "# Strength Prompt 27. IP assetization comparison table",
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
            f"- `infra_traffic_ott` has the thickest exact-period comparison, but under the conservative rule it only matches at `{pretty_periods('infra_traffic_ott')}` because `Netflix` lacks a direct `intangible_assets` row for `FY2024`.",
            f"- `mus_label_ip_export` only matches at `{pretty_periods('mus_label_ip_export')}`; `Warner Music` has no same-period direct row for the Korean anchors' `2025H1` or `2025Q3` filings.",
            f"- `mus_streaming_paid_core` is partially salvageable because `Dreamus` and `Spotify` overlap at `{pretty_periods('mus_streaming_paid_core')}`, but `Kakao Entertainment` still has no direct filing row.",
            "- The proxy is intentionally conservative: it uses `intangible_assets / abs(content_investment)` only when both rows exist and leaves the cell blank when either side is missing or the investment base is nonpositive.",
        ]
    )
    LOG_PATH.write_text(log_text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
