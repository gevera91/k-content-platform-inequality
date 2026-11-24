from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np


ROOT = Path(__file__).resolve().parents[1]

PLATFORM_MONTH_PATH = ROOT / "data/processed/variable_panel_platform_month.csv"
PLATFORM_QUARTER_PATH = ROOT / "data/processed/variable_panel_platform_quarter.csv"
EVENT_PANEL_PATH = ROOT / "data/processed/event_study_panel.csv"
SECTOR_COUNTRY_CPII_PATH = ROOT / "data/processed/cpii_panel_sector_country_quarter.csv"

OUT_MUSIC = ROOT / "outputs/tables/regression_results_music.csv"
OUT_WEBTOON = ROOT / "outputs/tables/regression_results_webtoon.csv"
OUT_INFRA = ROOT / "outputs/tables/regression_results_infra.csv"
OUT_CROSS = ROOT / "outputs/tables/regression_results_cross_country.csv"
OUT_LOG = ROOT / "logs/regression_run_log.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


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
    for i in range(n_obs):
        x_i = x_mat[i : i + 1].T
        meat += float(resid[i] ** 2) * (x_i @ x_i.T)

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


def prepare_numeric_rows(
    rows: list[dict[str, str]],
    dependent_var: str,
    explanatory_vars: list[str],
) -> list[dict[str, str]]:
    prepared: list[dict[str, str]] = []
    for row in rows:
        dep = to_float(row.get(dependent_var, ""))
        if dep is None:
            continue
        ok = True
        clone = dict(row)
        clone[dependent_var] = str(dep)
        for var in explanatory_vars:
            value = to_float(row.get(var, ""))
            if value is None:
                ok = False
                break
            clone[var] = str(value)
        if ok:
            prepared.append(clone)
    return prepared


def make_event_sample(
    rows: list[dict[str, str]],
    sector_std: str,
    dependent_var: str,
    include_medium: bool,
    baseline_rel: int,
) -> tuple[list[dict[str, str]], list[str], str, str]:
    filtered: list[dict[str, str]] = []
    strength_allowed = {"strong", "medium"} if include_medium else {"strong"}
    for row in rows:
        if row["sector_std"] != sector_std:
            continue
        if row["sample_strength"] not in strength_allowed:
            continue
        dep = to_float(row.get(dependent_var, ""))
        if dep is None:
            continue
        clone = dict(row)
        clone[dependent_var] = str(dep)
        filtered.append(clone)

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
        if rel < 0:
            rel_name = f"treated_rel_m{abs(rel)}"
        else:
            rel_name = f"treated_rel_p{rel}"
        created_vars.append(rel_name)
        for row in filtered:
            row[rel_name] = (
                "1"
                if row["treated_flag"] == "1" and int(row["relative_period"]) == rel
                else "0"
            )

    notes = (
        "strong-only"
        if not include_medium
        else "strong+medium"
    )
    return filtered, created_vars, str(baseline_rel), notes


def pretrend_result(
    result: RegressionResult,
    lead_vars: list[str],
) -> tuple[str, str]:
    if not lead_vars:
        return "not_applicable", "No lead coefficient estimated."
    present = [var for var in lead_vars if var in result.coefficients]
    if not present:
        return "not_testable", "Lead coefficients were dropped or not estimable."

    decision = "pass"
    pieces = []
    for var in present:
        p_val = result.p_values.get(var, float("nan"))
        coef = result.coefficients.get(var, float("nan"))
        pieces.append(f"{var}:coef={coef:.4f},p={p_val:.4f}")
        if not math.isnan(p_val) and p_val < 0.10:
            decision = "fail"
    return decision, "; ".join(pieces)


