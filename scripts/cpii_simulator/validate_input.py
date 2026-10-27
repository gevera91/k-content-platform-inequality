#!/usr/bin/env python3
"""Validate wide-form CPII company inputs and optional economic exposures."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date
import math
from pathlib import Path
import re
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DICTIONARY_PATH = PROJECT_ROOT / "data" / "registry" / "cpii_simulator_variable_dictionary.csv"
BENCHMARK_REGISTRY_PATH = PROJECT_ROOT / "data" / "registry" / "cpii_benchmark_registry.csv"
PERIOD_RE = re.compile(r"^\d{4}Q[1-4]$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
GROUPS = {"domestic", "foreign", "other"}
QUALITIES = {"A", "B", "C", "SYNTHETIC"}
CONSTRUCTION_MODES = {"direct", "derived", "proxy", "mixed"}
FEATURE_CONSTRUCTION_MODES = {"direct", "derived", "proxy"}
ISO_CURRENCIES = {
    "AED", "AUD", "BRL", "CAD", "CHF", "CNY", "DKK", "EUR", "GBP", "HKD",
    "IDR", "INR", "JPY", "KRW", "MXN", "MYR", "NOK", "NZD", "PHP", "PLN",
    "RUB", "SAR", "SEK", "SGD", "THB", "TRY", "TWD", "USD", "VND", "ZAR",
}

METADATA_FIELDS = [
    "observation_id", "company_name", "company_group", "sector", "service_scope",
    "focal_market", "reporting_period", "benchmark_id", "currency", "price_year",
    "input_quality", "synthetic_flag", "construction_mode", "source_id", "source_date", "carry_lag_q",
    "market_common_exposure_adjusted", "company_exposure_factor", "source_note",
]
COMPARABILITY_FIELDS = ["sector", "service_scope", "focal_market", "reporting_period", "benchmark_id"]
MONETIZATION_COMPARABILITY_FIELDS = ["currency", "price_year"]
EXPOSURE_BASES = [
    "revenue", "positive_pretax_income", "average_interest_bearing_debt",
    "content_investment", "eligible_market_revenue", "scenario_conversion_rate",
]
PAIR_ID_SEPARATOR = "__vs__"
EXCEL_WILDCARD_CHARACTERS = frozenset("*?~")


@dataclass(frozen=True)
class Issue:
    severity: str
    row: str
    field: str
    message: str

    def render(self) -> str:
        return f"{self.severity} [{self.row}] {self.field}: {self.message}"


def observation_id_error(value: object) -> str | None:
    """Return the reason an ID is unsafe for exact Excel/Python pair matching."""
    raw = "" if value is None else str(value)
    if not raw.strip():
        return "required value is blank"
    if raw != raw.strip():
        return "leading or trailing whitespace is not allowed"
    if len(raw) > 64:
        return "maximum length is 64 characters"
    if PAIR_ID_SEPARATOR in raw:
        return f"reserved token {PAIR_ID_SEPARATOR!r} is not allowed"
    if any(character in raw for character in EXCEL_WILDCARD_CHARACTERS):
        return "Excel wildcard characters *, ?, and ~ are not allowed"
    if any("a" <= character <= "z" for character in raw):
        return "ASCII lowercase letters are not allowed; use uppercase IDs"
    if not re.fullmatch(r"[A-Z0-9_.-]+", raw):
        return "use only ASCII uppercase letters, digits, underscore, hyphen, or period"
    return None


def valid_source_date(value: str) -> bool:
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}|2100-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if reader.fieldnames is None:
            raise ValueError("CSV header is missing")
        fields = list(reader.fieldnames)
        if any(field is None or not str(field).strip() for field in fields):
            raise ValueError("CSV header contains a blank column name")
        if len(fields) != len(set(fields)):
            raise ValueError("CSV header contains duplicate column names")
        rows: list[dict[str, str]] = []
        for row_number, raw_row in enumerate(reader, start=2):
            if None in raw_row:
                raise ValueError(f"CSV row {row_number} has more fields than the header")
            # DictReader uses None for cells omitted by a truncated record. Keep the
            # row so the normal required-value checks can report every blank field.
            rows.append({field: "" if raw_row.get(field) is None else str(raw_row[field]) for field in fields})
        return fields, rows


def active_definitions() -> list[dict[str, str]]:
    _, rows = read_csv(DICTIONARY_PATH)
    return [row for row in rows if row["status"] == "active"]


def benchmark_registry() -> dict[str, dict[str, str]]:
    _, rows = read_csv(BENCHMARK_REGISTRY_PATH)
    return {row["benchmark_id"]: row for row in rows}


def parse_number(text: str) -> float:
    try:
        value = float(text)
    except (TypeError, ValueError) as exc:
        raise ValueError("not numeric") from exc
    if not math.isfinite(value):
        raise ValueError("not finite")
    return value


def validate_company_rows(
    path: Path,
    strict: bool = True,
    *,
    require_complete_features: bool = True,
) -> tuple[list[dict[str, str]], list[Issue]]:
    fields, rows = read_csv(path)
    definitions = active_definitions()
    benchmarks = benchmark_registry()
    active_names = [row["variable_name"] for row in definitions]
    issues: list[Issue] = []
    required_columns = METADATA_FIELDS[:-1] + active_names
    required_values = METADATA_FIELDS[:-1] + (active_names if require_complete_features else [])
    for field in required_columns:
        if field not in fields:
            issues.append(Issue("ERROR", "header", field, "required column is missing"))
    if any(issue.severity == "ERROR" for issue in issues):
        return rows, issues
    if len(rows) < 2:
        issues.append(Issue("ERROR", "file", "rows", "at least two company rows are required"))

    seen_ids: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        raw_row_id = row.get("observation_id", "")
        row_id = raw_row_id.strip() or f"CSV row {row_number}"
        id_error = observation_id_error(raw_row_id)
        if id_error:
            issues.append(Issue("ERROR", row_id, "observation_id", id_error))
        for field in required_values:
            if field != "observation_id" and not row.get(field, "").strip():
                issues.append(Issue("ERROR", row_id, field, "required value is blank"))
        if row_id in seen_ids:
            issues.append(Issue("ERROR", row_id, "observation_id", "duplicate identifier"))
        seen_ids.add(row_id)
        for field in COMPARABILITY_FIELDS:
            raw_value = row.get(field, "")
            if raw_value != raw_value.strip():
                issues.append(Issue("ERROR", row_id, field, "leading or trailing whitespace is not allowed"))
            if "  " in raw_value:
                issues.append(Issue("ERROR", row_id, field, "repeated spaces are not allowed in comparison fields"))
        if row.get("company_group") not in GROUPS:
            issues.append(Issue("ERROR", row_id, "company_group", "use domestic, foreign, or other"))
        if row.get("input_quality") not in QUALITIES:
            issues.append(Issue("ERROR", row_id, "input_quality", "use A, B, C, or SYNTHETIC"))
        elif row.get("input_quality") == "C":
            issues.append(Issue("WARNING", row_id, "input_quality", "C-grade input materially limits interpretation"))
        synthetic_flag = row.get("synthetic_flag")
        if synthetic_flag not in {"yes", "no"}:
            issues.append(Issue("ERROR", row_id, "synthetic_flag", "use yes or no"))
        elif (synthetic_flag == "yes") != (row.get("input_quality") == "SYNTHETIC"):
            issues.append(Issue("ERROR", row_id, "synthetic_flag", "synthetic_flag=yes and input_quality=SYNTHETIC must appear together"))
        if row.get("construction_mode") not in CONSTRUCTION_MODES:
            issues.append(Issue("ERROR", row_id, "construction_mode", "use direct, derived, proxy, or mixed"))
        elif row.get("construction_mode") in {"proxy", "mixed"}:
            issues.append(Issue("WARNING", row_id, "construction_mode", "proxy/mixed construction requires prominent disclosure"))
        if not PERIOD_RE.fullmatch(row.get("reporting_period", "")):
            issues.append(Issue("ERROR", row_id, "reporting_period", "expected YYYYQ1..YYYYQ4"))
        if not CURRENCY_RE.fullmatch(row.get("currency", "")) or row.get("currency") not in ISO_CURRENCIES:
            issues.append(Issue("ERROR", row_id, "currency", "unsupported ISO 4217 currency code"))
        try:
            price_year = int(row.get("price_year", ""))
            if not 2000 <= price_year <= 2100:
                raise ValueError
        except ValueError:
            issues.append(Issue("ERROR", row_id, "price_year", "expected integer from 2000 through 2100"))
        if not valid_source_date(row.get("source_date", "")):
            issues.append(Issue("ERROR", row_id, "source_date", "expected a real YYYY-MM-DD date from 2000 through 2100"))
        try:
            lag = int(row.get("carry_lag_q", ""))
            if lag < 0:
                raise ValueError
            if lag > 1:
                issues.append(Issue("WARNING", row_id, "carry_lag_q", "carry-forward exceeds one quarter"))
        except ValueError:
            issues.append(Issue("ERROR", row_id, "carry_lag_q", "expected a nonnegative integer"))
        if row.get("market_common_exposure_adjusted") != "yes":
            issues.append(Issue("ERROR", row_id, "market_common_exposure_adjusted", "scoring requires company-specific exposure adjustment"))
        try:
            factor = parse_number(row.get("company_exposure_factor", ""))
            if not 0 <= factor <= 1:
                raise ValueError
        except ValueError:
            issues.append(Issue("ERROR", row_id, "company_exposure_factor", "expected a number from 0 through 1"))

        for definition in definitions:
            name = definition["variable_name"]
            text = row.get(name, "").strip()
            if not text:
                continue
            try:
                value = parse_number(text)
            except ValueError:
                issues.append(Issue("ERROR", row_id, name, "expected a finite number"))
                continue
            low, high = float(definition["soft_min"]), float(definition["soft_max"])
            if value < low or value > high:
                issues.append(Issue("WARNING", row_id, name, f"{value:g} is outside review envelope [{low:g}, {high:g}]; value is not clipped here"))

        benchmark = benchmarks.get(row.get("benchmark_id", ""))
        if benchmark is None:
            issues.append(Issue("ERROR", row_id, "benchmark_id", "ID is not registered with a versioned definition and source hash"))
        else:
            for field in ("sector", "reporting_period"):
                if benchmark[field] != row.get(field):
                    issues.append(Issue("ERROR", row_id, "benchmark_id", f"registered benchmark {field} does not match input"))
            if not re.fullmatch(r"[0-9a-f]{64}", benchmark.get("source_hash", "")):
                issues.append(Issue("ERROR", row_id, "benchmark_id", "registered source_hash is not SHA-256"))
            if benchmark.get("status") == "synthetic_only" and synthetic_flag != "yes":
                issues.append(Issue("ERROR", row_id, "benchmark_id", "synthetic-only benchmark cannot score a real-company row"))

    for field in COMPARABILITY_FIELDS:
        values = {row.get(field, "").strip() for row in rows if row.get(field, "").strip()}
        if len(values) > 1:
            severity = "ERROR" if strict else "WARNING"
            issues.append(Issue(severity, "comparison set", field, f"values differ: {', '.join(sorted(values))}"))
    for field in MONETIZATION_COMPARABILITY_FIELDS:
        values = {row.get(field, "").strip() for row in rows if row.get(field, "").strip()}
        if len(values) > 1:
            issues.append(Issue("WARNING", "comparison set", field, f"score comparison remains available, but common monetary comparison is disabled: {', '.join(sorted(values))}"))
    return rows, issues


def validate_provenance_rows(path: Path, company_rows: list[dict[str, str]]) -> list[Issue]:
    fields, rows = read_csv(path)
    issues: list[Issue] = []
    required = [
        "observation_id", "variable_name", "source_id", "source_date", "input_quality",
        "construction_mode", "carry_lag_q", "benchmark_id", "formula_note", "synthetic_flag",
    ]
    for field in required:
        if field not in fields:
            issues.append(Issue("ERROR", "provenance header", field, "required provenance column is missing"))
    if issues:
        return issues
    companies = {row["observation_id"]: row for row in company_rows}
    definitions = {row["variable_name"]: row for row in active_definitions()}
    expected = {(company_id, variable) for company_id in companies for variable in definitions}
    observed: set[tuple[str, str]] = set()
    for row_number, row in enumerate(rows, start=2):
        raw_row_id = row.get("observation_id", "")
        row_id = raw_row_id or f"CSV row {row_number}"
        variable = row.get("variable_name", "")
        id_error = observation_id_error(raw_row_id)
        if id_error:
            issues.append(Issue("ERROR", row_id, "observation_id", id_error))
        key = (row_id, variable)
        if key in observed:
            issues.append(Issue("ERROR", row_id, variable, "duplicate feature provenance row"))
        observed.add(key)
        company = companies.get(row_id)
        definition = definitions.get(variable)
        if company is None:
            issues.append(Issue("ERROR", row_id, "observation_id", "no matching company input"))
            continue
        if definition is None:
            issues.append(Issue("ERROR", row_id, "variable_name", "not an active CPII feature"))
            continue
        if not row.get("source_id", "").strip() or not row.get("formula_note", "").strip():
            issues.append(Issue("ERROR", row_id, variable, "source_id and formula_note are required"))
        if not valid_source_date(row.get("source_date", "")):
            issues.append(Issue("ERROR", row_id, variable, "source_date must be a real YYYY-MM-DD date from 2000 through 2100"))
        if row.get("input_quality") not in QUALITIES:
            issues.append(Issue("ERROR", row_id, variable, "invalid input_quality"))
        if row.get("construction_mode") not in FEATURE_CONSTRUCTION_MODES:
            issues.append(Issue("ERROR", row_id, variable, "use direct, derived, or proxy"))
        try:
            lag = int(row.get("carry_lag_q", ""))
            if lag < 0:
                raise ValueError
            if lag > 1:
                issues.append(Issue("WARNING", row_id, variable, "feature source is carried more than one quarter"))
        except ValueError:
            issues.append(Issue("ERROR", row_id, variable, "carry_lag_q must be nonnegative integer"))
        requires_benchmark = definition["requires_benchmark"] == "yes"
        if requires_benchmark and row.get("benchmark_id") != company.get("benchmark_id"):
            issues.append(Issue("ERROR", row_id, variable, "benchmark-gap feature must use the registered company benchmark_id"))
        if not requires_benchmark and row.get("benchmark_id", "").strip():
            issues.append(Issue("WARNING", row_id, variable, "benchmark_id is ignored for a non-gap feature"))
        if row.get("synthetic_flag") != company.get("synthetic_flag"):
            issues.append(Issue("ERROR", row_id, variable, "synthetic flag does not match company row"))
    for missing_id, missing_variable in sorted(expected - observed):
        issues.append(Issue("ERROR", missing_id, missing_variable, "feature-level provenance row is missing"))
    return issues


def validate_exposure_rows(path: Path, company_rows: list[dict[str, str]]) -> list[Issue]:
    fields, rows = read_csv(path)
    issues: list[Issue] = []
    required = ["observation_id", "currency", "price_year", "exposure_period", "period_year_fraction", "exposure_source_id", "exposure_quality"]
    value_fields = [f"{base}_{case}" for base in EXPOSURE_BASES for case in ("low", "base", "high")]
    for field in required + value_fields:
        if field not in fields:
            issues.append(Issue("ERROR", "exposure header", field, "required exposure column is missing"))
    if issues:
        return issues
    companies = {row["observation_id"]: row for row in company_rows}
    exposure_ids: set[str] = set()
    matched_rows: list[tuple[dict[str, str], dict[str, str]]] = []
    for row_number, row in enumerate(rows, start=2):
        raw_row_id = row.get("observation_id", "")
        row_id = raw_row_id.strip() or f"CSV row {row_number}"
        id_error = observation_id_error(raw_row_id)
        if id_error:
            issues.append(Issue("ERROR", row_id, "observation_id", id_error))
        if row_id in exposure_ids:
            issues.append(Issue("ERROR", row_id, "observation_id", "duplicate exposure row"))
        exposure_ids.add(row_id)
        company = companies.get(row_id)
        if company is None:
            issues.append(Issue("ERROR", row_id, "observation_id", "no matching company input row"))
            continue
        matched_rows.append((company, row))
        for field in ("currency", "price_year"):
            if row.get(field, "").strip() != company.get(field, "").strip():
                issues.append(Issue("ERROR", row_id, field, "does not match company input"))
        if row.get("exposure_quality") not in QUALITIES:
            issues.append(Issue("ERROR", row_id, "exposure_quality", "use A, B, C, or SYNTHETIC"))
        period = row.get("exposure_period", "")
        company_period = company.get("reporting_period", "")
        if period != company_period and period != company_period[:4]:
            issues.append(Issue("ERROR", row_id, "exposure_period", "must equal feature quarter or its calendar year"))
        try:
            fraction = parse_number(row.get("period_year_fraction", ""))
            if not 0 < fraction <= 1:
                raise ValueError
        except ValueError:
            issues.append(Issue("ERROR", row_id, "period_year_fraction", "expected a number greater than 0 and no greater than 1"))
        supplied = False
        for base in EXPOSURE_BASES:
            values: list[float | None] = []
            for case in ("low", "base", "high"):
                field = f"{base}_{case}"
                text = row.get(field, "").strip()
                if not text:
                    values.append(None)
                    continue
                supplied = True
                try:
                    value = parse_number(text)
                    upper = 1 if base == "scenario_conversion_rate" else math.inf
                    if not 0 <= value <= upper:
                        raise ValueError
                    values.append(value)
                except ValueError:
                    values.append(None)
                    issues.append(Issue("ERROR", row_id, field, "expected a nonnegative finite number" + (" no greater than 1" if base == "scenario_conversion_rate" else "")))
            present = sum(value is not None for value in values)
            if present not in {0, 3}:
                issues.append(Issue("ERROR", row_id, base, "supply a complete low/base/high triplet or leave all three blank"))
            if present == 3 and not (values[0] <= values[1] <= values[2]):
                issues.append(Issue("ERROR", row_id, base, "expected low <= base <= high"))
        if supplied and not row.get("exposure_source_id", "").strip():
            issues.append(Issue("ERROR", row_id, "exposure_source_id", "required when any economic exposure is supplied"))
        scenario_values = [row.get(f"scenario_conversion_rate_{case}", "").strip() for case in ("low", "base", "high")]
        market_values = [row.get(f"eligible_market_revenue_{case}", "").strip() for case in ("low", "base", "high")]
        if any(scenario_values) != any(market_values):
            issues.append(Issue("ERROR", row_id, "cross_market_transfer_index", "scenario conversion rate and eligible market revenue must be supplied together"))

    exposure_cohorts: dict[tuple[str, ...], list[dict[str, str]]] = {}
    for company, exposure in matched_rows:
        key = tuple(
            company.get(field, "").strip()
            for field in COMPARABILITY_FIELDS + MONETIZATION_COMPARABILITY_FIELDS
        )
        exposure_cohorts.setdefault(key, []).append(exposure)
    for cohort_rows in exposure_cohorts.values():
        if len(cohort_rows) < 2:
            continue
        periods = {row.get("exposure_period", "").strip() for row in cohort_rows}
        if len(periods) > 1:
            issues.append(
                Issue(
                    "ERROR",
                    "economic comparison set",
                    "exposure_period",
                    "comparable companies must use the same exposure period basis: " + ", ".join(sorted(periods)),
                )
            )
        fractions: list[float] = []
        for row in cohort_rows:
            try:
                fraction = parse_number(row.get("period_year_fraction", ""))
            except ValueError:
                continue
            if 0 < fraction <= 1:
                fractions.append(fraction)
        if fractions and any(
            not math.isclose(value, fractions[0], rel_tol=0.0, abs_tol=1e-12)
            for value in fractions[1:]
        ):
            issues.append(
                Issue(
                    "ERROR",
                    "economic comparison set",
                    "period_year_fraction",
                    "comparable companies must use the same period fraction: "
                    + ", ".join(f"{value:g}" for value in sorted(set(fractions))),
                )
            )
    for missing in sorted(set(companies) - exposure_ids):
        issues.append(Issue("WARNING", missing, "economic_exposure", "score remains available; monetary interpretation is disabled"))
    return issues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("company_csv", type=Path)
    parser.add_argument("--exposures", type=Path)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--allow-incomparable", action="store_true", help="downgrade cross-row comparability errors to warnings")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        company_rows, issues = validate_company_rows(args.company_csv, strict=not args.allow_incomparable)
        if args.exposures:
            issues.extend(validate_exposure_rows(args.exposures, company_rows))
        else:
            issues.append(Issue("WARNING", "file", "economic_exposure", "not supplied; CPII scoring is enabled and monetary interpretation is disabled"))
        if args.provenance:
            issues.extend(validate_provenance_rows(args.provenance, company_rows))
        else:
            issues.append(Issue("WARNING", "file", "feature_provenance", "not supplied; scores are calculable but auditability is incomplete"))
    except (OSError, ValueError, csv.Error) as exc:
        print(f"ERROR [file] csv: {exc}", file=sys.stderr)
        return 1
    for issue in issues:
        print(issue.render())
    errors = sum(issue.severity == "ERROR" for issue in issues)
    warnings = sum(issue.severity == "WARNING" for issue in issues)
    if errors:
        print(f"FAIL input validation: {errors} error(s), {warnings} warning(s)", file=sys.stderr)
        return 1
    print(f"PASS input validation: {len(company_rows)} companies, {warnings} warning(s); strict CPII scoring enabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
