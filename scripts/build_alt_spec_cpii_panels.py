#!/usr/bin/env python3

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ACCESS_DATE = "2026-03-29"
PROMPT_NAME = "Post Step 06"

PROJECT_MANIFEST_PATH = ROOT / "data/registry/project_manifest.csv"
WORKFLOW_LOG_PATH = ROOT / "logs/workflow_log.md"
LOG_PATH = ROOT / "logs/alt_spec_cpii_storage_log.md"
SUMMARY_PATH = ROOT / "data/processed/cpii_alt_spec_storage_summary.csv"

PANEL_CONFIGS = [
    {
        "panel_level": "sector_country_quarter",
        "input_path": ROOT / "data/processed/cpii_panel_sector_country_quarter.csv",
        "alt_a_path": ROOT / "data/processed/cpii_panel_sector_country_quarter_alt_a.csv",
        "alt_b_path": ROOT / "data/processed/cpii_panel_sector_country_quarter_alt_b.csv",
        "alt_a_spec_code": "CPII_SCQ_ALT_A_REGRISK_V1",
        "alt_b_spec_code": "CPII_SCQ_ALT_B_COMPLETE_V1",
    },
    {
        "panel_level": "sector_quarter",
        "input_path": ROOT / "data/processed/cpii_panel_sector_quarter.csv",
        "alt_a_path": ROOT / "data/processed/cpii_panel_sector_quarter_alt_a.csv",
        "alt_b_path": ROOT / "data/processed/cpii_panel_sector_quarter_alt_b.csv",
        "alt_a_spec_code": "CPII_SQ_ALT_A_REGRISK_V1",
        "alt_b_spec_code": "CPII_SQ_ALT_B_COMPLETE_V1",
    },
    {
        "panel_level": "firm_country_quarter",
        "input_path": ROOT / "data/processed/cpii_panel_firm_country_quarter.csv",
        "alt_a_path": ROOT / "data/processed/cpii_panel_firm_country_quarter_alt_a.csv",
        "alt_b_path": ROOT / "data/processed/cpii_panel_firm_country_quarter_alt_b.csv",
        "alt_a_spec_code": "CPII_FCQ_ALT_A_REGRISK_V1",
        "alt_b_spec_code": "CPII_FCQ_ALT_B_COMPLETE_V1",
    },
]

SUBINDEX_FIELDS = ["I_reg", "I_risk", "I_market"]
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

SPECS = {
    "alt_a": {
        "label": "Alternative A",
        "weights": {"I_reg": 0.4, "I_risk": 0.4, "I_market": 0.2},
        "require_complete": False,
        "min_observed": 2,
        "weight_scheme": "reg_risk_emphasis_reweighted_over_observed",
    },
    "alt_b": {
        "label": "Alternative B",
        "weights": {"I_reg": 1.0 / 3.0, "I_risk": 1.0 / 3.0, "I_market": 1.0 / 3.0},
        "require_complete": True,
        "min_observed": 3,
        "weight_scheme": "strict_complete_case_equal_weight",
    },
}


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        normalized_rows = []
        for row in rows:
            normalized_rows.append({field: row.get(field, "") for field in fieldnames})
        writer.writerows(normalized_rows)


def to_float(value: str | None) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.10f}"


def join_nonempty(values: list[str]) -> str:
    return "|".join(value for value in values if value)


def compute_alt_cpii_fields(
    row: dict[str, str],
    spec_key: str,
    spec_code: str,
) -> dict[str, str]:
    spec = SPECS[spec_key]
    weights = spec["weights"]
    observed_names: list[str] = []
    missing_names: list[str] = []
    observed_weight_raw = 0.0
    weighted_sum = 0.0

    for field in SUBINDEX_FIELDS:
        value = to_float(row.get(field, ""))
        if value is None:
            missing_names.append(field)
            continue
        observed_names.append(field)
        weight = float(weights[field])
        observed_weight_raw += weight
        weighted_sum += value * weight

    if spec["require_complete"] and missing_names:
        cpii = None
        status = "not_computed"
        weight_sum = None
        raw_score = None
    elif len(observed_names) < int(spec["min_observed"]) or observed_weight_raw <= 0.0:
        cpii = None
        status = "not_computed"
        weight_sum = None
        raw_score = None
    else:
        cpii = weighted_sum / observed_weight_raw
        status = "computed"
        weight_sum = 1.0
        raw_score = cpii / 100.0

    return {
        "baseline_spec_code": row.get("spec_code", ""),
        "baseline_CPII": row.get("CPII", ""),
        "baseline_cpii_status": row.get("cpii_status", ""),
        "baseline_cpii_weight_sum": row.get("cpii_weight_sum", ""),
        "alt_spec_variant": spec_key,
        "alt_spec_label": str(spec["label"]),
        "alt_require_complete_flag": "yes" if spec["require_complete"] else "no",
        "alt_min_observed_subindex_count": str(spec["min_observed"]),
        "top_level_observed_weight_raw": fmt(observed_weight_raw if observed_names else None),
        "spec_code": spec_code,
        "top_level_weight_scheme": str(spec["weight_scheme"]),
        "top_level_base_weight_reg": fmt(float(weights["I_reg"])),
        "top_level_base_weight_risk": fmt(float(weights["I_risk"])),
        "top_level_base_weight_market": fmt(float(weights["I_market"])),
        "cpii_observed_subindex_count": str(len(observed_names)),
        "cpii_missing_subindex_count": str(len(missing_names)),
        "cpii_missing_share": fmt(len(missing_names) / 3.0),
        "cpii_subindex_names_used": join_nonempty(observed_names),
        "cpii_subindex_names_missing": join_nonempty(missing_names),
        "cpii_weight_sum": fmt(weight_sum),
        "cpii_raw_score": fmt(raw_score),
        "cpii_status": status,
        "CPII": fmt(cpii),
    }


