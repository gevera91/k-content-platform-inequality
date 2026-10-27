#!/usr/bin/env node

/**
 * Read-only QA gate for the client CPII comparator workbook.
 *
 * The verifier deliberately re-imports the exported XLSX with
 * @oai/artifact-tool. It never exports or mutates the workbook. Its only
 * outputs are bounded PNG previews and a portable JSON audit record.
 */

import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";


const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(SCRIPT_DIR, "../..");
const DEFAULT_WORKBOOK = path.join(
  PROJECT_ROOT,
  "outputs/client_delivery/CPII_Company_Comparator.xlsx",
);
const DEFAULT_OUTPUT_DIR = path.join(
  PROJECT_ROOT,
  "logs/cpii_simulator_workbook_qa",
);

const REQUIRED_SHEETS = Object.freeze([
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
]);

const FORMULA_SHEETS = Object.freeze([
  "01_INPUT_COMPANIES",
  "02_INPUT_ECON_BASES",
  "03_COMPARE_2",
  "04_COMPARE_N",
  "05_ECON_INTERPRET",
  "06_SENSITIVITY",
  "90_CALC_FEATURES",
  "91_CALC_SCORES",
  "99_QA_AUDIT",
]);

const REQUIRED_WORKBOOK_STRINGS = Object.freeze([
  "CPII_FIRM_INPUT_EQW_V1",
  "POOL_SCQ_P01_P99_EMP_RANK_V1",
  "research_beta_due_to_low_support_active_features",
  "입력범위 미포함",
]);

// These ranges intentionally cap the visual audit. Large input/anchor sheets
// show their title, headers, warnings, and representative first rows without
// producing unmanageably large images.
const RENDER_RANGES = Object.freeze({
  "00_README": "A1:H39",
  "01_INPUT_COMPANIES": "A1:AD14",
  "02_INPUT_ECON_BASES": "A1:AA14",
  "03_COMPARE_2": "A1:R49",
  "04_COMPARE_N": "A1:AM40",
  "05_ECON_INTERPRET": "A1:S23",
  "06_SENSITIVITY": "A1:H22",
  "07_INPUT_PROVENANCE": "A1:J24",
  "90_CALC_FEATURES": "A1:N18",
  "91_CALC_SCORES": "A1:AD18",
  "92_REF_VARIABLES": "A1:P55",
  "93_REF_ANCHORS": "A1:C30",
  "94_EXPECTED_OUTPUTS": "A1:P21",
  "99_QA_AUDIT": "A1:H26",
});

// Sheet summaries can stop at a table boundary even when formula cells extend
// beyond it. These explicit v1 bounds cover the complete 30x30 pair matrix and
// all prefilled 100-company calculation rows.
const FORMULA_SCAN_RANGES = Object.freeze({
  "01_INPUT_COMPANIES": "A1:AD106",
  "02_INPUT_ECON_BASES": "A1:AA106",
  "03_COMPARE_2": "A1:R49",
  "04_COMPARE_N": "A1:AO106",
  "05_ECON_INTERPRET": "A1:S23",
  "06_SENSITIVITY": "A1:H21",
  "90_CALC_FEATURES": "A1:N1006",
  "91_CALC_SCORES": "A1:AD106",
  "99_QA_AUDIT": "A1:H25",
});

