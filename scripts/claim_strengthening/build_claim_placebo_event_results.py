from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PLACEBO_REGISTRY_PATH = (
    PROJECT_ROOT / "data/registry/claim_strengthening/placebo_event_registry.csv"
)
EVENT_PANEL_PATH = PROJECT_ROOT / "data/processed/event_study_panel.csv"
ACTUAL_RESULTS_PATH = PROJECT_ROOT / "outputs/tables/regression_results_webtoon.csv"

OUTPUT_TABLE_PATH = (
    PROJECT_ROOT / "outputs/tables/claim_strengthening/T_claim_placebo_event_results.csv"
)
OUTPUT_FIGURE_PATH = (
    PROJECT_ROOT / "outputs/figures/claim_strengthening/F_claim_placebo_event_plot.png"
)


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


def build_placebo_event_sample() -> tuple[list[dict[str, str]], list[str], str, int]:
    placebo_ids = {row["event_id"] for row in read_csv(PLACEBO_REGISTRY_PATH)}
    filtered: list[dict[str, str]] = []
    for row in read_csv(EVENT_PANEL_PATH):
        if row["event_id"] not in placebo_ids:
            continue
        dep = to_float(row.get("investment_recovery_ratio", ""))
        if dep is None:
            continue
        clone = dict(row)
        clone["investment_recovery_ratio"] = str(dep)
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


def load_actual_event_rows() -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    event_rows = [
        row
        for row in read_csv(ACTUAL_RESULTS_PATH)
        if row["model_type"] == "event_study"
    ]
    by_var = {row["explanatory_variable"]: row for row in event_rows}
    model_meta = event_rows[0] if event_rows else {}
    return by_var, model_meta


def build_output_rows() -> tuple[list[dict[str, str]], dict[str, str]]:
    sample_rows, placebo_vars, baseline_period, placebo_event_count = build_placebo_event_sample()
    placebo_result = fit_ols(
        sample_rows,
        dependent_var="investment_recovery_ratio",
        explanatory_vars=placebo_vars,
        fixed_effect_vars=["event_id", "service_std", "year_quarter"],
    )
    placebo_pretrend_result, placebo_pretrend_detail = pretrend_result(
        placebo_result,
        [var for var in placebo_vars if var.endswith("m1")],
    )

    actual_by_var, actual_model_meta = load_actual_event_rows()
    output_rows: list[dict[str, str]] = []
    for variable in placebo_vars:
        actual_row = actual_by_var.get(variable, {})
        placebo_coef = placebo_result.coefficients.get(variable, float("nan"))
        actual_coef = to_float(actual_row.get("coefficient", ""))
        placebo_p = placebo_result.p_values.get(variable, float("nan"))
        actual_p = to_float(actual_row.get("p_value", ""))

        if actual_coef is None:
            note = "Actual comparator missing for this relative period"
        elif math.isnan(placebo_p) or math.isnan(actual_p):
            note = "At least one side is not estimable"
        elif placebo_p < 0.10 and actual_p < 0.10 and (placebo_coef * actual_coef) > 0:
            note = "Placebo reproduces the direction and significance of the actual estimate"
        elif placebo_p < 0.10 and actual_p >= 0.10:
            note = "Placebo is significant while the actual estimate is not"
        elif placebo_p >= 0.10 and actual_p < 0.10:
            note = "Actual estimate is stronger than placebo on this relative period"
        else:
            note = "Neither side is statistically strong on this relative period"

        output_rows.append(
            {
                "sector_std": "webtoon_story",
                "comparison_scope": "placebo_webtoon_vs_actual_webtoon",
                "explanatory_variable": variable,
                "placebo_event_count": str(placebo_event_count),
                "placebo_sample_n": str(placebo_result.n_obs),
                "placebo_treated_n": str(sum(row["treated_flag"] == "1" for row in sample_rows)),
                "placebo_control_n": str(sum(row["control_flag"] == "1" for row in sample_rows)),
                "placebo_baseline_period": baseline_period,
                "placebo_coefficient": f"{placebo_coef:.10f}",
                "placebo_standard_error": f"{placebo_result.std_errors.get(variable, float('nan')):.10f}",
                "placebo_p_value": f"{placebo_p:.10f}",
                "placebo_pretrend_test_result": placebo_pretrend_result,
                "placebo_pretrend_detail": placebo_pretrend_detail,
                "actual_model_id": actual_model_meta.get("model_id", ""),
                "actual_sample_n": actual_model_meta.get("sample_n", ""),
                "actual_treated_n": actual_model_meta.get("treated_n", ""),
                "actual_control_n": actual_model_meta.get("control_n", ""),
                "actual_baseline_period": actual_model_meta.get("baseline_period", ""),
                "actual_coefficient": "" if actual_coef is None else f"{actual_coef:.10f}",
                "actual_standard_error": actual_row.get("standard_error", ""),
                "actual_p_value": actual_row.get("p_value", ""),
                "actual_pretrend_test_result": actual_model_meta.get("pretrend_test_result", ""),
                "actual_pretrend_detail": actual_model_meta.get("pretrend_detail", ""),
                "placebo_minus_actual_coefficient": (
                    ""
                    if actual_coef is None
                    else f"{(placebo_coef - actual_coef):.10f}"
                ),
                "comparison_note": note,
            }
        )

    meta = {
        "placebo_pretrend_result": placebo_pretrend_result,
        "placebo_pretrend_detail": placebo_pretrend_detail,
        "actual_pretrend_result": actual_model_meta.get("pretrend_test_result", ""),
        "actual_pretrend_detail": actual_model_meta.get("pretrend_detail", ""),
    }
    return output_rows, meta


