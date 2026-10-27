#!/usr/bin/env python3
"""Validate the v1 CPII simulator variable dictionary without external packages."""

from __future__ import annotations

import csv
import math
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DICTIONARY_PATH = PROJECT_ROOT / "data" / "registry" / "cpii_simulator_variable_dictionary.csv"
ANCHOR_INPUT_PATH = PROJECT_ROOT / "data" / "processed" / "variable_panel_sector_quarter.csv"

EXPECTED_ACTIVE = {
    "I_reg": {
        "effective_tax_rate_gap": (1, "signed_log1p"),
        "network_cost_ratio": (1, "signed_log1p"),
        "infra_dependency_ratio": (1, "signed_log1p"),
    },
    "I_risk": {
        "funding_cost_spread": (1, "signed_log1p"),
        "ip_assetization_gap": (1, "signed_log1p"),
        "investment_recovery_ratio": (-1, "signed_log1p"),
        "cashflow_recovery_ratio": (-1, "signed_log1p"),
    },
    "I_market": {
        "cross_market_transfer_index": (1, "signed_log1p"),
        "foreign_dependency_ratio": (1, "identity"),
        "outflow_to_capex_ratio": (1, "signed_log1p"),
    },
}
EXPECTED_INACTIVE = {"creator_share_ratio", "bundle_leverage_index"}
GAP_VARIABLES = {"effective_tax_rate_gap", "funding_cost_spread", "ip_assetization_gap"}
VALID_MONETIZATION_CLASSES = {
    "conditional_accounting_equivalent",
    "conditional_performance_equivalent",
    "scenario_only",
    "non_monetizable",
    "inactive",
}
REQUIRED_COLUMNS = {
    "variable_name",
    "display_name_ko",
    "subindex",
    "status",
    "direction_code",
    "transform",
    "input_unit",
    "operational_definition",
    "construction_type",
    "preferred_input_level",
    "requires_benchmark",
    "benchmark_rule",
    "entity_scope",
    "soft_min",
    "soft_max",
    "anchor_observed_min",
    "anchor_observed_max",
    "monetization_class",
    "economic_base",
    "overlap_family",
    "report_alignment",
    "notes",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def fail(message: str) -> None:
    raise ValueError(message)


def observed_ranges(path: Path, variables: set[str]) -> dict[str, tuple[float, float]]:
    rows = read_csv(path)
    values: dict[str, list[float]] = {name: [] for name in variables}
    for row in rows:
        for name in variables:
            raw = row.get(name, "").strip()
            if not raw:
                continue
            value = float(raw)
            if not math.isfinite(value):
                fail(f"non-finite anchor value for {name}")
            values[name].append(value)
    return {name: (min(items), max(items)) for name, items in values.items() if items}


def main() -> int:
    rows = read_csv(DICTIONARY_PATH)
    if not rows:
        fail("variable dictionary is empty")
    missing_columns = REQUIRED_COLUMNS - set(rows[0])
    if missing_columns:
        fail(f"missing dictionary columns: {sorted(missing_columns)}")

    names = [row["variable_name"] for row in rows]
    if len(names) != len(set(names)):
        fail("duplicate variable_name rows")
    expected_names = set(EXPECTED_INACTIVE)
    for variables in EXPECTED_ACTIVE.values():
        expected_names.update(variables)
    if set(names) != expected_names:
        fail(f"variable set mismatch: expected {sorted(expected_names)}, got {sorted(names)}")

    active_by_axis: dict[str, set[str]] = {axis: set() for axis in EXPECTED_ACTIVE}
    for row in rows:
        for field in REQUIRED_COLUMNS - {"economic_base"}:
            if not row[field].strip():
                fail(f"{row['variable_name']}: blank required field {field}")
        name = row["variable_name"]
        status = row["status"]
        if status == "active":
            if row["subindex"] not in active_by_axis:
                fail(f"{name}: unexpected subindex {row['subindex']}")
            active_by_axis[row["subindex"]].add(name)
            expected_direction, expected_transform = EXPECTED_ACTIVE[row["subindex"]][name]
            if int(row["direction_code"]) != expected_direction:
                fail(f"{name}: direction mismatch")
            if row["transform"] != expected_transform:
                fail(f"{name}: transform mismatch")
        elif status != "inactive":
            fail(f"{name}: invalid status {status}")

        soft_min = float(row["soft_min"])
        soft_max = float(row["soft_max"])
        anchor_min = float(row["anchor_observed_min"])
        anchor_max = float(row["anchor_observed_max"])
        if soft_min > soft_max or anchor_min > anchor_max:
            fail(f"{name}: invalid range order")
        if row["monetization_class"] not in VALID_MONETIZATION_CLASSES:
            fail(f"{name}: invalid monetization class")
        if name in GAP_VARIABLES and row["requires_benchmark"] != "yes":
            fail(f"{name}: benchmark-relative gap must require a shared benchmark")
        if name not in GAP_VARIABLES and row["requires_benchmark"] != "no":
            fail(f"{name}: unexpected benchmark requirement")

    for axis, expected in EXPECTED_ACTIVE.items():
        if active_by_axis[axis] != set(expected):
            fail(f"{axis}: active set mismatch")
    inactive = {row["variable_name"] for row in rows if row["status"] == "inactive"}
    if inactive != EXPECTED_INACTIVE:
        fail("inactive shadow set mismatch")

    actual_ranges = observed_ranges(ANCHOR_INPUT_PATH, set(names))
    for row in rows:
        name = row["variable_name"]
        expected = actual_ranges.get(name)
        if expected is None:
            fail(f"{name}: no source observations")
        declared = (float(row["anchor_observed_min"]), float(row["anchor_observed_max"]))
        if any(abs(a - b) > 1e-10 for a, b in zip(expected, declared)):
            fail(f"{name}: declared anchor range {declared} != source {expected}")

    print(
        "PASS variable dictionary: "
        f"{len(rows)} rows; active counts="
        + "/".join(str(len(active_by_axis[axis])) for axis in ("I_reg", "I_risk", "I_market"))
        + "; inactive=2; source ranges reconciled"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError) as exc:
        print(f"FAIL variable dictionary: {exc}", file=sys.stderr)
        raise SystemExit(1)
