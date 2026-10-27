#!/usr/bin/env python3
"""Rebuild frozen-snapshot analyses in an isolated workspace and compare results."""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CORE = [
    "scripts/build_subindex_panels.py",
    "scripts/build_cpii_panels.py",
    "scripts/build_policy_scenarios.py",
    "scripts/review_strengthening_20260915.py",
]
FULL = [
    "scripts/build_spec_robustness.py",
    "scripts/build_alt_spec_cpii_panels.py",
    "scripts/build_country_comparison_tables.py",
    "scripts/build_firm_comparison_tables.py",
    "scripts/build_timeseries_analysis.py",
    "scripts/run_sector_regressions.py",
    "scripts/ofcom_proxy_sensitivity.py",
    "scripts/claim_strengthening/build_claim_pretrend_check.py",
    "scripts/claim_strengthening/build_claim_placebo_event_results.py",
    "scripts/claim_strengthening/build_claim_placebo_outcome_results.py",
]


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare_csv(reference, generated):
    left_fields, left = rows(reference)
    right_fields, right = rows(generated)
    result = {"path": reference.relative_to(ROOT).as_posix(), "rows": len(right),
              "numeric_cells": 0, "mismatches": [], "reference_sha256": sha(reference),
              "generated_sha256": sha(generated)}
    if left_fields != right_fields:
        result["mismatches"].append({"kind": "columns", "reference": left_fields, "generated": right_fields})
    if len(left) != len(right):
        result["mismatches"].append({"kind": "row_count", "reference": len(left), "generated": len(right)})
    for number, (a, b) in enumerate(zip(left, right), start=2):
        for field in left_fields:
            av, bv = a[field], b.get(field)
            if av == bv:
                try:
                    float(av)
                    result["numeric_cells"] += 1
                except (TypeError, ValueError):
                    pass
                continue
            try:
                x, y = float(av), float(bv)
                result["numeric_cells"] += 1
                equal = (math.isnan(x) and math.isnan(y)) or math.isclose(x, y, rel_tol=1e-10, abs_tol=1e-8)
            except (TypeError, ValueError):
                equal = False
            if not equal and len(result["mismatches"]) < 20:
                result["mismatches"].append({"row": number, "column": field, "reference": av, "generated": bv})
    result["passed"] = not result["mismatches"]
    return result


