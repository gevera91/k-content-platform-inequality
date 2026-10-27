#!/usr/bin/env python3

import calendar
import csv
import json
import ssl
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
ACCESS_DATE = date.today().isoformat()
PROMPT_NAME = "Exec Prompt 20"
SSL_CONTEXT = ssl._create_unverified_context()

DATA_DIR = BASE_DIR / "data"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
REGISTRY_DIR = DATA_DIR / "registry"
LOG_DIR = BASE_DIR / "logs"

FINANCIAL_PANEL_PATH = INTERIM_DIR / "financial_extraction_panel.csv"
MUSIC_PANEL_PATH = INTERIM_DIR / "music_market_raw_panel.csv"
WEBTOON_TITLE_PATH = INTERIM_DIR / "webtoon_title_raw_panel.csv"
WEBTOON_PLATFORM_PATH = INTERIM_DIR / "webtoon_platform_raw_panel.csv"
INFRA_PANEL_PATH = INTERIM_DIR / "infra_service_raw_panel.csv"
MACRO_PANEL_PATH = PROCESSED_DIR / "macro_exchange_cpi_panel.csv"

OUTPUT_PATH = INTERIM_DIR / "standardized_numeric_panel.csv"
LOG_PATH = LOG_DIR / "standardization_log.md"
PROJECT_MANIFEST_PATH = REGISTRY_DIR / "project_manifest.csv"
WORKFLOW_LOG_PATH = LOG_DIR / "workflow_log.md"

PROJECT_MANIFEST_FIELDS = [
    "artifact_type",
    "path",
    "owner_step",
    "source_type",
    "source_url",
    "access_date",
    "status",
    "notes",
]

OUTPUT_FIELDS = [
    "standardized_row_id",
    "source_panel",
    "source_row_key",
    "panel_unit_type",
    "country_std",
    "firm_std",
    "service_std",
    "title_std",
    "filing_id",
    "sector_std",
    "metric_name",
    "metric_variant",
    "period_type",
    "raw_period_label",
    "date_standardized",
    "period_end_date",
    "year",
    "year_month",
    "year_quarter",
    "fiscal_period",
    "metric_value_raw",
    "metric_value_numeric_raw",
    "metric_unit_raw",
    "currency_raw",
    "unit_category",
    "metric_unit_standardized",
    "fx_reference_country_std",
    "fx_reference_year_month",
    "fx_to_krw",
    "cpi_index_2021",
    "deflator_index_2021",
    "metric_value_krw_nominal",
    "metric_value_real_krw_cpi2021",
    "metric_value_real_krw_deflator2021",
    "metric_value_standardized",
    "carry_forward_used",
    "standardization_status",
    "collection_status",
    "source_ref",
    "macro_ref_note",
    "notes",
]

WORLD_BANK_ISO3 = {
    "au": "AUS",
    "ca": "CAN",
    "cn": "CHN",
    "de": "DEU",
    "jp": "JPN",
    "kr": "KOR",
    "lu": "LUX",
    "sg": "SGP",
    "uk": "GBR",
    "us": "USA",
}

WB_INDICATORS = {
    "local_per_usd": "PA.NUS.FCRF",
    "cpi_raw": "FP.CPI.TOTL",
    "deflator_raw": "NY.GDP.DEFL.ZS",
}

FETCHED_MACRO_CACHE = {}


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def append_unique_rows(path, fieldnames, new_rows, unique_keys):
    existing_rows = []
    seen = set()
    if path.exists():
        existing_rows = read_csv(path)
        for row in existing_rows:
            seen.add(tuple(row[key] for key in unique_keys))
    for row in new_rows:
        normalized = {field: str(row.get(field, "")) for field in fieldnames}
        key = tuple(normalized[key_field] for key_field in unique_keys)
        if key not in seen:
            existing_rows.append(normalized)
            seen.add(key)
    write_csv(path, existing_rows, fieldnames)


def append_workflow_section(path, header, bullets):
    section_lines = ["", f"### {header}", ""]
    section_lines.extend(f"- {bullet}" for bullet in bullets)
    section = "\n".join(section_lines) + "\n"
    existing = path.read_text(encoding="utf-8") if path.exists() else "# Workflow Log\n"
    if header in existing:
        return
    path.write_text(existing.rstrip() + section, encoding="utf-8")


