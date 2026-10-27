#!/usr/bin/env python3

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont


BASE_DIR = Path(__file__).resolve().parents[1]

SECTOR_PATH = BASE_DIR / "data/processed/cpii_panel_sector_quarter.csv"
COUNTRY_PATH = BASE_DIR / "data/processed/cpii_panel_sector_country_quarter.csv"
FIRM_PATH = BASE_DIR / "data/processed/cpii_panel_firm_country_quarter.csv"

OUT_FIG_SECTOR = BASE_DIR / "outputs/figures/cpii_timeseries_by_sector.png"
OUT_FIG_COUNTRY = BASE_DIR / "outputs/figures/cpii_timeseries_by_country.png"
OUT_FIG_FIRM = BASE_DIR / "outputs/figures/cpii_timeseries_by_firm.png"
OUT_TABLE = BASE_DIR / "outputs/tables/timeseries_change_summary.csv"
OUT_LOG = BASE_DIR / "logs/timeseries_analysis_log.md"
MANIFEST_PATH = BASE_DIR / "data/registry/project_manifest.csv"
WORKFLOW_LOG_PATH = BASE_DIR / "logs/workflow_log.md"

ACCESS_DATE = "2026-03-29"
PROMPT_NAME = "Exec Prompt 29"
LARGE_CHANGE_THRESHOLD = 5.0
BREAK_THRESHOLD = 3.0

COLOR_PALETTE = [
    "#0B6E4F",
    "#C44900",
    "#386FA4",
    "#7A4419",
    "#8B1E3F",
    "#3C6997",
    "#5B8E7D",
    "#C84C09",
    "#6A4C93",
    "#2D6A4F",
]


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def safe_float(value: str) -> Optional[float]:
    if value is None:
        return None
    stripped = str(value).strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def fmt(value: Optional[float]) -> str:
    if value is None:
        return ""
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def join_nonempty(values: Iterable[str]) -> str:
    cleaned = sorted({value for value in values if value})
    return "|".join(cleaned)


def quarter_sort_key(value: str) -> Tuple[int, int]:
    return int(value[:4]), int(value[-1])


def mean_or_none(values: Iterable[Optional[float]]) -> Optional[float]:
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def moving_average(values: List[Optional[float]], window: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for idx in range(len(values)):
        current = values[max(0, idx - window + 1): idx + 1]
        if len(current) < window:
            out.append(None)
            continue
        cleaned = [value for value in current if value is not None]
        if len(cleaned) != window:
            out.append(None)
        else:
            out.append(sum(cleaned) / window)
    return out


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def lighten(color: Tuple[int, int, int], amount: float = 0.45) -> Tuple[int, int, int]:
    return tuple(int(channel + (255 - channel) * amount) for channel in color)


def font_default() -> ImageFont.ImageFont:
    return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def build_sector_series() -> Dict[str, List[Dict[str, object]]]:
    rows = [
        row for row in read_csv(SECTOR_PATH)
        if safe_float(row.get("CPII", "")) is not None
    ]
    series: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row in rows:
        series[row["sector_std"]].append(
            {
                "entity_type": "sector",
                "entity_id": row["sector_std"],
                "sector_std": row["sector_std"],
                "home_country": "",
                "year_quarter": row["year_quarter"],
                "CPII": safe_float(row["CPII"]),
                "I_reg": safe_float(row["I_reg"]),
                "I_risk": safe_float(row["I_risk"]),
                "I_market": safe_float(row["I_market"]),
                "support_count": int(row.get("cpii_observed_subindex_count", "0") or 0),
                "support_count_meaning": "observed_subindex_count",
                "support_list": row.get("cpii_subindex_names_used", ""),
            }
        )
    return {
        key: sorted(items, key=lambda item: quarter_sort_key(str(item["year_quarter"])))
        for key, items in series.items()
    }


def build_country_series() -> Dict[str, List[Dict[str, object]]]:
    rows = [
        row for row in read_csv(COUNTRY_PATH)
        if safe_float(row.get("CPII", "")) is not None
    ]
    grouped: Dict[Tuple[str, str], List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["country_std"], row["year_quarter"])].append(row)

    series: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for (country_std, year_quarter), members in sorted(grouped.items(), key=lambda item: (item[0][0], quarter_sort_key(item[0][1]))):
        series[country_std].append(
            {
                "entity_type": "country",
                "entity_id": country_std,
                "sector_std": "",
                "home_country": "",
                "year_quarter": year_quarter,
                "CPII": mean_or_none(safe_float(member["CPII"]) for member in members),
                "I_reg": mean_or_none(safe_float(member["I_reg"]) for member in members),
                "I_risk": mean_or_none(safe_float(member["I_risk"]) for member in members),
                "I_market": mean_or_none(safe_float(member["I_market"]) for member in members),
                "support_count": len(members),
                "support_count_meaning": "sector_count_used",
                "support_list": join_nonempty(member["sector_std"] for member in members),
            }
        )
    return series


