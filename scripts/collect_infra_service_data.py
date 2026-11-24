from __future__ import annotations

import csv
import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pypdf import PdfReader


PROJECT_DIR = Path(__file__).resolve().parents[1]
ACCESS_DATE = date.today().isoformat()
ACCESS_DATE_TAG = ACCESS_DATE.replace("-", "")
PROMPT_LABEL = "Exec Prompt 17"

RAW_DIR = PROJECT_DIR / "data" / "raw" / "infra"
INTERIM_DIR = PROJECT_DIR / "data" / "interim"
LOG_DIR = PROJECT_DIR / "logs"
REGISTRY_DIR = PROJECT_DIR / "data" / "registry"
UK_MARKET_USAGE_2024_EXTRACT_PATH = (
    PROJECT_DIR / "data" / "raw" / "uk" / "market_usage" / "uk_market_usage_ofcom_online_nation_2024_extracted_20260329.csv"
)
TW_MARKET_USAGE_2024_EXTRACT_PATH = (
    PROJECT_DIR / "data" / "raw" / "tw" / "market_usage" / "tw_market_usage_moda_digital_access_survey_2024_extracted_20260329.csv"
)

SOURCE_MANIFEST_PATH = REGISTRY_DIR / "source_manifest.csv"
PROJECT_MANIFEST_PATH = REGISTRY_DIR / "project_manifest.csv"
WORKFLOW_LOG_PATH = LOG_DIR / "workflow_log.md"
COUNTRY_MARKET_USAGE_REGISTRY_PATH = INTERIM_DIR / "country_market_usage_registry.csv"
FILING_METADATA_PANEL_PATH = INTERIM_DIR / "filing_metadata_panel.csv"

SOURCE_REGISTRY_PATH = INTERIM_DIR / "infra_source_registry.csv"
RAW_PANEL_PATH = INTERIM_DIR / "infra_service_raw_panel.csv"
LOG_PATH = LOG_DIR / "infra_service_collection_log.md"


@dataclass
class SecContext:
    context_id: str
    start_date: str
    end_date: str
    segment_text: str


@dataclass
class SecFact:
    name: str
    context_ref: str
    value: str


def run_curl(url: str, output_path: Path, *, insecure: bool = True) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["curl", "-sL", "-A", "Mozilla/5.0"]
    if insecure:
        cmd.append("-k")
    cmd.extend([url, "-o", str(output_path)])
    return subprocess.run(cmd, check=False).returncode


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def upsert_csv(path: Path, rows: list[dict[str, str]], key_fields: list[str], fieldnames: list[str]) -> None:
    existing: dict[tuple[str, ...], dict[str, str]] = {}
    if path.exists():
        with path.open(newline="") as f:
            for row in csv.DictReader(f):
                existing[tuple(row[field] for field in key_fields)] = row
    for row in rows:
        normalized = {field: str(row.get(field, "")) for field in fieldnames}
        existing[tuple(normalized[field] for field in key_fields)] = normalized
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in sorted(existing.values(), key=lambda item: tuple(item[field] for field in key_fields)):
            writer.writerow(row)


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def to_float(value: str) -> float:
    cleaned = value.replace(",", "").replace("%", "").replace("(", "-").replace(")", "").strip()
    if not cleaned:
        return 0.0
    return float(cleaned)


