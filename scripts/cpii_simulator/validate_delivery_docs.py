#!/usr/bin/env python3
"""Validate the CPII customer guide and header-only delivery templates."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GUIDE_PATH = PROJECT_ROOT / "docs" / "cpii_comparator_user_guide.md"
WORKBOOK_PATH = PROJECT_ROOT / "outputs" / "client_delivery" / "CPII_Company_Comparator.xlsx"
ANCHOR_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cpii_simulator"
    / "anchor"
    / "POOL_SCQ_P01_P99_EMP_RANK_V1.json"
)
EXAMPLE_DIR = PROJECT_ROOT / "outputs" / "tables" / "cpii_simulator" / "examples"
WORKBOOK_VERSION = "CPII_COMPARATOR_XLSX_V1.0.1"

TEMPLATE_SPECS = {
    "CPII_Input_Template.csv": "cpii_simulator_input_schema.csv",
    "CPII_Economic_Exposure_Template.csv": "cpii_economic_exposure_schema.csv",
    "CPII_Feature_Provenance_Template.csv": "cpii_feature_provenance_schema.csv",
    "CPII_Feature_Range_Template.csv": "cpii_feature_range_schema.csv",
}

REQUIRED_GUIDE_HEADINGS = (
    "## 1. 이 도구가 하는 일과 하지 않는 일",
    "## 2. 10분 빠른 시작 — Excel",
    "## 3. 회사 입력 규칙",
    "## 4. 어떤 회사들이 서로 비교 가능한가",
    "## 5. 결과 읽는 순서",
    "## 6. 점수차를 경제적으로 해석하는 법",
    "## 7. 합성 예시 재현",
    "## 9. 자주 발생하는 오류와 해결",
    "## 10. 버전 확인과 변경관리",
)

REQUIRED_GUIDE_PHRASES = (
    "Research Beta",
    "고정 앵커",
    "가중합 0.001",
    "비용 0.1%",
    "기업 백분위 0.1%",
    "규제·시장 feature 하나의 기준분포 위치 약 0.9%p",
    "위험 feature 하나의 약 1.2%p",
    "sector + service_scope + focal_market + reporting_period + benchmark_id",
    "역차별 가설 관련 구조적 부담격차",
    "공통규모 상당액",
    "실제규모 차이",
    "시나리오 금액",
    "never_auto_sum",
    "신뢰구간, 확률구간 또는 예측구간이 아닙니다",
    "차별, 역차별, 위법성, 손해 또는 인과효과를 판정하지 않습니다",
    "회사명이 아니라 **회사별 feature 값과 비교 메타데이터**를 직접 입력",
    "python3 scripts/cpii_simulator/build_fictional_examples.py --check",
    "python3 scripts/cpii_simulator/validate_input.py",
    "python3 scripts/cpii_simulator/run_simulation_audit.py",
    "CPII_Feature_Range_Template.csv",
)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"missing CSV header: {path.relative_to(PROJECT_ROOT)}")
        return list(reader.fieldnames), list(reader)


def schema_fields(schema_name: str) -> list[str]:
    path = PROJECT_ROOT / "data" / "registry" / schema_name
    _, rows = read_csv(path)
    fields = [row["field_name"].strip() for row in rows]
    if not fields or any(not field for field in fields):
        raise ValueError(f"invalid schema fields: {path.relative_to(PROJECT_ROOT)}")
    return fields


def validate_templates() -> list[str]:
    messages: list[str] = []
    delivery_dir = PROJECT_ROOT / "outputs" / "client_delivery"
    for template_name, schema_name in TEMPLATE_SPECS.items():
        path = delivery_dir / template_name
        actual_header, rows = read_csv(path)
        expected_header = schema_fields(schema_name)
        if actual_header != expected_header:
            raise ValueError(
                f"template header mismatch: {template_name}; "
                f"expected {expected_header!r}, got {actual_header!r}"
            )
        if rows:
            raise ValueError(f"delivery template must be header-only: {template_name}")
        messages.append(f"{template_name}={len(actual_header)} fields")

    example_map = {
        "CPII_Input_Template.csv": "fictional_companies.csv",
        "CPII_Economic_Exposure_Template.csv": "fictional_exposures.csv",
        "CPII_Feature_Provenance_Template.csv": "fictional_feature_provenance.csv",
        "CPII_Feature_Range_Template.csv": "fictional_feature_ranges.csv",
    }
    input_dir = PROJECT_ROOT / "data" / "processed" / "cpii_simulator" / "examples"
    for template_name, example_name in example_map.items():
        template_header, _ = read_csv(delivery_dir / template_name)
        example_header, example_rows = read_csv(input_dir / example_name)
        if template_header != example_header:
            raise ValueError(f"template/example header mismatch: {template_name} vs {example_name}")
        if not example_rows:
            raise ValueError(f"fictional example is empty: {example_name}")
    return messages


def validate_guide() -> str:
    text = GUIDE_PATH.read_text(encoding="utf-8")
    for required in REQUIRED_GUIDE_HEADINGS + REQUIRED_GUIDE_PHRASES:
        if required not in text:
            raise ValueError(f"guide is missing required content: {required!r}")
    if "/Users/" in text or "GoogleDrive" in text:
        raise ValueError("guide contains a workstation-specific path")

    anchor = json.loads(ANCHOR_PATH.read_text(encoding="utf-8"))
    for version in (anchor["product_spec_version"], anchor["anchor_version"]):
        if version not in text:
            raise ValueError(f"guide omits version {version}")
    if anchor["release_status"] != "research_beta_due_to_low_support_active_features":
        raise ValueError("unexpected anchor release status")
    joint = anchor["source"]["joint_support"]
    if f"{joint['complete_row_count']}행" not in text or f"{anchor['source']['row_count']}행 중" not in text:
        raise ValueError("guide omits joint-support counts")

    with (EXAMPLE_DIR / "company_scores.csv").open("r", encoding="utf-8", newline="") as handle:
        scores = {row["observation_id"]: float(row["CPII"]) for row in csv.DictReader(handle)}
    expected_score_fragments = (f"{scores['SYN-A']:.2f}", f"{scores['SYN-B']:.2f}")
    if any(fragment not in text for fragment in expected_score_fragments):
        raise ValueError("guide's fictional Excel check does not match generated scores")

    with (EXAMPLE_DIR / "golden_equal_gap_summary.csv").open("r", encoding="utf-8", newline="") as handle:
        golden = list(csv.DictReader(handle))
    if len(golden) != 2:
        raise ValueError("expected two golden equal-gap rows")
    gaps = [float(row["delta_cpii_points"]) for row in golden]
    amounts = [float(row["common_size_amount_base_krw"]) for row in golden]
    if abs(gaps[0] - gaps[1]) > 1e-9:
        raise ValueError("golden CPII gaps are no longer equal")
    guide_numbers = (f"{gaps[0]:.4f}", f"{amounts[0] / 100_000_000:.2f}억원", f"{amounts[1] / 100_000_000:.2f}억원")
    if any(number not in text for number in guide_numbers):
        raise ValueError("guide's golden economic example is stale")
    return f"guide={len(text.splitlines())} lines; versions and synthetic checks current"


def validate_workbook_presence() -> str:
    if not WORKBOOK_PATH.exists() or WORKBOOK_PATH.stat().st_size == 0:
        raise ValueError("client workbook is missing or empty")
    if not zipfile.is_zipfile(WORKBOOK_PATH):
        raise ValueError("client workbook is not a valid OOXML package")
    with zipfile.ZipFile(WORKBOOK_PATH) as archive:
        names = set(archive.namelist())
        if "xl/workbook.xml" not in names:
            raise ValueError("client workbook package lacks xl/workbook.xml")
        if any(name.lower().endswith("vbaproject.bin") for name in names):
            raise ValueError("client workbook unexpectedly contains VBA")
        package_text = "\n".join(
            archive.read(name).decode("utf-8", errors="ignore")
            for name in names
            if name.lower().endswith((".xml", ".rels", ".txt", ".json", ".csv"))
        )
        if WORKBOOK_VERSION not in package_text:
            raise ValueError(f"client workbook is not {WORKBOOK_VERSION}")
    return f"workbook={WORKBOOK_PATH.stat().st_size} bytes; OOXML macro-free"


def validate_example_reproducibility() -> str:
    command = [sys.executable, "scripts/cpii_simulator/build_fictional_examples.py", "--check"]
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stdout + "\n" + result.stderr).strip()
        raise ValueError(f"fictional example check failed: {detail}")
    if "PASS fictional examples" not in result.stdout:
        raise ValueError("fictional example check returned no PASS marker")
    return result.stdout.strip()


def main() -> int:
    try:
        template_messages = validate_templates()
        guide_message = validate_guide()
        workbook_message = validate_workbook_presence()
        example_message = validate_example_reproducibility()
    except (OSError, ValueError, KeyError, csv.Error, json.JSONDecodeError) as exc:
        print(f"FAIL delivery docs: {exc}", file=sys.stderr)
        return 1
    print("PASS delivery docs")
    for message in template_messages:
        print(f"- {message}")
    print(f"- {guide_message}")
    print(f"- {workbook_message}")
    print(f"- {example_message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
