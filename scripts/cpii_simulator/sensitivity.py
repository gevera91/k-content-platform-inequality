#!/usr/bin/env python3
"""Specification and optional input-range sensitivity for CPII pair gaps."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from .compare import _pair_comparability
from .engine import AXES, load_anchor, score_row
from .validate_input import observation_id_error


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROBUSTNESS_PATH = PROJECT_ROOT / "outputs" / "tables" / "spec_robustness_summary.csv"
DEPENDENCY_PATH = PROJECT_ROOT / "data" / "registry" / "cpii_feature_dependency_registry.csv"
OVERLAP_REDUCED_EXCLUSIONS = {
    "infra_dependency_ratio",
    "outflow_to_capex_ratio",
    "cashflow_recovery_ratio",
}
FEATURE_RANGE_FIELDS = (
    "observation_id",
    "variable_name",
    "low",
    "base",
    "high",
    "range_type",
    "source_id",
)
ALLOWED_RANGE_TYPES = {"measurement", "assumption", "source_interval"}


def _active_feature_names(anchor: Mapping[str, Any]) -> set[str]:
    return {
        name
        for axis in AXES
        for name in anchor["active_components"][axis]
    }


def read_feature_ranges(
    path: Path,
    company_rows: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, tuple[float, float, float]]]:
    """Read and fully validate the documented long-form feature-range CSV."""
    inputs = tuple(company_rows)
    if not inputs:
        raise ValueError("feature ranges require at least one company input row")

    company_by_id: dict[str, Mapping[str, Any]] = {}
    for position, row in enumerate(inputs, start=1):
        raw_id = row.get("observation_id")
        row_id = "" if raw_id is None else str(raw_id)
        id_error = observation_id_error(raw_id)
        if id_error:
            raise ValueError(f"invalid company observation_id at row {position}: {id_error}")
        if row_id in company_by_id:
            raise ValueError(f"company inputs contain duplicate observation_id: {row_id}")
        company_by_id[row_id] = row

    anchor = load_anchor()
    active_names = _active_feature_names(anchor)
    parsed: dict[str, dict[str, tuple[float, float, float]]] = {}
    seen: set[tuple[str, str]] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        header = tuple(reader.fieldnames or ())
        if header != FEATURE_RANGE_FIELDS:
            raise ValueError(
                "feature-range CSV header must be exactly: " + ",".join(FEATURE_RANGE_FIELDS)
            )
        row_count = 0
        for line_number, row in enumerate(reader, start=2):
            row_count += 1
            if None in row or any(row.get(field) is None for field in FEATURE_RANGE_FIELDS):
                raise ValueError(f"feature-range row {line_number} has too many or too few fields")

            raw_id = row["observation_id"]
            row_id = raw_id.strip()
            if raw_id != row_id:
                raise ValueError(
                    f"feature-range row {line_number} has whitespace around observation_id"
                )
            id_error = observation_id_error(raw_id)
            if id_error:
                raise ValueError(
                    f"feature-range row {line_number} has invalid observation_id: {id_error}"
                )
            if row_id not in company_by_id:
                raise ValueError(
                    f"feature-range row {line_number} references unknown observation_id: {row_id}"
                )

            raw_name = row["variable_name"]
            name = raw_name.strip()
            if raw_name != name or name not in active_names:
                raise ValueError(
                    f"feature-range row {line_number} references inactive or unknown feature: {raw_name!r}"
                )
            key = (row_id, name)
            if key in seen:
                raise ValueError(
                    f"duplicate feature-range row for observation_id/variable_name: {row_id}/{name}"
                )
            seen.add(key)

            raw_range_type = row["range_type"]
            range_type = raw_range_type.strip()
            if raw_range_type != range_type or range_type not in ALLOWED_RANGE_TYPES:
                raise ValueError(
                    f"feature-range row {line_number} has invalid range_type: {raw_range_type!r}"
                )
            raw_source_id = row["source_id"]
            if raw_source_id != raw_source_id.strip() or not raw_source_id.strip():
                raise ValueError(
                    f"feature-range row {line_number} requires a nonblank, trimmed source_id"
                )

            values: list[float] = []
            for field in ("low", "base", "high"):
                try:
                    value = float(row[field])
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"feature-range row {line_number} has nonnumeric {field}"
                    ) from exc
                if not math.isfinite(value):
                    raise ValueError(
                        f"feature-range row {line_number} requires finite low/base/high values"
                    )
                values.append(value)
            triplet = (values[0], values[1], values[2])
            if not triplet[0] <= triplet[1] <= triplet[2]:
                raise ValueError(
                    f"feature-range row {line_number} must satisfy low <= base <= high"
                )
            parsed.setdefault(row_id, {})[name] = triplet

    if row_count == 0:
        raise ValueError("feature-range CSV must contain at least one data row")

    # This also binds every supplied base value to the matching company input.
    return _validated_ranges(parsed, inputs, anchor)


def _score_from_normalized(
    score: Mapping[str, Any],
    *,
    anchor: Mapping[str, Any] | None = None,
    excluded: set[str] | None = None,
    top_weights: Mapping[str, float] | None = None,
) -> float:
    frozen = anchor if anchor is not None else load_anchor()
    excluded_names = excluded or set()
    weights = dict(top_weights or {axis: 1.0 / len(AXES) for axis in AXES})
    axis_scores: dict[str, float] = {}
    for axis in AXES:
        names = [name for name in frozen["active_components"][axis] if name not in excluded_names]
        if not names:
            raise ValueError(f"specification leaves {axis} without a feature")
        axis_scores[axis] = 100.0 * sum(float(score["normalized_features"][name]) for name in names) / len(names)
    weight_sum = sum(weights.values())
    return sum(axis_scores[axis] * weights[axis] for axis in AXES) / weight_sum


def _validated_ranges(
    ranges: Mapping[str, Mapping[str, tuple[float, float, float]]],
    inputs: Iterable[Mapping[str, Any]],
    anchor: Mapping[str, Any],
) -> dict[str, dict[str, tuple[float, float, float]]]:
    active_names = _active_feature_names(anchor)
    input_rows = tuple(inputs)
    known_ids = {str(row["observation_id"]) for row in input_rows}
    unknown_ids = sorted(str(row_id) for row_id in ranges if str(row_id) not in known_ids)
    if unknown_ids:
        raise ValueError(
            "ranges reference unknown observation_id value(s): " + ",".join(unknown_ids)
        )
    validated: dict[str, dict[str, tuple[float, float, float]]] = {}
    for input_row in input_rows:
        row_id = str(input_row["observation_id"])
        supplied = ranges.get(row_id, {})
        if not isinstance(supplied, Mapping):
            raise ValueError(f"ranges for {row_id} must be a feature mapping")
        validated[row_id] = {}
        for name, raw_triplet in supplied.items():
            if name not in active_names:
                raise ValueError(f"range references inactive or unknown feature: {name}")
            if isinstance(raw_triplet, (str, bytes)):
                raise ValueError(f"range for {row_id}/{name} must contain low, base, and high")
            try:
                items = tuple(raw_triplet)
            except TypeError as exc:
                raise ValueError(f"range for {row_id}/{name} must contain low, base, and high") from exc
            if len(items) != 3:
                raise ValueError(f"range for {row_id}/{name} must contain exactly three values")
            try:
                triplet = (float(items[0]), float(items[1]), float(items[2]))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"range for {row_id}/{name} must be numeric") from exc
            if not all(math.isfinite(value) for value in triplet):
                raise ValueError(f"range for {row_id}/{name} must be finite")
            if not triplet[0] <= triplet[1] <= triplet[2]:
                raise ValueError(f"range for {row_id}/{name} must satisfy low <= base <= high")
            try:
                input_value = float(input_row.get(name))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"company input for {row_id}/{name} must be numeric") from exc
            if not math.isfinite(input_value):
                raise ValueError(f"company input for {row_id}/{name} must be finite")
            tolerance = 1e-12 * max(1.0, abs(input_value), abs(triplet[1]))
            if not math.isclose(triplet[1], input_value, rel_tol=0.0, abs_tol=tolerance):
                raise ValueError(
                    f"range base for {row_id}/{name} must equal the company input"
                )
            validated[row_id][name] = triplet
    return validated


def _method_context() -> dict[str, float]:
    with ROBUSTNESS_PATH.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    selected: dict[str, float] = {}
    for row in rows:
        if row["comparison_id"] == "baseline_vs_alt_a" and row["metric_category"] == "score_difference":
            selected[row["metric_name"]] = float(row["metric_value"])
    return selected


def dependency_warnings(row: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []
    network = float(row["network_cost_ratio"])
    foreign = float(row["foreign_dependency_ratio"])
    infra = float(row["infra_dependency_ratio"])
    expected = network * foreign
    tolerance = max(0.005, 0.05 * max(abs(expected), abs(infra), 1e-12))
    if abs(infra - expected) > tolerance:
        warnings.append(
            "infra_dependency_ratio_inconsistent_with_network_cost_ratio_times_foreign_dependency_ratio"
        )
    return warnings


def analyze_pair_sensitivity(
    input_a: Mapping[str, Any],
    input_b: Mapping[str, Any],
    *,
    ranges: Mapping[str, Mapping[str, tuple[float, float, float]]] | None = None,
) -> dict[str, Any]:
    raw_id_a = input_a.get("observation_id")
    raw_id_b = input_b.get("observation_id")
    row_id_a = "" if raw_id_a is None else str(raw_id_a)
    row_id_b = "" if raw_id_b is None else str(raw_id_b)
    if not row_id_a or not row_id_b:
        raise ValueError("sensitivity analysis requires nonblank observation_id values")
    for row_id, id_error in (
        (row_id_a, observation_id_error(raw_id_a)),
        (row_id_b, observation_id_error(raw_id_b)),
    ):
        if id_error:
            raise ValueError(f"invalid observation_id {row_id!r}: {id_error}")
    if row_id_a == row_id_b:
        raise ValueError("sensitivity analysis requires two distinct observation_id values")
    comparable, mismatches = _pair_comparability(input_a, input_b)
    if not comparable:
        raise ValueError(f"cannot analyze sensitivity for incomparable pair: {mismatches}")

    frozen = load_anchor()
    score_a = score_row(input_a, frozen, strict=True)
    score_b = score_row(input_b, frozen, strict=True)
    variants: list[dict[str, Any]] = []

    def add(name: str, value_a: float, value_b: float, category: str) -> None:
        variants.append(
            {
                "specification": name,
                "category": category,
                "score_a": value_a,
                "score_b": value_b,
                "delta_cpii_points_a_minus_b": value_a - value_b,
            }
        )

    add("baseline_full_research_beta", float(score_a["CPII"]), float(score_b["CPII"]), "baseline")
    add(
        "alternative_top_weights_40_40_20",
        _score_from_normalized(score_a, anchor=frozen, top_weights={"I_reg": 0.4, "I_risk": 0.4, "I_market": 0.2}),
        _score_from_normalized(score_b, anchor=frozen, top_weights={"I_reg": 0.4, "I_risk": 0.4, "I_market": 0.2}),
        "method_specification",
    )
    low_support = set(frozen["low_support_active_features"])
    add(
        "exclude_low_support_features",
        _score_from_normalized(score_a, anchor=frozen, excluded=low_support),
        _score_from_normalized(score_b, anchor=frozen, excluded=low_support),
        "method_specification",
    )
    add(
        "overlap_reduced",
        _score_from_normalized(score_a, anchor=frozen, excluded=OVERLAP_REDUCED_EXCLUSIONS),
        _score_from_normalized(score_b, anchor=frozen, excluded=OVERLAP_REDUCED_EXCLUSIONS),
        "method_specification",
    )

    selected_ranges: dict[str, dict[str, tuple[float, float, float]]] = {}
    if ranges is not None:
        selected_ranges = _validated_ranges(ranges, (input_a, input_b), frozen)
    input_range_assessed = any(selected_ranges.values())
    if input_range_assessed:
        for corner_name, a_side, b_side in (
            ("input_corner_low_gap", "low", "high"),
            ("input_corner_high_gap", "high", "low"),
        ):
            corner_a, corner_b = dict(input_a), dict(input_b)
            for row_id, target, side in (
                (row_id_a, corner_a, a_side),
                (row_id_b, corner_b, b_side),
            ):
                for name, triplet in selected_ranges[row_id].items():
                    direction = int(frozen["profiles"][name]["direction_code"])
                    index = {"low": 0, "high": 2}[side]
                    if direction == -1:
                        index = 2 - index
                    target[name] = triplet[index]
            corner_score_a = score_row(corner_a, frozen, strict=True)
            corner_score_b = score_row(corner_b, frozen, strict=True)
            add(corner_name, float(corner_score_a["CPII"]), float(corner_score_b["CPII"]), "input_range")

    gaps = [float(row["delta_cpii_points_a_minus_b"]) for row in variants]
    positive = sum(value > 1e-12 for value in gaps)
    negative = sum(value < -1e-12 for value in gaps)
    sign_stable = not (positive and negative) and not any(abs(value) <= 1e-12 for value in gaps)
    unclear = min(gaps) <= 0 <= max(gaps) or not sign_stable
    context = _method_context()
    baseline_abs = abs(gaps[0])
    if baseline_abs < context["median_abs_score_diff"]:
        context_label = "below_historical_median_method_sensitivity"
    elif baseline_abs < context["mean_abs_score_diff"]:
        context_label = "between_historical_median_and_mean_method_sensitivity"
    else:
        context_label = "above_historical_mean_method_sensitivity"
    return {
        "pair_id": f"{row_id_a}__vs__{row_id_b}",
        "observation_id_a": row_id_a,
        "observation_id_b": row_id_b,
        "input_range_assessed": "yes" if input_range_assessed else "no",
        "input_range_feature_count_a": len(selected_ranges.get(row_id_a, {})),
        "input_range_feature_count_b": len(selected_ranges.get(row_id_b, {})),
        "input_range_feature_count_total": (
            len(selected_ranges.get(row_id_a, {})) + len(selected_ranges.get(row_id_b, {}))
        ),
        "variants": variants,
        "sensitivity_min_points": min(gaps),
        "sensitivity_max_points": max(gaps),
        "sign_stable": "yes" if sign_stable else "no",
        "interpretation_status": "difference_unclear" if unclear else "direction_stable_across_tested_specifications",
        "positive_specification_share_descriptive": positive / len(gaps),
        "probability_interpretation_allowed": "no",
        "range_type": "deterministic_sensitivity_range_not_confidence_interval",
        "empirical_pair_gap_percentile": None,
        "empirical_pair_gap_percentile_status": "not_available_insufficient_joint_reference_support",
        "historical_method_sensitivity_median_abs_points": context["median_abs_score_diff"],
        "historical_method_sensitivity_mean_abs_points": context["mean_abs_score_diff"],
        "baseline_gap_method_context": context_label,
        "low_support_effective_weight": frozen["low_support_effective_weight"],
        "dependency_warnings_a": dependency_warnings(input_a),
        "dependency_warnings_b": dependency_warnings(input_b),
    }
