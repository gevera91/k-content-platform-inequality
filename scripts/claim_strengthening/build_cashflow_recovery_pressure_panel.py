from __future__ import annotations

import csv
from collections import defaultdict
import importlib.util
from pathlib import Path
import re
from statistics import mean, median


BASE_DIR = Path(__file__).resolve().parents[2]
CORE_SAMPLE_PATH = (
    BASE_DIR
    / "data/registry/claim_strengthening/reverse_discrimination_core_sample_v1.csv"
)
FILING_METADATA_PATH = BASE_DIR / "data/interim/filing_metadata_panel.csv"
FINANCIAL_PANEL_PATH = BASE_DIR / "data/interim/financial_extraction_panel.csv"
OUTPUT_PATH = (
    BASE_DIR
    / "data/processed/claim_strengthening/cashflow_recovery_pressure_panel.csv"
)
LOG_PATH = (
    BASE_DIR / "logs/claim_strengthening/cashflow_recovery_pressure_log.md"
)
HELPER_SCRIPT_PATH = BASE_DIR / "scripts/build_financial_extraction_panel.py"

SKIP_GROUPS = {"current_report", "major_issues"}
OPERATING_CASHFLOW_IX_TAGS = [
    "us-gaap:NetCashProvidedByUsedInOperatingActivities",
    "ifrs-full:CashFlowsFromUsedInOperatingActivities",
    "ifrs-full:CashFlowsFromUsedInOperatingActivitiesContinuingOperations",
    "ifrs-full:CashFlowsUsedInOperations",
    "ifrs-full:CashFlowsFromOperations",
]
KR_OPERATING_CASHFLOW_PATTERNS = [
    "cash flows from (used in) operating activities",
    "cash flows from operating activities",
    "net cash flows from operating activities",
    "net cash provided by operating activities",
    "cash generated from operations",
]