def report_claims(work, profile):
    checks = []
    def check(name, actual, expected, tolerance=0):
        good = math.isclose(actual, expected, abs_tol=tolerance, rel_tol=0)
        checks.append({"claim": name, "actual": actual, "expected": expected, "tolerance": tolerance, "passed": good})
    _, panel = rows(work / "data/processed/cpii_panel_sector_quarter.csv")
    grouped = defaultdict(list)
    common = defaultdict(list)
    for row in panel:
        if row["CPII"]:
            grouped[row["sector_std"]].append(float(row["CPII"]))
            if row["year_quarter"] in ("2025Q2", "2025Q3", "2025Q4"):
                common[row["sector_std"]].append(float(row["CPII"]))
    for sector, expected in {"music": 54.13, "webtoon_story": 54.23, "digital_infra": 43.00}.items():
        check("CPII full-period mean: " + sector, statistics.mean(grouped[sector]), expected, .005)
    for sector, expected in {"music": 55.845, "webtoon_story": 50.426, "digital_infra": 43.401}.items():
        check("CPII 2025Q2-Q4 mean: " + sector, statistics.mean(common[sector]), expected, .0005)
    _, policy = rows(work / "outputs/tables/review_20260915/policy_baseline_decomposition_summary.csv")
    for row in policy:
        if row["scenario"] == "NET":
            expected = {"music": 10.851, "webtoon_story": 13.205, "digital_infra": 7.877}[row["sector"]]
            check("NET same-input reduction: " + row["sector"], float(row["mean_same_input_difference"]), expected, .0005)
    _, cases = rows(work / "outputs/tables/claim_strengthening/signed_rebuild/T_signed_korea_market_case_studies.csv")
    signed = defaultdict(list)
    for row in cases:
        signed[row["sector_std"]].append(float(row["extended_signed_score"]))
        if "melon" in str(row).lower() and "spotify" in str(row).lower():
            check("Melon-Spotify core direction", float(row["core_signed_score"]), .5000, .00005)
            check("Melon-Spotify extended direction", float(row["extended_signed_score"]), .5375, .00005)
    for sector, expected in {"music": .451, "webtoon_story": .167, "digital_infra": .482}.items():
        check("Extended direction mean: " + sector, statistics.mean(signed[sector]), expected, .0005)
    _, robust = rows(work / "outputs/tables/review_20260915/signed_axis_robustness.csv")
    check("Extended cases positive after axis deletion", sum(float(r["extended_loo_min"]) > 0 for r in robust), 11)
    check("Extended cases positive across weight box", sum(float(r["extended_box_weight_min"]) > 0 for r in robust), 11)
    _, adverse = rows(work / "outputs/tables/review_20260915/policy_adverse_sensitivity_contrasts.csv")
    check("Positive adverse NET pairwise contrasts", sum(float(r["adverse_net_advantage"]) > 0 for r in adverse), 30)
    if profile == "full":
        _, pretrend = rows(work / "outputs/tables/claim_strengthening/T_claim_pretrend_check.csv")
        check("Narrow event cases failing pretrend conditions", sum(r["pretrend_pass_flag"] == "no" for r in pretrend), 9)
        _, sector_sensitivity = rows(work / "logs/ofcom_proxy_sensitivity_sector_summary.csv")
        check("Ofcom proxy exclusion maximum sector-mean change", max(abs(float(r["delta_mean_CPII"])) for r in sector_sensitivity), .868, .0005)
        _, firm_sensitivity = rows(work / "logs/ofcom_proxy_sensitivity_firm_country_uk.csv")
        check("Ofcom proxy exclusion maximum firm-row change", max(abs(float(r["delta_CPII"])) for r in firm_sensitivity if r["delta_CPII"]), 17.240, .0005)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("core", "full"), default="full")
    parser.add_argument("--output-dir", type=Path, default=Path("replication_runs") / datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--skip-tests", action="store_true", help="Skip unit tests; numerical comparisons still run")
    args = parser.parse_args()
    targets = json.loads((ROOT / "publication/REPLICATION_TARGETS.json").read_text())
    missing = [p for p in targets[args.profile] if not (ROOT / p).is_file()]
    if missing:
        parser.error("required frozen reference files are missing: " + ", ".join(missing))
    out = args.output_dir.resolve()
    if out.exists():
        parser.error("output directory already exists; choose a new directory to preserve prior runs")
    if out == ROOT or out in ROOT.parents:
        parser.error("output directory must not be the repository or its parent")
    out.mkdir(parents=True)
    work = out / "workspace"
    work.mkdir()
    copy_jobs = []
    for relative in ("scripts", "tests", "data", "outputs/tables", "spreadsheet", "docs"):
        source = ROOT / relative
        if source.exists():
            for path in source.rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                    copy_jobs.append((path, work / path.relative_to(ROOT)))
    def stage(job):
        source, destination = job
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(stage, copy_jobs))
    (work / "outputs/figures").mkdir(parents=True, exist_ok=True)
    (work / "logs").mkdir(exist_ok=True)
    (out / "logs").mkdir()
    before = {p.relative_to(work).as_posix(): p.stat().st_mtime_ns
              for folder in (work / "data/processed", work / "outputs/tables") for p in folder.rglob("*.csv")}
    summary = {"created_utc": datetime.now(timezone.utc).isoformat(), "profile": args.profile,
               "python": sys.version.split()[0], "network_required": False, "commands": [],
               "numeric_tolerance": {"absolute": 1e-8, "relative": 1e-10}}
    commands = [[sys.executable, script] for script in CORE]
    if args.profile == "full":
        commands.extend([sys.executable, script] for script in FULL)
    commands.append([sys.executable, "-m", "scripts.cpii_simulator.build_fictional_examples"])
    failed = False
    for index, command in enumerate(commands, start=1):
        logfile = out / "logs" / f"{index:02d}.log"
        with logfile.open("w") as handle:
            result = subprocess.run(command, cwd=work, stdout=handle, stderr=subprocess.STDOUT)
        summary["commands"].append({"command": ["python", *command[1:]], "exit_code": result.returncode, "log": f"logs/{index:02d}.log"})
        print(f"[{index}/{len(commands)}] {'PASS' if result.returncode == 0 else 'FAIL'} {' '.join(command[1:])}", flush=True)
        if result.returncode:
            failed = True
            break
    regenerated = [p for folder in (work / "data/processed", work / "outputs/tables") for p in folder.rglob("*.csv")
                   if before.get(p.relative_to(work).as_posix()) != p.stat().st_mtime_ns]
    comparisons = []
    for path in sorted(regenerated):
        reference = ROOT / path.relative_to(work)
        if reference.exists():
            comparisons.append(compare_csv(reference, path))
    summary["comparisons"] = comparisons
    summary["new_generated_tables"] = [p.relative_to(work).as_posix() for p in regenerated if not (ROOT / p.relative_to(work)).exists()]
    compared_paths = {c["path"] for c in comparisons}
    summary["expected_reference_tables_not_regenerated"] = sorted(set(targets[args.profile]) - compared_paths)
    failed |= bool(summary["expected_reference_tables_not_regenerated"])
    if not failed:
        summary["report_claims"] = report_claims(work, args.profile)
        failed |= not all(c["passed"] for c in summary["report_claims"])
        if not args.skip_tests:
            command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
            with (out / "logs/unit_tests.log").open("w") as handle:
                result = subprocess.run(command, cwd=work, stdout=handle, stderr=subprocess.STDOUT)
            summary["tests_exit_code"] = result.returncode
            failed |= result.returncode != 0
    failed |= not all(c["passed"] for c in comparisons)
    summary["status"] = "FAIL" if failed else "PASS"
    summary["regenerated_reference_tables"] = len(comparisons)
    summary["verified_numeric_cells"] = sum(c["numeric_cells"] for c in comparisons)
    (out / "replication_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({k: summary[k] for k in ("status", "regenerated_reference_tables", "verified_numeric_cells")}, ensure_ascii=False))
    print("Full receipt:", out / "replication_summary.json")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
