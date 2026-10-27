#!/usr/bin/env python3
from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

MATRIX_PATH = ROOT / "data/registry/firm_country_service_matrix.csv"
SERVICE_DICT_PATH = ROOT / "data/registry/entity_dictionary_service.csv"
OBLIGATION_DICT_PATH = ROOT / "data/registry/claim_strengthening/regulatory_obligation_dictionary_v2.csv"
REG_SOURCE_INDEX_PATH = ROOT / "data/interim/regulatory_source_index.csv"
OUTPUT_PATH = ROOT / "data/interim/claim_strengthening/jp_uk_regulatory_obligations_core.csv"
LOG_PATH = ROOT / "logs/claim_strengthening/jp_uk_regulatory_obligations_log.md"


SELECTED_ROWS = [
    {"country_std": "jp", "peer_group_id": "mus_label_ip_export", "firm_std": "jyp_ent", "service_std": "jyp_music_ip"},
    {"country_std": "jp", "peer_group_id": "mus_label_ip_export", "firm_std": "yg_ent", "service_std": "yg_music_ip"},
    {"country_std": "jp", "peer_group_id": "mus_label_ip_export", "firm_std": "warner_music", "service_std": "wmg_music_ip"},
    {"country_std": "jp", "peer_group_id": "webtoon_serial_platform", "firm_std": "kakao_piccoma", "service_std": "piccoma"},
    {"country_std": "jp", "peer_group_id": "webtoon_serial_platform", "firm_std": "naver", "service_std": "naver_webtoon"},
    {"country_std": "jp", "peer_group_id": "webtoon_serial_platform", "firm_std": "kidari_studio", "service_std": "lezhin_comics"},
    {"country_std": "jp", "peer_group_id": "webtoon_serial_platform", "firm_std": "webtoon_ent", "service_std": "webtoon"},
    {"country_std": "uk", "peer_group_id": "mus_label_ip_export", "firm_std": "warner_music", "service_std": "wmg_music_ip"},
    {"country_std": "uk", "peer_group_id": "webtoon_internal_geo_split", "firm_std": "webtoon_ent", "service_std": "webtoon"},
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def source_map(country_std: str) -> dict[str, dict[str, str]]:
    rows = read_csv(REG_SOURCE_INDEX_PATH)
    return {row["source_id"]: row for row in rows if row["country_std"] == country_std}


def classify(country_std: str, service_type: str, obligation_id: str) -> tuple[str, str, str, str]:
    """
    Returns: applies_flag, burden_score, source_id, coding_note
    """
    if country_std == "jp":
        if service_type == "music_ip_portfolio":
            if obligation_id in {"CON01", "CON02", "REV01", "REV02", "NET01", "NET02"}:
                source_id = "jp_reg_meti_digital_platform_consultation_desk" if obligation_id == "CON02" else "jp_reg_jftc_msca_consultation_desk"
                return (
                    "scope_no",
                    "0",
                    source_id,
                    "현재 일본 직접 source set은 app store·mobile software competition 관련 문서라서 music IP portfolio unit에 직접 적용되는 서비스 운영 의무로 코딩하지 않음",
                )
            return (
                "unclear",
                "",
                "jp_reg_jftc_msca_consultation_desk",
                "현재 일본 직접 source set만으로는 music IP portfolio unit의 신고·자료제출·조세·데이터 의무를 service level로 직접 확정하기 어려움",
            )

        if service_type == "webtoon_platform":
            if obligation_id in {"CON02", "REV01", "REV02", "NET01", "NET02"}:
                source_id = "jp_reg_meti_digital_platform_consultation_desk" if obligation_id == "CON02" else "jp_reg_jftc_msca_consultation_desk"
                note = (
                    "현재 일본 직접 근거 문서는 app store operator transparency 및 mobile software competition consultation channel이라서 웹툰 app publisher 자체의 결제·중개 규율로 직접 적용하지 않음"
                    if obligation_id == "CON02"
                    else "현재 일본 직접 source set은 콘텐츠 등급·망 협상 의무를 웹툰 플랫폼 단위에 직접 부과하는 문서가 아님"
                )
                return ("scope_no", "0", source_id, note)
            return (
                "unclear",
                "",
                "jp_reg_jftc_msca_consultation_desk",
                "현재 일본 직접 source set만으로는 웹툰 플랫폼 단위의 등록·자료제출·조세·데이터 의무를 service level로 직접 확정하기 어려움",
            )

    if country_std == "uk":
        if obligation_id in {"REG01", "DOC01", "DOC02", "PARA01", "CON02"}:
            return (
                "scope_no",
                "0",
                "uk_reg_digital_markets_regime_guidance",
                "현재 영국 직접 source set의 digital markets regime는 SMS designation을 받은 very large digital firms에 대한 규율이므로, 현 단계에서 해당 서비스에 바로 적용되는 의무로 코딩하지 않음",
            )
        return (
            "unclear",
            "",
            "uk_reg_dmcc_act_2024",
            "현재 영국 직접 source set만으로는 해당 서비스 단위의 조세·데이터·소비자·심의 관련 burden을 direct service level로 확정하기 어려움",
        )

    return ("unclear", "", "", "country rule not found")


def effective_date_for(country_std: str, source: dict[str, str]) -> str:
    if country_std == "jp":
        return source["application_date"] or source["execution_date"] or "pre-2026-03-28"
    return source["application_date"] or source["execution_date"] or source["document_date"] or "pre-2026-03-28"


def enforcement_evidence_for(country_std: str, source: dict[str, str], source_id: str) -> str:
    if country_std == "jp" and source_id == "jp_reg_meti_digital_platform_consultation_desk":
        return (
            "Official METI-linked slide deck says the TFDPA was enforced in February 2021 and designated app store platforms were set on 2021-04-01; current coding uses that actor scope conservatively."
        )
    if country_std == "jp":
        return (
            "Official JFTC consultation desk page confirms a Mobile Software Competition Act consultation channel, but the current raw page is a landing page without article-level obligations by service type."
        )
    if source_id == "uk_reg_digital_markets_regime_guidance":
        return (
            "Official CMA guidance says the UK digital markets competition regime came into force from January 2025 and applies through SMS investigations and conduct requirements for designated firms."
        )
    return (
        "Official DMCC Act 2024 source provides the statutory framework, but the current source set does not by itself identify service-level obligations for the selected peer service."
    )


def build_rows() -> list[dict[str, str]]:
    matrix_rows = read_csv(MATRIX_PATH)
    service_rows = read_csv(SERVICE_DICT_PATH)
    obligation_rows = read_csv(OBLIGATION_DICT_PATH)

    matrix_keys = {
        (row["country_std"], row["firm_std"], row["service_std"]): row for row in matrix_rows
    }
    service_info = {row["service_std"]: row for row in service_rows}
    jp_sources = source_map("jp")
    uk_sources = source_map("uk")

    output_rows: list[dict[str, str]] = []
    for selected in SELECTED_ROWS:
        key = (selected["country_std"], selected["firm_std"], selected["service_std"])
        if key not in matrix_keys:
            raise ValueError(f"Selected row not found in matrix: {key}")

        service = service_info[selected["service_std"]]
        country_sources = jp_sources if selected["country_std"] == "jp" else uk_sources

        for obligation in obligation_rows:
            applies_flag, burden_score, source_id, coding_note = classify(
                selected["country_std"], service["service_type"], obligation["obligation_id"]
            )
            source = country_sources[source_id]
            output_rows.append(
                {
                    "country_std": selected["country_std"],
                    "firm_std": selected["firm_std"],
                    "service_std": selected["service_std"],
                    "obligation_id": obligation["obligation_id"],
                    "applies_flag": applies_flag,
                    "effective_date": effective_date_for(selected["country_std"], source),
                    "enforcement_evidence": enforcement_evidence_for(selected["country_std"], source, source_id),
                    "source_url": source["source_url"],
                    "raw_file": source["raw_storage_path"],
                    "peer_group_id": selected["peer_group_id"],
                    "service_type": service["service_type"],
                    "obligation_name_ko": obligation["obligation_name_ko"],
                    "burden_score": burden_score,
                    "source_id": source_id,
                    "coding_note": coding_note,
                }
            )

    output_rows.sort(key=lambda r: (r["country_std"], r["peer_group_id"], r["service_std"], r["obligation_id"]))
    return output_rows


def write_outputs(rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "country_std",
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
    country_counts: dict[str, int] = {}
    for row in rows:
        country_counts[row["country_std"]] = country_counts.get(row["country_std"], 0) + 1
    services = sorted({f"{row['country_std']}:{row['service_std']}" for row in rows})

    with LOG_PATH.open("w") as f:
        f.write("# Strength Prompt 14. 일본/영국 규제 의무 추출\n\n")
        f.write("- `jp_uk_regulatory_obligations_core.csv`는 일본과 영국의 핵심 peer 셀에 대해 obligation dictionary v2 기준의 service-obligation 표를 정리한 것이다.\n")
        f.write("- 이번 단계는 과잉 확정을 피하기 위해 `applies_flag`를 `yes`, `scope_no`, `unclear`로 구분했다.\n")
        f.write("  - `yes`: 현재 일본·영국 직접 source set에서 service-level burden channel이 직접 확인된 경우\n")
        f.write("  - `scope_no`: 현재 확보한 직접 문서의 규율 대상이 해당 서비스 단위와 명확히 다른 경우\n")
        f.write("  - `unclear`: 현재 직접 source set만으로는 service-level burden을 직접 확정하기 어려운 경우\n")
        f.write("- 일본 직접 source set은 mobile software competition consultation desk와 app store transparency consultation source이고, 영국 직접 source set은 DMCC Act 및 CMA digital markets regime guidance다.\n")
        f.write("- 따라서 이 표는 일본·영국 peer가 burden을 지지 않는다는 결론이 아니라, 현재 직접 source set이 주로 app store operator 또는 SMS designated firm을 겨냥하고 있어 selected peer service에 바로 매핑되는 의무가 제한적이라는 보수적 추출 결과다.\n\n")
        f.write(f"- total rows: `{total}`\n")
        f.write(f"- applies yes: `{yes_count}`\n")
        f.write(f"- scope_no: `{scope_no_count}`\n")
        f.write(f"- unclear: `{unclear_count}`\n")
        f.write(f"- rows by country: `jp={country_counts.get('jp', 0)}, uk={country_counts.get('uk', 0)}`\n")
        f.write(f"- covered service-country cells: `{', '.join(services)}`\n")


def main() -> None:
    rows = build_rows()
    write_outputs(rows)


if __name__ == "__main__":
    main()
