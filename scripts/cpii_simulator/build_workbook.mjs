#!/usr/bin/env node
/** Build the macro-free CPII client workbook using @oai/artifact-tool only. */

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const args = process.argv.slice(2);
const argValue = (name, fallback = null) => {
  const index = args.indexOf(name);
  return index >= 0 && index + 1 < args.length ? args[index + 1] : fallback;
};
const projectRoot = path.resolve(argValue("--project-root", path.resolve(import.meta.dirname, "../..")));
const outputPath = path.resolve(
  argValue("--output", path.join(projectRoot, "outputs/client_delivery/CPII_Comparator_v2/CPII_Company_Comparator.xlsx")),
);
const payloadPath = path.join(
  projectRoot,
  "outputs/tables/cpii_simulator/workbook/workbook_payload.json",
);
const payload = JSON.parse(await fs.readFile(payloadPath, "utf8"));
payload.metadata.workbook_version = "CPII_COMPARATOR_XLSX_V2.0.0";
const capacity = payload.metadata.company_capacity;
const matrixCapacity = payload.metadata.pair_matrix_capacity;

const COLORS = {
  navy: "#172B4D",
  teal: "#0F766E",
  paleTeal: "#DDF4EF",
  blue: "#E8F1FB",
  gray: "#F3F4F6",
  darkGray: "#475569",
  yellow: "#FFF4CC",
  amber: "#F59E0B",
  red: "#FDE2E2",
  redText: "#991B1B",
  green: "#DCFCE7",
  greenText: "#166534",
  white: "#FFFFFF",
  border: "#CBD5E1",
};

const workbook = Workbook.create();
const sheetNames = [
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
];
const sheets = Object.fromEntries(sheetNames.map((name) => [name, workbook.worksheets.add(name)]));

function excelCol(oneBased) {
  let value = oneBased;
  let text = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    text = String.fromCharCode(65 + remainder) + text;
    value = Math.floor((value - 1) / 26);
  }
  return text;
}

function title(sheet, heading, subtitle, lastCol) {
  sheet.showGridLines = false;
  sheet.getRange(`A1:${lastCol}1`).merge();
  sheet.getRange("A1").values = [[heading]];
  sheet.getRange(`A1:${lastCol}1`).format = {
    fill: COLORS.navy,
    font: { bold: true, color: COLORS.white, size: 16 },
    rowHeight: 30,
    verticalAlignment: "center",
  };
  sheet.getRange(`A2:${lastCol}3`).merge();
  sheet.getRange("A2").values = [[subtitle]];
  sheet.getRange(`A2:${lastCol}3`).format = {
    fill: COLORS.yellow,
    font: { color: COLORS.redText, size: 10 },
    wrapText: true,
    verticalAlignment: "center",
    rowHeight: 24,
  };
}

function header(range) {
  range.format = {
    fill: COLORS.teal,
    font: { bold: true, color: COLORS.white },
    wrapText: true,
    verticalAlignment: "center",
    horizontalAlignment: "center",
    borders: { preset: "all", style: "thin", color: COLORS.border },
  };
}

function body(range, fill = COLORS.white) {
  range.format = {
    fill,
    borders: { preset: "all", style: "thin", color: COLORS.border },
    verticalAlignment: "center",
  };
}

function fitAndCap(sheet, rangeAddress, cap = 24) {
  const range = sheet.getRange(rangeAddress);
  range.format.autofitColumns();
  range.format.autofitRows();
  range.format.wrapText = true;
  // Explicit widths below keep long text from creating unusably wide sheets.
  return cap;
}

function q(name) {
  return `'${name}'`;
}

function excelText(value) {
  return `"${String(value).replaceAll('"', '""')}"`;
}

function blankPreservingIndex(valueRange, idRange, selector) {
  const indexed = `INDEX(${valueRange},MATCH(${selector},${idRange},0))`;
  return `IFERROR(IF(${indexed}="","",${indexed}),"")`;
}

function numericPreservingIndex(valueRange, idRange, selector) {
  const indexed = `INDEX(${valueRange},MATCH(${selector},${idRange},0))`;
  return `IFERROR(IF(COUNT(${indexed})=0,"",${indexed}),"")`;
}

function eligibleStatus(statusExpression) {
  return `OR(LEFT(${statusExpression},4)="PASS",LEFT(${statusExpression},5)="READY")`;
}

function assertBalancedFormula(formula, label) {
  let depth = 0;
  let inString = false;
  for (const character of formula) {
    if (character === '"') {
      inString = !inString;
    } else if (!inString && character === "(") {
      depth += 1;
    } else if (!inString && character === ")") {
      depth -= 1;
      if (depth < 0) {
        throw new Error(`unbalanced formula (${label}): unexpected closing parenthesis`);
      }
    }
  }
  if (inString || depth !== 0) {
    throw new Error(`unbalanced formula (${label}): quote=${inString}, depth=${depth}`);
  }
  return formula;
}

// 00_README
{
  const s = sheets["00_README"];
  title(
    s,
    "CPII 회사 입력형 비교 도구 v2",
    "이 파일은 방법론 설명·탐색용 베타입니다. 차별·위법성·손해·인과효과를 판정하지 않으며, 10개 변수 결합 기준표본은 159행 중 2행뿐입니다.",
    "H",
  );
  s.getRange("A5:H5").merge();
  s.getRange("A5").values = [["빠른 시작"]];
  header(s.getRange("A5:H5"));
  s.getRange("A6:H10").values = [
    ["1", "01_INPUT_COMPANIES", "파란 셀에 회사별 feature와 비교 메타데이터를 입력합니다.", null, null, null, null, null],
    ["2", "02_INPUT_ECON_BASES", "금액 해석이 필요할 때만 노출액 low/base/high를 입력합니다. 비워도 CPII 점수는 계산됩니다.", null, null, null, null, null],
    ["3", "03_COMPARE_2 / 04_COMPARE_N", "두 회사 상세 또는 최대 100개 cohort별 순위를 확인합니다. pair matrix 화면은 30개까지입니다.", null, null, null, null, null],
    ["4", "05_ECON_INTERPRET", "금액은 채널별 조건부 상당액/시나리오입니다. overlap family가 있어 합계를 제공하지 않습니다.", null, null, null, null, null],
    ["5", "06_SENSITIVITY / 99_QA_AUDIT", "대체사양·저지원·중복채널과 Python 기준값 일치를 확인합니다.", null, null, null, null, null],
  ];
  s.getRange("A6:A10").format = { fill: COLORS.teal, font: { bold: true, color: COLORS.white }, horizontalAlignment: "center" };
  body(s.getRange("B6:H10"), COLORS.white);
  s.getRange("A12:H12").merge();
  s.getRange("A12").values = [["0.1점은 무엇을 뜻하나"]];
  header(s.getRange("A12:H12"));
  s.getRange("A13:H16").merge();
  s.getRange("A13").values = [[
    "ΔCPII 0.10점은 feature별 기준분포 위치 차이의 가중합이 0.001이라는 뜻입니다. 비용·매출 0.1% 또는 기업 백분위 0.1%가 아닙니다. 다른 9개 변수가 같다면 규제/시장 feature 하나의 약 0.9%p 위치 차이 또는 위험 feature 하나의 약 1.2%p 위치 차이가 0.10점을 만들 수 있지만, 실제로는 양·음 기여도가 상쇄될 수도 있습니다.",
  ]];
  s.getRange("A13:H16").format = { fill: COLORS.paleTeal, wrapText: true, font: { size: 11 }, verticalAlignment: "center" };
  s.getRange("A18:D25").values = [
    ["항목", "값", "항목", "값"],
    ["Workbook version", payload.metadata.workbook_version, "Method version", payload.metadata.method_version],
    ["Anchor version", payload.metadata.anchor_version, "Release status", payload.metadata.release_status],
    ["기준분포 행", payload.metadata.joint_reference_row_count, "10변수 결합완전 행", payload.metadata.joint_complete_reference_count],
    ["결합지지 상태", payload.metadata.joint_support_eligibility, "저지원 가중치", payload.metadata.low_support_effective_weight],
    ["회사 입력 한도", capacity, "화면 pair matrix 한도", matrixCapacity],
    ["점수 의미", "feature별 주변분포 위치의 가중평균", "기업 백분위", "제공하지 않음"],
    ["금액 총합", "제공하지 않음", "low/base/high", "민감도 범위(신뢰구간 아님)"],
  ];
  header(s.getRange("A18:D18"));
  body(s.getRange("A19:D25"));
  s.getRange("D22").format.numberFormat = "0.00%";
  s.getRange("A27:H29").merge();
  s.getRange("A27").values = [[
    "용어 규칙: 국내기업과 해외기업이 동일 산업·서비스·시장·기간·등록 benchmark로 비교되고 품질 게이트를 통과한 경우에도 ‘역차별 가설 관련 구조적 부담격차’라고만 표시합니다. 이 지표만으로 차별 여부를 단정할 수 없습니다.",
  ]];
  s.getRange("A27:H29").format = { fill: COLORS.red, font: { color: COLORS.redText, bold: true }, wrapText: true };
  s.getRange("A:A").format.columnWidth = 18;
  s.getRange("B:B").format.columnWidth = 42;
  s.getRange("C:C").format.columnWidth = 20;
  s.getRange("D:D").format.columnWidth = 42;
  s.getRange("E:H").format.columnWidth = 18;
  s.freezePanes.freezeRows(3);
  s.getRange("A31:H31").merge();
  s.getRange("A31").values = [["v2 검증 보강 · 점수 산식과 고정 기준분포 유지"]];
  header(s.getRange("A31:H31"));
  const versionNotes = [
    "인프라 결합 검사: 인프라 결합값 = 망비용률 × 해외의존비율. v1의 열 참조 오류 수정.",
    "예시 입력 수정 후에도 정상 입력의 비교 허용. 원래 10개 값과 일치할 때만 합성 예시 기대점수 대조.",
    "관측 ID는 영문 대문자·숫자·하이픈·밑줄·마침표 1~64자. 회사명은 한국어 등 자유 입력.",
    "출처일은 2000~2100년의 실제 날짜를 YYYY-MM-DD 텍스트로 입력. 비교집단 필드의 앞뒤 공백 금지.",
    "산업·서비스·시장·분기·기준 ID의 대소문자까지 일치한 관측끼리 비교. 통제항목은 지정값 그대로 입력.",
    "양의 A−B는 A의 부담지수가 더 높다는 뜻. 기준−개선후로 정의한 정책 점수 감소량과 부호 기준 구별.",
    "노출계수는 입력값에 이미 반영한 조정의 기록이며 자동 승산 없음. 출처 시트 기록은 외부 사실 검증의 대체 불가.",
    "동봉 비교기준은 합성 예시 전용 1건. 실제 기업 비교 전에는 실제 비교군·산식·원천 해시의 등록과 통합문서 재생성 필요.",
  ];
  versionNotes.forEach((note, index) => {
    const row = 32 + index;
    s.getRange(`A${row}:H${row}`).merge();
    s.getRange(`A${row}`).values = [[note]];
    s.getRange(`A${row}:H${row}`).format = { wrapText: true, rowHeight: 27, font: { size: 11 }, verticalAlignment: "center" };
  });
}

