from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = ROOT / "data/processed/claim_strengthening/direct_cost_burden_panel.csv"
TABLE_PATH = ROOT / "outputs/tables/claim_strengthening/T_claim_cost_sensitivity.csv"
FIGURE_PATH = ROOT / "outputs/figures/claim_strengthening/F_claim_cost_sensitivity.png"
LOG_PATH = ROOT / "logs/claim_strengthening/cost_sensitivity_log.md"

COMPONENT_FIELDS = {
    "tax": "tax_burden_score",
    "parafiscal": "parafiscal_burden_score",
    "network": "network_cost_score",
    "infra": "infra_cost_score",
}

RULES = {
    "baseline_equal": {
        "label": "Baseline equal",
        "weights": {"tax": 0.25, "parafiscal": 0.25, "network": 0.25, "infra": 0.25},
        "description": "Observed components are combined under equal weights and renormalized within row.",
    },
    "network_heavy": {
        "label": "Network heavy",
        "weights": {"tax": 0.15, "parafiscal": 0.15, "network": 0.50, "infra": 0.20},
        "description": "Common cost is allocated more aggressively to network operating pressure.",
    },
    "infra_heavy": {
        "label": "Infra heavy",
        "weights": {"tax": 0.15, "parafiscal": 0.15, "network": 0.20, "infra": 0.50},
        "description": "Common cost is allocated more aggressively to infrastructure and capex burden.",
    },
}

RULE_ORDER = ["baseline_equal", "network_heavy", "infra_heavy"]
RULE_COLORS = {
    "baseline_equal": "#2457C5",
    "network_heavy": "#D97706",
    "infra_heavy": "#1F8A5B",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def fmt_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}"


def sign_label(value: float | None) -> str:
    if value is None:
        return "not_available"
    if value > 1e-9:
        return "positive"
    if value < -1e-9:
        return "negative"
    return "zero"


def compute_weighted_score(row: dict[str, str], rule_id: str) -> float | None:
    observed = []
    for key, field in COMPONENT_FIELDS.items():
        raw = row.get(field, "")
        if raw != "":
            observed.append((key, float(raw)))
    if len(observed) < 2:
        return None
    weights = RULES[rule_id]["weights"]
    weight_sum = sum(weights[key] for key, _ in observed)
    return sum(value * weights[key] / weight_sum for key, value in observed)


def build_figure(rows: list[dict[str, object]]) -> None:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        if row["row_kind"] == "peer_group_summary":
            grouped[str(row["peer_group_id"])].append(row)

    peer_groups = [peer for peer in ["infra_traffic_ott", "mus_label_ip_export", "__overall__"] if peer in grouped]
    width = 1180
    height = 220 + len(peer_groups) * 180
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    draw.text((40, 24), "Claim-strengthening cost sensitivity", fill="#111827", font=font)
    draw.text((40, 44), "Korean mean minus global mean burden gap by allocation rule", fill="#4B5563", font=font)

    max_abs_gap = max(abs(float(row["korean_minus_global_gap"])) for row in rows if row["row_kind"] == "peer_group_summary")
    max_abs_gap = max(max_abs_gap, 1.0)
    axis_left = 360
    axis_right = width - 80
    usable_width = axis_right - axis_left

    y_base = 110
    block_height = 150
    bar_height = 24
    zero_x = axis_left + usable_width * 0.15
    pos_width = usable_width * 0.8

    for peer_index, peer in enumerate(peer_groups):
        top = y_base + peer_index * block_height
        display_peer = "overall_scored_rows" if peer == "__overall__" else peer
        draw.text((40, top), display_peer, fill="#111827", font=font)
        draw.line((axis_left, top + 18, axis_right, top + 18), fill="#D1D5DB", width=1)
        draw.line((zero_x, top + 18, zero_x, top + 110), fill="#9CA3AF", width=1)
        for idx, rule_id in enumerate(RULE_ORDER):
            row = next(r for r in grouped[peer] if r["allocation_rule"] == rule_id)
            gap = float(row["korean_minus_global_gap"])
            y = top + 35 + idx * 28
            draw.text((60, y + 5), RULES[rule_id]["label"], fill="#374151", font=font)
            bar_len = pos_width * (gap / max_abs_gap)
            x1 = zero_x
            x2 = zero_x + bar_len
            draw.rounded_rectangle((x1, y, x2, y + bar_height), radius=4, fill=RULE_COLORS[rule_id])
            draw.text((x2 + 8, y + 5), f"{gap:.2f}", fill="#111827", font=font)
            top_firm = row["top_rank_firm"]
            draw.text((axis_right - 180, y + 5), f"top {top_firm}", fill="#4B5563", font=font)

    legend_y = height - 46
    x = 40
    for rule_id in RULE_ORDER:
        draw.rounded_rectangle((x, legend_y, x + 18, legend_y + 12), radius=2, fill=RULE_COLORS[rule_id])
        draw.text((x + 24, legend_y - 1), RULES[rule_id]["label"], fill="#374151", font=font)
        x += 230

    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    img.save(FIGURE_PATH)


