#!/usr/bin/env python3

from __future__ import annotations

import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Optional

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]

VARIABLE_PLATFORM_MONTH_PATH = ROOT / "data/processed/variable_panel_platform_month.csv"
VARIABLE_PLATFORM_QUARTER_PATH = ROOT / "data/processed/variable_panel_platform_quarter.csv"
VARIABLE_TITLE_QUARTER_PATH = ROOT / "data/processed/variable_panel_title_quarter.csv"
VARIABLE_SECTOR_QUARTER_PATH = ROOT / "data/processed/variable_panel_sector_quarter.csv"
SUBINDEX_SECTOR_QUARTER_PATH = ROOT / "data/processed/subindex_panel_sector_quarter.csv"
CPII_SECTOR_QUARTER_PATH = ROOT / "data/processed/cpii_panel_sector_quarter.csv"
CPII_SECTOR_COUNTRY_QUARTER_PATH = ROOT / "data/processed/cpii_panel_sector_country_quarter.csv"
REGRESSION_MUSIC_PATH = ROOT / "outputs/tables/regression_results_music.csv"
REGRESSION_WEBTOON_PATH = ROOT / "outputs/tables/regression_results_webtoon.csv"
TIMESERIES_SUMMARY_PATH = ROOT / "outputs/tables/timeseries_change_summary.csv"

T08_PATH = ROOT / "outputs/tables/T08_basic_stats_summary.csv"
T09_PATH = ROOT / "outputs/tables/T09_cpii_sector_mean_comparison.csv"
T10_PATH = ROOT / "outputs/tables/T10_cpii_extreme_observations.csv"
F03_PATH = ROOT / "outputs/figures/F03_cpii_subindex_decomposition.png"
F04_PATH = ROOT / "outputs/figures/F04_cpii_sector_mean_compare.png"
F05_PATH = ROOT / "outputs/figures/F05_music_event_study_plot.png"
F06_PATH = ROOT / "outputs/figures/F06_webtoon_story_event_study_plot.png"
F07_PATH = ROOT / "outputs/figures/F07_digital_infra_pressure_scatter.png"
F08_PATH = ROOT / "outputs/figures/F08_core_variable_correlation_heatmap.png"
LOG_PATH = ROOT / "logs/report_ready_asset_build_log.md"
MANIFEST_PATH = ROOT / "data/registry/project_manifest.csv"
WORKFLOW_LOG_PATH = ROOT / "logs/workflow_log.md"

ACCESS_DATE = "2026-03-29"
PROMPT_NAME = "Post Step 01"

CORE_VARIABLES = [
    "effective_tax_rate_gap",
    "network_cost_ratio",
    "infra_dependency_ratio",
    "funding_cost_spread",
    "ip_assetization_gap",
    "investment_recovery_ratio",
    "cashflow_recovery_ratio",
    "creator_share_ratio",
    "bundle_leverage_index",
    "cross_market_transfer_index",
    "foreign_dependency_ratio",
    "outflow_to_capex_ratio",
]

CORR_VARIABLES = [
    "network_cost_ratio",
    "funding_cost_spread",
    "investment_recovery_ratio",
    "cashflow_recovery_ratio",
    "foreign_dependency_ratio",
    "outflow_to_capex_ratio",
    "I_reg",
    "I_risk",
    "I_market",
    "CPII",
]

CORR_LABELS = {
    "network_cost_ratio": "net_cost",
    "funding_cost_spread": "fund_spread",
    "investment_recovery_ratio": "inv_recovery",
    "cashflow_recovery_ratio": "cash_recovery",
    "foreign_dependency_ratio": "foreign_dep",
    "outflow_to_capex_ratio": "outflow_capex",
    "I_reg": "I_reg",
    "I_risk": "I_risk",
    "I_market": "I_market",
    "CPII": "CPII",
}

DISPLAY_NAME = {
    "music": "Music",
    "webtoon_story": "Webtoon/Story",
    "digital_infra": "Digital Infra",
}

PANEL_PATHS = {
    "platform_month": VARIABLE_PLATFORM_MONTH_PATH,
    "platform_quarter": VARIABLE_PLATFORM_QUARTER_PATH,
    "title_quarter": VARIABLE_TITLE_QUARTER_PATH,
    "sector_country_quarter": VARIABLE_SECTOR_QUARTER_PATH,
}

BAR_COLORS = {
    "I_reg": (202, 103, 2),
    "I_risk": (52, 101, 164),
    "I_market": (11, 110, 79),
}

BACKGROUND = (248, 246, 240)
PANEL_BG = (255, 255, 255)
GRID = (214, 213, 208)
TEXT = (42, 42, 42)
MUTED = (104, 104, 104)
LINE = (58, 110, 165)
RED = (176, 64, 64)
GREEN = (32, 122, 88)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def safe_float(value: object) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def fmt(value: Optional[float], digits: int = 6) -> str:
    if value is None:
        return ""
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def quarter_sort_key(value: str) -> tuple[int, int]:
    return int(value[:4]), int(value[-1])


