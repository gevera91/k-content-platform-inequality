from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[2]

COMPOSITE_PATH = (
    PROJECT_ROOT
    / "data/processed/claim_strengthening/reverse_discrimination_composite_narrow.csv"
)
GAP_PATH = (
    PROJECT_ROOT / "outputs/tables/claim_strengthening/T_claim_korea_vs_global_gap.csv"
)
OUTPUT_TABLE_PATH = (
    PROJECT_ROOT / "outputs/tables/claim_strengthening/T_claim_channel_decomposition.csv"
)
OUTPUT_FIGURE_PATH = (
    PROJECT_ROOT / "outputs/figures/claim_strengthening/F_claim_channel_decomposition.png"
)


CHANNELS = [
    ("reg", "i_reg_narrow", "Regulation"),
    ("risk", "i_risk_narrow", "Cost/Risk"),
    ("market", "i_market_narrow", "Market Transfer"),
]


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def build_firm_level_rows() -> dict[str, list[dict[str, object]]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    with COMPOSITE_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            grouped[(row["peer_group_id"], row["firm_std"])].append(row)

    peer_level: dict[str, list[dict[str, object]]] = defaultdict(list)
    for (peer_group_id, firm_std), items in grouped.items():
        eligible = [
            row
            for row in items
            if row["composite_rank_eligible_flag"] == "yes" and row["composite_narrow"]
        ]
        chosen = eligible if eligible else [row for row in items if row["composite_narrow"]]
        korean_flag = any(row["analysis_role"].startswith("korean") for row in items)

        out: dict[str, object] = {
            "peer_group_id": peer_group_id,
            "firm_std": firm_std,
            "korean_firm_flag": korean_flag,
            "ranking_basis": "eligible_mean" if eligible else "all_row_mean_fallback",
        }
        for _, field_name, _ in CHANNELS:
            vals = [float(row[field_name]) for row in chosen if row[field_name] != ""]
            out[field_name] = mean(vals) if vals else None
        peer_level[peer_group_id].append(out)
    return peer_level


def load_gap_table() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    with GAP_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            out[row["peer_group_id"]] = row
    return out


def build_rows() -> list[dict[str, str]]:
    firm_level = build_firm_level_rows()
    gap_table = load_gap_table()
    rows: list[dict[str, str]] = []

    for peer_group_id, items in sorted(firm_level.items()):
        korean_rows = [row for row in items if row["korean_firm_flag"]]
        global_rows = [row for row in items if not row["korean_firm_flag"]]
        total_gap = float(gap_table[peer_group_id]["korea_minus_global_gap"])
        disadvantage_flag = "yes" if total_gap < 0 else "no"

        channel_components: list[float] = []
        channel_stats: list[tuple[str, str, float | None, float | None, float | None]] = []
        for channel_id, field_name, channel_label in CHANNELS:
            korean_values = [row[field_name] for row in korean_rows if row[field_name] is not None]
            global_values = [row[field_name] for row in global_rows if row[field_name] is not None]
            korean_mean = mean(korean_values) if korean_values else None
            global_mean = mean(global_values) if global_values else None
            gap = (
                korean_mean - global_mean
                if korean_mean is not None and global_mean is not None
                else None
            )
            channel_stats.append((channel_id, channel_label, korean_mean, global_mean, gap))
            if gap is not None and total_gap < 0:
                channel_components.append(max(0.0, -gap))

        total_adverse = sum(channel_components)

        for channel_id, channel_label, korean_mean, global_mean, gap in channel_stats:
            if gap is not None and total_gap < 0:
                adverse_component = max(0.0, -gap)
                adverse_share = adverse_component / total_adverse if total_adverse > 0 else None
            else:
                adverse_component = 0.0 if gap is not None else None
                adverse_share = None

            rows.append(
                {
                    "peer_group_id": peer_group_id,
                    "overall_korea_minus_global_gap": f"{total_gap:.6f}",
                    "overall_disadvantage_flag": disadvantage_flag,
                    "channel_id": channel_id,
                    "channel_label": channel_label,
                    "korean_channel_mean": (
                        f"{korean_mean:.6f}" if korean_mean is not None else ""
                    ),
                    "global_channel_mean": (
                        f"{global_mean:.6f}" if global_mean is not None else ""
                    ),
                    "korea_minus_global_channel_gap": (
                        f"{gap:.6f}" if gap is not None else ""
                    ),
                    "adverse_gap_component": (
                        f"{adverse_component:.6f}" if adverse_component is not None else ""
                    ),
                    "adverse_share_of_observed_disadvantage": (
                        f"{adverse_share:.6f}" if adverse_share is not None else ""
                    ),
                    "channel_data_flag": (
                        "observed" if gap is not None else "no_usable_channel_data"
                    ),
                    "interpretation_note": (
                        "Channel not observed under current narrow evidence"
                        if gap is None
                        else "Channel contributes to Korean disadvantage"
                        if adverse_component > 0
                        else "Channel does not worsen Korean disadvantage"
                    ),
                }
            )

    return rows


def write_table(rows: list[dict[str, str]]) -> None:
    OUTPUT_TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "peer_group_id",
        "overall_korea_minus_global_gap",
        "overall_disadvantage_flag",
        "channel_id",
        "channel_label",
        "korean_channel_mean",
        "global_channel_mean",
        "korea_minus_global_channel_gap",
        "adverse_gap_component",
        "adverse_share_of_observed_disadvantage",
        "channel_data_flag",
        "interpretation_note",
    ]
    with OUTPUT_TABLE_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def draw_figure(rows: list[dict[str, str]]) -> None:
    peer_order = []
    grouped: dict[str, dict[str, float]] = defaultdict(dict)
    overall_gap: dict[str, float] = {}
    for row in rows:
        peer = row["peer_group_id"]
        if peer not in peer_order:
            peer_order.append(peer)
        overall_gap[peer] = float(row["overall_korea_minus_global_gap"])
        grouped[peer][row["channel_id"]] = (
            float(row["adverse_gap_component"]) if row["adverse_gap_component"] else 0.0
        )

    width = 1150
    height = 480
    margin_left = 250
    margin_right = 70
    margin_top = 85
    margin_bottom = 70
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    bar_height = plot_height // max(len(peer_order), 1) - 18

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    colors = {
        "reg": "#6c757d",
        "risk": "#b02a37",
        "market": "#1d4ed8",
        "axis": "#222222",
        "grid": "#d9d9d9",
        "text": "#222222",
    }

    max_total = max(
        [sum(grouped[peer].values()) for peer in peer_order] + [1.0]
    )

    label_map = {
        "infra_traffic_ott": "Infra Traffic OTT",
        "mus_label_ip_export": "Music IP Export",
        "mus_streaming_paid_core": "Music Streaming Paid",
    }

    draw.text(
        (width // 2, 28),
        "Channel Decomposition of Korea Disadvantage",
        fill=colors["text"],
        font=font,
        anchor="ma",
    )
    draw.text(
        (width // 2, 48),
        "Only adverse components are stacked; positive-gap peers remain at zero",
        fill=colors["text"],
        font=font,
        anchor="ma",
    )

    # grid
    for frac in [0.25, 0.5, 0.75, 1.0]:
        x = margin_left + int(plot_width * frac)
        draw.line([(x, margin_top), (x, margin_top + plot_height)], fill=colors["grid"], width=1)

    for idx, peer in enumerate(peer_order):
        y0 = margin_top + idx * (bar_height + 24)
        y1 = y0 + bar_height
        draw.text(
            (margin_left - 12, y0 + bar_height // 2),
            label_map.get(peer, peer),
            fill=colors["text"],
            font=font,
            anchor="rs",
        )
        current_x = margin_left
        for channel_id, _, _ in CHANNELS:
            value = grouped[peer].get(channel_id, 0.0)
            seg_width = int((value / max_total) * plot_width)
            if seg_width > 0:
                draw.rounded_rectangle(
                    [current_x, y0, current_x + seg_width, y1],
                    radius=4,
                    fill=colors[channel_id],
                )
                current_x += seg_width

        draw.text(
            (current_x + 10, y0 + bar_height // 2),
            f"overall gap {overall_gap[peer]:.2f}",
            fill=colors["text"],
            font=font,
            anchor="lm",
        )

    legend_y = height - 34
    legend_x = margin_left
    for channel_id, _, label in CHANNELS:
        draw.rectangle([legend_x, legend_y, legend_x + 14, legend_y + 14], fill=colors[channel_id])
        draw.text((legend_x + 20, legend_y + 11), label, fill=colors["text"], font=font, anchor="lm")
        legend_x += 170

    OUTPUT_FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT_FIGURE_PATH)


def main() -> None:
    rows = build_rows()
    write_table(rows)
    draw_figure(rows)


if __name__ == "__main__":
    main()
