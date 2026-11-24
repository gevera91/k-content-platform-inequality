#!/usr/bin/env python3
from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

CORE_SAMPLE_PATH = ROOT / "data/registry/claim_strengthening/reverse_discrimination_core_sample_v1.csv"
SERVICE_DICT_PATH = ROOT / "data/registry/entity_dictionary_service.csv"
OBLIGATION_DICT_PATH = ROOT / "data/registry/claim_strengthening/regulatory_obligation_dictionary_v2.csv"
REG_SOURCE_INDEX_PATH = ROOT / "data/interim/regulatory_source_index.csv"
OUTPUT_PATH = ROOT / "data/interim/claim_strengthening/kr_regulatory_obligations_core.csv"
LOG_PATH = ROOT / "logs/claim_strengthening/kr_regulatory_obligations_log.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def source_map() -> dict[str, dict[str, str]]:
    rows = read_csv(REG_SOURCE_INDEX_PATH)
    return {row["source_id"]: row for row in rows if row["country_std"] == "kr"}


def classify(service_type: str, obligation_id: str) -> tuple[str, str | None, str, str]:
    """
    Returns: applies_flag, burden_score, source_id, coding_note
    """
    if service_type == "music_streaming":
        if obligation_id == "DOC01":
            return (
                "yes",
                "1",
                "kr_reg_telecommunications_business_act",
                "온라인 정보통신서비스 제공자에게 notice_reporting 성격의 기본 행정 제출의무가 존재하는 것으로 보수적으로 코딩",
            )
        if obligation_id == "DOC02":
            return (
                "yes",
                "2",
                "kr_reg_telecommunications_business_act",
                "provider_duties 항목을 근거로 수시 자료제출·조사 협조의무를 보수적으로 적용",
            )
        if obligation_id == "CON01":
            return (
                "yes",
                "1",
                "kr_reg_telecommunications_business_act",
                "provider_duties를 이용자 보호·고지·민원 대응 성격의 기본 의무로 보수적으로 코딩",
            )
        if obligation_id == "DATA02":
            return (
                "yes",
                "2",
                "kr_reg_telecommunications_business_act",
                "information_protection 항목을 근거로 기록 보존·보호 및 운영상 지속 대응 의무를 적용",
            )
        if obligation_id == "CON02":
            return (
                "scope_no",
                "0",
                "kr_reg_kcc_app_market_notice",
                "현재 직접 근거 문서는 app market business operator 대상 notice라서 멜론·플로에는 직접 적용하지 않음",
            )
        return (
            "unclear",
            "",
            "kr_reg_telecommunications_business_act",
            "현재 한국 core source set만으로는 해당 의무의 서비스별 직접 적용을 확정하기 어려움",
        )

    if service_type == "music_ip_portfolio":
        if obligation_id in {"CON01", "CON02", "REV01", "REV02", "NET01", "NET02"}:
            return (
                "scope_no",
                "0",
                "kr_reg_telecommunications_business_act",
                "현재 비교단위는 소비자-facing 앱이 아니라 music IP portfolio unit이라 서비스 운영의무를 직접 코딩하지 않음",
            )
        return (
            "unclear",
            "",
            "kr_reg_telecommunications_business_act",
            "현재 한국 core source set은 IP portfolio unit에 대한 직접 규제 burden을 article level로 확인하기에 부족함",
        )

    if service_type == "telecom_network":
        if obligation_id == "DOC01":
            return (
                "yes",
                "2",
                "kr_reg_telecommunications_business_act",
                "notice_reporting 항목을 근거로 통신망 사업 단위의 정기 보고·신고 의무를 보수적으로 적용",
            )
        if obligation_id == "DOC02":
            return (
                "yes",
                "2",
                "kr_reg_telecommunications_business_act",
                "provider_duties 항목을 근거로 수시 자료제출·조사 협조의무를 적용",
            )
        if obligation_id == "NET02":
            return (
                "yes",
                "2",
                "kr_reg_telecommunications_business_act",
                "network_utilization 및 provider_duties 항목을 근거로 망 관련 절차·협상·자료대응 부담을 적용",
            )
        if obligation_id == "CON01":
            return (
                "yes",
                "1",
                "kr_reg_telecommunications_business_act",
                "provider_duties를 이용자 보호·고지 및 민원 대응 성격의 기본 의무로 코딩",
            )
        if obligation_id == "DATA02":
            return (
                "yes",
                "2",
                "kr_reg_telecommunications_business_act",
                "information_protection 항목을 근거로 로그·기록·보호 관련 지속의무를 적용",
            )
        if obligation_id in {"REV01", "REV02", "CON02"}:
            source_id = (
                "kr_reg_kcc_app_market_notice" if obligation_id == "CON02" else "kr_reg_telecommunications_business_act"
            )
            note = (
                "현재 직접 근거 문서는 app market business operator 대상 notice라서 통신망 사업 단위에는 직접 적용하지 않음"
                if obligation_id == "CON02"
                else "현재 비교단위는 telecom network service라서 콘텐츠 등급·검열 의무를 직접 코딩하지 않음"
            )
            return ("scope_no", "0", source_id, note)
        return (
            "unclear",
            "",
            "kr_reg_telecommunications_business_act",
            "현재 한국 core source set만으로는 해당 의무의 통신망 사업 단위 적용을 article level로 확정하기 어려움",
        )

    return ("unclear", "", "kr_reg_telecommunications_business_act", "service_type rule not found")