def percentile(values: list[float], q: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * q
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def mean(values: Iterable[float]) -> Optional[float]:
    values_list = list(values)
    return sum(values_list) / len(values_list) if values_list else None


def stdev(values: list[float]) -> Optional[float]:
    if not values:
        return None
    if len(values) == 1:
        return 0.0
    return statistics.stdev(values)


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for candidate in candidates:
        candidate_path = Path(candidate)
        if candidate_path.exists():
            try:
                return ImageFont.truetype(str(candidate_path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def build_t08_basic_stats() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for panel_scope, path in PANEL_PATHS.items():
        panel_rows = read_csv(path)
        for variable_name in CORE_VARIABLES:
            values = [
                value
                for row in panel_rows
                if (value := safe_float(row.get(variable_name, ""))) is not None
            ]
            if not values:
                continue
            rows.append(
                {
                    "panel_scope": panel_scope,
                    "variable_name": variable_name,
                    "observation_count": str(len(values)),
                    "mean": fmt(mean(values)),
                    "stddev": fmt(stdev(values)),
                    "p25": fmt(percentile(values, 0.25)),
                    "median": fmt(percentile(values, 0.50)),
                    "p75": fmt(percentile(values, 0.75)),
                    "min": fmt(min(values)),
                    "max": fmt(max(values)),
                }
            )
    rows.sort(key=lambda row: (row["panel_scope"], row["variable_name"]))
    write_csv(
        T08_PATH,
        rows,
        [
            "panel_scope",
            "variable_name",
            "observation_count",
            "mean",
            "stddev",
            "p25",
            "median",
            "p75",
            "min",
            "max",
        ],
    )
    return rows


def build_t09_sector_means() -> list[dict[str, str]]:
    cpii_rows = [
        row for row in read_csv(CPII_SECTOR_QUARTER_PATH) if safe_float(row.get("CPII", "")) is not None
    ]
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in cpii_rows:
        grouped[row["sector_std"]].append(row)

    summary_rows: list[dict[str, str]] = []
    for sector_std, members in grouped.items():
        cpii_values = [safe_float(member["CPII"]) for member in members if safe_float(member["CPII"]) is not None]
        i_reg_values = [safe_float(member["I_reg"]) for member in members if safe_float(member["I_reg"]) is not None]
        i_risk_values = [safe_float(member["I_risk"]) for member in members if safe_float(member["I_risk"]) is not None]
        i_market_values = [safe_float(member["I_market"]) for member in members if safe_float(member["I_market"]) is not None]
        summary_rows.append(
            {
                "sector_std": sector_std,
                "sector_label": DISPLAY_NAME.get(sector_std, sector_std),
                "observation_count": str(len(cpii_values)),
                "mean_CPII": fmt(mean(cpii_values)),
                "stddev_CPII": fmt(stdev(cpii_values)),
                "mean_I_reg": fmt(mean(i_reg_values)),
                "mean_I_risk": fmt(mean(i_risk_values)),
                "mean_I_market": fmt(mean(i_market_values)),
            }
        )

    ranking = sorted(
        summary_rows,
        key=lambda row: (-float(row["mean_CPII"]), row["sector_std"]),
    )
    for index, row in enumerate(ranking, start=1):
        row["rank_by_mean_CPII"] = str(index)

    ordered_rows = sorted(ranking, key=lambda row: int(row["rank_by_mean_CPII"]))
    write_csv(
        T09_PATH,
        ordered_rows,
        [
            "sector_std",
            "sector_label",
            "observation_count",
            "mean_CPII",
            "stddev_CPII",
            "mean_I_reg",
            "mean_I_risk",
            "mean_I_market",
            "rank_by_mean_CPII",
        ],
    )
    return ordered_rows


def build_t10_extremes() -> list[dict[str, str]]:
    cpii_rows = [
        row for row in read_csv(CPII_SECTOR_QUARTER_PATH) if safe_float(row.get("CPII", "")) is not None
    ]
    change_lookup = {
        (row["sector_std"], row["year_quarter"]): row
        for row in read_csv(TIMESERIES_SUMMARY_PATH)
        if row["entity_type"] == "sector"
    }

    ranked = sorted(cpii_rows, key=lambda row: float(row["CPII"]))
    selected = [("bottom", row) for row in ranked[:5]] + [("top", row) for row in ranked[-5:][::-1]]

    out_rows: list[dict[str, str]] = []
    for index, (rank_group, row) in enumerate(selected, start=1):
        lookup = change_lookup.get((row["sector_std"], row["year_quarter"]), {})
        out_rows.append(
            {
                "rank_group": rank_group,
                "rank_order": str(index if rank_group == "bottom" else index - 5),
                "sector_std": row["sector_std"],
                "sector_label": DISPLAY_NAME.get(row["sector_std"], row["sector_std"]),
                "year_quarter": row["year_quarter"],
                "CPII": fmt(safe_float(row["CPII"])),
                "I_reg": fmt(safe_float(row["I_reg"])),
                "I_risk": fmt(safe_float(row["I_risk"])),
                "I_market": fmt(safe_float(row["I_market"])),
                "dominant_subindex": lookup.get("dominant_subindex", ""),
                "large_change_flag": lookup.get("large_change_flag", ""),
                "structural_break_candidate": lookup.get("structural_break_candidate", ""),
                "cause_candidate_memo": lookup.get("cause_candidate_memo", ""),
            }
        )

    write_csv(
        T10_PATH,
        out_rows,
        [
            "rank_group",
            "rank_order",
            "sector_std",
            "sector_label",
            "year_quarter",
            "CPII",
            "I_reg",
            "I_risk",
            "I_market",
            "dominant_subindex",
            "large_change_flag",
            "structural_break_candidate",
            "cause_candidate_memo",
        ],
    )
    return out_rows


def event_points_from_regression(path: Path) -> tuple[list[dict[str, float]], str, str, str]:
    rows = [row for row in read_csv(path) if row["model_type"] == "event_study"]
    if not rows:
        return [], "", "", ""

    points: list[dict[str, float]] = []
    baseline_period = rows[0].get("baseline_period", "")
    pretrend_result = rows[0].get("pretrend_test_result", "")
    model_label = rows[0].get("model_label", "")
    for row in rows:
        var = row["explanatory_variable"]
        if "treated_rel_" not in var:
            continue
        suffix = var.replace("treated_rel_", "")
        if suffix.startswith("m"):
            x_value = -int(suffix[1:])
        elif suffix.startswith("p"):
            x_value = int(suffix[1:])
        else:
            continue
        coefficient = safe_float(row["coefficient"])
        standard_error = safe_float(row["standard_error"])
        if coefficient is None or standard_error is None:
            continue
        points.append(
            {
                "x": float(x_value),
                "coef": coefficient,
                "se": standard_error,
                "lower": coefficient - 1.96 * standard_error,
                "upper": coefficient + 1.96 * standard_error,
            }
        )
    if baseline_period:
        baseline_x = float(int(baseline_period))
        points.append({"x": baseline_x, "coef": 0.0, "se": 0.0, "lower": 0.0, "upper": 0.0, "baseline": 1.0})
    points.sort(key=lambda item: item["x"])
    return points, baseline_period, pretrend_result, model_label


def joined_sector_country_rows() -> list[dict[str, str]]:
    variable_lookup = {
        row["panel_sector_quarter_id"]: row
        for row in read_csv(VARIABLE_SECTOR_QUARTER_PATH)
    }
    joined: list[dict[str, str]] = []
    for row in read_csv(CPII_SECTOR_COUNTRY_QUARTER_PATH):
        if safe_float(row.get("CPII", "")) is None:
            continue
        variable_row = variable_lookup.get(row["panel_sector_quarter_id"])
        if not variable_row:
            continue
        merged = dict(variable_row)
        merged.update(
            {
                "I_reg": row.get("I_reg", ""),
                "I_risk": row.get("I_risk", ""),
                "I_market": row.get("I_market", ""),
                "CPII": row.get("CPII", ""),
            }
        )
        joined.append(merged)
    return joined


def build_scatter_points() -> list[dict[str, object]]:
    points: list[dict[str, object]] = []
    for row in joined_sector_country_rows():
        if row["sector_std"] != "digital_infra":
            continue
        x_value = safe_float(row.get("network_cost_ratio", ""))
        y_value = safe_float(row.get("CPII", ""))
        if x_value is None or y_value is None:
            continue
        points.append(
            {
                "x": x_value,
                "y": y_value,
                "label": f"{row['country_std']} {row['year_quarter']}",
            }
        )
    return points


def correlation(values_x: list[float], values_y: list[float]) -> Optional[float]:
    if len(values_x) < 2 or len(values_y) < 2 or len(values_x) != len(values_y):
        return None
    mean_x = sum(values_x) / len(values_x)
    mean_y = sum(values_y) / len(values_y)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(values_x, values_y))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in values_x))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in values_y))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def build_correlation_matrix() -> tuple[list[str], list[list[Optional[float]]], int]:
    joined_rows = joined_sector_country_rows()
    matrix: list[list[Optional[float]]] = []
    max_pair_n = 0
    for variable_x in CORR_VARIABLES:
        row_values: list[Optional[float]] = []
        for variable_y in CORR_VARIABLES:
            x_values: list[float] = []
            y_values: list[float] = []
            for row in joined_rows:
                value_x = safe_float(row.get(variable_x, ""))
                value_y = safe_float(row.get(variable_y, ""))
                if value_x is None or value_y is None:
                    continue
                x_values.append(value_x)
                y_values.append(value_y)
            max_pair_n = max(max_pair_n, len(x_values))
            row_values.append(correlation(x_values, y_values))
        matrix.append(row_values)
    labels = [CORR_LABELS[name] for name in CORR_VARIABLES]
    return labels, matrix, max_pair_n


