#!/usr/bin/env node

/** Read-only verifier for the 12 adversarial CPII workbook scenarios. */

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";


const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(SCRIPT_DIR, "../..");
const DEFAULT_INPUT_DIR = path.join(PROJECT_ROOT, "logs/cpii_simulator_workbook_scenarios");

function parseArgs(argv) {
  let inputDir = DEFAULT_INPUT_DIR;
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--help" || token === "-h") {
      console.log("Usage: node scripts/cpii_simulator/verify_workbook_scenarios.mjs [--input-dir PATH]");
      process.exit(0);
    }
    if (token !== "--input-dir") throw new Error(`unknown argument: ${token}`);
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) throw new Error("--input-dir requires a path");
    inputDir = path.resolve(value);
    index += 1;
  }
  return { inputDir };
}

function meaningfulTable(inspection) {
  return Array.from(inspection?.records ?? []).find((record) => record?.kind === "table");
}

async function readValues(workbook, sheetId, range) {
  const inspection = await workbook.inspect({
    kind: "table",
    sheetId,
    range,
    include: "values,formulas",
    tableMaxRows: 20,
    tableMaxCols: 20,
    maxChars: 100_000,
  });
  const table = meaningfulTable(inspection);
  if (!table || !Array.isArray(table.values)) {
    throw new Error(`could not inspect ${sheetId}!${range}`);
  }
  return table.values;
}

const blank = (value) => value === null || value === "";
const finite = (value) => typeof value === "number" && Number.isFinite(value);
const near = (value, target, tolerance = 1e-9) => finite(value) && Math.abs(value - target) <= tolerance;
const exact = (value, target) => value === target;
const prefix = (value, target) => typeof value === "string" && value.startsWith(target);

