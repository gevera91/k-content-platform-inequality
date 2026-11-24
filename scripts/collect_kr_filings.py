#!/usr/bin/env python3

import csv
import html
import re
import ssl
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
ACCESS_DATE = "2026-03-28"
STAMP = "20260328"
PROMPT_NAME = "Exec Prompt 12"
USER_AGENT = "Mozilla/5.0"
SSL_CONTEXT = ssl._create_unverified_context()

SEARCH_URL = "https://englishdart.fss.or.kr/dsbb001/search.ax"
VIEWER_URL = "https://englishdart.fss.or.kr/dsbh001/main.do?rcpNo={rcp_no}"
XBRL_URL = "https://engopendart.fss.or.kr/xbrl/viewer/main.do?rcpNo={rcp_no}&lang=en"

SPECIAL_SEARCH_QUERIES = {
    "hybe": ["HYBE", "HYBE Co. Ltd."],
    "jyp_ent": ["JYP Entertainment Corporation", "JYP Ent.", "JYP Entertainment"],
    "kidari_studio": ["KidariStudio", "KidariStudio Inc."],
    "lg_uplus": ["LG Uplus Corp", "LG Uplus Corp."],
    "sk_telecom": ["SK Telecom", "SK Telecom Co. Ltd."],
    "yg_ent": ["YG Entertainment", "YG Entertainment Inc."],
}

FILING_GROUP_ORDER = ["annual", "semiannual", "quarterly", "major_issues"]


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def fetch_url(url, data=None):
    headers = {"User-Agent": USER_AGENT}
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=45, context=SSL_CONTEXT) as response:
        return response.read().decode("utf-8", "ignore")


def post_search(query, page):
    payload = urllib.parse.urlencode(
        {
            "textCrpNm": query,
            "textCrpNmAddPer": "true",
            "currentPage": str(page),
            "businessCode": "all",
            "corporationType": "all",
            "searchIndex": "",
            "textCrpCik": "",
        }
    ).encode()
    return fetch_url(SEARCH_URL, data=payload)


def normalize_space(text):
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def clean_html_text(html_text):
    text = re.sub(r"(?is)<script.*?</script>", " ", html_text)
    text = re.sub(r"(?is)<style.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", "\n", text)
    return html.unescape(text)


def parse_search_rows(page_html):
    rows = []
    for block in re.findall(r"<tr>(.*?)</tr>", page_html, flags=re.S):
        if "dsbh001/main.do?rcpNo=" not in block:
            continue
        anchor_match = re.search(
            r"(<a href=\"/dsbh001/main\.do\?rcpNo=(\d+)\".*?</a>)", block, flags=re.S
        )
        if not anchor_match:
            continue
        anchor_html = anchor_match.group(1)
        rcp_no = anchor_match.group(2)
        title_attr_match = re.search(
            r'title=\"([^\"]+?)\s+Report Viewer New Window\"', anchor_html
        )
        title_attr = normalize_space(title_attr_match.group(1)) if title_attr_match else ""
        text_inner = normalize_space(re.sub(r"<[^>]+>", " ", anchor_html))
        date_match = re.findall(r"<td>\s*([0-9]{4}\.[0-9]{2}\.[0-9]{2})\s*</td>", block)
        filed_date = date_match[-1] if date_match else ""
        select_match = re.search(r"selectKey=(\d+)", block)
        xbrl_available = "openXbrlViewerNew" in block and "btn_xbrlviewer" in block
        rows.append(
            {
                "rcp_no": rcp_no,
                "report_title_attr": title_attr,
                "report_title_text": text_inner,
                "filing_date": filed_date,
                "select_key": select_match.group(1) if select_match else "",
                "xbrl_available": "y" if xbrl_available else "n",
            }
        )
    return rows


def filing_group_for_title(title):
    lower = title.lower()
    if "semi-annual report" in lower:
        return "semiannual"
    if "quarterly report" in lower:
        return "quarterly"
    if "report on major issues" in lower:
        return "major_issues"
    if "annual report" in lower:
        return "annual"
    return ""


def extract_report_period(title_text):
    match = re.search(r"\(([^)]+)\)", title_text)
    return match.group(1) if match else ""


