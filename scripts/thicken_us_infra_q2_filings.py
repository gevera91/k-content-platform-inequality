#!/usr/bin/env python3

import csv
import importlib.util
import json
import ssl
import urllib.request
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
ACCESS_DATE = "2026-03-29"
STAMP = "20260329"
PROMPT_NAME = "Post Step 13"
SEC_UA = "Mozilla/5.0 research@example.com"
SSL_CONTEXT = ssl._create_unverified_context()

GLOBAL_MANIFEST_PATH = BASE_DIR / "data/interim/global_filing_manifest.csv"
SOURCE_MANIFEST_PATH = BASE_DIR / "data/registry/source_manifest.csv"
PROJECT_MANIFEST_PATH = BASE_DIR / "data/registry/project_manifest.csv"
WORKFLOW_LOG_PATH = BASE_DIR / "logs/workflow_log.md"
LOG_PATH = BASE_DIR / "logs/us_infra_q2_sample_thickening_log.md"

TARGET_FIRMS = ["akamai", "alphabet", "amazon", "cloudflare", "netflix"]
TARGET_FISCAL_PERIOD = "20250630"


def load_collect_module():
    module_path = BASE_DIR / "scripts/collect_global_filings.py"
    spec = importlib.util.spec_from_file_location("collect_global_filings", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SEC = load_collect_module()


def read_csv(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
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
        key = tuple(normalized[key] for key in unique_keys)
        if key not in seen:
            existing_rows.append(normalized)
            seen.add(key)
    write_csv(path, existing_rows, fieldnames)


def relative_path(path):
    return path.relative_to(BASE_DIR).as_posix()


def fetch_recent_submissions(cik):
    url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
    request = urllib.request.Request(url, headers={"User-Agent": SEC_UA})
    with urllib.request.urlopen(request, timeout=45, context=SSL_CONTEXT) as response:
        return json.load(response)


def choose_q2_10q(filings):
    for filing in filings:
        if filing["form"] == "10-Q" and TARGET_FISCAL_PERIOD in filing["primary_document"]:
            return filing
    for filing in filings:
        if filing["form"] == "10-Q" and filing["filing_date"].startswith("2025-07"):
            return filing
    for filing in filings:
        if filing["form"] == "10-Q" and filing["filing_date"].startswith("2025-08"):
            return filing
    return None


def template_for_firm(manifest_rows, firm_std):
    candidates = [row for row in manifest_rows if row["firm_std"] == firm_std and row["collection_status"] == "collected"]
    candidates.sort(key=lambda row: (row["filing_group"] != "annual", row["filing_date"]))
    return candidates[0] if candidates else None


def save_q2_filing(firm_std, cik, filing):
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
        / f"{firm_std}_interim_q2_{accession_compact}_filing_{STAMP}{extension}"
    )
    content = SEC.fetch_bytes(source_url, SEC_UA)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(content)
    return source_url, raw_path, content


def build():
    manifest_rows = read_csv(GLOBAL_MANIFEST_PATH)
    manifest_fieldnames = list(manifest_rows[0].keys())
    existing_keys = {(row["firm_std"], row["accession_or_doc_id"]) for row in manifest_rows}

    source_rows = []
    collected_rows = []
    skipped_rows = []

    for firm_std in TARGET_FIRMS:
        template = template_for_firm(manifest_rows, firm_std)
        if not template:
            skipped_rows.append({"firm_std": firm_std, "reason": "template_missing"})
            continue

        cik = SEC.SEC_CIK_MAP[firm_std]
        submissions = fetch_recent_submissions(cik)
        filings = SEC.parse_recent_filings(submissions)
        filing = choose_q2_10q(filings)
        if not filing:
            skipped_rows.append({"firm_std": firm_std, "reason": "q2_10q_not_found"})
            continue

        unique_key = (firm_std, filing["accession_number"])
        if unique_key in existing_keys:
            skipped_rows.append({"firm_std": firm_std, "reason": "already_present", "accession": filing["accession_number"]})
            continue

        source_url, raw_path, content = save_q2_filing(firm_std, cik, filing)
        raw_html = content.decode("utf-8", "ignore")
        lines = SEC.extract_html_lines(raw_html)
        note_locations = SEC.extract_note_locations(lines, template["sector_std"])
        currency = SEC.detect_currency(raw_html, firm_std)
        accounting_standard = SEC.detect_accounting_standard(raw_html, firm_std)

        manifest_row = {
            "firm_std": firm_std,
            "firm_name_std": template["firm_name_std"],
            "issuer_country_std": template["issuer_country_std"],
            "source_system_country_std": "us",
            "sector_std": template["sector_std"],
            "service_std": template["service_std"],
            "filing_system": "SEC_EDGAR",
            "listed_flag": template["listed_flag"],
            "filing_group": "interim",
            "filing_form": filing["form"],
            "filing_date": filing["filing_date"],
            "fiscal_period": TARGET_FISCAL_PERIOD,
            "accession_or_doc_id": filing["accession_number"],
            "source_url": source_url,
            "raw_path": relative_path(raw_path),
            "file_format": raw_path.suffix.lower().lstrip("."),
            "currency": currency,
            "accounting_standard": accounting_standard,
            "note_location_segment": note_locations["note_location_segment"],
            "note_location_revenue": note_locations["note_location_revenue"],
            "note_location_cost": note_locations["note_location_cost"],
            "note_location_tax": note_locations["note_location_tax"],
            "note_location_intangible": note_locations["note_location_intangible"],
            "note_location_capex": note_locations["note_location_capex"],
            "collection_status": "collected",
            "notes": "post_step_q2_us_infra_sample_thickening",
        }
        manifest_rows.append(manifest_row)
        existing_keys.add(unique_key)

        source_rows.append(
            {
                "source_file": relative_path(raw_path),
                "source_url": source_url,
                "access_date": ACCESS_DATE,
                "country_std": "us",
                "firm_std": firm_std,
                "service_std": template["service_std"],
                "sector_std": template["sector_std"],
                "file_format": raw_path.suffix.lower().lstrip("."),
                "collected_by_prompt": PROMPT_NAME,
                "status": "collected",
            }
        )
        collected_rows.append(
            {
                "firm_std": firm_std,
                "filing_date": filing["filing_date"],
                "accession": filing["accession_number"],
                "raw_path": relative_path(raw_path),
                "source_url": source_url,
            }
        )

    manifest_rows = sorted(
        manifest_rows,
        key=lambda row: (
            row["issuer_country_std"],
            row["firm_std"],
            row["filing_date"],
            row["filing_group"],
            row["accession_or_doc_id"],
        ),
    )
    write_csv(GLOBAL_MANIFEST_PATH, manifest_rows, manifest_fieldnames)

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
        SOURCE_MANIFEST_PATH,
        source_fieldnames,
        source_rows,
        unique_keys=("source_file", "source_url"),
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
        PROJECT_MANIFEST_PATH,
        project_fieldnames,
        [
            {
                "artifact_type": "file",
                "path": "scripts/thicken_us_infra_q2_filings.py",
                "owner_step": PROMPT_NAME,
                "source_type": "local_script",
                "source_url": "",
                "access_date": ACCESS_DATE,
                "status": "created",
                "notes": "Post-step SEC collector for 2025Q2 digital infrastructure 10-Q sample thickening.",
            },
            {
                "artifact_type": "file",
                "path": "logs/us_infra_q2_sample_thickening_log.md",
                "owner_step": PROMPT_NAME,
                "source_type": "official_public_multi",
                "source_url": "https://www.sec.gov/",
                "access_date": ACCESS_DATE,
                "status": "created",
                "notes": "Q2 2025 U.S. digital infrastructure filing thickening log.",
            },
        ],
        unique_keys=("path",),
    )

    periods_by_firm = {}
    for firm_std in TARGET_FIRMS:
        periods = sorted(
            {
                row["fiscal_period"]
                for row in manifest_rows
                if row["firm_std"] == firm_std
                and row["collection_status"] == "collected"
                and row["filing_group"] == "interim"
            }
        )
        periods_by_firm[firm_std] = periods

    log_lines = [
        "# U.S. Infra Q2 Sample Thickening Log",
        "",
        f"- Access date: `{ACCESS_DATE}`",
        f"- Prompt: `{PROMPT_NAME}`",
        f"- Target firms: `{len(TARGET_FIRMS)}`",
        f"- Newly collected Q2 filings: `{len(collected_rows)}`",
        f"- Skipped targets: `{len(skipped_rows)}`",
        "",
        "## Collected Rows",
        "",
    ]
    if collected_rows:
        for row in collected_rows:
            log_lines.append(
                f"- `{row['firm_std']}` | filing_date `{row['filing_date']}` | accession `{row['accession']}` | raw `{row['raw_path']}`"
            )
    else:
        log_lines.append("- No new filings were added because all target rows were already present.")

    log_lines.extend(["", "## Period Coverage After Thickening", ""])
    for firm_std in TARGET_FIRMS:
        log_lines.append(f"- `{firm_std}` interim periods: `{', '.join(periods_by_firm.get(firm_std, []))}`")

    log_lines.extend(["", "## Skipped Targets", ""])
    if skipped_rows:
        for row in skipped_rows:
            detail = row.get("accession", "")
            suffix = f" | accession `{detail}`" if detail else ""
            log_lines.append(f"- `{row['firm_std']}` | reason `{row['reason']}`{suffix}")
    else:
        log_lines.append("- None")

    LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    with WORKFLOW_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(
            f"\n## {PROMPT_NAME}. U.S. digital infrastructure 2025Q2 filing thickening\n"
            f"- Added `{len(collected_rows)}` SEC 10-Q filings for `akamai/alphabet/amazon/cloudflare/netflix` where missing.\n"
            f"- Updated `global_filing_manifest.csv` and `source_manifest.csv` for 2025Q2 coverage.\n"
        )


if __name__ == "__main__":
    build()
