#!/usr/bin/env python3
"""Build the deterministic LaTeX appendix for the CPII company comparator."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cpii_simulator"
    / "examples"
    / "fictional_companies.csv"
)
EXAMPLE_DIR = PROJECT_ROOT / "outputs" / "tables" / "cpii_simulator" / "examples"
ANCHOR_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cpii_simulator"
    / "anchor"
    / "POOL_SCQ_P01_P99_EMP_RANK_V1.json"
)
OUTPUT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "tables"
    / "cpii_simulator"
    / "appendix"
    / "cpii_interpretation_appendix.tex"
)

SOURCE_PATHS = (
    INPUT_PATH,
    EXAMPLE_DIR / "company_ranking.csv",
    EXAMPLE_DIR / "pair_gap_matrix.csv",
    EXAMPLE_DIR / "pair_gaps.csv",
    EXAMPLE_DIR / "pair_contributions.csv",
    EXAMPLE_DIR / "economic_interpretations.csv",
    EXAMPLE_DIR / "golden_equal_gap_summary.csv",
    EXAMPLE_DIR / "sensitivity_summary.csv",
    ANCHOR_PATH,
)

AXIS_ORDER = ("I_reg", "I_risk", "I_market")
PAIR_ID = "SYN-A__vs__SYN-B"
MONEY_SCALE_KRW = 100_000_000.0

_LATEX_ESCAPES = str.maketrans(
    {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
)


def latex_escape(value: Any) -> str:
    """Escape data-originated text before including it in LaTeX."""

    return str(value).translate(_LATEX_ESCAPES)


def tex_code(value: Any) -> str:
    return r"\texttt{" + latex_escape(value) + "}"


def tex_code_breakable(value: Any) -> str:
    """Render machine labels in monospace while allowing breaks after underscores."""

    escaped = latex_escape(value).replace(r"\_", r"\_\allowbreak{}")
    return r"\texttt{" + escaped + "}"


def wrap_cell(*parts: str) -> str:
    return r"\WrapCell{" + r"\\".join(parts) + "}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"missing CSV header: {path.relative_to(PROJECT_ROOT)}")
        return list(reader.fieldnames), list(reader)


def require_fields(label: str, fields: Sequence[str], required: Iterable[str]) -> None:
    missing = sorted(set(required) - set(fields))
    if missing:
        raise ValueError(f"{label} is missing fields: {', '.join(missing)}")


def finite_float(row: Mapping[str, str], field: str, context: str) -> float:
    text = row.get(field, "").strip()
    if not text:
        raise ValueError(f"{context}: blank numeric field {field}")
    try:
        value = float(text)
    except ValueError as exc:
        raise ValueError(f"{context}: invalid numeric field {field}={text!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"{context}: non-finite numeric field {field}")
    return value


def one_row(rows: Sequence[Mapping[str, str]], context: str, **criteria: str) -> Mapping[str, str]:
    matches = [row for row in rows if all(row.get(key) == value for key, value in criteria.items())]
    if len(matches) != 1:
        rendered = ", ".join(f"{key}={value!r}" for key, value in criteria.items())
        raise ValueError(f"{context}: expected one row for {rendered}, got {len(matches)}")
    return matches[0]


def fmt_decimal(value: float, places: int = 2, *, signed: bool = False) -> str:
    if abs(value) < 0.5 * 10 ** (-places):
        value = 0.0
    pattern = f"{'+' if signed else ''},.{places}f"
    return format(value, pattern)


def fmt_points(value: float, places: int = 2) -> str:
    return fmt_decimal(value, places, signed=True)


def fmt_percent(value: float, places: int = 2) -> str:
    return fmt_decimal(value * 100.0, places) + r"\%"


def fmt_raw(value: float, unit: str) -> str:
    if unit in {"decimal_ratio", "index_0_1"}:
        return fmt_decimal(value, 4)
    if unit == "multiple":
        return fmt_decimal(value, 2)
    return format(value, ".6g")


def fmt_money_100m(value: float, *, signed: bool = True) -> str:
    return fmt_decimal(value / MONEY_SCALE_KRW, 2, signed=signed)


def axis_tex(axis: str) -> str:
    mapping = {
        "I_reg": r"$I_{\mathrm{reg}}$",
        "I_risk": r"$I_{\mathrm{risk}}$",
        "I_market": r"$I_{\mathrm{market}}$",
    }
    try:
        return mapping[axis]
    except KeyError as exc:
        raise ValueError(f"unexpected active axis: {axis}") from exc


def unit_label(unit: str) -> str:
    mapping = {
        "decimal_ratio": "소수비율",
        "multiple": "배수",
        "index_0_1": "0--1 지수",
    }
    return mapping.get(unit, unit)


def economic_class_label(value: str) -> str:
    mapping = {
        "conditional_accounting_equivalent": "조건부 회계 상당액",
        "conditional_performance_equivalent": "조건부 성과 상당액",
        "scenario_only": "가정 기반 시나리오",
        "non_monetizable": "화폐환산 불가",
    }
    return mapping.get(value, value)


def economic_base_label(value: str) -> str:
    mapping = {
        "positive_pretax_income": "양(+) 세전이익",
        "average_interest_bearing_debt": "평균 이자부부채",
        "content_investment": "콘텐츠투자액",
        "eligible_market_revenue": "대상시장 매출",
        "revenue": "매출",
        "none": "적용 없음",
    }
    return mapping.get(value, value)


def overlap_label(value: str) -> str:
    mapping = {
        "tax_burden": "조세부담",
        "recovery": "회수성",
        "network_infrastructure": "네트워크·인프라",
        "financing_ip": "자금·IP",
        "market_transfer": "시장전이",
    }
    return mapping.get(value, value)


def sensitivity_label(value: str) -> str:
    mapping = {
        "difference_unclear": "차이 불명확",
        "direction_stable_across_tested_specifications": "시험 사양 내 방향 유지",
    }
    return mapping.get(value, value)


def add_longtable_header(
    lines: list[str],
    column_spec: str,
    caption: str,
    label: str,
    header_cells: Sequence[str],
) -> None:
    header = " & ".join(header_cells) + r" \\"
    lines.extend(
        [
            r"\begin{longtable}{" + column_spec + "}",
            r"\caption{" + caption + r"}\label{" + label + r"}\\",
            r"\toprule",
            header,
            r"\midrule",
            r"\endfirsthead",
            r"\toprule",
            header,
            r"\midrule",
            r"\endhead",
        ]
    )


def load_sources() -> dict[str, Any]:
    company_fields, companies = read_csv(INPUT_PATH)
    ranking_fields, ranking = read_csv(EXAMPLE_DIR / "company_ranking.csv")
    matrix_fields, matrix = read_csv(EXAMPLE_DIR / "pair_gap_matrix.csv")
    pair_fields, pairs = read_csv(EXAMPLE_DIR / "pair_gaps.csv")
    contribution_fields, contributions = read_csv(EXAMPLE_DIR / "pair_contributions.csv")
    economic_fields, economic = read_csv(EXAMPLE_DIR / "economic_interpretations.csv")
    golden_fields, golden = read_csv(EXAMPLE_DIR / "golden_equal_gap_summary.csv")
    sensitivity_fields, sensitivity = read_csv(EXAMPLE_DIR / "sensitivity_summary.csv")
    anchor = json.loads(ANCHOR_PATH.read_text(encoding="utf-8"))

    require_fields(
        "fictional_companies.csv",
        company_fields,
        (
            "observation_id",
            "company_name",
            "company_group",
            "synthetic_flag",
            "source_note",
        ),
    )
    require_fields(
        "company_ranking.csv",
        ranking_fields,
        (
            "observation_id",
            "company_name",
            "company_group",
            "CPII",
            "I_reg",
            "I_risk",
            "I_market",
            "active_feature_count",
            "observed_feature_count",
            "burden_rank_desc",
            "release_status",
            "anchor_version",
            "method_version",
            "synthetic_flag",
        ),
    )
    require_fields("pair_gap_matrix.csv", matrix_fields, ("observation_id",))
    require_fields(
        "pair_gaps.csv",
        pair_fields,
        (
            "pair_id",
            "observation_id_a",
            "observation_id_b",
            "delta_cpii_points_a_minus_b",
            "comparable",
            "pair_eligible",
            "interpretation_gate",
            "legal_causal_disclaimer",
        ),
    )
    require_fields(
        "pair_contributions.csv",
        contribution_fields,
        (
            "pair_id",
            "subindex",
            "variable_name",
            "display_name_ko",
            "input_unit",
            "direction_code",
            "raw_a",
            "raw_b",
            "direction_aligned_raw_difference",
            "normalized_a",
            "normalized_b",
            "normalized_difference",
            "effective_feature_weight",
            "cpii_point_contribution",
            "absolute_driver_rank",
            "low_support_anchor",
        ),
    )
    require_fields(
        "economic_interpretations.csv",
        economic_fields,
        (
            "pair_id",
            "variable_name",
            "display_name_ko",
            "interpretation_class",
            "economic_base",
            "overlap_family",
            "aggregation_rule",
            "causal_status",
            "currency",
            "price_year",
            "availability",
            "common_size_amount_low",
            "common_size_amount_base",
            "common_size_amount_high",
            "actual_scale_amount_low",
            "actual_scale_amount_base",
            "actual_scale_amount_high",
        ),
    )
    require_fields(
        "golden_equal_gap_summary.csv",
        golden_fields,
        (
            "example_pair",
            "observation_id_a",
            "observation_id_b",
            "single_changed_driver",
            "delta_cpii_points",
            "common_exposure_base",
            "common_size_amount_base_krw",
            "interpretation_class",
            "synthetic_disclaimer",
        ),
    )
    require_fields(
        "sensitivity_summary.csv",
        sensitivity_fields,
        (
            "pair_id",
            "sensitivity_min_points",
            "sensitivity_max_points",
            "sign_stable",
            "interpretation_status",
            "positive_specification_share_descriptive",
            "probability_interpretation_allowed",
            "range_type",
            "empirical_pair_gap_percentile_status",
            "low_support_effective_weight",
        ),
    )

    if not isinstance(anchor, dict):
        raise ValueError("anchor JSON root must be an object")
    for field in (
        "anchor_version",
        "product_spec_version",
        "release_status",
        "active_components",
        "low_support_active_features",
        "low_support_effective_weight",
        "profiles",
        "source",
    ):
        if field not in anchor:
            raise ValueError(f"anchor JSON is missing {field}")

    if len(companies) < 3:
        raise ValueError("appendix requires at least three fictional companies")
    if not companies or any(row["synthetic_flag"].lower() != "yes" for row in companies):
        raise ValueError("every appendix company must be marked synthetic")
    if any(row["synthetic_flag"].lower() != "yes" for row in ranking):
        raise ValueError("every ranked appendix company must be marked synthetic")

    company_ids = [row["observation_id"] for row in companies]
    if len(company_ids) != len(set(company_ids)):
        raise ValueError("fictional company observation_id values must be unique")
    if set(company_ids) != {row["observation_id"] for row in ranking}:
        raise ValueError("company input and ranking observation IDs differ")
    if matrix_fields[1:] != company_ids:
        raise ValueError("pair matrix columns must follow fictional company input order")
    if [row["observation_id"] for row in matrix] != company_ids:
        raise ValueError("pair matrix rows must follow fictional company input order")

    active_components = anchor["active_components"]
    if not isinstance(active_components, dict):
        raise ValueError("anchor active_components must be an object")
    active_features: list[str] = []
    for axis in AXIS_ORDER:
        names = active_components.get(axis)
        if not isinstance(names, list) or not names:
            raise ValueError(f"anchor has no active feature list for {axis}")
        active_features.extend(str(name) for name in names)
    if len(active_features) != len(set(active_features)):
        raise ValueError("anchor active feature lists overlap")
    if len(active_features) != 10:
        raise ValueError(f"expected ten operational features, got {len(active_features)}")
    require_fields("fictional_companies.csv", company_fields, active_features)

    if len(pairs) != len(company_ids) * (len(company_ids) - 1) // 2:
        raise ValueError("pair_gaps.csv does not contain every unordered company pair")
    pair = one_row(pairs, "pair_gaps.csv", pair_id=PAIR_ID)
    pair_contributions = [row for row in contributions if row["pair_id"] == PAIR_ID]
    if {row["variable_name"] for row in pair_contributions} != set(active_features):
        raise ValueError(f"{PAIR_ID} contribution trace does not cover all active features")
    delta = finite_float(pair, "delta_cpii_points_a_minus_b", PAIR_ID)
    contribution_sum = sum(
        finite_float(row, "cpii_point_contribution", f"{PAIR_ID}/{row['variable_name']}")
        for row in pair_contributions
    )
    if not math.isclose(contribution_sum, delta, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError(f"{PAIR_ID} contribution sum differs from pair gap")

    pair_economic = [row for row in economic if row["pair_id"] == PAIR_ID]
    if {row["variable_name"] for row in pair_economic} != set(active_features):
        raise ValueError(f"{PAIR_ID} economic trace does not cover all active features")
    if any(row["aggregation_rule"] != "never_auto_sum" for row in economic):
        raise ValueError("every economic interpretation row must use never_auto_sum")

    if len(golden) != 2:
        raise ValueError(f"expected two equal-gap golden rows, got {len(golden)}")
    network_golden = one_row(
        golden,
        "golden_equal_gap_summary.csv",
        single_changed_driver="network_cost_ratio",
    )
    funding_golden = one_row(
        golden,
        "golden_equal_gap_summary.csv",
        single_changed_driver="funding_cost_spread",
    )
    golden_network_gap = finite_float(network_golden, "delta_cpii_points", "network golden pair")
    golden_funding_gap = finite_float(funding_golden, "delta_cpii_points", "funding golden pair")
    if not math.isclose(golden_network_gap, golden_funding_gap, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("golden pair CPII gaps are no longer equal")
    network_amount = finite_float(
        network_golden, "common_size_amount_base_krw", "network golden pair"
    )
    funding_amount = finite_float(
        funding_golden, "common_size_amount_base_krw", "funding golden pair"
    )
    if funding_amount == 0.0:
        raise ValueError("funding golden amount cannot be zero")

    pair_sensitivity = one_row(sensitivity, "sensitivity_summary.csv", pair_id=PAIR_ID)
    source = anchor["source"]
    if not isinstance(source, dict) or not isinstance(source.get("joint_support"), dict):
        raise ValueError("anchor source.joint_support must be an object")

    return {
        "companies": companies,
        "ranking": ranking,
        "matrix_fields": matrix_fields,
        "matrix": matrix,
        "pairs": pairs,
        "pair": pair,
        "contributions": contributions,
        "pair_contributions": pair_contributions,
        "economic": economic,
        "pair_economic": pair_economic,
        "golden": golden,
        "network_golden": network_golden,
        "funding_golden": funding_golden,
        "sensitivity": sensitivity,
        "pair_sensitivity": pair_sensitivity,
        "anchor": anchor,
        "active_features": active_features,
        "network_amount": network_amount,
        "funding_amount": funding_amount,
    }


def build_appendix() -> str:
    data = load_sources()
    companies: list[Mapping[str, str]] = data["companies"]
    ranking: list[Mapping[str, str]] = data["ranking"]
    matrix_fields: list[str] = data["matrix_fields"]
    matrix: list[Mapping[str, str]] = data["matrix"]
    pairs: list[Mapping[str, str]] = data["pairs"]
    pair: Mapping[str, str] = data["pair"]
    contributions: list[Mapping[str, str]] = data["pair_contributions"]
    economics: list[Mapping[str, str]] = data["pair_economic"]
    sensitivity: list[Mapping[str, str]] = data["sensitivity"]
    anchor: Mapping[str, Any] = data["anchor"]
    active_features: list[str] = data["active_features"]

    company_by_id = {row["observation_id"]: row for row in companies}
    pair_by_id = {row["pair_id"]: row for row in pairs}
    contribution_by_name = {row["variable_name"]: row for row in contributions}
    economic_by_name = {row["variable_name"]: row for row in economics}
    profiles: Mapping[str, Mapping[str, Any]] = anchor["profiles"]
    joint: Mapping[str, Any] = anchor["source"]["joint_support"]
    row_count = int(anchor["source"]["row_count"])
    complete_count = int(joint["complete_row_count"])
    low_support_weight = float(anchor["low_support_effective_weight"])
    component_counts = [len(anchor["active_components"][axis]) for axis in AXIS_ORDER]
    count_text = "/".join(str(count) for count in component_counts)
    method_version = str(anchor["product_spec_version"])
    anchor_version = str(anchor["anchor_version"])

    delta = finite_float(pair, "delta_cpii_points_a_minus_b", PAIR_ID)
    contribution_sum = sum(
        finite_float(row, "cpii_point_contribution", row["variable_name"])
        for row in contributions
    )
    residual = contribution_sum - delta
    sensitivity_pair: Mapping[str, str] = data["pair_sensitivity"]

    network_golden: Mapping[str, str] = data["network_golden"]
    funding_golden: Mapping[str, str] = data["funding_golden"]
    network_amount = float(data["network_amount"])
    funding_amount = float(data["funding_amount"])
    golden_ratio = abs(network_amount / funding_amount)
    golden_gap = finite_float(network_golden, "delta_cpii_points", "network golden pair")

    provenance = [
        "% AUTO-GENERATED by scripts/cpii_simulator/build_appendix.py; do not edit.",
        "% Deterministic source provenance (SHA256):",
    ]
    for path in SOURCE_PATHS:
        provenance.append(
            f"% source-sha256: {path.relative_to(PROJECT_ROOT).as_posix()} {sha256_file(path)}"
        )

    lines: list[str] = provenance + [
        "",
        r"\chapter{회사 입력형 CPII 비교와 경제적 차이 해석}",
        r"\label{app:cpii_company_comparator}",
        "",
        r"\noindent\fbox{\parbox{0.96\textwidth}{\textbf{Research Beta 경고.} "
        + "방법론 설명용 합성자료이며 실제 기업에 대한 추정이 아님. "
        + "현재 고정 앵커의 결합 기준표본과 일부 feature의 지원도가 매우 낮으므로, 결과는 연구·전략분석 보조지표로만 사용한다. "
        + "차별·역차별·위법성·손해 또는 인과효과를 판정하지 않는다.}}",
        "",
        r"\section{세 점수체계와 해석 단위}",
        "회사 입력형 비교기에서 서로 다른 세 수치를 같은 축으로 읽어서는 안 된다. ",
        "",
    ]

    lines.extend(
        [
            r"\begingroup",
            r"\small",
            r"\setlength{\tabcolsep}{4pt}",
        ]
    )
    add_longtable_header(
        lines,
        r"@{}L{3.2cm}L{2.8cm}L{8.3cm}@{}",
        "CPII 관련 세 점수체계의 구분",
        "tab:cpii_appendix_scale_distinction",
        ("수치", "범위·부호", "정확한 의미"),
    )
    lines.extend(
        [
            r"회사별 CPII & $0$--$100$ & 고정 기준분포에서 feature별 부담 위치를 정해진 가중치로 합성한 회사별 구조적 부담점수. 기업 백분위가 아니다. \\",
            r"회사쌍 점수차 $\Delta\mathrm{CPII}_{A-B}$ & \(-100\)--\(+100\) & $\mathrm{CPII}(A)-\mathrm{CPII}(B)$이다. 양수는 A의 측정 부담 위치가 B보다 높고, 음수는 그 반대다. \\",
            r"legacy signed evidence score & \(-1\)--\(+1\) & 0을 중심으로 판단·증거를 코딩한 별도 지표다. feature 기반 CPII나 A-B 점수차가 아니며 같은 축·범례·해석 규칙을 쓰지 않는다. \\",
            r"\bottomrule",
            r"\end{longtable}",
            r"\endgroup",
            "",
            r"특히 $\Delta\mathrm{CPII}=0.10$점은 feature별 기준분포 위치 차이의 \textbf{가중합이 정확히 $0.001$}이라는 뜻이다($0.10/100=0.001$). 이는 비용 $0.1\%$, 매출 $0.1\%$, 회사 간 기업 백분위 $0.1\%$p를 뜻하지 않는다. 점수차는 먼저 feature 기여도로 분해한 뒤, 해당 원단위와 등록된 경제 노출기준이 있을 때만 채널별로 해석한다.",
            "",
            r"\section{고정 앵커와 운용 사양}",
            "방법론 버전 "
            + tex_code(method_version)
            + "은 고정 앵커 "
            + tex_code(anchor_version)
            + "을 사용한다. 입력 회사 집합을 추가·삭제·재정렬해도 기존 회사 점수는 바뀌지 않는다. ",
            "현재 앵커에서 10개 활성 feature가 모두 관측된 결합 기준표본은 "
            + f"{complete_count}/{row_count}행"
            + "뿐이다. 저지원 활성 feature "
            + ", ".join(tex_code(name) for name in anchor["low_support_active_features"])
            + "의 합산 유효가중치는 "
            + fmt_percent(low_support_weight)
            + "다. 따라서 회사 경험적 백분위, pair-gap 경험적 백분위, 산업 대표분포 주장은 비활성화한다.",
            "",
            "운용 feature 구성은 "
            + axis_tex("I_reg")
            + "/"
            + axis_tex("I_risk")
            + "/"
            + axis_tex("I_market")
            + f" 순서로 {count_text}, 합계 {len(active_features)}개다. 이 구성은 보고서의 더 넓은 이론 변수목록을 자동 대체하지 않는다.",
            "",
            r"\begin{align}",
            r"z_{ij} &= \mathcal{N}_{j}^{\mathrm{fixed}}\!\left(d_j x_{ij}\right), \\",
            r"I_{ik} &= \frac{100}{|J_k|}\sum_{j\in J_k} z_{ij}, \qquad k\in\{\mathrm{reg},\mathrm{risk},\mathrm{market}\}, \\",
            r"\mathrm{CPII}_i &= \frac{1}{3}\sum_k I_{ik}, \\",
            r"\Delta\mathrm{CPII}_{A-B} &= \mathrm{CPII}_A-\mathrm{CPII}_B =\sum_j 100w_j\left(z_{Aj}-z_{Bj}\right).",
            r"\end{align}",
            r"여기서 $d_j$는 부담 증가 방향을 맞추는 부호, $\mathcal{N}_{j}^{\mathrm{fixed}}$는 고정 앵커의 변환·1\%/99\% winsorization·경험순위 정규화, $w_j$는 하위지수 내부 동일가중과 세 축 동일가중을 전개한 유효 feature 가중치다.",
            "",
            r"\section{합성 회사 입력과 \texorpdfstring{$n$}{n}개 회사 비교}",
            r"\textbf{방법론 설명용 합성자료이며 실제 기업에 대한 추정이 아님.} "
            + "아래 네 회사는 원천 CSV에서 생성한 통제 합성 예시다. 회사명은 식별자일 뿐이며 값을 조회·추론·대체하지 않는다.",
            "",
            r"\begin{landscape}",
            r"\begingroup",
            r"\scriptsize",
            r"\setlength{\tabcolsep}{2.5pt}",
        ]
    )

    input_headers = ["축", "입력 feature", "단위", "방향"] + [
        wrap_cell(tex_code(row["observation_id"]), latex_escape(row["company_name"]))
        for row in companies
    ]
    input_column_spec = "@{}L{1.2cm}L{4.1cm}L{1.7cm}L{1.0cm}" + "L{2.1cm}" * len(companies) + "@{}"
    add_longtable_header(
        lines,
        input_column_spec,
        "방법론 설명용 합성 회사의 10개 원단위 입력",
        "tab:cpii_appendix_synthetic_inputs",
        input_headers,
    )
    for axis in AXIS_ORDER:
        for feature in anchor["active_components"][axis]:
            metadata = contribution_by_name[feature]
            profile = profiles[feature]
            row_cells = [
                axis_tex(axis),
                wrap_cell(latex_escape(profile["display_name_ko"]), tex_code_breakable(feature)),
                latex_escape(unit_label(metadata["input_unit"])),
                fmt_points(float(profile["direction_code"]), 0),
            ]
            row_cells.extend(
                fmt_raw(
                    finite_float(company_by_id[company["observation_id"]], feature, company["observation_id"]),
                    metadata["input_unit"],
                )
                for company in companies
            )
            lines.append(" & ".join(row_cells) + r" \\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{longtable}",
            r"\endgroup",
            r"\end{landscape}",
            "",
            r"\begingroup",
            r"\small",
            r"\setlength{\tabcolsep}{4pt}",
        ]
    )
    add_longtable_header(
        lines,
        r"@{}L{1.0cm}L{3.7cm}L{1.5cm}L{1.5cm}L{1.5cm}L{1.5cm}L{2.4cm}@{}",
        "합성 회사의 고정 앵커 점수와 부담순위",
        "tab:cpii_appendix_synthetic_ranking",
        ("순위", "회사", "CPII", axis_tex("I_reg"), axis_tex("I_risk"), axis_tex("I_market"), "관측/활성 feature"),
    )
    ranking_sorted = sorted(
        ranking,
        key=lambda row: finite_float(row, "burden_rank_desc", row["observation_id"]),
    )
    for row in ranking_sorted:
        rank_value = finite_float(row, "burden_rank_desc", row["observation_id"])
        rank_text = str(int(rank_value)) if rank_value.is_integer() else fmt_decimal(rank_value, 1)
        lines.append(
            " & ".join(
                [
                    rank_text,
                    wrap_cell(tex_code(row["observation_id"]), latex_escape(row["company_name"]), tex_code(row["company_group"])),
                    fmt_decimal(finite_float(row, "CPII", row["observation_id"]), 2),
                    fmt_decimal(finite_float(row, "I_reg", row["observation_id"]), 2),
                    fmt_decimal(finite_float(row, "I_risk", row["observation_id"]), 2),
                    fmt_decimal(finite_float(row, "I_market", row["observation_id"]), 2),
                    str(int(finite_float(row, "observed_feature_count", row["observation_id"])))
                    + "/"
                    + str(int(finite_float(row, "active_feature_count", row["observation_id"]))),
                ]
            )
            + r" \\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{longtable}",
            r"\endgroup",
            "",
            r"\begingroup",
            r"\small",
            r"\setlength{\tabcolsep}{5pt}",
        ]
    )
    matrix_headers = [r"행 $A$ $-$ 열 $B$"] + [tex_code(field) for field in matrix_fields[1:]]
    matrix_spec = "@{}L{3.0cm}" + "L{2.0cm}" * (len(matrix_fields) - 1) + "@{}"
    add_longtable_header(
        lines,
        matrix_spec,
        "합성 회사 CPII 점수차 행렬(행 A $-$ 열 B, 점)",
        "tab:cpii_appendix_pair_matrix",
        matrix_headers,
    )
    for matrix_row in matrix:
        row_id = matrix_row["observation_id"]
        cells = [wrap_cell(tex_code(row_id), latex_escape(company_by_id[row_id]["company_name"]))]
        for column_id in matrix_fields[1:]:
            cells.append(fmt_points(finite_float(matrix_row, column_id, f"matrix/{row_id}"), 2))
        lines.append(" & ".join(cells) + r" \\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{longtable}",
            r"\endgroup",
            "표의 대각선은 0이고, 각 비대각 원소는 반대 방향 원소와 부호가 반대다. 순위와 행렬은 동일한 고정 앵커와 공통 10개 feature로 계산된다.",
            "",
            r"\section{2개 회사 상세 추적: SYN-A 대 SYN-B}",
            tex_code(pair["observation_id_a"])
            + "와 "
            + tex_code(pair["observation_id_b"])
            + "는 동일 cohort에서 비교 가능하며, 기준 점수차는 "
            + rf"$\Delta\mathrm{{CPII}}_{{A-B}}={fmt_points(delta, 2)}$점"
            + "이다. 다음 표는 원단위 입력에서 고정 앵커 위치, 유효가중치, CPII 기여도까지 한 줄로 추적한다.",
            "",
            r"\begin{landscape}",
            r"\begingroup",
            r"\scriptsize",
            r"\setlength{\tabcolsep}{2.2pt}",
        ]
    )
    add_longtable_header(
        lines,
        r"@{}L{0.8cm}L{3.9cm}L{1.4cm}L{1.4cm}L{2.0cm}L{1.5cm}L{1.5cm}L{1.5cm}L{1.8cm}@{}",
        "SYN-A 대 SYN-B의 feature별 점수차 분해",
        "tab:cpii_appendix_driver_trace",
        ("순위", "driver", "원값 A", "원값 B", "방향정렬 원차", "$z_A$", "$z_B$", "$w_j$", "기여도(점)"),
    )
    contributions_sorted = sorted(
        contributions,
        key=lambda row: finite_float(row, "absolute_driver_rank", row["variable_name"]),
    )
    for row in contributions_sorted:
        unit = row["input_unit"]
        rank_value = finite_float(row, "absolute_driver_rank", row["variable_name"])
        lines.append(
            " & ".join(
                [
                    str(int(rank_value)),
                    wrap_cell(latex_escape(row["display_name_ko"]), tex_code_breakable(row["variable_name"]), axis_tex(row["subindex"])),
                    fmt_raw(finite_float(row, "raw_a", row["variable_name"]), unit),
                    fmt_raw(finite_float(row, "raw_b", row["variable_name"]), unit),
                    fmt_raw(
                        finite_float(row, "direction_aligned_raw_difference", row["variable_name"]),
                        unit,
                    ),
                    fmt_decimal(finite_float(row, "normalized_a", row["variable_name"]), 4),
                    fmt_decimal(finite_float(row, "normalized_b", row["variable_name"]), 4),
                    fmt_percent(finite_float(row, "effective_feature_weight", row["variable_name"]), 2),
                    fmt_points(finite_float(row, "cpii_point_contribution", row["variable_name"]), 2),
                ]
            )
            + r" \\"
        )
    lines.extend(
        [
            r"\midrule",
            r"\multicolumn{8}{r}{기여도 합계} & " + fmt_points(contribution_sum, 6) + r" \\",
            r"\multicolumn{8}{r}{합계 $-$ 표시 전 원점수차 잔차} & " + format(residual, "+.2e") + r" \\",
            r"\bottomrule",
            r"\end{longtable}",
            r"\endgroup",
            r"\end{landscape}",
            "",
        ]
    )

    top_three = contributions_sorted[:3]
    top_driver_text = ", ".join(
        latex_escape(row["display_name_ko"])
        + " "
        + fmt_points(finite_float(row, "cpii_point_contribution", row["variable_name"]), 2)
        + "점"
        for row in top_three
    )
    lines.extend(
        [
            "절대기여도 상위 3개 driver는 " + top_driver_text + "이다. 양의 기여는 A-B 점수차를 넓히고 음의 기여는 줄이며, 0 기여도도 원값 차이가 없다는 뜻은 아닐 수 있다. 고정 경험순위에서 같은 위치로 매핑되면 원값 차이가 있어도 점수 기여는 0이 된다.",
            "",
            r"\subsection{원단위 차이에서 경제량까지}",
            "공통규모 상당액은 두 회사에 공통으로 적용한 노출기준에서 driver의 원단위 차이를 비교한다. 실제규모 차이는 회사별 수준과 회사별 노출액을 각각 결합하므로 공통규모 값과 다른 질문에 답한다. "
            + tex_code("scenario_only")
            + "는 관측 손익이 아니라 명시적 가정에 따른 시나리오이며, "
            + tex_code("non_monetizable")
            + "은 독립적·비중복 경제계수가 식별되지 않아 금액으로 바꾸지 않는다.",
            "",
            r"\begin{landscape}",
            r"\begingroup",
            r"\scriptsize",
            r"\setlength{\tabcolsep}{2pt}",
        ]
    )
    econ_currency = economics[0]["currency"]
    econ_price_year = economics[0]["price_year"]
    add_longtable_header(
        lines,
        r"@{}L{4.3cm}L{3.1cm}L{3.1cm}L{4.1cm}L{4.1cm}L{2.5cm}@{}",
        "SYN-A 대 SYN-B의 경제해석 low/base/high(" + latex_escape(econ_price_year) + "년 " + latex_escape(econ_currency) + ", 억원)",
        "tab:cpii_appendix_economic_trace",
        ("driver", "해석 유형", "노출기준", r"공통규모 low / base / high", r"실제규모 low / base / high", "중복군"),
    )
    for contribution in contributions_sorted:
        row = economic_by_name[contribution["variable_name"]]

        def amount_cell(field: str) -> str:
            text = row.get(field, "").strip()
            return "--" if not text else fmt_money_100m(finite_float(row, field, row["variable_name"]))

        def amount_triplet(prefix: str) -> str:
            fields = [f"{prefix}_low", f"{prefix}_base", f"{prefix}_high"]
            values = [amount_cell(field) for field in fields]
            if values == ["--", "--", "--"]:
                return "--"
            return " / ".join(values)

        lines.append(
            " & ".join(
                [
                    wrap_cell(latex_escape(row["display_name_ko"]), tex_code_breakable(row["variable_name"])),
                    latex_escape(economic_class_label(row["interpretation_class"])),
                    latex_escape(economic_base_label(row["economic_base"])),
                    amount_triplet("common_size_amount"),
                    amount_triplet("actual_scale_amount"),
                    latex_escape(overlap_label(row["overlap_family"])),
                ]
            )
            + r" \\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{longtable}",
            r"\endgroup",
            r"\end{landscape}",
            "모든 경제해석 행의 집계 규칙은 "
            + tex_code("never_auto_sum")
            + "이다. 조건부 회계 상당액, 조건부 성과 상당액, 시나리오 금액은 개념과 중복 family가 다르고 서로 원인·결과 관계일 수도 있으므로 합계 손실액처럼 자동 합산하지 않는다. low/base/high도 결정론적 입력·노출 가정 범위이며 신뢰구간이나 확률구간이 아니다.",
            "",
            r"\section{같은 점수차, 다른 경제적 크기: 골든 통제 예시}",
            "두 골든 pair는 하나의 driver만 바꾸어 동일한 CPII 점수차를 만들지만 노출기준과 원단위가 다르다.",
            "",
            r"\begingroup",
            r"\small",
            r"\setlength{\tabcolsep}{4pt}",
        ]
    )
    add_longtable_header(
        lines,
        r"@{}L{3.2cm}L{3.0cm}L{2.2cm}L{2.8cm}L{2.8cm}@{}",
        "동일 CPII 점수차의 네트워크·조달금리 경제량 대비",
        "tab:cpii_appendix_equal_gap_golden",
        ("통제 pair", "단일 변경 driver", r"$\Delta$CPII(점)", "공통 노출 base(억원)", "공통규모 base(억원)"),
    )
    for row in (network_golden, funding_golden):
        lines.append(
            " & ".join(
                [
                    wrap_cell(
                        "네트워크 비용률 통제"
                        if row["single_changed_driver"] == "network_cost_ratio"
                        else "조달금리 통제",
                        tex_code(row["observation_id_a"]),
                        tex_code(row["observation_id_b"]),
                    ),
                    (
                        "네트워크 비용률"
                        if row["single_changed_driver"] == "network_cost_ratio"
                        else "조달금리 스프레드"
                    ),
                    fmt_points(finite_float(row, "delta_cpii_points", row["example_pair"]), 4),
                    fmt_money_100m(finite_float(row, "common_exposure_base", row["example_pair"]), signed=False),
                    fmt_money_100m(finite_float(row, "common_size_amount_base_krw", row["example_pair"]), signed=False),
                ]
            )
            + r" \\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{longtable}",
            r"\endgroup",
            "두 pair의 점수차는 각각 "
            + fmt_decimal(golden_gap, 4)
            + "점으로 같지만, 네트워크 비용률 채널의 공통규모 base는 약 "
            + fmt_money_100m(network_amount, signed=False)
            + "억원, 자금조달비용 스프레드 채널은 약 "
            + fmt_money_100m(funding_amount, signed=False)
            + "억원이다. 전자는 후자의 약 "
            + fmt_decimal(golden_ratio, 2)
            + "배다. 따라서 보편적인 ``CPII 1점당 원화'' 계수는 존재하지 않는다.",
            "",
            r"\section{민감도 판독과 한계}",
            r"\begingroup",
            r"\footnotesize",
            r"\setlength{\tabcolsep}{2pt}",
        ]
    )
    add_longtable_header(
        lines,
        r"@{}L{2.5cm}L{1.5cm}L{2.8cm}L{1.5cm}L{2.0cm}L{3.8cm}@{}",
        "합성 회사 pair별 결정론적 민감도 범위",
        "tab:cpii_appendix_sensitivity",
        ("pair", "기준 gap", "민감도 구간 [min, max]", "부호 안정", "양(+) 사양 비중", "판독"),
    )
    for row in sensitivity:
        baseline = pair_by_id[row["pair_id"]]
        min_value = finite_float(row, "sensitivity_min_points", row["pair_id"])
        max_value = finite_float(row, "sensitivity_max_points", row["pair_id"])
        lines.append(
            " & ".join(
                [
                    latex_escape(row["pair_id"].replace("__vs__", "–")),
                    fmt_points(finite_float(baseline, "delta_cpii_points_a_minus_b", row["pair_id"]), 2),
                    "[" + fmt_points(min_value, 2) + ", " + fmt_points(max_value, 2) + "]",
                    tex_code(row["sign_stable"]),
                    fmt_percent(finite_float(row, "positive_specification_share_descriptive", row["pair_id"]), 2),
                    latex_escape(sensitivity_label(row["interpretation_status"])),
                ]
            )
            + r" \\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{longtable}",
            r"\endgroup",
            "선택 pair "
            + latex_escape(PAIR_ID.replace("__vs__", "–"))
            + "의 범위는 "
            + fmt_points(finite_float(sensitivity_pair, "sensitivity_min_points", PAIR_ID), 2)
            + "점에서 "
            + fmt_points(finite_float(sensitivity_pair, "sensitivity_max_points", PAIR_ID), 2)
            + "점이며 0을 포함한다. 따라서 기준점수의 부호만으로 안정된 차이라고 결론내리지 않고 "
            + latex_escape(sensitivity_label(sensitivity_pair["interpretation_status"]))
            + "로 판독한다.",
            "",
            r"\begingroup\small",
            r"\begin{itemize}[leftmargin=2em,itemsep=0.15em,topsep=0.25em]",
            r"\item 민감도 [min, max] 구간은 입력 범위와 사전 정의 대체 사양을 통과시킨 결정론적 범위다. 신뢰구간·확률구간·예측구간이 아니며, 양(+) 사양 비중도 확률이 아니다.",
            r"\item 결합 기준표본이 얇으므로 회사 경험적 백분위, pair-gap 경험적 백분위, 산업 대표성은 주장하지 않는다. 저지원 feature의 가중치가 결과에 포함된다는 Research Beta 경고를 항상 함께 본다.",
            r"\item 합성 예시는 계산 재현성을 검증할 뿐 실제 회사, 산업 평균, 법적 차별·역차별, 위법성, 손해 또는 인과효과의 증거가 아니다.",
            r"\end{itemize}",
            r"\endgroup",
            "",
            "% End of auto-generated CPII company-comparator appendix.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_or_check(check: bool) -> None:
    content = build_appendix()
    if check:
        if not OUTPUT_PATH.exists():
            raise ValueError(f"missing generated appendix: {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
        actual = OUTPUT_PATH.read_text(encoding="utf-8")
        if actual != content:
            raise ValueError(
                f"stale generated appendix: {OUTPUT_PATH.relative_to(PROJECT_ROOT)}; "
                "run build_appendix.py without --check"
            )
        print("PASS CPII interpretation appendix: sources, formulas, examples, and hashes are current")
        return

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(content, encoding="utf-8")
    print(f"WROTE {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare the committed fragment byte-for-byte")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        write_or_check(args.check)
    except (OSError, ValueError, KeyError, TypeError, csv.Error, json.JSONDecodeError) as exc:
        print(f"FAIL CPII interpretation appendix: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
