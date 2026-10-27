#!/usr/bin/env python3

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple


BASE_DIR = Path(__file__).resolve().parents[1]
STANDARDIZED_PATH = BASE_DIR / "data/interim/standardized_numeric_panel.csv"
DEDUP_PATH = BASE_DIR / "data/interim/deduplicated_panel.csv"
MISSING_AUDIT_PATH = BASE_DIR / "data/interim/missingness_audit.csv"
LOG_PATH = BASE_DIR / "logs/dedup_missing_log.md"
MANIFEST_PATH = BASE_DIR / "data/registry/project_manifest.csv"
WORKFLOW_LOG_PATH = BASE_DIR / "logs/workflow_log.md"

ACCESS_DATE = "2026-03-29"
PROMPT_NAME = "Exec Prompt 21"

KEY_FIELDS = [
    "source_panel",
    "country_std",
    "firm_std",
    "service_std",
    "title_std",
    "filing_id",
    "sector_std",
    "metric_name",
    "metric_variant",
    "period_end_date",
]


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def safe_float(value: str) -> float | None:
    if value is None:
        return None
    stripped = str(value).strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def dedup_key(row: Dict[str, str]) -> Tuple[str, ...]:
    return tuple(row.get(field, "") for field in KEY_FIELDS)


def infer_missing_reason(row: Dict[str, str]) -> str:
    if row.get("metric_value_standardized", "").strip():
        return "not_missing"

    notes = row.get("notes", "")
    if "proxy_not_used_for_this_storefront" in notes:
        return "proxy_not_applicable_for_storefront"

    if row.get("unit_category") == "amount" and not row.get("metric_value_krw_nominal", "").strip():
        return "macro_reference_missing_for_conversion"

    if row.get("metric_value_numeric_raw", "").strip():
        return "standardized_value_missing_after_conversion"

    if row.get("metric_value_raw", "").strip():
        return "raw_value_present_but_non_numeric"

    return "source_value_not_available"


def resolve_group(group: List[Dict[str, str]]) -> Tuple[Dict[str, str], str, int]:
    ordered = sorted(group, key=lambda row: int(row["_source_order"]))
    if len(ordered) == 1:
        kept = dict(ordered[0])
        return kept, "unique_row", 0

    metric_name = ordered[0].get("metric_name", "")
    standardized_values = {row.get("metric_value_standardized", "") for row in ordered}

    if len(standardized_values) == 1:
        kept = dict(ordered[0])
        return kept, "identical_duplicate_keep_first", len(ordered) - 1

    if metric_name == "title_position":
        ranked = []
        for row in ordered:
            value = safe_float(row.get("metric_value_standardized", ""))
            rank_value = float("inf") if value is None else value
            ranked.append((rank_value, int(row["_source_order"]), row))
        kept = dict(sorted(ranked, key=lambda item: (item[0], item[1]))[0][2])
        return kept, "conflicting_title_position_keep_min_rank", len(ordered) - 1

    kept = dict(ordered[0])
    return kept, "conflicting_duplicate_keep_first", len(ordered) - 1


