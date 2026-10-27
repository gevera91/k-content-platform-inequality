#!/usr/bin/env python3

import calendar
import csv
import re
from collections import Counter
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
ACCESS_DATE = "2026-03-29"
PROMPT_NAME = "Exec Prompt 14"


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


def normalize_date(value):
    value = value.strip()
    if not value:
        return ""
    if re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", value):
        return value.replace(".", "-")
    return value


def last_day_of_month(year, month):
    return calendar.monthrange(year, month)[1]


def derive_period_from_kr(report_period, filing_group, filing_date):
    filing_date = normalize_date(filing_date)
    if filing_group == "major_issues":
        return f"EVENT_{filing_date.replace('-', '')}", filing_date, "event"
    if re.fullmatch(r"\d{4}\.\d{2}", report_period):
        year_str, month_str = report_period.split(".")
        year = int(year_str)
        month = int(month_str)
        period_end = f"{year:04d}-{month:02d}-{last_day_of_month(year, month):02d}"
        if filing_group == "annual":
            return f"FY{year}", period_end, "annual"
        if filing_group == "semiannual":
            half = "H1" if month <= 6 else "H2"
            return f"{year}{half}", period_end, "semiannual"
        quarter_map = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}
        quarter = quarter_map.get(month, f"M{month:02d}")
        return f"{year}{quarter}", period_end, "quarterly"
    return "", "", ""


def derive_period_from_global(fiscal_period, filing_group, filing_date):
    filing_date = normalize_date(filing_date)
    if filing_group == "current_report":
        return f"EVENT_{filing_date.replace('-', '')}", filing_date, "event"

    if re.fullmatch(r"\d{8}", fiscal_period):
        year = int(fiscal_period[:4])
        month = int(fiscal_period[4:6])
        day = int(fiscal_period[6:8])
        period_end = f"{year:04d}-{month:02d}-{day:02d}"
        if filing_group == "annual":
            return f"FY{year}", period_end, "annual"
        quarter_map = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}
        quarter = quarter_map.get(month, f"M{month:02d}")
        return f"{year}{quarter}", period_end, "interim"

    match = re.search(
        r"(Fiscal Year Ended|Nine Months Ended|Six Months Ended|Three Months Ended|3rd Quarter Ended)\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})",
        fiscal_period,
        re.I,
    )
    if match:
        label, month_name, day, year = match.groups()
        month_map = {
            "January": 1,
            "February": 2,
            "March": 3,
            "April": 4,
            "May": 5,
            "June": 6,
            "July": 7,
            "August": 8,
            "September": 9,
            "October": 10,
            "November": 11,
            "December": 12,
        }
        month = month_map[month_name]
        period_end = f"{int(year):04d}-{month:02d}-{int(day):02d}"
        if "Fiscal Year" in label:
            return f"FY{year}", period_end, "annual"
        if "Nine Months" in label or "3rd Quarter" in label:
            return f"{year}Q3", period_end, "interim"
        if "Six Months" in label:
            return f"{year}H1", period_end, "interim"
        if "Three Months" in label:
            quarter_map = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}
            return f"{year}{quarter_map.get(month, 'QX')}", period_end, "interim"

    return fiscal_period, "", "unknown"


def build_coverage_notes_kr(row):
    notes = []
    if row["raw_xbrl_path"]:
        notes.append("preferred_source=xbrl")
        notes.append("secondary_source=viewer")
    else:
        notes.append("preferred_source=viewer")
    notes.append(f"filing_group={row['filing_group']}")
    notes.append("currency=KRW_proxy")
    notes.append("accounting=K_IFRS_proxy")
    if row["notes"]:
        notes.append(f"collection_note={row['notes']}")
    return "; ".join(notes)


def build_coverage_notes_global(row):
    notes = [f"filing_group={row['filing_group']}"]
    if row["notes"]:
        notes.append(row["notes"])
    if row["filing_system"] == "SEC_EDGAR":
        notes.append("primary_source=filing_html")
    if row["filing_system"] == "EDINET_fallback_official_ir":
        notes.append("fallback=official_ir_pdf")
    return "; ".join(notes)


