from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[2]

FIRM_DICTIONARY_PATH = PROJECT_ROOT / "data/registry/entity_dictionary_firm.csv"
MUSIC_MARKET_RAW_PATH = PROJECT_ROOT / "data/interim/music_market_raw_panel.csv"
CORE_SAMPLE_PATH = (
    PROJECT_ROOT
    / "data/registry/claim_strengthening/reverse_discrimination_core_sample_v1.csv"
)
OUTPUT_TABLE_PATH = (
    PROJECT_ROOT
    / "data/processed/claim_strengthening/concentration_decomposition_table.csv"
)
OUTPUT_FIGURE_PATH = (
    PROJECT_ROOT
    / "outputs/figures/claim_strengthening/F_claim_concentration_decomposition.png"
)


GROUP_SPECS = [
    {
        "peer_group_id": "mus_streaming_paid_core",
        "country_std": "kr",
        "metric_variant": "streaming_top200_inverse_rank_share",
        "market_hhi_variant": "streaming_top200_distributor_inverse_rank",
        "proxy_scope": "kr_streaming_chart_proxy_market",
        "construction_note": (
            "Direct paid-streaming service share is unavailable for Spotify@kr, so this "
            "group uses the KR streaming chart distributor-share proxy to decompose local "
            "versus global concentration."
        ),
    },
    {
        "peer_group_id": "mus_label_ip_export",
        "country_std": "kr",
        "metric_variant": "digital_top200_score_share",
        "market_hhi_variant": "digital_top200_distributor_score",
        "proxy_scope": "kr_digital_chart_proxy_market",
        "construction_note": (
            "Direct cross-country label share is unavailable for jp/us cells, so this group "
            "uses the KR digital chart distributor-share proxy to decompose local versus "
            "global concentration."
        ),
    },
]


def load_firm_home_country() -> dict[str, str]:
    mapping: dict[str, str] = {}
    with FIRM_DICTIONARY_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            mapping[row["firm_std"]] = row["home_country"]
    return mapping


def load_music_market_rows():
    firm_rows: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    market_hhi: dict[tuple[str, str], float] = {}

    with MUSIC_MARKET_RAW_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            period_key = row["year_month"]
            variant = row["metric_variant"]

            if (
                row["panel_unit_type"] == "firm_month"
                and row["metric_name"] == "chart_share"
                and row["country_std"] == "kr"
            ):
                firm_rows[(variant, period_key)].append(row)

            if (
                row["panel_unit_type"] == "market_month"
                and row["metric_name"] == "music_service_hhi"
                and row["country_std"] == "kr"
            ):
                market_hhi[(variant, period_key)] = float(row["metric_value"])

    return firm_rows, market_hhi


def load_core_sample_missing_cells() -> list[dict[str, str]]:
    missing_rows: list[dict[str, str]] = []
    with CORE_SAMPLE_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["include_flag"] != "yes":
                continue
            if row["peer_group_id"] == "infra_traffic_ott":
                missing_rows.append(
                    {
                        "peer_group_id": row["peer_group_id"],
                        "country_std": row["country_std"],
                        "period_key": "",
                        "metric_variant": "",
                        "proxy_scope": "no_direct_market_share_proxy",
                        "market_hhi_observed": "",
                        "local_top_firm_std": "",
                        "local_top_share": "",
                        "global_top_firm_std": "",
                        "global_top_share": "",
                        "local_total_share": "",
                        "global_total_share": "",
                        "observed_share_coverage": "",
                        "residual_untracked_share": "",
                        "local_hhi_component": "",
                        "global_hhi_component": "",
                        "observed_hhi_component_sum": "",
                        "local_minus_global_hhi_gap": "",
                        "latest_period_flag": "no",
                        "decomposition_status": "no_direct_market_share_proxy",
                        "construction_note": (
                            "Infra traffic peers do not have public market-share raw on the "
                            "same scale, so concentration decomposition is not directly built."
                        ),
                    }
                )
            elif row["peer_group_id"] == "mus_label_ip_export" and row["country_std"] in {
                "jp",
                "us",
            }:
                missing_rows.append(
                    {
                        "peer_group_id": row["peer_group_id"],
                        "country_std": row["country_std"],
                        "period_key": "",
                        "metric_variant": "",
                        "proxy_scope": "no_direct_market_share_proxy",
                        "market_hhi_observed": "",
                        "local_top_firm_std": "",
                        "local_top_share": "",
                        "global_top_firm_std": "",
                        "global_top_share": "",
                        "local_total_share": "",
                        "global_total_share": "",
                        "observed_share_coverage": "",
                        "residual_untracked_share": "",
                        "local_hhi_component": "",
                        "global_hhi_component": "",
                        "observed_hhi_component_sum": "",
                        "local_minus_global_hhi_gap": "",
                        "latest_period_flag": "no",
                        "decomposition_status": "no_direct_market_share_proxy",
                        "construction_note": (
                            "Comparable direct music chart-share raw is only available for KR, "
                            "so the jp/us IP-export cells remain outside direct concentration "
                            "decomposition."
                        ),
                    }
                )
    return missing_rows


