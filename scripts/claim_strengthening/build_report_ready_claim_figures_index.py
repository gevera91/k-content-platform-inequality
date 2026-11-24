from __future__ import annotations

import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

OUTPUT_PATH = (
    PROJECT_ROOT
    / "outputs/figures/claim_strengthening/report_ready_claim_figures_index.csv"
)


FIGURE_ROWS = [
    {
        "claim_figure_id": "CF01",
        "source_file": "outputs/figures/claim_strengthening/F_claim_korea_vs_global_gap.png",
        "selection_status": "include_core",
        "recommended_section": "결론 강화 / 핵심 비교",
        "planned_title_kr": "한국 vs 글로벌 peer 평균 격차 도표",
        "tex_label_proposal": "fig:claim_gap_main",
        "insertion_order": "1",
        "why_selected": "현재 strongest defensible sentence를 가장 직관적으로 보여 주는 핵심 그림이다.",
        "key_message": "streaming은 한국 평균이 높고 infra와 music IP는 반대 방향이라는 현재 핵심 분포를 바로 보여 준다.",
        "caution_if_used": "surviving core peer 기준 결과라는 범위를 반드시 함께 적어야 한다.",
    },
    {
        "claim_figure_id": "CF02",
        "source_file": "outputs/figures/claim_strengthening/F_claim_channel_decomposition.png",
        "selection_status": "include_core",
        "recommended_section": "결론 강화 / 채널 분해",
        "planned_title_kr": "한국-글로벌 격차의 채널별 기여분 분해도",
        "tex_label_proposal": "fig:claim_channel_decomp",
        "insertion_order": "2",
        "why_selected": "gap을 risk와 market 채널로 분해해 왜 방향이 갈리는지 시각적으로 설명해 준다.",
        "key_message": "infra는 주로 risk 채널, music IP는 주로 market 채널 차이로 읽힌다.",
        "caution_if_used": "reg 채널 공백을 숨기지 말고 같이 밝혀야 한다.",
    },
    {
        "claim_figure_id": "CF03",
        "source_file": "outputs/figures/claim_strengthening/F_claim_cost_sensitivity.png",
        "selection_status": "include_support",
        "recommended_section": "결론 강화 / 강건성",
        "planned_title_kr": "비용배분 규칙 민감도 도표",
        "tex_label_proposal": "fig:claim_cost_sensitivity",
        "insertion_order": "3",
        "why_selected": "인프라 비용 부담 방향이 비용배분 규칙 변화에도 크게 흔들리지 않는다는 점을 보여 준다.",
        "key_message": "infra burden gap의 부호와 상위 순위는 세 규칙에서 유지된다.",
        "caution_if_used": "music coverage가 얇다는 점을 그림 캡션에 명시해야 한다.",
    },
    {
        "claim_figure_id": "CF04",
        "source_file": "outputs/figures/claim_strengthening/F_claim_placebo_event_plot.png",
        "selection_status": "include_support",
        "recommended_section": "결론 강화 / 한계와 검증",
        "planned_title_kr": "placebo vs actual 사건연구 비교도",
        "tex_label_proposal": "fig:claim_placebo_event",
        "insertion_order": "4",
        "why_selected": "현재 사건축이 강화 근거라기보다 식별 취약성 점검 결과라는 점을 가장 잘 보여 준다.",
        "key_message": "webtoon placebo가 actual pretrend failure를 거의 재현한다.",
        "caution_if_used": "강화 증거 그림이 아니라 한계·falsification 그림으로 설명해야 한다.",
    },
    {
        "claim_figure_id": "CF05",
        "source_file": "outputs/figures/claim_strengthening/F_claim_concentration_decomposition.png",
        "selection_status": "include_appendix",
        "recommended_section": "부록 / 시장구조 참고",
        "planned_title_kr": "로컬 vs 글로벌 집중도 분해도",
        "tex_label_proposal": "fig:claim_concentration_decomp",
        "insertion_order": "5",
        "why_selected": "music proxy market에서 local/global concentration component를 상세히 보여 줘 market 축 해석을 보완한다.",
        "key_message": "현재 직접 분해가 가능한 한국 music proxy market에서는 로컬 상위사 집중이 더 크게 잡힌다.",
        "caution_if_used": "exact same-service market share가 아니라 KR music chart proxy market이라는 점을 분명히 해야 한다.",
    },
    {
        "claim_figure_id": "CF06",
        "source_file": "outputs/figures/claim_strengthening/F_claim_reg_lag_timeline.png",
        "selection_status": "exclude_for_now",
        "recommended_section": "보류",
        "planned_title_kr": "규제 시차 타임라인",
        "tex_label_proposal": "fig:claim_reg_lag_timeline",
        "insertion_order": "",
        "why_selected": "후보 그림으로는 중요하지만 현재 numeric lag rows가 0이라 신뢰 가능한 시각화로 만들 근거가 부족하다.",
        "key_message": "service-matched 규제 시차는 아직 수치로 그릴 만큼 직접 날짜 증거가 부족하다.",
        "caution_if_used": "현 단계에서 넣으면 규제축 공백만 부각되고 결론 강화에는 도움이 되지 않는다.",
    },
]


def build_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in FIGURE_ROWS:
        path = PROJECT_ROOT / row["source_file"]
        enriched = dict(row)
        enriched["source_exists"] = "yes" if path.exists() else "no"
        rows.append(enriched)
    return rows


def write_rows(rows: list[dict[str, str]]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "claim_figure_id",
        "source_file",
        "source_exists",
        "selection_status",
        "recommended_section",
        "planned_title_kr",
        "tex_label_proposal",
        "insertion_order",
        "why_selected",
        "key_message",
        "caution_if_used",
    ]
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    write_rows(build_rows())


if __name__ == "__main__":
    main()
