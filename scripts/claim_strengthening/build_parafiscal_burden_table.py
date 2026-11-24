from __future__ import annotations

import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CORE_SAMPLE_PATH = (
    PROJECT_ROOT
    / "data/registry/claim_strengthening/reverse_discrimination_core_sample_v1.csv"
)
INPUT_PATHS = [
    (
        "kr",
        PROJECT_ROOT / "data/interim/claim_strengthening/kr_regulatory_obligations_core.csv",
    ),
    (
        "us",
        PROJECT_ROOT / "data/interim/claim_strengthening/us_regulatory_obligations_core.csv",
    ),
    (
        None,
        PROJECT_ROOT / "data/interim/claim_strengthening/jp_uk_regulatory_obligations_core.csv",
    ),
    (
        None,
        PROJECT_ROOT / "data/interim/claim_strengthening/ca_tw_regulatory_obligations_core.csv",
    ),
]
OUTPUT_PATH = (
    PROJECT_ROOT / "data/processed/claim_strengthening/parafiscal_burden_table.csv"
)
LOG_PATH = (
    PROJECT_ROOT / "logs/claim_strengthening/parafiscal_burden_log.md"
)

RELEVANT_OBLIGATIONS = {
    "REG01": "registration_or_licensing_fee_proxy",
    "TAX02": "special_digital_tax_or_withholding",
    "PARA01": "parafiscal_fund_or_contribution",
    "NET01": "network_payment_or_interconnection",
    "NET02": "network_negotiation_or_procedural_burden",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def normalize_country(row: dict[str, str], fallback_country: str | None) -> str:
    if row.get("country_std"):
        return row["country_std"]
    if fallback_country is not None:
        return fallback_country
    return ""


def annualized_value(applies_flag: str, burden_score: str) -> str:
    if applies_flag == "scope_no":
        return "0"
    if applies_flag == "yes" and burden_score:
        return f"burden_score_proxy_{burden_score}"
    if applies_flag == "yes":
        return "mandatory_not_quantified"
    if applies_flag == "unclear":
        return "not_quantified_unclear"
    return ""


def mandatory_flag(applies_flag: str) -> str:
    if applies_flag == "yes":
        return "yes"
    if applies_flag == "scope_no":
        return "no"
    if applies_flag == "unclear":
        return "unclear"
    return ""


def main() -> None:
    core_rows = [row for row in read_csv(CORE_SAMPLE_PATH) if row["include_flag"] == "yes"]
    core_keys = {
        (row["peer_group_id"], row["firm_std"], row["service_std"]) for row in core_rows
    }
    comparison_country_map = {
        (row["peer_group_id"], row["firm_std"], row["service_std"]): row["country_std"]
        for row in core_rows
    }

    output_rows: list[dict[str, str]] = []

    for fallback_country, path in INPUT_PATHS:
        for row in read_csv(path):
            if row["obligation_id"] not in RELEVANT_OBLIGATIONS:
                continue
            core_key = (row["peer_group_id"], row["firm_std"], row["service_std"])
            if core_key not in core_keys:
                continue

            jurisdiction_country = normalize_country(row, fallback_country)
            applies_flag = row["applies_flag"]
            burden_score = row.get("burden_score", "")

            output_rows.append(
                {
                    "country_std": jurisdiction_country,
                    "service_std": row["service_std"],
                    "burden_type": RELEVANT_OBLIGATIONS[row["obligation_id"]],
                    "annualized_amount_or_rate": annualized_value(applies_flag, burden_score),
                    "mandatory_flag": mandatory_flag(applies_flag),
                    "source_url": row["source_url"],
                    "peer_group_id": row["peer_group_id"],
                    "firm_std": row["firm_std"],
                    "comparison_country_std": comparison_country_map[core_key],
                    "obligation_id": row["obligation_id"],
                    "applies_flag": applies_flag,
                    "burden_score": burden_score,
                    "quantification_basis": (
                        "scope_no_zero"
                        if applies_flag == "scope_no"
                        else "burden_score_proxy"
                        if applies_flag == "yes" and burden_score
                        else "not_quantified_direct_source"
                    ),
                    "source_id": row.get("source_id", ""),
                    "coding_note": row.get("coding_note", ""),
                }
            )

    output_rows.sort(
        key=lambda row: (
            row["peer_group_id"],
            row["country_std"],
            row["service_std"],
            row["burden_type"],
            row["firm_std"],
        )
    )

    fieldnames = [
        "country_std",
        "service_std",
        "burden_type",
        "annualized_amount_or_rate",
        "mandatory_flag",
        "source_url",
        "peer_group_id",
        "firm_std",
        "comparison_country_std",
        "obligation_id",
        "applies_flag",
        "burden_score",
        "quantification_basis",
        "source_id",
        "coding_note",
    ]
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    from collections import Counter

    mandatory_counter = Counter(row["mandatory_flag"] for row in output_rows)
    basis_counter = Counter(row["quantification_basis"] for row in output_rows)
    burden_type_counter = Counter(row["burden_type"] for row in output_rows)

    log_lines = [
        "# Strength Prompt 21. 조세·준조세 부담 테이블 작성",
        "",
        "- `parafiscal_burden_table.csv`는 core sample include row만 남긴 뒤 `REG01`, `TAX02`, `PARA01`, `NET01`, `NET02`만 추려 법인세 외 부담을 서비스-국가 단위로 정리한 표다.",
        "- 현재 direct source set은 실제 요율·금액보다 의무 존재와 강도 코딩이 더 많기 때문에 `annualized_amount_or_rate`는 실제 수치가 없으면 `burden_score_proxy_*`, `0`, `not_quantified_unclear` 같은 표준 문자열로 저장했다.",
        "- 따라서 이 표는 실측 부담률 테이블이 아니라, 다음 direct cost burden panel에서 준조세·망 부담을 점수화할 때 사용할 직접 burden 근거표에 가깝다.",
        "",
        f"- total rows: `{len(output_rows)}`",
        "",
        "## Mandatory distribution",
        "",
    ]

    for key in sorted(mandatory_counter):
        log_lines.append(f"- `{key}`: `{mandatory_counter[key]}`")

    log_lines.extend(["", "## Quantification basis", ""])
    for key in sorted(basis_counter):
        log_lines.append(f"- `{key}`: `{basis_counter[key]}`")

    log_lines.extend(["", "## Burden type coverage", ""])
    for key in sorted(burden_type_counter):
        log_lines.append(f"- `{key}`: `{burden_type_counter[key]}`")

    LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