def normalize_space(value):
    return " ".join((value or "").replace("\xa0", " ").split())


def parse_number(value):
    text = normalize_space(value)
    if text in {"", "na", "n/a", "-", "—"}:
        return None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    text = text.replace(",", "")
    if text.startswith("-"):
        negative = True
        text = text[1:]
    try:
        number = float(text)
    except ValueError:
        return None
    if negative:
        number *= -1
    return number


def serialize_number(value):
    if value is None:
        return ""
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.8f}".rstrip("0").rstrip(".")


def last_day_of_month(year, month):
    return calendar.monthrange(year, month)[1]


def quarter_end_date(year_quarter):
    year = int(year_quarter[:4])
    quarter = int(year_quarter[-1])
    month = quarter * 3
    return f"{year:04d}-{month:02d}-{last_day_of_month(year, month):02d}"


def derive_quarter_from_month(year_month):
    year = int(year_month[:4])
    month = int(year_month[5:7])
    quarter = (month - 1) // 3 + 1
    return f"{year:04d}Q{quarter}"


def derive_period_fields_month(year_month):
    year = year_month[:4]
    month = year_month[5:7]
    period_end = f"{year}-{month}-{last_day_of_month(int(year), int(month)):02d}"
    return {
        "period_type": "month",
        "raw_period_label": year_month,
        "date_standardized": period_end,
        "period_end_date": period_end,
        "year": year,
        "year_month": year_month,
        "year_quarter": derive_quarter_from_month(year_month),
        "fiscal_period": "",
    }


def derive_period_fields_quarter(year_quarter):
    period_end = quarter_end_date(year_quarter)
    return {
        "period_type": "quarter",
        "raw_period_label": year_quarter,
        "date_standardized": period_end,
        "period_end_date": period_end,
        "year": year_quarter[:4],
        "year_month": period_end[:7],
        "year_quarter": year_quarter,
        "fiscal_period": "",
    }


def derive_period_fields_financial(row):
    period_end = row["fiscal_period_end"]
    return {
        "period_type": row["period_granularity"] or "fiscal_period",
        "raw_period_label": row["fiscal_period"],
        "date_standardized": period_end,
        "period_end_date": period_end,
        "year": period_end[:4],
        "year_month": period_end[:7],
        "year_quarter": derive_quarter_from_month(period_end[:7]),
        "fiscal_period": row["fiscal_period"],
    }


def fetch_world_bank_indicator(iso3, indicator):
    url = f"https://api.worldbank.org/v2/country/{iso3}/indicator/{indicator}?format=json&per_page=200"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=25, context=SSL_CONTEXT) as response:
        payload = json.load(response)
    return {entry["date"]: entry["value"] for entry in payload[1] if entry.get("date")}


