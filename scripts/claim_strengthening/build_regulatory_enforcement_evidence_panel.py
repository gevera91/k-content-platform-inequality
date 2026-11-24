#!/usr/bin/env python3
from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

SOURCE_INDEX_PATH = ROOT / "data/interim/regulatory_source_index.csv"
INPUT_SPECS = [
    ("kr", ROOT / "data/interim/claim_strengthening/kr_regulatory_obligations_core.csv"),
    ("us", ROOT / "data/interim/claim_strengthening/us_regulatory_obligations_core.csv"),
    ("mixed", ROOT / "data/interim/claim_strengthening/jp_uk_regulatory_obligations_core.csv"),
    ("mixed", ROOT / "data/interim/claim_strengthening/ca_tw_regulatory_obligations_core.csv"),
]
OUTPUT_PATH = ROOT / "data/processed/claim_strengthening/regulatory_enforcement_evidence_panel.csv"
LOG_PATH = ROOT / "logs/claim_strengthening/regulatory_enforcement_evidence_log.md"

EXPLICIT_ENFORCEMENT_SOURCES = {
    "tw_reg_moda_meta_ad_disclosure",
}
INVESTIGATION_OR_FORMAL_ACTION_SOURCES = {
    "uk_reg_digital_markets_regime_guidance",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def load_source_index() -> dict[str, dict[str, str]]:
    return {row["source_id"]: row for row in read_csv(SOURCE_INDEX_PATH)}


def normalize_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for mode, path in INPUT_SPECS:
        for row in read_csv(path):
            normalized = dict(row)
            if mode in {"kr", "us"}:
                normalized["country_std"] = mode
            rows.append(normalized)
    return rows


def classify_law_exists(applies_flag: str) -> str:
    if applies_flag == "yes":
        return "yes"
    if applies_flag == "scope_no":
        return "no"
    return "unclear"


def classify_enforced(applies_flag: str, source_id: str) -> str:
    if source_id in EXPLICIT_ENFORCEMENT_SOURCES and applies_flag == "yes":
        return "yes"
    if source_id in EXPLICIT_ENFORCEMENT_SOURCES and applies_flag == "scope_no":
        return "no"
    if source_id in EXPLICIT_ENFORCEMENT_SOURCES:
        return "unclear"

    if source_id in INVESTIGATION_OR_FORMAL_ACTION_SOURCES and applies_flag == "yes":
        return "yes"
    if source_id in INVESTIGATION_OR_FORMAL_ACTION_SOURCES and applies_flag == "scope_no":
        return "no"

    if applies_flag == "scope_no":
        return "no"
    return "unclear"


def first_enforcement_date(source: dict[str, str], enforced_flag: str) -> str:
    if enforced_flag != "yes":
        return ""
    for key in ("application_date", "execution_date", "document_date"):
        value = source.get(key, "")
        if value:
            return value
    return ""


def evidence_strength(law_exists_flag: str, enforced_flag: str, source: dict[str, str]) -> str:
    if enforced_flag == "yes":
        return "strong"
    if law_exists_flag == "yes":
        return "medium"
    if law_exists_flag == "unclear":
        return "weak"
    return "none"


def evidence_note(row: dict[str, str], source: dict[str, str], law_exists_flag: str, enforced_flag: str) -> str:
    if enforced_flag == "yes":
        return "Current source contains an explicit enforcement or investigation action that is treated as service-matched enforcement evidence."
    if law_exists_flag == "yes":
        return "Current source is treated as actor-matched law-on-the-books evidence, but not as service-matched enforcement evidence."
    if row["applies_flag"] == "scope_no":
        return "Current official source exists, but its actor scope does not directly match the selected service unit."
    return "Current official source exists, but the extracted material is insufficient to confirm service-level applicability or service-matched enforcement."


def build_rows() -> list[dict[str, str]]:
    source_index = load_source_index()
    input_rows = normalize_rows()
    output_rows: list[dict[str, str]] = []

    for row in input_rows:
        source = source_index[row["source_id"]]
        law_exists_flag = classify_law_exists(row["applies_flag"])
        enforced_flag = classify_enforced(row["applies_flag"], row["source_id"])
        output_rows.append(
            {
                "country_std": row["country_std"],
                "firm_std": row["firm_std"],
                "service_std": row["service_std"],
                "obligation_id": row["obligation_id"],
                "law_exists_flag": law_exists_flag,
                "enforced_flag": enforced_flag,
                "first_enforcement_date": first_enforcement_date(source, enforced_flag),
                "evidence_strength": evidence_strength(law_exists_flag, enforced_flag, source),
                "law_effective_date": row["effective_date"],
                "peer_group_id": row.get("peer_group_id", ""),
                "source_id": row["source_id"],
                "source_url": row["source_url"],
                "raw_file": row["raw_file"],
                "applies_flag_source_table": row["applies_flag"],
                "service_type": row.get("service_type", ""),
                "evidence_note": evidence_note(row, source, law_exists_flag, enforced_flag),
            }
        )

    output_rows.sort(
        key=lambda r: (r["country_std"], r["service_std"], r["obligation_id"], r["firm_std"])
    )
    return output_rows


def write_outputs(rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "country_std",
        "firm_std",
        "service_std",
        "obligation_id",
        "law_exists_flag",
        "enforced_flag",
        "first_enforcement_date",
        "evidence_strength",
        "law_effective_date",
        "peer_group_id",
        "source_id",
        "source_url",
        "raw_file",
        "applies_flag_source_table",
        "service_type",
        "evidence_note",
    ]
    with OUTPUT_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    law_counts: dict[str, int] = {}
    enforced_counts: dict[str, int] = {}
    strength_counts: dict[str, int] = {}
    for row in rows:
        law_counts[row["law_exists_flag"]] = law_counts.get(row["law_exists_flag"], 0) + 1
        enforced_counts[row["enforced_flag"]] = enforced_counts.get(row["enforced_flag"], 0) + 1
        strength_counts[row["evidence_strength"]] = strength_counts.get(row["evidence_strength"], 0) + 1

    with LOG_PATH.open("w") as f:
        f.write("# Strength Prompt 16. 집행 증거 분리표 작성\n\n")
        f.write("- `regulatory_enforcement_evidence_panel.csv`는 국가별 service-obligation 표를 합쳐 `법상 의무 존재`와 `서비스-매칭된 실제 집행`을 분리한 패널이다.\n")
        f.write("- `law_exists_flag`는 기존 source table의 `applies_flag`를 기준으로 `yes/no/unclear`로 재정의했다.\n")
        f.write("  - `yes`: 현재 source set에서 actor-matched law-on-the-books burden이 확인된 경우\n")
        f.write("  - `no`: 현재 공식 source의 actor scope가 선택 서비스와 명확히 다른 경우\n")
        f.write("  - `unclear`: 현재 source set만으로는 service-level 적용을 확정하기 어려운 경우\n")
        f.write("- `enforced_flag`는 explicit enforcement case 또는 formal investigation source가 service-matched로 연결되는 경우에만 `yes`를 허용하고, 그 외에는 보수적으로 `no` 또는 `unclear`로 남겼다.\n")
        f.write("- 현재 패널은 직접 규제 burden gap 비교를 위한 중간 증거표이며, service-matched enforcement evidence가 매우 제한적이라는 사실 자체를 드러내는 역할을 한다.\n\n")
        f.write(f"- total rows: `{total}`\n")
        f.write(
            f"- law_exists_flag distribution: `yes={law_counts.get('yes', 0)}, no={law_counts.get('no', 0)}, unclear={law_counts.get('unclear', 0)}`\n"
        )
        f.write(
            f"- enforced_flag distribution: `yes={enforced_counts.get('yes', 0)}, no={enforced_counts.get('no', 0)}, unclear={enforced_counts.get('unclear', 0)}`\n"
        )
        f.write(
            f"- evidence_strength distribution: `strong={strength_counts.get('strong', 0)}, medium={strength_counts.get('medium', 0)}, weak={strength_counts.get('weak', 0)}, none={strength_counts.get('none', 0)}`\n"
        )


def main() -> None:
    rows = build_rows()
    write_outputs(rows)


if __name__ == "__main__":
    main()