def search_company(query):
    all_rows = []
    seen = set()
    found_groups = set()
    for page in range(1, 21):
        page_html = post_search(query, page)
        rows = parse_search_rows(page_html)
        if not rows:
            break
        new_rows = [row for row in rows if row["rcp_no"] not in seen]
        if not new_rows:
            break
        for row in new_rows:
            seen.add(row["rcp_no"])
            group = filing_group_for_title(row["report_title_attr"] or row["report_title_text"])
            if group:
                found_groups.add(group)
        all_rows.extend(new_rows)
        if found_groups >= set(FILING_GROUP_ORDER):
            break
        time.sleep(0.15)
    return all_rows


def resolve_query(firm_row):
    query_candidates = []
    seen = set()
    for raw in SPECIAL_SEARCH_QUERIES.get(firm_row["firm_std"], []):
        if raw and raw not in seen:
            query_candidates.append(raw)
            seen.add(raw)
    for raw in [
        firm_row["filing_name_primary"],
        firm_row["firm_name_std"],
        firm_row["firm_name_original"],
        firm_row["firm_name_ko"],
    ]:
        if raw and raw not in seen:
            query_candidates.append(raw)
            seen.add(raw)

    raw = firm_row["filing_name_primary"]
    variants = [
        raw.replace(" Co. Ltd.", ""),
        raw.replace(" Corporation", ""),
        raw.replace(" Corp.", ""),
        raw.replace(" Inc.", ""),
        raw.replace(" Company", ""),
        raw.replace(".", ""),
    ]
    for variant in variants:
        variant = variant.strip()
        if variant and variant not in seen:
            query_candidates.append(variant)
            seen.add(variant)

    best_query = ""
    best_rows = []
    for query in query_candidates:
        rows = search_company(query)
        if rows:
            best_query = query
            best_rows = rows
            break
    return best_query, best_rows


def choose_filings(rows):
    chosen = {}
    for row in rows:
        group = filing_group_for_title(row["report_title_attr"] or row["report_title_text"])
        if group and group not in chosen:
            chosen[group] = row
    return chosen


def extract_candidate_lines(html_text):
    text = clean_html_text(html_text)
    lines = []
    seen = set()
    for raw_line in text.splitlines():
        line = normalize_space(raw_line)
        if len(line) < 4 or len(line) > 180:
            continue
        if not re.search(r"[A-Za-z]", line):
            continue
        if re.search(
            r"^(skip|open|close|copyright|download|list|english|search|main|previous|next)\b",
            line,
            re.I,
        ):
            continue
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)
    return lines


def first_line(lines, keywords):
    for keyword in keywords:
        key = keyword.lower()
        for line in lines:
            if key in line.lower():
                return line
    return ""


def extract_note_locations(html_text, sector):
    lines = extract_candidate_lines(html_text)
    note_locations = {
        "note_location_intangible_assets": first_line(lines, ["intangible assets", "intangible asset"])
        or "not_explicit_in_saved_filing",
        "note_location_income_tax_expense": first_line(
            lines, ["income tax", "tax expense", "income taxes"]
        )
        or "not_explicit_in_saved_filing",
        "note_location_pretax_profit": first_line(
            lines,
            [
                "profit before income tax",
                "income before income tax",
                "profit before tax",
                "statement of comprehensive income",
                "statement of income",
            ],
        )
        or "not_explicit_in_saved_filing",
    }

    if sector in {"music", "webtoon_story"}:
        note_locations["note_location_content_investment"] = first_line(
            lines,
            [
                "content",
                "royalt",
                "production",
                "cost of sales",
                "breakdown of expenses by nature",
                "operating segment",
                "contract assets",
                "licenses",
                "subscription",
                "artist",
                "webtoon",
                "story",
            ],
        ) or "not_explicit_in_saved_filing"
        note_locations["note_location_network_cost"] = "not_core_for_sector"
    else:
        note_locations["note_location_content_investment"] = "not_core_for_sector"
        note_locations["note_location_network_cost"] = first_line(
            lines,
            [
                "network",
                "telecommunication",
                "cost of services",
                "cost of sales",
                "breakdown of expenses by nature",
                "property and equipment",
                "depreciation",
                "operating expenses",
            ],
        ) or "not_explicit_in_saved_filing"

    return note_locations