def build_outputs(rows: List[Dict[str, str]]) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], Dict[str, Counter], int]:
    grouped: Dict[Tuple[str, ...], List[Dict[str, str]]] = defaultdict(list)
    for index, row in enumerate(rows, start=1):
        row_copy = dict(row)
        row_copy["_source_order"] = str(index)
        grouped[dedup_key(row_copy)].append(row_copy)

    dedup_rows: List[Dict[str, str]] = []
    missing_rows: List[Dict[str, str]] = []

    source_duplicate_counter: Counter = Counter()
    metric_duplicate_counter: Counter = Counter()
    resolution_counter: Counter = Counter()
    missing_reason_counter: Counter = Counter()
    missing_metric_counter: Counter = Counter()

    dedup_fieldnames = [
        "dedup_row_id",
        *rows[0].keys(),
        "duplicate_group_size",
        "duplicate_dropped_count",
        "duplicate_flag",
        "duplicate_resolution",
        "source_duplicate_row_ids",
        "missing_flag",
        "missing_reason",
    ]

    audit_fieldnames = [
        "missing_audit_id",
        "dedup_row_id",
        "standardized_row_id",
        "source_panel",
        "country_std",
        "firm_std",
        "service_std",
        "title_std",
        "filing_id",
        "sector_std",
        "metric_name",
        "metric_variant",
        "period_end_date",
        "year_month",
        "year_quarter",
        "unit_category",
        "missing_field",
        "missing_flag",
        "missing_reason",
        "duplicate_flag",
        "duplicate_resolution",
        "carry_forward_used",
        "source_ref",
        "notes",
    ]

    missing_audit_id = 1
    for dedup_index, (_, group) in enumerate(sorted(grouped.items(), key=lambda item: min(int(row["_source_order"]) for row in item[1])), start=1):
        kept_row, resolution, dropped_count = resolve_group(group)
        duplicate_group_size = len(group)
        duplicate_flag = "yes" if duplicate_group_size > 1 else "no"

        if dropped_count:
            source_duplicate_counter[kept_row["source_panel"]] += dropped_count
            metric_duplicate_counter[kept_row["metric_name"]] += dropped_count
            resolution_counter[resolution] += dropped_count

        missing_reason = infer_missing_reason(kept_row)
        missing_flag = "yes" if missing_reason != "not_missing" else "no"
        if missing_flag == "yes":
            missing_reason_counter[missing_reason] += 1
            missing_metric_counter[kept_row["metric_name"]] += 1

        source_duplicate_row_ids = "|".join(row.get("standardized_row_id", "") for row in sorted(group, key=lambda row: int(row["_source_order"])))

        output_row = {field: kept_row.get(field, "") for field in rows[0].keys()}
        output_row.update(
            {
                "dedup_row_id": f"dedup_{dedup_index:05d}",
                "duplicate_group_size": str(duplicate_group_size),
                "duplicate_dropped_count": str(dropped_count),
                "duplicate_flag": duplicate_flag,
                "duplicate_resolution": resolution,
                "source_duplicate_row_ids": source_duplicate_row_ids,
                "missing_flag": missing_flag,
                "missing_reason": missing_reason,
            }
        )
        dedup_rows.append({field: output_row.get(field, "") for field in dedup_fieldnames})

        if missing_flag == "yes":
            audit_row = {
                "missing_audit_id": f"missing_{missing_audit_id:05d}",
                "dedup_row_id": output_row["dedup_row_id"],
                "standardized_row_id": output_row.get("standardized_row_id", ""),
                "source_panel": output_row.get("source_panel", ""),
                "country_std": output_row.get("country_std", ""),
                "firm_std": output_row.get("firm_std", ""),
                "service_std": output_row.get("service_std", ""),
                "title_std": output_row.get("title_std", ""),
                "filing_id": output_row.get("filing_id", ""),
                "sector_std": output_row.get("sector_std", ""),
                "metric_name": output_row.get("metric_name", ""),
                "metric_variant": output_row.get("metric_variant", ""),
                "period_end_date": output_row.get("period_end_date", ""),
                "year_month": output_row.get("year_month", ""),
                "year_quarter": output_row.get("year_quarter", ""),
                "unit_category": output_row.get("unit_category", ""),
                "missing_field": "metric_value_standardized",
                "missing_flag": "yes",
                "missing_reason": missing_reason,
                "duplicate_flag": duplicate_flag,
                "duplicate_resolution": resolution,
                "carry_forward_used": output_row.get("carry_forward_used", ""),
                "source_ref": output_row.get("source_ref", ""),
                "notes": output_row.get("notes", ""),
            }
            missing_rows.append({field: audit_row.get(field, "") for field in audit_fieldnames})
            missing_audit_id += 1

    counters = {
        "source_duplicate_counter": source_duplicate_counter,
        "metric_duplicate_counter": metric_duplicate_counter,
        "resolution_counter": resolution_counter,
        "missing_reason_counter": missing_reason_counter,
        "missing_metric_counter": missing_metric_counter,
    }
    total_removed = sum(int(row["duplicate_dropped_count"]) for row in dedup_rows)
    return dedup_rows, missing_rows, counters, total_removed


def format_counter(counter: Counter) -> List[str]:
    if not counter:
        return ["- 없음"]
    return [f"- `{key}`: `{value}`" for key, value in sorted(counter.items())]


def write_log(
    total_input_rows: int,
    dedup_rows: List[Dict[str, str]],
    missing_rows: List[Dict[str, str]],
    counters: Dict[str, Counter],
    total_removed: int,
) -> None:
    duplicate_group_count = sum(1 for row in dedup_rows if row["duplicate_flag"] == "yes")
    log_lines = [
        "# Dedup and Missingness Log",
        "",
        f"- Access date: `{ACCESS_DATE}`",
        f"- Prompt: `{PROMPT_NAME}`",
        f"- Input rows: `{total_input_rows}`",
        f"- Deduplicated rows: `{len(dedup_rows)}`",
        f"- Duplicate groups: `{duplicate_group_count}`",
        f"- Duplicate rows removed: `{total_removed}`",
        f"- Missing rows after deduplication: `{len(missing_rows)}`",
        "",
        "## Duplicate Source Counts",
        *format_counter(counters["source_duplicate_counter"]),
        "",
        "## Duplicate Metric Counts",
        *format_counter(counters["metric_duplicate_counter"]),
        "",
        "## Duplicate Resolution Counts",
        *format_counter(counters["resolution_counter"]),
        "",
        "## Missing Reason Counts",
        *format_counter(counters["missing_reason_counter"]),
        "",
        "## Missing Metric Counts",
        *format_counter(counters["missing_metric_counter"]),
        "",
        "## Resolution Rules",
        "- `identical_duplicate_keep_first`: 완전히 같은 값이 반복된 관측은 최초 행만 유지했다.",
        "- `conflicting_title_position_keep_min_rank`: 같은 작품이 같은 분기 스냅샷에서 여러 번 노출된 경우 가장 좋은 순위(최소값)를 유지했다.",
        "- 결측은 메우지 않고 그대로 보존했으며, `missing_reason`에 사유만 기록했다.",
        "",
        "## Notes",
        "- 중복은 모두 `webtoon_title_raw_panel`에서 발생했고, 플랫폼 storefront 중복 노출이 주원인이었다.",
        "- 결측은 dedup 이후 `webtoon` 영어 storefront의 `local_ip_proxy`, `translated_proxy`에만 남았고, 이는 해당 storefront에서 프록시를 사용하지 않은 구조적 결측으로 기록했다.",
        "- `carry_forward_used`는 표준화 단계 값을 그대로 유지했다.",
    ]
    LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")


