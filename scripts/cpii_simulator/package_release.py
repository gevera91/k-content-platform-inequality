#!/usr/bin/env python3
"""Build and independently verify the versioned CPII customer release bundle."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from xml.etree import ElementTree


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RELEASE_DIR = PROJECT_ROOT / "outputs" / "client_delivery" / "CPII_Comparator_v1"
RELEASE_VERSION = "CPII_Comparator_v1"
METHOD_VERSION = "CPII_FIRM_INPUT_EQW_V1"
ANCHOR_VERSION = "POOL_SCQ_P01_P99_EMP_RANK_V1"
WORKBOOK_VERSION = "CPII_COMPARATOR_XLSX_V1.0.1"
EXPECTED_SHEETS = [
    "00_README",
    "01_INPUT_COMPANIES",
    "02_INPUT_ECON_BASES",
    "03_COMPARE_2",
    "04_COMPARE_N",
    "05_ECON_INTERPRET",
    "06_SENSITIVITY",
    "07_INPUT_PROVENANCE",
    "90_CALC_FEATURES",
    "91_CALC_SCORES",
    "92_REF_VARIABLES",
    "93_REF_ANCHORS",
    "94_EXPECTED_OUTPUTS",
    "99_QA_AUDIT",
]
MINIMUM_FORMULA_COUNT = 10_000
EXPECTED_PDF_PAGES = 131
EXPECTED_PDF_SHA256 = "f2f776af11b2d271859b532fd830e010b7c1187fc7e49064d22b376d1fa1f73a"
FORMULA_CONTRACT = {
    ("01_INPUT_COMPANIES", "AD7"): ("91_CALC_SCORES", "$AB$7"),
    ("02_INPUT_ECON_BASES", "AA7"): (
        "ERROR: LOW/BASE/HIGH",
        "ERROR: COMPANY CURRENCY/YEAR",
        "ERROR: TRANSFER ASSUMPTION",
    ),
    ("03_COMPARE_2", "A14"): (
        "N/A: 동일 관측 선택",
        "N/A: 입력 검증 실패",
        "N/A: ID 없음/중복",
    ),
    ("03_COMPARE_2", "D8"): ('$A$14<>"비교 가능"',),
    ("04_COMPARE_N", "E7"): ("COUNTIFS", "-1)/2"),
    ("04_COMPARE_N", "J7"): ("N/A:input", "N/A:cohort"),
    ("05_ECON_INTERPRET", "I8"): (
        "PAIR NOT COMPARABLE",
        "MISSING EXPOSURE",
        "TIME BASIS MISMATCH",
    ),
    ("06_SENSITIVITY", "B8"): ("03_COMPARE_2", "비교 가능"),
    ("90_CALC_FEATURES", "E7"): ("COUNT(", "$T$7", "01_INPUT_COMPANIES"),
    ("91_CALC_SCORES", "AB7"): (
        "ERROR: DUPLICATE ID",
        "ERROR: BENCHMARK",
        "ERROR: EXPOSURE ADJUSTMENT",
    ),
}
PRIVATE_MARKERS = (
    "/" + "Users/",
    "Google" + "Drive-",
    "Downloads" + "/tmp",
    "mialphakorea" + "@gmail.com",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_map(project_root: Path) -> list[tuple[Path, Path]]:
    pairs: list[tuple[str, str]] = [
        ("docs/cpii_comparator_start_here.md", "START_HERE.md"),
        ("docs/cpii_comparator_release_notes.md", "RELEASE_NOTES.md"),
        ("docs/cpii_comparator_user_guide.md", "CPII_Comparator_User_Guide.md"),
        ("outputs/client_delivery/CPII_Company_Comparator.xlsx", "CPII_Company_Comparator.xlsx"),
        ("outputs/client_delivery/CPII_Input_Template.csv", "CPII_Input_Template.csv"),
        ("outputs/client_delivery/CPII_Economic_Exposure_Template.csv", "CPII_Economic_Exposure_Template.csv"),
        ("outputs/client_delivery/CPII_Feature_Provenance_Template.csv", "CPII_Feature_Provenance_Template.csv"),
        ("outputs/client_delivery/CPII_Feature_Range_Template.csv", "CPII_Feature_Range_Template.csv"),
        ("build/kakao_enter.pdf", "Kakao_Enter_Report_with_CPII_Comparator_Appendix.pdf"),
        ("docs/cpii_simulator_design_decisions.md", "methodology/cpii_simulator_design_decisions.md"),
        ("outputs/tables/cpii_simulator/appendix/cpii_interpretation_appendix.tex", "methodology/cpii_interpretation_appendix.tex"),
        ("outputs/tables/spec_robustness_summary.csv", "outputs/tables/spec_robustness_summary.csv"),
        ("logs/cpii_simulator_release_qa.md", "validation/cpii_simulator_release_qa.md"),
        ("logs/cpii_simulator_simulation_audit.md", "validation/cpii_simulator_simulation_audit.md"),
        ("logs/cpii_research_team_synthesis.md", "validation/cpii_research_team_synthesis.md"),
        ("logs/cpii_simulator_workbook_qa/workbook_audit.json", "validation/workbook_audit.json"),
        ("logs/cpii_fictional_example_generation.md", "logs/cpii_fictional_example_generation.md"),
        ("logs/cpii_simulator_anchor_manifest.md", "validation/cpii_simulator_anchor_manifest.md"),
        ("logs/cpii_simulator_variable_reconciliation.md", "validation/cpii_simulator_variable_reconciliation.md"),
        ("scripts/cpii_simulator/package_release.py", "verify_release.py"),
    ]

    registry_names = [
        "cpii_simulator_variable_dictionary.csv",
        "cpii_simulator_input_schema.csv",
        "cpii_economic_exposure_schema.csv",
        "cpii_feature_provenance_schema.csv",
        "cpii_feature_range_schema.csv",
        "cpii_benchmark_registry.csv",
        "cpii_feature_dependency_registry.csv",
        "cpii_economic_bridge_registry.csv",
    ]
    pairs.extend((f"data/registry/{name}", f"data/registry/{name}") for name in registry_names)

    anchor_names = [
        f"{ANCHOR_VERSION}.json",
        f"{ANCHOR_VERSION}_reference_values.csv",
        "anchor_manifest.json",
    ]
    pairs.extend(
        (f"data/processed/cpii_simulator/anchor/{name}", f"data/processed/cpii_simulator/anchor/{name}")
        for name in anchor_names
    )

    input_names = [
        "fictional_companies.csv",
        "fictional_exposures.csv",
        "fictional_feature_provenance.csv",
        "fictional_feature_ranges.csv",
        "golden_equal_gap_companies.csv",
        "golden_equal_gap_exposures.csv",
    ]
    pairs.extend(
        (f"data/processed/cpii_simulator/examples/{name}", f"data/processed/cpii_simulator/examples/{name}")
        for name in input_names
    )

    example_output_names = [
        "company_ranking.csv",
        "company_scores.csv",
        "economic_interpretations.csv",
        "example_manifest.json",
        "golden_equal_gap_summary.csv",
        "pair_contributions.csv",
        "pair_gap_matrix.csv",
        "pair_gaps.csv",
        "pair_narratives.csv",
        "sensitivity_summary.csv",
        "sensitivity_variants.csv",
    ]
    pairs.extend(
        (f"outputs/tables/cpii_simulator/examples/{name}", f"outputs/tables/cpii_simulator/examples/{name}")
        for name in example_output_names
    )

    reproduction_scripts = [
        "__init__.py",
        "build_fictional_examples.py",
        "cli.py",
        "compare.py",
        "decompose.py",
        "economic_bridge.py",
        "engine.py",
        "narrative.py",
        "run_simulation_audit.py",
        "sensitivity.py",
        "validate_input.py",
    ]
    pairs.extend(
        (f"scripts/cpii_simulator/{name}", f"scripts/cpii_simulator/{name}")
        for name in reproduction_scripts
    )

    resolved = [(project_root / source, Path(destination)) for source, destination in pairs]
    destinations = [str(destination) for _, destination in resolved]
    if len(destinations) != len(set(destinations)):
        raise ValueError("duplicate release destination in package allowlist")
    return resolved


def write_manifest(release_dir: Path) -> None:
    manifest_path = release_dir / "SHA256SUMS.csv"
    files = sorted(
        path for path in release_dir.rglob("*")
        if path.is_file() and path != manifest_path
    )
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "size_bytes", "sha256"])
        writer.writeheader()
        for path in files:
            writer.writerow(
                {
                    "path": path.relative_to(release_dir).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )


def _read_manifest(release_dir: Path) -> list[dict[str, str]]:
    path = release_dir / "SHA256SUMS.csv"
    if not path.is_file():
        raise ValueError("missing SHA256SUMS.csv")
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or set(rows[0]) != {"path", "size_bytes", "sha256"}:
        raise ValueError("invalid SHA256SUMS.csv schema")
    return rows


def _safe_relative(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute() or not raw or ".." in path.parts or path.as_posix() != raw:
        raise ValueError(f"unsafe manifest path: {raw!r}")
    return path


def _verify_workbook(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        lowered = [name.lower() for name in names]
        forbidden_parts = ("vbaproject.bin", "xl/externallinks/", "xl/connections.xml")
        hits = [name for name, lower in zip(names, lowered) if any(part in lower for part in forbidden_parts)]
        if hits:
            raise ValueError(f"workbook contains macro/external-link parts: {hits}")

        workbook_xml = archive.read("xl/workbook.xml")
        root = ElementTree.fromstring(workbook_xml)
        sheet_nodes = root.findall(".//{*}sheet")
        sheet_names = [node.attrib["name"] for node in sheet_nodes]
        if sheet_names != EXPECTED_SHEETS:
            raise ValueError(f"workbook sheet contract mismatch: {sheet_names}")

        relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {
            node.attrib["Id"]: node.attrib["Target"]
            for node in relationships.findall(".//{*}Relationship")
        }
        sheet_parts: dict[str, str] = {}
        relationship_key = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        for node in sheet_nodes:
            target = targets[node.attrib[relationship_key]].lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            sheet_parts[node.attrib["name"]] = target

        formula_count = 0
        error_cells: list[str] = []
        formulas: dict[tuple[str, str], str] = {}
        oversized: list[str] = []
        formula_error_tokens: list[str] = []
        error_pattern = re.compile(
            r"#REF!|#DIV/0!|#VALUE!|#NAME\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!|"
            r"#FIELD!|#BLOCKED!|#UNKNOWN!|#CONNECT!|#GETTING_DATA|#ERROR!|#CIRC!|"
            r"#NOT_IMPLEMENTED!|#TRACE!|#BUSY!|#DATA!|#PYTHON!",
            flags=re.IGNORECASE,
        )
        for sheet_name, member_name in sheet_parts.items():
            sheet_root = ElementTree.fromstring(archive.read(member_name))
            formula_count += len(sheet_root.findall(".//{*}f"))
            for cell in sheet_root.findall(".//{*}c"):
                if cell.attrib.get("t") == "e":
                    error_cells.append(cell.attrib.get("r", "unknown"))
                formula = cell.find("{*}f")
                if formula is None:
                    continue
                formula_text = formula.text or ""
                address = cell.attrib.get("r", "unknown").upper()
                formulas[(sheet_name, address)] = formula_text
                if len(formula_text) > 8192:
                    oversized.append(f"{sheet_name}!{address}")
                if error_pattern.search(formula_text):
                    formula_error_tokens.append(f"{sheet_name}!{address}")
        if formula_count < MINIMUM_FORMULA_COUNT:
            raise ValueError(
                f"workbook formula count {formula_count} is below the minimum "
                f"{MINIMUM_FORMULA_COUNT}"
            )
        if error_cells:
            raise ValueError(f"workbook cached error cells: {error_cells[:10]}")
        if oversized:
            raise ValueError(f"workbook formulas exceed Excel's length limit: {oversized[:10]}")
        if formula_error_tokens:
            raise ValueError(f"workbook formulas contain literal error tokens: {formula_error_tokens[:10]}")
        contract_failures = []
        for key, required_tokens in FORMULA_CONTRACT.items():
            formula = formulas.get(key, "")
            missing = [token for token in required_tokens if token not in formula]
            if not formula or missing:
                contract_failures.append(f"{key[0]}!{key[1]} missing {missing or ['formula']}")
        if contract_failures:
            raise ValueError("workbook critical-formula contract mismatch: " + "; ".join(contract_failures))

        joined = b"\n".join(archive.read(name) for name in names if name.endswith((".xml", ".rels")))
        text = joined.decode("utf-8", errors="ignore")
        if 'TargetMode="External"' in text:
            raise ValueError("workbook contains an external relationship")
        for marker in PRIVATE_MARKERS:
            if marker in text:
                raise ValueError(f"workbook contains private path marker {marker!r}")
        for required in (WORKBOOK_VERSION, METHOD_VERSION, ANCHOR_VERSION, "research_beta_due_to_low_support_active_features"):
            if required not in text:
                raise ValueError(f"workbook is missing required version/status string {required!r}")
    return {"sheet_count": len(sheet_names), "formula_count": formula_count}


def _verify_pdf(path: Path) -> dict[str, object]:
    missing_tools = [tool for tool in ("pdfinfo", "pdftotext") if shutil.which(tool) is None]
    if missing_tools:
        if sha256(path) != EXPECTED_PDF_SHA256:
            raise ValueError(
                "Poppler is unavailable and the PDF does not match the frozen release SHA-256; "
                "install command(s): " + ", ".join(missing_tools)
            )
        return {
            "pages": EXPECTED_PDF_PAGES,
            "size_bytes": path.stat().st_size,
            "content_check": "PASS_frozen_sha256_fallback",
        }
    if path.stat().st_size < 1_000_000 or path.read_bytes()[:5] != b"%PDF-":
        raise ValueError("final report is not the expected non-trivial PDF")
    info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=False)
    if info.returncode != 0:
        raise ValueError(f"pdfinfo failed: {info.stderr.strip()}")
    match = re.search(r"^Pages:\s+(\d+)\s*$", info.stdout, flags=re.MULTILINE)
    if not match or int(match.group(1)) != EXPECTED_PDF_PAGES:
        raise ValueError(f"PDF page count is not {EXPECTED_PDF_PAGES}")
    extracted = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True, check=False)
    if extracted.returncode != 0:
        raise ValueError(f"pdftotext failed: {extracted.stderr.strip()}")
    for marker in PRIVATE_MARKERS:
        if marker in extracted.stdout:
            raise ValueError(f"PDF contains private path marker {marker!r}")
    for required in ("Research Beta", "0.10", "1.3889", "997.52", "2.00"):
        if required not in extracted.stdout:
            raise ValueError(f"PDF is missing required appendix evidence {required!r}")
    return {
        "pages": EXPECTED_PDF_PAGES,
        "size_bytes": path.stat().st_size,
        "content_check": "PASS_poppler",
    }


def _verify_examples(release_dir: Path) -> dict[str, object]:
    companies_path = release_dir / "data/processed/cpii_simulator/examples/fictional_companies.csv"
    pairs_path = release_dir / "outputs/tables/cpii_simulator/examples/pair_gaps.csv"
    golden_path = release_dir / "outputs/tables/cpii_simulator/examples/golden_equal_gap_summary.csv"
    with companies_path.open("r", encoding="utf-8", newline="") as handle:
        companies = list(csv.DictReader(handle))
    with pairs_path.open("r", encoding="utf-8", newline="") as handle:
        pairs = list(csv.DictReader(handle))
    with golden_path.open("r", encoding="utf-8", newline="") as handle:
        golden = list(csv.DictReader(handle))
    if len(companies) != 4 or len(pairs) != 6 or len(golden) != 2:
        raise ValueError("synthetic example cardinality mismatch")
    if any(row.get("synthetic_flag") != "yes" or row.get("input_quality") != "SYNTHETIC" for row in companies):
        raise ValueError("release contains a non-synthetic company example")

    check = subprocess.run(
        [sys.executable, "scripts/cpii_simulator/build_fictional_examples.py", "--check"],
        cwd=release_dir,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    if check.returncode != 0 or "PASS fictional examples" not in check.stdout:
        raise ValueError(f"standalone fictional-example check failed: {check.stdout}\n{check.stderr}")
    return {"company_count": 4, "unordered_pair_count": 6, "golden_pair_count": 2}


def verify_release(release_dir: Path, require_package_record: bool = True) -> dict[str, object]:
    release_dir = release_dir.resolve()
    if not release_dir.is_dir():
        raise ValueError(f"release directory not found: {release_dir}")
    for path in release_dir.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"symlink is forbidden in release: {path.relative_to(release_dir)}")
        if path.is_file() and path.stat().st_mode & 0o444 != 0o444:
            raise ValueError(f"release file is not world-readable: {path.relative_to(release_dir)}")

    rows = _read_manifest(release_dir)
    listed: set[str] = set()
    for row in rows:
        relative = _safe_relative(row["path"])
        raw = relative.as_posix()
        if raw in listed:
            raise ValueError(f"duplicate manifest path: {raw}")
        listed.add(raw)
        path = release_dir / relative
        if not path.is_file():
            raise ValueError(f"missing release file: {raw}")
        if path.stat().st_size != int(row["size_bytes"]):
            raise ValueError(f"size mismatch: {raw}")
        if sha256(path) != row["sha256"]:
            raise ValueError(f"SHA-256 mismatch: {raw}")

    actual = {
        path.relative_to(release_dir).as_posix()
        for path in release_dir.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS.csv"
    }
    if actual != listed:
        raise ValueError(f"manifest file-set mismatch: missing={sorted(actual-listed)}, extra={sorted(listed-actual)}")

    required_files = {
        "START_HERE.md",
        "RELEASE_NOTES.md",
        "CPII_Comparator_User_Guide.md",
        "CPII_Company_Comparator.xlsx",
        "CPII_Input_Template.csv",
        "CPII_Economic_Exposure_Template.csv",
        "CPII_Feature_Provenance_Template.csv",
        "CPII_Feature_Range_Template.csv",
        "Kakao_Enter_Report_with_CPII_Comparator_Appendix.pdf",
        "validation/cpii_simulator_release_qa.md",
        "validation/cpii_simulator_simulation_audit.md",
        "validation/workbook_audit.json",
        "verify_release.py",
    }
    if require_package_record:
        required_files.add("validation/package_verification.json")
    missing_required = required_files - actual
    if missing_required:
        raise ValueError(f"required release files missing: {sorted(missing_required)}")

    text_suffixes = {".md", ".csv", ".json", ".py", ".tex"}
    for path in sorted(release_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in text_suffixes:
            continue
        text = path.read_text(encoding="utf-8")
        for marker in PRIVATE_MARKERS:
            if marker in text:
                raise ValueError(f"private path marker {marker!r} in {path.relative_to(release_dir)}")

    for doc_name in ("START_HERE.md", "RELEASE_NOTES.md", "CPII_Comparator_User_Guide.md"):
        doc = (release_dir / doc_name).read_text(encoding="utf-8")
        for required in ("Research Beta", METHOD_VERSION, ANCHOR_VERSION):
            if required not in doc:
                raise ValueError(f"{doc_name} missing {required!r}")

    audit = json.loads((release_dir / "validation/workbook_audit.json").read_text(encoding="utf-8"))
    if audit.get("audit_schema_version") != "CPII_WORKBOOK_AUDIT_V1" or audit.get("status") != "PASS":
        raise ValueError("bundled workbook audit schema/status is not an accepted PASS")
    if not all(section.get("passed") for section in audit.get("checks", {}).values()):
        raise ValueError("bundled workbook audit contains a failed section")

    workbook = _verify_workbook(release_dir / "CPII_Company_Comparator.xlsx")
    if audit.get("workbook", {}).get("sha256") != sha256(
        release_dir / "CPII_Company_Comparator.xlsx"
    ):
        raise ValueError("bundled workbook audit is not bound to the bundled workbook")
    if audit["checks"]["formulas"]["total_formula_records"] != workbook["formula_count"]:
        raise ValueError("bundled workbook audit formula count does not match workbook")
    if not audit.get("checks", {}).get("formula_contract", {}).get("passed"):
        raise ValueError("bundled workbook audit lacks a passing critical-formula contract")
    pdf = _verify_pdf(release_dir / "Kakao_Enter_Report_with_CPII_Comparator_Appendix.pdf")
    examples = _verify_examples(release_dir)
    if require_package_record:
        package_record = json.loads(
            (release_dir / "validation/package_verification.json").read_text(encoding="utf-8")
        )
        if package_record.get("status") != "PASS" or package_record.get("release_version") != RELEASE_VERSION:
            raise ValueError("package verification record is not a PASS for this release")
        if package_record.get("expected_final_file_count") != len(actual) + 1:
            raise ValueError("package verification record file count mismatch")
        if package_record.get("workbook_sha256") != sha256(release_dir / "CPII_Company_Comparator.xlsx"):
            raise ValueError("package verification record workbook hash mismatch")
        if package_record.get("pdf_sha256") != sha256(
            release_dir / "Kakao_Enter_Report_with_CPII_Comparator_Appendix.pdf"
        ):
            raise ValueError("package verification record PDF hash mismatch")
    return {
        "release_version": RELEASE_VERSION,
        "file_count": len(actual) + 1,
        "workbook": workbook,
        "pdf": pdf,
        "examples": examples,
        "privacy_scan": "PASS",
        "manifest": "PASS",
    }


def build_release(project_root: Path, release_dir: Path, replace: bool) -> dict[str, object]:
    project_root = project_root.resolve()
    release_dir = release_dir.resolve()
    allowed_parent = (project_root / "outputs" / "client_delivery").resolve()
    if release_dir.parent != allowed_parent or release_dir.name != RELEASE_VERSION:
        raise ValueError(f"build target must be exactly {allowed_parent / RELEASE_VERSION}")
    if release_dir.exists() and not replace:
        raise ValueError(f"release already exists; verify it or rebuild with --replace: {release_dir}")

    release_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{RELEASE_VERSION}.", dir=release_dir.parent))
    try:
        for source, destination in copy_map(project_root):
            if not source.is_file() or source.is_symlink():
                raise ValueError(f"required source missing or unsafe: {source.relative_to(project_root)}")
            target = temporary / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            target.chmod(0o644)
        write_manifest(temporary)
        (temporary / "SHA256SUMS.csv").chmod(0o644)
        preliminary = verify_release(temporary, require_package_record=False)
        package_record = {
            "schema_version": "CPII_RELEASE_VERIFICATION_V1",
            "release_version": RELEASE_VERSION,
            "release_date": "2026-09-03",
            "status": "PASS",
            "expected_final_file_count": preliminary["file_count"] + 1,
            "manifest_check": preliminary["manifest"],
            "privacy_scan": preliminary["privacy_scan"],
            "workbook": preliminary["workbook"],
            "workbook_sha256": sha256(temporary / "CPII_Company_Comparator.xlsx"),
            "pdf": preliminary["pdf"],
            "pdf_sha256": sha256(temporary / "Kakao_Enter_Report_with_CPII_Comparator_Appendix.pdf"),
            "examples": preliminary["examples"],
            "note": "Created after preliminary standalone verification; the final manifest including this record was then verified again.",
        }
        record_path = temporary / "validation/package_verification.json"
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(
            json.dumps(package_record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        record_path.chmod(0o644)
        write_manifest(temporary)
        (temporary / "SHA256SUMS.csv").chmod(0o644)
        result = verify_release(temporary)
        if release_dir.exists():
            shutil.rmtree(release_dir)
        temporary.replace(release_dir)
        return result
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path, help="verify an existing release directory")
    parser.add_argument("--output", type=Path, default=DEFAULT_RELEASE_DIR, help="build destination")
    parser.add_argument("--replace", action="store_true", help="replace the exact generated v1 directory")
    args = parser.parse_args()
    try:
        if args.verify:
            result = verify_release(args.verify)
            action = "verified"
        else:
            result = build_release(PROJECT_ROOT, args.output, args.replace)
            action = "built and verified"
    except (OSError, ValueError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f"FAIL CPII release: {exc}", file=sys.stderr)
        return 1
    print(f"PASS CPII release {action}: {json.dumps(result, ensure_ascii=False, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