def append_unique_rows(
    path: Path,
    fieldnames: list[str],
    new_rows: list[dict[str, str]],
    unique_keys: list[str],
) -> None:
    existing_rows: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()
    if path.exists():
        existing_rows, _ = read_csv(path)
        for row in existing_rows:
            seen.add(tuple(row.get(key, "") for key in unique_keys))
    for row in new_rows:
        normalized = {field: str(row.get(field, "")) for field in fieldnames}
        key = tuple(normalized[key_field] for key_field in unique_keys)
        if key not in seen:
            existing_rows.append(normalized)
            seen.add(key)
    write_csv(path, existing_rows, fieldnames)


def append_workflow_section(path: Path, header: str, bullets: list[str]) -> None:
    section_lines = ["", f"### {header}", ""]
    section_lines.extend(f"- {bullet}" for bullet in bullets)
    section = "\n".join(section_lines) + "\n"
    existing = path.read_text(encoding="utf-8") if path.exists() else "# Workflow Log\n"
    if header in existing:
        return
    path.write_text(existing.rstrip() + section, encoding="utf-8")


def build_alt_panel(
    rows: list[dict[str, str]],
    fieldnames: list[str],
    spec_key: str,
    spec_code: str,
) -> tuple[list[dict[str, str]], dict[str, str]]:
    extra_fields = [
        "baseline_spec_code",
        "baseline_CPII",
        "baseline_cpii_status",
        "baseline_cpii_weight_sum",
        "alt_spec_variant",
        "alt_spec_label",
        "alt_require_complete_flag",
        "alt_min_observed_subindex_count",
        "top_level_observed_weight_raw",
    ]
    out_rows: list[dict[str, str]] = []
    computed_rows = 0
    identical_rows = 0
    differing_rows = 0

    for row in rows:
        alt_fields = compute_alt_cpii_fields(row, spec_key, spec_code)
        out_row = dict(row)
        out_row.update(alt_fields)
        out_rows.append(out_row)
        if out_row["cpii_status"] == "computed":
            computed_rows += 1
            baseline_value = to_float(out_row.get("baseline_CPII", ""))
            alt_value = to_float(out_row.get("CPII", ""))
            if baseline_value is not None and alt_value is not None:
                if abs(baseline_value - alt_value) < 1e-12:
                    identical_rows += 1
                else:
                    differing_rows += 1

    out_fieldnames = fieldnames[:]
    for extra_field in extra_fields:
        if extra_field not in out_fieldnames:
            out_fieldnames.append(extra_field)

    summary = {
        "total_rows": str(len(rows)),
        "computed_rows": str(computed_rows),
        "not_computed_rows": str(len(rows) - computed_rows),
        "computed_share": fmt(computed_rows / len(rows) if rows else None),
        "identical_to_baseline_rows": str(identical_rows),
        "differs_from_baseline_rows": str(differing_rows),
    }
    return out_rows, {"fieldnames": out_fieldnames, **summary}


def update_project_manifest(new_entries: list[dict[str, str]]) -> None:
    append_unique_rows(PROJECT_MANIFEST_PATH, PROJECT_MANIFEST_FIELDS, new_entries, ["path"])


