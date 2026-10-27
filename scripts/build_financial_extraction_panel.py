#!/usr/bin/env python3

import csv
import html as html_lib
import re
import ssl
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

from lxml import html


BASE_DIR = Path(__file__).resolve().parents[1]
ACCESS_DATE = date.today().isoformat()
PROMPT_NAME = "Exec Prompt 19"
USER_AGENT = "Mozilla/5.0 research@example.com"
SSL_CONTEXT = ssl._create_unverified_context()

DATA_DIR = BASE_DIR / "data"
INTERIM_DIR = DATA_DIR / "interim"
REGISTRY_DIR = DATA_DIR / "registry"
LOG_DIR = BASE_DIR / "logs"
SCRIPTS_DIR = BASE_DIR / "scripts"

FILING_PANEL_PATH = INTERIM_DIR / "filing_metadata_panel.csv"
KR_FILING_MANIFEST_PATH = INTERIM_DIR / "kr_filing_manifest.csv"
OUTPUT_PANEL_PATH = INTERIM_DIR / "financial_extraction_panel.csv"
OUTPUT_LOG_PATH = LOG_DIR / "financial_extraction_log.md"
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
    "filing_id",
    "firm_std",
    "firm_name_std",
    "country_std",
    "filing_system_country_std",
    "sector_std",
    "service_std",
    "filing_group",
    "filing_form",
    "fiscal_period",
    "fiscal_period_end",
    "period_granularity",
    "metric_name",
    "metric_value_raw",
    "currency",
    "source_page_or_note",
    "extraction_method",
    "metric_value_display",
    "raw_scale",
    "metric_quality",
    "source_file",
    "source_url",
    "notes",
]

PERIODIC_GROUPS = {"annual", "interim", "semiannual", "quarterly"}
SKIP_GROUPS = {"current_report", "major_issues"}

IX_DURATION_TAGS = {
    "revenue",
    "pretax_income",
    "tax_expense",
    "content_investment",
    "network_cloud_cost",
    "interest_expense",
    "capex",
}
IX_INSTANT_TAGS = {"debt", "intangible_assets"}

IX_TAGS = {
    "revenue": [
        "us-gaap:Revenues",
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax",
        "ifrs-full:Revenue",
    ],
    "pretax_income": [
        "us-gaap:IncomeBeforeTaxExpenseBenefit",
        "us-gaap:IncomeBeforeProvisionForIncomeTaxes",
        "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "ifrs-full:ProfitLossBeforeTax",
    ],
    "pretax_income_component_sum": [
        "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
        "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign",
    ],
    "tax_expense": [
        "us-gaap:IncomeTaxExpenseBenefit",
        "ifrs-full:IncomeTaxExpenseContinuingOperations",
    ],
    "interest_expense": [
        "us-gaap:InterestExpense",
        "us-gaap:InterestExpenseDebt",
        "us-gaap:InterestExpenseNonoperating",
        "ifrs-full:FinanceCosts",
        "ifrs-full:AdjustmentsForInterestExpense",
    ],
    "capex": [
        "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
        "us-gaap:PaymentsToAcquireProductiveAssets",
        "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
        "ifrs-full:AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipment",
    ],
    "content_investment": [
        "nflx:AdditionstoStreamingContentAssets",
        "amzn:VideoAndMusicContentExpense",
        "amzn:VideoandMusicContentExpense",
        "us-gaap:PaymentsToAcquireIntangibleAssets",
        "ifrs-full:PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities",
        "ifrs-full:AdditionsOtherThanThroughBusinessCombinationsIntangibleAssetsOtherThanGoodwill",
    ],
    "content_investment_instant_proxy": [
        "amzn:VideoAndMusicContentCapitalizedCosts",
        "amzn:VideoandMusicContentCapitalizedCosts",
    ],
    "network_cloud_cost": [
        "amzn:TechnologyAndInfrastructureExpense",
        "us-gaap:CostOfRevenue",
        "us-gaap:CostOfSales",
        "us-gaap:CostOfGoodsSold",
        "ifrs-full:CostOfSales",
    ],
    "intangible_assets": [
        "us-gaap:FiniteLivedIntangibleAssetsNet",
        "us-gaap:IntangibleAssetsNetExcludingGoodwill",
        "us-gaap:OtherIntangibleAssetsNet",
        "ifrs-full:IntangibleAssetsOtherThanGoodwill",
        "ifrs-full:IntangibleAssetsAndGoodwill",
        "tme:IntangibleAssetsOtherThanGoodwillNetBookAmount",
    ],
    "debt_direct": [
        "us-gaap:LongTermDebt",
        "us-gaap:LongTermDebtAndFinanceLeaseObligations",
        "us-gaap:LongTermDebtAndCapitalLeaseObligations",
        "us-gaap:DebtInstrumentCarryingAmount",
        "ifrs-full:Borrowings",
    ],
    "debt_current": [
        "us-gaap:LongTermDebtCurrent",
        "us-gaap:ShortTermBorrowings",
        "us-gaap:CurrentPortionOfLongTermDebt",
        "us-gaap:ConvertibleDebtCurrent",
        "ifrs-full:CurrentBorrowings",
    ],
    "debt_noncurrent": [
        "us-gaap:LongTermDebtNoncurrent",
        "us-gaap:ConvertibleDebtNoncurrent",
        "ifrs-full:NoncurrentBorrowings",
    ],
}

