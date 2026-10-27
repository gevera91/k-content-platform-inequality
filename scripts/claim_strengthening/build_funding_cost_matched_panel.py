from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parents[2]
CORE_SAMPLE_PATH = ROOT / "data/registry/claim_strengthening/reverse_discrimination_core_sample_v1.csv"
FINANCIAL_PATH = ROOT / "data/interim/financial_extraction_panel.csv"
OUTPUT_PATH = ROOT / "data/processed/claim_strengthening/funding_cost_matched_panel.csv"
LOG_PATH = ROOT / "logs/claim_strengthening/funding_cost_matched_log.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def parse_fiscal_period(period: str) -> tuple[int, int]:
    if not period:
        return (0, 0)
    if period.startswith("FY"):
        return (int(period[2:]), 12)
    if "Q" in period:
        year, quarter = period.split("Q", 1)
        return (int(year), int(quarter) * 3)
    if "H" in period:
        year, half = period.split("H", 1)
        return (int(year), int(half) * 6)
    return (0, 0)


def fmt_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}"


def is_korean_role(role: str) -> bool:
    return "korean" in role


def is_global_role(role: str) -> bool:
    return "global" in role


def main() -> None:
    core_rows = [row for row in read_csv(CORE_SAMPLE_PATH) if row["include_flag"] == "yes"]
    financial_rows = read_csv(FINANCIAL_PATH)

    fin_by_firm_period: dict[tuple[str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    firm_periods: dict[str, set[str]] = defaultdict(set)
    for row in financial_rows:
        if row["metric_name"] not in {"interest_expense", "debt"}:
            continue
        key = (row["firm_std"], row["fiscal_period"])
        fin_by_firm_period[key][row["metric_name"]] = row
        firm_periods[row["firm_std"]].add(row["fiscal_period"])

    provisional_rows: list[dict[str, object]] = []
    for core_row in core_rows:
        periods = sorted(firm_periods.get(core_row["firm_std"], set()), key=parse_fiscal_period)
        if not periods:
            provisional_rows.append(
                {
                    "peer_group_id": core_row["peer_group_id"],
                    "firm_std": core_row["firm_std"],
                    "service_std": core_row["service_std"],
                    "country_std": core_row["country_std"],
                    "analysis_role": core_row["analysis_role"],
                    "fiscal_period": "",
                    "period_granularity": "",
                    "interest_expense_raw": "",
                    "interest_expense_for_rate": "",
                    "debt_raw": "",
                    "borrowing_rate_proxy": "",
                    "opposite_side_reference_rate": "",
                    "funding_cost_spread_signed": "",
                    "korean_minus_global_spread": "",
                    "comparability_flag": "no",
                    "exclude_reason": "no_financial_metric_rows",
                    "matched_peer_observation_count": "0",
                    "matched_korean_observation_count": "0",
                    "matched_global_observation_count": "0",
                    "interest_sign_flag": "",
                    "source_currency": "",
                    "interest_source_note": "",
                    "debt_source_note": "",
                    "interest_extraction_method": "",
                    "debt_extraction_method": "",
                }
            )
            continue

        for fiscal_period in periods:
            metric_map = fin_by_firm_period[(core_row["firm_std"], fiscal_period)]
            interest_row = metric_map.get("interest_expense")
            debt_row = metric_map.get("debt")
            interest_raw = float(interest_row["metric_value_raw"]) if interest_row and interest_row["metric_value_raw"] else None
            debt_raw = float(debt_row["metric_value_raw"]) if debt_row and debt_row["metric_value_raw"] else None

            exclude_reason = ""
            interest_for_rate = None
            borrowing_rate = None
            interest_sign_flag = ""
            if interest_raw is None or debt_raw is None:
                exclude_reason = "missing_interest_or_debt_pair"
            elif debt_raw <= 0:
                exclude_reason = "nonpositive_debt_not_interpretable"
            else:
                interest_for_rate = abs(interest_raw)
                if interest_raw < 0:
                    interest_sign_flag = "negative_raw_abs_used"
                elif interest_raw == 0:
                    interest_sign_flag = "zero_raw"
                else:
                    interest_sign_flag = "positive_raw"
                borrowing_rate = interest_for_rate / debt_raw

            period_granularity = ""
            if interest_row:
                period_granularity = interest_row["period_granularity"]
            elif debt_row:
                period_granularity = debt_row["period_granularity"]

            provisional_rows.append(
                {
                    "peer_group_id": core_row["peer_group_id"],
                    "firm_std": core_row["firm_std"],
                    "service_std": core_row["service_std"],
                    "country_std": core_row["country_std"],
                    "analysis_role": core_row["analysis_role"],
                    "fiscal_period": fiscal_period,
                    "period_granularity": period_granularity,
                    "interest_expense_raw": fmt_float(interest_raw),
                    "interest_expense_for_rate": fmt_float(interest_for_rate),
                    "debt_raw": fmt_float(debt_raw),
                    "borrowing_rate_proxy": fmt_float(borrowing_rate),
                    "opposite_side_reference_rate": "",
                    "funding_cost_spread_signed": "",
                    "korean_minus_global_spread": "",
                    "comparability_flag": "no",
                    "exclude_reason": exclude_reason,
                    "matched_peer_observation_count": "0",
                    "matched_korean_observation_count": "0",
                    "matched_global_observation_count": "0",
                    "interest_sign_flag": interest_sign_flag,
                    "source_currency": (
                        interest_row["currency"] if interest_row else (debt_row["currency"] if debt_row else "")
                    ),
                    "interest_source_note": interest_row["source_page_or_note"] if interest_row else "",
                    "debt_source_note": debt_row["source_page_or_note"] if debt_row else "",
                    "interest_extraction_method": interest_row["extraction_method"] if interest_row else "",
                    "debt_extraction_method": debt_row["extraction_method"] if debt_row else "",
                }
            )

    valid_group_rows: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in provisional_rows:
        if row["borrowing_rate_proxy"] == "":
            continue
        valid_group_rows[(str(row["peer_group_id"]), str(row["fiscal_period"]))].append(row)

    for row in provisional_rows:
        group_key = (str(row["peer_group_id"]), str(row["fiscal_period"]))
        valid_rows = valid_group_rows.get(group_key, [])
        korean_rates = [float(r["borrowing_rate_proxy"]) for r in valid_rows if is_korean_role(str(r["analysis_role"]))]
        global_rates = [float(r["borrowing_rate_proxy"]) for r in valid_rows if is_global_role(str(r["analysis_role"]))]
        row["matched_peer_observation_count"] = str(len(valid_rows))
        row["matched_korean_observation_count"] = str(len(korean_rates))
        row["matched_global_observation_count"] = str(len(global_rates))

        if row["borrowing_rate_proxy"] == "":
            if row["exclude_reason"] == "":
                row["exclude_reason"] = "missing_interest_or_debt_pair"
            continue

        if len(korean_rates) == 0:
            row["exclude_reason"] = "no_korean_anchor_same_fiscal_period"
            continue
        if len(global_rates) == 0:
            row["exclude_reason"] = "no_global_peer_same_fiscal_period"
            continue

        global_reference = median(global_rates)
        korean_reference = sum(korean_rates) / len(korean_rates)
        row_rate = float(row["borrowing_rate_proxy"])
        if is_korean_role(str(row["analysis_role"])):
            opposite_reference = global_reference
        else:
            opposite_reference = korean_reference
        row["opposite_side_reference_rate"] = fmt_float(opposite_reference)
        row["funding_cost_spread_signed"] = fmt_float(row_rate - opposite_reference)
        row["korean_minus_global_spread"] = fmt_float(korean_reference - global_reference)
        row["comparability_flag"] = "yes"
        row["exclude_reason"] = ""

    fieldnames = [
        "peer_group_id",
        "firm_std",
        "service_std",
        "country_std",
        "analysis_role",
        "fiscal_period",
        "period_granularity",
        "interest_expense_raw",
        "interest_expense_for_rate",
        "debt_raw",
        "borrowing_rate_proxy",
        "opposite_side_reference_rate",
        "funding_cost_spread_signed",
        "korean_minus_global_spread",
        "comparability_flag",
        "exclude_reason",
        "matched_peer_observation_count",
        "matched_korean_observation_count",
        "matched_global_observation_count",
        "interest_sign_flag",
        "source_currency",
        "interest_source_note",
        "debt_source_note",
        "interest_extraction_method",
        "debt_extraction_method",
    ]
    write_csv(OUTPUT_PATH, provisional_rows, fieldnames)

    comparability_counter = Counter(row["comparability_flag"] for row in provisional_rows)
    exclude_counter = Counter(row["exclude_reason"] for row in provisional_rows if row["exclude_reason"])
    comparable_rows = [row for row in provisional_rows if row["comparability_flag"] == "yes"]
    comparable_groups = sorted(
        {(row["peer_group_id"], row["fiscal_period"]) for row in comparable_rows},
        key=lambda x: (x[0], parse_fiscal_period(x[1])),
    )
    negative_flag_count = sum(1 for row in provisional_rows if row["interest_sign_flag"] == "negative_raw_abs_used")

    log_lines = [
        "# Strength Prompt 26. 자금조달 비용 matched panel 작성",
        "",
        "- `funding_cost_matched_panel.csv`은 core sample include row를 기준으로 `interest_expense`와 `debt`를 다시 짝지어 `borrowing_rate_proxy = abs(interest_expense) / debt`를 계산한 matched funding-cost panel이다.",
        "- 이번 단계는 공시상 비용 항목의 부호 관행 차이를 줄이기 위해 borrowing-rate proxy 계산에 `abs(interest_expense)`를 사용하되, raw 값과 sign flag는 그대로 보존했다.",
        "- `comparability_flag = yes`는 같은 `peer_group_id`와 같은 `fiscal_period`에서 유효 borrowing-rate row가 한국 side와 글로벌 side 모두 존재할 때만 부여했다.",
        "",
        f"- total rows: `{len(provisional_rows)}`",
        f"- comparable yes: `{comparability_counter.get('yes', 0)}`",
        f"- comparable no: `{comparability_counter.get('no', 0)}`",
        f"- negative raw interest rows normalized by abs(): `{negative_flag_count}`",
        "",
        "## Exclude reasons",
        "",
    ]
    for key, value in sorted(exclude_counter.items()):
        log_lines.append(f"- `{key}`: `{value}`")
    log_lines.extend(["", "## Comparable peer-periods", ""])
    if comparable_groups:
        for peer_group_id, fiscal_period in comparable_groups:
            log_lines.append(f"- `{peer_group_id} | {fiscal_period}`")
    else:
        log_lines.append("- none")

    log_lines.extend(
        [
            "",
            "## Key interpretation",
            "",
            "- `infra_traffic_ott`는 `FY2024`, `2025Q3`, `FY2025`에서 exact-period direct borrowing-rate 비교가 성립한다.",
            "- `mus_label_ip_export`는 `Warner Music`과 `YG`의 `FY2025`만 간신히 매치되고, `JYP`는 현재 debt metric이 없어 같은 기준 borrowing-rate를 만들 수 없다.",
            "- `mus_streaming_paid_core`는 `Spotify` debt metric 부재로 direct matched comparison이 아직 성립하지 않는다.",
            "- 따라서 자금조달 비용 직접 비교는 현재 인프라가 가장 두껍고, 음악 IP는 제한적, 음악 스트리밍은 아직 취약하다는 결론으로 읽는 것이 가장 안전하다.",
        ]
    )
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
