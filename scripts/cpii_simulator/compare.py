#!/usr/bin/env python3
"""Two-company and n-company comparison views over the single CPII engine."""

from __future__ import annotations

import argparse
import csv
from itertools import combinations
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.cpii_simulator.engine import flatten_score, read_company_csv, score_rows
    from scripts.cpii_simulator.validate_input import (
        COMPARABILITY_FIELDS,
        MONETIZATION_COMPARABILITY_FIELDS,
        observation_id_error,
        validate_company_rows,
    )
else:
    from .engine import flatten_score, read_company_csv, score_rows
    from .validate_input import (
        COMPARABILITY_FIELDS,
        MONETIZATION_COMPARABILITY_FIELDS,
        observation_id_error,
        validate_company_rows,
    )


VERSION_FIELDS = ("method_version", "anchor_version")
SENSITIVITY_SUMMARY_FIELDS = (
    "pair_id",
    "observation_id_a",
    "observation_id_b",
    "input_range_assessed",
    "input_range_feature_count_a",
    "input_range_feature_count_b",
    "input_range_feature_count_total",
    "sensitivity_min_points",
    "sensitivity_max_points",
    "sign_stable",
    "interpretation_status",
    "positive_specification_share_descriptive",
    "probability_interpretation_allowed",
    "range_type",
    "empirical_pair_gap_percentile",
    "empirical_pair_gap_percentile_status",
    "historical_method_sensitivity_median_abs_points",
    "historical_method_sensitivity_mean_abs_points",
    "baseline_gap_method_context",
    "low_support_effective_weight",
    "dependency_warnings_a",
    "dependency_warnings_b",
)
SENSITIVITY_VARIANT_FIELDS = (
    "pair_id",
    "observation_id_a",
    "observation_id_b",
    "input_range_assessed",
    "input_range_feature_count_a",
    "input_range_feature_count_b",
    "specification",
    "category",
    "score_a",
    "score_b",
    "delta_cpii_points_a_minus_b",
)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def cohort_id(row: Mapping[str, Any]) -> str:
    """Return an injective, serialization-safe identifier for a cohort tuple."""
    return json.dumps(
        [_text(row.get(field)) for field in COMPARABILITY_FIELDS],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _validated_headline_rows(
    scored_rows: Iterable[Mapping[str, Any]],
    *,
    operation: str,
) -> list[dict[str, Any]]:
    """Copy and validate rows before producing any headline comparison output."""
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    common_versions: tuple[str, str] | None = None
    for position, source in enumerate(scored_rows, start=1):
        row = dict(source)
        raw_row_id = row.get("observation_id")
        row_id = "" if raw_row_id is None else str(raw_row_id)
        if not row_id.strip():
            raise ValueError(f"{operation} requires a nonblank observation_id at row {position}")
        id_error = observation_id_error(raw_row_id)
        if id_error:
            raise ValueError(f"{operation} has invalid observation_id at row {position}: {id_error}")
        if row_id in seen_ids:
            raise ValueError(f"{operation} requires unique observation_id values; duplicate: {row_id}")
        seen_ids.add(row_id)
        row["observation_id"] = row_id

        if row.get("score_mode") != "strict_all_active":
            raise ValueError(f"{operation} requires strict all-active CPII scores")
        try:
            cpii = float(row.get("CPII"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{operation} requires a finite CPII value for {row_id}") from exc
        if not math.isfinite(cpii) or not 0 <= cpii <= 100:
            raise ValueError(f"{operation} requires a finite CPII value in [0, 100] for {row_id}")
        if row.get("score_eligible") != "yes":
            raise ValueError(f"{operation} requires score_eligible=yes for {row_id}")
        row["CPII"] = cpii

        if row.get("market_common_exposure_adjusted") != "yes":
            raise ValueError(
                f"{operation} requires market_common_exposure_adjusted=yes for {row_id}"
            )
        try:
            exposure_factor = float(row.get("company_exposure_factor"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{operation} requires a valid company_exposure_factor for {row_id}") from exc
        if not math.isfinite(exposure_factor) or not 0 <= exposure_factor <= 1:
            raise ValueError(f"{operation} requires company_exposure_factor in [0, 1] for {row_id}")
        row["company_exposure_factor"] = exposure_factor

        for field in COMPARABILITY_FIELDS:
            raw_value = "" if row.get(field) is None else str(row.get(field))
            if raw_value != raw_value.strip():
                raise ValueError(
                    f"{operation} does not allow leading or trailing whitespace in {field} for {row_id}"
                )

        versions = (
            _text(row.get("method_version")),
            _text(row.get("anchor_version")),
        )
        if not all(versions):
            raise ValueError(f"{operation} requires nonblank method_version and anchor_version")
        if common_versions is None:
            common_versions = versions
        elif versions != common_versions:
            raise ValueError(f"{operation} cannot mix method_version or anchor_version values")
        rows.append(row)
    return rows


def _rank_descending(values: list[tuple[str, float]]) -> dict[str, float]:
    ordered = sorted(values, key=lambda item: (-item[1], item[0]))
    ranks: dict[str, float] = {}
    index = 0
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[index][1]:
            end += 1
        average_rank = ((index + 1) + (end + 1)) / 2.0
        for position in range(index, end + 1):
            ranks[ordered[position][0]] = average_rank
        index = end + 1
    return ranks


def rank_companies(scored_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = _validated_headline_rows(scored_rows, operation="headline ranking")
    ranks: dict[str, float] = {}
    cohorts: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        cohorts.setdefault(cohort_id(row), []).append(row)
    for members in cohorts.values():
        ranks.update(_rank_descending([(str(row["observation_id"]), float(row["CPII"])) for row in members]))
    ranked = []
    for row in rows:
        item = flatten_score(row)
        item["cohort_id"] = cohort_id(row)
        item["cohort_size"] = len(cohorts[cohort_id(row)])
        item["burden_rank_desc"] = ranks[str(row["observation_id"])]
        ranked.append(item)
    return sorted(ranked, key=lambda row: (row["burden_rank_desc"], row["observation_id"]))


def _pair_comparability(a: Mapping[str, Any], b: Mapping[str, Any]) -> tuple[bool, str]:
    mismatches = [
        field
        for field in COMPARABILITY_FIELDS
        if ("" if a.get(field) is None else str(a.get(field))) != _text(a.get(field))
        or ("" if b.get(field) is None else str(b.get(field))) != _text(b.get(field))
        or not _text(a.get(field))
        or not _text(b.get(field))
        or _text(a.get(field)) != _text(b.get(field))
    ]
    for field in VERSION_FIELDS:
        if field in a or field in b:
            if (
                not _text(a.get(field))
                or not _text(b.get(field))
                or _text(a.get(field)) != _text(b.get(field))
            ):
                mismatches.append(field)
    return not mismatches, "|".join(mismatches)


def _pair_type(a: Mapping[str, Any], b: Mapping[str, Any], comparable: bool) -> str:
    groups = {str(a.get("company_group", "")), str(b.get("company_group", ""))}
    evidence_ok = all(
        row.get("input_quality") in {"A", "B", "SYNTHETIC"}
        and row.get("construction_mode") in {"direct", "derived"}
        for row in (a, b)
    )
    if comparable and evidence_ok and groups == {"domestic", "foreign"}:
        return "reverse_discrimination_hypothesis_related_structural_burden_gap"
    return "structural_burden_gap"


def pair_records(scored_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = _validated_headline_rows(scored_rows, operation="pair comparison")
    records: list[dict[str, Any]] = []
    for a, b in combinations(rows, 2):
        comparable, mismatch_fields = _pair_comparability(a, b)
        raw_gap = float(a["CPII"]) - float(b["CPII"])
        gap = raw_gap if comparable else None
        pair_type = _pair_type(a, b, comparable)
        domestic_minus_foreign: float | None = None
        if pair_type == "reverse_discrimination_hypothesis_related_structural_burden_gap":
            domestic_minus_foreign = raw_gap if a.get("company_group") == "domestic" else -raw_gap
        monetary_mismatches = [
            field
            for field in MONETIZATION_COMPARABILITY_FIELDS
            if not _text(a.get(field))
            or not _text(b.get(field))
            or _text(a.get(field)) != _text(b.get(field))
        ]
        records.append(
            {
                "pair_id": f"{a['observation_id']}__vs__{b['observation_id']}",
                "observation_id_a": a["observation_id"],
                "company_name_a": a.get("company_name", ""),
                "company_group_a": a.get("company_group", ""),
                "observation_id_b": b["observation_id"],
                "company_name_b": b.get("company_name", ""),
                "company_group_b": b.get("company_group", ""),
                "cpii_a": float(a["CPII"]),
                "cpii_b": float(b["CPII"]),
                "delta_cpii_points_a_minus_b": gap,
                "absolute_gap_points": None if gap is None else abs(gap),
                "pair_type": pair_type,
                "domestic_minus_foreign_points": domestic_minus_foreign,
                "comparable": "yes" if comparable else "no",
                "pair_eligible": "yes" if comparable else "no",
                "monetization_eligible": "yes" if comparable and not monetary_mismatches else "no",
                "reverse_discrimination_label_eligible": (
                    "yes"
                    if pair_type == "reverse_discrimination_hypothesis_related_structural_burden_gap"
                    else "no"
                ),
                "mismatch_fields": mismatch_fields,
                "monetization_mismatch_fields": "|".join(monetary_mismatches),
                "interpretation_gate": (
                    "research_beta_feature_marginal_position_only"
                    if comparable
                    else "blocked_incomparable_metadata"
                ),
                "empirical_pair_gap_percentile": None,
                "empirical_pair_gap_percentile_status": "not_available_insufficient_joint_reference_support",
                "legal_causal_disclaimer": "not_a_finding_of_discrimination_illegality_damage_or_causality",
                "method_version": a.get("method_version", ""),
                "anchor_version": a.get("anchor_version", ""),
            }
        )
    return records


def pairwise_matrix(scored_rows: Iterable[Mapping[str, Any]]) -> tuple[list[str], list[list[Any]]]:
    rows = _validated_headline_rows(scored_rows, operation="pairwise matrix")
    ids = [str(row["observation_id"]) for row in rows]
    indexed = {str(row["observation_id"]): row for row in rows}
    matrix: list[list[Any]] = []
    for row_id in ids:
        cells: list[Any] = [row_id]
        for column_id in ids:
            if row_id == column_id:
                cells.append(0.0)
                continue
            comparable, mismatches = _pair_comparability(indexed[row_id], indexed[column_id])
            cells.append(
                float(indexed[row_id]["CPII"]) - float(indexed[column_id]["CPII"])
                if comparable
                else f"N/A:{mismatches}"
            )
        matrix.append(cells)
    return ["observation_id"] + ids, matrix


def compare_companies(company_rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    if len(company_rows) < 2:
        raise ValueError("at least two companies are required")
    scored = score_rows(company_rows, strict=True)
    return {
        "scored": scored,
        "ranking": rank_companies(scored),
        "pairs": pair_records(scored),
        "matrix": pairwise_matrix(scored),
    }


def _csv_safe_value(value: Any) -> Any:
    """Neutralize spreadsheet formulas while retaining numeric CSV cell types."""
    if isinstance(value, set):
        value = sorted(value, key=str)
    if isinstance(value, (list, tuple, dict)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=isinstance(value, dict))
    if not isinstance(value, str) or not value:
        return value
    stripped = value.lstrip()
    if value[0] in "\t\r\n" or (stripped and stripped[0] in "=+-@"):
        return "'" + value
    return value


def _write_dict_csv(
    path: Path,
    rows: list[Mapping[str, Any]],
    *,
    fieldnames: Iterable[str] | None = None,
) -> None:
    selected_fields = list(fieldnames or (list(rows[0]) if rows else []))
    if not selected_fields:
        raise ValueError(f"cannot write headerless CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=selected_fields)
        writer.writeheader()
        writer.writerows(
            {
                field: _csv_safe_value(row.get(field))
                for field in selected_fields
            }
            for row in rows
        )


def _write_matrix_csv(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([_csv_safe_value(value) for value in header])
        writer.writerows([_csv_safe_value(value) for value in row] for row in rows)


def _build_sensitivity_outputs(
    company_rows: list[Mapping[str, Any]],
    ranges: Mapping[str, Mapping[str, tuple[float, float, float]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    # Lazy import avoids compare <-> sensitivity import recursion at module load.
    if __package__ in {None, ""}:
        from scripts.cpii_simulator.sensitivity import analyze_pair_sensitivity
    else:
        from .sensitivity import analyze_pair_sensitivity

    summaries: list[dict[str, Any]] = []
    variants: list[dict[str, Any]] = []
    skipped = 0
    for input_a, input_b in combinations(company_rows, 2):
        comparable, _ = _pair_comparability(input_a, input_b)
        if not comparable:
            skipped += 1
            continue
        pair_ids = (str(input_a["observation_id"]), str(input_b["observation_id"]))
        pair_ranges = {
            row_id: ranges[row_id]
            for row_id in pair_ids
            if row_id in ranges
        }
        result = analyze_pair_sensitivity(input_a, input_b, ranges=pair_ranges)
        variant_rows = list(result["variants"])
        summary = {key: value for key, value in result.items() if key != "variants"}
        summaries.append(summary)
        variant_context = {
            "pair_id": summary["pair_id"],
            "observation_id_a": summary["observation_id_a"],
            "observation_id_b": summary["observation_id_b"],
            "input_range_assessed": summary["input_range_assessed"],
            "input_range_feature_count_a": summary["input_range_feature_count_a"],
            "input_range_feature_count_b": summary["input_range_feature_count_b"],
        }
        variants.extend({**variant_context, **variant} for variant in variant_rows)
    return summaries, variants, skipped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("company_csv", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--feature-ranges",
        type=Path,
        help="optional long-form feature-range CSV for deterministic pair sensitivity",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        company_rows, issues = validate_company_rows(
            args.company_csv,
            strict=False,
            require_complete_features=True,
        )
        for issue in issues:
            print(issue.render(), file=sys.stderr if issue.severity == "ERROR" else sys.stdout)
        errors = [issue for issue in issues if issue.severity == "ERROR"]
        if errors:
            print(f"FAIL comparison input: {len(errors)} validation error(s)", file=sys.stderr)
            return 1
        result = compare_companies(company_rows)
        sensitivity_summaries: list[dict[str, Any]] = []
        sensitivity_variants: list[dict[str, Any]] = []
        skipped_sensitivity_pairs = 0
        if args.feature_ranges is not None:
            if __package__ in {None, ""}:
                from scripts.cpii_simulator.sensitivity import read_feature_ranges
            else:
                from .sensitivity import read_feature_ranges

            ranges = read_feature_ranges(args.feature_ranges, company_rows)
            sensitivity_summaries, sensitivity_variants, skipped_sensitivity_pairs = (
                _build_sensitivity_outputs(company_rows, ranges)
            )
        _write_dict_csv(args.output_dir / "company_scores.csv", [flatten_score(row) for row in result["scored"]])
        _write_dict_csv(args.output_dir / "company_ranking.csv", result["ranking"])
        _write_dict_csv(args.output_dir / "pair_gaps.csv", result["pairs"])
        header, matrix = result["matrix"]
        _write_matrix_csv(args.output_dir / "pair_gap_matrix.csv", header, matrix)
        if args.feature_ranges is not None:
            _write_dict_csv(
                args.output_dir / "sensitivity_summary.csv",
                sensitivity_summaries,
                fieldnames=SENSITIVITY_SUMMARY_FIELDS,
            )
            _write_dict_csv(
                args.output_dir / "sensitivity_variants.csv",
                sensitivity_variants,
                fieldnames=SENSITIVITY_VARIANT_FIELDS,
            )
    except (OSError, ValueError, csv.Error) as exc:
        print(f"FAIL comparison: {exc}", file=sys.stderr)
        return 1
    suffix = ""
    if args.feature_ranges is not None:
        suffix = (
            f"; sensitivity for {len(sensitivity_summaries)} comparable pair(s)"
            f" ({skipped_sensitivity_pairs} incomparable pair(s) skipped)"
        )
    print(
        f"WROTE comparison outputs for {len(company_rows)} companies "
        f"and {len(result['pairs'])} unordered pairs{suffix}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
