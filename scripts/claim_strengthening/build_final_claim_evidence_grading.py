from __future__ import annotations

import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT / "data/processed/claim_strengthening/claim_statement_matrix.csv"
)
OUTPUT_PATH = (
    PROJECT_ROOT / "data/processed/claim_strengthening/final_claim_evidence_grading.csv"
)


GRADE_MAP = {
    "minimum_claim": {
        "evidence_grade": "B",
        "recommended_report_use": "allowed_with_explicit_scope_limit",
        "supporting_tables": (
            "outputs/tables/claim_strengthening/T_claim_peer_rank.csv|"
            "outputs/tables/claim_strengthening/T_claim_korea_vs_global_gap.csv|"
            "outputs/tables/claim_strengthening/T_claim_channel_decomposition.csv|"
            "outputs/tables/claim_strengthening/T_claim_balanced_panel_summary.csv"
        ),
        "supporting_figures": (
            "outputs/figures/claim_strengthening/F_claim_korea_vs_global_gap.png|"
            "outputs/figures/claim_strengthening/F_claim_channel_decomposition.png"
        ),
        "main_residual_risk": (
            "supportive direct gap이 streaming peer 한 축에 집중돼 있고 "
            "infra·music IP에서는 한국 평균이 더 높지 않아 일반화 범위가 제한된다"
        ),
        "grading_note": (
            "일부 comparable cell에서 반복 관측이 있다는 문장까지는 현재 증거로 방어 가능하지만 "
            "전면 일반화는 금물이다"
        ),
    },
    "base_claim": {
        "evidence_grade": "C",
        "recommended_report_use": "conditional_only_not_for_assertive_main_text",
        "supporting_tables": (
            "outputs/tables/claim_strengthening/T_claim_korea_vs_global_gap.csv|"
            "outputs/tables/claim_strengthening/T_claim_channel_decomposition.csv|"
            "outputs/tables/claim_strengthening/T_claim_cost_sensitivity.csv|"
            "outputs/tables/claim_strengthening/T_claim_balanced_panel_summary.csv|"
            "outputs/tables/claim_strengthening/T_claim_leave_one_country_out.csv|"
            "outputs/tables/claim_strengthening/T_claim_leave_one_peer_out.csv|"
            "outputs/tables/claim_strengthening/T_claim_alt_hypothesis_reduction.csv"
        ),
        "supporting_figures": (
            "outputs/figures/claim_strengthening/F_claim_korea_vs_global_gap.png|"
            "outputs/figures/claim_strengthening/F_claim_channel_decomposition.png|"
            "outputs/figures/claim_strengthening/F_claim_cost_sensitivity.png"
        ),
        "main_residual_risk": (
            "reg_narrow가 사실상 공백이고 leave-one-peer-out에서 spotify 제거 시 "
            "supportive peer가 0이 되어 평균적 구조부담 문장은 아직 불안정하다"
        ),
        "grading_note": (
            "조건부 문장이나 토론 파트에서는 쓸 수 있지만 현재 최종 결론의 단정적 핵심 문장으로 쓰기엔 이르다"
        ),
    },
    "strong_claim": {
        "evidence_grade": "D",
        "recommended_report_use": "do_not_use_as_assertive_conclusion",
        "supporting_tables": (
            "outputs/tables/claim_strengthening/T_claim_pretrend_check.csv|"
            "outputs/tables/claim_strengthening/T_claim_placebo_event_results.csv|"
            "outputs/tables/claim_strengthening/T_claim_placebo_outcome_results.csv|"
            "outputs/tables/claim_strengthening/T_claim_leave_one_country_out.csv|"
            "outputs/tables/claim_strengthening/T_claim_leave_one_peer_out.csv|"
            "outputs/tables/claim_strengthening/T_claim_alt_hypothesis_reduction.csv"
        ),
        "supporting_figures": (
            "outputs/figures/claim_strengthening/F_claim_placebo_event_plot.png"
        ),
        "main_residual_risk": (
            "placebo와 pretrend에서 식별 취약성이 드러났고 9개 대체 설명 전부가 "
            "여전히 결론을 약화시킬 수 있어 strong claim은 현재 과장이다"
        ),
        "grading_note": (
            "현재 결과는 strong claim을 강화하기보다 보류해야 한다는 판단 근거를 제공한다"
        ),
    },
}


def read_rows() -> list[dict[str, str]]:
    with INPUT_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def build_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in read_rows():
        meta = GRADE_MAP[row["claim_level"]]
        rows.append(
            {
                "claim_level": row["claim_level"],
                "claim_sentence": row["claim_sentence_ko"],
                "evidence_grade": meta["evidence_grade"],
                "recommended_report_use": meta["recommended_report_use"],
                "supporting_tables": meta["supporting_tables"],
                "supporting_figures": meta["supporting_figures"],
                "main_residual_risk": meta["main_residual_risk"],
                "grading_note": meta["grading_note"],
                "current_support_status": row["current_support_status"],
            }
        )
    return rows


def write_rows(rows: list[dict[str, str]]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "claim_level",
        "claim_sentence",
        "evidence_grade",
        "recommended_report_use",
        "supporting_tables",
        "supporting_figures",
        "main_residual_risk",
        "grading_note",
        "current_support_status",
    ]
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    write_rows(build_rows())


if __name__ == "__main__":
    main()