KR_PATTERNS = {
    "revenue": ["operating revenue", "revenue", "sales"],
    "pretax_income": ["profit (loss) before tax", "profit before tax", "income before tax"],
    "tax_expense": ["tax expense (income)", "income tax expense", "tax expense", "income taxes"],
    "interest_expense": [
        "adjustments for interest expenses",
        "finance costs",
        "finance expense",
        "interest expenses",
        "interest expense",
    ],
    "capex": [
        "payments for acquisition of property, plant and equipment",
        "purchase of property, plant and equipment, classified as investing activities",
        "purchase of property, plant and equipment",
        "purchase of property plant and equipment",
        "acquisition of property, plant and equipment",
        "acquisition of intangible asset and investment property",
        "acquisition of intangible assets",
        "additions other than through business combinations property plant and equipment",
    ],
    "content_investment": [
        "payments for acquisition of intangible assets",
        "purchase of intangible assets, classified as investing activities",
        "purchase of intangible assets",
        "acquisition of intangible asset and investment property",
        "acquisition of intangible assets",
        "additions other than through business combinations intangible assets",
        "acquisition and capital expenditure",
        "contents related expenses",
        "content related expenses",
    ],
    "intangible_assets": [
        "intangible assets and goodwill",
        "intangible assets other than goodwill",
        "intangible assets",
    ],
    "network_cloud_cost": [
        "interconnection charges",
        "international interconnection fees",
        "contact line expense",
        "communication expense",
        "utility expenses",
        "operating expense",
        "network",
        "cost of sales",
        "other operating expense",
        "operating expenses",
    ],
    "debt_sum": [
        "current borrowings",
        "borrowings",
        "long-term borrowings",
        "long term borrowings",
        "bonds issued",
        "debentures",
        "lease liabilities",
        "current lease liabilities",
        "non-current lease liabilities",
        "noncurrent lease liabilities",
        "current portion of long-term borrowings",
        "current portion of long term borrowings",
    ],
}

KR_ROLE_CACHE = {}


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


def normalize_label(value):
    return normalize_space(value).strip().lower()


def parse_number(value):
    text = normalize_space(html_lib.unescape(re.sub(r"<[^>]+>", " ", value or "")))
    if not text or text in {"-", "—", "–", "na", "n/a"}:
        return None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    text = text.replace(",", "").replace(" ", "")
    if text.startswith("-"):
        negative = True
        text = text[1:]
    if text in {"", ".", "--"}:
        return None
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
    return f"{value:.6f}".rstrip("0").rstrip(".")


def parse_iso_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def month_name_to_number(name):
    month_lookup = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }
    return month_lookup.get(name.lower(), 0)


def parse_descriptor(descriptor):
    text = normalize_space(descriptor)
    lowered = text.lower()

    range_match = re.search(r"(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})", text)
    if range_match:
        start = parse_iso_date(range_match.group(1))
        end = parse_iso_date(range_match.group(2))
        if start and end:
            return {
                "kind": "duration",
                "start": start,
                "end": end,
                "duration_days": (end - start).days,
            }

    instant_match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if instant_match:
        instant = parse_iso_date(instant_match.group(1))
        if instant:
            return {"kind": "instant", "instant": instant, "end": instant, "duration_days": 0}

    english_date = re.search(
        r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2}),\s+(\d{4})",
        lowered,
    )
    if english_date:
        month = month_name_to_number(english_date.group(1))
        day = int(english_date.group(2))
        year = int(english_date.group(3))
        end = date(year, month, day)
        duration_days = 0
        if "nine months ended" in lowered:
            duration_days = 270
            return {"kind": "duration", "start": None, "end": end, "duration_days": duration_days}
        if "six months ended" in lowered:
            duration_days = 180
            return {"kind": "duration", "start": None, "end": end, "duration_days": duration_days}
        if "three months ended" in lowered:
            duration_days = 90
            return {"kind": "duration", "start": None, "end": end, "duration_days": duration_days}
        if "year ended" in lowered:
            duration_days = 365
            return {"kind": "duration", "start": None, "end": end, "duration_days": duration_days}
        return {"kind": "instant", "instant": end, "end": end, "duration_days": 0}

    year_match = re.fullmatch(r"(?:note\s*\|\s*)?(\d{4})", lowered)
    if year_match:
        year = int(year_match.group(1))
        end = date(year, 12, 31)
        return {"kind": "duration", "start": None, "end": end, "duration_days": 365}

    if "year ended" in lowered:
        year_tail = re.search(r"(\d{4})", lowered)
        if year_tail:
            year = int(year_tail.group(1))
            end = date(year, 12, 31)
            return {"kind": "duration", "start": None, "end": end, "duration_days": 365}

    return None


def table_to_grid(table_node):
    grid = []
    rowspan_cache = {}
    for tr in table_node.xpath(".//tr"):
        row = []
        col_idx = 0
        while col_idx in rowspan_cache:
            cached = rowspan_cache[col_idx]
            row.append(cached["text"])
            cached["remaining"] -= 1
            if cached["remaining"] == 0:
                del rowspan_cache[col_idx]
            col_idx += 1

        for cell in tr.xpath("./th|./td"):
            text = normalize_space(" ".join(cell.xpath(".//text()")))
            rowspan = int(cell.get("rowspan", "1") or "1")
            colspan = int(cell.get("colspan", "1") or "1")
            for _ in range(colspan):
                row.append(text)
                if rowspan > 1:
                    rowspan_cache[col_idx] = {"text": text, "remaining": rowspan - 1}
                col_idx += 1
                while col_idx in rowspan_cache:
                    cached = rowspan_cache[col_idx]
                    row.append(cached["text"])
                    cached["remaining"] -= 1
                    if cached["remaining"] == 0:
                        del rowspan_cache[col_idx]
                    col_idx += 1
        if any(cell for cell in row):
            grid.append(row)
    return grid


def simple_table_rows(table_node):
    rows = []
    for tr in table_node.xpath(".//tr"):
        cells = [
            normalize_space(" ".join(cell.xpath(".//text()")))
            for cell in tr.xpath("./th|./td")
        ]
        cells = [cell for cell in cells if cell]
        if cells:
            rows.append(cells)
    return rows


def build_column_descriptors(grid, header_rows=3):
    if not grid:
        return []
    top_rows = grid[: min(header_rows, len(grid))]
    max_cols = max(len(row) for row in top_rows)
    padded_rows = []
    for row in top_rows:
        pad = max_cols - len(row)
        padded_rows.append([""] * pad + row)
    descriptors = []
    for col_idx in range(max_cols):
        parts = []
        for row in padded_rows:
            value = normalize_space(row[col_idx])
            if value and value not in parts:
                parts.append(value)
        descriptors.append(" | ".join(parts))
    return descriptors