def extract_metric_from_csv(raw_file: Path, metric_name: str) -> float:
    with raw_file.open(newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if row.get("metric_name") == metric_name and row.get("metric_value"):
            return float(row["metric_value"])
    raise RuntimeError(f"{metric_name} not found in {raw_file}")


def format_decimal(value: float) -> str:
    return f"{value:.6f}"


def quarter_from_end_date(date_str: str) -> str:
    year = int(date_str[:4])
    month = int(date_str[5:7])
    quarter = ((month - 1) // 3) + 1
    return f"{year}Q{quarter}"


def year_month_from_end_date(date_str: str) -> str:
    return date_str[:7]


def sec_quarter_start(end_date: str) -> str:
    year = int(end_date[:4])
    month = int(end_date[5:7])
    quarter = ((month - 1) // 3) + 1
    start_month = {1: 1, 2: 4, 3: 7, 4: 10}[quarter]
    return f"{year}-{start_month:02d}-01"


def annual_start(end_date: str) -> str:
    return f"{end_date[:4]}-01-01"


def parse_opendart_rows(html_text: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    pattern = re.compile(
        r'<span class="concept-label" id="[^"]+">([^<]+)</span></td><td class="monetary-item">'
        r'<span class="fact-value" id="[^"]+">([^<]*)</span>',
        re.S,
    )
    for label, value in pattern.findall(html_text):
        label = re.sub(r"\s+", " ", label).strip()
        value = value.strip()
        if label and value:
            rows[label] = value
    return rows


def extract_pdf_text(pdf_path: Path) -> str:
    return "\n".join((page.extract_text() or "") for page in PdfReader(str(pdf_path)).pages)


def parse_sec_contexts(text: str) -> dict[str, SecContext]:
    contexts: dict[str, SecContext] = {}
    context_pattern = re.compile(r'<xbrli:context id="([^"]+)">(.*?)</xbrli:context>', re.S)
    for context_id, block in context_pattern.findall(text):
        start_match = re.search(r"<xbrli:startDate>([^<]+)</xbrli:startDate>", block)
        end_match = re.search(r"<xbrli:endDate>([^<]+)</xbrli:endDate>", block)
        if not start_match or not end_match:
            continue
        segment_match = re.search(r"<xbrli:segment>(.*?)</xbrli:segment>", block, re.S)
        contexts[context_id] = SecContext(
            context_id=context_id,
            start_date=start_match.group(1),
            end_date=end_match.group(1),
            segment_text=segment_match.group(1) if segment_match else "",
        )
    return contexts


def parse_sec_facts(text: str) -> list[SecFact]:
    pattern = re.compile(
        r'<ix:nonFraction[^>]*contextRef="([^"]+)"[^>]*name="([^"]+)"[^>]*>([^<]+)</ix:nonFraction>',
        re.S,
    )
    return [SecFact(name=name, context_ref=context_ref, value=value.strip()) for context_ref, name, value in pattern.findall(text)]


def extract_sec_value(
    contexts: dict[str, SecContext],
    facts: list[SecFact],
    *,
    concept_priority: list[str],
    start_date: str,
    end_date: str,
    require_no_segment: bool = True,
) -> str | None:
    for concept in concept_priority:
        for fact in facts:
            if fact.name != concept:
                continue
            ctx = contexts.get(fact.context_ref)
            if not ctx:
                continue
            if ctx.start_date != start_date or ctx.end_date != end_date:
                continue
            if require_no_segment and ctx.segment_text.strip():
                continue
            if fact.value:
                return fact.value
    return None


def load_country_market_rows() -> dict[str, dict[str, str]]:
    rows = read_csv(COUNTRY_MARKET_USAGE_REGISTRY_PATH)
    best: dict[str, tuple[int, dict[str, str]]] = {}
    for row in rows:
        country = row["country_std"]
        status = row.get("collection_status", "")
        file_format = row.get("file_format", "")
        score = 0
        if status.startswith("collected"):
            score += 10
        if "blocked" in status:
            score -= 10
        if file_format == "csv":
            score += 5
        elif file_format == "pdf":
            score += 3
        elif file_format == "html":
            score += 2
        if "proxy_activity" in row.get("coverage_type", ""):
            score += 1
        if country not in best or score > best[country][0]:
            best[country] = (score, row)
    return {country: payload[1] for country, payload in best.items()}


def extract_kr_video_proxy(raw_file: Path) -> float:
    text = raw_file.read_text(errors="ignore")
    match = re.search(r"OTT\) 이용률은 ([0-9.]+)%", text)
    if not match:
        raise RuntimeError("KR OTT usage ratio not found")
    return float(match.group(1)) / 100.0


def extract_tw_video_proxy(raw_file: Path) -> float:
    if raw_file.suffix.lower() == ".csv":
        return extract_metric_from_csv(raw_file, "foreign_dependency_ratio")
    text = raw_file.read_text(errors="ignore")
    match = re.search(r"online video entertainment \(([0-9.]+)%\)", text, re.I)
    if not match:
        raise RuntimeError("TW online video entertainment ratio not found")
    return float(match.group(1)) / 100.0


def extract_uk_video_proxy(raw_file: Path) -> float:
    if raw_file.suffix.lower() == ".csv":
        return extract_metric_from_csv(raw_file, "foreign_dependency_ratio")
    text = raw_file.read_text(errors="ignore")
    match = re.search(r"YouTube reached 94% of UK online adults", text, re.I)
    if match:
        return 0.94
    raise RuntimeError("UK YouTube reach proxy not found")


def extract_us_video_proxy(raw_file: Path) -> float:
    with raw_file.open(newline="") as f:
        rows = list(csv.DictReader(f))
    for row in reversed(rows):
        if row["dataset"] == "Nov 2023" and row["variable"] == "videoUser":
            return float(row["usProp"])
    raise RuntimeError("US Nov 2023 videoUser ratio not found")


def extract_jp_video_proxy(raw_file: Path) -> float:
    text = extract_pdf_text(raw_file)
    match = re.search(r"Internet usage rate \(individuals\) in 2020 was ([0-9.]+)\s+percent", text, re.I)
    if not match:
        raise RuntimeError("JP internet usage proxy not found")
    return float(match.group(1)) / 100.0


def extract_ca_video_proxies(raw_file: Path) -> tuple[float, float]:
    text = extract_pdf_text(raw_file)
    match = re.search(
        r"([0-9]+)% children aged 2-17 consumed content on YouTube and ([0-9]+)% consumed content on an SVOD",
        text,
        re.I,
    )
    if not match:
        raise RuntimeError("CA youth YouTube/SVOD proxy not found")
    youtube_share = float(match.group(1)) / 100.0
    netflix_share = float(match.group(2)) / 100.0
    return youtube_share, netflix_share


def collect_new_raw_sources() -> list[dict[str, str]]:
    raw_rows: list[dict[str, str]] = []

    new_sources = [
        (
            "https://developers.cloudflare.com/radar/get-started/first-request/",
            RAW_DIR / "cloudflare" / f"us_cloudflare_radar_docs_{ACCESS_DATE_TAG}.html",
            "us",
            "cloudflare",
            "cloudflare_cdn",
            "html",
            "collected",
        ),
        (
            "https://developers.google.com/youtube/v3/getting-started",
            RAW_DIR / "youtube" / f"us_youtube_data_api_getting_started_{ACCESS_DATE_TAG}.html",
            "us",
            "alphabet",
            "youtube",
            "html",
            "pending_api_key",
        ),
        (
            "https://top10.netflix.com/",
            RAW_DIR / "netflix" / f"us_netflix_top10_home_{ACCESS_DATE_TAG}.html",
            "us",
            "netflix",
            "netflix",
            "html",
            "collected_limited_attention_proxy",
        ),
    ]

    for url, output_path, country_std, firm_std, service_std, file_format, status in new_sources:
        run_curl(url, output_path)
        raw_rows.append(
            {
                "source_file": str(output_path.relative_to(PROJECT_DIR)),
                "source_url": url,
                "access_date": ACCESS_DATE,
                "country_std": country_std,
                "firm_std": firm_std,
                "service_std": service_std,
                "sector_std": "digital_infra",
                "file_format": file_format,
                "collected_by_prompt": PROMPT_LABEL,
                "status": status,
            }
        )

    cloudflare_probe_path = RAW_DIR / "cloudflare" / f"us_cloudflare_radar_api_probe_{ACCESS_DATE_TAG}.json"
    cloudflare_probe_path.parent.mkdir(parents=True, exist_ok=True)
    cloudflare_probe = subprocess.check_output(
        [
            "curl",
            "-sL",
            "-A",
            "Mozilla/5.0",
            "https://api.cloudflare.com/client/v4/radar/http/top/locations/KR",
        ],
        text=True,
    )
    cloudflare_probe_path.write_text(cloudflare_probe)
    raw_rows.append(
        {
            "source_file": str(cloudflare_probe_path.relative_to(PROJECT_DIR)),
            "source_url": "https://api.cloudflare.com/client/v4/radar/http/top/locations/KR",
            "access_date": ACCESS_DATE,
            "country_std": "us",
            "firm_std": "cloudflare",
            "service_std": "cloudflare_cdn",
            "sector_std": "digital_infra",
            "file_format": "json",
            "collected_by_prompt": PROMPT_LABEL,
            "status": "blocked_access",
        }
    )

    opendart_roles = [
        (
            "kt",
            "kt_network",
            "https://engopendart.fss.or.kr/xbrl/viewer/view.do?xbrlExtSeq=20260323000402&roleId=D320000&lang=en",
            RAW_DIR / "opendart" / f"kr_kt_income_statement_{ACCESS_DATE_TAG}.html",
        ),
        (
            "kt",
            "kt_network",
            "https://engopendart.fss.or.kr/xbrl/viewer/view.do?xbrlExtSeq=20260323000402&roleId=D520000&lang=en",
            RAW_DIR / "opendart" / f"kr_kt_cash_flow_{ACCESS_DATE_TAG}.html",
        ),
        (
            "sk_telecom",
            "skt_network",
            "https://engopendart.fss.or.kr/xbrl/viewer/view.do?xbrlExtSeq=20260318000088&roleId=D320000&lang=en",
            RAW_DIR / "opendart" / f"kr_sk_telecom_income_statement_{ACCESS_DATE_TAG}.html",
        ),
        (
            "sk_telecom",
            "skt_network",
            "https://engopendart.fss.or.kr/xbrl/viewer/view.do?xbrlExtSeq=20260318000088&roleId=D520000&lang=en",
            RAW_DIR / "opendart" / f"kr_sk_telecom_cash_flow_{ACCESS_DATE_TAG}.html",
        ),
        (
            "lg_uplus",
            "lguplus_network",
            "https://engopendart.fss.or.kr/xbrl/viewer/view.do?xbrlExtSeq=20260313000018&roleId=D320000&lang=en",
            RAW_DIR / "opendart" / f"kr_lg_uplus_income_statement_{ACCESS_DATE_TAG}.html",
        ),
        (
            "lg_uplus",
            "lguplus_network",
            "https://engopendart.fss.or.kr/xbrl/viewer/view.do?xbrlExtSeq=20260313000018&roleId=D520000&lang=en",
            RAW_DIR / "opendart" / f"kr_lg_uplus_cash_flow_{ACCESS_DATE_TAG}.html",
        ),
    ]
    for firm_std, service_std, url, output_path in opendart_roles:
        run_curl(url, output_path)
        raw_rows.append(
            {
                "source_file": str(output_path.relative_to(PROJECT_DIR)),
                "source_url": url,
                "access_date": ACCESS_DATE,
                "country_std": "kr",
                "firm_std": firm_std,
                "service_std": service_std,
                "sector_std": "digital_infra",
                "file_format": "html",
                "collected_by_prompt": PROMPT_LABEL,
                "status": "collected",
            }
        )
    return raw_rows


def build_country_proxy_rows(country_market_rows: dict[str, dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, float]]:
    proxies: dict[str, float] = {}
    proxies["kr"] = extract_kr_video_proxy(PROJECT_DIR / country_market_rows["kr"]["raw_storage_path"])
    proxies["tw_2024"] = extract_metric_from_csv(TW_MARKET_USAGE_2024_EXTRACT_PATH, "foreign_dependency_ratio")
    proxies["tw_2025"] = extract_tw_video_proxy(PROJECT_DIR / country_market_rows["tw"]["raw_storage_path"])
    proxies["us"] = extract_us_video_proxy(PROJECT_DIR / country_market_rows["us"]["raw_storage_path"])
    proxies["jp"] = extract_jp_video_proxy(PROJECT_DIR / country_market_rows["jp"]["raw_storage_path"])
    proxies["uk_2024"] = extract_uk_video_proxy(UK_MARKET_USAGE_2024_EXTRACT_PATH)
    ca_youtube, ca_netflix = extract_ca_video_proxies(PROJECT_DIR / country_market_rows["ca"]["raw_storage_path"])

    rows: list[dict[str, str]] = []
    country_configs = [
        (
            "kr",
            "2025-12",
            "2025Q4",
            "country_ott_usage_proxy",
            "KOCCA OTT usage ratio used as upper-bound foreign video dependence proxy",
            proxies["kr"],
            f"infra_kr_market_usage_proxy",
            country_market_rows["kr"]["raw_storage_path"],
        ),
        (
            "us",
            "2023-11",
            "2023Q4",
            "country_video_user_proxy",
            "NTIA Nov 2023 videoUser share used as country-level foreign video dependence proxy",
            proxies["us"],
            "infra_us_market_usage_proxy",
            country_market_rows["us"]["raw_storage_path"],
        ),
        (
            "jp",
            "2020-12",
            "2020Q4",
            "country_internet_usage_proxy",
            "MIC 2020 internet usage rate used as broad digital video dependence proxy",
            proxies["jp"],
            "infra_jp_market_usage_proxy",
            country_market_rows["jp"]["raw_storage_path"],
        ),
        (
            "uk",
            "2024-12",
            "2024Q4",
            "country_video_service_reach_proxy",
            "Ofcom Online Nation 2024 records 94% YouTube reach among UK online adults; retained as a UK foreign-video dependence proxy.",
            proxies["uk_2024"],
            "infra_uk_market_usage_proxy_2024",
            str(UK_MARKET_USAGE_2024_EXTRACT_PATH.relative_to(PROJECT_DIR)),
        ),
        (
            "tw",
            "2024-12",
            "2024Q4",
            "country_online_video_entertainment_proxy",
            "MODA 2024 Digital Access Survey reports 91.1% online video entertainment among Taiwan internet users age 12+.",
            proxies["tw_2024"],
            "infra_tw_market_usage_proxy_2024",
            str(TW_MARKET_USAGE_2024_EXTRACT_PATH.relative_to(PROJECT_DIR)),
        ),
        (
            "tw",
            "2025-12",
            "2025Q4",
            "country_video_entertainment_proxy",
            "MODA online video entertainment share used as foreign video dependence proxy",
            proxies["tw_2025"],
            "infra_tw_market_usage_proxy_2025",
            country_market_rows["tw"]["raw_storage_path"],
        ),
    ]
    for country_std, year_month, year_quarter, variant, note, proxy_value, source_id, raw_source_file in country_configs:
        for firm_std, service_std in [("netflix", "netflix"), ("alphabet", "youtube")]:
            rows.append(
                {
                    "panel_unit_type": "service_country_quarter",
                    "country_std": country_std,
                    "year_month": year_month,
                    "year_quarter": year_quarter,
                    "firm_std": firm_std,
                    "service_std": service_std,
                    "metric_name": "foreign_dependency_ratio",
                    "metric_variant": variant,
                    "metric_value": format_decimal(proxy_value),
                    "metric_unit": "share",
                    "source_id": source_id,
                    "raw_source_file": raw_source_file,
                    "collection_status": "collected_proxy",
                    "notes": note,
                }
            )

    ca_source = country_market_rows["ca"]
    rows.extend(
        [
            {
                "panel_unit_type": "service_country_quarter",
                "country_std": "ca",
                "year_month": "2024-12",
                "year_quarter": "2024Q4",
                "firm_std": "netflix",
                "service_std": "netflix",
                "metric_name": "foreign_dependency_ratio",
                "metric_variant": "youth_svod_penetration_proxy",
                "metric_value": format_decimal(ca_netflix),
                "metric_unit": "share",
                "source_id": "infra_ca_market_usage_proxy",
                "raw_source_file": ca_source["raw_storage_path"],
                "collection_status": "collected_proxy",
                "notes": "CRTC youth 2-17 SVOD penetration used as Netflix exposure proxy in Canada.",
            },
            {
                "panel_unit_type": "service_country_quarter",
                "country_std": "ca",
                "year_month": "2024-12",
                "year_quarter": "2024Q4",
                "firm_std": "alphabet",
                "service_std": "youtube",
                "metric_name": "foreign_dependency_ratio",
                "metric_variant": "youth_youtube_penetration_proxy",
                "metric_value": format_decimal(ca_youtube),
                "metric_unit": "share",
                "source_id": "infra_ca_market_usage_proxy",
                "raw_source_file": ca_source["raw_storage_path"],
                "collection_status": "collected_proxy",
                "notes": "CRTC youth 2-17 YouTube penetration used as YouTube exposure proxy in Canada.",
            },
        ]
    )
    return rows, proxies


def build_korean_telco_rows(kr_proxy: float) -> list[dict[str, str]]:
    firm_specs = [
        (
            "kt",
            "kt_network",
            RAW_DIR / "opendart" / f"kr_kt_income_statement_{ACCESS_DATE_TAG}.html",
            RAW_DIR / "opendart" / f"kr_kt_cash_flow_{ACCESS_DATE_TAG}.html",
            "Acquisition of intangible asset and investment property",
            "combined_capex_proxy_including_intangible_asset_and_investment_property",
        ),
        (
            "sk_telecom",
            "skt_network",
            RAW_DIR / "opendart" / f"kr_sk_telecom_income_statement_{ACCESS_DATE_TAG}.html",
            RAW_DIR / "opendart" / f"kr_sk_telecom_cash_flow_{ACCESS_DATE_TAG}.html",
            "Purchase of property, plant and equipment",
            "purchase_of_property_plant_and_equipment",
        ),
        (
            "lg_uplus",
            "lguplus_network",
            RAW_DIR / "opendart" / f"kr_lg_uplus_income_statement_{ACCESS_DATE_TAG}.html",
            RAW_DIR / "opendart" / f"kr_lg_uplus_cash_flow_{ACCESS_DATE_TAG}.html",
            "Payments for acquisition of property, plant and equipment",
            "payments_for_acquisition_of_property_plant_and_equipment",
        ),
    ]

    rows: list[dict[str, str]] = []
    for firm_std, service_std, income_path, cash_path, capex_label, capex_variant in firm_specs:
        income_map = parse_opendart_rows(income_path.read_text(errors="ignore"))
        cash_map = parse_opendart_rows(cash_path.read_text(errors="ignore"))
        revenue = to_float(income_map["Operating revenue"] if "Operating revenue" in income_map else income_map["Revenue"])
        operating_expense = to_float(income_map["Operating expense"])
        capex_value = abs(to_float(cash_map[capex_label]))
        year_month = "2025-12"
        year_quarter = "2025Q4"
        network_cost_ratio = operating_expense / revenue
        capex_ratio = capex_value / revenue
        outflow_ratio = operating_expense / capex_value
        traffic_pressure = kr_proxy * network_cost_ratio
        source_id = f"infra_{firm_std}_opendart_roles"

        rows.extend(
            [
                {
                    "panel_unit_type": "service_country_quarter",
                    "country_std": "kr",
                    "year_month": year_month,
                    "year_quarter": year_quarter,
                    "firm_std": firm_std,
                    "service_std": service_std,
                    "metric_name": "network_cost_ratio",
                    "metric_variant": "operating_expense_ratio_proxy",
                    "metric_value": format_decimal(network_cost_ratio),
                    "metric_unit": "share",
                    "source_id": source_id,
                    "raw_source_file": f"{income_path.relative_to(PROJECT_DIR)}",
                    "collection_status": "collected_proxy",
                    "notes": "Operating expense divided by revenue from consolidated OpenDART XBRL statement as conservative network cost proxy.",
                },
                {
                    "panel_unit_type": "service_country_quarter",
                    "country_std": "kr",
                    "year_month": year_month,
                    "year_quarter": year_quarter,
                    "firm_std": firm_std,
                    "service_std": service_std,
                    "metric_name": "domestic_infra_capex_ratio",
                    "metric_variant": capex_variant,
                    "metric_value": format_decimal(capex_ratio),
                    "metric_unit": "share",
                    "source_id": source_id,
                    "raw_source_file": f"{cash_path.relative_to(PROJECT_DIR)}",
                    "collection_status": "collected_proxy",
                    "notes": "OpenDART consolidated cash-flow capital spending proxy divided by revenue.",
                },
                {
                    "panel_unit_type": "service_country_quarter",
                    "country_std": "kr",
                    "year_month": year_month,
                    "year_quarter": year_quarter,
                    "firm_std": firm_std,
                    "service_std": service_std,
                    "metric_name": "outflow_to_capex_ratio",
                    "metric_variant": "operating_expense_to_capex_proxy",
                    "metric_value": format_decimal(outflow_ratio),
                    "metric_unit": "ratio",
                    "source_id": source_id,
                    "raw_source_file": f"{income_path.relative_to(PROJECT_DIR)} | {cash_path.relative_to(PROJECT_DIR)}",
                    "collection_status": "collected_proxy",
                    "notes": "Operating expense divided by capital spending proxy used as broad investment-pressure proxy.",
                },
                {
                    "panel_unit_type": "service_country_quarter",
                    "country_std": "kr",
                    "year_month": year_month,
                    "year_quarter": year_quarter,
                    "firm_std": firm_std,
                    "service_std": service_std,
                    "metric_name": "foreign_dependency_ratio",
                    "metric_variant": "korea_ott_usage_proxy",
                    "metric_value": format_decimal(kr_proxy),
                    "metric_unit": "share",
                    "source_id": "infra_kr_market_usage_proxy",
                    "raw_source_file": "data/raw/kr/market_usage/kr_market_usage_kocca_content_usage_20260328.html",
                    "collection_status": "collected_proxy",
                    "notes": "KOCCA OTT usage ratio used as foreign traffic dependence proxy for Korean telecom network cells.",
                },
                {
                    "panel_unit_type": "service_country_quarter",
                    "country_std": "kr",
                    "year_month": year_month,
                    "year_quarter": year_quarter,
                    "firm_std": firm_std,
                    "service_std": service_std,
                    "metric_name": "traffic_cost_pressure",
                    "metric_variant": "foreign_video_dependence_x_operating_expense_ratio_proxy",
                    "metric_value": format_decimal(traffic_pressure),
                    "metric_unit": "share",
                    "source_id": source_id,
                    "raw_source_file": f"data/raw/kr/market_usage/kr_market_usage_kocca_content_usage_20260328.html | {income_path.relative_to(PROJECT_DIR)}",
                    "collection_status": "collected_proxy",
                    "notes": "Country OTT usage proxy multiplied by operating-expense ratio proxy.",
                },
            ]
        )
    return rows


def build_global_filing_rows() -> list[dict[str, str]]:
    filing_rows = read_csv(FILING_METADATA_PANEL_PATH)
    target_services = {
        "netflix": {"firm_std": "netflix", "service_std": "netflix", "variant": "firm_exact"},
        "cloudflare": {"firm_std": "cloudflare", "service_std": "cloudflare_cdn", "variant": "firm_exact"},
        "akamai": {"firm_std": "akamai", "service_std": "akamai_cdn", "variant": "firm_exact"},
        "amazon": {"firm_std": "amazon", "service_std": "aws", "variant": "amazon_company_level_proxy"},
        "alphabet": {"firm_std": "alphabet", "service_std": "youtube", "variant": "alphabet_company_level_proxy"},
    }
    rows: list[dict[str, str]] = []

    sec_files = [
        row
        for row in filing_rows
        if row["firm_std"] in target_services and row["filing_group"] in {"annual", "interim"}
    ]
    for row in sec_files:
        file_path = PROJECT_DIR / row["source_file"]
        text = file_path.read_text(errors="ignore")
        contexts = parse_sec_contexts(text)
        facts = parse_sec_facts(text)

        end_date = row["fiscal_period_end"]
        if row["filing_group"] == "annual":
            start_date = annual_start(end_date)
        else:
            start_date = sec_quarter_start(end_date)

        revenue = extract_sec_value(
            contexts,
            facts,
            concept_priority=[
                "us-gaap:Revenues",
                "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                "us-gaap:SalesRevenueNet",
            ],
            start_date=start_date,
            end_date=end_date,
            require_no_segment=True,
        )
        cost_of_revenue = extract_sec_value(
            contexts,
            facts,
            concept_priority=["us-gaap:CostOfRevenue", "us-gaap:CostOfSales", "us-gaap:CostOfGoodsSold"],
            start_date=start_date,
            end_date=end_date,
            require_no_segment=True,
        )
        capex = extract_sec_value(
            contexts,
            facts,
            concept_priority=[
                "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
                "us-gaap:PropertyAndEquipmentAdditions",
                "us-gaap:CapitalExpendituresIncurredButNotYetPaid",
            ],
            start_date=start_date,
            end_date=end_date,
            require_no_segment=True,
        )
        if not revenue or not cost_of_revenue or not capex:
            continue

        revenue_value = to_float(revenue)
        cost_value = abs(to_float(cost_of_revenue))
        capex_value = abs(to_float(capex))
        spec = target_services[row["firm_std"]]
        year_quarter = quarter_from_end_date(end_date)
        year_month = year_month_from_end_date(end_date)
        network_cost_ratio = cost_value / revenue_value
        capex_ratio = capex_value / revenue_value
        outflow_ratio = cost_value / capex_value
        collection_status = "collected" if spec["variant"] == "firm_exact" else "collected_company_proxy"

        for metric_name, metric_variant, metric_value, unit in [
            ("network_cost_ratio", f"{spec['variant']}_cost_of_revenue_ratio", network_cost_ratio, "share"),
            ("domestic_infra_capex_ratio", f"{spec['variant']}_capex_ratio", capex_ratio, "share"),
            ("outflow_to_capex_ratio", f"{spec['variant']}_cost_to_capex_ratio", outflow_ratio, "ratio"),
        ]:
            rows.append(
                {
                    "panel_unit_type": "service_country_quarter",
                    "country_std": "us",
                    "year_month": year_month,
                    "year_quarter": year_quarter,
                    "firm_std": spec["firm_std"],
                    "service_std": spec["service_std"],
                    "metric_name": metric_name,
                    "metric_variant": metric_variant,
                    "metric_value": format_decimal(metric_value),
                    "metric_unit": unit,
                    "source_id": f"infra_{spec['firm_std']}_sec_filings",
                    "raw_source_file": row["source_file"],
                    "collection_status": collection_status,
                    "notes": "SEC filing-based ratio. Service-level exact for Netflix/Cloudflare/Akamai; company-level proxy for YouTube/AWS.",
                }
            )
    return rows


def build_source_registry(country_market_rows: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    rows = [
        {
            "source_id": "infra_cloudflare_radar_docs",
            "source_name": "Cloudflare Radar getting-started documentation",
            "source_url": "https://developers.cloudflare.com/radar/get-started/first-request/",
            "country_std": "us",
            "firm_std": "cloudflare",
            "service_std": "cloudflare_cdn",
            "metric_targets": "traffic_cost_pressure|foreign_dependency_ratio",
            "collection_status": "blocked_access",
            "raw_storage_path": f"data/raw/infra/cloudflare/us_cloudflare_radar_docs_{ACCESS_DATE_TAG}.html",
            "access_date": ACCESS_DATE,
            "notes": "Documentation collected, but public API probe requires auth headers and the public Radar UI is challenge-protected in this environment.",
        },
        {
            "source_id": "infra_cloudflare_radar_probe",
            "source_name": "Cloudflare Radar unauthenticated API probe",
            "source_url": "https://api.cloudflare.com/client/v4/radar/http/top/locations/KR",
            "country_std": "us",
            "firm_std": "cloudflare",
            "service_std": "cloudflare_cdn",
            "metric_targets": "traffic_cost_pressure|foreign_dependency_ratio",
            "collection_status": "blocked_access",
            "raw_storage_path": f"data/raw/infra/cloudflare/us_cloudflare_radar_api_probe_{ACCESS_DATE_TAG}.json",
            "access_date": ACCESS_DATE,
            "notes": "Probe returns missing-auth error, confirming Cloudflare Radar cannot be directly harvested without credentials.",
        },
        {
            "source_id": "infra_youtube_api_docs",
            "source_name": "YouTube Data API getting-started page",
            "source_url": "https://developers.google.com/youtube/v3/getting-started",
            "country_std": "us",
            "firm_std": "alphabet",
            "service_std": "youtube",
            "metric_targets": "foreign_dependency_ratio",
            "collection_status": "pending_api_key",
            "raw_storage_path": f"data/raw/infra/youtube/us_youtube_data_api_getting_started_{ACCESS_DATE_TAG}.html",
            "access_date": ACCESS_DATE,
            "notes": "Official documentation collected, but direct API extraction is deferred because an API key is required.",
        },
        {
            "source_id": "infra_netflix_top10_home",
            "source_name": "Netflix Top 10 public homepage",
            "source_url": "https://top10.netflix.com/",
            "country_std": "us",
            "firm_std": "netflix",
            "service_std": "netflix",
            "metric_targets": "foreign_dependency_ratio",
            "collection_status": "collected_limited_attention_proxy",
            "raw_storage_path": f"data/raw/infra/netflix/us_netflix_top10_home_{ACCESS_DATE_TAG}.html",
            "access_date": ACCESS_DATE,
            "notes": "Public Tudum Top10 homepage collected, but it is not promoted to the main panel because it lacks a directly comparable country service-share denominator.",
        },
        {
            "source_id": "infra_kr_market_usage_proxy",
            "source_name": "KOCCA content usage survey OTT release",
            "source_url": country_market_rows["kr"]["source_url"],
            "country_std": "kr",
            "firm_std": "",
            "service_std": "",
            "metric_targets": "foreign_dependency_ratio|traffic_cost_pressure",
            "collection_status": "collected_reused_existing",
            "raw_storage_path": country_market_rows["kr"]["raw_storage_path"],
            "access_date": country_market_rows["kr"]["access_date"],
            "notes": "Reused official KOCCA OTT usage raw for Korean foreign-video dependence proxy.",
        },
        {
            "source_id": "infra_us_market_usage_proxy",
            "source_name": "NTIA analyze-table CSV video usage proxy",
            "source_url": country_market_rows["us"]["source_url"],
            "country_std": "us",
            "firm_std": "",
            "service_std": "",
            "metric_targets": "foreign_dependency_ratio",
            "collection_status": "collected_reused_existing",
            "raw_storage_path": country_market_rows["us"]["raw_storage_path"],
            "access_date": country_market_rows["us"]["access_date"],
            "notes": "Reused NTIA videoUser proxy from Nov 2023 for U.S. country-level dependence.",
        },
        {
            "source_id": "infra_jp_market_usage_proxy",
            "source_name": "MIC ICT White Paper internet usage proxy",
            "source_url": country_market_rows["jp"]["source_url"],
            "country_std": "jp",
            "firm_std": "",
            "service_std": "",
            "metric_targets": "foreign_dependency_ratio",
            "collection_status": "collected_reused_existing",
            "raw_storage_path": country_market_rows["jp"]["raw_storage_path"],
            "access_date": country_market_rows["jp"]["access_date"],
            "notes": "Reused MIC PDF and promoted internet-usage-rate proxy where direct video penetration was not available from the retained raw.",
        },
        {
            "source_id": "infra_tw_market_usage_proxy",
            "source_name": "MODA online video entertainment proxy",
            "source_url": country_market_rows["tw"]["source_url"],
            "country_std": "tw",
            "firm_std": "",
            "service_std": "",
            "metric_targets": "foreign_dependency_ratio",
            "collection_status": "collected_reused_existing",
            "raw_storage_path": country_market_rows["tw"]["raw_storage_path"],
            "access_date": country_market_rows["tw"]["access_date"],
            "notes": "Reused MODA survey release and promoted online-video-entertainment share as the Taiwan proxy.",
        },
        {
            "source_id": "infra_tw_market_usage_proxy_2024",
            "source_name": "MODA 2024 online video entertainment extracted proxy",
            "source_url": "https://www-api.moda.gov.tw/File/Get/moda/zh-tw/EJ97STRSQKlDPXJ",
            "country_std": "tw",
            "firm_std": "",
            "service_std": "",
            "metric_targets": "foreign_dependency_ratio",
            "collection_status": "collected_reused_existing",
            "raw_storage_path": str(TW_MARKET_USAGE_2024_EXTRACT_PATH.relative_to(PROJECT_DIR)),
            "access_date": ACCESS_DATE,
            "notes": "Browser-extracted MODA PDF observation for 2024Q4 online-video-entertainment usage (91.1%).",
        },
        {
            "source_id": "infra_uk_market_usage_proxy_2024",
            "source_name": "Ofcom 2024 YouTube reach extracted proxy",
            "source_url": "https://www.ofcom.org.uk/siteassets/resources/documents/research-and-data/online-research/online-nation/2024/online-nation-2024-report.pdf?v=386238",
            "country_std": "uk",
            "firm_std": "",
            "service_std": "",
            "metric_targets": "foreign_dependency_ratio",
            "collection_status": "collected_reused_existing",
            "raw_storage_path": str(UK_MARKET_USAGE_2024_EXTRACT_PATH.relative_to(PROJECT_DIR)),
            "access_date": ACCESS_DATE,
            "notes": "Browser-extracted Ofcom Online Nation 2024 observation for YouTube reach (94%) retained as the UK foreign-video dependence proxy.",
        },
        {
            "source_id": "infra_ca_market_usage_proxy",
            "source_name": "CRTC youth audiovisual penetration proxy",
            "source_url": country_market_rows["ca"]["source_url"],
            "country_std": "ca",
            "firm_std": "",
            "service_std": "",
            "metric_targets": "foreign_dependency_ratio",
            "collection_status": "collected_reused_existing",
            "raw_storage_path": country_market_rows["ca"]["raw_storage_path"],
            "access_date": country_market_rows["ca"]["access_date"],
            "notes": "Reused CRTC PDF and promoted youth YouTube/SVOD penetration as the retained Canada proxy.",
        },
        {
            "source_id": "infra_kt_opendart_roles",
            "source_name": "KT OpenDART XBRL statement roles",
            "source_url": "https://engopendart.fss.or.kr/xbrl/viewer/main.do?rcpNo=20260323001553&lang=en",
            "country_std": "kr",
            "firm_std": "kt",
            "service_std": "kt_network",
            "metric_targets": "network_cost_ratio|domestic_infra_capex_ratio|outflow_to_capex_ratio|traffic_cost_pressure",
            "collection_status": "collected",
            "raw_storage_path": f"data/raw/infra/opendart/kr_kt_*_{ACCESS_DATE_TAG}.html",
            "access_date": ACCESS_DATE,
            "notes": "Collected consolidated income-statement and cash-flow role pages from the English OpenDART XBRL viewer.",
        },
        {
            "source_id": "infra_sk_telecom_opendart_roles",
            "source_name": "SK Telecom OpenDART XBRL statement roles",
            "source_url": "https://engopendart.fss.or.kr/xbrl/viewer/main.do?rcpNo=20260318000532&lang=en",
            "country_std": "kr",
            "firm_std": "sk_telecom",
            "service_std": "skt_network",
            "metric_targets": "network_cost_ratio|domestic_infra_capex_ratio|outflow_to_capex_ratio|traffic_cost_pressure",
            "collection_status": "collected",
            "raw_storage_path": f"data/raw/infra/opendart/kr_sk_telecom_*_{ACCESS_DATE_TAG}.html",
            "access_date": ACCESS_DATE,
            "notes": "Collected consolidated income-statement and cash-flow role pages from the English OpenDART XBRL viewer.",
        },
        {
            "source_id": "infra_lg_uplus_opendart_roles",
            "source_name": "LG Uplus OpenDART XBRL statement roles",
            "source_url": "https://engopendart.fss.or.kr/xbrl/viewer/main.do?rcpNo=20260313000442&lang=en",
            "country_std": "kr",
            "firm_std": "lg_uplus",
            "service_std": "lguplus_network",
            "metric_targets": "network_cost_ratio|domestic_infra_capex_ratio|outflow_to_capex_ratio|traffic_cost_pressure",
            "collection_status": "collected",
            "raw_storage_path": f"data/raw/infra/opendart/kr_lg_uplus_*_{ACCESS_DATE_TAG}.html",
            "access_date": ACCESS_DATE,
            "notes": "Collected consolidated income-statement and cash-flow role pages from the English OpenDART XBRL viewer.",
        },
        {
            "source_id": "infra_netflix_sec_filings",
            "source_name": "Netflix SEC filings reuse",
            "source_url": "https://www.sec.gov/edgar/search-and-access",
            "country_std": "us",
            "firm_std": "netflix",
            "service_std": "netflix",
            "metric_targets": "network_cost_ratio|domestic_infra_capex_ratio|outflow_to_capex_ratio",
            "collection_status": "collected_reused_existing",
            "raw_storage_path": "data/raw/us/filings/netflix/*",
            "access_date": ACCESS_DATE,
            "notes": "Reused annual and 10-Q raw filings collected in Exec Prompt 13.",
        },
        {
            "source_id": "infra_alphabet_sec_filings",
            "source_name": "Alphabet SEC filings reuse",
            "source_url": "https://www.sec.gov/edgar/search-and-access",
            "country_std": "us",
            "firm_std": "alphabet",
            "service_std": "youtube",
            "metric_targets": "network_cost_ratio|domestic_infra_capex_ratio|outflow_to_capex_ratio",
            "collection_status": "collected_company_proxy",
            "raw_storage_path": "data/raw/us/filings/alphabet/*",
            "access_date": ACCESS_DATE,
            "notes": "Reused annual and 10-Q raw filings. Ratios remain Alphabet-company proxies, not YouTube-exact cost/capex splits.",
        },
        {
            "source_id": "infra_amazon_sec_filings",
            "source_name": "Amazon SEC filings reuse",
            "source_url": "https://www.sec.gov/edgar/search-and-access",
            "country_std": "us",
            "firm_std": "amazon",
            "service_std": "aws",
            "metric_targets": "network_cost_ratio|domestic_infra_capex_ratio|outflow_to_capex_ratio",
            "collection_status": "collected_company_proxy",
            "raw_storage_path": "data/raw/us/filings/amazon/*",
            "access_date": ACCESS_DATE,
            "notes": "Reused annual and 10-Q raw filings. Ratios remain Amazon-company proxies, not AWS-exact cost/capex splits.",
        },
        {
            "source_id": "infra_cloudflare_sec_filings",
            "source_name": "Cloudflare SEC filings reuse",
            "source_url": "https://www.sec.gov/edgar/search-and-access",
            "country_std": "us",
            "firm_std": "cloudflare",
            "service_std": "cloudflare_cdn",
            "metric_targets": "network_cost_ratio|domestic_infra_capex_ratio|outflow_to_capex_ratio",
            "collection_status": "collected_reused_existing",
            "raw_storage_path": "data/raw/us/filings/cloudflare/*",
            "access_date": ACCESS_DATE,
            "notes": "Reused annual and 10-Q raw filings collected in Exec Prompt 13.",
        },
        {
            "source_id": "infra_akamai_sec_filings",
            "source_name": "Akamai SEC filings reuse",
            "source_url": "https://www.sec.gov/edgar/search-and-access",
            "country_std": "us",
            "firm_std": "akamai",
            "service_std": "akamai_cdn",
            "metric_targets": "network_cost_ratio|domestic_infra_capex_ratio|outflow_to_capex_ratio",
            "collection_status": "collected_reused_existing",
            "raw_storage_path": "data/raw/us/filings/akamai/*",
            "access_date": ACCESS_DATE,
            "notes": "Reused annual and 10-Q raw filings collected in Exec Prompt 13.",
        },
    ]
    return rows


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
            "path": "scripts/collect_infra_service_data.py",
            "owner_step": PROMPT_LABEL,
            "source_type": "local_code",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Reproducible collector for infrastructure service raw sources, panel assembly, and manifest updates.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/interim/infra_service_raw_panel.csv",
            "owner_step": PROMPT_LABEL,
            "source_type": "derived_public_panel",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Long-form service-country-quarter panel for infrastructure proxies and filing-derived ratios.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/interim/infra_source_registry.csv",
            "owner_step": PROMPT_LABEL,
            "source_type": "public_web_collection",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Infrastructure-sector source registry with blocked, proxy, and reused-filing statuses.",
        },
        {
            "artifact_type": "file",
            "path": "logs/infra_service_collection_log.md",
            "owner_step": PROMPT_LABEL,
            "source_type": "execution_log",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Execution log summarizing raw collection outcomes, promoted metrics, and unresolved access limits.",
        },
    ]
    upsert_csv(PROJECT_MANIFEST_PATH, rows, ["path"], fieldnames)


def append_workflow_log(raw_count: int, panel_rows: int, status_counts: Counter[str]) -> None:
    text = WORKFLOW_LOG_PATH.read_text() if WORKFLOW_LOG_PATH.exists() else "# Workflow Log\n"
    block = (
        f"\n### {PROMPT_LABEL}. 디지털 인프라 분야 서비스·트래픽 데이터 수집\n\n"
        f"- `data/raw/infra/` 아래 신규 raw 파일 `{raw_count}`건 저장\n"
        f"- `data/interim/infra_source_registry.csv` 생성 및 소스 상태 `{dict(status_counts)}` 기록\n"
        f"- `data/interim/infra_service_raw_panel.csv` 생성, 총 `{panel_rows}`행의 서비스-국가-분기 패널 구축\n"
        f"- 국내 통신 3사에 대해 OpenDART XBRL role 페이지에서 `revenue`, `operating expense`, `capex proxy`를 추출함\n"
        f"- 글로벌 비교군은 기존 SEC raw filing을 재사용해 `network_cost_ratio`, `domestic_infra_capex_ratio`, `outflow_to_capex_ratio`를 구축함\n"
        f"- `Cloudflare Radar`는 인증 필요, `YouTube Data API`는 키 필요 상태로 기록하고 메인 패널에는 직접 승격하지 않음\n"
    )
    if block not in text:
        WORKFLOW_LOG_PATH.write_text(text.rstrip() + "\n" + block)


def write_log(raw_files: list[dict[str, str]], source_registry_rows: list[dict[str, str]], panel_rows: list[dict[str, str]]) -> None:
    metric_counts = Counter(row["metric_name"] for row in panel_rows)
    status_counts = Counter(row["collection_status"] for row in panel_rows)
    source_status_counts = Counter(row["collection_status"] for row in source_registry_rows)
    log_text = "\n".join(
        [
            f"# {PROMPT_LABEL} Log",
            "",
            f"- access_date: `{ACCESS_DATE}`",
            f"- new_raw_files: `{len(raw_files)}`",
            f"- source_registry_rows: `{len(source_registry_rows)}`",
            f"- infra_service_raw_panel_rows: `{len(panel_rows)}`",
            f"- panel_metric_counts: `{dict(metric_counts)}`",
            f"- panel_status_counts: `{dict(status_counts)}`",
            f"- source_status_counts: `{dict(source_status_counts)}`",
            "",
            "## Promoted Raw Sources",
            "",
            "- Korean telecom XBRL role pages: `income statement` + `cash flow statement` for `KT`, `SK Telecom`, `LG Uplus`.",
            "- Reused country market raw: `KOCCA`, `NTIA`, `MIC`, `MODA`, `CRTC`.",
            "- Browser-extracted country proxy raw: `Ofcom Online Nation 2024`, `MODA 113-year Digital Access Survey main report`.",
            "- Reused SEC filings: `Netflix`, `Alphabet`, `Amazon`, `Cloudflare`, `Akamai`.",
            "",
            "## Deferred or Blocked",
            "",
            "- `Cloudflare Radar` public API probe returned missing-auth response and the public Radar UI remained challenge-protected.",
            "- `YouTube Data API` documentation was collected, but direct extraction remains `pending_api_key`.",
            "- Shell retrieval of Ofcom raw remains challenge-blocked, so the retained UK proxy uses a browser-extracted official observation CSV rather than a direct shell-harvested PDF.",
            "- `Netflix Top 10` homepage was collected, but it was not promoted because it does not expose a directly comparable service-share denominator for this panel.",
            "",
            "## Proxy Rules Used in This Step",
            "",
            "- Korean telecom `network_cost_ratio`: `operating_expense / revenue` from consolidated OpenDART statement.",
            "- Korean telecom `domestic_infra_capex_ratio`: cash-flow capital-spending proxy divided by revenue.",
            "- Korean telecom `traffic_cost_pressure`: `foreign_dependency_ratio * network_cost_ratio` using Korea OTT usage share from KOCCA.",
            "- Global infra firm ratios: SEC `cost_of_revenue / revenue`, `capex / revenue`, and `cost_of_revenue / capex`.",
            "- `YouTube` and `AWS` ratios remain company-level proxies because service-specific cost and capex splits are not separately disclosed in retained public filings.",
        ]
    )
    LOG_PATH.write_text(log_text + "\n")


def main() -> None:
    raw_manifest_rows = collect_new_raw_sources()
    source_manifest_fields = [
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
    upsert_csv(SOURCE_MANIFEST_PATH, raw_manifest_rows, ["source_file"], source_manifest_fields)

    country_market_rows = load_country_market_rows()
    country_proxy_rows, proxy_values = build_country_proxy_rows(country_market_rows)
    korean_telco_rows = build_korean_telco_rows(proxy_values["kr"])
    global_filing_rows = build_global_filing_rows()
    panel_rows = country_proxy_rows + korean_telco_rows + global_filing_rows

    panel_fieldnames = [
        "panel_unit_type",
        "country_std",
        "year_month",
        "year_quarter",
        "firm_std",
        "service_std",
        "metric_name",
        "metric_variant",
        "metric_value",
        "metric_unit",
        "source_id",
        "raw_source_file",
        "collection_status",
        "notes",
    ]
    panel_rows = sorted(
        panel_rows,
        key=lambda row: (
            row["country_std"],
            row["service_std"],
            row["year_quarter"],
            row["metric_name"],
            row["metric_variant"],
        ),
    )
    write_csv(RAW_PANEL_PATH, panel_rows, panel_fieldnames)

    source_registry_rows = build_source_registry(country_market_rows)
    source_registry_fieldnames = [
        "source_id",
        "source_name",
        "source_url",
        "country_std",
        "firm_std",
        "service_std",
        "metric_targets",
        "collection_status",
        "raw_storage_path",
        "access_date",
        "notes",
    ]
    write_csv(SOURCE_REGISTRY_PATH, source_registry_rows, source_registry_fieldnames)

    update_project_manifest()
    write_log(raw_manifest_rows, source_registry_rows, panel_rows)
    append_workflow_log(len(raw_manifest_rows), len(panel_rows), Counter(row["collection_status"] for row in source_registry_rows))


if __name__ == "__main__":
    main()