def build_fetched_macro_country(country_std, macro_lookup):
    if country_std in FETCHED_MACRO_CACHE:
        return FETCHED_MACRO_CACHE[country_std]

    iso3 = WORLD_BANK_ISO3.get(country_std)
    if not iso3:
        FETCHED_MACRO_CACHE[country_std] = {}
        return {}

    try:
        local_per_usd = fetch_world_bank_indicator(iso3, WB_INDICATORS["local_per_usd"])
        cpi_raw = fetch_world_bank_indicator(iso3, WB_INDICATORS["cpi_raw"])
        deflator_raw = fetch_world_bank_indicator(iso3, WB_INDICATORS["deflator_raw"])
    except Exception:
        FETCHED_MACRO_CACHE[country_std] = {}
        return {}

    cpi_base = cpi_raw.get("2021")
    deflator_base = deflator_raw.get("2021")
    rows = {}

    for year_str in sorted(set(local_per_usd) | set(cpi_raw) | set(deflator_raw)):
        if not year_str.isdigit():
            continue
        year = int(year_str)
        for month in range(1, 13):
            year_month = f"{year:04d}-{month:02d}"
            us_row = macro_lookup.get(("us", year_month))
            us_fx = parse_number(us_row["fx_to_krw"]) if us_row else None
            local_value = local_per_usd.get(year_str)
            fx_to_krw = us_fx / local_value if us_fx is not None and local_value not in {None, 0} else None
            cpi_index = (cpi_raw[year_str] / cpi_base * 100.0) if cpi_base not in {None, 0} and cpi_raw.get(year_str) is not None else None
            deflator_index = (deflator_raw[year_str] / deflator_base * 100.0) if deflator_base not in {None, 0} and deflator_raw.get(year_str) is not None else None
            if fx_to_krw is None and cpi_index is None and deflator_index is None:
                continue
            rows[year_month] = {
                "country_std": country_std,
                "year_month": year_month,
                "fx_to_krw": serialize_number(fx_to_krw),
                "cpi_index": serialize_number(cpi_index),
                "deflator": serialize_number(deflator_index),
                "source_url": (
                    f"https://api.worldbank.org/v2/country/{iso3}/indicator/{WB_INDICATORS['local_per_usd']}?format=json&per_page=200"
                    f" | https://api.worldbank.org/v2/country/{iso3}/indicator/{WB_INDICATORS['cpi_raw']}?format=json&per_page=200"
                    f" | https://api.worldbank.org/v2/country/{iso3}/indicator/{WB_INDICATORS['deflator_raw']}?format=json&per_page=200"
                ),
                "macro_origin": "worldbank_live_fetch_exact_annual",
            }

    FETCHED_MACRO_CACHE[country_std] = rows
    return rows


def load_macro_lookup():
    lookup = {}
    for row in read_csv(MACRO_PANEL_PATH):
        key = (row["country_std"], row["year_month"])
        lookup[key] = {
            "country_std": row["country_std"],
            "year_month": row["year_month"],
            "fx_to_krw": row["fx_to_krw"],
            "cpi_index": row["cpi_index"],
            "deflator": row["deflator"],
            "source_url": row["source_url"],
            "macro_origin": "local_macro_panel_exact",
        }
    return lookup


def get_macro_reference(country_std, year_month, macro_lookup):
    if (country_std, year_month) not in macro_lookup:
        fetched = build_fetched_macro_country(country_std, macro_lookup)
        for fetched_year_month, row in fetched.items():
            macro_lookup[(country_std, fetched_year_month)] = row

    exact = macro_lookup.get((country_std, year_month))
    if exact:
        return exact, "no", exact["macro_origin"]

    candidate_keys = [
        key for key in macro_lookup.keys() if key[0] == country_std and key[1] <= year_month
    ]
    if not candidate_keys:
        return None, "", "missing_macro_reference"

    ref_key = max(candidate_keys, key=lambda item: item[1])
    ref_row = macro_lookup[ref_key].copy()
    origin = ref_row["macro_origin"]
    return ref_row, "yes", origin.replace("_exact", "_carry_forward")


def classify_metric(source_panel, metric_name, metric_unit_raw):
    if source_panel == "financial_extraction_panel":
        return "amount", "krw_nominal", True
    if metric_name == "service_monthly_price_krw":
        return "amount", "krw_nominal", True
    if metric_name == "relative_price_gap":
        return "ratio", "ratio", False
    if metric_name == "music_service_hhi":
        return "index", "hhi_0_10000", False
    if metric_name == "title_position":
        return "rank", "rank_ascending", False
    if metric_name in {"local_ip_proxy", "translated_proxy"}:
        return "binary", "binary_0_1", False
    if metric_unit_raw == "share":
        return "share", "share_0_1", False
    if metric_unit_raw == "ratio":
        return "ratio", "ratio", False
    if metric_unit_raw == "count":
        return "count", "count", False
    if metric_unit_raw == "krw":
        return "amount", "krw_nominal", True
    if metric_unit_raw == "HHI_10000":
        return "index", "hhi_0_10000", False
    return "unknown", "unknown", False