// 01_INPUT_COMPANIES
const companyFields = [
  "observation_id", "company_name", "company_group", "sector", "service_scope", "focal_market",
  "reporting_period", "benchmark_id", "currency", "price_year", "input_quality", "synthetic_flag",
  "construction_mode", "source_id", "source_date", "carry_lag_q", "market_common_exposure_adjusted",
  "company_exposure_factor", "source_note", ...payload.active_order,
];
const companyHeaderKo = [
  "관측 ID", "회사명", "그룹", "산업", "서비스", "시장", "기간", "Benchmark ID", "통화", "가격연도",
  "품질", "합성", "구축방식", "출처 ID", "출처일", "이월분기", "시장공통값 보정", "회사노출계수", "메모",
  ...payload.feature_config.map((row) => row.display_name_ko),
];
{
  const s = sheets["01_INPUT_COMPANIES"];
  const inputLastCol = excelCol(companyFields.length);
  const lastCol = excelCol(companyFields.length + 1);
  title(s, "01 | 회사·Feature 입력", "파란 셀만 편집하십시오. 한 행은 하나의 회사-시장-기간 관측입니다. 입력 검증이 PASS/READY인 서로 다른 관측만 비교됩니다.", lastCol);
  s.getRange(`A6:${inputLastCol}6`).values = [companyHeaderKo];
  s.getRange(`${lastCol}6`).values = [["입력 검증"]];
  header(s.getRange(`A6:${lastCol}6`));
  const values = Array.from({ length: capacity }, (_, index) =>
    companyFields.map((field) => (index < payload.companies.length ? payload.companies[index][field] ?? null : null)),
  );
  s.getRange(`A7:${inputLastCol}${6 + capacity}`).values = values;
  body(s.getRange(`A7:${inputLastCol}${6 + capacity}`), COLORS.blue);
  s.tables.add(`A6:${inputLastCol}${6 + capacity}`, true, "InputCompaniesTable").style = "TableStyleMedium2";
  s.getRange(`C7:C${6 + capacity}`).dataValidation = { rule: { type: "list", values: ["domestic", "foreign", "other"] } };
  s.getRange(`K7:K${6 + capacity}`).dataValidation = { rule: { type: "list", values: ["A", "B", "C", "SYNTHETIC"] } };
  s.getRange(`L7:L${6 + capacity}`).dataValidation = { rule: { type: "list", values: ["yes", "no"] } };
  s.getRange(`M7:M${6 + capacity}`).dataValidation = { rule: { type: "list", values: ["direct", "derived", "proxy", "mixed"] } };
  s.getRange(`Q7:Q${6 + capacity}`).dataValidation = { rule: { type: "list", values: ["yes", "no"] } };
  s.getRange(`J7:J${6 + capacity}`).dataValidation = { rule: { type: "whole", operator: "between", formula1: 2000, formula2: 2100 } };
  s.getRange(`P7:P${6 + capacity}`).dataValidation = { rule: { type: "whole", operator: "greaterThanOrEqual", formula1: 0 } };
  s.getRange(`R7:R${6 + capacity}`).dataValidation = { rule: { type: "decimal", operator: "between", formula1: 0, formula2: 1 } };
  s.getRange(`H7:H${6 + capacity}`).dataValidation = { rule: { type: "list", values: payload.benchmarks.map((row) => row.benchmark_id) } };
  s.getRange(`I7:I${6 + capacity}`).dataValidation = { rule: { type: "list", values: payload.supported_currencies } };
  for (let featureIndex = 0; featureIndex < payload.active_order.length; featureIndex += 1) {
    const featureCol = excelCol(20 + featureIndex);
    s.getRange(`${featureCol}7:${featureCol}${6 + capacity}`).dataValidation = {
      rule: { type: "decimal", operator: "between", formula1: -1e307, formula2: 1e307 },
    };
  }
  s.getRange(`T7:${inputLastCol}${6 + capacity}`).format.numberFormat = "0.000000";
  s.getRange(`${lastCol}7:${lastCol}${6 + capacity}`).formulas = Array.from(
    { length: capacity },
    (_, index) => [`=IF(A${7 + index}="","",${q("91_CALC_SCORES")}!$AB$${7 + index})`],
  );
  body(s.getRange(`${lastCol}7:${lastCol}${6 + capacity}`), COLORS.gray);
  s.getRange(`A7:A${6 + capacity}`).conditionalFormats.add("duplicateValues", { format: { fill: COLORS.red, font: { color: COLORS.redText } } });
  s.getRange(`${lastCol}7:${lastCol}${6 + capacity}`).conditionalFormats.add("containsText", { text: "ERROR", format: { fill: COLORS.red, font: { color: COLORS.redText, bold: true } } });
  s.getRange(`${lastCol}7:${lastCol}${6 + capacity}`).conditionalFormats.add("containsText", { text: "INPUT REQUIRED", format: { fill: COLORS.red, font: { color: COLORS.redText, bold: true } } });
  s.getRange(`${lastCol}7:${lastCol}${6 + capacity}`).conditionalFormats.add("containsText", { text: "CHECK", format: { fill: COLORS.red, font: { color: COLORS.redText, bold: true } } });
  s.getRange(`${lastCol}7:${lastCol}${6 + capacity}`).conditionalFormats.add("containsText", { text: "READY", format: { fill: COLORS.green, font: { color: COLORS.greenText } } });
  s.getRange(`${lastCol}7:${lastCol}${6 + capacity}`).conditionalFormats.add("containsText", { text: "PASS", format: { fill: COLORS.green, font: { color: COLORS.greenText } } });
  s.freezePanes.freezeRows(6);
  s.freezePanes.freezeColumns(2);
  fitAndCap(s, `A6:${lastCol}${Math.min(16, 6 + capacity)}`);
  s.getRange("A:A").format.columnWidth = 17;
  s.getRange("B:B").format.columnWidth = 21;
  s.getRange("C:C").format.columnWidth = 14;
  s.getRange("D:G").format.columnWidth = 20;
  s.getRange("H:H").format.columnWidth = 34;
  s.getRange("I:M").format.columnWidth = 16;
  s.getRange("N:N").format.columnWidth = 30;
  s.getRange("O:R").format.columnWidth = 18;
  s.getRange("S:S").format.columnWidth = 46;
  s.getRange(`T:${inputLastCol}`).format.columnWidth = 19;
  s.getRange(`${lastCol}:${lastCol}`).format.columnWidth = 31;
  s.getRange(`A6:${lastCol}6`).format.rowHeight = 42;
  s.getRange("A7:S10").format.wrapText = true;
  s.getRange("A7:S10").format.autofitRows();
}

// 02_INPUT_ECON_BASES
const exposureFields = [
  "observation_id", "currency", "price_year", "exposure_period", "period_year_fraction",
  "revenue_low", "revenue_base", "revenue_high",
  "positive_pretax_income_low", "positive_pretax_income_base", "positive_pretax_income_high",
  "average_interest_bearing_debt_low", "average_interest_bearing_debt_base", "average_interest_bearing_debt_high",
  "content_investment_low", "content_investment_base", "content_investment_high",
  "eligible_market_revenue_low", "eligible_market_revenue_base", "eligible_market_revenue_high",
  "scenario_conversion_rate_low", "scenario_conversion_rate_base", "scenario_conversion_rate_high",
  "exposure_source_id", "exposure_quality", "exposure_note",
];
{
  const s = sheets["02_INPUT_ECON_BASES"];
  const inputLastCol = excelCol(exposureFields.length);
  const lastCol = excelCol(exposureFields.length + 1);
  title(s, "02 | 경제 노출액 입력", "점수 계산에는 필요하지 않습니다. 금액 해석용 low/base/high는 완전한 세 값으로 입력하고 AA열 검증이 READY인지 확인하십시오.", lastCol);
  const display = [
    "관측 ID", "통화", "가격연도", "노출기간", "연환산계수",
    "매출 Low", "매출 Base", "매출 High", "양(+) 세전이익 Low", "양(+) 세전이익 Base", "양(+) 세전이익 High",
    "평균 이자부부채 Low", "평균 이자부부채 Base", "평균 이자부부채 High",
    "콘텐츠투자 Low", "콘텐츠투자 Base", "콘텐츠투자 High", "전이대상매출 Low", "전이대상매출 Base", "전이대상매출 High",
    "전환율 Low", "전환율 Base", "전환율 High", "출처 ID", "품질", "메모",
  ];
  s.getRange(`A6:${inputLastCol}6`).values = [display];
  s.getRange(`${lastCol}6`).values = [["노출행 검증"]];
  header(s.getRange(`A6:${lastCol}6`));
  const values = Array.from({ length: capacity }, (_, index) =>
    exposureFields.map((field) => (index < payload.exposures.length ? payload.exposures[index][field] ?? null : null)),
  );
  s.getRange(`A7:${inputLastCol}${6 + capacity}`).values = values;
  body(s.getRange(`A7:${inputLastCol}${6 + capacity}`), COLORS.blue);
  s.tables.add(`A6:${inputLastCol}${6 + capacity}`, true, "InputEconomicBasesTable").style = "TableStyleMedium2";
  s.getRange(`A7:A${6 + capacity}`).dataValidation = { rule: { type: "list", formula1: `INDIRECT("'01_INPUT_COMPANIES'!$A$7:$A$${6 + capacity}")` } };
  s.getRange(`B7:B${6 + capacity}`).dataValidation = { rule: { type: "list", values: payload.supported_currencies } };
  s.getRange(`C7:C${6 + capacity}`).dataValidation = { rule: { type: "whole", operator: "between", formula1: 2000, formula2: 2100 } };
  s.getRange(`E7:E${6 + capacity}`).dataValidation = { rule: { type: "decimal", operator: "between", formula1: 0.000001, formula2: 1 } };
  s.getRange(`F7:W${6 + capacity}`).dataValidation = { rule: { type: "decimal", operator: "greaterThanOrEqual", formula1: 0 } };
  s.getRange(`U7:W${6 + capacity}`).dataValidation = { rule: { type: "decimal", operator: "between", formula1: 0, formula2: 1 } };
  s.getRange(`Y7:Y${6 + capacity}`).dataValidation = { rule: { type: "list", values: ["A", "B", "C", "SYNTHETIC"] } };
  s.getRange(`F7:T${6 + capacity}`).format.numberFormat = "#,##0;[Red]-#,##0";
  s.getRange(`U7:W${6 + capacity}`).format.numberFormat = "0.00%";
  const companyIds = `${q("01_INPUT_COMPANIES")}!$A$7:$A$${6 + capacity}`;
  const companyValue = (column, row) => blankPreservingIndex(
    `${q("01_INPUT_COMPANIES")}!$${column}$7:$${column}$${6 + capacity}`,
    companyIds,
    `$A${row}`,
  );
  const tripletValid = (firstColumn, middleColumn, lastColumn, row, unitInterval = false) => {
    const range = `$${firstColumn}${row}:$${lastColumn}${row}`;
    const upperCheck = unitInterval ? `,MAX(${range})<=1` : "";
    return `OR(COUNTBLANK(${range})=3,AND(COUNT(${range})=3,MIN(${range})>=0,$${firstColumn}${row}<=$${middleColumn}${row},$${middleColumn}${row}<=$${lastColumn}${row}${upperCheck}))`;
  };
  const validationFormulas = [];
  for (let index = 0; index < capacity; index += 1) {
    const row = 7 + index;
    const tripletsOk = [
      tripletValid("F", "G", "H", row),
      tripletValid("I", "J", "K", row),
      tripletValid("L", "M", "N", row),
      tripletValid("O", "P", "Q", row),
      tripletValid("R", "S", "T", row),
      tripletValid("U", "V", "W", row, true),
    ].join(",");
    const idUnsafe = `OR($A${row}<>TRIM($A${row}),NOT(EXACT($A${row},UPPER($A${row}))),LEN($A${row})>64,ISNUMBER(FIND("*",$A${row})),ISNUMBER(FIND("?",$A${row})),ISNUMBER(FIND("~",$A${row})))`;
    const transferPairOk = `OR(AND(COUNTBLANK($R${row}:$T${row})=3,COUNTBLANK($U${row}:$W${row})=3),AND(COUNT($R${row}:$T${row})=3,COUNT($U${row}:$W${row})=3))`;
    const validationFormula =
      `=IF($A${row}="","",IF(${idUnsafe},"ERROR: ID FORMAT",IF(COUNTIF($A$7:$A$${6 + capacity},$A${row})<>1,"ERROR: DUPLICATE EXPOSURE ID",IF(COUNTIF(${companyIds},$A${row})<>1,"ERROR: COMPANY ID",IF(OR($B${row}="",COUNTIF(${q("92_REF_VARIABLES")}!$L$21:$L$${20 + payload.supported_currencies.length},$B${row})<>1),"ERROR: CURRENCY",IF(OR(NOT(ISNUMBER($C${row})),$C${row}<>INT($C${row}),$C${row}<2000,$C${row}>2100),"ERROR: PRICE YEAR",IF(OR($D${row}="",AND($D${row}<>${companyValue("G", row)},$D${row}<>LEFT(${companyValue("G", row)},4))),"ERROR: EXPOSURE PERIOD",IF(OR(NOT(ISNUMBER($E${row})),$E${row}<=0,$E${row}>1),"ERROR: PERIOD FRACTION",IF(OR($B${row}<>${companyValue("I", row)},$C${row}<>${companyValue("J", row)}),"ERROR: COMPANY CURRENCY/YEAR",IF(NOT(OR($Y${row}="A",$Y${row}="B",$Y${row}="C",$Y${row}="SYNTHETIC")),"ERROR: QUALITY",IF(NOT(AND(${tripletsOk})),"ERROR: LOW/BASE/HIGH",IF(NOT(${transferPairOk}),"ERROR: TRANSFER ASSUMPTION",IF(AND(COUNTA($F${row}:$W${row})>0,$X${row}=""),"ERROR: SOURCE","READY")))))))))))))`;
    validationFormulas.push([
      assertBalancedFormula(validationFormula, `02_INPUT_ECON_BASES!${lastCol}${row}`),
    ]);
  }
  s.getRange(`${lastCol}7:${lastCol}${6 + capacity}`).formulas = validationFormulas;
  body(s.getRange(`${lastCol}7:${lastCol}${6 + capacity}`), COLORS.gray);
  s.getRange(`${lastCol}7:${lastCol}${6 + capacity}`).conditionalFormats.add("containsText", { text: "ERROR", format: { fill: COLORS.red, font: { color: COLORS.redText, bold: true } } });
  s.getRange(`${lastCol}7:${lastCol}${6 + capacity}`).conditionalFormats.add("containsText", { text: "READY", format: { fill: COLORS.green, font: { color: COLORS.greenText } } });
  s.freezePanes.freezeRows(6);
  s.freezePanes.freezeColumns(1);
  fitAndCap(s, `A6:${lastCol}${Math.min(14, 6 + capacity)}`);
  s.getRange("A:E").format.columnWidth = 15;
  s.getRange("F:W").format.columnWidth = 18;
  s.getRange("X:X").format.columnWidth = 30;
  s.getRange("Y:Y").format.columnWidth = 16;
  s.getRange("Z:Z").format.columnWidth = 52;
  s.getRange(`${lastCol}:${lastCol}`).format.columnWidth = 34;
  s.getRange(`A6:${lastCol}6`).format.rowHeight = 42;
  s.getRange("X7:Z10").format.wrapText = true;
  s.getRange("A7:Z10").format.autofitRows();
}

