#!/usr/bin/env python3
"""Rules-based Korean explanations for CPII pair-gap results."""

from __future__ import annotations

from typing import Any, Mapping


DISCLAIMER_KO = (
    "이 결과는 동결 기준분포에 대한 feature별 상대위치를 합성한 연구용 베타 지표이며, "
    "차별·위법성·손해·인과효과를 판정하거나 기업 백분위를 뜻하지 않습니다."
)


def _signed(value: float, *, decimals: int = 2) -> str:
    """Format a signed number without rounding a real non-zero value to zero."""

    if value != 0.0 and round(value, decimals) == 0.0:
        for places in range(decimals + 1, 9):
            if round(value, places) != 0.0:
                return f"{value:+.{places}f}"
        return f"{value:+.6e}"
    return f"{value:+.{decimals}f}"


def _absolute(value: float, *, decimals: int = 2) -> str:
    if value != 0.0 and round(abs(value), decimals) == 0.0:
        for places in range(decimals + 1, 9):
            if round(abs(value), places) != 0.0:
                return f"{abs(value):.{places}f}"
        return f"{abs(value):.6e}"
    return f"{abs(value):.{decimals}f}"


def explain_point_gap(delta_points: float) -> str:
    weighted_position = delta_points / 100.0
    return (
        f"ΔCPII {_signed(delta_points)}점은 각 feature의 기준분포상 위치 차이를 정해진 가중치로 합산한 값이 "
        f"{_signed(weighted_position, decimals=4)}라는 뜻입니다. 이는 비용·매출의 {_absolute(delta_points)}%나 기업 백분위 차이가 아닙니다. "
        "다른 9개 feature가 같다는 가정 아래 0.10점은 규제/시장 feature 하나에서는 약 0.9%p, "
        "위험 feature 하나에서는 약 1.2%p의 feature별 기준분포 위치 차이에 해당하지만, 실제로는 큰 양·음 기여도가 상쇄된 결과일 수도 있습니다."
    )


def build_pair_narrative(
    pair: Mapping[str, Any],
    decomposition: Mapping[str, Any],
    sensitivity: Mapping[str, Any],
    economic: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    delta = float(pair["delta_cpii_points_a_minus_b"])
    direction = "A의 구조적 부담 위치가 B보다 높습니다" if delta > 0 else "A의 구조적 부담 위치가 B보다 낮습니다" if delta < 0 else "두 회사의 구조적 부담 위치가 같습니다"
    nonzero_drivers = [
        row for row in decomposition["features"]
        if abs(float(row["cpii_point_contribution"])) > 1e-12
    ]
    drivers = sorted(
        nonzero_drivers,
        key=lambda row: (-abs(float(row["cpii_point_contribution"])), row["variable_name"]),
    )[:3]
    if drivers:
        driver_text = "절대 기여도 상위 driver는 " + ", ".join(
            f"{row['display_name_ko']} {_signed(float(row['cpii_point_contribution']))}점"
            for row in drivers
        ) + "입니다."
    else:
        driver_text = "관측된 feature 수준의 CPII 기여도 차이가 없어 상위 driver를 선정하지 않습니다."
    if sensitivity["interpretation_status"] == "difference_unclear":
        uncertainty = (
            f"테스트한 사양·입력 범위가 {_signed(float(sensitivity['sensitivity_min_points']))}~"
            f"{_signed(float(sensitivity['sensitivity_max_points']))}점이고 0을 포함하거나 부호가 바뀌어 차이는 불명확합니다."
        )
    else:
        uncertainty = (
            f"테스트한 사양·입력 범위가 {_signed(float(sensitivity['sensitivity_min_points']))}~"
            f"{_signed(float(sensitivity['sensitivity_max_points']))}점으로 방향이 유지됩니다. 이 범위는 신뢰구간이 아닙니다."
        )
    money_text = "경제 노출액이 없어 금액 해석은 비활성화됩니다."
    if economic:
        available = [row for row in economic["rows"] if row["availability"] == "available"]
        if available:
            examples = ", ".join(
                f"{row['display_name_ko']} {float(row['common_size_amount_base']):+,.0f} {row['currency']}"
                for row in available[:3]
            )
            money_text = (
                f"공통규모 기준 채널별 상당액 예시는 {examples}입니다. "
                "중복·시나리오 채널이 섞여 있어 총액으로 합산하지 않습니다."
            )
    headline = f"ΔCPII(A-B)={_signed(delta)}점: {direction}."
    return {
        "headline_ko": headline,
        "scale_explanation_ko": explain_point_gap(delta),
        "drivers_ko": driver_text,
        "economic_interpretation_ko": money_text,
        "sensitivity_ko": uncertainty,
        "disclaimer_ko": DISCLAIMER_KO,
        "full_narrative_ko": " ".join(
            [headline, explain_point_gap(delta), driver_text, money_text, uncertainty, DISCLAIMER_KO]
        ),
    }