def build_firm_series() -> Dict[str, List[Dict[str, object]]]:
    rows = [
        row for row in read_csv(FIRM_PATH)
        if safe_float(row.get("CPII", "")) is not None
    ]
    grouped: Dict[Tuple[str, str], List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["firm_std"], row["year_quarter"])].append(row)

    series: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for (firm_std, year_quarter), members in sorted(grouped.items(), key=lambda item: (item[0][0], quarter_sort_key(item[0][1]))):
        series[firm_std].append(
            {
                "entity_type": "firm",
                "entity_id": firm_std,
                "sector_std": members[0]["sector_std"],
                "home_country": members[0]["home_country"],
                "year_quarter": year_quarter,
                "CPII": mean_or_none(safe_float(member["CPII"]) for member in members),
                "I_reg": mean_or_none(safe_float(member["I_reg"]) for member in members),
                "I_risk": mean_or_none(safe_float(member["I_risk"]) for member in members),
                "I_market": mean_or_none(safe_float(member["I_market"]) for member in members),
                "support_count": len(members),
                "support_count_meaning": "market_country_count_used",
                "support_list": join_nonempty(member["country_std"] for member in members),
            }
        )
    return series


def analyze_series(
    series_dict: Dict[str, List[Dict[str, object]]],
) -> Tuple[List[Dict[str, str]], Dict[str, List[Dict[str, object]]], List[Tuple[str, str, float, str]]]:
    summary_rows: List[Dict[str, str]] = []
    enriched_series: Dict[str, List[Dict[str, object]]] = {}
    break_candidates: List[Tuple[str, str, float, str]] = []

    for entity_id, items in sorted(series_dict.items()):
        ordered = sorted(items, key=lambda item: quarter_sort_key(str(item["year_quarter"])))
        cpii_values = [item["CPII"] for item in ordered]
        ma2_values = moving_average(cpii_values, 2)
        ma4_values = moving_average(cpii_values, 4)

        abs_changes = []
        for idx in range(1, len(ordered)):
            current = ordered[idx]["CPII"]
            previous = ordered[idx - 1]["CPII"]
            if current is not None and previous is not None:
                abs_changes.append(abs(current - previous))
        max_abs_change = max(abs_changes) if abs_changes else None

        enriched_items: List[Dict[str, object]] = []
        for idx, item in enumerate(ordered):
            prev = ordered[idx - 1] if idx > 0 else None
            current_cpii = item["CPII"]
            prev_cpii = prev["CPII"] if prev else None
            level_change = (
                current_cpii - prev_cpii
                if current_cpii is not None and prev_cpii is not None
                else None
            )
            rate_change = (
                level_change / prev_cpii
                if level_change is not None and prev_cpii not in (None, 0)
                else None
            )
            delta_i_reg = (
                item["I_reg"] - prev["I_reg"]
                if prev and item["I_reg"] is not None and prev["I_reg"] is not None
                else None
            )
            delta_i_risk = (
                item["I_risk"] - prev["I_risk"]
                if prev and item["I_risk"] is not None and prev["I_risk"] is not None
                else None
            )
            delta_i_market = (
                item["I_market"] - prev["I_market"]
                if prev and item["I_market"] is not None and prev["I_market"] is not None
                else None
            )

            dominant_subindex = ""
            dominant_delta = None
            dominant_candidates = {
                "I_reg": delta_i_reg,
                "I_risk": delta_i_risk,
                "I_market": delta_i_market,
            }
            observed_candidates = {
                key: value
                for key, value in dominant_candidates.items()
                if value is not None
            }
            if observed_candidates:
                dominant_subindex = max(observed_candidates, key=lambda key: abs(observed_candidates[key]))
                dominant_delta = observed_candidates[dominant_subindex]

            support_changed = (
                prev is not None and item["support_count"] != prev["support_count"]
            )
            large_change_flag = (
                "yes"
                if level_change is not None and abs(level_change) >= LARGE_CHANGE_THRESHOLD
                else "no"
            )
            structural_break_candidate = (
                "yes"
                if level_change is not None
                and max_abs_change is not None
                and abs(level_change) == max_abs_change
                and abs(level_change) >= BREAK_THRESHOLD
                else "no"
            )
            if structural_break_candidate == "yes":
                break_strength = "strong" if abs(level_change) >= LARGE_CHANGE_THRESHOLD and len(ordered) >= 3 else "tentative"
                break_candidates.append(
                    (
                        str(item["entity_type"]),
                        str(item["entity_id"]),
                        abs(level_change),
                        str(item["year_quarter"]),
                    )
                )
            else:
                break_strength = ""

            cause_parts = []
            if dominant_subindex and dominant_delta is not None:
                direction = "up" if dominant_delta > 0 else "down"
                cause_parts.append(f"{dominant_subindex}_{direction}_dominant")
            if support_changed:
                meaning = str(item["support_count_meaning"])
                if meaning == "sector_count_used":
                    cause_parts.append("sector_mix_changed")
                elif meaning == "market_country_count_used":
                    cause_parts.append("market_mix_changed")
                else:
                    cause_parts.append("support_mix_changed")
            if level_change is not None and not cause_parts:
                cause_parts.append("broad_based_or_small_change")
            cause_memo = "|".join(cause_parts)

            enriched_item = dict(item)
            enriched_item["moving_average_2q"] = ma2_values[idx]
            enriched_item["moving_average_4q"] = ma4_values[idx]
            enriched_item["prev_cpii_level"] = prev_cpii
            enriched_item["level_change"] = level_change
            enriched_item["rate_change"] = rate_change
            enriched_item["delta_I_reg"] = delta_i_reg
            enriched_item["delta_I_risk"] = delta_i_risk
            enriched_item["delta_I_market"] = delta_i_market
            enriched_item["large_change_flag"] = large_change_flag
            enriched_item["structural_break_candidate"] = structural_break_candidate
            enriched_item["break_strength"] = break_strength
            enriched_item["dominant_subindex"] = dominant_subindex
            enriched_item["cause_candidate_memo"] = cause_memo
            enriched_item["series_observation_count"] = len(ordered)
            enriched_items.append(enriched_item)

            summary_rows.append(
                {
                    "entity_type": str(item["entity_type"]),
                    "entity_id": str(item["entity_id"]),
                    "sector_std": str(item["sector_std"]),
                    "home_country": str(item["home_country"]),
                    "year_quarter": str(item["year_quarter"]),
                    "series_observation_count": str(len(ordered)),
                    "cpii_level": fmt(current_cpii),
                    "prev_cpii_level": fmt(prev_cpii),
                    "level_change": fmt(level_change),
                    "rate_change": fmt(rate_change),
                    "moving_average_2q": fmt(ma2_values[idx]),
                    "moving_average_4q": fmt(ma4_values[idx]),
                    "I_reg": fmt(item["I_reg"]),
                    "I_risk": fmt(item["I_risk"]),
                    "I_market": fmt(item["I_market"]),
                    "delta_I_reg": fmt(delta_i_reg),
                    "delta_I_risk": fmt(delta_i_risk),
                    "delta_I_market": fmt(delta_i_market),
                    "support_count": str(item["support_count"]),
                    "support_count_meaning": str(item["support_count_meaning"]),
                    "support_list": str(item["support_list"]),
                    "large_change_flag": large_change_flag,
                    "structural_break_candidate": structural_break_candidate,
                    "break_strength": break_strength,
                    "dominant_subindex": dominant_subindex,
                    "cause_candidate_memo": cause_memo,
                }
            )

        enriched_series[entity_id] = enriched_items

    break_candidates.sort(key=lambda item: (-item[2], item[0], item[1], item[3]))
    return summary_rows, enriched_series, break_candidates