// 07_INPUT_PROVENANCE
{
  const s = sheets["07_INPUT_PROVENANCE"];
  const fields = ["observation_id", "variable_name", "source_id", "source_date", "input_quality", "construction_mode", "carry_lag_q", "benchmark_id", "formula_note", "synthetic_flag"];
  title(s, "07 | Feature별 Provenance", "각 회사×feature마다 출처·시점·구축방식을 보존합니다. 행 수준 요약만으로 서로 다른 변수의 근거를 대체할 수 없습니다.", "J");
  s.getRange("A6:J6").values = [["관측 ID", "변수", "출처 ID", "기준일", "품질", "구축방식", "이월분기", "Benchmark ID", "산식·가정", "합성"]];
  header(s.getRange("A6:J6"));
  const provenanceCapacity = capacity * payload.active_order.length;
  const values = Array.from({ length: provenanceCapacity }, (_, index) =>
    fields.map((field) => (index < payload.provenance.length ? payload.provenance[index][field] ?? null : null)),
  );
  s.getRange(`A7:J${6 + provenanceCapacity}`).values = values;
  body(s.getRange(`A7:J${6 + provenanceCapacity}`), COLORS.blue);
  s.tables.add(`A6:J${6 + provenanceCapacity}`, true, "InputFeatureProvenanceTable").style = "TableStyleMedium2";
  s.getRange(`E7:E${6 + provenanceCapacity}`).dataValidation = { rule: { type: "list", values: ["A", "B", "C", "SYNTHETIC"] } };
  s.getRange(`F7:F${6 + provenanceCapacity}`).dataValidation = { rule: { type: "list", values: ["direct", "derived", "proxy"] } };
  s.getRange(`J7:J${6 + provenanceCapacity}`).dataValidation = { rule: { type: "list", values: ["yes", "no"] } };
  s.freezePanes.freezeRows(6);
  s.getRange("A:A").format.columnWidth = 18;
  s.getRange("B:B").format.columnWidth = 32;
  s.getRange("C:C").format.columnWidth = 38;
  s.getRange("D:G").format.columnWidth = 18;
  s.getRange("H:H").format.columnWidth = 34;
  s.getRange("I:I").format.columnWidth = 54;
  s.getRange("J:J").format.columnWidth = 12;
  s.getRange("A6:J6").format.rowHeight = 36;
  s.getRange(`C7:C${6 + provenanceCapacity}`).format.wrapText = true;
  s.getRange(`H7:I${6 + provenanceCapacity}`).format.wrapText = true;
  s.getRange(`A7:J${6 + payload.provenance.length}`).format.autofitRows();
}

// 92_REF_VARIABLES
const refFields = [
  "variable_name", "display_name_ko", "subindex", "direction_code", "input_unit",
  "rank_key_lower", "rank_key_upper", "reference_n", "effective_feature_weight", "low_support_anchor",
  "interpretation_class", "bridge_status", "economic_base", "overlap_family",
  "operational_definition", "plain_language_ko",
];
{
  const s = sheets["92_REF_VARIABLES"];
  title(s, "92 | 변수·가중치·경제 브리지 참조", "계산 참조 시트입니다. 사용자 편집 금지. 파란 입력 시트와 달리 회색으로 표시됩니다.", "P");
  s.getRange("A6:P6").values = [["변수", "표시명", "하위지수", "방향", "단위", "Rank key 하단", "Rank key 상단", "기준 N", "유효가중치", "저지원", "해석 유형", "브리지", "경제기준", "중복군", "운영 정의", "쉬운 설명"]];
  header(s.getRange("A6:P6"));
  s.getRange(`A7:P${6 + payload.feature_config.length}`).values = payload.feature_config.map((row) => refFields.map((field) => row[field] ?? null));
  body(s.getRange(`A7:P${6 + payload.feature_config.length}`), COLORS.gray);
  s.getRange(`F7:G${6 + payload.feature_config.length}`).format.numberFormat = "0.000000000000";
  s.getRange(`I7:I${6 + payload.feature_config.length}`).format.numberFormat = "0.000000";
  s.getRange(`J7:J${6 + payload.feature_config.length}`).conditionalFormats.add("containsText", { text: "yes", format: { fill: COLORS.red, font: { color: COLORS.redText, bold: true } } });
  s.freezePanes.freezeRows(6);
  s.getRange("A:A").format.columnWidth = 34;
  s.getRange("B:B").format.columnWidth = 30;
  s.getRange("C:C").format.columnWidth = 14;
  s.getRange("D:D").format.columnWidth = 10;
  s.getRange("E:E").format.columnWidth = 18;
  s.getRange("F:G").format.columnWidth = 22;
  s.getRange("H:J").format.columnWidth = 14;
  s.getRange("K:K").format.columnWidth = 30;
  s.getRange("L:L").format.columnWidth = 18;
  s.getRange("M:N").format.columnWidth = 28;
  s.getRange("O:P").format.columnWidth = 58;
  s.getRange("A6:P6").format.rowHeight = 40;
  s.getRange(`A7:B${6 + payload.feature_config.length}`).format.wrapText = true;
  s.getRange(`K7:P${6 + payload.feature_config.length}`).format.wrapText = true;
  s.getRange(`A7:P${6 + payload.feature_config.length}`).format.autofitRows();
  s.getRange("A19:J19").merge();
  s.getRange("A19").values = [["등록 Benchmark (ID·산업·기간·합성 전용 여부 검증용)"]];
  header(s.getRange("A19:J19"));
  const benchmarkFields = ["benchmark_id", "sector", "reporting_period", "cohort_definition", "calculation_rule", "benchmark_version", "source_type", "source_hash", "status", "notes"];
  s.getRange("A20:J20").values = [["Benchmark ID", "산업", "기간", "Cohort 정의", "산식", "버전", "원천유형", "원천 SHA-256", "상태", "주의"]];
  header(s.getRange("A20:J20"));
  s.getRange(`A21:J${20 + payload.benchmarks.length}`).values = payload.benchmarks.map(
    (row) => benchmarkFields.map((field) => row[field] ?? null),
  );
  body(s.getRange(`A21:J${20 + payload.benchmarks.length}`), COLORS.gray);
  s.getRange("L19:P19").merge();
  s.getRange("L19").values = [["지원 통화 코드"]];
  header(s.getRange("L19:P19"));
  s.getRange("L20").values = [["ISO code"]];
  header(s.getRange("L20:L20"));
  s.getRange(`L21:L${20 + payload.supported_currencies.length}`).values = payload.supported_currencies.map((code) => [code]);
  body(s.getRange(`L21:L${20 + payload.supported_currencies.length}`), COLORS.gray);
}

// 93_REF_ANCHORS
{
  const s = sheets["93_REF_ANCHORS"];
  title(s, "93 | 동결 Anchor Rank Keys", "계산 참조 시트입니다. signed-log가 단조함을 이용한 directed raw-space projection이며 Python canonical normalizer와 검증됩니다.", "C");
  s.getRange("A6:C6").values = [["변수", "참조 순서", "Directed rank key"]];
  header(s.getRange("A6:C6"));
  s.getRange(`A7:C${6 + payload.anchor_rank_keys.length}`).values = payload.anchor_rank_keys.map((row) => [row.variable_name, row.reference_order, row.rank_key_directed]);
  body(s.getRange(`A7:C${6 + payload.anchor_rank_keys.length}`), COLORS.gray);
  s.getRange(`C7:C${6 + payload.anchor_rank_keys.length}`).format.numberFormat = "0.000000000000";
  s.tables.add(`A6:C${6 + payload.anchor_rank_keys.length}`, true, "FrozenAnchorRankKeysTable").style = "TableStyleMedium4";
  s.freezePanes.freezeRows(6);
  s.getRange("A:A").format.columnWidth = 32;
  s.getRange("B:C").format.columnWidth = 22;
}

// 90_CALC_FEATURES
{
  const s = sheets["90_CALC_FEATURES"];
  title(s, "90 | Feature 정규화 계산", "계산 시트입니다. 사용자 편집 금지. 선택 회사 집합이 아니라 동결 anchor로 각 feature 위치를 계산합니다.", "N");
  s.getRange("A6:N6").values = [["입력행", "관측 ID", "회사명", "변수", "원값", "방향", "Clipped rank key", "기준 N", "정규화 위치", "상태", "Key 하단", "Key 상단", "유효가중치", "저지원"]];
  header(s.getRange("A6:N6"));
  const totalRows = capacity * payload.active_order.length;
  const anchorEnd = 6 + payload.anchor_rank_keys.length;
  const values = [];
  const formulas = [];
  for (let companyIndex = 0; companyIndex < capacity; companyIndex += 1) {
    const inputRow = 7 + companyIndex;
    for (let featureIndex = 0; featureIndex < payload.active_order.length; featureIndex += 1) {
      const feature = payload.feature_config[featureIndex];
      const featureInputCol = excelCol(20 + featureIndex);
      const calcRow = 7 + companyIndex * payload.active_order.length + featureIndex;
      values.push([
        companyIndex + 1, null, null, feature.variable_name, null, feature.direction_code, null,
        feature.reference_n, null, null, feature.rank_key_lower, feature.rank_key_upper,
        feature.effective_feature_weight, feature.low_support_anchor,
      ]);
      formulas.push([
        null,
        `=IF(${q("01_INPUT_COMPANIES")}!$A$${inputRow}="","",${q("01_INPUT_COMPANIES")}!$A$${inputRow})`,
        `=IF(B${calcRow}="","",${q("01_INPUT_COMPANIES")}!$B$${inputRow})`,
        null,
        `=IF(OR(B${calcRow}="",COUNT(${q("01_INPUT_COMPANIES")}!$${featureInputCol}$${inputRow})=0),"",${q("01_INPUT_COMPANIES")}!$${featureInputCol}$${inputRow})`,
        null,
        `=IF(NOT(ISNUMBER(E${calcRow})),"",MAX(K${calcRow},MIN(L${calcRow},E${calcRow}*F${calcRow})))`,
        null,
        `=IF(COUNT(G${calcRow})=0,"",(COUNTIFS(${q("93_REF_ANCHORS")}!$A$7:$A$${anchorEnd},D${calcRow},${q("93_REF_ANCHORS")}!$C$7:$C$${anchorEnd},"<"&G${calcRow})+COUNTIFS(${q("93_REF_ANCHORS")}!$A$7:$A$${anchorEnd},D${calcRow},${q("93_REF_ANCHORS")}!$C$7:$C$${anchorEnd},"<="&G${calcRow})-1)/(2*(H${calcRow}-1)))`,
        `=IF(B${calcRow}="","",IF(COUNT(E${calcRow})=0,"MISSING",IF(NOT(ISNUMBER(E${calcRow})),"INVALID",IF(E${calcRow}*F${calcRow}<K${calcRow},"WINSORIZED LOW",IF(E${calcRow}*F${calcRow}>L${calcRow},"WINSORIZED HIGH","OK")))))`,
        null, null, null, null,
      ]);
    }
  }
  s.getRange(`A7:N${6 + totalRows}`).values = values;
  s.getRange(`B7:C${6 + totalRows}`).formulas = formulas.map((row) => row.slice(1, 3));
  s.getRange(`E7:E${6 + totalRows}`).formulas = formulas.map((row) => [row[4]]);
  s.getRange(`G7:G${6 + totalRows}`).formulas = formulas.map((row) => [row[6]]);
  s.getRange(`I7:J${6 + totalRows}`).formulas = formulas.map((row) => row.slice(8, 10));
  body(s.getRange(`A7:N${6 + totalRows}`), COLORS.gray);
  s.getRange(`E7:I${6 + totalRows}`).format.numberFormat = "0.000000000000";
  s.getRange(`J7:J${6 + totalRows}`).conditionalFormats.add("containsText", { text: "MISSING", format: { fill: COLORS.red, font: { color: COLORS.redText } } });
  s.getRange(`J7:J${6 + totalRows}`).conditionalFormats.add("containsText", { text: "INVALID", format: { fill: COLORS.red, font: { color: COLORS.redText } } });
  s.getRange(`J7:J${6 + totalRows}`).conditionalFormats.add("containsText", { text: "WINSORIZED", format: { fill: COLORS.yellow, font: { color: COLORS.redText } } });
  s.freezePanes.freezeRows(6);
  s.getRange("A:A").format.columnWidth = 10;
  s.getRange("B:B").format.columnWidth = 18;
  s.getRange("C:C").format.columnWidth = 22;
  s.getRange("D:D").format.columnWidth = 34;
  s.getRange("E:N").format.columnWidth = 17;
}

