#!/usr/bin/env python3

from __future__ import annotations

import csv
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]

ACCESS_DATE = "2026-03-29"
PROMPT_NAME = "Post Step 16"

COUNTRY_MARKET_USAGE_REGISTRY_PATH = BASE_DIR / "data" / "interim" / "country_market_usage_registry.csv"
SOURCE_MANIFEST_PATH = BASE_DIR / "data" / "registry" / "source_manifest.csv"
PROJECT_MANIFEST_PATH = BASE_DIR / "data" / "registry" / "project_manifest.csv"
WORKFLOW_LOG_PATH = BASE_DIR / "logs" / "workflow_log.md"
LOG_PATH = BASE_DIR / "logs" / "uk_tw_infra_country_proxy_thickening_log.md"

UK_EXTRACT_PATH = (
    BASE_DIR
    / "data"
    / "raw"
    / "uk"
    / "market_usage"
    / "uk_market_usage_ofcom_online_nation_2024_extracted_20260329.csv"
)
TW_EXTRACT_PATH = (
    BASE_DIR
    / "data"
    / "raw"
    / "tw"
    / "market_usage"
    / "tw_market_usage_moda_digital_access_survey_2024_extracted_20260329.csv"
)


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def upsert_csv(path: Path, rows: list[dict[str, str]], key_fields: list[str], fieldnames: list[str]) -> None:
    existing: dict[tuple[str, ...], dict[str, str]] = {}
    if path.exists():
        for row in read_csv(path):
            existing[tuple(row.get(field, "") for field in key_fields)] = row
    for row in rows:
        normalized = {field: str(row.get(field, "")) for field in fieldnames}
        existing[tuple(normalized[field] for field in key_fields)] = normalized
    write_csv(
        path,
        sorted(existing.values(), key=lambda item: tuple(item[field] for field in key_fields)),
        fieldnames,
    )


def build_extract_rows() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    fieldnames = [
        "country_std",
        "reference_year_month",
        "reference_year_quarter",
        "metric_name",
        "metric_variant",
        "metric_value",
        "metric_unit",
        "source_title",
        "source_url",
        "access_date",
        "notes",
    ]
    uk_rows = [
        {
            "country_std": "uk",
            "reference_year_month": "2024-12",
            "reference_year_quarter": "2024Q4",
            "metric_name": "foreign_dependency_ratio",
            "metric_variant": "country_video_service_reach_proxy",
            "metric_value": "0.940000",
            "metric_unit": "share",
            "source_title": "Ofcom Online Nation 2024 report",
            "source_url": "https://www.ofcom.org.uk/siteassets/resources/documents/research-and-data/online-research/online-nation/2024/online-nation-2024-report.pdf?v=386238",
            "access_date": ACCESS_DATE,
            "notes": "Official Ofcom PDF lines 623-630 and 1722-1724 state that YouTube reached 94% of UK online adults in May 2024; retained as a UK foreign-video dependence proxy for digital infrastructure cells.",
        }
    ]
    tw_rows = [
        {
            "country_std": "tw",
            "reference_year_month": "2024-12",
            "reference_year_quarter": "2024Q4",
            "metric_name": "foreign_dependency_ratio",
            "metric_variant": "country_online_video_entertainment_proxy",
            "metric_value": "0.911000",
            "metric_unit": "share",
            "source_title": "113-year Digital Access Survey main report",
            "source_url": "https://www-api.moda.gov.tw/File/Get/moda/zh-tw/EJ97STRSQKlDPXJ",
            "access_date": ACCESS_DATE,
            "notes": "Official MODA PDF lines 46-49 report that 91.1% of Taiwan internet users aged 12+ used online video entertainment in the past three months; retained as a 2024Q4 Taiwan foreign-video dependence proxy.",
        }
    ]
    return uk_rows, tw_rows