def build_result_rows(
    *,
    sector_std: str,
    model_id: str,
    model_label: str,
    model_type: str,
    model_status: str,
    dependent_var: str,
    explanatory_vars: list[str],
    fixed_effects: list[str],
    sample_rows: list[dict[str, str]],
    result: RegressionResult,
    treated_n: int | None,
    control_n: int | None,
    baseline_period: str,
    pretrend_test_result: str,
    pretrend_detail: str,
    notes: str,
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for explanatory_var in explanatory_vars:
        coef = result.coefficients.get(explanatory_var, float("nan"))
        se = result.std_errors.get(explanatory_var, float("nan"))
        p_val = result.p_values.get(explanatory_var, float("nan"))
        out.append(
            {
                "sector_std": sector_std,
                "model_id": model_id,
                "model_label": model_label,
                "model_type": model_type,
                "model_status": model_status,
                "dependent_variable": dependent_var,
                "explanatory_variable": explanatory_var,
                "sample_n": str(result.n_obs),
                "treated_n": "" if treated_n is None else str(treated_n),
                "control_n": "" if control_n is None else str(control_n),
                "fixed_effects": "|".join(fixed_effects),
                "coefficient": f"{coef:.10f}" if not math.isnan(coef) else "",
                "standard_error": f"{se:.10f}" if not math.isnan(se) else "",
                "p_value": f"{p_val:.10f}" if not math.isnan(p_val) else "",
                "r_squared": f"{result.r_squared:.10f}" if not math.isnan(result.r_squared) else "",
                "residual_df": str(result.residual_df),
                "pretrend_test_result": pretrend_test_result,
                "pretrend_detail": pretrend_detail,
                "baseline_period": baseline_period,
                "notes": notes,
            }
        )
    return out


def run_models() -> dict[str, list[dict[str, str]]]:
    month_rows = read_csv(PLATFORM_MONTH_PATH)
    quarter_rows = read_csv(PLATFORM_QUARTER_PATH)
    event_rows = read_csv(EVENT_PANEL_PATH)
    cross_rows = read_csv(SECTOR_COUNTRY_CPII_PATH)

    results: dict[str, list[dict[str, str]]] = {
        "music": [],
        "webtoon": [],
        "infra": [],
        "cross_country": [],
    }

    # Music FE panel
    music_panel = [
        row for row in month_rows if row["sector_std"] == "music"
    ]
    music_panel = prepare_numeric_rows(
        music_panel,
        dependent_var="investment_recovery_ratio",
        explanatory_vars=["foreign_dependency_ratio"],
    )
    music_panel_result = fit_ols(
        music_panel,
        dependent_var="investment_recovery_ratio",
        explanatory_vars=["foreign_dependency_ratio"],
        fixed_effect_vars=["service_std", "year_month"],
    )
    results["music"].extend(
        build_result_rows(
            sector_std="music",
            model_id="music_service_month_fe_main",
            model_label="Music service-month FE panel",
            model_type="fe_panel",
            model_status="estimated",
            dependent_var="investment_recovery_ratio",
            explanatory_vars=["foreign_dependency_ratio"],
            fixed_effects=["service_std", "year_month"],
            sample_rows=music_panel,
            result=music_panel_result,
            treated_n=None,
            control_n=None,
            baseline_period="",
            pretrend_test_result="not_applicable",
            pretrend_detail="No event-time lead used in the main FE panel.",
            notes="Prompt requested service-month FE for music. Monthly panel exists, so the main FE regression uses the service-month panel directly.",
        )
    )

    # Music event study
    music_event_sample, music_event_vars, music_baseline, music_note = make_event_sample(
        event_rows,
        sector_std="music",
        dependent_var="investment_recovery_ratio",
        include_medium=False,
        baseline_rel=-1,
    )
    music_event_result = fit_ols(
        music_event_sample,
        dependent_var="investment_recovery_ratio",
        explanatory_vars=music_event_vars,
        fixed_effect_vars=["event_id", "service_std", "year_month"],
    )
    music_pretrend_vars = [var for var in music_event_vars if var.endswith("m3") or var.endswith("m2")]
    music_pretrend_result, music_pretrend_detail = pretrend_result(music_event_result, music_pretrend_vars)
    results["music"].extend(
        build_result_rows(
            sector_std="music",
            model_id="music_event_study_spotify_lossless",
            model_label="Music stacked event study on Spotify Lossless rollout",
            model_type="event_study",
            model_status="estimated",
            dependent_var="investment_recovery_ratio",
            explanatory_vars=music_event_vars,
            fixed_effects=["event_id", "service_std", "year_month"],
            sample_rows=music_event_sample,
            result=music_event_result,
            treated_n=sum(row["treated_flag"] == "1" for row in music_event_sample),
            control_n=sum(row["control_flag"] == "1" for row in music_event_sample),
            baseline_period=music_baseline,
            pretrend_test_result=music_pretrend_result,
            pretrend_detail=music_pretrend_detail,
            notes=f"Uses {music_note} events from the official event registry and omits relative period {music_baseline} as the baseline.",
        )
    )

    # Webtoon FE panel
    webtoon_panel = [
        row for row in quarter_rows if row["sector_std"] == "webtoon_story"
    ]
    webtoon_panel = prepare_numeric_rows(
        webtoon_panel,
        dependent_var="investment_recovery_ratio",
        explanatory_vars=["foreign_dependency_ratio"],
    )
    webtoon_panel_result = fit_ols(
        webtoon_panel,
        dependent_var="investment_recovery_ratio",
        explanatory_vars=["foreign_dependency_ratio"],
        fixed_effect_vars=["service_std", "year_quarter"],
    )
    results["webtoon"].extend(
        build_result_rows(
            sector_std="webtoon_story",
            model_id="webtoon_service_quarter_fe_main",
            model_label="Webtoon service-quarter FE panel",
            model_type="fe_panel",
            model_status="estimated",
            dependent_var="investment_recovery_ratio",
            explanatory_vars=["foreign_dependency_ratio"],
            fixed_effects=["service_std", "year_quarter"],
            sample_rows=webtoon_panel,
            result=webtoon_panel_result,
            treated_n=None,
            control_n=None,
            baseline_period="",
            pretrend_test_result="not_applicable",
            pretrend_detail="No event-time lead used in the main FE panel.",
            notes="Title-quarter panel is effectively a single-quarter cross-section in the current build, so the executable FE panel is the service-quarter alternative allowed by the prompt.",
        )
    )

    # Webtoon event study
    webtoon_event_sample, webtoon_event_vars, webtoon_baseline, webtoon_note = make_event_sample(
        event_rows,
        sector_std="webtoon_story",
        dependent_var="investment_recovery_ratio",
        include_medium=False,
        baseline_rel=0,
    )
    webtoon_event_result = fit_ols(
        webtoon_event_sample,
        dependent_var="investment_recovery_ratio",
        explanatory_vars=webtoon_event_vars,
        fixed_effect_vars=["event_id", "service_std", "year_quarter"],
    )
    webtoon_pretrend_vars = [var for var in webtoon_event_vars if var.endswith("m1")]
    webtoon_pretrend_result, webtoon_pretrend_detail = pretrend_result(
        webtoon_event_result, webtoon_pretrend_vars
    )
    results["webtoon"].extend(
        build_result_rows(
            sector_std="webtoon_story",
            model_id="webtoon_event_study_service_launches",
            model_label="Webtoon stacked event study on service-feature launches",
            model_type="event_study",
            model_status="estimated",
            dependent_var="investment_recovery_ratio",
            explanatory_vars=webtoon_event_vars,
            fixed_effects=["event_id", "service_std", "year_quarter"],
            sample_rows=webtoon_event_sample,
            result=webtoon_event_result,
            treated_n=sum(row["treated_flag"] == "1" for row in webtoon_event_sample),
            control_n=sum(row["control_flag"] == "1" for row in webtoon_event_sample),
            baseline_period=webtoon_baseline,
            pretrend_test_result=webtoon_pretrend_result,
            pretrend_detail=webtoon_pretrend_detail,
            notes=f"Uses {webtoon_note} events from the official event registry and omits relative period {webtoon_baseline} as the baseline to keep the single available pre-period testable.",
        )
    )

    # Infra FE panel
    infra_panel = [
        row for row in quarter_rows if row["sector_std"] == "digital_infra"
    ]
    infra_panel = prepare_numeric_rows(
        infra_panel,
        dependent_var="outflow_to_capex_ratio",
        explanatory_vars=["foreign_dependency_ratio", "network_cost_ratio"],
    )
    infra_panel_result = fit_ols(
        infra_panel,
        dependent_var="outflow_to_capex_ratio",
        explanatory_vars=["foreign_dependency_ratio", "network_cost_ratio"],
        fixed_effect_vars=["service_std", "year_quarter"],
    )
    results["infra"].extend(
        build_result_rows(
            sector_std="digital_infra",
            model_id="infra_service_quarter_fe_main",
            model_label="Digital infra service-quarter FE panel",
            model_type="fe_panel",
            model_status="estimated",
            dependent_var="outflow_to_capex_ratio",
            explanatory_vars=["foreign_dependency_ratio", "network_cost_ratio"],
            fixed_effects=["service_std", "year_quarter"],
            sample_rows=infra_panel,
            result=infra_panel_result,
            treated_n=None,
            control_n=None,
            baseline_period="",
            pretrend_test_result="not_applicable",
            pretrend_detail="No event-time lead used in the main FE panel.",
            notes="Monthly digital-infra panel is not available in the current data build, so the executable minimum model is the service-quarter FE variant.",
        )
    )

    # Cross-country sector-country panel
    cross_sample = prepare_numeric_rows(
        cross_rows,
        dependent_var="I_market",
        explanatory_vars=["I_reg", "I_risk"],
    )
    cross_result = fit_ols(
        cross_sample,
        dependent_var="I_market",
        explanatory_vars=["I_reg", "I_risk"],
        fixed_effect_vars=["sector_std", "year_quarter"],
    )
    results["cross_country"].extend(
        build_result_rows(
            sector_std="cross_country",
            model_id="cross_country_sector_country_panel",
            model_label="Cross-country sector-country quarter panel",
            model_type="sector_country_panel",
            model_status="estimated",
            dependent_var="I_market",
            explanatory_vars=["I_reg", "I_risk"],
            fixed_effects=["sector_std", "year_quarter"],
            sample_rows=cross_sample,
            result=cross_result,
            treated_n=None,
            control_n=None,
            baseline_period="",
            pretrend_test_result="not_applicable",
            pretrend_detail="No event-time lead used in the sector-country panel.",
            notes="Cross-country support regression uses the sector-country-quarter panel to test how regulatory and risk asymmetries relate to market-level imbalance.",
        )
    )

    return results


def result_fieldnames(rows: Iterable[dict[str, str]]) -> list[str]:
    preferred = [
        "sector_std",
        "model_id",
        "model_label",
        "model_type",
        "model_status",
        "dependent_variable",
        "explanatory_variable",
        "sample_n",
        "treated_n",
        "control_n",
        "fixed_effects",
        "coefficient",
        "standard_error",
        "p_value",
        "r_squared",
        "residual_df",
        "pretrend_test_result",
        "pretrend_detail",
        "baseline_period",
        "notes",
    ]
    all_keys = set().union(*(row.keys() for row in rows))
    extras = sorted(key for key in all_keys if key not in preferred)
    return preferred + extras


def write_log(results: dict[str, list[dict[str, str]]]) -> None:
    def summarize(rows: list[dict[str, str]]) -> str:
        model_ids = []
        seen = set()
        for row in rows:
            model_id = row["model_id"]
            if model_id not in seen:
                seen.add(model_id)
                model_ids.append(model_id)
        lines = []
        for model_id in model_ids:
            subset = [row for row in rows if row["model_id"] == model_id]
            ref = subset[0]
            lines.append(
                "- "
                f"`{model_id}` | y=`{ref['dependent_variable']}` | "
                f"x={','.join(row['explanatory_variable'] for row in subset)} | "
                f"n=`{ref['sample_n']}` | FE=`{ref['fixed_effects']}` | "
                f"pretrend=`{ref['pretrend_test_result']}`"
            )
        return "\n".join(lines)

    content = f"""# Exec Prompt 31 Regression Run Log

## Model Summary

### Music
{summarize(results['music'])}

### Webtoon
{summarize(results['webtoon'])}

### Digital Infra
{summarize(results['infra'])}

### Cross-country
{summarize(results['cross_country'])}

## Notes

- Estimation uses `numpy` OLS with HC1 heteroskedasticity-robust standard errors because `statsmodels` is not installed in the current environment.
- Coefficient p-values use a large-sample normal approximation.
- Music event-study baseline is `relative_period = -1`; the current executable sample retains an explicit pretrend check on the available negative lead terms that survive the final nonmissing filter.
- Webtoon event-study baseline is `relative_period = 0` because the current strong-event stack only exposes one usable pre-period `-1`; this keeps a minimal pretrend test feasible.
- Digital infra monthly service panel is unavailable in the current build, so the executed infra main model uses `service-quarter` FE instead of `service-month`.
"""
    OUT_LOG.write_text(content, encoding="utf-8")


def main() -> None:
    results = run_models()
    write_csv(OUT_MUSIC, results["music"], result_fieldnames(results["music"]))
    write_csv(OUT_WEBTOON, results["webtoon"], result_fieldnames(results["webtoon"]))
    write_csv(OUT_INFRA, results["infra"], result_fieldnames(results["infra"]))
    write_csv(OUT_CROSS, results["cross_country"], result_fieldnames(results["cross_country"]))
    write_log(results)


if __name__ == "__main__":
    main()