// 94_EXPECTED_OUTPUTS (must exist before score formulas are written)
const expectedFields = ["observation_id", "CPII", "I_reg", "I_risk", "I_market", ...payload.active_order.map((name) => `norm_${name}`)];
{
  const s = sheets["94_EXPECTED_OUTPUTS"];
  title(s, "94 | Python Golden Outputs", "합성 예시의 Python 기준값입니다. 계산 수식 parity와 동일점수·상이금액 사례를 검증합니다.", "P");
  s.getRange(`A6:${excelCol(expectedFields.length)}6`).values = [expectedFields];
  header(s.getRange(`A6:${excelCol(expectedFields.length)}6`));
  s.getRange(`A7:${excelCol(expectedFields.length)}${6 + payload.expected_scores.length}`).values = payload.expected_scores.map((row) => expectedFields.map((field) => row[field] ?? null));
  body(s.getRange(`A7:${excelCol(expectedFields.length)}${6 + payload.expected_scores.length}`), COLORS.gray);
  s.getRange("A13:I13").values = [["예시 pair", "A", "B", "단일 driver", "ΔCPII 점", "공통노출 Base", "공통규모 금액 KRW", "해석유형", "합성자료 경고"]];
  header(s.getRange("A13:I13"));
  const goldenFields = ["example_pair", "observation_id_a", "observation_id_b", "single_changed_driver", "delta_cpii_points", "common_exposure_base", "common_size_amount_base_krw", "interpretation_class", "synthetic_disclaimer"];
  s.getRange(`A14:I${13 + payload.golden_equal_gap_summary.length}`).values = payload.golden_equal_gap_summary.map((row) => goldenFields.map((field) => row[field] ?? null));
  body(s.getRange(`A14:I${13 + payload.golden_equal_gap_summary.length}`), COLORS.gray);
  s.getRange("E14:G15").format.numberFormat = "#,##0.000000";
  s.getRange("A18:H21").merge();
  s.getRange("A18").values = [["동일한 약 1.3888889 CPII점이라도 네트워크 비용 채널은 공통매출 1조원에서 약 997.52억원, 조달금리 채널은 평균부채 1,000억원에서 약 2.00억원입니다. 이는 점수당 보편 원화계수가 존재하지 않음을 보여주는 통제된 합성 예시입니다."]];
  s.getRange("A18:H21").format = { fill: COLORS.paleTeal, wrapText: true, font: { bold: true } };
  s.freezePanes.freezeRows(6);
  s.getRange("A:A").format.columnWidth = 26;
  s.getRange("B:C").format.columnWidth = 18;
  s.getRange("D:D").format.columnWidth = 28;
  s.getRange("E:E").format.columnWidth = 18;
  s.getRange("F:G").format.columnWidth = 25;
  s.getRange("H:H").format.columnWidth = 34;
  s.getRange("I:I").format.columnWidth = 58;
  s.getRange("J:P").format.columnWidth = 24;
  s.getRange(`A6:${excelCol(expectedFields.length)}6`).format.rowHeight = 58;
  s.getRange("H14:I15").format.wrapText = true;
  s.getRange("A14:I15").format.autofitRows();
}

// 91_CALC_SCORES
const scoreMetaHeaders = ["관측 ID", "회사명", "그룹", "산업", "서비스", "시장", "기간", "Benchmark", "품질", "구축방식", "Cohort ID"];
const normStartOneBased = scoreMetaHeaders.length + 1;
const axisStartOneBased = normStartOneBased + payload.active_order.length;
const scoreHeaders = [
  ...scoreMetaHeaders,
  ...payload.feature_config.map((row) => `N:${row.display_name_ko}`),
  "I_reg", "I_risk", "I_market", "CPII", "원본예시 기대값", "절대오차", "상태", "해석 제한", "v2 입력계약 검사",
];
{
  const s = sheets["91_CALC_SCORES"];
  const lastCol = excelCol(scoreHeaders.length);
  title(s, "91 | 회사별 CPII 계산", "계산 시트입니다. strict 10-feature 완전관측만 CPII를 표시하며 기업 백분위는 제공하지 않습니다.", lastCol);
  s.getRange(`A6:${lastCol}6`).values = [scoreHeaders];
  header(s.getRange(`A6:${lastCol}6`));
  const formulas = [];
  const inputSheet = q("01_INPUT_COMPANIES");
  const inputIdRange = `${inputSheet}!$A$7:$A$${6 + capacity}`;
  const benchmarkEnd = 20 + payload.benchmarks.length;
  const currencyEnd = 20 + payload.supported_currencies.length;
  for (let index = 0; index < capacity; index += 1) {
    const row = 7 + index;
    const inputRow = 7 + index;
    const firstCalcRow = 7 + index * payload.active_order.length;
    const metadataInputCols = ["A", "B", "C", "D", "E", "F", "G", "H", "K", "M"];
    const rowFormulas = metadataInputCols.map((col) => `=IF(OR(${inputSheet}!$A$${inputRow}="",${inputSheet}!$${col}$${inputRow}=""),"",${inputSheet}!$${col}$${inputRow})`);
    rowFormulas.push(`=IF(OR(A${row}="",COUNTBLANK(D${row}:H${row})>0),"",LEN(D${row})&":"&D${row}&LEN(E${row})&":"&E${row}&LEN(F${row})&":"&F${row}&LEN(G${row})&":"&G${row}&LEN(H${row})&":"&H${row})`);
    for (let featureIndex = 0; featureIndex < payload.active_order.length; featureIndex += 1) {
      rowFormulas.push(`=IF(A${row}="","",${q("90_CALC_FEATURES")}!$I$${firstCalcRow + featureIndex})`);
    }
    const normStart = excelCol(normStartOneBased);
    const regEnd = excelCol(normStartOneBased + 2);
    const riskStart = excelCol(normStartOneBased + 3);
    const riskEnd = excelCol(normStartOneBased + 6);
    const marketStart = excelCol(normStartOneBased + 7);
    const marketEnd = excelCol(normStartOneBased + 9);
    const iRegCol = excelCol(axisStartOneBased);
    const iRiskCol = excelCol(axisStartOneBased + 1);
    const iMarketCol = excelCol(axisStartOneBased + 2);
    const cpiiCol = excelCol(axisStartOneBased + 3);
    const expectedCol = excelCol(axisStartOneBased + 4);
    const diffCol = excelCol(axisStartOneBased + 5);
    rowFormulas.push(`=IF(COUNT(${normStart}${row}:${regEnd}${row})=3,100*AVERAGE(${normStart}${row}:${regEnd}${row}),"")`);
    rowFormulas.push(`=IF(COUNT(${riskStart}${row}:${riskEnd}${row})=4,100*AVERAGE(${riskStart}${row}:${riskEnd}${row}),"")`);
    rowFormulas.push(`=IF(COUNT(${marketStart}${row}:${marketEnd}${row})=3,100*AVERAGE(${marketStart}${row}:${marketEnd}${row}),"")`);
    rowFormulas.push(`=IF(COUNT(${iRegCol}${row}:${iMarketCol}${row})=3,AVERAGE(${iRegCol}${row}:${iMarketCol}${row}),"")`);
    rowFormulas.push(`=IFERROR(INDEX(${q("94_EXPECTED_OUTPUTS")}!$B$7:$B$10,MATCH(A${row},${q("94_EXPECTED_OUTPUTS")}!$A$7:$A$10,0)),"")`);
    rowFormulas.push(`=IF(OR(COUNT(${cpiiCol}${row})=0,COUNT(${expectedCol}${row})=0),"",ABS(${cpiiCol}${row}-${expectedCol}${row}))`);
    const src = (col) => `${inputSheet}!$${col}$${inputRow}`;
    const idUnsafe = `OR(${src("A")}<>TRIM(${src("A")}),NOT(EXACT(${src("A")},UPPER(${src("A")}))),LEN(${src("A")})>64,ISNUMBER(FIND("*",${src("A")})),ISNUMBER(FIND("?",${src("A")})),ISNUMBER(FIND("~",${src("A")})))`;
    const textRequired = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "K", "L", "M", "N", "O", "Q"]
      .map((col) => `LEN(TRIM(${src(col)}&""))=0`).join(",");
    const periodInvalid = `OR(LEN(${src("G")})<>6,MID(${src("G")},5,1)<>"Q",IFERROR(VALUE(LEFT(${src("G")},4)),0)<2000,IFERROR(VALUE(LEFT(${src("G")},4)),0)>2100,IFERROR(VALUE(RIGHT(${src("G")},1)),0)<1,IFERROR(VALUE(RIGHT(${src("G")},1)),0)>4)`;
    const benchmarkInvalid = `OR(COUNTIFS(${q("92_REF_VARIABLES")}!$A$21:$A$${benchmarkEnd},${src("H")},${q("92_REF_VARIABLES")}!$B$21:$B$${benchmarkEnd},${src("D")},${q("92_REF_VARIABLES")}!$C$21:$C$${benchmarkEnd},${src("G")})<>1,AND(IFERROR(INDEX(${q("92_REF_VARIABLES")}!$I$21:$I$${benchmarkEnd},MATCH(${src("H")},${q("92_REF_VARIABLES")}!$A$21:$A$${benchmarkEnd},0)),"")="synthetic_only",${src("L")}<>"yes"))`;
    const featureRangeInvalid = payload.feature_config.map((config, featureIndex) => {
      const col = excelCol(20 + featureIndex);
      return `OR(${src(col)}<${Number(config.soft_min)},${src(col)}>${Number(config.soft_max)})`;
    }).join(",");
    const featureCell = (name) => src(excelCol(20 + payload.active_order.indexOf(name)));
    const infra = featureCell("infra_dependency_ratio");
    const network = featureCell("network_cost_ratio");
    const foreign = featureCell("foreign_dependency_ratio");
    const dependencyInvalid = `ABS(${infra}-${network}*${foreign})>MAX(0.005,0.05*MAX(ABS(${network}*${foreign}),ABS(${infra}),0.000000000001))`;
    const warningSuffix = `IF(${src("K")}="C"," | C QUALITY","")&IF(OR(${src("M")}="proxy",${src("M")}="mixed")," | PROXY/MIXED","")&IF(${src("P")}>1," | CARRY>1","")&IF(OR(${featureRangeInvalid})," | REVIEW RANGE","")&IF(COUNTIF(${q("90_CALC_FEATURES")}!$J$${firstCalcRow}:$J$${firstCalcRow + payload.active_order.length - 1},"WINSORIZED*")>0," | WINSORIZED","")&IF(${dependencyInvalid}," | DEPENDENCY","")`;
    const calculationStatus = `IF(COUNT(${expectedCol}${row})=0,"READY",IF(${diffCol}${row}<=0.0000000001,"PASS","CHECK"))`;
    rowFormulas.push(`=IF(${src("A")}="","",IF(OR(${textRequired},COUNTBLANK(${inputSheet}!$A$${inputRow}:$R$${inputRow})>0),"INPUT REQUIRED",IF(${idUnsafe},"ERROR: ID FORMAT",IF(COUNTIF(${inputIdRange},${src("A")})<>1,"ERROR: DUPLICATE ID",IF(COUNT(${inputSheet}!$T$${inputRow}:$AC$${inputRow})<>10,"INPUT REQUIRED",IF(NOT(OR(${src("C")}="domestic",${src("C")}="foreign",${src("C")}="other")),"ERROR: COMPANY GROUP",IF(${periodInvalid},"ERROR: REPORTING PERIOD",IF(${benchmarkInvalid},"ERROR: BENCHMARK",IF(COUNTIF(${q("92_REF_VARIABLES")}!$L$21:$L$${currencyEnd},${src("I")})<>1,"ERROR: CURRENCY",IF(OR(NOT(ISNUMBER(${src("J")})),${src("J")}<>INT(${src("J")}),${src("J")}<2000,${src("J")}>2100),"ERROR: PRICE YEAR",IF(NOT(OR(${src("K")}="A",${src("K")}="B",${src("K")}="C",${src("K")}="SYNTHETIC")),"ERROR: QUALITY",IF(NOT(OR(AND(${src("L")}="yes",${src("K")}="SYNTHETIC"),AND(${src("L")}="no",${src("K")}<>"SYNTHETIC"))),"ERROR: SYNTHETIC FLAG",IF(NOT(OR(${src("M")}="direct",${src("M")}="derived",${src("M")}="proxy",${src("M")}="mixed")),"ERROR: CONSTRUCTION MODE",IF(OR(NOT(ISNUMBER(${src("P")})),${src("P")}<0,${src("P")}<>INT(${src("P")})),"ERROR: CARRY LAG",IF(${src("Q")}<>"yes","ERROR: EXPOSURE ADJUSTMENT",IF(OR(NOT(ISNUMBER(${src("R")})),${src("R")}<0,${src("R")}>1),"ERROR: EXPOSURE FACTOR",IF(COUNT(${cpiiCol}${row})=0,"ERROR: SCORE",${calculationStatus}&${warningSuffix})))))))))))))))))`);
    rowFormulas.push(`=IF(A${row}="","",IF(${eligibleStatus(`AB${row}`)},"RESEARCH BETA | 저지원 22.22% | 기업 백분위 N/A", "결과 사용 금지 | "&AB${row}))`);
    // Frozen expected scores apply only to unchanged example feature vectors.
    const originalExample = payload.companies.map((company) =>
      `AND(EXACT(A${row},${excelText(company.observation_id)}),COUNT(${inputSheet}!$T$${row}:$AC$${row})=10,${payload.active_order.map((name) => `${featureCell(name)}=${Number(company[name])}`).join(",")})`,
    ).join(",");
    rowFormulas[25] = `=IF(OR(${originalExample}),${rowFormulas[25].slice(1)},"")`;
    const exactChoice = (col, choices) => `OR(${choices.map((value) => `EXACT(${src(col)},${excelText(value)})`).join(",")})`;
    const dateCell = src("O");
    const dateValid = `IFERROR(AND(ISTEXT(${dateCell}),LEN(${dateCell})=10,VALUE(LEFT(${dateCell},4))>=2000,VALUE(LEFT(${dateCell},4))<=2100,EXACT(TEXT(DATE(VALUE(LEFT(${dateCell},4)),VALUE(MID(${dateCell},6,2)),VALUE(RIGHT(${dateCell},2))),"yyyy-mm-dd"),${dateCell})),FALSE)`;
    const trimmed = ["D", "E", "F", "G", "H"].map((col) => `EXACT(${src(col)},TRIM(${src(col)}))`).join(",");
    let invalidIdCharacters = src("A");
    for (const character of "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.") {
      invalidIdCharacters = `SUBSTITUTE(${invalidIdCharacters},"${character}","")`;
    }
    const benchmarkExact = payload.benchmarks.map((_, i) =>
      `AND(EXACT(${q("92_REF_VARIABLES")}!$A$${21 + i},${src("H")}),EXACT(${q("92_REF_VARIABLES")}!$B$${21 + i},${src("D")}),EXACT(${q("92_REF_VARIABLES")}!$C$${21 + i},${src("G")}))`,
    ).join(",");
    const enumValid = [exactChoice("C", ["domestic", "foreign", "other"]), exactChoice("K", ["A", "B", "C", "SYNTHETIC"]), exactChoice("L", ["yes", "no"]), exactChoice("M", ["direct", "derived", "proxy", "mixed"]), exactChoice("Q", ["yes"]), `EXACT(${src("I")},UPPER(${src("I")}))`].join(",");
    rowFormulas.push(`=IF(A${row}="","",IF(LEN(${invalidIdCharacters})>0,"ERROR: ID FORMAT",IF(NOT(AND(${trimmed})),"ERROR: COHORT WHITESPACE",IF(NOT(${dateValid}),"ERROR: SOURCE DATE",IF(NOT(AND(${enumValid})),"ERROR: EXACT ENUM",IF(NOT(IFERROR(OR(${benchmarkExact}),FALSE)),"ERROR: BENCHMARK",""))))))`);
    rowFormulas[27] = `=IF(A${row}="","",IF(AD${row}<>"",AD${row},${rowFormulas[27].slice(1)}))`;
    formulas.push(rowFormulas.map((formula, columnIndex) =>
      assertBalancedFormula(formula, `91_CALC_SCORES!${excelCol(columnIndex + 1)}${row}`),
    ));
  }
  s.getRange(`A7:${lastCol}${6 + capacity}`).formulas = formulas;
  body(s.getRange(`A7:${lastCol}${6 + capacity}`), COLORS.gray);
  s.getRange(`${excelCol(normStartOneBased)}7:${excelCol(axisStartOneBased - 1)}${6 + capacity}`).format.numberFormat = "0.0000000000";
  s.getRange(`${excelCol(axisStartOneBased)}7:${excelCol(axisStartOneBased + 5)}${6 + capacity}`).format.numberFormat = "0.0000000000";
  const statusRange = s.getRange(`${excelCol(axisStartOneBased + 6)}7:${excelCol(axisStartOneBased + 6)}${6 + capacity}`);
  statusRange.conditionalFormats.add("containsText", { text: "CHECK", format: { fill: COLORS.red, font: { color: COLORS.redText } } });
  statusRange.conditionalFormats.add("containsText", { text: "ERROR", format: { fill: COLORS.red, font: { color: COLORS.redText } } });
  statusRange.conditionalFormats.add("containsText", { text: "INPUT REQUIRED", format: { fill: COLORS.red, font: { color: COLORS.redText } } });
  statusRange.conditionalFormats.add("containsText", { text: "READY", format: { fill: COLORS.green, font: { color: COLORS.greenText } } });
  statusRange.conditionalFormats.add("containsText", { text: "PASS", format: { fill: COLORS.green, font: { color: COLORS.greenText } } });
  s.freezePanes.freezeRows(6);
  s.freezePanes.freezeColumns(2);
  s.getRange(`A:${lastCol}`).format.columnWidth = 17;
  s.getRange("B:B").format.columnWidth = 21;
  s.getRange("H:H").format.columnWidth = 34;
  s.getRange("I:J").format.columnWidth = 18;
  s.getRange("K:U").format.columnWidth = 20;
  s.getRange("K:K").format.columnWidth = 58;
  s.getRange(`${excelCol(scoreHeaders.length)}:${excelCol(scoreHeaders.length)}`).format.columnWidth = 38;
  s.getRange(`A6:${lastCol}6`).format.rowHeight = 48;
  s.getRange("H7:K10").format.wrapText = true;
  s.getRange(`A7:${lastCol}10`).format.autofitRows();
  s.getRange("AD:AD").format.columnWidth = 30;
}