const FORMULA_ERROR_SOURCE = "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!|#FIELD!|#BLOCKED!|#UNKNOWN!|#CONNECT!|#GETTING_DATA|#ERROR!|#CIRC!|#NOT_IMPLEMENTED!|#TRACE!|#BUSY!|#DATA!|#PYTHON!";
const FORMULA_ERROR_PATTERN = new RegExp(FORMULA_ERROR_SOURCE, "i");
const EXTERNAL_FORMULA_PATTERN = /file:\/\/|\[[^\]]+\.(?:xlsx?|xlsm|xlsb)\]/i;
const MAX_EXCEL_FORMULA_CHARS = 8192;
const FORMULA_CONTRACT = Object.freeze([
  { sheet: "01_INPUT_COMPANIES", address: "AD7", required: ["91_CALC_SCORES", "$AB$7"] },
  { sheet: "02_INPUT_ECON_BASES", address: "AA7", required: ["ERROR: LOW/BASE/HIGH", "ERROR: COMPANY CURRENCY/YEAR", "ERROR: TRANSFER ASSUMPTION"] },
  { sheet: "03_COMPARE_2", address: "A14", required: ["N/A: 동일 관측 선택", "N/A: 입력 검증 실패", "N/A: ID 없음/중복"] },
  { sheet: "03_COMPARE_2", address: "D8", required: ["$A$14<>\"비교 가능\""] },
  { sheet: "04_COMPARE_N", address: "E7", required: ["COUNTIFS", "-1)/2"] },
  { sheet: "04_COMPARE_N", address: "J7", required: ["N/A:input", "N/A:cohort"] },
  { sheet: "05_ECON_INTERPRET", address: "I8", required: ["PAIR NOT COMPARABLE", "MISSING EXPOSURE", "TIME BASIS MISMATCH"] },
  { sheet: "06_SENSITIVITY", address: "B8", required: ["03_COMPARE_2", "비교 가능"] },
  { sheet: "06_SENSITIVITY", address: "B16", required: ["0.000000000001", "비교 불가"] },
  { sheet: "90_CALC_FEATURES", address: "E7", required: ["COUNT(", "$T$7", "01_INPUT_COMPANIES"] },
  { sheet: "91_CALC_SCORES", address: "AB7", required: ["ERROR: DUPLICATE ID", "ERROR: BENCHMARK", "ERROR: EXPOSURE ADJUSTMENT"] },
  { sheet: "99_QA_AUDIT", address: "B16", required: ["COUNTA", ">=PASS", ">=READY"] },
]);


function usage() {
  return [
    "Usage: node scripts/cpii_simulator/verify_workbook.mjs [options]",
    "",
    "Options:",
    `  --workbook PATH    XLSX to inspect (default: ${path.relative(PROJECT_ROOT, DEFAULT_WORKBOOK)})`,
    `  --output-dir PATH  PNG/audit directory (default: ${path.relative(PROJECT_ROOT, DEFAULT_OUTPUT_DIR)})`,
    "  --audit-json PATH  JSON audit path (default: <output-dir>/workbook_audit.json)",
    "  --help             Show this help",
  ].join("\n");
}


function parseArgs(argv) {
  const options = {
    workbook: DEFAULT_WORKBOOK,
    outputDir: DEFAULT_OUTPUT_DIR,
    auditJson: null,
    help: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--help" || token === "-h") {
      options.help = true;
      continue;
    }
    if (!["--workbook", "--output-dir", "--audit-json"].includes(token)) {
      throw new Error(`unknown argument: ${token}`);
    }
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) {
      throw new Error(`${token} requires a path`);
    }
    index += 1;
    if (token === "--workbook") options.workbook = path.resolve(value);
    if (token === "--output-dir") options.outputDir = path.resolve(value);
    if (token === "--audit-json") options.auditJson = path.resolve(value);
  }
  options.workbook = path.resolve(options.workbook);
  options.outputDir = path.resolve(options.outputDir);
  options.auditJson = options.auditJson
    ? path.resolve(options.auditJson)
    : path.join(options.outputDir, "workbook_audit.json");
  return options;
}


function portablePath(filePath) {
  const relative = path.relative(PROJECT_ROOT, path.resolve(filePath));
  if (relative && !relative.startsWith("..") && !path.isAbsolute(relative)) {
    return relative.split(path.sep).join("/");
  }
  return path.basename(filePath);
}


function portableMessage(value) {
  return String(value)
    .replaceAll(PROJECT_ROOT, ".")
    .replaceAll(process.cwd(), ".");
}


function meaningfulRecords(inspection, kind) {
  return Array.from(inspection?.records ?? []).filter(
    (record) => record && record.kind === kind,
  );
}


function unique(items) {
  return [...new Set(items)];
}


function safeFileStem(name) {
  return name.replace(/[^A-Za-z0-9._-]+/g, "_");
}


async function sha256(filePath) {
  const bytes = await fs.readFile(filePath);
  return createHash("sha256").update(bytes).digest("hex");
}


