#!/usr/bin/env python3
"""Exact feature and subindex decomposition of CPII pair gaps."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
import sys
from typing import Any, Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.cpii_simulator.compare import _pair_comparability, _validated_headline_rows
    from scripts.cpii_simulator.engine import AXES, load_anchor, read_company_csv, score_rows
else:
    from .compare import _pair_comparability, _validated_headline_rows
    from .engine import AXES, load_anchor, read_company_csv, score_rows


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DICTIONARY_PATH = PROJECT_ROOT / "data" / "registry" / "cpii_simulator_variable_dictionary.csv"


def load_definitions() -> dict[str, dict[str, str]]:
    with DICTIONARY_PATH.open("r", encoding="utf-8", newline="") as handle:
        return {row["variable_name"]: row for row in csv.DictReader(handle)}


def decompose_pair(
    score_a: Mapping[str, Any],
    score_b: Mapping[str, Any],
    *,
    anchor: Mapping[str, Any] | None = None,
    definitions: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    score_a, score_b = _validated_headline_rows(
        [score_a, score_b],
        operation="decomposition",
    )
    comparable, mismatches = _pair_comparability(score_a, score_b)
    if not comparable:
        raise ValueError(f"cannot decompose incomparable pair; mismatches: {mismatches}")
    frozen = anchor if anchor is not None else load_anchor()
    dictionary = definitions if definitions is not None else load_definitions()
    top_weight = 1.0 / len(AXES)
    gap = float(score_a["CPII"]) - float(score_b["CPII"])
    features: list[dict[str, Any]] = []

    for axis in AXES:
        names = list(frozen["active_components"][axis])
        feature_weight = top_weight / len(names)
        for name in names:
            raw_a = float(score_a[f"raw_{name}"])
            raw_b = float(score_b[f"raw_{name}"])
            norm_a = float(score_a["normalized_features"][name])
            norm_b = float(score_b["normalized_features"][name])
            raw_difference = raw_a - raw_b
            normalized_difference = norm_a - norm_b
            if not all(
                math.isfinite(value)
                for value in (raw_a, raw_b, raw_difference, norm_a, norm_b, normalized_difference)
            ):
                raise ValueError(f"decomposition requires finite values and differences for {name}")
            contribution = 100.0 * feature_weight * normalized_difference
            if abs(contribution) <= 1e-15:
                role = "neutral"
            elif contribution * gap > 0:
                role = "gap_widening"
            else:
                role = "gap_offsetting"
            definition = dictionary[name]
            features.append(
                {
                    "pair_id": f"{score_a['observation_id']}__vs__{score_b['observation_id']}",
                    "observation_id_a": score_a["observation_id"],
                    "observation_id_b": score_b["observation_id"],
                    "company_name_a": score_a.get("company_name", ""),
                    "company_name_b": score_b.get("company_name", ""),
                    "subindex": axis,
                    "variable_name": name,
                    "display_name_ko": definition["display_name_ko"],
                    "input_unit": definition["input_unit"],
                    "direction_code": int(definition["direction_code"]),
                    "raw_a": raw_a,
                    "raw_b": raw_b,
                    "raw_difference_a_minus_b": raw_difference,
                    "direction_aligned_raw_difference": int(definition["direction_code"]) * raw_difference,
                    "normalized_a": norm_a,
                    "normalized_b": norm_b,
                    "normalized_difference": normalized_difference,
                    "effective_feature_weight": feature_weight,
                    "cpii_point_contribution": contribution,
                    "contribution_role": role,
                    "low_support_anchor": "yes" if name in frozen["low_support_active_features"] else "no",
                    "monetization_class": definition["monetization_class"],
                    "economic_base": definition["economic_base"],
                    "overlap_family": definition["overlap_family"],
                }
            )

    gross = sum(abs(row["cpii_point_contribution"]) for row in features)
    ordered = sorted(features, key=lambda row: (-abs(row["cpii_point_contribution"]), row["variable_name"]))
    for rank, row in enumerate(ordered, start=1):
        row["absolute_contribution_share"] = (
            abs(row["cpii_point_contribution"]) / gross if gross else 0.0
        )
        row["absolute_driver_rank"] = rank
    by_original_order = {row["variable_name"]: row for row in ordered}
    features = [by_original_order[row["variable_name"]] for row in features]

    subindices: list[dict[str, Any]] = []
    for axis in AXES:
        contribution = sum(
            row["cpii_point_contribution"] for row in features if row["subindex"] == axis
        )
        expected = top_weight * (float(score_a[axis]) - float(score_b[axis]))
        subindices.append(
            {
                "pair_id": f"{score_a['observation_id']}__vs__{score_b['observation_id']}",
                "subindex": axis,
                "subindex_a": float(score_a[axis]),
                "subindex_b": float(score_b[axis]),
                "subindex_difference": float(score_a[axis]) - float(score_b[axis]),
                "top_level_weight": top_weight,
                "cpii_point_contribution": contribution,
                "expected_weighted_subindex_difference": expected,
            }
        )

    residual = gap - sum(row["cpii_point_contribution"] for row in features)
    top_drivers = sorted(features, key=lambda row: (-abs(row["cpii_point_contribution"]), row["variable_name"]))[:3]
    return {
        "pair_id": f"{score_a['observation_id']}__vs__{score_b['observation_id']}",
        "delta_cpii_points_a_minus_b": gap,
        "feature_contribution_sum": sum(row["cpii_point_contribution"] for row in features),
        "decomposition_residual": residual,
        "gross_absolute_contribution": gross,
        "top_three_drivers": [row["variable_name"] for row in top_drivers],
        "features": features,
        "subindices": subindices,
    }


def decompose_all(scored_rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    scored_rows = _validated_headline_rows(scored_rows, operation="decomposition")
    results: list[dict[str, Any]] = []
    for left in range(len(scored_rows)):
        for right in range(left + 1, len(scored_rows)):
            comparable, _ = _pair_comparability(scored_rows[left], scored_rows[right])
            if comparable:
                results.append(decompose_pair(scored_rows[left], scored_rows[right]))
    return results


def write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("company_csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        scored = score_rows(read_company_csv(args.company_csv), strict=True)
        decompositions = decompose_all(scored)
        rows = [row for result in decompositions for row in result["features"]]
        write_csv(args.output, rows)
    except (OSError, ValueError, csv.Error) as exc:
        print(f"FAIL decomposition: {exc}", file=sys.stderr)
        return 1
    max_residual = max((abs(result["decomposition_residual"]) for result in decompositions), default=0.0)
    if max_residual > 1e-10:
        print(f"FAIL decomposition residual: {max_residual}", file=sys.stderr)
        return 1
    print(f"WROTE {len(rows)} feature contributions across {len(decompositions)} comparable pairs; max residual={max_residual:.3g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