def create_canvas(width: int, height: int) -> tuple[Image.Image, ImageDraw.ImageDraw, ImageFont.ImageFont, ImageFont.ImageFont, ImageFont.ImageFont]:
    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    title_font = load_font(28)
    label_font = load_font(18)
    small_font = load_font(14)
    return image, draw, title_font, label_font, small_font


def draw_stacked_bar(rows: list[dict[str, str]], output_path: Path) -> None:
    image, draw, title_font, label_font, small_font = create_canvas(1500, 920)
    ensure_parent(output_path)
    margin_left, margin_right, margin_top, margin_bottom = 120, 80, 130, 120
    plot_left = margin_left
    plot_top = margin_top
    plot_right = image.size[0] - margin_right
    plot_bottom = image.size[1] - margin_bottom
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top

    draw.rounded_rectangle((50, 50, image.size[0] - 50, image.size[1] - 50), radius=24, fill=PANEL_BG, outline=GRID, width=2)
    draw.text((80, 70), "F03. CPII Subindex Decomposition", font=title_font, fill=TEXT)
    draw.text((80, 108), "Stacked contribution to mean CPII by sector-quarter averages", font=label_font, fill=MUTED)

    contributions = []
    for row in rows:
        reg = float(row["mean_I_reg"]) / 3.0
        risk = float(row["mean_I_risk"]) / 3.0
        market = float(row["mean_I_market"]) / 3.0
        total = reg + risk + market
        contributions.append((row["sector_std"], reg, risk, market, total))

    max_total = max(total for _, _, _, _, total in contributions) if contributions else 100.0
    y_max = max(100.0, math.ceil(max_total / 10.0) * 10.0)

    for tick in range(0, int(y_max) + 1, 10):
        y = plot_bottom - (tick / y_max) * plot_height
        draw.line((plot_left, y, plot_right, y), fill=GRID, width=1)
        label = str(tick)
        width, height = text_size(draw, label, small_font)
        draw.text((plot_left - 16 - width, y - height / 2), label, font=small_font, fill=MUTED)

    bar_count = len(contributions)
    band = plot_width / max(bar_count, 1)
    bar_width = min(180, band * 0.55)
    legend_x = plot_right - 260
    legend_y = 86
    for idx, (name, color) in enumerate([("I_reg / 3", BAR_COLORS["I_reg"]), ("I_risk / 3", BAR_COLORS["I_risk"]), ("I_market / 3", BAR_COLORS["I_market"])]):
        y0 = legend_y + idx * 28
        draw.rectangle((legend_x, y0, legend_x + 18, y0 + 18), fill=color)
        draw.text((legend_x + 28, y0 - 2), name, font=small_font, fill=TEXT)

    for idx, (sector_std, reg, risk, market, total) in enumerate(contributions):
        cx = plot_left + band * idx + band / 2
        x0 = cx - bar_width / 2
        x1 = cx + bar_width / 2
        running = 0.0
        for key, value in [("I_market", market), ("I_risk", risk), ("I_reg", reg)]:
            y1 = plot_bottom - (running / y_max) * plot_height
            running += value
            y0 = plot_bottom - (running / y_max) * plot_height
            draw.rectangle((x0, y0, x1, y1), fill=BAR_COLORS[key], outline=PANEL_BG)
        label = DISPLAY_NAME.get(sector_std, sector_std)
        tw, th = text_size(draw, label, label_font)
        draw.text((cx - tw / 2, plot_bottom + 16), label, font=label_font, fill=TEXT)
        total_label = fmt(total, 2)
        tw, th = text_size(draw, total_label, small_font)
        draw.text((cx - tw / 2, plot_bottom - (total / y_max) * plot_height - th - 8), total_label, font=small_font, fill=TEXT)

    image.save(output_path)


