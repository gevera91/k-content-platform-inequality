from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data" / "processed" / "claim_strengthening" / "music_econ_extension"
FIG_DIR = PROJECT_ROOT / "outputs" / "figures" / "claim_strengthening"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def style_axes(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", color="#d7d9d3", linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)


def build_effective_burden_figure():
    rows = read_csv(DATA_DIR / "effective_burden_wedge_table.csv")
    order = [
        ("EBW01", "Legacy\ndirect gap"),
        ("EBW03", "Same-country\nbundle proxy"),
        ("EBW05", "Matched tax\nburden gap"),
        ("EBW02", "Licensing\ntransparency"),
        ("EBW07", "Tax\nobservability"),
        ("EBW04", "Governance\nlower bound"),
        ("EBW06", "Broad service\ncost gap"),
    ]
    row_map = {r["cell_id"]: r for r in rows}

    fig, ax = plt.subplots(figsize=(11.5, 6.5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, len(order) + 1)
    ax.axis("off")

    colors = {
        "legacy": "#1f3a5f",
        "market": "#c65d3a",
        "tax": "#2f7d59",
        "transparency": "#8b6fb3",
        "governance": "#6b5847",
        "caveat": "#9aa3a7",
    }

    title = "Music Streaming Effective Burden Wedge"
    subtitle = "Legacy anchor preserved; mechanism rows shown as parallel support objects, not a common-unit sum"
    ax.text(0, len(order) + 0.65, title, fontsize=18, fontweight="bold", color="#17212b")
    ax.text(0, len(order) + 0.25, subtitle, fontsize=10.5, color="#4c5967")

    for i, (row_id, label) in enumerate(order, start=1):
        row = row_map[row_id]
        y = len(order) - i + 1
        if row_id == "EBW01":
            face = colors["legacy"]
        elif row_id in {"EBW03"}:
            face = colors["market"]
        elif row_id in {"EBW05"}:
            face = colors["tax"]
        elif row_id in {"EBW02", "EBW07"}:
            face = colors["transparency"]
        elif row_id in {"EBW04"}:
            face = colors["governance"]
        else:
            face = colors["caveat"]

        box = FancyBboxPatch(
            (0.2, y - 0.33),
            9.3,
            0.58,
            boxstyle="round,pad=0.02,rounding_size=0.08",
            linewidth=0,
            facecolor=face,
            alpha=0.92,
        )
        ax.add_patch(box)
        ax.text(0.45, y - 0.02, label, va="center", ha="left", fontsize=11.2, color="white", fontweight="bold")
        ax.text(
            3.3,
            y - 0.02,
            f"{row['wedge_value']} {row['wedge_unit']}",
            va="center",
            ha="left",
            fontsize=10.8,
            color="white",
        )
        ax.text(
            6.0,
            y - 0.02,
            row["observed_or_bounded"].replace("_", " "),
            va="center",
            ha="left",
            fontsize=9.8,
            color="white",
        )

    ax.text(
        0.2,
        0.22,
        "Units differ across rows. The figure is a mechanism map: same-country price, transparency, tax, governance, and observability are shown in parallel.",
        fontsize=9.6,
        color="#55606b",
    )
    fig.tight_layout()
    fig.savefig(FIG_DIR / "F_music_econ_effective_burden_wedge.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def build_bundle_ladder_figure():
    rows = read_csv(DATA_DIR / "bundle_subsidy_wedge_table.csv")
    order = ["BSW01", "BSW02", "BSW03", "BSW04", "BSW05"]
    labels = {
        "BSW01": "Lite + YouTube Music\nseparate purchase",
        "BSW02": "Lite + Melon\nbasket",
        "BSW03": "Embedded music\nvs Melon",
        "BSW04": "Embedded music\nvs Spotify",
        "BSW05": "Premium vs\nMusic-only caveat",
    }
    row_map = {r["wedge_id"]: r for r in rows}
    values = [float(row_map[k]["subsidy_value_krw"]) for k in order]
    y = list(range(len(order)))
    colors = ["#1f3a5f", "#c65d3a", "#d98f4e", "#d98f4e", "#8a8f98"]

    fig, ax = plt.subplots(figsize=(10.8, 6.4))
    style_axes(ax)
    ax.axvline(0, color="#24303b", linewidth=1.2)
    bars = ax.barh(y, values, color=colors, height=0.62)
    ax.set_yticks(y, [labels[k] for k in order], fontsize=10.5)
    ax.set_xlabel("KRW subsidy relative to counterfactual", fontsize=11)
    ax.set_title("YouTube Bundle Subsidy Ladder", fontsize=18, fontweight="bold", color="#17212b", loc="left")
    ax.text(
        0,
        1.02,
        "Positive values mean the bundle is cheaper than the counterfactual basket; the final row is a feature-mismatch caveat.",
        transform=ax.transAxes,
        fontsize=10,
        color="#4c5967",
    )
    for bar, value in zip(bars, values):
        x = value + 110 if value >= 0 else value - 110
        ha = "left" if value >= 0 else "right"
        ax.text(x, bar.get_y() + bar.get_height() / 2, f"{int(value):,}", va="center", ha=ha, fontsize=10.2, color="#17212b")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "F_music_econ_bundle_subsidy_ladder.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def build_premium_lite_entry_proxy_figure():
    rows = read_csv(DATA_DIR / "premium_lite_did_results.csv")
    rows = [r for r in rows if r["estimation_status"] == "estimable_proxy_only"]
    labels = {
        "PLD01": "vs Melon regular",
        "PLD02": "vs Spotify Individual",
    }
    fig, ax = plt.subplots(figsize=(10.8, 6.4))
    ax.axvline(0, color="#24303b", linewidth=1.0)
    style_axes(ax)
    ax.set_ylim(-0.08, 1.48)

    y_positions = [1, 0]
    for y, row in zip(y_positions, rows):
        pre = float(row["pre_gap_value"])
        post = float(row["post_gap_value"])
        delta = int(post - pre)
        ax.plot([pre, post], [y, y], color="#c65d3a", linewidth=3, alpha=0.9)
        ax.scatter([pre], [y], color="#8a8f98", s=90, zorder=3, label="Pre" if y == 1 else None)
        ax.scatter([post], [y], color="#1f3a5f", s=90, zorder=3, label="Post" if y == 1 else None)
        ax.text(pre, y + 0.09, f"{int(pre):,}", ha="center", va="bottom", fontsize=10, color="#55606b")
        ax.text(post, y - 0.12, f"{int(post):,}", ha="center", va="top", fontsize=10, color="#17212b")
        ax.text(
            (pre + post) / 2,
            y + 0.16,
            f"DID-style proxy: {delta:,}",
            ha="center",
            va="center",
            fontsize=10.1,
            color="#c65d3a",
            bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="none", alpha=0.92),
        )

    ax.set_yticks(y_positions, [labels[r["result_id"]] for r in rows], fontsize=11)
    ax.set_xlabel("YouTube ecosystem minimum paid-entry gap (KRW)", fontsize=11)
    fig.suptitle(
        "Premium Lite Entry-Price Shock",
        x=0.125,
        y=0.975,
        ha="left",
        fontsize=18,
        fontweight="bold",
        color="#17212b",
    )
    fig.text(
        0.125,
        0.935,
        "Pre uses the existing YouTube Music Premium anchor. Post uses Premium Lite. "
        "This is a same-country price-entry proxy, not a usage DID.",
        ha="left",
        va="top",
        fontsize=10,
        color="#4c5967",
    )
    ax.legend(frameon=False, loc="lower right")
    fig.subplots_adjust(top=0.82, left=0.20, right=0.98, bottom=0.12)
    fig.savefig(FIG_DIR / "F_music_econ_premium_lite_entry_proxy.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def build_channel_mediation_map():
    rows = read_csv(DATA_DIR / "econ_channel_mediation_table.csv")
    picks = ["ECM01", "ECM03", "ECM06", "ECM09", "ECM10"]
    row_map = {r["mediation_id"]: r for r in rows}

    fig, ax = plt.subplots(figsize=(12.2, 7.2))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 10)
    ax.axis("off")

    ax.text(0, 9.55, "Legacy Channel to Econ Mechanism Bridge", fontsize=18, fontweight="bold", color="#17212b")
    ax.text(0, 9.08, "Schematic bridge only: channels are reinterpreted, not turned into causal mediation shares.", fontsize=10, color="#4c5967")

    channel_boxes = [
        (0.6, 7.0, 2.2, 1.1, "#8b6fb3", "Regulation"),
        (0.6, 4.8, 2.2, 1.1, "#2f7d59", "Cost / Risk"),
        (0.6, 2.6, 2.2, 1.1, "#c65d3a", "Market"),
    ]
    for x, y, w, h, color, text in channel_boxes:
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05,rounding_size=0.08", facecolor=color, edgecolor="none", alpha=0.92))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=12, color="white", fontweight="bold")

    bridge_boxes = [
        (4.2, 7.2, 3.1, 0.9, "#e8def6", "Licensing transparency wedge\n(ECM01)"),
        (4.2, 5.6, 3.1, 0.9, "#dcefe6", "Matched tax burden gap\n(ECM03)"),
        (4.2, 3.0, 3.1, 0.9, "#f7dfd6", "Same-country bundle undercut\n(ECM06)"),
        (4.2, 1.45, 3.1, 0.9, "#eceff1", "Identification caps\n(ECM09, ECM10)"),
    ]
    for x, y, w, h, color, text in bridge_boxes:
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05,rounding_size=0.06", facecolor=color, edgecolor="#c8ccd0", linewidth=0.8))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=10.5, color="#17212b")

    outcome_boxes = [
        (8.4, 7.15, 3.1, 0.95, "#f4f1dd", "Reg channel becomes a\nbounded transparency channel"),
        (8.4, 5.55, 3.1, 0.95, "#f4f1dd", "Risk channel splits into\ntax, governance, and tempering rows"),
        (8.4, 2.95, 3.1, 0.95, "#f4f1dd", "Market channel becomes a\nsame-country pull story"),
        (8.4, 1.40, 3.1, 0.95, "#f4f1dd", "Headline cap remains:\nforeign rate/tax gaps stay unestimated"),
    ]
    for x, y, w, h, color, text in outcome_boxes:
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05,rounding_size=0.06", facecolor=color, edgecolor="#d7ccb3", linewidth=0.8))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=10.2, color="#17212b")

    arrows = [
        ((2.8, 7.55), (4.2, 7.65)),
        ((2.8, 5.35), (4.2, 6.0)),
        ((2.8, 3.15), (4.2, 3.45)),
        ((2.8, 5.35), (4.2, 1.9)),
        ((2.8, 7.55), (4.2, 1.9)),
        ((7.3, 7.65), (8.4, 7.62)),
        ((7.3, 6.0), (8.4, 6.02)),
        ((7.3, 3.45), (8.4, 3.42)),
        ((7.3, 1.9), (8.4, 1.88)),
    ]
    for start, end in arrows:
        ax.annotate("", xy=end, xytext=start, arrowprops=dict(arrowstyle="->", color="#58636f", lw=1.4))

    fig.tight_layout()
    fig.savefig(FIG_DIR / "F_music_econ_channel_mediation_map.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def main():
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    build_effective_burden_figure()
    build_bundle_ladder_figure()
    build_premium_lite_entry_proxy_figure()
    build_channel_mediation_map()


if __name__ == "__main__":
    main()
