#!/usr/bin/env python3

import csv
import html
import json
import re
import ssl
import time
import urllib.request
import zlib
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
ACCESS_DATE = "2026-03-29"
STAMP = "20260329"
PROMPT_NAME = "Exec Prompt 13"
SEC_UA = "Mozilla/5.0 research@example.com"
GENERIC_UA = "Mozilla/5.0"
SSL_CONTEXT = ssl._create_unverified_context()

SEC_CIK_MAP = {
    "akamai": "0001086222",
    "alphabet": "0001652044",
    "amazon": "0001018724",
    "cloudflare": "0001477333",
    "netflix": "0001065280",
    "spotify": "0001639920",
    "tencent_music": "0001744676",
    "warner_music": "0001319161",
    "webtoon_ent": "0001997859",
}

SEC_PERIODIC_ACCESSION_OVERRIDE = {
    "spotify": "0001628280-25-048927",
    "tencent_music": "0000950103-25-014559",
}

KADOKAWA_LISTING_URLS = {
    "page1": "https://group.kadokawa.co.jp/global/information/page/1/",
    "page3": "https://group.kadokawa.co.jp/global/information/page/3/",
}

KADOKAWA_SELECTIONS = {
    "annual": {
        "title": "Earnings Results for the Fiscal Year Ended March 31, 2025",
        "source_url": "https://ssl4.eir-parts.net/doc/9468/ir_material_for_fiscal_ym13/177768/00.pdf",
        "filing_date": "2025-05-08",
    },
    "interim": {
        "title": "Earnings Results for the 3rd Quarter Ended December 31, 2025",
        "source_url": "https://ssl4.eir-parts.net/doc/9468/ir_material_for_fiscal_ym13/198090/00.pdf",
        "filing_date": "2026-02-12",
    },
    "current_report": {
        "title": "Notice Concerning Change of Major and Principal Shareholder",
        "source_url": "https://ssl4.eir-parts.net/doc/9468/ir_material7/275812/00.pdf",
        "filing_date": "2026-03-27",
    },
}

FIRM_CURRENCY_MAP = {
    "akamai": "USD",
    "alphabet": "USD",
    "amazon": "USD",
    "cloudflare": "USD",
    "kadokawa": "JPY",
    "netflix": "USD",
    "spotify": "EUR",
    "tencent_music": "RMB",
    "warner_music": "USD",
    "webtoon_ent": "USD",
}


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
        key = tuple(row[key] for key in unique_keys)
        if key not in seen:
            existing_rows.append(row)
            seen.add(key)
    write_csv(path, existing_rows, fieldnames)


def fetch_bytes(url, user_agent):
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=45, context=SSL_CONTEXT) as response:
        return response.read()


def fetch_text(url, user_agent):
    return fetch_bytes(url, user_agent).decode("utf-8", "ignore")


def save_bytes(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def relative_path(path):
    return path.relative_to(BASE_DIR).as_posix()


def normalize_space(text):
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def clean_html_text(raw_html):
    text = re.sub(r"(?is)<script.*?</script>", " ", raw_html)
    text = re.sub(r"(?is)<style.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", "\n", text)
    return html.unescape(text)


def extract_pdf_lines(path):
    data = path.read_bytes()
    lines = []
    seen = set()
    for match in re.finditer(rb"stream\r?\n", data):
        start = match.end()
        end = data.find(b"endstream", start)
        if end == -1:
            continue
        blob = data[start:end].strip(b"\r\n")
        try:
            decoded = zlib.decompress(blob).decode("latin1", "ignore")
        except Exception:
            continue
        for raw_line in decoded.splitlines():
            fragments = re.findall(r"\((.*?)\)", raw_line)
            if not fragments:
                continue
            line = "".join(fragments)
            line = line.replace("\\(", "(").replace("\\)", ")").replace("\\n", " ")
            line = normalize_space(line)
            if len(line) < 4 or len(line) > 220:
                continue
            if line in seen:
                continue
            seen.add(line)
            lines.append(line)
    return lines


def extract_html_lines(raw_html):
    lines = []
    seen = set()
    for raw_line in clean_html_text(raw_html).splitlines():
        line = normalize_space(raw_line)
        if len(line) < 4 or len(line) > 220:
            continue
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)
    return lines


