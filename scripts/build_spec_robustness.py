from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]

CPII_SCQ_PATH = ROOT / "data/processed/cpii_panel_sector_country_quarter.csv"
SUMMARY_PATH = ROOT / "outputs/tables/spec_robustness_summary.csv"
FIGURE_PATH = ROOT / "outputs/figures/spec_comparison_chart.png"
LOG_PATH = ROOT / "logs/robustness_log.md"


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


def quarter_index(value: str) -> int:
    year = int(value[:4])
    quarter = int(value[-1])
    return year * 4 + quarter - 1


def weighted_score(
    row: dict[str, str],
    weights: dict[str, float],
    require_complete: bool,
    min_observed: int,
) -> float | None:
    observed: list[tuple[float, float]] = []
    for key, weight in weights.items():
        value = to_float(row.get(key, ""))
        if value is None:
            if require_complete:
                return None
            continue
        observed.append((value, weight))

    if len(observed) < min_observed:
        return None

    total_weight = sum(weight for _, weight in observed)
    if total_weight <= 0:
        return None

    return sum(value * weight for value, weight in observed) / total_weight


def average_ranks(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    pos = 0
    while pos < len(indexed):
        end = pos
        while end + 1 < len(indexed) and indexed[end + 1][1] == indexed[pos][1]:
            end += 1
        avg_rank = (pos + end + 2) / 2.0
        for current in range(pos, end + 1):
            ranks[indexed[current][0]] = avg_rank
        pos = end + 1
    return ranks


def pearson_corr(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return float("nan")
    x_arr = np.asarray(xs, dtype=float)
    y_arr = np.asarray(ys, dtype=float)
    x_centered = x_arr - x_arr.mean()
    y_centered = y_arr - y_arr.mean()
    denom = math.sqrt(float((x_centered**2).sum()) * float((y_centered**2).sum()))
    if denom == 0:
        return float("nan")
    return float((x_centered * y_centered).sum() / denom)


def spearman_corr(xs: list[float], ys: list[float]) -> float:
    return pearson_corr(average_ranks(xs), average_ranks(ys))


def sign_label(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "missing"
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "zero"


def fit_fe_regression(
    rows: list[dict[str, str]],
    dependent_var: str,
    explanatory_vars: list[str],
    fixed_effect_vars: list[str],
) -> dict[str, dict[str, float]]:
    categories: dict[str, list[str]] = {}
    for fe_var in fixed_effect_vars:
        categories[fe_var] = sorted({row[fe_var] for row in rows})[1:]

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
    xtx_inv = np.linalg.pinv(x_mat.T @ x_mat)
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

    out: dict[str, dict[str, float]] = {}
    for idx, name in enumerate(param_names):
        out[name] = {
            "coef": float(beta[idx]),
            "std_error": float(std[idx]),
        }
    return out


def draw_chart(metric_cards: list[dict[str, float | str]]) -> None:
    width, height = 1500, 920
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.load_default()
    text_font = ImageFont.load_default()

    draw.text((40, 25), "Spec Robustness Comparison", fill="black", font=title_font)
    draw.text(
        (40, 50),
        "Baseline: equal-weight CPII with missing-subindex renormalization | Alt A: reg/risk emphasis | Alt B: strict complete-case",
        fill="black",
        font=text_font,
    )

    panel_x = [40, 770]
    panel_y = 110
    panel_w = 650
    panel_h = 700

    for idx, card in enumerate(metric_cards):
        x0 = panel_x[idx]
        y0 = panel_y
        draw.rounded_rectangle((x0, y0, x0 + panel_w, y0 + panel_h), radius=16, outline="black", width=2)
        draw.text((x0 + 20, y0 + 20), str(card["spec_label"]), fill="black", font=title_font)
        draw.text((x0 + 20, y0 + 45), str(card["spec_note"]), fill="black", font=text_font)

        bars = [
            ("Mean abs diff", float(card["mean_abs_diff"]), 0.0, float(card["score_scale_max"])),
            ("Rank corr", float(card["rank_corr"]), 0.0, 1.0),
            ("Priority overlap", float(card["priority_overlap_share"]), 0.0, 1.0),
            ("Sample retention", float(card["sample_retention"]), 0.0, 1.0),
            ("Sign stability", float(card["sign_stability_share"]), 0.0, 1.0),
        ]
        colors = ["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444"]

        for bar_idx, (label, value, lower, upper) in enumerate(bars):
            base_y = y0 + 100 + bar_idx * 110
            draw.text((x0 + 20, base_y), f"{label}: {value:.3f}", fill="black", font=text_font)
            bar_left = x0 + 20
            bar_top = base_y + 28
            bar_width = panel_w - 60
            bar_height = 28
            draw.rectangle((bar_left, bar_top, bar_left + bar_width, bar_top + bar_height), outline="#999999", width=1)
            scale = 0.0 if upper <= lower else max(0.0, min(1.0, (value - lower) / (upper - lower)))
            fill_width = int(bar_width * scale)
            draw.rectangle((bar_left, bar_top, bar_left + fill_width, bar_top + bar_height), fill=colors[bar_idx])
            draw.text((bar_left, bar_top + 36), f"range [{lower:.2f}, {upper:.2f}]", fill="#555555", font=text_font)

        draw.text(
            (x0 + 20, y0 + 650),
            f"Top-5 priority overlap count: {int(card['priority_overlap_count'])} | Common rows: {int(card['common_n'])}",
            fill="black",
            font=text_font,
        )

    image.save(FIGURE_PATH)


def main() -> None:
    rows = read_csv(CPII_SCQ_PATH)

    specs = {
        "baseline": {
            "label": "Baseline",
            "note": "Equal weights, missing-subindex renormalization",
        },
        "alt_a": {
            "label": "Alternative A",
            "note": "Reg/Risk emphasis weights (0.4, 0.4, 0.2)",
        },
        "alt_b": {
            "label": "Alternative B",
            "note": "Strict complete-case equal-weight CPII",
        },
    }

    for row in rows:
        baseline = to_float(row.get("CPII", ""))
        alt_a = weighted_score(
            row,
            {"I_reg": 0.4, "I_risk": 0.4, "I_market": 0.2},
            require_complete=False,
            min_observed=2,
        )
        alt_b = weighted_score(
            row,
            {"I_reg": 1 / 3, "I_risk": 1 / 3, "I_market": 1 / 3},
            require_complete=True,
            min_observed=3,
        )
        row["score_baseline"] = "" if baseline is None else f"{baseline:.10f}"
        row["score_alt_a"] = "" if alt_a is None else f"{alt_a:.10f}"
        row["score_alt_b"] = "" if alt_b is None else f"{alt_b:.10f}"

    summary_rows: list[dict[str, str]] = []
    chart_cards: list[dict[str, float | str]] = []

    baseline_available = [row for row in rows if row["score_baseline"] != ""]
    baseline_available_n = len(baseline_available)

    # common-support sample for sign-stability regression
    regression_common_rows = [
        row
        for row in rows
        if row["score_baseline"] != ""
        and row["score_alt_a"] != ""
        and row["score_alt_b"] != ""
        and row.get("I_reg", "") != ""
        and row.get("I_risk", "") != ""
    ]

    regression_signs: dict[str, dict[str, float]] = {}
    for dep in ["score_baseline", "score_alt_a", "score_alt_b"]:
        prepared = []
        for row in regression_common_rows:
            prepared.append(
                {
                    "sector_std": row["sector_std"],
                    "year_quarter": row["year_quarter"],
                    dep: row[dep],
                    "I_reg": row["I_reg"],
                    "I_risk": row["I_risk"],
                }
            )
        regression_signs[dep] = fit_fe_regression(
            prepared,
            dependent_var=dep,
            explanatory_vars=["I_reg", "I_risk"],
            fixed_effect_vars=["sector_std", "year_quarter"],
        )

    score_scale_max = 0.0
    comparison_cache: dict[str, dict[str, float | int | str | list[str]]] = {}

    for alt_key, alt_col in [("alt_a", "score_alt_a"), ("alt_b", "score_alt_b")]:
        available_alt = [row for row in rows if row[alt_col] != ""]
        common_rows = [row for row in rows if row["score_baseline"] != "" and row[alt_col] != ""]
        baseline_scores = [float(row["score_baseline"]) for row in common_rows]
        alt_scores = [float(row[alt_col]) for row in common_rows]
        diffs = [alt - base for base, alt in zip(baseline_scores, alt_scores)]
        abs_diffs = [abs(value) for value in diffs]
        mean_abs_diff = float(sum(abs_diffs) / len(abs_diffs)) if abs_diffs else float("nan")
        median_abs_diff = float(np.median(np.asarray(abs_diffs, dtype=float))) if abs_diffs else float("nan")
        max_abs_diff = max(abs_diffs) if abs_diffs else float("nan")
        mean_signed_diff = float(sum(diffs) / len(diffs)) if diffs else float("nan")
        rank_corr = spearman_corr(baseline_scores, alt_scores) if len(common_rows) >= 2 else float("nan")

        score_scale_max = max(score_scale_max, 0.0 if math.isnan(mean_abs_diff) else mean_abs_diff)

        summary_rows.extend(
            [
                {
                    "comparison_id": f"baseline_vs_{alt_key}",
                    "base_spec": "baseline",
                    "alt_spec": alt_key,
                    "metric_category": "score_difference",
                    "metric_name": "mean_abs_score_diff",
                    "analysis_level": "sector_country_quarter",
                    "metric_value": f"{mean_abs_diff:.10f}",
                    "sample_n": str(len(common_rows)),
                    "notes": "Average absolute CPII gap on the common-support sector-country-quarter sample.",
                },
                {
                    "comparison_id": f"baseline_vs_{alt_key}",
                    "base_spec": "baseline",
                    "alt_spec": alt_key,
                    "metric_category": "score_difference",
                    "metric_name": "median_abs_score_diff",
                    "analysis_level": "sector_country_quarter",
                    "metric_value": f"{median_abs_diff:.10f}",
                    "sample_n": str(len(common_rows)),
                    "notes": "Median absolute CPII gap on the common-support sector-country-quarter sample.",
                },
                {
                    "comparison_id": f"baseline_vs_{alt_key}",
                    "base_spec": "baseline",
                    "alt_spec": alt_key,
                    "metric_category": "score_difference",
                    "metric_name": "max_abs_score_diff",
                    "analysis_level": "sector_country_quarter",
                    "metric_value": f"{max_abs_diff:.10f}",
                    "sample_n": str(len(common_rows)),
                    "notes": "Largest absolute CPII gap on the common-support sector-country-quarter sample.",
                },
                {
                    "comparison_id": f"baseline_vs_{alt_key}",
                    "base_spec": "baseline",
                    "alt_spec": alt_key,
                    "metric_category": "score_difference",
                    "metric_name": "mean_signed_score_diff",
                    "analysis_level": "sector_country_quarter",
                    "metric_value": f"{mean_signed_diff:.10f}",
                    "sample_n": str(len(common_rows)),
                    "notes": "Average signed CPII change from baseline to the alternative specification.",
                },
                {
                    "comparison_id": f"baseline_vs_{alt_key}",
                    "base_spec": "baseline",
                    "alt_spec": alt_key,
                    "metric_category": "rank_correlation",
                    "metric_name": "spearman_rank_corr",
                    "analysis_level": "sector_country_quarter",
                    "metric_value": f"{rank_corr:.10f}",
                    "sample_n": str(len(common_rows)),
                    "notes": "Spearman rank correlation using CPII values on the common-support sample.",
                },
            ]
        )

        # latest policy priority stability
        baseline_latest: dict[str, tuple[int, float]] = {}
        alt_latest: dict[str, tuple[int, float]] = {}
        for row in rows:
            key = f"{row['sector_std']}|{row['country_std']}"
            q_idx = quarter_index(row["year_quarter"])
            base = to_float(row["score_baseline"])
            alt = to_float(row[alt_col])
            if base is not None:
                current = baseline_latest.get(key)
                if current is None or q_idx > current[0]:
                    baseline_latest[key] = (q_idx, base)
            if alt is not None:
                current = alt_latest.get(key)
                if current is None or q_idx > current[0]:
                    alt_latest[key] = (q_idx, alt)

        baseline_top5 = [
            key for key, (_, score) in sorted(baseline_latest.items(), key=lambda item: item[1][1], reverse=True)[:5]
        ]
        alt_top5 = [
            key for key, (_, score) in sorted(alt_latest.items(), key=lambda item: item[1][1], reverse=True)[:5]
        ]
        overlap = len(set(baseline_top5) & set(alt_top5))
        union = len(set(baseline_top5) | set(alt_top5))
        jaccard = overlap / union if union else float("nan")
        top1_same = int(bool(baseline_top5 and alt_top5 and baseline_top5[0] == alt_top5[0]))
        summary_rows.extend(
            [
                {
                    "comparison_id": f"baseline_vs_{alt_key}",
                    "base_spec": "baseline",
                    "alt_spec": alt_key,
                    "metric_category": "policy_priority_stability",
                    "metric_name": "top5_overlap_count",
                    "analysis_level": "sector_country_latest",
                    "metric_value": str(overlap),
                    "sample_n": "5",
                    "notes": f"Baseline top5={baseline_top5}; alt top5={alt_top5}",
                },
                {
                    "comparison_id": f"baseline_vs_{alt_key}",
                    "base_spec": "baseline",
                    "alt_spec": alt_key,
                    "metric_category": "policy_priority_stability",
                    "metric_name": "top5_jaccard",
                    "analysis_level": "sector_country_latest",
                    "metric_value": f"{jaccard:.10f}",
                    "sample_n": "5",
                    "notes": f"Baseline top5={baseline_top5}; alt top5={alt_top5}",
                },
                {
                    "comparison_id": f"baseline_vs_{alt_key}",
                    "base_spec": "baseline",
                    "alt_spec": alt_key,
                    "metric_category": "policy_priority_stability",
                    "metric_name": "top1_same_flag",
                    "analysis_level": "sector_country_latest",
                    "metric_value": str(top1_same),
                    "sample_n": "1",
                    "notes": f"Baseline top1={baseline_top5[:1]}; alt top1={alt_top5[:1]}",
                },
            ]
        )

        # sample change
        alt_n = len(available_alt)
        common_n = len(common_rows)
        retention = alt_n / baseline_available_n if baseline_available_n else float("nan")
        summary_rows.extend(
            [
                {
                    "comparison_id": f"baseline_vs_{alt_key}",
                    "base_spec": "baseline",
                    "alt_spec": alt_key,
                    "metric_category": "sample_change",
                    "metric_name": "available_row_count_alt",
                    "analysis_level": "sector_country_quarter",
                    "metric_value": str(alt_n),
                    "sample_n": str(alt_n),
                    "notes": f"Baseline available rows={baseline_available_n}",
                },
                {
                    "comparison_id": f"baseline_vs_{alt_key}",
                    "base_spec": "baseline",
                    "alt_spec": alt_key,
                    "metric_category": "sample_change",
                    "metric_name": "common_row_count",
                    "analysis_level": "sector_country_quarter",
                    "metric_value": str(common_n),
                    "sample_n": str(common_n),
                    "notes": "Rows with nonmissing scores under both baseline and the alternative specification.",
                },
                {
                    "comparison_id": f"baseline_vs_{alt_key}",
                    "base_spec": "baseline",
                    "alt_spec": alt_key,
                    "metric_category": "sample_change",
                    "metric_name": "alt_to_baseline_retention_ratio",
                    "analysis_level": "sector_country_quarter",
                    "metric_value": f"{retention:.10f}",
                    "sample_n": str(alt_n),
                    "notes": f"Alternative available rows divided by baseline available rows ({baseline_available_n}).",
                },
            ]
        )

        comparison_cache[alt_key] = {
            "mean_abs_diff": mean_abs_diff,
            "rank_corr": rank_corr,
            "priority_overlap_count": overlap,
            "priority_overlap_share": overlap / 5.0,
            "common_n": common_n,
            "sample_retention": retention,
            "baseline_top5": baseline_top5,
            "alt_top5": alt_top5,
        }

    # sign stability from common-support regression
    baseline_reg = regression_signs["score_baseline"]
    for alt_key, alt_dep in [("alt_a", "score_alt_a"), ("alt_b", "score_alt_b")]:
        alt_reg = regression_signs[alt_dep]
        stable_count = 0
        total = 0
        for var in ["I_reg", "I_risk"]:
            base_coef = baseline_reg[var]["coef"]
            alt_coef = alt_reg[var]["coef"]
            base_sign = sign_label(base_coef)
            alt_sign = sign_label(alt_coef)
            stable = int(base_sign == alt_sign)
            stable_count += stable
            total += 1
            summary_rows.append(
                {
                    "comparison_id": f"baseline_vs_{alt_key}",
                    "base_spec": "baseline",
                    "alt_spec": alt_key,
                    "metric_category": "sign_stability",
                    "metric_name": f"{var}_sign_stable",
                    "analysis_level": "sector_country_quarter_common_regression",
                    "metric_value": str(stable),
                    "sample_n": str(len(regression_common_rows)),
                    "notes": (
                        f"baseline_coef={base_coef:.10f} ({base_sign}), "
                        f"alt_coef={alt_coef:.10f} ({alt_sign})"
                    ),
                }
            )
        sign_share = stable_count / total if total else float("nan")
        comparison_cache[alt_key]["sign_stability_share"] = sign_share

    fieldnames = [
        "comparison_id",
        "base_spec",
        "alt_spec",
        "metric_category",
        "metric_name",
        "analysis_level",
        "metric_value",
        "sample_n",
        "notes",
    ]
    write_csv(SUMMARY_PATH, summary_rows, fieldnames)

    max_diff = max((float(card["mean_abs_diff"]) for card in comparison_cache.values()), default=1.0)
    for alt_key in ["alt_a", "alt_b"]:
        chart_cards.append(
            {
                "spec_label": specs[alt_key]["label"],
                "spec_note": specs[alt_key]["note"],
                "mean_abs_diff": float(comparison_cache[alt_key]["mean_abs_diff"]),
                "rank_corr": float(comparison_cache[alt_key]["rank_corr"]),
                "priority_overlap_count": float(comparison_cache[alt_key]["priority_overlap_count"]),
                "priority_overlap_share": float(comparison_cache[alt_key]["priority_overlap_share"]),
                "sample_retention": float(comparison_cache[alt_key]["sample_retention"]),
                "sign_stability_share": float(comparison_cache[alt_key]["sign_stability_share"]),
                "common_n": float(comparison_cache[alt_key]["common_n"]),
                "score_scale_max": max_diff if max_diff > 0 else 1.0,
            }
        )
    draw_chart(chart_cards)

    log_lines = [
        "# Exec Prompt 32 Robustness Log",
        "",
        "## Spec Definitions",
        "",
        "- `baseline`: existing equal-weight CPII with missing-subindex renormalization.",
        "- `alt_a`: regulation/risk emphasis weights `(0.4, 0.4, 0.2)` with the same missing-subindex renormalization rule.",
        "- `alt_b`: strict complete-case equal-weight CPII, requiring `I_reg`, `I_risk`, and `I_market` all to be observed.",
        "",
        "## Core Results",
        "",
    ]
    for alt_key in ["alt_a", "alt_b"]:
        cache = comparison_cache[alt_key]
        log_lines.extend(
            [
                f"### {specs[alt_key]['label']}",
                "",
                f"- Mean absolute score difference: `{float(cache['mean_abs_diff']):.6f}`",
                f"- Spearman rank correlation: `{float(cache['rank_corr']):.6f}`",
                f"- Top-5 policy priority overlap: `{int(cache['priority_overlap_count'])}/5`",
                f"- Sample retention vs baseline: `{float(cache['sample_retention']):.6f}`",
                f"- Sign stability share: `{float(cache['sign_stability_share']):.6f}`",
                f"- Latest baseline top-5 priorities: `{cache['baseline_top5']}`",
                f"- Latest alternative top-5 priorities: `{cache['alt_top5']}`",
                "",
            ]
        )

    log_lines.extend(
        [
            "## Sign-Stability Regression Sample",
            "",
            f"- Common-support regression rows: `{len(regression_common_rows)}`",
            f"- Baseline I_reg coefficient: `{baseline_reg['I_reg']['coef']:.10f}`",
            f"- Baseline I_risk coefficient: `{baseline_reg['I_risk']['coef']:.10f}`",
            f"- Alt A I_reg coefficient: `{regression_signs['score_alt_a']['I_reg']['coef']:.10f}`",
            f"- Alt A I_risk coefficient: `{regression_signs['score_alt_a']['I_risk']['coef']:.10f}`",
            f"- Alt B I_reg coefficient: `{regression_signs['score_alt_b']['I_reg']['coef']:.10f}`",
            f"- Alt B I_risk coefficient: `{regression_signs['score_alt_b']['I_risk']['coef']:.10f}`",
            "",
            "## Notes",
            "",
            "- Score-difference and rank-correlation metrics use sector-country-quarter rows on the common-support sample for each comparison.",
            "- Policy-priority stability uses the latest available score for each sector-country pair and compares the top five priorities under each specification.",
            "- Sample-change metrics quantify how many sector-country-quarter rows remain usable under the alternative specification relative to the baseline.",
        ]
    )
    LOG_PATH.write_text("\n".join(log_lines), encoding="utf-8")


if __name__ == "__main__":
    main()
