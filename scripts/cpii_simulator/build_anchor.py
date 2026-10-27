#!/usr/bin/env python3
"""Build and verify the frozen empirical-rank anchor for the CPII comparator."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = PROJECT_ROOT / "data" / "processed" / "variable_panel_sector_quarter.csv"
DICTIONARY_PATH = PROJECT_ROOT / "data" / "registry" / "cpii_simulator_variable_dictionary.csv"
LEGACY_SUBINDEX_CODE_PATH = PROJECT_ROOT / "scripts" / "build_subindex_panels.py"
LEGACY_CPII_CODE_PATH = PROJECT_ROOT / "scripts" / "build_cpii_panels.py"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "cpii_simulator" / "anchor"
ANCHOR_JSON_PATH = OUTPUT_DIR / "POOL_SCQ_P01_P99_EMP_RANK_V1.json"
REFERENCE_CSV_PATH = OUTPUT_DIR / "POOL_SCQ_P01_P99_EMP_RANK_V1_reference_values.csv"
MANIFEST_JSON_PATH = OUTPUT_DIR / "anchor_manifest.json"
LOG_PATH = PROJECT_ROOT / "logs" / "cpii_simulator_anchor_manifest.md"

ANCHOR_VERSION = "POOL_SCQ_P01_P99_EMP_RANK_V1"
PRODUCT_SPEC_VERSION = "CPII_FIRM_INPUT_EQW_V1"
BUILD_DATE = "2026-09-02"
WINSOR_P_LOWER = 0.01
WINSOR_P_UPPER = 0.99
MISSING_SHARE_THRESHOLD = 0.40
MIN_RESEARCH_N = 20
MIN_UNIQUE_VALUES = 10
SUBINDEX_ORDER = ("I_reg", "I_risk", "I_market")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def quantile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("quantile requires at least one value")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * probability
    lower_index = math.floor(index)
    upper_index = math.ceil(index)
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = index - lower_index
    return ordered[lower_index] * (1.0 - fraction) + ordered[upper_index] * fraction


def signed_log1p(value: float) -> float:
    if value == 0:
        return 0.0
    return math.copysign(math.log1p(abs(value)), value)


def transform(raw_value: float, direction: int, rule: str) -> tuple[float, float]:
    directed = raw_value * direction
    if rule == "signed_log1p":
        return directed, signed_log1p(directed)
    if rule == "identity":
        return directed, directed
    raise ValueError(f"unsupported transform: {rule}")


def compact_float(value: float) -> str:
    return format(value, ".17g")


def build_artifacts() -> tuple[str, str, str, str]:
    source_rows = read_csv(SOURCE_PATH)
    dictionary_rows = read_csv(DICTIONARY_PATH)
    if len(source_rows) != 159:
        raise ValueError(f"expected 159 anchor rows, got {len(source_rows)}")

    profiles: dict[str, dict[str, Any]] = {}
    reference_records: list[dict[str, str]] = []
    active_components: dict[str, list[str]] = {axis: [] for axis in SUBINDEX_ORDER}

    for definition in dictionary_rows:
        name = definition["variable_name"]
        direction = int(definition["direction_code"])
        rule = definition["transform"]
        observed: list[tuple[str, float, float, float]] = []
        for row in source_rows:
            text = row.get(name, "").strip()
            if not text:
                continue
            raw = float(text)
            if not math.isfinite(raw):
                raise ValueError(f"{name}: non-finite source value")
            directed, transformed = transform(raw, direction, rule)
            observed.append((row["panel_sector_quarter_id"], raw, directed, transformed))

        if len(observed) < 2:
            calculated_status = "inactive"
            inactive_reason = "n_lt_2"
            lower = upper = None
            winsorized: list[tuple[str, float, float, float, float]] = []
            unique_count = len(observed)
        else:
            transformed_values = [item[3] for item in observed]
            lower = quantile(transformed_values, WINSOR_P_LOWER)
            upper = quantile(transformed_values, WINSOR_P_UPPER)
            winsorized = [
                (row_id, raw, directed, transformed, min(max(transformed, lower), upper))
                for row_id, raw, directed, transformed in observed
            ]
            unique_count = len({item[4] for item in winsorized})
            if unique_count < 2:
                calculated_status = "inactive"
                inactive_reason = "winsorized_zero_variation"
            else:
                calculated_status = "active"
                inactive_reason = ""

        if definition["status"] != calculated_status:
            raise ValueError(
                f"{name}: dictionary status {definition['status']} != calculated {calculated_status}"
            )

        low_support_reasons: list[str] = []
        if calculated_status == "active":
            if len(observed) < MIN_RESEARCH_N:
                low_support_reasons.append(f"reference_n_lt_{MIN_RESEARCH_N}")
            if unique_count < MIN_UNIQUE_VALUES:
                low_support_reasons.append(f"unique_count_lt_{MIN_UNIQUE_VALUES}")
            active_components[definition["subindex"]].append(name)

        reference_values = sorted(item[4] for item in winsorized) if calculated_status == "active" else []
        profile: dict[str, Any] = {
            "variable_name": name,
            "display_name_ko": definition["display_name_ko"],
            "subindex": definition["subindex"],
            "status": calculated_status,
            "direction_code": direction,
            "transform": rule,
            "source_n": len(observed),
            "unique_count_post_winsor": unique_count,
            "inactive_reason": inactive_reason,
            "low_support_reasons": low_support_reasons,
            "headline_status": (
                "inactive"
                if calculated_status == "inactive"
                else "research_beta_only"
                if low_support_reasons
                else "eligible_research_input"
            ),
            "raw_min": min((item[1] for item in observed), default=None),
            "raw_max": max((item[1] for item in observed), default=None),
            "winsor_lower_transformed": lower,
            "winsor_upper_transformed": upper,
            "reference_n": len(reference_values),
            "reference_winsorized_values": reference_values,
        }
        profiles[name] = profile

        if calculated_status == "active":
            sorted_records = sorted(winsorized, key=lambda item: (item[4], item[0]))
            for order, (row_id, raw, directed, transformed, clipped) in enumerate(sorted_records, start=1):
                reference_records.append(
                    {
                        "variable_name": name,
                        "reference_order": str(order),
                        "panel_sector_quarter_id": row_id,
                        "raw_value": compact_float(raw),
                        "directed_value": compact_float(directed),
                        "transformed_value": compact_float(transformed),
                        "winsorized_transformed_value": compact_float(clipped),
                        "clipped_flag": "yes" if clipped != transformed else "no",
                    }
                )

    for axis in active_components:
        active_components[axis].sort()

    active_names = sorted(name for names in active_components.values() for name in names)
    joint_complete_rows = [
        row for row in source_rows if all(row.get(name, "").strip() for name in active_names)
    ]
    source_scope = {
        "sectors": sorted({row["sector_std"] for row in source_rows if row.get("sector_std", "")}),
        "countries": sorted({row["country_std"] for row in source_rows if row.get("country_std", "")}),
        "period_start": min(row["year_quarter"] for row in source_rows if row.get("year_quarter", "")),
        "period_end": max(row["year_quarter"] for row in source_rows if row.get("year_quarter", "")),
        "independent_entity_count": None,
        "independent_entity_note": "not_available_in_aggregate_sector_country_quarter_anchor",
    }
    joint_support = {
        "active_feature_count": len(active_names),
        "complete_row_count": len(joint_complete_rows),
        "complete_row_share": len(joint_complete_rows) / len(source_rows),
        "complete_row_sectors": sorted({row["sector_std"] for row in joint_complete_rows}),
        "complete_row_countries": sorted({row["country_std"] for row in joint_complete_rows}),
        "eligibility": "insufficient_joint_reference_support",
        "prohibited_claims": [
            "company_empirical_percentile",
            "empirical_pair_gap_percentile",
            "industry_representative_distribution",
        ],
    }
    low_support = [
        name for name, profile in profiles.items() if profile["status"] == "active" and profile["low_support_reasons"]
    ]
    package = {
        "anchor_version": ANCHOR_VERSION,
        "product_spec_version": PRODUCT_SPEC_VERSION,
        "build_date": BUILD_DATE,
        "release_status": "research_beta_due_to_low_support_active_features" if low_support else "research_release",
        "source": {
            "relative_path": str(SOURCE_PATH.relative_to(PROJECT_ROOT)),
            "row_count": len(source_rows),
            "sha256": sha256(SOURCE_PATH),
            "scope": source_scope,
            "joint_support": joint_support,
        },
        "method": {
            "direction": "higher_after_direction_means_higher_burden",
            "winsor_p_lower": WINSOR_P_LOWER,
            "winsor_p_upper": WINSOR_P_UPPER,
            "quantile_rule": "linear_interpolation_index_(n-1)*p",
            "normalization_rule": "existing_tie_midrank_and_novel_value_bisect_half_step",
            "normalization_formula": "((bisect_left+1)+bisect_right)/2 - 1, divided by n-1",
            "missing_share_threshold": MISSING_SHARE_THRESHOLD,
            "subindex_weighting": "equal_over_observed_subject_to_threshold",
            "top_level_weighting": "equal_over_observed_axes_subject_to_threshold",
            "strict_comparator_mode": "all_ten_active_features_and_all_three_axes",
        },
        "subindex_order": list(SUBINDEX_ORDER),
        "active_components": active_components,
        "top_level_weights": {axis: 1.0 / 3.0 for axis in SUBINDEX_ORDER},
        "low_support_active_features": sorted(low_support),
        "low_support_effective_weight": sum(
            (1.0 / len(active_components[profiles[name]["subindex"]])) * (1.0 / len(SUBINDEX_ORDER))
            for name in low_support
        ),
        "profiles": profiles,
    }
    anchor_json = json.dumps(package, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    reference_fields = [
        "variable_name",
        "reference_order",
        "panel_sector_quarter_id",
        "raw_value",
        "directed_value",
        "transformed_value",
        "winsorized_transformed_value",
        "clipped_flag",
    ]
    reference_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(reference_buffer, fieldnames=reference_fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(reference_records)
    reference_csv = reference_buffer.getvalue()

    component_counts = {axis: len(names) for axis, names in active_components.items()}
    manifest = {
        "anchor_version": ANCHOR_VERSION,
        "product_spec_version": PRODUCT_SPEC_VERSION,
        "build_date": BUILD_DATE,
        "source_row_count": len(source_rows),
        "active_component_counts": component_counts,
        "inactive_features": sorted(name for name, p in profiles.items() if p["status"] == "inactive"),
        "low_support_active_features": sorted(low_support),
        "low_support_effective_weight": package["low_support_effective_weight"],
        "joint_complete_reference_count": joint_support["complete_row_count"],
        "joint_complete_reference_share": joint_support["complete_row_share"],
        "joint_support_eligibility": joint_support["eligibility"],
        "source_scope": source_scope,
        "input_sha256": {
            str(path.relative_to(PROJECT_ROOT)): sha256(path)
            for path in (SOURCE_PATH, DICTIONARY_PATH, LEGACY_SUBINDEX_CODE_PATH, LEGACY_CPII_CODE_PATH)
        },
        "output_content_sha256": {
            ANCHOR_JSON_PATH.name: hashlib.sha256(anchor_json.encode("utf-8")).hexdigest(),
            REFERENCE_CSV_PATH.name: hashlib.sha256(reference_csv.encode("utf-8")).hexdigest(),
        },
    }
    manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    log_lines = [
        "# CPII Simulator Frozen Anchor Manifest",
        "",
        f"- Build date: `{BUILD_DATE}`",
        f"- Product specification: `{PRODUCT_SPEC_VERSION}`",
        f"- Anchor version: `{ANCHOR_VERSION}`",
        f"- Source: `{SOURCE_PATH.relative_to(PROJECT_ROOT)}`",
        f"- Source rows: `{len(source_rows)}`",
        f"- Source SHA-256: `{package['source']['sha256']}`",
        f"- Release status: `{package['release_status']}`",
        f"- Joint-complete rows (all ten active features): `{joint_support['complete_row_count']}/{len(source_rows)}`",
        f"- Joint-support eligibility: `{joint_support['eligibility']}`",
        f"- Low-support features' effective CPII weight: `{package['low_support_effective_weight']:.4%}`",
        "",
        "## Frozen method",
        "",
        "- Direction align -> signed_log1p/identity -> Type-7 P1/P99 winsorization -> empirical rank normalization.",
        "- Exact legacy parity is retained: ties use average rank; a novel interior value uses the existing bisect half-step.",
        "- The selected company set never changes the reference vector.",
        "- Strict client comparisons require all ten active variables and all three subindices.",
        "- The composite is a weighted average of feature-level marginal reference positions, not a company percentile.",
        "- Company-percentile, empirical pair-gap percentile, and industry-representative claims are disabled until joint support is expanded.",
        "",
        "## Profile summary",
        "",
        "| Variable | Status | N | Unique | Transformed P1 | Transformed P99 | Headline status |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for name in sorted(profiles):
        profile = profiles[name]
        lower_text = "" if profile["winsor_lower_transformed"] is None else f"{profile['winsor_lower_transformed']:.10g}"
        upper_text = "" if profile["winsor_upper_transformed"] is None else f"{profile['winsor_upper_transformed']:.10g}"
        log_lines.append(
            f"| `{name}` | {profile['status']} | {profile['source_n']} | "
            f"{profile['unique_count_post_winsor']} | {lower_text} | {upper_text} | "
            f"{profile['headline_status']} |"
        )
    log_lines.extend(
        [
            "",
            "## Low-support decision",
            "",
            f"- Active features below the documented support floor: `{','.join(sorted(low_support))}`.",
            "- They are retained solely for exact reduced-spec parity and visibly flagged `research_beta_only`.",
            "- No production headline, legal conclusion, or direct monetary claim may rely on these features without a new anchor version.",
            "",
            "## Output hashes",
            "",
            f"- `{ANCHOR_JSON_PATH.relative_to(PROJECT_ROOT)}`: `{manifest['output_content_sha256'][ANCHOR_JSON_PATH.name]}`",
            f"- `{REFERENCE_CSV_PATH.relative_to(PROJECT_ROOT)}`: `{manifest['output_content_sha256'][REFERENCE_CSV_PATH.name]}`",
            "",
        ]
    )
    log_text = "\n".join(log_lines)
    return anchor_json, reference_csv, manifest_json, log_text


def validate_semantics(anchor_json: str, reference_csv: str) -> None:
    package = json.loads(anchor_json)
    if package["anchor_version"] != ANCHOR_VERSION:
        raise ValueError("anchor version mismatch")
    if package["source"]["row_count"] != 159:
        raise ValueError("source row count mismatch")
    if {axis: len(names) for axis, names in package["active_components"].items()} != {
        "I_reg": 3,
        "I_risk": 4,
        "I_market": 3,
    }:
        raise ValueError("active component count mismatch")
    if package["low_support_active_features"] != ["cross_market_transfer_index", "foreign_dependency_ratio"]:
        raise ValueError("low-support feature decision changed")
    for name, profile in package["profiles"].items():
        values = profile["reference_winsorized_values"]
        if profile["status"] == "active":
            if len(values) != profile["reference_n"] or values != sorted(values):
                raise ValueError(f"{name}: invalid frozen reference vector")
            if not values or values[0] < profile["winsor_lower_transformed"] or values[-1] > profile["winsor_upper_transformed"]:
                raise ValueError(f"{name}: reference vector outside winsor bounds")
        elif values:
            raise ValueError(f"{name}: inactive profile has reference values")
    csv_rows = list(csv.DictReader(io.StringIO(reference_csv)))
    expected_rows = sum(profile["reference_n"] for profile in package["profiles"].values())
    if len(csv_rows) != expected_rows:
        raise ValueError("reference CSV row count mismatch")


def write_or_check(check: bool) -> None:
    anchor_json, reference_csv, manifest_json, log_text = build_artifacts()
    validate_semantics(anchor_json, reference_csv)
    expected = {
        ANCHOR_JSON_PATH: anchor_json,
        REFERENCE_CSV_PATH: reference_csv,
        MANIFEST_JSON_PATH: manifest_json,
        LOG_PATH: log_text,
    }
    if check:
        for path, content in expected.items():
            if not path.exists():
                raise ValueError(f"missing generated anchor artifact: {path.relative_to(PROJECT_ROOT)}")
            if path.read_text(encoding="utf-8") != content:
                raise ValueError(f"stale or modified anchor artifact: {path.relative_to(PROJECT_ROOT)}")
        print(
            "PASS frozen anchor: 159 source rows; active counts=3/4/3; "
            "two low-support features flagged; hashes and serialized vectors match"
        )
        return

    mismatched_existing = [
        path for path, content in expected.items() if path.exists() and path.read_text(encoding="utf-8") != content
    ]
    if mismatched_existing:
        names = ", ".join(str(path.relative_to(PROJECT_ROOT)) for path in mismatched_existing)
        raise ValueError(
            "refusing to overwrite changed content under an existing anchor version; "
            f"create a new ANCHOR_VERSION instead ({names})"
        )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    for path, content in expected.items():
        path.write_text(content, encoding="utf-8")
    print(f"WROTE frozen anchor: {ANCHOR_JSON_PATH.relative_to(PROJECT_ROOT)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify generated artifacts without rewriting")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        write_or_check(args.check)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"FAIL frozen anchor: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