def choose_best_column(descriptors, fiscal_period_end, instant=False):
    target_end = parse_iso_date(fiscal_period_end)
    if not target_end:
        return None, ""
    best = None
    for col_idx, descriptor in enumerate(descriptors):
        parsed = parse_descriptor(descriptor)
        if not parsed:
            continue
        if instant:
            candidate_end = parsed.get("instant") or parsed.get("end")
            if candidate_end != target_end:
                continue
            score = (1, parsed.get("duration_days", 0))
        else:
            candidate_end = parsed.get("end")
            if candidate_end != target_end:
                continue
            score = (2, parsed.get("duration_days", 0))
        if best is None or score > best[0]:
            best = (score, col_idx, descriptor)
    if best:
        return best[1], best[2]
    return None, ""


def match_label(label, patterns):
    lowered = normalize_label(label)
    return any(pattern in lowered for pattern in patterns)


def extract_from_grid(grid, fiscal_period_end, row_patterns, instant=False, allow_sum=False):
    descriptors = build_column_descriptors(grid)
    col_idx, descriptor = choose_best_column(descriptors, fiscal_period_end, instant=instant)
    if col_idx is None:
        return None

    matches = []
    for row in grid[1:]:
        if not row:
            continue
        label = normalize_space(row[0])
        if not label or not match_label(label, row_patterns):
            continue
        if col_idx >= len(row):
            continue
        value = parse_number(row[col_idx])
        if value is None:
            continue
        matches.append((label, value, normalize_space(row[col_idx])))

    if not matches:
        return None

    if allow_sum:
        total = sum(item[1] for item in matches)
        return {
            "value": total,
            "display": " + ".join(item[2] for item in matches),
            "source_label": " + ".join(item[0] for item in matches),
            "descriptor": descriptor,
        }

    label, value, display = matches[0]
    return {"value": value, "display": display, "source_label": label, "descriptor": descriptor}


def create_row(meta, metric_name, value, source_page_or_note, extraction_method, display_value="", raw_scale="", metric_quality="", notes=""):
    return {
        "filing_id": meta["filing_id"],
        "firm_std": meta["firm_std"],
        "firm_name_std": meta["firm_name_std"],
        "country_std": meta["country_std"],
        "filing_system_country_std": meta["filing_system_country_std"],
        "sector_std": meta["sector_std"],
        "service_std": meta["service_std"],
        "filing_group": meta["filing_group"],
        "filing_form": meta["filing_form"],
        "fiscal_period": meta["fiscal_period"],
        "fiscal_period_end": meta["fiscal_period_end"],
        "period_granularity": meta["period_granularity"],
        "metric_name": metric_name,
        "metric_value_raw": serialize_number(value),
        "currency": meta["currency"],
        "source_page_or_note": source_page_or_note,
        "extraction_method": extraction_method,
        "metric_value_display": display_value,
        "raw_scale": raw_scale,
        "metric_quality": metric_quality,
        "source_file": meta["source_file"],
        "source_url": meta["source_url"],
        "notes": notes,
    }


def fetch_url(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=45, context=SSL_CONTEXT) as response:
        return response.read().decode("utf-8", "ignore")


def parse_kr_role_map(source_file):
    doc = html.fromstring((BASE_DIR / source_file).read_bytes())
    role_entries = []
    for anchor in doc.xpath("//a[@onclick[contains(., 'viewDoc')]]"):
        onclick = anchor.get("onclick", "")
        match = re.search(r"viewDoc\('(?P<extseq>\d+)',\s*'[^']*',\s*'en',\s*'(?P<roleid>D\d+)'\)", onclick)
        if not match:
            continue
        label = normalize_space(" ".join(anchor.xpath(".//text()")))
        if not label:
            continue
        role_entries.append(
            {
                "label": label,
                "label_norm": normalize_label(label),
                "extseq": match.group("extseq"),
                "roleid": match.group("roleid"),
            }
        )
    return role_entries


def find_kr_role(role_entries, exact_label=None, contains=None):
    exact_norm = normalize_label(exact_label) if exact_label else ""
    if exact_norm and not exact_norm.startswith("not_"):
        for entry in role_entries:
            if entry["label_norm"] == exact_norm:
                return entry
    for keyword in contains or []:
        keyword_norm = normalize_label(keyword)
        for entry in role_entries:
            if keyword_norm in entry["label_norm"]:
                return entry
    return None


def find_kr_role_prefer_contains(role_entries, contains=None, fallback_exact_label=None):
    preferred = find_kr_role(role_entries, exact_label=None, contains=contains)
    if preferred:
        return preferred
    return find_kr_role(role_entries, exact_label=fallback_exact_label, contains=contains)


def get_kr_role_page(role_entry):
    if not role_entry:
        return "", ""
    cache_key = (role_entry["extseq"], role_entry["roleid"])
    if cache_key not in KR_ROLE_CACHE:
        url = (
            "https://engopendart.fss.or.kr/xbrl/viewer/view.do"
            f"?xbrlExtSeq={role_entry['extseq']}&roleId={role_entry['roleid']}&lang=en"
        )
        KR_ROLE_CACHE[cache_key] = (url, fetch_url(url))
    return KR_ROLE_CACHE[cache_key]


