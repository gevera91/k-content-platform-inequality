#!/usr/bin/env python3
"""Pure scoring engine for the frozen-anchor CPII feature-input comparator."""

from __future__ import annotations

import bisect
import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ANCHOR_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cpii_simulator"
    / "anchor"
    / "POOL_SCQ_P01_P99_EMP_RANK_V1.json"
)
METHOD_VERSION = "CPII_FIRM_INPUT_EQW_V1"
AXES = ("I_reg", "I_risk", "I_market")
MASS_POINT_WARNING_REL_TOL = 1e-10


class ScoringError(ValueError):
    """Raised when a row cannot be scored under the requested specification."""


def load_anchor(path: Path = DEFAULT_ANCHOR_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        anchor = json.load(handle)
    if anchor.get("product_spec_version") != METHOD_VERSION:
        raise ScoringError(
            f"anchor product specification {anchor.get('product_spec_version')!r} "
            f"does not match {METHOD_VERSION!r}"
        )
    return anchor


def signed_log1p(value: float) -> float:
    if value == 0:
        return 0.0
    return math.copysign(math.log1p(abs(value)), value)


def normalize_value(raw_value: float, profile: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the frozen legacy-compatible transform and empirical-rank mapping."""
    value = float(raw_value)
    if not math.isfinite(value):
        raise ScoringError("feature value must be finite")
    directed = value * int(profile["direction_code"])
    rule = str(profile["transform"])
    if rule == "signed_log1p":
        transformed = signed_log1p(directed)
    elif rule == "identity":
        transformed = directed
    else:
        raise ScoringError(f"unsupported transform {rule!r}")
    lower = float(profile["winsor_lower_transformed"])
    upper = float(profile["winsor_upper_transformed"])
    winsorized = min(max(transformed, lower), upper)
    reference = profile["reference_winsorized_values"]
    n = int(profile["reference_n"])
    if n < 2 or len(reference) != n:
        raise ScoringError("invalid frozen reference profile")
    lo = bisect.bisect_left(reference, winsorized)
    hi = bisect.bisect_right(reference, winsorized)
    average_rank = ((lo + 1) + hi) / 2.0
    percentile = (average_rank - 1.0) / (n - 1.0)
    repeated_values: list[float] = []
    cursor = 0
    while cursor < n:
        end = bisect.bisect_right(reference, reference[cursor], lo=cursor)
        if end - cursor > 1:
            repeated_values.append(float(reference[cursor]))
        cursor = end
    near_mass_point = any(
        abs(winsorized - point) <= MASS_POINT_WARNING_REL_TOL * max(1.0, abs(point))
        for point in repeated_values
    )
    return {
        "raw": value,
        "directed": directed,
        "transformed": transformed,
        "winsorized": winsorized,
        "normalized": percentile,
        "clipped_low": transformed < lower,
        "clipped_high": transformed > upper,
        "rank_discontinuity_warning": near_mass_point,
        "rank_warning_tolerance": MASS_POINT_WARNING_REL_TOL,
    }


def _as_optional_float(value: Any) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ScoringError(f"expected numeric feature value, got {value!r}") from exc
    if not math.isfinite(number):
        raise ScoringError(f"expected finite feature value, got {value!r}")
    return number


def score_row(
    row: Mapping[str, Any],
    anchor: Mapping[str, Any] | None = None,
    *,
    strict: bool = True,
) -> dict[str, Any]:
    """Score one company row; strict mode requires all ten active variables."""
    frozen = dict(anchor) if anchor is not None else load_anchor()
    profiles: Mapping[str, Mapping[str, Any]] = frozen["profiles"]
    active_components: Mapping[str, list[str]] = frozen["active_components"]
    active_names = [name for axis in AXES for name in active_components[axis]]
    normalized: dict[str, float] = {}
    transformations: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    flags: list[str] = []
    for name in active_names:
        raw = _as_optional_float(row.get(name))
        if raw is None:
            missing.append(name)
            continue
        details = normalize_value(raw, profiles[name])
        transformations[name] = details
        normalized[name] = float(details["normalized"])
        if details["clipped_low"]:
            flags.append(f"{name}:winsorized_low")
        if details["clipped_high"]:
            flags.append(f"{name}:winsorized_high")
        if profiles[name].get("headline_status") == "research_beta_only":
            flags.append(f"{name}:low_support_anchor")
            if details["rank_discontinuity_warning"]:
                flags.append(f"{name}:rank_discontinuity_warning")
    if strict and missing:
        raise ScoringError("strict mode requires all active variables; missing: " + ", ".join(sorted(missing)))

    subindices: dict[str, float | None] = {}
    weights_used: dict[str, dict[str, float]] = {}
    for axis in AXES:
        components = list(active_components[axis])
        observed = [name for name in components if name in normalized]
        missing_share = (len(components) - len(observed)) / len(components)
        if not observed or missing_share >= float(frozen["method"]["missing_share_threshold"]):
            subindices[axis] = None
            weights_used[axis] = {}
            flags.append(f"{axis}:not_computed")
        else:
            component_weight = 1.0 / len(observed)
            weights_used[axis] = {name: component_weight for name in observed}
            subindices[axis] = 100.0 * sum(normalized[name] for name in observed) / len(observed)

    observed_axes = [axis for axis in AXES if subindices[axis] is not None]
    missing_axis_share = (len(AXES) - len(observed_axes)) / len(AXES)
    if len(observed_axes) < 2 or missing_axis_share >= float(frozen["method"]["missing_share_threshold"]):
        cpii = None
        flags.append("CPII:not_computed")
    else:
        cpii = sum(float(subindices[axis]) for axis in observed_axes) / len(observed_axes)
    if strict and cpii is None:
        raise ScoringError("strict CPII could not be computed")

    output: dict[str, Any] = {
        "observation_id": row.get("observation_id", ""),
        "company_name": row.get("company_name", ""),
        "company_group": row.get("company_group", ""),
        "method_version": METHOD_VERSION,
        "anchor_version": frozen["anchor_version"],
        "release_status": frozen["release_status"],
        "score_eligible": "yes" if strict and cpii is not None else "no",
        "composite_interpretation": "weighted_average_of_feature_level_marginal_reference_positions",
        "company_empirical_percentile": None,
        "company_empirical_percentile_status": frozen["source"]["joint_support"]["eligibility"],
        "low_support_effective_weight": frozen.get("low_support_effective_weight"),
        "score_mode": "strict_all_active" if strict else "partial_diagnostic",
        "CPII": cpii,
        "cpii_raw_score": None if cpii is None else cpii / 100.0,
        "I_reg": subindices["I_reg"],
        "I_risk": subindices["I_risk"],
        "I_market": subindices["I_market"],
        "active_feature_count": len(active_names),
        "observed_feature_count": len(normalized),
        "missing_features": "|".join(sorted(missing)),
        "diagnostic_flags": "|".join(sorted(set(flags))),
        "normalized_features": normalized,
        "transformations": transformations,
        "subindex_feature_weights": weights_used,
    }
    for key in (
        "sector", "service_scope", "focal_market", "reporting_period", "benchmark_id",
        "currency", "price_year", "input_quality", "synthetic_flag", "construction_mode",
        "source_id", "source_date", "carry_lag_q", "market_common_exposure_adjusted",
        "company_exposure_factor", "source_note",
    ):
        output[key] = row.get(key, "")
    for name in active_names:
        output[f"raw_{name}"] = _as_optional_float(row.get(name))
        output[f"norm_{name}"] = normalized.get(name)
    return output


def score_rows(
    rows: Iterable[Mapping[str, Any]],
    anchor: Mapping[str, Any] | None = None,
    *,
    strict: bool = True,
) -> list[dict[str, Any]]:
    frozen = anchor if anchor is not None else load_anchor()
    return [score_row(row, frozen, strict=strict) for row in rows]


def read_company_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def flatten_score(score: Mapping[str, Any]) -> dict[str, Any]:
    """Return CSV-safe scalar fields while keeping full diagnostics available in Python."""
    return {
        key: value
        for key, value in score.items()
        if key not in {"normalized_features", "transformations", "subindex_feature_weights"}
    }