def first_line(lines, keywords):
    for keyword in keywords:
        keyword_lower = keyword.lower()
        for line in lines:
            if keyword_lower in line.lower():
                return line
    return ""


def detect_currency(text, firm_std):
    if firm_std in FIRM_CURRENCY_MAP:
        return FIRM_CURRENCY_MAP[firm_std]
    lower = text.lower()
    if "euro" in lower or "euros" in lower:
        return "EUR"
    if "renminbi" in lower or "rmb" in lower:
        return "RMB"
    if "japanese yen" in lower or "jpy" in lower:
        return "JPY"
    if "u.s. dollars" in lower or "us dollars" in lower or "usd" in lower:
        return "USD"
    return "USD"


def detect_accounting_standard(text, firm_std):
    lower = text.lower()
    if "international financial reporting standards" in lower or "ifrs" in lower:
        return "IFRS_IASB"
    if "generally accepted accounting principles in the united states" in lower or "u.s. gaap" in lower:
        return "US_GAAP"
    if "japanese gaap" in lower:
        return "JAPANESE_GAAP"
    if firm_std == "kadokawa":
        return "JAPANESE_GAAP_PROXY"
    if firm_std in {"spotify", "tencent_music"}:
        return "IFRS_OR_FOREIGN_ISSUER_PROXY"
    return "US_GAAP"


def extract_note_locations(lines, sector_std):
    return {
        "note_location_segment": first_line(
            lines,
            [
                "operating segment",
                "segment information",
                "reportable segment",
                "segments",
                "business segment",
            ],
        )
        or "not_explicit_in_saved_filing",
        "note_location_revenue": first_line(
            lines,
            ["revenue", "revenues", "net sales", "sales", "turnover"],
        )
        or "not_explicit_in_saved_filing",
        "note_location_cost": first_line(
            lines,
            [
                "cost of revenue",
                "cost of revenues",
                "cost of sales",
                "operating expenses",
                "costs and expenses",
                "content costs",
                "network costs",
                "selling, general",
            ],
        )
        or "not_explicit_in_saved_filing",
        "note_location_tax": first_line(
            lines,
            ["income taxes", "income tax expense", "tax expense", "provision for income taxes"],
        )
        or "not_explicit_in_saved_filing",
        "note_location_intangible": first_line(
            lines,
            ["intangible assets", "goodwill and intangible", "goodwill", "other intangible"],
        )
        or "not_explicit_in_saved_filing",
        "note_location_capex": first_line(
            lines,
            [
                "capital expenditures",
                "purchases of property and equipment",
                "property and equipment",
                "additions to property and equipment",
                "capex",
            ],
        )
        or "not_explicit_in_saved_filing",
    }


def parse_recent_filings(submissions_json):
    recent = submissions_json["filings"]["recent"]
    items = []
    total = len(recent["form"])
    for idx in range(total):
        items.append(
            {
                "form": recent["form"][idx],
                "filing_date": recent["filingDate"][idx],
                "accession_number": recent["accessionNumber"][idx],
                "primary_document": recent["primaryDocument"][idx],
                "primary_doc_description": recent["primaryDocDescription"][idx],
            }
        )
    return items


def choose_first(filings, forms):
    for filing in filings:
        if filing["form"] in forms:
            return filing
    return None


def choose_periodic_sec(firm_std, filings):
    override = SEC_PERIODIC_ACCESSION_OVERRIDE.get(firm_std)
    if override:
        for filing in filings:
            if filing["accession_number"] == override:
                return filing

    ten_q = choose_first(filings, {"10-Q"})
    if ten_q:
        return ten_q

    candidates = [filing for filing in filings if filing["form"] == "6-K"]
    if not candidates:
        return None
    quarter_tokens = ["20250331", "20250630", "20250930", "20251231", "q1", "q2", "q3", "quarter"]

    def score(filing):
        score_value = 0
        doc = filing["primary_document"].lower()
        desc = filing["primary_doc_description"].lower()
        if any(token in doc for token in quarter_tokens):
            score_value += 100
        if "earnings" in desc or "results" in desc:
            score_value += 25
        if filing["filing_date"][5:7] in {"02", "05", "08", "11"}:
            score_value += 10
        return (score_value, filing["filing_date"])

    return sorted(candidates, key=score, reverse=True)[0]