def update_country_market_usage_registry() -> None:
    fieldnames = [
        "country_std",
        "source_title",
        "source_url",
        "raw_storage_path",
        "file_format",
        "access_date",
        "source_frequency",
        "observation_unit",
        "candidate_variables_covered",
        "coverage_type",
        "candidate_variables_pending",
        "collection_status",
        "notes",
    ]
    rows = [
        {
            "country_std": "uk",
            "source_title": "Ofcom Online Nation 2024 extracted browser observation",
            "source_url": "https://www.ofcom.org.uk/siteassets/resources/documents/research-and-data/online-research/online-nation/2024/online-nation-2024-report.pdf?v=386238",
            "raw_storage_path": "data/raw/uk/market_usage/uk_market_usage_ofcom_online_nation_2024_extracted_20260329.csv",
            "file_format": "csv",
            "access_date": ACCESS_DATE,
            "source_frequency": "annual report extract",
            "observation_unit": "UK online adults age 18+ in May 2024",
            "candidate_variables_covered": "platform_usage_share",
            "coverage_type": "direct_browser_extracted",
            "candidate_variables_pending": "local_platform_share;paid_subscription_ratio;multihoming_rate;service_rank",
            "collection_status": "collected",
            "notes": "Browser-extracted official Ofcom Online Nation 2024 figure. YouTube reached 94% of UK online adults in May 2024 and is retained as the UK foreign-video dependence proxy for infrastructure analysis.",
        },
        {
            "country_std": "tw",
            "source_title": "MODA 113-year Digital Access Survey extracted browser observation",
            "source_url": "https://www-api.moda.gov.tw/File/Get/moda/zh-tw/EJ97STRSQKlDPXJ",
            "raw_storage_path": "data/raw/tw/market_usage/tw_market_usage_moda_digital_access_survey_2024_extracted_20260329.csv",
            "file_format": "csv",
            "access_date": ACCESS_DATE,
            "source_frequency": "annual report extract",
            "observation_unit": "Taiwan internet users age 12+ in 2024 survey",
            "candidate_variables_covered": "platform_usage_share",
            "coverage_type": "direct_browser_extracted",
            "candidate_variables_pending": "local_platform_share;paid_subscription_ratio;multihoming_rate;service_rank",
            "collection_status": "collected",
            "notes": "Browser-extracted official MODA PDF figure. Online video entertainment reached 91.1% among Taiwan internet users aged 12+ and is retained as a 2024Q4 foreign-video dependence proxy.",
        },
    ]
    upsert_csv(COUNTRY_MARKET_USAGE_REGISTRY_PATH, rows, ["country_std", "raw_storage_path"], fieldnames)


def update_source_manifest() -> None:
    fieldnames = [
        "source_file",
        "source_url",
        "access_date",
        "country_std",
        "firm_std",
        "service_std",
        "sector_std",
        "file_format",
        "collected_by_prompt",
        "status",
    ]
    rows = [
        {
            "source_file": "data/raw/uk/market_usage/uk_market_usage_ofcom_online_nation_2024_extracted_20260329.csv",
            "source_url": "https://www.ofcom.org.uk/siteassets/resources/documents/research-and-data/online-research/online-nation/2024/online-nation-2024-report.pdf?v=386238",
            "access_date": ACCESS_DATE,
            "country_std": "uk",
            "firm_std": "",
            "service_std": "",
            "sector_std": "digital_infra",
            "file_format": "csv",
            "collected_by_prompt": PROMPT_NAME,
            "status": "collected_browser_extracted",
        },
        {
            "source_file": "data/raw/tw/market_usage/tw_market_usage_moda_digital_access_survey_2024_extracted_20260329.csv",
            "source_url": "https://www-api.moda.gov.tw/File/Get/moda/zh-tw/EJ97STRSQKlDPXJ",
            "access_date": ACCESS_DATE,
            "country_std": "tw",
            "firm_std": "",
            "service_std": "",
            "sector_std": "digital_infra",
            "file_format": "csv",
            "collected_by_prompt": PROMPT_NAME,
            "status": "collected_browser_extracted",
        },
    ]
    upsert_csv(SOURCE_MANIFEST_PATH, rows, ["source_file"], fieldnames)