const scoreColumns = {
  id: "A", name: "B", group: "C", sector: "D", service: "E", market: "F", period: "G", benchmark: "H",
  quality: "I", construction: "J", cohort: "K",
  normStart: excelCol(normStartOneBased),
  iReg: excelCol(axisStartOneBased),
  iRisk: excelCol(axisStartOneBased + 1),
  iMarket: excelCol(axisStartOneBased + 2),
  cpii: excelCol(axisStartOneBased + 3),
  status: excelCol(axisStartOneBased + 6),
};
const scoreEndRow = 6 + capacity;

// 03_COMPARE_2
{
  const s = sheets["03_COMPARE_2"];
  title(s, "03 | 두 회사 상세 비교", "A-B 부호를 사용합니다. 국내-해외 적격 pair도 ‘역차별 가설 관련 구조적 부담격차’이며 법적·인과적 판정이 아닙니다.", "R");
  s.getRange("A4:A5").values = [["회사 A 관측 ID"], ["회사 B 관측 ID"]];
  s.getRange("B4:B5").values = [[payload.companies[0].observation_id], [payload.companies[1].observation_id]];
  s.getRange("A4:A5").format = { fill: COLORS.teal, font: { bold: true, color: COLORS.white } };
  s.getRange("B4:B5").format = { fill: COLORS.blue, font: { bold: true } };
  s.getRange("B4:B5").dataValidation = { rule: { type: "list", formula1: `INDIRECT("'01_INPUT_COMPANIES'!$A$7:$A$${6 + capacity}")` } };
  s.getRange("A7:D7").values = [["지표", "A", "B", "A-B"]];
  header(s.getRange("A7:D7"));
  s.getRange("A8:A11").values = [["CPII"], ["I_reg"], ["I_risk"], ["I_market"]];
  const companyIdRange = `${q("01_INPUT_COMPANIES")}!$A$7:$A$${6 + capacity}`;
  const scoreIdRange = `${q("91_CALC_SCORES")}!$A$7:$A$${scoreEndRow}`;
  const scoreLookup = (col, selector) => blankPreservingIndex(
    `${q("91_CALC_SCORES")}!$${col}$7:$${col}$${scoreEndRow}`,
    scoreIdRange,
    selector,
  );
  const scoreLookupNumeric = (col, selector) => numericPreservingIndex(
    `${q("91_CALC_SCORES")}!$${col}$7:$${col}$${scoreEndRow}`,
    scoreIdRange,
    selector,
  );
  const metrics = [scoreColumns.cpii, scoreColumns.iReg, scoreColumns.iRisk, scoreColumns.iMarket];
  const metricFormulas = metrics.map((col, index) => {
    const row = 8 + index;
    return [
      `=IF(OR(COUNTIF(${companyIdRange},$B$4)<>1,NOT(${eligibleStatus(scoreLookup(scoreColumns.status, "$B$4"))})),"",${scoreLookupNumeric(col, "$B$4")})`,
      `=IF(OR(COUNTIF(${companyIdRange},$B$5)<>1,NOT(${eligibleStatus(scoreLookup(scoreColumns.status, "$B$5"))})),"",${scoreLookupNumeric(col, "$B$5")})`,
      `=IF(OR($A$14<>"비교 가능",COUNT(B${row}:C${row})<>2),"",B${row}-C${row})`,
    ];
  });
  s.getRange("A8:D11").values = [["CPII", null, null, null], ["I_reg", null, null, null], ["I_risk", null, null, null], ["I_market", null, null, null]];
  s.getRange("B8:D11").formulas = metricFormulas;
  body(s.getRange("A8:D11"));
  s.getRange("B8:D11").format.numberFormat = "0.00;[Red]-0.00";
  s.getRange("A13:D13").values = [["비교상태", "Pair 유형", "결합지원", "주의"]];
  header(s.getRange("A13:D13"));
  const statusA = scoreLookup(scoreColumns.status, "$B$4");
  const statusB = scoreLookup(scoreColumns.status, "$B$5");
  const cohortA = scoreLookup(scoreColumns.cohort, "$B$4");
  const cohortB = scoreLookup(scoreColumns.cohort, "$B$5");
  const groupA = scoreLookup(scoreColumns.group, "$B$4");
  const groupB = scoreLookup(scoreColumns.group, "$B$5");
  const qualityA = scoreLookup(scoreColumns.quality, "$B$4");
  const qualityB = scoreLookup(scoreColumns.quality, "$B$5");
  const constructionA = scoreLookup(scoreColumns.construction, "$B$4");
  const constructionB = scoreLookup(scoreColumns.construction, "$B$5");
  s.getRange("A14:D14").formulas = [[
    `=IF(OR($B$4="",$B$5=""),"선택 필요",IF($B$4=$B$5,"N/A: 동일 관측 선택",IF(OR(COUNTIF(${companyIdRange},$B$4)<>1,COUNTIF(${companyIdRange},$B$5)<>1),"N/A: ID 없음/중복",IF(OR(NOT(${eligibleStatus(statusA)}),NOT(${eligibleStatus(statusB)})),"N/A: 입력 검증 실패",IF(OR(${cohortA}="",${cohortB}="",NOT(EXACT(${cohortA},${cohortB}))),"N/A: cohort 불일치","비교 가능")))))`,
    `=IF(A14<>"비교 가능","해석 불가",IF(AND(OR(AND(${groupA}="domestic",${groupB}="foreign"),AND(${groupA}="foreign",${groupB}="domestic")),OR(${qualityA}="A",${qualityA}="B",${qualityA}="SYNTHETIC"),OR(${qualityB}="A",${qualityB}="B",${qualityB}="SYNTHETIC"),OR(${constructionA}="direct",${constructionA}="derived"),OR(${constructionB}="direct",${constructionB}="derived")),"역차별 가설 관련 구조적 부담격차","구조적 부담격차"))`,
    `="10변수 결합완전 2/159"`,
    `="연구 베타·저지원 22.22%·기업 백분위 아님"`,
  ]];
  body(s.getRange("A14:D14"), COLORS.yellow);
  s.getRange("A14:D14").format.wrapText = true;
  s.getRange("A14:D14").format.rowHeight = 42;
  s.getRange("A16:I16").values = [["Feature", "하위지수", "원값 A", "원값 B", "정규화 A", "정규화 B", "가중치", "점수기여(A-B)", "역할"]];
  header(s.getRange("A16:I16"));
  const contribFormulas = [];
  for (let index = 0; index < payload.feature_config.length; index += 1) {
    const row = 17 + index;
    const configRow = 7 + index;
    contribFormulas.push([
      `=${q("92_REF_VARIABLES")}!$B$${configRow}`,
      `=${q("92_REF_VARIABLES")}!$C$${configRow}`,
      `=IF($A$14<>"비교 가능","",SUMIFS(${q("90_CALC_FEATURES")}!$E$7:$E$1006,${q("90_CALC_FEATURES")}!$B$7:$B$1006,$B$4,${q("90_CALC_FEATURES")}!$D$7:$D$1006,${q("92_REF_VARIABLES")}!$A$${configRow}))`,
      `=IF($A$14<>"비교 가능","",SUMIFS(${q("90_CALC_FEATURES")}!$E$7:$E$1006,${q("90_CALC_FEATURES")}!$B$7:$B$1006,$B$5,${q("90_CALC_FEATURES")}!$D$7:$D$1006,${q("92_REF_VARIABLES")}!$A$${configRow}))`,
      `=IF($A$14<>"비교 가능","",SUMIFS(${q("90_CALC_FEATURES")}!$I$7:$I$1006,${q("90_CALC_FEATURES")}!$B$7:$B$1006,$B$4,${q("90_CALC_FEATURES")}!$D$7:$D$1006,${q("92_REF_VARIABLES")}!$A$${configRow}))`,
      `=IF($A$14<>"비교 가능","",SUMIFS(${q("90_CALC_FEATURES")}!$I$7:$I$1006,${q("90_CALC_FEATURES")}!$B$7:$B$1006,$B$5,${q("90_CALC_FEATURES")}!$D$7:$D$1006,${q("92_REF_VARIABLES")}!$A$${configRow}))`,
      `=${q("92_REF_VARIABLES")}!$I$${configRow}`,
      `=IF(COUNT(E${row}:F${row})<>2,"",100*G${row}*(E${row}-F${row}))`,
      `=IF(COUNT(H${row})=0,"",IF(ABS(H${row})<=0.000000000001,"중립",IF(H${row}*$D$8>0,"격차 확대","격차 상쇄")))`,
    ]);
  }
  s.getRange("A17:I26").formulas = contribFormulas;
  body(s.getRange("A17:I26"));
  s.getRange("C17:H26").format.numberFormat = "0.0000;[Red]-0.0000";
  s.getRange("A28:G28").merge();
  s.getRange("A28").values = [["기여도 합 = ΔCPII (반올림 전 값으로 검증)"]];
  s.getRange("H28").formulas = [["=IF($A$14<>\"비교 가능\",\"\",SUM(H17:H26))"]];
  s.getRange("I28").formulas = [["=IF($A$14<>\"비교 가능\",\"N/A\",IF(ABS(H28-$D$8)<=0.0000000001,\"PASS\",\"CHECK\"))"]];
  body(s.getRange("A28:I28"), COLORS.paleTeal);
  s.getRange("H28").format.numberFormat = "0.0000000000";
  s.getRange("K32:L42").values = [["Feature", "기여도"], ...payload.feature_config.map((row) => [row.display_name_ko, null])];
  s.getRange("L33:L42").formulas = Array.from({ length: 10 }, (_, i) => [`=H${17 + i}`]);
  const contributionChart = s.charts.add("bar", s.getRange("K32:L42"));
  contributionChart.title = "Feature별 ΔCPII 기여도";
  contributionChart.hasLegend = false;
  contributionChart.setPosition("K2", "R15");
  s.getRange("K45:M49").values = [["지표", "A", "B"], ["CPII", null, null], ["I_reg", null, null], ["I_risk", null, null], ["I_market", null, null]];
  s.getRange("L46:M49").formulas = Array.from({ length: 4 }, (_, i) => [`=B${8 + i}`, `=C${8 + i}`]);
  const scoreChart = s.charts.add("bar", s.getRange("K45:M49"));
  scoreChart.title = "CPII 및 하위지수";
  scoreChart.hasLegend = true;
  scoreChart.setPosition("K17", "R30");
  s.freezePanes.freezeRows(3);
  s.getRange("A:A").format.columnWidth = 26;
  s.getRange("B:B").format.columnWidth = 34;
  s.getRange("C:C").format.columnWidth = 23;
  s.getRange("D:D").format.columnWidth = 32;
  s.getRange("E:I").format.columnWidth = 16;
  s.getRange("K:K").format.columnWidth = 30;
  s.getRange("L:M").format.columnWidth = 18;
  s.getRange("N:R").format.columnWidth = 13;
  s.getRange("A14:D14").format.rowHeight = 60;
  s.getRange("K32:K42").values = [["Feature"], ["유효세율"], ["인프라 결합"], ["네트워크 비용"], ["세전이익 회수"], ["조달금리"], ["투자 회수"], ["IP 자산화"], ["시장간 전이"], ["해외의존"], ["설비투자 압박"]];
  s.getRange("K32:K42").format.wrapText = true;
  s.getRange("K32:L42").format.autofitRows();
}

