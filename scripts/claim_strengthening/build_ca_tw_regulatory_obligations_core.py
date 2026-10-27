#!/usr/bin/env python3
from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

MATRIX_PATH = ROOT / "data/registry/firm_country_service_matrix.csv"
SERVICE_DICT_PATH = ROOT / "data/registry/entity_dictionary_service.csv"
OBLIGATION_DICT_PATH = ROOT / "data/registry/claim_strengthening/regulatory_obligation_dictionary_v2.csv"
REG_SOURCE_INDEX_PATH = ROOT / "data/interim/regulatory_source_index.csv"
OUTPUT_PATH = ROOT / "data/interim/claim_strengthening/ca_tw_regulatory_obligations_core.csv"
LOG_PATH = ROOT / "logs/claim_strengthening/ca_tw_regulatory_obligations_log.md"


SELECTED_ROWS = [
    {"country_std": "ca", "peer_group_id": "webtoon_internal_geo_split", "firm_std": "webtoon_ent", "service_std": "webtoon"},
    {"country_std": "tw", "peer_group_id": "webtoon_internal_geo_split", "firm_std": "webtoon_ent", "service_std": "webtoon"},
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
    if service_type != "webtoon_platform":
        return ("unclear", "", "", "service_type rule not found")

    if country_std == "ca":
        if obligation_id in {"REG01", "DOC01", "DOC02", "PARA01", "CON01", "CON02"}:
            source_id = "ca_reg_crtc_streaming_portal" if obligation_id in {"PARA01", "CON01", "CON02"} else "ca_reg_crtc_registration"
            return (
                "scope_no",
                "0",
                source_id,
                "현재 캐나다 직접 source set은 online streaming services registration·contribution portal을 다루므로 webtoon platform을 직접 규율하는 서비스 단위 의무로 코딩하지 않음",
            )
        return (
            "unclear",
            "",
            "ca_reg_crtc_streaming_portal",
            "현재 캐나다 직접 source set만으로는 webtoon platform의 조세·데이터·심의 관련 burden을 service level로 직접 확정하기 어려움",
        )

    if country_std == "tw":
        if obligation_id == "CON02":
            return (
                "scope_no",
                "0",
                "tw_reg_moda_meta_ad_disclosure",
                "현재 대만 직접 근거 문서는 Meta/Facebook 광고공시 집행사례라서 webtoon platform 일반 의무로 직접 적용하지 않음",
            )
        if obligation_id in {"REG01", "DOC01", "DOC02", "CON01"}:
            return (
                "scope_no",
                "0",
                "tw_reg_moda_online_retail_platform_directions",
                "현재 대만 직접 source set은 online retail platform directions라서 webtoon platform을 직접 규율하는 actor scope로 확정하지 않음",
            )
        return (
            "unclear",
            "",
            "tw_reg_moda_online_retail_platform_directions",
            "현재 대만 직접 source set은 enforcement case 1건과 revalidation needed retail-platform directions뿐이라 webtoon platform burden을 service level로 직접 확정하기 어려움",
        )

    return ("unclear", "", "", "country rule not found")


def effective_date_for(country_std: str, source: dict[str, str]) -> str:
    if country_std == "tw":
        return source["application_date"] or source["execution_date"] or source["document_date"] or "pre-2026-03-28"
    return source["application_date"] or source["execution_date"] or source["document_date"] or "pre-2026-03-28"


def enforcement_evidence_for(country_std: str, source: dict[str, str], source_id: str) -> str:
    if source_id == "ca_reg_crtc_registration":
        return (
            "Official CRTC registration page specifies that certain online streaming services must complete a registration form; current coding keeps actor scope conservative because the selected peer service is a webtoon platform."
        )
    if source_id == "ca_reg_crtc_streaming_portal":
        return (
            "Official CRTC streaming portal lists registration, conditions of service, base contributions, and fee-related obligations for online streaming services; current coding does not automatically map those duties to a webtoon platform."
        )
    if source_id == "tw_reg_moda_meta_ad_disclosure":
        return (
            "Official MODA press release is a specific enforcement case against Meta for incomplete advertisement disclosure on Facebook and is used only as actor-scope evidence, not as a general webtoon-platform burden rule."
        )
    return (
        "Official MODA source is an online retail platform directions file with downstream revalidation need noted in the regulatory source index; current coding therefore remains conservative for webtoon-platform burden extraction."
    )


def build_rows() -> list[dict[str, str]]:
    matrix_rows = read_csv(MATRIX_PATH)
    service_rows = read_csv(SERVICE_DICT_PATH)
    obligation_rows = read_csv(OBLIGATION_DICT_PATH)

    matrix_keys = {
        (row["country_std"], row["firm_std"], row["service_std"]): row for row in matrix_rows
    }
    service_info = {row["service_std"]: row for row in service_rows}
    ca_sources = source_map("ca")
    tw_sources = source_map("tw")

    output_rows: list[dict[str, str]] = []
    for selected in SELECTED_ROWS:
        key = (selected["country_std"], selected["firm_std"], selected["service_std"])
        if key not in matrix_keys:
            raise ValueError(f"Selected row not found in matrix: {key}")

        service = service_info[selected["service_std"]]
        country_sources = ca_sources if selected["country_std"] == "ca" else tw_sources

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

    output_rows.sort(key=lambda r: (r["country_std"], r["service_std"], r["obligation_id"]))
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

    with LOG_PATH.open("w") as f:
        f.write("# Strength Prompt 15. 캐나다/대만 규제 의무 추출\n\n")
        f.write("- `ca_tw_regulatory_obligations_core.csv`는 캐나다와 대만의 핵심 peer 셀에 대해 obligation dictionary v2 기준의 service-obligation 표를 정리한 것이다.\n")
        f.write("- 이번 단계는 과잉 확정을 피하기 위해 `applies_flag`를 `yes`, `scope_no`, `unclear`로 구분했다.\n")
        f.write("  - `yes`: 현재 캐나다·대만 직접 source set에서 service-level burden channel이 직접 확인된 경우\n")
        f.write("  - `scope_no`: 현재 확보한 직접 문서의 규율 대상이 해당 서비스 단위와 명확히 다른 경우\n")
        f.write("  - `unclear`: 현재 직접 source set만으로는 service-level burden을 직접 확정하기 어려운 경우\n")
        f.write("- 현재 캐나다 직접 source set은 CRTC online streaming registration/portal이고, 대만 직접 source set은 MODA Meta ad disclosure case와 online retail platform directions다.\n")
        f.write("- 따라서 이 표는 캐나다·대만 peer가 burden을 지지 않는다는 결론이 아니라, 현재 직접 source set이 webtoon platform보다 streaming service, retail platform, 또는 특정 enforcement case actor에 더 가깝기 때문에 service-level burden 직접 코딩이 제한적이라는 보수적 추출 결과다.\n\n")
        f.write(f"- total rows: `{total}`\n")
        f.write(f"- applies yes: `{yes_count}`\n")
        f.write(f"- scope_no: `{scope_no_count}`\n")
        f.write(f"- unclear: `{unclear_count}`\n")
        f.write(f"- rows by country: `ca={country_counts.get('ca', 0)}, tw={country_counts.get('tw', 0)}`\n")
        f.write("- covered service-country cells: `ca:webtoon, tw:webtoon`\n")


def main() -> None:
    rows = build_rows()
    write_outputs(rows)


if __name__ == "__main__":
    main()
