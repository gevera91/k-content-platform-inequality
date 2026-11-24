from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT / "outputs/tables/claim_strengthening/T_claim_peer_rank.csv"
)
OUTPUT_TABLE_PATH = (
    PROJECT_ROOT / "outputs/tables/claim_strengthening/T_claim_korea_vs_global_gap.csv"
)
OUTPUT_FIGURE_PATH = (
    PROJECT_ROOT / "outputs/figures/claim_strengthening/F_claim_korea_vs_global_gap.png"
)


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def load_rank_rows() -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    with INPUT_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            grouped[row["peer_group_id"]].append(row)
    return grouped


def build_table_rows() -> list[dict[str, str]]:
    grouped = load_rank_rows()
    rows: list[dict[str, str]] = []
    for peer_group_id, items in grouped.items():
        korean_rows = [row for row in items if row["korean_firm_flag"] == "yes"]
        global_rows = [row for row in items if row["korean_firm_flag"] == "no"]

        korean_values = [float(row["composite_narrow"]) for row in korean_rows]
        global_values = [float(row["composite_narrow"]) for row in global_rows]
        korean_mean = mean(korean_values)
        global_mean = mean(global_values)
        gap = korean_mean - global_mean

        best_korean = max(korean_rows, key=lambda row: float(row["composite_narrow"]))
        best_global = max(global_rows, key=lambda row: float(row["composite_narrow"]))
        fallback_count = sum(
            1 for row in korean_rows if row["ranking_basis"] == "all_row_mean_fallback"
        )

        rows.append(
            {
                "peer_group_id": peer_group_id,
                "korean_firm_count": str(len(korean_rows)),
                "global_peer_count": str(len(global_rows)),
                "korean_mean_composite": f"{korean_mean:.6f}",
                "global_peer_mean_composite": f"{global_mean:.6f}",
                "korea_minus_global_gap": f"{gap:.6f}",
                "gap_direction": (
                    "korean_higher"
                    if gap > 0
                    else "global_higher"
                    if gap < 0
                    else "tie"
                ),
                "best_korean_firm_std": best_korean["firm_std"],
                "best_korean_composite": best_korean["composite_narrow"],
                "best_global_firm_std": best_global["firm_std"],
                "best_global_composite": best_global["composite_narrow"],
                "korean_fallback_firm_count": str(fallback_count),
                "all_korean_eligible_flag": "yes" if fallback_count == 0 else "no",
                "interpretation_note": (
                    "Korean mean uses at least one fallback firm"
                    if fallback_count > 0
                    else "Korean mean uses only rank-eligible firm composites"
                ),
            }
        )
    rows.sort(key=lambda row: row["peer_group_id"])
    return rows


def write_table(rows: list[dict[str, str]]) -> None:
    OUTPUT_TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "peer_group_id",
        "korean_firm_count",
        "global_peer_count",
        "korean_mean_composite",
        "global_peer_mean_composite",
        "korea_minus_global_gap",
        "gap_direction",
        "best_korean_firm_std",
        "best_korean_composite",
        "best_global_firm_std",
        "best_global_composite",
        "korean_fallback_firm_count",
        "all_korean_eligible_flag",
        "interpretation_note",
    ]
    with OUTPUT_TABLE_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def draw_figure(rows: list[dict[str, str]]) -> None:
    width = 1100
    height = 460
    margin_left = 260
    margin_right = 80
    margin_top = 90
    margin_bottom = 70
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    center_x = margin_left + plot_width // 2

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    colors = {
        "axis": "#222222",
        "pos": "#2d6a4f",
        "neg": "#b02a37",
        "grid": "#d9d9d9",
        "text": "#222222",
    }

    values = [float(row["korea_minus_global_gap"]) for row in rows]
    max_abs = max(max(abs(v) for v in values), 1.0)
    step_y = plot_height // max(len(rows), 1)

    draw.text(
        (width // 2, 28),
        "Korea vs Global Mean Composite Gap",
        fill=colors["text"],
        font=font,
        anchor="ma",
    )
    draw.text(
        (width // 2, 48),
        "Positive means Korean-firm mean is higher; negative means global-peer mean is higher",
        fill=colors["text"],
        font=font,
        anchor="ma",
    )

    draw.line(
        [(center_x, margin_top), (center_x, margin_top + plot_height)],
        fill=colors["axis"],
        width=1,
    )
    for tick in [-1.0, -0.5, 0.5, 1.0]:
        x = int(center_x + tick * (plot_width / 2))
        draw.line(
            [(x, margin_top), (x, margin_top + plot_height)],
            fill=colors["grid"],
            width=1,
        )

    label_map = {
        "infra_traffic_ott": "Infra Traffic OTT",
        "mus_label_ip_export": "Music IP Export",
        "mus_streaming_paid_core": "Music Streaming Paid",
    }

    for idx, row in enumerate(rows):
        y_mid = margin_top + idx * step_y + step_y // 2
        gap = float(row["korea_minus_global_gap"])
        length = int((abs(gap) / max_abs) * (plot_width / 2 - 20))
        if gap >= 0:
            x0 = center_x
            x1 = center_x + length
            color = colors["pos"]
            value_anchor = "ls"
            value_x = x1 + 8
        else:
            x0 = center_x - length
            x1 = center_x
            color = colors["neg"]
            value_anchor = "rs"
            value_x = x0 - 8

        draw.rounded_rectangle(
            [x0, y_mid - 12, x1, y_mid + 12],
            radius=4,
            fill=color,
        )
        draw.text(
            (margin_left - 10, y_mid),
            label_map.get(row["peer_group_id"], row["peer_group_id"]),
            fill=colors["text"],
            font=font,
            anchor="rs",
        )
        draw.text(
            (value_x, y_mid + 4),
            f"{gap:.2f}",
            fill=colors["text"],
            font=font,
            anchor=value_anchor,
        )

    legend_y = height - 32
    draw.rectangle([margin_left, legend_y, margin_left + 14, legend_y + 14], fill=colors["pos"])
    draw.text((margin_left + 20, legend_y + 11), "Korean mean higher", fill=colors["text"], font=font, anchor="lm")
    draw.rectangle([margin_left + 190, legend_y, margin_left + 204, legend_y + 14], fill=colors["neg"])
    draw.text((margin_left + 210, legend_y + 11), "Global mean higher", fill=colors["text"], font=font, anchor="lm")

    OUTPUT_FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT_FIGURE_PATH)


def main() -> None:
    rows = build_table_rows()
    write_table(rows)
    draw_figure(rows)


if __name__ == "__main__":
    main()