def main() -> None:
    summary_rows: list[dict[str, str]] = []
    manifest_entries: list[dict[str, str]] = [
        {
            "artifact_type": "script",
            "path": "scripts/build_alt_spec_cpii_panels.py",
            "owner_step": PROMPT_NAME,
            "source_type": "local_code",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Builds row-level CPII panels for alternative specifications A and B across sector-country, sector, and firm-country grains.",
        },
        {
            "artifact_type": "dataset",
            "path": "data/processed/cpii_alt_spec_storage_summary.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_analysis_table",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Summary of total rows, computed rows, and baseline retention for Alt A and Alt B CPII storage outputs.",
        },
        {
            "artifact_type": "log",
            "path": "logs/alt_spec_cpii_storage_log.md",
            "owner_step": PROMPT_NAME,
            "source_type": "local_log",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Log documenting direct row-level storage of alternative CPII specifications A and B.",
        },
    ]

    for config in PANEL_CONFIGS:
        rows, fieldnames = read_csv(config["input_path"])
        baseline_computed_rows = sum(1 for row in rows if row.get("cpii_status", "") == "computed")

        for spec_key, output_path, spec_code in [
            ("alt_a", config["alt_a_path"], config["alt_a_spec_code"]),
            ("alt_b", config["alt_b_path"], config["alt_b_spec_code"]),
        ]:
            alt_rows, meta = build_alt_panel(rows, fieldnames, spec_key, spec_code)
            out_fieldnames = list(meta.pop("fieldnames"))  # type: ignore[arg-type]
            write_csv(output_path, alt_rows, out_fieldnames)

            computed_rows = int(meta["computed_rows"])
            summary_rows.append(
                {
                    "panel_level": config["panel_level"],
                    "alt_spec_variant": spec_key,
                    "spec_code": spec_code,
                    "total_rows": meta["total_rows"],
                    "baseline_computed_rows": str(baseline_computed_rows),
                    "computed_rows": meta["computed_rows"],
                    "not_computed_rows": meta["not_computed_rows"],
                    "computed_share": meta["computed_share"],
                    "retention_vs_baseline": fmt(computed_rows / baseline_computed_rows if baseline_computed_rows else None),
                    "identical_to_baseline_rows": meta["identical_to_baseline_rows"],
                    "differs_from_baseline_rows": meta["differs_from_baseline_rows"],
                    "input_panel_path": str(config["input_path"].relative_to(ROOT)),
                    "output_panel_path": str(output_path.relative_to(ROOT)),
                }
            )

            manifest_entries.append(
                {
                    "artifact_type": "dataset",
                    "path": str(output_path.relative_to(ROOT)),
                    "owner_step": PROMPT_NAME,
                    "source_type": "derived_analysis_table",
                    "source_url": "",
                    "access_date": ACCESS_DATE,
                    "status": "created",
                    "notes": f"Direct row-level {spec_key} CPII panel at {config['panel_level']} grain.",
                }
            )

    summary_fieldnames = [
        "panel_level",
        "alt_spec_variant",
        "spec_code",
        "total_rows",
        "baseline_computed_rows",
        "computed_rows",
        "not_computed_rows",
        "computed_share",
        "retention_vs_baseline",
        "identical_to_baseline_rows",
        "differs_from_baseline_rows",
        "input_panel_path",
        "output_panel_path",
    ]
    write_csv(SUMMARY_PATH, summary_rows, summary_fieldnames)

    lines = [
        "# Alternative CPII Storage Log",
        "",
        f"기준 시점: `{ACCESS_DATE}`",
        "",
        "## 목적",
        "",
        "- 기준 사양 외 대체 사양 A/B의 row-level CPII 패널을 직접 CSV로 저장",
        "- sector-country-quarter, sector-quarter, firm-country-quarter 세 grain 모두에 대해 동일한 저장 규칙을 적용",
        "- 최종 강건성 감사에서 Q4를 file-level 기준으로 판정 가능하게 만들기",
        "",
        "## 저장 규칙",
        "",
        "- `alt_a`: regulation/risk emphasis weights `(0.4, 0.4, 0.2)` with observed-weight renormalization",
        "- `alt_b`: strict complete-case equal-weight CPII requiring all three subindices",
        "- 각 alt panel은 baseline row를 그대로 유지하되 `baseline_*` 비교 필드와 새로운 top-level CPII 필드를 함께 저장",
        "",
        "## 저장 결과",
        "",
        "| panel_level | alt_spec | total_rows | baseline_computed_rows | computed_rows | retention_vs_baseline | identical_to_baseline_rows | differs_from_baseline_rows |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary_rows:
        lines.append(
            f"| {row['panel_level']} | {row['alt_spec_variant']} | {row['total_rows']} | {row['baseline_computed_rows']} | {row['computed_rows']} | {row['retention_vs_baseline']} | {row['identical_to_baseline_rows']} | {row['differs_from_baseline_rows']} |"
        )

    lines.extend(
        [
            "",
            "## 해석",
            "",
            "- `alt_a`는 baseline과 같은 row universe를 유지하면서 가중치만 변경하므로 baseline retention이 1.0으로 유지되는 패널이 많다.",
            "- `alt_b`는 complete-case를 요구하므로 baseline 대비 retention이 낮아진다.",
            "- 이 저장 파일들은 기존 `spec_robustness_summary.csv`와 `spec_comparison_chart.png`의 row-level 근거 자료 역할을 한다.",
            "",
        ]
    )
    LOG_PATH.write_text("\n".join(lines), encoding="utf-8")

    update_project_manifest(manifest_entries)

    workflow_bullets = [
        "`cpii_panel_sector_country_quarter_alt_a.csv`, `alt_b.csv`, `cpii_panel_sector_quarter_alt_a.csv`, `alt_b.csv`, `cpii_panel_firm_country_quarter_alt_a.csv`, `alt_b.csv`를 생성",
        "`data/processed/cpii_alt_spec_storage_summary.csv`에 패널별 계산 행 수와 baseline retention을 정리",
        "`logs/alt_spec_cpii_storage_log.md`에 대체 사양 저장 규칙과 row-level 직접 저장 완료 상태를 기록",
    ]
    append_workflow_section(WORKFLOW_LOG_PATH, "Post Step 06. 대체 사양 A/B row-level CPII 패널 저장", workflow_bullets)


if __name__ == "__main__":
    main()