def draw_mean_bar(rows: list[dict[str, str]], output_path: Path) -> None:
    image, draw, title_font, label_font, small_font = create_canvas(1500, 920)
    ensure_parent(output_path)
    margin_left, margin_right, margin_top, margin_bottom = 120, 80, 130, 120
    plot_left = margin_left
    plot_top = margin_top
    plot_right = image.size[0] - margin_right
    plot_bottom = image.size[1] - margin_bottom
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top
    draw.rounded_rectangle((50, 50, image.size[0] - 50, image.size[1] - 50), radius=24, fill=PANEL_BG, outline=GRID, width=2)
    draw.text((80, 70), "F04. Mean CPII By Sector", font=title_font, fill=TEXT)
    draw.text((80, 108), "Sector-quarter mean with one standard deviation band", font=label_font, fill=MUTED)

    y_max = max(max(float(row["mean_CPII"]) for row in rows) + 10.0, 100.0)
    for tick in range(0, int(y_max) + 1, 10):
        y = plot_bottom - (tick / y_max) * plot_height
        draw.line((plot_left, y, plot_right, y), fill=GRID, width=1)
        label = str(tick)
        width, height = text_size(draw, label, small_font)
        draw.text((plot_left - 16 - width, y - height / 2), label, font=small_font, fill=MUTED)

    band = plot_width / max(len(rows), 1)
    bar_width = min(180, band * 0.55)
    colors = [(11, 110, 79), (58, 110, 165), (202, 103, 2)]
    for idx, row in enumerate(rows):
        mean_value = float(row["mean_CPII"])
        std_value = float(row["stddev_CPII"])
        cx = plot_left + band * idx + band / 2
        x0 = cx - bar_width / 2
        x1 = cx + bar_width / 2
        y0 = plot_bottom - (mean_value / y_max) * plot_height
        draw.rectangle((x0, y0, x1, plot_bottom), fill=colors[idx % len(colors)], outline=PANEL_BG)
        center_y = plot_bottom - ((mean_value + std_value) / y_max) * plot_height
        bottom_y = plot_bottom - (max(mean_value - std_value, 0) / y_max) * plot_height
        draw.line((cx, center_y, cx, bottom_y), fill=TEXT, width=3)
        draw.line((cx - 12, center_y, cx + 12, center_y), fill=TEXT, width=3)
        draw.line((cx - 12, bottom_y, cx + 12, bottom_y), fill=TEXT, width=3)
        label = row["sector_label"]
        tw, th = text_size(draw, label, label_font)
        draw.text((cx - tw / 2, plot_bottom + 16), label, font=label_font, fill=TEXT)
        value_label = fmt(mean_value, 2)
        tw, th = text_size(draw, value_label, small_font)
        draw.text((cx - tw / 2, y0 - th - 8), value_label, font=small_font, fill=TEXT)

    image.save(output_path)


