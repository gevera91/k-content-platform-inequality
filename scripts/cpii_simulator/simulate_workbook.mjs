#!/usr/bin/env node

/** Generate adversarial workbook scenarios with @oai/artifact-tool.
 *
 * The caller may recalculate the exported files in Excel or LibreOffice and
 * inspect the documented cells. Scenario files are QA artifacts only and are
 * not included in the customer release bundle.
 */

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";


const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(SCRIPT_DIR, "../..");
const DEFAULT_WORKBOOK = path.join(PROJECT_ROOT, "outputs/client_delivery/CPII_Company_Comparator.xlsx");
const DEFAULT_OUTPUT_DIR = path.join(PROJECT_ROOT, "logs/cpii_simulator_workbook_scenarios");
const PAYLOAD_PATH = path.join(PROJECT_ROOT, "outputs/tables/cpii_simulator/workbook/workbook_payload.json");

const COMPANY_METADATA_FIELDS = [
  "observation_id", "company_name", "company_group", "sector", "service_scope", "focal_market",
  "reporting_period", "benchmark_id", "currency", "price_year", "input_quality", "synthetic_flag",
  "construction_mode", "source_id", "source_date", "carry_lag_q", "market_common_exposure_adjusted",
  "company_exposure_factor", "source_note",
];
const EXPOSURE_FIELDS = [
  "observation_id", "currency", "price_year", "exposure_period", "period_year_fraction",
  "revenue_low", "revenue_base", "revenue_high",
  "positive_pretax_income_low", "positive_pretax_income_base", "positive_pretax_income_high",
  "average_interest_bearing_debt_low", "average_interest_bearing_debt_base", "average_interest_bearing_debt_high",
  "content_investment_low", "content_investment_base", "content_investment_high",
  "eligible_market_revenue_low", "eligible_market_revenue_base", "eligible_market_revenue_high",
  "scenario_conversion_rate_low", "scenario_conversion_rate_base", "scenario_conversion_rate_high",
  "exposure_source_id", "exposure_quality", "exposure_note",
];

function parseArgs(argv) {
  const options = { workbook: DEFAULT_WORKBOOK, outputDir: DEFAULT_OUTPUT_DIR };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!['--workbook', '--output-dir'].includes(token)) throw new Error(`unknown argument: ${token}`);
    const value = argv[index + 1];
    if (!value || value.startsWith('--')) throw new Error(`${token} requires a path`);
    index += 1;
    if (token === '--workbook') options.workbook = path.resolve(value);
    if (token === '--output-dir') options.outputDir = path.resolve(value);
  }
  return options;
}

async function exportScenario(options, name, mutate) {
  const input = await FileBlob.load(options.workbook);
  const workbook = await SpreadsheetFile.importXlsx(input);
  await mutate(workbook);
  const outputPath = path.join(options.outputDir, `${name}.xlsx`);
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(outputPath);
  return outputPath;
}

function companyValues(source, companyFields, overrides = {}) {
  const row = { ...source, ...overrides };
  return [companyFields.map((field) => row[field] ?? null)];
}

function exposureValues(source, overrides = {}) {
  const row = { ...source, ...overrides };
  return [EXPOSURE_FIELDS.map((field) => row[field] ?? null)];
}