def choose_current_sec(filings, periodic_filing):
    periodic_accession = periodic_filing["accession_number"] if periodic_filing else ""
    for filing in filings:
        if filing["form"] == "8-K":
            return filing
    for filing in filings:
        if filing["form"] == "6-K" and filing["accession_number"] != periodic_accession:
            return filing
    return None


def save_sec_filing(firm_std, filing_group, cik, filing):
    accession_compact = filing["accession_number"].replace("-", "")
    archive_cik = str(int(cik))
    source_url = (
        f"https://www.sec.gov/Archives/edgar/data/{archive_cik}/{accession_compact}/{filing['primary_document']}"
    )
    extension = Path(filing["primary_document"]).suffix or ".html"
    raw_path = (
        BASE_DIR
        / "data/raw/us/filings"
        / firm_std
        / f"{firm_std}_{filing_group}_{accession_compact}_filing_{STAMP}{extension}"
    )
    content = fetch_bytes(source_url, SEC_UA)
    save_bytes(raw_path, content)
    return source_url, raw_path, content


def save_sec_submissions(firm_std, cik):
    source_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    raw_path = (
        BASE_DIR / "data/raw/us/filings" / firm_std / f"{firm_std}_submissions_{STAMP}.json"
    )
    content = fetch_bytes(source_url, SEC_UA)
    save_bytes(raw_path, content)
    return source_url, raw_path, json.loads(content.decode("utf-8"))


def parse_kadokawa_listing(url):
    raw_html = fetch_text(url, GENERIC_UA)
    items = re.findall(
        r'<li[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>.*?<time class="time">(.*?)</time>.*?<p class="text text-base__010">(.*?)</p>',
        raw_html,
        flags=re.S,
    )
    parsed = []
    for href, filed_time, raw_title in items:
        title = html.unescape(re.sub(r"<[^>]+>", " ", raw_title))
        parsed.append(
            {
                "href": href,
                "filing_date": normalize_space(filed_time).replace(",", ""),
                "title": normalize_space(title),
            }
        )
    return raw_html, parsed


def normalize_english_date(value):
    months = {
        "Jan": "01",
        "Feb": "02",
        "Mar": "03",
        "Apr": "04",
        "May": "05",
        "Jun": "06",
        "Jul": "07",
        "Aug": "08",
        "Sep": "09",
        "Oct": "10",
        "Nov": "11",
        "Dec": "12",
    }
    match = re.match(r"([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})", value)
    if not match:
        return value
    month, day, year = match.groups()
    return f"{year}-{months[month]}-{int(day):02d}"


def save_kadokawa_file(filing_group, url):
    extension = Path(url).suffix or ".pdf"
    raw_path = BASE_DIR / "data/raw/jp/filings/kadokawa" / f"kadokawa_{filing_group}_{STAMP}{extension}"
    content = fetch_bytes(url, GENERIC_UA)
    save_bytes(raw_path, content)
    return raw_path, content