def build_rows() -> list[dict[str, str]]:
    core_rows = read_csv(CORE_SAMPLE_PATH)
    service_rows = read_csv(SERVICE_DICT_PATH)
    obligation_rows = read_csv(OBLIGATION_DICT_PATH)
    reg_sources = source_map()

    service_info = {row["service_std"]: row for row in service_rows}
    kr_core = [
        row
        for row in core_rows
        if row["include_flag"] == "yes"
        and row["country_std"] == "kr"
        and row["analysis_role"].startswith("korean")
    ]

    output_rows: list[dict[str, str]] = []
    for core in kr_core:
        service = service_info[core["service_std"]]
        for obligation in obligation_rows:
            applies_flag, burden_score, source_id, coding_note = classify(service["service_type"], obligation["obligation_id"])
            source = reg_sources[source_id]

            if source_id == "kr_reg_kcc_app_market_notice":
                effective_date = source["application_date"] or source["execution_date"] or source["document_date"]
                enforcement_evidence = (
                    "Official KCC notice states that standards for app market business operators and forced payment method prohibition took effect on 2022-03-15; current service is coded against that actor scope."
                )
            else:
                effective_date = source["application_date"] or source["execution_date"] or "pre-2026-03-28"
                enforcement_evidence = (
                    "Official law.go act page saved locally; regulatory source index tags this source with "
                    + source["obligation_items"]
                    + ". Current coding uses that tagged obligation channel conservatively because article-level parsing is still pending."
                )

            output_rows.append(
                {
                    "firm_std": core["firm_std"],
                    "service_std": core["service_std"],
                    "obligation_id": obligation["obligation_id"],
                    "applies_flag": applies_flag,
                    "effective_date": effective_date,
                    "enforcement_evidence": enforcement_evidence,
                    "source_url": source["source_url"],
                    "raw_file": source["raw_storage_path"],
                    "peer_group_id": core["peer_group_id"],
                    "service_type": service["service_type"],
                    "obligation_name_ko": obligation["obligation_name_ko"],
                    "burden_score": burden_score,
                    "source_id": source_id,
                    "coding_note": coding_note,
                }
            )

    output_rows.sort(
        key=lambda r: (r["peer_group_id"], r["service_std"], r["obligation_id"])
    )
    return output_rows


def write_outputs(rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "firm_std",
        "service_std",
        "obligation_id",
        "applies_flag",
        "effective_date",
        "enforcement_evidence",
        "source_url",
        "raw_file",
        "peer_group_id",
        "service_type",
        "obligation_name_ko",
        "burden_score",
        "source_id",
        "coding_note",
    ]
    with OUTPUT_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    yes_count = sum(row["applies_flag"] == "yes" for row in rows)
    scope_no_count = sum(row["applies_flag"] == "scope_no" for row in rows)
    unclear_count = sum(row["applies_flag"] == "unclear" for row in rows)
    services = sorted({row["service_std"] for row in rows})

    with LOG_PATH.open("w") as f:
        f.write("# Strength Prompt 12. 한국 규제 의무 추출\n\n")
        f.write("- `kr_regulatory_obligations_core.csv`는 한국 core sample 서비스에 대해 obligation dictionary v2 기준으로 실제 적용 의무를 service-obligation 단위로 정리한 표다.\n")
        f.write("- 이번 단계는 과잉 확정을 피하기 위해 `applies_flag`를 `yes`, `scope_no`, `unclear`로 구분했다.\n")
        f.write("  - `yes`: 현재 한국 규제 source set에서 직접 burden channel이 확인된 경우\n")
        f.write("  - `scope_no`: 현재 확보한 직접 문서의 규율 대상이 해당 서비스 단위와 명확히 다른 경우\n")
        f.write("  - `unclear`: article-level parsing 또는 추가 source 없이는 보수적으로 확정하기 어려운 경우\n")
        f.write("- 현재 한국 직접 source는 사실상 두 개뿐이다. law.go act raw와 KCC app market notice raw를 사용했고, law.go act는 article-level extraction이 아직 미완료이므로 보수적 코딩을 적용했다.\n")
        f.write("- 따라서 이 표는 최종 burden table의 초벌 추출본이며, 다음 단계에서 미국·일본·영국 등과 같은 dictionary 기준으로 맞춘 뒤 direct gap table로 집계해야 한다.\n\n")
        f.write(f"- total rows: `{total}`\n")
        f.write(f"- applies yes: `{yes_count}`\n")
        f.write(f"- scope_no: `{scope_no_count}`\n")
        f.write(f"- unclear: `{unclear_count}`\n")
        f.write(f"- korean core services covered: `{', '.join(services)}`\n")


def main() -> None:
    rows = build_rows()
    write_outputs(rows)


if __name__ == "__main__":
    main()