def extract_kr_metrics(meta, kr_manifest_lookup):
    manifest_row = kr_manifest_lookup.get(meta["source_file"])
    if not manifest_row:
        return [], [{"reason": "kr_manifest_missing", "detail": meta["source_file"]}]

    role_entries = parse_kr_role_map(meta["source_file"])
    results = []
    issues = []

    role_specs = {
        "statement": find_kr_role_prefer_contains(
            role_entries,
            contains=[
                "income statement, by nature of expense",
                "statement of comprehensive income",
            ],
            fallback_exact_label=manifest_row.get("note_location_pretax_profit", ""),
        ),
        "cashflow": find_kr_role(role_entries, contains=["statement of cash flows"]),
        "position": find_kr_role(role_entries, contains=["statement of financial position"]),
        "intangible_note": find_kr_role(
            role_entries,
            exact_label=manifest_row.get("note_location_intangible_assets", ""),
            contains=["intangible assets"],
        ),
        "tax_note": find_kr_role(
            role_entries,
            exact_label=manifest_row.get("note_location_income_tax_expense", ""),
            contains=["income tax expense", "tax expense", "income taxes"],
        ),
        "network_note": find_kr_role(
            role_entries,
            exact_label=manifest_row.get("note_location_network_cost", ""),
            contains=["operating expenses", "other operating expenses"],
        ),
        "content_note": find_kr_role(
            role_entries,
            exact_label=manifest_row.get("note_location_content_investment", ""),
            contains=["revenue and cost of sales", "products and services", "operating expenses", "other operating expenses"],
        ),
    }

    fetched_pages = {}
    for key, role_entry in role_specs.items():
        if role_entry:
            fetched_pages[key] = get_kr_role_page(role_entry)

    def extract_metric(metric_name, preferred_sources, row_patterns, instant=False, allow_sum=False, quality="direct_kr_role"):
        for source_key in preferred_sources:
            url_text = fetched_pages.get(source_key)
            if not url_text:
                continue
            url, role_html = url_text
            doc = html.fromstring(role_html.encode("utf-8"))
            for table_node in doc.xpath("//table[contains(@class, 'fact-table')]"):
                extracted = extract_from_grid(
                    table_to_grid(table_node),
                    meta["fiscal_period_end"],
                    row_patterns,
                    instant=instant,
                    allow_sum=allow_sum,
                )
                if extracted:
                    source_label = role_specs[source_key]["label"]
                    results.append(
                        create_row(
                            meta,
                            metric_name,
                            extracted["value"],
                            f"{source_label} | {extracted['source_label']} | {extracted['descriptor']}",
                            "kr_role_table_label_match" if not allow_sum else "kr_role_table_label_sum",
                            display_value=extracted["display"],
                            raw_scale="none",
                            metric_quality=quality,
                            notes=url,
                        )
                    )
                    return True
        issues.append({"reason": f"{metric_name}_missing", "detail": meta["filing_id"]})
        return False

    extract_metric("revenue", ["statement", "content_note"], KR_PATTERNS["revenue"])
    extract_metric("pretax_income", ["statement"], KR_PATTERNS["pretax_income"])
    extract_metric("tax_expense", ["tax_note", "statement"], KR_PATTERNS["tax_expense"])
    extract_metric("interest_expense", ["cashflow", "statement"], KR_PATTERNS["interest_expense"])
    extract_metric("capex", ["cashflow"], KR_PATTERNS["capex"])
    extract_metric(
        "content_investment",
        ["cashflow", "content_note", "intangible_note"],
        KR_PATTERNS["content_investment"],
        quality="proxy_purchase_of_intangibles",
    )
    extract_metric(
        "intangible_assets",
        ["intangible_note", "position"],
        KR_PATTERNS["intangible_assets"],
        instant=True,
    )
    extract_metric(
        "debt",
        ["position"],
        KR_PATTERNS["debt_sum"],
        instant=True,
        allow_sum=True,
    )
    extract_metric(
        "network_cloud_cost",
        ["network_note", "content_note", "statement"],
        KR_PATTERNS["network_cloud_cost"],
        quality="proxy_network_cost_bucket",
    )

    return results, issues


def parse_ix_contexts(text):
    contexts = {}
    for block in re.finditer(r"<(?:xbrli:)?context\b[^>]*id=\"([^\"]+)\"[^>]*>(.*?)</(?:xbrli:)?context>", text, re.S):
        context_id = block.group(1)
        body = block.group(2)
        start_match = re.search(r"<(?:xbrli:)?startDate>([^<]+)</(?:xbrli:)?startDate>", body)
        end_match = re.search(r"<(?:xbrli:)?endDate>([^<]+)</(?:xbrli:)?endDate>", body)
        instant_match = re.search(r"<(?:xbrli:)?instant>([^<]+)</(?:xbrli:)?instant>", body)
        has_segment = bool(
            re.search(r"<(?:xbrli:)?segment>|<(?:xbrldi:)?explicitMember|<(?:xbrldi:)?typedMember", body)
        )
        contexts[context_id] = {
            "start": start_match.group(1) if start_match else "",
            "end": end_match.group(1) if end_match else "",
            "instant": instant_match.group(1) if instant_match else "",
            "has_segment": has_segment,
        }
    return contexts


def parse_ix_facts(text):
    facts = []
    for match in re.finditer(r"<ix:nonFraction\b([^>]*)>(.*?)</ix:nonFraction>", text, re.S):
        attr_text = match.group(1)
        value_text = match.group(2)
        attrs = dict(re.findall(r"([A-Za-z_:][A-Za-z0-9_:.-]*)=\"([^\"]*)\"", attr_text))
        tag_name = attrs.get("name", "")
        context_ref = attrs.get("contextRef", "")
        if not tag_name or not context_ref:
            continue
        display_text = normalize_space(html_lib.unescape(re.sub(r"<[^>]+>", " ", value_text)))
        display_value = parse_number(display_text)
        if display_value is None:
            continue
        sign = attrs.get("sign", "")
        scale = int(attrs.get("scale", "0") or "0")
        if sign == "-" and display_value > 0:
            display_value *= -1
        actual_value = display_value * (10 ** scale)
        facts.append(
            {
                "tag": tag_name,
                "context_ref": context_ref,
                "display_text": display_text,
                "display_value": display_value,
                "actual_value": actual_value,
                "scale": scale,
            }
        )
    return facts


def select_ix_fact(facts_by_tag, contexts, tags, fiscal_period_end, instant=False):
    target_end = fiscal_period_end
    candidates = []
    for tag in tags:
        for fact in facts_by_tag.get(tag, []):
            context = contexts.get(fact["context_ref"])
            if not context or context["has_segment"]:
                continue
            if instant:
                candidate_end = context["instant"] or context["end"]
                if target_end and candidate_end != target_end:
                    continue
                duration = 0
            else:
                if not context["end"]:
                    continue
                if target_end and context["end"] != target_end:
                    continue
                if context["start"] and context["end"]:
                    start_date = parse_iso_date(context["start"])
                    end_date = parse_iso_date(context["end"])
                    duration = (end_date - start_date).days if start_date and end_date else 0
                else:
                    duration = 0
            candidates.append((duration, fact, context))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], abs(item[1]["actual_value"])), reverse=True)
    duration, fact, context = candidates[0]
    return {
        "fact": fact,
        "context": context,
        "duration": duration,
    }