def standardize_amount(value_raw, currency_raw, country_std, year_month, macro_lookup):
    ref_row, carry_forward_used, macro_origin = get_macro_reference(country_std, year_month, macro_lookup)
    if not ref_row:
        return {
            "fx_reference_country_std": country_std,
            "fx_reference_year_month": "",
            "fx_to_krw": "",
            "cpi_index_2021": "",
            "deflator_index_2021": "",
            "metric_value_krw_nominal": "",
            "metric_value_real_krw_cpi2021": "",
            "metric_value_real_krw_deflator2021": "",
            "metric_value_standardized": "",
            "carry_forward_used": "",
            "standardization_status": "missing_macro_reference",
            "macro_ref_note": f"{country_std} macro reference missing for {year_month}",
        }

    fx_to_krw = 1.0 if currency_raw == "KRW" else parse_number(ref_row["fx_to_krw"])
    cpi_index = parse_number(ref_row["cpi_index"])
    deflator_index = parse_number(ref_row["deflator"])
    nominal_krw = value_raw if currency_raw == "KRW" else (value_raw * fx_to_krw if fx_to_krw is not None else None)
    real_cpi = nominal_krw * 100.0 / cpi_index if nominal_krw is not None and cpi_index not in {None, 0} else None
    real_deflator = nominal_krw * 100.0 / deflator_index if nominal_krw is not None and deflator_index not in {None, 0} else None
    status_prefix = "converted"
    if currency_raw == "KRW":
        status_prefix = "already_krw"
    status = f"{status_prefix}_{macro_origin}"
    if carry_forward_used == "yes":
        status = f"{status_prefix}_carry_forward"
    return {
        "fx_reference_country_std": ref_row["country_std"],
        "fx_reference_year_month": ref_row["year_month"],
        "fx_to_krw": serialize_number(fx_to_krw),
        "cpi_index_2021": serialize_number(cpi_index),
        "deflator_index_2021": serialize_number(deflator_index),
        "metric_value_krw_nominal": serialize_number(nominal_krw),
        "metric_value_real_krw_cpi2021": serialize_number(real_cpi),
        "metric_value_real_krw_deflator2021": serialize_number(real_deflator),
        "metric_value_standardized": serialize_number(nominal_krw),
        "carry_forward_used": carry_forward_used,
        "standardization_status": status,
        "macro_ref_note": f"{macro_origin} | {ref_row['country_std']} | {ref_row['year_month']} | {ref_row['source_url']}",
    }


def standardize_non_amount(value_raw):
    return {
        "fx_reference_country_std": "",
        "fx_reference_year_month": "",
        "fx_to_krw": "",
        "cpi_index_2021": "",
        "deflator_index_2021": "",
        "metric_value_krw_nominal": "",
        "metric_value_real_krw_cpi2021": "",
        "metric_value_real_krw_deflator2021": "",
        "metric_value_standardized": serialize_number(value_raw),
        "carry_forward_used": "no",
        "standardization_status": "standardized_non_amount",
        "macro_ref_note": "",
    }


def create_row(base_fields, value_raw, currency_raw, macro_lookup):
    unit_category, standardized_unit, is_amount = classify_metric(
        base_fields["source_panel"],
        base_fields["metric_name"],
        base_fields["metric_unit_raw"],
    )
    value_num = parse_number(base_fields["metric_value_raw"])
    if value_num is None:
        value_num = value_raw
    if is_amount and value_num is not None:
        conversion = standardize_amount(value_num, currency_raw, base_fields["country_std"], base_fields["year_month"], macro_lookup)
    else:
        conversion = standardize_non_amount(value_num)
    return {
        **base_fields,
        "metric_value_numeric_raw": serialize_number(value_num),
        "currency_raw": currency_raw,
        "unit_category": unit_category,
        "metric_unit_standardized": standardized_unit,
        **conversion,
    }


