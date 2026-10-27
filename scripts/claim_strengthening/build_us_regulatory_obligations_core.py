#!/usr/bin/env python3
from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

CORE_SAMPLE_PATH = ROOT / "data/registry/claim_strengthening/reverse_discrimination_core_sample_v1.csv"
SERVICE_DICT_PATH = ROOT / "data/registry/entity_dictionary_service.csv"
FIRM_DICT_PATH = ROOT / "data/registry/entity_dictionary_firm.csv"
OBLIGATION_DICT_PATH = ROOT / "data/registry/claim_strengthening/regulatory_obligation_dictionary_v2.csv"
REG_SOURCE_INDEX_PATH = ROOT / "data/interim/regulatory_source_index.csv"
OUTPUT_PATH = ROOT / "data/interim/claim_strengthening/us_regulatory_obligations_core.csv"
LOG_PATH = ROOT / "logs/claim_strengthening/us_regulatory_obligations_log.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def source_map() -> dict[str, dict[str, str]]:
    rows = read_csv(REG_SOURCE_INDEX_PATH)
    return {row["source_id"]: row for row in rows if row["country_std"] == "us"}


def classify(service_type: str, obligation_id: str) -> tuple[str, str, str, str]:
    """
    Returns: applies_flag, burden_score, source_id, coding_note
    """
    if service_type == "ott_video":
        if obligation_id in {"NET01", "NET02"}:
            return (
                "scope_no",
                "0",
                "us_reg_fcc_open_internet_order",
                "현재 미국 직접 근거 문서는 broadband internet access service 대상 open internet order라서 OTT edge provider인 Netflix에는 직접 적용하지 않음",
            )
        return (
            "unclear",
            "",
            "us_reg_doj_technology_digital_platforms",
            "현재 미국 직접 source set의 DOJ page는 조직·집행 소개 페이지라서 OTT 서비스 단위의 상시 의무를 직접 확정하기에는 부족함",
        )

    if service_type == "music_ip_portfolio":
        if obligation_id in {"CON01", "CON02", "REV01", "REV02"}:
            return (
                "scope_no",
                "0",
                "us_reg_doj_technology_digital_platforms",
                "현재 비교단위는 consumer-facing platform이 아니라 music IP portfolio라서 소비자·결제·사전심의 의무를 직접 코딩하지 않음",
            )
        if obligation_id in {"NET01", "NET02"}:
            return (
                "scope_no",
                "0",
                "us_reg_fcc_open_internet_order",
                "현재 미국 직접 근거 문서는 broadband internet access service 대상 order라서 music IP portfolio unit에는 직접 적용하지 않음",
            )
        return (
            "unclear",
            "",
            "us_reg_doj_technology_digital_platforms",
            "현재 미국 직접 source set만으로는 music IP portfolio unit의 신고·조세·자료제출 등 직접 burden을 service level로 확정하기 어려움",
        )

    return (
        "unclear",
        "",
        "us_reg_doj_technology_digital_platforms",
        "service_type rule not found",
    )


def build_rows() -> list[dict[str, str]]:
    core_rows = read_csv(CORE_SAMPLE_PATH)
    service_rows = read_csv(SERVICE_DICT_PATH)
    firm_rows = read_csv(FIRM_DICT_PATH)
    obligation_rows = read_csv(OBLIGATION_DICT_PATH)
    reg_sources = source_map()

    service_info = {row["service_std"]: row for row in service_rows}
    firm_info = {row["firm_std"]: row for row in firm_rows}

    seen: set[tuple[str, str, str]] = set()
    us_global_core: list[dict[str, str]] = []
    for row in core_rows:
        if row["include_flag"] != "yes":
            continue
        if not row["analysis_role"].startswith("global"):
            continue
        firm = firm_info.get(row["firm_std"], {})
        if firm.get("home_country") != "us":
            continue
        key = (row["peer_group_id"], row["firm_std"], row["service_std"])
        if key in seen:
            continue
        seen.add(key)
        us_global_core.append(row)

    output_rows: list[dict[str, str]] = []
    for core in us_global_core:
        service = service_info[core["service_std"]]
        for obligation in obligation_rows:
            applies_flag, burden_score, source_id, coding_note = classify(
                service["service_type"], obligation["obligation_id"]
            )
            source = reg_sources[source_id]

            if source_id == "us_reg_fcc_open_internet_order":
                effective_date = source["execution_date"] or source["document_date"]
                enforcement_evidence = (
                    "Official FCC order PDF; regulatory source index tags this source with "
                    + source["obligation_items"]
                    + ". Current coding uses actor scope conservatively because the order targets broadband internet access service and the source index notes an effective date of 2024-07-22 with later stay on 2024-08-05."
                )
            else:
                effective_date = source["document_date"] or "2023-07-27"
                enforcement_evidence = (
                    "Official DOJ Technology and Digital Platforms Section page says the section handles civil antitrust enforcement, competition advocacy, and competition policy for technology and digital platforms. Current coding does not treat this organizational enforcement page as a standing service-level obligation without a more specific rule."
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

    output_rows.sort(key=lambda r: (r["peer_group_id"], r["service_std"], r["obligation_id"]))
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
    firms = sorted({row["firm_std"] for row in rows})

    with LOG_PATH.open("w") as f:
        f.write("# Strength Prompt 13. 미국 비교군 규제 의무 추출\n\n")
        f.write("- `us_regulatory_obligations_core.csv`는 core sample v1에 포함된 미국 기반 글로벌 peer 서비스에 대해 obligation dictionary v2 기준으로 적용 의무를 정리한 표다.\n")
        f.write("- 이번 단계는 과잉 확정을 피하기 위해 `applies_flag`를 `yes`, `scope_no`, `unclear`로 구분했다.\n")
        f.write("  - `yes`: 현재 미국 직접 source set에서 service-level burden channel이 직접 확인된 경우\n")
        f.write("  - `scope_no`: 현재 확보한 직접 문서의 규율 대상이 해당 서비스 단위와 명확히 다른 경우\n")
        f.write("  - `unclear`: 현재 미국 직접 source set만으로는 service-level burden을 직접 확정하기 어려운 경우\n")
        f.write("- 현재 미국 직접 source는 DOJ Technology and Digital Platforms Section page와 FCC Open Internet Order 두 개뿐이다.\n")
        f.write("- 따라서 이 표는 미국 peer가 부담을 전혀 지지 않는다는 증거가 아니라, 현재 직접 source set에서 동일 dictionary 기준으로 바로 코딩 가능한 burden이 제한적이라는 보수적 추출 결과다.\n\n")
        f.write(f"- total rows: `{total}`\n")
        f.write(f"- applies yes: `{yes_count}`\n")
        f.write(f"- scope_no: `{scope_no_count}`\n")
        f.write(f"- unclear: `{unclear_count}`\n")
        f.write(f"- U.S.-based global peer firms covered: `{', '.join(firms)}`\n")
        f.write(f"- U.S.-based global peer services covered: `{', '.join(services)}`\n")


def main() -> None:
    rows = build_rows()
    write_outputs(rows)


if __name__ == "__main__":
    main()