def draw_event_plot(points: list[dict[str, float]], baseline_period: str, pretrend_result: str, model_label: str, title: str, output_path: Path) -> None:
    image, draw, title_font, label_font, small_font = create_canvas(1500, 920)
    ensure_parent(output_path)
    margin_left, margin_right, margin_top, margin_bottom = 120, 80, 130, 120
    plot_left = margin_left
    plot_top = margin_top
    plot_right = image.size[0] - margin_right
    plot_bottom = image.size[1] - margin_bottom
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top
    draw.rounded_rectangle((50, 50, image.size[0] - 50, image.size[1] - 50), radius=24, fill=PANEL_BG, outline=GRID, width=2)
    draw.text((80, 70), title, font=title_font, fill=TEXT)
    subtitle = f"{model_label} | baseline={baseline_period} | pretrend={pretrend_result}"
    draw.text((80, 108), subtitle, font=label_font, fill=MUTED)

    if not points:
        image.save(output_path)
        return

    x_values = [point["x"] for point in points]
    y_values = [point["lower"] for point in points] + [point["upper"] for point in points]
    x_min = min(x_values) - 0.5
    x_max = max(x_values) + 0.5
    y_min = min(y_values)
    y_max = max(y_values)
    span = max(abs(y_min), abs(y_max))
    y_min = min(-span * 1.1, y_min * 1.1)
    y_max = max(span * 1.1, y_max * 1.1)
    if y_min == y_max:
        y_min -= 1.0
        y_max += 1.0

    def x_to_px(value: float) -> float:
        return plot_left + (value - x_min) / (x_max - x_min) * plot_width

    def y_to_px(value: float) -> float:
        return plot_bottom - (value - y_min) / (y_max - y_min) * plot_height

    for tick in range(math.floor(y_min / 100.0) * 100, math.ceil(y_max / 100.0) * 100 + 1, 100):
        y = y_to_px(float(tick))
        draw.line((plot_left, y, plot_right, y), fill=GRID, width=1)
        label = str(tick)
        tw, th = text_size(draw, label, small_font)
        draw.text((plot_left - 16 - tw, y - th / 2), label, font=small_font, fill=MUTED)

    for tick in sorted(set(int(value) for value in x_values)):
        x = x_to_px(float(tick))
        draw.line((x, plot_top, x, plot_bottom), fill=(236, 236, 232), width=1)
        label = str(tick)
        tw, th = text_size(draw, label, small_font)
        draw.text((x - tw / 2, plot_bottom + 14), label, font=small_font, fill=MUTED)

    zero_y = y_to_px(0.0)
    zero_x = x_to_px(0.0)
    draw.line((plot_left, zero_y, plot_right, zero_y), fill=TEXT, width=2)
    draw.line((zero_x, plot_top, zero_x, plot_bottom), fill=RED, width=2)

    sorted_points = sorted(points, key=lambda point: point["x"])
    line_points = [(x_to_px(point["x"]), y_to_px(point["coef"])) for point in sorted_points]
    if len(line_points) > 1:
        draw.line(line_points, fill=LINE, width=4)

    for point in sorted_points:
        x = x_to_px(point["x"])
        y = y_to_px(point["coef"])
        lower = y_to_px(point["lower"])
        upper = y_to_px(point["upper"])
        baseline_flag = int(point.get("baseline", 0.0))
        draw.line((x, lower, x, upper), fill=LINE, width=3)
        draw.line((x - 10, lower, x + 10, lower), fill=LINE, width=3)
        draw.line((x - 10, upper, x + 10, upper), fill=LINE, width=3)
        if baseline_flag:
            draw.ellipse((x - 8, y - 8, x + 8, y + 8), outline=RED, width=3, fill=PANEL_BG)
        else:
            draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=LINE, outline=PANEL_BG, width=2)

    note = "Pretrend failed" if pretrend_result == "fail" else f"Pretrend={pretrend_result}"
    draw.text((plot_right - 220, plot_top + 8), note, font=label_font, fill=RED if pretrend_result == "fail" else MUTED)
    image.save(output_path)