def extract_ixbrl_metrics(meta, text):
    contexts = parse_ix_contexts(text)
    facts = parse_ix_facts(text)
    if not facts:
        return [], [{"reason": "no_ixbrl_facts", "detail": meta["filing_id"]}]

    facts_by_tag = defaultdict(list)
    for fact in facts:
        facts_by_tag[fact["tag"]].append(fact)

    results = []
    issues = []

    def add_from_selected(metric_name, selected, method, quality, notes=""):
        if not selected:
            issues.append({"reason": f"{metric_name}_missing", "detail": meta["filing_id"]})
            return
        fact = selected["fact"]
        context = selected["context"]
        period_label = context.get("instant") or context.get("end")
        descriptor = f"{fact['tag']} | context:{fact['context_ref']} | {period_label}"
        results.append(
            create_row(
                meta,
                metric_name,
                fact["actual_value"],
                descriptor,
                method,
                display_value=fact["display_text"],
                raw_scale=str(fact["scale"]),
                metric_quality=quality,
                notes=notes,
            )
        )

    add_from_selected(
        "revenue",
        select_ix_fact(facts_by_tag, contexts, IX_TAGS["revenue"], meta["fiscal_period_end"], instant=False),
        "sec_ixbrl_concept_context",
        "direct_ixbrl",
    )

    pretax_selected = select_ix_fact(
        facts_by_tag,
        contexts,
        IX_TAGS["pretax_income"],
        meta["fiscal_period_end"],
        instant=False,
    )
    if not pretax_selected:
        component_contexts = []
        component_values = []
        for tag in IX_TAGS["pretax_income_component_sum"]:
            selected = select_ix_fact(facts_by_tag, contexts, [tag], meta["fiscal_period_end"], instant=False)
            if selected:
                component_contexts.append(selected["fact"]["tag"])
                component_values.append(selected["fact"]["actual_value"])
        if component_values:
            results.append(
                create_row(
                    meta,
                    "pretax_income",
                    sum(component_values),
                    " + ".join(component_contexts),
                    "sec_ixbrl_component_sum",
                    display_value=" + ".join(serialize_number(value) for value in component_values),
                    raw_scale="mixed",
                    metric_quality="derived_ixbrl_component_sum",
                )
            )
        else:
            issues.append({"reason": "pretax_income_missing", "detail": meta["filing_id"]})
    else:
        add_from_selected(
            "pretax_income",
            pretax_selected,
            "sec_ixbrl_concept_context",
            "direct_ixbrl",
        )

    add_from_selected(
        "tax_expense",
        select_ix_fact(facts_by_tag, contexts, IX_TAGS["tax_expense"], meta["fiscal_period_end"], instant=False),
        "sec_ixbrl_concept_context",
        "direct_ixbrl",
    )
    add_from_selected(
        "interest_expense",
        select_ix_fact(
            facts_by_tag,
            contexts,
            IX_TAGS["interest_expense"],
            meta["fiscal_period_end"],
            instant=False,
        ),
        "sec_ixbrl_concept_context",
        "direct_ixbrl_or_proxy",
    )
    add_from_selected(
        "capex",
        select_ix_fact(facts_by_tag, contexts, IX_TAGS["capex"], meta["fiscal_period_end"], instant=False),
        "sec_ixbrl_concept_context",
        "direct_ixbrl_or_proxy",
    )
    content_selected = select_ix_fact(
        facts_by_tag,
        contexts,
        IX_TAGS["content_investment"],
        meta["fiscal_period_end"],
        instant=False,
    )
    content_method = "sec_ixbrl_concept_context"
    content_quality = "direct_nflx_or_proxy_intangibles"
    content_notes = ""
    if not content_selected and meta.get("firm_std") == "amazon":
        content_selected = select_ix_fact(
            facts_by_tag,
            contexts,
            IX_TAGS["content_investment_instant_proxy"],
            meta["fiscal_period_end"],
            instant=True,
        )
        if content_selected:
            content_quality = "proxy_amzn_capitalized_content_stock"
            content_notes = "Amazon video/music capitalized content stock used as content investment proxy when duration content-spend fact is unavailable."
    add_from_selected(
        "content_investment",
        content_selected,
        content_method,
        content_quality,
        notes=content_notes,
    )
    add_from_selected(
        "network_cloud_cost",
        select_ix_fact(
            facts_by_tag,
            contexts,
            IX_TAGS["network_cloud_cost"],
            meta["fiscal_period_end"],
            instant=False,
        ),
        "sec_ixbrl_concept_context",
        "proxy_cost_of_revenue",
    )
    add_from_selected(
        "intangible_assets",
        select_ix_fact(
            facts_by_tag,
            contexts,
            IX_TAGS["intangible_assets"],
            meta["fiscal_period_end"],
            instant=True,
        ),
        "sec_ixbrl_concept_context",
        "direct_ixbrl_or_proxy",
    )

    debt_selected = select_ix_fact(
        facts_by_tag,
        contexts,
        IX_TAGS["debt_direct"],
        meta["fiscal_period_end"],
        instant=True,
    )
    if debt_selected:
        add_from_selected("debt", debt_selected, "sec_ixbrl_concept_context", "direct_ixbrl")
    else:
        current_selected = select_ix_fact(
            facts_by_tag,
            contexts,
            IX_TAGS["debt_current"],
            meta["fiscal_period_end"],
            instant=True,
        )
        noncurrent_selected = select_ix_fact(
            facts_by_tag,
            contexts,
            IX_TAGS["debt_noncurrent"],
            meta["fiscal_period_end"],
            instant=True,
        )
        if current_selected or noncurrent_selected:
            component_rows = []
            total = 0.0
            for selected in [current_selected, noncurrent_selected]:
                if not selected:
                    continue
                fact = selected["fact"]
                total += fact["actual_value"]
                component_rows.append(fact["tag"])
            results.append(
                create_row(
                    meta,
                    "debt",
                    total,
                    " + ".join(component_rows),
                    "sec_ixbrl_component_sum",
                    display_value=" + ".join(component_rows),
                    raw_scale="mixed",
                    metric_quality="derived_ixbrl_component_sum",
                )
            )
        else:
            issues.append({"reason": "debt_missing", "detail": meta["filing_id"]})

    return results, issues