def build_financial_rows(macro_lookup):
    rows = []
    for idx, row in enumerate(read_csv(FINANCIAL_PANEL_PATH), start=1):
        period_fields = derive_period_fields_financial(row)
        base_fields = {
            "standardized_row_id": f"financial_{idx:05d}",
            "source_panel": "financial_extraction_panel",
            "source_row_key": f"{row['filing_id']}|{row['metric_name']}",
            "panel_unit_type": "firm_fiscal_period",
            "country_std": row["country_std"],
            "firm_std": row["firm_std"],
            "service_std": row["service_std"],
            "title_std": "",
            "filing_id": row["filing_id"],
            "sector_std": row["sector_std"],
            "metric_name": row["metric_name"],
            "metric_variant": "",
            "metric_value_raw": row["metric_value_raw"],
            "metric_unit_raw": "currency_amount",
            "collection_status": "collected",
            "source_ref": f"{row['source_file']} | {row['source_url']}",
            "notes": f"{row['source_page_or_note']} | {row['extraction_method']} | {row['metric_quality']}",
            **period_fields,
        }
        rows.append(create_row(base_fields, parse_number(row["metric_value_raw"]), row["currency"], macro_lookup))
    return rows


def build_music_rows(macro_lookup):
    rows = []
    for idx, row in enumerate(read_csv(MUSIC_PANEL_PATH), start=1):
        period_fields = derive_period_fields_month(row["year_month"])
        base_fields = {
            "standardized_row_id": f"music_{idx:05d}",
            "source_panel": "music_market_raw_panel",
            "source_row_key": "|".join(
                [
                    row["panel_unit_type"],
                    row["country_std"],
                    row["year_month"],
                    row["firm_std"],
                    row["service_std"],
                    row["metric_name"],
                    row["metric_variant"],
                ]
            ),
            "panel_unit_type": row["panel_unit_type"],
            "country_std": row["country_std"],
            "firm_std": row["firm_std"],
            "service_std": row["service_std"],
            "title_std": "",
            "filing_id": "",
            "sector_std": "music",
            "metric_name": row["metric_name"],
            "metric_variant": row["metric_variant"],
            "metric_value_raw": row["metric_value"],
            "metric_unit_raw": row["metric_unit"],
            "collection_status": row["collection_status"],
            "source_ref": f"{row['source_id']} | {row['raw_source_file']}",
            "notes": row["notes"],
            **period_fields,
        }
        currency_raw = "KRW" if row["metric_unit"] == "krw" and row["metric_name"] != "relative_price_gap" else ""
        rows.append(create_row(base_fields, parse_number(row["metric_value"]), currency_raw, macro_lookup))
    return rows


def build_webtoon_platform_rows(macro_lookup):
    rows = []
    for idx, row in enumerate(read_csv(WEBTOON_PLATFORM_PATH), start=1):
        period_fields = derive_period_fields_quarter(row["year_quarter"])
        base_fields = {
            "standardized_row_id": f"webtoon_platform_{idx:05d}",
            "source_panel": "webtoon_platform_raw_panel",
            "source_row_key": "|".join(
                [
                    row["panel_unit_type"],
                    row["country_std"],
                    row["year_quarter"],
                    row["firm_std"],
                    row["service_std"],
                    row["metric_name"],
                    row["metric_variant"],
                ]
            ),
            "panel_unit_type": row["panel_unit_type"],
            "country_std": row["country_std"],
            "firm_std": row["firm_std"],
            "service_std": row["service_std"],
            "title_std": "",
            "filing_id": "",
            "sector_std": "webtoon_story",
            "metric_name": row["metric_name"],
            "metric_variant": row["metric_variant"],
            "metric_value_raw": row["metric_value"],
            "metric_unit_raw": row["metric_unit"],
            "collection_status": row["collection_status"],
            "source_ref": f"{row['source_id']} | {row['raw_source_file']}",
            "notes": row["notes"],
            **period_fields,
        }
        rows.append(create_row(base_fields, parse_number(row["metric_value"]), "", macro_lookup))
    return rows