def load_helper_module():
    spec = importlib.util.spec_from_file_location("bfe_helper", HELPER_SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


HELPER = load_helper_module()


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


def analysis_side(analysis_role: str) -> str:
    return "korean" if "korean" in analysis_role else "global"


def choose_investment_metric(peer_group_id: str) -> str:
    if peer_group_id.startswith("infra_"):
        return "capex"
    return "content_investment"


def build_financial_lookup(
    rows: list[dict[str, str]],
) -> dict[tuple[str, str, str], dict[str, str]]:
    lookup: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        lookup[(row["firm_std"], row["fiscal_period"], row["metric_name"])] = row
    return lookup


def extract_kr_operating_cash_flow(meta: dict[str, str]) -> dict[str, str]:
    role_entries = HELPER.parse_kr_role_map(meta["source_file"])
    role_entry = HELPER.find_kr_role(role_entries, contains=["statement of cash flows"])
    if not role_entry:
        return {"exclude_reason": "kr_cashflow_role_missing"}

    url, role_html = HELPER.get_kr_role_page(role_entry)
    doc = HELPER.html.fromstring(role_html.encode("utf-8"))
    for table_node in doc.xpath("//table[contains(@class, 'fact-table')]"):
        extracted = HELPER.extract_from_grid(
            HELPER.table_to_grid(table_node),
            meta["fiscal_period_end"],
            KR_OPERATING_CASHFLOW_PATTERNS,
            instant=False,
            allow_sum=False,
        )
        if extracted:
            return {
                "operating_cash_flow": fmt_float(extracted["value"]),
                "operating_cash_flow_source_note": (
                    f"{role_entry['label']} | {extracted['source_label']} | {extracted['descriptor']}"
                ),
                "operating_cash_flow_extraction_method": "kr_role_table_label_match",
                "operating_cash_flow_source_url": url,
                "cashflow_measure_type": "direct_operating_cash_flow",
                "exclude_reason": "",
            }
    return {"exclude_reason": "operating_cash_flow_missing"}


def extract_ix_operating_cash_flow(meta: dict[str, str]) -> dict[str, str]:
    source_path = BASE_DIR / meta["source_file"]
    if not source_path.exists():
        return {"exclude_reason": "source_file_missing"}

    text = source_path.read_text(encoding="utf-8", errors="ignore")
    contexts = HELPER.parse_ix_contexts(text)
    facts = HELPER.parse_ix_facts(text)
    if not facts:
        return {"exclude_reason": "no_ixbrl_facts"}

    facts_by_tag: dict[str, list[dict[str, object]]] = defaultdict(list)
    for fact in facts:
        facts_by_tag[fact["tag"]].append(fact)

    selected = HELPER.select_ix_fact(
        facts_by_tag,
        contexts,
        OPERATING_CASHFLOW_IX_TAGS,
        meta["fiscal_period_end"],
        instant=False,
    )
    if not selected:
        return {"exclude_reason": "operating_cash_flow_missing"}

    fact = selected["fact"]
    context = selected["context"]
    period_label = context.get("instant") or context.get("end")
    descriptor = f"{fact['tag']} | context:{fact['context_ref']} | {period_label}"
    return {
        "operating_cash_flow": fmt_float(fact["actual_value"]),
        "operating_cash_flow_source_note": descriptor,
        "operating_cash_flow_extraction_method": "sec_ixbrl_concept_context",
        "operating_cash_flow_source_url": meta["source_url"],
        "cashflow_measure_type": "direct_operating_cash_flow",
        "exclude_reason": "",
    }


def extract_spotify_operating_cash_flow_from_tables(meta: dict[str, str]) -> dict[str, str]:
    source_path = BASE_DIR / meta["source_file"]
    if not source_path.exists():
        return {"exclude_reason": "source_file_missing"}

    doc = HELPER.html.fromstring(source_path.read_bytes())
    tables = []
    for idx, table_node in enumerate(doc.xpath("//table")):
        rows = HELPER.simple_table_rows(table_node)
        if rows:
            tables.append((idx, rows))

    for table_idx, rows in tables:
        joined = " | ".join(" / ".join(row) for row in rows[:25]).lower()
        if "operating activities" not in joined:
            continue
        if "net cash flows from operating activities" not in joined and "net cash provided by operating activities" not in joined:
            continue

        slot_info = HELPER.spotify_income_slot(rows, meta["filing_group"], meta["fiscal_period_end"])
        if slot_info is None:
            continue
        extracted = HELPER.spotify_extract_metric_from_rows(
            rows,
            ["net cash flows from operating activities", "net cash provided by operating activities"],
            slot_info,
        )
        if extracted:
            full_text = HELPER.normalize_space(" ".join(doc.xpath("//text()"))).lower()
            unit_multiplier = (
                1_000_000
                if any(token in full_text for token in ["millions of euros", "in € millions", "(in € millions)"])
                else 1
            )
            return {
                "operating_cash_flow": fmt_float(extracted["value"] * unit_multiplier),
                "operating_cash_flow_source_note": (
                    f"table:{table_idx} | {extracted['label']} | value_index:{extracted['value_idx']}"
                ),
                "operating_cash_flow_extraction_method": "spotify_html_table_fallback_direct",
                "operating_cash_flow_source_url": meta["source_url"],
                "cashflow_measure_type": "direct_operating_cash_flow",
                "exclude_reason": "",
            }
    return {"exclude_reason": "spotify_cashflow_table_missing"}


def extract_operating_cash_flow(meta: dict[str, str]) -> dict[str, str]:
    if meta["filing_system"] == "OpenDART":
        return extract_kr_operating_cash_flow(meta)
    ix_result = extract_ix_operating_cash_flow(meta)
    if not ix_result.get("exclude_reason"):
        return ix_result
    if meta["firm_std"] == "spotify":
        table_result = extract_spotify_operating_cash_flow_from_tables(meta)
        if not table_result.get("exclude_reason"):
            return table_result
    return ix_result


def main() -> None:
    core_rows = [r for r in read_csv(CORE_SAMPLE_PATH) if r["include_flag"] == "yes"]
    metadata_rows = [
        r
        for r in read_csv(FILING_METADATA_PATH)
        if r["filing_group"] not in SKIP_GROUPS and r["fiscal_period"]
    ]
    financial_lookup = build_financial_lookup(read_csv(FINANCIAL_PANEL_PATH))

    metadata_by_firm: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in metadata_rows:
        metadata_by_firm[row["firm_std"]].append(row)
    for firm_std in metadata_by_firm:
        metadata_by_firm[firm_std].sort(key=lambda row: period_sort_key(row["fiscal_period"]))

    ocf_cache: dict[str, dict[str, str]] = {}
    output_rows: list[dict[str, str]] = []

    for core_row in core_rows:
        firm_std = core_row["firm_std"]
        firm_metadata = metadata_by_firm.get(firm_std, [])
        investment_metric = choose_investment_metric(core_row["peer_group_id"])

        if not firm_metadata:
            output_rows.append(
                {
                    "peer_group_id": core_row["peer_group_id"],
                    "firm_std": firm_std,
                    "service_std": core_row["service_std"],
                    "country_std": core_row["country_std"],
                    "analysis_role": core_row["analysis_role"],
                    "fiscal_period": "",
                    "period_granularity": "",
                    "cashflow_measure_type": "",
                    "operating_cash_flow": "",
                    "investment_base_metric": investment_metric,
                    "investment_base_raw": "",
                    "investment_base_for_pressure": "",
                    "investment_sign_flag": "",
                    "cashflow_pressure_ratio": "",
                    "cashflow_coverage_ratio": "",
                    "opposite_side_reference_pressure_ratio": "",
                    "pressure_gap_signed": "",
                    "korean_minus_global_pressure_gap": "",
                    "comparability_flag": "no",
                    "exclude_reason": "no_filing_metadata_rows",
                    "matched_korean_firm_count": "0",
                    "matched_global_firm_count": "0",
                    "matched_peer_firm_count": "0",
                    "operating_cash_flow_source_note": "",
                    "investment_source_note": "",
                    "operating_cash_flow_extraction_method": "",
                    "investment_extraction_method": "",
                    "source_currency": "",
                    "evidence_note": "No filing metadata row exists for this core-sample firm, so no direct operating cash-flow extraction is possible.",
                }
            )
            continue

        for meta in firm_metadata:
            cache_key = meta["filing_id"]
            if cache_key not in ocf_cache:
                ocf_cache[cache_key] = extract_operating_cash_flow(meta)
            ocf_info = ocf_cache[cache_key]

            investment_row = financial_lookup.get((firm_std, meta["fiscal_period"], investment_metric))
            investment_raw = parse_float(investment_row["metric_value_raw"] if investment_row else "")
            investment_for_pressure: float | None = None
            investment_sign_flag = ""
            if investment_raw is not None:
                if investment_raw < 0:
                    investment_for_pressure = abs(investment_raw)
                    investment_sign_flag = "negative_raw_abs_used"
                elif investment_raw > 0:
                    investment_for_pressure = investment_raw
                    investment_sign_flag = "positive_raw"
                else:
                    investment_for_pressure = 0.0
                    investment_sign_flag = "zero_raw"

            operating_cash_flow = parse_float(ocf_info.get("operating_cash_flow", ""))
            pressure_ratio: float | None = None
            coverage_ratio: float | None = None

            exclude_reason = ocf_info.get("exclude_reason", "")
            if operating_cash_flow is None and not exclude_reason:
                exclude_reason = "missing_operating_cash_flow"

            if investment_row is None:
                exclude_reason = "missing_investment_base_metric"
            elif investment_for_pressure == 0:
                exclude_reason = "nonpositive_investment_base_not_interpretable"
            elif operating_cash_flow is not None and operating_cash_flow <= 0:
                exclude_reason = "nonpositive_operating_cash_flow_not_interpretable"

            if (
                operating_cash_flow is not None
                and operating_cash_flow > 0
                and investment_for_pressure is not None
                and investment_for_pressure > 0
            ):
                pressure_ratio = investment_for_pressure / operating_cash_flow
                coverage_ratio = operating_cash_flow / investment_for_pressure

            output_rows.append(
                {
                    "peer_group_id": core_row["peer_group_id"],
                    "firm_std": firm_std,
                    "service_std": core_row["service_std"],
                    "country_std": core_row["country_std"],
                    "analysis_role": core_row["analysis_role"],
                    "fiscal_period": meta["fiscal_period"],
                    "period_granularity": meta["period_granularity"],
                    "cashflow_measure_type": ocf_info.get("cashflow_measure_type", ""),
                    "operating_cash_flow": fmt_float(operating_cash_flow),
                    "investment_base_metric": investment_metric,
                    "investment_base_raw": fmt_float(investment_raw),
                    "investment_base_for_pressure": fmt_float(investment_for_pressure),
                    "investment_sign_flag": investment_sign_flag,
                    "cashflow_pressure_ratio": fmt_float(pressure_ratio),
                    "cashflow_coverage_ratio": fmt_float(coverage_ratio),
                    "opposite_side_reference_pressure_ratio": "",
                    "pressure_gap_signed": "",
                    "korean_minus_global_pressure_gap": "",
                    "comparability_flag": "no",
                    "exclude_reason": exclude_reason,
                    "matched_korean_firm_count": "0",
                    "matched_global_firm_count": "0",
                    "matched_peer_firm_count": "0",
                    "operating_cash_flow_source_note": ocf_info.get("operating_cash_flow_source_note", ""),
                    "investment_source_note": investment_row["source_page_or_note"] if investment_row else "",
                    "operating_cash_flow_extraction_method": ocf_info.get("operating_cash_flow_extraction_method", ""),
                    "investment_extraction_method": investment_row["extraction_method"] if investment_row else "",
                    "source_currency": meta["currency"],
                    "evidence_note": "",
                }
            )

    grouped_rows: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in output_rows:
        grouped_rows[(row["peer_group_id"], row["fiscal_period"])].append(row)

    comparable_periods: list[tuple[str, str]] = []
    negative_investment_count = sum(
        row["investment_sign_flag"] == "negative_raw_abs_used" for row in output_rows
    )

    for (peer_group_id, fiscal_period), rows in grouped_rows.items():
        if not fiscal_period:
            continue
        unique_side_pressure: dict[str, dict[str, float]] = {"korean": {}, "global": {}}
        for row in rows:
            pressure = parse_float(row["cashflow_pressure_ratio"])
            if pressure is None:
                continue
            side = analysis_side(row["analysis_role"])
            unique_side_pressure[side][row["firm_std"]] = pressure

        korean_values = list(unique_side_pressure["korean"].values())
        global_values = list(unique_side_pressure["global"].values())
        korean_mean = mean(korean_values) if korean_values else None
        global_median = median(global_values) if global_values else None
        comparable = korean_mean is not None and global_median is not None
        if comparable:
            comparable_periods.append((peer_group_id, fiscal_period))

        for row in rows:
            pressure = parse_float(row["cashflow_pressure_ratio"])
            row["matched_korean_firm_count"] = str(len(unique_side_pressure["korean"]))
            row["matched_global_firm_count"] = str(len(unique_side_pressure["global"]))
            row["matched_peer_firm_count"] = str(
                len(unique_side_pressure["korean"]) + len(unique_side_pressure["global"])
            )

            if pressure is not None and comparable:
                opposite_reference = (
                    global_median if analysis_side(row["analysis_role"]) == "korean" else korean_mean
                )
                row["comparability_flag"] = "yes"
                row["opposite_side_reference_pressure_ratio"] = fmt_float(opposite_reference)
                row["pressure_gap_signed"] = fmt_float(pressure - opposite_reference)
                row["korean_minus_global_pressure_gap"] = fmt_float(korean_mean - global_median)
            elif pressure is not None and not comparable:
                if len(unique_side_pressure["korean"]) == 0:
                    row["exclude_reason"] = "no_korean_anchor_same_fiscal_period"
                elif len(unique_side_pressure["global"]) == 0:
                    row["exclude_reason"] = "no_global_peer_same_fiscal_period"

            evidence_parts: list[str] = []
            if row["exclude_reason"] == "no_filing_metadata_rows":
                evidence_parts.append("No filing metadata row exists.")
            else:
                if row["cashflow_measure_type"] == "direct_operating_cash_flow":
                    evidence_parts.append("Direct operating cash-flow row extracted from the filing.")
                else:
                    evidence_parts.append("Direct operating cash-flow row unavailable.")

                if parse_float(row["investment_base_raw"]) is not None:
                    if row["investment_sign_flag"] == "negative_raw_abs_used":
                        evidence_parts.append(
                            f"`{row['investment_base_metric']}` is signed as outflow, so abs() is used for the pressure ratio."
                        )
                    else:
                        evidence_parts.append(
                            f"`{row['investment_base_metric']}` is observed directly in the financial extraction panel."
                        )
                else:
                    evidence_parts.append(f"`{row['investment_base_metric']}` row is missing.")

                if parse_float(row["cashflow_pressure_ratio"]) is not None:
                    if row["comparability_flag"] == "yes":
                        evidence_parts.append("Same-peer same-period pressure comparison is available.")
                    else:
                        evidence_parts.append("Pressure ratio is observed, but no opposite-side same-period peer exists.")
                else:
                    evidence_parts.append("Pressure ratio is left blank under the conservative direct-construction rule.")
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
        "cashflow_measure_type",
        "operating_cash_flow",
        "investment_base_metric",
        "investment_base_raw",
        "investment_base_for_pressure",
        "investment_sign_flag",
        "cashflow_pressure_ratio",
        "cashflow_coverage_ratio",
        "opposite_side_reference_pressure_ratio",
        "pressure_gap_signed",
        "korean_minus_global_pressure_gap",
        "comparability_flag",
        "exclude_reason",
        "matched_korean_firm_count",
        "matched_global_firm_count",
        "matched_peer_firm_count",
        "operating_cash_flow_source_note",
        "investment_source_note",
        "operating_cash_flow_extraction_method",
        "investment_extraction_method",
        "source_currency",
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
            "# Strength Prompt 29. Cashflow recovery pressure panel",
            "",
            "## Summary",
            "",
            f"- total rows: `{len(output_rows)}`",
            f"- `comparability_flag = yes`: `{comparable_yes}`",
            f"- `comparability_flag = no`: `{comparable_no}`",
            f"- `investment_sign_flag = negative_raw_abs_used`: `{negative_investment_count}`",
            "",
            "## Comparable peer-periods",
            "",
            periods_text,
            "",
            "## Key interpretation",
            "",
            "- This panel uses direct operating cash flow from Korean cash-flow statements and SEC iXBRL cash-flow tags wherever possible; it does not fall back to pretax-income proxies.",
            "- `infra_traffic_ott` uses `capex` as the platform-investment base, while the music peer groups use `content_investment` as the content-investment base.",
            "- `Spotify` is partially salvaged through a direct HTML-table fallback for the interim 6-K, but `mus_streaming_paid_core` still fails the matched comparison because `Dreamus` has negative direct operating cash flow in every available filing and `Kakao Entertainment` has no filing row.",
            "- As a result, this prompt isolates cash-flow burden more narrowly than the earlier recovery-horizon step and is designed to feed the direct `I_risk_narrow` construction in the next prompt.",
        ]
    )
    LOG_PATH.write_text(log_text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