def find_table_with_rows(tables, required_labels):
    required_norm = [normalize_label(label) for label in required_labels]
    for table_index, grid in tables:
        label_set = {normalize_label(row[0]) for row in grid if row}
        if all(
            any(required in label for label in label_set)
            for required in required_norm
        ):
            return table_index, grid
    return None, None


def row_index_by_substrings(grid, substrings):
    target_patterns = [pattern.lower() for pattern in substrings]
    for idx, row in enumerate(grid):
        if not row:
            continue
        label = normalize_label(row[0])
        if all(pattern in label for pattern in target_patterns):
            return idx
    return None


def spotify_select_first_total_column(rows):
    header_row = rows[0] if rows else []
    for idx, value in enumerate(header_row):
        if normalize_label(value) == "total":
            return idx
    return None


def spotify_find_table(tables, keyword_sets, any_of=None):
    any_of = any_of or []
    for table_index, rows in tables:
        joined = " | ".join(" / ".join(row) for row in rows).lower()
        if not all(keyword.lower() in joined for keyword in keyword_sets):
            continue
        if any_of and not any(option.lower() in joined for option in any_of):
            continue
        return table_index, rows
    return None, None


def spotify_find_row(rows, keywords):
    for row in rows:
        if not row:
            continue
        label = normalize_label(row[0])
        if any(keyword in label for keyword in keywords):
            return row
    return None


def spotify_income_slot(rows, filing_group, fiscal_period_end):
    target_year = fiscal_period_end[:4]
    if filing_group == "annual":
        header_years = rows[0][1:]
        if target_year in header_years:
            return {"slot": header_years.index(target_year), "numeric_slots": len(header_years)}
        return None

    if len(rows) < 2:
        return None
    group_row = rows[0]
    year_row = rows[1]
    if not year_row or normalize_label(year_row[0]) != "note":
        return None
    year_values = year_row[1:]
    if not group_row:
        return None
    repeat = len(year_values) // len(group_row) if group_row else 0
    if repeat <= 0:
        return None
    grouped_headers = []
    for group_label in group_row:
        grouped_headers.extend([group_label] * repeat)
    for offset, (year_value, group_label) in enumerate(zip(year_values, grouped_headers)):
        if year_value == target_year and "nine months ended" in group_label.lower():
            return {"slot": offset, "numeric_slots": len(year_values)}
    for offset, year_value in enumerate(year_values):
        if year_value == target_year:
            return {"slot": offset, "numeric_slots": len(year_values)}
    return None


def spotify_balance_slot(rows, filing_group, fiscal_period_end):
    target_year = fiscal_period_end[:4]
    header = rows[0][1:] if rows else []
    if filing_group == "annual":
        if target_year in header:
            return {"slot": header.index(target_year), "numeric_slots": len(header)}
        return None
    for idx, value in enumerate(header):
        if fiscal_period_end in value or target_year in value:
            return {"slot": idx, "numeric_slots": len(header)}
    return None


def spotify_extract_metric_from_rows(rows, row_keywords, slot_info):
    if slot_info is None:
        return None
    row = spotify_find_row(rows, row_keywords)
    if not row:
        return None
    if isinstance(slot_info, int):
        value_idx = slot_info
    else:
        note_shift = 1 if len(row) == slot_info["numeric_slots"] + 2 else 0
        value_idx = 1 + slot_info["slot"] + note_shift
    if value_idx >= len(row):
        return None
    display = normalize_space(row[value_idx])
    value = parse_number(display)
    if value is None:
        return None
    return {"value": value, "display": display, "label": row[0], "value_idx": value_idx}


def spotify_extract_intangible_investment(rows):
    total_col_idx = spotify_select_first_total_column(rows)
    if total_col_idx is None:
        return None
    value_idx = total_col_idx + 1
    total_value = 0.0
    displays = []
    found_any = False
    for row_keyword in ["additions", "acquisitions"]:
        row = spotify_find_row(rows, [row_keyword])
        if not row or value_idx >= len(row):
            continue
        display = normalize_space(row[value_idx])
        value = parse_number(display)
        if value is None:
            continue
        total_value += value
        displays.append(display)
        found_any = True
    if not found_any:
        return None
    return {"value": total_value, "display": " + ".join(displays)}