def draw_scatter(points: list[dict[str, object]], output_path: Path) -> None:
    image, draw, title_font, label_font, small_font = create_canvas(1500, 920)
    ensure_parent(output_path)
    margin_left, margin_right, margin_top, margin_bottom = 120, 80, 130, 120
    plot_left = margin_left
    plot_top = margin_top
    plot_right = image.size[0] - margin_right
    plot_bottom = image.size[1] - margin_bottom
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top
    draw.rounded_rectangle((50, 50, image.size[0] - 50, image.size[1] - 50), radius=24, fill=PANEL_BG, outline=GRID, width=2)
    draw.text((80, 70), "F07. Digital Infra Cost Pressure vs CPII", font=title_font, fill=TEXT)
    draw.text((80, 108), "Digital-infrastructure sector-country-quarter points with fitted line", font=label_font, fill=MUTED)

    if not points:
        image.save(output_path)
        return

    x_values = [float(point["x"]) for point in points]
    y_values = [float(point["y"]) for point in points]
    x_min, x_max = min(x_values), max(x_values)
    y_min, y_max = min(y_values), max(y_values)
    x_pad = max((x_max - x_min) * 0.10, 0.01)
    y_pad = max((y_max - y_min) * 0.10, 1.0)
    x_min -= x_pad
    x_max += x_pad
    y_min -= y_pad
    y_max += y_pad

    def x_to_px(value: float) -> float:
        return plot_left + (value - x_min) / (x_max - x_min) * plot_width

    def y_to_px(value: float) -> float:
        return plot_bottom - (value - y_min) / (y_max - y_min) * plot_height

    for tick in range(math.floor(y_min / 5.0) * 5, math.ceil(y_max / 5.0) * 5 + 1, 5):
        y = y_to_px(float(tick))
        draw.line((plot_left, y, plot_right, y), fill=GRID, width=1)
        label = str(tick)
        tw, th = text_size(draw, label, small_font)
        draw.text((plot_left - 16 - tw, y - th / 2), label, font=small_font, fill=MUTED)

    for idx in range(6):
        x_tick = x_min + (x_max - x_min) * idx / 5
        x = x_to_px(x_tick)
        draw.line((x, plot_top, x, plot_bottom), fill=(236, 236, 232), width=1)
        label = fmt(x_tick, 2)
        tw, th = text_size(draw, label, small_font)
        draw.text((x - tw / 2, plot_bottom + 14), label, font=small_font, fill=MUTED)

    mean_x = sum(x_values) / len(x_values)
    mean_y = sum(y_values) / len(y_values)
    denom = sum((value - mean_x) ** 2 for value in x_values)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_values, y_values)) / denom if denom else 0.0
    intercept = mean_y - slope * mean_x
    start_y = intercept + slope * x_min
    end_y = intercept + slope * x_max
    draw.line((x_to_px(x_min), y_to_px(start_y), x_to_px(x_max), y_to_px(end_y)), fill=RED, width=4)

    for point in points:
        x = x_to_px(float(point["x"]))
        y = y_to_px(float(point["y"]))
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=LINE, outline=PANEL_BG, width=2)
        label = str(point["label"])
        draw.text((x + 8, y - 16), label, font=small_font, fill=MUTED)

    image.save(output_path)


def correlation_color(value: Optional[float]) -> tuple[int, int, int]:
    if value is None:
        return (235, 235, 235)
    clipped = max(-1.0, min(1.0, value))
    if clipped >= 0:
        intensity = int(255 - clipped * 170)
        return (intensity, 245, intensity)
    intensity = int(255 - abs(clipped) * 170)
    return (245, intensity, intensity)


