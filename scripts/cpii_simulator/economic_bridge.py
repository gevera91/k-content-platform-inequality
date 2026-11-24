#!/usr/bin/env python3
"""Feature-specific economic interpretation bridges for CPII pair differences."""

from __future__ import annotations

import csv
import math
from pathlib import Path
import sys
from typing import Any, Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.cpii_simulator.compare import _pair_comparability, _text, _validated_headline_rows
    from scripts.cpii_simulator.decompose import load_definitions
    from scripts.cpii_simulator.validate_input import QUALITIES, observation_id_error, read_csv
else:
    from .compare import _pair_comparability, _text, _validated_headline_rows
    from .decompose import load_definitions
    from .validate_input import QUALITIES, observation_id_error, read_csv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = PROJECT_ROOT / "data" / "registry" / "cpii_economic_bridge_registry.csv"
CASES = ("low", "base", "high")


def load_bridge_registry() -> dict[str, dict[str, str]]:
    with REGISTRY_PATH.open("r", encoding="utf-8", newline="") as handle:
        return {row["variable_name"]: row for row in csv.DictReader(handle)}


def read_exposures(path: Path) -> dict[str, dict[str, str]]:
    fields, rows = read_csv(path)
    if "observation_id" not in fields:
        raise ValueError("exposure CSV requires observation_id column")
    exposures: dict[str, dict[str, str]] = {}
    for row_number, row in enumerate(rows, start=2):
        row_id = _text(row.get("observation_id"))
        id_error = observation_id_error(row.get("observation_id"))
        if id_error:
            raise ValueError(f"exposure CSV row {row_number} has invalid observation_id: {id_error}")
        if row_id in exposures:
            raise ValueError(f"duplicate exposure observation_id: {row_id}")
        normalized = dict(row)
        normalized["observation_id"] = row_id
        exposures[row_id] = normalized
    return exposures


def _finite_number(row: Mapping[str, Any], field: str) -> float:
    value = row.get(field)
    if value is None or str(value).strip() == "":
        raise KeyError(field)
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _number(row: Mapping[str, Any], field: str) -> float:
    number = _finite_number(row, field)
    if number < 0:
        raise ValueError(f"{field} must be nonnegative")
    return number


def _unit_interval(row: Mapping[str, Any], field: str, *, allow_zero: bool) -> float:
    number = _number(row, field)
    if number > 1 or (not allow_zero and number <= 0):
        bounds = "from 0 through 1" if allow_zero else "greater than 0 and no greater than 1"
        raise ValueError(f"{field} must be {bounds}")
    return number


def _triplet(
    row: Mapping[str, Any],
    base: str,
    *,
    upper: float | None = None,
) -> tuple[float, float, float]:
    values = tuple(_number(row, f"{base}_{case}") for case in CASES)
    if upper is not None and any(value > upper for value in values):
        raise ValueError(f"{base} values must be no greater than {upper:g}")
    if not values[0] <= values[1] <= values[2]:
        raise ValueError(f"{base} must satisfy low <= base <= high")
    return values


def _exposure_metadata_check(
    score_a: Mapping[str, Any],
    score_b: Mapping[str, Any],
    exposure_a: Mapping[str, Any],
    exposure_b: Mapping[str, Any],
) -> tuple[str, float | None, float | None]:
    expected_a = _text(score_a.get("observation_id"))
    expected_b = _text(score_b.get("observation_id"))
    if _text(exposure_a.get("observation_id")) != expected_a or _text(exposure_b.get("observation_id")) != expected_b:
        return "exposure_observation_id_mismatch", None, None

    sources = (
        _text(exposure_a.get("exposure_source_id")),
        _text(exposure_b.get("exposure_source_id")),
    )
    if not all(sources):
        return "missing_exposure_source_id", None, None
    qualities = (
        _text(exposure_a.get("exposure_quality")),
        _text(exposure_b.get("exposure_quality")),
    )
    if any(quality not in QUALITIES for quality in qualities):
        return "invalid_exposure_quality", None, None

    currencies = (
        _text(exposure_a.get("currency")),
        _text(exposure_b.get("currency")),
        _text(score_a.get("currency")),
        _text(score_b.get("currency")),
    )
    years = (
        _text(exposure_a.get("price_year")),
        _text(exposure_b.get("price_year")),
        _text(score_a.get("price_year")),
        _text(score_b.get("price_year")),
    )
    if not all(currencies) or len(set(currencies)) != 1 or not all(years) or len(set(years)) != 1:
        return "currency_or_price_year_mismatch", None, None

    reporting_a = _text(score_a.get("reporting_period"))
    reporting_b = _text(score_b.get("reporting_period"))
    exposure_period_a = _text(exposure_a.get("exposure_period"))
    exposure_period_b = _text(exposure_b.get("exposure_period"))
    if (
        not exposure_period_a
        or not exposure_period_b
        or exposure_period_a != exposure_period_b
        or exposure_period_a not in {reporting_a, reporting_a[:4]}
        or exposure_period_b not in {reporting_b, reporting_b[:4]}
    ):
        return "exposure_period_mismatch", None, None

    try:
        period_a = _unit_interval(exposure_a, "period_year_fraction", allow_zero=False)
        period_b = _unit_interval(exposure_b, "period_year_fraction", allow_zero=False)
    except (KeyError, TypeError, ValueError) as exc:
        return f"missing_or_invalid_exposure:{exc}", None, None
    if not math.isclose(period_a, period_b, rel_tol=0.0, abs_tol=1e-12):
        return "period_year_fraction_mismatch", None, None
    return "", period_a, period_b