def build_webtoon_title_rows(macro_lookup):
    rows = []
    counter = 0
    metric_specs = [
        ("title_position", "position", "rank", "position_snapshot"),
        ("local_ip_proxy", "local_ip_proxy", "binary", "binary_proxy"),
        ("translated_proxy", "translated_proxy", "binary", "binary_proxy"),
    ]
    for row in read_csv(WEBTOON_TITLE_PATH):
        period_fields = derive_period_fields_quarter(row["year_quarter"])
        for metric_name, source_field, metric_unit_raw, metric_variant in metric_specs:
            counter += 1
            base_fields = {
                "standardized_row_id": f"webtoon_title_{counter:05d}",
                "source_panel": "webtoon_title_raw_panel",
                "source_row_key": f"{row['title_std']}|{row['year_quarter']}|{metric_name}",
                "panel_unit_type": "title_quarter",
                "country_std": row["country_std"],
                "firm_std": row["firm_std"],
                "service_std": row["service_std"],
                "title_std": row["title_std"],
                "filing_id": "",
                "sector_std": "webtoon_story",
                "metric_name": metric_name,
                "metric_variant": metric_variant,
                "metric_value_raw": row[source_field],
                "metric_unit_raw": metric_unit_raw,
                "collection_status": row["collection_status"],
                "source_ref": f"{row['source_id']} | {row['raw_source_file']}",
                "notes": f"{row['notes']} | {row['proxy_basis']}",
                **period_fields,
            }
            rows.append(create_row(base_fields, parse_number(row[source_field]), "", macro_lookup))
    return rows


def build_infra_rows(macro_lookup):
    rows = []
    for idx, row in enumerate(read_csv(INFRA_PANEL_PATH), start=1):
        period_fields = derive_period_fields_month(row["year_month"])
        period_fields["period_type"] = "quarter_snapshot"
        period_fields["raw_period_label"] = row["year_quarter"]
        base_fields = {
            "standardized_row_id": f"infra_{idx:05d}",
            "source_panel": "infra_service_raw_panel",
            "source_row_key": "|".join(
                [
                    row["panel_unit_type"],
                    row["country_std"],
                    row["year_quarter"],
                    row["firm_std"],
                    row["service_std"],
                    row["metric_name"],
                    row["metric_variant"],
                ]
            ),
            "panel_unit_type": row["panel_unit_type"],
            "country_std": row["country_std"],
            "firm_std": row["firm_std"],
            "service_std": row["service_std"],
            "title_std": "",
            "filing_id": "",
            "sector_std": "digital_infra",
            "metric_name": row["metric_name"],
            "metric_variant": row["metric_variant"],
            "metric_value_raw": row["metric_value"],
            "metric_unit_raw": row["metric_unit"],
            "collection_status": row["collection_status"],
            "source_ref": f"{row['source_id']} | {row['raw_source_file']}",
            "notes": row["notes"],
            **period_fields,
        }
        rows.append(create_row(base_fields, parse_number(row["metric_value"]), "", macro_lookup))
    return rows


def build_log(rows):
    source_counts = Counter(row["source_panel"] for row in rows)
    unit_counts = Counter(row["unit_category"] for row in rows)
    status_counts = Counter(row["standardization_status"] for row in rows)
    amount_rows = [row for row in rows if row["unit_category"] == "amount"]
    currency_counts = Counter(row["currency_raw"] for row in amount_rows)
    carry_counts = Counter(row["carry_forward_used"] for row in amount_rows)
    missing_amount = sum(1 for row in amount_rows if row["metric_value_krw_nominal"] == "")

    log_lines = [
        "# Standardization Log",
        "",
        f"- Access date: `{ACCESS_DATE}`",
        f"- Prompt: `{PROMPT_NAME}`",
        f"- Output rows: `{len(rows)}`",
        f"- Amount rows: `{len(amount_rows)}`",
        f"- Amount rows without KRW conversion: `{missing_amount}`",
        "",
        "## Source Panel Counts",
        "",
    ]
    for panel_name, count in sorted(source_counts.items()):
        log_lines.append(f"- `{panel_name}`: `{count}` rows")

    log_lines.extend(["", "## Unit Category Counts", ""])
    for unit_name, count in sorted(unit_counts.items()):
        log_lines.append(f"- `{unit_name}`: `{count}` rows")

    log_lines.extend(["", "## Amount Currency Counts", ""])
    for currency_name, count in sorted(currency_counts.items()):
        log_lines.append(f"- `{currency_name or 'blank'}`: `{count}` rows")

    log_lines.extend(["", "## Standardization Status Counts", ""])
    for status_name, count in sorted(status_counts.items()):
        log_lines.append(f"- `{status_name}`: `{count}` rows")

    log_lines.extend(
        [
            "",
            "## Carry-Forward Summary",
            "",
            f"- `carry_forward_used=yes`: `{carry_counts.get('yes', 0)}` amount rows",
            f"- `carry_forward_used=no`: `{carry_counts.get('no', 0)}` amount rows",
            "",
            "## Notes",
            "",
            "- 표준 날짜는 모두 `period_end_date` 기준으로 정렬했고 `year_month`, `year_quarter`는 그 종료시점 기준으로 재계산했다.",
            "- 금액행은 `metric_value_raw`를 보존하면서 `metric_value_krw_nominal`, `metric_value_real_krw_cpi2021`, `metric_value_real_krw_deflator2021`를 추가했다.",
            "- `2025`와 `2026-03` 시점 금액행 중 공개 거시 기준이 비어 있는 경우 가장 최근 공개월을 carry-forward했고, 해당 여부를 `carry_forward_used`와 `standardization_status`에 기록했다.",
            "- `LU`와 `CN`은 local macro panel에 없기 때문에 공식 `World Bank` 공개 API 연간값을 보조 참조로 사용했고, 실제 환산에 사용한 기준월은 `fx_reference_year_month`에 남겼다.",
            "- `relative_price_gap`는 원 패널에서 `metric_unit=krw`로 표기돼 있었지만 값의 의미가 비율이므로 표준화 단계에서 `ratio`로 재분류했다.",
        ]
    )

    LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")