def build_panel():
    kr_rows = read_csv(BASE_DIR / "data/interim/kr_filing_manifest.csv")
    global_rows = read_csv(BASE_DIR / "data/interim/global_filing_manifest.csv")

    panel_rows = []
    excluded_rows = []

    for row in kr_rows:
        if row["collection_status"] != "collected":
            excluded_rows.append(
                {
                    "origin": "kr",
                    "firm_std": row["firm_std"],
                    "filing_group": row["filing_group"],
                    "collection_status": row["collection_status"],
                    "notes": row["notes"],
                }
            )
            continue
        fiscal_period, fiscal_period_end, period_granularity = derive_period_from_kr(
            row["report_period"], row["filing_group"], row["filing_date"]
        )
        source_file = row["raw_xbrl_path"] or row["raw_viewer_path"]
        source_url = row["xbrl_url"] or row["viewer_url"]
        panel_rows.append(
            {
                "filing_id": f"kr_{row['firm_std']}_{row['filing_group']}_{row['rcp_no']}",
                "firm_std": row["firm_std"],
                "firm_name_std": row["firm_name_std"],
                "country_std": "kr",
                "filing_system_country_std": "kr",
                "sector_std": row["sector_std"],
                "service_std": row["service_std"],
                "filing_system": row["filing_system"],
                "filing_group": row["filing_group"],
                "filing_date": normalize_date(row["filing_date"]),
                "fiscal_period": fiscal_period,
                "fiscal_period_end": fiscal_period_end,
                "period_granularity": period_granularity,
                "filing_type": row["filing_type"],
                "filing_form": row["filing_type"],
                "source_file": source_file,
                "source_url": source_url,
                "secondary_source_file": row["raw_viewer_path"] if row["raw_xbrl_path"] else "",
                "secondary_source_url": row["viewer_url"] if row["raw_xbrl_path"] else "",
                "source_format": "html",
                "currency": "KRW",
                "accounting_standard": "K_IFRS_PROXY",
                "coverage_notes": build_coverage_notes_kr(row),
            }
        )

    for row in global_rows:
        if row["collection_status"] != "collected":
            excluded_rows.append(
                {
                    "origin": "global",
                    "firm_std": row["firm_std"],
                    "filing_group": row["filing_group"],
                    "collection_status": row["collection_status"],
                    "notes": row["notes"],
                }
            )
            continue
        fiscal_period, fiscal_period_end, period_granularity = derive_period_from_global(
            row["fiscal_period"], row["filing_group"], row["filing_date"]
        )
        panel_rows.append(
            {
                "filing_id": f"{row['country_std'] if 'country_std' in row else row['issuer_country_std']}_{row['firm_std']}_{row['filing_group']}_{row['accession_or_doc_id']}",
                "firm_std": row["firm_std"],
                "firm_name_std": row["firm_name_std"],
                "country_std": row["issuer_country_std"],
                "filing_system_country_std": row["source_system_country_std"],
                "sector_std": row["sector_std"],
                "service_std": row["service_std"],
                "filing_system": row["filing_system"],
                "filing_group": row["filing_group"],
                "filing_date": normalize_date(row["filing_date"]),
                "fiscal_period": fiscal_period,
                "fiscal_period_end": fiscal_period_end,
                "period_granularity": period_granularity,
                "filing_type": row["filing_form"],
                "filing_form": row["filing_form"],
                "source_file": row["raw_path"],
                "source_url": row["source_url"],
                "secondary_source_file": "",
                "secondary_source_url": "",
                "source_format": row["file_format"],
                "currency": row["currency"],
                "accounting_standard": row["accounting_standard"],
                "coverage_notes": build_coverage_notes_global(row),
            }
        )

    panel_rows = sorted(
        panel_rows,
        key=lambda item: (
            item["country_std"],
            item["firm_std"],
            item["filing_date"],
            item["filing_group"],
        ),
    )

    panel_fieldnames = [
        "filing_id",
        "firm_std",
        "firm_name_std",
        "country_std",
        "filing_system_country_std",
        "sector_std",
        "service_std",
        "filing_system",
        "filing_group",
        "filing_date",
        "fiscal_period",
        "fiscal_period_end",
        "period_granularity",
        "filing_type",
        "filing_form",
        "source_file",
        "source_url",
        "secondary_source_file",
        "secondary_source_url",
        "source_format",
        "currency",
        "accounting_standard",
        "coverage_notes",
    ]
    write_csv(BASE_DIR / "data/interim/filing_metadata_panel.csv", panel_rows, panel_fieldnames)

    project_rows = [
        {
            "artifact_type": "file",
            "path": "scripts/build_filing_metadata_panel.py",
            "owner_step": PROMPT_NAME,
            "source_type": "local_script",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Builds unified filing metadata panel from Korean and global filing manifests.",
        },
        {
            "artifact_type": "file",
            "path": "data/interim/filing_metadata_panel.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_registry",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Unified filing metadata panel with standardized period mapping and source-file selection.",
        },
        {
            "artifact_type": "file",
            "path": "logs/filing_metadata_log.md",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_registry",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Metadata panel construction log, period rules, and excluded rows summary.",
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

    origin_counts = Counter(
        "kr" if row["filing_system"] == "OpenDART" else "global" for row in panel_rows
    )
    country_counts = Counter(row["country_std"] for row in panel_rows)
    excluded_status_counts = Counter(row["collection_status"] for row in excluded_rows)

    log_lines = [
        "# Filing Metadata Log",
        "",
        f"- Access date: `{ACCESS_DATE}`",
        f"- Prompt: `{PROMPT_NAME}`",
        f"- Total panel rows: `{len(panel_rows)}`",
        f"- Korean collected filing rows included: `{origin_counts['kr']}`",
        f"- Global collected filing rows included: `{origin_counts['global']}`",
        f"- Excluded non-collected rows: `{len(excluded_rows)}`",
        "",
        "## Standardization Rules",
        "",
        "- `country_std` is the issuer-home-country code, not the filing-system country.",
        "- `filing_system_country_std` preserves filing jurisdiction such as `us` for SEC foreign private issuers.",
        "- Korean `annual`, `semiannual`, `quarterly` rows prefer `xbrl` as `source_file` when available and keep the viewer path as `secondary_source_file`.",
        "- Korean listed-firm currency/accounting fields are standardized as `KRW` and `K_IFRS_PROXY` for metadata-stage harmonization.",
        "- SEC issuers keep the filing HTML as the primary `source_file`; KADOKAWA keeps official IR PDFs because EDINET API returned `401 invalid subscription key` on `2026-03-29`.",
        "- `fiscal_period` is normalized to compact labels such as `FY2025`, `2025Q3`, `2025H1`, or `EVENT_20260327`.",
        "",
        "## Panel Coverage",
        "",
    ]
    for country_std in sorted(country_counts):
        log_lines.append(f"- `{country_std}`: `{country_counts[country_std]}` rows")

    log_lines.extend(
        [
            "",
            "## Excluded Rows",
            "",
            f"- excluded status counts: `{dict(excluded_status_counts)}`",
        ]
    )
    for row in excluded_rows:
        log_lines.append(
            f"- `{row['origin']}` | `{row['firm_std']}` | `{row['filing_group']}` | `{row['collection_status']}` | `{row['notes'] or 'no extra note'}`"
        )

    log_lines.extend(
        [
            "",
            "## Required Columns Check",
            "",
            "- Required columns present: `firm_std`, `country_std`, `filing_date`, `fiscal_period`, `filing_type`, `source_file`, `source_url`, `currency`, `accounting_standard`, `coverage_notes`.",
        ]
    )
    (BASE_DIR / "logs/filing_metadata_log.md").write_text("\n".join(log_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build_panel()