def _require_finite_amount(value: float, label: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{label} is nonfinite")
    return value


def monetize_pair(
    score_a: Mapping[str, Any],
    score_b: Mapping[str, Any],
    exposures: Mapping[str, Mapping[str, Any]],
    *,
    registry: Mapping[str, Mapping[str, str]] | None = None,
    definitions: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    score_a, score_b = _validated_headline_rows(
        [score_a, score_b],
        operation="economic interpretation",
    )
    comparable, mismatches = _pair_comparability(score_a, score_b)
    if not comparable:
        raise ValueError(f"incomparable score pair: {mismatches}")
    rules = registry if registry is not None else load_bridge_registry()
    dictionary = definitions if definitions is not None else load_definitions()
    pair_id = f"{score_a['observation_id']}__vs__{score_b['observation_id']}"
    exposure_a = exposures.get(str(score_a["observation_id"]))
    exposure_b = exposures.get(str(score_b["observation_id"]))
    metadata_issue = ""
    period_a: float | None = None
    period_b: float | None = None
    if exposure_a is not None and exposure_b is not None:
        metadata_issue, period_a, period_b = _exposure_metadata_check(
            score_a,
            score_b,
            exposure_a,
            exposure_b,
        )
    rows: list[dict[str, Any]] = []

    for name, rule in rules.items():
        definition = dictionary[name]
        direction = int(definition["direction_code"])
        try:
            raw_a = _finite_number(score_a, f"raw_{name}")
            raw_b = _finite_number(score_b, f"raw_{name}")
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"economic interpretation requires finite raw score feature {name}: {exc}") from exc
        directional_difference = direction * (raw_a - raw_b)
        record: dict[str, Any] = {
            "pair_id": pair_id,
            "variable_name": name,
            "display_name_ko": definition["display_name_ko"],
            "interpretation_class": rule["interpretation_class"],
            "bridge_status": rule["bridge_status"],
            "raw_difference_a_minus_b": raw_a - raw_b,
            "burden_aligned_rate_or_multiple_difference": directional_difference,
            "economic_base": rule["economic_base"],
            "currency": _text(exposure_a.get("currency")) if exposure_a else "",
            "price_year": _text(exposure_a.get("price_year")) if exposure_a else "",
            "exposure_period": _text(exposure_a.get("exposure_period")) if exposure_a else "",
            "exposure_period_a": _text(exposure_a.get("exposure_period")) if exposure_a else "",
            "exposure_period_b": _text(exposure_b.get("exposure_period")) if exposure_b else "",
            "period_year_fraction_a": period_a,
            "period_year_fraction_b": period_b,
            "exposure_source_id_a": _text(exposure_a.get("exposure_source_id")) if exposure_a else "",
            "exposure_source_id_b": _text(exposure_b.get("exposure_source_id")) if exposure_b else "",
            "exposure_quality_a": _text(exposure_a.get("exposure_quality")) if exposure_a else "",
            "exposure_quality_b": _text(exposure_b.get("exposure_quality")) if exposure_b else "",
            "overlap_family": rule["overlap_family"],
            "aggregation_rule": rule["aggregation_rule"],
            "causal_status": rule["causal_status"],
            "plain_language_ko": rule["plain_language_ko"],
            "common_size_definition": rule["common_size_rule"],
            "actual_scale_definition": rule["actual_scale_rule"],
            "availability": "available",
            "unavailability_reason": "",
        }
        for case in CASES:
            record[f"company_exposure_a_{case}"] = None
            record[f"company_exposure_b_{case}"] = None
            record[f"common_exposure_{case}"] = None
            record[f"conversion_rate_a_{case}"] = None
            record[f"conversion_rate_b_{case}"] = None
            record[f"common_conversion_rate_{case}"] = None
            record[f"common_size_amount_{case}"] = None
            record[f"actual_scale_amount_{case}"] = None

        if rule["bridge_status"] != "enabled":
            record["availability"] = "not_monetizable"
            record["unavailability_reason"] = "no_identified_nonoverlapping_economic_bridge"
            rows.append(record)
            continue
        if exposure_a is None or exposure_b is None:
            record["availability"] = "not_available"
            record["unavailability_reason"] = "missing_company_exposure_row"
            rows.append(record)
            continue
        if metadata_issue:
            record["availability"] = "not_available"
            record["unavailability_reason"] = metadata_issue
            rows.append(record)
            continue

        base = rule["economic_base"]
        try:
            bases_a = _triplet(exposure_a, base)
            bases_b = _triplet(exposure_b, base)
            conversions_a: tuple[float, float, float] | None = None
            conversions_b: tuple[float, float, float] | None = None
            if rule["formula_code"] == "directional_gap_times_base_and_conversion":
                conversions_a = _triplet(exposure_a, "scenario_conversion_rate", upper=1.0)
                conversions_b = _triplet(exposure_b, "scenario_conversion_rate", upper=1.0)
            for index, case in enumerate(CASES):
                base_a = bases_a[index]
                base_b = bases_b[index]
                common_base = (base_a + base_b) / 2.0
                record[f"company_exposure_a_{case}"] = base_a
                record[f"company_exposure_b_{case}"] = base_b
                if rule["formula_code"] == "directional_gap_times_base_and_conversion":
                    if conversions_a is None or conversions_b is None:
                        raise ValueError("conversion triplets were not initialized")
                    conversion_a = conversions_a[index]
                    conversion_b = conversions_b[index]
                    common_conversion = (conversion_a + conversion_b) / 2.0
                    common_amount = directional_difference * common_base * common_conversion
                    actual_amount = direction * (
                        raw_a * base_a * conversion_a - raw_b * base_b * conversion_b
                    )
                    record[f"conversion_rate_a_{case}"] = conversion_a
                    record[f"conversion_rate_b_{case}"] = conversion_b
                    record[f"common_conversion_rate_{case}"] = common_conversion
                else:
                    applied_period_a = period_a if rule["period_factor_required"] == "yes" else 1.0
                    applied_period_b = period_b if rule["period_factor_required"] == "yes" else 1.0
                    if applied_period_a is None or applied_period_b is None:
                        raise ValueError("period fractions were not initialized")
                    common_period = (applied_period_a + applied_period_b) / 2.0
                    common_amount = directional_difference * common_base * common_period
                    actual_amount = direction * (
                        raw_a * base_a * applied_period_a - raw_b * base_b * applied_period_b
                    )
                record[f"common_exposure_{case}"] = common_base
                record[f"common_size_amount_{case}"] = _require_finite_amount(
                    common_amount,
                    f"common_size_amount_{case}",
                )
                record[f"actual_scale_amount_{case}"] = _require_finite_amount(
                    actual_amount,
                    f"actual_scale_amount_{case}",
                )
        except (KeyError, TypeError, ValueError) as exc:
            record["availability"] = "not_available"
            record["unavailability_reason"] = f"missing_or_invalid_exposure:{exc}"
            for case in CASES:
                record[f"company_exposure_a_{case}"] = None
                record[f"company_exposure_b_{case}"] = None
                record[f"common_exposure_{case}"] = None
                record[f"conversion_rate_a_{case}"] = None
                record[f"conversion_rate_b_{case}"] = None
                record[f"common_conversion_rate_{case}"] = None
                record[f"common_size_amount_{case}"] = None
                record[f"actual_scale_amount_{case}"] = None
        rows.append(record)

    return {
        "pair_id": pair_id,
        "rows": rows,
        "total_amount": None,
        "total_status": "not_computed_mixed_interpretation_classes_and_overlap_families",
        "disclaimer": "Amounts are conditional equivalents or scenarios, not identified causal damages; actual-scale differences also include company size.",
    }


def flatten_monetization(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in result["rows"]]