def extract_spotify_metrics(meta, source_bytes):
    doc = html.fromstring(source_bytes)
    full_text = normalize_space(" ".join(doc.xpath("//text()"))).lower()
    unit_multiplier = (
        1_000_000
        if any(token in full_text for token in ["millions of euros", "in € millions", "(in € millions)"])
        else 1
    )

    tables = []
    for idx, table_node in enumerate(doc.xpath("//table")):
        rows = simple_table_rows(table_node)
        if rows:
            tables.append((idx, rows))

    results = []
    issues = []

    income_table_idx, income_rows = spotify_find_table(
        tables,
        ["revenue", "finance costs"],
        any_of=["income before tax", "income/(loss) before tax"],
    )
    if income_rows:
        slot_info = spotify_income_slot(income_rows, meta["filing_group"], meta["fiscal_period_end"])
        metric_specs = {
            "revenue": (["revenue"], "spotify_html_table_fallback_direct", "direct_html_table"),
            "pretax_income": (["income before tax", "income/(loss) before tax"], "spotify_html_table_fallback_direct", "direct_html_table"),
            "tax_expense": (["income tax expense", "income tax benefit"], "spotify_html_table_fallback_direct", "direct_html_table"),
            "interest_expense": (["finance costs"], "spotify_html_table_fallback_direct", "direct_html_table"),
            "network_cloud_cost": (["cost of revenue"], "spotify_html_table_fallback_proxy", "proxy_cost_of_revenue"),
        }
        for metric_name, (row_keys, method, quality) in metric_specs.items():
            extracted = spotify_extract_metric_from_rows(income_rows, row_keys, slot_info)
            if extracted:
                results.append(
                    create_row(
                        meta,
                        metric_name,
                        extracted["value"] * unit_multiplier,
                        f"table:{income_table_idx} | {extracted['label']} | value_index:{extracted['value_idx']}",
                        method,
                        display_value=extracted["display"],
                        raw_scale="table_units_1e6",
                        metric_quality=quality,
                    )
                )
            else:
                issues.append({"reason": f"{metric_name}_missing", "detail": meta["filing_id"]})
    else:
        issues.append({"reason": "spotify_income_table_missing", "detail": meta["filing_id"]})

    balance_table_idx, balance_rows = spotify_find_table(tables, ["intangible assets", "assets", "non-current assets"])
    if balance_rows:
        slot_info = spotify_balance_slot(balance_rows, meta["filing_group"], meta["fiscal_period_end"])
        extracted = spotify_extract_metric_from_rows(balance_rows, ["intangible assets"], slot_info)
        if extracted:
            results.append(
                create_row(
                    meta,
                    "intangible_assets",
                    extracted["value"] * unit_multiplier,
                    f"table:{balance_table_idx} | {extracted['label']} | value_index:{extracted['value_idx']}",
                    "spotify_html_table_fallback_direct",
                    display_value=extracted["display"],
                    raw_scale="table_units_1e6",
                    metric_quality="direct_html_table",
                )
            )
        else:
            issues.append({"reason": "intangible_assets_missing", "detail": meta["filing_id"]})
    else:
        issues.append({"reason": "spotify_balance_table_missing", "detail": meta["filing_id"]})

    property_table_idx, property_rows = spotify_find_table(tables, ["property and equipment", "additions"])
    if property_rows:
        total_col_idx = spotify_select_first_total_column(property_rows)
        value_idx = total_col_idx + 1 if total_col_idx is not None else None
        extracted = spotify_extract_metric_from_rows(property_rows, ["additions"], value_idx)
        if extracted:
            results.append(
                create_row(
                    meta,
                    "capex",
                    extracted["value"] * unit_multiplier,
                    f"table:{property_table_idx} | {extracted['label']} | value_index:{value_idx}",
                    "spotify_html_table_fallback_proxy",
                    display_value=extracted["display"],
                    raw_scale="table_units_1e6",
                    metric_quality="proxy_property_additions",
                )
            )
        else:
            issues.append({"reason": "capex_missing", "detail": meta["filing_id"]})
    else:
        issues.append({"reason": "spotify_property_table_missing", "detail": meta["filing_id"]})

    intangible_table_idx, intangible_rows = spotify_find_table(
        tables,
        ["internal development costs", "acquired intangible assets", "additions"],
    )
    if intangible_rows:
        extracted = spotify_extract_intangible_investment(intangible_rows)
        if extracted:
            results.append(
                create_row(
                    meta,
                    "content_investment",
                    extracted["value"] * unit_multiplier,
                    f"table:{intangible_table_idx} | additions+acquisitions | first_total_column",
                    "spotify_html_table_fallback_proxy",
                    display_value=extracted["display"],
                    raw_scale="table_units_1e6",
                    metric_quality="proxy_intangible_additions",
                )
            )
        else:
            issues.append({"reason": "content_investment_missing", "detail": meta["filing_id"]})
    else:
        issues.append({"reason": "spotify_intangible_table_missing", "detail": meta["filing_id"]})

    return results, issues


def infer_extraction_mode(meta, source_bytes):
    if meta["country_std"] == "kr":
        return "kr_xbrl"
    if meta["firm_std"] == "spotify":
        return "spotify_html"
    if meta["firm_std"] == "kadokawa":
        return "pdf_manual"
    source_text = source_bytes.decode("utf-8", "ignore")
    if "<ix:nonFraction" in source_text:
        return "ixbrl"
    return "unstructured_html"


def load_kr_manifest_lookup():
    lookup = {}
    for row in read_csv(KR_FILING_MANIFEST_PATH):
        raw_xbrl_path = normalize_space(row.get("raw_xbrl_path", ""))
        if raw_xbrl_path:
            lookup[raw_xbrl_path] = row
    return lookup


def build_output():
    filing_rows = read_csv(FILING_PANEL_PATH)
    kr_manifest_lookup = load_kr_manifest_lookup()
    extraction_rows = []
    skipped = []
    issue_counter = Counter()
    extracted_filing_counts = Counter()

    for meta in filing_rows:
        filing_group = meta["filing_group"]
        if filing_group in SKIP_GROUPS:
            skipped.append(
                {
                    "filing_id": meta["filing_id"],
                    "firm_std": meta["firm_std"],
                    "filing_group": filing_group,
                    "reason": "event_or_major_issue_skipped",
                }
            )
            continue
        if filing_group not in PERIODIC_GROUPS:
            skipped.append(
                {
                    "filing_id": meta["filing_id"],
                    "firm_std": meta["firm_std"],
                    "filing_group": filing_group,
                    "reason": "non_periodic_group",
                }
            )
            continue

        source_path = BASE_DIR / meta["source_file"]
        if not source_path.exists():
            skipped.append(
                {
                    "filing_id": meta["filing_id"],
                    "firm_std": meta["firm_std"],
                    "filing_group": filing_group,
                    "reason": f"missing_source_file:{meta['source_file']}",
                }
            )
            continue

        source_bytes = source_path.read_bytes()
        mode = infer_extraction_mode(meta, source_bytes)

        if mode == "kr_xbrl":
            rows, issues = extract_kr_metrics(meta, kr_manifest_lookup)
        elif mode == "ixbrl":
            rows, issues = extract_ixbrl_metrics(meta, source_bytes.decode("utf-8", "ignore"))
        elif mode == "spotify_html":
            rows, issues = extract_spotify_metrics(meta, source_bytes)
        elif mode == "pdf_manual":
            rows = []
            issues = [{"reason": "pdf_manual_mapping_needed", "detail": meta["filing_id"]}]
        else:
            rows = []
            issues = [{"reason": "unstructured_html_manual_mapping_needed", "detail": meta["filing_id"]}]

        if rows:
            extraction_rows.extend(rows)
            extracted_filing_counts[meta["firm_std"]] += 1
        else:
            skipped.append(
                {
                    "filing_id": meta["filing_id"],
                    "firm_std": meta["firm_std"],
                    "filing_group": filing_group,
                    "reason": issues[0]["reason"] if issues else "no_rows_extracted",
                }
            )
        for issue in issues:
            issue_counter[issue["reason"]] += 1

    extraction_rows.sort(
        key=lambda row: (
            row["firm_std"],
            row["fiscal_period"],
            row["metric_name"],
        )
    )
    write_csv(OUTPUT_PANEL_PATH, extraction_rows, OUTPUT_FIELDS)
    build_log(extraction_rows, skipped, issue_counter, extracted_filing_counts)
    update_project_manifest()
    update_workflow_log(extraction_rows, skipped, issue_counter)