def build_manifest():
    firm_rows = read_csv(BASE_DIR / "data/registry/entity_dictionary_firm.csv")
    universe_rows = read_csv(BASE_DIR / "data/registry/firm_universe.csv")

    sector_map = {}
    service_map = {}
    for row in universe_rows:
        sector_map.setdefault(row["firm_std"], row["sector_primary"])
        service_map.setdefault(row["firm_std"], row["service_std_candidate"])

    listed_global = [
        row
        for row in firm_rows
        if row["listed_flag"] == "y" and row["home_country"] != "kr" and row["filing_system"] in {"SEC_EDGAR", "EDINET"}
    ]
    nonlisted_global = [
        row
        for row in firm_rows
        if row["listed_flag"] == "n" and row["home_country"] != "kr"
    ]

    manifest_rows = []
    source_rows = []
    project_rows = []
    log_rows = []

    for firm in listed_global:
        firm_std = firm["firm_std"]
        sector_std = sector_map.get(firm_std, "")
        service_std = service_map.get(firm_std, "")

        if firm["filing_system"] == "SEC_EDGAR":
            cik = SEC_CIK_MAP[firm_std]
            submissions_url, submissions_path, submissions_json = save_sec_submissions(firm_std, cik)
            source_rows.append(
                {
                    "source_file": relative_path(submissions_path),
                    "source_url": submissions_url,
                    "access_date": ACCESS_DATE,
                    "country_std": "us",
                    "firm_std": firm_std,
                    "service_std": service_std,
                    "sector_std": sector_std,
                    "file_format": "json",
                    "collected_by_prompt": PROMPT_NAME,
                    "status": "collected",
                }
            )

            filings = parse_recent_filings(submissions_json)
            annual = choose_first(filings, {"20-F", "10-K", "40-F"})
            interim = choose_periodic_sec(firm_std, filings)
            current = choose_current_sec(filings, interim)
            selection = {
                "annual": annual,
                "interim": interim,
                "current_report": current,
            }

            annual_text_reference = ""
            annual_lines_reference = []
            annual_currency = ""
            annual_accounting = ""
            for group, filing in selection.items():
                if not filing:
                    manifest_rows.append(
                        {
                            "firm_std": firm_std,
                            "firm_name_std": firm["firm_name_std"],
                            "issuer_country_std": firm["home_country"],
                            "source_system_country_std": "us",
                            "sector_std": sector_std,
                            "service_std": service_std,
                            "filing_system": "SEC_EDGAR",
                            "listed_flag": firm["listed_flag"],
                            "filing_group": group,
                            "filing_form": "",
                            "filing_date": "",
                            "fiscal_period": "",
                            "accession_or_doc_id": "",
                            "source_url": "",
                            "raw_path": "",
                            "file_format": "",
                            "currency": "",
                            "accounting_standard": "",
                            "note_location_segment": "not_collected",
                            "note_location_revenue": "not_collected",
                            "note_location_cost": "not_collected",
                            "note_location_tax": "not_collected",
                            "note_location_intangible": "not_collected",
                            "note_location_capex": "not_collected",
                            "collection_status": "required_filing_not_found",
                            "notes": "No matching filing form found in SEC recent submissions.",
                        }
                    )
                    continue

                source_url, raw_path, content = save_sec_filing(firm_std, group, cik, filing)
                time.sleep(0.15)
                extension = raw_path.suffix.lower().lstrip(".")
                source_rows.append(
                    {
                        "source_file": relative_path(raw_path),
                        "source_url": source_url,
                        "access_date": ACCESS_DATE,
                        "country_std": "us",
                        "firm_std": firm_std,
                        "service_std": service_std,
                        "sector_std": sector_std,
                        "file_format": extension,
                        "collected_by_prompt": PROMPT_NAME,
                        "status": "collected",
                    }
                )

                raw_text = content.decode("utf-8", "ignore")
                lines = extract_html_lines(raw_text)
                note_locations = extract_note_locations(lines, sector_std)
                fiscal_period_match = re.search(r"20\d{2}(?:1231|0930|0630|0331)", filing["primary_document"])
                fiscal_period = fiscal_period_match.group(0) if fiscal_period_match else filing["filing_date"][:7]

                if group == "annual":
                    annual_text_reference = clean_html_text(raw_text)
                    annual_lines_reference = lines
                    annual_currency = detect_currency(annual_text_reference, firm_std)
                    annual_accounting = detect_accounting_standard(annual_text_reference, firm_std)

                manifest_rows.append(
                    {
                        "firm_std": firm_std,
                        "firm_name_std": firm["firm_name_std"],
                        "issuer_country_std": firm["home_country"],
                        "source_system_country_std": "us",
                        "sector_std": sector_std,
                        "service_std": service_std,
                        "filing_system": "SEC_EDGAR",
                        "listed_flag": firm["listed_flag"],
                        "filing_group": group,
                        "filing_form": filing["form"],
                        "filing_date": filing["filing_date"],
                        "fiscal_period": fiscal_period,
                        "accession_or_doc_id": filing["accession_number"],
                        "source_url": source_url,
                        "raw_path": relative_path(raw_path),
                        "file_format": extension,
                        "currency": annual_currency if annual_currency else detect_currency(clean_html_text(raw_text), firm_std),
                        "accounting_standard": annual_accounting if annual_accounting else detect_accounting_standard(clean_html_text(raw_text), firm_std),
                        "note_location_segment": note_locations["note_location_segment"],
                        "note_location_revenue": note_locations["note_location_revenue"],
                        "note_location_cost": note_locations["note_location_cost"],
                        "note_location_tax": note_locations["note_location_tax"],
                        "note_location_intangible": note_locations["note_location_intangible"],
                        "note_location_capex": note_locations["note_location_capex"],
                        "collection_status": "collected",
                        "notes": "foreign_private_issuer_proxy_6k" if firm_std in {"spotify", "tencent_music"} and group != "annual" else "",
                    }
                )

            log_rows.append(
                {
                    "firm_std": firm_std,
                    "system": "SEC_EDGAR",
                    "annual_form": annual["form"] if annual else "",
                    "interim_form": interim["form"] if interim else "",
                    "current_form": current["form"] if current else "",
                    "currency": annual_currency,
                    "accounting_standard": annual_accounting,
                }
            )

        elif firm["filing_system"] == "EDINET":
            page1_html, _ = parse_kadokawa_listing(KADOKAWA_LISTING_URLS["page1"])
            page3_html, _ = parse_kadokawa_listing(KADOKAWA_LISTING_URLS["page3"])
            page1_path = BASE_DIR / "data/raw/jp/filings/kadokawa" / f"kadokawa_listing_page1_{STAMP}.html"
            page3_path = BASE_DIR / "data/raw/jp/filings/kadokawa" / f"kadokawa_listing_page3_{STAMP}.html"
            save_bytes(page1_path, page1_html.encode("utf-8"))
            save_bytes(page3_path, page3_html.encode("utf-8"))
            for url, path in [(KADOKAWA_LISTING_URLS["page1"], page1_path), (KADOKAWA_LISTING_URLS["page3"], page3_path)]:
                source_rows.append(
                    {
                        "source_file": relative_path(path),
                        "source_url": url,
                        "access_date": ACCESS_DATE,
                        "country_std": "jp",
                        "firm_std": firm_std,
                        "service_std": service_std,
                        "sector_std": sector_std,
                        "file_format": "html",
                        "collected_by_prompt": PROMPT_NAME,
                        "status": "collected",
                    }
                )

            annual_text_reference = ""
            annual_currency = "JPY"
            annual_accounting = "JAPANESE_GAAP_PROXY"
            for group, info in KADOKAWA_SELECTIONS.items():
                raw_path, _ = save_kadokawa_file(group, info["source_url"])
                source_rows.append(
                    {
                        "source_file": relative_path(raw_path),
                        "source_url": info["source_url"],
                        "access_date": ACCESS_DATE,
                        "country_std": "jp",
                        "firm_std": firm_std,
                        "service_std": service_std,
                        "sector_std": sector_std,
                        "file_format": raw_path.suffix.lower().lstrip("."),
                        "collected_by_prompt": PROMPT_NAME,
                        "status": "collected",
                    }
                )
                lines = extract_pdf_lines(raw_path)
                note_locations = extract_note_locations(lines, sector_std)
                combined_text = "\n".join(lines)
                if group == "annual":
                    annual_text_reference = combined_text
                    annual_currency = detect_currency(combined_text, firm_std)
                    annual_accounting = detect_accounting_standard(combined_text, firm_std)

                manifest_rows.append(
                    {
                        "firm_std": firm_std,
                        "firm_name_std": firm["firm_name_std"],
                        "issuer_country_std": firm["home_country"],
                        "source_system_country_std": "jp",
                        "sector_std": sector_std,
                        "service_std": service_std,
                        "filing_system": "EDINET_fallback_official_ir",
                        "listed_flag": firm["listed_flag"],
                        "filing_group": group,
                        "filing_form": "official_ir_pdf",
                        "filing_date": info["filing_date"],
                        "fiscal_period": info["title"],
                        "accession_or_doc_id": Path(info["source_url"]).parts[-2],
                        "source_url": info["source_url"],
                        "raw_path": relative_path(raw_path),
                        "file_format": raw_path.suffix.lower().lstrip("."),
                        "currency": annual_currency,
                        "accounting_standard": annual_accounting,
                        "note_location_segment": note_locations["note_location_segment"],
                        "note_location_revenue": note_locations["note_location_revenue"],
                        "note_location_cost": note_locations["note_location_cost"],
                        "note_location_tax": note_locations["note_location_tax"],
                        "note_location_intangible": note_locations["note_location_intangible"],
                        "note_location_capex": note_locations["note_location_capex"],
                        "collection_status": "collected",
                        "notes": "Official IR fallback used because EDINET API returned 401 subscription-key error on 2026-03-29.",
                    }
                )

            log_rows.append(
                {
                    "firm_std": firm_std,
                    "system": "EDINET_fallback_official_ir",
                    "annual_form": "official_ir_pdf",
                    "interim_form": "official_ir_pdf",
                    "current_form": "official_ir_pdf",
                    "currency": annual_currency,
                    "accounting_standard": annual_accounting,
                }
            )

    for firm in nonlisted_global:
        manifest_rows.append(
            {
                "firm_std": firm["firm_std"],
                "firm_name_std": firm["firm_name_std"],
                "issuer_country_std": firm["home_country"],
                "source_system_country_std": firm["home_country"],
                "sector_std": sector_map.get(firm["firm_std"], ""),
                "service_std": service_map.get(firm["firm_std"], ""),
                "filing_system": firm["filing_system"],
                "listed_flag": firm["listed_flag"],
                "filing_group": "direct_filing_status",
                "filing_form": "",
                "filing_date": "",
                "fiscal_period": "",
                "accession_or_doc_id": "",
                "source_url": "",
                "raw_path": "",
                "file_format": "",
                "currency": "",
                "accounting_standard": "",
                "note_location_segment": "not_available_without_direct_public_filing",
                "note_location_revenue": "not_available_without_direct_public_filing",
                "note_location_cost": "not_available_without_direct_public_filing",
                "note_location_tax": "not_available_without_direct_public_filing",
                "note_location_intangible": "not_available_without_direct_public_filing",
                "note_location_capex": "not_available_without_direct_public_filing",
                "collection_status": "no_direct_public_filing",
                "notes": "Parent-indirect-public route required for later collection.",
            }
        )

    manifest_fieldnames = [
        "firm_std",
        "firm_name_std",
        "issuer_country_std",
        "source_system_country_std",
        "sector_std",
        "service_std",
        "filing_system",
        "listed_flag",
        "filing_group",
        "filing_form",
        "filing_date",
        "fiscal_period",
        "accession_or_doc_id",
        "source_url",
        "raw_path",
        "file_format",
        "currency",
        "accounting_standard",
        "note_location_segment",
        "note_location_revenue",
        "note_location_cost",
        "note_location_tax",
        "note_location_intangible",
        "note_location_capex",
        "collection_status",
        "notes",
    ]
    write_csv(BASE_DIR / "data/interim/global_filing_manifest.csv", manifest_rows, manifest_fieldnames)

    source_fieldnames = [
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
    append_unique_rows(
        BASE_DIR / "data/registry/source_manifest.csv",
        source_fieldnames,
        source_rows,
        unique_keys=("source_file", "source_url"),
    )

    project_rows.extend(
        [
            {
                "artifact_type": "file",
                "path": "scripts/collect_global_filings.py",
                "owner_step": PROMPT_NAME,
                "source_type": "local_script",
                "source_url": "",
                "access_date": ACCESS_DATE,
                "status": "created",
                "notes": "Reusable SEC and overseas-official filing collection script.",
            },
            {
                "artifact_type": "file",
                "path": "data/interim/global_filing_manifest.csv",
                "owner_step": PROMPT_NAME,
                "source_type": "official_public_multi",
                "source_url": "https://www.sec.gov/ ; https://group.kadokawa.co.jp/",
                "access_date": ACCESS_DATE,
                "status": "created",
                "notes": "Global filing manifest with annual/interim/current report metadata and note-location fields.",
            },
            {
                "artifact_type": "file",
                "path": "logs/global_filings_log.md",
                "owner_step": PROMPT_NAME,
                "source_type": "official_public_multi",
                "source_url": "https://www.sec.gov/ ; https://group.kadokawa.co.jp/",
                "access_date": ACCESS_DATE,
                "status": "created",
                "notes": "Global filing collection log and comparable accounting-item candidate summary.",
            },
        ]
    )
    project_fieldnames = [
        "artifact_type",
        "path",
        "owner_step",
        "source_type",
        "source_url",
        "access_date",
        "status",
        "notes",
    ]
    append_unique_rows(
        BASE_DIR / "data/registry/project_manifest.csv",
        project_fieldnames,
        project_rows,
        unique_keys=("path",),
    )

    collected_count = sum(1 for row in manifest_rows if row["collection_status"] == "collected")
    no_direct_count = sum(1 for row in manifest_rows if row["collection_status"] == "no_direct_public_filing")
    missing_count = sum(1 for row in manifest_rows if row["collection_status"] == "required_filing_not_found")
    domestic_sec = [row for row in log_rows if row["system"] == "SEC_EDGAR" and row["accounting_standard"] == "US_GAAP"]
    foreign_sec = [row for row in log_rows if row["system"] == "SEC_EDGAR" and row["firm_std"] in {"spotify", "tencent_music"}]

    log_lines = [
        "# Global Filings Log",
        "",
        f"- Access date: `{ACCESS_DATE}`",
        f"- Prompt: `{PROMPT_NAME}`",
        f"- Listed global firms covered: `{len(listed_global)}`",
        f"- Nonlisted global firms logged without direct public filings: `{no_direct_count}`",
        f"- Collected manifest rows: `{collected_count}`",
        f"- Missing required filing rows: `{missing_count}`",
        "",
        "## Coverage Summary",
        "",
    ]
    for row in log_rows:
        log_lines.append(
            f"- `{row['firm_std']}`: system `{row['system']}` | annual `{row['annual_form']}` | interim `{row['interim_form']}` | current `{row['current_form']}` | currency `{row['currency']}` | accounting `{row['accounting_standard']}`"
        )

    log_lines.extend(
        [
            "",
            "## Comparable Accounting Item Candidates",
            "",
            "| system_group | annual_form | interim_form | current_form | revenue_candidate | cost_candidate | tax_candidate | intangible_candidate | capex_candidate | notes |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            "| SEC domestic issuers | 10-K | 10-Q | 8-K | revenue / net sales | cost of revenue / operating expenses | income taxes / tax expense | intangible assets / goodwill | capital expenditures / property and equipment | U.S. GAAP issuers such as Warner, WEBTOON, Netflix, Alphabet, Amazon, Cloudflare, Akamai |",
            "| SEC foreign private issuers | 20-F | 6-K quarterly proxy | 6-K current proxy | revenue / net sales | cost of revenue / operating expenses | income taxes | intangible assets / goodwill | capital expenditures / property and equipment | Spotify and Tencent Music use 6-K proxy filings for interim/current coverage |",
            "| Japan official IR fallback | annual earnings results PDF | quarterly earnings results PDF | notice PDF | net sales | expenses / amortization / extraordinary loss | taxes if present in extracted PDF text | goodwill / intangible if present in extracted PDF text | capex / property if present in extracted PDF text | EDINET API returned 401 on March 29, 2026, so KADOKAWA official IR PDFs were retained as the public fallback |",
            "",
            "## Nonlisted Firm Status",
            "",
            "- `kakao_piccoma`: direct public filing unavailable in this prompt; parent-indirect-public route required.",
        ]
    )
    (BASE_DIR / "logs/global_filings_log.md").write_text("\n".join(log_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build_manifest()