// 04_COMPARE_N
{
  const s = sheets["04_COMPARE_N"];
  const matrixLastCol = excelCol(9 + matrixCapacity);
  title(s, "04 | n개 회사 Cohort별 비교", "최대 100개 회사를 동일 엔진으로 계산합니다. 순위는 같은 cohort 안에서만 부여되고, 다른 cohort의 pair matrix 셀은 N/A입니다.", matrixLastCol);
  s.getRange("A6:G6").values = [["관측 ID", "회사명", "Cohort", "CPII", "Cohort 부담순위", "상태", "주의"]];
  header(s.getRange("A6:G6"));
  const rankingFormulas = [];
  const rankPartialFormulas = [];
  for (let index = 0; index < capacity; index += 1) {
    const row = 7 + index;
    const scoreRow = 7 + index;
    rankingFormulas.push([
      `=IF(${q("91_CALC_SCORES")}!A${scoreRow}="","",${q("91_CALC_SCORES")}!A${scoreRow})`,
      `=IF($A${row}="","",${q("91_CALC_SCORES")}!B${scoreRow})`,
      `=IF($A${row}="","",${q("91_CALC_SCORES")}!K${scoreRow})`,
      `=IF(OR($A${row}="",NOT(${eligibleStatus(`${q("91_CALC_SCORES")}!${scoreColumns.status}${scoreRow}`)})),"",${q("91_CALC_SCORES")}!${scoreColumns.cpii}${scoreRow})`,
      `=IF(COUNT(D${row})=0,"",1+SUM(AN${row}:AO${row})-1/2)`,
      `=IF($A${row}="","",${q("91_CALC_SCORES")}!${scoreColumns.status}${scoreRow})`,
      `=IF(A${row}="","","연구 베타 | 기업 백분위 아님")`,
    ]);
    // Scalar EXACT avoids array-formula incompatibilities between engines.
    // Two bounded sums keep every formula below Excel's 8192-character limit.
    rankPartialFormulas.push([0, 1].map((half) => {
      const start = half * 50;
      const terms = Array.from({ length: Math.min(50, capacity - start) }, (_, i) => {
        const peer = 7 + start + i;
        return `IF(AND(EXACT($C$${peer},$C${row}),ISNUMBER($D$${peer})),($D$${peer}>$D${row})+($D$${peer}=$D${row})/2,0)`;
      });
      return `=IF(COUNT($D${row})=0,"",SUM(${terms.join(",")}))`;
    }));
  }
  s.getRange(`A7:G${6 + capacity}`).formulas = rankingFormulas;
  s.getRange("AN6:AO6").values = [["순위 검산 1~50", "순위 검산 51~100"]];
  header(s.getRange("AN6:AO6"));
  s.getRange(`AN7:AO${6 + capacity}`).formulas = rankPartialFormulas;
  body(s.getRange(`AN7:AO${6 + capacity}`), COLORS.gray);
  s.getRange("AN:AO").format.columnWidth = 22;
  body(s.getRange(`A7:G${6 + capacity}`), COLORS.gray);
  s.getRange(`D7:D${6 + capacity}`).format.numberFormat = "0.00";
  s.getRange(`A6:G${6 + capacity}`).conditionalFormats.add("containsText", { text: "CHECK", format: { fill: COLORS.red } });
  const matrixStartCol = 9;
  const matrixEndCol = matrixStartCol + matrixCapacity;
  const matrixEndLetter = excelCol(matrixEndCol);
  s.getRange(`I5:${matrixEndLetter}5`).merge();
  s.getRange("I5").values = [[`Pair gap matrix (A행-B열, 화면 ${matrixCapacity}개; 초과 시 Python CSV export)`]];
  header(s.getRange(`I5:${matrixEndLetter}5`));
  s.getRange("I6").values = [["A-B"]];
  const headerFormulas = [Array.from({ length: matrixCapacity }, (_, index) => `=IF($A$${7 + index}="","",$A$${7 + index})`)];
  s.getRange(`J6:${matrixEndLetter}6`).formulas = headerFormulas;
  s.getRange(`I7:I${6 + matrixCapacity}`).formulas = Array.from({ length: matrixCapacity }, (_, index) => [`=IF($A$${7 + index}="","",$A$${7 + index})`]);
  header(s.getRange(`I6:${matrixEndLetter}6`));
  header(s.getRange(`I7:I${6 + matrixCapacity}`));
  const matrixFormulas = [];
  for (let rowIndex = 0; rowIndex < matrixCapacity; rowIndex += 1) {
    const rankingRow = 7 + rowIndex;
    const formulas = [];
    for (let colIndex = 0; colIndex < matrixCapacity; colIndex += 1) {
      const comparisonRow = 7 + colIndex;
      formulas.push(
        `=IF(OR($A${rankingRow}="",$A$${comparisonRow}=""),"",IF(COUNT($D${rankingRow},$D$${comparisonRow})<>2,"N/A:input",IF(EXACT($C${rankingRow},$C$${comparisonRow}),$D${rankingRow}-$D$${comparisonRow},"N/A:cohort")))`,
      );
    }
    matrixFormulas.push(formulas);
  }
  s.getRange(`J7:${matrixEndLetter}${6 + matrixCapacity}`).formulas = matrixFormulas;
  body(s.getRange(`J7:${matrixEndLetter}${6 + matrixCapacity}`), COLORS.gray);
  s.getRange(`J7:${matrixEndLetter}${6 + matrixCapacity}`).format.numberFormat = "0.00;[Red]-0.00";
  s.getRange(`J7:${matrixEndLetter}${6 + matrixCapacity}`).conditionalFormats.add("colorScale", { colors: ["#2563EB", "#FFFFFF", "#DC2626"], thresholds: ["min", { type: "num", value: 0 }, "max"] });
  s.freezePanes.freezeRows(6);
  s.freezePanes.freezeColumns(2);
  s.getRange("A:A").format.columnWidth = 18;
  s.getRange("B:B").format.columnWidth = 22;
  s.getRange("C:C").format.columnWidth = 60;
  s.getRange("D:F").format.columnWidth = 18;
  s.getRange("G:G").format.columnWidth = 30;
  s.getRange(`I:${matrixEndLetter}`).format.columnWidth = 13;
  s.getRange("C7:G10").format.wrapText = true;
  s.getRange("A7:G10").format.autofitRows();
}