async function inspectFormulas(workbook, sheetName, usedRange) {
  const formulaRange = FORMULA_SCAN_RANGES[sheetName] ?? usedRange ?? "A1:AZ250";
  const inspection = await workbook.inspect({
    kind: "formula",
    sheetId: sheetName,
    range: formulaRange,
    maxChars: 5_000_000,
    options: { maxResults: 50_000 },
  });
  const formulas = meaningfulRecords(inspection, "formula");
  return {
    range: formulaRange,
    count: formulas.length,
    truncated: Boolean(inspection.truncated),
    records: formulas,
    sample: formulas.slice(0, 8).map((record) => ({
      address: record.address,
      formula: record.formula,
    })),
  };
}


async function run(options) {
  await fs.mkdir(options.outputDir, { recursive: true });
  await fs.mkdir(path.dirname(options.auditJson), { recursive: true });

  const audit = {
    audit_schema_version: "CPII_WORKBOOK_AUDIT_V1",
    generated_at_utc: new Date().toISOString(),
    workbook: {
      path: portablePath(options.workbook),
      sha256: null,
      size_bytes: null,
    },
    contract: {
      required_sheets: REQUIRED_SHEETS,
      formula_sheets: FORMULA_SHEETS,
      required_strings: REQUIRED_WORKBOOK_STRINGS,
    },
    checks: {},
    renders: [],
    failures: [],
    status: "FAIL",
  };

  try {
    const stat = await fs.stat(options.workbook);
    if (!stat.isFile()) {
      throw new Error("workbook path is not a regular file");
    }
    audit.workbook.size_bytes = stat.size;
    audit.workbook.sha256 = await sha256(options.workbook);

    const input = await FileBlob.load(options.workbook);
    const workbook = await SpreadsheetFile.importXlsx(input);
    const version = workbook.worksheets.getItem("00_README").getRange("B19").values[0][0];
    if (!["CPII_COMPARATOR_XLSX_V1.0.1", "CPII_COMPARATOR_XLSX_V2.0.0"].includes(version)) {
      throw new Error(`unsupported workbook version: ${version}`);
    }
    audit.workbook.version = version;
    audit.checks.artifact_tool_import = { passed: true };

    const sheetInspection = await workbook.inspect({
      kind: "sheet",
      include: "id,name",
      maxChars: 30_000,
    });
    const sheetRecords = meaningfulRecords(sheetInspection, "sheet");
    const actualSheets = sheetRecords.map((record) => record.name);
    const usedRangeBySheet = Object.fromEntries(
      sheetRecords.map((record) => [record.name, record.range ?? record.address]),
    );
    const missingSheets = REQUIRED_SHEETS.filter(
      (name) => !actualSheets.includes(name),
    );
    const unexpectedSheets = actualSheets.filter(
      (name) => !REQUIRED_SHEETS.includes(name),
    );
    const duplicateSheets = unique(actualSheets.filter(
      (name, index) => actualSheets.indexOf(name) !== index,
    ));
    const orderMatches =
      actualSheets.length === REQUIRED_SHEETS.length
      && actualSheets.every((name, index) => name === REQUIRED_SHEETS[index]);
    audit.checks.sheet_contract = {
      passed:
        missingSheets.length === 0
        && unexpectedSheets.length === 0
        && duplicateSheets.length === 0
        && orderMatches,
      actual_sheets: actualSheets,
      missing_sheets: missingSheets,
      unexpected_sheets: unexpectedSheets,
      duplicate_sheets: duplicateSheets,
      order_matches: orderMatches,
      inspect_truncated: Boolean(sheetInspection.truncated),
    };
    if (missingSheets.length > 0) {
      audit.failures.push(`missing required sheets: ${missingSheets.join(", ")}`);
    }
    if (unexpectedSheets.length > 0) {
      audit.failures.push(`unexpected sheets: ${unexpectedSheets.join(", ")}`);
    }
    if (duplicateSheets.length > 0) {
      audit.failures.push(`duplicate sheet names: ${duplicateSheets.join(", ")}`);
    }
    if (!orderMatches) {
      audit.failures.push("worksheet order does not match the v1 workbook contract");
    }

    const formulaBySheet = {};
    const allFormulaRecords = [];
    for (const sheetName of actualSheets) {
      try {
        const result = await inspectFormulas(
          workbook,
          sheetName,
          usedRangeBySheet[sheetName],
        );
        formulaBySheet[sheetName] = {
          range: result.range,
          count: result.count,
          truncated: result.truncated,
          sample: result.sample,
        };
        allFormulaRecords.push(
          ...result.records.map((record) => ({ ...record, sheet: sheetName })),
        );
      } catch (error) {
        formulaBySheet[sheetName] = {
          range: usedRangeBySheet[sheetName] ?? "A1:AZ250",
          count: 0,
          inspection_error: portableMessage(error?.message ?? error),
        };
        audit.failures.push(
          `formula inspection failed for ${sheetName}: ${portableMessage(error?.message ?? error)}`,
        );
      }
    }
    const formulaSheetsMissingFormulas = FORMULA_SHEETS.filter(
      (sheetName) => (formulaBySheet[sheetName]?.count ?? 0) === 0,
    );
    const truncatedFormulaSheets = actualSheets.filter(
      (sheetName) => formulaBySheet[sheetName]?.truncated,
    );
    const formulaTokenErrors = allFormulaRecords
      .filter((record) => FORMULA_ERROR_PATTERN.test(String(record.formula ?? "")))
      .map((record) => ({
        sheet: record.sheet,
        address: record.address,
        formula: record.formula,
      }));
    const externalFormulaTokens = allFormulaRecords
      .filter((record) => EXTERNAL_FORMULA_PATTERN.test(String(record.formula ?? "")))
      .map((record) => ({
        sheet: record.sheet,
        address: record.address,
        formula: record.formula,
      }));
    const oversizedFormulas = allFormulaRecords
      .filter((record) => String(record.formula ?? "").length > MAX_EXCEL_FORMULA_CHARS)
      .map((record) => ({
        sheet: record.sheet,
        address: record.address,
        length: String(record.formula ?? "").length,
      }));
    audit.checks.formulas = {
      passed:
        allFormulaRecords.length > 0
        && formulaSheetsMissingFormulas.length === 0
        && truncatedFormulaSheets.length === 0
        && formulaTokenErrors.length === 0
        && externalFormulaTokens.length === 0
        && oversizedFormulas.length === 0,
      scan_scope: "full artifact-tool-reported used range for every sheet",
      total_formula_records: allFormulaRecords.length,
      by_sheet: formulaBySheet,
      required_sheets_without_formulas: formulaSheetsMissingFormulas,
      truncated_formula_sheets: truncatedFormulaSheets,
      formula_error_tokens: formulaTokenErrors,
      external_workbook_tokens: externalFormulaTokens,
      oversized_formulas: oversizedFormulas,
    };
    if (allFormulaRecords.length === 0) {
      audit.failures.push("no formulas were found in the workbook");
    }
    if (formulaSheetsMissingFormulas.length > 0) {
      audit.failures.push(
        `dynamic sheets without formulas: ${formulaSheetsMissingFormulas.join(", ")}`,
      );
    }
    if (truncatedFormulaSheets.length > 0) {
      audit.failures.push(
        `formula inspection was truncated for: ${truncatedFormulaSheets.join(", ")}`,
      );
    }
    if (formulaTokenErrors.length > 0) {
      audit.failures.push(
        `formula text contains error tokens in ${formulaTokenErrors.length} cell(s)`,
      );
    }
    if (externalFormulaTokens.length > 0) {
      audit.failures.push(
        `formula text contains external-workbook tokens in ${externalFormulaTokens.length} cell(s)`,
      );
    }
    if (oversizedFormulas.length > 0) {
      audit.failures.push(
        `Excel formula length exceeds ${MAX_EXCEL_FORMULA_CHARS} characters in ${oversizedFormulas.length} cell(s)`,
      );
    }

    const formulaIndex = new Map(
      allFormulaRecords.map((record) => [
        `${record.sheet}!${String(record.address).toUpperCase()}`,
        String(record.formula ?? ""),
      ]),
    );
    const contracts = FORMULA_CONTRACT.map((rule) =>
      version === "CPII_COMPARATOR_XLSX_V2.0.0" && rule.sheet === "04_COMPARE_N" && rule.address === "E7"
        ? { ...rule, required: ["SUM", "AN7:AO7", "-1/2"] } : rule,
    );
    if (version === "CPII_COMPARATOR_XLSX_V2.0.0") {
      contracts.push({ sheet: "91_CALC_SCORES", address: "AD7", required: ["ERROR: SOURCE DATE", "ERROR: EXACT ENUM", "ERROR: COHORT WHITESPACE"] });
      contracts.push({ sheet: "91_CALC_SCORES", address: "Z7", required: ["EXACT", "SYN-A", "COUNT"] });
      contracts.push({ sheet: "04_COMPARE_N", address: "AN7", required: ["EXACT", "ISNUMBER"] });
    }
    const formulaContractResults = contracts.map((rule) => {
      const formula = formulaIndex.get(`${rule.sheet}!${rule.address.toUpperCase()}`) ?? "";
      const missingTokens = rule.required.filter((token) => !formula.includes(token));
      return {
        sheet: rule.sheet,
        address: rule.address,
        passed: Boolean(formula) && missingTokens.length === 0,
        missing_tokens: missingTokens,
      };
    });
    audit.checks.formula_contract = {
      passed: formulaContractResults.every((result) => result.passed),
      rules: formulaContractResults,
    };
    for (const result of formulaContractResults.filter((item) => !item.passed)) {
      audit.failures.push(
        `critical formula contract failed at ${result.sheet}!${result.address}: missing ${result.missing_tokens.join(", ")}`,
      );
    }

    const embeddedQaInspection = await workbook.inspect({
      kind: "table",
      sheetId: "99_QA_AUDIT",
      range: "A6:D18",
      include: "values,formulas",
      tableMaxRows: 20,
      tableMaxCols: 4,
      maxChars: 100_000,
    });
    const embeddedQaTable = meaningfulRecords(embeddedQaInspection, "table")[0];
    const embeddedQaRows = Array.isArray(embeddedQaTable?.values)
      ? embeddedQaTable.values.slice(1).map((row, index) => ({
        row: 7 + index,
        check: row?.[0] ?? null,
        observed: row?.[1] ?? null,
        criterion: row?.[2] ?? null,
        result: row?.[3] ?? null,
      }))
      : [];
    const embeddedQaFailures = embeddedQaRows.filter((row) => row.result !== "PASS");
    audit.checks.embedded_qa = {
      passed:
        embeddedQaRows.length === 12
        && embeddedQaFailures.length === 0
        && !embeddedQaInspection.truncated,
      rows: embeddedQaRows,
      failed_rows: embeddedQaFailures,
      truncated: Boolean(embeddedQaInspection.truncated),
    };
    if (!audit.checks.embedded_qa.passed) {
      audit.failures.push(
        `embedded 99_QA_AUDIT gate failed (${embeddedQaFailures.length} non-PASS row(s), ${embeddedQaRows.length}/12 rows read)`,
      );
    }

    const errorMatches = [];
    const errorScanBySheet = {};
    for (const sheetName of actualSheets) {
      const scanRange = FORMULA_SCAN_RANGES[sheetName]
        ?? usedRangeBySheet[sheetName]
        ?? "A1:AZ250";
      const inspection = await workbook.inspect({
        kind: "match",
        sheetId: sheetName,
        range: scanRange,
        searchTerm: FORMULA_ERROR_SOURCE,
        maxChars: 5_000_000,
        options: {
          useRegex: true,
          maxResults: 1_000,
          matchFormulas: true,
        },
        summary: `CPII formula and cached-value error scan: ${sheetName}`,
      });
      const matches = meaningfulRecords(inspection, "match").map(
        (record) => ({
          sheet: record.sheet,
          address: record.address,
          value: record.value,
          formula: record.formula,
          match: record.match,
        }),
      );
      errorMatches.push(...matches);
      errorScanBySheet[sheetName] = {
        range: scanRange,
        count: matches.length,
        truncated: Boolean(inspection.truncated),
      };
    }
    const truncatedErrorScans = Object.entries(errorScanBySheet)
      .filter(([, check]) => check.truncated)
      .map(([sheetName]) => sheetName);
    audit.checks.error_tokens = {
      passed: errorMatches.length === 0 && truncatedErrorScans.length === 0,
      count: errorMatches.length,
      matches: errorMatches,
      by_sheet: errorScanBySheet,
      truncated_sheets: truncatedErrorScans,
    };
    if (errorMatches.length > 0) {
      audit.failures.push(
        `formula/cached-value error scan found ${errorMatches.length} cell(s)`,
      );
    }
    if (truncatedErrorScans.length > 0) {
      audit.failures.push(
        `formula error scan was truncated for: ${truncatedErrorScans.join(", ")}`,
      );
    }

    const stringChecks = {};
    for (const requiredText of REQUIRED_WORKBOOK_STRINGS) {
      const inspection = await workbook.inspect({
        kind: "match",
        searchTerm: requiredText,
        maxChars: 20_000,
        options: { maxResults: 50, matchFormulas: true },
        summary: `required workbook string: ${requiredText}`,
      });
      const matches = meaningfulRecords(inspection, "match").map((record) => ({
        sheet: record.sheet,
        address: record.address,
        match: record.match,
      }));
      stringChecks[requiredText] = {
        passed: matches.length > 0 && !inspection.truncated,
        matches,
        truncated: Boolean(inspection.truncated),
      };
      if (matches.length === 0) {
        audit.failures.push(`required workbook string not found: ${requiredText}`);
      }
      if (inspection.truncated) {
        audit.failures.push(`required-string scan was truncated: ${requiredText}`);
      }
    }
    audit.checks.required_strings = {
      passed: Object.values(stringChecks).every((check) => check.passed),
      strings: stringChecks,
    };

    for (const sheetName of actualSheets) {
      const renderRange = RENDER_RANGES[sheetName] ?? "A1:T40";
      const outputName = `${safeFileStem(sheetName)}.png`;
      const outputPath = path.join(options.outputDir, outputName);
      try {
        const preview = await workbook.render({
          sheetName,
          range: renderRange,
          format: "png",
          scale: 1,
        });
        const previewBytes = new Uint8Array(await preview.arrayBuffer());
        await fs.writeFile(outputPath, previewBytes);
        const passed = previewBytes.byteLength >= 512;
        audit.renders.push({
          sheet: sheetName,
          range: renderRange,
          output: portablePath(outputPath),
          size_bytes: previewBytes.byteLength,
          passed,
        });
        if (!passed) {
          audit.failures.push(
            `rendered PNG is unexpectedly small for ${sheetName}: ${previewBytes.byteLength} bytes`,
          );
        }
      } catch (error) {
        audit.renders.push({
          sheet: sheetName,
          range: renderRange,
          output: portablePath(outputPath),
          passed: false,
          error: portableMessage(error?.message ?? error),
        });
        audit.failures.push(
          `render failed for ${sheetName}: ${portableMessage(error?.message ?? error)}`,
        );
      }
    }
    const renderedSheets = new Set(audit.renders
      .filter((render) => render.passed)
      .map((render) => render.sheet));
    const sheetsWithoutRender = actualSheets.filter(
      (sheetName) => !renderedSheets.has(sheetName),
    );
    audit.checks.render_all_sheets = {
      passed: sheetsWithoutRender.length === 0 && actualSheets.length > 0,
      rendered_sheet_count: renderedSheets.size,
      actual_sheet_count: actualSheets.length,
      sheets_without_passing_render: sheetsWithoutRender,
    };
    if (actualSheets.length === 0) {
      audit.failures.push("artifact-tool did not discover any worksheets");
    }
  } catch (error) {
    audit.checks.artifact_tool_import ??= { passed: false };
    audit.failures.push(`fatal verification error: ${portableMessage(error?.message ?? error)}`);
  }

  audit.failures = unique(audit.failures);
  audit.status = audit.failures.length === 0 ? "PASS" : "FAIL";
  await fs.writeFile(
    options.auditJson,
    `${JSON.stringify(audit, null, 2)}\n`,
    "utf8",
  );

  const auditLabel = portablePath(options.auditJson);
  if (audit.status === "PASS") {
    console.log(`PASS CPII workbook audit: ${auditLabel}`);
    return 0;
  }
  console.error(`FAIL CPII workbook audit: ${auditLabel}`);
  for (const failure of audit.failures) {
    console.error(`- ${failure}`);
  }
  return 1;
}


let options;
try {
  options = parseArgs(process.argv.slice(2));
} catch (error) {
  console.error(`FAIL argument parsing: ${error.message}`);
  console.error(usage());
  process.exitCode = 2;
}

if (options?.help) {
  console.log(usage());
} else if (options) {
  process.exitCode = await run(options);
}
