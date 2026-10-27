#!/usr/bin/env python3
"""Build deterministic fictional-company CPII examples and all derived outputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
from typing import Any, Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.cpii_simulator.compare import compare_companies
    from scripts.cpii_simulator.decompose import decompose_pair
    from scripts.cpii_simulator.economic_bridge import flatten_monetization, monetize_pair
    from scripts.cpii_simulator.engine import flatten_score, score_rows
    from scripts.cpii_simulator.narrative import build_pair_narrative
    from scripts.cpii_simulator.sensitivity import analyze_pair_sensitivity
    from scripts.cpii_simulator.validate_input import (
        validate_company_rows,
        validate_exposure_rows,
        validate_provenance_rows,
    )
else:
    from .compare import compare_companies
    from .decompose import decompose_pair
    from .economic_bridge import flatten_monetization, monetize_pair
    from .engine import flatten_score, score_rows
    from .narrative import build_pair_narrative
    from .sensitivity import analyze_pair_sensitivity
    from .validate_input import validate_company_rows, validate_exposure_rows, validate_provenance_rows


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = PROJECT_ROOT / "data" / "processed" / "cpii_simulator" / "examples"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "tables" / "cpii_simulator" / "examples"
LOG_PATH = PROJECT_ROOT / "logs" / "cpii_fictional_example_generation.md"
BUILD_DATE = "2026-09-02"

FEATURES = [
    "effective_tax_rate_gap", "network_cost_ratio", "infra_dependency_ratio",
    "funding_cost_spread", "ip_assetization_gap", "investment_recovery_ratio",
    "cashflow_recovery_ratio", "cross_market_transfer_index",
    "foreign_dependency_ratio", "outflow_to_capex_ratio",
]
COMPANY_FIELDS = [
    "observation_id", "company_name", "company_group", "sector", "service_scope",
    "focal_market", "reporting_period", "benchmark_id", "currency", "price_year",
    "input_quality", "synthetic_flag", "construction_mode", "source_id", "source_date",
    "carry_lag_q", "market_common_exposure_adjusted", "company_exposure_factor", "source_note",
] + FEATURES
EXPOSURE_BASES = [
    "revenue", "positive_pretax_income", "average_interest_bearing_debt",
    "content_investment", "eligible_market_revenue", "scenario_conversion_rate",
]
EXPOSURE_FIELDS = [
    "observation_id", "currency", "price_year", "exposure_period", "period_year_fraction",
] + [f"{name}_{case}" for name in EXPOSURE_BASES for case in ("low", "base", "high")] + [
    "exposure_source_id", "exposure_quality", "exposure_note",
]
PROVENANCE_FIELDS = [
    "observation_id", "variable_name", "source_id", "source_date", "input_quality",
    "construction_mode", "carry_lag_q", "benchmark_id", "formula_note", "synthetic_flag",
]
RANGE_FIELDS = ["observation_id", "variable_name", "low", "base", "high", "range_type", "source_id"]


def base_metadata(row_id: str, name: str, group: str, exposure_factor: float) -> dict[str, Any]:
    return {
        "observation_id": row_id,
        "company_name": name,
        "company_group": group,
        "sector": "digital_content",
        "service_scope": "integrated_content",
        "focal_market": "Korea",
        "reporting_period": "2025Q4",
        "benchmark_id": "BM-DIGITAL-CONTENT-2025Q4",
        "currency": "KRW",
        "price_year": 2025,
        "input_quality": "SYNTHETIC",
        "synthetic_flag": "yes",
        "construction_mode": "derived",
        "source_id": "SYNTHETIC-METHOD-DEMO",
        "source_date": "2025-12-31",
        "carry_lag_q": 0,
        "market_common_exposure_adjusted": "yes",
        "company_exposure_factor": exposure_factor,
        "source_note": "방법론 설명용 합성자료; 실제 기업 추정이 아님",
    }


def fictional_companies() -> list[dict[str, Any]]:
    definitions = [
        ("SYN-A", "가온 콘텐츠", "domestic", 0.82, [-0.020, 0.180, 0.13320, 0.012, 0.080, 3.20, 0.42, 0.28, 0.74, 8.5]),
        ("SYN-B", "누리 미디어", "foreign", 0.70, [-0.055, 0.105, 0.06405, 0.004, 0.025, 4.10, 0.73, 0.16, 0.61, 4.0]),
        ("SYN-C", "다온 스토리", "foreign", 0.64, [0.010, 0.145, 0.09860, 0.018, 0.110, 2.65, 0.18, 0.34, 0.68, 6.8]),
        ("SYN-D", "라온 플레이", "domestic", 0.77, [-0.005, 0.160, 0.11360, 0.009, 0.065, 3.55, 0.51, 0.24, 0.71, 7.4]),
    ]
    rows: list[dict[str, Any]] = []
    for row_id, name, group, exposure_factor, values in definitions:
        row = base_metadata(row_id, name, group, exposure_factor)
        row.update(dict(zip(FEATURES, values)))
        rows.append(row)
    return rows


def exposure_row(
    row_id: str,
    revenue: float,
    pretax: float,
    debt: float,
    investment: float,
    eligible_revenue: float,
    conversion: float,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "observation_id": row_id,
        "currency": "KRW",
        "price_year": 2025,
        "exposure_period": "2025",
        "period_year_fraction": 1.0,
        "exposure_source_id": "SYNTHETIC-ECON-DEMO",
        "exposure_quality": "SYNTHETIC",
        "exposure_note": "방법론 설명용 합성 노출액; low/high는 신뢰구간이 아님",
    }
    values = {
        "revenue": revenue,
        "positive_pretax_income": pretax,
        "average_interest_bearing_debt": debt,
        "content_investment": investment,
        "eligible_market_revenue": eligible_revenue,
        "scenario_conversion_rate": conversion,
    }
    for base, value in values.items():
        low_factor, high_factor = (0.8, 1.2) if base == "scenario_conversion_rate" else (0.9, 1.1)
        row[f"{base}_low"] = value * low_factor
        row[f"{base}_base"] = value
        row[f"{base}_high"] = min(1.0, value * high_factor) if base == "scenario_conversion_rate" else value * high_factor
    return row


def fictional_exposures(company_rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    parameters = {
        "SYN-A": (1.0e12, 8.0e10, 3.0e11, 2.2e11, 2.5e11, 0.04),
        "SYN-B": (1.4e12, 1.4e11, 2.2e11, 1.8e11, 3.5e11, 0.025),
        "SYN-C": (6.0e11, 3.0e10, 1.5e11, 2.0e11, 1.8e11, 0.06),
        "SYN-D": (2.0e12, 2.0e11, 4.0e11, 3.0e11, 5.0e11, 0.03),
    }
    return [exposure_row(row["observation_id"], *parameters[str(row["observation_id"])]) for row in company_rows]


def feature_provenance(company_rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    gap_features = {"effective_tax_rate_gap", "funding_cost_spread", "ip_assetization_gap"}
    rows: list[dict[str, Any]] = []
    for company in company_rows:
        for name in FEATURES:
            mode = "derived" if name in gap_features or name in {"infra_dependency_ratio", "cross_market_transfer_index", "outflow_to_capex_ratio"} else "direct"
            rows.append(
                {
                    "observation_id": company["observation_id"],
                    "variable_name": name,
                    "source_id": f"SYNTHETIC-{company['observation_id']}-{name}",
                    "source_date": "2025-12-31",
                    "input_quality": "SYNTHETIC",
                    "construction_mode": mode,
                    "carry_lag_q": 0,
                    "benchmark_id": company["benchmark_id"] if name in gap_features else "",
                    "formula_note": "방법론 설명용 통제 입력; 실제 공시·추정값이 아님",
                    "synthetic_flag": "yes",
                }
            )
    return rows


def feature_ranges(company_rows: list[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, tuple[float, float, float]]]]:
    rows: list[dict[str, Any]] = []
    mapping: dict[str, dict[str, tuple[float, float, float]]] = {}
    for company in company_rows:
        row_id = str(company["observation_id"])
        mapping[row_id] = {}
        for name in FEATURES:
            base = float(company[name])
            span = max(abs(base) * 0.05, 0.001 if "ratio" in name or "gap" in name or "index" in name else 0.02)
            triplet = (base - span, base, base + span)
            mapping[row_id][name] = triplet
            rows.append(
                {
                    "observation_id": row_id,
                    "variable_name": name,
                    "low": triplet[0],
                    "base": triplet[1],
                    "high": triplet[2],
                    "range_type": "assumption",
                    "source_id": "SYNTHETIC-RANGE-DEMO",
                }
            )
    return rows, mapping


def golden_companies() -> list[dict[str, Any]]:
    template = fictional_companies()[0]
    rows: list[dict[str, Any]] = []
    for row_id, name, group in (
        ("GOLD-N-A", "가상 네트워크 A", "domestic"),
        ("GOLD-N-B", "가상 네트워크 B", "foreign"),
        ("GOLD-F-A", "가상 조달 A", "domestic"),
        ("GOLD-F-B", "가상 조달 B", "foreign"),
    ):
        row = dict(template)
        row.update(base_metadata(row_id, name, group, 0.75))
        row["source_note"] = "같은 CPII 점수차·다른 금액을 보이는 1-feature 통제 실험용 합성자료"
        rows.append(row)
    rows[0]["network_cost_ratio"] = 0.446823515
    rows[1]["network_cost_ratio"] = 0.3470713765
    rows[2]["funding_cost_spread"] = 0.0
    rows[3]["funding_cost_spread"] = -0.001999222
    return rows


def golden_exposures(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        exposure_row(str(row["observation_id"]), 1.0e12, 1.0e11, 1.0e11, 2.0e11, 2.5e11, 0.05)
        for row in rows
    ]


def csv_text(rows: list[Mapping[str, Any]], fields: list[str] | None = None) -> str:
    if not rows:
        return ""
    fieldnames = fields or list(rows[0])
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def matrix_text(matrix: tuple[list[str], list[list[Any]]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(matrix[0])
    writer.writerows(matrix[1])
    return buffer.getvalue()


def build_artifacts() -> dict[Path, str]:
    companies = fictional_companies()
    exposures = fictional_exposures(companies)
    exposure_map = {str(row["observation_id"]): row for row in exposures}
    provenance = feature_provenance(companies)
    ranges_rows, ranges_map = feature_ranges(companies)
    comparison = compare_companies(companies)
    pair_by_id = {row["pair_id"]: row for row in comparison["pairs"]}
    score_by_id = {str(row["observation_id"]): row for row in comparison["scored"]}

    decompositions: list[dict[str, Any]] = []
    economic_rows: list[dict[str, Any]] = []
    sensitivity_summaries: list[dict[str, Any]] = []
    sensitivity_variants: list[dict[str, Any]] = []
    narratives: list[dict[str, Any]] = []
    for pair_id, pair in pair_by_id.items():
        score_a = score_by_id[str(pair["observation_id_a"])]
        score_b = score_by_id[str(pair["observation_id_b"])]
        input_a = next(row for row in companies if row["observation_id"] == pair["observation_id_a"])
        input_b = next(row for row in companies if row["observation_id"] == pair["observation_id_b"])
        decomposition = decompose_pair(score_a, score_b)
        economic = monetize_pair(score_a, score_b, exposure_map)
        pair_ranges = {
            str(input_a["observation_id"]): ranges_map[str(input_a["observation_id"])],
            str(input_b["observation_id"]): ranges_map[str(input_b["observation_id"])],
        }
        sensitivity = analyze_pair_sensitivity(input_a, input_b, ranges=pair_ranges)
        narrative = build_pair_narrative(pair, decomposition, sensitivity, economic)
        decompositions.extend(decomposition["features"])
        economic_rows.extend(flatten_monetization(economic))
        summary = {key: value for key, value in sensitivity.items() if key != "variants" and not isinstance(value, list)}
        summary["dependency_warnings_a"] = "|".join(sensitivity["dependency_warnings_a"])
        summary["dependency_warnings_b"] = "|".join(sensitivity["dependency_warnings_b"])
        sensitivity_summaries.append(summary)
        sensitivity_variants.extend({"pair_id": pair_id, **row} for row in sensitivity["variants"])
        narratives.append({"pair_id": pair_id, **narrative})

    golden = golden_companies()
    golden_exp = golden_exposures(golden)
    golden_exp_map = {str(row["observation_id"]): row for row in golden_exp}
    golden_scores = score_rows(golden, strict=True)
    golden_score_map = {str(row["observation_id"]): row for row in golden_scores}
    golden_summary: list[dict[str, Any]] = []
    for pair_name, left, right, driver in (
        ("network_cost_channel", "GOLD-N-A", "GOLD-N-B", "network_cost_ratio"),
        ("funding_cost_channel", "GOLD-F-A", "GOLD-F-B", "funding_cost_spread"),
    ):
        a, b = golden_score_map[left], golden_score_map[right]
        money = monetize_pair(a, b, golden_exp_map)
        channel = next(row for row in money["rows"] if row["variable_name"] == driver)
        golden_summary.append(
            {
                "example_pair": pair_name,
                "observation_id_a": left,
                "observation_id_b": right,
                "single_changed_driver": driver,
                "delta_cpii_points": float(a["CPII"]) - float(b["CPII"]),
                "common_exposure_base": channel["common_exposure_base"],
                "common_size_amount_base_krw": channel["common_size_amount_base"],
                "interpretation_class": channel["interpretation_class"],
                "synthetic_disclaimer": "methodology_only_not_real_company_estimate",
            }
        )
    amount_ratio = golden_summary[0]["common_size_amount_base_krw"] / golden_summary[1]["common_size_amount_base_krw"]

    artifacts: dict[Path, str] = {
        INPUT_DIR / "fictional_companies.csv": csv_text(companies, COMPANY_FIELDS),
        INPUT_DIR / "fictional_exposures.csv": csv_text(exposures, EXPOSURE_FIELDS),
        INPUT_DIR / "fictional_feature_provenance.csv": csv_text(provenance, PROVENANCE_FIELDS),
        INPUT_DIR / "fictional_feature_ranges.csv": csv_text(ranges_rows, RANGE_FIELDS),
        INPUT_DIR / "golden_equal_gap_companies.csv": csv_text(golden, COMPANY_FIELDS),
        INPUT_DIR / "golden_equal_gap_exposures.csv": csv_text(golden_exp, EXPOSURE_FIELDS),
        OUTPUT_DIR / "company_scores.csv": csv_text([flatten_score(row) for row in comparison["scored"]]),
        OUTPUT_DIR / "company_ranking.csv": csv_text(comparison["ranking"]),
        OUTPUT_DIR / "pair_gaps.csv": csv_text(comparison["pairs"]),
        OUTPUT_DIR / "pair_gap_matrix.csv": matrix_text(comparison["matrix"]),
        OUTPUT_DIR / "pair_contributions.csv": csv_text(decompositions),
        OUTPUT_DIR / "economic_interpretations.csv": csv_text(economic_rows),
        OUTPUT_DIR / "sensitivity_summary.csv": csv_text(sensitivity_summaries),
        OUTPUT_DIR / "sensitivity_variants.csv": csv_text(sensitivity_variants),
        OUTPUT_DIR / "pair_narratives.csv": csv_text(narratives),
        OUTPUT_DIR / "golden_equal_gap_summary.csv": csv_text(golden_summary),
    }
    manifest_payload = {
        "build_date": BUILD_DATE,
        "synthetic_data": True,
        "company_count": len(companies),
        "unordered_pair_count": len(comparison["pairs"]),
        "golden_pair_count": len(golden_summary),
        "golden_gap_difference_points": abs(golden_summary[0]["delta_cpii_points"] - golden_summary[1]["delta_cpii_points"]),
        "golden_amount_ratio": amount_ratio,
        "files_sha256": {
            str(path.relative_to(PROJECT_ROOT)): hashlib.sha256(text.encode("utf-8")).hexdigest()
            for path, text in sorted(artifacts.items(), key=lambda item: str(item[0]))
        },
    }
    artifacts[OUTPUT_DIR / "example_manifest.json"] = json.dumps(manifest_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    log = [
        "# CPII Fictional Example Generation Log",
        "",
        f"- Build date: `{BUILD_DATE}`",
        "- Data status: `synthetic_methodology_demo_only`",
        f"- Main companies: `{len(companies)}`",
        f"- Main unordered pairs: `{len(comparison['pairs'])}`",
        f"- Golden controlled pairs: `{len(golden_summary)}`",
        f"- Golden CPII gap difference: `{manifest_payload['golden_gap_difference_points']:.12g}` points",
        f"- Golden economic amount ratio (network/funding): `{amount_ratio:.3f}x`",
        "- Every score, rank, pair gap, contribution, economic channel, sensitivity result, and narrative is regenerated by this script.",
        "- Low/base/high outputs are deterministic sensitivity ranges, not confidence intervals.",
        "- Monetary channels are never summed because interpretation classes and overlap families differ.",
        "- No row estimates or names a real company.",
        "",
    ]
    artifacts[LOG_PATH] = "\n".join(log)
    return artifacts


def validate_generated_inputs(artifacts: Mapping[Path, str]) -> None:
    companies_path = INPUT_DIR / "fictional_companies.csv"
    exposures_path = INPUT_DIR / "fictional_exposures.csv"
    provenance_path = INPUT_DIR / "fictional_feature_provenance.csv"
    company_rows, issues = validate_company_rows(companies_path, strict=True)
    issues.extend(validate_exposure_rows(exposures_path, company_rows))
    issues.extend(validate_provenance_rows(provenance_path, company_rows))
    errors = [issue for issue in issues if issue.severity == "ERROR"]
    if errors:
        raise ValueError("generated example validation failed: " + "; ".join(issue.render() for issue in errors))
    manifest = json.loads(artifacts[OUTPUT_DIR / "example_manifest.json"])
    if manifest["golden_gap_difference_points"] > 1e-9:
        raise ValueError("golden pair CPII gaps are not equal within 1e-9")
    if manifest["golden_amount_ratio"] < 400:
        raise ValueError("golden pair does not demonstrate sufficiently different economic amounts")


def write_or_check(check: bool) -> None:
    artifacts = build_artifacts()
    if check:
        for path, content in artifacts.items():
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise ValueError(f"missing or stale generated example: {path.relative_to(PROJECT_ROOT)}")
        validate_generated_inputs(artifacts)
        print("PASS fictional examples: 4-company n-mode, 6 pairs, 2 equal-gap golden pairs, >400x amount contrast")
        return
    for path, content in artifacts.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    validate_generated_inputs(artifacts)
    print("WROTE fictional examples and all derived outputs")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        write_or_check(args.check)
    except (OSError, ValueError, KeyError, csv.Error) as exc:
        print(f"FAIL fictional examples: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
