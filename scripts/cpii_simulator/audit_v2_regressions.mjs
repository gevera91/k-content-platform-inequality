#!/usr/bin/env node
/** Exercise exported workbooks in memory; never overwrite either release. */
import fs from "node:fs/promises";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const args = process.argv.slice(2);
const value = (flag) => args[args.indexOf(flag) + 1];
const root = path.resolve(value("--project-root"));
const file = path.resolve(value("--workbook"));
const output = path.resolve(value("--output"));
const python = process.env.CPII_PYTHON || "python3";
const blob = await FileBlob.load(file);
const cases = [
  ["baseline", []],
  ["edit_example", [["V7", 0.25], ["U7", 0.185]]],
  ["invalid_date", [["O7", "2025-02-30"]]],
  ["invalid_date_text", [["O7", "not-a-date"]]],
  ["basic_date", [["O7", "20251231"]]],
  ["valid_leap_date", [["O7", "2024-02-29"]]],
  ["invalid_leap_date", [["O7", "2100-02-29"]]],
  ["cohort_whitespace", [["E7", " integrated_content"]]],
  ["cohort_case", [["E8", "Integrated_content"]]],
  ["enum_case", [["C7", "DOMESTIC"]]],
  ["benchmark_case", [["H7", "bm-digital-content-2025q4"]]],
  ["non_ascii_id", [["A7", "COMPANY-É"]]],
  ["dependency_warning", [["U7", 0.8]]],
  ["missing_feature", [["T7", null]]],
  ["zero_feature", [["T7", 0]]],
  ["duplicate_id", [["A8", "SYN-A"]]],
  ["tie", []],
  ["reverse_pair", []],
];
const records = [];
for (const [name, edits] of cases) {
  const wb = await SpreadsheetFile.importXlsx(blob);
  const sheet = (id) => wb.worksheets.getItem(id);
  const input = sheet("01_INPUT_COMPANIES");
  const initial = input.getRange("A7:AC10").values;
  for (const [cell, content] of edits) input.getRange(cell).values = [[content]];
  if (name === "tie") input.getRange("T8:AC8").values = [initial[0].slice(19)];
  if (name === "reverse_pair") sheet("03_COMPARE_2").getRange("B4:B5").values = [["SYN-B"], ["SYN-A"]];
  const read = (id, range) => sheet(id).getRange(range).values;
  const scores = read("91_CALC_SCORES", "Y7:AB10");
  const pair = read("03_COMPARE_2", "A14")[0][0];
  const gap = read("03_COMPARE_2", "D8")[0][0];
  const inputValues = input.getRange("A7:AC10").values;
  const code = "import csv,json,sys; from scripts.cpii_simulator.engine import score_rows; rows=list(csv.DictReader(open('data/processed/cpii_simulator/examples/fictional_companies.csv'))); order=json.load(open('outputs/tables/cpii_simulator/workbook/workbook_payload.json'))['active_order']; vals=json.load(sys.stdin); [(row.update(dict(zip(order,v[19:])))) for row,v in zip(rows,vals)]; print(json.dumps([r['CPII'] for r in score_rows(rows)]))";
  let expected = null;
  if (name !== "missing_feature") expected = JSON.parse(execFileSync(python, ["-c", code], { cwd: root, input: JSON.stringify(inputValues), encoding: "utf8" }));
  const isV2 = read("00_README", "B19")[0][0].includes("V2.");
  const checks = [];
  const check = (label, ok) => checks.push({ label, passed: !!ok });
  const near = (a, b) => typeof a === "number" && Math.abs(a - b) < 1e-9;
  const blocked = ["invalid_date", "invalid_date_text", "basic_date", "invalid_leap_date", "cohort_whitespace", "enum_case", "benchmark_case", "non_ascii_id", "missing_feature", "duplicate_id"].includes(name);
  const blank = (v) => v === null || v === "";
  if (expected) check("all_four_scores_match_python", scores.every((r, i) => near(r[0], expected[i])));
  if (blocked) {
    check("input_rejected", !/^(PASS|READY)/.test(scores[0][3]));
    check("gap_blocked", blank(gap));
  } else if (name === "cohort_case") {
    check("different_case_not_same_cohort", pair === "N/A: cohort 불일치");
    check("matrix_blocked", read("04_COMPARE_N", "K7")[0][0] === "N/A:cohort");
    check("separate_cohort_rank", near(read("04_COMPARE_N", "E8")[0][0], 1));
  } else {
    check("valid_pair_available", pair === "비교 가능");
    check("gap_matches_python", near(gap, name === "reverse_pair" ? expected[1] - expected[0] : expected[0] - expected[1]));
    check("decomposition_exact", near(read("03_COMPARE_2", "H28")[0][0], gap));
    if (name === "baseline") check("no_spurious_dependency_warning", scores.every((r) => !r[3].includes("DEPENDENCY")));
    if (name === "baseline") check("baseline_ranks", read("04_COMPARE_N", "E7:E10").every((r,i)=>near(r[0],[2,4,1,3][i])));
    if (name === "dependency_warning") check("dependency_warning_present", scores[0][3].includes("DEPENDENCY"));
    if (name === "tie") check("average_tie_rank", near(read("04_COMPARE_N", "E7")[0][0], read("04_COMPARE_N", "E8")[0][0]));
  }
  records.push({ name, status: scores[0][3], pair, gap, checks, failures: checks.filter((c) => !c.passed) });
  console.log(`${name}: ${records.at(-1).failures.length} failed checks`);
  if (name === "baseline" && isV2) {
    await fs.mkdir(path.dirname(output), { recursive: true });
    const inspection = await wb.inspect({ kind: "region", sheetId: "03_COMPARE_2", range: "A7:I28", maxChars: 6000, tableMaxRows: 23, tableMaxCols: 9 });
    await fs.writeFile(path.join(path.dirname(output), "inspection.json"), JSON.stringify(inspection, null, 2));
  }
}
const result = { workbook: path.basename(file), sha256: createHash("sha256").update(await fs.readFile(file)).digest("hex"), case_count: records.length, assertion_count: records.reduce((n,r)=>n+r.checks.length,0), failures: records.flatMap((r)=>r.failures.map((c)=>({case:r.name,...c}))), cases: records };
await fs.mkdir(path.dirname(output), { recursive: true });
await fs.writeFile(output, JSON.stringify(result, null, 2) + "\n");
if (args.includes("--require-pass") && result.failures.length) process.exitCode = 1;