def build_table_rows() -> list[dict[str, str]]:
    firm_home_country = load_firm_home_country()
    firm_rows, market_hhi = load_music_market_rows()

    output_rows: list[dict[str, str]] = []

    for spec in GROUP_SPECS:
        variant = spec["metric_variant"]
        periods = sorted(
            period_key for row_variant, period_key in firm_rows.keys() if row_variant == variant
        )
        latest_period = periods[-1]

        for period_key in periods:
            rows = firm_rows[(variant, period_key)]
            hhi_variant = spec["market_hhi_variant"]
            local_entries = []
            global_entries = []

            for row in rows:
                share = float(row["metric_value"])
                firm_std = row["firm_std"]
                if firm_home_country.get(firm_std) == spec["country_std"]:
                    local_entries.append((firm_std, share))
                else:
                    global_entries.append((firm_std, share))

            local_entries.sort(key=lambda item: (-item[1], item[0]))
            global_entries.sort(key=lambda item: (-item[1], item[0]))

            local_total_share = sum(share for _, share in local_entries)
            global_total_share = sum(share for _, share in global_entries)
            observed_share_coverage = local_total_share + global_total_share
            residual_untracked_share = max(0.0, 1.0 - observed_share_coverage)
            local_hhi_component = sum((share**2) * 10000.0 for _, share in local_entries)
            global_hhi_component = sum((share**2) * 10000.0 for _, share in global_entries)

            output_rows.append(
                {
                    "peer_group_id": spec["peer_group_id"],
                    "country_std": spec["country_std"],
                    "period_key": period_key,
                    "metric_variant": variant,
                    "proxy_scope": spec["proxy_scope"],
                    "market_hhi_observed": f"{market_hhi[(hhi_variant, period_key)]:.6f}",
                    "local_top_firm_std": local_entries[0][0] if local_entries else "",
                    "local_top_share": (
                        f"{local_entries[0][1]:.9f}" if local_entries else ""
                    ),
                    "global_top_firm_std": global_entries[0][0] if global_entries else "",
                    "global_top_share": (
                        f"{global_entries[0][1]:.9f}" if global_entries else ""
                    ),
                    "local_total_share": f"{local_total_share:.9f}",
                    "global_total_share": f"{global_total_share:.9f}",
                    "observed_share_coverage": f"{observed_share_coverage:.9f}",
                    "residual_untracked_share": f"{residual_untracked_share:.9f}",
                    "local_hhi_component": f"{local_hhi_component:.6f}",
                    "global_hhi_component": f"{global_hhi_component:.6f}",
                    "observed_hhi_component_sum": (
                        f"{(local_hhi_component + global_hhi_component):.6f}"
                    ),
                    "local_minus_global_hhi_gap": (
                        f"{(local_hhi_component - global_hhi_component):.6f}"
                    ),
                    "latest_period_flag": "yes" if period_key == latest_period else "no",
                    "decomposition_status": "direct_chart_proxy_market",
                    "construction_note": spec["construction_note"],
                }
            )

    output_rows.extend(load_core_sample_missing_cells())
    output_rows.sort(
        key=lambda row: (
            row["peer_group_id"],
            row["country_std"],
            row["period_key"] == "",
            row["period_key"],
        )
    )
    return output_rows