async function run(options) {
  await fs.mkdir(options.outputDir, { recursive: true });
  const payload = JSON.parse(await fs.readFile(PAYLOAD_PATH, 'utf8'));
  const base = payload.companies[0];
  const companyFields = [...COMPANY_METADATA_FIELDS, ...payload.active_order];
  const generated = [];

  generated.push(await exportScenario(options, '01_blank_feature', (workbook) => {
    workbook.worksheets.getItem('01_INPUT_COMPANIES').getRange('T7').values = [[null]];
  }));

  generated.push(await exportScenario(options, '02_literal_zero_feature', (workbook) => {
    const input = workbook.worksheets.getItem('01_INPUT_COMPANIES');
    input.getRange('A11:AC11').values = companyValues(base, companyFields, {
      observation_id: 'SIM-ZERO',
      company_name: '합성 제로값 관측',
      effective_tax_rate_gap: 0,
    });
    const compare = workbook.worksheets.getItem('03_COMPARE_2');
    compare.getRange('B4:B5').values = [['SIM-ZERO'], ['SYN-B']];
  }));

  generated.push(await exportScenario(options, '03_duplicate_id', (workbook) => {
    workbook.worksheets.getItem('01_INPUT_COMPANIES').getRange('A11:AC11').values = companyValues(base, companyFields, {
      observation_id: 'SYN-A',
      company_name: '중복 ID 관측',
    });
  }));

  generated.push(await exportScenario(options, '04_self_pair', (workbook) => {
    workbook.worksheets.getItem('03_COMPARE_2').getRange('B4:B5').values = [['SYN-A'], ['SYN-A']];
  }));

  generated.push(await exportScenario(options, '05_cohort_mismatch', (workbook) => {
    workbook.worksheets.getItem('01_INPUT_COMPANIES').getRange('F8').values = [['other_market']];
  }));

  generated.push(await exportScenario(options, '06_invalid_exposure_triplet', (workbook) => {
    const sheet = workbook.worksheets.getItem('02_INPUT_ECON_BASES');
    sheet.getRange('F7:H7').values = [[2_000_000_000_000, 1_200_000_000_000, 1_300_000_000_000]];
  }));

  generated.push(await exportScenario(options, '07_average_tie_rank', (workbook) => {
    const input = workbook.worksheets.getItem('01_INPUT_COMPANIES');
    const zeroFeatures = Object.fromEntries(payload.active_order.map((name) => [name, 0]));
    input.getRange('A11:AC11').values = companyValues(base, companyFields, {
      ...zeroFeatures,
      observation_id: 'SIM-TIE-A',
      company_name: '합성 동률 A',
    });
    input.getRange('A12:AC12').values = companyValues(base, companyFields, {
      ...zeroFeatures,
      observation_id: 'SIM-TIE-B',
      company_name: '합성 동률 B',
    });
  }));

  generated.push(await exportScenario(options, '08_capacity_row_100', (workbook) => {
    workbook.worksheets.getItem('01_INPUT_COMPANIES').getRange('A106:AC106').values = companyValues(base, companyFields, {
      observation_id: 'SIM-ROW-100',
      company_name: '합성 100번째 관측',
    });
  }));

  generated.push(await exportScenario(options, '09_lowercase_id', (workbook) => {
    workbook.worksheets.getItem('01_INPUT_COMPANIES').getRange('A11:AC11').values = companyValues(base, companyFields, {
      observation_id: 'sim-lower',
      company_name: '소문자 ID 관측',
    });
  }));

  generated.push(await exportScenario(options, '10_wildcard_id', (workbook) => {
    workbook.worksheets.getItem('01_INPUT_COMPANIES').getRange('A11:AC11').values = companyValues(base, companyFields, {
      observation_id: 'SIM*BAD',
      company_name: '금지문자 ID 관측',
    });
  }));

  generated.push(await exportScenario(options, '11_zero_economic_base', (workbook) => {
    workbook.worksheets.getItem('02_INPUT_ECON_BASES').getRange('F7:H8').values = [
      [0, 0, 0],
      [0, 0, 0],
    ];
  }));

  generated.push(await exportScenario(options, '12_identical_pair_context_only', (workbook) => {
    workbook.worksheets.getItem('01_INPUT_COMPANIES').getRange('A11:AC11').values = companyValues(base, companyFields, {
      observation_id: 'SIM-SAME',
      company_name: '동일 Feature 관측',
    });
    workbook.worksheets.getItem('02_INPUT_ECON_BASES').getRange('A11:Z11').values = exposureValues(payload.exposures[0], {
      observation_id: 'SIM-SAME',
    });
    workbook.worksheets.getItem('03_COMPARE_2').getRange('B4:B5').values = [['SYN-A'], ['SIM-SAME']];
  }));

  const manifest = {
    schema_version: 'CPII_WORKBOOK_SCENARIOS_V1',
    workbook: path.basename(options.workbook),
    scenarios: generated.map((file) => path.basename(file)),
    expected_after_recalculation: {
      '01_blank_feature': {
        "91_CALC_SCORES!Y7": 'blank',
        "91_CALC_SCORES!AB7": 'INPUT REQUIRED',
        "03_COMPARE_2!A14": 'N/A: 입력 검증 실패',
        "03_COMPARE_2!D8": 'blank',
        "99_QA_AUDIT!B16": 1,
        "99_QA_AUDIT!D16": 'FAIL',
      },
      '02_literal_zero_feature': {
        "91_CALC_SCORES!Y11": 'finite number',
        "91_CALC_SCORES!AB11": 'READY prefix',
        "03_COMPARE_2!A14": '비교 가능',
      },
      '03_duplicate_id': {
        "91_CALC_SCORES!AB7": 'ERROR: DUPLICATE ID',
        "03_COMPARE_2!A14": 'N/A: ID 없음/중복',
        "99_QA_AUDIT!B16": 2,
        "99_QA_AUDIT!D16": 'FAIL',
      },
      '04_self_pair': {
        "03_COMPARE_2!A14": 'N/A: 동일 관측 선택',
        "03_COMPARE_2!D8": 'blank',
      },
      '05_cohort_mismatch': {
        "03_COMPARE_2!A14": 'N/A: cohort 불일치',
        "05_ECON_INTERPRET!I8": 'PAIR NOT COMPARABLE',
        "06_SENSITIVITY!B8": 'blank',
      },
      '06_invalid_exposure_triplet': {
        "02_INPUT_ECON_BASES!AA7": 'ERROR: LOW/BASE/HIGH',
        "05_ECON_INTERPRET!I8": 'EXPOSURE INPUT ERROR',
        "05_ECON_INTERPRET!M8": 'blank',
      },
      '07_average_tie_rank': {
        "04_COMPARE_N!E11": 'same half-rank as E12',
      },
      '08_capacity_row_100': {
        "91_CALC_SCORES!Y106": 'finite number',
        "91_CALC_SCORES!AB106": 'READY prefix',
      },
      '09_lowercase_id': {
        "91_CALC_SCORES!AB11": 'ERROR: ID FORMAT',
        "99_QA_AUDIT!B16": 1,
        "99_QA_AUDIT!D16": 'FAIL',
      },
      '10_wildcard_id': {
        "91_CALC_SCORES!AB11": 'ERROR: ID FORMAT',
        "99_QA_AUDIT!B16": 1,
        "99_QA_AUDIT!D16": 'FAIL',
      },
      '11_zero_economic_base': {
        "02_INPUT_ECON_BASES!AA7:AA8": 'READY',
        "05_ECON_INTERPRET!I10": 'AVAILABLE - DO NOT SUM',
        "05_ECON_INTERPRET!J10:O10": 'numeric zero',
      },
      '12_identical_pair_context_only': {
        "03_COMPARE_2!A14": '비교 가능',
        "03_COMPARE_2!D8": 'numeric zero',
        "05_ECON_INTERPRET!I8": 'AVAILABLE - CONTEXT ONLY',
        "05_ECON_INTERPRET!M8:R8": 'numeric zero',
      },
    },
  };
  await fs.writeFile(path.join(options.outputDir, 'scenario_manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
  console.log(`WROTE ${generated.length} CPII workbook scenarios to ${path.relative(PROJECT_ROOT, options.outputDir)}`);
}

let options;
try {
  options = parseArgs(process.argv.slice(2));
  await run(options);
} catch (error) {
  console.error(`FAIL workbook scenario generation: ${error?.message ?? error}`);
  process.exitCode = 1;
}
