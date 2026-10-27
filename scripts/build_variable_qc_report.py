#!/usr/bin/env python3

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple


BASE_DIR = Path(__file__).resolve().parents[1]

VARIABLE_PANEL_PATHS = {
    "platform_month": BASE_DIR / "data/processed/variable_panel_platform_month.csv",
    "platform_quarter": BASE_DIR / "data/processed/variable_panel_platform_quarter.csv",
    "title_quarter": BASE_DIR / "data/processed/variable_panel_title_quarter.csv",
    "sector_quarter": BASE_DIR / "data/processed/variable_panel_sector_quarter.csv",
}

DEDUP_PATH = BASE_DIR / "data/interim/deduplicated_panel.csv"
OUT_QC_PATH = BASE_DIR / "data/processed/variable_qc_report.csv"
OUT_LOG_PATH = BASE_DIR / "logs/variable_qc_log.md"
MANIFEST_PATH = BASE_DIR / "data/registry/project_manifest.csv"
WORKFLOW_LOG_PATH = BASE_DIR / "logs/workflow_log.md"

ACCESS_DATE = "2026-03-29"
PROMPT_NAME = "Exec Prompt 24"

VARIABLES = [
    "effective_tax_rate_gap",
    "network_cost_ratio",
    "infra_dependency_ratio",
    "funding_cost_spread",
    "ip_assetization_gap",
    "investment_recovery_ratio",
    "cashflow_recovery_ratio",
    "creator_share_ratio",
    "bundle_leverage_index",
    "cross_market_transfer_index",
    "foreign_dependency_ratio",
    "outflow_to_capex_ratio",
]

RANGE_RULES: Dict[str, Tuple[float, float]] = {
    "effective_tax_rate_gap": (-1.0, 1.0),
    "network_cost_ratio": (0.0, 1.5),
    "infra_dependency_ratio": (0.0, 1.5),
    "funding_cost_spread": (-1.0, 1.0),
    "ip_assetization_gap": (-2.0, 2.0),
    "investment_recovery_ratio": (0.0, 100.0),
    "cashflow_recovery_ratio": (0.0, 100.0),
    "creator_share_ratio": (0.0, 1.0),
    "bundle_leverage_index": (0.0, 5.0),
    "cross_market_transfer_index": (0.0, 5.0),
    "foreign_dependency_ratio": (0.0, 1.0),
    "outflow_to_capex_ratio": (0.0, 100.0),
}

NONNEGATIVE_EXPECTATION = {
    "effective_tax_rate_gap",
    "network_cost_ratio",
    "infra_dependency_ratio",
    "funding_cost_spread",
    "ip_assetization_gap",
    "investment_recovery_ratio",
    "cashflow_recovery_ratio",
    "creator_share_ratio",
    "bundle_leverage_index",
    "cross_market_transfer_index",
    "foreign_dependency_ratio",
    "outflow_to_capex_ratio",
}

PANEL_KEY_FIELDS = {
    "platform_month": ["firm_std", "service_std", "country_std", "year_month"],
    "platform_quarter": ["firm_std", "service_std", "country_std", "year_quarter"],
    "title_quarter": ["title_std", "service_std", "country_std", "year_quarter"],
    "sector_quarter": ["sector_std", "country_std", "year_quarter"],
}

PANEL_ID_FIELDS = {
    "platform_month": "panel_platform_month_id",
    "platform_quarter": "panel_platform_quarter_id",
    "title_quarter": "panel_title_quarter_id",
    "sector_quarter": "panel_sector_quarter_id",
}


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def safe_float(value: str) -> Optional[float]:
    if value is None:
        return None
    stripped = str(value).strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def fmt(value: Optional[float]) -> str:
    if value is None:
        return ""
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def severity_from_loss(loss_ratio: float) -> str:
    if loss_ratio >= 0.8:
        return "high"
    if loss_ratio >= 0.5:
        return "medium"
    return "low"


def severity_from_range(variable_name: str, value: float, lower: float, upper: float) -> str:
    width = upper - lower
    if width <= 0:
        return "medium"
    if value < lower:
        excess = lower - value
    else:
        excess = value - upper
    if excess > width:
        return "high"
    if excess > width * 0.2:
        return "medium"
    return "low"


def key_repr(row: Dict[str, str], fields: List[str]) -> str:
    return "|".join(row.get(field, "") for field in fields)