def update_project_manifest():
    new_rows = [
        {
            "artifact_type": "script",
            "path": "scripts/build_standardized_numeric_panel.py",
            "owner_step": PROMPT_NAME,
            "source_type": "local_code",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Standardizes dates, currencies, and units across financial, music, webtoon, and infrastructure numeric panels.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/interim/standardized_numeric_panel.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_standardized_panel",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Long standardized numeric panel with preserved raw values, KRW conversions, and real-value columns.",
        },
        {
            "artifact_type": "log",
            "path": "logs/standardization_log.md",
            "owner_step": PROMPT_NAME,
            "source_type": "local_log",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Summary log for date alignment, KRW conversion coverage, unit classification, and carry-forward usage.",
        },
    ]
    append_unique_rows(PROJECT_MANIFEST_PATH, PROJECT_MANIFEST_FIELDS, new_rows, ["path"])


def update_workflow_log(rows):
    amount_rows = [row for row in rows if row["unit_category"] == "amount"]
    carry_forward_count = sum(1 for row in amount_rows if row["carry_forward_used"] == "yes")
    bullets = [
        f"`data/interim/standardized_numeric_panel.csv` 생성, 총 `{len(rows)}`행을 월/분기/회계기간 기준으로 정렬",
        f"금액행 `{len(amount_rows)}`건에 대해 `KRW`, `실질 CPI 2021`, `실질 GDP deflator 2021` 열을 추가",
        f"`carry_forward_used=yes` 금액행 `{carry_forward_count}`건을 별도 플래그로 남기고 `logs/standardization_log.md`에 근거를 기록",
        "비율·지수·개수·순위·이진값과 금액을 구분해 `unit_category`와 `metric_unit_standardized`를 고정",
    ]
    append_workflow_section(WORKFLOW_LOG_PATH, "Exec Prompt 20. 날짜·통화·단위 표준화", bullets)


def build_output():
    macro_lookup = load_macro_lookup()
    rows = []
    rows.extend(build_financial_rows(macro_lookup))
    rows.extend(build_music_rows(macro_lookup))
    rows.extend(build_webtoon_platform_rows(macro_lookup))
    rows.extend(build_webtoon_title_rows(macro_lookup))
    rows.extend(build_infra_rows(macro_lookup))
    rows.sort(
        key=lambda row: (
            row["source_panel"],
            row["country_std"],
            row["firm_std"],
            row["service_std"],
            row["title_std"],
            row["metric_name"],
            row["date_standardized"],
        )
    )
    write_csv(OUTPUT_PATH, rows, OUTPUT_FIELDS)
    build_log(rows)
    update_project_manifest()
    update_workflow_log(rows)


if __name__ == "__main__":
    build_output()