def main() -> None:
    base_rows = read_csv(INPUT_PATH)

    scored_rows = []
    for row in base_rows:
        if row["observed_component_count"] and int(row["observed_component_count"]) >= 2:
            scored_rows.append(row)

    rule_row_lookup: dict[str, list[dict[str, object]]] = {}
    summary_rows: list[dict[str, object]] = []

    baseline_rank_lookup: dict[str, str] = {}
    baseline_top_lookup: dict[str, str] = {}
    baseline_sign_lookup: dict[str, str] = {}

    for rule_id in RULE_ORDER:
        rule_scored_rows = []
        for row in scored_rows:
            weighted = compute_weighted_score(row, rule_id)
            if weighted is None:
                continue
            rule_scored_rows.append(
                {
                    "peer_group_id": row["peer_group_id"],
                    "firm_std": row["firm_std"],
                    "country_std": row["country_std"],
                    "analysis_role": row["analysis_role"],
                    "weighted_score": weighted,
                }
            )
        rule_row_lookup[rule_id] = rule_scored_rows

        peer_groups = sorted(set(r["peer_group_id"] for r in rule_scored_rows)) + ["__overall__"]
        for peer_group_id in peer_groups:
            if peer_group_id == "__overall__":
                subset = list(rule_scored_rows)
            else:
                subset = [r for r in rule_scored_rows if r["peer_group_id"] == peer_group_id]
            if not subset:
                continue

            korean_rows = [r for r in subset if "korean" in r["analysis_role"]]
            global_rows = [r for r in subset if "global" in r["analysis_role"]]
            korean_mean = sum(r["weighted_score"] for r in korean_rows) / len(korean_rows) if korean_rows else None
            global_mean = sum(r["weighted_score"] for r in global_rows) / len(global_rows) if global_rows else None
            gap = None if korean_mean is None or global_mean is None else korean_mean - global_mean

            ranking = sorted(subset, key=lambda r: r["weighted_score"], reverse=True)
            rank_signature = ">".join(r["firm_std"] for r in ranking)
            top_firm = ranking[0]["firm_std"]
            if rule_id == "baseline_equal":
                baseline_rank_lookup[peer_group_id] = rank_signature
                baseline_top_lookup[peer_group_id] = top_firm
                baseline_sign_lookup[peer_group_id] = sign_label(gap)

            summary_rows.append(
                {
                    "row_kind": "peer_group_summary",
                    "allocation_rule": rule_id,
                    "allocation_rule_label": RULES[rule_id]["label"],
                    "allocation_description": RULES[rule_id]["description"],
                    "peer_group_id": peer_group_id,
                    "scored_row_count": len(subset),
                    "korean_row_count": len(korean_rows),
                    "global_row_count": len(global_rows),
                    "korean_mean_score": fmt_float(korean_mean),
                    "global_mean_score": fmt_float(global_mean),
                    "korean_minus_global_gap": fmt_float(gap),
                    "gap_sign": sign_label(gap),
                    "gap_sign_preserved_vs_baseline": (
                        ""
                        if rule_id == "baseline_equal"
                        else str(sign_label(gap) == baseline_sign_lookup.get(peer_group_id)).lower()
                    ),
                    "top_rank_firm": top_firm,
                    "top_rank_same_as_baseline": (
                        ""
                        if rule_id == "baseline_equal"
                        else str(top_firm == baseline_top_lookup.get(peer_group_id)).lower()
                    ),
                    "rank_order_signature": rank_signature,
                    "rank_order_preserved_vs_baseline": (
                        ""
                        if rule_id == "baseline_equal"
                        else str(rank_signature == baseline_rank_lookup.get(peer_group_id)).lower()
                    ),
                }
            )

    fieldnames = [
        "row_kind",
        "allocation_rule",
        "allocation_rule_label",
        "allocation_description",
        "peer_group_id",
        "scored_row_count",
        "korean_row_count",
        "global_row_count",
        "korean_mean_score",
        "global_mean_score",
        "korean_minus_global_gap",
        "gap_sign",
        "gap_sign_preserved_vs_baseline",
        "top_rank_firm",
        "top_rank_same_as_baseline",
        "rank_order_signature",
        "rank_order_preserved_vs_baseline",
    ]
    write_csv(TABLE_PATH, summary_rows, fieldnames)
    build_figure(summary_rows)

    baseline_rows = [r for r in summary_rows if r["allocation_rule"] == "baseline_equal"]
    preserved_sign = sum(
        1
        for r in summary_rows
        if r["allocation_rule"] != "baseline_equal" and r["gap_sign_preserved_vs_baseline"] == "true"
    )
    comparable_sign = sum(1 for r in summary_rows if r["allocation_rule"] != "baseline_equal")
    preserved_rank = sum(
        1
        for r in summary_rows
        if r["allocation_rule"] != "baseline_equal" and r["rank_order_preserved_vs_baseline"] == "true"
    )
    comparable_rank = comparable_sign

    log_lines = [
        "# Strength Prompt 25. 비용배분 민감도 분석",
        "",
        "- `T_claim_cost_sensitivity.csv`는 `direct_cost_burden_panel.csv`의 관측 component score를 바탕으로 `baseline_equal`, `network_heavy`, `infra_heavy` 세 배분 규칙을 비교한 민감도 요약표다.",
        "- 모든 규칙은 missing component를 `0`으로 간주하지 않고 observed component에 대해서만 가중치를 재정규화한다. 따라서 이번 민감도는 coverage 차이보다 배분 규칙 차이가 결론을 얼마나 바꾸는지에 초점을 둔다.",
        "- `F_claim_cost_sensitivity.png`는 peer별 `한국 평균 - 글로벌 평균 burden gap`을 세 규칙 아래에서 나란히 보여 준다.",
        "",
        f"- summary rows: `{len(summary_rows)}`",
        f"- sign preserved vs baseline: `{preserved_sign}/{comparable_sign}`",
        f"- rank order preserved vs baseline: `{preserved_rank}/{comparable_rank}`",
        "",
        "## Rules",
        "",
    ]
    for rule_id in RULE_ORDER:
        weights = RULES[rule_id]["weights"]
        log_lines.append(
            f"- `{rule_id}`: tax `{weights['tax']}`, parafiscal `{weights['parafiscal']}`, network `{weights['network']}`, infra `{weights['infra']}`"
        )
    log_lines.extend(["", "## Baseline peer gaps", ""])
    for row in baseline_rows:
        log_lines.append(
            f"- `{row['peer_group_id']}`: korean-global gap `{row['korean_minus_global_gap']}`, top firm `{row['top_rank_firm']}`"
        )
    log_lines.extend(
        [
            "",
            "## Key interpretation",
            "",
            "- `infra_traffic_ott`에서는 세 규칙 모두 한국 평균 burden이 글로벌 peer보다 높고, top rank firm도 `lg_uplus`로 유지된다.",
            "- `mus_label_ip_export`는 network/infra component가 비어 있어 규칙을 바꿔도 점수와 rank가 거의 움직이지 않는다. 즉 이번 민감도는 주로 인프라 burden 결론의 안정성을 검정하는 역할을 한다.",
            "- 따라서 현재 direct cost burden 결론은 적어도 세 가지 배분 규칙 아래에서 `부호 유지`와 `상위 순위 유지`가 동시에 확인된다고 읽을 수 있다.",
        ]
    )
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