def draw_heatmap(labels: list[str], matrix: list[list[Optional[float]]], max_pair_n: int, output_path: Path) -> None:
    cell = 90
    left = 260
    top = 180
    width = left + len(labels) * cell + 90
    height = top + len(labels) * cell + 100
    image, draw, title_font, label_font, small_font = create_canvas(width, height)
    ensure_parent(output_path)
    draw.rounded_rectangle((30, 30, width - 30, height - 30), radius=24, fill=PANEL_BG, outline=GRID, width=2)
    draw.text((60, 60), "F08. Core Variable Correlation Heatmap", font=title_font, fill=TEXT)
    draw.text((60, 102), f"Pairwise Pearson correlations on sector-country-quarter rows | max pair n={max_pair_n}", font=label_font, fill=MUTED)

    for idx, label in enumerate(labels):
        x = left + idx * cell + cell / 2
        tw, th = text_size(draw, label, small_font)
        draw.text((x - tw / 2, top - 36), label, font=small_font, fill=TEXT)
        tw, th = text_size(draw, label, small_font)
        draw.text((left - 18 - tw, top + idx * cell + cell / 2 - th / 2), label, font=small_font, fill=TEXT)

    for row_idx, row_values in enumerate(matrix):
        for col_idx, value in enumerate(row_values):
            x0 = left + col_idx * cell
            y0 = top + row_idx * cell
            x1 = x0 + cell
            y1 = y0 + cell
            draw.rectangle((x0, y0, x1, y1), fill=correlation_color(value), outline=GRID)
            label = "" if value is None else fmt(value, 2)
            tw, th = text_size(draw, label, label_font)
            draw.text((x0 + cell / 2 - tw / 2, y0 + cell / 2 - th / 2), label, font=label_font, fill=TEXT)

    image.save(output_path)


def update_project_manifest() -> None:
    manifest_rows = read_csv(MANIFEST_PATH)
    additions = [
        {
            "artifact_type": "script",
            "path": "scripts/build_report_ready_assets.py",
            "owner_step": PROMPT_NAME,
            "source_type": "local_code",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Builds remaining report-ready tables and figures T08-T10 and F03-F08 from already processed CPII and regression outputs.",
        },
        {
            "artifact_type": "table",
            "path": "outputs/tables/T08_basic_stats_summary.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_report_asset",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Basic statistics summary across core analytical variables and panel scopes.",
        },
        {
            "artifact_type": "table",
            "path": "outputs/tables/T09_cpii_sector_mean_comparison.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_report_asset",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Sector mean comparison table for CPII and its three subindexes.",
        },
        {
            "artifact_type": "table",
            "path": "outputs/tables/T10_cpii_extreme_observations.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_report_asset",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Top and bottom sector-quarter CPII observations with change diagnostics.",
        },
        {
            "artifact_type": "figure",
            "path": "outputs/figures/F03_cpii_subindex_decomposition.png",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_report_asset",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Stacked sector decomposition chart using mean subindex contributions to CPII.",
        },
        {
            "artifact_type": "figure",
            "path": "outputs/figures/F04_cpii_sector_mean_compare.png",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_report_asset",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Bar chart comparing mean CPII by sector with one-standard-deviation bands.",
        },
        {
            "artifact_type": "figure",
            "path": "outputs/figures/F05_music_event_study_plot.png",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_report_asset",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Music event-study coefficient plot built from the estimated regression result table.",
        },
        {
            "artifact_type": "figure",
            "path": "outputs/figures/F06_webtoon_story_event_study_plot.png",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_report_asset",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Webtoon/story event-study coefficient plot built from the estimated regression result table.",
        },
        {
            "artifact_type": "figure",
            "path": "outputs/figures/F07_digital_infra_pressure_scatter.png",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_report_asset",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Scatter plot relating digital-infrastructure network cost ratio and CPII.",
        },
        {
            "artifact_type": "figure",
            "path": "outputs/figures/F08_core_variable_correlation_heatmap.png",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_report_asset",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Heatmap of pairwise correlations across raw variables, subindexes, and CPII.",
        },
        {
            "artifact_type": "log",
            "path": "logs/report_ready_asset_build_log.md",
            "owner_step": PROMPT_NAME,
            "source_type": "local_log",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Build log for the completion of previously missing report-ready tables and figures.",
        },
    ]
    existing_keys = {(row["owner_step"], row["path"]) for row in manifest_rows}
    for addition in additions:
        key = (addition["owner_step"], addition["path"])
        if key not in existing_keys:
            manifest_rows.append(addition)
            existing_keys.add(key)
    write_csv(MANIFEST_PATH, manifest_rows, list(manifest_rows[0].keys()))


def update_workflow_log() -> None:
    header = f"### {PROMPT_NAME}. report-ready 자산 미완료분 생성"
    existing = WORKFLOW_LOG_PATH.read_text(encoding="utf-8") if WORKFLOW_LOG_PATH.exists() else ""
    if header in existing:
        return
    addition = "\n".join(
        [
            header,
            "",
            "- `scripts/build_report_ready_assets.py`를 생성하고 기존 processed/result 파일에서 누락된 report-ready 자산 `T08`, `T09`, `T10`, `F03`, `F04`, `F05`, `F06`, `F07`, `F08`을 생성",
            "- `T08_basic_stats_summary.csv`, `T09_cpii_sector_mean_comparison.csv`, `T10_cpii_extreme_observations.csv`를 생성",
            "- `F03_cpii_subindex_decomposition.png`, `F04_cpii_sector_mean_compare.png`, `F05_music_event_study_plot.png`, `F06_webtoon_story_event_study_plot.png`, `F07_digital_infra_pressure_scatter.png`, `F08_core_variable_correlation_heatmap.png`를 생성",
            "- `logs/report_ready_asset_build_log.md`에 입력 파일, 생성 규칙, 관측치 수를 기록",
        ]
    )
    if existing and not existing.endswith("\n"):
        existing += "\n"
    WORKFLOW_LOG_PATH.write_text(existing + addition + "\n", encoding="utf-8")


