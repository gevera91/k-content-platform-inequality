#!/usr/bin/env python3
"""Read cached OOXML results after independent spreadsheet recalculation."""
import argparse
import hashlib
import json
from pathlib import Path
import posixpath
from xml.etree import ElementTree as ET
import zipfile


def check(path):
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as archive:
        strings = ["".join(t.itertext()) for t in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        rels = {r.attrib["Id"]:r.attrib["Target"] for r in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
        sheets = {}
        for node in ET.fromstring(archive.read("xl/workbook.xml")).findall(".//m:sheet", ns):
            target = rels[node.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
            member = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            cells = {}
            for c in ET.fromstring(archive.read(member)).findall(".//m:c", ns):
                value = c.findtext("m:v", namespaces=ns)
                kind = c.attrib.get("t")
                if kind == "s":
                    value = strings[int(value)]
                elif kind == "e":
                    raise ValueError(f"cached error: {node.attrib['name']}!{c.attrib['r']}={value}")
                elif value is not None and kind not in {"str", "inlineStr"}:
                    value = float(value)
                cells[c.attrib["r"]] = value
            sheets[node.attrib["name"]] = cells
    assertions = []
    def near(label, a, b):
        ok = isinstance(a, (int, float)) and abs(a - b) <= 1e-10
        assertions.append({"check": label, "observed": a, "expected": b, "passed": ok})
    for row in range(7, 11):
        actual = sheets["91_CALC_SCORES"]
        expected = sheets["94_EXPECTED_OUTPUTS"]
        for destination, source in zip("YVWXLMNOPQRSTU", "BCDEFGHIJKLMNO"):
            near(f"score_or_feature_{destination}{row}", actual[f"{destination}{row}"], expected[f"{source}{row}"])
        near(f"rank_{row}", sheets["04_COMPARE_N"][f"E{row}"], [2,4,1,3][row-7])
    for row in range(7,19):
        observed = sheets["99_QA_AUDIT"][f"D{row}"]
        assertions.append({"check": f"audit_D{row}", "observed": observed, "passed": observed == "PASS"})
    return {"workbook": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "calculation_source": "independent_spreadsheet_cached_results", "assertion_count": len(assertions), "failures": [a for a in assertions if not a["passed"]], "assertions": assertions}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = check(args.workbook)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{result['assertion_count']} assertions; {len(result['failures'])} failures")
    raise SystemExit(bool(result["failures"]))