def save_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def relative_path(path):
    return path.relative_to(BASE_DIR).as_posix()


def append_unique_rows(path, fieldnames, new_rows, unique_keys):
    existing = []
    existing_keys = set()
    if path.exists():
        existing = read_csv(path)
        for row in existing:
            existing_keys.add(tuple(row[key] for key in unique_keys))
    for row in new_rows:
        key = tuple(row[key] for key in unique_keys)
        if key not in existing_keys:
            existing.append(row)
            existing_keys.add(key)
    write_csv(path, existing, fieldnames)


def build_manifest():
    firm_rows = read_csv(BASE_DIR / "data/registry/entity_dictionary_firm.csv")
    universe_rows = read_csv(BASE_DIR / "data/registry/firm_universe.csv")

    sector_map = {}
    service_map = {}
    for row in universe_rows:
        if row["home_country"] != "kr":
            continue
        sector_map.setdefault(row["firm_std"], row["sector_primary"])
        service_map.setdefault(row["firm_std"], row["service_std_candidate"])

    listed_firms = [
        row
        for row in firm_rows
        if row["home_country"] == "kr"
        and row["listed_flag"] == "y"
        and row["filing_system"] == "OpenDART"
    ]
    nonlisted_firms = [
        row
        for row in firm_rows
        if row["home_country"] == "kr" and row["listed_flag"] == "n"
    ]

    manifest_rows = []
    source_rows = []
    firm_logs = []

    for firm in listed_firms:
        firm_std = firm["firm_std"]
        sector_std = sector_map.get(firm_std, "")
        service_std = service_map.get(firm_std, "")
        query_used, rows = resolve_query(firm)
        chosen = choose_filings(rows)

        reference_html = ""
        note_reference_group = ""

        saved_rows = {}
        for group in FILING_GROUP_ORDER:
            row = chosen.get(group)
            if not row:
                continue
            raw_dir = BASE_DIR / "data/raw/kr/filings" / firm_std
            viewer_path = raw_dir / f"{firm_std}_{group}_{row['rcp_no']}_viewer_{STAMP}.html"
            xbrl_path = raw_dir / f"{firm_std}_{group}_{row['rcp_no']}_xbrl_{STAMP}.html"
            viewer_url = VIEWER_URL.format(rcp_no=row["rcp_no"])
            xbrl_url = XBRL_URL.format(rcp_no=row["rcp_no"]) if row["xbrl_available"] == "y" else ""

            viewer_html = fetch_url(viewer_url)
            save_text(viewer_path, viewer_html)
            saved_html = viewer_html
            saved_xbrl_path = ""

            source_rows.append(
                {
                    "source_file": relative_path(viewer_path),
                    "source_url": viewer_url,
                    "access_date": ACCESS_DATE,
                    "country_std": "kr",
                    "firm_std": firm_std,
                    "service_std": service_std,
                    "sector_std": sector_std,
                    "file_format": "html",
                    "collected_by_prompt": PROMPT_NAME,
                    "status": "collected",
                }
            )

            if row["xbrl_available"] == "y":
                xbrl_html = fetch_url(xbrl_url)
                save_text(xbrl_path, xbrl_html)
                saved_html = xbrl_html
                saved_xbrl_path = relative_path(xbrl_path)
                source_rows.append(
                    {
                        "source_file": relative_path(xbrl_path),
                        "source_url": xbrl_url,
                        "access_date": ACCESS_DATE,
                        "country_std": "kr",
                        "firm_std": firm_std,
                        "service_std": service_std,
                        "sector_std": sector_std,
                        "file_format": "html",
                        "collected_by_prompt": PROMPT_NAME,
                        "status": "collected",
                    }
                )
            if not reference_html and group in {"annual", "semiannual", "quarterly"}:
                reference_html = saved_html
                note_reference_group = group

            saved_rows[group] = {
                "report_title": row["report_title_attr"] or row["report_title_text"],
                "report_period": extract_report_period(row["report_title_text"]),
                "rcp_no": row["rcp_no"],
                "filing_date": row["filing_date"],
                "viewer_url": viewer_url,
                "xbrl_url": xbrl_url,
                "raw_viewer_path": relative_path(viewer_path),
                "raw_xbrl_path": saved_xbrl_path,
                "xbrl_available": row["xbrl_available"],
            }
            time.sleep(0.15)

        note_locations = (
            extract_note_locations(reference_html, sector_std)
            if reference_html
            else {
                "note_location_content_investment": "reference_filing_not_collected",
                "note_location_network_cost": "reference_filing_not_collected",
                "note_location_intangible_assets": "reference_filing_not_collected",
                "note_location_pretax_profit": "reference_filing_not_collected",
                "note_location_income_tax_expense": "reference_filing_not_collected",
            }
        )

        for group in FILING_GROUP_ORDER:
            saved = saved_rows.get(group)
            if saved:
                manifest_rows.append(
                    {
                        "firm_std": firm_std,
                        "firm_name_std": firm["firm_name_std"],
                        "listed_flag": firm["listed_flag"],
                        "sector_std": sector_std,
                        "service_std": service_std,
                        "filing_system": firm["filing_system"],
                        "query_used": query_used,
                        "note_reference_group": note_reference_group,
                        "filing_group": group,
                        "filing_type": saved["report_title"],
                        "report_period": saved["report_period"],
                        "rcp_no": saved["rcp_no"],
                        "filing_date": saved["filing_date"],
                        "viewer_url": saved["viewer_url"],
                        "xbrl_url": saved["xbrl_url"],
                        "raw_viewer_path": saved["raw_viewer_path"],
                        "raw_xbrl_path": saved["raw_xbrl_path"],
                        "xbrl_available": saved["xbrl_available"],
                        "note_location_content_investment": note_locations["note_location_content_investment"],
                        "note_location_network_cost": note_locations["note_location_network_cost"],
                        "note_location_intangible_assets": note_locations["note_location_intangible_assets"],
                        "note_location_pretax_profit": note_locations["note_location_pretax_profit"],
                        "note_location_income_tax_expense": note_locations[
                            "note_location_income_tax_expense"
                        ],
                        "collection_status": "collected",
                        "notes": "",
                    }
                )
            else:
                manifest_rows.append(
                    {
                        "firm_std": firm_std,
                        "firm_name_std": firm["firm_name_std"],
                        "listed_flag": firm["listed_flag"],
                        "sector_std": sector_std,
                        "service_std": service_std,
                        "filing_system": firm["filing_system"],
                        "query_used": query_used,
                        "note_reference_group": note_reference_group,
                        "filing_group": group,
                        "filing_type": "",
                        "report_period": "",
                        "rcp_no": "",
                        "filing_date": "",
                        "viewer_url": "",
                        "xbrl_url": "",
                        "raw_viewer_path": "",
                        "raw_xbrl_path": "",
                        "xbrl_available": "",
                        "note_location_content_investment": note_locations["note_location_content_investment"],
                        "note_location_network_cost": note_locations["note_location_network_cost"],
                        "note_location_intangible_assets": note_locations["note_location_intangible_assets"],
                        "note_location_pretax_profit": note_locations["note_location_pretax_profit"],
                        "note_location_income_tax_expense": note_locations[
                            "note_location_income_tax_expense"
                        ],
                        "collection_status": "required_filing_not_found",
                        "notes": "Search pages exhausted without a matching filing title.",
                    }
                )

        firm_logs.append(
            {
                "firm_std": firm_std,
                "query_used": query_used,
                "collected_groups": ", ".join([group for group in FILING_GROUP_ORDER if group in saved_rows]),
                "missing_groups": ", ".join([group for group in FILING_GROUP_ORDER if group not in saved_rows]),
                "reference_group": note_reference_group or "none",
            }
        )

    for firm in nonlisted_firms:
        manifest_rows.append(
            {
                "firm_std": firm["firm_std"],
                "firm_name_std": firm["firm_name_std"],
                "listed_flag": firm["listed_flag"],
                "sector_std": sector_map.get(firm["firm_std"], ""),
                "service_std": service_map.get(firm["firm_std"], ""),
                "filing_system": firm["filing_system"],
                "query_used": "",
                "note_reference_group": "",
                "filing_group": "direct_filing_status",
                "filing_type": "",
                "report_period": "",
                "rcp_no": "",
                "filing_date": "",
                "viewer_url": "",
                "xbrl_url": "",
                "raw_viewer_path": "",
                "raw_xbrl_path": "",
                "xbrl_available": "",
                "note_location_content_investment": "not_available_without_direct_public_filing",
                "note_location_network_cost": "not_available_without_direct_public_filing",
                "note_location_intangible_assets": "not_available_without_direct_public_filing",
                "note_location_pretax_profit": "not_available_without_direct_public_filing",
                "note_location_income_tax_expense": "not_available_without_direct_public_filing",
                "collection_status": "no_direct_public_filing",
                "notes": (
                    "Indirect parent-public route required."
                    if firm["filing_system"] == "parent_indirect_public"
                    else "No direct OpenDART filing system available."
                ),
            }
        )

    manifest_fieldnames = [
        "firm_std",
        "firm_name_std",
        "listed_flag",
        "sector_std",
        "service_std",
        "filing_system",
        "query_used",
        "note_reference_group",
        "filing_group",
        "filing_type",
        "report_period",
        "rcp_no",
        "filing_date",
        "viewer_url",
        "xbrl_url",
        "raw_viewer_path",
        "raw_xbrl_path",
        "xbrl_available",
        "note_location_content_investment",
        "note_location_network_cost",
        "note_location_intangible_assets",
        "note_location_pretax_profit",
        "note_location_income_tax_expense",
        "collection_status",
        "notes",
    ]
    write_csv(BASE_DIR / "data/interim/kr_filing_manifest.csv", manifest_rows, manifest_fieldnames)

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

    project_rows = [
        {
            "artifact_type": "file",
            "path": "scripts/collect_kr_filings.py",
            "owner_step": PROMPT_NAME,
            "source_type": "local_script",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Reusable OpenDART English filing collection script for Korean listed firms.",
        },
        {
            "artifact_type": "file",
            "path": "data/interim/kr_filing_manifest.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "official_public_multi",
            "source_url": "https://englishdart.fss.or.kr/",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Korean filing manifest with filing metadata and note-location fields.",
        },
        {
            "artifact_type": "file",
            "path": "logs/kr_filings_log.md",
            "owner_step": PROMPT_NAME,
            "source_type": "official_public_multi",
            "source_url": "https://englishdart.fss.or.kr/",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Collection log for Korean listed-firm filings and direct-filing gaps for nonlisted firms.",
        },
    ]
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
    missing_count = sum(
        1 for row in manifest_rows if row["collection_status"] == "required_filing_not_found"
    )
    nonlisted_count = sum(
        1 for row in manifest_rows if row["collection_status"] == "no_direct_public_filing"
    )

    log_lines = [
        "# Korean Filings Log",
        "",
        f"- Access date: `{ACCESS_DATE}`",
        f"- Prompt: `{PROMPT_NAME}`",
        f"- Listed Korean firms searched: `{len(listed_firms)}`",
        f"- Nonlisted Korean firms logged without direct filings: `{nonlisted_count}`",
        f"- Collected filing rows: `{collected_count}`",
        f"- Missing required filing rows: `{missing_count}`",
        "",
        "## Query Resolution",
        "",
    ]
    for item in firm_logs:
        log_lines.append(
            f"- `{item['firm_std']}`: query `{item['query_used']}` | collected `{item['collected_groups'] or 'none'}` | missing `{item['missing_groups'] or 'none'}` | notes from `{item['reference_group']}`"
        )

    log_lines.extend(
        [
            "",
            "## Nonlisted Firm Status",
            "",
            "- `kakao_ent`: direct OpenDART filing unavailable; parent-public route required.",
            "- `ridi`: direct OpenDART filing unavailable; company-only public sources needed.",
            "",
            "## Note-Location Rules",
            "",
            "- `note_reference_group` prioritizes `annual`, then `semiannual`, then `quarterly`.",
            "- `content_investment` is only resolved for `music` and `webtoon_story`; other sectors are marked `not_core_for_sector`.",
            "- `network_cost` is only resolved for `digital_infra`; other sectors are marked `not_core_for_sector`.",
        ]
    )
    (BASE_DIR / "logs/kr_filings_log.md").write_text("\n".join(log_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build_manifest()
