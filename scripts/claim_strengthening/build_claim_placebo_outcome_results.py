from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PLACEBO_REGISTRY_PATH = (
    PROJECT_ROOT / "data/registry/claim_strengthening/placebo_event_registry.csv"
)
EVENT_PANEL_PATH = PROJECT_ROOT / "data/processed/event_study_panel.csv"
OUTPUT_TABLE_PATH = (
    PROJECT_ROOT / "outputs/tables/claim_strengthening/T_claim_placebo_outcome_results.csv"
)


OUTCOME_SPECS = [
    {
        "outcome_variable": "foreign_dependency_ratio",
        "outcome_label": "Foreign dependency ratio",
        "placebo_type": "structural_exposure_placebo",
        "why_placebo_outcome": (
            "Foreign dependency is a slow-moving structural exposure metric and should not jump because of "
            "domestic self-upgrades or Korean-owned foreign expansion placebo events."
        ),
    },
    {
        "outcome_variable": "available_variable_count",
        "outcome_label": "Available variable count",
        "placebo_type": "measurement_diagnostic_placebo",
        "why_placebo_outcome": (
            "Observed variable count is a data-availability diagnostic rather than an economic claim outcome, "
            "so systematic event-time movement would indicate measurement instability rather than reverse discrimination."
        ),
    },
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def to_float(value: str) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normal_p_value(t_value: float) -> float:
    return math.erfc(abs(t_value) / math.sqrt(2.0))


@dataclass
class RegressionResult:
    coefficients: dict[str, float]
    std_errors: dict[str, float]
    p_values: dict[str, float]
    n_obs: int
    rank: int
    r_squared: float
    residual_df: int


def fit_ols(
    rows: list[dict[str, str]],
    dependent_var: str,
    explanatory_vars: list[str],
    fixed_effect_vars: list[str],
) -> RegressionResult:
    categories: dict[str, list[str]] = {}
    for fe_var in fixed_effect_vars:
        values = sorted({row[fe_var] for row in rows})
        categories[fe_var] = values[1:]

    param_names = ["Intercept"] + explanatory_vars[:]
    for fe_var in fixed_effect_vars:
        param_names.extend(f"{fe_var}={value}" for value in categories[fe_var])

    x_data: list[list[float]] = []
    y_data: list[float] = []
    for row in rows:
        x_row = [1.0]
        x_row.extend(float(row[var]) for var in explanatory_vars)
        for fe_var in fixed_effect_vars:
            current = row[fe_var]
            for value in categories[fe_var]:
                x_row.append(1.0 if current == value else 0.0)
        x_data.append(x_row)
        y_data.append(float(row[dependent_var]))

    x_mat = np.asarray(x_data, dtype=float)
    y_vec = np.asarray(y_data, dtype=float)
    xtx = x_mat.T @ x_mat
    xtx_inv = np.linalg.pinv(xtx)
    beta = xtx_inv @ (x_mat.T @ y_vec)
    fitted = x_mat @ beta
    resid = y_vec - fitted
    n_obs, k_vars = x_mat.shape
    rank = int(np.linalg.matrix_rank(x_mat))

    meat = np.zeros((k_vars, k_vars), dtype=float)
    for index in range(n_obs):
        x_i = x_mat[index : index + 1].T
        meat += float(resid[index] ** 2) * (x_i @ x_i.T)

    scale = n_obs / max(n_obs - rank, 1)
    cov = scale * (xtx_inv @ meat @ xtx_inv)
    std = np.sqrt(np.maximum(np.diag(cov), 0.0))

    coefficients = {name: float(beta[idx]) for idx, name in enumerate(param_names)}
    std_errors = {name: float(std[idx]) for idx, name in enumerate(param_names)}
    p_values: dict[str, float] = {}
    for idx, name in enumerate(param_names):
        se = std[idx]
        if se <= 0:
            p_values[name] = float("nan")
        else:
            p_values[name] = normal_p_value(float(beta[idx] / se))

    y_mean = float(y_vec.mean())
    tss = float(((y_vec - y_mean) ** 2).sum())
    rss = float((resid**2).sum())
    r_squared = float("nan") if tss == 0 else 1.0 - (rss / tss)

    return RegressionResult(
        coefficients=coefficients,
        std_errors=std_errors,
        p_values=p_values,
        n_obs=n_obs,
        rank=rank,
        r_squared=r_squared,
        residual_df=max(n_obs - rank, 0),
    )


def pretrend_result(result: RegressionResult, lead_vars: list[str]) -> tuple[str, str]:
    if not lead_vars:
        return "not_applicable", "No lead coefficient estimated."
    present = [var for var in lead_vars if var in result.coefficients]
    if not present:
        return "not_testable", "Lead coefficients were dropped or not estimable."

    decision = "pass"
    pieces: list[str] = []
    for var in present:
        coef = result.coefficients.get(var, float("nan"))
        p_val = result.p_values.get(var, float("nan"))
        pieces.append(f"{var}:coef={coef:.4f},p={p_val:.4f}")
        if not math.isnan(p_val) and p_val < 0.10:
            decision = "fail"
    return decision, "; ".join(pieces)


def build_sample(outcome_variable: str) -> tuple[list[dict[str, str]], list[str], str, int]:
    placebo_ids = {row["event_id"] for row in read_csv(PLACEBO_REGISTRY_PATH)}
    filtered: list[dict[str, str]] = []
    for row in read_csv(EVENT_PANEL_PATH):
        if row["event_id"] not in placebo_ids:
            continue
        dep = to_float(row.get(outcome_variable, ""))
        if dep is None:
            continue
        clone = dict(row)
        clone[outcome_variable] = str(dep)
        filtered.append(clone)

    baseline_rel = 0
    rel_values = sorted(
        {
            int(row["relative_period"])
            for row in filtered
            if row["treated_flag"] == "1"
        }
    )
    rel_values = [rel for rel in rel_values if rel != baseline_rel]

    created_vars: list[str] = []
    for rel in rel_values:
        rel_name = f"treated_rel_m{abs(rel)}" if rel < 0 else f"treated_rel_p{rel}"
        created_vars.append(rel_name)
        for row in filtered:
            row[rel_name] = (
                "1"
                if row["treated_flag"] == "1" and int(row["relative_period"]) == rel
                else "0"
            )

    return filtered, created_vars, str(baseline_rel), len(placebo_ids)


def build_rows() -> list[dict[str, str]]:
    output_rows: list[dict[str, str]] = []
    for spec in OUTCOME_SPECS:
        sample_rows, event_vars, baseline_period, placebo_event_count = build_sample(
            spec["outcome_variable"]
        )
        result = fit_ols(
            sample_rows,
            dependent_var=spec["outcome_variable"],
            explanatory_vars=event_vars,
            fixed_effect_vars=["event_id", "service_std", "year_quarter"],
        )
        pretrend_test_result, pretrend_detail = pretrend_result(
            result,
            [var for var in event_vars if var.endswith("m1")],
        )

        for variable in event_vars:
            coefficient = result.coefficients.get(variable, float("nan"))
            p_value = result.p_values.get(variable, float("nan"))
            interpretation_note = (
                "Placebo outcome shows a significant event-time coefficient"
                if not math.isnan(p_value) and p_value < 0.10
                else "Placebo outcome does not show a significant event-time coefficient"
            )
            output_rows.append(
                {
                    "sector_std": "webtoon_story",
                    "model_scope": "placebo_webtoon_outcome_test",
                    "outcome_variable": spec["outcome_variable"],
                    "outcome_label": spec["outcome_label"],
                    "placebo_type": spec["placebo_type"],
                    "why_placebo_outcome": spec["why_placebo_outcome"],
                    "explanatory_variable": variable,
                    "sample_n": str(result.n_obs),
                    "treated_n": str(sum(row["treated_flag"] == "1" for row in sample_rows)),
                    "control_n": str(sum(row["control_flag"] == "1" for row in sample_rows)),
                    "placebo_event_count": str(placebo_event_count),
                    "baseline_period": baseline_period,
                    "coefficient": f"{coefficient:.10f}",
                    "standard_error": f"{result.std_errors.get(variable, float('nan')):.10f}",
                    "p_value": f"{p_value:.10f}",
                    "r_squared": f"{result.r_squared:.10f}",
                    "pretrend_test_result": pretrend_test_result,
                    "pretrend_detail": pretrend_detail,
                    "significant_at_10pct_flag": (
                        "yes" if not math.isnan(p_value) and p_value < 0.10 else "no"
                    ),
                    "interpretation_note": interpretation_note,
                }
            )
    return output_rows


def write_table(rows: list[dict[str, str]]) -> None:
    OUTPUT_TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "sector_std",
        "model_scope",
        "outcome_variable",
        "outcome_label",
        "placebo_type",
        "why_placebo_outcome",
        "explanatory_variable",
        "sample_n",
        "treated_n",
        "control_n",
        "placebo_event_count",
        "baseline_period",
        "coefficient",
        "standard_error",
        "p_value",
        "r_squared",
        "pretrend_test_result",
        "pretrend_detail",
        "significant_at_10pct_flag",
        "interpretation_note",
    ]
    with OUTPUT_TABLE_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    write_table(build_rows())


if __name__ == "__main__":
    main()
