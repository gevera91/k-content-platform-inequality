#!/usr/bin/env python3
"""Package or verify the comparator v2 without modifying the v1 release."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
VERSION = "CPII_COMPARATOR_XLSX_V2.0.0"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files(root):
    return sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.name != "SHA256SUMS.csv")


def dump(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pdf_pages(path):
    info = subprocess.check_output(["pdfinfo", str(path)], text=True)
    return int(re.search(r"^Pages:\s+(\d+)", info, re.M)[1])


def verify(release):
    release = release.resolve()
    for path in release.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"symlink in package: {path.name}")
    with (release / "SHA256SUMS.csv").open(newline="", encoding="utf-8") as handle:
        manifest = list(csv.DictReader(handle))
    listed = set()
    for item in manifest:
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts or relative.as_posix() in listed:
            raise ValueError("invalid or duplicate manifest path")
        listed.add(relative.as_posix())
        source = release / relative
        if source.stat().st_size != int(item["size_bytes"]) or digest(source) != item["sha256"]:
            raise ValueError(f"integrity mismatch: {relative}")
    if listed != {p.relative_to(release).as_posix() for p in files(release)}:
        raise ValueError("manifest file-set mismatch")
    sys.path.insert(0, str(release))
    from scripts.cpii_simulator import package_release as checks
    checks.WORKBOOK_VERSION = VERSION
    checks.FORMULA_CONTRACT[("04_COMPARE_N", "E7")] = ("SUM", "AN7:AO7", "-1/2")
    checks.FORMULA_CONTRACT[("04_COMPARE_N", "AN7")] = ("EXACT", "ISNUMBER")
    checks.FORMULA_CONTRACT[("91_CALC_SCORES", "AD7")] = ("ERROR: SOURCE DATE", "ERROR: EXACT ENUM")
    workbook = release / "CPII_Company_Comparator.xlsx"
    structure = checks._verify_workbook(workbook)
    audit = json.loads((release / "validation/workbook_audit.json").read_text())
    regression = json.loads((release / "validation/v2_regressions.json").read_text())
    for record in (audit["workbook"], regression):
        if record["sha256"] != digest(workbook):
            raise ValueError("workbook audit does not correspond to packaged XLSX")
    if audit["status"] != "PASS" or regression["failures"]:
        raise ValueError("v2 workbook audit or regression failure")
    examples = checks._verify_examples(release)
    metadata = json.loads((release / "RELEASE_METADATA.json").read_text())
    for name, record in metadata["pdfs"].items():
        path = release / name
        if digest(path) != record["sha256"]:
            raise ValueError("PDF integrity mismatch")
        if shutil.which("pdfinfo") and pdf_pages(path) != record["pages"]:
            raise ValueError("PDF page count mismatch")
        if shutil.which("pdftotext"):
            text = subprocess.check_output(["pdftotext", str(path), "-"], text=True)
            if "CPII 기업 비교기 v2" not in text:
                raise ValueError("missing v2 report section")
    for path in files(release):
        if path.suffix in {".md", ".json", ".csv", ".py", ".mjs", ".tex"}:
            content = path.read_text(encoding="utf-8")
            if re.search(r"/(?:Users|home)/[^\s]+|GoogleDrive[-]", content):
                raise ValueError(f"private absolute path in {path.name}")
    return {"release": "CPII_Comparator_v2", "files": len(listed), "workbook": structure, "examples": examples, "regression_cases": regression["case_count"], "regression_assertions": regression["assertion_count"], "pdfs": {k:v["pages"] for k,v in metadata["pdfs"].items()}, "status": "PASS"}


def build(root):
    release = root / "outputs/client_delivery/CPII_Comparator_v2"
    if (release / "SHA256SUMS.csv").exists():
        raise ValueError("v2 already sealed; do not overwrite an existing release")
    workbook = release / "CPII_Company_Comparator.xlsx"
    if not workbook.exists():
        raise ValueError("build the v2 workbook before packaging")
    mapping = {
        "docs/cpii_comparator_v2_start_here.md": "START_HERE.md",
        "docs/cpii_comparator_v2_guide.md": "CPII_Comparator_User_Guide.md",
        "docs/cpii_comparator_v2_release_notes.md": "RELEASE_NOTES.md",
        "build/kakao_enter.pdf": "Kakao_Enter_Report_with_CPII_Comparator_Appendix.pdf",
        "build/kakao_enter_summary.pdf": "Kakao_Enter_Summary.pdf",
        "cpii_comparator_v2_section.tex": "methodology/cpii_comparator_v2_section.tex",
        "docs/cpii_simulator_design_decisions.md": "methodology/cpii_simulator_design_decisions.md",
        "outputs/tables/spec_robustness_summary.csv": "outputs/tables/spec_robustness_summary.csv",
        "logs/cpii_comparator_v2/v1_regressions.json": "validation/v1_regressions.json",
        "logs/cpii_comparator_v2/v2_regressions.json": "validation/v2_regressions.json",
        "logs/cpii_comparator_v2/v2_workbook/workbook_audit.json": "validation/workbook_audit.json",
        "logs/cpii_comparator_v2/python_tests.log": "validation/python_tests.log",
        "logs/cpii_comparator_v2/libreoffice_cached_check.json": "validation/libreoffice_cached_check.json",
        "logs/cpii_fictional_example_generation.md": "logs/cpii_fictional_example_generation.md",
        "scripts/cpii_simulator/package_v2.py": "verify_release.py",
    }
    for name in ("CPII_Input_Template.csv", "CPII_Economic_Exposure_Template.csv", "CPII_Feature_Provenance_Template.csv", "CPII_Feature_Range_Template.csv"):
        mapping[f"outputs/client_delivery/{name}"] = name
    for relative, pattern in (("data/registry", "cpii_*.csv"), ("data/processed/cpii_simulator/anchor", "*"), ("data/processed/cpii_simulator/examples", "*.csv"), ("outputs/tables/cpii_simulator/examples", "*"), ("outputs/tables/cpii_simulator/workbook", "*.json")):
        for source in (root / relative).glob(pattern):
            if source.is_file():
                mapping[source.relative_to(root).as_posix()] = source.relative_to(root).as_posix()
    scripts = ("__init__.py", "engine.py", "cli.py", "compare.py", "decompose.py", "economic_bridge.py", "narrative.py", "sensitivity.py", "validate_input.py", "build_fictional_examples.py", "build_workbook_payload.py", "build_workbook.mjs", "verify_workbook.mjs", "audit_v2_regressions.mjs", "check_recalculated_v2.py", "package_release.py")
    for name in scripts:
        mapping[f"scripts/cpii_simulator/{name}"] = f"scripts/cpii_simulator/{name}"
    for source, target in mapping.items():
        destination = release / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / source, destination)
        destination.chmod(0o644)
    payload_path = release / "outputs/tables/cpii_simulator/workbook/workbook_payload.json"
    payload = json.loads(payload_path.read_text())
    payload["metadata"]["workbook_version"] = VERSION
    dump(payload_path, payload)
    metadata = {"release": "CPII_Comparator_v2", "date": "2026-09-15", "workbook_version": VERSION, "method_version": "CPII_FIRM_INPUT_EQW_V1", "anchor_version": "POOL_SCQ_P01_P99_EMP_RANK_V1", "v1_manifest_sha256": digest(root / "outputs/client_delivery/CPII_Comparator_v1/SHA256SUMS.csv"), "pdfs": {}}
    for name in ("Kakao_Enter_Report_with_CPII_Comparator_Appendix.pdf", "Kakao_Enter_Summary.pdf"):
        path = release / name
        metadata["pdfs"][name] = {"sha256": digest(path), "pages": pdf_pages(path)}
    dump(release / "RELEASE_METADATA.json", metadata)
    with (release / "SHA256SUMS.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "size_bytes", "sha256"])
        writer.writeheader()
        for path in files(release):
            writer.writerow({"path": path.relative_to(release).as_posix(), "size_bytes": path.stat().st_size, "sha256": digest(path)})
    return verify(release)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--verify", type=Path)
    operation.add_argument("--build", action="store_true")
    args = parser.parse_args()
    result = verify(args.verify) if args.verify else build(ROOT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