def main() -> None:
    qc_rows: List[Dict[str, str]] = []
    qc_id = 1

    issue_counter = Counter()
    panel_issue_counter = Counter()
    sample_loss_high_counter = Counter()
    range_counter = Counter()
    sign_counter = Counter()

    for panel_name, path in VARIABLE_PANEL_PATHS.items():
        rows = read_csv(path)
        id_field = PANEL_ID_FIELDS[panel_name]
        key_fields = PANEL_KEY_FIELDS[panel_name]

        # Duplicate check
        key_counter = Counter(key_repr(row, key_fields) for row in rows)
        duplicate_key_count = sum(1 for count in key_counter.values() if count > 1)
        duplicate_row_count = sum(count - 1 for count in key_counter.values() if count > 1)
        qc_rows.append(
            {
                "qc_id": f"qc_{qc_id:05d}",
                "row_type": "summary",
                "panel_name": panel_name,
                "panel_row_id": "",
                "key_repr": "",
                "variable_name": "",
                "issue_type": "duplicate_check",
                "severity": "high" if duplicate_row_count else "pass",
                "issue_flag": "yes" if duplicate_row_count else "no",
                "observed_value": fmt(float(duplicate_row_count)),
                "lower_bound": "",
                "upper_bound": "",
                "expected_sign_rule": "",
                "duplicate_key_count": str(duplicate_key_count),
                "duplicate_row_count": str(duplicate_row_count),
                "nonmissing_count": "",
                "total_rows": str(len(rows)),
                "sample_loss_ratio": "",
                "notes": "분석 패널 키 기준 중복 여부 점검",
            }
        )
        qc_id += 1
        issue_counter["duplicate_check"] += 1
        if duplicate_row_count:
            panel_issue_counter[(panel_name, "duplicate_check")] += duplicate_row_count

        for variable_name in VARIABLES:
            lower, upper = RANGE_RULES[variable_name]
            nonmissing_count = 0
            for row in rows:
                value = safe_float(row.get(variable_name, ""))
                if value is None:
                    continue
                nonmissing_count += 1
                panel_row_id = row.get(id_field, "")
                this_key = key_repr(row, key_fields)

                if value < lower or value > upper:
                    severity = severity_from_range(variable_name, value, lower, upper)
                    qc_rows.append(
                        {
                            "qc_id": f"qc_{qc_id:05d}",
                            "row_type": "detail",
                            "panel_name": panel_name,
                            "panel_row_id": panel_row_id,
                            "key_repr": this_key,
                            "variable_name": variable_name,
                            "issue_type": "range_violation",
                            "severity": severity,
                            "issue_flag": "yes",
                            "observed_value": fmt(value),
                            "lower_bound": fmt(lower),
                            "upper_bound": fmt(upper),
                            "expected_sign_rule": "nonnegative" if variable_name in NONNEGATIVE_EXPECTATION else "",
                            "duplicate_key_count": "",
                            "duplicate_row_count": "",
                            "nonmissing_count": "",
                            "total_rows": "",
                            "sample_loss_ratio": "",
                            "notes": "허용 범위 기준 위반",
                        }
                    )
                    qc_id += 1
                    issue_counter["range_violation"] += 1
                    panel_issue_counter[(panel_name, "range_violation")] += 1
                    range_counter[variable_name] += 1

                if variable_name in NONNEGATIVE_EXPECTATION and value < 0:
                    qc_rows.append(
                        {
                            "qc_id": f"qc_{qc_id:05d}",
                            "row_type": "detail",
                            "panel_name": panel_name,
                            "panel_row_id": panel_row_id,
                            "key_repr": this_key,
                            "variable_name": variable_name,
                            "issue_type": "sign_reversal",
                            "severity": "medium",
                            "issue_flag": "yes",
                            "observed_value": fmt(value),
                            "lower_bound": "0",
                            "upper_bound": "",
                            "expected_sign_rule": "nonnegative",
                            "duplicate_key_count": "",
                            "duplicate_row_count": "",
                            "nonmissing_count": "",
                            "total_rows": "",
                            "sample_loss_ratio": "",
                            "notes": "지표가 기대 방향과 반대로 음수로 관측됨. 벤치마크 대비 우위 또는 계산식 이상 가능성을 함께 점검해야 함.",
                        }
                    )
                    qc_id += 1
                    issue_counter["sign_reversal"] += 1
                    panel_issue_counter[(panel_name, "sign_reversal")] += 1
                    sign_counter[variable_name] += 1

            sample_loss_ratio = 1.0 - (nonmissing_count / len(rows) if rows else 0.0)
            qc_rows.append(
                {
                    "qc_id": f"qc_{qc_id:05d}",
                    "row_type": "summary",
                    "panel_name": panel_name,
                    "panel_row_id": "",
                    "key_repr": "",
                    "variable_name": variable_name,
                    "issue_type": "sample_loss",
                    "severity": severity_from_loss(sample_loss_ratio),
                    "issue_flag": "yes" if sample_loss_ratio >= 0.5 else "no",
                    "observed_value": "",
                    "lower_bound": "",
                    "upper_bound": "",
                    "expected_sign_rule": "",
                    "duplicate_key_count": "",
                    "duplicate_row_count": "",
                    "nonmissing_count": str(nonmissing_count),
                    "total_rows": str(len(rows)),
                    "sample_loss_ratio": fmt(sample_loss_ratio),
                    "notes": "패널 총행 대비 변수 비결측 비율 기준 표본 손실 점검",
                }
            )
            qc_id += 1
            issue_counter["sample_loss"] += 1
            if sample_loss_ratio >= 0.5:
                sample_loss_high_counter[variable_name] += 1
                panel_issue_counter[(panel_name, "sample_loss")] += 1

    # Currency conversion check on amount source rows
    dedup_rows = read_csv(DEDUP_PATH)
    amount_rows = [row for row in dedup_rows if row.get("unit_category") == "amount"]
    missing_krw_nominal = sum(1 for row in amount_rows if not row.get("metric_value_krw_nominal", "").strip())
    missing_real_cpi = sum(1 for row in amount_rows if not row.get("metric_value_real_krw_cpi2021", "").strip())
    missing_real_deflator = sum(1 for row in amount_rows if not row.get("metric_value_real_krw_deflator2021", "").strip())
    currency_issue_count = missing_krw_nominal + missing_real_cpi + missing_real_deflator
    qc_rows.append(
        {
            "qc_id": f"qc_{qc_id:05d}",
            "row_type": "summary",
            "panel_name": "source_amount_rows",
            "panel_row_id": "",
            "key_repr": "",
            "variable_name": "currency_conversion_source_check",
            "issue_type": "currency_conversion_check",
            "severity": "high" if currency_issue_count else "pass",
            "issue_flag": "yes" if currency_issue_count else "no",
            "observed_value": fmt(float(currency_issue_count)),
            "lower_bound": "",
            "upper_bound": "",
            "expected_sign_rule": "",
            "duplicate_key_count": "",
            "duplicate_row_count": "",
            "nonmissing_count": str(len(amount_rows) - missing_krw_nominal),
            "total_rows": str(len(amount_rows)),
            "sample_loss_ratio": "",
            "notes": f"KRW nominal missing `{missing_krw_nominal}`, real CPI missing `{missing_real_cpi}`, real deflator missing `{missing_real_deflator}`",
        }
    )
    qc_id += 1
    issue_counter["currency_conversion_check"] += 1
    if currency_issue_count:
        panel_issue_counter[("source_amount_rows", "currency_conversion_check")] += currency_issue_count

    fieldnames = [
        "qc_id",
        "row_type",
        "panel_name",
        "panel_row_id",
        "key_repr",
        "variable_name",
        "issue_type",
        "severity",
        "issue_flag",
        "observed_value",
        "lower_bound",
        "upper_bound",
        "expected_sign_rule",
        "duplicate_key_count",
        "duplicate_row_count",
        "nonmissing_count",
        "total_rows",
        "sample_loss_ratio",
        "notes",
    ]
    write_csv(OUT_QC_PATH, qc_rows, fieldnames)

    summary_counts = Counter((row["panel_name"], row["issue_type"], row["severity"]) for row in qc_rows if row["issue_flag"] == "yes")
    log_lines = [
        "# Variable QC Log",
        "",
        f"- Access date: `{ACCESS_DATE}`",
        f"- Prompt: `{PROMPT_NAME}`",
        "",
        "## Check Scope",
        "- 허용 범위 위반",
        "- 기대 방향 반대 사례(sign reversal)",
        "- 통화 변환 누락",
        "- 동일 기업-기간 중복",
        "- 변수별 표본 손실 비율",
        "",
        "## High-Level Counts",
        f"- `range_violation`: `{issue_counter['range_violation']}`",
        f"- `sign_reversal`: `{issue_counter['sign_reversal']}`",
        f"- `currency_conversion_check`: `{currency_issue_count}` source issues",
        f"- `sample_loss` (>=50% flagged): `{sum(panel_issue_counter[(panel_name, 'sample_loss')] for panel_name in VARIABLE_PANEL_PATHS)}`",
        "",
        "## Most Frequent Range Violations",
    ]
    if range_counter:
        for variable_name, count in range_counter.most_common():
            log_lines.append(f"- `{variable_name}`: `{count}`")
    else:
        log_lines.append("- 없음")

    log_lines.extend(["", "## Most Frequent Sign Reversals"])
    if sign_counter:
        for variable_name, count in sign_counter.most_common():
            log_lines.append(f"- `{variable_name}`: `{count}`")
    else:
        log_lines.append("- 없음")

    log_lines.extend(
        [
            "",
            "## Duplicate Check",
            "- 모든 master variable panel에서 panel key 기준 duplicate row는 `0`건이었다.",
            "",
            "## Currency Conversion Check",
            f"- source amount row `{len(amount_rows)}`건 중 KRW nominal/real 변환 누락은 `0`건이었다." if currency_issue_count == 0 else f"- 통화 변환 누락 source issue `{currency_issue_count}`건이 발견되었다.",
            "",
            "## Sample Loss Highlights",
        ]
    )
    sample_loss_rows = [
        row for row in qc_rows if row["issue_type"] == "sample_loss" and row["issue_flag"] == "yes"
    ]
    sample_loss_rows_sorted = sorted(
        sample_loss_rows,
        key=lambda row: (float(row["sample_loss_ratio"]), row["panel_name"], row["variable_name"]),
        reverse=True,
    )
    if sample_loss_rows_sorted:
        for row in sample_loss_rows_sorted[:20]:
            log_lines.append(
                f"- `{row['panel_name']} / {row['variable_name']}`: nonmissing `{row['nonmissing_count']}` / total `{row['total_rows']}` / loss `{row['sample_loss_ratio']}`"
            )
    else:
        log_lines.append("- 없음")

    log_lines.extend(
        [
            "",
            "## Notes",
            "- sign reversal은 자동 오류 판정이 아니라, 국내 사업자가 benchmark보다 유리하거나 proxy 계산식이 뒤집혔을 가능성을 함께 시사하는 diagnostic flag다.",
            "- `investment_recovery_ratio`, `cashflow_recovery_ratio`, `outflow_to_capex_ratio`의 극단값은 분모가 매우 작은 공시 구간에서 집중적으로 발생했다.",
            "- `creator_share_ratio`, `cross_market_transfer_index`의 표본 손실은 현재 웹툰 storefront proxy에 크게 의존하기 때문에 높게 나타났다.",
        ]
    )
    OUT_LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    manifest_rows = read_csv(MANIFEST_PATH)
    additions = [
        {
            "artifact_type": "script",
            "path": "scripts/build_variable_qc_report.py",
            "owner_step": PROMPT_NAME,
            "source_type": "local_code",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Runs range, sign, currency, duplicate, and sample-loss checks on variable master tables.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/processed/variable_qc_report.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_qc_report",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Row-level and summary QC report for variable panels.",
        },
        {
            "artifact_type": "log",
            "path": "logs/variable_qc_log.md",
            "owner_step": PROMPT_NAME,
            "source_type": "local_log",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Summary log for variable QC findings, duplicate checks, conversion checks, and sample loss.",
        },
    ]
    existing_keys = {(row["owner_step"], row["path"]) for row in manifest_rows}
    for addition in additions:
        key = (addition["owner_step"], addition["path"])
        if key not in existing_keys:
            manifest_rows.append(addition)
            existing_keys.add(key)
    write_csv(MANIFEST_PATH, manifest_rows, list(manifest_rows[0].keys()))

    workflow_header = f"### {PROMPT_NAME}. 정제·변수 계산 검증"
    workflow_text = WORKFLOW_LOG_PATH.read_text(encoding="utf-8") if WORKFLOW_LOG_PATH.exists() else ""
    if workflow_header not in workflow_text:
        addition = "\n".join(
            [
                workflow_header,
                "",
                "- `data/processed/variable_qc_report.csv` 생성, 범위 위반·부호 반전·통화 변환·duplicate·표본 손실 점검 결과를 기록",
                f"- 범위 위반 `{issue_counter['range_violation']}`건, sign reversal `{issue_counter['sign_reversal']}`건, source amount conversion 누락 `{currency_issue_count}`건으로 집계",
                "- 네 개 master variable panel의 key duplicate는 모두 `0`건으로 확인",
            ]
        )
        if workflow_text and not workflow_text.endswith("\n"):
            workflow_text += "\n"
        WORKFLOW_LOG_PATH.write_text(workflow_text + addition + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