def update_project_manifest() -> None:
    fieldnames = [
        "artifact_type",
        "path",
        "owner_step",
        "source_type",
        "source_url",
        "access_date",
        "status",
        "notes",
    ]
    rows = [
        {
            "artifact_type": "script",
            "path": "scripts/thicken_uk_tw_infra_country_proxies.py",
            "owner_step": PROMPT_NAME,
            "source_type": "local_code",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Writes browser-extracted UK and Taiwan infrastructure proxy raw files and updates the country market usage registry.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/raw/uk/market_usage/uk_market_usage_ofcom_online_nation_2024_extracted_20260329.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "browser_extracted_public_data",
            "source_url": "https://www.ofcom.org.uk/siteassets/resources/documents/research-and-data/online-research/online-nation/2024/online-nation-2024-report.pdf?v=386238",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Local extract of the retained 94% UK YouTube reach observation from the official Ofcom report.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/raw/tw/market_usage/tw_market_usage_moda_digital_access_survey_2024_extracted_20260329.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "browser_extracted_public_data",
            "source_url": "https://www-api.moda.gov.tw/File/Get/moda/zh-tw/EJ97STRSQKlDPXJ",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Local extract of the retained 91.1% Taiwan online-video-entertainment observation from the official MODA PDF.",
        },
        {
            "artifact_type": "file",
            "path": "logs/uk_tw_infra_country_proxy_thickening_log.md",
            "owner_step": PROMPT_NAME,
            "source_type": "execution_log",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Log of the UK/TW digital infrastructure proxy thickening step.",
        },
    ]
    upsert_csv(PROJECT_MANIFEST_PATH, rows, ["path"], fieldnames)


def append_workflow_log() -> None:
    block = (
        f"\n### {PROMPT_NAME}. UK/TW 디지털 인프라 국가 proxy 보강\n\n"
        "- `uk 2024Q4` Ofcom Online Nation 공식 관측치(YouTube reach 94%)를 browser-extracted raw로 추가함\n"
        "- `tw 2024Q4` MODA 113년 디지털 근용 보고서의 온라인 영상 이용률(91.1%)을 browser-extracted raw로 추가함\n"
        "- 두 관측치를 `country_market_usage_registry`와 `source_manifest`에 등록해 이후 인프라 파이프라인에서 재사용 가능하게 정리함\n"
    )
    text = WORKFLOW_LOG_PATH.read_text(encoding="utf-8") if WORKFLOW_LOG_PATH.exists() else "# Workflow Log\n"
    if block not in text:
        WORKFLOW_LOG_PATH.write_text(text.rstrip() + "\n" + block, encoding="utf-8")


def write_log() -> None:
    lines = [
        f"# {PROMPT_NAME} Log",
        "",
        f"- access_date: `{ACCESS_DATE}`",
        "- created_raw_files: `2`",
        "- countries_thickened: `uk`, `tw`",
        "- retained_metrics: `foreign_dependency_ratio`",
        "",
        "## UK retained observation",
        "",
        "- Source: Ofcom Online Nation 2024 report",
        "- Metric: `YouTube reach among UK online adults = 94%`",
        "- Retained quarter anchor: `2024Q4`",
        "",
        "## Taiwan retained observation",
        "",
        "- Source: MODA 113-year Digital Access Survey main report",
        "- Metric: `online video entertainment among Taiwan internet users age 12+ = 91.1%`",
        "- Retained quarter anchor: `2024Q4`",
    ]
    LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    uk_rows, tw_rows = build_extract_rows()
    extract_fieldnames = [
        "country_std",
        "reference_year_month",
        "reference_year_quarter",
        "metric_name",
        "metric_variant",
        "metric_value",
        "metric_unit",
        "source_title",
        "source_url",
        "access_date",
        "notes",
    ]
    write_csv(UK_EXTRACT_PATH, uk_rows, extract_fieldnames)
    write_csv(TW_EXTRACT_PATH, tw_rows, extract_fieldnames)
    update_country_market_usage_registry()
    update_source_manifest()
    update_project_manifest()
    write_log()
    append_workflow_log()


if __name__ == "__main__":
    main()
