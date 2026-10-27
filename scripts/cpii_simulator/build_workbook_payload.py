#!/usr/bin/env python3
"""Generate the portable JSON payload consumed by the artifact-tool workbook builder."""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.cpii_simulator.engine import load_anchor, normalize_value, read_company_csv, score_rows
    from scripts.cpii_simulator.validate_input import ISO_CURRENCIES
else:
    from .engine import load_anchor, normalize_value, read_company_csv, score_rows
    from .validate_input import ISO_CURRENCIES


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_DIR = PROJECT_ROOT / "data" / "processed" / "cpii_simulator" / "examples"
REGISTRY_DIR = PROJECT_ROOT / "data" / "registry"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "tables" / "cpii_simulator" / "workbook" / "workbook_payload.json"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def coerce_numeric_fields(
    rows: list[dict[str, Any]],
    *,
    float_fields: set[str],
    integer_fields: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return workbook-ready rows with true numeric cells, not CSV text.

    Excel's COUNT/ISNUMBER validation gates intentionally reject numeric-looking
    text.  Keeping CSV strings in the workbook would therefore make the bundled
    examples fail the same validation applied to client-entered numbers.
    """

    integer_fields = integer_fields or set()
    converted: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        for field in float_fields | integer_fields:
            value = row.get(field)
            if value in {None, ""}:
                continue
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(f"non-finite workbook value for {field}: {value!r}")
            row[field] = int(number) if field in integer_fields else number
        converted.append(row)
    return converted


def inverse_transform(value: float, rule: str) -> float:
    if rule == "identity":
        return value
    if rule == "signed_log1p":
        return math.copysign(math.expm1(abs(value)), value)
    raise ValueError(rule)


def projected_normalize(raw: float, config: dict[str, Any], rank_keys: list[float]) -> float:
    directed = raw * int(config["direction_code"])
    clipped = min(max(directed, float(config["rank_key_lower"])), float(config["rank_key_upper"]))
    lo = bisect.bisect_left(rank_keys, clipped)
    hi = bisect.bisect_right(rank_keys, clipped)
    return ((((lo + 1) + hi) / 2.0) - 1.0) / (len(rank_keys) - 1.0)


def build_payload() -> dict[str, Any]:
    anchor = load_anchor()
    dictionary = read_csv(REGISTRY_DIR / "cpii_simulator_variable_dictionary.csv")
    bridge = {row["variable_name"]: row for row in read_csv(REGISTRY_DIR / "cpii_economic_bridge_registry.csv")}
    benchmarks = read_csv(REGISTRY_DIR / "cpii_benchmark_registry.csv")
    companies = read_company_csv(EXAMPLE_DIR / "fictional_companies.csv")
    exposures = read_csv(EXAMPLE_DIR / "fictional_exposures.csv")
    provenance = read_csv(EXAMPLE_DIR / "fictional_feature_provenance.csv")
    expected_scores = score_rows(companies, anchor, strict=True)
    feature_config: list[dict[str, Any]] = []
    anchor_rank_keys: list[dict[str, Any]] = []
    rank_key_map: dict[str, list[float]] = {}
    active_order = [name for axis in anchor["subindex_order"] for name in anchor["active_components"][axis]]
    companies = coerce_numeric_fields(
        companies,
        float_fields={"company_exposure_factor", *active_order},
        integer_fields={"price_year", "carry_lag_q"},
    )
    exposures = coerce_numeric_fields(
        exposures,
        float_fields={
            "period_year_fraction",
            "revenue_low", "revenue_base", "revenue_high",
            "positive_pretax_income_low", "positive_pretax_income_base", "positive_pretax_income_high",
            "average_interest_bearing_debt_low", "average_interest_bearing_debt_base", "average_interest_bearing_debt_high",
            "content_investment_low", "content_investment_base", "content_investment_high",
            "eligible_market_revenue_low", "eligible_market_revenue_base", "eligible_market_revenue_high",
            "scenario_conversion_rate_low", "scenario_conversion_rate_base", "scenario_conversion_rate_high",
        },
        integer_fields={"price_year"},
    )
    definition_map = {row["variable_name"]: row for row in dictionary}
    for name in active_order:
        profile = anchor["profiles"][name]
        rule = profile["transform"]
        keys = [inverse_transform(float(value), rule) for value in profile["reference_winsorized_values"]]
        rank_key_map[name] = keys
        axis = profile["subindex"]
        config = {
            **definition_map[name],
            **bridge[name],
            "direction_code": int(profile["direction_code"]),
            "reference_n": int(profile["reference_n"]),
            "rank_key_lower": inverse_transform(float(profile["winsor_lower_transformed"]), rule),
            "rank_key_upper": inverse_transform(float(profile["winsor_upper_transformed"]), rule),
            "effective_feature_weight": (1.0 / len(anchor["subindex_order"])) / len(anchor["active_components"][axis]),
            "low_support_anchor": "yes" if name in anchor["low_support_active_features"] else "no",
        }
        feature_config.append(config)
        anchor_rank_keys.extend(
            {"variable_name": name, "reference_order": index, "rank_key_directed": value}
            for index, value in enumerate(keys, start=1)
        )

    for name in active_order:
        config = next(row for row in feature_config if row["variable_name"] == name)
        profile = anchor["profiles"][name]
        raw_observed = [float(row[f"raw_{name}"]) for row in expected_scores]
        probes = raw_observed + [
            inverse_transform(float(profile["winsor_lower_transformed"]), profile["transform"]) / int(profile["direction_code"]),
            inverse_transform(float(profile["winsor_upper_transformed"]), profile["transform"]) / int(profile["direction_code"]),
        ]
        for raw in probes:
            projected = projected_normalize(raw, config, rank_key_map[name])
            canonical = float(normalize_value(raw, profile)["normalized"])
            if not math.isclose(projected, canonical, rel_tol=0.0, abs_tol=1e-15):
                raise ValueError(f"rank-key projection parity failure for {name}: {raw}")

    expected_rows = []
    for row in expected_scores:
        expected_rows.append(
            {
                "observation_id": row["observation_id"],
                "CPII": row["CPII"],
                "I_reg": row["I_reg"],
                "I_risk": row["I_risk"],
                "I_market": row["I_market"],
                **{f"norm_{name}": row["normalized_features"][name] for name in active_order},
            }
        )
    return {
        "metadata": {
            "build_date": "2026-09-03",
            "workbook_version": "CPII_COMPARATOR_XLSX_V2.0.0",
            "method_version": anchor["product_spec_version"],
            "anchor_version": anchor["anchor_version"],
            "release_status": anchor["release_status"],
            "joint_complete_reference_count": anchor["source"]["joint_support"]["complete_row_count"],
            "joint_reference_row_count": anchor["source"]["row_count"],
            "joint_support_eligibility": anchor["source"]["joint_support"]["eligibility"],
            "low_support_effective_weight": anchor["low_support_effective_weight"],
            "company_capacity": 100,
            "pair_matrix_capacity": 30,
        },
        "active_order": active_order,
        "benchmarks": benchmarks,
        "supported_currencies": sorted(ISO_CURRENCIES),
        "feature_config": feature_config,
        "anchor_rank_keys": anchor_rank_keys,
        "companies": companies,
        "exposures": exposures,
        "provenance": provenance,
        "expected_scores": expected_rows,
        "golden_equal_gap_summary": read_csv(
            PROJECT_ROOT / "outputs" / "tables" / "cpii_simulator" / "examples" / "golden_equal_gap_summary.csv"
        ),
        "sensitivity_summary": read_csv(
            PROJECT_ROOT / "outputs" / "tables" / "cpii_simulator" / "examples" / "sensitivity_summary.csv"
        ),
        "source_hashes": {
            str(path.relative_to(PROJECT_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                EXAMPLE_DIR / "fictional_companies.csv",
                EXAMPLE_DIR / "fictional_exposures.csv",
                EXAMPLE_DIR / "fictional_feature_provenance.csv",
                REGISTRY_DIR / "cpii_simulator_variable_dictionary.csv",
                REGISTRY_DIR / "cpii_economic_bridge_registry.csv",
            )
        },
    }


def serialize() -> str:
    return json.dumps(build_payload(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        content = serialize()
        if args.check:
            if not OUTPUT_PATH.exists() or OUTPUT_PATH.read_text(encoding="utf-8") != content:
                raise ValueError("workbook payload is missing or stale")
            print("PASS workbook payload: rank-key projection and serialized content match")
            return 0
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(content, encoding="utf-8")
        print(f"WROTE workbook payload: {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    except (OSError, ValueError, KeyError, csv.Error) as exc:
        print(f"FAIL workbook payload: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
