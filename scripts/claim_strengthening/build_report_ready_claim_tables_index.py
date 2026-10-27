from __future__ import annotations

import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

OUTPUT_PATH = (
    PROJECT_ROOT
    / "outputs/tables/claim_strengthening/report_ready_claim_tables_index.csv"
)


TABLE_ROWS = [
    {
        "claim_table_id": "CT01",
        "source_file": "outputs/tables/claim_strengthening/T_claim_korea_vs_global_gap.csv",
        "selection_status": "include_core",
        "recommended_section": "결론 강화 / 핵심 비교",
        "planned_title_kr": "한국 vs 글로벌 peer 평균 격차표",
        "tex_label_proposal": "tab:claim_gap_main",
        "insertion_order": "1",
        "why_selected": "현재 강화 결론에서 가장 직접적으로 한국 평균과 글로벌 평균의 방향을 보여 주는 핵심 표다.",
        "key_message": "streaming만 한국 평균이 높고 infra와 music IP는 반대 방향이라는 점을 한눈에 보여 준다.",
        "caution_if_used": "전면 일반화 대신 surviving core peer 기준 비교라는 범위 제한을 반드시 붙여야 한다.",
    },
    {
        "claim_table_id": "CT02",
        "source_file": "outputs/tables/claim_strengthening/T_claim_channel_decomposition.csv",
        "selection_status": "include_core",
        "recommended_section": "결론 강화 / 채널 분해",
        "planned_title_kr": "한국-글로벌 격차의 채널별 기여분 분해표",
        "tex_label_proposal": "tab:claim_channel_decomp",
        "insertion_order": "2",
        "why_selected": "결론을 단순 점수 차이가 아니라 risk와 market 채널 기여분으로 설명하게 해 준다.",
        "key_message": "infra는 주로 risk, music IP는 주로 market 채널에서 차이가 난다는 점을 정리한다.",
        "caution_if_used": "reg 채널은 현재 usable data가 거의 없으므로 규제 역차별의 직접 증거처럼 쓰면 안 된다.",
    },
    {
        "claim_table_id": "CT03",
        "source_file": "outputs/tables/claim_strengthening/T_claim_balanced_panel_summary.csv",
        "selection_status": "include_core",
        "recommended_section": "결론 강화 / 강건성",
        "planned_title_kr": "공통기간 balanced panel 재계산 요약표",
        "tex_label_proposal": "tab:claim_balanced_summary",
        "insertion_order": "3",
        "why_selected": "공통기간 필터를 걸어도 현재 핵심 gap 방향이 유지된다는 점을 간단히 보여 준다.",
        "key_message": "balanced panel을 적용해도 현재 세 peer의 gap 방향은 뒤집히지 않는다.",
        "caution_if_used": "balanced panel 자체가 이미 좁은 core sample이라는 점을 함께 적어야 한다.",
    },
    {
        "claim_table_id": "CT04",
        "source_file": "outputs/tables/claim_strengthening/T_claim_cost_sensitivity.csv",
        "selection_status": "include_support",
        "recommended_section": "결론 강화 / 강건성",
        "planned_title_kr": "비용배분 규칙 민감도 요약표",
        "tex_label_proposal": "tab:claim_cost_sensitivity",
        "insertion_order": "4",
        "why_selected": "인프라 비용 부담 방향이 배분 규칙 변화에 쉽게 뒤집히지 않는다는 강건성 근거를 준다.",
        "key_message": "infra burden gap의 부호와 상위 순위가 배분 규칙 세 가지에서 유지된다.",
        "caution_if_used": "music 쪽 coverage는 얇으므로 전체 산업 일반론으로 확장하면 안 된다.",
    },
    {
        "claim_table_id": "CT05",
        "source_file": "outputs/tables/claim_strengthening/T_claim_placebo_event_results.csv",
        "selection_status": "include_support",
        "recommended_section": "결론 강화 / 한계와 검증",
        "planned_title_kr": "placebo 사건연구와 actual 사건연구 비교표",
        "tex_label_proposal": "tab:claim_placebo_event",
        "insertion_order": "5",
        "why_selected": "현재 사건축의 식별 취약성을 독자에게 숨기지 않고 직접 보여 주는 핵심 falsification 표다.",
        "key_message": "webtoon placebo가 actual pretrend failure를 거의 재현해 사건축을 강한 근거로 쓰기 어렵다는 점을 보여 준다.",
        "caution_if_used": "강화 근거라기보다 제한·식별 취약성 표로 설명해야 한다.",
    },
    {
        "claim_table_id": "CT06",
        "source_file": "outputs/tables/claim_strengthening/T_claim_alt_hypothesis_reduction.csv",
        "selection_status": "include_support",
        "recommended_section": "결론 강화 / 반대 가설 점검",
        "planned_title_kr": "대체 설명 제거 현황표",
        "tex_label_proposal": "tab:claim_alt_reduction",
        "insertion_order": "6",
        "why_selected": "무엇이 줄었고 무엇이 아직 남았는지 한 장으로 정리해 과장된 결론을 막아 준다.",
        "key_message": "제품 범위 차이는 많이 줄었지만 품질·브랜드·공시·측정오차 가설은 여전히 강하게 남아 있다.",
        "caution_if_used": "현재 `can_still_weaken_claim=yes`가 9/9라는 점을 축소하면 안 된다.",
    },
    {
        "claim_table_id": "CT07",
        "source_file": "outputs/tables/claim_strengthening/T_claim_peer_rank.csv",
        "selection_status": "include_appendix",
        "recommended_section": "부록 / peer 상세 비교",
        "planned_title_kr": "peer 내부 순위 상세표",
        "tex_label_proposal": "tab:claim_peer_rank",
        "insertion_order": "7",
        "why_selected": "각 peer 내부에서 한국 firm이 몇 위인지 상세하게 보여 주어 본문 gap 표의 해석을 보완한다.",
        "key_message": "kt, dreamus, jyp_ent 등 best Korean firm의 위치와 global benchmark 거리 차이를 직접 제시한다.",
        "caution_if_used": "fallback mean을 쓴 firm이 있어 본문 핵심 표보다는 부록이 적절하다.",
    },
    {
        "claim_table_id": "CT08",
        "source_file": "outputs/tables/claim_strengthening/T_claim_leave_one_peer_out.csv",
        "selection_status": "include_appendix",
        "recommended_section": "부록 / 민감도 분석",
        "planned_title_kr": "글로벌 peer 제외 민감도 표",
        "tex_label_proposal": "tab:claim_leave_one_peer",
        "insertion_order": "8",
        "why_selected": "spotify 제거 시 supportive peer가 사라지는 현재 취약성을 투명하게 보여 주는 핵심 민감도 표다.",
        "key_message": "netflix·warner_music 제거는 방향 유지지만 spotify 제거 시 positive-gap peer가 0이 된다.",
        "caution_if_used": "결론 강화 표가 아니라 결론 범위 제한 표라는 점을 분명히 해야 한다.",
    },
    {
        "claim_table_id": "CT09",
        "source_file": "outputs/tables/claim_strengthening/T_claim_reg_lag_summary.csv",
        "selection_status": "exclude_for_now",
        "recommended_section": "보류",
        "planned_title_kr": "규제 시차 요약표",
        "tex_label_proposal": "tab:claim_reg_lag",
        "insertion_order": "",
        "why_selected": "후보 표로는 중요하지만 현재 numeric lag rows가 0이라 강화용 본문 표로는 정보력이 약하다.",
        "key_message": "직접 규제 시차 비교는 아직 service-matched 날짜 증거 부족으로 수치화되지 않는다.",
        "caution_if_used": "현 단계에서 넣으면 규제 축 공백만 더 크게 부각될 수 있다.",
    },
    {
        "claim_table_id": "CT10",
        "source_file": "outputs/tables/claim_strengthening/T_claim_placebo_outcome_results.csv",
        "selection_status": "exclude_for_now",
        "recommended_section": "보류",
        "planned_title_kr": "무관한 결과변수 placebo 표",
        "tex_label_proposal": "tab:claim_placebo_outcome",
        "insertion_order": "",
        "why_selected": "방법론 검증에는 유용하지만 현재는 placebo event 표와 alt-hypothesis 표로도 한계 설명이 가능해 중복성이 높다.",
        "key_message": "무관한 outcome에서도 event-time 반응이 나타나 현재 식별이 취약함을 보여 준다.",
        "caution_if_used": "결론 강화 섹션을 지나치게 방어적이고 장황하게 만들 수 있다.",
    },
]


def build_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in TABLE_ROWS:
        source_path = PROJECT_ROOT / row["source_file"]
        enriched = dict(row)
        enriched["source_exists"] = "yes" if source_path.exists() else "no"
        rows.append(enriched)
    return rows


def write_rows(rows: list[dict[str, str]]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "claim_table_id",
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
