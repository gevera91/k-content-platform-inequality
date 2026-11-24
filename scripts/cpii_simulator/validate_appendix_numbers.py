#!/usr/bin/env python3
"""Validate the generated CPII appendix and its inclusion in the report."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from typing import Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.cpii_simulator import build_appendix as builder
else:
    from . import build_appendix as builder


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_INPUT = r"\input{outputs/tables/cpii_simulator/appendix/cpii_interpretation_appendix.tex}"
FORBIDDEN_LEGACY_WORDING = (
    "부담귀착 방향 사례점수(0--1)",
    "부담귀착 방향 사례점수는 0--1 척도",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"missing CSV header: {path.relative_to(PROJECT_ROOT)}")
        return list(reader)


def number(row: Mapping[str, str], field: str, context: str) -> float:
    text = row.get(field, "").strip()
    if not text:
        raise ValueError(f"{context}: missing {field}")
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"{context}: non-finite {field}")
    return value


def one(rows: Sequence[Mapping[str, str]], context: str, **criteria: str) -> Mapping[str, str]:
    matches = [row for row in rows if all(row.get(key) == value for key, value in criteria.items())]
    if len(matches) != 1:
        raise ValueError(f"{context}: expected one matching row, got {len(matches)}")
    return matches[0]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_fragments(text: str, fragments: Sequence[str], context: str) -> None:
    missing = [fragment for fragment in fragments if fragment not in text]
    if missing:
        raise ValueError(f"{context} is missing required content: {missing[0]!r}")


def run_builder_check() -> str:
    result = subprocess.run(
        [sys.executable, "scripts/cpii_simulator/build_appendix.py", "--check"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stdout + "\n" + result.stderr).strip()
        raise ValueError(f"appendix builder --check failed: {detail}")
    if "PASS CPII interpretation appendix" not in result.stdout:
        raise ValueError("appendix builder returned no PASS marker")
    return result.stdout.strip()


def validate_input_line(report_text: str) -> str:
    uncommented_lines = [line.split("%", 1)[0].strip() for line in report_text.splitlines()]
    if EXPECTED_INPUT not in uncommented_lines:
        raise ValueError(f"report is missing exact appendix input line: {EXPECTED_INPUT}")
    if uncommented_lines.count(EXPECTED_INPUT) != 1:
        raise ValueError("report must input the generated CPII appendix exactly once")
    return "report input=present exactly once"


def validate_provenance(fragment: str) -> str:
    pattern = re.compile(r"^% source-sha256: (\S+) ([0-9a-f]{64})$", re.MULTILINE)
    recorded = dict(pattern.findall(fragment))
    expected = {
        path.relative_to(PROJECT_ROOT).as_posix(): sha256(path)
        for path in builder.SOURCE_PATHS
    }
    if set(recorded) != set(expected):
        missing = sorted(set(expected) - set(recorded))
        extra = sorted(set(recorded) - set(expected))
        raise ValueError(f"appendix provenance source set differs; missing={missing}, extra={extra}")
    stale = [relative for relative, digest in expected.items() if recorded[relative] != digest]
    if stale:
        raise ValueError(f"appendix provenance hash is stale: {stale[0]}")
    return f"provenance={len(expected)} source SHA256 values current"


def validate_concepts(fragment: str, report_text: str) -> str:
    anchor = json.loads(builder.ANCHOR_PATH.read_text(encoding="utf-8"))
    counts = [len(anchor["active_components"][axis]) for axis in builder.AXIS_ORDER]
    joint = anchor["source"]["joint_support"]
    required = (
        r"\chapter{회사 입력형 CPII 비교와 경제적 차이 해석}",
        r"\label{app:cpii_company_comparator}",
        "Research Beta",
        r"\(-100\)--\(+100\)",
        "A-B",
        "legacy signed evidence score",
        r"\(-1\)--\(+1\)",
        r"$\Delta\mathrm{CPII}=0.10$",
        "0.001",
        r"비용 $0.1\%$",
        r"매출 $0.1\%$",
        "기업 백분위",
        "고정 앵커",
        f"{int(joint['complete_row_count'])}/{int(anchor['source']['row_count'])}행",
        builder.fmt_percent(float(anchor["low_support_effective_weight"])),
        "/".join(str(value) for value in counts),
        f"합계 {sum(counts)}개",
        r"\Delta\mathrm{CPII}_{A-B}",
        "합성 회사",
        "방법론 설명용 합성자료이며 실제 기업에 대한 추정이 아님",
        "SYN-A 대 SYN-B",
        "공통규모",
        "실제규모",
        r"scenario\_only",
        r"non\_monetizable",
        r"never\_auto\_sum",
        "민감도",
        "신뢰구간",
        "인과효과",
        "자동 합산하지 않는다",
    )
    require_fragments(fragment, required, "generated appendix")

    for wording in FORBIDDEN_LEGACY_WORDING:
        if wording in report_text:
            raise ValueError(f"report retains incorrect legacy signed-score wording: {wording!r}")
    require_fragments(
        report_text,
        (
            "부담귀착 부호형 증거점수",
            "$[-1,+1]$",
            "영(0)",
            "이는 0--100 CPII",
        ),
        "report legacy signed-score correction",
    )
    return "concepts=three scales, 0.10 rule, anchor support, economics, sensitivity, and legacy correction present"


def validate_numeric_invariants(fragment: str) -> str:
    companies = read_csv(builder.INPUT_PATH)
    ranking = read_csv(builder.EXAMPLE_DIR / "company_ranking.csv")
    matrix = read_csv(builder.EXAMPLE_DIR / "pair_gap_matrix.csv")
    pairs = read_csv(builder.EXAMPLE_DIR / "pair_gaps.csv")
    contributions = read_csv(builder.EXAMPLE_DIR / "pair_contributions.csv")
    economic = read_csv(builder.EXAMPLE_DIR / "economic_interpretations.csv")
    golden = read_csv(builder.EXAMPLE_DIR / "golden_equal_gap_summary.csv")
    sensitivity = read_csv(builder.EXAMPLE_DIR / "sensitivity_summary.csv")

    ids = [row["observation_id"] for row in companies]
    score_order = sorted(
        ranking,
        key=lambda row: number(row, "burden_rank_desc", row["observation_id"]),
    )
    score_values = [number(row, "CPII", row["observation_id"]) for row in score_order]
    if score_values != sorted(score_values, reverse=True):
        raise ValueError("burden ranks are not descending by CPII")
    for row in ranking:
        require_fragments(
            fragment,
            (builder.tex_code(row["observation_id"]), builder.fmt_decimal(number(row, "CPII", row["observation_id"]), 2)),
            f"ranking row {row['observation_id']}",
        )

    matrix_by_id = {row["observation_id"]: row for row in matrix}
    for left in ids:
        diagonal = number(matrix_by_id[left], left, f"matrix {left}/{left}")
        if abs(diagonal) > 1e-12:
            raise ValueError(f"pair matrix diagonal is not zero for {left}")
        for right in ids:
            value = number(matrix_by_id[left], right, f"matrix {left}/{right}")
            reverse = number(matrix_by_id[right], left, f"matrix {right}/{left}")
            if not math.isclose(value, -reverse, rel_tol=0.0, abs_tol=1e-10):
                raise ValueError(f"pair matrix is not antisymmetric for {left}/{right}")
            if builder.fmt_points(value, 2) not in fragment:
                raise ValueError(f"appendix omits current matrix number for {left}/{right}")

    pair = one(pairs, "pair gaps", pair_id=builder.PAIR_ID)
    gap = number(pair, "delta_cpii_points_a_minus_b", builder.PAIR_ID)
    if not math.isclose(gap, number(matrix_by_id["SYN-A"], "SYN-B", builder.PAIR_ID), rel_tol=0.0, abs_tol=1e-10):
        raise ValueError("SYN-A/SYN-B pair gap differs from matrix")
    pair_contributions = [row for row in contributions if row["pair_id"] == builder.PAIR_ID]
    contribution_sum = sum(number(row, "cpii_point_contribution", row["variable_name"]) for row in pair_contributions)
    if not math.isclose(contribution_sum, gap, rel_tol=0.0, abs_tol=1e-10):
        raise ValueError("SYN-A/SYN-B feature contributions do not sum to its gap")
    for row in pair_contributions:
        expected = builder.fmt_points(number(row, "cpii_point_contribution", row["variable_name"]), 2)
        if expected not in fragment:
            raise ValueError(f"appendix omits current contribution for {row['variable_name']}")

    pair_economic = [row for row in economic if row["pair_id"] == builder.PAIR_ID]
    if any(row["aggregation_rule"] != "never_auto_sum" for row in pair_economic):
        raise ValueError("SYN-A/SYN-B economic rows do not all use never_auto_sum")
    for row in pair_economic:
        for field in (
            "common_size_amount_low",
            "common_size_amount_base",
            "common_size_amount_high",
            "actual_scale_amount_low",
            "actual_scale_amount_base",
            "actual_scale_amount_high",
        ):
            if row[field].strip():
                token = builder.fmt_money_100m(number(row, field, row["variable_name"]))
                if token not in fragment:
                    raise ValueError(f"appendix omits current economic number {row['variable_name']}/{field}")

    network = one(golden, "golden rows", single_changed_driver="network_cost_ratio")
    funding = one(golden, "golden rows", single_changed_driver="funding_cost_spread")
    network_gap = number(network, "delta_cpii_points", "network golden")
    funding_gap = number(funding, "delta_cpii_points", "funding golden")
    if not math.isclose(network_gap, funding_gap, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("golden gaps are not equal")
    network_amount = number(network, "common_size_amount_base_krw", "network golden")
    funding_amount = number(funding, "common_size_amount_base_krw", "funding golden")
    ratio = abs(network_amount / funding_amount)
    golden_tokens = (
        builder.fmt_decimal(network_gap, 4),
        builder.fmt_money_100m(network_amount, signed=False),
        builder.fmt_money_100m(funding_amount, signed=False),
        builder.fmt_decimal(ratio, 2),
    )
    require_fragments(fragment, golden_tokens, "golden equal-gap example")

    for row in sensitivity:
        tokens = (
            builder.latex_escape(row["pair_id"].replace("__vs__", "–")),
            builder.fmt_points(number(row, "sensitivity_min_points", row["pair_id"]), 2),
            builder.fmt_points(number(row, "sensitivity_max_points", row["pair_id"]), 2),
        )
        require_fragments(fragment, tokens, f"sensitivity row {row['pair_id']}")

    regenerated = builder.build_appendix()
    if fragment != regenerated:
        raise ValueError("fragment differs from independently regenerated appendix content")
    return f"numbers={len(ranking)} ranks, {len(ids) ** 2} matrix cells, {len(pair_contributions)} drivers, {len(pair_economic)} economic rows current"


def validate_no_absolute_paths(report_text: str, fragment: str) -> str:
    for label, text in (("report", report_text), ("generated appendix", fragment)):
        if "/Users/" in text or "GoogleDrive" in text or "file://" in text:
            raise ValueError(f"{label} contains a workstation-specific absolute path")
        if re.search(r"[A-Za-z]:\\(?:Users|Documents|Desktop)\\", text):
            raise ValueError(f"{label} contains a Windows workstation-specific path")
    return "paths=no workstation-specific absolute paths"


def resolve_report(argument: Path) -> Path:
    path = argument if argument.is_absolute() else PROJECT_ROOT / argument
    if not path.is_file():
        raise ValueError(f"report does not exist: {argument}")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="report TeX path, normally kakao_enter.tex")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report_path = resolve_report(args.report)
        builder_message = run_builder_check()
        report_text = report_path.read_text(encoding="utf-8")
        fragment = builder.OUTPUT_PATH.read_text(encoding="utf-8")
        messages = [
            builder_message,
            validate_input_line(report_text),
            validate_provenance(fragment),
            validate_concepts(fragment, report_text),
            validate_numeric_invariants(fragment),
            validate_no_absolute_paths(report_text, fragment),
        ]
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError, csv.Error, json.JSONDecodeError) as exc:
        print(f"FAIL CPII appendix validation: {exc}", file=sys.stderr)
        return 1
    print("PASS CPII appendix integration and generated-number validation")
    for message in messages:
        print(f"- {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
