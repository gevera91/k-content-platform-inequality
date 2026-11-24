from __future__ import annotations

import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT / "data/processed/claim_strengthening/alternative_hypothesis_registry.csv"
)
OUTPUT_PATH = (
    PROJECT_ROOT / "outputs/tables/claim_strengthening/T_claim_alt_hypothesis_reduction.csv"
)


REDUCTION_MAP = {
    "ALT01": {
        "test_used": (
            "direct_cost_burden_panel|matched_effective_tax_rate_panel|"
            "funding_cost_matched_panel|leave_one_peer_out"
        ),
        "status": "partially_reduced",
        "residual_risk": "high",
        "can_still_weaken_claim": "yes",
        "evidence_summary": (
            "직접 비용·조달비용을 matched ratio로 다시 계산했지만 "
            "명시적 size-normalization table은 없고 supportive peer가 streaming 한 축에 치우쳐 있다."
        ),
        "linked_outputs": (
            "data/processed/claim_strengthening/direct_cost_burden_panel.csv|"
            "data/processed/claim_strengthening/funding_cost_matched_panel.csv|"
            "outputs/tables/claim_strengthening/T_claim_leave_one_peer_out.csv"
        ),
    },
    "ALT02": {
        "test_used": (
            "service_equivalence_rules|switching_cost_narrow_panel|"
            "placebo_outcome_test"
        ),
        "status": "still_open",
        "residual_risk": "high",
        "can_still_weaken_claim": "yes",
        "evidence_summary": (
            "서비스 동등성 규칙은 세웠지만 직접 품질 proxy table은 없고, "
            "웹툰 placebo outcome에서도 무관한 결과변수 반응이 남아 품질 차이를 분리하지 못했다."
        ),
        "linked_outputs": (
            "data/registry/claim_strengthening/service_equivalence_rules.csv|"
            "data/processed/claim_strengthening/switching_cost_narrow_panel.csv|"
            "outputs/tables/claim_strengthening/T_claim_placebo_outcome_results.csv"
        ),
    },
    "ALT03": {
        "test_used": (
            "cross_market_transfer_panel|switching_cost_narrow_panel|"
            "placebo_event_comparison|pretrend_recheck"
        ),
        "status": "still_open",
        "residual_risk": "high",
        "can_still_weaken_claim": "yes",
        "evidence_summary": (
            "전이와 switching evidence는 일부 있지만 transfer gap은 한국 불리 방향으로 일관되지 않고, "
            "event study는 placebo와 pretrend 재점검에서 방어되지 않았다."
        ),
        "linked_outputs": (
            "data/processed/claim_strengthening/cross_market_transfer_matched_panel.csv|"
            "data/processed/claim_strengthening/switching_cost_narrow_panel.csv|"
            "outputs/tables/claim_strengthening/T_claim_placebo_event_results.csv|"
            "outputs/tables/claim_strengthening/T_claim_pretrend_check.csv"
        ),
    },
    "ALT04": {
        "test_used": (
            "common_period_audit|balanced_panel|pretrend_recheck|"
            "leave_one_country_out"
        ),
        "status": "partially_reduced",
        "residual_risk": "medium",
        "can_still_weaken_claim": "yes",
        "evidence_summary": (
            "공통기간·balanced panel·country leave-one-out으로 level compare의 시차 문제는 일부 줄었지만, "
            "event-study 사전추세 실패가 남아 timing 가설은 완전히 제거되지 않았다."
        ),
        "linked_outputs": (
            "data/processed/claim_strengthening/common_period_audit_matched.csv|"
            "data/processed/claim_strengthening/reverse_discrimination_balanced_panel.csv|"
            "outputs/tables/claim_strengthening/T_claim_pretrend_check.csv|"
            "outputs/tables/claim_strengthening/T_claim_leave_one_country_out.csv"
        ),
    },
    "ALT05": {
        "test_used": (
            "comparable_country_filter|balanced_panel|leave_one_country_out"
        ),
        "status": "partially_reduced",
        "residual_risk": "medium",
        "can_still_weaken_claim": "yes",
        "evidence_summary": (
            "비교 가능한 국가 셀만 남기고 country leave-one-out까지 확인했지만, "
            "한국 전용 셀에 의존하는 infra와 streaming이 남아 거시환경 차이를 완전히 배제하진 못했다."
        ),
        "linked_outputs": (
            "data/processed/claim_strengthening/comparable_country_cell_filter.csv|"
            "outputs/tables/claim_strengthening/T_claim_balanced_panel_summary.csv|"
            "outputs/tables/claim_strengthening/T_claim_leave_one_country_out.csv"
        ),
    },
    "ALT06": {
        "test_used": (
            "matched_filing_metrics|cashflow_pressure_panel|"
            "funding_cost_panel"
        ),
        "status": "still_open",
        "residual_risk": "high",
        "can_still_weaken_claim": "yes",
        "evidence_summary": (
            "공시 기반 직접 지표를 늘렸지만 listed-only subsample이나 filing-independent table이 아직 없고, "
            "kakao_ent 부재처럼 공시 가용성 비대칭이 일부 peer에서 그대로 남아 있다."
        ),
        "linked_outputs": (
            "data/processed/claim_strengthening/matched_effective_tax_rate_panel.csv|"
            "data/processed/claim_strengthening/funding_cost_matched_panel.csv|"
            "data/processed/claim_strengthening/cashflow_recovery_pressure_panel.csv"
        ),
    },
    "ALT07": {
        "test_used": (
            "service_equivalence_rules|matched_peer_registry|"
            "comparable_country_filter|core_sample_redesign"
        ),
        "status": "substantially_reduced",
        "residual_risk": "medium",
        "can_still_weaken_claim": "yes",
        "evidence_summary": (
            "서비스 동등성 규칙과 core sample 재설계로 scope mismatch를 크게 줄였지만, "
            "infra는 adjacent burden peer이고 webtoon direct core는 비어 있어 완전 소거는 아니다."
        ),
        "linked_outputs": (
            "data/registry/claim_strengthening/service_equivalence_rules.csv|"
            "data/processed/claim_strengthening/matched_peer_registry.csv|"
            "data/processed/claim_strengthening/comparable_country_cell_filter.csv|"
            "data/registry/claim_strengthening/reverse_discrimination_core_sample_v1.csv"
        ),
    },
    "ALT08": {
        "test_used": (
            "matched_peer_registry|comparable_country_filter|"
            "core_sample_exclusion_log|leave_one_peer_out"
        ),
        "status": "partially_reduced",
        "residual_risk": "medium",
        "can_still_weaken_claim": "yes",
        "evidence_summary": (
            "peer 묶음을 보수적으로 다시 설계했지만 leave-one-peer-out에서 "
            "spotify를 빼면 supportive peer가 0이 되어 매칭 민감성이 여전히 남아 있다."
        ),
        "linked_outputs": (
            "data/processed/claim_strengthening/matched_peer_registry.csv|"
            "data/processed/claim_strengthening/core_sample_exclusion_log.csv|"
            "outputs/tables/claim_strengthening/T_claim_leave_one_peer_out.csv"
        ),
    },
    "ALT09": {
        "test_used": (
            "direct_only_matched_panels|i_reg_narrow_check|"
            "placebo_outcome_test|leave_one_country_out"
        ),
        "status": "still_open",
        "residual_risk": "high",
        "can_still_weaken_claim": "yes",
        "evidence_summary": (
            "직접 matched panel을 많이 만들었지만 reg_narrow는 여전히 공백이고, "
            "thin direct panel·fallback 평균·placebo outcome 반응이 남아 측정오차 가설이 계속 중요하다."
        ),
        "linked_outputs": (
            "data/processed/claim_strengthening/i_reg_narrow_panel.csv|"
            "data/processed/claim_strengthening/direct_cost_burden_panel.csv|"
            "outputs/tables/claim_strengthening/T_claim_placebo_outcome_results.csv|"
            "outputs/tables/claim_strengthening/T_claim_leave_one_country_out.csv"
        ),
    },
}


def read_rows() -> list[dict[str, str]]:
    with INPUT_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def build_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in read_rows():
        meta = REDUCTION_MAP[row["alt_id"]]
        rows.append(
            {
                "alt_id": row["alt_id"],
                "alternative_hypothesis": row["alternative_hypothesis"],
                "priority": row["priority"],
                "current_relevance": row["current_relevance"],
                "test_used": meta["test_used"],
                "status": meta["status"],
                "residual_risk": meta["residual_risk"],
                "can_still_weaken_claim": meta["can_still_weaken_claim"],
                "evidence_summary": meta["evidence_summary"],
                "linked_outputs": meta["linked_outputs"],
            }
        )
    rows.sort(key=lambda item: item["alt_id"])
    return rows


def write_rows(rows: list[dict[str, str]]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "alt_id",
        "alternative_hypothesis",
        "priority",
        "current_relevance",
        "test_used",
        "status",
        "residual_risk",
        "can_still_weaken_claim",
        "evidence_summary",
        "linked_outputs",
    ]
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    write_rows(build_rows())


if __name__ == "__main__":
    main()