def draw_line_panel(
    draw: ImageDraw.ImageDraw,
    rect: Tuple[int, int, int, int],
    series_items: List[Dict[str, object]],
    ordered_quarters: List[str],
    title: str,
    color_rgb: Tuple[int, int, int],
    support_label: bool = False,
) -> None:
    left, top, right, bottom = rect
    font = font_default()
    title_font = font
    bg_color = (255, 255, 255)
    axis_color = (70, 70, 70)
    grid_color = (220, 220, 220)

    draw.rounded_rectangle(rect, radius=8, fill=bg_color, outline=(210, 210, 210))
    draw.text((left + 10, top + 8), title, fill=(20, 20, 20), font=title_font)

    chart_left = left + 36
    chart_top = top + 28
    chart_right = right - 14
    chart_bottom = bottom - 26
    chart_width = max(chart_right - chart_left, 10)
    chart_height = max(chart_bottom - chart_top, 10)

    for y_tick in [0, 25, 50, 75, 100]:
        y = chart_bottom - int((y_tick / 100.0) * chart_height)
        draw.line((chart_left, y, chart_right, y), fill=grid_color, width=1)
        draw.text((left + 4, y - 5), str(y_tick), fill=(90, 90, 90), font=font)

    quarter_positions = {}
    if len(ordered_quarters) == 1:
        quarter_positions[ordered_quarters[0]] = chart_left + chart_width // 2
    else:
        for idx, quarter in enumerate(ordered_quarters):
            x = chart_left + int(idx * chart_width / (len(ordered_quarters) - 1))
            quarter_positions[quarter] = x

    for idx, quarter in enumerate(ordered_quarters):
        x = quarter_positions[quarter]
        draw.line((x, chart_top, x, chart_bottom), fill=(245, 245, 245), width=1)
        if len(ordered_quarters) <= 6 or idx in {0, len(ordered_quarters) - 1}:
            text = quarter.replace("Q", "-Q")
            tw, _ = text_size(draw, text, font)
            draw.text((x - tw // 2, chart_bottom + 4), text, fill=(90, 90, 90), font=font)

    draw.rectangle((chart_left, chart_top, chart_right, chart_bottom), outline=axis_color, width=1)

    actual_points = []
    ma_points = []
    for item in series_items:
        value = item["CPII"]
        if value is None:
            continue
        x = quarter_positions[str(item["year_quarter"])]
        y = chart_bottom - int((float(value) / 100.0) * chart_height)
        actual_points.append((x, y))
        ma_value = item.get("moving_average_2q")
        if ma_value is not None:
            ma_y = chart_bottom - int((float(ma_value) / 100.0) * chart_height)
            ma_points.append((x, ma_y))

    if len(ma_points) >= 2:
        draw.line(ma_points, fill=lighten(color_rgb, 0.55), width=2)
    if len(actual_points) >= 2:
        draw.line(actual_points, fill=color_rgb, width=3)
    for idx, item in enumerate(series_items):
        value = item["CPII"]
        if value is None:
            continue
        x = quarter_positions[str(item["year_quarter"])]
        y = chart_bottom - int((float(value) / 100.0) * chart_height)
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=color_rgb, outline=color_rgb)
        if idx == len(series_items) - 1:
            label = f"{value:.1f}"
            draw.text((min(x + 6, chart_right - 24), y - 8), label, fill=color_rgb, font=font)
        if support_label and item.get("support_count"):
            label = str(item["support_count"])
            draw.text((x - 4, min(y + 8, chart_bottom - 10)), label, fill=(110, 110, 110), font=font)


def create_sector_figure(sector_series: Dict[str, List[Dict[str, object]]]) -> None:
    ordered_quarters = sorted(
        {
            str(item["year_quarter"])
            for items in sector_series.values()
            for item in items
        },
        key=quarter_sort_key,
    )
    image = Image.new("RGB", (1600, 900), (248, 246, 241))
    draw = ImageDraw.Draw(image)
    font = font_default()

    draw.text((40, 24), "CPII Timeseries By Sector", fill=(20, 20, 20), font=font)
    draw.text((40, 42), "Solid line: CPII level, light line: trailing 2-quarter average", fill=(80, 80, 80), font=font)

    panel_rect = (40, 80, 1260, 820)
    draw.rounded_rectangle(panel_rect, radius=10, fill=(255, 255, 255), outline=(210, 210, 210))

    chart_left = panel_rect[0] + 52
    chart_top = panel_rect[1] + 30
    chart_right = panel_rect[2] - 18
    chart_bottom = panel_rect[3] - 36
    chart_width = chart_right - chart_left
    chart_height = chart_bottom - chart_top

    for y_tick in [0, 25, 50, 75, 100]:
        y = chart_bottom - int((y_tick / 100.0) * chart_height)
        draw.line((chart_left, y, chart_right, y), fill=(225, 225, 225), width=1)
        draw.text((panel_rect[0] + 8, y - 5), str(y_tick), fill=(90, 90, 90), font=font)

    quarter_positions = {}
    if len(ordered_quarters) == 1:
        quarter_positions[ordered_quarters[0]] = chart_left + chart_width // 2
    else:
        for idx, quarter in enumerate(ordered_quarters):
            x = chart_left + int(idx * chart_width / (len(ordered_quarters) - 1))
            quarter_positions[quarter] = x
            draw.line((x, chart_top, x, chart_bottom), fill=(242, 242, 242), width=1)
            label = quarter.replace("Q", "-Q")
            tw, _ = text_size(draw, label, font)
            draw.text((x - tw // 2, chart_bottom + 8), label, fill=(90, 90, 90), font=font)

    draw.rectangle((chart_left, chart_top, chart_right, chart_bottom), outline=(70, 70, 70), width=1)

    legend_x = 1300
    legend_y = 120
    for idx, sector_std in enumerate(sorted(sector_series)):
        color = hex_to_rgb(COLOR_PALETTE[idx % len(COLOR_PALETTE)])
        lighter = lighten(color, 0.55)
        items = sector_series[sector_std]
        ma_values = moving_average([item["CPII"] for item in items], 2)
        actual_points = []
        ma_points = []
        for item, ma_value in zip(items, ma_values):
            x = quarter_positions[str(item["year_quarter"])]
            y = chart_bottom - int((float(item["CPII"]) / 100.0) * chart_height)
            actual_points.append((x, y))
            if ma_value is not None:
                ma_y = chart_bottom - int((float(ma_value) / 100.0) * chart_height)
                ma_points.append((x, ma_y))
        if len(ma_points) >= 2:
            draw.line(ma_points, fill=lighter, width=2)
        if len(actual_points) >= 2:
            draw.line(actual_points, fill=color, width=3)
        for point in actual_points:
            draw.ellipse((point[0] - 4, point[1] - 4, point[0] + 4, point[1] + 4), fill=color, outline=color)
        last_x, last_y = actual_points[-1]
        draw.text((min(last_x + 8, chart_right - 50), last_y - 9), f"{items[-1]['CPII']:.1f}", fill=color, font=font)

        draw.line((legend_x, legend_y + idx * 26 + 6, legend_x + 22, legend_y + idx * 26 + 6), fill=color, width=3)
        draw.line((legend_x, legend_y + idx * 26 + 12, legend_x + 22, legend_y + idx * 26 + 12), fill=lighter, width=2)
        draw.text((legend_x + 30, legend_y + idx * 26), sector_std, fill=(40, 40, 40), font=font)

    image.save(OUT_FIG_SECTOR)


def create_grid_figure(
    series_dict: Dict[str, List[Dict[str, object]]],
    ordered_keys: List[str],
    ordered_quarters: List[str],
    title: str,
    subtitle: str,
    output_path: Path,
    columns: int,
    support_label: bool = False,
) -> None:
    card_width = 460
    card_height = 250
    rows = (len(ordered_keys) + columns - 1) // columns
    image = Image.new("RGB", (columns * card_width + 60, rows * card_height + 110), (248, 246, 241))
    draw = ImageDraw.Draw(image)
    font = font_default()

    draw.text((24, 20), title, fill=(20, 20, 20), font=font)
    draw.text((24, 38), subtitle, fill=(80, 80, 80), font=font)

    for idx, key in enumerate(ordered_keys):
        row_idx = idx // columns
        col_idx = idx % columns
        x0 = 20 + col_idx * card_width
        y0 = 70 + row_idx * card_height
        rect = (x0, y0, x0 + card_width - 24, y0 + card_height - 20)
        color = hex_to_rgb(COLOR_PALETTE[idx % len(COLOR_PALETTE)])
        draw_line_panel(draw, rect, series_dict[key], ordered_quarters, key, color, support_label=support_label)

    image.save(output_path)


def main() -> None:
    sector_series = build_sector_series()
    country_series = build_country_series()
    firm_series_all = build_firm_series()
    firm_series = {
        key: value
        for key, value in firm_series_all.items()
        if len(value) >= 2
    }
    excluded_singletons = sorted(
        key for key, value in firm_series_all.items() if len(value) < 2
    )

    sector_summary_rows, sector_enriched, sector_breaks = analyze_series(sector_series)
    country_summary_rows, country_enriched, country_breaks = analyze_series(country_series)
    firm_summary_rows, firm_enriched, firm_breaks = analyze_series(firm_series_all)

    all_summary_rows = sorted(
        sector_summary_rows + country_summary_rows + firm_summary_rows,
        key=lambda row: (row["entity_type"], row["entity_id"], quarter_sort_key(row["year_quarter"])),
    )
    write_csv(OUT_TABLE, all_summary_rows, list(all_summary_rows[0].keys()))

    sector_quarters = sorted(
        {row["year_quarter"] for row in sector_summary_rows},
        key=quarter_sort_key,
    )
    country_quarters = sorted(
        {row["year_quarter"] for row in country_summary_rows},
        key=quarter_sort_key,
    )
    firm_quarters = sorted(
        {row["year_quarter"] for row in firm_summary_rows if row["entity_id"] in firm_series},
        key=quarter_sort_key,
    )

    create_sector_figure(sector_enriched)
    create_grid_figure(
        country_enriched,
        ordered_keys=sorted(country_enriched),
        ordered_quarters=country_quarters,
        title="CPII Timeseries By Country",
        subtitle="Each panel shows the country-quarter average CPII across available sectors. Small grey labels mark sector counts.",
        output_path=OUT_FIG_COUNTRY,
        columns=3,
        support_label=True,
    )
    create_grid_figure(
        {key: firm_enriched[key] for key in sorted(firm_series)},
        ordered_keys=sorted(firm_series),
        ordered_quarters=firm_quarters,
        title="CPII Timeseries By Firm",
        subtitle="Each panel shows the firm-quarter mean CPII across available market countries. Small grey labels mark country counts.",
        output_path=OUT_FIG_FIRM,
        columns=4,
        support_label=True,
    )

    all_breaks = sorted(sector_breaks + country_breaks + firm_breaks, key=lambda item: (-item[2], item[0], item[1], item[3]))
    top_breaks = all_breaks[:10]
    large_change_count = sum(1 for row in all_summary_rows if row["large_change_flag"] == "yes")
    strong_break_count = sum(1 for row in all_summary_rows if row["break_strength"] == "strong")
    tentative_break_count = sum(1 for row in all_summary_rows if row["break_strength"] == "tentative")

    log_lines = [
        "# Timeseries Analysis Log",
        "",
        f"- Access date: `{ACCESS_DATE}`",
        f"- Prompt: `{PROMPT_NAME}`",
        "- 시계열 요약표는 sector, country, firm 세 수준을 하나의 long table로 통합했다.",
        "- country 시계열은 `country-quarter`에서 이용 가능한 sector 평균 CPII이고, firm 시계열은 `firm-quarter`에서 이용 가능한 market-country 평균 CPII이다.",
        "",
        "## Generated Outputs",
        "- `outputs/figures/cpii_timeseries_by_sector.png`",
        "- `outputs/figures/cpii_timeseries_by_country.png`",
        "- `outputs/figures/cpii_timeseries_by_firm.png`",
        "- `outputs/tables/timeseries_change_summary.csv`",
        "",
        "## Coverage",
        f"- sector series: `{len(sector_enriched)}`",
        f"- country series: `{len(country_enriched)}`",
        f"- firm series total: `{len(firm_enriched)}`",
        f"- firm series plotted (>=2 quarters): `{len(firm_series)}`",
        f"- excluded singleton firm series: `{join_nonempty(excluded_singletons) or 'none'}`",
        f"- total summary rows: `{len(all_summary_rows)}`",
        "",
        "## Required Analyses Covered",
        "- 수준 변화: `cpii_level`, `prev_cpii_level`, `level_change`에 기록",
        "- 변화율: `rate_change`에 기록",
        "- 구조적 전환점 후보: `structural_break_candidate`, `break_strength`에 기록",
        "- 이동평균: `moving_average_2q`, `moving_average_4q`에 기록",
        "- 큰 폭 변화 원인 후보: `dominant_subindex`, `cause_candidate_memo`에 기록",
        "",
        "## Change Diagnostics",
        f"- large change rows (|ΔCPII| >= {LARGE_CHANGE_THRESHOLD}): `{large_change_count}`",
        f"- strong break candidates: `{strong_break_count}`",
        f"- tentative break candidates: `{tentative_break_count}`",
        f"- top 10 absolute change candidates: `{top_breaks}`",
        "",
        "## Notes",
        "- sector figure는 실선으로 수준, 옅은 선으로 2분기 이동평균을 함께 표시한다.",
        "- country와 firm figure의 작은 회색 숫자는 각각 sector count와 market-country count를 뜻한다.",
        "- country 시계열은 quarter마다 포함 sector가 달라질 수 있고, firm 시계열은 quarter마다 포함 market이 달라질 수 있으므로 큰 폭 변화 해석 시 `cause_candidate_memo`와 `support_count`를 함께 봐야 한다.",
    ]
    OUT_LOG.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    manifest_rows = read_csv(MANIFEST_PATH)
    additions = [
        {
            "artifact_type": "script",
            "path": "scripts/build_timeseries_analysis.py",
            "owner_step": PROMPT_NAME,
            "source_type": "local_code",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Builds quarter-level CPII change summaries and PNG timeseries figures for sector, country, and firm views.",
        },
        {
            "artifact_type": "figure",
            "path": "outputs/figures/cpii_timeseries_by_sector.png",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_figure",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Sector-level CPII timeseries chart with trailing 2-quarter moving averages.",
        },
        {
            "artifact_type": "figure",
            "path": "outputs/figures/cpii_timeseries_by_country.png",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_figure",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Country-level CPII timeseries small-multiple chart using quarter means across available sectors.",
        },
        {
            "artifact_type": "figure",
            "path": "outputs/figures/cpii_timeseries_by_firm.png",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_figure",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Firm-level CPII timeseries small-multiple chart using quarter means across available market countries.",
        },
        {
            "artifact_type": "table",
            "path": "outputs/tables/timeseries_change_summary.csv",
            "owner_step": PROMPT_NAME,
            "source_type": "derived_timeseries_table",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Unified change-summary table with level, rate, moving averages, structural break flags, and cause memos.",
        },
        {
            "artifact_type": "log",
            "path": "logs/timeseries_analysis_log.md",
            "owner_step": PROMPT_NAME,
            "source_type": "local_log",
            "source_url": "",
            "access_date": ACCESS_DATE,
            "status": "created",
            "notes": "Coverage and diagnostics log for sector, country, and firm CPII timeseries analysis.",
        },
    ]
    existing_keys = {(row["owner_step"], row["path"]) for row in manifest_rows}
    for addition in additions:
        key = (addition["owner_step"], addition["path"])
        if key not in existing_keys:
            manifest_rows.append(addition)
            existing_keys.add(key)
    write_csv(MANIFEST_PATH, manifest_rows, list(manifest_rows[0].keys()))

    workflow_header = f"### {PROMPT_NAME}. 분야별·기업별 시계열 분석"
    workflow_text = WORKFLOW_LOG_PATH.read_text(encoding="utf-8") if WORKFLOW_LOG_PATH.exists() else ""
    if workflow_header not in workflow_text:
        addition = "\n".join(
            [
                workflow_header,
                "",
                "- `outputs/figures/cpii_timeseries_by_sector.png`, `cpii_timeseries_by_country.png`, `cpii_timeseries_by_firm.png`를 생성",
                "- `outputs/tables/timeseries_change_summary.csv`에 수준 변화, 변화율, 이동평균, 구조적 전환점 후보, 원인 후보 메모를 통합 기록",
                "- `logs/timeseries_analysis_log.md`에 plotted series 수, singleton 제외 대상, 큰 폭 변화 후보를 기록",
            ]
        )
        if workflow_text and not workflow_text.endswith("\n"):
            workflow_text += "\n"
        WORKFLOW_LOG_PATH.write_text(workflow_text + addition + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