def build_log(extraction_rows, skipped, issue_counter, extracted_filing_counts):
    metric_counts = Counter(row["metric_name"] for row in extraction_rows)
    method_counts = Counter(row["extraction_method"] for row in extraction_rows)
    firm_counts = Counter(row["firm_std"] for row in extraction_rows)
    filing_metric_counts = Counter((row["filing_id"], row["metric_name"]) for row in extraction_rows)
    filing_coverage = Counter()
    for filing_id, _metric_name in filing_metric_counts:
        filing_coverage[filing_id] += 1

    log_lines = [
        "# Financial Extraction Log",
        "",
        f"- Access date: `{ACCESS_DATE}`",
        f"- Prompt: `{PROMPT_NAME}`",
        f"- Output rows: `{len(extraction_rows)}`",
        f"- Unique filings with at least one extracted metric: `{len(filing_coverage)}`",
        f"- Skipped filings: `{len(skipped)}`",
        "",
        "## Metric Coverage",
        "",
    ]

    for metric_name in [
        "revenue",
        "pretax_income",
        "tax_expense",
        "content_investment",
        "network_cloud_cost",
        "interest_expense",
        "debt",
        "intangible_assets",
        "capex",
    ]:
        log_lines.append(f"- `{metric_name}`: `{metric_counts.get(metric_name, 0)}` rows")

    log_lines.extend(["", "## Extraction Method Counts", ""])
    for method_name, count in sorted(method_counts.items()):
        log_lines.append(f"- `{method_name}`: `{count}` rows")

    log_lines.extend(["", "## Firm Coverage", ""])
    for firm_std in sorted(firm_counts):
        log_lines.append(
            f"- `{firm_std}`: `{firm_counts[firm_std]}` rows across `{extracted_filing_counts.get(firm_std, 0)}` filings"
        )

    log_lines.extend(["", "## Major Skip Reasons", ""])
    for reason, count in issue_counter.most_common():
        log_lines.append(f"- `{reason}`: `{count}`")

    log_lines.extend(["", "## Explicitly Skipped Filings", ""])
    for row in skipped:
        log_lines.append(
            f"- `{row['firm_std']}` | `{row['filing_id']}` | `{row['filing_group']}` | `{row['reason']}`"
        )

    log_lines.extend(
        [
            "",
            "## Implementation Notes",
            "",
            "- 한국 공시는 `OpenDART` XBRL tree에서 role label을 읽은 뒤 role page HTML을 즉시 조회하여 표 기반으로 추출함.",
            "- 미국/해외 공시는 inline XBRL fact와 context를 결합해 기간말/기간누적 기준으로 선택했고 `scale`을 반영한 실제 금액을 `metric_value_raw`에 저장함.",
            "- `Spotify`는 inline XBRL fact 대신 HTML 표 fallback을 사용했으며 문서 내 `millions of Euros` 단위를 반영해 값에 `1,000,000`을 곱함.",
            "- `network_cloud_cost`는 직접 계정이 부족한 경우 `Cost of revenue` 또는 통신사 운영비 note의 네트워크 관련 항목을 프록시로 사용함.",
            "- `content_investment`는 `Netflix`에서는 streaming content additions를, 그 외에는 intangible asset purchase/addition 계열을 프록시로 사용함.",
            "- `KADOKAWA` PDF와 `Tencent Music` 6-K interim은 이번 단계에서 자동 매핑 신뢰도가 낮아 `manual_mapping_needed`로 보류함.",
        ]
    )

    OUTPUT_LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")


def update_project_manifest():
    new_rows = [
        {
            "artifact_type": "script",
            "path": "scripts/build_financial_extraction_panel.py",
            "owner_step": PROMPT_NAME,
            "source_type": "local_code",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Extracts comparable financial metrics from Korean XBRL, SEC inline XBRL, and Spotify HTML tables.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/interim/financial_extraction_panel.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_financial_panel",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Tidy filing-metric extraction panel with raw values, currencies, source notes, and extraction methods.",
        },
        {
            "artifact_type": "log",
            "path": "logs/financial_extraction_log.md",
            "owner_step": PROMPT_NAME,
            "source_type": "local_log",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Coverage and skip log for filing-level financial extraction.",
        },
    ]
    append_unique_rows(PROJECT_MANIFEST_PATH, PROJECT_MANIFEST_FIELDS, new_rows, ["path"])


def update_workflow_log(extraction_rows, skipped, issue_counter):
    revenue_rows = sum(1 for row in extraction_rows if row["metric_name"] == "revenue")
    debt_rows = sum(1 for row in extraction_rows if row["metric_name"] == "debt")
    bullets = [
        f"`data/interim/financial_extraction_panel.csv` 생성, 총 `{len(extraction_rows)}`개 재무 metric row를 filing-기준 tidy 형식으로 정리",
        f"`revenue` `{revenue_rows}`건, `debt` `{debt_rows}`건 등 필수 항목을 한국 XBRL, SEC iXBRL, Spotify HTML fallback에서 통합 추출",
        f"`logs/financial_extraction_log.md`에 추출 방식별 건수와 skip 사유 `{sum(issue_counter.values())}`건을 기록",
        f"이벤트성 공시와 자동 매핑 신뢰도가 낮은 filing `{len(skipped)}`건은 보류 목록으로 분리",
    ]
    append_workflow_section(WORKFLOW_LOG_PATH, "Exec Prompt 19. 공시 숫자 추출 테이블 작성", bullets)


if __name__ == "__main__":
    build_output()
