#!/usr/bin/env python3
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ACCESS_DATE = date.today().isoformat()

V1_PANEL_PATH = PROJECT_ROOT / "data" / "processed" / "claim_strengthening" / "kr_music_reverse_discrimination_reanalysis.csv"
V1_SUMMARY_PATH = PROJECT_ROOT / "outputs" / "tables" / "claim_strengthening" / "T_kr_music_reverse_discrimination_summary.csv"
REVISION_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "claim_strengthening"
    / "music_factcheck"
    / "music_metric_revision_registry.csv"
)

V2_PANEL_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "claim_strengthening"
    / "music_factcheck"
    / "kr_music_reverse_discrimination_reanalysis_v2.csv"
)
V2_SUMMARY_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "tables"
    / "claim_strengthening"
    / "T_kr_music_reverse_discrimination_summary_v2.csv"
)
V2_FIGURE_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "figures"
    / "claim_strengthening"
    / "F_kr_music_reverse_discrimination_summary_v2.png"
)
V2_LOG_PATH = (
    PROJECT_ROOT
    / "logs"
    / "claim_strengthening"
    / "music_factcheck"
    / "kr_music_reverse_discrimination_reanalysis_v2_log.md"
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def layer_judgment(score: float) -> str:
    if score >= 85:
        return "strong_support"
    if score >= 70:
        return "support_with_nuance"
    if score >= 50:
        return "mixed_support"
    return "weak_support"


def overall_sentence_from_judgment(judgment: str) -> str:
    if judgment == "strong_support":
        return "한국 음악산업은 국내 핵심 경쟁 접점 기준에서 평균적으로 높은 구조적 역차별 노출을 보인다."
    if judgment == "support_with_nuance":
        return "한국 음악산업은 국내 핵심 경쟁 접점 기준에서 평균적으로 구조적 불리함이 더 자주 관측되지만, 일부 축은 여전히 조건부다."
    if judgment == "mixed_support":
        return "한국 음악산업의 일부 핵심 접점에서는 구조적 비대칭이 반복 관측되지만, 산업 전체 평균의 역차별 headline은 더 조건부로 읽어야 한다."
    return "현재 재분석만으로는 한국 음악산업 전체 평균의 구조적 역차별을 강하게 단정하기 어렵다."


def build_added_rows() -> list[dict[str, str]]:
    return [
        {
            "layer_id": "L4",
            "layer_name": "foreign_metric_dependence",
            "metric_id": "luminate_korea_panel_inclusion_counterevidence",
            "metric_name": "Luminate added Melon and FLO to the Republic of Korea panel in 2023",
            "metric_value": "1.000000",
            "metric_unit": "flag",
            "support_score_0_100": "40.000000",
            "claim_effect": "tempers_overstatement",
            "evidence_strength": "strong",
            "source_id": "foreign_metric_dependence_alt_test|luminate_2023_report",
            "source_url": "https://luminatedata.com/wp-content/uploads/2024/01/Luminate_Year-End_Report_2023.pdf",
            "analysis_note": "Luminate's 2023 year-end report says Melon and FLO were added to the Republic of Korea streaming-data panel during 2023. This does not remove foreign metric dependence, but it directly weakens a blanket story that Korean music data are simply excluded from the foreign scoreboard system.",
            "v1_support_score_0_100": "",
            "revision_action": "add",
        },
        {
            "layer_id": "L5",
            "layer_name": "tax_asymmetry",
            "metric_id": "korea_digital_tax_reach_exists",
            "metric_name": "Korean law does not leave foreign digital platforms fully outside VAT and corporate-tax reach",
            "metric_value": "1.000000",
            "metric_unit": "flag",
            "support_score_0_100": "20.000000",
            "claim_effect": "tempers_overstatement",
            "evidence_strength": "strong",
            "source_id": "korea_digital_service_tax_rulebook",
            "source_url": "local_factcheck_rulebook",
            "analysis_note": "The official Korean tax rulebook confirms that foreign digital platforms are not categorically outside Korea's VAT and corporate-tax reach. This does not make Korea-facing tax incidence fully observable, but it does weaken any blanket narrative that foreign music platforms are simply untaxed in Korea.",
            "v1_support_score_0_100": "",
            "revision_action": "add",
        },
    ]


def build_v2_panel(v1_rows: list[dict[str, str]], revisions: list[dict[str, str]]) -> list[dict[str, str]]:
    revision_map = {row["metric_id"]: row for row in revisions}
    v2_rows: list[dict[str, str]] = []

    for row in v1_rows:
        metric_id = row["metric_id"]
        revision = revision_map[metric_id]
        new_row = dict(row)
        new_row["v1_support_score_0_100"] = row["support_score_0_100"]
        new_row["support_score_0_100"] = f"{float(revision['new_support_score']):.6f}"
        new_row["revision_action"] = revision["revision_action"]

        if metric_id == "gross_vs_net_slogan_overstatement":
            new_row["analysis_note"] = (
                "Factcheck reconfirmed that the strongest defensible reading is not a universal one-line domestic-gross versus foreign-net formula gap, "
                "but a transparency and comparability asymmetry between a published domestic tariff and less publicly comparable foreign-platform arrangements."
            )
        elif metric_id == "youtube_residual_claim_signal":
            new_row["analysis_note"] = (
                "The YouTube residual-claim portal now supports only a narrower reading: some YouTube-related settlement requires extra claims and verification workflow. "
                "That can complicate transparency and comparability, but the portal does not by itself prove unfair rates or misconduct."
            )
        elif metric_id == "billboard_repeat_download_shift":
            new_row["analysis_note"] = (
                "Billboard-related rule changes are now coded as a partial export-facing metric-dependence signal rather than direct anti-K-pop proof. "
                "The strongest reading is that foreign-owned metric design weakened channels where K-pop had been relatively strong, while several alternative explanations remain open."
            )
        elif metric_id == "streaming_peer_tax_score_gap":
            new_row["analysis_note"] = (
                "The direct-cost tax score gap still points in the same direction as the matched FY2025 Dreamus-versus-Spotify effective-tax-rate gap, "
                "but it is a second-stage burden score and therefore receives lower support weight than the underlying matched ETR calculation."
            )
        elif metric_id == "bigtech_korea_tax_visibility_gap":
            new_row["analysis_note"] = (
                "Current executable-panel missingness supports only a Korea-facing tax visibility gap, not a blanket nonpayment claim. "
                "The metric therefore remains in v2 at a much lower weight as a limited transparency signal."
            )
        elif metric_id == "foreign_contract_opacity":
            new_row["analysis_note"] = (
                "Official factchecks still do not reveal a precise foreign-platform rate formula, but they do strengthen the narrower claim that foreign arrangements are less transparent "
                "and less directly comparable to the published domestic tariff and ordinary settlement workflow."
            )

        v2_rows.append(new_row)

    v2_rows.extend(build_added_rows())
    v2_rows.sort(key=lambda row: (row["layer_id"], row["metric_id"]))
    return v2_rows


def build_summary(panel_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    layer_names: dict[str, str] = {}
    for row in panel_rows:
        grouped.setdefault(row["layer_id"], []).append(row)
        layer_names[row["layer_id"]] = row["layer_name"]

    summary_rows: list[dict[str, str]] = []
    layer_scores: list[float] = []
    supportive_total = 0
    tempering_total = 0

    for layer_id in sorted(grouped):
        rows = grouped[layer_id]
        scores = [float(row["support_score_0_100"]) for row in rows]
        layer_score = mean(scores)
        layer_scores.append(layer_score)
        supportive_count = sum(1 for row in rows if row["claim_effect"] == "supports_structural_discrimination")
        tempering_count = len(rows) - supportive_count
        supportive_total += supportive_count
        tempering_total += tempering_count
        judgment = layer_judgment(layer_score)
        if layer_score >= 70:
            note = "This layer continues to support the domestic structural-disadvantage reading for Korean music."
        elif layer_score >= 50:
            note = "This layer remains directionally supportive but now needs stronger caveats."
        else:
            note = "This layer is now too mixed to headline without stronger additional evidence."
        summary_rows.append(
            {
                "summary_level": "layer",
                "layer_id": layer_id,
                "layer_name": layer_names[layer_id],
                "metric_count": str(len(rows)),
                "supportive_metric_count": str(supportive_count),
                "tempering_metric_count": str(tempering_count),
                "average_support_score_0_100": f"{layer_score:.6f}",
                "supportive_share": f"{supportive_count / len(rows):.6f}",
                "headline_judgment": judgment,
                "interpretation_note": note,
            }
        )

    overall_score = mean(layer_scores)
    overall_judgment = layer_judgment(overall_score)
    summary_rows.append(
        {
            "summary_level": "overall",
            "layer_id": "OVERALL",
            "layer_name": "kr_music_domestic_structural_average_v2",
            "metric_count": str(len(panel_rows)),
            "supportive_metric_count": str(supportive_total),
            "tempering_metric_count": str(tempering_total),
            "average_support_score_0_100": f"{overall_score:.6f}",
            "supportive_share": f"{supportive_total / len(panel_rows):.6f}",
            "headline_judgment": overall_judgment,
            "interpretation_note": overall_sentence_from_judgment(overall_judgment),
        }
    )
    return summary_rows


def draw_figure(summary_rows: list[dict[str, str]]) -> None:
    layer_rows = [row for row in summary_rows if row["summary_level"] == "layer"]
    width = 1100
    height = 520
    margin_left = 240
    margin_top = 80
    plot_width = width - margin_left - 110
    step_y = 86

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    colors = {
        "axis": "#333333",
        "bar": "#1f6feb",
        "grid": "#dddddd",
        "text": "#111111",
    }
    label_map = {
        "regulatory_licensing_asymmetry": "Regulatory / Licensing",
        "google_bundle_platform_power": "Google Bundle Power",
        "domestic_governance_opacity": "Domestic Governance",
        "foreign_metric_dependence": "Foreign Metrics",
        "tax_asymmetry": "Tax Asymmetry",
    }

    draw.text((width // 2, 24), "Korean Music Reverse-Discrimination Reanalysis v2", fill=colors["text"], font=font, anchor="ma")
    draw.text((width // 2, 44), "Layer average support scores after factcheck-driven recoding", fill=colors["text"], font=font, anchor="ma")

    for tick in range(0, 101, 20):
        x = margin_left + int(plot_width * (tick / 100))
        draw.line([(x, margin_top), (x, margin_top + step_y * len(layer_rows))], fill=colors["grid"], width=1)
        draw.text((x, margin_top - 10), str(tick), fill=colors["text"], font=font, anchor="ms")

    for idx, row in enumerate(layer_rows):
        y = margin_top + idx * step_y + 28
        score = float(row["average_support_score_0_100"])
        x1 = margin_left + int(plot_width * (score / 100))
        draw.text((margin_left - 12, y), label_map.get(row["layer_name"], row["layer_name"]), fill=colors["text"], font=font, anchor="rs")
        draw.rounded_rectangle([margin_left, y - 12, x1, y + 12], radius=4, fill=colors["bar"])
        draw.text((x1 + 8, y + 1), f"{score:.1f}", fill=colors["text"], font=font, anchor="ls")

    V2_FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(V2_FIGURE_PATH)


def strongest_layer(summary_rows: list[dict[str, str]]) -> dict[str, str]:
    layer_rows = [row for row in summary_rows if row["summary_level"] == "layer"]
    return max(layer_rows, key=lambda row: float(row["average_support_score_0_100"]))


def write_log(v1_summary: list[dict[str, str]], v2_summary: list[dict[str, str]], v2_panel: list[dict[str, str]], revisions: list[dict[str, str]]) -> None:
    v1_layer_map = {row["layer_id"]: row for row in v1_summary if row["summary_level"] == "layer"}
    v2_layer_map = {row["layer_id"]: row for row in v2_summary if row["summary_level"] == "layer"}
    v1_overall = next(row for row in v1_summary if row["summary_level"] == "overall")
    v2_overall = next(row for row in v2_summary if row["summary_level"] == "overall")

    v1_sentence = "국내 핵심 경쟁 접점 기준으로 보면 한국 음악산업은 평균적으로 구조적 역차별 노출이 높다."
    v2_sentence = overall_sentence_from_judgment(v2_overall["headline_judgment"])
    top_layer = strongest_layer(v2_summary)

    with V2_LOG_PATH.open("w", encoding="utf-8") as handle:
        handle.write("# Korean Music Reverse-Discrimination Reanalysis v2\n\n")
        handle.write("- 이번 v2는 사실검증 결과를 반영해 `직접 근거는 유지`, `과장 해석은 하향`, `counterevidence는 명시 추가`하는 방식으로 재계산했다.\n")
        handle.write("- 핵심 변화는 `Billboard`, `YouTube residual`, `big-tech tax visibility`의 점수 하향과, `Melon/FLO의 Luminate 편입`, `외국 디지털 플랫폼에 대한 한국 tax reach 존재`의 신규 반영이다.\n\n")

        handle.write("## Revision Mix\n\n")
        actions = {}
        for row in revisions:
            actions[row["revision_action"]] = actions.get(row["revision_action"], 0) + 1
        for key in ["keep", "upgrade", "downgrade", "add"]:
            handle.write(f"- `{key}`: `{actions.get(key, 0)}`\n")

        handle.write("\n## Layer Score Change v1 -> v2\n\n")
        for layer_id in sorted(v2_layer_map):
            old_score = float(v1_layer_map[layer_id]["average_support_score_0_100"])
            new_score = float(v2_layer_map[layer_id]["average_support_score_0_100"])
            delta = new_score - old_score
            handle.write(
                f"- `{layer_id} {v2_layer_map[layer_id]['layer_name']}`: `{old_score:.6f} -> {new_score:.6f}` (`{delta:+.6f}`), judgment `{v1_layer_map[layer_id]['headline_judgment']} -> {v2_layer_map[layer_id]['headline_judgment']}`\n"
            )

        old_overall = float(v1_overall["average_support_score_0_100"])
        new_overall = float(v2_overall["average_support_score_0_100"])
        handle.write("\n## Overall Change\n\n")
        handle.write(f"- overall score: `{old_overall:.6f} -> {new_overall:.6f}` (`{new_overall - old_overall:+.6f}`)\n")
        handle.write(f"- headline judgment: `{v1_overall['headline_judgment']} -> {v2_overall['headline_judgment']}`\n")
        handle.write(f"- supportive share: `{v1_overall['supportive_share']} -> {v2_overall['supportive_share']}`\n")

        handle.write("\n## Strongest Sentence Change\n\n")
        handle.write(f"- v1 strongest sentence: `{v1_sentence}`\n")
        handle.write(f"- v2 strongest sentence: `{v2_sentence}`\n")
        handle.write(
            f"- v2 strongest surviving layer: `{top_layer['layer_id']} {top_layer['layer_name']}` with score `{top_layer['average_support_score_0_100']}` and judgment `{top_layer['headline_judgment']}`\n"
        )

        handle.write("\n## Metric Notes\n\n")
        for row in v2_panel:
            if row["revision_action"] in {"downgrade", "add"}:
                handle.write(
                    f"- `{row['metric_id']}` (`{row['revision_action']}`): v1 `{row['v1_support_score_0_100'] or 'NA'}` -> v2 `{row['support_score_0_100']}`\n"
                )


def main() -> None:
    v1_rows = read_csv(V1_PANEL_PATH)
    v1_summary = read_csv(V1_SUMMARY_PATH)
    revisions = read_csv(REVISION_PATH)
    v2_panel = build_v2_panel(v1_rows, revisions)
    panel_fields = [
        "layer_id",
        "layer_name",
        "metric_id",
        "metric_name",
        "metric_value",
        "metric_unit",
        "support_score_0_100",
        "claim_effect",
        "evidence_strength",
        "source_id",
        "source_url",
        "analysis_note",
        "v1_support_score_0_100",
        "revision_action",
    ]
    write_csv(V2_PANEL_PATH, panel_fields, v2_panel)

    v2_summary = build_summary(v2_panel)
    summary_fields = [
        "summary_level",
        "layer_id",
        "layer_name",
        "metric_count",
        "supportive_metric_count",
        "tempering_metric_count",
        "average_support_score_0_100",
        "supportive_share",
        "headline_judgment",
        "interpretation_note",
    ]
    write_csv(V2_SUMMARY_PATH, summary_fields, v2_summary)
    draw_figure(v2_summary)
    write_log(v1_summary, v2_summary, v2_panel, revisions)


if __name__ == "__main__":
    main()
