#!/usr/bin/env python3

import csv
import importlib.util
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
ACCESS_DATE = "2026-03-29"
STAMP = "20260329"
PROMPT_NAME = "Post Step 15"

KR_MANIFEST_PATH = BASE_DIR / "data/interim/kr_filing_manifest.csv"
SOURCE_MANIFEST_PATH = BASE_DIR / "data/registry/source_manifest.csv"
PROJECT_MANIFEST_PATH = BASE_DIR / "data/registry/project_manifest.csv"
WORKFLOW_LOG_PATH = BASE_DIR / "logs/workflow_log.md"
LOG_PATH = BASE_DIR / "logs/kr_telecom_fy2024_sample_thickening_log.md"

TARGET_FILINGS = {
    "kt": {
        "rcp_no": "20250321001834",
        "filing_date": "2025.03.21",
        "report_period": "2024.12",
    },
    "sk_telecom": {
        "rcp_no": "20250317000684",
        "filing_date": "2025.03.17",
        "report_period": "2024.12",
    },
    "lg_uplus": {
        "rcp_no": "20250317000701",
        "filing_date": "2025.03.17",
        "report_period": "2024.12",
    },
}


def load_collect_module():
    module_path = BASE_DIR / "scripts/collect_kr_filings.py"
    spec = importlib.util.spec_from_file_location("collect_kr_filings", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


KR = load_collect_module()


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
            seen.add(tuple(row.get(key, "") for key in unique_keys))
    for row in new_rows:
        normalized = {field: str(row.get(field, "")) for field in fieldnames}
        key = tuple(normalized.get(key, "") for key in unique_keys)
        if key not in seen:
            existing_rows.append(normalized)
            seen.add(key)
    write_csv(path, existing_rows, fieldnames)


def relative_path(path):
    return path.relative_to(BASE_DIR).as_posix()


def template_rows_by_firm(manifest_rows):
    templates = {}
    for row in manifest_rows:
        if row.get("collection_status") != "collected":
            continue
        if row.get("filing_group") != "annual":
            continue
        templates.setdefault(row["firm_std"], row)
    return templates


def save_filing_pair(firm_std, rcp_no):
    raw_dir = BASE_DIR / "data/raw/kr/filings" / firm_std
    viewer_path = raw_dir / f"{firm_std}_annual_{rcp_no}_viewer_{STAMP}.html"
    xbrl_path = raw_dir / f"{firm_std}_annual_{rcp_no}_xbrl_{STAMP}.html"
    viewer_url = KR.VIEWER_URL.format(rcp_no=rcp_no)
    xbrl_url = KR.XBRL_URL.format(rcp_no=rcp_no)

    viewer_html = KR.fetch_url(viewer_url)
    xbrl_html = KR.fetch_url(xbrl_url)

    KR.save_text(viewer_path, viewer_html)
    KR.save_text(xbrl_path, xbrl_html)
    return viewer_url, xbrl_url, viewer_path, xbrl_path, xbrl_html


def build():
    manifest_rows = read_csv(KR_MANIFEST_PATH)
    manifest_fieldnames = list(manifest_rows[0].keys())
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

    templates = template_rows_by_firm(manifest_rows)
    existing_keys = {(row["firm_std"], row["rcp_no"]) for row in manifest_rows}

    source_rows = []
    collected_rows = []
    skipped_rows = []

    for firm_std, target in TARGET_FILINGS.items():
        unique_key = (firm_std, target["rcp_no"])
        if unique_key in existing_keys:
            skipped_rows.append(
                {
                    "firm_std": firm_std,
                    "reason": "already_present",
                    "rcp_no": target["rcp_no"],
                }
            )
            continue

        template = templates.get(firm_std)
        if not template:
            skipped_rows.append(
                {
                    "firm_std": firm_std,
                    "reason": "template_missing",
                    "rcp_no": target["rcp_no"],
                }
            )
            continue

        viewer_url, xbrl_url, viewer_path, xbrl_path, xbrl_html = save_filing_pair(
            firm_std, target["rcp_no"]
        )
        note_locations = KR.extract_note_locations(xbrl_html, template["sector_std"])

        manifest_rows.append(
            {
                "firm_std": firm_std,
                "firm_name_std": template["firm_name_std"],
                "listed_flag": template["listed_flag"],
                "sector_std": template["sector_std"],
                "service_std": template["service_std"],
                "filing_system": template["filing_system"],
                "query_used": template["query_used"],
                "note_reference_group": "annual",
                "filing_group": "annual",
                "filing_type": "Annual Report",
                "report_period": target["report_period"],
                "rcp_no": target["rcp_no"],
                "filing_date": target["filing_date"],
                "viewer_url": viewer_url,
                "xbrl_url": xbrl_url,
                "raw_viewer_path": relative_path(viewer_path),
                "raw_xbrl_path": relative_path(xbrl_path),
                "xbrl_available": "y",
                "note_location_content_investment": note_locations[
                    "note_location_content_investment"
                ],
                "note_location_network_cost": note_locations["note_location_network_cost"],
                "note_location_intangible_assets": note_locations[
                    "note_location_intangible_assets"
                ],
                "note_location_pretax_profit": note_locations["note_location_pretax_profit"],
                "note_location_income_tax_expense": note_locations[
                    "note_location_income_tax_expense"
                ],
                "collection_status": "collected",
                "notes": "post_step_kr_telecom_fy2024_sample_thickening",
            }
        )
        existing_keys.add(unique_key)

        source_rows.extend(
            [
                {
                    "source_file": relative_path(viewer_path),
                    "source_url": viewer_url,
                    "access_date": ACCESS_DATE,
                    "country_std": "kr",
                    "firm_std": firm_std,
                    "service_std": template["service_std"],
                    "sector_std": template["sector_std"],
                    "file_format": "html",
                    "collected_by_prompt": PROMPT_NAME,
                    "status": "collected",
                },
                {
                    "source_file": relative_path(xbrl_path),
                    "source_url": xbrl_url,
                    "access_date": ACCESS_DATE,
                    "country_std": "kr",
                    "firm_std": firm_std,
                    "service_std": template["service_std"],
                    "sector_std": template["sector_std"],
                    "file_format": "html",
                    "collected_by_prompt": PROMPT_NAME,
                    "status": "collected",
                },
            ]
        )
        collected_rows.append(
            {
                "firm_std": firm_std,
                "rcp_no": target["rcp_no"],
                "filing_date": target["filing_date"],
                "viewer_path": relative_path(viewer_path),
                "xbrl_path": relative_path(xbrl_path),
            }
        )

    manifest_rows = sorted(
        manifest_rows,
        key=lambda row: (
            row["firm_std"],
            row["filing_group"],
            row["filing_date"],
            row["rcp_no"],
        ),
    )
    write_csv(KR_MANIFEST_PATH, manifest_rows, manifest_fieldnames)
    append_unique_rows(
        SOURCE_MANIFEST_PATH,
        source_fieldnames,
        source_rows,
        unique_keys=("source_file", "source_url"),
    )
    append_unique_rows(
        PROJECT_MANIFEST_PATH,
        project_fieldnames,
        [
            {
                "artifact_type": "file",
                "path": "scripts/thicken_kr_telecom_fy2024_filings.py",
                "owner_step": PROMPT_NAME,
                "source_type": "local_script",
                "source_url": "",
                "access_date": ACCESS_DATE,
                "status": "created",
                "notes": "Post-step KR telecom FY2024 annual filing thickening script.",
            },
            {
                "artifact_type": "file",
                "path": "logs/kr_telecom_fy2024_sample_thickening_log.md",
                "owner_step": PROMPT_NAME,
                "source_type": "official_public_multi",
                "source_url": "https://englishdart.fss.or.kr/",
                "access_date": ACCESS_DATE,
                "status": "created",
                "notes": "KR telecom FY2024 annual filing thickening log.",
            },
        ],
        unique_keys=("path",),
    )

    annual_periods = {}
    for firm_std in TARGET_FILINGS:
        annual_periods[firm_std] = sorted(
            {
                row["report_period"]
                for row in manifest_rows
                if row["firm_std"] == firm_std
                and row["collection_status"] == "collected"
                and row["filing_group"] == "annual"
            }
        )

    log_lines = [
        "# KR Telecom FY2024 Sample Thickening Log",
        "",
        f"- Access date: `{ACCESS_DATE}`",
        f"- Prompt: `{PROMPT_NAME}`",
        f"- Target firms: `{len(TARGET_FILINGS)}`",
        f"- Newly collected FY2024 annual filings: `{len(collected_rows)}`",
        f"- Skipped targets: `{len(skipped_rows)}`",
        "",
        "## Collected Rows",
        "",
    ]
    if collected_rows:
        for row in collected_rows:
            log_lines.append(
                f"- `{row['firm_std']}` | filing_date `{row['filing_date']}` | rcp `{row['rcp_no']}` | viewer `{row['viewer_path']}` | xbrl `{row['xbrl_path']}`"
            )
    else:
        log_lines.append("- No new FY2024 telecom filings were added.")

    log_lines.extend(["", "## Annual Report Period Coverage After Thickening", ""])
    for firm_std in sorted(annual_periods):
        log_lines.append(
            f"- `{firm_std}` annual periods: `{', '.join(annual_periods[firm_std])}`"
        )

    log_lines.extend(["", "## Skipped Targets", ""])
    if skipped_rows:
        for row in skipped_rows:
            log_lines.append(
                f"- `{row['firm_std']}` | reason `{row['reason']}` | rcp `{row['rcp_no']}`"
            )
    else:
        log_lines.append("- None")

    LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    with WORKFLOW_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(
            f"\n## {PROMPT_NAME}. KR telecom FY2024 filing thickening\n"
            f"- Added `{len(collected_rows)}` FY2024 annual OpenDART filings for `kt/sk_telecom/lg_uplus` where missing.\n"
            f"- Updated `kr_filing_manifest.csv` and `source_manifest.csv` to open `2024Q4` firm-quarter coverage for domestic telecom peers.\n"
        )


if __name__ == "__main__":
    build()