def write_table(rows: list[dict[str, str]]) -> None:
    OUTPUT_TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "sector_std",
        "comparison_scope",
        "explanatory_variable",
        "placebo_event_count",
        "placebo_sample_n",
        "placebo_treated_n",
        "placebo_control_n",
        "placebo_baseline_period",
        "placebo_coefficient",
        "placebo_standard_error",
        "placebo_p_value",
        "placebo_pretrend_test_result",
        "placebo_pretrend_detail",
        "actual_model_id",
        "actual_sample_n",
        "actual_treated_n",
        "actual_control_n",
        "actual_baseline_period",
        "actual_coefficient",
        "actual_standard_error",
        "actual_p_value",
        "actual_pretrend_test_result",
        "actual_pretrend_detail",
        "placebo_minus_actual_coefficient",
        "comparison_note",
    ]
    with OUTPUT_TABLE_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def rel_from_variable(name: str) -> int:
    if name.endswith("m1"):
        return -1
    if "treated_rel_m" in name:
        return -int(name.split("treated_rel_m", 1)[1])
    if "treated_rel_p" in name:
        return int(name.split("treated_rel_p", 1)[1])
    raise ValueError(name)


def draw_figure(rows: list[dict[str, str]], meta: dict[str, str]) -> None:
    width = 1100
    height = 520
    margin_left = 90
    margin_right = 70
    margin_top = 100
    margin_bottom = 90
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    colors = {
        "actual": "#b02a37",
        "placebo": "#1d4ed8",
        "axis": "#222222",
        "grid": "#d9d9d9",
        "text": "#222222",
        "muted": "#6c757d",
    }

    ordered = sorted(rows, key=lambda row: rel_from_variable(row["explanatory_variable"]))
    actual_points: list[tuple[int, float, float]] = []
    placebo_points: list[tuple[int, float, float]] = []
    all_bounds: list[float] = []
    for row in ordered:
        rel = rel_from_variable(row["explanatory_variable"])
        placebo_coef = float(row["placebo_coefficient"])
        placebo_se = float(row["placebo_standard_error"])
        actual_coef = float(row["actual_coefficient"])
        actual_se = float(row["actual_standard_error"])
        placebo_points.append((rel, placebo_coef, placebo_se))
        actual_points.append((rel, actual_coef, actual_se))
        all_bounds.extend(
            [
                placebo_coef - 1.96 * placebo_se,
                placebo_coef + 1.96 * placebo_se,
                actual_coef - 1.96 * actual_se,
                actual_coef + 1.96 * actual_se,
            ]
        )

    y_min = min(all_bounds + [-10.0])
    y_max = max(all_bounds + [10.0])
    if y_min == y_max:
        y_min -= 1.0
        y_max += 1.0

    rel_values = [rel for rel, _, _ in actual_points]
    x_positions = {
        rel: margin_left + int(index * plot_width / max(len(rel_values) - 1, 1))
        for index, rel in enumerate(rel_values)
    }

    def y_to_px(value: float) -> int:
        ratio = (value - y_min) / (y_max - y_min)
        return int(margin_top + plot_height - ratio * plot_height)

    draw.text(
        (width // 2, 28),
        "Placebo Event Study vs Actual Webtoon Event Study",
        fill=colors["text"],
        font=font,
        anchor="ma",
    )
    subtitle = (
        f"Actual pretrend={meta['actual_pretrend_result']} | "
        f"Placebo pretrend={meta['placebo_pretrend_result']}"
    )
    draw.text((width // 2, 48), subtitle, fill=colors["muted"], font=font, anchor="ma")
    draw.text(
        (width // 2, 66),
        "Webtoon-style stacked event study with baseline period 0 and FE: event_id | service_std | year_quarter",
        fill=colors["muted"],
        font=font,
        anchor="ma",
    )

    for fraction in [0.0, 0.25, 0.5, 0.75, 1.0]:
        y_value = y_min + (y_max - y_min) * fraction
        y = y_to_px(y_value)
        draw.line([(margin_left, y), (margin_left + plot_width, y)], fill=colors["grid"], width=1)
        draw.text((margin_left - 8, y), f"{y_value:.0f}", fill=colors["text"], font=font, anchor="rs")

    zero_y = y_to_px(0.0)
    draw.line([(margin_left, zero_y), (margin_left + plot_width, zero_y)], fill=colors["axis"], width=2)
    draw.line([(margin_left, margin_top), (margin_left, margin_top + plot_height)], fill=colors["axis"], width=2)

    for rel, _, _ in actual_points:
        x = x_positions[rel]
        draw.line([(x, margin_top), (x, margin_top + plot_height)], fill=colors["grid"], width=1)
        draw.text((x, margin_top + plot_height + 18), f"{rel:+d}", fill=colors["text"], font=font, anchor="ma")

    def draw_series(points: list[tuple[int, float, float]], color: str, label_offset: int) -> None:
        prev = None
        for rel, coef, se in points:
            x = x_positions[rel]
            y = y_to_px(coef)
            low = y_to_px(coef - 1.96 * se)
            high = y_to_px(coef + 1.96 * se)
            draw.line([(x, low), (x, high)], fill=color, width=2)
            draw.line([(x - 5, low), (x + 5, low)], fill=color, width=2)
            draw.line([(x - 5, high), (x + 5, high)], fill=color, width=2)
            draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill=color)
            draw.text((x, y + label_offset), f"{coef:.1f}", fill=color, font=font, anchor="ma")
            if prev is not None:
                draw.line([prev, (x, y)], fill=color, width=3)
            prev = (x, y)

    draw_series(actual_points, colors["actual"], -14)
    draw_series(placebo_points, colors["placebo"], 16)

    legend_y = height - 34
    draw.line([(margin_left, legend_y), (margin_left + 24, legend_y)], fill=colors["actual"], width=3)
    draw.ellipse([margin_left + 8, legend_y - 4, margin_left + 16, legend_y + 4], fill=colors["actual"])
    draw.text((margin_left + 32, legend_y + 1), "Actual webtoon event study", fill=colors["text"], font=font, anchor="lm")
    draw.line([(margin_left + 260, legend_y), (margin_left + 284, legend_y)], fill=colors["placebo"], width=3)
    draw.ellipse([margin_left + 268, legend_y - 4, margin_left + 276, legend_y + 4], fill=colors["placebo"])
    draw.text((margin_left + 292, legend_y + 1), "Placebo webtoon event study", fill=colors["text"], font=font, anchor="lm")

    OUTPUT_FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT_FIGURE_PATH)


def main() -> None:
    rows, meta = build_output_rows()
    write_table(rows)
    draw_figure(rows, meta)


if __name__ == "__main__":
    main()