const SCENARIOS = [
  {
    file: "01_blank_feature.xlsx",
    async check(workbook) {
      const score = (await readValues(workbook, "91_CALC_SCORES", "Y7:AB7"))[0];
      const pair = (await readValues(workbook, "03_COMPARE_2", "A14"))[0][0];
      const gap = (await readValues(workbook, "03_COMPARE_2", "D8"))[0][0];
      const audit = (await readValues(workbook, "99_QA_AUDIT", "B16:D16"))[0];
      return [
        ["blank score", blank(score[0]), score[0]],
        ["input required", exact(score[3], "INPUT REQUIRED"), score[3]],
        ["pair blocked", exact(pair, "N/A: 입력 검증 실패"), pair],
        ["gap blank", blank(gap), gap],
        ["blocked-row count", near(audit[0], 1), audit[0]],
        ["blocked-row gate", exact(audit[2], "FAIL"), audit[2]],
      ];
    },
  },
  {
    file: "02_literal_zero_feature.xlsx",
    async check(workbook) {
      const feature = (await readValues(workbook, "90_CALC_FEATURES", "E47"))[0][0];
      const score = (await readValues(workbook, "91_CALC_SCORES", "Y11:AB11"))[0];
      const pair = (await readValues(workbook, "03_COMPARE_2", "A14"))[0][0];
      const gap = (await readValues(workbook, "03_COMPARE_2", "D8"))[0][0];
      return [
        ["literal zero preserved", near(feature, 0), feature],
        ["finite score", finite(score[0]), score[0]],
        ["ready", prefix(score[3], "READY"), score[3]],
        ["pair comparable", exact(pair, "비교 가능"), pair],
        ["finite gap", finite(gap), gap],
      ];
    },
  },
  {
    file: "03_duplicate_id.xlsx",
    async check(workbook) {
      const first = (await readValues(workbook, "91_CALC_SCORES", "AB7"))[0][0];
      const duplicate = (await readValues(workbook, "91_CALC_SCORES", "AB11"))[0][0];
      const pair = (await readValues(workbook, "03_COMPARE_2", "A14"))[0][0];
      const audit = (await readValues(workbook, "99_QA_AUDIT", "B16:D16"))[0];
      return [
        ["first duplicate blocked", exact(first, "ERROR: DUPLICATE ID"), first],
        ["second duplicate blocked", exact(duplicate, "ERROR: DUPLICATE ID"), duplicate],
        ["selector blocked", exact(pair, "N/A: ID 없음/중복"), pair],
        ["two blocked rows counted", near(audit[0], 2), audit[0]],
        ["blocked-row gate", exact(audit[2], "FAIL"), audit[2]],
      ];
    },
  },
  {
    file: "04_self_pair.xlsx",
    async check(workbook) {
      const pair = (await readValues(workbook, "03_COMPARE_2", "A14"))[0][0];
      const gap = (await readValues(workbook, "03_COMPARE_2", "D8"))[0][0];
      return [
        ["self pair blocked", exact(pair, "N/A: 동일 관측 선택"), pair],
        ["gap blank", blank(gap), gap],
      ];
    },
  },
  {
    file: "05_cohort_mismatch.xlsx",
    async check(workbook) {
      const pair = (await readValues(workbook, "03_COMPARE_2", "A14"))[0][0];
      const economic = (await readValues(workbook, "05_ECON_INTERPRET", "I8"))[0][0];
      const sensitivity = (await readValues(workbook, "06_SENSITIVITY", "B8"))[0][0];
      return [
        ["cohort blocked", exact(pair, "N/A: cohort 불일치"), pair],
        ["economic blocked", exact(economic, "PAIR NOT COMPARABLE"), economic],
        ["sensitivity blank", blank(sensitivity), sensitivity],
      ];
    },
  },
  {
    file: "06_invalid_exposure_triplet.xlsx",
    async check(workbook) {
      const status = (await readValues(workbook, "02_INPUT_ECON_BASES", "AA7"))[0][0];
      const economic = (await readValues(workbook, "05_ECON_INTERPRET", "I8:M8"))[0];
      return [
        ["range order blocked", exact(status, "ERROR: LOW/BASE/HIGH"), status],
        ["economic input blocked", exact(economic[0], "EXPOSURE INPUT ERROR"), economic[0]],
        ["amount blank", blank(economic[4]), economic[4]],
      ];
    },
  },
  {
    file: "07_average_tie_rank.xlsx",
    async check(workbook) {
      const rows = await readValues(workbook, "04_COMPARE_N", "E11:E12");
      return [
        ["average tie rank A", near(rows[0][0], 5.5), rows[0][0]],
        ["average tie rank B", near(rows[1][0], 5.5), rows[1][0]],
      ];
    },
  },
  {
    file: "08_capacity_row_100.xlsx",
    async check(workbook) {
      const row = (await readValues(workbook, "91_CALC_SCORES", "Y106:AB106"))[0];
      return [
        ["row 100 finite score", finite(row[0]), row[0]],
        ["row 100 ready", prefix(row[3], "READY"), row[3]],
      ];
    },
  },
  {
    file: "09_lowercase_id.xlsx",
    async check(workbook) {
      const status = (await readValues(workbook, "91_CALC_SCORES", "AB11"))[0][0];
      const audit = (await readValues(workbook, "99_QA_AUDIT", "B16:D16"))[0];
      return [
        ["lowercase ID blocked", exact(status, "ERROR: ID FORMAT"), status],
        ["blocked row counted", near(audit[0], 1), audit[0]],
        ["blocked-row gate", exact(audit[2], "FAIL"), audit[2]],
      ];
    },
  },
  {
    file: "10_wildcard_id.xlsx",
    async check(workbook) {
      const status = (await readValues(workbook, "91_CALC_SCORES", "AB11"))[0][0];
      const audit = (await readValues(workbook, "99_QA_AUDIT", "B16:D16"))[0];
      return [
        ["wildcard ID blocked", exact(status, "ERROR: ID FORMAT"), status],
        ["blocked row counted", near(audit[0], 1), audit[0]],
        ["blocked-row gate", exact(audit[2], "FAIL"), audit[2]],
      ];
    },
  },
  {
    file: "11_zero_economic_base.xlsx",
    async check(workbook) {
      const statuses = (await readValues(workbook, "02_INPUT_ECON_BASES", "AA7:AA8")).flat();
      const economic = (await readValues(workbook, "05_ECON_INTERPRET", "I10:O10"))[0];
      return [
        ["zero base status A", exact(statuses[0], "READY"), statuses[0]],
        ["zero base status B", exact(statuses[1], "READY"), statuses[1]],
        ["zero amount available", exact(economic[0], "AVAILABLE - DO NOT SUM"), economic[0]],
        ["zero amounts numeric", economic.slice(1).every((value) => near(value, 0)), economic.slice(1)],
      ];
    },
  },
  {
    file: "12_identical_pair_context_only.xlsx",
    async check(workbook) {
      const pair = (await readValues(workbook, "03_COMPARE_2", "A14"))[0][0];
      const gap = (await readValues(workbook, "03_COMPARE_2", "D8"))[0][0];
      const residual = (await readValues(workbook, "03_COMPARE_2", "H28"))[0][0];
      const economic = (await readValues(workbook, "05_ECON_INTERPRET", "I8:R8"))[0];
      return [
        ["identical pair comparable", exact(pair, "비교 가능"), pair],
        ["zero score gap", near(gap, 0), gap],
        ["zero decomposition residual", near(residual, 0), residual],
        ["context-only economic label", exact(economic[0], "AVAILABLE - CONTEXT ONLY"), economic[0]],
        ["context-only amounts numeric zero", economic.slice(4).every((value) => near(value, 0)), economic.slice(4)],
      ];
    },
  },
];

async function verifyScenario(inputDir, scenario) {
  const filePath = path.join(inputDir, scenario.file);
  await fs.access(filePath);
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(filePath));
  const checks = await scenario.check(workbook);
  const failures = checks
    .filter(([, passed]) => !passed)
    .map(([name, , observed]) => ({ name, observed }));
  return { file: scenario.file, check_count: checks.length, failures };
}

async function run({ inputDir }) {
  const results = [];
  for (const scenario of SCENARIOS) {
    results.push(await verifyScenario(inputDir, scenario));
  }
  const failures = results.flatMap((result) => result.failures.map((failure) => ({ file: result.file, ...failure })));
  if (failures.length) {
    console.error(JSON.stringify({ input_dir: path.basename(inputDir), failures }, null, 2));
    throw new Error(`${failures.length} workbook scenario check(s) failed`);
  }
  const checkCount = results.reduce((sum, result) => sum + result.check_count, 0);
  console.log(`PASS ${SCENARIOS.length} workbook scenarios (${checkCount} assertions): ${path.basename(inputDir)}`);
}

try {
  await run(parseArgs(process.argv.slice(2)));
} catch (error) {
  console.error(`FAIL workbook scenarios: ${error?.message ?? error}`);
  process.exitCode = 1;
}