def write_table(rows: list[dict[str, str]]) -> None:
    OUTPUT_TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "peer_group_id",
        "country_std",
        "period_key",
        "metric_variant",
        "proxy_scope",
        "market_hhi_observed",
        "local_top_firm_std",
        "local_top_share",
        "global_top_firm_std",
        "global_top_share",
        "local_total_share",
        "global_total_share",
        "observed_share_coverage",
        "residual_untracked_share",
        "local_hhi_component",
        "global_hhi_component",
        "observed_hhi_component_sum",
        "local_minus_global_hhi_gap",
        "latest_period_flag",
        "decomposition_status",
        "construction_note",
    ]
    with OUTPUT_TABLE_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_figure(rows: list[dict[str, str]]) -> None:
    latest_rows = [
        row
        for row in rows
        if row["latest_period_flag"] == "yes"
        and row["decomposition_status"] == "direct_chart_proxy_market"
    ]
    latest_rows.sort(key=lambda row: row["peer_group_id"])

    labels = []
    local_top = []
    local_other = []
    global_top = []
    global_other = []
    residual = []
    local_hhi = []
    global_hhi = []
    titles = {
        "mus_label_ip_export": "Music IP Export\n(KR Digital Chart Proxy)",
        "mus_streaming_paid_core": "Music Streaming\n(KR Streaming Chart Proxy)",
    }

    for row in latest_rows:
        labels.append(titles.get(row["peer_group_id"], row["peer_group_id"]))
        local_top_share = float(row["local_top_share"])
        global_top_share = float(row["global_top_share"])
        local_total_share = float(row["local_total_share"])
        global_total_share = float(row["global_total_share"])
        local_top.append(local_top_share)
        local_other.append(max(0.0, local_total_share - local_top_share))
        global_top.append(global_top_share)
        global_other.append(max(0.0, global_total_share - global_top_share))
        residual.append(float(row["residual_untracked_share"]))
        local_hhi.append(float(row["local_hhi_component"]))
        global_hhi.append(float(row["global_hhi_component"]))

    width = 1200
    height = 600
    margin = 60
    gap = 40
    panel_width = (width - margin * 2 - gap) // 2
    panel_height = 360
    panel_top = 120
    left_x0 = margin
    right_x0 = margin + panel_width + gap

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    colors = {
        "local_top": "#1b4332",
        "local_other": "#40916c",
        "global_top": "#9d0208",
        "global_other": "#dc2f02",
        "residual": "#adb5bd",
        "local_hhi": "#2d6a4f",
        "global_hhi": "#e85d04",
        "axis": "#222222",
    }

    def draw_text(x: int, y: int, text: str, anchor: str = "la") -> None:
        draw.text((x, y), text, fill=colors["axis"], font=font, anchor=anchor)

    def draw_share_panel() -> None:
        x0 = left_x0
        y0 = panel_top
        x1 = x0 + panel_width
        y1 = y0 + panel_height
        draw.rectangle([x0, y0, x1, y1], outline=colors["axis"], width=1)
        draw_text((x0 + x1) // 2, 70, "Latest Share Decomposition", anchor="ma")

        bar_width = 110
        spacing = (panel_width - bar_width * len(labels)) // (len(labels) + 1)
        current_x = x0 + spacing
        for i, label in enumerate(labels):
            values = [
                ("local_top", local_top[i]),
                ("local_other", local_other[i]),
                ("global_top", global_top[i]),
                ("global_other", global_other[i]),
                ("residual", residual[i]),
            ]
            current_bottom = y1
            for key, value in values:
                segment_height = int(value * panel_height)
                if segment_height <= 0:
                    continue
                draw.rectangle(
                    [
                        current_x,
                        current_bottom - segment_height,
                        current_x + bar_width,
                        current_bottom,
                    ],
                    fill=colors[key],
                    outline="white",
                )
                current_bottom -= segment_height

            draw_text(current_x + bar_width // 2, y1 + 18, label.replace("\n", " "), anchor="ma")
            current_x += bar_width + spacing

        legend_items = [
            ("Local Top 1", "local_top"),
            ("Other Local", "local_other"),
            ("Global Top 1", "global_top"),
            ("Other Global", "global_other"),
            ("Residual Untracked", "residual"),
        ]
        lx = x0
        ly = y1 + 55
        for text, key in legend_items:
            draw.rectangle([lx, ly, lx + 12, ly + 12], fill=colors[key], outline=colors[key])
            draw_text(lx + 18, ly + 10, text, anchor="lm")
            lx += 128

    def draw_hhi_panel() -> None:
        x0 = right_x0
        y0 = panel_top
        x1 = x0 + panel_width
        y1 = y0 + panel_height
        draw.rectangle([x0, y0, x1, y1], outline=colors["axis"], width=1)
        draw_text((x0 + x1) // 2, 70, "Latest HHI Decomposition", anchor="ma")

        max_hhi = max(local_hhi + global_hhi) if labels else 1.0
        group_width = 150
        bar_width = 48
        spacing = (panel_width - group_width * len(labels)) // (len(labels) + 1)
        current_x = x0 + spacing
        for i, label in enumerate(labels):
            local_height = int((local_hhi[i] / max_hhi) * panel_height)
            global_height = int((global_hhi[i] / max_hhi) * panel_height)
            draw.rectangle(
                [current_x, y1 - local_height, current_x + bar_width, y1],
                fill=colors["local_hhi"],
                outline="white",
            )
            draw.rectangle(
                [current_x + bar_width + 12, y1 - global_height, current_x + bar_width * 2 + 12, y1],
                fill=colors["global_hhi"],
                outline="white",
            )
            draw_text(current_x + group_width // 2, y1 + 18, label.replace("\n", " "), anchor="ma")
            current_x += group_width + spacing

        legend_items = [
            ("Local HHI Component", "local_hhi"),
            ("Global HHI Component", "global_hhi"),
        ]
        lx = x0
        ly = y1 + 55
        for text, key in legend_items:
            draw.rectangle([lx, ly, lx + 12, ly + 12], fill=colors[key], outline=colors[key])
            draw_text(lx + 18, ly + 10, text, anchor="lm")
            lx += 180

    draw_text(width // 2, 30, "Claim Strengthening Concentration Decomposition", anchor="ma")
    draw_share_panel()
    draw_hhi_panel()

    OUTPUT_FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT_FIGURE_PATH)


def main() -> None:
    rows = build_table_rows()
    write_table(rows)
    build_figure(rows)


if __name__ == "__main__":
    main()
