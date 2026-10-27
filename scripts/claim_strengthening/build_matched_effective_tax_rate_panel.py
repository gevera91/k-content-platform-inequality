from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CORE_SAMPLE_PATH = (
    PROJECT_ROOT
    / "data/registry/claim_strengthening/reverse_discrimination_core_sample_v1.csv"
)
FINANCIAL_EXTRACTION_PATH = (
    PROJECT_ROOT / "data/interim/financial_extraction_panel.csv"
)
OUTPUT_PATH = (
    PROJECT_ROOT
    / "data/processed/claim_strengthening/matched_effective_tax_rate_panel.csv"
)
LOG_PATH = (
    PROJECT_ROOT
    / "logs/claim_strengthening/matched_effective_tax_rate_log.md"
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def normalize_role(analysis_role: str) -> str:
    if analysis_role.startswith("korean_"):
        return "korean"
    if analysis_role.startswith("global_"):
        return "global"
    return "other"


def period_granularity(fiscal_period: str) -> str:
    if fiscal_period.startswith("FY"):
        return "annual"
    if "Q" in fiscal_period:
        return "quarterly"
    if "H" in fiscal_period:
        return "semiannual"
    return "other"


def safe_float(value: str) -> float | None:
    if value == "":
        return None
    return float(value)


def main() -> None:
    core_rows = [row for row in read_csv(CORE_SAMPLE_PATH) if row["include_flag"] == "yes"]
    core_firms = {row["firm_std"] for row in core_rows}
    fin_rows = [
        row
        for row in read_csv(FINANCIAL_EXTRACTION_PATH)
        if row["firm_std"] in core_firms
        and row["metric_name"] in {"pretax_income", "tax_expense"}
    ]

    metric_by_firm_period: dict[tuple[str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    periods_by_firm: dict[str, set[str]] = defaultdict(set)

    for row in fin_rows:
        key = (row["firm_std"], row["fiscal_period"])
        metric_by_firm_period[key][row["metric_name"]] = row
        periods_by_firm[row["firm_std"]].add(row["fiscal_period"])

    output_rows: list[dict[str, str]] = []
    status_counter: Counter[str] = Counter()
    missing_firms = sorted({row["firm_std"] for row in core_rows if row["firm_std"] not in periods_by_firm})

    for core_row in core_rows:
        firm = core_row["firm_std"]
        for fiscal_period in sorted(periods_by_firm.get(firm, set())):
            metric_bucket = metric_by_firm_period[(firm, fiscal_period)]
            pretax_row = metric_bucket.get("pretax_income")
            tax_row = metric_bucket.get("tax_expense")

            pretax_income = (
                safe_float(pretax_row["metric_value_raw"]) if pretax_row is not None else None
            )
            tax_expense = (
                safe_float(tax_row["metric_value_raw"]) if tax_row is not None else None
            )

            effective_tax_rate = ""
            exclude_reason = ""

            if pretax_row is None or tax_row is None:
                comparability_flag = "no"
                exclude_reason = "missing_tax_or_pretax_pair"
            elif pretax_income is None or tax_expense is None:
                comparability_flag = "no"
                exclude_reason = "missing_numeric_value"
            elif pretax_income == 0:
                comparability_flag = "no"
                exclude_reason = "zero_pretax_income"
            else:
                effective_tax_rate = f"{tax_expense / pretax_income:.6f}"
                comparability_flag = "pending_match_check"

            output_rows.append(
                {
                    "peer_group_id": core_row["peer_group_id"],
                    "firm_std": core_row["firm_std"],
                    "service_std": core_row["service_std"],
                    "country_std": core_row["country_std"],
                    "analysis_role": core_row["analysis_role"],
                    "fiscal_period": fiscal_period,
                    "period_granularity": period_granularity(fiscal_period),
                    "pretax_income_raw": "" if pretax_income is None else f"{pretax_income:.0f}",
                    "tax_expense_raw": "" if tax_expense is None else f"{tax_expense:.0f}",
                    "effective_tax_rate": effective_tax_rate,
                    "comparability_flag": comparability_flag,
                    "exclude_reason": exclude_reason,
                    "source_currency": (
                        pretax_row["currency"] if pretax_row is not None else (tax_row["currency"] if tax_row is not None else "")
                    ),
                    "pretax_source_note": pretax_row["source_page_or_note"] if pretax_row is not None else "",
                    "tax_source_note": tax_row["source_page_or_note"] if tax_row is not None else "",
                    "pretax_extraction_method": pretax_row["extraction_method"] if pretax_row is not None else "",
                    "tax_extraction_method": tax_row["extraction_method"] if tax_row is not None else "",
                    "matched_peer_observation_count": "",
                    "matched_korean_observation_count": "",
                    "matched_global_observation_count": "",
                }
            )

    comparable_counts: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"korean": 0, "global": 0})

    for row in output_rows:
        if row["effective_tax_rate"] != "":
            side = normalize_role(row["analysis_role"])
            if side in {"korean", "global"}:
                comparable_counts[(row["peer_group_id"], row["fiscal_period"])][side] += 1

    for row in output_rows:
        if row["comparability_flag"] == "pending_match_check":
            counts = comparable_counts[(row["peer_group_id"], row["fiscal_period"])]
            row["matched_korean_observation_count"] = str(counts["korean"])
            row["matched_global_observation_count"] = str(counts["global"])
            row["matched_peer_observation_count"] = str(counts["korean"] + counts["global"])

            if counts["korean"] > 0 and counts["global"] > 0:
                row["comparability_flag"] = "yes"
                row["exclude_reason"] = ""
            elif counts["global"] == 0:
                row["comparability_flag"] = "no"
                row["exclude_reason"] = "no_global_peer_same_fiscal_period"
            elif counts["korean"] == 0:
                row["comparability_flag"] = "no"
                row["exclude_reason"] = "no_korean_anchor_same_fiscal_period"
            else:
                row["comparability_flag"] = "no"
                row["exclude_reason"] = "insufficient_same_period_match"
        else:
            counts = comparable_counts[(row["peer_group_id"], row["fiscal_period"])]
            row["matched_korean_observation_count"] = str(counts["korean"])
            row["matched_global_observation_count"] = str(counts["global"])
            row["matched_peer_observation_count"] = str(counts["korean"] + counts["global"])

        status_counter[row["exclude_reason"] or "comparable_yes"] += 1

    fieldnames = [
        "peer_group_id",
        "firm_std",
        "service_std",
        "country_std",
        "analysis_role",
        "fiscal_period",
        "period_granularity",
        "pretax_income_raw",
        "tax_expense_raw",
        "effective_tax_rate",
        "comparability_flag",
        "exclude_reason",
        "matched_peer_observation_count",
        "matched_korean_observation_count",
        "matched_global_observation_count",
        "source_currency",
        "pretax_source_note",
        "tax_source_note",
        "pretax_extraction_method",
        "tax_extraction_method",
    ]
    write_csv(OUTPUT_PATH, output_rows, fieldnames)

    comparable_rows = [row for row in output_rows if row["comparability_flag"] == "yes"]
    comparable_periods = sorted(
        {
            (row["peer_group_id"], row["fiscal_period"])
            for row in comparable_rows
        }
    )

    log_lines = [
        "# Strength Prompt 20. 유효세율 matched extraction 재실행",
        "",
        "- `matched_effective_tax_rate_panel.csv`는 core sample include row만 남긴 뒤 `financial_extraction_panel.csv`의 `pretax_income`, `tax_expense`를 짝지어 유효세율을 다시 계산한 결과다.",
        "- 유효세율은 `tax_expense / pretax_income`으로 계산했고, 같은 `peer_group_id` 안에서 같은 `fiscal_period`에 한국 anchor와 글로벌 peer가 모두 존재할 때만 `comparability_flag = yes`를 부여했다.",
        "- 쌍이 없는 경우나 같은 기간 cross-side 관측이 없으면 점수를 남기더라도 비교불가로 표시했다.",
        "",
        f"- total rows: `{len(output_rows)}`",
        f"- comparable rows: `{len(comparable_rows)}`",
        f"- comparable peer-period cells: `{len(comparable_periods)}`",
        f"- firms with no extracted tax-rate candidate: `{', '.join(missing_firms) if missing_firms else 'none'}`",
        "",
        "## Exclude/comparability distribution",
        "",
    ]

    for key in sorted(status_counter):
        log_lines.append(f"- `{key}`: `{status_counter[key]}`")

    log_lines.extend(
        [
            "",
            "## Comparable peer-period cells",
            "",
        ]
    )
    for peer_group_id, fiscal_period in comparable_periods:
        counts = comparable_counts[(peer_group_id, fiscal_period)]
        log_lines.append(
            f"- `{peer_group_id} | {fiscal_period}`: korean `{counts['korean']}`, global `{counts['global']}`"
        )

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