def write_log(
    t08_rows: list[dict[str, str]],
    t09_rows: list[dict[str, str]],
    t10_rows: list[dict[str, str]],
    music_points: list[dict[str, float]],
    webtoon_points: list[dict[str, float]],
    scatter_points: list[dict[str, object]],
    max_pair_n: int,
) -> None:
    lines = [
        "# Report Ready Asset Build Log",
        "",
        f"- Access date: `{ACCESS_DATE}`",
        f"- Owner step: `{PROMPT_NAME}`",
        "- 목적: Exec Prompt 35와 37에서 남아 있던 missing-but-derivable report-ready 자산 9개를 실제 파일로 생성한다.",
        "",
        "## Generated Tables",
        f"- `T08_basic_stats_summary.csv`: `{len(t08_rows)}` rows",
        f"- `T09_cpii_sector_mean_comparison.csv`: `{len(t09_rows)}` rows",
        f"- `T10_cpii_extreme_observations.csv`: `{len(t10_rows)}` rows",
        "",
        "## Generated Figures",
        f"- `F03_cpii_subindex_decomposition.png`: sectors `{len(t09_rows)}`개 기준 누적막대",
        f"- `F04_cpii_sector_mean_compare.png`: sectors `{len(t09_rows)}`개 기준 평균 비교",
        f"- `F05_music_event_study_plot.png`: plotted coefficients `{len(music_points)}`",
        f"- `F06_webtoon_story_event_study_plot.png`: plotted coefficients `{len(webtoon_points)}`",
        f"- `F07_digital_infra_pressure_scatter.png`: points `{len(scatter_points)}`",
        f"- `F08_core_variable_correlation_heatmap.png`: max pair n `{max_pair_n}`",
        "",
        "## Construction Rules",
        "- `T08`은 4개 variable panel에서 12개 핵심 변수만 골라 관측치 수, 평균, 표준편차, 25/50/75 분위, 최소, 최대를 계산했다.",
        "- `T09`는 계산 완료된 `sector-quarter` CPII 행만 사용해 분야별 평균 CPII와 하위 지수 평균을 산출했다.",
        "- `T10`은 `sector-quarter` CPII 상위 5개와 하위 5개를 뽑고 `timeseries_change_summary.csv`의 진단 플래그를 결합했다.",
        "- `F05`, `F06`은 event-study 회귀 결과표의 계수와 `1.96*SE` 기반 신뢰구간만 사용해 coefficient plot으로 그렸다.",
        "- `F07`과 `F08`은 `variable_panel_sector_quarter.csv`와 `cpii_panel_sector_country_quarter.csv`를 `panel_sector_quarter_id`로 결합한 뒤 생성했다.",
        "",
        "## Notes",
        "- `F03`은 mean CPII 자체가 아니라 `I_reg/3`, `I_risk/3`, `I_market/3`의 누적 기여분으로 표시했다.",
        "- event-study 그림에는 baseline period의 0점을 별도 표시했고, 사전추세 판정은 subtitle에 함께 적었다.",
        "- correlation heatmap은 pairwise complete observations를 사용했으며, 관측치가 2개 미만인 조합은 빈칸으로 남겼다.",
    ]
    LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    t08_rows = build_t08_basic_stats()
    t09_rows = build_t09_sector_means()
    t10_rows = build_t10_extremes()

    draw_stacked_bar(t09_rows, F03_PATH)
    draw_mean_bar(t09_rows, F04_PATH)

    music_points, music_baseline, music_pretrend, music_label = event_points_from_regression(REGRESSION_MUSIC_PATH)
    webtoon_points, webtoon_baseline, webtoon_pretrend, webtoon_label = event_points_from_regression(REGRESSION_WEBTOON_PATH)
    draw_event_plot(music_points, music_baseline, music_pretrend, music_label, "F05. Music Event Study", F05_PATH)
    draw_event_plot(webtoon_points, webtoon_baseline, webtoon_pretrend, webtoon_label, "F06. Webtoon/Story Event Study", F06_PATH)

    scatter_points = build_scatter_points()
    draw_scatter(scatter_points, F07_PATH)

    labels, matrix, max_pair_n = build_correlation_matrix()
    draw_heatmap(labels, matrix, max_pair_n, F08_PATH)

    write_log(t08_rows, t09_rows, t10_rows, music_points, webtoon_points, scatter_points, max_pair_n)
    update_project_manifest()
    update_workflow_log()


if __name__ == "__main__":
    main()