// 05_ECON_INTERPRET
const exposureColumnByField = {
  ...Object.fromEntries(exposureFields.map((field, index) => [field, excelCol(index + 1)])),
  validation_status: "AA",
};
{
  const s = sheets["05_ECON_INTERPRET"];
  title(s, "05 | 점수차의 경제적 해석", "점수당 보편 원화계수는 없습니다. 비교·노출 검증을 통과한 채널별 조건부 상당액/시나리오만 표시하며 합계를 제공하지 않습니다.", "S");
  s.getRange("A4:A5").values = [["회사 A"], ["회사 B"]];
  s.getRange("B4:B5").formulas = [[`=${q("03_COMPARE_2")}!B4`], [`=${q("03_COMPARE_2")}!B5`]];
  s.getRange("A4:A5").format = { fill: COLORS.teal, font: { bold: true, color: COLORS.white } };
  s.getRange("B4:B5").format = { fill: COLORS.gray, font: { bold: true } };
  const exposureIds = `${q("02_INPUT_ECON_BASES")}!$A$7:$A$${6 + capacity}`;
  const companyIds = `${q("01_INPUT_COMPANIES")}!$A$7:$A$${6 + capacity}`;
  const lookup = (field, selector) => blankPreservingIndex(
    `${q("02_INPUT_ECON_BASES")}!$${exposureColumnByField[field]}$7:$${exposureColumnByField[field]}$${6 + capacity}`,
    exposureIds,
    selector,
  );
  const numericLookup = (field, selector) => numericPreservingIndex(
    `${q("02_INPUT_ECON_BASES")}!$${exposureColumnByField[field]}$7:$${exposureColumnByField[field]}$${6 + capacity}`,
    exposureIds,
    selector,
  );
  const companyLookup = (column, selector) => blankPreservingIndex(
    `${q("01_INPUT_COMPANIES")}!$${column}$7:$${column}$${6 + capacity}`,
    companyIds,
    selector,
  );
  s.getRange("C4:C5").values = [["회사 통화/연도"], ["회사 통화/연도"]];
  s.getRange("D4:D5").formulas = [
    [`=IF($B4="","",${companyLookup("I", "$B4")}&"/"&${companyLookup("J", "$B4")})`],
    [`=IF($B5="","",${companyLookup("I", "$B5")}&"/"&${companyLookup("J", "$B5")})`],
  ];
  s.getRange("E4:E5").values = [["노출 기간/계수"], ["노출 기간/계수"]];
  s.getRange("F4:F5").formulas = [
    [`=IF(COUNTIF(${exposureIds},$B4)<>1,"",${lookup("exposure_period", "$B4")}&" / "&${numericLookup("period_year_fraction", "$B4")})`],
    [`=IF(COUNTIF(${exposureIds},$B5)<>1,"",${lookup("exposure_period", "$B5")}&" / "&${numericLookup("period_year_fraction", "$B5")})`],
  ];
  s.getRange("G4:G5").values = [["노출행 검증"], ["노출행 검증"]];
  s.getRange("H4:H5").formulas = [
    [`=IF($B4="","",IF(COUNTIF(${exposureIds},$B4)=0,"MISSING",IF(COUNTIF(${exposureIds},$B4)>1,"DUPLICATE",${lookup("validation_status", "$B4")})))`],
    [`=IF($B5="","",IF(COUNTIF(${exposureIds},$B5)=0,"MISSING",IF(COUNTIF(${exposureIds},$B5)>1,"DUPLICATE",${lookup("validation_status", "$B5")})))`],
  ];
  s.getRange("I4").values = [["Pair 상태"]];
  s.getRange("J4:S5").merge();
  s.getRange("J4").formulas = [[`=${q("03_COMPARE_2")}!A14`]];
  s.getRange("C4:C5").format = { fill: COLORS.teal, font: { bold: true, color: COLORS.white } };
  s.getRange("E4:E5").format = { fill: COLORS.teal, font: { bold: true, color: COLORS.white } };
  s.getRange("G4:G5").format = { fill: COLORS.teal, font: { bold: true, color: COLORS.white } };
  s.getRange("I4").format = { fill: COLORS.teal, font: { bold: true, color: COLORS.white } };
  body(s.getRange("D4:D5"), COLORS.gray);
  body(s.getRange("F4:F5"), COLORS.gray);
  body(s.getRange("H4:H5"), COLORS.gray);
  body(s.getRange("J4:S5"), COLORS.gray);
  const headers = ["Feature", "CPII 기여점", "해석유형", "중복군", "경제기준", "원값차 A-B", "부담방향 차이", "통화", "가용상태", "공통노출 Low", "Base", "High", "공통규모 금액 Low", "Base", "High", "실제규모 차이 Low", "Base", "High", "주의"];
  s.getRange("A7:S7").values = [headers];
  header(s.getRange("A7:S7"));
  const formulas = [];
  for (let index = 0; index < payload.feature_config.length; index += 1) {
    const config = payload.feature_config[index];
    const row = 8 + index;
    const configRow = 7 + index;
    const baseName = config.economic_base;
    const enabled = config.bridge_status === "enabled";
    const rawA = `SUMIFS(${q("90_CALC_FEATURES")}!$E$7:$E$1006,${q("90_CALC_FEATURES")}!$B$7:$B$1006,$B$4,${q("90_CALC_FEATURES")}!$D$7:$D$1006,${q("92_REF_VARIABLES")}!$A$${configRow})`;
    const rawB = `SUMIFS(${q("90_CALC_FEATURES")}!$E$7:$E$1006,${q("90_CALC_FEATURES")}!$B$7:$B$1006,$B$5,${q("90_CALC_FEATURES")}!$D$7:$D$1006,${q("92_REF_VARIABLES")}!$A$${configRow})`;
    const commonExposure = (caseName) => `(${numericLookup(`${baseName}_${caseName}`, "$B$4")}+${numericLookup(`${baseName}_${caseName}`, "$B$5")})/2`;
    const periodCommon = `(${numericLookup("period_year_fraction", "$B$4")}+${numericLookup("period_year_fraction", "$B$5")})/2`;
    const conversionCommon = (caseName) => `(${numericLookup(`scenario_conversion_rate_${caseName}`, "$B$4")}+${numericLookup(`scenario_conversion_rate_${caseName}`, "$B$5")})/2`;
    const amountCommon = (caseName) => {
      if (!enabled) return '=""';
      const multiplier = config.formula_code === "directional_gap_times_base_and_period"
        ? `*${periodCommon}`
        : config.formula_code === "directional_gap_times_base_and_conversion"
          ? `*${conversionCommon(caseName)}`
          : "";
      return `=IF(LEFT(I${row},9)<>"AVAILABLE","",G${row}*${commonExposure(caseName)}${multiplier})`;
    };
    const actualAmount = (caseName) => {
      if (!enabled) return '=""';
      const baseA = numericLookup(`${baseName}_${caseName}`, "$B$4");
      const baseB = numericLookup(`${baseName}_${caseName}`, "$B$5");
      let multiplierA = "";
      let multiplierB = "";
      if (config.formula_code === "directional_gap_times_base_and_period") {
        multiplierA = `*${numericLookup("period_year_fraction", "$B$4")}`;
        multiplierB = `*${numericLookup("period_year_fraction", "$B$5")}`;
      } else if (config.formula_code === "directional_gap_times_base_and_conversion") {
        multiplierA = `*${numericLookup(`scenario_conversion_rate_${caseName}`, "$B$4")}`;
        multiplierB = `*${numericLookup(`scenario_conversion_rate_${caseName}`, "$B$5")}`;
      }
      return `=IF(LEFT(I${row},9)<>"AVAILABLE","",${config.direction_code}*((${rawA})*${baseA}${multiplierA}-(${rawB})*${baseB}${multiplierB}))`;
    };
    const baseMissing = enabled
      ? `OR(${["low", "base", "high"].flatMap((caseName) => [numericLookup(`${baseName}_${caseName}`, "$B$4"), numericLookup(`${baseName}_${caseName}`, "$B$5")]).map((term) => `COUNT(${term})=0`).join(",")})`
      : "FALSE";
    const conversionMissing = config.formula_code === "directional_gap_times_base_and_conversion"
      ? `OR(${["low", "base", "high"].flatMap((caseName) => [numericLookup(`scenario_conversion_rate_${caseName}`, "$B$4"), numericLookup(`scenario_conversion_rate_${caseName}`, "$B$5")]).map((term) => `COUNT(${term})=0`).join(",")})`
      : "FALSE";
    const availability = !enabled
      ? `=IF(${q("03_COMPARE_2")}!$A$14<>"비교 가능","PAIR NOT COMPARABLE","NON-MONETIZABLE")`
      : `=IF(${q("03_COMPARE_2")}!$A$14<>"비교 가능","PAIR NOT COMPARABLE",IF(OR(COUNTIF(${exposureIds},$B$4)=0,COUNTIF(${exposureIds},$B$5)=0),"MISSING EXPOSURE",IF(OR(COUNTIF(${exposureIds},$B$4)<>1,COUNTIF(${exposureIds},$B$5)<>1),"DUPLICATE EXPOSURE ID",IF(OR($H$4<>"READY",$H$5<>"READY"),"EXPOSURE INPUT ERROR",IF($D$4<>$D$5,"CURRENCY/YEAR MISMATCH",IF($F$4<>$F$5,"TIME BASIS MISMATCH",IF(${baseMissing},"MISSING EXPOSURE",IF(${conversionMissing},"MISSING ASSUMPTION",IF(ABS(B${row})<=0.000000000001,"AVAILABLE - CONTEXT ONLY","AVAILABLE - DO NOT SUM")))))))))`;
    const assumptionNote = config.formula_code === "directional_gap_times_base_and_conversion"
      ? " | 명시적 전환율 가정 필요"
      : config.formula_code === "directional_gap_times_base_and_period"
        ? " | 동일 기간·연환산계수 필요"
        : "";
    formulas.push([
      `=${q("92_REF_VARIABLES")}!$B$${configRow}`,
      `=${q("03_COMPARE_2")}!$H$${17 + index}`,
      `=${q("92_REF_VARIABLES")}!$K$${configRow}`,
      `=${q("92_REF_VARIABLES")}!$N$${configRow}`,
      `=${q("92_REF_VARIABLES")}!$M$${configRow}`,
      `=IF(${q("03_COMPARE_2")}!$A$14<>"비교 가능","",(${rawA})-(${rawB}))`,
      `=IF(COUNT(F${row})=0,"",${config.direction_code}*F${row})`,
      enabled ? `=${lookup("currency", "$B$4")}` : '=""',
      availability,
      enabled ? `=IF(LEFT(I${row},9)<>"AVAILABLE","",${commonExposure("low")})` : '=""',
      enabled ? `=IF(LEFT(I${row},9)<>"AVAILABLE","",${commonExposure("base")})` : '=""',
      enabled ? `=IF(LEFT(I${row},9)<>"AVAILABLE","",${commonExposure("high")})` : '=""',
      amountCommon("low"), amountCommon("base"), amountCommon("high"),
      actualAmount("low"), actualAmount("base"), actualAmount("high"),
      `=IF(${q("03_COMPARE_2")}!$A$14<>"비교 가능","비교 불가",IF(ABS(B${row})<=0.000000000001,"선택된 ΔCPII 기여점 0: 원단위 맥락만 제공 | ","")&${q("92_REF_VARIABLES")}!$P$${configRow}&${excelText(assumptionNote)})`,
    ]);
  }
  s.getRange("A8:S17").formulas = formulas;
  body(s.getRange("A8:S17"));
  s.getRange("B8:B17").format.numberFormat = "0.000000;[Red]-0.000000";
  s.getRange("F8:G17").format.numberFormat = "0.000000;[Red]-0.000000";
  s.getRange("J8:R17").format.numberFormat = "#,##0;[Red]-#,##0";
  s.getRange("I8:I17").conditionalFormats.add("containsText", { text: "AVAILABLE", format: { fill: COLORS.green, font: { color: COLORS.greenText } } });
  s.getRange("I8:I17").conditionalFormats.add("containsText", { text: "MISMATCH", format: { fill: COLORS.red, font: { color: COLORS.redText } } });
  s.getRange("I8:I17").conditionalFormats.add("containsText", { text: "ERROR", format: { fill: COLORS.red, font: { color: COLORS.redText } } });
  s.getRange("I8:I17").conditionalFormats.add("containsText", { text: "PAIR NOT", format: { fill: COLORS.red, font: { color: COLORS.redText } } });
  s.getRange("A20:S23").merge();
  s.getRange("A20").values = [["합계 미제공: network/infra/outflow, funding/IP, 두 recovery 변수는 원천 또는 경제 의미가 겹칠 수 있고, 조건부 회계·성과 상당액과 시나리오가 혼재합니다. 실제규모 A-B는 구조적 rate 차이뿐 아니라 회사규모 차이도 포함합니다."]];
  s.getRange("A20:S23").format = { fill: COLORS.red, font: { color: COLORS.redText, bold: true }, wrapText: true };
  s.freezePanes.freezeRows(7);
  s.getRange("A:A").format.columnWidth = 28;
  s.getRange("B:B").format.columnWidth = 16;
  s.getRange("C:C").format.columnWidth = 36;
  s.getRange("D:E").format.columnWidth = 28;
  s.getRange("F:H").format.columnWidth = 18;
  s.getRange("I:I").format.columnWidth = 31;
  s.getRange("J:R").format.columnWidth = 18;
  s.getRange("S:S").format.columnWidth = 64;
  s.getRange("A7:S7").format.rowHeight = 42;
  s.getRange("A8:E17").format.wrapText = true;
  s.getRange("I8:I17").format.wrapText = true;
  s.getRange("S8:S17").format.wrapText = true;
  s.getRange("A8:S17").format.autofitRows();
}

