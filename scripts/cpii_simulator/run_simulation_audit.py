#!/usr/bin/env python3
"""Deterministic high-volume invariant audit for the CPII simulator.

This script intentionally has no sampling/count CLI switches: the workload is a
versioned QA contract.  Re-running it therefore exercises exactly the same
20,000 core cases, 5,000 economic cases, 1,000 input-range cases, and one
100-company/4,950-pair performance case.

Fixed random seeds
------------------
core=2026090301, economic=2026090302, sensitivity=2026090303,
performance=2026090304.

Fixed numeric tolerances
------------------------
score/decomposition absolute tolerance=1e-10; economic relative tolerance=1e-12
and absolute tolerance=1e-6; sign classification tolerance=1e-12.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import sys
from time import perf_counter
from typing import Any, Mapping


if __package__ in {None, ""}:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(PROJECT_ROOT))
    from scripts.cpii_simulator.compare import compare_companies, pair_records
    from scripts.cpii_simulator.decompose import decompose_pair, load_definitions
    from scripts.cpii_simulator.economic_bridge import load_bridge_registry, monetize_pair
    from scripts.cpii_simulator.engine import AXES, load_anchor, score_row
    from scripts.cpii_simulator.sensitivity import analyze_pair_sensitivity
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    from .compare import compare_companies, pair_records
    from .decompose import decompose_pair, load_definitions
    from .economic_bridge import load_bridge_registry, monetize_pair
    from .engine import AXES, load_anchor, score_row
    from .sensitivity import analyze_pair_sensitivity


AUDIT_VERSION = "CPII_SIMULATION_AUDIT_V1"
CORE_CASES = 20_000
ECONOMIC_CASES = 5_000
SENSITIVITY_CASES = 1_000
PERFORMANCE_COMPANIES = 100
PERFORMANCE_PAIRS = PERFORMANCE_COMPANIES * (PERFORMANCE_COMPANIES - 1) // 2

SEEDS = {
    "core": 2_026_090_301,
    "economic": 2_026_090_302,
    "sensitivity": 2_026_090_303,
    "performance": 2_026_090_304,
}
SCORE_ABS_TOL = 1e-10
ECONOMIC_REL_TOL = 1e-12
ECONOMIC_ABS_TOL = 1e-6
SIGN_TOL = 1e-12


class AuditFailure(AssertionError):
    """An invariant failure annotated with its audit section and case."""


@dataclass
class Checks:
    count: int = 0

    def require(self, condition: bool, message: str) -> None:
        self.count += 1
        if not condition:
            raise AuditFailure(message)

    def close(
        self,
        actual: float,
        expected: float,
        message: str,
        *,
        abs_tol: float = SCORE_ABS_TOL,
        rel_tol: float = 0.0,
    ) -> None:
        self.require(
            math.isfinite(actual)
            and math.isfinite(expected)
            and math.isclose(actual, expected, rel_tol=rel_tol, abs_tol=abs_tol),
            f"{message}: actual={actual!r}, expected={expected!r}",
        )


def _active_names(anchor: Mapping[str, Any]) -> list[str]:
    return [name for axis in AXES for name in anchor["active_components"][axis]]


def _soft_bounds(definitions: Mapping[str, Mapping[str, str]]) -> dict[str, tuple[float, float]]:
    return {
        name: (float(definition["soft_min"]), float(definition["soft_max"]))
        for name, definition in definitions.items()
        if definition.get("status") == "active"
    }


def _feature_value(
    rng: random.Random,
    low: float,
    high: float,
    case_index: int,
    feature_index: int,
    *,
    profile: Mapping[str, Any] | None = None,
) -> float:
    """Mix boundaries, zero, mass points, and continuous interior values."""
    selector = (case_index * 17 + feature_index * 7) % 29
    if profile is not None:
        lower_transformed = float(profile["winsor_lower_transformed"])
        upper_transformed = float(profile["winsor_upper_transformed"])
        span = max(1.0, upper_transformed - lower_transformed)
        mode = selector % 8
        if mode == 0:
            transformed = lower_transformed
        elif mode == 1:
            transformed = upper_transformed
        elif mode == 2:
            transformed = lower_transformed - 0.2 * span
        elif mode == 3:
            transformed = upper_transformed + 0.2 * span
        elif mode == 4:
            reference = profile["reference_winsorized_values"]
            transformed = float(reference[rng.randrange(len(reference))])
        elif mode == 5:
            transformed = 0.0
        else:
            transformed = rng.uniform(lower_transformed, upper_transformed)
        if profile["transform"] == "signed_log1p":
            directed = math.copysign(math.expm1(abs(transformed)), transformed)
        elif profile["transform"] == "identity":
            directed = transformed
        else:
            raise AuditFailure(f"unsupported audit transform {profile['transform']!r}")
        return directed / int(profile["direction_code"])
    if selector == 0:
        return low
    if selector == 1:
        return high
    if selector == 2 and low <= 0.0 <= high:
        return 0.0
    if selector == 3:
        return (low + high) / 2.0
    return rng.uniform(low, high)


def _company_row(
    rng: random.Random,
    anchor: Mapping[str, Any],
    bounds: Mapping[str, tuple[float, float]],
    row_id: str,
    group: str,
    case_index: int,
    *,
    profile_stress: bool = False,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "observation_id": row_id,
        "company_name": f"Deterministic company {row_id}",
        "company_group": group,
        "sector": "digital_content",
        "service_scope": "integrated_content",
        "focal_market": "Korea",
        "reporting_period": "2025Q4",
        "benchmark_id": "BM-DIGITAL-CONTENT-2025Q4",
        "currency": "KRW",
        "price_year": "2025",
        "input_quality": "SYNTHETIC",
        "synthetic_flag": "yes",
        "construction_mode": "derived",
        "source_id": "SIMULATION-AUDIT",
        "source_date": "2026-09-03",
        "carry_lag_q": "0",
        "market_common_exposure_adjusted": "yes",
        "company_exposure_factor": rng.random(),
        "source_note": "deterministic simulation audit",
    }
    for feature_index, name in enumerate(_active_names(anchor)):
        low, high = bounds[name]
        row[name] = _feature_value(
            rng,
            low,
            high,
            case_index,
            feature_index,
            profile=anchor["profiles"][name] if profile_stress else None,
        )
    return row


def _company_pair(
    rng: random.Random,
    anchor: Mapping[str, Any],
    bounds: Mapping[str, tuple[float, float]],
    prefix: str,
    case_index: int,
    *,
    profile_stress: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        _company_row(
            rng,
            anchor,
            bounds,
            f"{prefix}-{case_index:05d}-A",
            "domestic",
            case_index * 2,
            profile_stress=profile_stress,
        ),
        _company_row(
            rng,
            anchor,
            bounds,
            f"{prefix}-{case_index:05d}-B",
            "foreign",
            case_index * 2 + 1,
            profile_stress=profile_stress,
        ),
    )


def _update_digest(digest: Any, *values: Any) -> None:
    digest.update("|".join(str(value) for value in values).encode("utf-8"))
    digest.update(b"\n")


def _check_score(
    checks: Checks,
    score: Mapping[str, Any],
    anchor: Mapping[str, Any],
    label: str,
) -> None:
    cpii = float(score["CPII"])
    checks.require(math.isfinite(cpii) and 0.0 <= cpii <= 100.0, f"{label}: CPII outside [0,100]")
    checks.require(score["score_eligible"] == "yes", f"{label}: score not eligible")
    checks.require(score["score_mode"] == "strict_all_active", f"{label}: score mode is not strict")
    checks.require(score["observed_feature_count"] == 10, f"{label}: expected ten observed features")
    axis_values: list[float] = []
    for axis in AXES:
        value = float(score[axis])
        axis_values.append(value)
        checks.require(math.isfinite(value) and 0.0 <= value <= 100.0, f"{label}: {axis} outside [0,100]")
        names = anchor["active_components"][axis]
        expected = 100.0 * sum(float(score["normalized_features"][name]) for name in names) / len(names)
        checks.close(value, expected, f"{label}: {axis} aggregation")
    checks.close(cpii, sum(axis_values) / len(axis_values), f"{label}: top-level aggregation")
    checks.close(float(score["cpii_raw_score"]), cpii / 100.0, f"{label}: raw score scaling")
    for name in _active_names(anchor):
        normalized = float(score["normalized_features"][name])
        checks.require(
            math.isfinite(normalized) and 0.0 <= normalized <= 1.0,
            f"{label}: normalized {name} outside [0,1]",
        )


def _run_core(
    anchor: Mapping[str, Any],
    definitions: Mapping[str, Mapping[str, str]],
    bounds: Mapping[str, tuple[float, float]],
) -> dict[str, Any]:
    rng = random.Random(SEEDS["core"])
    checks = Checks()
    digest = hashlib.sha256()
    max_residual = 0.0
    max_pair_reversal_error = 0.0
    max_feature_reversal_error = 0.0
    started = perf_counter()

    for case_index in range(CORE_CASES):
        input_a, input_b = _company_pair(
            rng,
            anchor,
            bounds,
            "CORE",
            case_index,
            profile_stress=True,
        )
        score_a = score_row(input_a, anchor, strict=True)
        score_b = score_row(input_b, anchor, strict=True)
        label = f"core case {case_index}"
        _check_score(checks, score_a, anchor, f"{label} A")
        _check_score(checks, score_b, anchor, f"{label} B")

        for name in _active_names(anchor):
            directed_difference = int(anchor["profiles"][name]["direction_code"]) * (
                float(input_a[name]) - float(input_b[name])
            )
            normalized_difference = (
                float(score_a["normalized_features"][name])
                - float(score_b["normalized_features"][name])
            )
            checks.require(
                directed_difference == 0.0
                or normalized_difference == 0.0
                or math.copysign(1.0, directed_difference) == math.copysign(1.0, normalized_difference),
                f"{label}: direction/normalization monotonicity failed for {name}",
            )

        forward = pair_records([score_a, score_b])[0]
        backward = pair_records([score_b, score_a])[0]
        gap = float(score_a["CPII"]) - float(score_b["CPII"])
        checks.require(forward["comparable"] == "yes", f"{label}: pair unexpectedly incomparable")
        checks.require(forward["pair_eligible"] == "yes", f"{label}: pair unexpectedly ineligible")
        checks.require(forward["monetization_eligible"] == "yes", f"{label}: monetization unexpectedly ineligible")
        checks.require(
            forward["pair_type"] == "reverse_discrimination_hypothesis_related_structural_burden_gap",
            f"{label}: reverse-discrimination label gate failed",
        )
        checks.close(float(forward["delta_cpii_points_a_minus_b"]), gap, f"{label}: pair gap")
        checks.close(float(forward["absolute_gap_points"]), abs(gap), f"{label}: absolute gap")
        reversal_error = abs(float(forward["delta_cpii_points_a_minus_b"]) + float(backward["delta_cpii_points_a_minus_b"]))
        max_pair_reversal_error = max(max_pair_reversal_error, reversal_error)
        checks.require(reversal_error <= SCORE_ABS_TOL, f"{label}: pair reversal error={reversal_error}")
        checks.close(
            float(forward["domestic_minus_foreign_points"]),
            float(backward["domestic_minus_foreign_points"]),
            f"{label}: domestic-minus-foreign orientation",
        )

        decomposition = decompose_pair(score_a, score_b, anchor=anchor, definitions=definitions)
        reversed_decomposition = decompose_pair(score_b, score_a, anchor=anchor, definitions=definitions)
        residual = abs(float(decomposition["decomposition_residual"]))
        max_residual = max(max_residual, residual)
        checks.require(residual <= SCORE_ABS_TOL, f"{label}: decomposition residual={residual}")
        checks.close(
            float(decomposition["feature_contribution_sum"]),
            gap,
            f"{label}: feature contribution sum",
        )
        checks.close(
            sum(float(row["cpii_point_contribution"]) for row in decomposition["subindices"]),
            gap,
            f"{label}: subindex contribution sum",
        )
        for row in decomposition["subindices"]:
            checks.close(
                float(row["cpii_point_contribution"]),
                float(row["expected_weighted_subindex_difference"]),
                f"{label}: subindex identity {row['subindex']}",
            )
        reverse_by_name = {
            row["variable_name"]: float(row["cpii_point_contribution"])
            for row in reversed_decomposition["features"]
        }
        for row in decomposition["features"]:
            name = str(row["variable_name"])
            contribution = float(row["cpii_point_contribution"])
            feature_reversal_error = abs(contribution + reverse_by_name[name])
            max_feature_reversal_error = max(max_feature_reversal_error, feature_reversal_error)
            checks.require(
                feature_reversal_error <= SCORE_ABS_TOL,
                f"{label}: feature reversal error for {name}={feature_reversal_error}",
            )
        gross = float(decomposition["gross_absolute_contribution"])
        share_sum = sum(float(row["absolute_contribution_share"]) for row in decomposition["features"])
        checks.close(share_sum, 1.0 if gross else 0.0, f"{label}: absolute contribution shares")
        _update_digest(
            digest,
            case_index,
            format(float(score_a["CPII"]), ".17g"),
            format(float(score_b["CPII"]), ".17g"),
            format(gap, ".17g"),
            format(float(decomposition["feature_contribution_sum"]), ".17g"),
        )

    return {
        "cases": CORE_CASES,
        "invariant_checks": checks.count,
        "max_decomposition_residual": max_residual,
        "max_pair_reversal_error": max_pair_reversal_error,
        "max_feature_reversal_error": max_feature_reversal_error,
        "sha256": digest.hexdigest(),
        "elapsed_seconds": round(perf_counter() - started, 6),
    }


def _ordered_triplet(rng: random.Random, base: float, *, upper: float | None = None) -> tuple[float, float, float]:
    low = base * rng.uniform(0.50, 1.0)
    if upper is None:
        high = base * rng.uniform(1.0, 2.0)
    else:
        high = base + (upper - base) * rng.random()
    return low, base, high


def _exposure(rng: random.Random, row_id: str, period: float) -> dict[str, Any]:
    row: dict[str, Any] = {
        "observation_id": row_id,
        "currency": "KRW",
        "price_year": "2025",
        "exposure_period": "2025Q4",
        "period_year_fraction": period,
        "exposure_source_id": "SIMULATION-AUDIT",
        "exposure_quality": "SYNTHETIC",
        "exposure_note": "deterministic simulation audit",
    }
    for base in (
        "revenue",
        "positive_pretax_income",
        "average_interest_bearing_debt",
        "content_investment",
        "eligible_market_revenue",
    ):
        center = 10.0 ** rng.uniform(6.0, 15.0)
        for case, value in zip(("low", "base", "high"), _ordered_triplet(rng, center)):
            row[f"{base}_{case}"] = value
    conversion = rng.uniform(0.0, 1.0)
    for case, value in zip(
        ("low", "base", "high"),
        _ordered_triplet(rng, conversion, upper=1.0),
    ):
        row[f"scenario_conversion_rate_{case}"] = value
    return row


def _run_economic(
    anchor: Mapping[str, Any],
    definitions: Mapping[str, Mapping[str, str]],
    bounds: Mapping[str, tuple[float, float]],
) -> dict[str, Any]:
    rng = random.Random(SEEDS["economic"])
    registry = load_bridge_registry()
    checks = Checks()
    digest = hashlib.sha256()
    enabled_case_conversions = 0
    max_amount_error = 0.0
    max_reversal_error = 0.0
    started = perf_counter()

    for case_index in range(ECONOMIC_CASES):
        input_a, input_b = _company_pair(rng, anchor, bounds, "ECON", case_index)
        score_a = score_row(input_a, anchor, strict=True)
        score_b = score_row(input_b, anchor, strict=True)
        period = rng.uniform(1.0 / 365.0, 1.0)
        exposure_a = _exposure(rng, str(score_a["observation_id"]), period)
        exposure_b = _exposure(rng, str(score_b["observation_id"]), period)
        exposures = {
            str(score_a["observation_id"]): exposure_a,
            str(score_b["observation_id"]): exposure_b,
        }
        result = monetize_pair(
            score_a,
            score_b,
            exposures,
            registry=registry,
            definitions=definitions,
        )
        reversed_result = monetize_pair(
            score_b,
            score_a,
            exposures,
            registry=registry,
            definitions=definitions,
        )
        reversed_by_name = {row["variable_name"]: row for row in reversed_result["rows"]}
        label = f"economic case {case_index}"
        checks.require(result["total_amount"] is None, f"{label}: universal total must remain disabled")
        checks.require(
            result["total_status"] == "not_computed_mixed_interpretation_classes_and_overlap_families",
            f"{label}: total status changed",
        )
        checks.require(len(result["rows"]) == len(registry), f"{label}: registry row count mismatch")

        for record in result["rows"]:
            name = str(record["variable_name"])
            rule = registry[name]
            checks.require(record["aggregation_rule"] == "never_auto_sum", f"{label}/{name}: aggregation rule")
            if rule["bridge_status"] != "enabled":
                checks.require(record["availability"] == "not_monetizable", f"{label}/{name}: disabled bridge availability")
                for case in ("low", "base", "high"):
                    checks.require(record[f"common_size_amount_{case}"] is None, f"{label}/{name}: disabled common amount")
                    checks.require(record[f"actual_scale_amount_{case}"] is None, f"{label}/{name}: disabled actual amount")
                continue

            checks.require(record["availability"] == "available", f"{label}/{name}: enabled bridge unavailable")
            direction = int(definitions[name]["direction_code"])
            raw_a = float(score_a[f"raw_{name}"])
            raw_b = float(score_b[f"raw_{name}"])
            directional_difference = direction * (raw_a - raw_b)
            checks.close(
                float(record["burden_aligned_rate_or_multiple_difference"]),
                directional_difference,
                f"{label}/{name}: directional difference",
            )
            base = rule["economic_base"]
            for case in ("low", "base", "high"):
                base_a = float(exposure_a[f"{base}_{case}"])
                base_b = float(exposure_b[f"{base}_{case}"])
                common_base = (base_a + base_b) / 2.0
                checks.close(
                    float(record[f"common_exposure_{case}"]),
                    common_base,
                    f"{label}/{name}/{case}: common exposure",
                    abs_tol=ECONOMIC_ABS_TOL,
                    rel_tol=ECONOMIC_REL_TOL,
                )
                if rule["formula_code"] == "directional_gap_times_base_and_conversion":
                    conversion_a = float(exposure_a[f"scenario_conversion_rate_{case}"])
                    conversion_b = float(exposure_b[f"scenario_conversion_rate_{case}"])
                    common_conversion = (conversion_a + conversion_b) / 2.0
                    expected_common = directional_difference * common_base * common_conversion
                    expected_actual = direction * (
                        raw_a * base_a * conversion_a - raw_b * base_b * conversion_b
                    )
                else:
                    applied_period = period if rule["period_factor_required"] == "yes" else 1.0
                    expected_common = directional_difference * common_base * applied_period
                    expected_actual = direction * (
                        raw_a * base_a * applied_period - raw_b * base_b * applied_period
                    )
                actual_common = float(record[f"common_size_amount_{case}"])
                actual_scale = float(record[f"actual_scale_amount_{case}"])
                common_error = abs(actual_common - expected_common)
                actual_error = abs(actual_scale - expected_actual)
                max_amount_error = max(max_amount_error, common_error, actual_error)
                checks.close(
                    actual_common,
                    expected_common,
                    f"{label}/{name}/{case}: common-size amount",
                    abs_tol=ECONOMIC_ABS_TOL,
                    rel_tol=ECONOMIC_REL_TOL,
                )
                checks.close(
                    actual_scale,
                    expected_actual,
                    f"{label}/{name}/{case}: actual-scale amount",
                    abs_tol=ECONOMIC_ABS_TOL,
                    rel_tol=ECONOMIC_REL_TOL,
                )
                reversed_record = reversed_by_name[name]
                common_reversal_error = abs(
                    actual_common + float(reversed_record[f"common_size_amount_{case}"])
                )
                actual_reversal_error = abs(
                    actual_scale + float(reversed_record[f"actual_scale_amount_{case}"])
                )
                max_reversal_error = max(
                    max_reversal_error,
                    common_reversal_error,
                    actual_reversal_error,
                )
                checks.close(
                    float(reversed_record[f"common_size_amount_{case}"]),
                    -actual_common,
                    f"{label}/{name}/{case}: reversed common-size amount",
                    abs_tol=ECONOMIC_ABS_TOL,
                    rel_tol=ECONOMIC_REL_TOL,
                )
                checks.close(
                    float(reversed_record[f"actual_scale_amount_{case}"]),
                    -actual_scale,
                    f"{label}/{name}/{case}: reversed actual-scale amount",
                    abs_tol=ECONOMIC_ABS_TOL,
                    rel_tol=ECONOMIC_REL_TOL,
                )
                enabled_case_conversions += 1
        _update_digest(
            digest,
            case_index,
            *(
                format(float(row["common_size_amount_base"]), ".17g")
                for row in result["rows"]
                if row["availability"] == "available"
            ),
        )

    return {
        "cases": ECONOMIC_CASES,
        "enabled_low_base_high_conversions_checked": enabled_case_conversions,
        "invariant_checks": checks.count,
        "max_recomputed_amount_absolute_error": max_amount_error,
        "max_pair_reversal_absolute_error": max_reversal_error,
        "sha256": digest.hexdigest(),
        "elapsed_seconds": round(perf_counter() - started, 6),
    }


def _feature_ranges(
    rng: random.Random,
    input_a: Mapping[str, Any],
    input_b: Mapping[str, Any],
    names: list[str],
    bounds: Mapping[str, tuple[float, float]],
) -> dict[str, dict[str, tuple[float, float, float]]]:
    shuffled_a = names[:]
    shuffled_b = names[:]
    rng.shuffle(shuffled_a)
    rng.shuffle(shuffled_b)
    chosen = {
        str(input_a["observation_id"]): shuffled_a[: rng.randint(1, len(names))],
        str(input_b["observation_id"]): shuffled_b[: rng.randint(1, len(names))],
    }
    ranges: dict[str, dict[str, tuple[float, float, float]]] = {}
    for row in (input_a, input_b):
        row_id = str(row["observation_id"])
        ranges[row_id] = {}
        for name in chosen[row_id]:
            base = float(row[name])
            low_bound, high_bound = bounds[name]
            low = base - (base - low_bound) * rng.random()
            high = base + (high_bound - base) * rng.random()
            ranges[row_id][name] = (low, base, high)
    return ranges


def _expected_corner_gap(
    input_a: Mapping[str, Any],
    input_b: Mapping[str, Any],
    ranges: Mapping[str, Mapping[str, tuple[float, float, float]]],
    anchor: Mapping[str, Any],
    *,
    high_gap: bool,
) -> float:
    corner_a = dict(input_a)
    corner_b = dict(input_b)
    for row, target, choose_high_burden in (
        (input_a, corner_a, high_gap),
        (input_b, corner_b, not high_gap),
    ):
        row_id = str(row["observation_id"])
        for name, triplet in ranges[row_id].items():
            direction = int(anchor["profiles"][name]["direction_code"])
            raw_index = 2 if choose_high_burden else 0
            if direction == -1:
                raw_index = 2 - raw_index
            target[name] = triplet[raw_index]
    score_a = score_row(corner_a, anchor, strict=True)
    score_b = score_row(corner_b, anchor, strict=True)
    return float(score_a["CPII"]) - float(score_b["CPII"])


def _run_sensitivity(
    anchor: Mapping[str, Any],
    bounds: Mapping[str, tuple[float, float]],
) -> dict[str, Any]:
    rng = random.Random(SEEDS["sensitivity"])
    names = _active_names(anchor)
    checks = Checks()
    digest = hashlib.sha256()
    max_corner_error = 0.0
    total_feature_ranges = 0
    started = perf_counter()

    for case_index in range(SENSITIVITY_CASES):
        input_a, input_b = _company_pair(rng, anchor, bounds, "RANGE", case_index)
        ranges = _feature_ranges(rng, input_a, input_b, names, bounds)
        total_feature_ranges += sum(len(feature_ranges) for feature_ranges in ranges.values())
        result = analyze_pair_sensitivity(input_a, input_b, ranges=ranges)
        label = f"sensitivity case {case_index}"
        checks.require(result["input_range_assessed"] == "yes", f"{label}: range not assessed")
        checks.require(result["input_range_feature_count_total"] == sum(len(v) for v in ranges.values()), f"{label}: range count")
        checks.require(len(result["variants"]) == 6, f"{label}: expected six variants")
        checks.require(result["probability_interpretation_allowed"] == "no", f"{label}: probability claim enabled")
        checks.require("not_confidence_interval" in result["range_type"], f"{label}: range mislabeled")
        gaps: list[float] = []
        variants = {str(row["specification"]): row for row in result["variants"]}
        for specification, row in variants.items():
            score_a = float(row["score_a"])
            score_b = float(row["score_b"])
            gap = float(row["delta_cpii_points_a_minus_b"])
            gaps.append(gap)
            checks.require(
                all(math.isfinite(value) for value in (score_a, score_b, gap)),
                f"{label}/{specification}: nonfinite variant",
            )
            checks.require(0.0 <= score_a <= 100.0 and 0.0 <= score_b <= 100.0, f"{label}/{specification}: score bounds")
            checks.close(gap, score_a - score_b, f"{label}/{specification}: gap identity")
        expected_low = _expected_corner_gap(input_a, input_b, ranges, anchor, high_gap=False)
        expected_high = _expected_corner_gap(input_a, input_b, ranges, anchor, high_gap=True)
        low_gap = float(variants["input_corner_low_gap"]["delta_cpii_points_a_minus_b"])
        high_gap = float(variants["input_corner_high_gap"]["delta_cpii_points_a_minus_b"])
        max_corner_error = max(max_corner_error, abs(low_gap - expected_low), abs(high_gap - expected_high))
        checks.close(low_gap, expected_low, f"{label}: low-gap corner")
        checks.close(high_gap, expected_high, f"{label}: high-gap corner")
        checks.require(low_gap <= high_gap + SCORE_ABS_TOL, f"{label}: corner ordering")
        checks.close(float(result["sensitivity_min_points"]), min(gaps), f"{label}: sensitivity minimum")
        checks.close(float(result["sensitivity_max_points"]), max(gaps), f"{label}: sensitivity maximum")
        positive = sum(value > SIGN_TOL for value in gaps)
        checks.close(
            float(result["positive_specification_share_descriptive"]),
            positive / len(gaps),
            f"{label}: positive specification share",
        )
        expected_stable = not (
            any(value > SIGN_TOL for value in gaps) and any(value < -SIGN_TOL for value in gaps)
        ) and not any(abs(value) <= SIGN_TOL for value in gaps)
        checks.require(
            result["sign_stable"] == ("yes" if expected_stable else "no"),
            f"{label}: sign-stability classification",
        )
        _update_digest(
            digest,
            case_index,
            *(format(value, ".17g") for value in gaps),
        )

    return {
        "cases": SENSITIVITY_CASES,
        "feature_ranges_checked": total_feature_ranges,
        "invariant_checks": checks.count,
        "max_corner_recomputation_error": max_corner_error,
        "sha256": digest.hexdigest(),
        "elapsed_seconds": round(perf_counter() - started, 6),
    }


def _run_performance(
    anchor: Mapping[str, Any],
    bounds: Mapping[str, tuple[float, float]],
) -> dict[str, Any]:
    rng = random.Random(SEEDS["performance"])
    rows = [
        _company_row(
            rng,
            anchor,
            bounds,
            f"PERF-{index:03d}",
            ("domestic", "foreign", "other")[index % 3],
            index,
        )
        for index in range(PERFORMANCE_COMPANIES)
    ]
    started = perf_counter()
    result = compare_companies(rows)
    elapsed = perf_counter() - started
    if len(result["pairs"]) != PERFORMANCE_PAIRS:
        raise AuditFailure(
            f"performance: expected {PERFORMANCE_PAIRS} pairs, got {len(result['pairs'])}"
        )
    header, matrix = result["matrix"]
    if len(result["scored"]) != PERFORMANCE_COMPANIES or len(result["ranking"]) != PERFORMANCE_COMPANIES:
        raise AuditFailure("performance: score/ranking row count mismatch")
    if len(header) != PERFORMANCE_COMPANIES + 1 or len(matrix) != PERFORMANCE_COMPANIES:
        raise AuditFailure("performance: pair matrix dimensions mismatch")
    values = {row[0]: dict(zip(header[1:], row[1:])) for row in matrix}
    for row_id in header[1:]:
        if values[row_id][row_id] != 0.0:
            raise AuditFailure(f"performance: nonzero matrix diagonal for {row_id}")
    max_matrix_antisymmetry_error = max(
        abs(float(values[left][right]) + float(values[right][left]))
        for left_index, left in enumerate(header[1:])
        for right in header[left_index + 2 :]
    )
    if max_matrix_antisymmetry_error > SCORE_ABS_TOL:
        raise AuditFailure(
            f"performance: matrix antisymmetry error={max_matrix_antisymmetry_error}"
        )
    digest = hashlib.sha256()
    for row in result["pairs"]:
        _update_digest(
            digest,
            row["pair_id"],
            format(float(row["delta_cpii_points_a_minus_b"]), ".17g"),
        )
    return {
        "companies": PERFORMANCE_COMPANIES,
        "unordered_pairs": len(result["pairs"]),
        "matrix_cells": PERFORMANCE_COMPANIES * PERFORMANCE_COMPANIES,
        "max_matrix_antisymmetry_error": max_matrix_antisymmetry_error,
        "sha256": digest.hexdigest(),
        "elapsed_seconds": round(elapsed, 6),
        "unordered_pairs_per_second": round(len(result["pairs"]) / elapsed, 3),
        "timing_scope": "warm-process compare_companies wall clock; no pass/fail threshold",
    }


def run() -> dict[str, Any]:
    started = perf_counter()
    anchor = load_anchor()
    definitions = load_definitions()
    bounds = _soft_bounds(definitions)
    active_names = _active_names(anchor)
    if set(active_names) != set(bounds) or len(active_names) != 10:
        raise AuditFailure("audit generator and frozen ten-feature specification are out of sync")
    result = {
        "audit_version": AUDIT_VERSION,
        "status": "PASS",
        "method_version": anchor["product_spec_version"],
        "anchor_version": anchor["anchor_version"],
        "python_version": platform.python_version(),
        "seeds": SEEDS,
        "tolerances": {
            "score_and_decomposition_abs": SCORE_ABS_TOL,
            "economic_rel": ECONOMIC_REL_TOL,
            "economic_abs": ECONOMIC_ABS_TOL,
            "sign": SIGN_TOL,
        },
    }
    result["core"] = _run_core(anchor, definitions, bounds)
    result["economic"] = _run_economic(anchor, definitions, bounds)
    result["sensitivity"] = _run_sensitivity(anchor, bounds)
    result["performance"] = _run_performance(anchor, bounds)
    result["total_elapsed_seconds"] = round(perf_counter() - started, 6)
    return result


def main() -> int:
    try:
        result = run()
    except Exception as exc:  # noqa: BLE001 - the audit must produce a compact machine-readable failure.
        failure = {
            "audit_version": AUDIT_VERSION,
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "seeds": SEEDS,
        }
        print(json.dumps(failure, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