def update_manifest() -> None:
    rows = read_csv(MANIFEST_PATH)
    additions = [
        {
            "artifact_type": "script",
            "path": "scripts/build_deduplicated_panel.py",
            "owner_step": PROMPT_NAME,
            "source_type": "local_code",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Builds a deduplicated long panel and a missingness audit from standardized numeric data.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/interim/deduplicated_panel.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_deduplicated_panel",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Deduplicated numeric panel with duplicate-resolution flags and missingness reason fields.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/interim/missingness_audit.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_missingness_audit",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Row-level audit of retained missing analytic values after deduplication.",
        },
        {
            "artifact_type": "log",
            "path": "logs/dedup_missing_log.md",
            "owner_step": PROMPT_NAME,
            "source_type": "local_log",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Summary log for duplicate-resolution rules, retained missingness, and row counts.",
        },
    ]

    existing_keys = {(row["owner_step"], row["path"]) for row in rows}
    for addition in additions:
        key = (addition["owner_step"], addition["path"])
        if key not in existing_keys:
            rows.append(addition)
            existing_keys.add(key)

    fieldnames = list(rows[0].keys())
    write_csv(MANIFEST_PATH, rows, fieldnames)


def update_workflow_log(dedup_rows: List[Dict[str, str]], missing_rows: List[Dict[str, str]], counters: Dict[str, Counter], total_removed: int) -> None:
    section_header = f"### {PROMPT_NAME}. 중복 제거와 결측 사유 기록"
    if WORKFLOW_LOG_PATH.exists():
        current = WORKFLOW_LOG_PATH.read_text(encoding="utf-8")
    else:
        current = ""
    if section_header in current:
        return

    total_input_rows = len(dedup_rows) + total_removed
    lines = [
        section_header,
        "",
        f"- `data/interim/deduplicated_panel.csv` 생성, 입력 `{total_input_rows}`행을 중복 해소 후 `{len(dedup_rows)}`행으로 정리",
        f"- 중복 제거 `{total_removed}`행은 `identical_duplicate_keep_first {counters['resolution_counter'].get('identical_duplicate_keep_first', 0)}`와 `conflicting_title_position_keep_min_rank {counters['resolution_counter'].get('conflicting_title_position_keep_min_rank', 0)}` 규칙으로 처리",
        f"- `data/interim/missingness_audit.csv`에 retain된 결측 `{len(missing_rows)}`행과 사유 `proxy_not_applicable_for_storefront`를 기록",
        "- `logs/dedup_missing_log.md`에 source/metric별 중복 분포와 결측 사유 분포를 정리",
    ]
    addition = "\n".join(lines) + "\n"
    if current and not current.endswith("\n"):
        current += "\n"
    WORKFLOW_LOG_PATH.write_text(current + addition, encoding="utf-8")


def main() -> None:
    standardized_rows = read_csv(STANDARDIZED_PATH)
    dedup_rows, missing_rows, counters, total_removed = build_outputs(standardized_rows)
    dedup_fieldnames = list(dedup_rows[0].keys()) if dedup_rows else []
    missing_fieldnames = list(missing_rows[0].keys()) if missing_rows else [
        "missing_audit_id",
        "dedup_row_id",
        "standardized_row_id",
        "source_panel",
        "country_std",
        "firm_std",
        "service_std",
        "title_std",
        "filing_id",
        "sector_std",
        "metric_name",
        "metric_variant",
        "period_end_date",
        "year_month",
        "year_quarter",
        "unit_category",
        "missing_field",
        "missing_flag",
        "missing_reason",
        "duplicate_flag",
        "duplicate_resolution",
        "carry_forward_used",
        "source_ref",
        "notes",
    ]

    write_csv(DEDUP_PATH, dedup_rows, dedup_fieldnames)
    write_csv(MISSING_AUDIT_PATH, missing_rows, missing_fieldnames)
    write_log(len(standardized_rows), dedup_rows, missing_rows, counters, total_removed)
    update_manifest()
    update_workflow_log(dedup_rows, missing_rows, counters, total_removed)


if __name__ == "__main__":
    main()