// 06_SENSITIVITY
{
  const s = sheets["06_SENSITIVITY"];
  title(s, "06 | 방법론 사양 민감도 (입력범위 미포함)", "이 시트는 4개 방법론 사양만 비교합니다. feature low/base/high 입력 불확실성은 평가하지 않으므로 종합 안정성 결론으로 사용하지 마십시오.", "H");
  s.getRange("A4:B5").values = [["회사 A", null], ["회사 B", null]];
  s.getRange("B4:B5").formulas = [[`=${q("03_COMPARE_2")}!B4`], [`=${q("03_COMPARE_2")}!B5`]];
  s.getRange("A4:A5").format = { fill: COLORS.teal, font: { color: COLORS.white, bold: true } };
  body(s.getRange("B4:B5"), COLORS.gray);
  s.getRange("A7:E7").values = [["사양", "A 점수", "B 점수", "ΔCPII(A-B)", "의미"]];
  header(s.getRange("A7:E7"));
  s.getRange("A8:A11").values = [["Baseline full research beta"], ["Top weights 40/40/20"], ["저지원 feature 제외"], ["중복채널 축소"]];
  const idx = (scoreCol, selector) => numericPreservingIndex(
    `${q("91_CALC_SCORES")}!$${scoreCol}$7:$${scoreCol}$${scoreEndRow}`,
    `${q("91_CALC_SCORES")}!$A$7:$A$${scoreEndRow}`,
    selector,
  );
  const normCol = (featureIndex) => excelCol(normStartOneBased + featureIndex);
  const scoreNorm = (featureIndex, selector) => idx(normCol(featureIndex), selector);
  const baseA = idx(scoreColumns.cpii, "$B$4");
  const baseB = idx(scoreColumns.cpii, "$B$5");
  const weighted = (selector) => `0.4*${idx(scoreColumns.iReg, selector)}+0.4*${idx(scoreColumns.iRisk, selector)}+0.2*${idx(scoreColumns.iMarket, selector)}`;
  const lowSupportExcluded = (selector) => `(100*AVERAGE(${scoreNorm(0, selector)},${scoreNorm(1, selector)},${scoreNorm(2, selector)})+100*AVERAGE(${scoreNorm(3, selector)},${scoreNorm(4, selector)},${scoreNorm(5, selector)},${scoreNorm(6, selector)})+100*${scoreNorm(9, selector)})/3`;
  const overlapReduced = (selector) => `(100*AVERAGE(${scoreNorm(0, selector)},${scoreNorm(2, selector)})+100*AVERAGE(${scoreNorm(4, selector)},${scoreNorm(5, selector)},${scoreNorm(6, selector)})+100*AVERAGE(${scoreNorm(7, selector)},${scoreNorm(8, selector)}) )/3`;
  const specExpressions = [
    [baseA, baseB, "현행 10개 feature; 저지원 22.22%"],
    [weighted("$B$4"), weighted("$B$5"), "상위축 가중치 변경"],
    [lowSupportExcluded("$B$4"), lowSupportExcluded("$B$5"), "cross-market·foreign dependency 제외"],
    [overlapReduced("$B$4"), overlapReduced("$B$5"), "infra·outflow·cashflow recovery 제외"],
  ];
  s.getRange("B8:E11").formulas = specExpressions.map((row, index) => [
    `=IF(${q("03_COMPARE_2")}!$A$14<>"비교 가능","",${row[0]})`,
    `=IF(${q("03_COMPARE_2")}!$A$14<>"비교 가능","",${row[1]})`,
    `=IF(COUNT(B${8 + index}:C${8 + index})<>2,"",B${8 + index}-C${8 + index})`,
    `="${row[2]}"`,
  ]);
  body(s.getRange("A8:E11"));
  s.getRange("B8:D11").format.numberFormat = "0.00;[Red]-0.00";
  s.getRange("A13:B21").values = [
    ["판정 항목", "결과"],
    ["방법론 사양 최소", null],
    ["방법론 사양 최대", null],
    ["방법론 사양 내 부호", null],
    ["방법론 사양 해석", null],
    ["입력범위 민감도", "미평가 — 이 시트에는 feature low/base/high 없음"],
    ["종합 안정성 결론", "제공하지 않음 — Python --feature-ranges 분석 필요"],
    ["기존 대체사양 중앙 절대차", 1.0985372963],
    ["기존 대체사양 평균 절대차", 2.0659532773],
  ];
  header(s.getRange("A13:B13"));
  s.getRange("B14:B17").formulas = [
    ["=IF(COUNT(D8:D11)=4,MIN(D8:D11),\"\")"],
    ["=IF(COUNT(D8:D11)=4,MAX(D8:D11),\"\")"],
    ["=IF(COUNT(B14:B15)<>2,\"비교 불가\",IF(AND(B14>0.000000000001,B15>0.000000000001),\"양(+) 안정\",IF(AND(B14<-0.000000000001,B15<-0.000000000001),\"음(-) 안정\",\"부호 불안정\")))"],
    ["=IF(COUNT(B14:B15)<>2,\"비교 불가\",IF(OR(AND(B14>0.000000000001,B15>0.000000000001),AND(B14<-0.000000000001,B15<-0.000000000001)),\"방법 사양 내 방향 유지(종합판정 아님)\",\"방법 사양 내 차이 불명확\"))"],
  ];
  body(s.getRange("A14:B21"), COLORS.gray);
  s.getRange("B14:B15").format.numberFormat = "0.00;[Red]-0.00";
  s.getRange("B17").conditionalFormats.add("containsText", { text: "불명확", format: { fill: COLORS.red, font: { color: COLORS.redText, bold: true } } });
  s.getRange("D13:H21").merge();
  s.getRange("D13").values = [["주의: 이 workbook의 최소·최대는 4개 방법론 사양만 반영합니다. 입력·측정 불확실성은 별도 feature range CSV와 Python --feature-ranges로 평가하십시오. 두 범위 모두 결정론적 민감도이며 확률, 신뢰구간, 통계적 유의성 또는 경험적 pair-gap 백분위가 아닙니다."]];
  s.getRange("D13:H21").format = { fill: COLORS.yellow, wrapText: true, font: { color: COLORS.redText } };
  s.getRange("A:H").format.columnWidth = 21;
}

// 99_QA_AUDIT
{
  const s = sheets["99_QA_AUDIT"];
  title(s, "99 | QA·감사추적", "FAIL은 확인 필요. 예시 변경에 따른 검증 제외는 입력 오류와 구별. 수식은 반올림 전 값으로 비교합니다.", "H");
  s.getRange("A6:D6").values = [["검사", "관측/값", "기준", "결과"]];
  header(s.getRange("A6:D6"));
  const diffCol = excelCol(axisStartOneBased + 5);
  const calcStatusCol = excelCol(axisStartOneBased + 6);
  const calcStatusRange = `${q("91_CALC_SCORES")}!$${calcStatusCol}$7:$${calcStatusCol}$${6 + capacity}`;
  const goldenStatusCells = Array.from(
    { length: payload.expected_scores.length },
    (_, index) => `${q("91_CALC_SCORES")}!$${calcStatusCol}$${7 + index}`,
  );
  s.getRange("A7:C18").values = [
    ["Python parity 최대 절대오차", null, "<=1E-10"],
    ["원본예시 대조 가능 행수", null, "기본 입력 4행"],
    ["선택 pair 기여도 잔차", null, "<=1E-10"],
    ["Anchor version", payload.metadata.anchor_version, payload.metadata.anchor_version],
    ["Method version", payload.metadata.method_version, payload.metadata.method_version],
    ["저지원 유효가중치", payload.metadata.low_support_effective_weight, "22.22%"],
    ["10-feature 결합완전", payload.metadata.joint_complete_reference_count, "공개·제한"],
    ["경제금액 총합", "미계산", "never_auto_sum"],
    ["기업/Pair 경험적 백분위", "N/A", "insufficient_joint_reference_support"],
    ["사용자 회사입력 차단행", null, "0"],
    ["경제 노출입력 오류행", null, "0"],
    ["선택 pair 상태", null, "비교 가능"],
  ];
  s.getRange("B7").formulas = [[`=IF(B8=0,"",MAX(${q("91_CALC_SCORES")}!$${diffCol}$7:$${diffCol}$106))`]];
  s.getRange("B8").formulas = [[`=COUNT(${q("91_CALC_SCORES")}!$Z$7:$Z$106)`]];
  s.getRange("B9").formulas = [[`=IF(${q("03_COMPARE_2")}!$A$14<>"비교 가능","",ABS(${q("03_COMPARE_2")}!$H$28-${q("03_COMPARE_2")}!$D$8))`]];
  s.getRange("B16").formulas = [[`=COUNTA(${q("01_INPUT_COMPANIES")}!$A$7:$A$${6 + capacity})-COUNTIFS(${calcStatusRange},">=PASS",${calcStatusRange},"<PAST")-COUNTIFS(${calcStatusRange},">=READY",${calcStatusRange},"<READZ")`]];
  s.getRange("B17").formulas = [[`=COUNTA(${q("02_INPUT_ECON_BASES")}!$A$7:$A$${6 + capacity})-COUNTIF(${q("02_INPUT_ECON_BASES")}!$AA$7:$AA$${6 + capacity},"READY")`]];
  s.getRange("B18").formulas = [[`=${q("03_COMPARE_2")}!$A$14`]];
  const resultFormulas = [
    "=IF(B8=0,\"예시 검증 제외\",IF(B7<=0.0000000001,\"PASS\",\"FAIL\"))",
    "=IF(B8=4,\"PASS\",\"예시 변경/입력 확인\")",
    "=IF(COUNT(B9)=0,\"비교 불가\",IF(B9<=0.0000000001,\"PASS\",\"FAIL\"))",
    "=IF(B10=C10,\"PASS\",\"FAIL\")",
    "=IF(B11=C11,\"PASS\",\"FAIL\")",
    "=IF(ABS(B12-2/9)<=0.0000000001,\"PASS\",\"FAIL\")",
    "=IF(B13=2,\"PASS\",\"FAIL\")",
    "=IF(B14=\"미계산\",\"PASS\",\"FAIL\")",
    "=IF(B15=\"N/A\",\"PASS\",\"FAIL\")",
    "=IF(B16=0,\"PASS\",\"FAIL\")",
    "=IF(B17=0,\"PASS\",\"FAIL\")",
    "=IF(B18=C18,\"PASS\",\"FAIL\")",
  ];
  s.getRange("D7:D18").formulas = resultFormulas.map((formula) => [formula]);
  body(s.getRange("A7:D18"), COLORS.gray);
  s.getRange("B7:B9").format.numberFormat = "0.000000000000";
  s.getRange("B12").format.numberFormat = "0.00%";
  s.getRange("D7:D18").conditionalFormats.add("containsText", { text: "PASS", format: { fill: COLORS.green, font: { color: COLORS.greenText, bold: true } } });
  s.getRange("D7:D18").conditionalFormats.add("containsText", { text: "FAIL", format: { fill: COLORS.red, font: { color: COLORS.redText, bold: true } } });
  s.getRange("A21:H25").merge();
  s.getRange("A21").values = [[`Source hashes: ${Object.entries(payload.source_hashes).map(([key, value]) => `${key}=${value}`).join(" | ")}`]];
  s.getRange("A21:H25").format = { fill: COLORS.gray, wrapText: true, font: { size: 9, color: COLORS.darkGray } };
  s.getRange("A:A").format.columnWidth = 34;
  s.getRange("B:C").format.columnWidth = 44;
  s.getRange("D:D").format.columnWidth = 16;
  s.getRange("E:H").format.columnWidth = 22;
  s.getRange("A7:C18").format.wrapText = true;
  s.getRange("A7:D18").format.autofitRows();
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
process.stdout.write(`WROTE artifact-tool workbook: ${outputPath}\n`);
